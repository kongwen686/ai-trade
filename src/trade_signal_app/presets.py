from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestPreset:
    preset_id: str
    label: str
    description: str
    values: dict[str, object]


BACKTEST_PRESETS: tuple[BacktestPreset, ...] = (
    BacktestPreset(
        preset_id="custom",
        label="Custom",
        description="保留当前手动参数，适合按任务临时微调。",
        values={},
    ),
    BacktestPreset(
        preset_id="balanced_swing",
        label="Balanced Swing",
        description="偏均衡的波段模板，兼顾信号质量、止盈空间和回撤控制。",
        values={
            "lookback_bars": 240,
            "score_threshold": 70.0,
            "holding_periods": "3,6,12",
            "portfolio_top_n": 2,
            "cooldown_bars": 2,
            "stop_loss_pct": 4.0,
            "take_profit_pct": 9.0,
            "max_holding_bars": 12,
            "slippage_model": "dynamic",
            "min_slippage_bps": 2.0,
            "max_slippage_bps": 25.0,
            "min_volume_ratio": 1.1,
            "min_buy_pressure": 0.52,
            "min_rsi": 45.0,
            "max_rsi": 72.0,
            "no_kdj_confirmation": False,
        },
    ),
    BacktestPreset(
        preset_id="breakout_aggressive",
        label="Breakout Aggressive",
        description="更强调量价突破和动量延续，容忍更高波动，适合追强。",
        values={
            "lookback_bars": 180,
            "score_threshold": 76.0,
            "holding_periods": "2,4,8",
            "portfolio_top_n": 1,
            "cooldown_bars": 1,
            "stop_loss_pct": 5.2,
            "take_profit_pct": 12.0,
            "max_holding_bars": 10,
            "slippage_model": "dynamic",
            "min_slippage_bps": 3.0,
            "max_slippage_bps": 30.0,
            "min_volume_ratio": 1.28,
            "min_buy_pressure": 0.58,
            "min_rsi": 50.0,
            "max_rsi": 78.0,
            "no_kdj_confirmation": True,
        },
    ),
    BacktestPreset(
        preset_id="portfolio_rotation",
        label="Portfolio Rotation",
        description="偏组合轮动，限制单次暴露和并发，优先看横截面 top N。",
        values={
            "lookback_bars": 300,
            "score_threshold": 68.0,
            "holding_periods": "3,6,9",
            "portfolio_top_n": 3,
            "cooldown_bars": 3,
            "stop_loss_pct": 3.8,
            "take_profit_pct": 7.5,
            "max_holding_bars": 9,
            "capital_fraction_pct": 60.0,
            "max_portfolio_exposure_pct": 75.0,
            "max_concurrent_positions": 3,
            "slippage_model": "dynamic",
            "min_slippage_bps": 1.5,
            "max_slippage_bps": 18.0,
            "min_volume_ratio": 1.05,
            "min_buy_pressure": 0.51,
            "min_rsi": 43.0,
            "max_rsi": 70.0,
            "no_kdj_confirmation": False,
        },
    ),
    BacktestPreset(
        preset_id="btc_cycle_trend",
        label="BTC Cycle Trend",
        description="基于 BTC 大级别趋势跟随，强调顺势、分层试单和中等持仓周期。",
        values={
            "lookback_bars": 240,
            "score_threshold": 70.0,
            "holding_periods": "3,6,12",
            "portfolio_top_n": 1,
            "cooldown_bars": 2,
            "stop_loss_pct": 4.2,
            "take_profit_pct": 9.5,
            "max_holding_bars": 12,
            "capital_fraction_pct": 85.0,
            "max_portfolio_exposure_pct": 100.0,
            "max_concurrent_positions": 1,
            "slippage_model": "dynamic",
            "min_slippage_bps": 2.0,
            "max_slippage_bps": 22.0,
            "min_volume_ratio": 1.1,
            "min_buy_pressure": 0.52,
            "min_rsi": 46.0,
            "max_rsi": 74.0,
            "no_kdj_confirmation": False,
        },
    ),
    BacktestPreset(
        preset_id="btc_core_trading",
        label="BTC Core Trading",
        description="模拟核心仓加交易仓的双层管理，允许围绕主方向做更积极的仓位调整。",
        values={
            "lookback_bars": 220,
            "score_threshold": 72.0,
            "holding_periods": "2,4,8",
            "portfolio_top_n": 1,
            "cooldown_bars": 1,
            "stop_loss_pct": 3.6,
            "take_profit_pct": 8.0,
            "max_holding_bars": 8,
            "capital_fraction_pct": 70.0,
            "max_portfolio_exposure_pct": 85.0,
            "max_concurrent_positions": 1,
            "slippage_model": "dynamic",
            "min_slippage_bps": 2.0,
            "max_slippage_bps": 20.0,
            "min_volume_ratio": 1.08,
            "min_buy_pressure": 0.56,
            "min_rsi": 46.0,
            "max_rsi": 74.0,
            "no_kdj_confirmation": True,
        },
    ),
    BacktestPreset(
        preset_id="btc_compounding_risk_off",
        label="BTC Compounding Risk-Off",
        description="偏复利和回撤控制，主动压低暴露与并发，更重视账户生存而不是单笔弹性。",
        values={
            "lookback_bars": 300,
            "score_threshold": 68.0,
            "holding_periods": "3,6,9",
            "portfolio_top_n": 1,
            "cooldown_bars": 3,
            "stop_loss_pct": 3.4,
            "take_profit_pct": 7.0,
            "max_holding_bars": 9,
            "capital_fraction_pct": 55.0,
            "max_portfolio_exposure_pct": 60.0,
            "max_concurrent_positions": 1,
            "slippage_model": "dynamic",
            "min_slippage_bps": 1.5,
            "max_slippage_bps": 16.0,
            "min_volume_ratio": 1.05,
            "min_buy_pressure": 0.51,
            "min_rsi": 44.0,
            "max_rsi": 70.0,
            "no_kdj_confirmation": False,
        },
    ),
)


def get_backtest_preset(preset_id: str) -> BacktestPreset:
    normalized = (preset_id or "custom").strip().lower()
    for preset in BACKTEST_PRESETS:
        if preset.preset_id == normalized:
            return preset
    return BACKTEST_PRESETS[0]


def apply_backtest_preset(params: dict[str, object], preset_id: str) -> dict[str, object]:
    preset = get_backtest_preset(preset_id)
    return {**params, **preset.values, "preset": preset.preset_id}


def list_backtest_presets() -> list[dict[str, object]]:
    return [
        {
            "preset_id": preset.preset_id,
            "label": preset.label,
            "description": preset.description,
            "values": dict(preset.values),
        }
        for preset in BACKTEST_PRESETS
    ]
