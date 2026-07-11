from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import math
import statistics

from .backtest import (
    bars_per_day,
    build_historical_ticker,
    rolling_liquidity_baseline,
    run_backtest_for_series,
    run_overnight_seasonality_backtest,
)
from .indicators import build_indicator_snapshot, clamp, ema, rsi
from .models import BacktestReport, Candlestick
from .presets import get_backtest_preset
from .scoring import build_reasons, build_subscores, composite_score, compute_liquidity_score, grade_from_score
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig, evaluate_long_entry
from .time_utils import APP_TIMEZONE, now_app_time, to_app_time
from .tradingview_data import load_tradingview_csv, tradingview_cache_path


BTC_SYMBOL = "BTCUSDT"
BTC_EXCHANGE = "BINANCE"
BTC_SIGNAL_INTERVAL = "4h"
BTC_DAILY_INTERVAL = "1d"
BTC_ENTRY_INTERVAL = "1h"
BTC_LEVERAGE_REFERENCE = 5.0
BTC_PRESET_IDS = (
    "btc_cycle_trend",
    "btc_core_trading",
    "btc_compounding_risk_off",
    "btc_overnight_seasonality",
)


@dataclass(frozen=True)
class BtcTimeframes:
    primary: list[Candlestick]
    daily: list[Candlestick]
    entry: list[Candlestick]


def build_btc_signal_summary(
    *,
    cache_root: Path,
    exchange: str = BTC_EXCHANGE,
    generated_at: datetime | None = None,
    include_backtests: bool = True,
    market_price: float | None = None,
) -> dict[str, object]:
    timeframes = load_btc_timeframes(cache_root=cache_root, exchange=exchange)
    return build_btc_signal_from_candles(
        primary_candles=timeframes.primary,
        daily_candles=timeframes.daily,
        entry_candles=timeframes.entry,
        exchange=exchange,
        generated_at=generated_at,
        include_backtests=include_backtests,
        market_price=market_price,
    )


def load_btc_timeframes(*, cache_root: Path, exchange: str = BTC_EXCHANGE) -> BtcTimeframes:
    primary = _load_cached_candles(cache_root=cache_root, exchange=exchange, interval=BTC_SIGNAL_INTERVAL)
    daily = _load_cached_candles(cache_root=cache_root, exchange=exchange, interval=BTC_DAILY_INTERVAL, required=False) or primary
    entry = _load_cached_candles(cache_root=cache_root, exchange=exchange, interval=BTC_ENTRY_INTERVAL, required=False) or primary
    if len(primary) < 260:
        raise ValueError(f"{BTC_SYMBOL} {BTC_SIGNAL_INTERVAL} 历史 K 线不足，至少需要 260 根。")
    return BtcTimeframes(primary=primary, daily=daily, entry=entry)


