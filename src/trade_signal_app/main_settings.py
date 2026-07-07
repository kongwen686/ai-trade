from __future__ import annotations

import json

from .config import SETTINGS
from .data_services import LLM_PROVIDER_PRESETS, PUBLIC_DATA_PRESETS, get_llm_provider, llm_provider_ids, public_data_preset_ids
from .platform import okx_credential_state
from .presets import apply_backtest_preset, list_backtest_presets
from .runtime_config import AUTOTRADE_EXIT_PROFILES, AutoTradeDefaults, BacktestDefaults, IntelligenceDefaults, RuntimeConfig, ScanDefaults
from .tradingview_data import TRADINGVIEW_INTERVALS

SCAN_INTERVALS = {"15m", "1h", "4h", "1d"}
AUTOTRADE_MODES = {"paper", "live"}
AUTOTRADE_EXCHANGES = {"binance", "okx"}
X_ACCOUNT_MODES = {"off", "blend", "only"}
X_PROVIDERS = {"official_api", "nitter_rss", "session_scrape"}
FEE_MODELS = {"flat", "maker_taker"}
FEE_SOURCES = {"manual", "account", "symbol"}
FEE_ROLES = {"maker", "taker"}
SLIPPAGE_MODELS = {"fixed", "dynamic"}
TRADINGVIEW_INTERVAL_CHOICES = set(TRADINGVIEW_INTERVALS)
MARKET_DATA_PRESETS = public_data_preset_ids("market")
ONCHAIN_DATA_PRESETS = public_data_preset_ids("onchain")
LLM_PROVIDERS = llm_provider_ids()


def _parse_int_value(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{label} 需要是整数。") from exc


def _parse_float_value(value: str, label: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{label} 需要是数字。") from exc


def _parse_multiline_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


def _validate_choice(value: str, label: str, choices: set[str]) -> None:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{label} 只能是：{allowed}。")


def _validate_range(value: float, label: str, *, minimum: float | None = None, maximum: float | None = None) -> None:
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} 不能小于 {minimum:g}。")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} 不能大于 {maximum:g}。")


def _get_first(query: dict[str, list[str]], key: str, default: str) -> str:
    return query.get(key, [default])[0]


def _parse_bool_flag(query: dict[str, list[str]], key: str) -> bool:
    return key in query and any(str(value).strip() not in {"", "0", "false", "False", "off"} for value in query.get(key, []))


def _runtime_bool(form: dict[str, list[str]], key: str, current: bool) -> bool:
    if key not in form:
        return current
    return _parse_bool_flag(form, key)


