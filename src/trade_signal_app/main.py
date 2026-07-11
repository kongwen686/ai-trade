from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass, replace
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import os
from threading import Event, RLock, Thread
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

from . import __version__
from .app_state import AppState
from .backtest import resolve_execution_config_from_binance
from .binance_client import BinancePublicAPIError, parse_ticker
from .btc_signal import BTC_SYMBOL, build_btc_signal_summary
from .carry import (
    build_carry_market_snapshots,
    carry_position_from_payload,
    carry_position_mark_payload,
    run_carry_paper_cycle,
)
from .config import BASE_DIR, SETTINGS
from .entry_filters import anti_chase_reason_from_config, structure_adjusted_exit_prices, structure_entry_reason_from_config
from .feishu import FeishuNotificationError, FeishuTradeNotifier
from .intelligence import IntelligenceHub, IntelligenceSnapshot, LlmInsightClient
from .okx_client import OKXSpotGateway
from .onchain import DEFAULT_ONCHAIN_SYMBOLS, OPEN_MULTICHAIN_CONFIGS, OpenMultiChainOnchainProvider
from .platform import build_platform_snapshot, okx_credential_state
from .presets import get_strategy_template, list_backtest_presets, list_strategy_templates
from .runtime_config import AutoTradeDefaults, RuntimeConfig
from . import main_settings as settings_handlers
from . import main_backtest as backtest_handlers
from . import main_scan as scan_handlers
from .main_request_body import _read_body, _strategy_description_from_body
from .storage import LocalDataStore
from .stat_arb import PairStatArbConfig, run_pair_stat_arb_from_archives
from .strategy_builder import compile_strategy, compile_strategy_template
from .time_utils import APP_TIMEZONE, now_app_time
from .volatility import volatility_entry_reason
from .trading import (
    AutoTrader,
    FILLED_TRADE_STATUSES,
    LIVE_CONFIRM_VALUE,
    TRADE_EVENT_ACTIONS,
    TradingEvent,
    TradingPosition,
    TradingRunReport,
    TradingStateStore,
)
from .views import normalize_language, render_backtest_page, render_btc_signal_page, render_index_page, render_settings_page, render_terminal_module_page, render_terminal_page, render_trading_page

RUNTIME_CONFIG_PATH = BASE_DIR / "data" / "runtime_config.json"
TRADING_STATE_PATH = BASE_DIR / "data" / "trading_state.json"
LOCAL_DATABASE_PATH = BASE_DIR / "data" / "ai_trade.sqlite3"
TRADINGVIEW_CACHE_DIR = BASE_DIR / "data" / "tradingview_klines"
APP_STATE = AppState(SETTINGS, RUNTIME_CONFIG_PATH)
MARKET_TICKER_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
TERMINAL_SNAPSHOT_TTL_SECONDS = 45
TERMINAL_SYNC_TIMEOUT_SECONDS = 1.2
ONCHAIN_SYNC_TIMEOUT_SECONDS = 6.0
ONCHAIN_WORKBENCH_SYNC_TIMEOUT_SECONDS = 6.0
LLM_WORKBENCH_TIMEOUT_SECONDS = 8
OKX_GATEWAY_TIMEOUT_SECONDS = 5
TERMINAL_MODULES = {"market", "community", "onchain", "basis", "strategies", "trading", "risk"}
_TERMINAL_CACHE_LOCK = RLock()
_TERMINAL_CACHE: dict[str, object] = {"key": None, "expires_at": datetime.min.replace(tzinfo=APP_TIMEZONE), "payload": None}
_TERMINAL_INFLIGHT: dict[tuple[object, ...], Future] = {}
_TERMINAL_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="terminal-refresh")
_ONCHAIN_MODULE_CACHE_LOCK = RLock()
_ONCHAIN_MODULE_CACHE: dict[str, object] = {"key": None, "expires_at": datetime.min.replace(tzinfo=APP_TIMEZONE), "payload": None}
_ONCHAIN_INFLIGHT: dict[tuple[object, ...], Future] = {}
_ONCHAIN_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="onchain-refresh")
_BACKTEST_JOB_LOCK = RLock()
_BACKTEST_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtest-job")
_BACKTEST_JOBS: dict[str, dict[str, object]] = {}
_BACKTEST_JOB_RESULTS: dict[str, tuple[dict[str, object], dict[str, object], str | None]] = {}
BACKTEST_JOB_HISTORY_LIMIT = 20
BACKTEST_JOB_ACTIVE_LIMIT = 3
PAPER_AUTO_DEFAULT_INTERVAL_SECONDS = 300
PAPER_AUTO_MIN_INTERVAL_SECONDS = 30
FEISHU_DAILY_REPORT_HOUR = 22
FEISHU_DAILY_REPORT_MINUTE = 0
FEISHU_DAILY_REPORT_RETRY_SECONDS = 300
FEISHU_DAILY_REPORT_HEARTBEAT_SECONDS = 60
FEISHU_DAILY_REPORT_CATCHUP_WINDOW = timedelta(hours=12)
FEISHU_DAILY_SUMMARY_CHANNEL = "feishu_daily_summary"
FEISHU_BTC_SIGNAL_CHANNEL = "feishu_btc_signal"
TRADING_STATUS_FILLED_EVENT_LIMIT = 5000
TRADING_STATUS_DIAGNOSTIC_EVENT_LIMIT = 500
REALTIME_MARKET_MAX_SYMBOLS = 40
_PAPER_AUTO_LOCK = RLock()
_CARRY_PAPER_LOCK = RLock()
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
    "force_paper": True,
    "mode_label": "paper_only",
}
_FEISHU_DAILY_REPORT_LOCK = RLock()
_FEISHU_DAILY_REPORT_RUN_LOCK = RLock()
_FEISHU_DAILY_REPORT_STOP_EVENT: Event | None = None
_FEISHU_DAILY_REPORT_THREAD: Thread | None = None
_FEISHU_DAILY_REPORT_STATE: dict[str, object] = {
    "running": False,
    "last_sent_date": None,
    "last_btc_sent_date": None,
    "last_run_at": None,
    "last_error": "",
    "next_run_at": None,
    "last_result": None,
}
_validate_runtime_config = settings_handlers._validate_runtime_config
_scan_params_from_config = settings_handlers._scan_params_from_config
_backtest_params_from_config = settings_handlers._backtest_params_from_config
_settings_params_from_config = settings_handlers._settings_params_from_config


def _settings_status_from_config(config: RuntimeConfig) -> dict[str, object]:
    return settings_handlers._settings_status_from_config(
        config,
        storage_mode=APP_STATE.storage_mode_label(),
        tradingview_cache_dir=TRADINGVIEW_CACHE_DIR,
    )


def _settings_context() -> tuple[dict[str, object], dict[str, object]]:
    runtime_config, _ = APP_STATE.snapshot()
    return _settings_params_from_config(runtime_config), _settings_status_from_config(runtime_config)


def _import_runtime_config_template(form: dict[str, list[str]]) -> RuntimeConfig:
    current_config, _ = APP_STATE.snapshot()
    return settings_handlers._import_runtime_config_template(
        form,
        current_config=current_config,
        settings=SETTINGS,
    )


def _build_runtime_config(form: dict[str, list[str]]) -> RuntimeConfig:
    current_config, _ = APP_STATE.snapshot()
    return settings_handlers._build_runtime_config(form, current_config=current_config)


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
    try:
        database_status = store.database_status()
    except Exception as exc:  # noqa: BLE001
        database_status = {
            "path": str(LOCAL_DATABASE_PATH),
            "exists": LOCAL_DATABASE_PATH.exists(),
            "error": str(exc),
        }

    runtime_config_status = {
        "path": str(RUNTIME_CONFIG_PATH),
        "exists": RUNTIME_CONFIG_PATH.exists(),
        "storage_mode": APP_STATE.storage_mode_label(),
    }
    autotrade = runtime_config.autotrade_defaults
    live_confirmed = os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE
    blockers = []
    if autotrade.live_enabled and not autotrade.order_test_only:
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
        "generated_at": now_app_time().isoformat(),
        "runtime_config": runtime_config_status,
        "trading_state": trading_state_status,
        "database": database_status,
        "features": {
            "binance_public_market_data": True,
            "binance_public_market_websocket": True,
            "realtime_market_rest_fallback": True,
            "tradingview_unofficial_market_data": True,
            "binance_private_auth_configured": bool(runtime_config.binance_api_key and runtime_config.binance_api_secret),
            "okx_private_connector": okx_state["status"],
            "autotrade_execution_exchange": runtime_config.autotrade_defaults.execution_exchange,
            "autotrade_paper_enabled": runtime_config.autotrade_defaults.paper_enabled,
            "autotrade_live_enabled": runtime_config.autotrade_defaults.live_enabled,
            "volatility_regime_filter": runtime_config.autotrade_defaults.volatility_filter_enabled,
            "carry_paper_engine": True,
            "carry_paper_entries_enabled": runtime_config.carry_paper_defaults.enabled,
            "pair_stat_arb_backtest": True,
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
            "paper_enabled": autotrade.paper_enabled,
            "live_enabled": autotrade.live_enabled,
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
    return TradingStateStore(TRADING_STATE_PATH, database_path=LOCAL_DATABASE_PATH)


def _local_data_store() -> LocalDataStore:
    return LocalDataStore(LOCAL_DATABASE_PATH)


def _carry_paper_status_payload() -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    config = runtime_config.carry_paper_defaults
    store = _local_data_store()
    positions = [
        carry_position_from_payload(payload)
        for payload in store.load_carry_paper_position_payloads()
    ]
    events = store.load_carry_paper_event_payloads(limit=5000)
    closed_events = [event for event in events if str(event.get("action") or "").upper() == "CLOSE"]
    position_payloads = [
        _to_jsonable(carry_position_mark_payload(position, config))
        for position in positions
    ]
    realized_pnl = sum(float(event.get("realized_pnl") or 0.0) for event in closed_events)
    winning_trades = sum(1 for event in closed_events if float(event.get("realized_pnl") or 0.0) > 0)
    return {
        "enabled": config.enabled,
        "mode": "paper",
        "research_only": True,
        "execution_boundary": "public market data -> local simulation -> SQLite; no exchange order gateway",
        "config": _to_jsonable(config),
        "open_positions": position_payloads,
        "recent_events": events[:50],
        "metrics": {
            "open_positions": len(positions),
            "gross_exposure": round(sum(position.notional_per_leg * 2 for position in positions), 8),
            "unrealized_pnl": round(
                sum(float(payload.get("net_pnl") or 0.0) for payload in position_payloads if isinstance(payload, dict)),
                8,
            ),
            "closed_trades": len(closed_events),
            "winning_trades": winning_trades,
            "win_rate_pct": round((winning_trades / len(closed_events)) * 100, 2) if closed_events else 0.0,
            "realized_pnl": round(realized_pnl, 8),
            "funding_pnl": round(sum(float(event.get("funding_pnl") or 0.0) for event in closed_events), 8),
            "costs": round(
                sum(float(event.get("costs") or 0.0) for event in closed_events)
                + sum(position.entry_cost for position in positions),
                8,
            ),
        },
    }


def _run_carry_paper_once(
    *,
    market_sections: dict[str, object] | None = None,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    sections = market_sections or _realtime_market_sections(runtime_config, scanner)
    spreads = [item for item in sections.get("spreads", []) if isinstance(item, dict)]
    funding_rates = [item for item in sections.get("funding_rates", []) if isinstance(item, dict)]
    snapshots = build_carry_market_snapshots(
        spreads,
        funding_rates,
        observed_at=observed_at,
    )
    with _CARRY_PAPER_LOCK:
        store = _local_data_store()
        positions = [
            carry_position_from_payload(payload)
            for payload in store.load_carry_paper_position_payloads()
        ]
        report = run_carry_paper_cycle(
            snapshots=snapshots,
            positions=positions,
            config=runtime_config.carry_paper_defaults,
        )
        store.replace_carry_paper_positions(
            [payload for payload in _to_jsonable(report.positions) if isinstance(payload, dict)]
        )
        store.append_carry_paper_events(
            [payload for payload in _to_jsonable(report.events) if isinstance(payload, dict)]
        )
        payload = _to_jsonable(report)
        if isinstance(payload, dict):
            payload["warning"] = str(sections.get("warning") or "")
            payload["status"] = _carry_paper_status_payload()
    return payload if isinstance(payload, dict) else {}


def _stat_arb_defaults_payload() -> dict[str, object]:
    return {
        "strategy": "pair_stat_arb",
        "research_only": True,
        "config": _to_jsonable(PairStatArbConfig()),
        "input": {
            "archive_a": "One symbol/interval CSV, ZIP, directory, or glob pattern.",
            "archive_b": "A second symbol with the same interval and overlapping timestamps.",
        },
        "execution_model": "signal at aligned close; fill at next aligned open; no exchange orders",
    }


def _stat_arb_config_from_payload(payload: dict[str, object]) -> PairStatArbConfig:
    defaults = PairStatArbConfig()
    return PairStatArbConfig(
        lookback_bars=int(payload.get("lookback_bars", defaults.lookback_bars)),
        entry_z=float(payload.get("entry_z", defaults.entry_z)),
        exit_z=float(payload.get("exit_z", defaults.exit_z)),
        stop_z=float(payload.get("stop_z", defaults.stop_z)),
        max_holding_bars=int(payload.get("max_holding_bars", defaults.max_holding_bars)),
        min_correlation=float(payload.get("min_correlation", defaults.min_correlation)),
        max_hedge_ratio=float(payload.get("max_hedge_ratio", defaults.max_hedge_ratio)),
        notional_per_leg=float(payload.get("notional_per_leg", defaults.notional_per_leg)),
        initial_equity=float(payload.get("initial_equity", defaults.initial_equity)),
        fee_bps_per_leg=float(payload.get("fee_bps_per_leg", defaults.fee_bps_per_leg)),
        slippage_bps_per_leg=float(payload.get("slippage_bps_per_leg", defaults.slippage_bps_per_leg)),
    )


def _run_stat_arb_backtest_payload(payload: dict[str, object]) -> dict[str, object]:
    archive_a = str(payload.get("archive_a") or payload.get("archives_a") or "").strip()
    archive_b = str(payload.get("archive_b") or payload.get("archives_b") or "").strip()
    if not archive_a or not archive_b:
        raise ValueError("配对回测需要同时提供 archive_a 和 archive_b。")
    config = _stat_arb_config_from_payload(payload)
    params = {
        "archive_a": archive_a,
        "archive_b": archive_b,
        "config": _to_jsonable(config),
    }
    try:
        report, sources = run_pair_stat_arb_from_archives(
            archive_a=archive_a,
            archive_b=archive_b,
            config=config,
        )
    except ValueError as exc:
        _local_data_store().record_research_backtest_run(
            strategy="pair_stat_arb",
            params=params,
            payload={},
            error=str(exc),
        )
        raise
    report_payload = _to_jsonable(report)
    result = {
        "params": params,
        "sources": sources,
        "report": report_payload,
    }
    run_uid = _local_data_store().record_research_backtest_run(
        strategy="pair_stat_arb",
        params=params,
        payload=result,
    )
    result["run_uid"] = run_uid
    return result


def _mapping_from_request_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    raw = _read_body(handler)
    if "application/json" in handler.headers.get("Content-Type", ""):
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 请求体无效。") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON 请求体根节点必须是对象。")
        return payload
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in parse_qs(raw).items()
    }


