from __future__ import annotations

from datetime import datetime, timezone

from .models import Candlestick, IndicatorSnapshot
from .volatility import build_volatility_state


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []

    smoothing = 2 / (period + 1)
    current = values[0]
    result = [current]
    for value in values[1:]:
        current = (value * smoothing) + (current * (1 - smoothing))
        result.append(current)
    return result


def rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) < 2:
        return [50.0 for _ in values]

    gains = [0.0]
    losses = [0.0]
    for previous, current in zip(values, values[1:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[1 : period + 1]) / period if len(gains) > period else sum(gains[1:]) / max(len(gains) - 1, 1)
    avg_loss = sum(losses[1 : period + 1]) / period if len(losses) > period else sum(losses[1:]) / max(len(losses) - 1, 1)

    series = [50.0] * min(period, len(values))
    for index in range(period, len(values)):
        if index > period:
            avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period

        if avg_loss == 0:
            series.append(100.0)
            continue

        relative_strength = avg_gain / avg_loss
        series.append(100 - (100 / (1 + relative_strength)))
    return series[: len(values)]


def macd(values: list[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> tuple[list[float], list[float], list[float]]:
    fast = ema(values, fast_period)
    slow = ema(values, slow_period)
    line = [fast_value - slow_value for fast_value, slow_value in zip(fast, slow)]
    signal = ema(line, signal_period)
    hist = [macd_value - signal_value for macd_value, signal_value in zip(line, signal)]
    return line, signal, hist


def stochastic_kdj(highs: list[float], lows: list[float], closes: list[float], period: int = 9) -> tuple[list[float], list[float], list[float]]:
    if not closes:
        return [], [], []

    k_values: list[float] = []
    d_values: list[float] = []
    j_values: list[float] = []
    k_current = 50.0
    d_current = 50.0

    for index, close_value in enumerate(closes):
        start = max(0, index - period + 1)
        highest = max(highs[start : index + 1])
        lowest = min(lows[start : index + 1])
        if highest == lowest:
            rsv = 50.0
        else:
            rsv = ((close_value - lowest) / (highest - lowest)) * 100

        k_current = ((2 / 3) * k_current) + ((1 / 3) * rsv)
        d_current = ((2 / 3) * d_current) + ((1 / 3) * k_current)
        j_current = (3 * k_current) - (2 * d_current)

        k_values.append(k_current)
        d_values.append(d_current)
        j_values.append(j_current)

    return k_values, d_values, j_values


def _level_strength(values: list[float], level: float, tolerance_pct: float = 0.006) -> float:
    if level <= 0:
        return 0.0
    tolerance = level * tolerance_pct
    return float(sum(1 for value in values if abs(value - level) <= tolerance))


def _nearest_structure_levels(
    *,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    lookback: int = 48,
) -> dict[str, float]:
    latest_close = closes[-1]
    start = max(0, len(closes) - lookback)
    previous_lows = lows[start:-1] or lows[start:]
    previous_highs = highs[start:-1] or highs[start:]
    support_candidates = [low for low in previous_lows if low <= latest_close]
    resistance_candidates = [high for high in previous_highs if high >= latest_close]

    support_level = max(support_candidates) if support_candidates else min(previous_lows)
    resistance_level = min(resistance_candidates) if resistance_candidates else max(previous_highs)
    support_distance_pct = ((latest_close - support_level) / latest_close) * 100 if latest_close and support_level <= latest_close else 0.0
    resistance_distance_pct = ((resistance_level - latest_close) / latest_close) * 100 if latest_close and resistance_level > latest_close else 0.0
    support_strength = _level_strength(previous_lows, support_level)
    resistance_strength = _level_strength(previous_highs, resistance_level)
    recent_high = max(previous_highs + [highs[-1]])
    pullback_from_high_pct = ((recent_high - latest_close) / recent_high) * 100 if recent_high else 0.0
    risk_pct = max(support_distance_pct + 0.6, 0.1)
    reward_pct = max(resistance_distance_pct - 0.4, 0.0)
    structure_risk_reward = reward_pct / risk_pct if risk_pct else 0.0

    return {
        "support_level": support_level,
        "resistance_level": resistance_level,
        "support_distance_pct": support_distance_pct,
        "resistance_distance_pct": resistance_distance_pct,
        "support_strength": support_strength,
        "resistance_strength": resistance_strength,
        "structure_risk_reward": structure_risk_reward,
        "pullback_from_high_pct": pullback_from_high_pct,
    }


def _volume_ratio(candles: list[Candlestick], volumes: list[float], *, as_of: datetime) -> float:
    previous_volume_window = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
    avg_volume = sum(previous_volume_window) / max(len(previous_volume_window), 1)
    raw_ratio = volumes[-1] / avg_volume if avg_volume else 1.0
    latest = candles[-1]
    if latest.close_time <= as_of or latest.open_time >= as_of or len(volumes) < 3:
        return raw_ratio

    duration = (latest.close_time - latest.open_time).total_seconds()
    elapsed = (as_of - latest.open_time).total_seconds()
    if duration <= 0 or elapsed <= 0:
        return raw_ratio

    progress = clamp(elapsed / duration, 0.0, 1.0)
    earlier_window = volumes[-22:-2] if len(volumes) >= 22 else volumes[:-2]
    earlier_avg = sum(earlier_window) / max(len(earlier_window), 1)
    previous_closed_ratio = volumes[-2] / earlier_avg if earlier_avg else 1.0
    # Blend observed current volume with the last closed bar for the unfinished
    # portion. This removes the strong time-of-bar bias without extrapolating a
    # few early trades into an extreme volume spike.
    return raw_ratio + ((1.0 - progress) * previous_closed_ratio)


def build_indicator_snapshot(candles: list[Candlestick], *, as_of: datetime | None = None) -> IndicatorSnapshot:
    if len(candles) < 60:
        raise ValueError("At least 60 klines are required to compute stable indicators.")

    closes = [candle.close_price for candle in candles]
    highs = [candle.high_price for candle in candles]
    lows = [candle.low_price for candle in candles]
    volumes = [candle.volume for candle in candles]
    taker_buy_ratios = [
        candle.taker_buy_base_volume / candle.volume if candle.volume else 0.5 for candle in candles
    ]

    ema_20_series = ema(closes, 20)
    ema_50_series = ema(closes, 50)
    rsi_series = rsi(closes, 14)
    macd_line, macd_signal, macd_hist = macd(closes)
    k_values, d_values, j_values = stochastic_kdj(highs, lows, closes, 9)

    latest_close = closes[-1]
    latest_ema_20 = ema_20_series[-1]
    latest_ema_50 = ema_50_series[-1]
    effective_as_of = as_of or datetime.now(timezone.utc)
    volume_ratio = _volume_ratio(candles, volumes, as_of=effective_as_of)
    structure = _nearest_structure_levels(highs=highs, lows=lows, closes=closes)
    volatility = build_volatility_state(candles)

    return IndicatorSnapshot(
        close_price=latest_close,
        ema_20=latest_ema_20,
        ema_50=latest_ema_50,
        ema_spread_pct=((latest_ema_20 - latest_ema_50) / latest_ema_50) * 100 if latest_ema_50 else 0.0,
        price_vs_ema20_pct=((latest_close - latest_ema_20) / latest_ema_20) * 100 if latest_ema_20 else 0.0,
        rsi_14=rsi_series[-1],
        macd=macd_line[-1],
        macd_signal=macd_signal[-1],
        macd_hist=macd_hist[-1],
        bullish_macd_cross=macd_line[-2] <= macd_signal[-2] and macd_line[-1] > macd_signal[-1],
        macd_hist_rising=macd_hist[-1] > macd_hist[-2],
        k_value=k_values[-1],
        d_value=d_values[-1],
        j_value=j_values[-1],
        bullish_kdj_cross=k_values[-2] <= d_values[-2] and k_values[-1] > d_values[-1],
        volume_ratio=volume_ratio,
        buy_pressure_ratio=taker_buy_ratios[-1],
        recent_change_pct=((latest_close - closes[-7]) / closes[-7]) * 100 if len(closes) > 6 and closes[-7] else 0.0,
        support_level=structure["support_level"],
        resistance_level=structure["resistance_level"],
        support_distance_pct=structure["support_distance_pct"],
        resistance_distance_pct=structure["resistance_distance_pct"],
        support_strength=structure["support_strength"],
        resistance_strength=structure["resistance_strength"],
        structure_risk_reward=structure["structure_risk_reward"],
        pullback_from_high_pct=structure["pullback_from_high_pct"],
        volatility_regime=volatility.regime,
        volatility_label=volatility.label,
        realized_volatility_pct=volatility.realized_volatility_pct,
        baseline_volatility_pct=volatility.baseline_volatility_pct,
        volatility_percentile=volatility.volatility_percentile,
        volatility_ratio=volatility.volatility_ratio,
        atr_pct=volatility.atr_pct,
        volatility_shock_sigma=volatility.shock_sigma,
        closes=closes[-48:],
    )