def _validate_runtime_config(config: RuntimeConfig) -> None:
    _validate_choice(config.scan_defaults.interval, "Scan Interval", SCAN_INTERVALS)
    _validate_choice(config.autotrade_defaults.mode, "Auto Trade Mode", AUTOTRADE_MODES)
    _validate_choice(config.autotrade_defaults.execution_exchange, "Auto Trade Exchange", AUTOTRADE_EXCHANGES)
    _validate_choice(config.autotrade_defaults.exit_profile, "Auto Trade Exit Profile", AUTOTRADE_EXIT_PROFILES)
    _validate_choice(config.x_account_mode, "X Account Mode", X_ACCOUNT_MODES)
    _validate_choice(config.x_provider, "X Provider", X_PROVIDERS)
    _validate_choice(config.market_data_preset, "Market Data Preset", MARKET_DATA_PRESETS)
    _validate_choice(config.tradingview_interval, "TradingView Interval", TRADINGVIEW_INTERVAL_CHOICES)
    _validate_choice(config.onchain_data_preset, "On-chain Data Preset", ONCHAIN_DATA_PRESETS)
    _validate_choice(config.llm_provider, "LLM Provider", LLM_PROVIDERS)
    _validate_choice(config.backtest_defaults.fee_model, "Backtest Fee Model", FEE_MODELS)
    _validate_choice(config.backtest_defaults.fee_source, "Backtest Fee Source", FEE_SOURCES)
    _validate_choice(config.backtest_defaults.entry_fee_role, "Backtest Entry Fee Role", FEE_ROLES)
    _validate_choice(config.backtest_defaults.exit_fee_role, "Backtest Exit Fee Role", FEE_ROLES)
    _validate_choice(config.backtest_defaults.slippage_model, "Backtest Slippage Model", SLIPPAGE_MODELS)
    preset_ids = {str(item["preset_id"]) for item in list_backtest_presets()}
    _validate_choice(config.backtest_defaults.preset, "Backtest Preset", preset_ids)

    _validate_range(config.binance_recv_window_ms, "Binance RecvWindow", minimum=1)
    _validate_range(config.x_recent_window_hours, "X Window Hours", minimum=1)
    _validate_range(config.x_recent_max_results, "X Max Results", minimum=10, maximum=100)
    _validate_range(config.reddit_recent_window_hours, "Reddit Window Hours", minimum=1)
    _validate_range(config.reddit_max_results, "Reddit Max Results", minimum=5, maximum=100)
    _validate_range(config.x_account_weight_pct, "Account Weight", minimum=0, maximum=100)
    _validate_range(config.tradingview_bars, "TradingView Bars", minimum=100, maximum=50000)
    if config.feishu_webhook_url and not config.feishu_webhook_url.startswith(("http://", "https://")):
        raise ValueError("Feishu Webhook URL 必须以 http:// 或 https:// 开头。")
    if not config.tradingview_exchange.strip().isalnum():
        raise ValueError("TradingView Exchange 只能包含字母和数字。")
    if not config.tradingview_symbols:
        raise ValueError("TradingView Symbols 至少需要填写一个标的。")
    for symbol in config.tradingview_symbols:
        if not symbol.replace("-", "").replace("_", "").isalnum():
            raise ValueError("TradingView Symbols 只能包含字母、数字、横线或下划线。")

    scan = config.scan_defaults
    _validate_range(scan.candidate_pool, "Candidate Pool", minimum=5, maximum=40)
    _validate_range(scan.min_quote_volume, "Min Quote Volume", minimum=0)
    _validate_range(scan.min_trade_count, "Min Trade Count", minimum=0)
    if not scan.quote_asset.strip().isalnum():
        raise ValueError("Quote Asset 只能包含字母和数字。")

    autotrade = config.autotrade_defaults
    _validate_range(autotrade.quote_order_qty, "Auto Trade Quote Order Qty", minimum=0.01)
    _validate_range(autotrade.leverage, "Auto Trade Leverage", minimum=1, maximum=20)
    _validate_range(autotrade.risk_per_trade_pct, "Auto Trade Risk Per Trade", minimum=0.1, maximum=100)
    _validate_range(autotrade.max_open_positions, "Auto Trade Max Open Positions", minimum=1)
    _validate_range(autotrade.max_total_quote_exposure, "Auto Trade Max Exposure", minimum=0.01)
    _validate_range(autotrade.score_threshold, "Auto Trade Score Threshold", minimum=0, maximum=100)
    _validate_range(autotrade.min_volume_ratio, "Auto Trade Min Volume Ratio", minimum=0)
    _validate_range(autotrade.min_buy_pressure, "Auto Trade Min Buy Pressure", minimum=0, maximum=1)
    _validate_range(autotrade.stop_loss_pct, "Auto Trade Stop Loss", minimum=0.1)
    _validate_range(autotrade.take_profit_pct, "Auto Trade Take Profit", minimum=0.1)
    _validate_range(autotrade.profit_protection_trigger_pct, "Auto Trade Profit Protection Trigger", minimum=0)
    _validate_range(autotrade.profit_protection_lock_pct, "Auto Trade Profit Protection Lock", minimum=0)
    _validate_range(autotrade.trailing_stop_pct, "Auto Trade Trailing Stop", minimum=0)
    _validate_range(autotrade.trend_hold_min_score, "Auto Trade Trend Hold Score", minimum=0, maximum=100)
    _validate_range(autotrade.trend_hold_min_volume_ratio, "Auto Trade Trend Hold Volume", minimum=0)
    _validate_range(autotrade.trend_hold_min_buy_pressure, "Auto Trade Trend Hold Buy Pressure", minimum=0, maximum=1)
    _validate_range(autotrade.emergency_drawdown_pct, "Auto Trade Emergency Drawdown", minimum=0, maximum=50)
    if autotrade.profit_protection_enabled and autotrade.profit_protection_lock_pct > autotrade.profit_protection_trigger_pct:
        raise ValueError("Auto Trade Profit Protection Lock 不能大于 Trigger。")
    _validate_range(autotrade.cooldown_minutes, "Auto Trade Cooldown", minimum=0)

    intelligence = config.intelligence_defaults
    _validate_range(intelligence.min_intel_severity, "Intelligence Min Severity", minimum=0, maximum=100)
    _validate_range(intelligence.min_spread_bps, "Intelligence Min Spread", minimum=0)
    _validate_range(intelligence.whale_transfer_threshold_usd, "Whale Transfer Threshold", minimum=0)

    backtest = config.backtest_defaults
    _validate_range(backtest.lookback_bars, "Lookback Bars", minimum=60)
    _validate_range(backtest.portfolio_top_n, "Portfolio Top N", minimum=0)
    _validate_range(backtest.cooldown_bars, "Cooldown Bars", minimum=0)
    _validate_range(backtest.stop_loss_pct, "Backtest Stop Loss", minimum=0)
    _validate_range(backtest.take_profit_pct, "Backtest Take Profit", minimum=0)
    _validate_range(backtest.max_holding_bars, "Max Holding Bars", minimum=1)
    _validate_range(backtest.fee_bps, "Fee bps", minimum=0)
    _validate_range(backtest.maker_fee_bps, "Maker Fee", minimum=0)
    _validate_range(backtest.taker_fee_bps, "Taker Fee", minimum=0)
    _validate_range(backtest.fee_discount_pct, "Fee Discount", minimum=0, maximum=100)
    _validate_range(backtest.slippage_bps, "Slippage bps", minimum=0)
    _validate_range(backtest.min_slippage_bps, "Min Slippage", minimum=0)
    _validate_range(backtest.max_slippage_bps, "Max Slippage", minimum=0)
    _validate_range(backtest.slippage_window_bars, "Slip Window", minimum=1)
    _validate_range(backtest.capital_fraction_pct, "Capital", minimum=0, maximum=100)
    _validate_range(backtest.max_portfolio_exposure_pct, "Max Exposure", minimum=0, maximum=100)
    _validate_range(backtest.max_concurrent_positions, "Max Concurrent", minimum=0)
    _validate_range(backtest.min_volume_ratio, "Backtest Min Volume Ratio", minimum=0)
    _validate_range(backtest.min_buy_pressure, "Backtest Min Buy Pressure", minimum=0, maximum=1)
    _validate_range(backtest.min_rsi, "Min RSI", minimum=0, maximum=100)
    _validate_range(backtest.max_rsi, "Max RSI", minimum=0, maximum=100)
    if backtest.min_rsi > backtest.max_rsi:
        raise ValueError("Min RSI 不能大于 Max RSI。")