def _record_backtest_run(params: dict[str, object], payload: dict[str, object], error: str | None) -> None:
    try:
        _local_data_store().record_backtest_run(params=params, payload=payload, error=error)
    except Exception:  # noqa: BLE001
        return


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


def _feishu_trade_notifier(runtime_config: RuntimeConfig) -> FeishuTradeNotifier | None:
    webhook_url = runtime_config.feishu_webhook_url.strip()
    if not webhook_url:
        return None
    return FeishuTradeNotifier(webhook_url)


def _notify_trade_event(
    notifier: FeishuTradeNotifier | None,
    *,
    event: TradingEvent,
    position: TradingPosition | None = None,
) -> None:
    if notifier is None:
        return
    try:
        notifier.notify_trade(event=event, position=position)
    except FeishuNotificationError as exc:
        print(f"Feishu trade notification failed for {event.action} {event.symbol}: {exc}")


def _live_prices_for_symbols(scanner: object, symbols: set[str] | list[str] | tuple[str, ...]) -> dict[str, float]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized_symbol = str(symbol).upper().strip()
        if normalized_symbol and normalized_symbol not in seen:
            normalized.append(normalized_symbol)
            seen.add(normalized_symbol)
    if not normalized:
        return {}

    gateway = getattr(scanner, "gateway", None)
    prices: dict[str, float] = {}
    ticker_prices = getattr(gateway, "ticker_prices", None)
    if callable(ticker_prices):
        try:
            for symbol, price in (ticker_prices(normalized) or {}).items():
                normalized_symbol = str(symbol).upper()
                parsed_price = float(price)
                if normalized_symbol in seen and parsed_price > 0:
                    prices[normalized_symbol] = parsed_price
        except Exception:  # noqa: BLE001
            prices = {}

    missing_symbols = [symbol for symbol in normalized if symbol not in prices]
    ticker_price = getattr(gateway, "ticker_price", None)
    if missing_symbols and callable(ticker_price):
        for symbol in list(missing_symbols):
            try:
                parsed_price = float(ticker_price(symbol))
            except Exception:  # noqa: BLE001
                continue
            if parsed_price > 0:
                prices[symbol] = parsed_price
        missing_symbols = [symbol for symbol in normalized if symbol not in prices]

    ticker24hr_symbols = getattr(gateway, "ticker24hr_symbols", None)
    if missing_symbols and callable(ticker24hr_symbols):
        try:
            for row in ticker24hr_symbols(missing_symbols):
                symbol = str(row.get("symbol", "")).upper()
                if symbol in missing_symbols:
                    parsed_price = float(row["lastPrice"])
                    if parsed_price > 0:
                        prices[symbol] = parsed_price
        except Exception:  # noqa: BLE001
            pass
        missing_symbols = [symbol for symbol in normalized if symbol not in prices]

    cached_ticker24hr = getattr(gateway, "cached_ticker24hr", None)
    if missing_symbols and callable(cached_ticker24hr):
        try:
            cached_rows = cached_ticker24hr() or []
        except Exception:  # noqa: BLE001
            cached_rows = []
        for row in cached_rows:
            try:
                ticker = parse_ticker(row)
            except (KeyError, TypeError, ValueError):
                continue
            symbol = ticker.symbol.upper()
            if symbol in missing_symbols and ticker.last_price > 0:
                prices[symbol] = ticker.last_price
    return prices


def _realtime_market_symbols(query: dict[str, list[str]]) -> list[str]:
    raw_values = query.get("symbols", [])
    symbols: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        for value in str(raw_value).replace("\n", ",").split(","):
            symbol = value.strip().upper()
            if not symbol or symbol in seen:
                continue
            if not symbol.isalnum():
                raise ValueError(f"无效实时行情标的：{symbol}")
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        symbols = list(MARKET_TICKER_SYMBOLS)
    if len(symbols) > REALTIME_MARKET_MAX_SYMBOLS:
        raise ValueError(f"实时行情单次最多查询 {REALTIME_MARKET_MAX_SYMBOLS} 个标的。")
    return symbols


def _realtime_market_payload(query: dict[str, list[str]]) -> dict[str, object]:
    symbols = _realtime_market_symbols(query)
    _, scanner = APP_STATE.snapshot()
    gateway = getattr(scanner, "gateway", scanner)
    prices = _live_prices_for_symbols(scanner, symbols)
    changes: dict[str, float] = {}
    ticker24hr_symbols = getattr(gateway, "ticker24hr_symbols", None)
    if callable(ticker24hr_symbols):
        try:
            for row in ticker24hr_symbols(symbols):
                ticker = parse_ticker(row)
                if ticker.symbol.upper() in symbols:
                    changes[ticker.symbol.upper()] = ticker.price_change_percent
        except Exception:  # noqa: BLE001
            changes = {}
    items = [
        {
            "symbol": symbol,
            "price": prices[symbol],
            "change_pct": changes.get(symbol),
        }
        for symbol in symbols
        if symbol in prices
    ]
    return {
        "generated_at": now_app_time().isoformat(),
        "source": "binance_spot_rest",
        "read_only": True,
        "requested_symbols": len(symbols),
        "returned_symbols": len(items),
        "items": items,
    }


def _live_price_for_symbol(scanner: object, symbol: str, fallback: float = 0.0) -> float:
    normalized = symbol.upper().strip()
    live_price = _live_prices_for_symbols(scanner, [normalized]).get(normalized)
    return live_price if live_price and live_price > 0 else fallback


def _build_btc_signal_summary(
    now: datetime | None = None,
    *,
    include_backtests: bool = True,
) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    return build_btc_signal_summary(
        cache_root=TRADINGVIEW_CACHE_DIR,
        exchange=runtime_config.tradingview_exchange or "BINANCE",
        generated_at=now,
        include_backtests=include_backtests,
        market_price=_live_price_for_symbol(scanner, BTC_SYMBOL),
    )


def _notify_btc_signal(
    notifier: FeishuTradeNotifier | None,
    *,
    summary: dict[str, object],
) -> bool:
    if notifier is None:
        return False
    try:
        return notifier.notify_btc_signal(summary=summary)
    except FeishuNotificationError as exc:
        print(f"Feishu BTC signal notification failed: {exc}")
        return False


def _btc_signal_payload(query: dict[str, list[str]] | None = None) -> dict[str, object]:
    query = query or {}
    include_backtests = not _parse_bool_flag(query, "fast")
    return {"summary": _build_btc_signal_summary(include_backtests=include_backtests)}


def _push_btc_signal_payload(query: dict[str, list[str]] | None = None) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    notifier = _feishu_trade_notifier(runtime_config)
    payload = _btc_signal_payload(query)
    sent = _notify_btc_signal(notifier, summary=payload["summary"])
    return {**payload, "sent": bool(sent), "reason": "sent" if sent else "not_configured_or_failed"}


def _next_feishu_daily_report_at(now: datetime | None = None) -> datetime:
    current = (now or now_app_time()).astimezone(APP_TIMEZONE)
    target = current.replace(
        hour=FEISHU_DAILY_REPORT_HOUR,
        minute=FEISHU_DAILY_REPORT_MINUTE,
        second=0,
        microsecond=0,
    )
    if current > target:
        target += timedelta(days=1)
    return target


