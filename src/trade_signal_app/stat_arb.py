from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import statistics

from .archive_loader import load_public_data_klines
from .backtest import archive_key, resolve_archive_paths
from .models import Candlestick
from .tradingview_data import load_tradingview_csv


@dataclass(frozen=True)
class PairStatArbConfig:
    lookback_bars: int = 120
    entry_z: float = 2.0
    exit_z: float = 0.4
    stop_z: float = 3.5
    max_holding_bars: int = 48
    min_correlation: float = 0.65
    max_hedge_ratio: float = 3.0
    notional_per_leg: float = 1000.0
    initial_equity: float = 10_000.0
    fee_bps_per_leg: float = 10.0
    slippage_bps_per_leg: float = 2.0


@dataclass(frozen=True)
class AlignedPairBar:
    open_time: datetime
    close_time: datetime
    open_a: float
    close_a: float
    open_b: float
    close_b: float


@dataclass(frozen=True)
class PairSignalState:
    hedge_ratio: float
    intercept: float
    correlation: float
    spread_mean: float
    spread_std: float
    z_score: float
    half_life_bars: float | None


@dataclass(frozen=True)
class PairStatArbTrade:
    direction: str
    signal_at: datetime
    opened_at: datetime
    closed_at: datetime
    hedge_ratio: float
    entry_z: float
    exit_z: float
    entry_price_a: float
    entry_price_b: float
    exit_price_a: float
    exit_price_b: float
    quantity_a: float
    quantity_b: float
    gross_pnl: float
    costs: float
    net_pnl: float
    return_pct: float
    bars_held: int
    exit_reason: str


@dataclass(frozen=True)
class PairEquityPoint:
    timestamp: datetime
    equity: float
    drawdown_pct: float


@dataclass(frozen=True)
class PairStatArbReport:
    strategy: str
    research_only: bool
    symbol_a: str
    symbol_b: str
    interval: str
    aligned_bars: int
    sample_start: datetime
    sample_end: datetime
    config: PairStatArbConfig
    diagnostics: dict[str, object]
    trades: list[PairStatArbTrade]
    equity_curve: list[PairEquityPoint]
    metrics: dict[str, float | int]
    warnings: list[str]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_config(config: PairStatArbConfig) -> None:
    if config.lookback_bars < 30:
        raise ValueError("lookback_bars must be at least 30.")
    if config.entry_z <= 0:
        raise ValueError("entry_z must be positive.")
    if config.exit_z < 0 or config.exit_z >= config.entry_z:
        raise ValueError("exit_z must be non-negative and lower than entry_z.")
    if config.stop_z <= config.entry_z:
        raise ValueError("stop_z must be greater than entry_z.")
    if config.max_holding_bars < 1:
        raise ValueError("max_holding_bars must be positive.")
    if not 0 <= config.min_correlation <= 1:
        raise ValueError("min_correlation must be between 0 and 1.")
    if config.max_hedge_ratio <= 0:
        raise ValueError("max_hedge_ratio must be positive.")
    if config.notional_per_leg <= 0 or config.initial_equity <= 0:
        raise ValueError("notional_per_leg and initial_equity must be positive.")
    if config.fee_bps_per_leg < 0 or config.slippage_bps_per_leg < 0:
        raise ValueError("fees and slippage cannot be negative.")


