from __future__ import annotations

from html import escape

from .views_common import _display_value, _layout, _text, _url, normalize_language
from .views_components import _float_from_any, _format_signed_number, _terminal_rows


def _fmt(value: object, digits: int = 2) -> str:
    return f"{_float_from_any(value):,.{digits}f}"


def _pct(value: object, digits: int = 2) -> str:
    return f"{_float_from_any(value):+,.{digits}f}%"


def _btc_visual_chart(signal: dict[str, object], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    technical = signal.get("technical") if isinstance(signal.get("technical"), dict) else {}
    snapshot = technical.get("indicator_snapshot") if isinstance(technical.get("indicator_snapshot"), dict) else {}
    closes = snapshot.get("closes") if isinstance(snapshot.get("closes"), list) else []
    values = [_float_from_any(item) for item in closes if _float_from_any(item) > 0][-48:]
    price = _float_from_any(signal.get("price"))
    analysis_price = _float_from_any(signal.get("analysis_price"))
    kline_close = analysis_price if analysis_price > 0 else values[-1] if values else 0.0
    price_source = str(signal.get("price_source") or "")
    if not values and price > 0:
        values = [price]
    elif values and price > 0:
        values[-1] = price
    trade_levels = signal.get("trade_levels") if isinstance(signal.get("trade_levels"), dict) else {}
    reference_lines = [
        ("support", t("支撑", "Support"), _float_from_any(trade_levels.get("support_level"))),
        ("stop", t("止损", "Stop"), _float_from_any(trade_levels.get("stop_price"))),
        ("take", t("止盈", "Take"), _float_from_any(trade_levels.get("take_profit_price"))),
        ("resistance", t("阻力", "Resistance"), _float_from_any(trade_levels.get("resistance_level"))),
    ]
    chart_values = values + [line[2] for line in reference_lines if line[2] > 0]
    if not chart_values:
        return f'<p class="helper-text">{escape(t("暂无可绘制的 BTC 价格序列。", "No BTC price series available to draw."))}</p>'
    minimum = min(chart_values)
    maximum = max(chart_values)
    padding = max((maximum - minimum) * 0.08, maximum * 0.002)
    minimum -= padding
    maximum += padding
    span = maximum - minimum or 1.0
    width = 920
    height = 340
    chart_left = 56
    plot_right = width - 214
    label_left = plot_right + 18
    chart_top = 34
    chart_bottom = height - 54

    def x_for(index: int) -> float:
        if len(values) <= 1:
            return (chart_left + plot_right) / 2
        return chart_left + ((plot_right - chart_left) * index / (len(values) - 1))

    def y_for(value: float) -> float:
        return chart_bottom - ((value - minimum) / span) * (chart_bottom - chart_top)

    price_points = [(x_for(index), y_for(value)) for index, value in enumerate(values)]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in price_points)
    if price_points:
        price_path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in price_points)
        area_path = (
            f"M{price_points[0][0]:.1f} {chart_bottom:.1f} "
            + " L".join(f"{x:.1f} {y:.1f}" for x, y in price_points)
            + f" L{price_points[-1][0]:.1f} {chart_bottom:.1f} Z"
        )
    else:
        price_path = ""
        area_path = ""

    level_items = []
    legend = []
    for class_name, label, value in reference_lines:
        if value <= 0:
            continue
        y = y_for(value)
        level_items.append({"class": class_name, "label": label, "value": value, "line_y": y, "label_y": y})
        legend.append(f'<span class="{escape(class_name)}">{escape(label)} {_fmt(value, 2)}</span>')
    level_items.sort(key=lambda item: item["label_y"])
    label_gap = 30.0
    for index, item in enumerate(level_items):
        if index == 0:
            item["label_y"] = max(chart_top + 14, item["label_y"])
            continue
        previous = level_items[index - 1]
        item["label_y"] = max(item["label_y"], previous["label_y"] + label_gap)
    if level_items:
        overflow = level_items[-1]["label_y"] - (chart_bottom - 12)
        if overflow > 0:
            for item in level_items:
                item["label_y"] -= overflow
        underflow = (chart_top + 14) - level_items[0]["label_y"]
        if underflow > 0:
            for item in level_items:
                item["label_y"] += underflow
    line_paths = []
    label_paths = []
    for item in level_items:
        class_name = str(item["class"])
        label = str(item["label"])
        value = float(item["value"])
        line_y = float(item["line_y"])
        label_y = float(item["label_y"])
        line_paths.append(
            f'<line class="btc-chart-level {escape(class_name)}" x1="{chart_left}" y1="{line_y:.1f}" x2="{plot_right}" y2="{line_y:.1f}"></line>'
            f'<path class="btc-chart-connector {escape(class_name)}" d="M{plot_right:.1f} {line_y:.1f} H{label_left - 8:.1f} V{label_y:.1f}"></path>'
        )
        label_paths.append(
            f'<g class="btc-chart-level-label {escape(class_name)}" transform="translate({label_left:.1f} {label_y - 14:.1f})">'
            f'<rect width="166" height="28" rx="9"></rect>'
            f'<text x="10" y="18">{escape(label)} {_fmt(value, 2)}</text>'
            f'</g>'
        )
    current_marker = ""
    if values:
        current_marker = f'<circle cx="{x_for(len(values) - 1):.1f}" cy="{y_for(values[-1]):.1f}" r="5"></circle>'
    top_label = _fmt(maximum - padding, 2)
    bottom_label = _fmt(minimum + padding, 2)
    mid_label = _fmt((maximum + minimum) / 2, 2)
    current_price_label = _fmt(values[-1], 2) if values else "-"
    kline_close_label = f' · {escape(t("K线收盘", "K-line close"))} {_fmt(kline_close, 2)}' if price_source == "live_market" and kline_close > 0 else ""
    return f"""
      <div class="btc-visual-chart">
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(t("BTC走势图", "BTC price chart"))}">
          <defs>
            <linearGradient id="btcPriceArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stop-color="#50d7e8" stop-opacity="0.28"></stop>
              <stop offset="100%" stop-color="#50d7e8" stop-opacity="0.02"></stop>
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="{width}" height="{height}" rx="18"></rect>
          <path class="btc-chart-grid" d="M{chart_left} {chart_top}H{plot_right} M{chart_left} {(chart_top + chart_bottom) / 2:.1f}H{plot_right} M{chart_left} {chart_bottom}H{plot_right}"></path>
          <text x="14" y="{chart_top + 4}" class="btc-chart-axis">{escape(top_label)}</text>
          <text x="14" y="{(chart_top + chart_bottom) / 2 + 4:.1f}" class="btc-chart-axis">{escape(mid_label)}</text>
          <text x="14" y="{chart_bottom + 4}" class="btc-chart-axis">{escape(bottom_label)}</text>
          {"".join(line_paths)}
          {f'<path class="btc-chart-area" d="{escape(area_path)}"></path>' if area_path else ''}
          {f'<path class="btc-chart-price" d="{escape(price_path)}"></path>' if price_path else f'<polyline class="btc-chart-price" points="{escape(points)}"></polyline>'}
          {current_marker}
          {"".join(label_paths)}
          <text x="{chart_left}" y="{height - 14}" class="btc-chart-axis">{escape(t("最近48根K线 + 实时价", "Last 48 candles + live price"))}</text>
          <text x="{plot_right - 236}" y="{height - 14}" class="btc-chart-axis">{escape(t("当前价", "Last"))} {escape(current_price_label)}{kline_close_label}</text>
        </svg>
        <div class="btc-chart-legend">{"".join(legend)}</div>
      </div>
    """


