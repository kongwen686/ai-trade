from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from html import escape
from pathlib import Path
import csv
import io
import json
from threading import RLock
from time import perf_counter
from urllib.parse import urlencode

from .backtest import (
    bars_per_day,
    group_archives,
    merge_candles,
    resolve_archive_paths,
    run_backtest_for_series,
    run_overnight_seasonality_backtest,
    run_portfolio_backtest,
    run_rebalance_premium_backtest,
)
from .main_settings import (
    FEE_MODELS,
    FEE_ROLES,
    FEE_SOURCES,
    SLIPPAGE_MODELS,
    _backtest_params_from_config,
    _get_first,
    _parse_bool_flag,
    _parse_float_value,
    _parse_int_value,
    _validate_choice,
    _validate_range,
)
from .presets import apply_backtest_preset
from .runtime_config import TRADINGVIEW_BARS_MAX, TRADINGVIEW_BARS_MIN, RuntimeConfig
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig
from .tradingview_data import fetch_tradingview_history
from .ui import format_backtest_report, format_portfolio_report, format_rebalance_premium_report
from .views_common import normalize_language


_BACKTEST_RESULT_CACHE_MAX_ENTRIES = 6
_BACKTEST_RESULT_CACHE_LOCK = RLock()
_BACKTEST_RESULT_CACHE: OrderedDict[str, dict[str, object]] = OrderedDict()


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


def _parse_query_int(query: dict[str, list[str]], key: str, default: int, label: str) -> int:
    return _parse_int_value(_get_first(query, key, str(default)), label)


def _parse_query_float(query: dict[str, list[str]], key: str, default: float, label: str) -> float:
    return _parse_float_value(_get_first(query, key, str(default)), label)


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


def _selected_cached_archive_if_available(*, exchange: object, symbol: object, interval: object) -> str:
    exchange_value = str(exchange).strip().upper()
    symbol_value = str(symbol).strip().upper()
    interval_value = str(interval).strip()
    if not all(value and value.replace("-", "").replace("_", "").isalnum() for value in (exchange_value, symbol_value, interval_value)):
        return ""
    candidate = Path("data/tradingview_klines") / exchange_value / symbol_value / f"{interval_value}.csv"
    return str(candidate) if resolve_archive_paths([str(candidate)]) else ""


def _backtest_cache_key(params: dict[str, object], paths: list[Path]) -> str:
    files = []
    for path in paths:
        stat = path.stat()
        files.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns))
    return json.dumps({"params": params, "files": files}, ensure_ascii=True, sort_keys=True, default=str)


def _cached_backtest_payload(cache_key: str) -> dict[str, object] | None:
    with _BACKTEST_RESULT_CACHE_LOCK:
        payload = _BACKTEST_RESULT_CACHE.get(cache_key)
        if payload is None:
            return None
        _BACKTEST_RESULT_CACHE.move_to_end(cache_key)
        return deepcopy(payload)


def _store_backtest_payload(cache_key: str, payload: dict[str, object]) -> None:
    with _BACKTEST_RESULT_CACHE_LOCK:
        _BACKTEST_RESULT_CACHE[cache_key] = deepcopy(payload)
        _BACKTEST_RESULT_CACHE.move_to_end(cache_key)
        while len(_BACKTEST_RESULT_CACHE) > _BACKTEST_RESULT_CACHE_MAX_ENTRIES:
            _BACKTEST_RESULT_CACHE.popitem(last=False)


def _minimum_required_backtest_bars(holding_periods: list[int], exit_config: ExitRuleConfig) -> int:
    max_horizon = max(max(holding_periods) + 1, exit_config.max_holding_bars + 1)
    return 60 + max_horizon


