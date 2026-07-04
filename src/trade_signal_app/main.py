from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import csv
import io
import json
import os
from threading import Event, RLock, Thread
from urllib.parse import parse_qs, urlencode, urlparse

from . import __version__
from .app_state import AppState
from .backtest import (
    bars_per_day,
    group_archives,
    merge_candles,
    resolve_archive_paths,
    resolve_execution_config_from_binance,
    run_backtest_for_series,
    run_overnight_seasonality_backtest,
    run_portfolio_backtest,
    run_rebalance_premium_backtest,
)
from .binance_client import BinancePublicAPIError, parse_ticker
from .config import BASE_DIR, SETTINGS
from .data_services import LLM_PROVIDER_PRESETS, PUBLIC_DATA_PRESETS, get_llm_provider, llm_provider_ids, public_data_preset_ids
from .intelligence import IntelligenceHub, IntelligenceSnapshot, LlmInsightClient
from .okx_client import OKXSpotGateway
from .onchain import DEFAULT_ONCHAIN_SYMBOLS, OPEN_MULTICHAIN_CONFIGS, OpenMultiChainOnchainProvider
from .platform import build_platform_snapshot, okx_credential_state
from .presets import apply_backtest_preset, list_backtest_presets
from .runtime_config import AutoTradeDefaults, BacktestDefaults, IntelligenceDefaults, RuntimeConfig, ScanDefaults
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig
from .strategy_builder import compile_strategy
from .trading import AutoTrader, LIVE_CONFIRM_VALUE, TradingEvent, TradingPosition, TradingRunReport, TradingStateStore
from .tradingview_data import TRADINGVIEW_INTERVALS, fetch_tradingview_history
from .ui import format_backtest_report, format_portfolio_report, format_rebalance_premium_report, format_signal_row
from .views import normalize_language, render_backtest_page, render_index_page, render_settings_page, render_terminal_module_page, render_terminal_page, render_trading_page

RUNTIME_CONFIG_PATH = BASE_DIR / "data" / "runtime_config.json"
TRADING_STATE_PATH = BASE_DIR / "data" / "trading_state.json"
TRADINGVIEW_CACHE_DIR = BASE_DIR / "data" / "tradingview_klines"
APP_STATE = AppState(SETTINGS, RUNTIME_CONFIG_PATH)
MARKET_TICKER_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
TERMINAL_SNAPSHOT_TTL_SECONDS = 45
TERMINAL_SYNC_TIMEOUT_SECONDS = 1.2
ONCHAIN_SYNC_TIMEOUT_SECONDS = 6.0
ONCHAIN_WORKBENCH_SYNC_TIMEOUT_SECONDS = 6.0
LLM_WORKBENCH_TIMEOUT_SECONDS = 8
OKX_GATEWAY_TIMEOUT_SECONDS = 5
SCAN_SYNC_TIMEOUT_SECONDS = 0.8
TERMINAL_MODULES = {"market", "community", "onchain", "basis", "strategies", "trading", "risk"}
_TERMINAL_CACHE_LOCK = RLock()
_TERMINAL_CACHE: dict[str, object] = {"key": None, "expires_at": datetime.min.replace(tzinfo=timezone.utc), "payload": None}
_TERMINAL_INFLIGHT: dict[tuple[object, ...], Future] = {}
_TERMINAL_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="terminal-refresh")
_ONCHAIN_MODULE_CACHE_LOCK = RLock()
_ONCHAIN_MODULE_CACHE: dict[str, object] = {"key": None, "expires_at": datetime.min.replace(tzinfo=timezone.utc), "payload": None}
_ONCHAIN_INFLIGHT: dict[tuple[object, ...], Future] = {}
_ONCHAIN_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="onchain-refresh")
_SCAN_CACHE_LOCK = RLock()
_SCAN_PAYLOAD_CACHE: dict[tuple[object, ...], tuple[datetime, dict[str, object]]] = {}
_SCAN_INFLIGHT: dict[tuple[object, ...], Future] = {}
_SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan-refresh")
PAPER_AUTO_DEFAULT_INTERVAL_SECONDS = 300
PAPER_AUTO_MIN_INTERVAL_SECONDS = 30
_PAPER_AUTO_LOCK = RLock()
_PAPER_AUTO_STOP_EVENT: Event | None = None
_PAPER_AUTO_THREAD: Thread | None = None
_PAPER_AUTO_STATE: dict[str, object] = {
    "running": False,
    "interval_seconds": PAPER_AUTO_DEFAULT_INTERVAL_SECONDS,
    "started_at": None,
    "stopped_at": None,
    "last_run_at": None,
    "last_error": "",
    "run_count": 0,
    "last_result": None,
}
SCAN_INTERVALS = {"15m", "1h", "4h", "1d"}
SCAN_VIEW_MODES = {"cards", "table"}
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


def _to_jsonable(value: object) -> object:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


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


def _parse_query_int(query: dict[str, list[str]], key: str, default: object, label: str) -> int:
    return _parse_int_value(_get_first(query, key, str(default)), label)


def _parse_query_float(query: dict[str, list[str]], key: str, default: object, label: str) -> float:
    return _parse_float_value(_get_first(query, key, str(default)), label)


def _validate_choice(value: str, label: str, choices: set[str]) -> None:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{label} 只能是：{allowed}。")


def _validate_range(value: float, label: str, *, minimum: float | None = None, maximum: float | None = None) -> None:
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} 不能小于 {minimum:g}。")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} 不能大于 {maximum:g}。")


def _validate_runtime_config(config: RuntimeConfig) -> None:
    _validate_choice(config.scan_defaults.interval, "Scan Interval", SCAN_INTERVALS)
    _validate_choice(config.autotrade_defaults.mode, "Auto Trade Mode", AUTOTRADE_MODES)
    _validate_choice(config.autotrade_defaults.execution_exchange, "Auto Trade Exchange", AUTOTRADE_EXCHANGES)
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
    _validate_range(autotrade.max_open_positions, "Auto Trade Max Open Positions", minimum=1)
    _validate_range(autotrade.max_total_quote_exposure, "Auto Trade Max Exposure", minimum=0.01)
    _validate_range(autotrade.score_threshold, "Auto Trade Score Threshold", minimum=0, maximum=100)
    _validate_range(autotrade.min_volume_ratio, "Auto Trade Min Volume Ratio", minimum=0)
    _validate_range(autotrade.min_buy_pressure, "Auto Trade Min Buy Pressure", minimum=0, maximum=1)
    _validate_range(autotrade.stop_loss_pct, "Auto Trade Stop Loss", minimum=0.1)
    _validate_range(autotrade.take_profit_pct, "Auto Trade Take Profit", minimum=0.1)
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
        "autotrade_max_open_positions": autotrade.max_open_positions,
        "autotrade_max_total_quote_exposure": autotrade.max_total_quote_exposure,
        "autotrade_score_threshold": autotrade.score_threshold,
        "autotrade_min_volume_ratio": autotrade.min_volume_ratio,
        "autotrade_min_buy_pressure": autotrade.min_buy_pressure,
        "autotrade_stop_loss_pct": autotrade.stop_loss_pct,
        "autotrade_take_profit_pct": autotrade.take_profit_pct,
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


def _settings_status_from_config(config: RuntimeConfig) -> dict[str, object]:
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
        "tradingview_cache_dir": str(TRADINGVIEW_CACHE_DIR),
        "storage_mode": APP_STATE.storage_mode_label(),
        "autotrade_enabled": config.autotrade_defaults.enabled,
        "autotrade_mode": config.autotrade_defaults.mode,
        "intelligence_enabled": config.intelligence_defaults.enabled,
        "llm_enabled": config.intelligence_defaults.llm_enabled,
        "llm_provider": config.intelligence_defaults.llm_provider,
        "llm_configured": bool(config.intelligence_defaults.llm_api_key or config.intelligence_defaults.openai_api_key),
        "public_data_presets": [preset.__dict__ for preset in PUBLIC_DATA_PRESETS],
        "llm_provider_presets": [preset.__dict__ for preset in LLM_PROVIDER_PRESETS],
    }


def _settings_context() -> tuple[dict[str, object], dict[str, object]]:
    runtime_config, _ = APP_STATE.snapshot()
    return _settings_params_from_config(runtime_config), _settings_status_from_config(runtime_config)


def _health_payload() -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    okx_state = okx_credential_state(runtime_config)
    store = _trading_store()
    trading_state_status: dict[str, object] = {
        "path": str(TRADING_STATE_PATH),
        "exists": TRADING_STATE_PATH.exists(),
        "readable": True,
        "open_positions": 0,
        "events": 0,
        "error": "",
    }
    try:
        trading_state_status["open_positions"] = len(store.load())
        trading_state_status["events"] = len(store.load_events())
    except Exception as exc:  # noqa: BLE001
        trading_state_status.update({"readable": False, "error": str(exc)})

    runtime_config_status = {
        "path": str(RUNTIME_CONFIG_PATH),
        "exists": RUNTIME_CONFIG_PATH.exists(),
        "storage_mode": APP_STATE.storage_mode_label(),
    }
    autotrade = runtime_config.autotrade_defaults
    live_confirmed = os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE
    blockers = []
    if autotrade.mode == "live" and not autotrade.order_test_only:
        selected_exchange = autotrade.execution_exchange.lower()
        if selected_exchange == "okx":
            okx_state = okx_credential_state(runtime_config)
            if not okx_state["configured"]:
                blockers.append("OKX API key/secret/passphrase 未完整配置")
        elif not (runtime_config.binance_api_key and runtime_config.binance_api_secret):
            blockers.append("Binance API key/secret 未配置")
        if not live_confirmed:
            blockers.append(f"缺少环境变量 AI_TRADE_LIVE_CONFIRM={LIVE_CONFIRM_VALUE}")

    return {
        "ok": bool(trading_state_status["readable"]),
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_config": runtime_config_status,
        "trading_state": trading_state_status,
        "features": {
            "binance_public_market_data": True,
            "tradingview_unofficial_market_data": True,
            "binance_private_auth_configured": bool(runtime_config.binance_api_key and runtime_config.binance_api_secret),
            "okx_private_connector": okx_state["status"],
            "autotrade_execution_exchange": runtime_config.autotrade_defaults.execution_exchange,
            "x_auth_configured": bool(runtime_config.x_bearer_token),
            "x_provider": runtime_config.x_provider,
            "x_nitter_configured": bool(runtime_config.x_nitter_base_url),
            "x_session_scrape_configured": bool(runtime_config.x_session_command),
            "market_data_preset": runtime_config.market_data_preset,
            "onchain_data_preset": runtime_config.onchain_data_preset,
            "onchain_key_configured": bool(runtime_config.onchain_api_key),
            "llm_provider": runtime_config.intelligence_defaults.llm_provider,
            "llm_configured": bool(runtime_config.intelligence_defaults.llm_api_key or runtime_config.openai_api_key),
            "openai_configured": bool(runtime_config.openai_api_key),
        },
        "autotrade": {
            "enabled": autotrade.enabled,
            "mode": autotrade.mode,
            "order_test_only": autotrade.order_test_only,
            "live_confirmed": live_confirmed,
            "local_blockers": blockers,
        },
        "external_checks": {
            "performed": False,
            "message": "Health check is local-only. Use /api/trading/readiness and /api/platform/exchange-auth for exchange account checks.",
        },
    }


def _export_runtime_config_template(*, include_secrets: bool) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    return runtime_config.to_template_payload(include_secrets=include_secrets)


def _trading_store() -> TradingStateStore:
    return TradingStateStore(TRADING_STATE_PATH)


def _okx_gateway(runtime_config: RuntimeConfig) -> OKXSpotGateway:
    return OKXSpotGateway(
        ttl_seconds=SETTINGS.scan_ttl_seconds,
        timeout=OKX_GATEWAY_TIMEOUT_SECONDS,
        api_key=runtime_config.okx_api_key,
        api_secret=runtime_config.okx_api_secret,
        passphrase=runtime_config.okx_api_passphrase,
    )


def _execution_gateway(runtime_config: RuntimeConfig, scanner: object) -> object:
    if runtime_config.autotrade_defaults.execution_exchange.lower() == "okx":
        return _okx_gateway(runtime_config)
    return getattr(scanner, "gateway", scanner)


def _latest_prices_for_open_positions(
    positions: list[TradingPosition],
    scanner: object,
    signal_prices: dict[str, float] | None = None,
) -> dict[str, float]:
    latest_prices = {symbol.upper(): price for symbol, price in (signal_prices or {}).items() if price > 0}
    missing_symbols = {position.symbol.upper() for position in positions if position.symbol.upper() not in latest_prices}
    if not missing_symbols:
        return latest_prices

    gateway = getattr(scanner, "gateway", None)
    cached_ticker24hr = getattr(gateway, "cached_ticker24hr", None)
    if callable(cached_ticker24hr):
        try:
            cached_rows = cached_ticker24hr() or []
        except Exception:  # noqa: BLE001
            cached_rows = []
        for row in cached_rows:
            try:
                ticker = parse_ticker(row)
            except (KeyError, TypeError, ValueError):
                continue
            if ticker.symbol.upper() in missing_symbols:
                latest_prices[ticker.symbol.upper()] = ticker.last_price
        missing_symbols = {symbol for symbol in missing_symbols if symbol not in latest_prices}

    ticker24hr_symbols = getattr(gateway, "ticker24hr_symbols", None)
    if missing_symbols and callable(ticker24hr_symbols):
        try:
            for row in ticker24hr_symbols(sorted(missing_symbols)):
                symbol = str(row.get("symbol", "")).upper()
                if symbol in missing_symbols:
                    latest_prices[symbol] = float(row["lastPrice"])
        except Exception:  # noqa: BLE001
            return latest_prices
    return latest_prices


def _serialize_trading_position(position: TradingPosition, latest_price: float | None = None) -> dict[str, object]:
    current_notional = None
    unrealized_pnl = None
    unrealized_pnl_pct = None
    if latest_price is not None and latest_price > 0:
        current_notional = position.quantity * latest_price
        unrealized_pnl = current_notional - position.quote_notional
        unrealized_pnl_pct = (unrealized_pnl / position.quote_notional) * 100 if position.quote_notional else 0.0
    return {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "entry_price": position.entry_price,
        "last_price": latest_price,
        "quote_notional": position.quote_notional,
        "current_notional": current_notional,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "score": position.score,
        "grade": position.grade,
        "opened_at": position.opened_at.isoformat(),
        "stop_price": position.stop_price,
        "take_profit_price": position.take_profit_price,
        "mode": position.mode,
        "client_order_id": position.client_order_id,
        "exchange": position.exchange,
    }


def _serialize_trading_event(event: TradingEvent) -> dict[str, object]:
    return {
        "action": event.action,
        "symbol": event.symbol,
        "mode": event.mode,
        "status": event.status,
        "message": event.message,
        "exchange": event.exchange,
        "score": event.score,
        "price": event.price,
        "quantity": event.quantity,
        "quote_notional": event.quote_notional,
        "realized_pnl": event.realized_pnl,
        "realized_pnl_pct": event.realized_pnl_pct,
        "exit_reason": event.exit_reason,
        "created_at": event.created_at.isoformat(),
        "response": event.response,
    }


def _sort_trading_events_desc(events: list[TradingEvent]) -> list[TradingEvent]:
    return sorted(events, key=_event_created_at_utc, reverse=True)


def _serialize_trading_report(report: TradingRunReport, latest_prices: dict[str, float] | None = None) -> dict[str, object]:
    latest_prices = latest_prices or {}
    return {
        "enabled": report.enabled,
        "mode": report.mode,
        "scanned_symbols": report.scanned_symbols,
        "returned_signals": report.returned_signals,
        "open_positions": [
            _serialize_trading_position(position, latest_prices.get(position.symbol.upper()))
            for position in report.open_positions
        ],
        "events": [_serialize_trading_event(event) for event in _sort_trading_events_desc(report.events)],
        "generated_at": report.generated_at.isoformat(),
    }


def _trading_status_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    store = _trading_store()
    positions = store.load()
    events = _sort_trading_events_desc(store.load_events())
    latest_prices = _latest_prices_for_open_positions(positions, scanner)
    return {
        "config": _to_jsonable(runtime_config.autotrade_defaults),
        "readiness": _trading_readiness_payload(),
        "open_positions": [
            _serialize_trading_position(position, latest_prices.get(position.symbol.upper()))
            for position in positions
        ],
        "events": [_serialize_trading_event(event) for event in events[:30]],
    }


def _exchange_auth_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    binance_status = scanner.gateway.account_status({runtime_config.scan_defaults.quote_asset})
    okx_state = okx_credential_state(runtime_config)
    if bool(okx_state["configured"]):
        okx_status = _okx_gateway(runtime_config).account_status({runtime_config.scan_defaults.quote_asset})
    else:
        okx_status = {
            "exchange": "OKX",
            "configured": bool(okx_state["configured"]),
            "partial": bool(okx_state["partial"]),
            "authenticated": False,
            "can_trade": False,
            "status": okx_state["status"],
            "message": okx_state["message"],
            "missing": okx_state["missing"],
            "balances": [],
            "quote_available": 0.0,
        }
    return {
        "binance": binance_status,
        "okx": okx_status,
    }


def _local_binance_auth_status(configured: bool) -> dict[str, object]:
    return {
        "exchange": "BINANCE",
        "configured": configured,
        "authenticated": False,
        "can_trade": False,
        "status": "unchecked" if configured else "not_configured",
        "message": "Binance 账户授权未在本次本地状态检查中访问。使用 /api/platform/exchange-auth 执行真实授权检查。" if configured else "BINANCE_API_KEY / BINANCE_API_SECRET 未配置。",
        "balances": [],
        "quote_available": 0.0,
    }


def _local_okx_auth_status(runtime_config: RuntimeConfig) -> dict[str, object]:
    okx_state = okx_credential_state(runtime_config)
    return {
        "exchange": "OKX",
        "configured": bool(okx_state["configured"]),
        "partial": bool(okx_state["partial"]),
        "authenticated": False,
        "can_trade": False,
        "status": "unchecked" if okx_state["configured"] else okx_state["status"],
        "message": "OKX 账户授权未在本次本地状态检查中访问。使用 /api/platform/exchange-auth 执行真实授权检查。" if okx_state["configured"] else okx_state["message"],
        "balances": [],
        "quote_available": 0.0,
        "missing": okx_state["missing"],
    }