def _feishu_notification_key(channel: str, report_date: str) -> str:
    return f"{channel}:{report_date}"


def _load_feishu_delivery(channel: str, report_date: str) -> dict[str, object] | None:
    try:
        return _local_data_store().load_notification_delivery(_feishu_notification_key(channel, report_date))
    except Exception as exc:  # noqa: BLE001
        with _FEISHU_DAILY_REPORT_LOCK:
            _FEISHU_DAILY_REPORT_STATE["last_error"] = f"调度状态读取失败：{exc}"
        return None


def _record_feishu_delivery(
    channel: str,
    report_date: str,
    *,
    status: str,
    error: str = "",
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        return _local_data_store().record_notification_delivery(
            notification_key=_feishu_notification_key(channel, report_date),
            channel=channel,
            report_date=report_date,
            status=status,
            error=error,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        with _FEISHU_DAILY_REPORT_LOCK:
            _FEISHU_DAILY_REPORT_STATE["last_error"] = f"调度状态写入失败：{exc}"
        print(f"Feishu daily scheduler state persistence failed: {exc}", flush=True)
        return {}


def _feishu_delivery_sent(channel: str, report_date: str) -> bool:
    delivery = _load_feishu_delivery(channel, report_date)
    if delivery is not None:
        return delivery.get("status") == "sent"
    with _FEISHU_DAILY_REPORT_LOCK:
        state_key = "last_sent_date" if channel == FEISHU_DAILY_SUMMARY_CHANNEL else "last_btc_sent_date"
        return _FEISHU_DAILY_REPORT_STATE.get(state_key) == report_date


def _feishu_report_complete(report_date: str) -> bool:
    return _feishu_delivery_sent(FEISHU_DAILY_SUMMARY_CHANNEL, report_date) and _feishu_delivery_sent(
        FEISHU_BTC_SIGNAL_CHANNEL,
        report_date,
    )


def _pending_feishu_daily_report_at(now: datetime | None = None) -> datetime:
    current = (now or now_app_time()).astimezone(APP_TIMEZONE)
    today_target = current.replace(
        hour=FEISHU_DAILY_REPORT_HOUR,
        minute=FEISHU_DAILY_REPORT_MINUTE,
        second=0,
        microsecond=0,
    )
    previous_target = today_target - timedelta(days=1)

    candidate: datetime | None = None
    if current >= today_target:
        candidate = today_target
    elif current - previous_target <= FEISHU_DAILY_REPORT_CATCHUP_WINDOW:
        candidate = previous_target

    if candidate is not None and not _feishu_report_complete(candidate.date().isoformat()):
        return candidate

    next_target = _next_feishu_daily_report_at(current)
    if next_target <= current:
        next_target += timedelta(days=1)
    return next_target


def _feishu_daily_report_status_payload(now: datetime | None = None) -> dict[str, object]:
    current = (now or now_app_time()).astimezone(APP_TIMEZONE)
    runtime_config, _ = APP_STATE.snapshot()
    try:
        deliveries = _local_data_store().list_notification_deliveries(limit=10)
        storage_error = ""
    except Exception as exc:  # noqa: BLE001
        deliveries = []
        storage_error = str(exc)
    with _FEISHU_DAILY_REPORT_LOCK:
        state = dict(_FEISHU_DAILY_REPORT_STATE)
        thread_alive = _FEISHU_DAILY_REPORT_THREAD is not None and _FEISHU_DAILY_REPORT_THREAD.is_alive()
    return {
        **state,
        "running": bool(state.get("running") and thread_alive),
        "thread_alive": thread_alive,
        "webhook_configured": bool(runtime_config.feishu_webhook_url.strip()),
        "timezone": "UTC+8",
        "scheduled_time": f"{FEISHU_DAILY_REPORT_HOUR:02d}:{FEISHU_DAILY_REPORT_MINUTE:02d}",
        "retry_seconds": FEISHU_DAILY_REPORT_RETRY_SECONDS,
        "catchup_hours": FEISHU_DAILY_REPORT_CATCHUP_WINDOW.total_seconds() / 3600,
        "calculated_next_run_at": _pending_feishu_daily_report_at(current).isoformat(),
        "deliveries": deliveries,
        "storage_error": storage_error,
    }


def _manual_feishu_report_at(form: dict[str, list[str]]) -> datetime:
    report_date = _get_first(form, "report_date", "").strip()
    if report_date:
        try:
            parsed = datetime.strptime(report_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("report_date 必须使用 YYYY-MM-DD 格式。") from exc
        return parsed.replace(
            hour=FEISHU_DAILY_REPORT_HOUR,
            minute=FEISHU_DAILY_REPORT_MINUTE,
            second=0,
            microsecond=0,
            tzinfo=APP_TIMEZONE,
        )
    current = now_app_time()
    pending = _pending_feishu_daily_report_at(current)
    return pending if pending <= current else current


def _event_in_app_day(event: TradingEvent, start: datetime, end: datetime) -> bool:
    created_at = event.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=APP_TIMEZONE)
    created_at = created_at.astimezone(APP_TIMEZONE)
    return start <= created_at < end


def _build_feishu_daily_summary(now: datetime | None = None) -> dict[str, object]:
    generated_at = (now or now_app_time()).astimezone(APP_TIMEZONE)
    day_start = generated_at.replace(hour=0, minute=0, second=0, microsecond=0)
    runtime_config, scanner = APP_STATE.snapshot()
    warnings: list[str] = []

    try:
        scan_payload, _ = scan_handlers._scan_payload(
            {},
            runtime_config=runtime_config,
            scanner=scanner,
            force_refresh=True,
        )
    except Exception as exc:  # noqa: BLE001
        scan_payload = {"summary": {}, "signals": []}
        warnings.append(f"信号扫描统计失败：{exc}")
    scan_summary = scan_payload.get("summary") if isinstance(scan_payload.get("summary"), dict) else {}
    scan_signals = scan_payload.get("signals") if isinstance(scan_payload.get("signals"), list) else []

    try:
        store = _trading_store()
        positions = store.load()
        events = _sort_trading_events_desc(store.load_events())
        latest_prices = _latest_prices_for_open_positions(positions, scanner)
        account_metrics = _paper_account_metrics(positions=positions, events=events, latest_prices=latest_prices)
    except Exception as exc:  # noqa: BLE001
        positions = []
        events = []
        account_metrics = {}
        warnings.append(f"交易账户统计失败：{exc}")
    today_events = [event for event in events if _event_in_app_day(event, day_start, generated_at + timedelta(seconds=1))]
    today_filled = [event for event in today_events if _is_filled_trade_event(event)]
    today_sells = [event for event in today_filled if event.action == "SELL"]
    today_realized_pnl = sum(float(event.realized_pnl or 0.0) for event in today_sells)

    try:
        terminal_payload = _fast_terminal_payload()
    except Exception as exc:  # noqa: BLE001
        terminal_payload = {}
        warnings.append(f"情报与风控统计失败：{exc}")
    llm_insight = terminal_payload.get("llm_insight") if isinstance(terminal_payload.get("llm_insight"), dict) else {}
    intel_metrics = llm_insight.get("metrics") if isinstance(llm_insight.get("metrics"), dict) else {}
    execution_risk = terminal_payload.get("execution_risk") if isinstance(terminal_payload.get("execution_risk"), dict) else {}
    blocked_symbols = execution_risk.get("blocked_symbols") if isinstance(execution_risk.get("blocked_symbols"), dict) else {}
    allowed_symbols = execution_risk.get("allowed_symbols") if isinstance(execution_risk.get("allowed_symbols"), list) else []

    return {
        "date": generated_at.date().isoformat(),
        "generated_at": generated_at.isoformat(),
        "scan": {
            "scanned_symbols": int(float(scan_summary.get("scanned_symbols") or 0)),
            "returned_signals": int(float(scan_summary.get("returned_signals") or len(scan_signals))),
            "top_symbols": [str(item.get("symbol") or "").upper() for item in scan_signals if isinstance(item, dict) and item.get("symbol")][:8],
            "cached": bool(scan_payload.get("cached")),
            "fallback": bool(scan_payload.get("fallback")),
        },
        "trading": {
            "today_trades": len(today_filled),
            "today_buys": sum(1 for event in today_filled if event.action == "BUY"),
            "today_sells": len(today_sells),
            "today_realized_pnl": round(today_realized_pnl, 8),
            "total_trades": int(float(account_metrics.get("total_trades") or 0)),
            "closed_trades": int(float(account_metrics.get("closed_trades") or 0)),
            "win_rate_pct": float(account_metrics.get("win_rate_pct") or 0.0),
            "profit_loss_ratio": float(account_metrics.get("profit_loss_ratio") or 0.0),
            "realized_pnl": float(account_metrics.get("realized_pnl") or 0.0),
            "unrealized_pnl": float(account_metrics.get("unrealized_pnl") or 0.0),
            "total_pnl": float(account_metrics.get("total_pnl") or 0.0),
            "open_positions": len(positions),
        },
        "intelligence": {
            "intel_items": int(float(intel_metrics.get("intel_items") or 0)),
            "onchain_events": int(float(intel_metrics.get("onchain_events") or 0)),
            "strategy_hits": int(float(intel_metrics.get("strategy_hits") or 0)),
            "spreads": int(float(intel_metrics.get("spreads") or 0)),
            "funding_rates": int(float(intel_metrics.get("funding_rates") or 0)),
        },
        "risk": {
            "status": str(execution_risk.get("status") or "unknown"),
            "risk_score": float(execution_risk.get("risk_score") or 0.0),
            "allowed": len(allowed_symbols),
            "blocked": len(blocked_symbols),
        },
        "warnings": warnings,
    }


def _run_feishu_daily_report_once(now: datetime | None = None) -> dict[str, object]:
    report_at = (now or now_app_time()).astimezone(APP_TIMEZONE)
    report_date = report_at.date().isoformat()
    attempted_at = now_app_time()
    with _FEISHU_DAILY_REPORT_RUN_LOCK:
        daily_complete = _feishu_delivery_sent(FEISHU_DAILY_SUMMARY_CHANNEL, report_date)
        btc_complete = _feishu_delivery_sent(FEISHU_BTC_SIGNAL_CHANNEL, report_date)
        if daily_complete and btc_complete:
            result = {
                "sent": False,
                "daily_sent": False,
                "btc_sent": False,
                "complete": True,
                "date": report_date,
                "reason": "already_sent",
                "error": "",
            }
            with _FEISHU_DAILY_REPORT_LOCK:
                _FEISHU_DAILY_REPORT_STATE.update(
                    {
                        "last_sent_date": report_date,
                        "last_btc_sent_date": report_date,
                        "last_run_at": attempted_at.isoformat(),
                        "last_error": "",
                        "last_result": result,
                    }
                )
            return result

        runtime_config, _ = APP_STATE.snapshot()
        notifier = _feishu_trade_notifier(runtime_config)
        if notifier is None:
            error = "飞书 Webhook 未配置"
            if not daily_complete:
                _record_feishu_delivery(
                    FEISHU_DAILY_SUMMARY_CHANNEL,
                    report_date,
                    status="not_configured",
                    error=error,
                )
            if not btc_complete:
                _record_feishu_delivery(
                    FEISHU_BTC_SIGNAL_CHANNEL,
                    report_date,
                    status="not_configured",
                    error=error,
                )
            result = {
                "sent": False,
                "daily_sent": False,
                "btc_sent": False,
                "complete": False,
                "date": report_date,
                "reason": "not_configured",
                "error": error,
            }
            with _FEISHU_DAILY_REPORT_LOCK:
                _FEISHU_DAILY_REPORT_STATE.update(
                    {
                        "last_run_at": attempted_at.isoformat(),
                        "last_error": error,
                        "last_result": result,
                    }
                )
            return result

        daily_sent = False
        btc_sent = False
        errors: list[str] = []
        if not daily_complete:
            try:
                summary = _build_feishu_daily_summary(now=report_at)
                daily_sent = bool(notifier.notify_daily_summary(summary=summary))
                if not daily_sent:
                    raise FeishuNotificationError("飞书接口未确认日报发送成功")
                _record_feishu_delivery(
                    FEISHU_DAILY_SUMMARY_CHANNEL,
                    report_date,
                    status="sent",
                    metadata={
                        "generated_at": summary.get("generated_at"),
                        "today_trades": (summary.get("trading") or {}).get("today_trades")
                        if isinstance(summary.get("trading"), dict)
                        else 0,
                        "today_realized_pnl": (summary.get("trading") or {}).get("today_realized_pnl")
                        if isinstance(summary.get("trading"), dict)
                        else 0.0,
                    },
                )
                daily_complete = True
            except Exception as exc:  # noqa: BLE001
                message = f"每日统计推送失败：{exc}"
                errors.append(message)
                _record_feishu_delivery(
                    FEISHU_DAILY_SUMMARY_CHANNEL,
                    report_date,
                    status="failed",
                    error=str(exc),
                )
                print(f"Feishu daily summary notification failed: {exc}", flush=True)

        if not btc_complete:
            try:
                btc_summary = _build_btc_signal_summary(now=report_at, include_backtests=True)
                btc_sent = bool(notifier.notify_btc_signal(summary=btc_summary))
                if not btc_sent:
                    raise FeishuNotificationError("飞书接口未确认 BTC 日报发送成功")
                _record_feishu_delivery(
                    FEISHU_BTC_SIGNAL_CHANNEL,
                    report_date,
                    status="sent",
                    metadata={
                        "generated_at": btc_summary.get("generated_at"),
                        "action": btc_summary.get("action"),
                        "price": btc_summary.get("price"),
                    },
                )
                btc_complete = True
            except Exception as exc:  # noqa: BLE001
                message = f"BTC 专属信号推送失败：{exc}"
                errors.append(message)
                _record_feishu_delivery(
                    FEISHU_BTC_SIGNAL_CHANNEL,
                    report_date,
                    status="failed",
                    error=str(exc),
                )
                print(f"Feishu BTC signal notification failed: {exc}", flush=True)

        complete = bool(daily_complete and btc_complete)
        sent = bool(daily_sent or btc_sent)
        result = {
            "sent": sent,
            "daily_sent": daily_sent,
            "btc_sent": btc_sent,
            "complete": complete,
            "date": report_date,
            "reason": "sent" if complete and sent else "already_sent" if complete else "partial" if sent else "error",
            "error": "；".join(errors),
        }
        with _FEISHU_DAILY_REPORT_LOCK:
            _FEISHU_DAILY_REPORT_STATE.update(
                {
                    "last_run_at": attempted_at.isoformat(),
                    "last_error": result["error"],
                    "last_sent_date": report_date if daily_complete else _FEISHU_DAILY_REPORT_STATE.get("last_sent_date"),
                    "last_btc_sent_date": report_date if btc_complete else _FEISHU_DAILY_REPORT_STATE.get("last_btc_sent_date"),
                    "last_result": result,
                }
            )
        return result


def _feishu_daily_report_worker(stop_event: Event) -> None:
    retry_not_before: datetime | None = None
    while not stop_event.is_set():
        current = now_app_time()
        try:
            target = _pending_feishu_daily_report_at(current)
            due_at = target
            if target <= current and retry_not_before is not None and retry_not_before > current:
                due_at = retry_not_before
            with _FEISHU_DAILY_REPORT_LOCK:
                _FEISHU_DAILY_REPORT_STATE["next_run_at"] = due_at.isoformat()

            wait_seconds = max(0.0, (due_at - current).total_seconds())
            if wait_seconds > 0:
                if stop_event.wait(min(wait_seconds, FEISHU_DAILY_REPORT_HEARTBEAT_SECONDS)):
                    break
                continue

            result = _run_feishu_daily_report_once(now=target)
            retry_not_before = None if result.get("complete") else now_app_time() + timedelta(seconds=FEISHU_DAILY_REPORT_RETRY_SECONDS)
        except Exception as exc:  # noqa: BLE001
            retry_not_before = now_app_time() + timedelta(seconds=FEISHU_DAILY_REPORT_RETRY_SECONDS)
            with _FEISHU_DAILY_REPORT_LOCK:
                _FEISHU_DAILY_REPORT_STATE.update(
                    {
                        "last_run_at": now_app_time().isoformat(),
                        "last_error": str(exc),
                        "next_run_at": retry_not_before.isoformat(),
                    }
                )
            print(f"Feishu daily report scheduler failed: {exc}", flush=True)
    with _FEISHU_DAILY_REPORT_LOCK:
        if _FEISHU_DAILY_REPORT_STOP_EVENT is stop_event:
            _FEISHU_DAILY_REPORT_STATE.update({"running": False, "next_run_at": None})


def _start_feishu_daily_report_scheduler() -> dict[str, object]:
    global _FEISHU_DAILY_REPORT_STOP_EVENT, _FEISHU_DAILY_REPORT_THREAD
    with _FEISHU_DAILY_REPORT_LOCK:
        if _FEISHU_DAILY_REPORT_THREAD is not None and _FEISHU_DAILY_REPORT_THREAD.is_alive():
            return dict(_FEISHU_DAILY_REPORT_STATE)
        stop_event = Event()
        _FEISHU_DAILY_REPORT_STOP_EVENT = stop_event
        _FEISHU_DAILY_REPORT_THREAD = Thread(
            target=_feishu_daily_report_worker,
            args=(stop_event,),
            name="feishu-daily-report",
            daemon=True,
        )
        _FEISHU_DAILY_REPORT_STATE.update(
            {
                "running": True,
                "last_error": "",
                "next_run_at": _pending_feishu_daily_report_at().isoformat(),
            }
        )
        _FEISHU_DAILY_REPORT_THREAD.start()
        return dict(_FEISHU_DAILY_REPORT_STATE)


def _stop_feishu_daily_report_scheduler() -> dict[str, object]:
    with _FEISHU_DAILY_REPORT_LOCK:
        stop_event = _FEISHU_DAILY_REPORT_STOP_EVENT
        thread = _FEISHU_DAILY_REPORT_THREAD
        if stop_event is not None:
            stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)
    with _FEISHU_DAILY_REPORT_LOCK:
        _FEISHU_DAILY_REPORT_STATE.update({"running": False, "next_run_at": None})
        return dict(_FEISHU_DAILY_REPORT_STATE)


def _latest_prices_for_open_positions(
    positions: list[TradingPosition],
    scanner: object,
    signal_prices: dict[str, float] | None = None,
) -> dict[str, float]:
    latest_prices = {symbol.upper(): price for symbol, price in (signal_prices or {}).items() if price > 0}
    position_symbols = {position.symbol.upper() for position in positions}
    latest_prices.update(_live_prices_for_symbols(scanner, sorted(position_symbols)))
    return latest_prices


def _evaluate_forced_paper_exits(
    *,
    positions: list[TradingPosition],
    config: AutoTradeDefaults,
    events: list[TradingEvent],
    latest_prices: dict[str, float],
    signal_by_symbol: dict[str, object],
    scanner: object,
    store: TradingStateStore,
    notifier: FeishuTradeNotifier | None,
) -> list[TradingPosition]:
    trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)
    return trader._evaluate_exits(positions, config, events, latest_prices, signal_by_symbol=signal_by_symbol)