def _btc_level_rows(signal: dict[str, object]) -> list[dict[str, object]]:
    trade_levels = signal.get("trade_levels") if isinstance(signal.get("trade_levels"), dict) else {}
    return [
        {"name": "当前价", "value": _fmt(signal.get("price"), 2), "note": signal.get("action_label") or signal.get("action") or "-"},
        {"name": "支撑位", "value": _fmt(trade_levels.get("support_level"), 2), "note": f"距离 {_fmt(trade_levels.get('support_distance_pct'), 2)}%"},
        {"name": "阻力位", "value": _fmt(trade_levels.get("resistance_level"), 2), "note": f"空间 {_fmt(trade_levels.get('resistance_distance_pct'), 2)}%"},
        {"name": "止损价", "value": _fmt(trade_levels.get("stop_price"), 2), "note": f"5x ROI {_pct(trade_levels.get('leveraged_stop_roi_pct'))}"},
        {"name": "止盈价", "value": _fmt(trade_levels.get("take_profit_price"), 2), "note": f"5x ROI {_pct(trade_levels.get('leveraged_take_profit_roi_pct'))}"},
        {"name": "结构盈亏比", "value": _fmt(trade_levels.get("risk_reward_ratio"), 2), "note": "止盈空间 / 止损风险"},
    ]