def build_btc_signal_from_candles(
    *,
    primary_candles: list[Candlestick],
    daily_candles: list[Candlestick] | None = None,
    entry_candles: list[Candlestick] | None = None,
    exchange: str = BTC_EXCHANGE,
    generated_at: datetime | None = None,
    include_backtests: bool = True,
    market_price: float | None = None,
) -> dict[str, object]:
    if len(primary_candles) < 260:
        raise ValueError(f"{BTC_SYMBOL} {BTC_SIGNAL_INTERVAL} 历史 K 线不足，至少需要 260 根。")

    daily_candles = daily_candles or primary_candles
    entry_candles = entry_candles or primary_candles
    generated = (generated_at or now_app_time()).astimezone(APP_TIMEZONE)
    primary = sorted(primary_candles, key=lambda candle: candle.open_time)
    daily = sorted(daily_candles, key=lambda candle: candle.open_time)
    entry = sorted(entry_candles, key=lambda candle: candle.open_time)
    latest = primary[-1]
    latest_market_price = float(market_price or 0.0)
    current_price = latest_market_price if latest_market_price > 0 else latest.close_price
    primary_for_signal = _candles_with_live_price(primary, current_price) if latest_market_price > 0 else primary
    daily_for_signal = _candles_with_live_price(daily, current_price) if latest_market_price > 0 else daily
    entry_for_signal = _candles_with_live_price(entry, current_price) if latest_market_price > 0 else entry
    history = primary_for_signal[-300:]
    indicators = build_indicator_snapshot(history)
    technical_score, technical_context = _technical_score(primary=primary_for_signal, indicators=indicators)
    regime = _regime_metrics(primary=primary_for_signal, daily=daily_for_signal, entry=entry_for_signal, indicators=indicators)
    preset_context = _btc_preset_backtests(primary=primary, entry=entry) if include_backtests else []
    backtest_score = _backtest_quality_score(preset_context)
    score = round((technical_score * 0.45) + (regime["score"] * 0.35) + (backtest_score * 0.20), 2)
    grade = grade_from_score(score)
    selected_preset = _select_preset(preset_context)
    trade_levels = _trade_levels(indicators=indicators, close_price=current_price, selected_preset=selected_preset)
    action_context = _action_decision(
        score=score,
        indicators=indicators,
        regime=regime,
        technical_context=technical_context,
        trade_levels=trade_levels,
    )
    stats = _btc_statistics(primary=primary, daily=daily, entry=entry)
    reasons, warnings = _btc_reasons_and_warnings(
        action=action_context["action"],
        indicators=indicators,
        regime=regime,
        technical_context=technical_context,
        preset_context=preset_context,
        trade_levels=trade_levels,
    )

    return {
        "symbol": BTC_SYMBOL,
        "exchange": exchange.upper(),
        "generated_at": generated.isoformat(),
        "signal_time": to_app_time(latest.close_time).isoformat(),
        "interval": BTC_SIGNAL_INTERVAL,
        "action": action_context["action"],
        "action_label": action_context["action_label"],
        "signal": action_context["signal"],
        "advice": action_context["advice"],
        "score": score,
        "grade": grade,
        "confidence": _confidence_label(score=score, action=action_context["action"], warnings=warnings),
        "price": current_price,
        "analysis_price": latest.close_price,
        "price_source": "live_market" if latest_market_price > 0 else "cached_kline_close",
        "trade_levels": trade_levels,
        "regime": regime,
        "technical": {
            **technical_context,
            "indicator_snapshot": {
                "ema_20": round(indicators.ema_20, 8),
                "ema_50": round(indicators.ema_50, 8),
                "ema_200": round(regime["ema_200"], 8),
                "rsi_14": round(indicators.rsi_14, 2),
                "macd_hist": round(indicators.macd_hist, 8),
                "volume_ratio": round(indicators.volume_ratio, 4),
                "buy_pressure_ratio": round(indicators.buy_pressure_ratio, 4),
                "support_level": round(indicators.support_level, 8),
                "resistance_level": round(indicators.resistance_level, 8),
                "structure_risk_reward": round(indicators.structure_risk_reward, 4),
                "closes": [round(value, 8) for value in indicators.closes[-48:]],
            },
        },
        "preset_backtests": preset_context,
        "selected_preset": selected_preset,
        "statistics": stats,
        "reasons": reasons,
        "warnings": warnings,
    }


def _candles_with_live_price(candles: list[Candlestick], live_price: float) -> list[Candlestick]:
    if not candles or live_price <= 0:
        return candles
    latest = candles[-1]
    return [
        *candles[:-1],
        replace(
            latest,
            high_price=max(latest.high_price, live_price),
            low_price=min(latest.low_price, live_price),
            close_price=live_price,
        ),
    ]


def _load_cached_candles(
    *,
    cache_root: Path,
    exchange: str,
    interval: str,
    required: bool = True,
) -> list[Candlestick]:
    path = tradingview_cache_path(cache_root, exchange, BTC_SYMBOL, interval)
    if not path.exists():
        if required:
            raise ValueError(f"未找到 {exchange.upper()}:{BTC_SYMBOL} {interval} 本地 TradingView 缓存：{path}")
        return []
    return load_tradingview_csv(path, interval=interval)


