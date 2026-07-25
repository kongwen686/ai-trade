from __future__ import annotations

from dataclasses import dataclass

from .entry_filters import (
    ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT,
    ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT,
    ANTI_CHASE_DEFAULT_MAX_RSI,
    STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT,
    STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT,
    STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO,
    STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH,
    anti_chase_reason,
    structure_entry_reason_from_config,
)
from .models import IndicatorSnapshot
from .volatility import volatility_entry_reason


@dataclass(frozen=True)
class EntryRuleConfig:
    min_score: float = 70.0
    min_volume_ratio: float = 1.10
    min_buy_pressure_ratio: float = 0.52
    min_rsi: float = 45.0
    max_rsi: float = 72.0
    anti_chase_enabled: bool = True
    max_entry_rsi: float = ANTI_CHASE_DEFAULT_MAX_RSI
    max_entry_price_vs_ema20_pct: float = ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT
    max_entry_recent_change_pct: float = ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT
    structure_filter_enabled: bool = False
    max_entry_support_distance_pct: float = STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT
    min_entry_support_strength: float = STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH
    min_entry_risk_reward_ratio: float = STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO
    min_entry_resistance_distance_pct: float = STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT
    volatility_filter_enabled: bool = True
    block_extreme_volatility: bool = True
    max_entry_volatility_percentile: float = 92.0
    max_entry_volatility_ratio: float = 2.0
    require_macd_rising: bool = True
    require_kdj_confirmation: bool = True
    indicator_confluence_enabled: bool = True
    major_trend_breakout_enabled: bool = True
    major_trend_breakout_min_score: float = 85.0
    major_trend_breakout_min_volume_ratio: float = 1.25
    major_trend_breakout_min_buy_pressure: float = 0.55
    major_trend_breakout_max_rsi: float = 70.0
    major_trend_breakout_max_boll_position: float = 1.05
    eth_trend_pullback_enabled: bool = True
    eth_trend_pullback_min_score: float = 90.0
    eth_trend_pullback_max_boll_position: float = 0.80
    eth_trend_pullback_max_atr_pct: float = 2.0
    stop_loss_pct: float = 4.0
    take_profit_pct: float = 9.0

    @property
    def min_buy_pressure(self) -> float:
        return self.min_buy_pressure_ratio


@dataclass(frozen=True)
class ExitRuleConfig:
    max_holding_bars: int = 12
    stop_loss_pct: float = 4.0
    take_profit_pct: float = 9.0
    cooldown_bars_after_exit: int = 0
    conservative_intrabar: bool = True
    structure_exits_enabled: bool = True
    support_stop_buffer_pct: float = 0.6
    resistance_take_profit_buffer_pct: float = 0.4
    profit_protection_enabled: bool = True
    profit_protection_trigger_pct: float = 3.0
    profit_protection_lock_pct: float = 0.5
    trailing_stop_pct: float = 2.0
    trend_hold_enabled: bool = False


@dataclass(frozen=True)
class ExecutionConfig:
    fee_bps: float = 10.0
    fee_model: str = "flat"
    fee_source: str = "manual"
    maker_fee_bps: float = 10.0
    taker_fee_bps: float = 10.0
    entry_fee_role: str = "taker"
    exit_fee_role: str = "taker"
    fee_discount_pct: float = 0.0
    apply_binance_discount: bool = True
    slippage_bps: float = 5.0
    capital_fraction_pct: float = 100.0
    slippage_model: str = "fixed"
    min_slippage_bps: float = 2.0
    max_slippage_bps: float = 25.0
    slippage_window_bars: int = 20
    max_portfolio_exposure_pct: float = 100.0
    max_concurrent_positions: int = 0


@dataclass(frozen=True)
class TriggerDecision:
    allowed: bool
    reasons: list[str]
    status: str = ""
    setup: str = ""


