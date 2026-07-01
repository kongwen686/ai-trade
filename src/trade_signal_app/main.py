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
from threading import RLock
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
from .intelligence import IntelligenceHub, IntelligenceSnapshot
from .onchain import DEFAULT_ONCHAIN_SYMBOLS, OpenMultiChainOnchainProvider
from .platform import build_platform_snapshot
from .presets import apply_backtest_preset, list_backtest_presets
from .runtime_config import AutoTradeDefaults, BacktestDefaults, IntelligenceDefaults, RuntimeConfig, ScanDefaults
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig
from .strategy_builder import compile_strategy
from .trading import AutoTrader, LIVE_CONFIRM_VALUE, TradingEvent, TradingPosition, TradingRunReport, TradingStateStore
from .ui import format_backtest_report, format_portfolio_report, format_rebalance_premium_report, format_signal_row
from .views import normalize_language, render_backtest_page, render_index_page, render_settings_page, render_terminal_module_page, render_terminal_page, render_trading_page

RUNTIME_CONFIG_PATH = BASE_DIR / "data" / "runtime_config.json"
TRADING_STATE_PATH = BASE_DIR / "data" / "trading_state.json"
APP_STATE = AppState(SETTINGS, RUNTIME_CONFIG_PATH)
MARKET_TICKER_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
TERMINAL_SNAPSHOT_TTL_SECONDS = 45
SCAN_SYNC_TIMEOUT_SECONDS = 8
_TERMINAL_CACHE_LOCK = RLock()
_TERMINAL_CACHE: dict[str, object] = {"key": None, "expires_at": datetime.min.replace(tzinfo=timezone.utc), "payload": None}
_ONCHAIN_MODULE_CACHE_LOCK = RLock()
_ONCHAIN_MODULE_CACHE: dict[str, object] = {"key": None, "expires_at": datetime.min.replace(tzinfo=timezone.utc), "payload": None}
_SCAN_CACHE_LOCK = RLock()
_SCAN_PAYLOAD_CACHE: dict[tuple[object, ...], tuple[datetime, dict[str, object]]] = {}
_SCAN_INFLIGHT: dict[tuple[object, ...], Future] = {}
_SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan-refresh")
SCAN_INTERVALS = {"15m", "1h", "4h", "1d"}
SCAN_VIEW_MODES = {"cards", "table"}
AUTOTRADE_MODES = {"paper", "live"}
X_ACCOUNT_MODES = {"off", "blend", "only"}
X_PROVIDERS = {"official_api", "nitter_rss", "session_scrape"}
FEE_MODELS = {"flat", "maker_taker"}
FEE_SOURCES = {"manual", "account", "symbol"}
FEE_ROLES = {"maker", "taker"}
SLIPPAGE_MODELS = {"fixed", "dynamic"}
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
    _validate_choice(config.x_account_mode, "X Account Mode", X_ACCOUNT_MODES)
    _validate_choice(config.x_provider, "X Provider", X_PROVIDERS)
    _validate_choice(config.market_data_preset, "Market Data Preset", MARKET_DATA_PRESETS)
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
    return {
        "binance_recv_window_ms": config.binance_recv_window_ms,
        "okx_auth_configured": bool(config.okx_api_key and config.okx_api_secret and config.okx_api_passphrase),
        "market_data_preset": config.market_data_preset,
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
    return {
        "binance_auth_configured": bool(config.binance_api_key and config.binance_api_secret),
        "binance_auth_label": "API key + secret 已配置" if config.binance_api_key and config.binance_api_secret else "未配置",
        "okx_auth_configured": bool(config.okx_api_key and config.okx_api_secret and config.okx_api_passphrase),
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
        if not (runtime_config.binance_api_key and runtime_config.binance_api_secret):
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
            "binance_private_auth_configured": bool(runtime_config.binance_api_key and runtime_config.binance_api_secret),
            "okx_private_connector": "configured_pending_connector"
            if runtime_config.okx_api_key and runtime_config.okx_api_secret and runtime_config.okx_api_passphrase
            else "not_configured",
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


def _serialize_trading_position(position: TradingPosition) -> dict[str, object]:
    return {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "entry_price": position.entry_price,
        "quote_notional": position.quote_notional,
        "score": position.score,
        "grade": position.grade,
        "opened_at": position.opened_at.isoformat(),
        "stop_price": position.stop_price,
        "take_profit_price": position.take_profit_price,
        "mode": position.mode,
        "client_order_id": position.client_order_id,
    }


def _serialize_trading_event(event: TradingEvent) -> dict[str, object]:
    return {
        "action": event.action,
        "symbol": event.symbol,
        "mode": event.mode,
        "status": event.status,
        "message": event.message,
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


def _serialize_trading_report(report: TradingRunReport) -> dict[str, object]:
    return {
        "enabled": report.enabled,
        "mode": report.mode,
        "scanned_symbols": report.scanned_symbols,
        "returned_signals": report.returned_signals,
        "open_positions": [_serialize_trading_position(position) for position in report.open_positions],
        "events": [_serialize_trading_event(event) for event in report.events],
        "generated_at": report.generated_at.isoformat(),
    }


def _trading_status_payload() -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    store = _trading_store()
    positions = store.load()
    events = store.load_events()
    return {
        "config": _to_jsonable(runtime_config.autotrade_defaults),
        "readiness": _trading_readiness_payload(),
        "open_positions": [_serialize_trading_position(position) for position in positions],
        "events": [_serialize_trading_event(event) for event in events[-30:]],
    }


def _exchange_auth_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    binance_status = scanner.gateway.account_status({runtime_config.scan_defaults.quote_asset})
    okx_configured = bool(runtime_config.okx_api_key and runtime_config.okx_api_secret and runtime_config.okx_api_passphrase)
    return {
        "binance": binance_status,
        "okx": {
            "exchange": "OKX",
            "configured": okx_configured,
            "authenticated": False,
            "can_trade": False,
            "status": "configured_pending_connector" if okx_configured else "not_configured",
            "message": "OKX 凭据已保存，但当前版本尚未接入 OKX 私有交易接口。" if okx_configured else "OKX API Key / Secret / Passphrase 未配置。",
            "balances": [],
            "quote_available": 0.0,
        },
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


def _trading_readiness_payload(*, check_account: bool | None = None) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    config = runtime_config.autotrade_defaults
    has_configured_credentials = bool(runtime_config.binance_api_key and runtime_config.binance_api_secret)
    should_check_account = check_account if check_account is not None else (config.mode == "live" and not config.order_test_only)
    if should_check_account:
        binance_status = scanner.gateway.account_status({runtime_config.scan_defaults.quote_asset})
    else:
        binance_status = _local_binance_auth_status(has_configured_credentials)
    live_confirmed = os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE
    has_credentials = bool(binance_status.get("configured"))
    authenticated = bool(binance_status.get("authenticated"))
    can_trade = bool(binance_status.get("can_trade"))
    quote_available = float(binance_status.get("quote_available") or 0.0)
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
            blockers.append("Binance API key/secret 未配置")
        if has_credentials and not authenticated:
            blockers.append("Binance 账户认证失败")
        if authenticated and not can_trade:
            blockers.append("Binance API 未开启交易权限")
        if not live_confirmed:
            blockers.append(f"缺少环境变量 AI_TRADE_LIVE_CONFIRM={LIVE_CONFIRM_VALUE}")
        if authenticated and quote_available < config.quote_order_qty:
            blockers.append(f"{runtime_config.scan_defaults.quote_asset} 可用余额不足")
    return {
        "mode": config.mode,
        "enabled": config.enabled,
        "order_test_only": config.order_test_only,
        "live_ready": live_ready,
        "live_confirmed": live_confirmed,
        "quote_asset": runtime_config.scan_defaults.quote_asset,
        "quote_order_qty": config.quote_order_qty,
        "quote_available": quote_available,
        "account_check_performed": should_check_account,
        "exchange_status": binance_status,
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
    for event in _trading_store().load_events()[-30:]:
        if event.status in {"blocked", "risk_blocked", "rejected", "auth_failed"} and _event_created_at_utc(event) >= cutoff:
            count += 1
    return count


def _layout_context(readiness: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "market_ticker": _market_ticker_payload(),
        "alert_count": _alert_count_payload(readiness),
    }


def _run_trading_once(*, force_paper: bool = False) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    autotrade_config = runtime_config.autotrade_defaults
    if force_paper:
        autotrade_config = replace(
            autotrade_config,
            enabled=True,
            mode="paper",
            order_test_only=True,
        )
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
            )
            _trading_store().append_events([event])
            return _serialize_trading_report(
                TradingRunReport(
                    enabled=autotrade_config.enabled,
                    mode=autotrade_config.mode,
                    scanned_symbols=0,
                    returned_signals=0,
                    open_positions=positions,
                    events=[event],
                )
            )
    risk_snapshot = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS).snapshot()
    blocked_symbols = risk_snapshot.execution_risk.blocked_symbols
    trader = AutoTrader(scanner=scanner, state_store=_trading_store(), blocked_symbols=blocked_symbols)
    return _serialize_trading_report(trader.run_once(autotrade_config))


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


def _terminal_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    cached_payload = _cached_terminal_payload()
    if cached_payload is not None:
        return cached_payload
    cache_key = _terminal_cache_key(runtime_config)
    with _TERMINAL_CACHE_LOCK:
        cached_payload = _cached_terminal_payload()
        if cached_payload is not None:
            return cached_payload
        hub = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS)
        payload = {
            **_serialize_intelligence_snapshot(hub.snapshot()),
            "platform": _platform_payload(),
        }
        _TERMINAL_CACHE.update(
            {
                "key": cache_key,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=TERMINAL_SNAPSHOT_TTL_SECONDS),
                "payload": payload,
            }
        )
        return payload


def _read_filtered_spreads(runtime_config: RuntimeConfig) -> list[object]:
    return [
        item
        for item in sorted(IntelligenceHub._read_spread_csv(SETTINGS.futures_basis_csv), key=lambda candidate: abs(candidate.spread_bps), reverse=True)
        if abs(item.spread_bps) >= runtime_config.intelligence_defaults.min_spread_bps
    ][:10]


def _fast_market_module_payload() -> dict[str, object]:
    cached = _cached_terminal_payload()
    if cached is not None:
        return {
            "module": "market",
            "intel_items": cached["intel_items"],
            "spreads": cached["spreads"],
            "strategy_hits": cached["strategy_hits"],
            "cached": True,
        }
    runtime_config, _ = APP_STATE.snapshot()
    ticker_payload = _market_ticker_payload()
    intel_items = []
    for item in ticker_payload.get("items", []):
        if not isinstance(item, dict):
            continue
        change_pct = float(item.get("change_pct") or 0.0)
        quote_volume = float(item.get("quote_volume") or 0.0)
        symbol = str(item.get("symbol") or "")
        intel_items.append(
            {
                "source": "binance",
                "symbol": symbol,
                "title": f"{symbol} 24h 涨跌幅 {change_pct:+.2f}%，成交额 {quote_volume:,.0f}",
                "category": "market_ticker",
                "severity": min(95.0, 45.0 + abs(change_pct) * 4),
                "sentiment": 0.6 if change_pct >= 0 else -0.4,
                "url": "",
            }
        )
    return {
        "module": "market",
        "intel_items": intel_items,
        "spreads": _to_jsonable(_read_filtered_spreads(runtime_config)),
        "strategy_hits": [],
        "cached": False,
        "warning": "完整技术指标扫描仍在 /api/scan；此模块优先返回实时 ticker 轻量视图以避免 UI 阻塞。",
    }


def _community_only_module_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    hub = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS)
    intel_items = IntelligenceHub._read_exchange_intel_csv(SETTINGS.exchange_intel_csv)
    return {
        "module": "community",
        "twitter_accounts": _to_jsonable(hub._build_twitter_accounts()),
        "intel_items": _to_jsonable(
            [
                item
                for item in sorted(intel_items, key=lambda candidate: candidate.severity, reverse=True)
                if item.severity >= runtime_config.intelligence_defaults.min_intel_severity
            ][:12]
        ),
    }