def _technical_score(*, primary: list[Candlestick], indicators: object) -> tuple[float, dict[str, object]]:
    day_bars = bars_per_day(primary)
    ticker = build_historical_ticker(BTC_SYMBOL, primary, len(primary) - 1, day_bars)
    quote_volumes, trade_counts = rolling_liquidity_baseline(BTC_SYMBOL, primary, len(primary) - 1, day_bars, history_windows=90)
    liquidity_score = compute_liquidity_score(ticker, quote_volumes, trade_counts)
    breakdown = build_subscores(
        ticker=ticker,
        indicators=indicators,
        liquidity_score=liquidity_score,
        community_signal=None,
    )
    score = composite_score(breakdown)
    reasons, warnings = build_reasons(ticker, indicators, None)
    return score, {
        "score": score,
        "breakdown": {
            "trend": breakdown.trend,
            "momentum": breakdown.momentum,
            "timing": breakdown.timing,
            "volume": breakdown.volume,
            "liquidity": breakdown.liquidity,
            "market": breakdown.market,
        },
        "liquidity_score": liquidity_score,
        "price_change_24h_pct": round(ticker.price_change_percent, 4),
        "reasons": reasons,
        "warnings": warnings,
    }


def _regime_metrics(
    *,
    primary: list[Candlestick],
    daily: list[Candlestick],
    entry: list[Candlestick],
    indicators: object,
) -> dict[str, object]:
    closes = [candle.close_price for candle in primary]
    daily_closes = [candle.close_price for candle in daily]
    entry_closes = [candle.close_price for candle in entry]
    ema_20 = indicators.ema_20
    ema_50 = indicators.ema_50
    ema_200 = ema(closes, 200)[-1]
    daily_ema_50 = ema(daily_closes, min(50, len(daily_closes)))[-1] if daily_closes else ema_50
    daily_ema_200 = ema(daily_closes, min(200, len(daily_closes)))[-1] if daily_closes else ema_200
    hourly_rsi = rsi(entry_closes, 14)[-1] if len(entry_closes) >= 14 else indicators.rsi_14
    return_24h = _window_return_pct(entry, 24 if len(entry) >= 24 else min(6, len(primary) - 1))
    return_7d = _window_return_pct(primary, bars_per_day(primary) * 7)
    close = closes[-1]

    score = 0.0
    if close > ema_200:
        score += 20
    if ema_20 > ema_50:
        score += 18
    if ema_50 > ema_200:
        score += 16
    if daily_closes and daily_closes[-1] > daily_ema_200:
        score += 18
    if 45 <= indicators.rsi_14 <= 68:
        score += 10
    elif 38 <= indicators.rsi_14 <= 74:
        score += 6
    if indicators.support_distance_pct <= 3.5 and indicators.structure_risk_reward >= 1.2:
        score += 10
    if return_24h <= 6 and indicators.price_vs_ema20_pct <= 4.5:
        score += 8
    score = round(clamp(score, 0, 100), 2)

    if close < ema_200 or (daily_closes and daily_closes[-1] < daily_ema_200):
        label = "风险收缩"
    elif ema_20 > ema_50 > ema_200 and (not daily_closes or daily_closes[-1] > daily_ema_200):
        label = "多头趋势"
    elif close > ema_200:
        label = "震荡偏多"
    else:
        label = "震荡观察"

    return {
        "label": label,
        "score": score,
        "ema_200": ema_200,
        "daily_ema_50": daily_ema_50,
        "daily_ema_200": daily_ema_200,
        "close_vs_ema200_pct": _pct(close, ema_200),
        "daily_close_vs_ema200_pct": _pct(daily_closes[-1], daily_ema_200) if daily_closes else 0.0,
        "entry_rsi_14": round(hourly_rsi, 2),
        "entry_return_24h_pct": round(return_24h, 4),
        "return_7d_pct": round(return_7d, 4),
        "trend_bullish": bool(close > ema_200 and ema_20 > ema_50),
        "daily_bullish": bool(not daily_closes or daily_closes[-1] > daily_ema_200),
    }


