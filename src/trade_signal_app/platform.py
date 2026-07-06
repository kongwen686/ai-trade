from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .data_services import get_llm_provider, get_public_data_preset
from .runtime_config import RuntimeConfig
from .time_utils import now_app_time
from .trading import TradingEvent, TradingPosition


@dataclass(frozen=True)
class PlatformComponent:
    layer: str
    name: str
    status: str
    capability: str
    endpoint: str = ""
    configured: bool = False


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    status: str
    trigger: str
    execution: str
    risk_controls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    name: str
    status: str
    threshold: str
    action: str


@dataclass(frozen=True)
class AccountSnapshot:
    exchange: str
    mode: str
    status: str
    open_positions: int
    quote_exposure: float
    max_quote_exposure: float
    realized_pnl: float = 0.0
    closed_trades: int = 0
    win_rate_pct: float = 0.0


@dataclass(frozen=True)
class PlatformSnapshot:
    generated_at: datetime
    components: list[PlatformComponent]
    strategies: list[StrategyDefinition]
    risk_rules: list[RiskRule]
    accounts: list[AccountSnapshot]
    recent_events: list[TradingEvent]


def okx_credential_state(config: RuntimeConfig) -> dict[str, object]:
    present = {
        "API Key": bool(config.okx_api_key),
        "API Secret": bool(config.okx_api_secret),
        "Passphrase": bool(config.okx_api_passphrase),
    }
    missing = [name for name, exists in present.items() if not exists]
    configured = not missing
    partial = bool([name for name, exists in present.items() if exists]) and not configured
    if configured:
        return {
            "configured": True,
            "partial": False,
            "status": "configured",
            "label": "凭据已完整保存",
            "message": "OKX API Key / Secret / Passphrase 已保存，可用于授权检查和自动交易执行。",
            "missing": [],
        }
    if partial:
        return {
            "configured": False,
            "partial": True,
            "status": "partial_configured",
            "label": "部分配置",
            "message": "OKX 凭据已部分保存，缺少：" + "、".join(missing),
            "missing": missing,
        }
    return {
        "configured": False,
        "partial": False,
        "status": "not_configured",
        "label": "未配置",
        "message": "OKX API Key / Secret / Passphrase 未配置。",
        "missing": missing,
    }


def _event_created_at_utc(event: TradingEvent) -> datetime:
    created_at = event.created_at
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def build_platform_snapshot(
    *,
    config: RuntimeConfig,
    positions: list[TradingPosition],
    events: list[TradingEvent],
) -> PlatformSnapshot:
    return PlatformSnapshot(
        generated_at=now_app_time(),
        components=build_components(config),
        strategies=build_strategy_catalog(config),
        risk_rules=build_risk_rules(config),
        accounts=build_account_snapshots_from_events(config, positions, events),
        recent_events=sorted(events, key=_event_created_at_utc, reverse=True)[:30],
    )


def build_components(config: RuntimeConfig) -> list[PlatformComponent]:
    binance_auth_configured = bool(config.binance_api_key and config.binance_api_secret)
    okx_state = okx_credential_state(config)
    market_preset = get_public_data_preset(config.market_data_preset)
    onchain_preset = get_public_data_preset(config.onchain_data_preset)
    llm_provider = get_llm_provider(config.intelligence_defaults.llm_provider)
    llm_configured = bool(config.intelligence_defaults.llm_api_key or config.intelligence_defaults.openai_api_key)
    x_configured = (
        bool(config.x_bearer_token)
        if config.x_provider == "official_api"
        else bool(config.x_nitter_base_url)
        if config.x_provider == "nitter_rss"
        else bool(config.x_session_command)
    )
    return [
        PlatformComponent(
            "接入层",
            "Binance API",
            "configured" if binance_auth_configured else "ready_public",
            "现货公开行情、账户授权状态和受保护市价单" if binance_auth_configured else "现货公开行情；账户级接口需要配置 API key/secret",
            "/api/platform/exchange-auth" if binance_auth_configured else "/api/scan",
            binance_auth_configured,
        ),
        PlatformComponent(
            "接入层",
            "OKX API",
            str(okx_state["status"]),
            str(okx_state["message"]),
            "/settings",
            bool(okx_state["configured"] or okx_state["partial"]),
        ),
        PlatformComponent("接入层", market_preset.name, "ready_public", market_preset.description, market_preset.base_url, True),
        PlatformComponent("接入层", "Twitter/X", "configured" if x_configured else "source_missing", f"社区热度和指定账号情报；provider={config.x_provider}", "/settings", x_configured),
        PlatformComponent("接入层", onchain_preset.name, "ready_public" if not onchain_preset.auth_required else "key_optional", onchain_preset.description, onchain_preset.base_url, True),
        PlatformComponent("接入层", llm_provider.name, "configured" if llm_configured else "fallback", "综合指标分析和风险解释；未配置 key 时使用本地规则", "/settings", llm_configured),
        PlatformComponent("策略层", "Signal Scoring", "ready", "趋势、动量、量能、社区评分", "/api/scan", True),
        PlatformComponent("策略层", "Basis Monitor", "ready", "现货/合约价差和跨市场 basis", "/api/terminal/snapshot", True),
        PlatformComponent("策略层", "Strategy Hits", "ready", "自动交易候选和策略命中", "/api/terminal/snapshot", True),
        PlatformComponent("执行层", "Paper Trading", "ready", "本地模拟交易和持仓状态", "/api/trading/run", True),
        PlatformComponent("执行层", "Live Guard", "guarded", "实盘环境变量、order/test 和密钥保护", "/trading", config.autotrade_defaults.mode == "live"),
        PlatformComponent("执行层", "Order Manager", "ready", "市价买入、卖出、客户端订单号", "/api/trading/run", True),
        PlatformComponent("执行层", "Position Manager", "ready", "持仓、止损、止盈和冷却", "/api/trading/status", True),
        PlatformComponent("数据层", "Runtime Config", "ready", "本地配置、模板导入导出、可选加密", "/settings", True),
        PlatformComponent("数据层", "Trading State", "ready", "持仓和事件历史持久化", "/api/trading/status", True),
        PlatformComponent("风控层", "Execution Risk Gate", "ready", "链上、价差、策略命中执行前阻断", "/api/terminal/snapshot", True),
    ]