def _tradingview_fetch_result(form: dict[str, list[str]], *, runtime_config: RuntimeConfig, tradingview_cache_dir: object) -> dict[str, object]:
    symbol = _get_first(
        form,
        "tradingview_symbol",
        runtime_config.tradingview_symbols[0] if runtime_config.tradingview_symbols else "BTCUSDT",
    ).strip().upper()
    exchange = _get_first(form, "tradingview_exchange", runtime_config.tradingview_exchange).strip().upper() or "BINANCE"
    interval = _get_first(form, "tradingview_interval", runtime_config.tradingview_interval).strip() or runtime_config.tradingview_interval
    bars = _parse_int_value(_get_first(form, "tradingview_bars", str(runtime_config.tradingview_bars)), "TradingView Bars")
    _validate_range(bars, "TradingView Bars", minimum=TRADINGVIEW_BARS_MIN, maximum=TRADINGVIEW_BARS_MAX)

    result = fetch_tradingview_history(
        cache_root=tradingview_cache_dir,
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


def _tradingview_backtest_redirect(form: dict[str, list[str]], lang: str, *, runtime_config: RuntimeConfig, tradingview_cache_dir: object) -> str:
    result = _tradingview_fetch_result(form, runtime_config=runtime_config, tradingview_cache_dir=tradingview_cache_dir)
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


def _backtest_payload(
    query: dict[str, list[str]],
    *,
    runtime_config: RuntimeConfig,
    scanner: object,
    resolve_execution_config,
) -> tuple[dict[str, object], dict[str, object], str | None]:
    request_started = perf_counter()
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
        "volatility_filter_enabled": _parse_bool_flag(query, "volatility_filter_enabled"),
        "block_extreme_volatility": _parse_bool_flag(query, "block_extreme_volatility"),
        "max_entry_volatility_percentile": _parse_query_float(
            query,
            "max_entry_volatility_percentile",
            base_params["max_entry_volatility_percentile"],
            "Max Volatility Percentile",
        ),
        "max_entry_volatility_ratio": _parse_query_float(
            query,
            "max_entry_volatility_ratio",
            base_params["max_entry_volatility_ratio"],
            "Max Volatility Ratio",
        ),
        "stability_checks": _parse_bool_flag(query, "stability_checks"),
        "parameter_sweep": _parse_bool_flag(query, "parameter_sweep"),
        "tradingview_exchange": _get_first(query, "tradingview_exchange", runtime_config.tradingview_exchange),
        "tradingview_symbol": _get_first(
            query,
            "tradingview_symbol",
            runtime_config.tradingview_symbols[0] if runtime_config.tradingview_symbols else "BTCUSDT",
        ),
        "tradingview_interval": _get_first(query, "tradingview_interval", runtime_config.tradingview_interval),
        "tradingview_bars": _parse_query_int(query, "tradingview_bars", runtime_config.tradingview_bars, "TradingView Bars"),
        "tv_fetched": _parse_bool_flag(query, "tv_fetched"),
        "sample_start_at": "全部历史 K 线",
    }
    if not str(params["archives"]).strip() and query:
        params["archives"] = _selected_cached_archive_if_available(
            exchange=params["tradingview_exchange"],
            symbol=params["tradingview_symbol"],
            interval=params["tradingview_interval"],
        )
    if "no_binance_discount" not in query:
        params["no_binance_discount"] = bool(base_params["no_binance_discount"])
    if "no_kdj_confirmation" not in query:
        params["no_kdj_confirmation"] = bool(base_params["no_kdj_confirmation"])
    if "volatility_filter_enabled" not in query:
        params["volatility_filter_enabled"] = bool(base_params["volatility_filter_enabled"])
    if "block_extreme_volatility" not in query:
        params["block_extreme_volatility"] = bool(base_params["block_extreme_volatility"])

    archive_patterns = _split_archives(str(params["archives"]))
    if not archive_patterns:
        error = "没有填写 ZIP/CSV 历史数据；可先使用右侧 TradingView 拉取，或填入本地缓存路径。" if query else None
        return _empty_backtest_payload(params), params, error

    resolve_started = perf_counter()
    paths = resolve_archive_paths(archive_patterns)
    resolve_archives_seconds = perf_counter() - resolve_started
    if not paths:
        return _empty_backtest_payload(params), params, "没有匹配到任何 ZIP/CSV 历史 K 线文件。"

    cache_key = _backtest_cache_key(params, paths) if str(params["fee_source"]) == "manual" else ""
    cached_payload = _cached_backtest_payload(cache_key) if cache_key else None
    if cached_payload is not None:
        cached_payload["performance"] = {
            **dict(cached_payload.get("performance") or {}),
            "cache_hit": True,
            "total_seconds": round(perf_counter() - request_started, 4),
            "resolve_archives_seconds": round(resolve_archives_seconds, 4),
        }
        return cached_payload, params, None

    holding_periods = [int(item) for item in str(params["holding_periods"]).split(",") if item.strip()]
    entry_config = EntryRuleConfig(
        min_score=float(params["score_threshold"]),
        min_volume_ratio=float(params["min_volume_ratio"]),
        min_buy_pressure_ratio=float(params["min_buy_pressure"]),
        min_rsi=float(params["min_rsi"]),
        max_rsi=float(params["max_rsi"]),
        max_entry_rsi=float(params["max_rsi"]),
        require_kdj_confirmation=not bool(params["no_kdj_confirmation"]),
        volatility_filter_enabled=bool(params["volatility_filter_enabled"]),
        block_extreme_volatility=bool(params["block_extreme_volatility"]),
        max_entry_volatility_percentile=float(params["max_entry_volatility_percentile"]),
        max_entry_volatility_ratio=float(params["max_entry_volatility_ratio"]),
    )
    exit_config = ExitRuleConfig(
        max_holding_bars=int(params["max_holding_bars"]),
        stop_loss_pct=float(params["stop_loss_pct"]),
        take_profit_pct=float(params["take_profit_pct"]),
        cooldown_bars_after_exit=int(params["cooldown_bars"]),
    )
    minimum_required_bars = _minimum_required_backtest_bars(holding_periods, exit_config)
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
            resolve_execution_config(
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
    data_warnings: list[str] = []
    load_data_seconds = 0.0
    series_backtest_seconds = 0.0
    candle_count = 0
    for (symbol, interval), archive_paths in sorted(grouped.items()):
        is_overnight_preset = str(params["preset"]) == "btc_overnight_seasonality"
        analysis_cache = {}
        load_started = perf_counter()
        candles = merge_candles(archive_paths)
        load_data_seconds += perf_counter() - load_started
        if not candles:
            data_warnings.append(f"{symbol} {interval} 已跳过：没有可回测 K 线。")
            continue
        candle_count += len(candles)
        candles_by_interval.setdefault(interval, {})[symbol] = candles
        if not is_overnight_preset and len(candles) < int(params["lookback_bars"]):
            data_warnings.append(
                f"{symbol} {interval} 有效样本只有 {len(candles)} 根 K 线，低于当前 lookback {int(params['lookback_bars'])}；"
                "当前回测会使用输入文件中的全部历史 K 线。"
            )
        if not is_overnight_preset and len(candles) < minimum_required_bars:
            data_warnings.append(
                f"{symbol} {interval} 已跳过：至少需要 {minimum_required_bars} 根 K 线才能覆盖指标预热和退出窗口，"
                f"当前样本共 {len(candles)} 根。"
            )
            continue
        try:
            report_execution_config = (
                resolve_execution_config(
                    gateway=scanner.gateway,
                    execution_config=account_execution_config,
                    symbol=symbol,
                )
                if execution_config.fee_source == "symbol"
                else account_execution_config
            )
        except Exception as exc:  # noqa: BLE001
            return _empty_backtest_payload(params), params, str(exc)
        if is_overnight_preset:
            try:
                series_started = perf_counter()
                report = run_overnight_seasonality_backtest(
                    symbol=symbol,
                    interval=interval,
                    candles=candles,
                    execution_config=report_execution_config,
                )
                series_backtest_seconds += perf_counter() - series_started
            except ValueError as exc:
                data_warnings.append(f"{symbol} {interval} 已跳过：{exc}")
                continue
        else:
            try:
                series_started = perf_counter()
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
                    sample_start_time=None,
                    analysis_cache=analysis_cache,
                )
                series_backtest_seconds += perf_counter() - series_started
            except ValueError as exc:
                data_warnings.append(f"{symbol} {interval} 已跳过：{exc}")
                continue
        reports_by_interval.setdefault(interval, []).append(report)
        series_reports.append(format_backtest_report(report))
        series_contexts.append((symbol, interval, candles, report_execution_config, None, analysis_cache))

    portfolio_started = perf_counter()
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
    portfolio_seconds = perf_counter() - portfolio_started

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

    stability_started = perf_counter()
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
    stability_seconds = perf_counter() - stability_started
    parameter_sweep_started = perf_counter()
    parameter_sweep = (
        _run_backtest_parameter_sweep(
            series_contexts=series_contexts,
            params=params,
            holding_periods=holding_periods,
            entry_config=entry_config,
            exit_config=exit_config,
        )
        if bool(params["parameter_sweep"])
        and str(params["preset"]) not in {"btc_overnight_seasonality", "crypto_rebalance_premium"}
        else []
    )
    parameter_sweep_seconds = perf_counter() - parameter_sweep_started

    payload = {
        "series_reports": series_reports,
        "portfolio_reports": portfolio_reports,
        "rebalance_reports": rebalance_reports,
        "parameter_sweep": parameter_sweep,
        "performance": {
            "cache_hit": False,
            "total_seconds": round(perf_counter() - request_started, 4),
            "resolve_archives_seconds": round(resolve_archives_seconds, 4),
            "load_data_seconds": round(load_data_seconds, 4),
            "series_backtest_seconds": round(series_backtest_seconds, 4),
            "portfolio_seconds": round(portfolio_seconds, 4),
            "stability_seconds": round(stability_seconds, 4),
            "parameter_sweep_seconds": round(parameter_sweep_seconds, 4),
            "series_count": len(series_reports),
            "candle_count": candle_count,
        },
        "strategy_explanation": _build_backtest_strategy_explanation(
            params=params,
            series_reports=series_reports,
            portfolio_reports=portfolio_reports,
            rebalance_reports=rebalance_reports,
            stability_checks=stability_checks,
            parameter_sweep=parameter_sweep,
            data_warnings=data_warnings,
        ),
    }
    if cache_key:
        _store_backtest_payload(cache_key, payload)
    return payload, params, None