def align_pair_candles(
    candles_a: list[Candlestick],
    candles_b: list[Candlestick],
) -> list[AlignedPairBar]:
    by_time_b = {_as_utc(candle.open_time): candle for candle in candles_b}
    aligned: list[AlignedPairBar] = []
    for candle_a in candles_a:
        candle_b = by_time_b.get(_as_utc(candle_a.open_time))
        if candle_b is None:
            continue
        prices = (
            candle_a.open_price,
            candle_a.close_price,
            candle_b.open_price,
            candle_b.close_price,
        )
        if any(price <= 0 or not math.isfinite(price) for price in prices):
            continue
        aligned.append(
            AlignedPairBar(
                open_time=_as_utc(candle_a.open_time),
                close_time=max(_as_utc(candle_a.close_time), _as_utc(candle_b.close_time)),
                open_a=candle_a.open_price,
                close_a=candle_a.close_price,
                open_b=candle_b.open_price,
                close_b=candle_b.close_price,
            )
        )
    return sorted(aligned, key=lambda item: item.open_time)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ols(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return 0.0, 0.0
    mean_x = _mean(x_values)
    mean_y = _mean(y_values)
    variance_x = sum((value - mean_x) ** 2 for value in x_values)
    if variance_x <= 1e-18:
        return 0.0, mean_y
    covariance = sum(
        (x_value - mean_x) * (y_value - mean_y)
        for x_value, y_value in zip(x_values, y_values)
    )
    beta = covariance / variance_x
    return beta, mean_y - beta * mean_x


def _correlation(x_values: list[float], y_values: list[float]) -> float:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return 0.0
    mean_x = _mean(x_values)
    mean_y = _mean(y_values)
    covariance = sum(
        (x_value - mean_x) * (y_value - mean_y)
        for x_value, y_value in zip(x_values, y_values)
    )
    variance_x = sum((value - mean_x) ** 2 for value in x_values)
    variance_y = sum((value - mean_y) ** 2 for value in y_values)
    denominator = math.sqrt(variance_x * variance_y)
    if denominator <= 1e-18:
        return 0.0
    return max(-1.0, min(1.0, covariance / denominator))


def _half_life_bars(spreads: list[float]) -> float | None:
    if len(spreads) < 3:
        return None
    lagged = spreads[:-1]
    changes = [current - previous for previous, current in zip(spreads, spreads[1:])]
    slope, _ = _ols(lagged, changes)
    if slope >= -1e-9:
        return None
    value = -math.log(2) / slope
    return value if math.isfinite(value) and value > 0 else None


def _signal_state(
    aligned: list[AlignedPairBar],
    index: int,
    lookback_bars: int,
) -> PairSignalState | None:
    start = index - lookback_bars + 1
    if start < 0:
        return None
    window = aligned[start : index + 1]
    log_a = [math.log(bar.close_a) for bar in window]
    log_b = [math.log(bar.close_b) for bar in window]
    hedge_ratio, intercept = _ols(log_b, log_a)
    spreads = [
        value_a - (intercept + hedge_ratio * value_b)
        for value_a, value_b in zip(log_a, log_b)
    ]
    spread_mean = _mean(spreads)
    spread_std = statistics.pstdev(spreads)
    if spread_std <= 1e-12:
        z_score = 0.0
    else:
        z_score = (spreads[-1] - spread_mean) / spread_std
    return PairSignalState(
        hedge_ratio=hedge_ratio,
        intercept=intercept,
        correlation=_correlation(log_a, log_b),
        spread_mean=spread_mean,
        spread_std=spread_std,
        z_score=z_score,
        half_life_bars=_half_life_bars(spreads),
    )


def _exit_signal(
    *,
    direction: int,
    z_score: float,
    bars_held: int,
    config: PairStatArbConfig,
) -> str:
    if abs(z_score) <= config.exit_z:
        return "mean_reversion"
    if direction > 0 and z_score <= -config.stop_z:
        return "z_stop"
    if direction < 0 and z_score >= config.stop_z:
        return "z_stop"
    if bars_held >= config.max_holding_bars:
        return "max_holding"
    return ""


def _max_drawdown_pct(equities: list[float]) -> float:
    peak = equities[0] if equities else 0.0
    maximum = 0.0
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, ((peak - equity) / peak) * 100)
    return maximum


def _diagnostics(
    aligned: list[AlignedPairBar],
    config: PairStatArbConfig,
) -> dict[str, object]:
    state = _signal_state(aligned, len(aligned) - 1, min(config.lookback_bars, len(aligned)))
    if state is None:
        return {}
    return {
        "hedge_ratio": round(state.hedge_ratio, 8),
        "intercept": round(state.intercept, 8),
        "correlation": round(state.correlation, 8),
        "spread_mean": round(state.spread_mean, 8),
        "spread_std": round(state.spread_std, 8),
        "latest_z_score": round(state.z_score, 8),
        "half_life_bars": None if state.half_life_bars is None else round(state.half_life_bars, 4),
        "correlation_passed": state.correlation >= config.min_correlation,
        "hedge_ratio_passed": 0 < state.hedge_ratio <= config.max_hedge_ratio,
        "method": "rolling_log_ols_zscore",
    }