def _scan_params_from_config(config: RuntimeConfig) -> dict[str, object]:
    return {
        "quote_asset": config.scan_defaults.quote_asset,
        "interval": config.scan_defaults.interval,
        "candidate_pool": config.scan_defaults.candidate_pool,
        "min_quote_volume": int(config.scan_defaults.min_quote_volume),
        "min_trade_count": config.scan_defaults.min_trade_count,
    }


def _backtest_params_from_config(config: RuntimeConfig) -> dict[str, object]:
    defaults = config.backtest_defaults
    params = {
        "preset": defaults.preset,
        "archives": defaults.archives,
        "lookback_bars": defaults.lookback_bars,
        "score_threshold": defaults.score_threshold,
        "holding_periods": defaults.holding_periods,
        "portfolio_top_n": defaults.portfolio_top_n,
        "cooldown_bars": defaults.cooldown_bars,
        "stop_loss_pct": defaults.stop_loss_pct,
        "take_profit_pct": defaults.take_profit_pct,
        "max_holding_bars": defaults.max_holding_bars,
        "fee_bps": defaults.fee_bps,
        "fee_model": defaults.fee_model,
        "fee_source": defaults.fee_source,
        "maker_fee_bps": defaults.maker_fee_bps,
        "taker_fee_bps": defaults.taker_fee_bps,
        "entry_fee_role": defaults.entry_fee_role,
        "exit_fee_role": defaults.exit_fee_role,
        "fee_discount_pct": defaults.fee_discount_pct,
        "no_binance_discount": defaults.no_binance_discount,
        "slippage_bps": defaults.slippage_bps,
        "slippage_model": defaults.slippage_model,
        "min_slippage_bps": defaults.min_slippage_bps,
        "max_slippage_bps": defaults.max_slippage_bps,
        "slippage_window_bars": defaults.slippage_window_bars,
        "capital_fraction_pct": defaults.capital_fraction_pct,
        "max_portfolio_exposure_pct": defaults.max_portfolio_exposure_pct,
        "max_concurrent_positions": defaults.max_concurrent_positions,
        "min_volume_ratio": defaults.min_volume_ratio,
        "min_buy_pressure": defaults.min_buy_pressure,
        "min_rsi": defaults.min_rsi,
        "max_rsi": defaults.max_rsi,
        "no_kdj_confirmation": defaults.no_kdj_confirmation,
    }
    return apply_backtest_preset(params, defaults.preset)