def _empty_backtest_payload(params: dict[str, object], *, data_warnings: list[str] | None = None) -> dict[str, object]:
    return {
        "series_reports": [],
        "portfolio_reports": [],
        "rebalance_reports": [],
        "parameter_sweep": [],
        "performance": {
            "cache_hit": False,
            "total_seconds": 0.0,
            "resolve_archives_seconds": 0.0,
            "load_data_seconds": 0.0,
            "series_backtest_seconds": 0.0,
            "portfolio_seconds": 0.0,
            "stability_seconds": 0.0,
            "parameter_sweep_seconds": 0.0,
            "series_count": 0,
            "candle_count": 0,
        },
        "strategy_explanation": _build_backtest_strategy_explanation(
            params=params,
            series_reports=[],
            portfolio_reports=[],
            rebalance_reports=[],
            stability_checks=[],
            parameter_sweep=[],
            data_warnings=data_warnings or [],
        ),
    }


def _run_backtest_stability_checks(
    *,
    series_contexts: list[tuple[str, str, list, ExecutionConfig, datetime | None, dict]],
    params: dict[str, object],
    holding_periods: list[int],
    entry_config: EntryRuleConfig,
    exit_config: ExitRuleConfig,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    base_score = float(params["score_threshold"])
    base_slippage = float(params["slippage_bps"])
    for symbol, interval, candles, execution_config, sample_start_time, analysis_cache in series_contexts[:2]:
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
                    sample_start_time=sample_start_time,
                    analysis_cache=analysis_cache,
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
                sample_start_time=sample_start_time,
                analysis_cache=None,
            )
            item.update(window)
            checks.append(item)
    return checks