def _btc_preset_backtests(*, primary: list[Candlestick], entry: list[Candlestick]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for preset_id in BTC_PRESET_IDS:
        preset = get_backtest_preset(preset_id)
        values = preset.values
        try:
            if preset_id == "btc_overnight_seasonality":
                report = run_overnight_seasonality_backtest(
                    symbol=BTC_SYMBOL,
                    interval=BTC_ENTRY_INTERVAL,
                    candles=entry,
                    open_hour_utc=22,
                    hold_hours=2,
                    execution_config=_execution_config(values),
                )
            else:
                report = run_backtest_for_series(
                    symbol=BTC_SYMBOL,
                    interval=BTC_SIGNAL_INTERVAL,
                    candles=primary,
                    lookback_bars=_int_value(values, "lookback_bars", 240),
                    score_threshold=_float_value(values, "score_threshold", 70.0),
                    holding_periods=_holding_periods(values),
                    entry_config=_entry_config(values),
                    exit_config=_exit_config(values),
                    execution_config=_execution_config(values),
                    cooldown_bars=_int_value(values, "cooldown_bars", 0),
                    sample_start_time=None,
                )
            results.append(_preset_report_payload(preset_id=preset_id, label=preset.label, report=report))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "preset_id": preset_id,
                    "label": preset.label,
                    "status": "error",
                    "error": str(exc),
                    "quality_score": 0.0,
                }
            )
    return results


def _preset_report_payload(*, preset_id: str, label: str, report: BacktestReport) -> dict[str, object]:
    trade_stat = report.trade_stat
    final_equity = report.equity_curve[-1].equity if report.equity_curve else 1.0
    max_drawdown = min((point.drawdown_pct for point in report.equity_curve), default=0.0)
    win_rate = trade_stat.win_rate_pct if trade_stat is not None else 0.0
    avg_return = trade_stat.avg_return_pct if trade_stat is not None else 0.0
    profit_factor = trade_stat.profit_factor if trade_stat is not None else 0.0
    quality_score = _quality_score(
        signal_count=report.signal_count,
        win_rate_pct=win_rate,
        avg_return_pct=avg_return,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown,
    )
    return {
        "preset_id": preset_id,
        "label": label,
        "status": "ok",
        "candle_count": report.candle_count,
        "evaluated_bars": report.evaluated_bars,
        "signal_count": report.signal_count,
        "win_rate_pct": round(win_rate, 2),
        "avg_return_pct": round(avg_return, 4),
        "profit_factor": round(profit_factor, 4),
        "final_equity": round(final_equity, 6),
        "max_drawdown_pct": round(max_drawdown, 4),
        "quality_score": quality_score,
    }


def _quality_score(
    *,
    signal_count: int,
    win_rate_pct: float,
    avg_return_pct: float,
    profit_factor: float,
    max_drawdown_pct: float,
) -> float:
    if signal_count <= 0:
        return 0.0
    win_component = clamp(win_rate_pct, 0, 100) * 0.42
    return_component = clamp((avg_return_pct + 2.0) * 12, 0, 24)
    profit_component = clamp(profit_factor, 0, 3.0) / 3.0 * 22
    drawdown_component = clamp(18 - abs(min(max_drawdown_pct, 0.0)) * 0.7, 0, 18)
    activity_component = clamp(signal_count / 20, 0, 1) * 14
    return round(clamp(win_component + return_component + profit_component + drawdown_component + activity_component, 0, 100), 2)


def _backtest_quality_score(preset_context: list[dict[str, object]]) -> float:
    ok_scores = [
        float(item.get("quality_score") or 0.0)
        for item in preset_context
        if str(item.get("status") or "") == "ok"
    ]
    if not ok_scores:
        return 50.0
    return round((max(ok_scores) * 0.72) + (statistics.fmean(ok_scores) * 0.28), 2)


