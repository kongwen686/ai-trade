from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
import argparse
import glob
import json
import math
from pathlib import Path
import statistics

from . import __version__
from .archive_loader import load_public_data_klines
from .binance_client import BinanceSpotGateway
from .config import SETTINGS
from .indicators import build_indicator_snapshot
from .models import (
    BacktestReport,
    BacktestSignalEvent,
    Candlestick,
    EquityPoint,
    ForwardReturnStat,
    MarketTicker,
    PortfolioBacktestReport,
    PortfolioReturnStat,
    PortfolioSelection,
    TradePerformanceStat,
)
from .scoring import build_reasons, build_subscores, composite_score, compute_liquidity_score, grade_from_score
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig, evaluate_long_entry, normalize_return_pct


def archive_key(path: Path) -> tuple[str, str]:
    parts = path.stem.split("-")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse symbol/interval from archive name: {path.name}")
    return parts[0].upper(), parts[1]


def resolve_archive_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        matches = [Path(match) for match in glob.glob(item)]
        if matches:
            for match in matches:
                if match.is_dir():
                    paths.extend(sorted(match.rglob("*.zip")))
                elif match.suffix == ".zip":
                    paths.append(match)
            continue

        path = Path(item)
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.zip")))
        elif path.exists() and path.suffix == ".zip":
            paths.append(path)

    unique = []
    seen: set[Path] = set()
    for path in sorted(paths):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def group_archives(paths: list[Path]) -> dict[tuple[str, str], list[Path]]:
    groups: dict[tuple[str, str], list[Path]] = {}
    for path in paths:
        key = archive_key(path)
        groups.setdefault(key, []).append(path)
    return groups


def merge_candles(paths: list[Path]) -> list[Candlestick]:
    merged: dict[datetime, Candlestick] = {}
    for path in sorted(paths):
        for candle in load_public_data_klines(path):
            merged[candle.open_time] = candle
    return [merged[key] for key in sorted(merged)]


def bars_per_day(candles: list[Candlestick]) -> int:
    if len(candles) < 2:
        return 1
    deltas = []
    for previous, current in zip(candles, candles[1:]):
        delta = int((current.open_time - previous.open_time).total_seconds())
        if delta > 0:
            deltas.append(delta)
    if not deltas:
        return 1
    median_seconds = statistics.median(deltas)
    return max(1, round(86400 / median_seconds))


def build_historical_ticker(symbol: str, candles: list[Candlestick], index: int, day_bars: int) -> MarketTicker:
    start = max(0, index - day_bars + 1)
    window = candles[start : index + 1]
    reference_index = max(0, index - day_bars)
    reference_price = candles[reference_index].close_price
    current_price = candles[index].close_price
    change_pct = ((current_price - reference_price) / reference_price) * 100 if reference_price else 0.0
    return MarketTicker(
        symbol=symbol,
        last_price=current_price,
        price_change_percent=change_pct,
        quote_volume=sum(candle.quote_volume for candle in window),
        volume=sum(candle.volume for candle in window),
        trade_count=sum(candle.trade_count for candle in window),
    )


def rolling_liquidity_baseline(
    symbol: str,
    candles: list[Candlestick],
    index: int,
    day_bars: int,
    history_windows: int = 30,
) -> tuple[list[float], list[int]]:
    quote_volumes: list[float] = []
    trade_counts: list[int] = []
    for end_index in range(max(0, index - history_windows + 1), index + 1):
        ticker = build_historical_ticker(symbol, candles, end_index, day_bars)
        quote_volumes.append(ticker.quote_volume)
        trade_counts.append(ticker.trade_count)
    return quote_volumes, trade_counts