def _run_backtest_parameter_sweep(
    *,
    series_contexts: list[tuple[str, str, list, ExecutionConfig, datetime | None, dict]],
    params: dict[str, object],
    holding_periods: list[int],
    entry_config: EntryRuleConfig,
    exit_config: ExitRuleConfig,
) -> list[dict[str, object]]:
    """Run a bounded 3x3 sensitivity grid on the first valid full-history series."""
    if not series_contexts:
        return []
    symbol, interval, candles, execution_config, sample_start_time, analysis_cache = series_contexts[0]
    base_score = float(params["score_threshold"])
    base_stop = float(params["stop_loss_pct"])
    score_values = sorted({round(max(0.0, min(100.0, base_score + delta)), 2) for delta in (-4.0, 0.0, 4.0)})
    stop_values = sorted({round(max(0.1, min(50.0, base_stop * factor)), 2) for factor in (0.75, 1.0, 1.25)})
    results: list[dict[str, object]] = []
    for stop_loss_pct in stop_values:
        for score_threshold in score_values:
            item = _run_single_stability_check(
                symbol=symbol,
                interval=interval,
                check_name="parameter_sweep",
                candles=candles,
                params=params,
                holding_periods=holding_periods,
                entry_config=replace(entry_config, min_score=score_threshold),
                exit_config=replace(exit_config, stop_loss_pct=stop_loss_pct),
                execution_config=execution_config,
                sample_start_time=sample_start_time,
                analysis_cache=analysis_cache,
            )
            item.update(
                {
                    "score_threshold": score_threshold,
                    "stop_loss_pct": stop_loss_pct,
                    "base_cell": score_threshold == round(base_score, 2) and stop_loss_pct == round(base_stop, 2),
                    "scope": "first_series_full_history",
                }
            )
            if item.get("status") == "ok":
                final_equity = float(item.get("final_equity", 1.0))
                max_drawdown_pct = float(item.get("max_drawdown_pct", 0.0))
                return_pct = (final_equity - 1.0) * 100.0
                item["return_pct"] = round(return_pct, 4)
                item["risk_adjusted_return"] = round(return_pct / max(abs(max_drawdown_pct), 1.0), 4)
            results.append(item)
    return results


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
    sample_start_time: datetime | None,
    analysis_cache: dict | None = None,
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
            sample_start_time=sample_start_time,
            analysis_cache=analysis_cache,
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
    parameter_sweep: list[dict[str, object]],
    data_warnings: list[str] | None = None,
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
    successful_sweep = [item for item in parameter_sweep if item.get("status") == "ok"]
    best_sweep = max(
        successful_sweep,
        key=lambda item: (
            float(item.get("risk_adjusted_return", -1_000_000.0)),
            float(item.get("return_pct", -1_000_000.0)),
            bool(item.get("base_cell")),
        ),
        default=None,
    )
    if bool(params.get("parameter_sweep")) and not parameter_sweep:
        diagnostics.append("参数热力图未产生结果；当前预设不适用二维扫描，或没有有效单币种样本。")
    elif successful_sweep:
        positive_cells = sum(1 for item in successful_sweep if float(item.get("return_pct", 0.0)) > 0.0)
        diagnostics.append(f"参数邻域扫描完成 {len(successful_sweep)} 个组合，其中 {positive_cells} 个组合取得正收益。")
    if data_warnings:
        diagnostics = [*data_warnings, *diagnostics]
    cost_notes = _backtest_cost_notes(params)
    notes = [
        strategy_summary,
        "数据窗口：使用输入文件中的全部历史 K 线；不再按固定起点排除早期 K 线。",
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
        "parameter_sweep_enabled": bool(params.get("parameter_sweep")),
        "parameter_sweep": parameter_sweep,
        "best_parameter_cell": best_sweep,
        "notes": notes,
    }


