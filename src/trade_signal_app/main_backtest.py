from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
import csv
import io
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
from .runtime_config import RuntimeConfig
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig
from .tradingview_data import fetch_tradingview_history
from .ui import format_backtest_report, format_portfolio_report, format_rebalance_premium_report
from .views_common import normalize_language


LOCAL_TRADINGVIEW_ARCHIVE_PATTERN = "data/tradingview_klines/*/*/*.csv"


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


def _cached_archive_pattern_if_available() -> str:
    return LOCAL_TRADINGVIEW_ARCHIVE_PATTERN if resolve_archive_paths([LOCAL_TRADINGVIEW_ARCHIVE_PATTERN]) else ""


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
    _validate_range(bars, "TradingView Bars", minimum=100, maximum=50000)

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
    if not str(params["archives"]).strip() and query:
        params["archives"] = _cached_archive_pattern_if_available()
    if "no_binance_discount" not in query:
        params["no_binance_discount"] = bool(base_params["no_binance_discount"])
    if "no_kdj_confirmation" not in query:
        params["no_kdj_confirmation"] = bool(base_params["no_kdj_confirmation"])

    archive_patterns = _split_archives(str(params["archives"]))
    if not archive_patterns:
        error = "没有填写 ZIP/CSV 历史数据；可先使用右侧 TradingView 拉取，或填入本地缓存路径。" if query else None
        return _empty_backtest_payload(params), params, error

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
    for (symbol, interval), archive_paths in sorted(grouped.items()):
        candles = merge_candles(archive_paths)
        candles_by_interval.setdefault(interval, {})[symbol] = candles
        if len(candles) < int(params["lookback_bars"]):
            data_warnings.append(
                f"{symbol} {interval} 只有 {len(candles)} 根 K 线，低于当前 lookback {int(params['lookback_bars'])}；建议重新拉取更多历史数据。"
            )
        if len(candles) < minimum_required_bars:
            data_warnings.append(
                f"{symbol} {interval} 已跳过：至少需要 {minimum_required_bars} 根 K 线才能覆盖指标预热和退出窗口，当前只有 {len(candles)} 根。"
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
        if str(params["preset"]) == "btc_overnight_seasonality":
            try:
                report = run_overnight_seasonality_backtest(
                    symbol=symbol,
                    interval=interval,
                    candles=candles,
                    execution_config=report_execution_config,
                )
            except ValueError as exc:
                data_warnings.append(f"{symbol} {interval} 已跳过：{exc}")
                continue
        else:
            try:
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
            except ValueError as exc:
                data_warnings.append(f"{symbol} {interval} 已跳过：{exc}")
                continue
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
            data_warnings=data_warnings,
        ),
    }, params, None


def _empty_backtest_payload(params: dict[str, object], *, data_warnings: list[str] | None = None) -> dict[str, object]:
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
            data_warnings=data_warnings or [],
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
    if data_warnings:
        diagnostics = [*data_warnings, *diagnostics]
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
]
