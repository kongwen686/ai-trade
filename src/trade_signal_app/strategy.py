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


@dataclass(frozen=True)
class ExitRuleConfig:
    max_holding_bars: int = 12
    stop_loss_pct: float = 4.0
    take_profit_pct: float = 9.0
    cooldown_bars_after_exit: int = 0
    conservative_intrabar: bool = True


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


def evaluate_long_entry(
    *,
    score: float,
    indicators: IndicatorSnapshot,
    config: EntryRuleConfig,
) -> TriggerDecision:
    reasons: list[str] = []

    if score < config.min_score:
        return TriggerDecision(False, reasons)

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
        return TriggerDecision(False, [volatility_issue])
    reasons.append(f"波动状态可交易：{indicators.volatility_label}")

    if not (indicators.close_price > indicators.ema_20 and indicators.ema_20 > indicators.ema_50):
        return TriggerDecision(False, reasons)
    reasons.append("EMA 多头趋势成立")

    if indicators.rsi_14 < config.min_rsi:
        return TriggerDecision(False, reasons)
    effective_max_entry_rsi = config.max_entry_rsi
    if config.max_entry_rsi == ANTI_CHASE_DEFAULT_MAX_RSI and config.max_rsi != ANTI_CHASE_DEFAULT_MAX_RSI:
        effective_max_entry_rsi = config.max_rsi
    anti_chase = anti_chase_reason(
        rsi=indicators.rsi_14,
        price_vs_ema20_pct=indicators.price_vs_ema20_pct,
        recent_change_pct=indicators.recent_change_pct,
        enabled=config.anti_chase_enabled,
        max_rsi=effective_max_entry_rsi,
        max_price_vs_ema20_pct=config.max_entry_price_vs_ema20_pct,
        max_recent_change_pct=config.max_entry_recent_change_pct,
    )
    if anti_chase:
        return TriggerDecision(False, [*reasons, anti_chase])
    if indicators.rsi_14 > config.max_rsi:
        return TriggerDecision(False, reasons)
    reasons.append("RSI 位于可追踪区间")

    if indicators.volume_ratio < config.min_volume_ratio:
        return TriggerDecision(False, reasons)
    reasons.append(f"量能放大 {indicators.volume_ratio:.2f}x")

    if indicators.buy_pressure_ratio < config.min_buy_pressure_ratio:
        return TriggerDecision(False, reasons)
    reasons.append("主动买盘占优")

    structure_issue = structure_entry_reason_from_config(
        close_price=indicators.close_price,
        support_level=indicators.support_level,
        resistance_level=indicators.resistance_level,
        support_distance_pct=indicators.support_distance_pct,
        resistance_distance_pct=indicators.resistance_distance_pct,
        support_strength=indicators.support_strength,
        risk_reward_ratio=indicators.structure_risk_reward,
        volume_ratio=indicators.volume_ratio,
        buy_pressure_ratio=indicators.buy_pressure_ratio,
        community_score=None,
        config=config,
    )
    if structure_issue:
        return TriggerDecision(False, [*reasons, structure_issue])
    if config.structure_filter_enabled and indicators.support_level > 0:
        reasons.append("结构支撑与盈亏比确认")

    macd_confirmed = indicators.macd > indicators.macd_signal and indicators.macd_hist > 0
    if config.require_macd_rising:
        macd_confirmed = macd_confirmed and (
            indicators.macd_hist_rising or indicators.bullish_macd_cross
        )
    if not macd_confirmed:
        return TriggerDecision(False, reasons)
    reasons.append("MACD 动能确认")

    if config.require_kdj_confirmation and not (
        indicators.bullish_kdj_cross or indicators.k_value > indicators.d_value
    ):
        return TriggerDecision(False, reasons)
    if config.require_kdj_confirmation:
        reasons.append("KDJ 确认")

    return TriggerDecision(True, reasons)


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