def _backtest_strategy_type(preset: str) -> tuple[str, str]:
    mapping = {
        "breakout_aggressive": ("breakout", "区间突破 / 动量延续模板，强调高评分、强量能和较短持有周期。"),
        "portfolio_rotation": ("momentum_rotation", "动量轮动模板，先横截面筛选强势标的，再用组合层 top N 控制集中度。"),
        "trend_pullback_conservative": ("trend_pullback", "趋势回踩模板，等待支撑、量价恢复和波动率回落后再入场。"),
        "breakout_confirmed": ("confirmed_breakout", "确认突破模板，要求评分、量能、买压和波动率共同通过。"),
        "mean_reversion_guarded": ("guarded_mean_reversion", "受控均值回归模板，使用短持仓、冷却期和反弹确认限制接飞刀风险。"),
        "quality_rotation": ("quality_rotation", "高质量轮动模板，在主流高流动性标的中选择量价与评分前排。"),
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

    for item in payload.get("parameter_sweep", []):
        if not isinstance(item, dict):
            continue
        name = f'score_{item.get("score_threshold", "")}_stop_{item.get("stop_loss_pct", "")}'
        interval = item.get("interval", "")
        writer.writerow(["sensitivity", name, interval, "status", item.get("status", "")])
        for metric in (
            "symbol",
            "score_threshold",
            "stop_loss_pct",
            "final_equity",
            "return_pct",
            "max_drawdown_pct",
            "profit_factor",
            "signal_count",
            "risk_adjusted_return",
            "base_cell",
        ):
            if metric in item:
                writer.writerow(["sensitivity", name, interval, metric, item.get(metric, "")])
        if item.get("status") != "ok":
            writer.writerow(["sensitivity", name, interval, "message", item.get("message", "")])

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


def _backtest_export_html(payload: dict[str, object], params: dict[str, object], error: str | None) -> str:
    series_reports = [item for item in payload.get("series_reports", []) if isinstance(item, dict)]
    portfolio_reports = [item for item in payload.get("portfolio_reports", []) if isinstance(item, dict)]
    sweep = [item for item in payload.get("parameter_sweep", []) if isinstance(item, dict) and item.get("status") == "ok"]
    explanation = payload.get("strategy_explanation") if isinstance(payload.get("strategy_explanation"), dict) else {}
    param_rows = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in sorted(params.items())
    )
    result_rows: list[str] = []
    for report in series_reports:
        stat = report.get("trade_stat") if isinstance(report.get("trade_stat"), dict) else {}
        result_rows.append(
            "<tr>"
            f"<td>{escape(str(report.get('symbol', '')))}</td>"
            f"<td>{escape(str(report.get('interval', '')))}</td>"
            f"<td>{float(report.get('final_equity', 1.0)):.4f}</td>"
            f"<td>{float(report.get('max_drawdown_pct', 0.0)):+.2f}%</td>"
            f"<td>{float(stat.get('win_rate_pct', 0.0)):.2f}%</td>"
            f"<td>{float(stat.get('profit_factor', 0.0)):.3f}</td>"
            f"<td>{int(report.get('signal_count', 0))}</td>"
            "</tr>"
        )
    for report in portfolio_reports:
        stat = report.get("trade_stat") if isinstance(report.get("trade_stat"), dict) else {}
        result_rows.append(
            "<tr>"
            f"<td>Portfolio Top {int(report.get('top_n', 0))}</td>"
            f"<td>{escape(str(report.get('interval', '')))}</td>"
            f"<td>{float(report.get('final_equity', 1.0)):.4f}</td>"
            f"<td>{float(report.get('max_drawdown_pct', 0.0)):+.2f}%</td>"
            f"<td>{float(stat.get('win_rate_pct', 0.0)):.2f}%</td>"
            f"<td>{float(stat.get('profit_factor', 0.0)):.3f}</td>"
            f"<td>{int(report.get('batch_count', 0))}</td>"
            "</tr>"
        )
    score_values = sorted({float(item.get("score_threshold", 0.0)) for item in sweep})
    stop_values = sorted({float(item.get("stop_loss_pct", 0.0)) for item in sweep})
    sweep_lookup = {
        (float(item.get("stop_loss_pct", 0.0)), float(item.get("score_threshold", 0.0))): item
        for item in sweep
    }
    heatmap_rows = []
    for stop_loss_pct in stop_values:
        cells = []
        for score_threshold in score_values:
            item = sweep_lookup.get((stop_loss_pct, score_threshold))
            return_pct = float(item.get("return_pct", 0.0)) if item else 0.0
            tone = "positive" if return_pct > 0 else "negative"
            cells.append(
                f'<td class="{tone}"><strong>{return_pct:+.2f}%</strong>'
                f'<small>Eq {float(item.get("final_equity", 1.0)):.3f} / DD {float(item.get("max_drawdown_pct", 0.0)):+.2f}%</small></td>'
                if item
                else "<td>-</td>"
            )
        heatmap_rows.append(f"<tr><th>{stop_loss_pct:.2f}%</th>{''.join(cells)}</tr>")
    heatmap_html = (
        "<table><thead><tr><th>Stop \\ Score</th>"
        + "".join(f"<th>{value:.1f}</th>" for value in score_values)
        + f"</tr></thead><tbody>{''.join(heatmap_rows)}</tbody></table>"
        if sweep
        else "<p>Parameter sweep was not enabled or produced no valid result.</p>"
    )
    notes = explanation.get("notes") if isinstance(explanation.get("notes"), list) else []
    notes_html = "".join(f"<li>{escape(str(note))}</li>" for note in notes)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Trade Backtest Report</title>
  <style>
    :root {{ color-scheme: light; font-family: "Avenir Next", "PingFang SC", sans-serif; color: #172033; background: #eef4fb; }}
    body {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1, h2 {{ margin: 0 0 12px; }} p, li {{ line-height: 1.6; color: #526079; }}
    section {{ margin-top: 18px; padding: 20px; border: 1px solid #dce5f0; border-radius: 14px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }} th, td {{ padding: 10px; border: 1px solid #e1e8f0; text-align: left; }}
    th {{ background: #f5f8fc; }} td.positive {{ background: #e9fbf3; color: #087454; }} td.negative {{ background: #fff0f0; color: #b42332; }}
    td small {{ display: block; margin-top: 4px; opacity: .8; }} .scroll {{ overflow-x: auto; }} .error {{ color: #b42332; }}
  </style>
</head>
<body>
  <h1>AI Trade 回测研究报告</h1>
  <p>{escape(str(explanation.get("summary") or "基于当前参数生成的离线研究报告。"))}</p>
  {f'<p class="error">{escape(error)}</p>' if error else ''}
  <section><h2>结果摘要</h2><div class="scroll"><table><thead><tr><th>标的/组合</th><th>周期</th><th>最终权益</th><th>最大回撤</th><th>胜率</th><th>PF</th><th>样本数</th></tr></thead><tbody>{''.join(result_rows)}</tbody></table></div></section>
  <section><h2>参数敏感度热力图</h2><p>行是止损比例，列是评分阈值；绿色为正收益，红色为非正收益。</p><div class="scroll">{heatmap_html}</div></section>
  <section><h2>参数</h2><div class="scroll"><table><tbody>{param_rows}</tbody></table></div></section>
  <section><h2>研究说明</h2><ul>{notes_html}</ul></section>
</body>
</html>"""


__all__ = [
    '_path_with_lang',
    '_split_archives',
    '_tradingview_fetch_result',
    '_tradingview_backtest_redirect',
    '_backtest_payload',
    '_empty_backtest_payload',
    '_run_backtest_stability_checks',
    '_run_single_stability_check',
    '_walk_forward_validation_windows',
    '_build_backtest_strategy_explanation',
    '_backtest_strategy_type',
    '_backtest_cost_notes',
    '_backtest_diagnostics',
    '_backtest_export_csv',
    '_backtest_export_html',
    '_run_backtest_parameter_sweep',
]
