from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import re
from typing import Any
from urllib.request import Request, urlopen

from .intelligence import OpenAIInsightClient
from .presets import apply_backtest_preset, backtest_preset_ids, get_strategy_template
from .runtime_config import RuntimeConfig


SUPPORTED_QUOTES = ("USDT", "USDC", "BTC", "ETH")
SUPPORTED_INTERVALS = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d")
SUPPORTED_STYLES = ("trend_following", "breakout", "momentum", "mean_reversion", "rebalance", "seasonality", "basis", "balanced")
KNOWN_BASE_ASSETS = (
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "ADA",
    "DOGE",
    "AVAX",
    "LINK",
    "DOT",
    "MATIC",
    "POL",
    "LTC",
    "BCH",
    "UNI",
    "AAVE",
    "TRX",
    "TON",
    "ARB",
    "OP",
    "NEAR",
    "ATOM",
    "FIL",
    "APT",
    "SUI",
    "PEPE",
    "WIF",
    "ENA",
)
ASSET_ALIASES = {
    "比特币": "BTC",
    "大饼": "BTC",
    "以太坊": "ETH",
    "姨太": "ETH",
    "索拉纳": "SOL",
}
BACKTEST_PRESETS = backtest_preset_ids()


@dataclass(frozen=True)
class CompiledStrategy:
    name: str
    description: str
    symbols: list[str]
    quote_asset: str
    interval: str
    style: str
    entry_rules: list[str]
    exit_rules: list[str]
    risk_controls: list[str]
    backtest_defaults: dict[str, object]
    autotrade_defaults: dict[str, object]
    source: str
    model: str
    warnings: list[str]


def compile_strategy(description: str, runtime_config: RuntimeConfig) -> CompiledStrategy:
    """Compile a natural-language idea into the app's safe strategy parameter set."""
    text = description.strip()
    if not text:
        raise ValueError("请先描述交易策略。")

    local_compiler = LocalStrategyCompiler(runtime_config)
    local_result = local_compiler.compile(text)
    llm_config = runtime_config.intelligence_defaults
    api_key = llm_config.openai_api_key or runtime_config.openai_api_key
    model = llm_config.openai_model or runtime_config.openai_model
    if not llm_config.llm_enabled or not api_key:
        return local_result

    try:
        return OpenAIStrategyCompiler(runtime_config=runtime_config, api_key=api_key, model=model).compile(
            text,
            base=local_result,
        )
    except Exception as exc:  # noqa: BLE001
        warnings = [
            *local_result.warnings,
            f"OpenAI 策略编译失败，已回退本地规则：{exc}",
        ]
        return _replace_compiled(local_result, warnings=warnings)


def compile_strategy_template(template_id: str, runtime_config: RuntimeConfig) -> CompiledStrategy:
    """Compile a registered template without allowing it to activate any execution path."""
    template = get_strategy_template(template_id)
    base = LocalStrategyCompiler(runtime_config).compile(template.compiler_prompt)
    backtest_defaults = apply_backtest_preset(base.backtest_defaults, template.preset_id)
    autotrade_defaults = _merge_autotrade_defaults(base.autotrade_defaults, dict(template.autotrade_values))
    warning = "模板仅生成回测和 paper 参数，不会开启模拟轮询、实盘开关或真实订单。"
    return replace(
        base,
        name=template.label,
        description=template.description,
        symbols=list(template.symbols) or base.symbols,
        style=template.style,
        backtest_defaults=backtest_defaults,
        autotrade_defaults=autotrade_defaults,
        source="template_registry",
        model="deterministic_rules",
        warnings=_dedupe([*base.warnings, warning]),
    )


