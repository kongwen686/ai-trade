from __future__ import annotations

from .indicators import clamp
from .models import CommunitySignal, IndicatorSnapshot, MarketTicker, ScoreBreakdown


def _scaled_range(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 50.0
    normalized = (value - lower) / (upper - lower)
    return clamp(normalized * 100, 0, 100)


def compute_liquidity_score(ticker: MarketTicker, quote_volumes: list[float], trade_counts: list[int]) -> float:
    quote_score = _scaled_range(ticker.quote_volume, min(quote_volumes), max(quote_volumes))
    trade_score = _scaled_range(float(ticker.trade_count), float(min(trade_counts)), float(max(trade_counts)))
    return round((quote_score * 0.65) + (trade_score * 0.35), 2)


def build_subscores(
    ticker: MarketTicker,
    indicators: IndicatorSnapshot,
    liquidity_score: float,
    community_signal: CommunitySignal | None,
) -> ScoreBreakdown:
    trend = 0.0
    if indicators.close_price > indicators.ema_20:
        trend += 32
    if indicators.ema_20 > indicators.ema_50:
        trend += 38
    trend += clamp((indicators.ema_spread_pct + 1.5) * 8, 0, 18)
    trend += clamp((4 - abs(indicators.price_vs_ema20_pct - 2)) * 3, 0, 12)

    rsi_score = 0.0
    if 48 <= indicators.rsi_14 <= 62:
        rsi_score = 100
    elif 40 <= indicators.rsi_14 <= 70:
        rsi_score = 80
    elif 30 <= indicators.rsi_14 <= 75:
        rsi_score = 60
    else:
        rsi_score = 25

    macd_score = 30.0
    if indicators.macd > indicators.macd_signal:
        macd_score += 35
    if indicators.macd_hist > 0:
        macd_score += 20
    if indicators.macd_hist_rising:
        macd_score += 10
    if indicators.bullish_macd_cross:
        macd_score += 5
    momentum = clamp((macd_score * 0.6) + (rsi_score * 0.4), 0, 100)

    kdj_score = 25.0
    if indicators.k_value > indicators.d_value:
        kdj_score += 25
    if indicators.bullish_kdj_cross:
        kdj_score += 25
    if indicators.j_value < 90:
        kdj_score += 10
    if indicators.k_value < 65:
        kdj_score += 15

    extension_penalty = clamp(abs(indicators.price_vs_ema20_pct) * 4, 0, 30)
    timing = clamp(kdj_score + (30 - extension_penalty), 0, 100)

    volume = clamp((indicators.volume_ratio * 35) + (indicators.buy_pressure_ratio * 40), 0, 100)

    market = 45.0
    if 0.5 <= ticker.price_change_percent <= 8:
        market = 85.0
    elif -2 <= ticker.price_change_percent < 0.5:
        market = 65.0
    elif ticker.price_change_percent > 8:
        market = 55.0
    elif ticker.price_change_percent < -2:
        market = 30.0

    community = None if community_signal is None else clamp(community_signal.score, 0, 100)

    return ScoreBreakdown(
        trend=round(clamp(trend, 0, 100), 2),
        momentum=round(momentum, 2),
        timing=round(timing, 2),
        volume=round(volume, 2),
        liquidity=round(liquidity_score, 2),
        market=round(market, 2),
        community=None if community is None else round(community, 2),
    )


def composite_score(breakdown: ScoreBreakdown) -> float:
    weights = {
        "trend": 0.24,
        "momentum": 0.18,
        "timing": 0.14,
        "volume": 0.16,
        "liquidity": 0.10,
        "market": 0.08,
        "community": 0.10,
    }
    values = {
        "trend": breakdown.trend,
        "momentum": breakdown.momentum,
        "timing": breakdown.timing,
        "volume": breakdown.volume,
        "liquidity": breakdown.liquidity,
        "market": breakdown.market,
        "community": breakdown.community,
    }

    available = {name: weight for name, weight in weights.items() if values[name] is not None}
    weight_total = sum(available.values())
    score = 0.0
    for name, weight in available.items():
        score += (values[name] or 0.0) * (weight / weight_total)
    return round(score, 2)


def grade_from_score(score: float) -> str:
    if score >= 85:
        return "A+"
    if score >= 78:
        return "A"
    if score >= 70:
        return "B"
    if score >= 62:
        return "C"
    return "Watch"


def build_reasons(ticker: MarketTicker, indicators: IndicatorSnapshot, community_signal: CommunitySignal | None) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    if indicators.ema_20 > indicators.ema_50 and indicators.close_price > indicators.ema_20:
        reasons.append("EMA20/EMA50 多头排列")
    if indicators.bullish_macd_cross or (indicators.macd > indicators.macd_signal and indicators.macd_hist > 0):
        reasons.append("MACD 动能转强")
    if 45 <= indicators.rsi_14 <= 65:
        reasons.append("RSI 位于健康强势区")
    if indicators.volume_ratio >= 1.4:
        reasons.append(f"量能放大 {indicators.volume_ratio:.2f}x")
    if indicators.bullish_kdj_cross or indicators.k_value > indicators.d_value:
        reasons.append("KDJ 上拐确认")
    if ticker.price_change_percent > 0:
        reasons.append(f"24h 涨幅 {ticker.price_change_percent:.2f}%")
    if community_signal and community_signal.score >= 70:
        reasons.append(f"社区热度较高 ({community_signal.source})")

    if indicators.rsi_14 >= 72:
        warnings.append("RSI 过热，追高风险增大")
    if indicators.price_vs_ema20_pct >= 7:
        warnings.append("价格偏离 EMA20 过大")
    if indicators.volume_ratio < 0.9:
        warnings.append("最近一根 K 线量能不足")
    if ticker.price_change_percent <= -3:
        warnings.append("24h 价格仍偏弱")

    return reasons[:4], warnings[:3]