def _settings_params_from_config(config: RuntimeConfig) -> dict[str, object]:
    backtest = _backtest_params_from_config(config)
    autotrade = config.autotrade_defaults
    intelligence = config.intelligence_defaults
    okx_state = okx_credential_state(config)
    return {
        "binance_recv_window_ms": config.binance_recv_window_ms,
        "okx_auth_configured": bool(okx_state["configured"]),
        "okx_auth_partial": bool(okx_state["partial"]),
        "okx_auth_status": okx_state["status"],
        "okx_auth_label": okx_state["label"],
        "okx_auth_message": okx_state["message"],
        "market_data_preset": config.market_data_preset,
        "tradingview_username": config.tradingview_username,
        "tradingview_exchange": config.tradingview_exchange,
        "tradingview_symbols": config.tradingview_symbols,
        "tradingview_interval": config.tradingview_interval,
        "tradingview_bars": config.tradingview_bars,
        "tradingview_cache_enabled": config.tradingview_cache_enabled,
        "onchain_data_preset": config.onchain_data_preset,
        "onchain_api_base_url": config.onchain_api_base_url,
        "community_provider": config.community_provider,
        "x_provider": config.x_provider,
        "x_api_base_url": config.x_api_base_url,
        "x_nitter_base_url": config.x_nitter_base_url,
        "x_session_command": config.x_session_command,
        "x_recent_window_hours": config.x_recent_window_hours,
        "x_recent_max_results": config.x_recent_max_results,
        "x_language": config.x_language,
        "reddit_api_base_url": config.reddit_api_base_url,
        "reddit_recent_window_hours": config.reddit_recent_window_hours,
        "reddit_max_results": config.reddit_max_results,
        "reddit_user_agent": config.reddit_user_agent,
        "llm_provider": config.llm_provider,
        "llm_base_url": config.llm_base_url,
        "llm_model": config.llm_model,
        "openai_model": config.openai_model,
        "feishu_webhook_configured": bool(config.feishu_webhook_url),
        "x_account_mode": config.x_account_mode,
        "x_account_weight_pct": config.x_account_weight_pct,
        "x_tracked_accounts": config.x_tracked_accounts,
        "scan_quote_asset": config.scan_defaults.quote_asset,
        "scan_interval": config.scan_defaults.interval,
        "scan_candidate_pool": config.scan_defaults.candidate_pool,
        "scan_min_quote_volume": int(config.scan_defaults.min_quote_volume),
        "scan_min_trade_count": config.scan_defaults.min_trade_count,
        "autotrade_enabled": autotrade.enabled,
        "autotrade_mode": autotrade.mode,
        "autotrade_execution_exchange": autotrade.execution_exchange,
        "autotrade_quote_order_qty": autotrade.quote_order_qty,
        "autotrade_leverage": autotrade.leverage,
        "autotrade_risk_per_trade_pct": autotrade.risk_per_trade_pct,
        "autotrade_exit_profile": autotrade.exit_profile,
        "autotrade_max_open_positions": autotrade.max_open_positions,
        "autotrade_max_total_quote_exposure": autotrade.max_total_quote_exposure,
        "autotrade_score_threshold": autotrade.score_threshold,
        "autotrade_min_volume_ratio": autotrade.min_volume_ratio,
        "autotrade_min_buy_pressure": autotrade.min_buy_pressure,
        "autotrade_stop_loss_pct": autotrade.stop_loss_pct,
        "autotrade_take_profit_pct": autotrade.take_profit_pct,
        "autotrade_profit_protection_enabled": autotrade.profit_protection_enabled,
        "autotrade_profit_protection_trigger_pct": autotrade.profit_protection_trigger_pct,
        "autotrade_profit_protection_lock_pct": autotrade.profit_protection_lock_pct,
        "autotrade_trailing_stop_pct": autotrade.trailing_stop_pct,
        "autotrade_trend_hold_enabled": autotrade.trend_hold_enabled,
        "autotrade_trend_hold_min_score": autotrade.trend_hold_min_score,
        "autotrade_trend_hold_min_volume_ratio": autotrade.trend_hold_min_volume_ratio,
        "autotrade_trend_hold_min_buy_pressure": autotrade.trend_hold_min_buy_pressure,
        "autotrade_emergency_drawdown_pct": autotrade.emergency_drawdown_pct,
        "autotrade_cooldown_minutes": autotrade.cooldown_minutes,
        "autotrade_order_test_only": autotrade.order_test_only,
        "intelligence_enabled": intelligence.enabled,
        "intelligence_llm_enabled": intelligence.llm_enabled,
        "intelligence_llm_provider": intelligence.llm_provider,
        "intelligence_llm_base_url": intelligence.llm_base_url,
        "intelligence_llm_model": intelligence.llm_model,
        "intelligence_openai_model": intelligence.openai_model,
        "intelligence_min_intel_severity": intelligence.min_intel_severity,
        "intelligence_min_spread_bps": intelligence.min_spread_bps,
        "intelligence_whale_transfer_threshold_usd": intelligence.whale_transfer_threshold_usd,
        **{f"backtest_{key}": value for key, value in backtest.items()},
    }


def _settings_status_from_config(config: RuntimeConfig, *, storage_mode: str, tradingview_cache_dir: object) -> dict[str, object]:
    okx_state = okx_credential_state(config)
    return {
        "binance_auth_configured": bool(config.binance_api_key and config.binance_api_secret),
        "binance_auth_label": "API key + secret 已配置" if config.binance_api_key and config.binance_api_secret else "未配置",
        "okx_auth_configured": bool(okx_state["configured"]),
        "okx_auth_partial": bool(okx_state["partial"]),
        "okx_auth_status": okx_state["status"],
        "okx_auth_label": okx_state["label"],
        "okx_auth_message": okx_state["message"],
        "x_auth_configured": bool(config.x_bearer_token),
        "x_provider": config.x_provider,
        "x_provider_configured": (
            bool(config.x_bearer_token)
            if config.x_provider == "official_api"
            else bool(config.x_nitter_base_url)
            if config.x_provider == "nitter_rss"
            else bool(config.x_session_command)
        ),
        "tracked_account_count": len(config.x_tracked_accounts),
        "exchange_community_configured": bool(SETTINGS.exchange_community_urls),
        "tradingview_auth_configured": bool(config.tradingview_username and config.tradingview_password),
        "tradingview_cache_dir": str(tradingview_cache_dir),
        "storage_mode": storage_mode,
        "autotrade_enabled": config.autotrade_defaults.enabled,
        "autotrade_mode": config.autotrade_defaults.mode,
        "feishu_webhook_configured": bool(config.feishu_webhook_url),
        "intelligence_enabled": config.intelligence_defaults.enabled,
        "llm_enabled": config.intelligence_defaults.llm_enabled,
        "llm_provider": config.intelligence_defaults.llm_provider,
        "llm_configured": bool(config.intelligence_defaults.llm_api_key or config.intelligence_defaults.openai_api_key),
        "public_data_presets": [preset.__dict__ for preset in PUBLIC_DATA_PRESETS],
        "llm_provider_presets": [preset.__dict__ for preset in LLM_PROVIDER_PRESETS],
    }


