from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .runtime_config import RuntimeConfig
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


@dataclass(frozen=True)
class PlatformSnapshot:
    generated_at: datetime
    components: list[PlatformComponent]
    strategies: list[StrategyDefinition]
    risk_rules: list[RiskRule]
    accounts: list[AccountSnapshot]
    recent_events: list[TradingEvent]


def build_platform_snapshot(
    *,
    config: RuntimeConfig,
    positions: list[TradingPosition],
    events: list[TradingEvent],
) -> PlatformSnapshot:
    return PlatformSnapshot(
        generated_at=datetime.now(timezone.utc),
        components=build_components(config),
        strategies=build_strategy_catalog(config),
        risk_rules=build_risk_rules(config),
        accounts=build_account_snapshots(config, positions),
        recent_events=events[-30:],
    )


def build_components(config: RuntimeConfig) -> list[PlatformComponent]:
    return [
        PlatformComponent("接入层", "Binance API", "ready", "现货行情、账户费率、实盘市价单", "/api/scan", bool(config.binance_api_key and config.binance_api_secret)),
        PlatformComponent("接入层", "OKX API", "configured" if config.okx_api_key else "ready_public", "OKX 接入参数与后续跨交易所扩展", "", bool(config.okx_api_key and config.okx_api_secret and config.okx_api_passphrase)),
        PlatformComponent("接入层", "Twitter/X", "configured" if config.x_bearer_token else "token_missing", "热门社区和指定账号情报", "/settings", bool(config.x_bearer_token)),
        PlatformComponent("接入层", "On-chain CSV", "ready", "链上异动、大额转账、交易所流入流出", "/api/terminal/snapshot", True),
        PlatformComponent("接入层", "OpenAI", "configured" if config.openai_api_key else "fallback", "综合指标分析和风险解释", "/terminal", bool(config.openai_api_key)),
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
            "spot_futures_basis",
            "现货/合约价差策略",
            "monitoring",
            f"abs(spread_bps) >= {config.intelligence_defaults.min_spread_bps:.1f}",
            "套利/对冲观察",
            ["basis_extreme_block", "manual_review"],
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
    ]


def build_account_snapshots(config: RuntimeConfig, positions: list[TradingPosition]) -> list[AccountSnapshot]:
    exposure = sum(position.quote_notional for position in positions)
    return [
        AccountSnapshot(
            exchange="BINANCE",
            mode=config.autotrade_defaults.mode,
            status="configured" if config.binance_api_key and config.binance_api_secret else "paper_ready",
            open_positions=len(positions),
            quote_exposure=exposure,
            max_quote_exposure=config.autotrade_defaults.max_total_quote_exposure,
        ),
        AccountSnapshot(
            exchange="OKX",
            mode="monitor",
            status="configured" if config.okx_api_key and config.okx_api_secret and config.okx_api_passphrase else "not_configured",
            open_positions=0,
            quote_exposure=0.0,
            max_quote_exposure=0.0,
        ),
    ]