def run_backtest_for_series(
    *,
    symbol: str,
    interval: str,
    candles: list[Candlestick],
    lookback_bars: int,
    score_threshold: float,
    holding_periods: list[int],
    entry_config: EntryRuleConfig | None = None,
    exit_config: ExitRuleConfig | None = None,
    execution_config: ExecutionConfig | None = None,
    cooldown_bars: int | None = None,
) -> BacktestReport:
    entry_config = entry_config or EntryRuleConfig(min_score=score_threshold)
    horizons = sorted({value for value in holding_periods if value > 0})
    if not horizons:
        raise ValueError("holding_periods must contain at least one positive integer.")
    exit_config = exit_config or ExitRuleConfig(max_holding_bars=max(horizons))
    execution_config = execution_config or ExecutionConfig()
    max_horizon = max(max(horizons) + 1, exit_config.max_holding_bars + 1)
    if len(candles) < 60 + max_horizon:
        raise ValueError(f"Not enough candles for backtest: {symbol} {interval} has {len(candles)} bars.")

    day_bars = bars_per_day(candles)
    cooldown_bars = cooldown_bars if cooldown_bars is not None else exit_config.cooldown_bars_after_exit
    warmup = 60
    next_entry_index = warmup - 1
    events: list[BacktestSignalEvent] = []
    evaluated_bars = 0
    entry_fee_bps = resolve_fee_bps(
        fee_model=execution_config.fee_model,
        role=execution_config.entry_fee_role,
        flat_fee_bps=execution_config.fee_bps,
        maker_fee_bps=execution_config.maker_fee_bps,
        taker_fee_bps=execution_config.taker_fee_bps,
        fee_discount_pct=execution_config.fee_discount_pct,
    )
    exit_fee_bps = resolve_fee_bps(
        fee_model=execution_config.fee_model,
        role=execution_config.exit_fee_role,
        flat_fee_bps=execution_config.fee_bps,
        maker_fee_bps=execution_config.maker_fee_bps,
        taker_fee_bps=execution_config.taker_fee_bps,
        fee_discount_pct=execution_config.fee_discount_pct,
    )

    for index in range(warmup - 1, len(candles) - max_horizon):
        evaluated_bars += 1
        if index < next_entry_index:
            continue

        history = candles[max(0, index - lookback_bars + 1) : index + 1]
        indicators = build_indicator_snapshot(history)
        ticker = build_historical_ticker(symbol, candles, index, day_bars)
        quote_volumes, trade_counts = rolling_liquidity_baseline(symbol, candles, index, day_bars)
        liquidity_score = compute_liquidity_score(ticker, quote_volumes, trade_counts)
        breakdown = build_subscores(
            ticker=ticker,
            indicators=indicators,
            liquidity_score=liquidity_score,
            community_signal=None,
        )
        score = composite_score(breakdown)
        decision = evaluate_long_entry(
            score=score,
            indicators=indicators,
            config=entry_config,
        )
        if not decision.allowed:
            continue

        general_reasons, _ = build_reasons(ticker, indicators, None)
        reasons = decision.reasons + [reason for reason in general_reasons if reason not in decision.reasons]
        trade = simulate_long_trade(
            candles=candles,
            signal_index=index,
            max_holding_bars=exit_config.max_holding_bars,
            stop_loss_pct=exit_config.stop_loss_pct,
            take_profit_pct=exit_config.take_profit_pct,
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=resolve_slippage_bps(
                base_slippage_bps=execution_config.slippage_bps,
                slippage_model=execution_config.slippage_model,
                signal_quote_volume=history[-1].quote_volume,
                reference_quote_volumes=[candle.quote_volume for candle in history[-execution_config.slippage_window_bars :]],
                min_slippage_bps=execution_config.min_slippage_bps,
                max_slippage_bps=execution_config.max_slippage_bps,
            ),
        )
        forward_returns = {
            horizon: percent_return(trade.entry_fill_price, candles[trade.entry_index + horizon].close_price)
            for horizon in horizons
        }
        events.append(
            BacktestSignalEvent(
                symbol=symbol,
                interval=interval,
                entry_time=trade.entry_time,
                entry_price=trade.entry_fill_price,
                score=score,
                grade=grade_from_score(score),
                reasons=reasons,
                forward_returns_pct=forward_returns,
                signal_time=candles[index].close_time,
                exit_time=trade.exit_time,
                exit_price=trade.exit_fill_price,
                exit_reason=trade.exit_reason,
                gross_return_pct=trade.gross_return_pct,
                realized_return_pct=trade.realized_return_pct,
                bars_held=trade.bars_held,
                max_drawdown_pct=trade.max_drawdown_pct,
                max_runup_pct=trade.max_runup_pct,
                fee_bps=execution_config.fee_bps,
                slippage_bps=execution_config.slippage_bps,
                capital_fraction_pct=execution_config.capital_fraction_pct,
                effective_slippage_bps=trade.slippage_bps,
                entry_fee_bps=trade.entry_fee_bps,
                exit_fee_bps=trade.exit_fee_bps,
            )
        )
        next_entry_index = trade.exit_index + 1 + cooldown_bars

    stats = summarize_events(events, horizons)
    trade_stat = summarize_realized_trades(events)
    equity_curve = build_equity_curve_from_events(events, capital_fraction_pct=execution_config.capital_fraction_pct)
    return BacktestReport(
        symbol=symbol,
        interval=interval,
        candle_count=len(candles),
        evaluated_bars=evaluated_bars,
        signal_count=len(events),
        lookback_bars=lookback_bars,
        score_threshold=score_threshold,
        cooldown_bars=cooldown_bars,
        fee_bps=execution_config.fee_bps,
        slippage_bps=execution_config.slippage_bps,
        capital_fraction_pct=execution_config.capital_fraction_pct,
        generated_at=datetime.now(timezone.utc),
        fee_model=execution_config.fee_model,
        fee_source=execution_config.fee_source,
        maker_fee_bps=execution_config.maker_fee_bps,
        taker_fee_bps=execution_config.taker_fee_bps,
        entry_fee_role=execution_config.entry_fee_role,
        exit_fee_role=execution_config.exit_fee_role,
        fee_discount_pct=execution_config.fee_discount_pct,
        stats=stats,
        trade_stat=trade_stat,
        equity_curve=equity_curve,
        events=events,
    )


def summarize_events(events: list[BacktestSignalEvent], horizons: list[int]) -> list[ForwardReturnStat]:
    stats: list[ForwardReturnStat] = []
    for horizon in horizons:
        values = [event.forward_returns_pct[horizon] for event in events if horizon in event.forward_returns_pct]
        if not values:
            stats.append(
                ForwardReturnStat(
                    horizon_bars=horizon,
                    signal_count=0,
                    avg_return_pct=0.0,
                    median_return_pct=0.0,
                    win_rate_pct=0.0,
                    best_return_pct=0.0,
                    worst_return_pct=0.0,
                )
            )
            continue

        stats.append(
            ForwardReturnStat(
                horizon_bars=horizon,
                signal_count=len(values),
                avg_return_pct=round(statistics.fmean(values), 4),
                median_return_pct=round(statistics.median(values), 4),
                win_rate_pct=round((sum(1 for value in values if value > 0) / len(values)) * 100, 2),
                best_return_pct=round(max(values), 4),
                worst_return_pct=round(min(values), 4),
            )
        )
    return stats


