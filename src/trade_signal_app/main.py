from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import csv
import io
import json
from urllib.parse import parse_qs, urlparse

from .app_state import AppState
from .backtest import (
    group_archives,
    merge_candles,
    resolve_archive_paths,
    resolve_execution_config_from_binance,
    run_backtest_for_series,
    run_portfolio_backtest,
)
from .config import BASE_DIR, SETTINGS
from .presets import apply_backtest_preset, list_backtest_presets
from .runtime_config import BacktestDefaults, RuntimeConfig, ScanDefaults
from .strategy import EntryRuleConfig, ExecutionConfig, ExitRuleConfig
from .ui import format_backtest_report, format_portfolio_report, format_signal_row
from .views import render_backtest_page, render_index_page, render_settings_page

RUNTIME_CONFIG_PATH = BASE_DIR / "data" / "runtime_config.json"
APP_STATE = AppState(SETTINGS, RUNTIME_CONFIG_PATH)


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
    return {
        "binance_recv_window_ms": config.binance_recv_window_ms,
        "community_provider": config.community_provider,
        "x_api_base_url": config.x_api_base_url,
        "x_recent_window_hours": config.x_recent_window_hours,
        "x_recent_max_results": config.x_recent_max_results,
        "x_language": config.x_language,
        "reddit_api_base_url": config.reddit_api_base_url,
        "reddit_recent_window_hours": config.reddit_recent_window_hours,
        "reddit_max_results": config.reddit_max_results,
        "reddit_user_agent": config.reddit_user_agent,
        "x_account_mode": config.x_account_mode,
        "x_account_weight_pct": config.x_account_weight_pct,
        "x_tracked_accounts": config.x_tracked_accounts,
        "scan_quote_asset": config.scan_defaults.quote_asset,
        "scan_interval": config.scan_defaults.interval,
        "scan_candidate_pool": config.scan_defaults.candidate_pool,
        "scan_min_quote_volume": int(config.scan_defaults.min_quote_volume),
        "scan_min_trade_count": config.scan_defaults.min_trade_count,
        **{f"backtest_{key}": value for key, value in backtest.items()},
    }


def _settings_status_from_config(config: RuntimeConfig) -> dict[str, object]:
    return {
        "binance_auth_configured": bool(config.binance_api_key and config.binance_api_secret),
        "binance_auth_label": "API key + secret 已配置" if config.binance_api_key and config.binance_api_secret else "未配置",
        "x_auth_configured": bool(config.x_bearer_token),
        "tracked_account_count": len(config.x_tracked_accounts),
        "storage_mode": APP_STATE.storage_mode_label(),
    }


def _settings_context() -> tuple[dict[str, object], dict[str, object]]:
    runtime_config, _ = APP_STATE.snapshot()
    return _settings_params_from_config(runtime_config), _settings_status_from_config(runtime_config)


def _export_runtime_config_template(*, include_secrets: bool) -> dict[str, object]:
    runtime_config, _ = APP_STATE.snapshot()
    return runtime_config.to_template_payload(include_secrets=include_secrets)


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
    return RuntimeConfig.from_template_payload(payload, SETTINGS, current_config=current_config)


def _scan_payload(query: dict[str, list[str]]) -> tuple[dict[str, object], dict[str, object]]:
    runtime_config, scanner = APP_STATE.snapshot()
    scan_defaults = runtime_config.scan_defaults
    quote_asset = query.get("quote_asset", [scan_defaults.quote_asset])[0].upper()
    interval = query.get("interval", [scan_defaults.interval])[0]
    candidate_pool = int(query.get("candidate_pool", [str(scan_defaults.candidate_pool)])[0])
    min_quote_volume = float(query.get("min_quote_volume", [str(scan_defaults.min_quote_volume)])[0])
    min_trade_count = int(query.get("min_trade_count", [str(scan_defaults.min_trade_count)])[0])

    summary, signals = scanner.scan(
        quote_asset=quote_asset,
        interval=interval,
        candidate_pool=candidate_pool,
        min_quote_volume=min_quote_volume,
        min_trade_count=min_trade_count,
    )
    payload = {
        "summary": _to_jsonable(summary),
        "signals": [format_signal_row(signal) for signal in signals],
    }
    params = {
        "quote_asset": quote_asset,
        "interval": interval,
        "candidate_pool": candidate_pool,
        "min_quote_volume": int(min_quote_volume),
        "min_trade_count": min_trade_count,
    }
    return payload, params


def _get_first(query: dict[str, list[str]], key: str, default: str) -> str:
    return query.get(key, [default])[0]