def _serialize_trading_position(position: TradingPosition, latest_price: float | None = None) -> dict[str, object]:
    current_notional = None
    unrealized_pnl = None
    unrealized_pnl_pct = None
    unrealized_price_return_pct = None
    margin_notional = position.margin_notional if position.margin_notional is not None else position.quote_notional
    if latest_price is not None and latest_price > 0:
        current_notional = position.quantity * latest_price
        unrealized_pnl = current_notional - position.quote_notional
        unrealized_pnl_pct = (unrealized_pnl / margin_notional) * 100 if margin_notional else 0.0
        unrealized_price_return_pct = (unrealized_pnl / position.quote_notional) * 100 if position.quote_notional else 0.0
    return {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "entry_price": position.entry_price,
        "last_price": latest_price,
        "quote_notional": position.quote_notional,
        "margin_notional": margin_notional,
        "leverage": position.leverage,
        "current_notional": current_notional,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "unrealized_price_return_pct": unrealized_price_return_pct,
        "score": position.score,
        "grade": position.grade,
        "opened_at": position.opened_at.isoformat(),
        "stop_price": position.stop_price,
        "take_profit_price": position.take_profit_price,
        "highest_price": position.highest_price or position.entry_price,
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


def _ratio_metric(numerator: float, denominator: float) -> float:
    if denominator:
        return round(numerator / denominator, 4)
    return 999.0 if numerator else 0.0


def _paper_account_metrics(
    *,
    positions: list[TradingPosition],
    events: list[TradingEvent],
    latest_prices: dict[str, float] | None = None,
    symbol: str | None = None,
) -> dict[str, object]:
    latest_prices = latest_prices or {}
    normalized_symbol = symbol.upper() if symbol else None
    paper_positions = [position for position in positions if position.mode == "paper"]
    paper_events = [event for event in events if event.mode == "paper"]
    if normalized_symbol:
        paper_positions = [position for position in paper_positions if position.symbol.upper() == normalized_symbol]
        paper_events = [event for event in paper_events if event.symbol.upper() == normalized_symbol]
    filled_events = [
        event
        for event in paper_events
        if event.action in {"BUY", "SELL"} and event.status == "paper_filled"
    ]
    closed_events = [
        event
        for event in filled_events
        if event.action == "SELL" and event.realized_pnl is not None
    ]
    realized_values = [float(event.realized_pnl or 0.0) for event in closed_events]
    realized_pct_values = [float(event.realized_pnl_pct or 0.0) for event in closed_events if event.realized_pnl_pct is not None]
    wins = [value for value in realized_values if value > 0]
    losses = [value for value in realized_values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    unrealized_values: list[float] = []
    for position in paper_positions:
        latest_price = latest_prices.get(position.symbol.upper())
        if latest_price is not None and latest_price > 0:
            unrealized_values.append((position.quantity * latest_price) - position.quote_notional)
    realized_pnl = sum(realized_values)
    unrealized_pnl = sum(unrealized_values)
    return {
        "mode": "paper",
        "symbol": normalized_symbol or "",
        "event_count": len(paper_events),
        "diagnostic_event_count": len(paper_events) - len(filled_events),
        "open_positions": len(paper_positions),
        "quote_exposure": round(sum(position.quote_notional for position in paper_positions), 8),
        "margin_exposure": round(
            sum(position.margin_notional if position.margin_notional is not None else position.quote_notional for position in paper_positions),
            8,
        ),
        "total_trades": len(filled_events),
        "buy_trades": sum(1 for event in filled_events if event.action == "BUY"),
        "sell_trades": sum(1 for event in filled_events if event.action == "SELL"),
        "closed_trades": len(closed_events),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": sum(1 for value in realized_values if value == 0),
        "win_rate_pct": round((len(wins) / len(closed_events)) * 100, 2) if closed_events else 0.0,
        "profit_loss_ratio": _ratio_metric(avg_win, avg_loss),
        "profit_factor": _ratio_metric(gross_profit, gross_loss),
        "gross_profit": round(gross_profit, 8),
        "gross_loss": round(gross_loss, 8),
        "realized_pnl": round(realized_pnl, 8),
        "unrealized_pnl": round(unrealized_pnl, 8),
        "total_pnl": round(realized_pnl + unrealized_pnl, 8),
        "avg_realized_pnl": round(realized_pnl / len(realized_values), 8) if realized_values else 0.0,
        "avg_realized_pnl_pct": round(sum(realized_pct_values) / len(realized_pct_values), 4) if realized_pct_values else 0.0,
        "best_trade_pnl": round(max(realized_values), 8) if realized_values else 0.0,
        "worst_trade_pnl": round(min(realized_values), 8) if realized_values else 0.0,
    }


def _btc_account_metrics(
    *,
    positions: list[TradingPosition],
    events: list[TradingEvent],
    latest_prices: dict[str, float] | None = None,
) -> dict[str, object]:
    return _paper_account_metrics(
        positions=positions,
        events=events,
        latest_prices=latest_prices,
        symbol=BTC_SYMBOL,
    )


def _btc_trading_zone_payload(
    *,
    positions: list[TradingPosition],
    events: list[TradingEvent],
    latest_prices: dict[str, float] | None = None,
    include_signal: bool = True,
) -> dict[str, object]:
    latest_prices = latest_prices or {}
    btc_positions = [position for position in positions if position.mode == "paper" and position.symbol.upper() == BTC_SYMBOL]
    btc_events = [event for event in events if event.mode == "paper" and event.symbol.upper() == BTC_SYMBOL]
    payload: dict[str, object] = {
        "symbol": BTC_SYMBOL,
        "metrics": _btc_account_metrics(positions=positions, events=events, latest_prices=latest_prices),
        "open_positions": [
            _serialize_trading_position(position, latest_prices.get(position.symbol.upper()))
            for position in btc_positions
        ],
        "recent_events": [_serialize_trading_event(event) for event in _select_trading_status_events(_sort_trading_events_desc(btc_events))[:20]],
        "signal": None,
        "signal_error": "",
    }
    if include_signal:
        try:
            payload["signal"] = _build_btc_signal_summary(include_backtests=False)
        except Exception as exc:  # noqa: BLE001
            payload["signal_error"] = str(exc)
    return payload


def _current_btc_trading_zone_payload(*, include_signal: bool = True) -> dict[str, object]:
    _, scanner = APP_STATE.snapshot()
    store = _trading_store()
    positions = store.load()
    events = _sort_trading_events_desc(store.load_events())
    latest_prices = _latest_prices_for_open_positions(positions, scanner)
    return _btc_trading_zone_payload(
        positions=positions,
        events=events,
        latest_prices=latest_prices,
        include_signal=include_signal,
    )


def _sort_trading_events_desc(events: list[TradingEvent]) -> list[TradingEvent]:
    return sorted(events, key=_event_created_at_utc, reverse=True)


def _is_filled_trade_event(event: TradingEvent) -> bool:
    return event.action in TRADE_EVENT_ACTIONS and event.status in FILLED_TRADE_STATUSES


def _select_trading_status_events(events: list[TradingEvent]) -> list[TradingEvent]:
    filled_count = 0
    diagnostic_count = 0
    selected: list[TradingEvent] = []
    for event in events:
        if _is_filled_trade_event(event):
            if filled_count >= TRADING_STATUS_FILLED_EVENT_LIMIT:
                continue
            filled_count += 1
            selected.append(event)
            continue
        if diagnostic_count >= TRADING_STATUS_DIAGNOSTIC_EVENT_LIMIT:
            continue
        diagnostic_count += 1
        selected.append(event)
    return _sort_trading_events_desc(selected)


def _trading_event_summary(events: list[TradingEvent], returned_events: list[TradingEvent]) -> dict[str, object]:
    filled_events = [event for event in events if _is_filled_trade_event(event)]
    return {
        "total_events": len(events),
        "returned_events": len(returned_events),
        "filled_events": len(filled_events),
        "diagnostic_events": len(events) - len(filled_events),
        "filled_event_retention": TRADING_STATUS_FILLED_EVENT_LIMIT,
        "diagnostic_event_retention": TRADING_STATUS_DIAGNOSTIC_EVENT_LIMIT,
    }


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
        "account_metrics": _paper_account_metrics(
            positions=report.open_positions,
            events=report.events,
            latest_prices=latest_prices,
        ),
        "btc_trading": _btc_trading_zone_payload(
            positions=report.open_positions,
            events=report.events,
            latest_prices=latest_prices,
            include_signal=False,
        ),
        "generated_at": report.generated_at.isoformat(),
    }


def _trading_status_payload() -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    store = _trading_store()
    positions = store.load()
    events = _sort_trading_events_desc(store.load_events())
    status_events = _select_trading_status_events(events)
    latest_prices = _latest_prices_for_open_positions(positions, scanner)
    account_metrics = _paper_account_metrics(
        positions=positions,
        events=events,
        latest_prices=latest_prices,
    )
    store.record_metric_snapshot("paper_account", account_metrics)
    return {
        "config": _to_jsonable(runtime_config.autotrade_defaults),
        "readiness": _trading_readiness_payload(),
        "open_positions": [
            _serialize_trading_position(position, latest_prices.get(position.symbol.upper()))
            for position in positions
        ],
        "events": [_serialize_trading_event(event) for event in status_events],
        "event_summary": _trading_event_summary(events, status_events),
        "storage": store.database_status(),
        "account_metrics": account_metrics,
        "btc_trading": _btc_trading_zone_payload(
            positions=positions,
            events=events,
            latest_prices=latest_prices,
            include_signal=True,
        ),
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
    should_check_account = check_account if check_account is not None else (config.live_enabled and not config.order_test_only)
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
        config.live_enabled
        and has_credentials
        and authenticated
        and can_trade
        and live_confirmed
        and quote_available >= config.quote_order_qty
    )
    blockers = []
    if config.live_enabled:
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
        "paper_enabled": config.paper_enabled,
        "live_enabled": config.live_enabled,
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
    cutoff = now_app_time() - timedelta(hours=24)
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
    notifier = _feishu_trade_notifier(runtime_config)
    query = {
        "quote_asset": [runtime_config.scan_defaults.quote_asset],
        "interval": [runtime_config.scan_defaults.interval],
        "candidate_pool": [str(runtime_config.scan_defaults.candidate_pool)],
        "min_quote_volume": [str(runtime_config.scan_defaults.min_quote_volume)],
        "min_trade_count": [str(runtime_config.scan_defaults.min_trade_count)],
    }
    scan_payload, _ = _scan_payload(query, force_refresh=True)
    signals = [item for item in scan_payload.get("signals", []) if isinstance(item, dict)]
    store = _trading_store()
    all_positions = store.load()
    non_paper_positions = [position for position in all_positions if position.mode != "paper"]
    positions = [position for position in all_positions if position.mode == "paper"]
    events: list[TradingEvent] = []
    signal_prices = {
        str(signal.get("symbol", "")).upper(): float(signal.get("last_price") or 0.0)
        for signal in signals
        if str(signal.get("symbol", "")).strip()
    }
    latest_prices = _latest_prices_for_open_positions(positions, scanner, signal_prices)
    positions = _evaluate_forced_paper_exits(
        positions=positions,
        config=config,
        events=events,
        latest_prices=latest_prices,
        signal_by_symbol={str(signal.get("symbol", "")).upper(): signal for signal in signals},
        scanner=scanner,
        store=store,
        notifier=notifier,
    )
    now = now_app_time()
    open_symbols = {position.symbol for position in positions}
    exposure = sum(position.margin_notional if position.margin_notional is not None else position.quote_notional for position in positions)
    blocked_symbols = {}
    risk_payload = _fast_risk_module_payload().get("execution_risk", {})
    if isinstance(risk_payload, dict) and isinstance(risk_payload.get("blocked_symbols"), dict):
        blocked_symbols = risk_payload["blocked_symbols"]

    for signal in signals:
        symbol = str(signal.get("symbol") or "").upper()
        score = float(signal.get("score") or 0.0)
        signal_price = float(signal.get("last_price") or 0.0)
        price = _live_price_for_symbol(scanner, symbol, fallback=signal_price)
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
        volatility_issue = _scan_signal_volatility_entry_reason(signal, config)
        if volatility_issue:
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol=symbol,
                    mode="paper",
                    status="wait_volatility",
                    message=volatility_issue,
                    score=score,
                    price=price,
                    exchange=config.execution_exchange.upper(),
                )
            )
            continue
        anti_chase = _scan_signal_anti_chase_reason(signal, config)
        if anti_chase:
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol=symbol,
                    mode="paper",
                    status="wait_pullback",
                    message=anti_chase,
                    score=score,
                    price=price,
                    exchange=config.execution_exchange.upper(),
                )
            )
            continue
        structure_issue = _scan_signal_structure_entry_reason(signal, config, current_price=price)
        if structure_issue:
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol=symbol,
                    mode="paper",
                    status="wait_support",
                    message=structure_issue,
                    score=score,
                    price=price,
                    exchange=config.execution_exchange.upper(),
                )
            )
            continue
        leverage = max(1.0, config.leverage)
        margin_notional = config.quote_order_qty
        position_notional = margin_notional * leverage
        quantity = position_notional / price
        stop_price, take_profit_price = _scan_signal_structured_exit_prices(signal, price, config)
        position = TradingPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            quote_notional=position_notional,
            score=score,
            grade=str(signal.get("grade") or "B"),
            opened_at=now,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            mode="paper",
            client_order_id=f"aitrade-paper-{symbol.lower()}-{int(now.timestamp())}",
            exchange=config.execution_exchange.upper(),
            highest_price=price,
            leverage=leverage,
            margin_notional=margin_notional,
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
            quote_notional=position_notional,
            exchange=config.execution_exchange.upper(),
        )
        positions.append(position)
        events.append(event)
        _notify_trade_event(notifier, event=event, position=position)
        open_symbols.add(symbol)
        exposure += margin_notional

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
    combined_positions = [*non_paper_positions, *positions]
    store.save(combined_positions)
    store.append_events(events)
    latest_prices = _latest_prices_for_open_positions(combined_positions, scanner, signal_prices)
    return _serialize_trading_report(
        TradingRunReport(
            enabled=True,
            mode="paper",
            scanned_symbols=int(scan_payload.get("summary", {}).get("scanned_symbols", 0)) if isinstance(scan_payload.get("summary"), dict) else 0,
            returned_signals=int(scan_payload.get("summary", {}).get("returned_signals", len(signals))) if isinstance(scan_payload.get("summary"), dict) else len(signals),
            open_positions=combined_positions,
            events=events,
        ),
        latest_prices=latest_prices,
    )