MAJOR_TREND_SYMBOLS = {"BTCUSDT"}
MAJOR_PULLBACK_SYMBOLS = {"ETHUSDT"}
MAJOR_PULLBACK_MIN_BOLL_POSITION = 0.35


def _indicator_value(indicators: object, name: str, default: object) -> object:
    return getattr(indicators, name, default)


def _coerce_indicator_snapshot(indicators: object, current_price: float | None) -> IndicatorSnapshot:
    if isinstance(indicators, IndicatorSnapshot):
        return indicators
    close_price = float(_indicator_value(indicators, "close_price", current_price or 0.0) or current_price or 0.0)
    trend_reference = close_price if close_price > 0 else 1.0
    return IndicatorSnapshot(
        close_price=close_price,
        ema_20=float(_indicator_value(indicators, "ema_20", trend_reference * 0.98) or trend_reference * 0.98),
        ema_50=float(_indicator_value(indicators, "ema_50", trend_reference * 0.95) or trend_reference * 0.95),
        ema_spread_pct=float(_indicator_value(indicators, "ema_spread_pct", 3.0) or 3.0),
        price_vs_ema20_pct=float(_indicator_value(indicators, "price_vs_ema20_pct", 0.0) or 0.0),
        rsi_14=float(_indicator_value(indicators, "rsi_14", 50.0) or 50.0),
        macd=float(_indicator_value(indicators, "macd", 1.0) or 1.0),
        macd_signal=float(_indicator_value(indicators, "macd_signal", 0.5) or 0.5),
        macd_hist=float(_indicator_value(indicators, "macd_hist", 0.5) or 0.5),
        bullish_macd_cross=bool(_indicator_value(indicators, "bullish_macd_cross", False)),
        macd_hist_rising=bool(_indicator_value(indicators, "macd_hist_rising", True)),
        k_value=float(_indicator_value(indicators, "k_value", 60.0) or 60.0),
        d_value=float(_indicator_value(indicators, "d_value", 55.0) or 55.0),
        j_value=float(_indicator_value(indicators, "j_value", 70.0) or 70.0),
        bullish_kdj_cross=bool(_indicator_value(indicators, "bullish_kdj_cross", False)),
        volume_ratio=float(_indicator_value(indicators, "volume_ratio", 1.0) or 1.0),
        buy_pressure_ratio=float(_indicator_value(indicators, "buy_pressure_ratio", 0.5) or 0.5),
        recent_change_pct=float(_indicator_value(indicators, "recent_change_pct", 0.0) or 0.0),
        boll_mb=float(_indicator_value(indicators, "boll_mb", 0.0) or 0.0),
        boll_up=float(_indicator_value(indicators, "boll_up", 0.0) or 0.0),
        boll_dn=float(_indicator_value(indicators, "boll_dn", 0.0) or 0.0),
        boll_bandwidth_pct=float(_indicator_value(indicators, "boll_bandwidth_pct", 0.0) or 0.0),
        boll_position=float(_indicator_value(indicators, "boll_position", 0.5) or 0.5),
        support_level=float(_indicator_value(indicators, "support_level", 0.0) or 0.0),
        resistance_level=float(_indicator_value(indicators, "resistance_level", 0.0) or 0.0),
        support_distance_pct=float(_indicator_value(indicators, "support_distance_pct", 0.0) or 0.0),
        resistance_distance_pct=float(_indicator_value(indicators, "resistance_distance_pct", 0.0) or 0.0),
        support_strength=float(_indicator_value(indicators, "support_strength", 0.0) or 0.0),
        resistance_strength=float(_indicator_value(indicators, "resistance_strength", 0.0) or 0.0),
        structure_risk_reward=float(_indicator_value(indicators, "structure_risk_reward", 0.0) or 0.0),
        pullback_from_high_pct=float(_indicator_value(indicators, "pullback_from_high_pct", 0.0) or 0.0),
        volatility_regime=str(_indicator_value(indicators, "volatility_regime", "normal") or "normal"),
        volatility_label=str(_indicator_value(indicators, "volatility_label", "常态波动") or "常态波动"),
        volatility_percentile=float(_indicator_value(indicators, "volatility_percentile", 50.0) or 50.0),
        volatility_ratio=float(_indicator_value(indicators, "volatility_ratio", 1.0) or 1.0),
        atr_pct=float(_indicator_value(indicators, "atr_pct", 0.0) or 0.0),
        closes=list(_indicator_value(indicators, "closes", []) or []),
    )


