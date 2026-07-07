from __future__ import annotations

from datetime import datetime
from html import escape

from .time_utils import format_app_datetime
from .views_common import _display_value, _hidden_lang_input, _text, _url


_DATETIME_FIELD_KEYS = {
    "created_at",
    "updated_at",
    "entry_time",
    "exit_time",
    "opened_at",
    "closed_at",
    "next_funding_time",
}


def _terminal_rows(items: list[dict[str, object]], columns: list[tuple[str, str]], *, lang: str = "zh") -> str:
    if not items:
        return f'<p class="helper-text">{escape(_text(lang, "暂无数据。配置本地 CSV 或外部数据源后会自动显示。", "No data yet. Configure local CSV or external data sources to populate this panel."))}</p>'
    header = "".join(f"<th>{escape(label)}</th>" for label, _ in columns)
    rows = []
    for item in items:
        cells = "".join(f"<td>{escape(_format_cell(item.get(key), lang, key=key))}</td>" for _, key in columns)
        rows.append(f"<tr>{cells}</tr>")
    column_count = max(1, len(columns))
    width_class = "terminal-table-compact" if column_count <= 3 else "terminal-table-medium" if column_count <= 5 else "terminal-table-wide"
    return f'<div class="terminal-table-shell"><table class="ant-table data-table terminal-table {width_class}"><tr>{header}</tr><tbody>{"".join(rows)}</tbody></table></div>'


def _format_datetime_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_app_datetime(value)
    text = str(value).strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    return format_app_datetime(parsed)


def _format_cell(value: object, lang: str = "zh", *, key: str | None = None) -> str:
    if value is None:
        return ""
    if key in _DATETIME_FIELD_KEYS:
        return _format_datetime_value(value)
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        return f"{value:.2f}"
    if isinstance(value, list):
        return " / ".join(_display_value(item, lang) for item in value[:3])
    return _display_value(value, lang)