def _scan_signal_anti_chase_reason(signal: dict[str, object], config: AutoTradeDefaults) -> str:
    return anti_chase_reason_from_config(
        rsi=_float_from_mapping(signal, "rsi_14", 50.0),
        price_vs_ema20_pct=_float_from_mapping(signal, "price_vs_ema20_pct"),
        recent_change_pct=_float_from_mapping(signal, "recent_change_pct"),
        config=config,
    )


def _scan_signal_volatility_entry_reason(signal: dict[str, object], config: AutoTradeDefaults) -> str:
    return volatility_entry_reason(
        regime=str(signal.get("volatility_regime") or "normal"),
        percentile=_float_from_mapping(signal, "volatility_percentile", 50.0),
        ratio=_float_from_mapping(signal, "volatility_ratio", 1.0),
        atr_pct=_float_from_mapping(signal, "atr_pct", 0.0),
        enabled=config.volatility_filter_enabled,
        block_extreme=config.block_extreme_volatility,
        max_percentile=config.max_entry_volatility_percentile,
        max_ratio=config.max_entry_volatility_ratio,
    )


def _scan_signal_structure_entry_reason(
    signal: dict[str, object],
    config: AutoTradeDefaults,
    *,
    current_price: float | None = None,
) -> str:
    community_score = signal.get("community_score")
    try:
        parsed_community_score = float(community_score) if community_score is not None else None
    except (TypeError, ValueError):
        parsed_community_score = None
    return structure_entry_reason_from_config(
        close_price=current_price if current_price and current_price > 0 else _float_from_mapping(signal, "last_price"),
        support_level=_float_from_mapping(signal, "support_level"),
        resistance_level=_float_from_mapping(signal, "resistance_level"),
        support_distance_pct=_float_from_mapping(signal, "support_distance_pct"),
        resistance_distance_pct=_float_from_mapping(signal, "resistance_distance_pct"),
        support_strength=_float_from_mapping(signal, "support_strength"),
        risk_reward_ratio=_float_from_mapping(signal, "structure_risk_reward"),
        volume_ratio=_float_from_mapping(signal, "volume_ratio", 1.0),
        buy_pressure_ratio=_float_from_mapping(signal, "buy_pressure_ratio", 0.0),
        community_score=parsed_community_score,
        config=config,
    )