def entry_rule_config_from_runtime(config: object) -> EntryRuleConfig:
    return EntryRuleConfig(
        min_score=float(getattr(config, "score_threshold", 75.0)),
        min_volume_ratio=float(getattr(config, "min_volume_ratio", 1.10)),
        min_buy_pressure_ratio=float(getattr(config, "min_buy_pressure", 0.52)),
        max_rsi=float(getattr(config, "max_entry_rsi", 72.0)),
        anti_chase_enabled=bool(getattr(config, "anti_chase_enabled", True)),
        max_entry_rsi=float(getattr(config, "max_entry_rsi", 72.0)),
        max_entry_price_vs_ema20_pct=float(getattr(config, "max_entry_price_vs_ema20_pct", 5.0)),
        max_entry_recent_change_pct=float(getattr(config, "max_entry_recent_change_pct", 4.0)),
        structure_filter_enabled=bool(getattr(config, "structure_filter_enabled", True)),
        max_entry_support_distance_pct=float(getattr(config, "max_entry_support_distance_pct", 2.5)),
        min_entry_support_strength=float(getattr(config, "min_entry_support_strength", 2.0)),
        min_entry_risk_reward_ratio=float(getattr(config, "min_entry_risk_reward_ratio", 1.4)),
        min_entry_resistance_distance_pct=float(getattr(config, "min_entry_resistance_distance_pct", 2.0)),
        volatility_filter_enabled=bool(getattr(config, "volatility_filter_enabled", True)),
        block_extreme_volatility=bool(getattr(config, "block_extreme_volatility", True)),
        max_entry_volatility_percentile=float(getattr(config, "max_entry_volatility_percentile", 92.0)),
        max_entry_volatility_ratio=float(getattr(config, "max_entry_volatility_ratio", 2.0)),
        indicator_confluence_enabled=bool(getattr(config, "indicator_confluence_enabled", True)),
        major_trend_breakout_enabled=bool(getattr(config, "major_trend_breakout_enabled", True)),
        major_trend_breakout_min_score=float(getattr(config, "major_trend_breakout_min_score", 85.0)),
        major_trend_breakout_min_volume_ratio=float(
            getattr(config, "major_trend_breakout_min_volume_ratio", 1.25)
        ),
        major_trend_breakout_min_buy_pressure=float(
            getattr(config, "major_trend_breakout_min_buy_pressure", 0.55)
        ),
        major_trend_breakout_max_rsi=float(getattr(config, "major_trend_breakout_max_rsi", 70.0)),
        major_trend_breakout_max_boll_position=float(
            getattr(config, "major_trend_breakout_max_boll_position", 1.05)
        ),
        eth_trend_pullback_enabled=bool(getattr(config, "eth_trend_pullback_enabled", True)),
        eth_trend_pullback_min_score=float(getattr(config, "eth_trend_pullback_min_score", 90.0)),
        eth_trend_pullback_max_boll_position=float(
            getattr(config, "eth_trend_pullback_max_boll_position", 0.80)
        ),
        eth_trend_pullback_max_atr_pct=float(getattr(config, "eth_trend_pullback_max_atr_pct", 2.0)),
        stop_loss_pct=float(getattr(config, "stop_loss_pct", 4.0)),
        take_profit_pct=float(getattr(config, "take_profit_pct", 9.0)),
    )