def summarize_realized_trades(events: list[BacktestSignalEvent]) -> TradePerformanceStat:
    realized_returns = [event.realized_return_pct for event in events if event.realized_return_pct is not None]
    if not realized_returns:
        return TradePerformanceStat(
            trade_count=0,
            avg_return_pct=0.0,
            median_return_pct=0.0,
            win_rate_pct=0.0,
            best_return_pct=0.0,
            worst_return_pct=0.0,
            avg_bars_held=0.0,
            avg_max_drawdown_pct=0.0,
            profit_factor=0.0,
        )

    bars_held = [event.bars_held or 0 for event in events if event.realized_return_pct is not None]
    max_drawdowns = [event.max_drawdown_pct or 0.0 for event in events if event.realized_return_pct is not None]
    gross_profit = sum(value for value in realized_returns if value > 0)
    gross_loss = abs(sum(value for value in realized_returns if value < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else 999.0
    return TradePerformanceStat(
        trade_count=len(realized_returns),
        avg_return_pct=round(statistics.fmean(realized_returns), 4),
        median_return_pct=round(statistics.median(realized_returns), 4),
        win_rate_pct=round((sum(1 for value in realized_returns if value > 0) / len(realized_returns)) * 100, 2),
        best_return_pct=round(max(realized_returns), 4),
        worst_return_pct=round(min(realized_returns), 4),
        avg_bars_held=round(statistics.fmean(bars_held), 2) if bars_held else 0.0,
        avg_max_drawdown_pct=round(statistics.fmean(max_drawdowns), 4) if max_drawdowns else 0.0,
        profit_factor=profit_factor,
    )


def build_equity_curve_from_events(events: list[BacktestSignalEvent], capital_fraction_pct: float) -> list[EquityPoint]:
    equity = 1.0
    peak = 1.0
    curve: list[EquityPoint] = []
    for event in sorted(events, key=lambda item: item.exit_time or item.entry_time):
        if event.realized_return_pct is None:
            continue
        capital_fraction = max(0.0, min(event.capital_fraction_pct / 100, 1.0))
        equity *= 1 + ((event.realized_return_pct / 100) * capital_fraction)
        peak = max(peak, equity)
        drawdown_pct = ((equity / peak) - 1) * 100 if peak else 0.0
        curve.append(
            EquityPoint(
                time=event.exit_time or event.entry_time,
                equity=round(equity, 6),
                drawdown_pct=round(drawdown_pct, 4),
                period_return_pct=round(event.realized_return_pct, 4),
            )
        )
    return curve


def rate_to_bps(value: str | float | int | None) -> float:
    if value is None:
        return 0.0
    return round(float(value) * 10_000, 4)


def normalize_binance_discount_factor(value: str | float | int | None) -> float:
    if value is None:
        return 1.0
    discount_value = float(value)
    if discount_value <= 0:
        return 1.0
    if discount_value <= 0.5:
        return round(1 - discount_value, 8)
    return round(discount_value, 8)


def resolve_commission_from_account_payload(payload: dict[str, object]) -> tuple[float, float, float]:
    commission_rates = payload.get("commissionRates", {})
    if not isinstance(commission_rates, dict):
        return 0.0, 0.0, 0.0
    maker_fee_bps = rate_to_bps(commission_rates.get("maker"))
    taker_fee_bps = rate_to_bps(commission_rates.get("taker"))
    return maker_fee_bps, taker_fee_bps, 0.0


def resolve_commission_from_symbol_payload(
    payload: dict[str, object],
    *,
    apply_discount: bool,
) -> tuple[float, float, float]:
    standard = payload.get("standardCommission", {})
    special = payload.get("specialCommission", {})
    tax = payload.get("taxCommission", {})
    discount = payload.get("discount", {})

    if not isinstance(standard, dict) or not isinstance(special, dict) or not isinstance(tax, dict):
        return 0.0, 0.0, 0.0

    discount_factor = 1.0
    discount_pct = 0.0
    if apply_discount and isinstance(discount, dict):
        if bool(discount.get("enabledForAccount")) and bool(discount.get("enabledForSymbol")):
            discount_factor = normalize_binance_discount_factor(discount.get("discount"))
            discount_pct = round((1 - discount_factor) * 100, 4)

    maker_fee_bps = round(
        (rate_to_bps(standard.get("maker")) * discount_factor)
        + rate_to_bps(special.get("maker"))
        + rate_to_bps(tax.get("maker")),
        4,
    )
    taker_fee_bps = round(
        (rate_to_bps(standard.get("taker")) * discount_factor)
        + rate_to_bps(special.get("taker"))
        + rate_to_bps(tax.get("taker")),
        4,
    )
    return maker_fee_bps, taker_fee_bps, discount_pct


def resolve_execution_config_from_binance(
    *,
    gateway: BinanceSpotGateway,
    execution_config: ExecutionConfig,
    symbol: str | None,
) -> ExecutionConfig:
    if execution_config.fee_source == "manual":
        return execution_config
    if not gateway.has_user_data_auth():
        raise ValueError("未配置 BINANCE_API_KEY / BINANCE_API_SECRET，无法自动读取账户手续费。")

    if execution_config.fee_source == "account":
        maker_fee_bps, taker_fee_bps, fee_discount_pct = resolve_commission_from_account_payload(gateway.account())
    elif execution_config.fee_source == "symbol":
        if not symbol:
            raise ValueError("fee_source=symbol 时必须提供 symbol。")
        maker_fee_bps, taker_fee_bps, fee_discount_pct = resolve_commission_from_symbol_payload(
            gateway.account_commission(symbol),
            apply_discount=execution_config.apply_binance_discount,
        )
    else:
        raise ValueError(f"Unsupported fee_source: {execution_config.fee_source}")

    return replace(
        execution_config,
        fee_model="maker_taker",
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        fee_discount_pct=fee_discount_pct,
    )


def resolve_fee_bps(
    *,
    fee_model: str,
    role: str,
    flat_fee_bps: float,
    maker_fee_bps: float,
    taker_fee_bps: float,
    fee_discount_pct: float,
) -> float:
    if fee_model == "maker_taker":
        base_fee_bps = maker_fee_bps if role == "maker" else taker_fee_bps
    else:
        base_fee_bps = flat_fee_bps

    discount_multiplier = 1 - max(0.0, min(fee_discount_pct, 100.0)) / 100
    return round(base_fee_bps * discount_multiplier, 4)


def format_fee_summary(
    *,
    fee_model: str,
    fee_source: str,
    flat_fee_bps: float,
    maker_fee_bps: float,
    taker_fee_bps: float,
    entry_fee_role: str,
    exit_fee_role: str,
    fee_discount_pct: float,
) -> str:
    if fee_model == "maker_taker":
        entry_fee_bps = resolve_fee_bps(
            fee_model=fee_model,
            role=entry_fee_role,
            flat_fee_bps=flat_fee_bps,
            maker_fee_bps=maker_fee_bps,
            taker_fee_bps=taker_fee_bps,
            fee_discount_pct=fee_discount_pct,
        )
        exit_fee_bps = resolve_fee_bps(
            fee_model=fee_model,
            role=exit_fee_role,
            flat_fee_bps=flat_fee_bps,
            maker_fee_bps=maker_fee_bps,
            taker_fee_bps=taker_fee_bps,
            fee_discount_pct=fee_discount_pct,
        )
        discount = f" | discount {fee_discount_pct:.1f}%" if fee_discount_pct > 0 else ""
        return (
            f"[{fee_source}] maker/taker {maker_fee_bps:.2f}/{taker_fee_bps:.2f}bps"
            f" | entry {entry_fee_role} {entry_fee_bps:.2f}bps"
            f" | exit {exit_fee_role} {exit_fee_bps:.2f}bps"
            f"{discount}"
        )
    discount = f" | discount {fee_discount_pct:.1f}%" if fee_discount_pct > 0 else ""
    effective_fee_bps = resolve_fee_bps(
        fee_model=fee_model,
        role="taker",
        flat_fee_bps=flat_fee_bps,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        fee_discount_pct=fee_discount_pct,
    )
    return f"[{fee_source}] flat {effective_fee_bps:.2f}bps{discount}"


class TradePath:
    def __init__(
        self,
        *,
        entry_index: int,
        entry_time: datetime,
        entry_raw_price: float,
        entry_fill_price: float,
        exit_index: int,
        exit_time: datetime,
        exit_raw_price: float,
        exit_fill_price: float,
        exit_reason: str,
        gross_return_pct: float,
        realized_return_pct: float,
        bars_held: int,
        max_drawdown_pct: float,
        max_runup_pct: float,
        slippage_bps: float,
        entry_fee_bps: float,
        exit_fee_bps: float,
    ) -> None:
        self.entry_index = entry_index
        self.entry_time = entry_time
        self.entry_raw_price = entry_raw_price
        self.entry_fill_price = entry_fill_price
        self.exit_index = exit_index
        self.exit_time = exit_time
        self.exit_raw_price = exit_raw_price
        self.exit_fill_price = exit_fill_price
        self.exit_reason = exit_reason
        self.gross_return_pct = gross_return_pct
        self.realized_return_pct = realized_return_pct
        self.bars_held = bars_held
        self.max_drawdown_pct = max_drawdown_pct
        self.max_runup_pct = max_runup_pct
        self.slippage_bps = slippage_bps
        self.entry_fee_bps = entry_fee_bps
        self.exit_fee_bps = exit_fee_bps


def simulate_long_trade(
    *,
    candles: list[Candlestick],
    signal_index: int,
    max_holding_bars: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    entry_fee_bps: float,
    exit_fee_bps: float,
    slippage_bps: float,
    ) -> TradePath:
    entry_index = signal_index + 1
    entry_bar = candles[entry_index]
    entry_price = entry_bar.open_price
    stop_price = entry_price * (1 - (stop_loss_pct / 100))
    take_price = entry_price * (1 + (take_profit_pct / 100))
    last_index = min(len(candles) - 1, entry_index + max_holding_bars - 1)
    min_low = entry_price
    max_high = entry_price

    for current_index in range(entry_index, last_index + 1):
        candle = candles[current_index]
        min_low = min(min_low, candle.low_price)
        max_high = max(max_high, candle.high_price)
        exit_reason = intrabar_exit_reason(
            stop_price=stop_price,
            take_price=take_price,
            low_price=candle.low_price,
            high_price=candle.high_price,
        )
        if exit_reason == "stop_loss":
            exit_price = stop_price
            return create_trade_path(
                entry_index=entry_index,
                entry_price=entry_price,
                exit_index=current_index,
                exit_price=exit_price,
                exit_reason=exit_reason,
                candles=candles,
                min_low=min_low,
                max_high=max_high,
                entry_fee_bps=entry_fee_bps,
                exit_fee_bps=exit_fee_bps,
                slippage_bps=slippage_bps,
            )
        if exit_reason == "take_profit":
            exit_price = take_price
            return create_trade_path(
                entry_index=entry_index,
                entry_price=entry_price,
                exit_index=current_index,
                exit_price=exit_price,
                exit_reason=exit_reason,
                candles=candles,
                min_low=min_low,
                max_high=max_high,
                entry_fee_bps=entry_fee_bps,
                exit_fee_bps=exit_fee_bps,
                slippage_bps=slippage_bps,
            )

    return create_trade_path(
        entry_index=entry_index,
        entry_price=entry_price,
        exit_index=last_index,
        exit_price=candles[last_index].close_price,
        exit_reason="time_exit",
        candles=candles,
        min_low=min_low,
        max_high=max_high,
        entry_fee_bps=entry_fee_bps,
        exit_fee_bps=exit_fee_bps,
        slippage_bps=slippage_bps,
    )


def intrabar_exit_reason(*, stop_price: float, take_price: float, low_price: float, high_price: float) -> str | None:
    hit_stop = low_price <= stop_price
    hit_take = high_price >= take_price
    if hit_stop and hit_take:
        return "stop_loss"
    if hit_stop:
        return "stop_loss"
    if hit_take:
        return "take_profit"
    return None


def create_trade_path(
    *,
    entry_index: int,
    entry_price: float,
    exit_index: int,
    exit_price: float,
    exit_reason: str,
    candles: list[Candlestick],
    min_low: float,
    max_high: float,
    entry_fee_bps: float,
    exit_fee_bps: float,
    slippage_bps: float,
) -> TradePath:
    entry_fill_price = apply_long_entry_slippage(entry_price, slippage_bps)
    exit_fill_price = apply_long_exit_slippage(exit_price, slippage_bps)
    gross_return_pct = normalize_return_pct(percent_return(entry_price, exit_price))
    realized_return_pct = normalize_return_pct(
        compute_net_long_return_pct(
            entry_fill_price=entry_fill_price,
            exit_fill_price=exit_fill_price,
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
        )
    )
    return TradePath(
        entry_index=entry_index,
        entry_time=candles[entry_index].open_time,
        entry_raw_price=entry_price,
        entry_fill_price=entry_fill_price,
        exit_index=exit_index,
        exit_time=candles[exit_index].close_time,
        exit_raw_price=exit_price,
        exit_fill_price=exit_fill_price,
        exit_reason=exit_reason,
        gross_return_pct=gross_return_pct,
        realized_return_pct=realized_return_pct,
        bars_held=(exit_index - entry_index) + 1,
        max_drawdown_pct=normalize_return_pct(percent_return(entry_price, min_low)),
        max_runup_pct=normalize_return_pct(percent_return(entry_price, max_high)),
        slippage_bps=slippage_bps,
        entry_fee_bps=entry_fee_bps,
        exit_fee_bps=exit_fee_bps,
    )


def apply_long_entry_slippage(price: float, slippage_bps: float) -> float:
    return price * (1 + (slippage_bps / 10_000))


def apply_long_exit_slippage(price: float, slippage_bps: float) -> float:
    return price * (1 - (slippage_bps / 10_000))


def compute_net_long_return_pct(
    *,
    entry_fill_price: float,
    exit_fill_price: float,
    entry_fee_bps: float,
    exit_fee_bps: float,
) -> float:
    entry_fee_rate = entry_fee_bps / 10_000
    exit_fee_rate = exit_fee_bps / 10_000
    net_entry_cost = entry_fill_price * (1 + entry_fee_rate)
    net_exit_value = exit_fill_price * (1 - exit_fee_rate)
    return ((net_exit_value / net_entry_cost) - 1) * 100


def resolve_slippage_bps(
    *,
    base_slippage_bps: float,
    slippage_model: str,
    signal_quote_volume: float,
    reference_quote_volumes: list[float],
    min_slippage_bps: float,
    max_slippage_bps: float,
) -> float:
    if slippage_model != "dynamic":
        return round(base_slippage_bps, 4)

    valid = [value for value in reference_quote_volumes if value > 0]
    if not valid or signal_quote_volume <= 0:
        return round(base_slippage_bps, 4)

    reference = statistics.median(valid)
    liquidity_ratio = signal_quote_volume / reference if reference else 1.0
    if liquidity_ratio >= 1:
        multiplier = 1 / math.sqrt(min(liquidity_ratio, 9.0))
    else:
        multiplier = 1 + ((1 - liquidity_ratio) * 1.5)

    effective = base_slippage_bps * multiplier
    return round(max(min_slippage_bps, min(max_slippage_bps, effective)), 4)


class ActivePosition:
    def __init__(self, exit_time: datetime | None, capital_fraction_pct: float) -> None:
        self.exit_time = exit_time
        self.capital_fraction_pct = capital_fraction_pct


def run_portfolio_backtest(
    reports: list[BacktestReport],
    top_n: int,
    *,
    max_concurrent_positions: int | None = None,
    max_portfolio_exposure_pct: float | None = None,
) -> PortfolioBacktestReport | None:
    if top_n <= 0 or not reports:
        return None

    interval = reports[0].interval
    if any(report.interval != interval for report in reports):
        raise ValueError("Portfolio backtest requires reports from the same interval.")
    fee_bps = reports[0].fee_bps
    slippage_bps = reports[0].slippage_bps
    capital_fraction_pct = reports[0].capital_fraction_pct
    fee_model = reports[0].fee_model
    fee_source = reports[0].fee_source
    maker_fee_bps = reports[0].maker_fee_bps
    taker_fee_bps = reports[0].taker_fee_bps
    entry_fee_role = reports[0].entry_fee_role
    exit_fee_role = reports[0].exit_fee_role
    fee_discount_pct = reports[0].fee_discount_pct
    max_portfolio_exposure_pct = 100.0 if max_portfolio_exposure_pct is None else max_portfolio_exposure_pct
    max_concurrent_positions = max(top_n, 1) if max_concurrent_positions is None else max_concurrent_positions

    event_buckets: dict[datetime, list[BacktestSignalEvent]] = {}
    for report in reports:
        for event in report.events:
            event_buckets.setdefault(event.entry_time, []).append(event)

    if not event_buckets:
        return PortfolioBacktestReport(
            interval=interval,
            top_n=top_n,
            symbol_count=len(reports),
            batch_count=0,
            pick_count=0,
            score_threshold=reports[0].score_threshold,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            capital_fraction_pct=capital_fraction_pct,
            generated_at=datetime.now(timezone.utc),
            fee_model=fee_model,
            fee_source=fee_source,
            maker_fee_bps=maker_fee_bps,
            taker_fee_bps=taker_fee_bps,
            entry_fee_role=entry_fee_role,
            exit_fee_role=exit_fee_role,
            fee_discount_pct=fee_discount_pct,
            stats=[],
            selections=[],
        )

    horizons = sorted(next(iter(event_buckets.values()))[0].forward_returns_pct)
    selections: list[PortfolioSelection] = []
    active_positions: list[ActivePosition] = []
    for entry_time in sorted(event_buckets):
        active_positions = [
            position for position in active_positions if position.exit_time is None or position.exit_time > entry_time
        ]
        deployed_capital_pct = sum(position.capital_fraction_pct for position in active_positions)
        available_slots = max_concurrent_positions - len(active_positions)
        exposure_remaining_pct = max(0.0, max_portfolio_exposure_pct - deployed_capital_pct)
        if available_slots <= 0 or exposure_remaining_pct <= 0:
            continue
        ranked = sorted(
            event_buckets[entry_time],
            key=lambda event: (-event.score, event.symbol),
        )
        pick_limit = min(top_n, len(ranked), available_slots)
        if pick_limit <= 0:
            continue
        picks = ranked[:pick_limit]
        capital_per_pick_pct = min(capital_fraction_pct, exposure_remaining_pct / len(picks))
        total_capital_pct = capital_per_pick_pct * len(picks)
        average_returns = {
            horizon: round(statistics.fmean(event.forward_returns_pct[horizon] for event in picks), 4)
            for horizon in horizons
        }
        realized_values = [event.realized_return_pct for event in picks if event.realized_return_pct is not None]
        gross_values = [event.gross_return_pct for event in picks if event.gross_return_pct is not None]
        batch_return = round(statistics.fmean(realized_values), 4) if realized_values else None
        batch_gross_return = round(statistics.fmean(gross_values), 4) if gross_values else None
        exit_times = [event.exit_time for event in picks if event.exit_time is not None]
        batch_exit_time = max(exit_times) if exit_times else None
        selections.append(
            PortfolioSelection(
                entry_time=entry_time,
                picks=picks,
                average_forward_returns_pct=average_returns,
                exit_time=batch_exit_time,
                gross_return_pct=batch_gross_return,
                realized_return_pct=batch_return,
                capital_fraction_pct=round(total_capital_pct, 4),
                capital_per_pick_pct=round(capital_per_pick_pct, 4),
            )
        )
        for pick in picks:
            active_positions.append(
                ActivePosition(
                    exit_time=pick.exit_time,
                    capital_fraction_pct=capital_per_pick_pct,
                )
            )

    stats = summarize_portfolio_selections(selections, horizons)
    trade_stat = summarize_portfolio_trades(selections)
    equity_curve = build_equity_curve_from_selections(selections, capital_fraction_pct=capital_fraction_pct)
    return PortfolioBacktestReport(
        interval=interval,
        top_n=top_n,
        symbol_count=len(reports),
        batch_count=len(selections),
        pick_count=sum(len(selection.picks) for selection in selections),
        score_threshold=reports[0].score_threshold,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        capital_fraction_pct=capital_fraction_pct,
        generated_at=datetime.now(timezone.utc),
        fee_model=fee_model,
        fee_source=fee_source,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        entry_fee_role=entry_fee_role,
        exit_fee_role=exit_fee_role,
        fee_discount_pct=fee_discount_pct,
        stats=stats,
        trade_stat=trade_stat,
        equity_curve=equity_curve,
        selections=selections,
    )


def summarize_portfolio_selections(
    selections: list[PortfolioSelection],
    horizons: list[int],
) -> list[PortfolioReturnStat]:
    stats: list[PortfolioReturnStat] = []
    for horizon in horizons:
        batch_values = [
            selection.average_forward_returns_pct[horizon]
            for selection in selections
            if horizon in selection.average_forward_returns_pct
        ]
        pick_values = [
            pick.forward_returns_pct[horizon]
            for selection in selections
            for pick in selection.picks
            if horizon in pick.forward_returns_pct
        ]
        if not batch_values:
            stats.append(
                PortfolioReturnStat(
                    horizon_bars=horizon,
                    batch_count=0,
                    pick_count=0,
                    avg_batch_return_pct=0.0,
                    median_batch_return_pct=0.0,
                    avg_pick_return_pct=0.0,
                    win_rate_pct=0.0,
                    best_batch_return_pct=0.0,
                    worst_batch_return_pct=0.0,
                )
            )
            continue

        stats.append(
            PortfolioReturnStat(
                horizon_bars=horizon,
                batch_count=len(batch_values),
                pick_count=len(pick_values),
                avg_batch_return_pct=round(statistics.fmean(batch_values), 4),
                median_batch_return_pct=round(statistics.median(batch_values), 4),
                avg_pick_return_pct=round(statistics.fmean(pick_values), 4) if pick_values else 0.0,
                win_rate_pct=round((sum(1 for value in batch_values if value > 0) / len(batch_values)) * 100, 2),
                best_batch_return_pct=round(max(batch_values), 4),
                worst_batch_return_pct=round(min(batch_values), 4),
            )
        )
    return stats


def summarize_portfolio_trades(selections: list[PortfolioSelection]) -> TradePerformanceStat:
    realized_returns = [selection.realized_return_pct for selection in selections if selection.realized_return_pct is not None]
    if not realized_returns:
        return TradePerformanceStat(
            trade_count=0,
            avg_return_pct=0.0,
            median_return_pct=0.0,
            win_rate_pct=0.0,
            best_return_pct=0.0,
            worst_return_pct=0.0,
            avg_bars_held=0.0,
            avg_max_drawdown_pct=0.0,
            profit_factor=0.0,
        )

    bars_held = []
    drawdowns = []
    for selection in selections:
        if selection.realized_return_pct is None:
            continue
        held_values = [pick.bars_held or 0 for pick in selection.picks if pick.bars_held is not None]
        dd_values = [pick.max_drawdown_pct or 0.0 for pick in selection.picks if pick.max_drawdown_pct is not None]
        if held_values:
            bars_held.append(statistics.fmean(held_values))
        if dd_values:
            drawdowns.append(statistics.fmean(dd_values))

    gross_profit = sum(value for value in realized_returns if value > 0)
    gross_loss = abs(sum(value for value in realized_returns if value < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else 999.0
    return TradePerformanceStat(
        trade_count=len(realized_returns),
        avg_return_pct=round(statistics.fmean(realized_returns), 4),
        median_return_pct=round(statistics.median(realized_returns), 4),
        win_rate_pct=round((sum(1 for value in realized_returns if value > 0) / len(realized_returns)) * 100, 2),
        best_return_pct=round(max(realized_returns), 4),
        worst_return_pct=round(min(realized_returns), 4),
        avg_bars_held=round(statistics.fmean(bars_held), 2) if bars_held else 0.0,
        avg_max_drawdown_pct=round(statistics.fmean(drawdowns), 4) if drawdowns else 0.0,
        profit_factor=profit_factor,
    )


def build_equity_curve_from_selections(selections: list[PortfolioSelection], capital_fraction_pct: float) -> list[EquityPoint]:
    equity = 1.0
    peak = 1.0
    curve: list[EquityPoint] = []
    position_exits: list[tuple[datetime, float, float]] = []
    fallback_fraction = max(0.0, min(capital_fraction_pct / 100, 1.0))
    for selection in selections:
        per_pick_fraction = selection.capital_per_pick_pct / 100 if selection.capital_per_pick_pct else fallback_fraction
        for pick in selection.picks:
            if pick.realized_return_pct is None:
                continue
            position_exits.append(
                (
                    pick.exit_time or selection.exit_time or selection.entry_time,
                    pick.realized_return_pct,
                    per_pick_fraction,
                )
            )

    for exit_time, realized_return_pct, fraction in sorted(position_exits, key=lambda item: item[0]):
        equity *= 1 + ((realized_return_pct / 100) * fraction)
        peak = max(peak, equity)
        drawdown_pct = ((equity / peak) - 1) * 100 if peak else 0.0
        curve.append(
            EquityPoint(
                time=exit_time,
                equity=round(equity, 6),
                drawdown_pct=round(drawdown_pct, 4),
                period_return_pct=round(realized_return_pct, 4),
            )
        )
    return curve


def percent_return(entry_price: float, exit_price: float) -> float:
    if entry_price == 0:
        return 0.0
    return ((exit_price - entry_price) / entry_price) * 100


def render_report(report: BacktestReport, top_events: int) -> str:
    fee_summary = format_fee_summary(
        fee_model=report.fee_model,
        fee_source=report.fee_source,
        flat_fee_bps=report.fee_bps,
        maker_fee_bps=report.maker_fee_bps,
        taker_fee_bps=report.taker_fee_bps,
        entry_fee_role=report.entry_fee_role,
        exit_fee_role=report.exit_fee_role,
        fee_discount_pct=report.fee_discount_pct,
    )
    lines = [
        f"{report.symbol} {report.interval} | candles={report.candle_count} evaluated={report.evaluated_bars} signals={report.signal_count}",
        f"threshold={report.score_threshold:.2f} lookback={report.lookback_bars} cooldown={report.cooldown_bars}",
        f"costs -> fee {fee_summary} | slippage {report.slippage_bps:.2f}bps | capital {report.capital_fraction_pct:.1f}%",
    ]
    if report.trade_stat is not None:
        lines.append(
            "  "
            f"realized -> avg {report.trade_stat.avg_return_pct:+.2f}% | "
            f"win {report.trade_stat.win_rate_pct:.1f}% | "
            f"pf {report.trade_stat.profit_factor:.2f} | "
            f"avg hold {report.trade_stat.avg_bars_held:.1f} bars | "
            f"avg dd {report.trade_stat.avg_max_drawdown_pct:+.2f}%"
        )
    if report.equity_curve:
        lines.append(
            "  "
            f"equity -> final {report.equity_curve[-1].equity:.4f} | "
            f"max dd {min(point.drawdown_pct for point in report.equity_curve):+.2f}%"
        )
    for stat in report.stats:
        lines.append(
            "  "
            f"{stat.horizon_bars:>3} bars -> avg {stat.avg_return_pct:+.2f}% | "
            f"median {stat.median_return_pct:+.2f}% | win {stat.win_rate_pct:.1f}% | "
            f"best {stat.best_return_pct:+.2f}% | worst {stat.worst_return_pct:+.2f}%"
        )

    if report.events:
        lines.append("  recent signals:")
        for event in report.events[-top_events:]:
            returns = " | ".join(
                f"{h}:{event.forward_returns_pct[h]:+,.2f}%"
                for h in sorted(event.forward_returns_pct)
            )
            reason_text = ", ".join(event.reasons[:2]) if event.reasons else "no-reason"
            lines.append(
                "    "
                f"{event.entry_time.isoformat()} {event.grade} {event.score:.2f} "
                f"entry={event.entry_price:.6f} exit={event.exit_reason or 'n/a'} "
                f"fee={event.entry_fee_bps if event.entry_fee_bps is not None else 0:.2f}/{event.exit_fee_bps if event.exit_fee_bps is not None else 0:.2f}bps "
                f"slip={event.effective_slippage_bps if event.effective_slippage_bps is not None else event.slippage_bps:.2f}bps "
                f"gross={event.gross_return_pct if event.gross_return_pct is not None else 0:+.2f}% "
                f"realized={event.realized_return_pct if event.realized_return_pct is not None else 0:+.2f}% "
                f"{returns} [{reason_text}]"
            )
    return "\n".join(lines)


def render_portfolio_report(report: PortfolioBacktestReport, top_events: int) -> str:
    fee_summary = format_fee_summary(
        fee_model=report.fee_model,
        fee_source=report.fee_source,
        flat_fee_bps=report.fee_bps,
        maker_fee_bps=report.maker_fee_bps,
        taker_fee_bps=report.taker_fee_bps,
        entry_fee_role=report.entry_fee_role,
        exit_fee_role=report.exit_fee_role,
        fee_discount_pct=report.fee_discount_pct,
    )
    lines = [
        f"Portfolio {report.interval} | top_n={report.top_n} symbols={report.symbol_count} batches={report.batch_count} picks={report.pick_count}",
        f"threshold={report.score_threshold:.2f}",
        f"costs -> fee {fee_summary} | slippage {report.slippage_bps:.2f}bps | capital {report.capital_fraction_pct:.1f}%",
    ]
    if report.trade_stat is not None:
        lines.append(
            "  "
            f"realized -> avg batch {report.trade_stat.avg_return_pct:+.2f}% | "
            f"win {report.trade_stat.win_rate_pct:.1f}% | "
            f"pf {report.trade_stat.profit_factor:.2f} | "
            f"avg hold {report.trade_stat.avg_bars_held:.1f} bars | "
            f"avg dd {report.trade_stat.avg_max_drawdown_pct:+.2f}%"
        )
    if report.equity_curve:
        lines.append(
            "  "
            f"equity -> final {report.equity_curve[-1].equity:.4f} | "
            f"max dd {min(point.drawdown_pct for point in report.equity_curve):+.2f}%"
        )
    for stat in report.stats:
        lines.append(
            "  "
            f"{stat.horizon_bars:>3} bars -> avg batch {stat.avg_batch_return_pct:+.2f}% | "
            f"median {stat.median_batch_return_pct:+.2f}% | avg pick {stat.avg_pick_return_pct:+.2f}% | "
            f"win {stat.win_rate_pct:.1f}% | best {stat.best_batch_return_pct:+.2f}% | "
            f"worst {stat.worst_batch_return_pct:+.2f}%"
        )

    if report.selections:
        lines.append("  recent portfolio batches:")
        for selection in report.selections[-top_events:]:
            picks = ", ".join(
                f"{pick.symbol}:{pick.grade}/{pick.score:.2f}"
                for pick in selection.picks
            )
            returns = " | ".join(
                f"{h}:{selection.average_forward_returns_pct[h]:+,.2f}%"
                for h in sorted(selection.average_forward_returns_pct)
            )
            lines.append(
                "    "
                f"{selection.entry_time.isoformat()} [{picks}] alloc={selection.capital_fraction_pct:.1f}% "
                f"gross={selection.gross_return_pct if selection.gross_return_pct is not None else 0:+.2f}% "
                f"realized={selection.realized_return_pct if selection.realized_return_pct is not None else 0:+.2f}% {returns}"
            )
    return "\n".join(lines)


def json_default(value: object) -> object:
    if is_dataclass(value):
        return {key: json_default(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_default(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_default(item) for item in value]
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="trade_signal_app.backtest",
        description="Backtest the signal model on Binance public-data kline archives.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("archives", nargs="+", help="ZIP files, folders, or glob patterns from Binance public data.")
    parser.add_argument("--score-threshold", type=float, default=70.0, help="Minimum composite score to count as a signal.")
    parser.add_argument("--lookback-bars", type=int, default=240, help="Trailing bars used to compute indicators.")
    parser.add_argument(
        "--holding-periods",
        default="3,6,12",
        help="Comma-separated forward horizons in bars, e.g. 3,6,12",
    )
    parser.add_argument("--cooldown-bars", type=int, default=0, help="Bars to wait before opening another signal; 0 uses max horizon.")
    parser.add_argument("--stop-loss-pct", type=float, default=4.0, help="Stop-loss percentage for strategy exits.")
    parser.add_argument("--take-profit-pct", type=float, default=9.0, help="Take-profit percentage for strategy exits.")
    parser.add_argument(
        "--max-holding-bars",
        type=int,
        default=12,
        help="Maximum holding bars before a time exit.",
    )
    parser.add_argument("--min-volume-ratio", type=float, default=1.10, help="Minimum volume expansion ratio to trigger an entry.")
    parser.add_argument("--min-buy-pressure", type=float, default=0.52, help="Minimum taker-buy ratio to trigger an entry.")
    parser.add_argument("--min-rsi", type=float, default=45.0, help="Minimum RSI allowed for an entry.")
    parser.add_argument("--max-rsi", type=float, default=72.0, help="Maximum RSI allowed for an entry.")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Per-side trading fee in basis points.")
    parser.add_argument(
        "--fee-model",
        choices=["flat", "maker_taker"],
        default="flat",
        help="Use a single flat fee or separate maker/taker commissions.",
    )
    parser.add_argument(
        "--fee-source",
        choices=["manual", "account", "symbol"],
        default="manual",
        help="Use manual fees, current account commission rates, or symbol-specific account commissions.",
    )
    parser.add_argument("--maker-fee-bps", type=float, default=10.0, help="Maker fee in basis points when --fee-model=maker_taker.")
    parser.add_argument("--taker-fee-bps", type=float, default=10.0, help="Taker fee in basis points when --fee-model=maker_taker.")
    parser.add_argument(
        "--entry-fee-role",
        choices=["maker", "taker"],
        default="taker",
        help="Assumed liquidity role for entries when --fee-model=maker_taker.",
    )
    parser.add_argument(
        "--exit-fee-role",
        choices=["maker", "taker"],
        default="taker",
        help="Assumed liquidity role for exits when --fee-model=maker_taker.",
    )
    parser.add_argument(
        "--fee-discount-pct",
        type=float,
        default=0.0,
        help="Optional percentage discount applied after resolving flat or maker/taker fees.",
    )
    parser.add_argument(
        "--no-binance-discount",
        action="store_true",
        help="When fee-source=symbol, ignore the BNB discount section returned by Binance commission APIs.",
    )
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Per-side slippage in basis points.")
    parser.add_argument(
        "--slippage-model",
        choices=["fixed", "dynamic"],
        default="fixed",
        help="Use fixed slippage or adapt slippage to trailing quote-volume liquidity.",
    )
    parser.add_argument("--min-slippage-bps", type=float, default=2.0, help="Lower bound for dynamic slippage.")
    parser.add_argument("--max-slippage-bps", type=float, default=25.0, help="Upper bound for dynamic slippage.")
    parser.add_argument("--slippage-window-bars", type=int, default=20, help="Trailing bars used by the dynamic slippage model.")
    parser.add_argument(
        "--capital-fraction-pct",
        type=float,
        default=100.0,
        help="Fraction of equity deployed on each trade or portfolio batch.",
    )
    parser.add_argument(
        "--max-portfolio-exposure-pct",
        type=float,
        default=100.0,
        help="Maximum total portfolio exposure across overlapping positions.",
    )
    parser.add_argument(
        "--max-concurrent-positions",
        type=int,
        default=0,
        help="Maximum simultaneous open positions; 0 defaults to --portfolio-top-n.",
    )
    parser.add_argument(
        "--no-kdj-confirmation",
        action="store_true",
        help="Disable the KDJ confirmation requirement in the entry trigger.",
    )
    parser.add_argument(
        "--portfolio-top-n",
        type=int,
        default=0,
        help="If > 0, build a cross-sectional portfolio by taking the top N signals across symbols at each timestamp.",
    )
    parser.add_argument("--top-events", type=int, default=5, help="How many recent signals to print for each report.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    paths = resolve_archive_paths(args.archives)
    if not paths:
        raise SystemExit("No ZIP archives found.")

    holding_periods = [int(item) for item in args.holding_periods.split(",") if item.strip()]
    reports: list[BacktestReport] = []
    portfolio_reports: list[PortfolioBacktestReport] = []
    gateway = BinanceSpotGateway(
        ttl_seconds=SETTINGS.scan_ttl_seconds,
        api_key=SETTINGS.binance_api_key,
        api_secret=SETTINGS.binance_api_secret,
        recv_window_ms=SETTINGS.binance_recv_window_ms,
    )
    entry_config = EntryRuleConfig(
        min_score=args.score_threshold,
        min_volume_ratio=args.min_volume_ratio,
        min_buy_pressure_ratio=args.min_buy_pressure,
        min_rsi=args.min_rsi,
        max_rsi=args.max_rsi,
        require_kdj_confirmation=not args.no_kdj_confirmation,
    )
    exit_config = ExitRuleConfig(
        max_holding_bars=args.max_holding_bars,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        cooldown_bars_after_exit=args.cooldown_bars,
    )
    execution_config = ExecutionConfig(
        fee_bps=args.fee_bps,
        fee_model=args.fee_model,
        fee_source=args.fee_source,
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
        entry_fee_role=args.entry_fee_role,
        exit_fee_role=args.exit_fee_role,
        fee_discount_pct=args.fee_discount_pct,
        apply_binance_discount=not args.no_binance_discount,
        slippage_bps=args.slippage_bps,
        capital_fraction_pct=args.capital_fraction_pct,
        slippage_model=args.slippage_model,
        min_slippage_bps=args.min_slippage_bps,
        max_slippage_bps=args.max_slippage_bps,
        slippage_window_bars=args.slippage_window_bars,
        max_portfolio_exposure_pct=args.max_portfolio_exposure_pct,
        max_concurrent_positions=args.max_concurrent_positions,
    )

    grouped = group_archives(paths)
    reports_by_interval: dict[str, list[BacktestReport]] = {}
    try:
        account_execution_config = (
            resolve_execution_config_from_binance(
                gateway=gateway,
                execution_config=execution_config,
                symbol=None,
            )
            if execution_config.fee_source == "account"
            else execution_config
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for (symbol, interval), archive_paths in sorted(grouped.items()):
        candles = merge_candles(archive_paths)
        try:
            report_execution_config = (
                resolve_execution_config_from_binance(
                    gateway=gateway,
                    execution_config=account_execution_config,
                    symbol=symbol,
                )
                if execution_config.fee_source == "symbol"
                else account_execution_config
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        report = run_backtest_for_series(
            symbol=symbol,
            interval=interval,
            candles=candles,
            lookback_bars=args.lookback_bars,
            score_threshold=args.score_threshold,
            holding_periods=holding_periods,
            entry_config=entry_config,
            exit_config=exit_config,
            execution_config=report_execution_config,
            cooldown_bars=args.cooldown_bars or None,
        )
        reports.append(report)
        reports_by_interval.setdefault(interval, []).append(report)

    if args.portfolio_top_n > 0:
        for interval, interval_reports in sorted(reports_by_interval.items()):
            if not interval_reports:
                continue
            portfolio_report = run_portfolio_backtest(
                interval_reports,
                top_n=args.portfolio_top_n,
                max_concurrent_positions=args.max_concurrent_positions or None,
                max_portfolio_exposure_pct=args.max_portfolio_exposure_pct,
            )
            if portfolio_report is not None:
                portfolio_reports.append(portfolio_report)

    if args.json:
        print(
            json.dumps(
                json_default(
                    {
                        "series_reports": reports,
                        "portfolio_reports": portfolio_reports,
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    for index, report in enumerate(reports):
        if index:
            print()
        print(render_report(report, top_events=args.top_events))

    if portfolio_reports:
        print()
        for index, report in enumerate(portfolio_reports):
            if index:
                print()
            print(render_portfolio_report(report, top_events=args.top_events))


if __name__ == "__main__":
    main()