def _import_runtime_config_template(form: dict[str, list[str]], *, current_config: RuntimeConfig, settings: object = SETTINGS) -> RuntimeConfig:
    raw_template = _get_first(form, "config_template", "").strip()
    if not raw_template:
        raise ValueError("请先粘贴配置模板 JSON。")

    try:
        payload = json.loads(raw_template)
    except json.JSONDecodeError as exc:
        raise ValueError("配置模板不是合法 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("配置模板根节点必须是 JSON 对象。")

    config = RuntimeConfig.from_template_payload(payload, settings, current_config=current_config)
    _validate_runtime_config(config)
    return config


def _build_runtime_config(form: dict[str, list[str]], *, current_config: RuntimeConfig) -> RuntimeConfig:
    keep_binance_key = current_config.binance_api_key
    keep_binance_secret = current_config.binance_api_secret
    keep_okx_key = current_config.okx_api_key
    keep_okx_secret = current_config.okx_api_secret
    keep_okx_passphrase = current_config.okx_api_passphrase
    keep_x_bearer_token = current_config.x_bearer_token
    keep_onchain_api_key = current_config.onchain_api_key
    keep_tradingview_password = current_config.tradingview_password
    keep_llm_api_key = current_config.llm_api_key or current_config.openai_api_key
    keep_feishu_webhook_url = current_config.feishu_webhook_url
    if _parse_bool_flag(form, "clear_binance_auth"):
        keep_binance_key = ""
        keep_binance_secret = ""
    else:
        candidate = _get_first(form, "binance_api_key", "").strip()
        if candidate:
            keep_binance_key = candidate
        candidate = _get_first(form, "binance_api_secret", "").strip()
        if candidate:
            keep_binance_secret = candidate
    if _parse_bool_flag(form, "clear_okx_auth"):
        keep_okx_key = ""
        keep_okx_secret = ""
        keep_okx_passphrase = ""
    else:
        candidate = _get_first(form, "okx_api_key", "").strip()
        if candidate:
            keep_okx_key = candidate
        candidate = _get_first(form, "okx_api_secret", "").strip()
        if candidate:
            keep_okx_secret = candidate
        candidate = _get_first(form, "okx_api_passphrase", "").strip()
        if candidate:
            keep_okx_passphrase = candidate
    if _parse_bool_flag(form, "clear_x_auth"):
        keep_x_bearer_token = ""
    else:
        candidate = _get_first(form, "x_bearer_token", "").strip()
        if candidate:
            keep_x_bearer_token = candidate
    if _parse_bool_flag(form, "clear_onchain_auth"):
        keep_onchain_api_key = ""
    else:
        candidate = _get_first(form, "onchain_api_key", "").strip()
        if candidate:
            keep_onchain_api_key = candidate
    if _parse_bool_flag(form, "clear_tradingview_auth"):
        keep_tradingview_password = ""
    else:
        candidate = _get_first(form, "tradingview_password", "").strip()
        if candidate:
            keep_tradingview_password = candidate
    if _parse_bool_flag(form, "clear_llm_auth"):
        keep_llm_api_key = ""
    else:
        candidate = _get_first(form, "llm_api_key", "").strip() or _get_first(form, "openai_api_key", "").strip()
        if candidate:
            keep_llm_api_key = candidate
    if _parse_bool_flag(form, "clear_feishu_webhook"):
        keep_feishu_webhook_url = ""
    else:
        candidate = _get_first(form, "feishu_webhook_url", "").strip()
        if candidate:
            keep_feishu_webhook_url = candidate

    llm_provider = _get_first(form, "llm_provider", current_config.llm_provider).strip() or "openai"
    llm_model = _get_first(
        form,
        "llm_model",
        _get_first(form, "intelligence_openai_model", current_config.llm_model),
    ).strip() or get_llm_provider(llm_provider).default_model
    llm_base_url = _get_first(form, "llm_base_url", current_config.llm_base_url).strip()

    config = RuntimeConfig(
        binance_api_key=keep_binance_key,
        binance_api_secret=keep_binance_secret,
        binance_recv_window_ms=_parse_float_value(_get_first(form, "binance_recv_window_ms", str(current_config.binance_recv_window_ms)), "Binance RecvWindow"),
        okx_api_key=keep_okx_key,
        okx_api_secret=keep_okx_secret,
        okx_api_passphrase=keep_okx_passphrase,
        market_data_preset=_get_first(form, "market_data_preset", current_config.market_data_preset).strip() or "binance_public",
        tradingview_username=_get_first(form, "tradingview_username", current_config.tradingview_username).strip(),
        tradingview_password=keep_tradingview_password,
        tradingview_exchange=_get_first(form, "tradingview_exchange", current_config.tradingview_exchange).strip().upper() or current_config.tradingview_exchange,
        tradingview_symbols=[
            item.upper()
            for item in _parse_multiline_list(
                _get_first(form, "tradingview_symbols", "\n".join(current_config.tradingview_symbols))
            )
        ],
        tradingview_interval=_get_first(form, "tradingview_interval", current_config.tradingview_interval).strip() or current_config.tradingview_interval,
        tradingview_bars=_parse_int_value(_get_first(form, "tradingview_bars", str(current_config.tradingview_bars)), "TradingView Bars"),
        tradingview_cache_enabled=_runtime_bool(form, "tradingview_cache_enabled", current_config.tradingview_cache_enabled),
        onchain_data_preset=_get_first(form, "onchain_data_preset", current_config.onchain_data_preset).strip() or "open_multichain_keyless",
        onchain_api_key=keep_onchain_api_key,
        onchain_api_base_url=_get_first(form, "onchain_api_base_url", current_config.onchain_api_base_url).strip(),
        community_provider=_get_first(form, "community_provider", current_config.community_provider).strip() or "auto",
        x_provider=_get_first(form, "x_provider", current_config.x_provider).strip() or "official_api",
        x_bearer_token=keep_x_bearer_token,
        x_api_base_url=_get_first(form, "x_api_base_url", current_config.x_api_base_url).strip() or current_config.x_api_base_url,
        x_nitter_base_url=_get_first(form, "x_nitter_base_url", current_config.x_nitter_base_url).strip(),
        x_session_command=_get_first(form, "x_session_command", current_config.x_session_command).strip(),
        x_recent_window_hours=_parse_int_value(_get_first(form, "x_recent_window_hours", str(current_config.x_recent_window_hours)), "X Window Hours"),
        x_recent_max_results=_parse_int_value(_get_first(form, "x_recent_max_results", str(current_config.x_recent_max_results)), "X Max Results"),
        x_language=_get_first(form, "x_language", current_config.x_language).strip() or current_config.x_language,
        reddit_api_base_url=_get_first(form, "reddit_api_base_url", current_config.reddit_api_base_url).strip() or current_config.reddit_api_base_url,
        reddit_recent_window_hours=_parse_int_value(_get_first(form, "reddit_recent_window_hours", str(current_config.reddit_recent_window_hours)), "Reddit Window Hours"),
        reddit_max_results=_parse_int_value(_get_first(form, "reddit_max_results", str(current_config.reddit_max_results)), "Reddit Max Results"),
        reddit_user_agent=_get_first(form, "reddit_user_agent", current_config.reddit_user_agent).strip() or current_config.reddit_user_agent,
        llm_provider=llm_provider,
        llm_api_key=keep_llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        x_account_mode=_get_first(form, "x_account_mode", current_config.x_account_mode).strip() or current_config.x_account_mode,
        x_account_weight_pct=_parse_float_value(_get_first(form, "x_account_weight_pct", str(current_config.x_account_weight_pct)), "Account Weight"),
        x_tracked_accounts=_parse_multiline_list(_get_first(form, "x_tracked_accounts", "\n".join(current_config.x_tracked_accounts))),
        openai_api_key=keep_llm_api_key if llm_provider == "openai" else current_config.openai_api_key,
        openai_model=llm_model if llm_provider == "openai" else current_config.openai_model,
        feishu_webhook_url=keep_feishu_webhook_url,
        scan_defaults=ScanDefaults(
            quote_asset=_get_first(form, "scan_quote_asset", current_config.scan_defaults.quote_asset).strip().upper() or current_config.scan_defaults.quote_asset,
            interval=_get_first(form, "scan_interval", current_config.scan_defaults.interval).strip() or current_config.scan_defaults.interval,
            candidate_pool=_parse_int_value(_get_first(form, "scan_candidate_pool", str(current_config.scan_defaults.candidate_pool)), "Candidate Pool"),
            min_quote_volume=_parse_float_value(_get_first(form, "scan_min_quote_volume", str(current_config.scan_defaults.min_quote_volume)), "Min Quote Volume"),
            min_trade_count=_parse_int_value(_get_first(form, "scan_min_trade_count", str(current_config.scan_defaults.min_trade_count)), "Min Trade Count"),
        ),
        autotrade_defaults=AutoTradeDefaults(
            enabled=_runtime_bool(form, "autotrade_enabled", current_config.autotrade_defaults.enabled),
            mode=_get_first(form, "autotrade_mode", current_config.autotrade_defaults.mode).strip() or "paper",
            execution_exchange=_get_first(
                form,
                "autotrade_execution_exchange",
                current_config.autotrade_defaults.execution_exchange,
            ).strip().lower()
            or "binance",
            quote_order_qty=_parse_float_value(_get_first(form, "autotrade_quote_order_qty", str(current_config.autotrade_defaults.quote_order_qty)), "Auto Trade Quote Order Qty"),
            leverage=_parse_float_value(_get_first(form, "autotrade_leverage", str(current_config.autotrade_defaults.leverage)), "Auto Trade Leverage"),
            risk_per_trade_pct=_parse_float_value(_get_first(form, "autotrade_risk_per_trade_pct", str(current_config.autotrade_defaults.risk_per_trade_pct)), "Auto Trade Risk Per Trade"),
            exit_profile=_get_first(form, "autotrade_exit_profile", current_config.autotrade_defaults.exit_profile).strip() or "balanced",
            max_open_positions=_parse_int_value(_get_first(form, "autotrade_max_open_positions", str(current_config.autotrade_defaults.max_open_positions)), "Auto Trade Max Open Positions"),
            max_total_quote_exposure=_parse_float_value(_get_first(form, "autotrade_max_total_quote_exposure", str(current_config.autotrade_defaults.max_total_quote_exposure)), "Auto Trade Max Exposure"),
            score_threshold=_parse_float_value(_get_first(form, "autotrade_score_threshold", str(current_config.autotrade_defaults.score_threshold)), "Auto Trade Score Threshold"),
            min_volume_ratio=_parse_float_value(_get_first(form, "autotrade_min_volume_ratio", str(current_config.autotrade_defaults.min_volume_ratio)), "Auto Trade Min Volume Ratio"),
            min_buy_pressure=_parse_float_value(_get_first(form, "autotrade_min_buy_pressure", str(current_config.autotrade_defaults.min_buy_pressure)), "Auto Trade Min Buy Pressure"),
            stop_loss_pct=_parse_float_value(_get_first(form, "autotrade_stop_loss_pct", str(current_config.autotrade_defaults.stop_loss_pct)), "Auto Trade Stop Loss"),
            take_profit_pct=_parse_float_value(_get_first(form, "autotrade_take_profit_pct", str(current_config.autotrade_defaults.take_profit_pct)), "Auto Trade Take Profit"),
            profit_protection_enabled=_runtime_bool(form, "autotrade_profit_protection_enabled", current_config.autotrade_defaults.profit_protection_enabled),
            profit_protection_trigger_pct=_parse_float_value(_get_first(form, "autotrade_profit_protection_trigger_pct", str(current_config.autotrade_defaults.profit_protection_trigger_pct)), "Auto Trade Profit Protection Trigger"),
            profit_protection_lock_pct=_parse_float_value(_get_first(form, "autotrade_profit_protection_lock_pct", str(current_config.autotrade_defaults.profit_protection_lock_pct)), "Auto Trade Profit Protection Lock"),
            trailing_stop_pct=_parse_float_value(_get_first(form, "autotrade_trailing_stop_pct", str(current_config.autotrade_defaults.trailing_stop_pct)), "Auto Trade Trailing Stop"),
            trend_hold_enabled=_runtime_bool(form, "autotrade_trend_hold_enabled", current_config.autotrade_defaults.trend_hold_enabled),
            trend_hold_min_score=_parse_float_value(_get_first(form, "autotrade_trend_hold_min_score", str(current_config.autotrade_defaults.trend_hold_min_score)), "Auto Trade Trend Hold Score"),
            trend_hold_min_volume_ratio=_parse_float_value(_get_first(form, "autotrade_trend_hold_min_volume_ratio", str(current_config.autotrade_defaults.trend_hold_min_volume_ratio)), "Auto Trade Trend Hold Volume"),
            trend_hold_min_buy_pressure=_parse_float_value(_get_first(form, "autotrade_trend_hold_min_buy_pressure", str(current_config.autotrade_defaults.trend_hold_min_buy_pressure)), "Auto Trade Trend Hold Buy Pressure"),
            emergency_drawdown_pct=_parse_float_value(_get_first(form, "autotrade_emergency_drawdown_pct", str(current_config.autotrade_defaults.emergency_drawdown_pct)), "Auto Trade Emergency Drawdown"),
            cooldown_minutes=_parse_int_value(_get_first(form, "autotrade_cooldown_minutes", str(current_config.autotrade_defaults.cooldown_minutes)), "Auto Trade Cooldown"),
            order_test_only=_runtime_bool(form, "autotrade_order_test_only", current_config.autotrade_defaults.order_test_only),
        ),
        intelligence_defaults=IntelligenceDefaults(
            enabled=_runtime_bool(form, "intelligence_enabled", current_config.intelligence_defaults.enabled),
            llm_enabled=_runtime_bool(form, "intelligence_llm_enabled", current_config.intelligence_defaults.llm_enabled),
            llm_provider=llm_provider,
            llm_api_key=keep_llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            openai_api_key=keep_llm_api_key if llm_provider == "openai" else current_config.openai_api_key,
            openai_model=llm_model if llm_provider == "openai" else current_config.openai_model,
            min_intel_severity=_parse_float_value(_get_first(form, "intelligence_min_intel_severity", str(current_config.intelligence_defaults.min_intel_severity)), "Intelligence Min Severity"),
            min_spread_bps=_parse_float_value(_get_first(form, "intelligence_min_spread_bps", str(current_config.intelligence_defaults.min_spread_bps)), "Intelligence Min Spread"),
            whale_transfer_threshold_usd=_parse_float_value(_get_first(form, "intelligence_whale_transfer_threshold_usd", str(current_config.intelligence_defaults.whale_transfer_threshold_usd)), "Whale Transfer Threshold"),
        ),
        backtest_defaults=BacktestDefaults(
            preset=_get_first(form, "backtest_preset", current_config.backtest_defaults.preset).strip() or "custom",
            archives=_get_first(form, "backtest_archives", current_config.backtest_defaults.archives),
            lookback_bars=_parse_int_value(_get_first(form, "backtest_lookback_bars", str(current_config.backtest_defaults.lookback_bars)), "Lookback Bars"),
            score_threshold=_parse_float_value(_get_first(form, "backtest_score_threshold", str(current_config.backtest_defaults.score_threshold)), "Score Threshold"),
            holding_periods=_get_first(form, "backtest_holding_periods", current_config.backtest_defaults.holding_periods),
            portfolio_top_n=_parse_int_value(_get_first(form, "backtest_portfolio_top_n", str(current_config.backtest_defaults.portfolio_top_n)), "Portfolio Top N"),
            cooldown_bars=_parse_int_value(_get_first(form, "backtest_cooldown_bars", str(current_config.backtest_defaults.cooldown_bars)), "Cooldown Bars"),
            stop_loss_pct=_parse_float_value(_get_first(form, "backtest_stop_loss_pct", str(current_config.backtest_defaults.stop_loss_pct)), "Stop Loss"),
            take_profit_pct=_parse_float_value(_get_first(form, "backtest_take_profit_pct", str(current_config.backtest_defaults.take_profit_pct)), "Take Profit"),
            max_holding_bars=_parse_int_value(_get_first(form, "backtest_max_holding_bars", str(current_config.backtest_defaults.max_holding_bars)), "Max Holding Bars"),
            fee_bps=_parse_float_value(_get_first(form, "backtest_fee_bps", str(current_config.backtest_defaults.fee_bps)), "Fee bps"),
            fee_model=_get_first(form, "backtest_fee_model", current_config.backtest_defaults.fee_model),
            fee_source=_get_first(form, "backtest_fee_source", current_config.backtest_defaults.fee_source),
            maker_fee_bps=_parse_float_value(_get_first(form, "backtest_maker_fee_bps", str(current_config.backtest_defaults.maker_fee_bps)), "Maker Fee"),
            taker_fee_bps=_parse_float_value(_get_first(form, "backtest_taker_fee_bps", str(current_config.backtest_defaults.taker_fee_bps)), "Taker Fee"),
            entry_fee_role=_get_first(form, "backtest_entry_fee_role", current_config.backtest_defaults.entry_fee_role),
            exit_fee_role=_get_first(form, "backtest_exit_fee_role", current_config.backtest_defaults.exit_fee_role),
            fee_discount_pct=_parse_float_value(_get_first(form, "backtest_fee_discount_pct", str(current_config.backtest_defaults.fee_discount_pct)), "Fee Discount"),
            no_binance_discount=_runtime_bool(form, "backtest_no_binance_discount", current_config.backtest_defaults.no_binance_discount),
            slippage_bps=_parse_float_value(_get_first(form, "backtest_slippage_bps", str(current_config.backtest_defaults.slippage_bps)), "Slippage bps"),
            slippage_model=_get_first(form, "backtest_slippage_model", current_config.backtest_defaults.slippage_model),
            min_slippage_bps=_parse_float_value(_get_first(form, "backtest_min_slippage_bps", str(current_config.backtest_defaults.min_slippage_bps)), "Min Slippage"),
            max_slippage_bps=_parse_float_value(_get_first(form, "backtest_max_slippage_bps", str(current_config.backtest_defaults.max_slippage_bps)), "Max Slippage"),
            slippage_window_bars=_parse_int_value(_get_first(form, "backtest_slippage_window_bars", str(current_config.backtest_defaults.slippage_window_bars)), "Slip Window"),
            capital_fraction_pct=_parse_float_value(_get_first(form, "backtest_capital_fraction_pct", str(current_config.backtest_defaults.capital_fraction_pct)), "Capital"),
            max_portfolio_exposure_pct=_parse_float_value(_get_first(form, "backtest_max_portfolio_exposure_pct", str(current_config.backtest_defaults.max_portfolio_exposure_pct)), "Max Exposure"),
            max_concurrent_positions=_parse_int_value(_get_first(form, "backtest_max_concurrent_positions", str(current_config.backtest_defaults.max_concurrent_positions)), "Max Concurrent"),
            min_volume_ratio=_parse_float_value(_get_first(form, "backtest_min_volume_ratio", str(current_config.backtest_defaults.min_volume_ratio)), "Min Volume Ratio"),
            min_buy_pressure=_parse_float_value(_get_first(form, "backtest_min_buy_pressure", str(current_config.backtest_defaults.min_buy_pressure)), "Min Buy Pressure"),
            min_rsi=_parse_float_value(_get_first(form, "backtest_min_rsi", str(current_config.backtest_defaults.min_rsi)), "Min RSI"),
            max_rsi=_parse_float_value(_get_first(form, "backtest_max_rsi", str(current_config.backtest_defaults.max_rsi)), "Max RSI"),
            no_kdj_confirmation=_runtime_bool(form, "backtest_no_kdj_confirmation", current_config.backtest_defaults.no_kdj_confirmation),
        ),
    )
    _validate_runtime_config(config)
    return config


__all__ = [
    '_validate_runtime_config',
    '_scan_params_from_config',
    '_backtest_params_from_config',
    '_settings_params_from_config',
    '_settings_status_from_config',
    '_import_runtime_config_template',
    '_build_runtime_config',
]