def _macd_confirmed(indicators: IndicatorSnapshot, config: EntryRuleConfig) -> bool:
    confirmed = indicators.macd > indicators.macd_signal and indicators.macd_hist > 0
    if config.require_macd_rising:
        confirmed = confirmed and (indicators.macd_hist_rising or indicators.bullish_macd_cross)
    return confirmed


def _kdj_confirmed(indicators: IndicatorSnapshot, config: EntryRuleConfig) -> bool:
    return not config.require_kdj_confirmation or (
        (indicators.bullish_kdj_cross or indicators.k_value > indicators.d_value)
        and indicators.j_value <= 105.0
    )


def _major_breakout_candidate(
    *,
    symbol: str,
    score: float,
    indicators: IndicatorSnapshot,
    config: EntryRuleConfig,
) -> bool:
    return (
        config.indicator_confluence_enabled
        and config.major_trend_breakout_enabled
        and symbol.upper() in MAJOR_TREND_SYMBOLS
        and score >= config.major_trend_breakout_min_score
        and indicators.boll_mb > 0
        and indicators.boll_up > indicators.boll_dn
        and 0.82 <= indicators.boll_position <= config.major_trend_breakout_max_boll_position
        and indicators.close_price >= indicators.boll_mb
        and 52.0 <= indicators.rsi_14 <= config.major_trend_breakout_max_rsi
        and _macd_confirmed(indicators, config)
        and _kdj_confirmed(indicators, config)
    )


def _major_pullback_candidate(
    *,
    symbol: str,
    score: float,
    indicators: IndicatorSnapshot,
    config: EntryRuleConfig,
) -> bool:
    return (
        config.indicator_confluence_enabled
        and config.eth_trend_pullback_enabled
        and symbol.upper() in MAJOR_PULLBACK_SYMBOLS
        and score >= max(config.min_score, config.eth_trend_pullback_min_score)
        and indicators.boll_mb > 0
        and indicators.boll_up > indicators.boll_dn
        and MAJOR_PULLBACK_MIN_BOLL_POSITION
        <= indicators.boll_position
        <= config.eth_trend_pullback_max_boll_position
        and indicators.close_price >= indicators.boll_mb
        and 45.0 <= indicators.rsi_14 <= min(config.max_rsi, 68.0)
        and (indicators.atr_pct <= 0 or indicators.atr_pct <= config.eth_trend_pullback_max_atr_pct)
        and _macd_confirmed(indicators, config)
        and _kdj_confirmed(indicators, config)
    )


def _major_breakout_wait_decision(
    *, score: float, indicators: IndicatorSnapshot, config: EntryRuleConfig
) -> TriggerDecision:
    if score < config.major_trend_breakout_min_score:
        return TriggerDecision(
            False,
            [f"BTC 趋势突破评分 {score:.1f} 低于 {config.major_trend_breakout_min_score:.1f}"],
            status="wait_score",
        )
    if indicators.boll_mb <= 0 or indicators.boll_up <= indicators.boll_dn:
        return TriggerDecision(False, ["BTC 趋势突破等待有效 BOLL 轨道"], status="wait_momentum")
    if indicators.boll_position < 0.82 or indicators.close_price < indicators.boll_mb:
        return TriggerDecision(False, ["BTC 尚未进入 BOLL 上轨趋势确认区"], status="wait_momentum")
    if indicators.boll_position > config.major_trend_breakout_max_boll_position:
        return TriggerDecision(False, ["BTC 已明显超出 BOLL 上轨，等待回踩"], status="wait_pullback")
    if indicators.rsi_14 < 52.0:
        return TriggerDecision(False, ["BTC 突破 RSI 动能不足"], status="wait_momentum")
    if indicators.rsi_14 > config.major_trend_breakout_max_rsi:
        return TriggerDecision(False, ["BTC 突破 RSI 已过热，等待回调"], status="wait_pullback")
    if not _macd_confirmed(indicators, config):
        return TriggerDecision(False, ["BTC 突破缺少 MACD 持续确认"], status="wait_momentum")
    return TriggerDecision(False, ["BTC 突破缺少 KDJ 向上确认"], status="wait_momentum")