def _select_preset(preset_context: list[dict[str, object]]) -> dict[str, object]:
    ok_results = [item for item in preset_context if str(item.get("status") or "") == "ok"]
    if not ok_results:
        preset = get_backtest_preset("btc_core_trading")
        return {
            "preset_id": preset.preset_id,
            "label": preset.label,
            "stop_loss_pct": float(preset.values.get("stop_loss_pct", 3.6)),
            "take_profit_pct": float(preset.values.get("take_profit_pct", 8.0)),
            "quality_score": 50.0,
        }
    best = max(ok_results, key=lambda item: float(item.get("quality_score") or 0.0))
    preset = get_backtest_preset(str(best.get("preset_id") or "btc_core_trading"))
    return {
        "preset_id": preset.preset_id,
        "label": preset.label,
        "stop_loss_pct": float(preset.values.get("stop_loss_pct", 3.6)),
        "take_profit_pct": float(preset.values.get("take_profit_pct", 8.0)),
        "quality_score": float(best.get("quality_score") or 0.0),
        "win_rate_pct": float(best.get("win_rate_pct") or 0.0),
        "profit_factor": float(best.get("profit_factor") or 0.0),
    }


def _trade_levels(*, indicators: object, close_price: float, selected_preset: dict[str, object]) -> dict[str, object]:
    preset_stop_pct = float(selected_preset.get("stop_loss_pct") or 3.6)
    preset_take_pct = float(selected_preset.get("take_profit_pct") or 8.0)
    fallback_stop = close_price * (1 - preset_stop_pct / 100)
    support_stop = indicators.support_level * 0.992 if indicators.support_level > 0 else fallback_stop
    support_stop_pct = ((close_price - support_stop) / close_price) * 100 if close_price else preset_stop_pct
    stop_price = support_stop if 1.8 <= support_stop_pct <= 5.2 else fallback_stop
    stop_pct = ((close_price - stop_price) / close_price) * 100 if close_price else preset_stop_pct

    fallback_take = close_price * (1 + preset_take_pct / 100)
    resistance_take = indicators.resistance_level * 0.996 if indicators.resistance_level > close_price else fallback_take
    resistance_take_pct = ((resistance_take - close_price) / close_price) * 100 if close_price else preset_take_pct
    take_profit_price = resistance_take if resistance_take_pct >= max(2.5, stop_pct * 1.25) else fallback_take
    take_profit_pct = ((take_profit_price - close_price) / close_price) * 100 if close_price else preset_take_pct
    risk_reward_ratio = take_profit_pct / stop_pct if stop_pct > 0 else 0.0
    leveraged_stop_roi = -stop_pct * BTC_LEVERAGE_REFERENCE
    leveraged_take_roi = take_profit_pct * BTC_LEVERAGE_REFERENCE

    return {
        "entry_price": round(close_price, 8),
        "support_level": round(indicators.support_level, 8),
        "resistance_level": round(indicators.resistance_level, 8),
        "support_distance_pct": round(indicators.support_distance_pct, 4),
        "resistance_distance_pct": round(indicators.resistance_distance_pct, 4),
        "stop_price": round(stop_price, 8),
        "take_profit_price": round(take_profit_price, 8),
        "stop_pct": round(stop_pct, 4),
        "take_profit_pct": round(take_profit_pct, 4),
        "risk_reward_ratio": round(risk_reward_ratio, 4),
        "leverage_reference": BTC_LEVERAGE_REFERENCE,
        "leveraged_stop_roi_pct": round(leveraged_stop_roi, 4),
        "leveraged_take_profit_roi_pct": round(leveraged_take_roi, 4),
    }


