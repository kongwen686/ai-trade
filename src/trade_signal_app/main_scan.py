from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from threading import RLock

from .binance_client import parse_ticker
from .config import SETTINGS
from .main_settings import _get_first, _parse_int_value, _parse_float_value, _validate_choice, _validate_range
from .runtime_config import RuntimeConfig
from .ui import format_signal_row

SCAN_SYNC_TIMEOUT_SECONDS = 0.8
SCAN_INTERVALS = {"15m", "1h", "4h", "1d"}
SCAN_VIEW_MODES = {"cards", "table"}
MARKET_TICKER_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
_SCAN_CACHE_LOCK = RLock()
_SCAN_PAYLOAD_CACHE: dict[tuple[object, ...], tuple[datetime, dict[str, object]]] = {}
_SCAN_INFLIGHT: dict[tuple[object, ...], Future] = {}
_SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan-refresh")


def _to_jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    return value


def _parse_query_int(query: dict[str, list[str]], key: str, default: int, label: str) -> int:
    return _parse_int_value(_get_first(query, key, str(default)), label)


def _parse_query_float(query: dict[str, list[str]], key: str, default: float, label: str) -> float:
    return _parse_float_value(_get_first(query, key, str(default)), label)


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


def _fallback_scan_payload(params: dict[str, object], warning: str, *, scanner: object) -> dict[str, object]:
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


def _scan_payload(query: dict[str, list[str]], *, runtime_config: RuntimeConfig, scanner: object) -> tuple[dict[str, object], dict[str, object]]:
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
        payload = _fallback_scan_payload(params, f"完整扫描超过 {SCAN_SYNC_TIMEOUT_SECONDS} 秒，已返回实时 ticker 快速结果，后台继续刷新。", scanner=scanner)
    payload = _annotate_scan_summary(payload)
    _store_scan_payload(cache_key, payload)
    return payload, params


__all__ = [
    'SCAN_SYNC_TIMEOUT_SECONDS',
    '_SCAN_CACHE_LOCK',
    '_SCAN_PAYLOAD_CACHE',
    '_SCAN_INFLIGHT',
    '_SCAN_EXECUTOR',
    '_scan_cache_key',
    '_cached_scan_payload',
    '_store_scan_payload',
    '_annotate_scan_summary',
    '_run_scan_payload',
    '_format_scan_signal_row',
    '_complete_scan_future',
    '_fallback_scan_payload',
    '_scan_payload',
]