def _major_pullback_wait_decision(
    *, score: float, indicators: IndicatorSnapshot, config: EntryRuleConfig
) -> TriggerDecision:
    minimum_score = max(config.min_score, config.eth_trend_pullback_min_score)
    if score < minimum_score:
        return TriggerDecision(
            False,
            [f"ETH 动态回踩评分 {score:.1f} 低于 {minimum_score:.1f}"],
            status="wait_score",
        )
    if indicators.boll_mb <= 0 or indicators.boll_up <= indicators.boll_dn:
        return TriggerDecision(False, ["ETH 动态回踩等待有效 BOLL 轨道"], status="wait_momentum")
    if indicators.boll_position < MAJOR_PULLBACK_MIN_BOLL_POSITION or indicators.close_price < indicators.boll_mb:
        return TriggerDecision(False, ["ETH 尚未站稳 BOLL 中轨动态支撑"], status="wait_momentum")
    if indicators.boll_position > config.eth_trend_pullback_max_boll_position:
        return TriggerDecision(False, ["ETH 距离 BOLL 中轨过远，等待回踩"], status="wait_pullback")
    if indicators.rsi_14 < 45.0:
        return TriggerDecision(False, ["ETH 回踩后的 RSI 动能不足"], status="wait_momentum")
    if indicators.rsi_14 > min(config.max_rsi, 68.0):
        return TriggerDecision(False, ["ETH 回踩形态 RSI 已偏热"], status="wait_pullback")
    if indicators.atr_pct > config.eth_trend_pullback_max_atr_pct:
        return TriggerDecision(
            False,
            [f"ETH 4小时 ATR {indicators.atr_pct:.2f}% 高于 {config.eth_trend_pullback_max_atr_pct:.2f}%"],
            status="wait_volatility",
        )
    if not _macd_confirmed(indicators, config):
        return TriggerDecision(False, ["ETH 回踩缺少 MACD 持续确认"], status="wait_momentum")
    return TriggerDecision(False, ["ETH 回踩缺少 KDJ 向上确认"], status="wait_momentum")