class LocalStrategyCompiler:
    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self.runtime_config = runtime_config

    def compile(self, description: str) -> CompiledStrategy:
        normalized = _normalize_text(description)
        quote_asset = _extract_quote_asset(normalized, self.runtime_config.scan_defaults.quote_asset)
        symbols = _extract_symbols(normalized, quote_asset)
        interval = _extract_interval(normalized, self.runtime_config.scan_defaults.interval)
        style = _detect_style(normalized)
        stop_loss_pct = _clamp_float(
            _extract_percent(normalized, ("止损", "STOP LOSS", "STOP-LOSS")) or self.runtime_config.backtest_defaults.stop_loss_pct,
            _float_bounds("stop_loss_pct"),
        )
        take_profit_pct = _clamp_float(
            _extract_percent(normalized, ("止盈", "TAKE PROFIT", "TAKE-PROFIT", "目标收益")) or self.runtime_config.backtest_defaults.take_profit_pct,
            _float_bounds("take_profit_pct"),
        )
        holding_bars = _clamp_int(
            _extract_holding_bars(normalized, interval) or self.runtime_config.backtest_defaults.max_holding_bars,
            _int_bounds("max_holding_bars"),
        )
        warnings = _base_warnings(normalized, symbols)
        backtest_defaults = self._base_backtest_defaults()
        autotrade_defaults = self._base_autotrade_defaults()

        if style == "rebalance":
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "crypto_rebalance_premium",
                    "portfolio_top_n": 0,
                    "score_threshold": 68.0,
                    "holding_periods": "3,6,12",
                    "stop_loss_pct": max(float(stop_loss_pct), 6.0),
                    "take_profit_pct": max(float(take_profit_pct), 12.0),
                    "max_holding_bars": max(int(holding_bars), 12),
                    "min_volume_ratio": 1.0,
                    "min_buy_pressure": 0.5,
                    "min_rsi": 35.0,
                    "max_rsi": 85.0,
                    "no_kdj_confirmation": True,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "max_open_positions": min(max(len(symbols), 2), 10),
                    "score_threshold": 68.0,
                    "stop_loss_pct": max(float(stop_loss_pct), 6.0),
                    "take_profit_pct": max(float(take_profit_pct), 12.0),
                    "min_volume_ratio": 1.0,
                    "min_buy_pressure": 0.5,
                },
            )
            entry_rules = ["按标的池构建等权组合", "按回测周期定期再平衡", "比较等权再平衡与自然漂移组合"]
            exit_rules = ["组合权重偏离目标时调仓", "回测中计入手续费和滑点"]
            risk_controls = ["单标的等权暴露", "组合总暴露上限", "paper 模式验证后再考虑实盘"]
            warnings.append("再平衡策略当前输出为回测/组合参数，自动交易执行仍需人工确认调仓器。")
        elif style == "seasonality":
            if not any(symbol.startswith("BTC") for symbol in symbols):
                symbols = [f"BTC{quote_asset}", *[symbol for symbol in symbols if not symbol.startswith("BTC")]]
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "btc_overnight_seasonality",
                    "score_threshold": 0.0,
                    "holding_periods": str(max(1, int(holding_bars))),
                    "stop_loss_pct": max(float(stop_loss_pct), 20.0),
                    "take_profit_pct": max(float(take_profit_pct), 20.0),
                    "max_holding_bars": max(1, int(holding_bars)),
                    "min_volume_ratio": 1.0,
                    "min_buy_pressure": 0.0,
                    "min_rsi": 0.0,
                    "max_rsi": 100.0,
                    "no_kdj_confirmation": True,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "max_open_positions": 1,
                    "score_threshold": 0.0,
                    "stop_loss_pct": max(float(stop_loss_pct), 20.0),
                    "take_profit_pct": max(float(take_profit_pct), 20.0),
                    "min_volume_ratio": 1.0,
                    "min_buy_pressure": 0.0,
                },
            )
            entry_rules = ["BTC UTC 22:00 时间窗口做多", "不依赖评分阈值，优先做季节性回测"]
            exit_rules = [f"持有 {max(1, int(holding_bars))} 根 K 线后退出", "回测中计入手续费和滑点"]
            risk_controls = ["单标的单仓", "时间窗口策略必须先用历史数据验证", "paper 模式验证后再考虑实盘"]
            warnings.append("时间窗口策略依赖交易所 K 线时区，回测前请确认归档数据时间戳为 UTC。")
        elif style == "trend_following":
            preset = "btc_cycle_trend" if len(symbols) == 1 and symbols[0].startswith("BTC") else "balanced_swing"
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": preset,
                    "score_threshold": 70.0,
                    "holding_periods": "6,12,24",
                    "portfolio_top_n": min(max(len(symbols), 1), 3),
                    "cooldown_bars": 3,
                    "stop_loss_pct": max(float(stop_loss_pct), 4.0),
                    "take_profit_pct": max(float(take_profit_pct), 10.0),
                    "max_holding_bars": max(18, int(holding_bars)),
                    "min_volume_ratio": 1.08,
                    "min_buy_pressure": 0.52,
                    "min_rsi": 46.0,
                    "max_rsi": 80.0,
                    "no_kdj_confirmation": False,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "score_threshold": 72.0,
                    "max_open_positions": min(max(len(symbols), 1), 3),
                    "stop_loss_pct": max(float(stop_loss_pct), 4.0),
                    "take_profit_pct": max(float(take_profit_pct), 10.0),
                    "min_volume_ratio": 1.08,
                    "min_buy_pressure": 0.52,
                },
            )
            entry_rules = ["EMA 20/50 多头结构成立", "综合评分确认趋势质量", "量能不低于近期均值 1.08 倍"]
            exit_rules = [f"止损 {max(float(stop_loss_pct), 4.0):.1f}%", f"止盈 {max(float(take_profit_pct), 10.0):.1f}%", f"最多持有 {max(18, int(holding_bars))} 根 K 线"]
            risk_controls = ["趋势转弱后退出", "冷却期过滤反复假信号", "paper 模式验证后再考虑实盘"]
        elif style == "mean_reversion":
            rsi_ceiling = _extract_rsi_threshold(normalized, default=38.0)
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "custom",
                    "score_threshold": 62.0,
                    "holding_periods": "3,6,9",
                    "portfolio_top_n": min(max(len(symbols), 1), 3),
                    "cooldown_bars": 2,
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                    "max_holding_bars": max(3, int(holding_bars)),
                    "min_volume_ratio": 1.03,
                    "min_buy_pressure": 0.50,
                    "min_rsi": 0.0,
                    "max_rsi": rsi_ceiling,
                    "no_kdj_confirmation": False,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "score_threshold": 68.0,
                    "max_open_positions": min(max(len(symbols), 1), 3),
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                    "min_volume_ratio": 1.03,
                    "min_buy_pressure": 0.50,
                },
            )
            entry_rules = [f"RSI 低于 {rsi_ceiling:.1f} 后等待反弹确认", "量能不低于近期均值", "买压恢复到 0.50 以上"]
            exit_rules = [f"止损 {float(stop_loss_pct):.1f}%", f"止盈 {float(take_profit_pct):.1f}%", f"最多持有 {max(3, int(holding_bars))} 根 K 线"]
            risk_controls = ["冷却期避免连续接飞刀", "组合持仓数量限制", "paper 模式验证后再考虑实盘"]
        elif style == "breakout":
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "breakout_aggressive",
                    "score_threshold": 78.0,
                    "holding_periods": "2,4,8",
                    "portfolio_top_n": min(max(len(symbols), 1), 2),
                    "cooldown_bars": 2,
                    "stop_loss_pct": max(float(stop_loss_pct), 4.5),
                    "take_profit_pct": max(float(take_profit_pct), 12.0),
                    "max_holding_bars": max(8, int(holding_bars)),
                    "min_volume_ratio": 1.35,
                    "min_buy_pressure": 0.58,
                    "min_rsi": 52.0,
                    "max_rsi": 82.0,
                    "no_kdj_confirmation": True,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "score_threshold": 78.0,
                    "max_open_positions": min(max(len(symbols), 1), 2),
                    "stop_loss_pct": max(float(stop_loss_pct), 4.5),
                    "take_profit_pct": max(float(take_profit_pct), 12.0),
                    "min_volume_ratio": 1.35,
                    "min_buy_pressure": 0.58,
                },
            )
            entry_rules = ["价格突破关键阻力或整理区间", "成交量放大到均值 1.35 倍以上", "买压和评分同步确认"]
            exit_rules = [f"止损 {max(float(stop_loss_pct), 4.5):.1f}%", f"止盈 {max(float(take_profit_pct), 12.0):.1f}%", f"最多持有 {max(8, int(holding_bars))} 根 K 线"]
            risk_controls = ["假突破快速退出", "冷却期避免连续追高", "paper 模式验证后再考虑实盘"]
        elif style == "momentum":
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "portfolio_rotation",
                    "score_threshold": 74.0,
                    "holding_periods": "3,6,12",
                    "portfolio_top_n": min(max(len(symbols), 1), 3),
                    "cooldown_bars": 2,
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": max(float(take_profit_pct), 9.0),
                    "max_holding_bars": max(12, int(holding_bars)),
                    "min_volume_ratio": 1.15,
                    "min_buy_pressure": 0.54,
                    "min_rsi": 50.0,
                    "max_rsi": 82.0,
                    "no_kdj_confirmation": True,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "score_threshold": 74.0,
                    "max_open_positions": min(max(len(symbols), 1), 3),
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": max(float(take_profit_pct), 9.0),
                    "min_volume_ratio": 1.15,
                    "min_buy_pressure": 0.54,
                },
            )
            entry_rules = ["横截面评分或相对强弱排名靠前", "动量延续且成交活跃", "买压不低于 0.54"]
            exit_rules = [f"止损 {float(stop_loss_pct):.1f}%", f"止盈 {max(float(take_profit_pct), 9.0):.1f}%", f"最多持有 {max(12, int(holding_bars))} 根 K 线"]
            risk_controls = ["轮动换仓控制拥挤风险", "组合持仓数量限制", "paper 模式验证后再考虑实盘"]
        elif style == "basis":
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "portfolio_rotation",
                    "score_threshold": 68.0,
                    "portfolio_top_n": min(max(len(symbols), 1), 3),
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                    "min_volume_ratio": 1.05,
                    "min_buy_pressure": 0.51,
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "score_threshold": 72.0,
                    "max_open_positions": min(max(len(symbols), 1), 3),
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                    "min_volume_ratio": 1.05,
                    "min_buy_pressure": 0.51,
                },
            )
            entry_rules = ["现货/合约价差进入观察阈值", "信号评分过滤趋势方向", "异常 basis 进入风控复核"]
            exit_rules = [f"止损 {float(stop_loss_pct):.1f}%", f"止盈 {float(take_profit_pct):.1f}%", "价差回归或风险规则阻断后退出"]
            risk_controls = ["价差异常不直接实盘下单", "合约/现货腿需人工确认", "paper 模式验证后再考虑实盘"]
            warnings.append("当前自动交易引擎只执行现货多头，basis/套利策略会先编译为监控和回测参数。")
        else:
            backtest_defaults = _merge_backtest_defaults(
                backtest_defaults,
                {
                    "preset": "balanced_swing",
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                    "max_holding_bars": max(3, int(holding_bars)),
                    "portfolio_top_n": min(max(len(symbols), 1), 3),
                },
            )
            autotrade_defaults = _merge_autotrade_defaults(
                autotrade_defaults,
                {
                    "score_threshold": self.runtime_config.autotrade_defaults.score_threshold,
                    "max_open_positions": min(max(len(symbols), 1), 3),
                    "stop_loss_pct": float(stop_loss_pct),
                    "take_profit_pct": float(take_profit_pct),
                },
            )
            entry_rules = ["沿用综合评分信号", "量能和买压达到系统默认阈值", "趋势/震荡过滤由当前策略参数控制"]
            exit_rules = [f"止损 {float(stop_loss_pct):.1f}%", f"止盈 {float(take_profit_pct):.1f}%", f"最多持有 {max(3, int(holding_bars))} 根 K 线"]
            risk_controls = ["执行前风控", "组合持仓数量限制", "paper 模式验证后再考虑实盘"]

        if symbols == [f"BTC{quote_asset}"] and "BTC" not in normalized and "比特币" not in description:
            warnings.append("未识别到明确标的，已默认使用 BTC。")
        if re.search(r"做空|空头|SHORT|SELL SHORT", normalized):
            warnings.append("当前执行层只支持现货多头，做空描述已降级为观察/回测参数。")

        return CompiledStrategy(
            name=_strategy_name(style, symbols, interval),
            description=description,
            symbols=symbols,
            quote_asset=quote_asset,
            interval=interval,
            style=style,
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            risk_controls=risk_controls,
            backtest_defaults=backtest_defaults,
            autotrade_defaults=autotrade_defaults,
            source="local_rules",
            model="rules",
            warnings=_dedupe(warnings),
        )

    def _base_backtest_defaults(self) -> dict[str, object]:
        defaults = asdict(self.runtime_config.backtest_defaults)
        return apply_backtest_preset(defaults, str(defaults.get("preset", "custom")))

    def _base_autotrade_defaults(self) -> dict[str, object]:
        defaults = asdict(self.runtime_config.autotrade_defaults)
        defaults["enabled"] = False
        defaults["mode"] = "paper"
        defaults["paper_enabled"] = False
        defaults["live_enabled"] = False
        defaults["order_test_only"] = True
        return defaults