def _scan_signal_structured_exit_prices(
    signal: dict[str, object],
    price: float,
    config: AutoTradeDefaults,
) -> tuple[float, float]:
    return structure_adjusted_exit_prices(
        entry_price=price,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        support_level=_float_from_mapping(signal, "support_level"),
        resistance_level=_float_from_mapping(signal, "resistance_level"),
        enabled=config.structure_filter_enabled,
        support_stop_buffer_pct=config.support_stop_buffer_pct,
        resistance_take_profit_buffer_pct=config.resistance_take_profit_buffer_pct,
    )


def _active_autotrade_modes(config: AutoTradeDefaults) -> list[str]:
    modes: list[str] = []
    if config.paper_enabled:
        modes.append("paper")
    if config.live_enabled:
        modes.append("live")
    if not modes and config.enabled:
        mode = str(config.mode or "paper").strip() or "paper"
        if mode in {"paper", "live"}:
            modes.append(mode)
    return modes


def _combined_trading_report(
    *,
    config: AutoTradeDefaults,
    mode_label: str,
    reports: list[TradingRunReport],
    extra_events: list[TradingEvent] | None = None,
) -> TradingRunReport:
    events = [*(extra_events or [])]
    for report in reports:
        events.extend(report.events)
    positions = _trading_store().load()
    return TradingRunReport(
        enabled=config.enabled or config.paper_enabled or config.live_enabled,
        mode=mode_label,
        scanned_symbols=max((report.scanned_symbols for report in reports), default=0),
        returned_signals=max((report.returned_signals for report in reports), default=0),
        open_positions=positions,
        events=events,
    )


def _run_trading_once(*, force_paper: bool = False) -> dict[str, object]:
    runtime_config, scanner = APP_STATE.snapshot()
    autotrade_config = runtime_config.autotrade_defaults
    if force_paper:
        return _run_forced_paper_trading_once()
    active_modes = _active_autotrade_modes(autotrade_config)
    if not active_modes:
        risk_snapshot = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS).snapshot()
        trader = AutoTrader(
            scanner=scanner,
            state_store=_trading_store(),
            blocked_symbols=risk_snapshot.execution_risk.blocked_symbols,
            trade_notifier=_feishu_trade_notifier(runtime_config),
        )
        trader.set_execution_gateway(_execution_gateway(runtime_config, scanner))
        report = trader.run_once(autotrade_config)
        latest_prices = _latest_prices_for_open_positions(report.open_positions, scanner)
        return _serialize_trading_report(report, latest_prices=latest_prices)

    extra_events: list[TradingEvent] = []
    mode_label = "+".join(active_modes)
    runnable_modes = list(active_modes)
    if "live" in runnable_modes and not autotrade_config.order_test_only:
        try:
            readiness = _trading_readiness_payload()
        except Exception as exc:  # noqa: BLE001
            readiness = {
                "live_ready": False,
                "blockers": [f"实盘就绪检查异常：{exc}"],
            }
        if not readiness["live_ready"]:
            positions = _trading_store().load()
            blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
            blocker_message = "；".join(str(item) for item in blockers) or "未知原因"
            event = TradingEvent(
                action="SKIP",
                symbol="*",
                mode="live",
                status="blocked",
                message="实盘自动交易未就绪：" + blocker_message,
                exchange=autotrade_config.execution_exchange.upper(),
            )
            _trading_store().append_events([event])
            extra_events.append(event)
            runnable_modes = [mode for mode in runnable_modes if mode != "live"]
            if not runnable_modes:
                latest_prices = _latest_prices_for_open_positions(positions, scanner)
                return _serialize_trading_report(
                    TradingRunReport(
                        enabled=autotrade_config.enabled or autotrade_config.paper_enabled or autotrade_config.live_enabled,
                        mode=mode_label,
                        scanned_symbols=0,
                        returned_signals=0,
                        open_positions=positions,
                        events=extra_events,
                    ),
                    latest_prices=latest_prices,
                )
    risk_snapshot = IntelligenceHub(scanner=scanner, runtime_config=runtime_config, settings=SETTINGS).snapshot()
    blocked_symbols = risk_snapshot.execution_risk.blocked_symbols
    shared_scan_result = scanner.scan()
    reports: list[TradingRunReport] = []
    mode_isolated = autotrade_config.paper_enabled or autotrade_config.live_enabled or len(active_modes) > 1
    for mode in runnable_modes:
        trader = AutoTrader(
            scanner=scanner,
            state_store=_trading_store(),
            blocked_symbols=blocked_symbols,
            trade_notifier=_feishu_trade_notifier(runtime_config),
            isolate_mode=mode_isolated,
            scan_result=shared_scan_result,
        )
        trader.set_execution_gateway(_execution_gateway(runtime_config, scanner))
        reports.append(trader.run_once(replace(autotrade_config, enabled=True, mode=mode)))
    report = _combined_trading_report(
        config=autotrade_config,
        mode_label=mode_label,
        reports=reports,
        extra_events=extra_events,
    )
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


def _auto_loop_mode_label(force_paper: bool) -> str:
    return "paper_only" if force_paper else "configured_paper_live"


def _run_paper_auto_once(interval_seconds: int, *, force_paper: bool = True) -> None:
    try:
        result = _run_trading_once(force_paper=force_paper)
        with _PAPER_AUTO_LOCK:
            _PAPER_AUTO_STATE.update(
                {
                    "running": True,
                    "interval_seconds": interval_seconds,
                    "force_paper": force_paper,
                    "mode_label": _auto_loop_mode_label(force_paper),
                    "last_run_at": now_app_time().isoformat(),
                    "last_error": "",
                    "run_count": int(_PAPER_AUTO_STATE.get("run_count") or 0) + 1,
                    "last_result": result,
                }
            )
    except Exception as exc:  # noqa: BLE001
        with _PAPER_AUTO_LOCK:
            _PAPER_AUTO_STATE.update(
                {
                    "last_run_at": now_app_time().isoformat(),
                    "last_error": str(exc),
                }
            )


def _paper_auto_worker(stop_event: Event, interval_seconds: int, initial_delay: bool = True, force_paper: bool = True) -> None:
    if initial_delay and stop_event.wait(interval_seconds):
        return
    while not stop_event.is_set():
        _run_paper_auto_once(interval_seconds, force_paper=force_paper)
        if stop_event.wait(interval_seconds):
            break
    with _PAPER_AUTO_LOCK:
        if _PAPER_AUTO_STOP_EVENT is stop_event:
            _PAPER_AUTO_STATE.update(
                {
                    "running": False,
                    "stopped_at": now_app_time().isoformat(),
                }
            )


def _start_paper_auto_trading(
    interval_seconds: int = PAPER_AUTO_DEFAULT_INTERVAL_SECONDS,
    *,
    force_paper: bool = True,
) -> dict[str, object]:
    interval_seconds = max(PAPER_AUTO_MIN_INTERVAL_SECONDS, int(interval_seconds))
    global _PAPER_AUTO_STOP_EVENT, _PAPER_AUTO_THREAD
    previous_stop_event: Event | None = None
    previous_thread: Thread | None = None
    with _PAPER_AUTO_LOCK:
        if _PAPER_AUTO_THREAD is not None and _PAPER_AUTO_THREAD.is_alive():
            if bool(_PAPER_AUTO_STATE.get("force_paper", True)) != force_paper:
                previous_stop_event = _PAPER_AUTO_STOP_EVENT
                previous_thread = _PAPER_AUTO_THREAD
            else:
                _PAPER_AUTO_STATE["interval_seconds"] = interval_seconds
                _PAPER_AUTO_STATE["mode_label"] = _auto_loop_mode_label(force_paper)
                return _paper_auto_status_payload()
    if previous_stop_event is not None:
        previous_stop_event.set()
    if previous_thread is not None and previous_thread.is_alive():
        previous_thread.join(timeout=2)
    with _PAPER_AUTO_LOCK:
        if _PAPER_AUTO_THREAD is not None and _PAPER_AUTO_THREAD.is_alive():
            _PAPER_AUTO_STATE["interval_seconds"] = interval_seconds
            _PAPER_AUTO_STATE["mode_label"] = _auto_loop_mode_label(force_paper)
            return _paper_auto_status_payload()
        stop_event = Event()
        _PAPER_AUTO_STOP_EVENT = stop_event
        _PAPER_AUTO_STATE.update(
            {
                "running": True,
                "interval_seconds": interval_seconds,
                "started_at": now_app_time().isoformat(),
                "stopped_at": None,
                "last_error": "",
                "force_paper": force_paper,
                "mode_label": _auto_loop_mode_label(force_paper),
            }
        )
    _run_paper_auto_once(interval_seconds, force_paper=force_paper)
    with _PAPER_AUTO_LOCK:
        _PAPER_AUTO_THREAD = Thread(
            target=_paper_auto_worker,
            args=(stop_event, interval_seconds, True, force_paper),
            name="paper-auto-trading" if force_paper else "strategy-auto-trading",
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
                    "stopped_at": now_app_time().isoformat(),
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
    carry = runtime_config.carry_paper_defaults
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
        carry.enabled,
        carry.min_basis_bps,
        carry.min_funding_bps,
    )