def run_pair_stat_arb_backtest(
    *,
    symbol_a: str,
    symbol_b: str,
    interval: str,
    candles_a: list[Candlestick],
    candles_b: list[Candlestick],
    config: PairStatArbConfig | None = None,
) -> PairStatArbReport:
    config = config or PairStatArbConfig()
    _validate_config(config)
    if symbol_a.upper() == symbol_b.upper():
        raise ValueError("Pair symbols must be different.")
    aligned = align_pair_candles(candles_a, candles_b)
    minimum_bars = config.lookback_bars + config.max_holding_bars + 2
    if len(aligned) < minimum_bars:
        raise ValueError(
            f"Not enough aligned candles for pair backtest: need {minimum_bars}, got {len(aligned)}."
        )

    cost_rate = (config.fee_bps_per_leg + config.slippage_bps_per_leg) / 10_000
    trades: list[PairStatArbTrade] = []
    equity = config.initial_equity
    equity_values = [equity]
    equity_curve = [
        PairEquityPoint(
            timestamp=aligned[config.lookback_bars - 1].close_time,
            equity=equity,
            drawdown_pct=0.0,
        )
    ]
    skipped_low_correlation = 0
    skipped_hedge_ratio = 0
    index = config.lookback_bars - 1
    last_signal_index = len(aligned) - 2

    while index <= last_signal_index:
        state = _signal_state(aligned, index, config.lookback_bars)
        if state is None or abs(state.z_score) < config.entry_z:
            index += 1
            continue
        if state.correlation < config.min_correlation:
            skipped_low_correlation += 1
            index += 1
            continue
        if state.hedge_ratio <= 0 or state.hedge_ratio > config.max_hedge_ratio:
            skipped_hedge_ratio += 1
            index += 1
            continue

        direction = 1 if state.z_score <= -config.entry_z else -1
        entry_index = index + 1
        entry_bar = aligned[entry_index]
        quantity_a = config.notional_per_leg / entry_bar.open_a
        notional_b = config.notional_per_leg * state.hedge_ratio
        quantity_b = notional_b / entry_bar.open_b
        entry_gross_notional = config.notional_per_leg + notional_b
        entry_cost = entry_gross_notional * cost_rate
        exit_index = min(entry_index + config.max_holding_bars, len(aligned) - 1)
        exit_state = state
        exit_reason = "max_holding"

        for mark_index in range(entry_index, min(entry_index + config.max_holding_bars, len(aligned) - 1)):
            candidate = _signal_state(aligned, mark_index, config.lookback_bars)
            if candidate is None:
                continue
            bars_held = mark_index - entry_index + 1
            reason = _exit_signal(
                direction=direction,
                z_score=candidate.z_score,
                bars_held=bars_held,
                config=config,
            )
            if reason:
                exit_index = min(mark_index + 1, len(aligned) - 1)
                exit_state = candidate
                exit_reason = reason
                break

        exit_bar = aligned[exit_index]
        pnl_a = direction * quantity_a * (exit_bar.open_a - entry_bar.open_a)
        pnl_b = -direction * quantity_b * (exit_bar.open_b - entry_bar.open_b)
        gross_pnl = pnl_a + pnl_b
        exit_gross_notional = quantity_a * exit_bar.open_a + quantity_b * exit_bar.open_b
        costs = entry_cost + exit_gross_notional * cost_rate
        net_pnl = gross_pnl - costs
        equity += net_pnl
        equity_values.append(equity)
        peak = max(equity_values)
        drawdown_pct = ((peak - equity) / peak) * 100 if peak > 0 else 0.0
        trades.append(
            PairStatArbTrade(
                direction="long_spread" if direction > 0 else "short_spread",
                signal_at=aligned[index].close_time,
                opened_at=entry_bar.open_time,
                closed_at=exit_bar.open_time,
                hedge_ratio=state.hedge_ratio,
                entry_z=state.z_score,
                exit_z=exit_state.z_score,
                entry_price_a=entry_bar.open_a,
                entry_price_b=entry_bar.open_b,
                exit_price_a=exit_bar.open_a,
                exit_price_b=exit_bar.open_b,
                quantity_a=quantity_a,
                quantity_b=quantity_b,
                gross_pnl=gross_pnl,
                costs=costs,
                net_pnl=net_pnl,
                return_pct=(net_pnl / entry_gross_notional) * 100,
                bars_held=max(1, exit_index - entry_index),
                exit_reason=exit_reason,
            )
        )
        equity_curve.append(
            PairEquityPoint(
                timestamp=exit_bar.open_time,
                equity=equity,
                drawdown_pct=drawdown_pct,
            )
        )
        index = max(index + 1, exit_index)

    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl < 0]
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))
    warnings: list[str] = [
        "Research backtest only; rolling OLS diagnostics are not proof of stable cointegration.",
        "Signals are confirmed at close and filled at the next aligned open.",
    ]
    if skipped_low_correlation:
        warnings.append(f"Skipped {skipped_low_correlation} entry signals below the correlation threshold.")
    if skipped_hedge_ratio:
        warnings.append(f"Skipped {skipped_hedge_ratio} entry signals with an invalid hedge ratio.")
    if not trades:
        warnings.append("No qualifying pair trades were generated for the selected parameters.")

    return PairStatArbReport(
        strategy="pair_stat_arb",
        research_only=True,
        symbol_a=symbol_a.upper(),
        symbol_b=symbol_b.upper(),
        interval=interval,
        aligned_bars=len(aligned),
        sample_start=aligned[0].open_time,
        sample_end=aligned[-1].close_time,
        config=config,
        diagnostics=_diagnostics(aligned, config),
        trades=trades,
        equity_curve=equity_curve,
        metrics={
            "trade_count": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round((len(wins) / len(trades)) * 100, 4) if trades else 0.0,
            "gross_pnl": round(sum(trade.gross_pnl for trade in trades), 8),
            "costs": round(sum(trade.costs for trade in trades), 8),
            "net_pnl": round(sum(trade.net_pnl for trade in trades), 8),
            "total_return_pct": round(((equity - config.initial_equity) / config.initial_equity) * 100, 8),
            "max_drawdown_pct": round(_max_drawdown_pct(equity_values), 8),
            "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
            "average_trade_return_pct": round(_mean([trade.return_pct for trade in trades]), 8),
            "average_holding_bars": round(_mean([float(trade.bars_held) for trade in trades]), 4),
        },
        warnings=warnings,
    )