def _trading_readiness_payload(*, check_account: bool | None = None) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    config = runtime_config.autotrade_defaults
    selected_exchange = config.execution_exchange.lower()
    exchange_label = selected_exchange.upper()
    has_configured_credentials = (
        bool(runtime_config.binance_api_key and runtime_config.binance_api_secret)
        if selected_exchange == "binance"
        else bool(okx_credential_state(runtime_config)["configured"])
    )
    should_check_account = check_account if check_account is not None else (config.mode == "live" and not config.order_test_only)
    if should_check_account:
        exchange_status = (
            scanner.gateway.account_status({runtime_config.scan_defaults.quote_asset})
            if selected_exchange == "binance"
            else _okx_gateway(runtime_config).account_status({runtime_config.scan_defaults.quote_asset})
        )
    else:
        exchange_status = _local_binance_auth_status(has_configured_credentials) if selected_exchange == "binance" else _local_okx_auth_status(runtime_config)
    live_confirmed = os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE
    has_credentials = bool(exchange_status.get("configured"))
    authenticated = bool(exchange_status.get("authenticated"))
    can_trade = bool(exchange_status.get("can_trade"))
    quote_available = float(exchange_status.get("quote_available") or 0.0)
    live_ready = (
        config.mode == "live"
        and has_credentials
        and authenticated
        and can_trade
        and live_confirmed
        and quote_available >= config.quote_order_qty
    )
    blockers = []
    if config.mode == "live":
        if not has_credentials:
            blockers.append(f"{exchange_label} API 凭据未配置")
        if has_credentials and not authenticated:
            blockers.append(f"{exchange_label} 账户认证失败")
        if authenticated and not can_trade:
            blockers.append(f"{exchange_label} API 未开启交易权限")
        if not live_confirmed:
            blockers.append(f"缺少环境变量 AI_TRADE_LIVE_CONFIRM={LIVE_CONFIRM_VALUE}")
        if authenticated and quote_available < config.quote_order_qty:
            blockers.append(f"{runtime_config.scan_defaults.quote_asset} 可用余额不足")
    return {
        "mode": config.mode,
        "execution_exchange": selected_exchange,
        "enabled": config.enabled,
        "order_test_only": config.order_test_only,
        "live_ready": live_ready,
        "live_confirmed": live_confirmed,
        "quote_asset": runtime_config.scan_defaults.quote_asset,
        "quote_order_qty": config.quote_order_qty,
        "quote_available": quote_available,
        "account_check_performed": should_check_account,
        "exchange_status": exchange_status,
        "blockers": blockers,
    }


def _format_market_ticker_label(symbol: str, quote_asset: str) -> str:
    upper_symbol = symbol.upper()
    upper_quote = quote_asset.upper()
    if upper_quote and upper_symbol.endswith(upper_quote) and len(upper_symbol) > len(upper_quote):
        return f"{upper_symbol[:-len(upper_quote)]}/{upper_quote}"
    return upper_symbol


def _market_ticker_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    quote_asset = runtime_config.scan_defaults.quote_asset.upper()
    try:
        cached_ticker24hr = getattr(getattr(scanner, "gateway", None), "cached_ticker24hr", None)
        if not callable(cached_ticker24hr):
            return {"items": [], "error": "Ticker cache is unavailable for the current scanner.", "error_code": "cache_unavailable"}
        raw_rows = cached_ticker24hr()
        if raw_rows is None:
            ticker24hr_symbols = getattr(getattr(scanner, "gateway", None), "ticker24hr_symbols", None)
            if not callable(ticker24hr_symbols):
                return {"items": [], "error": "Ticker cache is empty. Run a market scan to load live ticker data.", "error_code": "cache_empty"}
            raw_rows = ticker24hr_symbols(list(MARKET_TICKER_SYMBOLS))
        tickers = []
        for row in raw_rows:
            try:
                ticker = parse_ticker(row)
            except (KeyError, TypeError, ValueError):
                continue
            if ticker.symbol.endswith(quote_asset):
                tickers.append(ticker)
        by_symbol = {ticker.symbol: ticker for ticker in tickers}
        selected = [by_symbol[symbol] for symbol in MARKET_TICKER_SYMBOLS if symbol in by_symbol]
        selected_symbols = {ticker.symbol for ticker in selected}
        selected.extend(
            ticker
            for ticker in sorted(tickers, key=lambda item: item.quote_volume, reverse=True)
            if ticker.symbol not in selected_symbols
        )
        items = [
            {
                "symbol": ticker.symbol,
                "label": _format_market_ticker_label(ticker.symbol, quote_asset),
                "change_pct": ticker.price_change_percent,
                "quote_volume": ticker.quote_volume,
            }
            for ticker in selected[:6]
        ]
        return {"items": items, "error": "" if items else "No ticker data for the configured quote asset.", "error_code": "" if items else "quote_empty"}
    except Exception as exc:  # noqa: BLE001
        return {"items": [], "error": str(exc), "error_code": "error"}


def _ticker_intel_rows(
    *,
    source: str,
    rows: list[dict],
    quote_asset: str,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    intel_items: list[dict[str, object]] = []
    spot_prices: dict[str, float] = {}
    for row in rows:
        try:
            ticker = parse_ticker(row)
        except (KeyError, TypeError, ValueError):
            continue
        if quote_asset and not ticker.symbol.endswith(quote_asset):
            continue
        symbol = ticker.symbol.upper()
        spot_prices[symbol] = ticker.last_price
        change_pct = ticker.price_change_percent
        quote_volume = ticker.quote_volume
        sentiment = max(-1.0, min(1.0, change_pct / 10))
        intel_items.append(
            {
                "source": source.lower(),
                "symbol": symbol,
                "title": f"{source} {symbol} 最新价 {ticker.last_price:.8g}，24h 涨跌幅 {change_pct:+.2f}%，成交额 {quote_volume:,.0f}",
                "category": "live_ticker",
                "severity": min(95.0, 42.0 + abs(change_pct) * 4 + min(quote_volume / 50_000_000, 18.0)),
                "sentiment": round(sentiment, 4),
                "url": "",
            }
        )
    return intel_items, spot_prices


def _live_binance_ticker_rows(scanner: object) -> list[dict]:
    gateway = getattr(scanner, "gateway", scanner)
    ticker24hr_symbols = getattr(gateway, "ticker24hr_symbols", None)
    if callable(ticker24hr_symbols):
        return ticker24hr_symbols(list(MARKET_TICKER_SYMBOLS))
    return []


def _live_okx_ticker_rows(runtime_config: RuntimeConfig) -> list[dict]:
    return _okx_gateway(runtime_config).ticker24hr_symbols(list(MARKET_TICKER_SYMBOLS))


def _live_funding_rows(symbols: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for symbol in symbols[:8]:
        funding = IntelligenceHub._fetch_binance_funding_rate(symbol)
        if funding is None:
            continue
        rows.append(_to_jsonable(funding))  # type: ignore[arg-type]
    return sorted(rows, key=lambda item: abs(float(item.get("funding_rate_bps", 0.0))), reverse=True)


def _live_spread_rows(
    spot_prices: dict[str, float],
    funding_rows: list[dict[str, object]],
    runtime_config: RuntimeConfig,
) -> list[dict[str, object]]:
    spreads: list[dict[str, object]] = []
    for funding in funding_rows:
        symbol = str(funding.get("symbol") or "").upper()
        spot_price = float(spot_prices.get(symbol) or 0.0)
        futures_price = float(funding.get("mark_price") or 0.0)
        if not symbol or spot_price <= 0 or futures_price <= 0:
            continue
        spread_bps = ((futures_price - spot_price) / spot_price) * 10_000
        spreads.append(
            {
                "symbol": symbol,
                "spot_exchange": "BINANCE",
                "futures_exchange": str(funding.get("futures_exchange") or "BINANCE-PERP"),
                "spot_price": round(spot_price, 8),
                "futures_price": round(futures_price, 8),
                "spread_bps": round(spread_bps, 4),
                "direction": "perp_premium" if spread_bps >= 0 else "perp_discount",
                "source": "binance_spot_futures_public",
            }
        )
    return sorted(spreads, key=lambda item: abs(float(item["spread_bps"])), reverse=True)[:10]


def _realtime_market_sections(runtime_config: RuntimeConfig, scanner: object, *, include_derivatives: bool = True) -> dict[str, object]:
    quote_asset = runtime_config.scan_defaults.quote_asset.upper()
    warnings: list[str] = []
    intel_items: list[dict[str, object]] = []
    spot_prices_by_exchange: dict[str, dict[str, float]] = {}
    source_status: list[dict[str, object]] = []

    for source, loader in (
        ("Binance", lambda: _live_binance_ticker_rows(scanner)),
        ("OKX", lambda: _live_okx_ticker_rows(runtime_config)),
    ):
        try:
            rows = loader()
        except Exception as exc:  # noqa: BLE001
            rows = []
            warnings.append(f"{source} 公开 ticker 拉取失败：{exc}")
        source_intel, source_prices = _ticker_intel_rows(source=source, rows=rows, quote_asset=quote_asset)
        intel_items.extend(source_intel)
        spot_prices_by_exchange[source.upper()] = source_prices
        source_status.append(
            {
                "source": source.lower(),
                "symbols": len(source_prices),
                "status": "live" if source_prices else "empty",
            }
        )

    symbols = list(
        dict.fromkeys(
            [
                *[symbol for symbol in MARKET_TICKER_SYMBOLS if symbol.endswith(quote_asset)],
                *spot_prices_by_exchange.get("BINANCE", {}).keys(),
                *spot_prices_by_exchange.get("OKX", {}).keys(),
            ]
        )
    )
    funding_rows: list[dict[str, object]] = []
    spread_rows: list[dict[str, object]] = []
    if include_derivatives:
        funding_rows = _live_funding_rows(symbols)
        if not funding_rows:
            csv_rows = _to_jsonable(IntelligenceHub._read_funding_csv(SETTINGS.futures_funding_csv))
            funding_rows = csv_rows if isinstance(csv_rows, list) else []
            if funding_rows:
                warnings.append("Binance futures 实时资金费率暂不可用，已降级读取本地 funding CSV。")
            else:
                warnings.append("Binance futures 实时资金费率暂不可用，且本地 funding CSV 为空。")

        spread_rows = _live_spread_rows(spot_prices_by_exchange.get("BINANCE", {}), funding_rows, runtime_config)
        if not spread_rows:
            csv_spreads = _to_jsonable(_read_filtered_spreads(runtime_config))
            spread_rows = csv_spreads if isinstance(csv_spreads, list) else []
            if spread_rows:
                warnings.append("实时现货/合约价差暂未形成，已降级读取本地 basis CSV。")
            else:
                warnings.append("实时现货/合约价差暂未形成，且本地 basis CSV 为空。")

    return {
        "intel_items": sorted(intel_items, key=lambda item: float(item.get("severity", 0.0)), reverse=True)[:16],
        "spreads": spread_rows[:10],
        "funding_rates": funding_rows[:12],
        "market_sources": source_status,
        "warning": "；".join(warnings),
    }


def _event_created_at_utc(event: TradingEvent) -> datetime:
    created_at = event.created_at
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def _alert_count_payload(readiness: dict[str, object] | None = None) -> int:
    readiness = readiness or _trading_readiness_payload()
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    count = len(blockers)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for event in _sort_trading_events_desc(_trading_store().load_events())[:30]:
        if event.status in {"blocked", "risk_blocked", "rejected", "auth_failed"} and _event_created_at_utc(event) >= cutoff:
            count += 1
    return count


def _layout_context(readiness: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "market_ticker": _market_ticker_payload(),
        "alert_count": _alert_count_payload(readiness),
    }


def _run_forced_paper_trading_once() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    config = replace(
        runtime_config.autotrade_defaults,
        enabled=True,
        mode="paper",
        order_test_only=True,
    )
    query = {
        "quote_asset": [runtime_config.scan_defaults.quote_asset],
        "interval": [runtime_config.scan_defaults.interval],
        "candidate_pool": [str(runtime_config.scan_defaults.candidate_pool)],
        "min_quote_volume": [str(runtime_config.scan_defaults.min_quote_volume)],
        "min_trade_count": [str(runtime_config.scan_defaults.min_trade_count)],
    }
    scan_payload, _ = _scan_payload(query)
    signals = [item for item in scan_payload.get("signals", []) if isinstance(item, dict)]
    positions = _trading_store().load()
    events: list[TradingEvent] = []
    now = datetime.now(timezone.utc)
    open_symbols = {position.symbol for position in positions}
    exposure = sum(position.quote_notional for position in positions)
    blocked_symbols = {}
    risk_payload = _fast_risk_module_payload().get("execution_risk", {})
    if isinstance(risk_payload, dict) and isinstance(risk_payload.get("blocked_symbols"), dict):
        blocked_symbols = risk_payload["blocked_symbols"]

    for signal in signals:
        symbol = str(signal.get("symbol") or "").upper()
        score = float(signal.get("score") or 0.0)
        price = float(signal.get("last_price") or 0.0)
        if not symbol or price <= 0:
            continue
        if len(positions) >= config.max_open_positions:
            break
        if exposure + config.quote_order_qty > config.max_total_quote_exposure:
            break
        if symbol in open_symbols:
            continue
        if symbol in blocked_symbols:
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol=symbol,
                    mode="paper",
                    status="risk_blocked",
                    message=str(blocked_symbols[symbol]),
                    score=score,
                    price=price,
                    exchange=config.execution_exchange.upper(),
                )
            )
            continue
        if score < config.score_threshold:
            continue
        quantity = config.quote_order_qty / price
        position = TradingPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            quote_notional=config.quote_order_qty,
            score=score,
            grade=str(signal.get("grade") or "B"),
            opened_at=now,
            stop_price=price * (1 - config.stop_loss_pct / 100),
            take_profit_price=price * (1 + config.take_profit_pct / 100),
            mode="paper",
            client_order_id=f"aitrade-paper-{symbol.lower()}-{int(now.timestamp())}",
            exchange=config.execution_exchange.upper(),
        )
        event = TradingEvent(
            action="BUY",
            symbol=symbol,
            mode="paper",
            status="paper_filled",
            message="模拟买入已记录。",
            score=score,
            price=price,
            quantity=quantity,
            quote_notional=config.quote_order_qty,
            exchange=config.execution_exchange.upper(),
        )
        positions.append(position)
        events.append(event)
        open_symbols.add(symbol)
        exposure += config.quote_order_qty

    if not events:
        events.append(
            TradingEvent(
                action="SKIP",
                symbol="*",
                mode="paper",
                status="no_signal",
                message="暂无满足模拟交易阈值的候选信号，已完成快速扫描。",
                exchange=config.execution_exchange.upper(),
            )
        )
    store = _trading_store()
    store.save(positions)
    store.append_events(events)
    signal_prices = {
        str(signal.get("symbol", "")).upper(): float(signal.get("last_price") or 0.0)
        for signal in signals
        if str(signal.get("symbol", "")).strip()
    }
    latest_prices = _latest_prices_for_open_positions(positions, scanner, signal_prices)
    return _serialize_trading_report(
        TradingRunReport(
            enabled=True,
            mode="paper",
            scanned_symbols=int(scan_payload.get("summary", {}).get("scanned_symbols", 0)) if isinstance(scan_payload.get("summary"), dict) else 0,
            returned_signals=int(scan_payload.get("summary", {}).get("returned_signals", len(signals))) if isinstance(scan_payload.get("summary"), dict) else len(signals),
            open_positions=positions,
            events=events,
        ),
        latest_prices=latest_prices,
    )


def _run_trading_once(*, force_paper: bool = False) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    autotrade_config = runtime_config.autotrade_defaults
    if force_paper:
        return _run_forced_paper_trading_once()
    elif autotrade_config.enabled and autotrade_config.mode == "live" and not autotrade_config.order_test_only:
        readiness = _trading_readiness_payload()
        if not readiness["live_ready"]:
            positions = _trading_store().load()
            event = TradingEvent(
                action="SKIP",
                symbol="*",
                mode="live",
                status="blocked",
                message="实盘自动交易未就绪：" + "；".join(str(item) for item in readiness["blockers"]),
                exchange=autotrade_config.execution_exchange.upper(),
            )
            _trading_store().append_events([event])
            latest_prices = _latest_prices_for_open_positions(positions, scanner)
            return _serialize_trading_report(
                TradingRunReport(
                    enabled=autotrade_config.enabled,
                    mode=autotrade_config.mode,
                    scanned_symbols=0,
                    returned_signals=0,
                    open_positions=positions,
                    events=[event],
                ),
                latest_prices=latest_prices,
            )
    risk_snapshot = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS).snapshot()
    blocked_symbols = risk_snapshot.execution_risk.blocked_symbols
    trader = AutoTrader(scanner=scanner, state_store=_trading_store(), blocked_symbols=blocked_symbols)
    trader.set_execution_gateway(_execution_gateway(runtime_config, scanner))
    report = trader.run_once(autotrade_config)
    latest_prices = _latest_prices_for_open_positions(report.open_positions, scanner)
    return _serialize_trading_report(report, latest_prices=latest_prices)


def _paper_auto_status_payload() -> dict[str, object]:
    with _PAPER_AUTO_LOCK:
        thread_alive = _PAPER_AUTO_THREAD.is_alive() if _PAPER_AUTO_THREAD is not None else False
        payload = dict(_PAPER_AUTO_STATE)
        payload["running"] = bool(payload.get("running")) and thread_alive
        result = payload.get("last_result")
        if isinstance(result, dict):
            payload["last_result"] = _to_jsonable(result)
        return _to_jsonable(payload)