def build_strategy_catalog(config: RuntimeConfig) -> list[StrategyDefinition]:
    auto_status = "enabled" if config.autotrade_defaults.enabled else "watch_only"
    return [
        StrategyDefinition(
            "auto_score_breakout",
            "综合评分突破",
            auto_status,
            f"score >= {config.autotrade_defaults.score_threshold:.1f}",
            "paper/live 市价买入",
            ["max_open_positions", "max_total_quote_exposure", "risk_gate"],
        ),
        StrategyDefinition(
            "volume_pressure",
            "量价压力策略",
            "watch_only",
            f"volume_ratio >= {config.autotrade_defaults.min_volume_ratio:.2f}, buy_pressure >= {config.autotrade_defaults.min_buy_pressure:.2f}",
            "候选优先级提升",
            ["risk_gate", "cooldown"],
        ),
        StrategyDefinition(
            "trend_following",
            "趋势跟随策略",
            "research",
            "EMA 20/50 trend, score filter, trailing review",
            "回测研究 / paper 趋势跟随观察",
            ["trend_filter", "cooldown", "position_sizing"],
        ),
        StrategyDefinition(
            "range_breakout",
            "区间突破策略",
            "research",
            "resistance breakout + volume expansion",
            "回测研究 / paper 突破观察",
            ["false_breakout_exit", "cooldown", "risk_gate"],
        ),
        StrategyDefinition(
            "momentum_rotation",
            "动量轮动策略",
            "research",
            "relative strength rank + score filter",
            "回测研究 / 组合轮动观察",
            ["diversification", "turnover_cost", "max_positions"],
        ),
        StrategyDefinition(
            "spot_futures_basis",
            "现货/合约价差策略",
            "monitoring",
            f"abs(spread_bps) >= {config.intelligence_defaults.min_spread_bps:.1f}",
            "套利/对冲观察",
            ["basis_extreme_block", "manual_review"],
        ),
        StrategyDefinition(
            "low_float_momentum_long",
            "小市值早期动量做多",
            "monitoring",
            "volume_ratio >= 2.5, 8% <= 24h_change <= 120%, funding <= +3.5bps/8h",
            "paper 观察 / 低费率追踪做多",
            ["funding_filter", "volume_spike", "take_profit_ladder"],
        ),
        StrategyDefinition(
            "blowoff_distribution_short",
            "小市值末端分布做空",
            "monitoring",
            "positive funding + extended RSI/EMA distance + volume spike",
            "合约做空观察 / 禁止现货追高",
            ["funding_overheat", "false_breakout_exit", "manual_review"],
        ),
        StrategyDefinition(
            "capitulation_rebound_long",
            "小市值暴跌反弹做多",
            "monitoring",
            "negative funding + 24h drawdown + RSI/EMA capitulation",
            "短线反弹观察",
            ["funding_short_crowding", "tight_stop", "mean_reversion_target"],
        ),
        StrategyDefinition(
            "crypto_rebalance_premium",
            "加密资产等权再平衡",
            "research",
            "equal-weight basket, periodic rebalance",
            "回测研究 / 组合再平衡观察",
            ["diversification", "turnover_cost", "spot_only"],
        ),
        StrategyDefinition(
            "btc_overnight_seasonality",
            "BTC 隔夜季节性",
            "research",
            "UTC 22:00 entry, hold 2 hours",
            "回测研究 / 时间窗口观察",
            ["time_window", "btc_only", "execution_cost"],
        ),
        StrategyDefinition(
            "onchain_whale_guard",
            "链上大额异动风控",
            "guarding",
            f"amount_usd >= {config.intelligence_defaults.whale_transfer_threshold_usd:.0f}",
            "阻断或降级自动开仓",
            ["exchange_inflow_block", "risk_score"],
        ),
    ]