def _basis_only_module_payload() -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    spreads = _read_filtered_spreads(runtime_config)
    return {
        "module": "basis",
        "spreads": _to_jsonable(spreads),
        "risk_rules": _platform_payload()["risk_rules"],
    }


def _fast_strategies_module_payload() -> dict[str, object]:
    platform = _platform_payload()
    cached = _cached_terminal_payload()
    return {
        "module": "strategies",
        "strategy_hits": cached["strategy_hits"] if cached is not None else [],
        "strategies": platform["strategies"],
        "cached": cached is not None,
        "warning": "" if cached is not None else "等待完整扫描前先展示策略配置；运行 /api/scan 后会出现实时命中。",
    }


def _fast_risk_module_payload() -> dict[str, object]:
    platform = _platform_payload()
    cached = _cached_terminal_payload()
    if cached is not None:
        return {
            "module": "risk",
            "execution_risk": cached["execution_risk"],
            "risk_rules": platform["risk_rules"],
            "cached": True,
        }
    return {
        "module": "risk",
        "execution_risk": {
            "status": "pending_scan",
            "risk_score": 0.0,
            "allowed_symbols": [],
            "blocked_symbols": {},
            "summary": "完整扫描尚未完成，当前仅展示静态风控规则。",
        },
        "risk_rules": platform["risk_rules"],
        "cached": False,
        "warning": "运行 /api/scan 或打开完整终端快照后会刷新执行前风控。",
    }