def evaluate_long_entry(
    *,
    score: float,
    indicators: IndicatorSnapshot,
    config: EntryRuleConfig,
    symbol: str = "",
    current_price: float | None = None,
) -> TriggerDecision:
    indicators = _coerce_indicator_snapshot(indicators, current_price)
    reasons: list[str] = []

    if score < config.min_score:
        return TriggerDecision(False, reasons, status="wait_score")

    volatility_issue = volatility_entry_reason(
        regime=indicators.volatility_regime,
        percentile=indicators.volatility_percentile,
        ratio=indicators.volatility_ratio,
        atr_pct=indicators.atr_pct,
        enabled=config.volatility_filter_enabled,
        block_extreme=config.block_extreme_volatility,
        max_percentile=config.max_entry_volatility_percentile,
        max_ratio=config.max_entry_volatility_ratio,
    )
    if volatility_issue:
        return TriggerDecision(False, [volatility_issue], status="wait_volatility")
    reasons.append(f"波动状态可交易：{indicators.volatility_label}")

    if not (indicators.close_price > indicators.ema_20 and indicators.ema_20 > indicators.ema_50):
        return TriggerDecision(False, [*reasons, "EMA20/EMA50 尚未形成多头共振"], status="wait_trend")
    reasons.append("EMA 多头趋势成立")

    breakout_candidate = _major_breakout_candidate(
        symbol=symbol,
        score=score,
        indicators=indicators,
        config=config,
    )
    pullback_candidate = _major_pullback_candidate(
        symbol=symbol,
        score=score,
        indicators=indicators,
        config=config,
    )
    normalized_symbol = symbol.upper()
    if (
        config.indicator_confluence_enabled
        and config.major_trend_breakout_enabled
        and normalized_symbol in MAJOR_TREND_SYMBOLS
        and not breakout_candidate
    ):
        return _major_breakout_wait_decision(score=score, indicators=indicators, config=config)
    if (
        config.indicator_confluence_enabled
        and config.eth_trend_pullback_enabled
        and normalized_symbol in MAJOR_PULLBACK_SYMBOLS
        and not pullback_candidate
    ):
        return _major_pullback_wait_decision(score=score, indicators=indicators, config=config)

    if indicators.rsi_14 < config.min_rsi:
        return TriggerDecision(False, [*reasons, "RSI 动能尚未进入有效区间"], status="wait_momentum")
    effective_max_entry_rsi = config.max_entry_rsi
    if config.max_entry_rsi == ANTI_CHASE_DEFAULT_MAX_RSI and config.max_rsi != ANTI_CHASE_DEFAULT_MAX_RSI:
        effective_max_entry_rsi = config.max_rsi
    anti_chase = anti_chase_reason(
        rsi=indicators.rsi_14,
        price_vs_ema20_pct=indicators.price_vs_ema20_pct,
        recent_change_pct=indicators.recent_change_pct,
        enabled=config.anti_chase_enabled,
        max_rsi=config.major_trend_breakout_max_rsi if breakout_candidate else effective_max_entry_rsi,
        max_price_vs_ema20_pct=(
            max(config.max_entry_price_vs_ema20_pct, 7.0)
            if breakout_candidate
            else max(config.max_entry_price_vs_ema20_pct, 5.5)
            if pullback_candidate
            else config.max_entry_price_vs_ema20_pct
        ),
        max_recent_change_pct=(
            max(config.max_entry_recent_change_pct, 7.0)
            if breakout_candidate
            else max(config.max_entry_recent_change_pct, 6.0)
            if pullback_candidate
            else config.max_entry_recent_change_pct
        ),
    )
    if anti_chase:
        return TriggerDecision(False, [*reasons, anti_chase], status="wait_pullback")
    if indicators.rsi_14 > (config.major_trend_breakout_max_rsi if breakout_candidate else config.max_rsi):
        return TriggerDecision(False, [*reasons, "RSI 已超过当前入场上限"], status="wait_pullback")
    reasons.append("RSI 位于可追踪区间")

    minimum_volume_ratio = (
        max(config.min_volume_ratio, config.major_trend_breakout_min_volume_ratio)
        if breakout_candidate
        else config.min_volume_ratio
    )
    if indicators.volume_ratio < minimum_volume_ratio:
        return TriggerDecision(
            False,
            [*reasons, f"量能确认不足：当前量比 {indicators.volume_ratio:.2f}x，低于 {minimum_volume_ratio:.2f}x"],
            status="wait_volume",
        )
    reasons.append(f"量能放大 {indicators.volume_ratio:.2f}x")

    minimum_buy_pressure = (
        max(config.min_buy_pressure_ratio, config.major_trend_breakout_min_buy_pressure)
        if breakout_candidate
        else config.min_buy_pressure_ratio
    )
    if indicators.buy_pressure_ratio < minimum_buy_pressure:
        return TriggerDecision(
            False,
            [
                *reasons,
                f"主动买盘确认不足：当前买压 {indicators.buy_pressure_ratio * 100:.1f}%，低于 {minimum_buy_pressure * 100:.1f}%",
            ],
            status="wait_buy_pressure",
        )
    reasons.append("主动买盘占优")

    if not _macd_confirmed(indicators, config):
        return TriggerDecision(False, [*reasons, "MACD 动能尚未形成持续确认"], status="wait_momentum")
    reasons.append("MACD 动能确认")

    if not _kdj_confirmed(indicators, config):
        return TriggerDecision(False, [*reasons, "KDJ 尚未形成向上确认或 J 值过热"], status="wait_momentum")
    if config.require_kdj_confirmation:
        reasons.append("KDJ 确认")

    has_boll = indicators.boll_mb > 0 and indicators.boll_up > indicators.boll_dn
    if config.indicator_confluence_enabled and has_boll:
        if indicators.boll_position > config.major_trend_breakout_max_boll_position:
            return TriggerDecision(
                False,
                [*reasons, f"价格超出 BOLL 上轨过多（位置 {indicators.boll_position:.2f}），等待回踩"],
                status="wait_pullback",
            )
        if not breakout_candidate and indicators.close_price < indicators.boll_mb and not indicators.bullish_kdj_cross:
            return TriggerDecision(
                False,
                [*reasons, "价格仍在 BOLL 中轨下方，且 KDJ 未形成回踩反转"],
                status="wait_momentum",
            )
        reasons.append(
            "BOLL 上轨趋势延续确认" if breakout_candidate else "BOLL 中轨与动量位置确认"
        )

    open_upside_breakout = breakout_candidate and indicators.resistance_level <= indicators.close_price
    minor_resistance_pullback = pullback_candidate and (
        indicators.resistance_level <= indicators.close_price
        or indicators.resistance_distance_pct <= config.min_entry_resistance_distance_pct
    )
    structure_support_level = indicators.support_level
    structure_support_distance = indicators.support_distance_pct
    structure_support_strength = indicators.support_strength
    if pullback_candidate:
        dynamic_support = max(indicators.boll_mb, indicators.ema_20)
        if 0 < dynamic_support < indicators.close_price:
            structure_support_level = dynamic_support
            structure_support_distance = ((indicators.close_price - dynamic_support) / indicators.close_price) * 100
            structure_support_strength = max(structure_support_strength, config.min_entry_support_strength)
    structure_issue = ""
    if not open_upside_breakout and not minor_resistance_pullback:
        structure_issue = structure_entry_reason_from_config(
            close_price=indicators.close_price,
            support_level=structure_support_level,
            resistance_level=indicators.resistance_level,
            support_distance_pct=structure_support_distance,
            resistance_distance_pct=indicators.resistance_distance_pct,
            support_strength=structure_support_strength,
            risk_reward_ratio=indicators.structure_risk_reward,
            volume_ratio=indicators.volume_ratio,
            buy_pressure_ratio=indicators.buy_pressure_ratio,
            community_score=None,
            config=config,
        )
    if structure_issue:
        return TriggerDecision(False, [*reasons, structure_issue], status="wait_support")
    if open_upside_breakout or minor_resistance_pullback:
        fixed_risk_reward = config.take_profit_pct / max(config.stop_loss_pct, 0.1)
        if fixed_risk_reward < config.min_entry_risk_reward_ratio:
            return TriggerDecision(
                False,
                [*reasons, f"突破模式固定盈亏比 {fixed_risk_reward:.2f} 不足"],
                status="wait_support",
            )
        reasons.append(
            "主流币开放上行突破，使用固定风险预算"
            if open_upside_breakout
            else "ETH BOLL/EMA 动态支撑确认，允许突破次级阻力"
        )
    elif config.structure_filter_enabled and structure_support_level > 0:
        reasons.append("BOLL 中轨/EMA20 动态支撑确认" if pullback_candidate else "结构支撑与盈亏比确认")

    if breakout_candidate:
        setup = "major_trend_breakout"
    elif pullback_candidate:
        setup = "major_trend_pullback"
    elif has_boll and indicators.boll_position <= 0.65:
        setup = "trend_pullback"
    else:
        setup = "trend_confirmation"
    return TriggerDecision(True, reasons, status="entry_ready", setup=setup)


def conservative_bar_exit(
    *,
    stop_price: float,
    take_price: float,
    low_price: float,
    high_price: float,
) -> str | None:
    hit_stop = low_price <= stop_price
    hit_take = high_price >= take_price
    if hit_stop and hit_take:
        return "stop_loss"
    if hit_stop:
        return "stop_loss"
    if hit_take:
        return "take_profit"
    return None


def normalize_return_pct(value: float) -> float:
    return round(value, 4)
