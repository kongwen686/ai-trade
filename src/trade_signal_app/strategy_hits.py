from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .strategy import entry_rule_config_from_runtime, evaluate_long_entry


@dataclass(frozen=True)
class StrategyHitScore:
    strategy: str
    score: float
    grade: str
    action: str
    reasons: list[str]


def _read(source: object | None, key: str, default: object = None) -> object:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _float(source: object | None, key: str, default: float = 0.0) -> float:
    try:
        return float(_read(source, key, default) or default)
    except (TypeError, ValueError):
        return default


def _signal_value(signal: object, key: str, default: object = None) -> object:
    direct = _read(signal, key, None)
    if direct is not None:
        return direct
    indicators = _read(signal, "indicators", None)
    indicator_value = _read(indicators, key, None)
    if indicator_value is not None:
        return indicator_value
    ticker = _read(signal, "ticker", None)
    return _read(ticker, key, default)


def _signal_float(signal: object, key: str, default: float = 0.0) -> float:
    try:
        return float(_signal_value(signal, key, default) or default)
    except (TypeError, ValueError):
        return default


def _signal_reasons(signal: object) -> list[str]:
    raw = _signal_value(signal, "reasons", [])
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(reason) for reason in raw if str(reason).strip()]


def _funding_reason(funding: object | None) -> str:
    if funding is None:
        return "资金费率未接入，按现货量价降级观察"
    rate = _float(funding, "funding_rate")
    bps = _float(funding, "funding_rate_bps", rate * 10_000)
    annualized = _float(funding, "annualized_pct", rate * 3 * 365 * 100)
    return f"资金费率 {bps:+.2f}bps/8h，年化 {annualized:+.1f}%"


def score_strategy_hits(
    signal: object,
    *,
    config: object,
    funding: object | None = None,
    spread: object | None = None,
) -> list[StrategyHitScore]:
    base_score = _signal_float(signal, "score")
    grade = str(_signal_value(signal, "grade", "") or ("A" if base_score >= 80 else "B" if base_score >= 65 else "C"))
    change_24h = _signal_float(signal, "price_change_percent")
    volume_ratio = _signal_float(signal, "volume_ratio", 1.0)
    buy_pressure = _signal_float(signal, "buy_pressure_ratio", 0.5)
    rsi = _signal_float(signal, "rsi_14", 50.0)
    price_vs_ema20 = _signal_float(signal, "price_vs_ema20_pct")
    funding_rate = _float(funding, "funding_rate") if funding is not None else 0.0

    context_reasons: list[str] = []
    if funding is not None:
        context_reasons.append(_funding_reason(funding))
    if spread is not None:
        context_reasons.append(f"现货/合约价差 {_float(spread, 'spread_bps'):+.2f}bps")
    base_reasons = [*_signal_reasons(signal)[:3], *context_reasons]

    entry_decision = evaluate_long_entry(
        symbol=str(_signal_value(signal, "symbol", "") or ""),
        score=base_score,
        indicators=_signal_value(signal, "indicators", signal),
        current_price=_signal_float(signal, "last_price"),
        config=entry_rule_config_from_runtime(config),
    )

    hits: list[StrategyHitScore] = []

    def add(strategy: str, score: float, action: str, reasons: list[str]) -> None:
        hits.append(
            StrategyHitScore(
                strategy=strategy,
                score=round(min(100.0, max(0.0, score)), 2),
                grade=grade,
                action=action,
                reasons=[reason for reason in reasons if reason][:5],
            )
        )

    threshold = float(getattr(config, "score_threshold", 75.0))
    if base_score >= threshold:
        action = (
            "candidate_buy"
            if entry_decision.allowed and bool(getattr(config, "enabled", False))
            else "watch"
            if entry_decision.allowed
            else entry_decision.status or "wait_momentum"
        )
        entry_reasons = entry_decision.reasons[-3:]
        add(
            "auto_score_breakout",
            base_score,
            action,
            [*entry_reasons, *base_reasons] or ["综合评分达到自动交易阈值"],
        )
    elif base_score >= 60 or abs(change_24h) >= 1.5:
        add(
            "market_momentum_watch",
            max(base_score, min(74.0, 58.0 + abs(change_24h) * 2)),
            "watch",
            base_reasons or ["实时行情进入观察池", f"24h 涨跌幅 {change_24h:+.2f}%"],
        )

    if volume_ratio >= 1.5 and buy_pressure >= 0.56:
        add("volume_pressure", base_score + 5, "priority_watch", ["量能放大", "主动买盘增强", *base_reasons])

    if base_score >= 68 and 8 <= change_24h <= 120 and volume_ratio >= 2.5 and buy_pressure >= 0.56 and funding_rate <= 0.00035:
        score = base_score + 4 + min(volume_ratio, 8.0) + (3 if funding_rate < 0 else 0)
        add(
            "low_float_momentum_long",
            score,
            "long_watch" if funding is not None else "watch_requires_funding",
            ["早期放量突破", f"24h 涨幅 {change_24h:+.1f}%", f"量能 {volume_ratio:.2f}x", _funding_reason(funding)],
        )

    if funding_rate >= 0.00025 and volume_ratio >= 2.0 and (change_24h >= 35 or rsi >= 78 or price_vs_ema20 >= 25):
        add(
            "blowoff_distribution_short",
            72 + funding_rate * 100_000 + min(volume_ratio * 2, 16),
            "short_watch",
            ["末端分布/拥挤多头候选", f"24h 涨幅 {change_24h:+.1f}%", f"RSI {rsi:.1f}，偏离 EMA20 {price_vs_ema20:+.1f}%", _funding_reason(funding)],
        )

    if funding_rate <= -0.00015 and change_24h <= -15 and (rsi <= 38 or price_vs_ema20 <= -12):
        add(
            "capitulation_rebound_long",
            68 + abs(funding_rate) * 100_000 + max(0.0, 38 - rsi),
            "rebound_long_watch",
            ["暴跌后空头拥挤反弹候选", f"24h 跌幅 {change_24h:+.1f}%", f"RSI {rsi:.1f}，偏离 EMA20 {price_vs_ema20:+.1f}%", _funding_reason(funding)],
        )

    return hits


__all__ = ["StrategyHitScore", "score_strategy_hits"]