def _parse_bool_flag(query: dict[str, list[str]], key: str) -> bool:
    return key in query and _get_first(query, key, "") not in {"", "0", "false", "False"}


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
        "lookback_bars": int(_get_first(query, "lookback_bars", str(base_params["lookback_bars"]))),
        "score_threshold": float(_get_first(query, "score_threshold", str(base_params["score_threshold"]))),
        "holding_periods": _get_first(query, "holding_periods", str(base_params["holding_periods"])),
        "portfolio_top_n": int(_get_first(query, "portfolio_top_n", str(base_params["portfolio_top_n"]))),
        "cooldown_bars": int(_get_first(query, "cooldown_bars", str(base_params["cooldown_bars"]))),
        "stop_loss_pct": float(_get_first(query, "stop_loss_pct", str(base_params["stop_loss_pct"]))),
        "take_profit_pct": float(_get_first(query, "take_profit_pct", str(base_params["take_profit_pct"]))),
        "max_holding_bars": int(_get_first(query, "max_holding_bars", str(base_params["max_holding_bars"]))),
        "fee_bps": float(_get_first(query, "fee_bps", str(base_params["fee_bps"]))),
        "fee_model": _get_first(query, "fee_model", str(base_params["fee_model"])),
        "fee_source": _get_first(query, "fee_source", str(base_params["fee_source"])),
        "maker_fee_bps": float(_get_first(query, "maker_fee_bps", str(base_params["maker_fee_bps"]))),
        "taker_fee_bps": float(_get_first(query, "taker_fee_bps", str(base_params["taker_fee_bps"]))),
        "entry_fee_role": _get_first(query, "entry_fee_role", str(base_params["entry_fee_role"])),
        "exit_fee_role": _get_first(query, "exit_fee_role", str(base_params["exit_fee_role"])),
        "fee_discount_pct": float(_get_first(query, "fee_discount_pct", str(base_params["fee_discount_pct"]))),
        "no_binance_discount": _parse_bool_flag(query, "no_binance_discount"),
        "slippage_bps": float(_get_first(query, "slippage_bps", str(base_params["slippage_bps"]))),
        "slippage_model": _get_first(query, "slippage_model", str(base_params["slippage_model"])),
        "min_slippage_bps": float(_get_first(query, "min_slippage_bps", str(base_params["min_slippage_bps"]))),
        "max_slippage_bps": float(_get_first(query, "max_slippage_bps", str(base_params["max_slippage_bps"]))),
        "slippage_window_bars": int(_get_first(query, "slippage_window_bars", str(base_params["slippage_window_bars"]))),
        "capital_fraction_pct": float(_get_first(query, "capital_fraction_pct", str(base_params["capital_fraction_pct"]))),
        "max_portfolio_exposure_pct": float(_get_first(query, "max_portfolio_exposure_pct", str(base_params["max_portfolio_exposure_pct"]))),
        "max_concurrent_positions": int(_get_first(query, "max_concurrent_positions", str(base_params["max_concurrent_positions"]))),
        "min_volume_ratio": float(_get_first(query, "min_volume_ratio", str(base_params["min_volume_ratio"]))),
        "min_buy_pressure": float(_get_first(query, "min_buy_pressure", str(base_params["min_buy_pressure"]))),
        "min_rsi": float(_get_first(query, "min_rsi", str(base_params["min_rsi"]))),
        "max_rsi": float(_get_first(query, "max_rsi", str(base_params["max_rsi"]))),
        "no_kdj_confirmation": _parse_bool_flag(query, "no_kdj_confirmation"),
    }
    if "no_binance_discount" not in query:
        params["no_binance_discount"] = bool(base_params["no_binance_discount"])
    if "no_kdj_confirmation" not in query:
        params["no_kdj_confirmation"] = bool(base_params["no_kdj_confirmation"])

    archive_patterns = _split_archives(str(params["archives"]))
    if not archive_patterns:
        return {"series_reports": [], "portfolio_reports": []}, params, None

    paths = resolve_archive_paths(archive_patterns)
    if not paths:
        return {"series_reports": [], "portfolio_reports": []}, params, "没有匹配到任何 ZIP 文件。"

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
        return {"series_reports": [], "portfolio_reports": []}, params, str(exc)
    for (symbol, interval), archive_paths in sorted(grouped.items()):
        candles = merge_candles(archive_paths)
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
            return {"series_reports": [], "portfolio_reports": []}, params, str(exc)
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

    return {"series_reports": series_reports, "portfolio_reports": portfolio_reports}, params, None


def _backtest_export_csv(payload: dict[str, object], params: dict[str, object], error: str | None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "name", "interval", "metric", "value"])
    writer.writerow(["meta", "backtest", "", "error", error or ""])
    for key, value in params.items():
        writer.writerow(["param", "backtest", "", key, value])

    for report in payload["series_reports"]:
        writer.writerow(["series", report["symbol"], report["interval"], "final_equity", report["final_equity"]])
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

    return buffer.getvalue()