def _action_decision(
    *,
    score: float,
    indicators: object,
    regime: dict[str, object],
    technical_context: dict[str, object],
    trade_levels: dict[str, object],
) -> dict[str, str]:
    entry_decision = evaluate_long_entry(
        score=score,
        indicators=indicators,
        config=EntryRuleConfig(
            min_score=68.0,
            min_volume_ratio=1.0,
            min_buy_pressure_ratio=0.50,
            min_rsi=42.0,
            max_rsi=74.0,
            anti_chase_enabled=True,
            structure_filter_enabled=True,
            max_entry_support_distance_pct=3.8,
            min_entry_support_strength=1.0,
            min_entry_risk_reward_ratio=1.15,
            min_entry_resistance_distance_pct=2.0,
            require_macd_rising=True,
            require_kdj_confirmation=False,
        ),
    )
    trend_ok = bool(regime.get("trend_bullish")) and bool(regime.get("daily_bullish"))
    overheated = (
        indicators.rsi_14 >= 74
        or indicators.price_vs_ema20_pct >= 5.5
        or float(regime.get("entry_return_24h_pct") or 0.0) >= 7.0
    )
    structure_ok = float(trade_levels.get("risk_reward_ratio") or 0.0) >= 1.2 and indicators.support_distance_pct <= 3.8
    risk_off = (
        not bool(regime.get("daily_bullish"))
        or float(regime.get("close_vs_ema200_pct") or 0.0) < -1.0
        or (indicators.ema_20 < indicators.ema_50 and indicators.macd < indicators.macd_signal)
    )

    if risk_off and score < 64:
        return {
            "action": "SELL",
            "action_label": "卖出/减仓",
            "signal": "btc_macro_risk_off_sell",
            "advice": "BTC 大级别趋势转弱，优先降低风险暴露；若已持仓，按计划减仓或等待重新站回 EMA200 后再评估。",
        }
    if score >= 72 and trend_ok and structure_ok and not overheated and (entry_decision.allowed or score >= 78):
        return {
            "action": "BUY",
            "action_label": "买入",
            "signal": "btc_regime_trend_pullback_buy",
            "advice": "BTC 多周期趋势与结构盈亏比同时满足，可采用分批试多；止损放在结构支撑下方，盈利后启用阶梯保护。",
        }
    return {
        "action": "HOLD",
        "action_label": "观察",
        "signal": "btc_wait_for_support_or_breakout",
        "advice": "暂不追价，等待更靠近 4h 支撑或放量突破阻力后再执行；已有仓位按止盈止损与趋势保护继续管理。",
    }