def _btc_metric_rows(signal: dict[str, object]) -> list[dict[str, object]]:
    regime = signal.get("regime") if isinstance(signal.get("regime"), dict) else {}
    statistics = signal.get("statistics") if isinstance(signal.get("statistics"), dict) else {}
    selected_preset = signal.get("selected_preset") if isinstance(signal.get("selected_preset"), dict) else {}
    return [
        {"name": "信号评分", "value": f"{_fmt(signal.get('score'), 2)} / {signal.get('grade') or '-'}", "note": signal.get("confidence") or "-"},
        {"name": "信号ID", "value": signal.get("signal") or "-", "note": signal.get("action_label") or signal.get("action") or "-"},
        {"name": "趋势状态", "value": regime.get("label") or "-", "note": f"1h RSI {_fmt(regime.get('entry_rsi_14'), 2)}"},
        {"name": "最佳预设", "value": selected_preset.get("label") or selected_preset.get("preset_id") or "-", "note": f"胜率 {_fmt(selected_preset.get('win_rate_pct'), 2)}%"},
        {"name": "近90天收益", "value": _pct(statistics.get("return_90d_pct")), "note": f"近365天 {_pct(statistics.get('return_365d_pct'))}"},
        {"name": "历史最大回撤", "value": _pct(statistics.get("max_drawdown_pct")), "note": f"年化波动 {_fmt(statistics.get('annualized_volatility_pct'), 2)}%"},
    ]


def _btc_backtest_rows(signal: dict[str, object]) -> list[dict[str, object]]:
    rows = []
    preset_backtests = signal.get("preset_backtests") if isinstance(signal.get("preset_backtests"), list) else []
    for item in preset_backtests:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "preset": item.get("label") or item.get("preset_id") or "-",
                "signals": item.get("signal_count", 0),
                "win_rate": f"{_fmt(item.get('win_rate_pct'), 2)}%",
                "profit_factor": _fmt(item.get("profit_factor"), 2),
                "drawdown": _pct(item.get("max_drawdown_pct")),
                "quality": _fmt(item.get("quality_score"), 2),
            }
        )
    return rows


def _list_panel(title: str, items: object, empty: str) -> str:
    values = [str(item) for item in items] if isinstance(items, list) else []
    if not values:
        values = [empty]
    return f"""
      <section class="ant-card nested-panel">
        <h3>{escape(title)}</h3>
        <ul class="strategy-warning-list">{"".join(f"<li>{escape(item)}</li>" for item in values[:8])}</ul>
      </section>
    """