class OpenAIStrategyCompiler:
    def __init__(self, *, runtime_config: RuntimeConfig, api_key: str, model: str, timeout: int = 25) -> None:
        self.runtime_config = runtime_config
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def compile(self, description: str, *, base: CompiledStrategy) -> CompiledStrategy:
        body = json.dumps(
            {
                "model": self.model,
                "input": self._prompt(description, base),
                "max_output_tokens": 900,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            "https://api.openai.com/v1/responses",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        text = OpenAIInsightClient._extract_output_text(payload)
        if not text:
            raise ValueError("模型没有返回可解析文本。")
        parsed = _extract_json_object(text)
        return _compiled_from_payload(parsed, base=base, model=self.model)

    @staticmethod
    def _prompt(description: str, base: CompiledStrategy) -> str:
        schema = {
            "name": "string",
            "description": "string",
            "symbols": ["BTCUSDT"],
            "quote_asset": "USDT",
            "interval": "15m",
            "style": "trend_following|breakout|momentum|mean_reversion|rebalance|seasonality|basis|balanced",
            "entry_rules": ["string"],
            "exit_rules": ["string"],
            "risk_controls": ["string"],
            "backtest_defaults": {"preset": "custom", "score_threshold": 70.0},
            "autotrade_defaults": {"enabled": False, "mode": "paper", "score_threshold": 75.0},
            "warnings": ["string"],
        }
        return (
            "你是加密货币量化策略编译器。请把用户自然语言策略拆解为本系统可运行的受限 JSON 参数。"
            "只允许现货多头或组合回测语义；不得输出代码；不得承诺收益；不得把 enabled 改成 true；"
            "自动交易 mode 必须保持 paper。输出必须是单个 JSON 对象，不能有 Markdown。\n\n"
            f"允许 style: {', '.join(SUPPORTED_STYLES)}。\n"
            f"允许 backtest preset: {', '.join(sorted(BACKTEST_PRESETS))}。\n"
            f"JSON schema 示例: {json.dumps(schema, ensure_ascii=False)}\n\n"
            f"本地规则初稿: {json.dumps(asdict(base), ensure_ascii=False)}\n\n"
            f"用户策略描述: {description}"
        )


def _compiled_from_payload(payload: dict[str, object], *, base: CompiledStrategy, model: str) -> CompiledStrategy:
    quote_asset = _safe_quote(str(payload.get("quote_asset", base.quote_asset)), base.quote_asset)
    symbols = _sanitize_symbols(payload.get("symbols"), quote_asset) or base.symbols
    interval = _safe_interval(str(payload.get("interval", base.interval)), base.interval)
    style = str(payload.get("style", base.style)).strip().lower()
    if style not in SUPPORTED_STYLES:
        style = base.style

    backtest_defaults = _merge_backtest_defaults(
        base.backtest_defaults,
        _dict_payload(payload.get("backtest_defaults")),
    )
    autotrade_defaults = _merge_autotrade_defaults(
        base.autotrade_defaults,
        _dict_payload(payload.get("autotrade_defaults")),
    )
    autotrade_defaults["enabled"] = False
    autotrade_defaults["mode"] = "paper"
    autotrade_defaults["paper_enabled"] = False
    autotrade_defaults["live_enabled"] = False
    autotrade_defaults["order_test_only"] = True

    return CompiledStrategy(
        name=_safe_text(payload.get("name"), base.name, max_length=80),
        description=_safe_text(payload.get("description"), base.description, max_length=600),
        symbols=symbols,
        quote_asset=quote_asset,
        interval=interval,
        style=style,
        entry_rules=_safe_text_list(payload.get("entry_rules"), base.entry_rules, limit=6),
        exit_rules=_safe_text_list(payload.get("exit_rules"), base.exit_rules, limit=6),
        risk_controls=_safe_text_list(payload.get("risk_controls"), base.risk_controls, limit=6),
        backtest_defaults=backtest_defaults,
        autotrade_defaults=autotrade_defaults,
        source="openai",
        model=model,
        warnings=_dedupe([*base.warnings, *_safe_text_list(payload.get("warnings"), [], limit=6)]),
    )


def _merge_backtest_defaults(base: dict[str, object], updates: dict[str, object]) -> dict[str, object]:
    result = dict(base)
    for key, value in updates.items():
        if key == "preset":
            preset = str(value).strip()
            result[key] = preset if preset in BACKTEST_PRESETS else result.get(key, "custom")
        elif key in {"lookback_bars", "portfolio_top_n", "cooldown_bars", "max_holding_bars", "slippage_window_bars", "max_concurrent_positions"}:
            result[key] = _clamp_int(value, _int_bounds(key))
        elif key in {
            "score_threshold",
            "stop_loss_pct",
            "take_profit_pct",
            "fee_bps",
            "maker_fee_bps",
            "taker_fee_bps",
            "fee_discount_pct",
            "slippage_bps",
            "min_slippage_bps",
            "max_slippage_bps",
            "capital_fraction_pct",
            "max_portfolio_exposure_pct",
            "min_volume_ratio",
            "min_buy_pressure",
            "min_rsi",
            "max_rsi",
            "max_entry_volatility_percentile",
            "max_entry_volatility_ratio",
        }:
            result[key] = _clamp_float(value, _float_bounds(key))
        elif key in {
            "no_binance_discount",
            "no_kdj_confirmation",
            "volatility_filter_enabled",
            "block_extreme_volatility",
        }:
            result[key] = _safe_bool(value)
        elif key == "holding_periods":
            result[key] = _safe_holding_periods(value, str(result.get(key, "3,6,12")))
        elif key in {"archives", "fee_model", "fee_source", "entry_fee_role", "exit_fee_role", "slippage_model"}:
            result[key] = _safe_choice_or_text(key, value, str(result.get(key, "")))
    return result


def _merge_autotrade_defaults(base: dict[str, object], updates: dict[str, object]) -> dict[str, object]:
    result = dict(base)
    for key, value in updates.items():
        if key == "enabled":
            result[key] = False
        elif key == "mode":
            result[key] = "paper"
        elif key in {"paper_enabled", "live_enabled"}:
            result[key] = False
        elif key == "order_test_only":
            result[key] = True
        elif key in {"max_open_positions", "cooldown_minutes"}:
            bounds = (1, 20) if key == "max_open_positions" else (0, 10080)
            result[key] = _clamp_int(value, bounds)
        elif key in {
            "quote_order_qty",
            "max_total_quote_exposure",
            "score_threshold",
            "min_volume_ratio",
            "min_buy_pressure",
            "stop_loss_pct",
            "take_profit_pct",
        }:
            result[key] = _clamp_float(value, _autotrade_float_bounds(key))
    result["enabled"] = False
    result["mode"] = "paper"
    result["paper_enabled"] = False
    result["live_enabled"] = False
    result["order_test_only"] = True
    return result


def _normalize_text(text: str) -> str:
    normalized = text.strip()
    for alias, base in ASSET_ALIASES.items():
        normalized = normalized.replace(alias, base)
    return normalized.upper()


def _extract_quote_asset(text: str, default: str) -> str:
    for quote in ("USDT", "USDC"):
        if re.search(rf"\b{quote}\b", text):
            return quote
    for base in KNOWN_BASE_ASSETS:
        for quote in SUPPORTED_QUOTES:
            if re.search(rf"\b{base}{quote}\b", text) or re.search(rf"(?:\$|\b){base}\s*[/_-]\s*{quote}\b", text):
                return quote
    return _safe_quote(default, "USDT")


def _extract_symbols(text: str, quote_asset: str) -> list[str]:
    symbols: list[str] = []
    for base in KNOWN_BASE_ASSETS:
        for quote in SUPPORTED_QUOTES:
            compact_pair = rf"\b{base}{quote}\b"
            separated_pair = rf"(?:\$|\b){base}\s*[/_-]\s*{quote}\b"
            if re.search(compact_pair, text) or re.search(separated_pair, text):
                symbol = f"{base}{quote}"
                if symbol not in symbols:
                    symbols.append(symbol)
        standalone = rf"(?:\$|\b){base}\b"
        if re.search(standalone, text) and not any(symbol.startswith(base) for symbol in symbols):
            symbols.append(f"{base}{quote_asset}")
    return symbols or [f"BTC{quote_asset}"]


def _sanitize_symbols(value: object, quote_asset: str) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\s,，/]+", value)
    elif isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        return []
    symbols: list[str] = []
    for raw in raw_items:
        text = _normalize_text(str(raw))
        for base in KNOWN_BASE_ASSETS:
            match = re.search(rf"\b{base}(?:({'|'.join(SUPPORTED_QUOTES)}))?\b", text)
            if match:
                quote = match.group(1) or quote_asset
                symbol = f"{base}{quote}"
                if symbol not in symbols:
                    symbols.append(symbol)
                break
    return symbols[:12]


def _extract_interval(text: str, default: str) -> str:
    if "日线" in text:
        return "1d"
    match = re.search(r"\b(1|3|5|15|30)\s*(M|MIN|分钟)\b", text)
    if match:
        return _safe_interval(f"{match.group(1)}m", default)
    match = re.search(r"\b(1|2|4|6|8|12)\s*(H|HOUR|小时)\b", text)
    if match:
        return _safe_interval(f"{match.group(1)}h", default)
    match = re.search(r"\b(1)\s*(D|DAY|天)\b", text)
    if match:
        return "1d"
    match = re.search(r"\b(1M|3M|5M|15M|30M|1H|2H|4H|6H|8H|12H|1D)\b", text)
    if match:
        return _safe_interval(match.group(1).lower(), default)
    return _safe_interval(default, "4h")


def _detect_style(text: str) -> str:
    if re.search(r"再平衡|等权|REBALANCE|EQUAL", text):
        return "rebalance"
    if re.search(r"隔夜|OVERNIGHT|22:00|22点|UTC\s*22", text):
        return "seasonality"
    if re.search(r"价差|套利|BASIS|FUNDING|资金费率", text):
        return "basis"
    if re.search(r"均值|回归|RSI|超卖|反弹|VWAP|布林|BOLLINGER|KELTNER|MEAN", text):
        return "mean_reversion"
    if re.search(r"趋势跟随|顺势|海龟|均线趋势|TREND FOLLOW|TREND-FOLLOW|TURTLE|DONCHIAN", text):
        return "trend_following"
    if re.search(r"突破|箱体|阻力|压力位|新高|放量突破|BREAKOUT|RESISTANCE|RANGE BREAK", text):
        return "breakout"
    if re.search(r"动量|强者恒强|相对强弱|轮动|涨幅排名|MOMENTUM|RELATIVE STRENGTH|ROTATION", text):
        return "momentum"
    if re.search(r"趋势|金叉|DEMA|EMA|MACD|放量|TREND", text):
        return "momentum"
    return "balanced"


def _extract_percent(text: str, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        pattern = rf"{re.escape(key)}\s*(?:为|设为|控制在|控制|<=|<|=|:|：|-)?\s*(\d+(?:\.\d+)?)\s*%"
        match = re.search(pattern, text)
        if match:
            return _clamp_float(match.group(1), (0.1, 100.0))
    return None


def _extract_holding_bars(text: str, interval: str) -> int | None:
    match = re.search(r"(?:持有|HOLD)\s*(\d+(?:\.\d+)?)\s*(分钟|MIN|M|小时|HOUR|H|天|DAY|D|根|BAR|BARS)", text)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    interval_minutes = _interval_minutes(interval)
    if unit in {"根", "BAR", "BARS"}:
        return max(1, int(round(amount)))
    if unit in {"分钟", "MIN", "M"}:
        minutes = amount
    elif unit in {"小时", "HOUR", "H"}:
        minutes = amount * 60
    else:
        minutes = amount * 1440
    return max(1, int(round(minutes / interval_minutes)))


def _extract_rsi_threshold(text: str, *, default: float) -> float:
    match = re.search(r"RSI\s*(?:<=|<|低于|小于)?\s*(\d+(?:\.\d+)?)", text)
    if match:
        return _clamp_float(match.group(1), (5.0, 60.0))
    if "超卖" in text:
        return 35.0
    return default


def _base_warnings(text: str, symbols: list[str]) -> list[str]:
    warnings = ["编译结果不会自动开启实盘；请先回测并用 paper 模式验证。"]
    if len(symbols) > 6:
        warnings.append("标的较多，自动交易会限制最大并发持仓。")
    if re.search(r"稳赚|保证收益|无风险|必赚|GUARANTEED", text):
        warnings.append("策略描述包含保证收益语义，系统已按风险策略处理，不承诺收益。")
    return warnings


def _strategy_name(style: str, symbols: list[str], interval: str) -> str:
    style_label = {
        "trend_following": "趋势跟随",
        "breakout": "突破",
        "mean_reversion": "均值回归",
        "momentum": "动量轮动",
        "rebalance": "等权再平衡",
        "seasonality": "隔夜季节性",
        "basis": "价差监控",
        "balanced": "综合评分",
    }[style]
    primary = symbols[0].replace("USDT", "") if symbols else "BTC"
    suffix = "组合" if len(symbols) > 1 else primary
    return f"{suffix} {interval} {style_label}策略"


def _extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型输出不是 JSON 对象。")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("模型输出 JSON 根节点必须是对象。")
    return parsed


def _dict_payload(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _safe_quote(value: str, default: str) -> str:
    candidate = value.strip().upper()
    return candidate if candidate in SUPPORTED_QUOTES else default.strip().upper()


def _safe_interval(value: str, default: str) -> str:
    candidate = value.strip().lower()
    return candidate if candidate in SUPPORTED_INTERVALS else default.strip().lower()


def _safe_text(value: object, default: str, *, max_length: int) -> str:
    text = str(value).strip() if value is not None else ""
    return (text or default)[:max_length]


def _safe_text_list(value: object, default: list[str], *, limit: int) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = default
    return _dedupe([item.strip()[:160] for item in items if item and item.strip()])[:limit]


def _safe_holding_periods(value: object, default: str) -> str:
    if isinstance(value, list):
        raw = ",".join(str(item) for item in value)
    else:
        raw = str(value)
    periods = []
    for item in re.split(r"[,，\s]+", raw):
        if not item:
            continue
        try:
            periods.append(str(_clamp_int(item, (1, 2000))))
        except ValueError:
            continue
    return ",".join(periods) if periods else default


def _safe_choice_or_text(key: str, value: object, default: str) -> str:
    candidate = str(value).strip()
    choices = {
        "fee_model": {"flat", "maker_taker"},
        "fee_source": {"manual", "account", "symbol"},
        "entry_fee_role": {"maker", "taker"},
        "exit_fee_role": {"maker", "taker"},
        "slippage_model": {"fixed", "dynamic"},
    }.get(key)
    if choices is not None:
        return candidate if candidate in choices else default
    return candidate[:1000]


def _safe_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"", "0", "false", "no", "off", "none", "null"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    return bool(normalized)


def _clamp_int(value: object, bounds: tuple[int, int]) -> int:
    number = int(float(str(value)))
    return max(bounds[0], min(bounds[1], number))


def _clamp_float(value: object, bounds: tuple[float, float]) -> float:
    number = float(str(value))
    return max(bounds[0], min(bounds[1], number))


def _int_bounds(key: str) -> tuple[int, int]:
    return {
        "lookback_bars": (20, 5000),
        "portfolio_top_n": (0, 20),
        "cooldown_bars": (0, 500),
        "max_holding_bars": (1, 2000),
        "slippage_window_bars": (1, 500),
        "max_concurrent_positions": (0, 20),
    }[key]


def _float_bounds(key: str) -> tuple[float, float]:
    return {
        "score_threshold": (0.0, 100.0),
        "stop_loss_pct": (0.1, 50.0),
        "take_profit_pct": (0.1, 100.0),
        "fee_bps": (0.0, 200.0),
        "maker_fee_bps": (0.0, 200.0),
        "taker_fee_bps": (0.0, 200.0),
        "fee_discount_pct": (0.0, 100.0),
        "slippage_bps": (0.0, 200.0),
        "min_slippage_bps": (0.0, 200.0),
        "max_slippage_bps": (0.0, 300.0),
        "capital_fraction_pct": (0.1, 100.0),
        "max_portfolio_exposure_pct": (0.1, 100.0),
        "min_volume_ratio": (0.0, 10.0),
        "min_buy_pressure": (0.0, 1.0),
        "min_rsi": (0.0, 100.0),
        "max_rsi": (0.0, 100.0),
        "max_entry_volatility_percentile": (0.0, 100.0),
        "max_entry_volatility_ratio": (0.1, 20.0),
    }[key]


def _autotrade_float_bounds(key: str) -> tuple[float, float]:
    return {
        "quote_order_qty": (0.01, 1_000_000.0),
        "max_total_quote_exposure": (0.01, 10_000_000.0),
        "score_threshold": (0.0, 100.0),
        "min_volume_ratio": (0.0, 10.0),
        "min_buy_pressure": (0.0, 1.0),
        "stop_loss_pct": (0.1, 50.0),
        "take_profit_pct": (0.1, 100.0),
    }[key]


def _interval_minutes(interval: str) -> float:
    if interval.endswith("m"):
        return float(interval[:-1])
    if interval.endswith("h"):
        return float(interval[:-1]) * 60
    if interval.endswith("d"):
        return float(interval[:-1]) * 1440
    return 240.0


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _replace_compiled(strategy: CompiledStrategy, **changes: Any) -> CompiledStrategy:
    payload = asdict(strategy)
    payload.update(changes)
    return CompiledStrategy(**payload)
