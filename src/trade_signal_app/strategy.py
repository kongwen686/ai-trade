from __future__ import annotations

from dataclasses import dataclass

from .models import IndicatorSnapshot


@dataclass(frozen=True)
class EntryRuleConfig:
    min_score: float = 70.0
    min_volume_ratio: float = 1.10
    min_buy_pressure_ratio: float = 0.52
    min_rsi: float = 45.0
    max_rsi: float = 72.0
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

    if not (indicators.close_price > indicators.ema_20 and indicators.ema_20 > indicators.ema_50):
        return TriggerDecision(False, reasons)
    reasons.append("EMA 多头趋势成立")

    if not (config.min_rsi <= indicators.rsi_14 <= config.max_rsi):
        return TriggerDecision(False, reasons)
    reasons.append("RSI 位于可追踪区间")

    if indicators.volume_ratio < config.min_volume_ratio:
        return TriggerDecision(False, reasons)
    reasons.append(f"量能放大 {indicators.volume_ratio:.2f}x")

    if indicators.buy_pressure_ratio < config.min_buy_pressure_ratio:
        return TriggerDecision(False, reasons)
    reasons.append("主动买盘占优")

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
