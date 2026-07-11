from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from threading import RLock

from .binance_client import parse_ticker
from .config import SETTINGS
from .main_settings import _get_first, _parse_int_value, _parse_float_value, _validate_choice, _validate_range
from .runtime_config import RuntimeConfig, SCAN_TIER_THRESHOLD_FIELDS
from .service import (
    FALLBACK_SCAN_BASES,
    LEVERAGED_SUFFIXES,
    STABLELIKE_BASES,
    select_tickers_for_scan,
)
from .time_utils import now_app_time
from .ui import format_signal_row

SCAN_SYNC_TIMEOUT_SECONDS = 0.8
SCAN_INTERVALS = {"15m", "1h", "2h", "4h", "1d"}
SCAN_VIEW_MODES = {"cards", "table"}
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
        *(params.get(key) for key in SCAN_TIER_THRESHOLD_FIELDS),
        params.get("community_provider", ""),
        params.get("x_provider", ""),
        params.get("x_account_mode", ""),
    )


def _signal_sort_key(signal: dict[str, object]) -> tuple[float, float, str]:
    try:
        score = float(signal.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        quote_volume_m = float(signal.get("quote_volume_m") or 0.0)
    except (TypeError, ValueError):
        quote_volume_m = 0.0
    return (-score, -quote_volume_m, str(signal.get("symbol") or ""))


def _sort_scan_payload_signals(payload: dict[str, object]) -> dict[str, object]:
    signals = payload.get("signals")
    if isinstance(signals, list):
        payload = dict(payload)
        payload["signals"] = sorted(
            [signal for signal in signals if isinstance(signal, dict)],
            key=_signal_sort_key,
        )
    return payload


def _cached_scan_payload(cache_key: tuple[object, ...]) -> dict[str, object] | None:
    now = now_app_time()
    with _SCAN_CACHE_LOCK:
        cached = _SCAN_PAYLOAD_CACHE.get(cache_key)
        if cached and cached[0] > now:
            payload = _sort_scan_payload_signals(dict(cached[1]))
            payload["cached"] = True
            return payload
    return None


def _store_scan_payload(cache_key: tuple[object, ...], payload: dict[str, object]) -> None:
    with _SCAN_CACHE_LOCK:
        _SCAN_PAYLOAD_CACHE[cache_key] = (
            now_app_time() + timedelta(seconds=SETTINGS.scan_ttl_seconds),
            dict(payload),
        )


def _annotate_scan_summary(payload: dict[str, object]) -> dict[str, object]:
    payload = _sort_scan_payload_signals(payload)
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
            "price_vs_ema20_pct": float(getattr(indicators, "price_vs_ema20_pct", 0.0) or 0.0),
            "recent_change_pct": float(getattr(indicators, "recent_change_pct", 0.0) or 0.0),
            "support_level": float(getattr(indicators, "support_level", 0.0) or 0.0),
            "resistance_level": float(getattr(indicators, "resistance_level", 0.0) or 0.0),
            "support_distance_pct": float(getattr(indicators, "support_distance_pct", 0.0) or 0.0),
            "resistance_distance_pct": float(getattr(indicators, "resistance_distance_pct", 0.0) or 0.0),
            "support_strength": float(getattr(indicators, "support_strength", 0.0) or 0.0),
            "resistance_strength": float(getattr(indicators, "resistance_strength", 0.0) or 0.0),
            "structure_risk_reward": float(getattr(indicators, "structure_risk_reward", 0.0) or 0.0),
            "pullback_from_high_pct": float(getattr(indicators, "pullback_from_high_pct", 0.0) or 0.0),
            "volume_ratio": float(getattr(indicators, "volume_ratio", 1.0) or 1.0),
            "buy_pressure_ratio": float(getattr(indicators, "buy_pressure_ratio", 0.5) or 0.5),
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
            "liquidity_eligible": bool(getattr(signal, "liquidity_eligible", True)),
            "liquidity_tier": str(getattr(signal, "liquidity_tier", "")),
            "liquidity_issue": str(getattr(signal, "liquidity_issue", "")),
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


def _fallback_ticker_rows(scanner: object, quote_asset: str) -> list[dict]:
    gateway = getattr(scanner, "gateway", None)
    cached_ticker24hr = getattr(gateway, "cached_ticker24hr", None)
    if callable(cached_ticker24hr):
        try:
            cached_rows = cached_ticker24hr()
        except Exception:  # noqa: BLE001
            cached_rows = None
        if isinstance(cached_rows, list) and cached_rows:
            return [row for row in cached_rows if isinstance(row, dict)]

    ticker24hr = getattr(gateway, "ticker24hr", None)
    if callable(ticker24hr):
        try:
            rows = ticker24hr()
        except Exception:  # noqa: BLE001
            rows = None
        if isinstance(rows, list) and rows:
            return [row for row in rows if isinstance(row, dict)]

    ticker24hr_symbols = getattr(gateway, "ticker24hr_symbols", None)
    if callable(ticker24hr_symbols):
        symbols = [f"{base}{quote_asset}" for base in FALLBACK_SCAN_BASES if base != quote_asset]
        try:
            rows = ticker24hr_symbols(symbols)
        except Exception:  # noqa: BLE001
            rows = []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _ticker_base_asset(symbol: str, quote_asset: str) -> str:
    return symbol[: -len(quote_asset)] if symbol.endswith(quote_asset) else symbol


def _is_fallback_ticker_eligible(symbol: str, quote_asset: str) -> bool:
    if not symbol.endswith(quote_asset):
        return False
    base_asset = _ticker_base_asset(symbol, quote_asset)
    if not base_asset or base_asset in STABLELIKE_BASES:
        return False
    return not base_asset.endswith(LEVERAGED_SUFFIXES)


def _fallback_scan_payload(params: dict[str, object], warning: str, *, scanner: object) -> dict[str, object]:
    quote_asset = str(params["quote_asset"]).upper()
    ticker_rows = _fallback_ticker_rows(scanner, quote_asset)
    tickers = []
    for row in ticker_rows:
        try:
            ticker = parse_ticker(row)
        except (KeyError, TypeError, ValueError):
            continue
        if _is_fallback_ticker_eligible(ticker.symbol.upper(), quote_asset):
            tickers.append(ticker)
    eligible_symbols = {ticker.symbol for ticker in tickers}
    selected_tickers, filtered_tickers, liquidity_profiles, liquidity_tier_stats, liquidity_status = select_tickers_for_scan(
        tickers,
        eligible_symbols=eligible_symbols,
        quote_asset=quote_asset,
        profile_source=params,
        candidate_pool=int(params["candidate_pool"]),
        alt_min_quote_volume=float(params["min_quote_volume"]),
        alt_min_trade_count=int(params["min_trade_count"]),
    )
    signals = []
    for ticker in selected_tickers:
        status = liquidity_status[ticker.symbol]
        score = min(82.0, 50.0 + abs(ticker.price_change_percent) * 3 + min(ticker.quote_volume / 1_000_000_000, 10.0))
        signals.append(
            {
                "symbol": ticker.symbol,
                "score": round(score, 2),
                "grade": "B" if score >= 70 else "C",
                "reasons": ["实时 ticker 快速返回", f"24h 成交额 {ticker.quote_volume / 1_000_000:.1f}M"],
                "warnings": [item for item in (str(status["message"]), warning) if item],
                "liquidity_eligible": bool(status["eligible"]),
                "liquidity_tier": str(status["tier"]),
                "liquidity_issue": str(status["message"]),
                "last_price": ticker.last_price,
                "quote_volume_m": ticker.quote_volume / 1_000_000,
                "price_change_percent": ticker.price_change_percent,
                "rsi_14": 50.0,
                "ema_spread_pct": 0.0,
                "price_vs_ema20_pct": 0.0,
                "recent_change_pct": 0.0,
                "support_level": 0.0,
                "resistance_level": 0.0,
                "support_distance_pct": 0.0,
                "resistance_distance_pct": 0.0,
                "support_strength": 0.0,
                "resistance_strength": 0.0,
                "structure_risk_reward": 0.0,
                "pullback_from_high_pct": 0.0,
                "volume_ratio": 1.0,
                "buy_pressure_ratio": 0.5,
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
                    "liquidity": min(100.0, ticker.quote_volume / 10_000_000) if status["eligible"] else min(35.0, ticker.quote_volume / 10_000_000),
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
            "fetched_at": now_app_time().isoformat(),
            "eligible_symbols": len(filtered_tickers),
            "candidate_symbols": len(selected_tickers),
            "candidate_pool": int(params["candidate_pool"]),
            "liquidity_profiles": liquidity_profiles,
            "liquidity_tier_stats": liquidity_tier_stats,
        },
        "signals": signals,
        "cached": False,
        "fallback": True,
        "warning": warning,
    }


def _scan_payload(
    query: dict[str, list[str]],
    *,
    runtime_config: RuntimeConfig,
    scanner: object,
    force_refresh: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
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
        **{key: getattr(scan_defaults, key) for key in SCAN_TIER_THRESHOLD_FIELDS},
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
    if not force_refresh:
        cached_payload = _cached_scan_payload(cache_key)
        if cached_payload is not None:
            return cached_payload, params
    with _SCAN_CACHE_LOCK:
        future = _SCAN_INFLIGHT.get(cache_key)
        if future is None or future.done():
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
    '_signal_sort_key',
    '_sort_scan_payload_signals',
    '_cached_scan_payload',
    '_store_scan_payload',
    '_annotate_scan_summary',
    '_run_scan_payload',
    '_format_scan_signal_row',
    '_complete_scan_future',
    '_fallback_scan_payload',
    '_scan_payload',
]
