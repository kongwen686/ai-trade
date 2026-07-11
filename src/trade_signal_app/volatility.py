from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

from .models import Candlestick


VOLATILITY_REGIME_LABELS = {
    "compressed": "波动压缩",
    "normal": "常态波动",
    "expansion": "波动扩张",
    "extreme": "极端波动",
}


@dataclass(frozen=True)
class VolatilityState:
    regime: str
    label: str
    realized_volatility_pct: float
    baseline_volatility_pct: float
    volatility_percentile: float
    volatility_ratio: float
    atr_pct: float
    shock_sigma: float


def build_volatility_state(
    candles: list[Candlestick],
    *,
    window: int = 20,
    baseline_window: int = 120,
    atr_window: int = 14,
) -> VolatilityState:
    if len(candles) < 3:
        return _empty_state()

    closes = [float(candle.close_price) for candle in candles if candle.close_price > 0]
    if len(closes) < 3:
        return _empty_state()
    returns = [
        math.log(current / previous) * 100
        for previous, current in zip(closes, closes[1:])
        if previous > 0 and current > 0
    ]
    if len(returns) < 2:
        return _empty_state()

    effective_window = max(2, min(int(window), len(returns)))
    current_volatility = _population_stddev(returns[-effective_window:])
    rolling_volatilities = _rolling_volatilities(
        returns,
        window=effective_window,
        baseline_window=max(effective_window, int(baseline_window)),
    )
    baseline_volatility = statistics.median(rolling_volatilities) if rolling_volatilities else current_volatility
    percentile = _percentile_rank(rolling_volatilities, current_volatility)
    ratio = current_volatility / baseline_volatility if baseline_volatility > 1e-9 else (1.0 if current_volatility <= 1e-9 else 3.0)
    atr_pct = _atr_pct(candles, atr_window=max(2, int(atr_window)))
    shock_sigma = abs(returns[-1]) / current_volatility if current_volatility > 1e-9 else 0.0
    regime = _classify_regime(
        realized_volatility_pct=current_volatility,
        percentile=percentile,
        ratio=ratio,
        atr_pct=atr_pct,
        shock_sigma=shock_sigma,
    )
    return VolatilityState(
        regime=regime,
        label=VOLATILITY_REGIME_LABELS[regime],
        realized_volatility_pct=round(current_volatility, 4),
        baseline_volatility_pct=round(baseline_volatility, 4),
        volatility_percentile=round(percentile, 2),
        volatility_ratio=round(ratio, 4),
        atr_pct=round(atr_pct, 4),
        shock_sigma=round(shock_sigma, 4),
    )


def volatility_entry_reason(
    *,
    regime: str,
    percentile: float,
    ratio: float,
    atr_pct: float,
    enabled: bool,
    block_extreme: bool,
    max_percentile: float,
    max_ratio: float,
) -> str:
    if not enabled:
        return ""
    normalized_regime = str(regime or "normal").lower()
    excessive_ratio = ratio >= max(1.0, float(max_ratio))
    excessive_percentile = percentile >= max(50.0, float(max_percentile)) and ratio >= 1.15
    if (block_extreme and normalized_regime == "extreme") or excessive_ratio or excessive_percentile:
        return (
            f"极端波动过滤：{VOLATILITY_REGIME_LABELS.get(normalized_regime, normalized_regime)}，"
            f"分位 {percentile:.1f}%，波动比 {ratio:.2f}x，ATR {atr_pct:.2f}%；等待波动回落"
        )
    return ""


def _rolling_volatilities(returns: list[float], *, window: int, baseline_window: int) -> list[float]:
    start = max(window, len(returns) - baseline_window + 1)
    prefix_sum = [0.0]
    prefix_square_sum = [0.0]
    for value in returns:
        prefix_sum.append(prefix_sum[-1] + value)
        prefix_square_sum.append(prefix_square_sum[-1] + (value * value))
    values = [
        _population_stddev_from_prefix(prefix_sum, prefix_square_sum, end - window, end)
        for end in range(start, len(returns) + 1)
    ]
    return values or [_population_stddev(returns[-window:])]


def _population_stddev(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(max(variance, 0.0))


def _population_stddev_from_prefix(
    prefix_sum: list[float],
    prefix_square_sum: list[float],
    start: int,
    end: int,
) -> float:
    count = end - start
    if count <= 0:
        return 0.0
    total = prefix_sum[end] - prefix_sum[start]
    square_total = prefix_square_sum[end] - prefix_square_sum[start]
    mean = total / count
    variance = (square_total / count) - (mean * mean)
    return math.sqrt(max(variance, 0.0))


def _percentile_rank(values: list[float], current: float) -> float:
    if not values:
        return 50.0
    below = sum(1 for value in values if value < current)
    equal = sum(1 for value in values if math.isclose(value, current, rel_tol=1e-9, abs_tol=1e-12))
    return ((below + (equal * 0.5)) / len(values)) * 100


def _atr_pct(candles: list[Candlestick], *, atr_window: int) -> float:
    ranges: list[float] = []
    for index, candle in enumerate(candles):
        previous_close = candle.open_price if index == 0 else candles[index - 1].close_price
        ranges.append(
            max(
                candle.high_price - candle.low_price,
                abs(candle.high_price - previous_close),
                abs(candle.low_price - previous_close),
            )
        )
    latest_close = candles[-1].close_price
    if latest_close <= 0:
        return 0.0
    recent = ranges[-min(atr_window, len(ranges)) :]
    return (sum(recent) / max(len(recent), 1) / latest_close) * 100


def _classify_regime(
    *,
    realized_volatility_pct: float,
    percentile: float,
    ratio: float,
    atr_pct: float,
    shock_sigma: float,
) -> str:
    if realized_volatility_pct <= 1e-9 and atr_pct <= 1e-9:
        return "compressed"
    if ratio >= 2.0 or shock_sigma >= 4.0 or (percentile >= 90.0 and ratio >= 1.35):
        return "extreme"
    if percentile >= 70.0 or ratio >= 1.2:
        return "expansion"
    if percentile <= 25.0 and ratio <= 0.85:
        return "compressed"
    return "normal"


def _empty_state() -> VolatilityState:
    return VolatilityState(
        regime="normal",
        label=VOLATILITY_REGIME_LABELS["normal"],
        realized_volatility_pct=0.0,
        baseline_volatility_pct=0.0,
        volatility_percentile=50.0,
        volatility_ratio=1.0,
        atr_pct=0.0,
        shock_sigma=0.0,
    )