def _onchain_only_module_payload(error: str = "") -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    threshold = runtime_config.intelligence_defaults.whale_transfer_threshold_usd
    cache_key = (
        runtime_config.onchain_data_preset,
        runtime_config.onchain_api_base_url,
        threshold,
    )
    now = datetime.now(timezone.utc)
    if not error:
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
    events = IntelligenceHub._read_onchain_csv(SETTINGS.onchain_events_csv)
    if runtime_config.onchain_data_preset == "open_multichain_keyless":
        try:
            events.extend(
                _to_jsonable(item)
                for item in OpenMultiChainOnchainProvider(
                    whale_threshold_usd=threshold,
                    base_url_override=runtime_config.onchain_api_base_url,
                ).fetch_events(list(DEFAULT_ONCHAIN_SYMBOLS), {})
            )
        except Exception:  # noqa: BLE001
            pass
    serializable_events = [
        _to_jsonable(event)
        for event in sorted(events, key=lambda candidate: float(candidate["severity"] if isinstance(candidate, dict) else candidate.severity), reverse=True)
        if (
            float(event["amount_usd"] if isinstance(event, dict) else event.amount_usd) >= threshold
            or float(event["severity"] if isinstance(event, dict) else event.severity) >= 45
        )
    ][:10]
    payload = {
        "module": "onchain",
        "onchain_events": serializable_events,
        "blocked_symbols": {},
        "fallback": bool(error),
        "warning": error,
    }
    if not error:
        with _ONCHAIN_MODULE_CACHE_LOCK:
            _ONCHAIN_MODULE_CACHE.update(
                {
                    "key": cache_key,
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=TERMINAL_SNAPSHOT_TTL_SECONDS),
                    "payload": payload,
                }
            )
    return payload


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