def _cached_terminal_payload() -> dict[str, object] | None:
    runtime_config, _ = APP_STATE.snapshot()
    cache_key = _terminal_cache_key(runtime_config)
    now = now_app_time()
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
                "expires_at": now_app_time() + timedelta(seconds=TERMINAL_SNAPSHOT_TTL_SECONDS),
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
        "btc_trading": _current_btc_trading_zone_payload(include_signal=True),
        "carry_paper": _carry_paper_status_payload(),
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
        "carry_paper": _carry_paper_status_payload(),
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
        price_vs_ema20 = _float_from_mapping(signal, "price_vs_ema20_pct")
        recent_change = _float_from_mapping(signal, "recent_change_pct")
        funding_rate = _float_from_mapping(funding or {}, "funding_rate")
        anti_chase = anti_chase_reason_from_config(
            rsi=rsi,
            price_vs_ema20_pct=price_vs_ema20,
            recent_change_pct=recent_change,
            config=runtime_config.autotrade_defaults,
        )
        volatility_issue = _scan_signal_volatility_entry_reason(signal, runtime_config.autotrade_defaults)
        structure_issue = _scan_signal_structure_entry_reason(signal, runtime_config.autotrade_defaults)

        if score >= threshold:
            add_hit(
                _strategy_hit_row(
                    signal=signal,
                    strategy="auto_score_breakout",
                    score=score,
                    grade=grade,
                    action="wait_volatility"
                    if volatility_issue
                    else "wait_pullback"
                    if anti_chase
                    else "wait_support"
                    if structure_issue
                    else "candidate_buy"
                    if runtime_config.autotrade_defaults.enabled
                    else "watch",
                    reasons=[volatility_issue, *reasons[:4]]
                    if volatility_issue
                    else [anti_chase, *reasons[:4]]
                    if anti_chase
                    else [structure_issue, *reasons[:4]]
                    if structure_issue
                    else reasons or ["综合评分达到自动交易阈值"],
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
        "strategy_templates": list_strategy_templates(),
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
    now = now_app_time()
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
                "expires_at": now_app_time() + timedelta(seconds=TERMINAL_SNAPSHOT_TTL_SECONDS),
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
    now = now_app_time()
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
        "carry_paper": _carry_paper_status_payload(),
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
        "generated_at": now_app_time().isoformat(),
        "scanned_symbols": 0,
        "returned_signals": 0,
        "intel_items": intel_items,
        "twitter_accounts": community["twitter_accounts"],
        "onchain_events": onchain_events,
        "onchain_sources": onchain.get("onchain_sources", []),
        "spreads": spreads,
        "funding_rates": funding_rates,
        "carry_paper": basis.get("carry_paper", _carry_paper_status_payload()),
        "market_sources": market.get("market_sources", []),
        "strategy_hits": strategy_hits,
        "strategy_templates": strategies.get("strategy_templates", list_strategy_templates()),
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
        "btc_trading": _current_btc_trading_zone_payload(include_signal=True),
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
        trading = _trading_status_payload()
        return {
            "module": module,
            "trading": trading,
            "accounts": platform["accounts"],
            "recent_events": platform["recent_events"],
            "btc_trading": trading.get("btc_trading") if isinstance(trading.get("btc_trading"), dict) else {},
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


def _compile_strategy_template_payload(template_id: str) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    template = get_strategy_template(template_id)
    compiled = compile_strategy_template(template.template_id, runtime_config)
    payload = _to_jsonable(compiled)
    payload["template"] = {
        "template_id": template.template_id,
        "label": template.label,
        "preset_id": template.preset_id,
        "risk_level": template.risk_level,
        "validation_status": template.validation_status,
        "recommended_intervals": list(template.recommended_intervals),
        "market_regimes": list(template.market_regimes),
        "paper_only": template.paper_only,
    }
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
        "volatility_filter_enabled",
        "block_extreme_volatility",
        "max_entry_volatility_percentile",
        "max_entry_volatility_ratio",
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


SCAN_SYNC_TIMEOUT_SECONDS = scan_handlers.SCAN_SYNC_TIMEOUT_SECONDS
_SCAN_CACHE_LOCK = scan_handlers._SCAN_CACHE_LOCK
_SCAN_PAYLOAD_CACHE = scan_handlers._SCAN_PAYLOAD_CACHE
_SCAN_INFLIGHT = scan_handlers._SCAN_INFLIGHT
_SCAN_EXECUTOR = scan_handlers._SCAN_EXECUTOR
_scan_cache_key = scan_handlers._scan_cache_key
_cached_scan_payload = scan_handlers._cached_scan_payload
_store_scan_payload = scan_handlers._store_scan_payload
_annotate_scan_summary = scan_handlers._annotate_scan_summary
_run_scan_payload = scan_handlers._run_scan_payload
_format_scan_signal_row = scan_handlers._format_scan_signal_row
_complete_scan_future = scan_handlers._complete_scan_future


def _fallback_scan_payload(params: dict[str, object], warning: str) -> dict[str, object]:
    _, scanner = APP_STATE.snapshot()
    return scan_handlers._fallback_scan_payload(params, warning, scanner=scanner)


def _scan_payload(query: dict[str, list[str]], *, force_refresh: bool = False) -> tuple[dict[str, object], dict[str, object]]:
    runtime_config, scanner = APP_STATE.snapshot()
    return scan_handlers._scan_payload(
        query,
        runtime_config=runtime_config,
        scanner=scanner,
        force_refresh=force_refresh,
    )


def _get_first(query: dict[str, list[str]], key: str, default: str) -> str:
    return query.get(key, [default])[0]


def _parse_bool_flag(query: dict[str, list[str]], key: str) -> bool:
    return key in query and any(str(value).strip() not in {"", "0", "false", "False", "off"} for value in query.get(key, []))


def _runtime_bool(form: dict[str, list[str]], key: str, current: bool) -> bool:
    if key not in form:
        return current
    return _parse_bool_flag(form, key)


_path_with_lang = backtest_handlers._path_with_lang
_split_archives = backtest_handlers._split_archives
_empty_backtest_payload = backtest_handlers._empty_backtest_payload
_backtest_export_csv = backtest_handlers._backtest_export_csv
_backtest_export_html = backtest_handlers._backtest_export_html


def _tradingview_fetch_result(form: dict[str, list[str]]) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    return backtest_handlers._tradingview_fetch_result(
        form,
        runtime_config=runtime_config,
        tradingview_cache_dir=TRADINGVIEW_CACHE_DIR,
    )


def _tradingview_backtest_redirect(form: dict[str, list[str]], lang: str) -> str:
    runtime_config, _ = APP_STATE.snapshot()
    return backtest_handlers._tradingview_backtest_redirect(
        form,
        lang,
        runtime_config=runtime_config,
        tradingview_cache_dir=TRADINGVIEW_CACHE_DIR,
    )


def _backtest_job_query_key(query: dict[str, list[str]]) -> str:
    normalized = {key: [str(value) for value in values] for key, values in sorted(query.items()) if key != "job_id"}
    return json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _backtest_job_redirect(query: dict[str, list[str]], job_id: str) -> str:
    redirect_query = {key: list(values) for key, values in query.items() if key != "job_id"}
    redirect_query["job_id"] = [job_id]
    return f"/backtest?{urlencode(redirect_query, doseq=True)}"


def _run_backtest_job(job_id: str, query: dict[str, list[str]]) -> None:
    with _BACKTEST_JOB_LOCK:
        job = _BACKTEST_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["started_at"] = now_app_time().isoformat()
        job["_started_monotonic"] = monotonic()
    try:
        runtime_config, scanner = APP_STATE.snapshot()
        result = backtest_handlers._backtest_payload(
            query,
            runtime_config=runtime_config,
            scanner=scanner,
            resolve_execution_config=resolve_execution_config_from_binance,
        )
        payload, params, error = result
        _record_backtest_run(params, payload, error)
        with _BACKTEST_JOB_LOCK:
            _BACKTEST_JOB_RESULTS[job_id] = deepcopy(result)
            job = _BACKTEST_JOBS.get(job_id)
            if job is not None:
                job["result_available"] = True
                job["status"] = "failed" if error else "completed"
                job["error"] = error or ""
                job["performance"] = deepcopy(payload.get("performance") or {})
    except Exception as exc:  # noqa: BLE001
        with _BACKTEST_JOB_LOCK:
            job = _BACKTEST_JOBS.get(job_id)
            if job is not None:
                job["status"] = "failed"
                job["error"] = str(exc)
    finally:
        with _BACKTEST_JOB_LOCK:
            job = _BACKTEST_JOBS.get(job_id)
            if job is not None:
                started = float(job.get("_started_monotonic") or monotonic())
                job["elapsed_seconds"] = round(monotonic() - started, 3)
                job["completed_at"] = now_app_time().isoformat()


def _start_backtest_job(query: dict[str, list[str]]) -> dict[str, object]:
    query_copy = {key: [str(value) for value in values] for key, values in query.items() if key != "job_id"}
    query_key = _backtest_job_query_key(query_copy)
    with _BACKTEST_JOB_LOCK:
        for existing in reversed(list(_BACKTEST_JOBS.values())):
            if existing.get("_query_key") == query_key and existing.get("status") in {"queued", "running"}:
                return _public_backtest_job(existing)
        active_jobs = sum(1 for item in _BACKTEST_JOBS.values() if item.get("status") in {"queued", "running"})
        if active_jobs >= BACKTEST_JOB_ACTIVE_LIMIT:
            raise ValueError(f"已有 {active_jobs} 个回测任务正在执行或排队，请等待任务完成后再提交。")
        job_id = uuid4().hex
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now_app_time().isoformat(),
            "started_at": None,
            "completed_at": None,
            "elapsed_seconds": 0.0,
            "error": "",
            "result_available": False,
            "performance": {},
            "redirect_url": _backtest_job_redirect(query_copy, job_id),
            "_query_key": query_key,
        }
        _BACKTEST_JOBS[job_id] = job
        while len(_BACKTEST_JOBS) > BACKTEST_JOB_HISTORY_LIMIT:
            expired_job_id = next(
                (
                    candidate_id
                    for candidate_id, candidate in _BACKTEST_JOBS.items()
                    if candidate_id != job_id and candidate.get("status") in {"completed", "failed"}
                ),
                "",
            )
            if not expired_job_id:
                break
            _BACKTEST_JOBS.pop(expired_job_id, None)
            _BACKTEST_JOB_RESULTS.pop(expired_job_id, None)
        _BACKTEST_JOB_EXECUTOR.submit(_run_backtest_job, job_id, query_copy)
        return _public_backtest_job(job)


def _public_backtest_job(job: dict[str, object]) -> dict[str, object]:
    payload = {key: deepcopy(value) for key, value in job.items() if not key.startswith("_")}
    if job.get("status") == "running":
        started = float(job.get("_started_monotonic") or monotonic())
        payload["elapsed_seconds"] = round(monotonic() - started, 3)
    return payload


def _backtest_job_status(job_id: str) -> dict[str, object] | None:
    with _BACKTEST_JOB_LOCK:
        job = _BACKTEST_JOBS.get(str(job_id).strip())
        return _public_backtest_job(job) if job is not None else None


def _backtest_job_result(job_id: str) -> tuple[dict[str, object], dict[str, object], str | None] | None:
    with _BACKTEST_JOB_LOCK:
        result = _BACKTEST_JOB_RESULTS.get(str(job_id).strip())
        return deepcopy(result) if result is not None else None


def _backtest_payload(query: dict[str, list[str]]) -> tuple[dict[str, object], dict[str, object], str | None]:
    job_id = _get_first(query, "job_id", "").strip()
    if job_id:
        result = _backtest_job_result(job_id)
        if result is not None:
            return result
    runtime_config, scanner = APP_STATE.snapshot()
    return backtest_handlers._backtest_payload(
        query,
        runtime_config=runtime_config,
        scanner=scanner,
        resolve_execution_config=resolve_execution_config_from_binance,
    )


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
                payload, params = _scan_payload(query, force_refresh=True)
                html = render_index_page(
                    summary=payload["summary"],
                    signals=payload["signals"],
                    params=params,
                    intervals=["15m", "1h", "2h", "4h", "1d"],
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

            if parsed.path == "/api/market/realtime":
                self._send_text(
                    json.dumps(_realtime_market_payload(query), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/scan":
                payload, _ = _scan_payload(query, force_refresh=_parse_bool_flag(query, "refresh"))
                self._send_text(
                    json.dumps(payload, ensure_ascii=False),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/btc/signal":
                self._send_text(
                    json.dumps(_to_jsonable(_btc_signal_payload(query)), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/btc/signal":
                payload = _btc_signal_payload(query)
                html = render_btc_signal_page(
                    summary=payload["summary"],
                    fast=_parse_bool_flag(query, "fast"),
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
                return

            if parsed.path == "/backtest":
                payload, params, error = _backtest_payload(query)
                _record_backtest_run(params, payload, error)
                html = render_backtest_page(
                    params=params,
                    series_reports=payload["series_reports"],
                    portfolio_reports=payload["portfolio_reports"],
                    rebalance_reports=payload["rebalance_reports"],
                    parameter_sweep=payload["parameter_sweep"],
                    strategy_explanation=payload["strategy_explanation"],
                    performance=payload["performance"],
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
                    event_summary=payload["event_summary"],
                    account_metrics=payload["account_metrics"],
                    btc_trading=payload.get("btc_trading") if isinstance(payload.get("btc_trading"), dict) else None,
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

            if parsed.path == "/api/storage/status":
                self._send_text(
                    json.dumps(_local_data_store().status(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/research/carry/paper/status":
                self._send_text(
                    json.dumps(_carry_paper_status_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/research/stat-arb/defaults":
                self._send_text(
                    json.dumps(_stat_arb_defaults_payload(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/notifications/feishu/daily/status":
                self._send_text(
                    json.dumps(_feishu_daily_report_status_payload(), ensure_ascii=False, indent=2),
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

            if parsed.path.startswith("/api/backtest/jobs/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                job = _backtest_job_status(job_id)
                if job is None:
                    self._send_text(
                        json.dumps({"error": "回测任务不存在或已过期。"}, ensure_ascii=False),
                        status=HTTPStatus.NOT_FOUND,
                        content_type="application/json; charset=utf-8",
                    )
                    return
                self._send_text(
                    json.dumps(job, ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/strategy/templates":
                self._send_text(
                    json.dumps({"templates": list_strategy_templates()}, ensure_ascii=False, indent=2),
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
                _record_backtest_run(params, payload, error)
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
                                    "parameter_sweep": payload["parameter_sweep"],
                                    "performance": payload["performance"],
                                    "strategy_explanation": payload["strategy_explanation"],
                                    "error": error,
                                }
                            ),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        content_type="application/json; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ai-trade-backtest.json"'},
                    )
                    return
                if export_format == "csv":
                    self._send_text(
                        _backtest_export_csv(payload, params, error),
                        content_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ai-trade-backtest.csv"'},
                    )
                    return
                if export_format == "html":
                    self._send_text(
                        _backtest_export_html(payload, params, error),
                        content_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ai-trade-backtest.html"'},
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
                _record_backtest_run(params, payload, error)
                self._send_text(
                    json.dumps(
                        _to_jsonable(
                            {
                                "params": params,
                                "series_reports": payload["series_reports"],
                                "portfolio_reports": payload["portfolio_reports"],
                                "rebalance_reports": payload["rebalance_reports"],
                                "parameter_sweep": payload["parameter_sweep"],
                                "performance": payload["performance"],
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

            if parsed.path == "/static/scan_live.js":
                script = (BASE_DIR / "static" / "scan_live.js").read_text(encoding="utf-8")
                self._send_text(script, content_type="text/javascript; charset=utf-8")
                return

            if parsed.path == "/static/backtest.js":
                script = (BASE_DIR / "static" / "backtest.js").read_text(encoding="utf-8")
                self._send_text(script, content_type="text/javascript; charset=utf-8")
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
            if parsed.path == "/api/backtest/jobs":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                form = parse_qs(body, keep_blank_values=True)
                job = _start_backtest_job(form)
                self._send_text(
                    json.dumps(job, ensure_ascii=False, indent=2),
                    status=HTTPStatus.ACCEPTED,
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/strategy/templates/compile":
                request_payload = _mapping_from_request_body(self)
                template_id = str(request_payload.get("template_id") or "").strip()
                try:
                    payload = _compile_strategy_template_payload(template_id)
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

            if parsed.path == "/terminal/strategies/templates/compile":
                request_payload = _mapping_from_request_body(self)
                lang = normalize_language(str(request_payload.get("lang") or lang))
                self._active_lang = lang
                template_id = str(request_payload.get("template_id") or "").strip()
                try:
                    payload = _compile_strategy_template_payload(template_id)
                    template = payload.get("template") if isinstance(payload.get("template"), dict) else {}
                    label = str(template.get("label") or template_id)
                    message = (
                        f"策略模板“{label}”已生成回测和 paper 参数，执行开关保持关闭。"
                        if lang == "zh"
                        else f'Strategy template "{label}" compiled; all execution switches remain off.'
                    )
                    error = None
                except ValueError as exc:
                    payload = None
                    message = None
                    error = str(exc)
                html = render_terminal_module_page(
                    snapshot=_terminal_page_snapshot("strategies"),
                    module="strategies",
                    strategy_builder_result=payload,
                    strategy_builder_text="",
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

            if parsed.path == "/terminal/strategies/stat-arb/run":
                request_payload = _mapping_from_request_body(self)
                lang = normalize_language(str(request_payload.get("lang") or lang))
                self._active_lang = lang
                try:
                    stat_arb_result = _run_stat_arb_backtest_payload(request_payload)
                    report = stat_arb_result.get("report") if isinstance(stat_arb_result.get("report"), dict) else {}
                    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
                    stat_arb_message = (
                        f"配对回测完成：{int(metrics.get('trade_count') or 0)} 笔，净收益 {float(metrics.get('net_pnl') or 0):+.4f}。"
                        if lang == "zh"
                        else f"Pair backtest completed: {int(metrics.get('trade_count') or 0)} trades, net PnL {float(metrics.get('net_pnl') or 0):+.4f}."
                    )
                    stat_arb_error = None
                except ValueError as exc:
                    stat_arb_result = None
                    stat_arb_message = None
                    stat_arb_error = str(exc)
                html = render_terminal_module_page(
                    snapshot=_terminal_page_snapshot("strategies"),
                    module="strategies",
                    stat_arb_result=stat_arb_result,
                    stat_arb_params=request_payload,
                    stat_arb_message=stat_arb_message,
                    stat_arb_error=stat_arb_error,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(
                    html,
                    content_type="text/html; charset=utf-8",
                    status=HTTPStatus.BAD_REQUEST if stat_arb_error else HTTPStatus.OK,
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
                        parameter_sweep=backtest_payload["parameter_sweep"],
                        strategy_explanation=backtest_payload["strategy_explanation"],
                        performance=backtest_payload["performance"],
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
                    positions=status_payload["open_positions"],
                    events=status_payload["events"],
                    event_summary=status_payload["event_summary"],
                    account_metrics=status_payload["account_metrics"],
                    btc_trading=status_payload.get("btc_trading") if isinstance(status_payload.get("btc_trading"), dict) else None,
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
                status = _start_paper_auto_trading(interval_seconds, force_paper=False)
                message = (
                    f"策略自动轮询已启动：每 {int(status['interval_seconds'])} 秒按当前模拟/实盘开关运行一轮。"
                    if lang == "zh"
                    else f"Strategy auto polling started: one run every {int(status['interval_seconds'])} seconds using current paper/live switches."
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
                message = "策略自动轮询已停止。" if lang == "zh" else "Strategy auto polling stopped."
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

            if parsed.path == "/api/research/carry/paper/run":
                self._send_text(
                    json.dumps(_run_carry_paper_once(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/research/stat-arb/backtest":
                try:
                    stat_arb_payload = _run_stat_arb_backtest_payload(_mapping_from_request_body(self))
                except ValueError as exc:
                    self._send_text(
                        json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2),
                        status=HTTPStatus.BAD_REQUEST,
                        content_type="application/json; charset=utf-8",
                    )
                    return
                self._send_text(
                    json.dumps(
                        stat_arb_payload,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/terminal/basis/carry/run":
                result = _run_carry_paper_once()
                message = (
                    f"Carry 模拟轮询完成：新开 {int(result.get('opened_count') or 0)}，平仓 {int(result.get('closed_count') or 0)}。"
                    if lang == "zh"
                    else f"Carry paper cycle completed: {int(result.get('opened_count') or 0)} opened, {int(result.get('closed_count') or 0)} closed."
                )
                html = render_terminal_module_page(
                    snapshot=_terminal_page_snapshot("basis"),
                    module="basis",
                    message=message,
                    lang=lang,
                    layout_context=_layout_context(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
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

            if parsed.path == "/api/trading/auto/start":
                form = parse_qs(_read_body(self))
                interval_seconds = _parse_int_value(
                    _get_first(form, "interval_seconds", str(PAPER_AUTO_DEFAULT_INTERVAL_SECONDS)),
                    "Auto Trade Interval",
                )
                self._send_text(
                    json.dumps(_start_paper_auto_trading(interval_seconds, force_paper=False), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/auto/stop":
                self._send_text(
                    json.dumps(_stop_paper_auto_trading(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/trading/paper/auto/stop":
                self._send_text(
                    json.dumps(_stop_paper_auto_trading(), ensure_ascii=False, indent=2),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/notifications/feishu/daily/run":
                form = parse_qs(_read_body(self))
                result = _run_feishu_daily_report_once(now=_manual_feishu_report_at(form))
                self._send_text(
                    json.dumps(
                        {"result": result, "status": _feishu_daily_report_status_payload()},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    content_type="application/json; charset=utf-8",
                )
                return

            if parsed.path == "/api/btc/signal/push":
                form = parse_qs(_read_body(self))
                self._send_text(
                    json.dumps(_to_jsonable(_push_btc_signal_payload(form)), ensure_ascii=False, indent=2),
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

    def _send_text(
        self,
        body: str,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = body.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            if hasattr(self, "_active_lang"):
                self.send_header("Set-Cookie", f"ai_trade_lang={self._active_lang}; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

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
    _start_feishu_daily_report_scheduler()
    print(f"Serving on http://{resolved_host}:{resolved_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        _stop_feishu_daily_report_scheduler()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