def render_btc_signal_page(
    *,
    summary: dict[str, object],
    fast: bool = False,
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    mode_label = t("快速视图", "Fast View") if fast else t("完整视图", "Full View")
    action_label = str(summary.get("action_label") or _display_value(summary.get("action"), active_lang) or "-")
    hero_right = f"""
      <div class="ant-statistic-card stat-card"><span>BTCUSDT</span><strong>{escape(action_label)}</strong><small>{escape(str(summary.get("signal") or "-"))}</small></div>
      <div class="ant-statistic-card stat-card"><span>{t("评分", "Score")}</span><strong>{_fmt(summary.get("score"), 2)}</strong><small>{escape(str(summary.get("grade") or "-"))}</small></div>
      <div class="ant-statistic-card stat-card"><span>{t("当前价", "Last")}</span><strong>{_fmt(summary.get("price"), 2)}</strong><small>{escape(str(summary.get("confidence") or "-"))}</small></div>
      <div class="ant-statistic-card stat-card"><span>{t("模式", "Mode")}</span><strong>{escape(mode_label)}</strong><small>{t("表格 + 走势图", "Table + chart")}</small></div>
    """
    json_path = "/api/btc/signal?fast=1" if fast else "/api/btc/signal"
    switch_path = "/btc/signal" if fast else "/btc/signal?fast=1"
    backtest_rows = _btc_backtest_rows(summary)
    backtest_panel = (
        _terminal_rows(
            backtest_rows,
            [("Preset", "preset"), ("Signals", "signals"), ("Win Rate", "win_rate"), ("PF", "profit_factor"), ("Max DD", "drawdown"), ("Quality", "quality")],
            lang=active_lang,
        )
        if backtest_rows
        else f'<p class="helper-text">{escape(t("快速视图未运行 BTC 预设回测，切换到完整视图可查看。", "Fast view skips BTC preset backtests; switch to full view to inspect them."))}</p>'
    )
    content = f"""
      <div class="page-section-stack btc-signal-page">
        <section class="ant-card control-panel">
          <div class="section-heading">
            <h2>{t("BTC信号走势图", "BTC Signal Chart")}</h2>
            <p>{escape(str(summary.get("advice") or t("等待 BTC 专属信号刷新。", "Waiting for BTC-specific signal refresh.")))}</p>
          </div>
          <div class="strategy-result-actions">
            <a class="action-link" href="{escape(_url(json_path, active_lang), quote=True)}">{t("查看 JSON", "View JSON")}</a>
            <a class="action-link" href="{escape(_url(switch_path, active_lang), quote=True)}">{t("切换快速/完整视图", "Toggle fast/full view")}</a>
            <a class="action-link" href="{escape(_url('/trading#trading-btc', active_lang), quote=True)}">{t("返回模拟账户 BTC 专区", "Back to paper BTC zone")}</a>
          </div>
          {_btc_visual_chart(summary, active_lang)}
        </section>
        <section class="btc-trading-grid">
          <article class="ant-card nested-panel table-shell">
            <h3>{t("关键价位", "Key Levels")}</h3>
            {_terminal_rows(_btc_level_rows(summary), [(t("项目", "Item"), "name"), (t("值", "Value"), "value"), (t("说明", "Note"), "note")], lang=active_lang)}
          </article>
          <article class="ant-card nested-panel table-shell">
            <h3>{t("信号与统计", "Signal & Stats")}</h3>
            {_terminal_rows(_btc_metric_rows(summary), [(t("项目", "Item"), "name"), (t("值", "Value"), "value"), (t("说明", "Note"), "note")], lang=active_lang)}
          </article>
        </section>
        <section class="ant-card nested-panel table-shell">
          <h3>{t("BTC预设回测", "BTC Preset Backtests")}</h3>
          {backtest_panel}
        </section>
        <section class="btc-trading-grid">
          {_list_panel(t("买卖理由", "Reasons"), summary.get("reasons"), t("暂无买卖理由。", "No reasons yet."))}
          {_list_panel(t("风险提示", "Risk Notes"), summary.get("warnings"), t("暂无额外风险。", "No extra risks yet."))}
        </section>
      </div>
    """
    return _layout(
        page_title="BTC Signal Visual",
        active_page="trading",
        hero_title=t("BTC 专属信号可视化", "BTC Signal Visual"),
        hero_text=t("把 JSON 信号转换成走势图、关键价位表、策略回测表和执行建议，便于快速判断是否值得出手。", "Turns JSON signal output into a chart, level table, preset table, and execution plan."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/btc/signal",
        layout_context=layout_context,
    )


__all__ = [
    "render_btc_signal_page",
]