def _build_runtime_config(form: dict[str, list[str]]) -> RuntimeConfig:
    current_config, _ = APP_STATE.snapshot()
    keep_binance_key = current_config.binance_api_key
    keep_binance_secret = current_config.binance_api_secret
    keep_x_bearer_token = current_config.x_bearer_token
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
    if _parse_bool_flag(form, "clear_x_auth"):
        keep_x_bearer_token = ""
    else:
        candidate = _get_first(form, "x_bearer_token", "").strip()
        if candidate:
            keep_x_bearer_token = candidate

    return RuntimeConfig(
        binance_api_key=keep_binance_key,
        binance_api_secret=keep_binance_secret,
        binance_recv_window_ms=_parse_float_value(_get_first(form, "binance_recv_window_ms", str(current_config.binance_recv_window_ms)), "Binance RecvWindow"),
        community_provider=_get_first(form, "community_provider", current_config.community_provider).strip() or "auto",
        x_bearer_token=keep_x_bearer_token,
        x_api_base_url=_get_first(form, "x_api_base_url", current_config.x_api_base_url).strip() or current_config.x_api_base_url,
        x_recent_window_hours=_parse_int_value(_get_first(form, "x_recent_window_hours", str(current_config.x_recent_window_hours)), "X Window Hours"),
        x_recent_max_results=_parse_int_value(_get_first(form, "x_recent_max_results", str(current_config.x_recent_max_results)), "X Max Results"),
        x_language=_get_first(form, "x_language", current_config.x_language).strip() or current_config.x_language,
        reddit_api_base_url=_get_first(form, "reddit_api_base_url", current_config.reddit_api_base_url).strip() or current_config.reddit_api_base_url,
        reddit_recent_window_hours=_parse_int_value(_get_first(form, "reddit_recent_window_hours", str(current_config.reddit_recent_window_hours)), "Reddit Window Hours"),
        reddit_max_results=_parse_int_value(_get_first(form, "reddit_max_results", str(current_config.reddit_max_results)), "Reddit Max Results"),
        reddit_user_agent=_get_first(form, "reddit_user_agent", current_config.reddit_user_agent).strip() or current_config.reddit_user_agent,
        x_account_mode=_get_first(form, "x_account_mode", current_config.x_account_mode).strip() or current_config.x_account_mode,
        x_account_weight_pct=_parse_float_value(_get_first(form, "x_account_weight_pct", str(current_config.x_account_weight_pct)), "Account Weight"),
        x_tracked_accounts=_parse_multiline_list(_get_first(form, "x_tracked_accounts", "\n".join(current_config.x_tracked_accounts))),
        scan_defaults=ScanDefaults(
            quote_asset=_get_first(form, "scan_quote_asset", current_config.scan_defaults.quote_asset).strip().upper() or current_config.scan_defaults.quote_asset,
            interval=_get_first(form, "scan_interval", current_config.scan_defaults.interval).strip() or current_config.scan_defaults.interval,
            candidate_pool=_parse_int_value(_get_first(form, "scan_candidate_pool", str(current_config.scan_defaults.candidate_pool)), "Candidate Pool"),
            min_quote_volume=_parse_float_value(_get_first(form, "scan_min_quote_volume", str(current_config.scan_defaults.min_quote_volume)), "Min Quote Volume"),
            min_trade_count=_parse_int_value(_get_first(form, "scan_min_trade_count", str(current_config.scan_defaults.min_trade_count)), "Min Trade Count"),
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


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if parsed.path == "/":
                payload, params = _scan_payload(query)
                html = render_index_page(
                    summary=payload["summary"],
                    signals=payload["signals"],
                    params=params,
                    intervals=["15m", "1h", "4h", "1d"],
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
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
                    error=error,
                    presets=list_backtest_presets(),
                )
                self._send_text(html, content_type="text/html; charset=utf-8")
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
                    message = "运行配置已保存。"
                if _parse_bool_flag(query, "imported"):
                    message = "配置模板已导入。"
                html = render_settings_page(
                    params=params,
                    status=status,
                    message=message,
                    error=None,
                    import_payload_text=None,
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
        except Exception as exc:  # noqa: BLE001
            self._send_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False),
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                content_type="application/json; charset=utf-8",
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/settings":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                form = parse_qs(payload)
                config = _build_runtime_config(form)
                APP_STATE.update_config(config)
                self._redirect("/settings?saved=1")
                return

            if parsed.path == "/settings/import":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                form = parse_qs(payload)
                config = _import_runtime_config_template(form)
                APP_STATE.update_config(config)
                self._redirect("/settings?imported=1")
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
            )
            self._send_text(html, content_type="text/html; charset=utf-8", status=HTTPStatus.BAD_REQUEST)
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
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()


def run() -> None:
    server = ThreadingHTTPServer((SETTINGS.server_host, SETTINGS.server_port), RequestHandler)
    print(f"Serving on http://{SETTINGS.server_host}:{SETTINGS.server_port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