def _float_from_any(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strategy_builder_panel(
    *,
    result: dict[str, object] | None,
    text: str,
    message: str | None,
    error: str | None,
    lang: str,
) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    notice = ""
    if message:
        notice = f'<div class="notice notice-success">{escape(message)}</div>'
    if error:
        notice = f'<div class="notice notice-error">{escape(error)}</div>'
    return f"""
      <form method="post" action="{_url('/terminal/strategies/compile', lang)}" class="ant-form strategy-builder-form">
        {_hidden_lang_input(lang)}
        <label class="strategy-builder-input">
          <span>{t("策略描述", "Strategy Description")}</span>
          <textarea name="strategy_description" rows="5" placeholder="{t("例如：BTC 15m RSI 超卖反弹，止损 3%，止盈 6%，最多持有 8 根 K 线。", "Example: BTC 15m RSI oversold rebound, 3% stop loss, 6% take profit, hold at most 8 bars.")}">{escape(text)}</textarea>
        </label>
        <button type="submit">{t("编译策略", "Compile Strategy")}</button>
      </form>
      {notice}
      {_strategy_builder_result(result, lang) if result else ""}
    """


def _strategy_builder_result(result: dict[str, object], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    symbols = result.get("symbols", [])
    symbol_text = " / ".join(str(item) for item in symbols) if isinstance(symbols, list) else str(symbols)
    backtest_defaults = result.get("backtest_defaults") if isinstance(result.get("backtest_defaults"), dict) else {}
    autotrade_defaults = result.get("autotrade_defaults") if isinstance(result.get("autotrade_defaults"), dict) else {}
    run_urls = result.get("run_urls") if isinstance(result.get("run_urls"), dict) else {}
    backtest_url = str(run_urls.get("backtest", "/backtest")) if isinstance(run_urls, dict) else "/backtest"
    paper_url = str(run_urls.get("paper_trading", "/terminal/trading")) if isinstance(run_urls, dict) else "/terminal/trading"
    warnings = result.get("warnings", [])
    warnings_html = ""
    if isinstance(warnings, list) and warnings:
        warnings_html = '<ul class="strategy-warning-list">' + "".join(f"<li>{escape(str(item))}</li>" for item in warnings[:6]) + "</ul>"

    rules = []
    for section, key in [
        (t("入场", "Entry"), "entry_rules"),
        (t("离场", "Exit"), "exit_rules"),
        (t("风控", "Risk"), "risk_controls"),
    ]:
        values = result.get(key, [])
        if isinstance(values, list):
            rules.extend({"section": section, "rule": item} for item in values)

    return f"""
      <div class="strategy-builder-result">
        <div class="mini-stat-grid compact-grid">
          <div class="mini-stat"><span>{t("来源", "Source")}</span><strong>{escape(str(result.get("source", "")))}</strong></div>
          <div class="mini-stat"><span>{t("模型", "Model")}</span><strong>{escape(str(result.get("model", "")))}</strong></div>
          <div class="mini-stat"><span>{t("风格", "Style")}</span><strong>{escape(str(result.get("style", "")))}</strong></div>
          <div class="mini-stat"><span>{t("标的", "Symbols")}</span><strong>{escape(symbol_text)}</strong></div>
          <div class="mini-stat"><span>{t("周期", "Interval")}</span><strong>{escape(str(result.get("interval", "")))}</strong></div>
          <div class="mini-stat"><span>{t("报价资产", "Quote")}</span><strong>{escape(str(result.get("quote_asset", "")))}</strong></div>
        </div>
        <div class="strategy-result-actions">
          <a class="action-link" href="{escape(_url(backtest_url, lang), quote=True)}">{t("打开回测", "Open Backtest")}</a>
          <a class="action-link" href="{escape(_url(paper_url, lang), quote=True)}">{t("查看 paper 执行", "View Paper Execution")}</a>
          <a class="action-link" href="{escape(_url('/settings', lang), quote=True)}">{t("配置模型", "Configure Model")}</a>
        </div>
        {_terminal_rows(rules, [(t("类型", "Type"), "section"), (t("规则", "Rule"), "rule")], lang=lang)}
        <div class="strategy-param-grid">
          <div>
            <h3>{t("回测参数", "Backtest Parameters")}</h3>
            {_strategy_param_table(backtest_defaults, ["preset", "score_threshold", "portfolio_top_n", "min_rsi", "max_rsi", "min_volume_ratio", "min_buy_pressure", "stop_loss_pct", "take_profit_pct", "max_holding_bars", "no_kdj_confirmation"], lang)}
          </div>
          <div>
            <h3>{t("Paper 执行参数", "Paper Execution Parameters")}</h3>
            {_strategy_param_table(autotrade_defaults, ["enabled", "mode", "quote_order_qty", "max_open_positions", "max_total_quote_exposure", "score_threshold", "min_volume_ratio", "min_buy_pressure", "stop_loss_pct", "take_profit_pct", "profit_protection_enabled", "profit_protection_trigger_pct", "profit_protection_lock_pct", "trailing_stop_pct", "cooldown_minutes", "order_test_only"], lang)}
          </div>
        </div>
        {warnings_html}
      </div>
    """


def _strategy_param_table(params: object, keys: list[str], lang: str) -> str:
    if not isinstance(params, dict):
        return f'<p class="helper-text">{escape(_text(lang, "暂无参数。", "No parameters."))}</p>'
    rows = [{"key": key, "value": params[key]} for key in keys if key in params]
    return _terminal_rows(rows, [("Key", "key"), ("Value", "value")], lang=lang)


def _trading_position_rows(positions: list[dict[str, object]], lang: str = "zh") -> str:
    t = lambda zh, en: _text(lang, zh, en)
    if not positions:
        return f'<p class="helper-text">{escape(t("当前没有自动交易持仓。", "No automated trading positions are open."))}</p>'
    rows = []
    for position in positions:
        last_price = position.get("last_price")
        unrealized_pnl = position.get("unrealized_pnl")
        unrealized_pnl_pct = position.get("unrealized_pnl_pct")
        unrealized_price_return_pct = position.get("unrealized_price_return_pct")
        last_price_text = t("待刷新", "Pending") if last_price is None else f'{float(last_price):.8f}'
        pnl_text = t("待刷新", "Pending") if unrealized_pnl is None else f'{float(unrealized_pnl):+.2f}'
        return_text = t("待刷新", "Pending") if unrealized_pnl_pct is None else f'{float(unrealized_pnl_pct):+.2f}%'
        price_return_text = "" if unrealized_price_return_pct is None else f'{float(unrealized_price_return_pct):+.2f}%'
        return_class = ""
        if unrealized_pnl_pct is not None:
            return_class = " positive" if float(unrealized_pnl_pct) >= 0 else " negative"
        rows.append(
            f"""
            <tr>
              <td>{escape(str(position["symbol"]))}</td>
              <td>{float(position["quantity"]):.8f}</td>
              <td>{float(position["entry_price"]):.8f}</td>
              <td>{escape(last_price_text)}</td>
              <td>{float(position["quote_notional"]):.2f}</td>
              <td>{float(position.get("margin_notional") or position["quote_notional"]):.2f} / {float(position.get("leverage") or 1.0):.1f}x</td>
              <td class="pnl-cell{return_class}">{escape(pnl_text)}</td>
              <td class="pnl-cell{return_class}">{escape(return_text)}</td>
              <td>{escape(price_return_text)}</td>
              <td>{float(position["score"]):.1f} / {escape(str(position["grade"]))}</td>
              <td>{float(position.get("highest_price") or position["entry_price"]):.8f}</td>
              <td>{float(position["stop_price"]):.8f}</td>
              <td>{float(position["take_profit_price"]):.8f}</td>
              <td>{escape(_display_value(position["mode"], lang))}</td>
            </tr>
            """
        )
    return f"""
      <table class="ant-table data-table">
        <tr>
          <th>{t("标的", "Symbol")}</th>
          <th>Qty</th>
          <th>{t("开仓价", "Entry")}</th>
          <th>{t("现价", "Last")}</th>
          <th>{t("名义金额", "Notional")}</th>
          <th>{t("保证金/杠杆", "Margin/Lev")}</th>
          <th>{t("浮动盈亏", "Unrealized PnL")}</th>
          <th>{t("保证金收益率", "Margin ROI")}</th>
          <th>{t("价格涨幅", "Price Return")}</th>
          <th>{t("信号", "Signal")}</th>
          <th>{t("最高价", "High")}</th>
          <th>{t("保护止损", "Protected Stop")}</th>
          <th>{t("止盈", "Take Profit")}</th>
          <th>{t("模式", "Mode")}</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _trading_event_rows(events: list[dict[str, object]], lang: str = "zh") -> str:
    t = lambda zh, en: _text(lang, zh, en)
    if not events:
        return f'<p class="helper-text">{escape(t("还没有本次执行事件。点击运行后会显示买入、卖出或跳过原因。", "No execution events yet. Run the engine to see buys, sells, skips, and block reasons."))}</p>'
    rows = []
    sorted_events = sorted(events, key=lambda event: str(event.get("created_at", "")), reverse=True)
    for event in sorted_events:
        rows.append(
            f"""
            <tr>
              <td>{escape(_format_datetime_value(event.get("created_at")))}</td>
              <td>{escape(_display_value(event["action"], lang))}</td>
              <td>{escape(str(event["symbol"]))}</td>
              <td>{escape(_display_value(event["status"], lang))}</td>
              <td>{escape(_display_value(event["message"], lang))}</td>
              <td>{'' if event.get("score") is None else f'{float(event["score"]):.1f}'}</td>
              <td>{'' if event.get("quote_notional") is None else f'{float(event["quote_notional"]):.2f}'}</td>
              <td>{escape(_display_value(event.get("exit_reason", ""), lang))}</td>
              <td>{'' if event.get("realized_pnl") is None else f'{float(event["realized_pnl"]):+.2f}'}</td>
            </tr>
            """
        )
    return f"""
      <table class="ant-table data-table">
        <tr>
          <th>{t("时间", "Time")}</th>
          <th>{t("动作", "Action")}</th>
          <th>{t("标的", "Symbol")}</th>
          <th>{t("状态", "Status")}</th>
          <th>{t("消息", "Message")}</th>
          <th>{t("评分", "Score")}</th>
          <th>{t("名义金额", "Notional")}</th>
          <th>{t("退出", "Exit")}</th>
          <th>{t("盈亏", "PnL")}</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


__all__ = [
    '_DATETIME_FIELD_KEYS',
    '_terminal_rows',
    '_format_datetime_value',
    '_format_cell',
    '_float_from_any',
    '_strategy_builder_panel',
    '_strategy_builder_result',
    '_strategy_param_table',
    '_trading_position_rows',
    '_trading_event_rows',
]