def _run_scan_payload(scanner: object, params: dict[str, object]) -> dict[str, object]:
    summary, signals = scanner.scan(
        quote_asset=str(params["quote_asset"]),
        interval=str(params["interval"]),
        candidate_pool=int(params["candidate_pool"]),
        min_quote_volume=float(params["min_quote_volume"]),
        min_trade_count=int(params["min_trade_count"]),
    )
    return {
        "summary": _to_jsonable(summary),
        "signals": [format_signal_row(signal) for signal in signals],
        "cached": False,
        "fallback": False,
    }


def _complete_scan_future(cache_key: tuple[object, ...], future: Future) -> None:
    try:
        payload = future.result()
    except Exception:  # noqa: BLE001
        payload = None
    with _SCAN_CACHE_LOCK:
        _SCAN_INFLIGHT.pop(cache_key, None)
    if isinstance(payload, dict):
        _store_scan_payload(cache_key, payload)


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
    signals = []
    for ticker in tickers[: int(params["candidate_pool"])]:
        score = min(82.0, 50.0 + abs(ticker.price_change_percent) * 3 + min(ticker.quote_volume / 1_000_000_000, 10.0))
        signals.append(
            {
                "symbol": ticker.symbol,
                "score": round(score, 2),
                "grade": "B" if score >= 70 else "C",
                "reasons": ["实时 ticker 快速返回", f"24h 成交额 {ticker.quote_volume / 1_000_000:.1f}M"],
                "warnings": [warning],
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
            "scanned_symbols": len(tickers),
            "returned_signals": len(signals),
            "min_quote_volume": float(params["min_quote_volume"]),
            "min_trade_count": int(params["min_trade_count"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
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
    _store_scan_payload(cache_key, payload)
    return payload, params


def _get_first(query: dict[str, list[str]], key: str, default: str) -> str:
    return query.get(key, [default])[0]


def _parse_bool_flag(query: dict[str, list[str]], key: str) -> bool:
    return key in query and _get_first(query, key, "") not in {"", "0", "false", "False"}


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
        return _empty_backtest_payload(params), params, "没有匹配到任何 ZIP 文件。"

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
            enabled=_parse_bool_flag(form, "autotrade_enabled"),
            mode=_get_first(form, "autotrade_mode", current_config.autotrade_defaults.mode).strip() or "paper",
            quote_order_qty=_parse_float_value(_get_first(form, "autotrade_quote_order_qty", str(current_config.autotrade_defaults.quote_order_qty)), "Auto Trade Quote Order Qty"),
            max_open_positions=_parse_int_value(_get_first(form, "autotrade_max_open_positions", str(current_config.autotrade_defaults.max_open_positions)), "Auto Trade Max Open Positions"),
            max_total_quote_exposure=_parse_float_value(_get_first(form, "autotrade_max_total_quote_exposure", str(current_config.autotrade_defaults.max_total_quote_exposure)), "Auto Trade Max Exposure"),
            score_threshold=_parse_float_value(_get_first(form, "autotrade_score_threshold", str(current_config.autotrade_defaults.score_threshold)), "Auto Trade Score Threshold"),
            min_volume_ratio=_parse_float_value(_get_first(form, "autotrade_min_volume_ratio", str(current_config.autotrade_defaults.min_volume_ratio)), "Auto Trade Min Volume Ratio"),
            min_buy_pressure=_parse_float_value(_get_first(form, "autotrade_min_buy_pressure", str(current_config.autotrade_defaults.min_buy_pressure)), "Auto Trade Min Buy Pressure"),
            stop_loss_pct=_parse_float_value(_get_first(form, "autotrade_stop_loss_pct", str(current_config.autotrade_defaults.stop_loss_pct)), "Auto Trade Stop Loss"),
            take_profit_pct=_parse_float_value(_get_first(form, "autotrade_take_profit_pct", str(current_config.autotrade_defaults.take_profit_pct)), "Auto Trade Take Profit"),
            cooldown_minutes=_parse_int_value(_get_first(form, "autotrade_cooldown_minutes", str(current_config.autotrade_defaults.cooldown_minutes)), "Auto Trade Cooldown"),
            order_test_only=_parse_bool_flag(form, "autotrade_order_test_only"),
        ),
        intelligence_defaults=IntelligenceDefaults(
            enabled=_parse_bool_flag(form, "intelligence_enabled"),
            llm_enabled=_parse_bool_flag(form, "intelligence_llm_enabled"),
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
            no_binance_discount=_parse_bool_flag(form, "backtest_no_binance_discount"),
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
            no_kdj_confirmation=_parse_bool_flag(form, "backtest_no_kdj_confirmation"),
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
                payload = _terminal_payload()
                html = render_terminal_page(payload, lang=lang, layout_context=_layout_context())
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path.startswith("/terminal/"):
                module = parsed.path.removeprefix("/terminal/").strip("/")
                if module in {"market", "community", "onchain", "basis", "strategies", "trading", "risk"}:
                    html = render_terminal_module_page(
                        snapshot=_terminal_payload(),
                        module=module,
                        trading_status=_trading_status_payload() if module == "trading" else None,
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

            if parsed.path.startswith("/api/terminal/modules/"):
                module = parsed.path.removeprefix("/api/terminal/modules/").strip("/")
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

            if parsed.path == "/api/backtest/presets":
                self._send_text(
                    json.dumps({"presets": list_backtest_presets()}, ensure_ascii=False, indent=2),
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
                    snapshot=_terminal_payload(),
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
                    snapshot=_terminal_payload(),
                    module="trading",
                    trading_status=_trading_status_payload(),
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