def _paper_auto_worker(stop_event: Event, interval_seconds: int) -> None:
    while not stop_event.is_set():
        try:
            result = _run_trading_once(force_paper=True)
            with _PAPER_AUTO_LOCK:
                _PAPER_AUTO_STATE.update(
                    {
                        "running": True,
                        "interval_seconds": interval_seconds,
                        "last_run_at": datetime.now(timezone.utc).isoformat(),
                        "last_error": "",
                        "run_count": int(_PAPER_AUTO_STATE.get("run_count") or 0) + 1,
                        "last_result": result,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            with _PAPER_AUTO_LOCK:
                _PAPER_AUTO_STATE.update(
                    {
                        "last_run_at": datetime.now(timezone.utc).isoformat(),
                        "last_error": str(exc),
                    }
                )
        if stop_event.wait(interval_seconds):
            break
    with _PAPER_AUTO_LOCK:
        if _PAPER_AUTO_STOP_EVENT is stop_event:
            _PAPER_AUTO_STATE.update(
                {
                    "running": False,
                    "stopped_at": datetime.now(timezone.utc).isoformat(),
                }
            )


def _start_paper_auto_trading(interval_seconds: int = PAPER_AUTO_DEFAULT_INTERVAL_SECONDS) -> dict[str, object]:
    interval_seconds = max(PAPER_AUTO_MIN_INTERVAL_SECONDS, int(interval_seconds))
    global _PAPER_AUTO_STOP_EVENT, _PAPER_AUTO_THREAD
    with _PAPER_AUTO_LOCK:
        if _PAPER_AUTO_THREAD is not None and _PAPER_AUTO_THREAD.is_alive():
            _PAPER_AUTO_STATE["interval_seconds"] = interval_seconds
            return _paper_auto_status_payload()
        stop_event = Event()
        _PAPER_AUTO_STOP_EVENT = stop_event
        _PAPER_AUTO_STATE.update(
            {
                "running": True,
                "interval_seconds": interval_seconds,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "stopped_at": None,
                "last_error": "",
            }
        )
        _PAPER_AUTO_THREAD = Thread(
            target=_paper_auto_worker,
            args=(stop_event, interval_seconds),
            name="paper-auto-trading",
            daemon=True,
        )
        _PAPER_AUTO_THREAD.start()
        return _paper_auto_status_payload()


def _stop_paper_auto_trading() -> dict[str, object]:
    with _PAPER_AUTO_LOCK:
        stop_event = _PAPER_AUTO_STOP_EVENT
        thread = _PAPER_AUTO_THREAD
        if stop_event is not None:
            stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)
    with _PAPER_AUTO_LOCK:
        if _PAPER_AUTO_THREAD is not None and not _PAPER_AUTO_THREAD.is_alive():
            _PAPER_AUTO_STATE.update(
                {
                    "running": False,
                    "stopped_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return _paper_auto_status_payload()


def _serialize_intelligence_snapshot(snapshot: IntelligenceSnapshot) -> dict[str, object]:
    return _to_jsonable(snapshot)


def _platform_payload() -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    store = _trading_store()
    snapshot = build_platform_snapshot(
        config=runtime_config,
        positions=store.load(),
        events=store.load_events(),
    )
    return _to_jsonable(snapshot)


def _terminal_cache_key(runtime_config: RuntimeConfig) -> tuple[object, ...]:
    scan = runtime_config.scan_defaults
    intelligence = runtime_config.intelligence_defaults
    autotrade = runtime_config.autotrade_defaults
    return (
        scan.quote_asset,
        scan.interval,
        scan.candidate_pool,
        scan.min_quote_volume,
        scan.min_trade_count,
        intelligence.enabled,
        intelligence.min_intel_severity,
        intelligence.min_spread_bps,
        intelligence.whale_transfer_threshold_usd,
        runtime_config.onchain_data_preset,
        runtime_config.x_account_mode,
        runtime_config.x_account_weight_pct,
        tuple(runtime_config.x_tracked_accounts),
        autotrade.enabled,
        autotrade.score_threshold,
    )


def _cached_terminal_payload() -> dict[str, object] | None:
    runtime_config, _ = APP_STATE.snapshot()
    cache_key = _terminal_cache_key(runtime_config)
    now = datetime.now(timezone.utc)
    with _TERMINAL_CACHE_LOCK:
        cached_payload = _TERMINAL_CACHE.get("payload")
        cached_expires_at = _TERMINAL_CACHE.get("expires_at")
        if (
            _TERMINAL_CACHE.get("key") == cache_key
            and isinstance(cached_payload, dict)
            and isinstance(cached_expires_at, datetime)
            and cached_expires_at > now
        ):
            return cached_payload
    return None


def _store_terminal_payload(cache_key: tuple[object, ...], payload: dict[str, object]) -> None:
    with _TERMINAL_CACHE_LOCK:
        _TERMINAL_CACHE.update(
            {
                "key": cache_key,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=TERMINAL_SNAPSHOT_TTL_SECONDS),
                "payload": payload,
            }
        )


def _build_terminal_payload_for_cache(cache_key: tuple[object, ...]) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    if _terminal_cache_key(runtime_config) != cache_key:
        raise RuntimeError("runtime_config_changed")
    hub = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS, use_live_funding=True)
    payload = {
        **_serialize_intelligence_snapshot(hub.snapshot()),
        "platform": _platform_payload(),
    }
    if isinstance(payload.get("onchain_events"), list):
        payload["onchain_events"] = _annotate_onchain_event_sources(payload["onchain_events"])  # type: ignore[arg-type]
    payload["onchain_sources"] = _onchain_source_rows(
        payload.get("onchain_events", []) if isinstance(payload.get("onchain_events"), list) else [],
        preset=runtime_config.onchain_data_preset,
    )
    llm_payload = payload.get("llm_insight") if isinstance(payload.get("llm_insight"), dict) else {}
    local_llm = _llm_local_analysis_payload(
        intel_items=[item for item in payload.get("intel_items", []) if isinstance(item, dict)] if isinstance(payload.get("intel_items"), list) else [],
        onchain_events=[item for item in payload.get("onchain_events", []) if isinstance(item, dict)] if isinstance(payload.get("onchain_events"), list) else [],
        spreads=[item for item in payload.get("spreads", []) if isinstance(item, dict)] if isinstance(payload.get("spreads"), list) else [],
        funding_rates=[item for item in payload.get("funding_rates", []) if isinstance(item, dict)] if isinstance(payload.get("funding_rates"), list) else [],
        strategy_hits=[item for item in payload.get("strategy_hits", []) if isinstance(item, dict)] if isinstance(payload.get("strategy_hits"), list) else [],
        execution_risk=payload.get("execution_risk") if isinstance(payload.get("execution_risk"), dict) else {},
    )
    payload["llm_insight"] = {
        "provider": llm_payload.get("provider", "local"),
        "model": llm_payload.get("model", "rules"),
        "status": llm_payload.get("status", "local_rules"),
        "analysis_mode": "llm" if llm_payload.get("status") == "ok" and llm_payload.get("provider") != "local" else "local_rules",
        **local_llm,
        "summary": llm_payload.get("summary") or local_llm["summary"],
    }
    _store_terminal_payload(cache_key, payload)
    _store_onchain_module_payload(
        _onchain_module_cache_key(runtime_config),
        {
            "module": "onchain",
            "onchain_events": payload.get("onchain_events", []),
            "onchain_sources": _onchain_source_rows(
                payload.get("onchain_events", []) if isinstance(payload.get("onchain_events"), list) else [],
                preset=runtime_config.onchain_data_preset,
            ),
            "blocked_symbols": (payload.get("execution_risk") or {}).get("blocked_symbols", {})
            if isinstance(payload.get("execution_risk"), dict)
            else {},
            "fallback": False,
            "warning": "",
        },
    )
    return payload


def _terminal_payload() -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    cached_payload = _cached_terminal_payload()
    if cached_payload is not None:
        return cached_payload
    cache_key = _terminal_cache_key(runtime_config)
    with _TERMINAL_CACHE_LOCK:
        cached_payload = _cached_terminal_payload()
        if cached_payload is not None:
            return cached_payload
        future = _TERMINAL_INFLIGHT.get(cache_key)
        if future is None or future.done():
            future = _TERMINAL_EXECUTOR.submit(_build_terminal_payload_for_cache, cache_key)
            _TERMINAL_INFLIGHT[cache_key] = future
    try:
        return future.result(timeout=TERMINAL_SYNC_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        payload = _fast_terminal_payload()
        payload["fallback"] = True
        payload["warning"] = "完整终端快照仍在后台刷新，当前先返回轻量快照以避免页面卡顿。"
        return payload
    except Exception as exc:  # noqa: BLE001
        with _TERMINAL_CACHE_LOCK:
            if _TERMINAL_INFLIGHT.get(cache_key) is future:
                _TERMINAL_INFLIGHT.pop(cache_key, None)
        payload = _fast_terminal_payload()
        payload["fallback"] = True
        payload["warning"] = f"完整终端快照刷新失败，当前返回轻量快照：{exc}"
        return payload


def _read_filtered_spreads(runtime_config: RuntimeConfig) -> list[object]:
    return [
        item
        for item in sorted(IntelligenceHub._read_spread_csv(SETTINGS.futures_basis_csv), key=lambda candidate: abs(candidate.spread_bps), reverse=True)
        if abs(item.spread_bps) >= runtime_config.intelligence_defaults.min_spread_bps
    ][:10]


def _fast_market_module_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    sections = _realtime_market_sections(runtime_config, scanner)
    return {
        "module": "market",
        "intel_items": sections["intel_items"],
        "spreads": sections["spreads"],
        "funding_rates": sections["funding_rates"],
        "market_sources": sections["market_sources"],
        "strategy_hits": [],
        "cached": False,
        "warning": sections.get("warning", ""),
    }


def _dedupe_intel_items(items: list[dict[str, object]], limit: int = 16) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(items, key=lambda candidate: _float_from_mapping(candidate, "severity"), reverse=True):
        key = (
            str(item.get("source") or "").lower(),
            str(item.get("symbol") or "").upper(),
            str(item.get("title") or "").strip().lower(),
        )
        if not key[1] or not key[2] or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _community_signal_intel_rows(scanner: object, symbols: list[str]) -> tuple[list[dict[str, object]], str]:
    provider = getattr(scanner, "community_provider", None)
    if provider is None:
        return [], "社区 provider 未接入 scanner。"
    unique_symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
    if not unique_symbols:
        return [], "社区情报缺少候选标的。"
    try:
        prepare = getattr(provider, "prepare", None)
        if callable(prepare):
            prepare(unique_symbols)
    except Exception as exc:  # noqa: BLE001
        return [], f"社区 provider 拉取失败：{exc}"

    rows: list[dict[str, object]] = []
    get_signal = getattr(provider, "get", None)
    if not callable(get_signal):
        return [], "社区 provider 不支持读取信号。"
    for symbol in unique_symbols[:16]:
        try:
            signal = get_signal(symbol)
        except Exception:  # noqa: BLE001
            continue
        if signal is None:
            continue
        mentions = "" if signal.mentions is None else f"，提及 {signal.mentions}"
        sentiment = "" if signal.sentiment is None else f"，情绪 {signal.sentiment:+.2f}"
        title = signal.summary or f"{symbol} 社区热度 {signal.score:.1f}{mentions}{sentiment}"
        rows.append(
            {
                "source": signal.source,
                "symbol": symbol,
                "title": title,
                "category": "community_heat",
                "severity": round(float(signal.score), 2),
                "sentiment": 0.0 if signal.sentiment is None else round(float(signal.sentiment), 4),
                "url": "",
            }
        )
    return rows, ""


def _community_only_module_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    hub = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS)
    sections = _realtime_market_sections(runtime_config, scanner, include_derivatives=False)
    live_items = [item for item in sections.get("intel_items", []) if isinstance(item, dict)]
    csv_items = _to_jsonable(IntelligenceHub._read_exchange_intel_csv(SETTINGS.exchange_intel_csv))
    csv_rows = [item for item in csv_items if isinstance(item, dict)] if isinstance(csv_items, list) else []
    symbols = [
        str(item.get("symbol") or "").upper()
        for item in [*live_items, *csv_rows]
        if isinstance(item, dict) and str(item.get("symbol") or "").strip()
    ]
    community_rows, community_warning = _community_signal_intel_rows(scanner, symbols or list(MARKET_TICKER_SYMBOLS))
    threshold = runtime_config.intelligence_defaults.min_intel_severity
    items = _dedupe_intel_items(
        [
            *community_rows,
            *live_items,
            *csv_rows,
        ],
        limit=16,
    )
    filtered_items = [item for item in items if _float_from_mapping(item, "severity") >= min(threshold, 45.0)]
    warning_parts = [str(sections.get("warning") or ""), community_warning]
    return {
        "module": "community",
        "twitter_accounts": _to_jsonable(hub._build_twitter_accounts()),
        "intel_items": filtered_items[:16],
        "market_sources": sections.get("market_sources", []),
        "cached": False,
        "warning": "；".join(part for part in warning_parts if part),
    }


def _basis_only_module_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    sections = _realtime_market_sections(runtime_config, scanner)
    return {
        "module": "basis",
        "spreads": sections["spreads"],
        "funding_rates": sections["funding_rates"],
        "risk_rules": _platform_payload()["risk_rules"],
        "market_sources": sections["market_sources"],
        "warning": sections.get("warning", ""),
    }


def _default_scan_params(runtime_config: RuntimeConfig) -> dict[str, object]:
    scan_defaults = runtime_config.scan_defaults
    return {
        "quote_asset": scan_defaults.quote_asset.upper(),
        "interval": scan_defaults.interval,
        "candidate_pool": scan_defaults.candidate_pool,
        "min_quote_volume": int(scan_defaults.min_quote_volume),
        "min_trade_count": scan_defaults.min_trade_count,
        "view_mode": "table",
        "community_provider": runtime_config.community_provider,
        "x_provider": runtime_config.x_provider,
        "x_account_mode": runtime_config.x_account_mode,
    }


def _float_from_mapping(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _strategy_reason_context(
    *,
    funding: dict[str, object] | None,
    spread: dict[str, object] | None,
) -> tuple[float | None, float | None, list[str]]:
    reasons: list[str] = []
    funding_bps: float | None = None
    spread_bps: float | None = None
    if funding:
        funding_bps = _float_from_mapping(funding, "funding_rate_bps")
        annualized = _float_from_mapping(funding, "annualized_pct")
        reasons.append(f"资金费率 {funding_bps:+.2f}bps/8h，年化 {annualized:+.1f}%")
    if spread:
        spread_bps = _float_from_mapping(spread, "spread_bps")
        reasons.append(f"现货/合约价差 {spread_bps:+.2f}bps")
    return funding_bps, spread_bps, reasons


def _strategy_hit_row(
    *,
    signal: dict[str, object],
    strategy: str,
    score: float,
    grade: str,
    action: str,
    reasons: list[str],
    funding_bps: float | None,
    spread_bps: float | None,
    source: str,
) -> dict[str, object]:
    return {
        "symbol": str(signal.get("symbol") or "").upper(),
        "strategy": strategy,
        "score": round(score, 2),
        "grade": grade,
        "action": action,
        "price_change_percent": round(_float_from_mapping(signal, "price_change_percent"), 2),
        "funding_rate_bps": funding_bps,
        "spread_bps": spread_bps,
        "source": source,
        "reasons": reasons[:5],
    }


def _strategy_hits_from_signal_rows(
    signals: list[dict[str, object]],
    *,
    funding_rates: list[dict[str, object]],
    spreads: list[dict[str, object]],
    runtime_config: RuntimeConfig,
    source: str,
) -> list[dict[str, object]]:
    threshold = runtime_config.autotrade_defaults.score_threshold
    funding_by_symbol = {str(item.get("symbol") or "").upper(): item for item in funding_rates}
    spread_by_symbol = {str(item.get("symbol") or "").upper(): item for item in spreads}
    hits: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add_hit(hit: dict[str, object]) -> None:
        key = (str(hit.get("symbol") or ""), str(hit.get("strategy") or ""))
        if not key[0] or key in seen:
            return
        seen.add(key)
        hits.append(hit)

    for signal in signals:
        symbol = str(signal.get("symbol") or "").upper()
        if not symbol:
            continue
        score = _float_from_mapping(signal, "score")
        grade = str(signal.get("grade") or ("A" if score >= 80 else "B" if score >= 65 else "C"))
        base_reasons = [str(reason) for reason in signal.get("reasons", []) if str(reason).strip()] if isinstance(signal.get("reasons"), list) else []
        funding = funding_by_symbol.get(symbol)
        spread = spread_by_symbol.get(symbol)
        funding_bps, spread_bps, context_reasons = _strategy_reason_context(funding=funding, spread=spread)
        reasons = [*base_reasons[:3], *context_reasons]
        change_pct = _float_from_mapping(signal, "price_change_percent")
        volume_ratio = _float_from_mapping(signal, "volume_ratio", 1.0)
        rsi = _float_from_mapping(signal, "rsi_14", 50.0)
        ema_spread = _float_from_mapping(signal, "ema_spread_pct")
        funding_rate = _float_from_mapping(funding or {}, "funding_rate")

        if score >= threshold:
            add_hit(
                _strategy_hit_row(
                    signal=signal,
                    strategy="auto_score_breakout",
                    score=score,
                    grade=grade,
                    action="candidate_buy" if runtime_config.autotrade_defaults.enabled else "watch",
                    reasons=reasons or ["综合评分达到自动交易阈值"],
                    funding_bps=funding_bps,
                    spread_bps=spread_bps,
                    source=source,
                )
            )
        elif score >= 60 or abs(change_pct) >= 1.5:
            add_hit(
                _strategy_hit_row(
                    signal=signal,
                    strategy="market_momentum_watch",
                    score=max(score, min(74.0, 58.0 + abs(change_pct) * 2)),
                    grade=grade,
                    action="watch",
                    reasons=reasons or ["实时行情进入观察池", f"24h 涨跌幅 {change_pct:+.2f}%"],
                    funding_bps=funding_bps,
                    spread_bps=spread_bps,
                    source=source,
                )
            )
        if volume_ratio >= 1.5:
            add_hit(
                _strategy_hit_row(
                    signal=signal,
                    strategy="volume_pressure",
                    score=min(100.0, score + min(volume_ratio * 2, 10.0)),
                    grade=grade,
                    action="priority_watch",
                    reasons=["量能放大", *reasons[:4]],
                    funding_bps=funding_bps,
                    spread_bps=spread_bps,
                    source=source,
                )
            )
        if funding_rate >= 0.00025 and (change_pct >= 8 or rsi >= 72 or ema_spread >= 10):
            add_hit(
                _strategy_hit_row(
                    signal=signal,
                    strategy="blowoff_distribution_short",
                    score=min(100.0, max(score, 72.0) + funding_rate * 100_000),
                    grade=grade,
                    action="short_watch",
                    reasons=["多头拥挤/末端分布候选", f"24h 涨跌幅 {change_pct:+.2f}%", *context_reasons],
                    funding_bps=funding_bps,
                    spread_bps=spread_bps,
                    source=source,
                )
            )
        if funding_rate <= -0.00015 and change_pct <= -5:
            add_hit(
                _strategy_hit_row(
                    signal=signal,
                    strategy="capitulation_rebound_long",
                    score=min(100.0, max(score, 68.0) + abs(funding_rate) * 100_000),
                    grade=grade,
                    action="rebound_long_watch",
                    reasons=["空头拥挤反弹候选", f"24h 涨跌幅 {change_pct:+.2f}%", *context_reasons],
                    funding_bps=funding_bps,
                    spread_bps=spread_bps,
                    source=source,
                )
            )
    return sorted(hits, key=lambda item: float(item.get("score") or 0.0), reverse=True)[:12]


def _strategy_hits_payload(
    runtime_config: RuntimeConfig,
    scanner: object,
    *,
    market_sections: dict[str, object] | None = None,
) -> dict[str, object]:
    params = _default_scan_params(runtime_config)
    cached_scan = _cached_scan_payload(_scan_cache_key(params))
    source = "scan_cache"
    if cached_scan is None:
        cached_scan = _fallback_scan_payload(params, "工作台策略命中使用实时 ticker 快速候选；完整扫描会在信号扫描页或后台缓存完成后替换。")
        source = "live_ticker"
    signals = [item for item in cached_scan.get("signals", []) if isinstance(item, dict)]
    sections = market_sections or _realtime_market_sections(runtime_config, scanner)
    funding_rates = [item for item in sections.get("funding_rates", []) if isinstance(item, dict)]
    spreads = [item for item in sections.get("spreads", []) if isinstance(item, dict)]
    warning_parts = [str(cached_scan.get("warning") or ""), str(sections.get("warning") or "")]
    return {
        "module": "strategies",
        "strategy_hits": _strategy_hits_from_signal_rows(
            signals,
            funding_rates=funding_rates,
            spreads=spreads,
            runtime_config=runtime_config,
            source=source,
        ),
        "cached": bool(cached_scan.get("cached")),
        "source": source,
        "warning": "；".join(part for part in warning_parts if part),
    }


def _fast_strategies_module_payload(market_payload: dict[str, object] | None = None) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    platform = _platform_payload()
    cached = _cached_terminal_payload()
    strategies_payload = _strategy_hits_payload(runtime_config, scanner, market_sections=market_payload)
    strategy_hits = cached["strategy_hits"] if cached is not None and cached.get("strategy_hits") else strategies_payload["strategy_hits"]
    return {
        "module": "strategies",
        "strategy_hits": strategy_hits,
        "strategies": platform["strategies"],
        "cached": cached is not None or strategies_payload["cached"],
        "warning": "" if cached is not None and cached.get("strategy_hits") else str(strategies_payload.get("warning") or ""),
    }


def _risk_factor_row(
    *,
    source: str,
    symbol: str,
    factor: str,
    value: object,
    severity: float,
    decision: str,
    reason: str,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "factor": factor,
        "value": value,
        "severity": round(severity, 2),
        "decision": decision,
        "reason": reason,
    }


def _fast_execution_risk_decision(
    *,
    runtime_config: RuntimeConfig,
    strategy_hits: list[dict[str, object]],
    onchain_events: list[dict[str, object]],
    spreads: list[dict[str, object]],
    funding_rates: list[dict[str, object]],
) -> dict[str, object]:
    blocked: dict[str, str] = {}
    factors: list[dict[str, object]] = []
    spread_block_threshold = max(runtime_config.intelligence_defaults.min_spread_bps * 4, 80.0)

    for event in onchain_events:
        symbol = str(event.get("symbol") or "").upper()
        direction = str(event.get("direction") or "").lower()
        severity = _float_from_mapping(event, "severity")
        amount_usd = _float_from_mapping(event, "amount_usd")
        blocks = bool(symbol and severity >= 85 and ("inflow" in direction or "deposit" in direction))
        reason = f"链上事件 {event.get('event_type') or 'event'}，严重度 {severity:.1f}"
        if blocks:
            blocked[symbol] = f"链上高严重度交易所流入：{severity:.0f}"
        factors.append(
            _risk_factor_row(
                source="onchain",
                symbol=symbol or "*",
                factor=str(event.get("event_type") or "onchain_event"),
                value=round(amount_usd, 2),
                severity=severity,
                decision="block" if blocks else "monitor",
                reason=reason,
            )
        )

    for spread in spreads:
        symbol = str(spread.get("symbol") or "").upper()
        spread_bps = _float_from_mapping(spread, "spread_bps")
        severity = min(100.0, abs(spread_bps) * 0.8)
        blocks = bool(symbol and abs(spread_bps) >= spread_block_threshold)
        if blocks:
            blocked.setdefault(symbol, f"现货/合约价差异常：{spread_bps:+.1f}bps")
        factors.append(
            _risk_factor_row(
                source="basis",
                symbol=symbol or "*",
                factor="spot_futures_basis",
                value=f"{spread_bps:+.2f}bps",
                severity=severity,
                decision="block" if blocks else "pass",
                reason=f"阻断阈值 {spread_block_threshold:.1f}bps",
            )
        )

    for funding in funding_rates:
        symbol = str(funding.get("symbol") or "").upper()
        funding_rate = _float_from_mapping(funding, "funding_rate")
        funding_bps = _float_from_mapping(funding, "funding_rate_bps")
        severity = min(100.0, abs(funding_bps) * 8)
        blocks = bool(symbol and funding_rate >= 0.001)
        if blocks:
            blocked.setdefault(symbol, f"合约资金费率过热：{funding_bps:+.2f}bps/8h")
        factors.append(
            _risk_factor_row(
                source="funding",
                symbol=symbol or "*",
                factor="funding_rate",
                value=f"{funding_bps:+.2f}bps",
                severity=severity,
                decision="block" if blocks else "pass",
                reason="正费率过热阈值 +10.00bps/8h",
            )
        )

    hit_symbols: list[str] = []
    for hit in strategy_hits:
        symbol = str(hit.get("symbol") or "").upper()
        if symbol and symbol not in hit_symbols:
            hit_symbols.append(symbol)
            score = _float_from_mapping(hit, "score")
            factors.append(
                _risk_factor_row(
                    source="strategy",
                    symbol=symbol,
                    factor=str(hit.get("strategy") or "strategy_hit"),
                    value=round(score, 2),
                    severity=max(0.0, min(100.0, 100.0 - score)),
                    decision="allow" if symbol not in blocked else "blocked_by_risk",
                    reason="策略候选进入执行前风控",
                )
            )

    allowed = [symbol for symbol in hit_symbols if symbol not in blocked]
    risk_score = min(
        100.0,
        max(
            [float(factor["severity"]) for factor in factors]
            + [len(blocked) * 25.0, 0.0]
        ),
    )
    status = "blocked" if blocked and not allowed else "caution" if blocked or risk_score >= 70 else "clear"
    summary = (
        f"执行前风控：基于 {len(strategy_hits)} 个策略候选、{len(onchain_events)} 条链上事件、"
        f"{len(spreads)} 条价差和 {len(funding_rates)} 条资金费率，允许 {len(allowed)} 个候选，"
        f"阻断 {len(blocked)} 个标的，风险分 {risk_score:.1f}。"
    )
    return {
        "status": status,
        "risk_score": round(risk_score, 2),
        "allowed_symbols": allowed,
        "blocked_symbols": blocked,
        "risk_factors": sorted(factors, key=lambda item: float(item.get("severity") or 0.0), reverse=True)[:16],
        "summary": summary,
    }


def _fast_risk_module_payload(
    *,
    market_payload: dict[str, object] | None = None,
    strategies_payload: dict[str, object] | None = None,
    onchain_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    platform = _platform_payload()
    cached = _cached_terminal_payload()
    if cached is not None:
        return {
            "module": "risk",
            "execution_risk": cached["execution_risk"],
            "risk_rules": platform["risk_rules"],
            "cached": True,
        }
    market_payload = market_payload or _fast_market_module_payload()
    strategies_payload = strategies_payload or _fast_strategies_module_payload(market_payload=market_payload)
    onchain_payload = onchain_payload or _cached_onchain_module_payload() or {
        "onchain_events": _local_onchain_events_payload(),
    }
    strategy_hits = [item for item in strategies_payload.get("strategy_hits", []) if isinstance(item, dict)]
    spreads = [item for item in market_payload.get("spreads", []) if isinstance(item, dict)]
    funding_rates = [item for item in market_payload.get("funding_rates", []) if isinstance(item, dict)]
    onchain_events = [item for item in onchain_payload.get("onchain_events", []) if isinstance(item, dict)]
    warning_parts = [
        str(strategies_payload.get("warning") or ""),
        str(market_payload.get("warning") or ""),
        str(onchain_payload.get("warning") or ""),
    ]
    return {
        "module": "risk",
        "execution_risk": _fast_execution_risk_decision(
            runtime_config=runtime_config,
            strategy_hits=strategy_hits,
            onchain_events=onchain_events,
            spreads=spreads,
            funding_rates=funding_rates,
        ),
        "risk_rules": platform["risk_rules"],
        "cached": False,
        "warning": "；".join(part for part in warning_parts if part),
    }


def _compact_reason_text(value: object, fallback: str = "") -> str:
    if isinstance(value, list):
        return "；".join(str(item) for item in value[:3] if str(item).strip()) or fallback
    text = str(value or "").strip()
    return text or fallback


def _llm_local_analysis_payload(
    *,
    intel_items: list[dict[str, object]],
    onchain_events: list[dict[str, object]],
    spreads: list[dict[str, object]],
    funding_rates: list[dict[str, object]],
    strategy_hits: list[dict[str, object]],
    execution_risk: dict[str, object],
) -> dict[str, object]:
    risk_score = _float_from_mapping(execution_risk, "risk_score")
    blocked_symbols = dict(execution_risk.get("blocked_symbols") or {}) if isinstance(execution_risk.get("blocked_symbols"), dict) else {}
    allowed_symbols = [str(item).upper() for item in execution_risk.get("allowed_symbols", [])] if isinstance(execution_risk.get("allowed_symbols"), list) else []
    high_onchain = sorted(onchain_events, key=lambda item: _float_from_mapping(item, "severity"), reverse=True)
    hot_spreads = sorted(spreads, key=lambda item: abs(_float_from_mapping(item, "spread_bps")), reverse=True)
    hot_funding = sorted(funding_rates, key=lambda item: abs(_float_from_mapping(item, "funding_rate_bps")), reverse=True)
    sorted_hits = sorted(strategy_hits, key=lambda item: _float_from_mapping(item, "score"), reverse=True)

    if blocked_symbols or risk_score >= 80:
        market_state = "风控优先：存在阻断标的或高风险因子，自动交易应只保留低敞口观察。"
    elif sorted_hits and allowed_symbols:
        market_state = "机会可执行：策略命中已通过当前执行前风控，可按 paper 模式优先验证。"
    elif sorted_hits:
        market_state = "机会观察：已有策略命中，但仍需等待执行前风控或更多数据确认。"
    elif intel_items or onchain_events or hot_spreads or hot_funding:
        market_state = "数据监控中：市场、社区、链上或衍生品因子已有输入，暂未形成明确执行候选。"
    else:
        market_state = "等待扫描：当前快照缺少足够的行情、情报和策略命中数据。"

    opportunities: list[dict[str, object]] = []
    for hit in sorted_hits[:4]:
        symbol = str(hit.get("symbol") or "").upper()
        if not symbol:
            continue
        opportunities.append(
            {
                "symbol": symbol,
                "action": hit.get("action") or "watch",
                "score": round(_float_from_mapping(hit, "score"), 2),
                "source": hit.get("strategy") or "strategy_hit",
                "reason": _compact_reason_text(hit.get("reasons"), "策略评分进入候选池。"),
            }
        )
    if not opportunities:
        for item in sorted(intel_items, key=lambda candidate: _float_from_mapping(candidate, "severity"), reverse=True)[:3]:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            opportunities.append(
                {
                    "symbol": symbol,
                    "action": "watch",
                    "score": round(_float_from_mapping(item, "severity"), 2),
                    "source": item.get("source") or "market_intel",
                    "reason": str(item.get("title") or "交易所/社区情报进入观察池。"),
                }
            )

    risks: list[dict[str, object]] = []
    for symbol, reason in list(blocked_symbols.items())[:4]:
        risks.append({"symbol": str(symbol).upper(), "level": "block", "source": "risk_gate", "reason": str(reason)})
    for event in high_onchain[:3]:
        severity = _float_from_mapping(event, "severity")
        if severity < 60:
            continue
        risks.append(
            {
                "symbol": str(event.get("symbol") or "*").upper(),
                "level": "high" if severity >= 85 else "monitor",
                "source": event.get("source") or event.get("chain") or "onchain",
                "reason": f"{event.get('event_type') or 'onchain_event'}，{event.get('direction') or 'unknown'}，严重度 {severity:.1f}",
            }
        )
    for spread in hot_spreads[:2]:
        spread_bps = _float_from_mapping(spread, "spread_bps")
        if abs(spread_bps) < 30:
            continue
        risks.append(
            {
                "symbol": str(spread.get("symbol") or "*").upper(),
                "level": "monitor",
                "source": "basis",
                "reason": f"现货/合约价差 {spread_bps:+.2f}bps，需防止回归或流动性偏移。",
            }
        )
    for funding in hot_funding[:2]:
        funding_bps = _float_from_mapping(funding, "funding_rate_bps")
        if abs(funding_bps) < 2:
            continue
        risks.append(
            {
                "symbol": str(funding.get("symbol") or "*").upper(),
                "level": "monitor",
                "source": "funding",
                "reason": f"资金费率 {funding_bps:+.2f}bps/8h，检查多空拥挤度。",
            }
        )

    actions: list[dict[str, object]] = []
    if blocked_symbols:
        actions.append({"priority": "high", "action": "暂停阻断标的自动开仓", "reason": "执行前风控已给出阻断原因。"})
    if allowed_symbols:
        actions.append({"priority": "medium", "action": "用 paper 模式执行允许候选", "reason": f"当前允许候选：{', '.join(allowed_symbols[:6])}。"})
    if sorted_hits and not allowed_symbols:
        actions.append({"priority": "medium", "action": "等待风控确认后再执行", "reason": "策略命中存在，但当前未形成允许候选。"})
    if not sorted_hits:
        actions.append({"priority": "low", "action": "运行信号扫描或降低候选阈值", "reason": "当前没有策略命中，建议先补齐扫描缓存。"})
    if not onchain_events:
        actions.append({"priority": "low", "action": "刷新链上公开数据源", "reason": "链上风险因子为空时，交易前确认度会降低。"})

    metrics = {
        "intel_items": len(intel_items),
        "onchain_events": len(onchain_events),
        "spreads": len(spreads),
        "funding_rates": len(funding_rates),
        "strategy_hits": len(strategy_hits),
        "risk_score": round(risk_score, 2),
        "allowed": len(allowed_symbols),
        "blocked": len(blocked_symbols),
    }
    summary = (
        f"{market_state} 本轮快照包含策略命中 {metrics['strategy_hits']} 个、链上异动 {metrics['onchain_events']} 条、"
        f"价差 {metrics['spreads']} 条、资金费率 {metrics['funding_rates']} 条，执行前风险分 {risk_score:.1f}。"
    )
    return {
        "market_state": market_state,
        "summary": summary,
        "opportunities": opportunities[:4],
        "risks": risks[:6],
        "actions": actions[:5],
        "metrics": metrics,
    }


def _fast_llm_insight_payload(
    *,
    runtime_config: RuntimeConfig,
    intel_items: list[dict[str, object]],
    onchain_events: list[dict[str, object]],
    spreads: list[dict[str, object]],
    funding_rates: list[dict[str, object]],
    strategy_hits: list[dict[str, object]],
    execution_risk: dict[str, object],
) -> dict[str, object]:
    local_payload = _llm_local_analysis_payload(
        intel_items=intel_items,
        onchain_events=onchain_events,
        spreads=spreads,
        funding_rates=funding_rates,
        strategy_hits=strategy_hits,
        execution_risk=execution_risk,
    )
    defaults = runtime_config.intelligence_defaults
    provider = defaults.llm_provider or runtime_config.llm_provider or "openai"
    api_key = defaults.llm_api_key or defaults.openai_api_key or runtime_config.llm_api_key or runtime_config.openai_api_key
    model = defaults.llm_model or runtime_config.llm_model or runtime_config.openai_model
    base_url = defaults.llm_base_url or runtime_config.llm_base_url
    if defaults.llm_enabled and api_key:
        prompt_payload = {
            "metrics": local_payload["metrics"],
            "market_state": local_payload["market_state"],
            "opportunities": local_payload["opportunities"],
            "risks": local_payload["risks"],
            "actions": local_payload["actions"],
            "intel_items": intel_items[:6],
            "onchain_events": onchain_events[:6],
            "spreads": spreads[:6],
            "funding_rates": funding_rates[:6],
            "strategy_hits": strategy_hits[:6],
            "execution_risk": execution_risk,
        }
        try:
            summary = LlmInsightClient(
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout=LLM_WORKBENCH_TIMEOUT_SECONDS,
            ).analyze(prompt_payload)
            if summary:
                return {
                    "provider": provider,
                    "model": model,
                    "status": "ok",
                    "analysis_mode": "llm",
                    **local_payload,
                    "summary": summary,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "provider": provider,
                "model": model,
                "status": "fallback",
                "analysis_mode": "local_rules",
                **local_payload,
                "summary": f"大模型接口暂不可用，已使用本地规则完成分析：{exc}。{local_payload['summary']}",
            }
    return {
        "provider": "local",
        "model": "rules",
        "status": "local_rules",
        "analysis_mode": "local_rules",
        **local_payload,
    }


def _cached_onchain_module_payload() -> dict[str, object] | None:
    now = datetime.now(timezone.utc)
    with _ONCHAIN_MODULE_CACHE_LOCK:
        cached_payload = _ONCHAIN_MODULE_CACHE.get("payload")
        cached_expires_at = _ONCHAIN_MODULE_CACHE.get("expires_at")
        if isinstance(cached_payload, dict) and isinstance(cached_expires_at, datetime) and cached_expires_at > now:
            return cached_payload
    return None


def _onchain_module_cache_key(runtime_config: RuntimeConfig) -> tuple[object, ...]:
    return (
        runtime_config.onchain_data_preset,
        runtime_config.onchain_api_base_url,
        runtime_config.intelligence_defaults.whale_transfer_threshold_usd,
    )


def _store_onchain_module_payload(cache_key: tuple[object, ...], payload: dict[str, object]) -> None:
    with _ONCHAIN_MODULE_CACHE_LOCK:
        _ONCHAIN_MODULE_CACHE.update(
            {
                "key": cache_key,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=TERMINAL_SNAPSHOT_TTL_SECONDS),
                "payload": payload,
            }
        )


def _local_onchain_events_payload() -> list[object]:
    runtime_config, _ = APP_STATE.snapshot()
    threshold = runtime_config.intelligence_defaults.whale_transfer_threshold_usd
    events = IntelligenceHub._read_onchain_csv(SETTINGS.onchain_events_csv)
    return _to_jsonable(
        [
            event
            for event in sorted(events, key=lambda candidate: candidate.severity, reverse=True)
            if event.amount_usd >= threshold or event.severity >= 45
        ][:10]
    )


def _local_onchain_module_payload(warning: str = "") -> dict[str, object]:
    return {
        "module": "onchain",
        "onchain_events": _local_onchain_events_payload(),
        "onchain_sources": [
            {
                "chain": "local_csv",
                "symbol": "*",
                "source": str(SETTINGS.onchain_events_csv),
                "status": "fallback" if warning else "local_csv",
            }
        ],
        "blocked_symbols": {},
        "fallback": bool(warning),
        "warning": warning,
    }


def _onchain_fallback_module_payload(warning: str, runtime_config: RuntimeConfig | None = None) -> dict[str, object]:
    runtime_config = runtime_config or APP_STATE.snapshot()[0]
    payload = _local_onchain_module_payload(warning)
    if runtime_config.onchain_data_preset != "local_csv":
        events = payload.get("onchain_events", [])
        payload["onchain_sources"] = _onchain_source_rows(events if isinstance(events, list) else [], preset=runtime_config.onchain_data_preset)
    return payload


def _onchain_price_map(scanner: object) -> dict[str, float]:
    rows: list[dict] = []
    try:
        rows.extend(_live_binance_ticker_rows(scanner))
    except Exception:  # noqa: BLE001
        pass
    price_map: dict[str, float] = {}
    for row in rows:
        try:
            ticker = parse_ticker(row)
        except (KeyError, TypeError, ValueError):
            continue
        if ticker.symbol.upper() in DEFAULT_ONCHAIN_SYMBOLS and ticker.last_price > 0:
            price_map[ticker.symbol.upper()] = ticker.last_price
    return price_map


def _onchain_source_rows(events: list[dict[str, object]], *, preset: str) -> list[dict[str, object]]:
    live_chains = {str(event.get("chain") or "") for event in events}
    return [
        {
            "chain": config.chain,
            "symbol": config.symbol,
            "source": config.source,
            "status": "api_live" if config.chain in live_chains else ("api_configured" if preset != "local_csv" else "local_csv"),
        }
        for config in OPEN_MULTICHAIN_CONFIGS
    ]


def _annotate_onchain_event_sources(events: list[object]) -> list[dict[str, object]]:
    source_by_chain = {config.chain: config.source for config in OPEN_MULTICHAIN_CONFIGS}
    annotated: list[dict[str, object]] = []
    for event in events:
        row = _to_jsonable(event)
        if not isinstance(row, dict):
            continue
        chain = str(row.get("chain") or "")
        row.setdefault("source", source_by_chain.get(chain, "local_csv"))
        annotated.append(row)
    return annotated


def _onchain_module_payload_with_timeout(timeout_seconds: float) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    cache_key = _onchain_module_cache_key(runtime_config)
    now = datetime.now(timezone.utc)
    with _ONCHAIN_MODULE_CACHE_LOCK:
        cached_payload = _ONCHAIN_MODULE_CACHE.get("payload")
        cached_expires_at = _ONCHAIN_MODULE_CACHE.get("expires_at")
        if (
            _ONCHAIN_MODULE_CACHE.get("key") == cache_key
            and isinstance(cached_payload, dict)
            and isinstance(cached_expires_at, datetime)
            and cached_expires_at > now
        ):
            return cached_payload
        future = _ONCHAIN_INFLIGHT.get(cache_key)
        if future is None or future.done():
            future = _ONCHAIN_EXECUTOR.submit(_build_onchain_module_payload_for_cache, cache_key)
            _ONCHAIN_INFLIGHT[cache_key] = future
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        return _onchain_fallback_module_payload("链上开放数据源仍在后台刷新，当前先返回本地链上事件缓存以避免页面卡顿。", runtime_config)
    except Exception as exc:  # noqa: BLE001
        with _ONCHAIN_MODULE_CACHE_LOCK:
            if _ONCHAIN_INFLIGHT.get(cache_key) is future:
                _ONCHAIN_INFLIGHT.pop(cache_key, None)
        return _onchain_fallback_module_payload(f"链上开放数据源刷新失败，当前返回本地链上事件缓存：{exc}", runtime_config)


def _fast_terminal_payload(
    *,
    market_payload: dict[str, object] | None = None,
    basis_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    cached = _cached_terminal_payload()
    if cached is not None and market_payload is None and basis_payload is None:
        return cached
    platform = _platform_payload()
    market = market_payload or _fast_market_module_payload()
    community = _community_only_module_payload()
    onchain = _cached_onchain_module_payload() or _onchain_module_payload_with_timeout(ONCHAIN_WORKBENCH_SYNC_TIMEOUT_SECONDS)
    basis = basis_payload or {
        "spreads": market.get("spreads", []),
        "funding_rates": market.get("funding_rates", []),
    }
    strategies = _fast_strategies_module_payload(market_payload=market)
    risk = _fast_risk_module_payload(
        market_payload=market,
        strategies_payload=strategies,
        onchain_payload=onchain,
    )["execution_risk"]
    intel_items = [item for item in market.get("intel_items", []) if isinstance(item, dict)]
    onchain_events = [item for item in onchain.get("onchain_events", []) if isinstance(item, dict)]
    spreads = [item for item in basis.get("spreads", []) if isinstance(item, dict)]
    funding_rates = [item for item in basis.get("funding_rates", []) if isinstance(item, dict)]
    strategy_hits = [item for item in strategies.get("strategy_hits", []) if isinstance(item, dict)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned_symbols": 0,
        "returned_signals": 0,
        "intel_items": intel_items,
        "twitter_accounts": community["twitter_accounts"],
        "onchain_events": onchain_events,
        "onchain_sources": onchain.get("onchain_sources", []),
        "spreads": spreads,
        "funding_rates": funding_rates,
        "market_sources": market.get("market_sources", []),
        "strategy_hits": strategy_hits,
        "llm_insight": _fast_llm_insight_payload(
            runtime_config=APP_STATE.snapshot()[0],
            intel_items=intel_items,
            onchain_events=onchain_events,
            spreads=spreads,
            funding_rates=funding_rates,
            strategy_hits=strategy_hits,
            execution_risk=risk,
        ),
        "execution_risk": risk,
        "platform": platform,
        "cached": False,
        "warning": "快速页面快照：避免浏览器首屏阻塞，完整扫描结果会通过缓存刷新。",
    }


def _build_onchain_module_payload_for_cache(cache_key: tuple[object, ...]) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    if _onchain_module_cache_key(runtime_config) != cache_key:
        raise RuntimeError("runtime_config_changed")
    threshold = runtime_config.intelligence_defaults.whale_transfer_threshold_usd
    warnings: list[str] = []
    events: list[object] = []
    if runtime_config.onchain_data_preset != "local_csv":
        price_map = _onchain_price_map(scanner)
        try:
            events.extend(
                _to_jsonable(item)
                for item in OpenMultiChainOnchainProvider(
                    whale_threshold_usd=threshold,
                    base_url_override=runtime_config.onchain_api_base_url,
                ).fetch_events(list(DEFAULT_ONCHAIN_SYMBOLS), price_map)
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"链上公开接口拉取失败：{exc}")
        if not price_map:
            warnings.append("实时价格映射暂不可用，链上大额转账 USD 估算会降级为网络快照。")
    if runtime_config.onchain_data_preset == "local_csv" or not events:
        local_events = IntelligenceHub._read_onchain_csv(SETTINGS.onchain_events_csv)
        if local_events:
            events.extend(local_events)
            if runtime_config.onchain_data_preset != "local_csv":
                warnings.append("链上接口结果为空，已降级读取本地 onchain CSV。")
    serializable_events = [
        event
        for event in _annotate_onchain_event_sources(
            [
                event
                for event in sorted(events, key=lambda candidate: float(candidate["severity"] if isinstance(candidate, dict) else candidate.severity), reverse=True)
                if (
                    float(event["amount_usd"] if isinstance(event, dict) else event.amount_usd) >= threshold
                    or float(event["severity"] if isinstance(event, dict) else event.severity) >= 45
                )
            ][:10]
        )
    ]
    if not serializable_events and runtime_config.onchain_data_preset != "local_csv":
        warnings.append("链上公开接口未返回可展示事件；请稍后刷新或检查网络访问。")
    payload = {
        "module": "onchain",
        "onchain_events": serializable_events,
        "onchain_sources": _onchain_source_rows(serializable_events, preset=runtime_config.onchain_data_preset),
        "blocked_symbols": {},
        "fallback": False,
        "warning": "；".join(warnings),
    }
    _store_onchain_module_payload(cache_key, payload)
    return payload


def _onchain_only_module_payload(error: str = "") -> dict[str, object]:
    if error:
        return _onchain_fallback_module_payload(error)
    return _onchain_module_payload_with_timeout(ONCHAIN_SYNC_TIMEOUT_SECONDS)


def _terminal_module_payload(module: str) -> dict[str, object]:
    if module == "market":
        return _fast_market_module_payload()
    if module == "community":
        return _community_only_module_payload()
    if module == "onchain":
        return _onchain_only_module_payload()
    if module == "basis":
        return _basis_only_module_payload()
    if module == "trading":
        platform = _platform_payload()
        return {
            "module": module,
            "trading": _trading_status_payload(),
            "accounts": platform["accounts"],
            "recent_events": platform["recent_events"],
        }
    if module == "strategies":
        return _fast_strategies_module_payload()
    if module == "risk":
        return _fast_risk_module_payload()
    try:
        snapshot = _terminal_payload()
    except Exception as exc:  # noqa: BLE001
        if module == "onchain":
            return _onchain_only_module_payload(str(exc))
        raise
    platform = snapshot["platform"]
    risk = snapshot["execution_risk"]
    if module == "market":
        return {
            "module": module,
            "intel_items": snapshot["intel_items"],
            "spreads": snapshot["spreads"],
            "funding_rates": snapshot.get("funding_rates", []),
            "strategy_hits": snapshot["strategy_hits"],
        }
    if module == "community":
        return {
            "module": module,
            "twitter_accounts": snapshot["twitter_accounts"],
            "intel_items": snapshot["intel_items"],
        }
    if module == "onchain":
        return {
            "module": module,
            "onchain_events": snapshot["onchain_events"],
            "blocked_symbols": risk["blocked_symbols"],
        }
    if module == "strategies":
        return {
            "module": module,
            "strategy_hits": snapshot["strategy_hits"],
            "strategies": platform["strategies"],
        }
    if module == "risk":
        return {
            "module": module,
            "execution_risk": risk,
            "risk_rules": platform["risk_rules"],
        }
    raise ValueError("未知总控台模块。")


def _terminal_page_snapshot(module: str) -> dict[str, object]:
    module_payload = _terminal_module_payload(module) if module in TERMINAL_MODULES else {}
    snapshot = _fast_terminal_payload(
        market_payload=module_payload if module == "market" else None,
        basis_payload=module_payload if module == "basis" else None,
    )
    if module in TERMINAL_MODULES:
        snapshot.update(module_payload)
    return snapshot


def _terminal_api_module_from_path(path: str) -> str | None:
    module = ""
    if path.startswith("/api/terminal/modules/"):
        module = path.removeprefix("/api/terminal/modules/").strip("/")
    elif path.startswith("/api/terminal/"):
        module = path.removeprefix("/api/terminal/").strip("/")
    return module if module in TERMINAL_MODULES else None


def _compile_strategy_payload(description: str) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    compiled = compile_strategy(description, runtime_config)
    payload = _to_jsonable(compiled)
    payload["run_urls"] = {
        "backtest": _compiled_strategy_backtest_url(payload["backtest_defaults"]),
        "paper_trading": "/terminal/trading",
        "settings": "/settings",
    }
    return payload


def _compiled_strategy_backtest_url(defaults: object) -> str:
    if not isinstance(defaults, dict):
        return "/backtest"
    allowed_keys = (
        "preset",
        "archives",
        "lookback_bars",
        "score_threshold",
        "holding_periods",
        "portfolio_top_n",
        "cooldown_bars",
        "stop_loss_pct",
        "take_profit_pct",
        "max_holding_bars",
        "fee_bps",
        "fee_model",
        "fee_source",
        "maker_fee_bps",
        "taker_fee_bps",
        "entry_fee_role",
        "exit_fee_role",
        "fee_discount_pct",
        "no_binance_discount",
        "slippage_bps",
        "slippage_model",
        "min_slippage_bps",
        "max_slippage_bps",
        "slippage_window_bars",
        "capital_fraction_pct",
        "max_portfolio_exposure_pct",
        "max_concurrent_positions",
        "min_volume_ratio",
        "min_buy_pressure",
        "min_rsi",
        "max_rsi",
        "no_kdj_confirmation",
    )
    query: dict[str, str] = {}
    for key in allowed_keys:
        if key not in defaults:
            continue
        value = defaults[key]
        if isinstance(value, bool):
            query[key] = "1" if value else "0"
        else:
            query[key] = str(value)
    return f"/backtest?{urlencode(query)}" if query else "/backtest"


def _read_body(handler: BaseHTTPRequestHandler) -> str:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return ""
    return handler.rfile.read(length).decode("utf-8")


def _strategy_description_from_body(handler: BaseHTTPRequestHandler) -> tuple[str, dict[str, list[str]]]:
    raw = _read_body(handler)
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 请求体无效。") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON 请求体根节点必须是对象。")
        description = str(payload.get("description") or payload.get("strategy_description") or "")
        lang = str(payload.get("lang") or "")
        form = {"strategy_description": [description]}
        if lang:
            form["lang"] = [lang]
        return description.strip(), form
    form = parse_qs(raw)
    description = _get_first(form, "strategy_description", _get_first(form, "description", ""))
    return description.strip(), form


def _import_runtime_config_template(form: dict[str, list[str]]) -> RuntimeConfig:
    raw_template = _get_first(form, "config_template", "").strip()
    if not raw_template:
        raise ValueError("请先粘贴配置模板 JSON。")

    try:
        payload = json.loads(raw_template)
    except json.JSONDecodeError as exc:
        raise ValueError("配置模板不是合法 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("配置模板根节点必须是 JSON 对象。")

    current_config, _ = APP_STATE.snapshot()
    config = RuntimeConfig.from_template_payload(payload, SETTINGS, current_config=current_config)
    _validate_runtime_config(config)
    return config


def _scan_cache_key(params: dict[str, object]) -> tuple[object, ...]:
    return (
        params["quote_asset"],
        params["interval"],
        params["candidate_pool"],
        params["min_quote_volume"],
        params["min_trade_count"],
        params.get("community_provider", ""),
        params.get("x_provider", ""),
        params.get("x_account_mode", ""),
    )


def _cached_scan_payload(cache_key: tuple[object, ...]) -> dict[str, object] | None:
    now = datetime.now(timezone.utc)
    with _SCAN_CACHE_LOCK:
        cached = _SCAN_PAYLOAD_CACHE.get(cache_key)
        if cached and cached[0] > now:
            payload = dict(cached[1])
            payload["cached"] = True
            return payload
    return None


def _store_scan_payload(cache_key: tuple[object, ...], payload: dict[str, object]) -> None:
    with _SCAN_CACHE_LOCK:
        _SCAN_PAYLOAD_CACHE[cache_key] = (
            datetime.now(timezone.utc) + timedelta(seconds=SETTINGS.scan_ttl_seconds),
            dict(payload),
        )


def _annotate_scan_summary(payload: dict[str, object]) -> dict[str, object]:
    summary = payload.get("summary")
    if isinstance(summary, dict):
        summary["fallback"] = bool(payload.get("fallback"))
        warning = str(payload.get("warning") or "")
        if warning:
            summary["warning"] = warning
    return payload


def _run_scan_payload(scanner: object, params: dict[str, object]) -> dict[str, object]:
    try:
        summary, signals = scanner.scan(
            quote_asset=str(params["quote_asset"]),
            interval=str(params["interval"]),
            candidate_pool=int(params["candidate_pool"]),
            min_quote_volume=float(params["min_quote_volume"]),
            min_trade_count=int(params["min_trade_count"]),
        )
    except TypeError:
        summary, signals = scanner.scan()
    return {
        "summary": _to_jsonable(summary),
        "signals": [_format_scan_signal_row(signal) for signal in signals],
        "cached": False,
        "fallback": False,
    }


def _format_scan_signal_row(signal: object) -> dict[str, object]:
    try:
        return format_signal_row(signal)  # type: ignore[arg-type]
    except AttributeError:
        ticker = getattr(signal, "ticker", object())
        indicators = getattr(signal, "indicators", object())
        return {
            "symbol": getattr(signal, "symbol", ""),
            "score": float(getattr(signal, "score", 0.0) or 0.0),
            "grade": getattr(signal, "grade", "C"),
            "reasons": list(getattr(signal, "reasons", []) or []),
            "warnings": list(getattr(signal, "warnings", []) or []),
            "last_price": float(getattr(ticker, "last_price", 0.0) or 0.0),
            "quote_volume_m": float(getattr(ticker, "quote_volume", 0.0) or 0.0) / 1_000_000,
            "price_change_percent": float(getattr(ticker, "price_change_percent", 0.0) or 0.0),
            "rsi_14": float(getattr(indicators, "rsi_14", 50.0) or 50.0),
            "ema_spread_pct": float(getattr(indicators, "ema_spread_pct", 0.0) or 0.0),
            "volume_ratio": float(getattr(indicators, "volume_ratio", 1.0) or 1.0),
            "macd_hist": float(getattr(indicators, "macd_hist", 0.0) or 0.0),
            "community_score": None,
            "community_source": None,
            "community_mentions": None,
            "community_sentiment": None,
            "community_sample_size": None,
            "community_summary": "",
            "community_drivers": [],
            "community_risks": [],
            "community_samples": [],
            "breakdown": {
                "trend": 50.0,
                "momentum": 50.0,
                "timing": 50.0,
                "volume": 50.0,
                "liquidity": 50.0,
                "market": 50.0,
                "community": 0.0,
            },
            "sparkline_points": "",
        }


def _complete_scan_future(cache_key: tuple[object, ...], future: Future) -> None:
    try:
        payload = future.result()
    except Exception:  # noqa: BLE001
        payload = None
    with _SCAN_CACHE_LOCK:
        _SCAN_INFLIGHT.pop(cache_key, None)
    if isinstance(payload, dict):
        _store_scan_payload(cache_key, _annotate_scan_summary(payload))


def _fallback_scan_payload(params: dict[str, object], warning: str) -> dict[str, object]:
    _, scanner = APP_STATE.snapshot()
    quote_asset = str(params["quote_asset"]).upper()
    ticker_rows = []
    ticker24hr_symbols = getattr(getattr(scanner, "gateway", None), "ticker24hr_symbols", None)
    if callable(ticker24hr_symbols):
        try:
            ticker_rows = ticker24hr_symbols([symbol for symbol in MARKET_TICKER_SYMBOLS if symbol.endswith(quote_asset)])
        except Exception:  # noqa: BLE001
            ticker_rows = []
    tickers = []
    for row in ticker_rows:
        try:
            ticker = parse_ticker(row)
        except (KeyError, TypeError, ValueError):
            continue
        if ticker.quote_volume >= float(params["min_quote_volume"]) and ticker.trade_count >= int(params["min_trade_count"]):
            tickers.append(ticker)
    tickers.sort(key=lambda item: item.quote_volume, reverse=True)
    selected_tickers = tickers[: int(params["candidate_pool"])]
    signals = []
    for ticker in selected_tickers:
        score = min(82.0, 50.0 + abs(ticker.price_change_percent) * 3 + min(ticker.quote_volume / 1_000_000_000, 10.0))
        signals.append(
            {
                "symbol": ticker.symbol,
                "score": round(score, 2),
                "grade": "B" if score >= 70 else "C",
                "reasons": ["实时 ticker 快速返回", f"24h 成交额 {ticker.quote_volume / 1_000_000:.1f}M"],
                "warnings": [warning],
                "last_price": ticker.last_price,
                "quote_volume_m": ticker.quote_volume / 1_000_000,
                "price_change_percent": ticker.price_change_percent,
                "rsi_14": 50.0,
                "ema_spread_pct": 0.0,
                "volume_ratio": 1.0,
                "macd_hist": 0.0,
                "community_score": None,
                "community_source": None,
                "community_mentions": None,
                "community_sentiment": None,
                "community_sample_size": None,
                "community_summary": "",
                "community_drivers": [],
                "community_risks": [],
                "community_samples": [],
                "breakdown": {
                    "trend": 50.0,
                    "momentum": 50.0,
                    "timing": 50.0,
                    "volume": 50.0,
                    "liquidity": min(100.0, ticker.quote_volume / 10_000_000),
                    "market": 50.0,
                    "community": 0.0,
                },
                "sparkline_points": "",
            }
        )
    return {
        "summary": {
            "quote_asset": quote_asset,
            "interval": str(params["interval"]),
            "scanned_symbols": len(selected_tickers),
            "returned_signals": len(signals),
            "min_quote_volume": float(params["min_quote_volume"]),
            "min_trade_count": int(params["min_trade_count"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "eligible_symbols": len(tickers),
            "candidate_symbols": len(selected_tickers),
            "candidate_pool": int(params["candidate_pool"]),
        },
        "signals": signals,
        "cached": False,
        "fallback": True,
        "warning": warning,
    }


def _scan_payload(query: dict[str, list[str]]) -> tuple[dict[str, object], dict[str, object]]:
    runtime_config, scanner = APP_STATE.snapshot()
    scan_defaults = runtime_config.scan_defaults
    quote_asset = query.get("quote_asset", [scan_defaults.quote_asset])[0].upper()
    interval = query.get("interval", [scan_defaults.interval])[0]
    view_mode = _get_first(query, "view_mode", "cards")
    _validate_choice(interval, "Scan Interval", SCAN_INTERVALS)
    _validate_choice(view_mode, "Scan View Mode", SCAN_VIEW_MODES)
    candidate_pool = _parse_query_int(query, "candidate_pool", scan_defaults.candidate_pool, "Candidate Pool")
    min_quote_volume = _parse_query_float(query, "min_quote_volume", scan_defaults.min_quote_volume, "Min Quote Volume")
    min_trade_count = _parse_query_int(query, "min_trade_count", scan_defaults.min_trade_count, "Min Trade Count")
    _validate_range(candidate_pool, "Candidate Pool", minimum=5, maximum=40)
    _validate_range(min_quote_volume, "Min Quote Volume", minimum=0)
    _validate_range(min_trade_count, "Min Trade Count", minimum=0)

    params = {
        "quote_asset": quote_asset,
        "interval": interval,
        "candidate_pool": candidate_pool,
        "min_quote_volume": int(min_quote_volume),
        "min_trade_count": min_trade_count,
        "view_mode": view_mode,
        "community_provider": runtime_config.community_provider,
        "x_provider": runtime_config.x_provider,
        "x_account_mode": runtime_config.x_account_mode,
        "x_provider_configured": (
            bool(runtime_config.x_bearer_token)
            if runtime_config.x_provider == "official_api"
            else bool(runtime_config.x_nitter_base_url)
            if runtime_config.x_provider == "nitter_rss"
            else bool(runtime_config.x_session_command)
        ),
        "community_local_configured": any(
            path.exists()
            for path in (
                SETTINGS.community_csv,
                SETTINGS.community_news_csv,
                SETTINGS.community_telegram_csv,
            )
        ),
        "exchange_community_configured": bool(SETTINGS.exchange_community_urls),
        "tracked_account_count": len(runtime_config.x_tracked_accounts),
    }
    cache_key = _scan_cache_key(params)
    cached_payload = _cached_scan_payload(cache_key)
    if cached_payload is not None:
        return cached_payload, params
    with _SCAN_CACHE_LOCK:
        future = _SCAN_INFLIGHT.get(cache_key)
        if future is None:
            future = _SCAN_EXECUTOR.submit(_run_scan_payload, scanner, dict(params))
            _SCAN_INFLIGHT[cache_key] = future
            future.add_done_callback(lambda completed, key=cache_key: _complete_scan_future(key, completed))
    try:
        payload = future.result(timeout=SCAN_SYNC_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        payload = _fallback_scan_payload(params, f"完整扫描超过 {SCAN_SYNC_TIMEOUT_SECONDS} 秒，已返回实时 ticker 快速结果，后台继续刷新。")
    payload = _annotate_scan_summary(payload)
    _store_scan_payload(cache_key, payload)
    return payload, params


def _get_first(query: dict[str, list[str]], key: str, default: str) -> str:
    return query.get(key, [default])[0]


def _parse_bool_flag(query: dict[str, list[str]], key: str) -> bool:
    return key in query and any(str(value).strip() not in {"", "0", "false", "False", "off"} for value in query.get(key, []))


def _runtime_bool(form: dict[str, list[str]], key: str, current: bool) -> bool:
    if key not in form:
        return current
    return _parse_bool_flag(form, key)


def _path_with_lang(path: str, lang: str, **params: object) -> str:
    query_params = {key: value for key, value in params.items() if value is not None}
    if normalize_language(lang) == "en":
        query_params["lang"] = "en"
    if not query_params:
        return path
    return f"{path}?{urlencode(query_params)}"


def _split_archives(value: str) -> list[str]:
    items = []
    for raw in value.replace(",", "\n").splitlines():
        item = raw.strip()
        if item:
            items.append(item)
    return items


def _tradingview_fetch_result(form: dict[str, list[str]]) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    symbol = _get_first(
        form,
        "tradingview_symbol",
        runtime_config.tradingview_symbols[0] if runtime_config.tradingview_symbols else "BTCUSDT",
    ).strip().upper()
    exchange = _get_first(form, "tradingview_exchange", runtime_config.tradingview_exchange).strip().upper() or "BINANCE"
    interval = _get_first(form, "tradingview_interval", runtime_config.tradingview_interval).strip() or runtime_config.tradingview_interval
    bars = _parse_int_value(_get_first(form, "tradingview_bars", str(runtime_config.tradingview_bars)), "TradingView Bars")
    _validate_range(bars, "TradingView Bars", minimum=100, maximum=50000)

    result = fetch_tradingview_history(
        cache_root=TRADINGVIEW_CACHE_DIR,
        exchange=exchange,
        symbol=symbol,
        interval=interval,
        bars=bars,
        username=runtime_config.tradingview_username,
        password=runtime_config.tradingview_password,
        cache_enabled=True,
    )
    return {
        "exchange": result.exchange,
        "symbol": result.symbol,
        "interval": result.interval,
        "bars": result.candle_count,
        "source": result.source,
        "cache_path": str(result.cache_path),
    }


def _tradingview_backtest_redirect(form: dict[str, list[str]], lang: str) -> str:
    result = _tradingview_fetch_result(form)
    runtime_config, _ = APP_STATE.snapshot()
    params = _backtest_params_from_config(runtime_config)
    params["archives"] = result["cache_path"]
    params["tradingview_exchange"] = result["exchange"]
    params["tradingview_symbol"] = result["symbol"]
    params["tradingview_interval"] = result["interval"]
    params["tradingview_bars"] = result["bars"]
    for key in ("preset", "lookback_bars", "score_threshold", "holding_periods", "portfolio_top_n"):
        if key in form:
            params[key] = _get_first(form, key, str(params.get(key, "")))
    if normalize_language(lang) == "en":
        params["lang"] = "en"
    params["tv_fetched"] = 1
    return f"/backtest?{urlencode({key: _to_jsonable(value) for key, value in params.items()})}"


def _backtest_payload(query: dict[str, list[str]]) -> tuple[dict[str, object], dict[str, object], str | None]:
    runtime_config, scanner = APP_STATE.snapshot()
    defaults = _backtest_params_from_config(runtime_config)
    preset_id = _get_first(query, "preset", str(defaults["preset"]))
    base_params = apply_backtest_preset(dict(defaults), preset_id)
    params = {
        "preset": preset_id,
        "archives": _get_first(query, "archives", str(base_params["archives"])),
        "lookback_bars": _parse_query_int(query, "lookback_bars", base_params["lookback_bars"], "Lookback Bars"),
        "score_threshold": _parse_query_float(query, "score_threshold", base_params["score_threshold"], "Score Threshold"),
        "holding_periods": _get_first(query, "holding_periods", str(base_params["holding_periods"])),
        "portfolio_top_n": _parse_query_int(query, "portfolio_top_n", base_params["portfolio_top_n"], "Portfolio Top N"),
        "cooldown_bars": _parse_query_int(query, "cooldown_bars", base_params["cooldown_bars"], "Cooldown Bars"),
        "stop_loss_pct": _parse_query_float(query, "stop_loss_pct", base_params["stop_loss_pct"], "Stop Loss"),
        "take_profit_pct": _parse_query_float(query, "take_profit_pct", base_params["take_profit_pct"], "Take Profit"),
        "max_holding_bars": _parse_query_int(query, "max_holding_bars", base_params["max_holding_bars"], "Max Holding Bars"),
        "fee_bps": _parse_query_float(query, "fee_bps", base_params["fee_bps"], "Fee bps"),
        "fee_model": _get_first(query, "fee_model", str(base_params["fee_model"])),
        "fee_source": _get_first(query, "fee_source", str(base_params["fee_source"])),
        "maker_fee_bps": _parse_query_float(query, "maker_fee_bps", base_params["maker_fee_bps"], "Maker Fee"),
        "taker_fee_bps": _parse_query_float(query, "taker_fee_bps", base_params["taker_fee_bps"], "Taker Fee"),
        "entry_fee_role": _get_first(query, "entry_fee_role", str(base_params["entry_fee_role"])),
        "exit_fee_role": _get_first(query, "exit_fee_role", str(base_params["exit_fee_role"])),
        "fee_discount_pct": _parse_query_float(query, "fee_discount_pct", base_params["fee_discount_pct"], "Fee Discount"),
        "no_binance_discount": _parse_bool_flag(query, "no_binance_discount"),
        "slippage_bps": _parse_query_float(query, "slippage_bps", base_params["slippage_bps"], "Slippage bps"),
        "slippage_model": _get_first(query, "slippage_model", str(base_params["slippage_model"])),
        "min_slippage_bps": _parse_query_float(query, "min_slippage_bps", base_params["min_slippage_bps"], "Min Slippage"),
        "max_slippage_bps": _parse_query_float(query, "max_slippage_bps", base_params["max_slippage_bps"], "Max Slippage"),
        "slippage_window_bars": _parse_query_int(query, "slippage_window_bars", base_params["slippage_window_bars"], "Slip Window"),
        "capital_fraction_pct": _parse_query_float(query, "capital_fraction_pct", base_params["capital_fraction_pct"], "Capital"),
        "max_portfolio_exposure_pct": _parse_query_float(query, "max_portfolio_exposure_pct", base_params["max_portfolio_exposure_pct"], "Max Exposure"),
        "max_concurrent_positions": _parse_query_int(query, "max_concurrent_positions", base_params["max_concurrent_positions"], "Max Concurrent"),
        "min_volume_ratio": _parse_query_float(query, "min_volume_ratio", base_params["min_volume_ratio"], "Min Volume Ratio"),
        "min_buy_pressure": _parse_query_float(query, "min_buy_pressure", base_params["min_buy_pressure"], "Min Buy Pressure"),
        "min_rsi": _parse_query_float(query, "min_rsi", base_params["min_rsi"], "Min RSI"),
        "max_rsi": _parse_query_float(query, "max_rsi", base_params["max_rsi"], "Max RSI"),
        "no_kdj_confirmation": _parse_bool_flag(query, "no_kdj_confirmation"),
        "stability_checks": _parse_bool_flag(query, "stability_checks"),
        "tradingview_exchange": _get_first(query, "tradingview_exchange", runtime_config.tradingview_exchange),
        "tradingview_symbol": _get_first(
            query,
            "tradingview_symbol",
            runtime_config.tradingview_symbols[0] if runtime_config.tradingview_symbols else "BTCUSDT",
        ),
        "tradingview_interval": _get_first(query, "tradingview_interval", runtime_config.tradingview_interval),
        "tradingview_bars": _parse_query_int(query, "tradingview_bars", runtime_config.tradingview_bars, "TradingView Bars"),
        "tv_fetched": _parse_bool_flag(query, "tv_fetched"),
    }
    if "no_binance_discount" not in query:
        params["no_binance_discount"] = bool(base_params["no_binance_discount"])
    if "no_kdj_confirmation" not in query:
        params["no_kdj_confirmation"] = bool(base_params["no_kdj_confirmation"])

    archive_patterns = _split_archives(str(params["archives"]))
    if not archive_patterns:
        return _empty_backtest_payload(params), params, None

    paths = resolve_archive_paths(archive_patterns)
    if not paths:
        return _empty_backtest_payload(params), params, "没有匹配到任何 ZIP/CSV 历史 K 线文件。"

    holding_periods = [int(item) for item in str(params["holding_periods"]).split(",") if item.strip()]
    entry_config = EntryRuleConfig(
        min_score=float(params["score_threshold"]),
        min_volume_ratio=float(params["min_volume_ratio"]),
        min_buy_pressure_ratio=float(params["min_buy_pressure"]),
        min_rsi=float(params["min_rsi"]),
        max_rsi=float(params["max_rsi"]),
        require_kdj_confirmation=not bool(params["no_kdj_confirmation"]),
    )
    exit_config = ExitRuleConfig(
        max_holding_bars=int(params["max_holding_bars"]),
        stop_loss_pct=float(params["stop_loss_pct"]),
        take_profit_pct=float(params["take_profit_pct"]),
        cooldown_bars_after_exit=int(params["cooldown_bars"]),
    )
    execution_config = ExecutionConfig(
        fee_bps=float(params["fee_bps"]),
        fee_model=str(params["fee_model"]),
        fee_source=str(params["fee_source"]),
        maker_fee_bps=float(params["maker_fee_bps"]),
        taker_fee_bps=float(params["taker_fee_bps"]),
        entry_fee_role=str(params["entry_fee_role"]),
        exit_fee_role=str(params["exit_fee_role"]),
        fee_discount_pct=float(params["fee_discount_pct"]),
        apply_binance_discount=not bool(params["no_binance_discount"]),
        slippage_bps=float(params["slippage_bps"]),
        capital_fraction_pct=float(params["capital_fraction_pct"]),
        slippage_model=str(params["slippage_model"]),
        min_slippage_bps=float(params["min_slippage_bps"]),
        max_slippage_bps=float(params["max_slippage_bps"]),
        slippage_window_bars=int(params["slippage_window_bars"]),
        max_portfolio_exposure_pct=float(params["max_portfolio_exposure_pct"]),
        max_concurrent_positions=int(params["max_concurrent_positions"]),
    )

    grouped = group_archives(paths)
    series_reports = []
    reports_by_interval: dict[str, list] = {}
    try:
        account_execution_config = (
            resolve_execution_config_from_binance(
                gateway=scanner.gateway,
                execution_config=execution_config,
                symbol=None,
            )
            if execution_config.fee_source == "account"
            else execution_config
        )
    except Exception as exc:  # noqa: BLE001
        return _empty_backtest_payload(params), params, str(exc)
    candles_by_interval: dict[str, dict[str, list]] = {}
    series_contexts = []
    for (symbol, interval), archive_paths in sorted(grouped.items()):
        candles = merge_candles(archive_paths)
        candles_by_interval.setdefault(interval, {})[symbol] = candles
        try:
            report_execution_config = (
                resolve_execution_config_from_binance(
                    gateway=scanner.gateway,
                    execution_config=account_execution_config,
                    symbol=symbol,
                )
                if execution_config.fee_source == "symbol"
                else account_execution_config
            )
        except Exception as exc:  # noqa: BLE001
            return _empty_backtest_payload(params), params, str(exc)
        if str(params["preset"]) == "btc_overnight_seasonality":
            report = run_overnight_seasonality_backtest(
                symbol=symbol,
                interval=interval,
                candles=candles,
                execution_config=report_execution_config,
            )
        else:
            report = run_backtest_for_series(
                symbol=symbol,
                interval=interval,
                candles=candles,
                lookback_bars=int(params["lookback_bars"]),
                score_threshold=float(params["score_threshold"]),
                holding_periods=holding_periods,
                entry_config=entry_config,
                exit_config=exit_config,
                execution_config=report_execution_config,
                cooldown_bars=int(params["cooldown_bars"]) or None,
            )
        reports_by_interval.setdefault(interval, []).append(report)
        series_reports.append(format_backtest_report(report))
        series_contexts.append((symbol, interval, candles, report_execution_config))

    portfolio_reports = []
    if int(params["portfolio_top_n"]) > 0:
        for _, interval_reports in sorted(reports_by_interval.items()):
            portfolio_report = run_portfolio_backtest(
                interval_reports,
                top_n=int(params["portfolio_top_n"]),
                max_concurrent_positions=execution_config.max_concurrent_positions or None,
                max_portfolio_exposure_pct=execution_config.max_portfolio_exposure_pct,
            )
            if portfolio_report is not None:
                portfolio_reports.append(format_portfolio_report(portfolio_report))

    rebalance_reports = []
    if str(params["preset"]) == "crypto_rebalance_premium":
        for interval, interval_candles in sorted(candles_by_interval.items()):
            sample_candles = next(iter(interval_candles.values()), [])
            rebalance_interval_bars = max(1, bars_per_day(sample_candles)) if sample_candles else 1
            rebalance_report = run_rebalance_premium_backtest(
                interval_candles,
                interval=interval,
                rebalance_interval_bars=rebalance_interval_bars,
                fee_bps=execution_config.fee_bps,
                slippage_bps=execution_config.slippage_bps,
            )
            if rebalance_report is not None:
                rebalance_reports.append(format_rebalance_premium_report(rebalance_report))

    stability_checks = (
        _run_backtest_stability_checks(
            series_contexts=series_contexts,
            params=params,
            holding_periods=holding_periods,
            entry_config=entry_config,
            exit_config=exit_config,
        )
        if bool(params["stability_checks"]) and str(params["preset"]) not in {"btc_overnight_seasonality", "crypto_rebalance_premium"}
        else []
    )

    return {
        "series_reports": series_reports,
        "portfolio_reports": portfolio_reports,
        "rebalance_reports": rebalance_reports,
        "strategy_explanation": _build_backtest_strategy_explanation(
            params=params,
            series_reports=series_reports,
            portfolio_reports=portfolio_reports,
            rebalance_reports=rebalance_reports,
            stability_checks=stability_checks,
        ),
    }, params, None


def _empty_backtest_payload(params: dict[str, object]) -> dict[str, object]:
    return {
        "series_reports": [],
        "portfolio_reports": [],
        "rebalance_reports": [],
        "strategy_explanation": _build_backtest_strategy_explanation(
            params=params,
            series_reports=[],
            portfolio_reports=[],
            rebalance_reports=[],
            stability_checks=[],
        ),
    }


def _run_backtest_stability_checks(
    *,
    series_contexts: list[tuple[str, str, list, ExecutionConfig]],
    params: dict[str, object],
    holding_periods: list[int],
    entry_config: EntryRuleConfig,
    exit_config: ExitRuleConfig,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    base_score = float(params["score_threshold"])
    base_slippage = float(params["slippage_bps"])
    for symbol, interval, candles, execution_config in series_contexts[:2]:
        variants = [
            ("score_minus_3", candles, replace(entry_config, min_score=max(0.0, base_score - 3.0)), execution_config),
            ("score_plus_3", candles, replace(entry_config, min_score=min(100.0, base_score + 3.0)), execution_config),
            ("slippage_plus_5bps", candles, entry_config, replace(execution_config, slippage_bps=base_slippage + 5.0)),
        ]
        for check_name, variant_candles, variant_entry_config, variant_execution_config in variants:
            checks.append(
                _run_single_stability_check(
                    symbol=symbol,
                    interval=interval,
                    check_name=check_name,
                    candles=variant_candles,
                    params=params,
                    holding_periods=holding_periods,
                    entry_config=variant_entry_config,
                    exit_config=exit_config,
                    execution_config=variant_execution_config,
                )
            )
        walk_forward_windows = _walk_forward_validation_windows(
            candles,
            holding_periods=holding_periods,
            max_holding_bars=exit_config.max_holding_bars,
        )
        if not walk_forward_windows:
            checks.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "check": "walk_forward",
                    "status": "error",
                    "message": "样本不足，无法构造滚动训练/验证窗口。",
                }
            )
        for index, window in enumerate(walk_forward_windows, start=1):
            validation_candles = candles[window["validation_start"] : window["validation_end"]]
            item = _run_single_stability_check(
                symbol=symbol,
                interval=interval,
                check_name=f"walk_forward_fold_{index}",
                candles=validation_candles,
                params=params,
                holding_periods=holding_periods,
                entry_config=entry_config,
                exit_config=exit_config,
                execution_config=execution_config,
            )
            item.update(window)
            checks.append(item)
    return checks


def _run_single_stability_check(
    *,
    symbol: str,
    interval: str,
    check_name: str,
    candles: list,
    params: dict[str, object],
    holding_periods: list[int],
    entry_config: EntryRuleConfig,
    exit_config: ExitRuleConfig,
    execution_config: ExecutionConfig,
) -> dict[str, object]:
    try:
        report = run_backtest_for_series(
            symbol=symbol,
            interval=interval,
            candles=candles,
            lookback_bars=int(params["lookback_bars"]),
            score_threshold=float(entry_config.min_score),
            holding_periods=holding_periods,
            entry_config=entry_config,
            exit_config=exit_config,
            execution_config=execution_config,
            cooldown_bars=int(params["cooldown_bars"]) or None,
        )
        return {
            "symbol": symbol,
            "interval": interval,
            "check": check_name,
            "status": "ok",
            "score_threshold": entry_config.min_score,
            "slippage_bps": execution_config.slippage_bps,
            "candle_count": len(candles),
            "final_equity": report.equity_curve[-1].equity if report.equity_curve else 1.0,
            "max_drawdown_pct": min((point.drawdown_pct for point in report.equity_curve), default=0.0),
            "signal_count": report.signal_count,
            "profit_factor": report.trade_stat.profit_factor if report.trade_stat is not None else 0.0,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol,
            "interval": interval,
            "check": check_name,
            "status": "error",
            "message": str(exc),
        }


def _walk_forward_validation_windows(
    candles: list,
    *,
    holding_periods: list[int],
    max_holding_bars: int,
) -> list[dict[str, int]]:
    max_horizon = max([*holding_periods, max_holding_bars, 1]) + 1
    min_validation_bars = 60 + max_horizon + 5
    min_train_bars = max(90, min_validation_bars)
    if len(candles) < min_train_bars + min_validation_bars:
        return []

    validation_bars = max(min_validation_bars, len(candles) // 5)
    train_bars = min_train_bars
    step = validation_bars
    windows: list[dict[str, int]] = []
    start = 0
    while len(windows) < 3:
        train_start = start
        train_end = train_start + train_bars
        validation_start = train_end
        validation_end = validation_start + validation_bars
        if validation_end > len(candles):
            break
        windows.append(
            {
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "train_bars": train_end - train_start,
                "validation_bars": validation_end - validation_start,
            }
        )
        start += step
    return windows


def _build_backtest_strategy_explanation(
    *,
    params: dict[str, object],
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
    rebalance_reports: list[dict[str, object]],
    stability_checks: list[dict[str, object]],
) -> dict[str, object]:
    preset = str(params.get("preset", "custom"))
    strategy_type, strategy_summary = _backtest_strategy_type(preset)
    total_series_trades = sum(int(report.get("signal_count", 0)) for report in series_reports)
    total_portfolio_batches = sum(int(report.get("batch_count", 0)) for report in portfolio_reports)
    best_series = max(series_reports, key=lambda item: float(item.get("final_equity", 0.0)), default=None)
    best_portfolio = max(portfolio_reports, key=lambda item: float(item.get("final_equity", 0.0)), default=None)
    trade_stats = [
        report.get("trade_stat")
        for report in [*series_reports, *portfolio_reports]
        if isinstance(report.get("trade_stat"), dict)
    ]
    max_drawdown = min(
        [float(report.get("max_drawdown_pct", 0.0)) for report in [*series_reports, *portfolio_reports]],
        default=0.0,
    )
    min_profit_factor = min((float(stat.get("profit_factor", 0.0)) for stat in trade_stats), default=0.0)
    best_equity = max(
        [float(report.get("final_equity", 0.0)) for report in [*series_reports, *portfolio_reports]],
        default=0.0,
    )
    diagnostics = _backtest_diagnostics(
        total_series_trades=total_series_trades,
        total_portfolio_batches=total_portfolio_batches,
        min_profit_factor=min_profit_factor,
        max_drawdown=max_drawdown,
        best_equity=best_equity,
        series_count=len(series_reports),
        stability_enabled=bool(params.get("stability_checks")),
        stability_checks=stability_checks,
    )
    cost_notes = _backtest_cost_notes(params)
    notes = [
        strategy_summary,
        f"入场过滤：score >= {float(params.get('score_threshold', 0.0)):.1f}, volume_ratio >= {float(params.get('min_volume_ratio', 0.0)):.2f}, buy_pressure >= {float(params.get('min_buy_pressure', 0.0)):.2f}。",
        f"退出假设：止损 {float(params.get('stop_loss_pct', 0.0)):.1f}%，止盈 {float(params.get('take_profit_pct', 0.0)):.1f}%，最多持有 {int(params.get('max_holding_bars', 0))} 根 K 线。",
        *cost_notes,
        *diagnostics,
    ]
    return {
        "preset": preset,
        "strategy_type": strategy_type,
        "summary": strategy_summary,
        "sample": {
            "series_count": len(series_reports),
            "portfolio_count": len(portfolio_reports),
            "rebalance_count": len(rebalance_reports),
            "series_trades": total_series_trades,
            "portfolio_batches": total_portfolio_batches,
        },
        "best": {
            "series": None
            if best_series is None
            else {
                "symbol": best_series.get("symbol", ""),
                "interval": best_series.get("interval", ""),
                "final_equity": best_series.get("final_equity", 0.0),
                "max_drawdown_pct": best_series.get("max_drawdown_pct", 0.0),
            },
            "portfolio": None
            if best_portfolio is None
            else {
                "interval": best_portfolio.get("interval", ""),
                "final_equity": best_portfolio.get("final_equity", 0.0),
                "max_drawdown_pct": best_portfolio.get("max_drawdown_pct", 0.0),
            },
        },
        "diagnostics": diagnostics,
        "cost_notes": cost_notes,
        "stability_enabled": bool(params.get("stability_checks")),
        "stability_checks": stability_checks,
        "notes": notes,
    }


def _backtest_strategy_type(preset: str) -> tuple[str, str]:
    mapping = {
        "breakout_aggressive": ("breakout", "区间突破 / 动量延续模板，强调高评分、强量能和较短持有周期。"),
        "portfolio_rotation": ("momentum_rotation", "动量轮动模板，先横截面筛选强势标的，再用组合层 top N 控制集中度。"),
        "balanced_swing": ("balanced_swing", "均衡波段模板，在趋势、动量、量能和买压之间取折中。"),
        "crypto_rebalance_premium": ("rebalance", "等权再平衡研究模板，用于比较定期再平衡和自然漂移组合。"),
        "btc_overnight_seasonality": ("seasonality", "BTC 时间窗口模板，研究 UTC 固定时段持有的季节性收益。"),
        "btc_cycle_trend": ("trend_following", "BTC 趋势跟随模板，强调 EMA 多头结构、趋势评分和中等持仓周期。"),
        "btc_core_trading": ("core_satellite", "BTC 核心仓加交易仓模板，围绕主方向做较积极的仓位调整。"),
        "btc_compounding_risk_off": ("risk_off_compounding", "偏复利和回撤控制模板，降低暴露并重视账户生存。"),
    }
    return mapping.get(preset, ("custom", "自定义参数模板，策略含义取决于当前阈值组合。"))


def _backtest_cost_notes(params: dict[str, object]) -> list[str]:
    fee_model = str(params.get("fee_model", "flat"))
    fee_source = str(params.get("fee_source", "manual"))
    slippage_model = str(params.get("slippage_model", "fixed"))
    notes = [
        f"成本假设：fee_model={fee_model}, fee_source={fee_source}, slippage_model={slippage_model}。",
    ]
    if slippage_model == "fixed":
        notes.append(f"当前固定滑点 {float(params.get('slippage_bps', 0.0)):.1f}bps；建议再用更高滑点复测做成本敏感性检查。")
    else:
        notes.append(
            f"动态滑点范围 {float(params.get('min_slippage_bps', 0.0)):.1f}-{float(params.get('max_slippage_bps', 0.0)):.1f}bps，结果更接近真实成交约束。"
        )
    return notes


def _backtest_diagnostics(
    *,
    total_series_trades: int,
    total_portfolio_batches: int,
    min_profit_factor: float,
    max_drawdown: float,
    best_equity: float,
    series_count: int,
    stability_enabled: bool,
    stability_checks: list[dict[str, object]],
) -> list[str]:
    diagnostics: list[str] = []
    if series_count == 0:
        diagnostics.append("尚未产生单币种回测结果；需要先提供本地历史 K 线 ZIP。")
        return diagnostics
    if total_series_trades < 20:
        diagnostics.append("交易样本少于 20 笔，统计稳定性不足，不建议据此直接调高实盘权重。")
    if total_portfolio_batches and total_portfolio_batches < 8:
        diagnostics.append("组合批次数少于 8 次，轮动策略稳定性仍需更多历史样本。")
    if best_equity <= 1.0:
        diagnostics.append("最佳权益未超过 1.0，当前参数没有表现出正收益优势。")
    if max_drawdown <= -20.0:
        diagnostics.append("最大回撤超过 20%，需要降低仓位、提高过滤阈值或缩短持有周期。")
    if min_profit_factor and min_profit_factor < 1.1:
        diagnostics.append("存在 Profit Factor 低于 1.10 的结果，交易成本或假信号可能侵蚀收益。")
    if not diagnostics:
        diagnostics.append("基础稳定性检查未发现明显红旗；仍需做样本外和参数邻域验证。")
    if not stability_enabled:
        diagnostics.append("高级稳定性检查未运行；勾选 Stability Checks 后会额外执行参数邻域和滚动 walk-forward 复测。")
    elif not stability_checks:
        diagnostics.append("高级稳定性检查未产生结果；当前预设可能不适用该检查或样本不足。")
    elif any(item.get("status") == "error" for item in stability_checks):
        diagnostics.append("部分高级稳定性检查失败；请查看检查表中的错误信息。")
    elif any(float(item.get("final_equity", 1.0)) <= 1.0 for item in stability_checks if item.get("status") == "ok"):
        diagnostics.append("参数邻域或样本外检查中出现权益不高于 1.0 的结果，策略稳健性需要继续验证。")
    else:
        diagnostics.append("高级稳定性检查全部完成，参数邻域和滚动 walk-forward 未出现明显失效。")
    return diagnostics


def _backtest_export_csv(payload: dict[str, object], params: dict[str, object], error: str | None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "name", "interval", "metric", "value"])
    writer.writerow(["meta", "backtest", "", "error", error or ""])
    explanation = payload.get("strategy_explanation")
    if isinstance(explanation, dict):
        writer.writerow(["meta", "strategy", "", "strategy_type", explanation.get("strategy_type", "")])
        writer.writerow(["meta", "strategy", "", "summary", explanation.get("summary", "")])
        for index, note in enumerate(explanation.get("notes", []) if isinstance(explanation.get("notes"), list) else [], start=1):
            writer.writerow(["meta", "strategy", "", f"note_{index}", note])
        for item in explanation.get("stability_checks", []) if isinstance(explanation.get("stability_checks"), list) else []:
            if not isinstance(item, dict):
                continue
            name = f'{item.get("symbol", "")}:{item.get("check", "")}'
            writer.writerow(["stability", name, item.get("interval", ""), "status", item.get("status", "")])
            if item.get("status") == "ok":
                writer.writerow(["stability", name, item.get("interval", ""), "final_equity", item.get("final_equity", "")])
                writer.writerow(["stability", name, item.get("interval", ""), "max_drawdown_pct", item.get("max_drawdown_pct", "")])
                writer.writerow(["stability", name, item.get("interval", ""), "profit_factor", item.get("profit_factor", "")])
                if "train_bars" in item:
                    writer.writerow(["stability", name, item.get("interval", ""), "train_bars", item.get("train_bars", "")])
                    writer.writerow(["stability", name, item.get("interval", ""), "validation_bars", item.get("validation_bars", "")])
            else:
                writer.writerow(["stability", name, item.get("interval", ""), "message", item.get("message", "")])
    for key, value in params.items():
        writer.writerow(["param", "backtest", "", key, value])

    for report in payload["series_reports"]:
        writer.writerow(["series", report["symbol"], report["interval"], "final_equity", report["final_equity"]])
        writer.writerow(["series", report["symbol"], report["interval"], "buy_hold_final_equity", report.get("buy_hold_final_equity", 1.0)])
        writer.writerow(["series", report["symbol"], report["interval"], "buy_hold_return_pct", report.get("buy_hold_return_pct", 0.0)])
        writer.writerow(["series", report["symbol"], report["interval"], "max_drawdown_pct", report["max_drawdown_pct"]])
        writer.writerow(["series", report["symbol"], report["interval"], "signal_count", report["signal_count"]])
        trade_stat = report.get("trade_stat")
        if trade_stat:
            writer.writerow(["series", report["symbol"], report["interval"], "win_rate_pct", trade_stat["win_rate_pct"]])
            writer.writerow(["series", report["symbol"], report["interval"], "profit_factor", trade_stat["profit_factor"]])

    for report in payload["portfolio_reports"]:
        name = f'portfolio_top_{report["top_n"]}'
        writer.writerow(["portfolio", name, report["interval"], "final_equity", report["final_equity"]])
        writer.writerow(["portfolio", name, report["interval"], "max_drawdown_pct", report["max_drawdown_pct"]])
        writer.writerow(["portfolio", name, report["interval"], "batch_count", report["batch_count"]])
        trade_stat = report.get("trade_stat")
        if trade_stat:
            writer.writerow(["portfolio", name, report["interval"], "win_rate_pct", trade_stat["win_rate_pct"]])
            writer.writerow(["portfolio", name, report["interval"], "profit_factor", trade_stat["profit_factor"]])

    for report in payload.get("rebalance_reports", []):
        name = "crypto_rebalance_premium"
        writer.writerow(["rebalance", name, report["interval"], "rebalanced_final_equity", report["rebalanced_final_equity"]])
        writer.writerow(["rebalance", name, report["interval"], "buy_hold_final_equity", report["buy_hold_final_equity"]])
        writer.writerow(["rebalance", name, report["interval"], "premium_pct", report["premium_pct"]])
        writer.writerow(["rebalance", name, report["interval"], "rebalance_count", report["rebalance_count"]])
        writer.writerow(["rebalance", name, report["interval"], "avg_turnover_pct", report["avg_turnover_pct"]])

    return buffer.getvalue()


def _build_runtime_config(form: dict[str, list[str]]) -> RuntimeConfig:
    current_config, _ = APP_STATE.snapshot()
    keep_binance_key = current_config.binance_api_key
    keep_binance_secret = current_config.binance_api_secret
    keep_okx_key = current_config.okx_api_key
    keep_okx_secret = current_config.okx_api_secret
    keep_okx_passphrase = current_config.okx_api_passphrase
    keep_x_bearer_token = current_config.x_bearer_token
    keep_onchain_api_key = current_config.onchain_api_key
    keep_tradingview_password = current_config.tradingview_password
    keep_llm_api_key = current_config.llm_api_key or current_config.openai_api_key
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
            max_open_positions=_parse_int_value(_get_first(form, "autotrade_max_open_positions", str(current_config.autotrade_defaults.max_open_positions)), "Auto Trade Max Open Positions"),
            max_total_quote_exposure=_parse_float_value(_get_first(form, "autotrade_max_total_quote_exposure", str(current_config.autotrade_defaults.max_total_quote_exposure)), "Auto Trade Max Exposure"),
            score_threshold=_parse_float_value(_get_first(form, "autotrade_score_threshold", str(current_config.autotrade_defaults.score_threshold)), "Auto Trade Score Threshold"),
            min_volume_ratio=_parse_float_value(_get_first(form, "autotrade_min_volume_ratio", str(current_config.autotrade_defaults.min_volume_ratio)), "Auto Trade Min Volume Ratio"),
            min_buy_pressure=_parse_float_value(_get_first(form, "autotrade_min_buy_pressure", str(current_config.autotrade_defaults.min_buy_pressure)), "Auto Trade Min Buy Pressure"),
            stop_loss_pct=_parse_float_value(_get_first(form, "autotrade_stop_loss_pct", str(current_config.autotrade_defaults.stop_loss_pct)), "Auto Trade Stop Loss"),
            take_profit_pct=_parse_float_value(_get_first(form, "autotrade_take_profit_pct", str(current_config.autotrade_defaults.take_profit_pct)), "Auto Trade Take Profit"),
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


class RequestHandler(BaseHTTPRequestHandler):
    def _request_lang(self, query: dict[str, list[str]]) -> str:
        lang = _get_first(query, "lang", "")
        if not lang:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            if "ai_trade_lang" in cookie:
                lang = cookie["ai_trade_lang"].value
        lang = normalize_language(lang)
        self._active_lang = lang
        return lang

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = self._request_lang(query)

        try:
            if parsed.path == "/api/health":
                self._send_text(
                    json.dumps(_health_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/":
                payload, params = _scan_payload(query)
                html = render_index_page(
                    summary=payload["summary"],
                    signals=payload["signals"],
                    params=params,
                    intervals=["15m", "1h", "4h", "1d"],
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/terminal":
                payload = _fast_terminal_payload()
                html = render_terminal_page(payload, lang=lang, layout_context=_layout_context())
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path.startswith("/terminal/"):
                module = parsed.path.removeprefix("/terminal/").strip("/")
                if module in TERMINAL_MODULES:
                    html = render_terminal_module_page(
                        snapshot=_terminal_page_snapshot(module),
                        module=module,
                        trading_status=_trading_status_payload() if module == "trading" else None,
                        paper_auto_status=_paper_auto_status_payload() if module == "trading" else None,
                        lang=lang,
                        layout_context=_layout_context(),
                    )
                    self._send_text(html, content_type="text/html; charset=utf-8")
                    return

            if parsed.path == "/api/terminal/snapshot":
                self._send_text(
                    json.dumps(_terminal_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            module = _terminal_api_module_from_path(parsed.path)
            if module:
                self._send_text(
                    json.dumps(_terminal_module_payload(module), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/platform/capabilities":
                self._send_text(
                    json.dumps(_platform_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/platform/accounts":
                payload = _platform_payload()
                self._send_text(
                    json.dumps({"accounts": payload["accounts"]}, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/platform/exchange-auth":
                self._send_text(
                    json.dumps(_exchange_auth_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/platform/strategies":
                payload = _platform_payload()
                self._send_text(
                    json.dumps({"strategies": payload["strategies"]}, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/platform/risk":
                payload = _platform_payload()
                self._send_text(
                    json.dumps({"risk_rules": payload["risk_rules"]}, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/platform/logs":
                payload = _platform_payload()
                self._send_text(
                    json.dumps({"events": payload["recent_events"]}, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/scan":
                payload, _ = _scan_payload(query)
                self._send_text(
                    json.dumps(payload, ensure_ascii=False),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/backtest":
                payload, params, error = _backtest_payload(query)
                html = render_backtest_page(
                    params=params,
                    series_reports=payload["series_reports"],
                    portfolio_reports=payload["portfolio_reports"],
                    rebalance_reports=payload["rebalance_reports"],
                    strategy_explanation=payload["strategy_explanation"],
                    error=error,
                    presets=list_backtest_presets(),
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/trading":
                payload = _trading_status_payload()
                html = render_trading_page(
                    config=payload["config"],
                    readiness=payload["readiness"],
                    positions=payload["open_positions"],
                    events=payload["events"],
                    lang=lang,
                    layout_context=_layout_context(payload["readiness"]),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/api/trading/status":
                self._send_text(
                    json.dumps(_trading_status_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/readiness":
                self._send_text(
                    json.dumps(_trading_readiness_payload(check_account=True), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/paper/auto/status":
                self._send_text(
                    json.dumps(_paper_auto_status_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/backtest/presets":
                self._send_text(
                    json.dumps({"presets": list_backtest_presets()}, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/backtest/tradingview/fetch":
                payload = _tradingview_fetch_result(query)
                self._send_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/backtest/export":
                payload, params, error = _backtest_payload(query)
                export_format = _get_first(query, "format", "csv").lower()
                if export_format == "json":
                    self._send_text(
                        json.dumps(
                            _to_jsonable(
                                {
                                    "params": params,
                                    "series_reports": payload["series_reports"],
                                    "portfolio_reports": payload["portfolio_reports"],
                                    "rebalance_reports": payload["rebalance_reports"],
                                    "strategy_explanation": payload["strategy_explanation"],
                                    "error": error,
                                }
                            ),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        content_type="application/json; charset=utf-8",
                    )
                    return
                if export_format == "csv":
                    self._send_text(
                        _backtest_export_csv(payload, params, error),
                        content_type="text/csv; charset=utf-8",
                    )
                    return
                self._send_text(
                    json.dumps({"error": "Unsupported export format."}, ensure_ascii=False),
                    status=HTTPStatus.BAD_REQUEST,
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/settings":
                params, status = _settings_context()
                message = None
                if _parse_bool_flag(query, "saved"):
                    message = "运行配置已保存。" if lang == "zh" else "Runtime configuration saved."
                if _parse_bool_flag(query, "imported"):
                    message = "配置模板已导入。" if lang == "zh" else "Configuration template imported."
                html = render_settings_page(
                    params=params,
                    status=status,
                    message=message,
                    error=None,
                    import_payload_text=None,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/api/settings/export":
                payload = _export_runtime_config_template(include_secrets=_parse_bool_flag(query, "include_secrets"))
                self._send_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/backtest":
                payload, params, error = _backtest_payload(query)
                self._send_text(
                    json.dumps(
                        _to_jsonable(
                            {
                                "params": params,
                                "series_reports": payload["series_reports"],
                                "portfolio_reports": payload["portfolio_reports"],
                                "rebalance_reports": payload["rebalance_reports"],
                                "strategy_explanation": payload["strategy_explanation"],
                                "error": error,
                            }
                        ),
                        ensure_ascii=False,
                    ),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/static/styles.css":
                css = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")
                self._send_text(css, content_type="text/css; charset=utf-8")
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False),
                status=HTTPStatus.BAD_REQUEST,
                content_type="application/json; charset=utf-8",
            )
        except BinancePublicAPIError as exc:
            self._send_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False),
                status=HTTPStatus.BAD_GATEWAY,
                content_type="application/json; charset=utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            self._send_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False),
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                content_type="application/json; charset=utf-8",
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = self._request_lang(query)
        try:
            if parsed.path == "/api/strategy/compile":
                try:
                    description, _ = _strategy_description_from_body(self)
                    payload = _compile_strategy_payload(description)
                except ValueError as exc:
                    self._send_text(
                        json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2),
                        status=HTTPStatus.BAD_REQUEST,
                        content_type="application/json; charset=utf-8",
                    )
                    return
                self._send_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/terminal/strategies/compile":
                description, form = _strategy_description_from_body(self)
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                try:
                    payload = _compile_strategy_payload(description)
                    message = "策略已编译为可回测和 paper 自动交易参数。" if lang == "zh" else "Strategy compiled into backtest and paper-trading parameters."
                    error = None
                except ValueError as exc:
                    payload = None
                    message = None
                    error = str(exc)
                html = render_terminal_module_page(
                    snapshot=_fast_terminal_payload(),
                    module="strategies",
                    strategy_builder_result=payload,
                    strategy_builder_text=description,
                    message=message,
                    error=error,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(
                    html,
                    content_type="text/html; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST if error else HTTPStatus.OK,
                )
                return

            if parsed.path == "/settings":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                form = parse_qs(payload)
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                config = _build_runtime_config(form)
                APP_STATE.update_config(config)
                self._redirect(_path_with_lang("/settings", lang, saved=1))
                return

            if parsed.path == "/scan/community/update":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                form = parse_qs(payload)
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                config = _build_runtime_config(form)
                APP_STATE.update_config(config)
                with _SCAN_CACHE_LOCK:
                    _SCAN_PAYLOAD_CACHE.clear()
                    _SCAN_INFLIGHT.clear()
                self._redirect(_path_with_lang("/", lang, community_saved=1))
                return

            if parsed.path == "/settings/import":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                form = parse_qs(payload)
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                config = _import_runtime_config_template(form)
                APP_STATE.update_config(config)
                self._redirect(_path_with_lang("/settings", lang, imported=1))
                return

            if parsed.path == "/backtest/tradingview/fetch":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                form = parse_qs(payload)
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                try:
                    self._redirect(_tradingview_backtest_redirect(form, lang))
                except ValueError as exc:
                    backtest_payload, params, _ = _backtest_payload({})
                    html = render_backtest_page(
                        params=params,
                        series_reports=backtest_payload["series_reports"],
                        portfolio_reports=backtest_payload["portfolio_reports"],
                        rebalance_reports=backtest_payload["rebalance_reports"],
                        strategy_explanation=backtest_payload["strategy_explanation"],
                        error=str(exc),
                        presets=list_backtest_presets(),
                        lang=lang,
                        layout_context=_layout_context(),
                    )
                    self._send_text(html, content_type="text/html; charset=utf-8", status=HTTPStatus.BAD_REQUEST)
                return

            if parsed.path == "/trading/run":
                payload = _run_trading_once()
                status_payload = _trading_status_payload()
                readiness = status_payload["readiness"]
                html = render_trading_page(
                    config={
                        **status_payload["config"],
                        "enabled": payload["enabled"],
                        "mode": payload["mode"],
                    },
                    readiness=readiness,
                    positions=payload["open_positions"],
                    events=payload["events"],
                    lang=lang,
                    layout_context=_layout_context(readiness),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/terminal/trading/run":
                payload = _run_trading_once(force_paper=True)
                filled = sum(1 for event in payload["events"] if event["status"] == "paper_filled")
                blocked = sum(1 for event in payload["events"] if event["status"] in {"risk_blocked", "blocked", "rejected"})
                message = (
                    f"模拟量化交易已执行：成交事件 {filled} 个，阻断/拒绝 {blocked} 个。"
                    if lang == "zh"
                    else f"Paper quant run completed: {filled} fill event(s), {blocked} blocked/rejected."
                )
                html = render_terminal_module_page(
                    snapshot=_fast_terminal_payload(),
                    module="trading",
                    trading_status=_trading_status_payload(),
                    paper_auto_status=_paper_auto_status_payload(),
                    message=message,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/terminal/trading/auto/start":
                form = parse_qs(_read_body(self))
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                interval_seconds = _parse_int_value(
                    _get_first(form, "interval_seconds", str(PAPER_AUTO_DEFAULT_INTERVAL_SECONDS)),
                    "Paper Auto Interval",
                )
                status = _start_paper_auto_trading(interval_seconds)
                message = (
                    f"模拟策略自动交易已启动：每 {int(status['interval_seconds'])} 秒运行一轮。"
                    if lang == "zh"
                    else f"Paper strategy auto trading started: one run every {int(status['interval_seconds'])} seconds."
                )
                html = render_terminal_module_page(
                    snapshot=_fast_terminal_payload(),
                    module="trading",
                    trading_status=_trading_status_payload(),
                    paper_auto_status=status,
                    message=message,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/terminal/trading/auto/stop":
                form = parse_qs(_read_body(self))
                lang = normalize_language(_get_first(form, "lang", lang))
                self._active_lang = lang
                status = _stop_paper_auto_trading()
                message = "模拟策略自动交易已停止。" if lang == "zh" else "Paper strategy auto trading stopped."
                html = render_terminal_module_page(
                    snapshot=_fast_terminal_payload(),
                    module="trading",
                    trading_status=_trading_status_payload(),
                    paper_auto_status=status,
                    message=message,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/api/trading/run":
                payload = _run_trading_once()
                self._send_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/paper/run":
                payload = _run_trading_once(force_paper=True)
                self._send_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/paper/auto/start":
                form = parse_qs(_read_body(self))
                interval_seconds = _parse_int_value(
                    _get_first(form, "interval_seconds", str(PAPER_AUTO_DEFAULT_INTERVAL_SECONDS)),
                    "Paper Auto Interval",
                )
                self._send_text(
                    json.dumps(_start_paper_auto_trading(interval_seconds), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/paper/auto/stop":
                self._send_text(
                    json.dumps(_stop_paper_auto_trading(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            params, status = _settings_context()
            html = render_settings_page(
                params=params,
                status=status,
                message=None,
                error=str(exc),
                import_payload_text=_get_first(form, "config_template", "") if "form" in locals() else None,
                lang=lang,
                layout_context=_layout_context(),
            )
            self._send_text(html, content_type="text/html; charset=utf-8", status=HTTPStatus.BAD_REQUEST)
        except BinancePublicAPIError as exc:
            self._send_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False),
                status=HTTPStatus.BAD_GATEWAY,
                content_type="application/json; charset=utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            self._send_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False),
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                content_type="application/json; charset=utf-8",
            )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _send_text(self, body: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if hasattr(self, "_active_lang"):
            self.send_header("Set-Cookie", f"ai_trade_lang={self._active_lang}; Path=/; SameSite=Lax")
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if hasattr(self, "_active_lang"):
            self.send_header("Set-Cookie", f"ai_trade_lang={self._active_lang}; Path=/; SameSite=Lax")
        self.end_headers()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="trade_signal_app", description="Run the AI Trade local web application.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--host", default=SETTINGS.server_host, help="Host interface to bind the local HTTP server.")
    parser.add_argument("--port", type=int, default=SETTINGS.server_port, help="TCP port to bind the local HTTP server.")
    return parser.parse_args(argv)


def run(*, host: str | None = None, port: int | None = None) -> None:
    resolved_host = host or SETTINGS.server_host
    resolved_port = port if port is not None else SETTINGS.server_port
    server = ThreadingHTTPServer((resolved_host, resolved_port), RequestHandler)
    print(f"Serving on http://{resolved_host}:{resolved_port}")
    server.serve_forever()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