def build_risk_rules(config: RuntimeConfig) -> list[RiskRule]:
    return [
        RiskRule("max_positions", "最大持仓数", "active", str(config.autotrade_defaults.max_open_positions), "拒绝新开仓"),
        RiskRule("max_exposure", "最大总敞口", "active", f"{config.autotrade_defaults.max_total_quote_exposure:.2f}", "拒绝超额订单"),
        RiskRule("stop_loss", "单仓止损", "active", f"{config.autotrade_defaults.stop_loss_pct:.1f}%", "触发平仓"),
        RiskRule("take_profit", "单仓止盈", "active", f"{config.autotrade_defaults.take_profit_pct:.1f}%", "触发平仓"),
        RiskRule("cooldown", "同标的冷却", "active", f"{config.autotrade_defaults.cooldown_minutes} minutes", "跳过重复开仓"),
        RiskRule("live_confirm", "实盘确认", "guarded", "AI_TRADE_LIVE_CONFIRM", "阻断真实订单"),
        RiskRule("order_test", "Binance order/test", "active" if config.autotrade_defaults.order_test_only else "disabled", str(config.autotrade_defaults.order_test_only), "仅校验不成交"),
        RiskRule("intel_gate", "智能执行风控", "active", "onchain + spread + strategy", "阻断风险标的"),
        RiskRule("funding_rate_guard", "合约资金费率风控", "active", "funding >= +10bps/8h", "阻断拥挤追多"),
    ]


def build_account_snapshots(config: RuntimeConfig, positions: list[TradingPosition]) -> list[AccountSnapshot]:
    return build_account_snapshots_from_events(config, positions, [])


def build_account_snapshots_from_events(
    config: RuntimeConfig,
    positions: list[TradingPosition],
    events: list[TradingEvent],
) -> list[AccountSnapshot]:
    okx_state = okx_credential_state(config)
    binance_positions = [position for position in positions if position.exchange.upper() == "BINANCE"]
    okx_positions = [position for position in positions if position.exchange.upper() == "OKX"]
    binance_exposure = sum(position.quote_notional for position in binance_positions)
    okx_exposure = sum(position.quote_notional for position in okx_positions)
    closed_events = [
        event
        for event in events
        if event.action == "SELL" and event.status in {"filled", "paper_filled"} and event.realized_pnl is not None
    ]
    realized_by_exchange = {
        exchange: sum(float(event.realized_pnl or 0.0) for event in closed_events if event.exchange.upper() == exchange)
        for exchange in {"BINANCE", "OKX"}
    }
    closed_by_exchange = {
        exchange: [event for event in closed_events if event.exchange.upper() == exchange]
        for exchange in {"BINANCE", "OKX"}
    }
    wins_by_exchange = {
        exchange: sum(1 for event in exchange_events if float(event.realized_pnl or 0.0) > 0)
        for exchange, exchange_events in closed_by_exchange.items()
    }
    win_rate_by_exchange = {
        exchange: (wins_by_exchange[exchange] / len(exchange_events)) * 100 if exchange_events else 0.0
        for exchange, exchange_events in closed_by_exchange.items()
    }
    return [
        AccountSnapshot(
            exchange="BINANCE",
            mode=config.autotrade_defaults.mode,
            status="configured" if config.binance_api_key and config.binance_api_secret else "paper_ready",
            open_positions=len(binance_positions),
            quote_exposure=binance_exposure,
            max_quote_exposure=config.autotrade_defaults.max_total_quote_exposure,
            realized_pnl=round(realized_by_exchange["BINANCE"], 8),
            closed_trades=len(closed_by_exchange["BINANCE"]),
            win_rate_pct=round(win_rate_by_exchange["BINANCE"], 2),
        ),
        AccountSnapshot(
            exchange="OKX",
            mode=config.autotrade_defaults.mode if config.autotrade_defaults.execution_exchange.lower() == "okx" else "monitor",
            status=str(okx_state["status"]),
            open_positions=len(okx_positions),
            quote_exposure=okx_exposure,
            max_quote_exposure=config.autotrade_defaults.max_total_quote_exposure if config.autotrade_defaults.execution_exchange.lower() == "okx" else 0.0,
            realized_pnl=round(realized_by_exchange["OKX"], 8),
            closed_trades=len(closed_by_exchange["OKX"]),
            win_rate_pct=round(win_rate_by_exchange["OKX"], 2),
        ),
    ]