def _btc_reasons_and_warnings(
    *,
    action: str,
    indicators: object,
    regime: dict[str, object],
    technical_context: dict[str, object],
    preset_context: list[dict[str, object]],
    trade_levels: dict[str, object],
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    reasons.extend(str(item) for item in technical_context.get("reasons", []) if str(item).strip())
    if regime.get("label"):
        reasons.append(f"BTC 当前处于{regime['label']}状态")
    if bool(regime.get("daily_bullish")):
        reasons.append("1d 收盘价位于 EMA200 上方")
    else:
        warnings.append("1d 收盘价低于 EMA200，大级别风险偏高")
    if indicators.support_level > 0:
        reasons.append(f"4h 支撑距离 {indicators.support_distance_pct:.2f}%，结构盈亏比 {trade_levels['risk_reward_ratio']:.2f}")
    best = _select_preset(preset_context)
    if best.get("win_rate_pct") is not None:
        reasons.append(
            f"最佳 BTC 预设 {best['label']}：胜率 {float(best.get('win_rate_pct') or 0):.2f}%，PF {float(best.get('profit_factor') or 0):.2f}"
        )
    warnings.extend(str(item) for item in technical_context.get("warnings", []) if str(item).strip())
    if float(regime.get("entry_rsi_14") or 0.0) >= 72:
        warnings.append("1h RSI 偏热，避免冲高后追入")
    if float(regime.get("entry_return_24h_pct") or 0.0) >= 7.0:
        warnings.append("近 24 小时涨幅偏大，短线回落概率升高")
    if indicators.support_distance_pct > 3.8:
        warnings.append("当前价距离 4h 支撑偏远，盈亏比不够舒适")
    if action == "SELL":
        warnings.append("触发 BTC 风险收缩卖出信号，应优先保护本金")
    return _dedupe(reasons)[:8], _dedupe(warnings)[:6]


def _btc_statistics(
    *,
    primary: list[Candlestick],
    daily: list[Candlestick],
    entry: list[Candlestick],
) -> dict[str, object]:
    close = primary[-1].close_price
    start = primary[0]
    end = primary[-1]
    return {
        "sample": {
            "primary_interval": BTC_SIGNAL_INTERVAL,
            "primary_bars": len(primary),
            "daily_bars": len(daily),
            "entry_bars": len(entry),
            "start_time": to_app_time(start.open_time).isoformat(),
            "end_time": to_app_time(end.close_time).isoformat(),
        },
        "latest_price": close,
        "buy_hold_return_pct": round(_pct(close, start.close_price), 4),
        "max_drawdown_pct": round(_max_drawdown_pct([candle.close_price for candle in primary]), 4),
        "annualized_volatility_pct": round(_annualized_volatility_pct(primary), 4),
        "return_30d_pct": round(_window_return_pct(primary, bars_per_day(primary) * 30), 4),
        "return_90d_pct": round(_window_return_pct(primary, bars_per_day(primary) * 90), 4),
        "return_365d_pct": round(_window_return_pct(primary, bars_per_day(primary) * 365), 4),
    }


def _entry_config(values: dict[str, object]) -> EntryRuleConfig:
    return EntryRuleConfig(
        min_score=_float_value(values, "score_threshold", 70.0),
        min_volume_ratio=_float_value(values, "min_volume_ratio", 1.1),
        min_buy_pressure_ratio=_float_value(values, "min_buy_pressure", 0.52),
        min_rsi=_float_value(values, "min_rsi", 45.0),
        max_rsi=_float_value(values, "max_rsi", 72.0),
        require_kdj_confirmation=not bool(values.get("no_kdj_confirmation", False)),
    )


def _exit_config(values: dict[str, object]) -> ExitRuleConfig:
    return ExitRuleConfig(
        max_holding_bars=_int_value(values, "max_holding_bars", max(_holding_periods(values))),
        stop_loss_pct=_float_value(values, "stop_loss_pct", 4.0),
        take_profit_pct=_float_value(values, "take_profit_pct", 9.0),
        cooldown_bars_after_exit=_int_value(values, "cooldown_bars", 0),
    )


def _execution_config(values: dict[str, object]) -> ExecutionConfig:
    return ExecutionConfig(
        fee_bps=_float_value(values, "fee_bps", 10.0),
        slippage_bps=_float_value(values, "slippage_bps", 5.0),
        capital_fraction_pct=_float_value(values, "capital_fraction_pct", 100.0),
        slippage_model=str(values.get("slippage_model") or "fixed"),
        min_slippage_bps=_float_value(values, "min_slippage_bps", 2.0),
        max_slippage_bps=_float_value(values, "max_slippage_bps", 25.0),
    )


def _holding_periods(values: dict[str, object]) -> list[int]:
    raw = str(values.get("holding_periods") or "3,6,12")
    periods = []
    for item in raw.replace("，", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = int(item)
        except ValueError:
            continue
        if value > 0:
            periods.append(value)
    return periods or [3, 6, 12]


def _float_value(values: dict[str, object], key: str, default: float) -> float:
    try:
        return float(values.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_value(values: dict[str, object], key: str, default: int) -> int:
    try:
        return int(float(values.get(key, default)))
    except (TypeError, ValueError):
        return default


def _window_return_pct(candles: list[Candlestick], bars: int) -> float:
    if len(candles) < 2:
        return 0.0
    bars = max(1, min(bars, len(candles) - 1))
    return _pct(candles[-1].close_price, candles[-1 - bars].close_price)


def _pct(current: float, reference: float) -> float:
    return ((current - reference) / reference) * 100 if reference else 0.0


def _max_drawdown_pct(closes: list[float]) -> float:
    if not closes:
        return 0.0
    peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak > 0:
            max_drawdown = min(max_drawdown, ((close / peak) - 1) * 100)
    return max_drawdown


def _annualized_volatility_pct(candles: list[Candlestick]) -> float:
    closes = [candle.close_price for candle in candles if candle.close_price > 0]
    if len(closes) < 3:
        return 0.0
    returns = [
        math.log(current / previous)
        for previous, current in zip(closes, closes[1:])
        if previous > 0 and current > 0
    ]
    if len(returns) < 2:
        return 0.0
    periods_per_year = bars_per_day(candles) * 365
    return statistics.stdev(returns) * math.sqrt(periods_per_year) * 100


def _confidence_label(*, score: float, action: str, warnings: list[str]) -> str:
    if action == "HOLD":
        return "中"
    if score >= 82 and len(warnings) <= 2:
        return "高"
    if score >= 72:
        return "中"
    return "低"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