def _stat_arb_archive_key(path: Path) -> tuple[str, str]:
    if path.suffix.lower() == ".csv":
        parts = path.stem.split("_")
        if len(parts) >= 3 and parts[-1] and parts[-1][:-1].isdigit() and parts[-1][-1] in "mhdwM":
            return parts[-2].upper(), parts[-1]
    return archive_key(path)


def _merge_stat_arb_candles(paths: list[Path], interval: str) -> list[Candlestick]:
    merged: dict[datetime, Candlestick] = {}
    for path in sorted(paths):
        candles = (
            load_tradingview_csv(path, interval=interval)
            if path.suffix.lower() == ".csv"
            else load_public_data_klines(path)
        )
        for candle in candles:
            merged[_as_utc(candle.open_time)] = candle
    return [merged[key] for key in sorted(merged)]


def _load_archive_series(pattern: str, label: str) -> tuple[str, str, list[Candlestick], list[Path]]:
    paths = resolve_archive_paths([pattern])
    if not paths:
        raise ValueError(f"{label} did not match any historical CSV or ZIP files.")
    groups: dict[tuple[str, str], list[Path]] = {}
    for path in paths:
        groups.setdefault(_stat_arb_archive_key(path), []).append(path)
    if len(groups) != 1:
        choices = ", ".join(f"{symbol}/{interval}" for symbol, interval in sorted(groups))
        raise ValueError(f"{label} must resolve to exactly one symbol/interval series; got: {choices}.")
    (symbol, interval), grouped_paths = next(iter(groups.items()))
    return symbol, interval, _merge_stat_arb_candles(grouped_paths, interval), grouped_paths


def run_pair_stat_arb_from_archives(
    *,
    archive_a: str,
    archive_b: str,
    config: PairStatArbConfig | None = None,
) -> tuple[PairStatArbReport, dict[str, object]]:
    symbol_a, interval_a, candles_a, paths_a = _load_archive_series(archive_a, "archive_a")
    symbol_b, interval_b, candles_b, paths_b = _load_archive_series(archive_b, "archive_b")
    if interval_a != interval_b:
        raise ValueError(f"Pair intervals must match: {interval_a} != {interval_b}.")
    report = run_pair_stat_arb_backtest(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        interval=interval_a,
        candles_a=candles_a,
        candles_b=candles_b,
        config=config,
    )
    return report, {
        "archive_a": archive_a,
        "archive_b": archive_b,
        "resolved_paths_a": [str(path) for path in paths_a],
        "resolved_paths_b": [str(path) for path in paths_b],
    }


__all__ = [
    "AlignedPairBar",
    "PairEquityPoint",
    "PairSignalState",
    "PairStatArbConfig",
    "PairStatArbReport",
    "PairStatArbTrade",
    "align_pair_candles",
    "run_pair_stat_arb_backtest",
    "run_pair_stat_arb_from_archives",
]
