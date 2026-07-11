from __future__ import annotations

from html import escape

from .time_utils import now_app_time
from .views_common import _display_value, _hidden_lang_input, _layout, _text, _url, normalize_language
from .views_components import _btc_trading_zone, _float_from_any, _strategy_builder_panel, _terminal_rows, _trading_account_metric_cards, _trading_event_rows, _trading_position_rows


def _terminal_card(title: str, value: str, subtitle: str, accent: str = "") -> str:
    return f"""
      <article class="terminal-kpi {escape(accent)}">
        <span>{escape(title)}</span>
        <strong>{escape(value)}</strong>
        <small>{escape(subtitle)}</small>
      </article>
    """


def _strategy_templates_panel(templates: object, lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    rows = templates if isinstance(templates, list) else []
    if not rows:
        return f'<p class="helper-text">{escape(t("当前没有可用策略模板。", "No strategy templates are available."))}</p>'
    risk_labels = {
        "low": t("低", "Low"),
        "medium": t("中", "Medium"),
        "medium_high": t("中高", "Medium High"),
        "high": t("高", "High"),
    }
    validation_labels = {
        "historical_validated": t("历史验证", "Historically Validated"),
        "paper_candidate": t("待模拟验证", "Paper Candidate"),
        "research": t("研究阶段", "Research"),
        "baseline": t("基线", "Baseline"),
        "unvalidated": t("未验证", "Unvalidated"),
    }
    cards: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        template_id = str(item.get("template_id") or "")
        preset_id = str(item.get("preset_id") or "custom")
        intervals = item.get("recommended_intervals") if isinstance(item.get("recommended_intervals"), list) else []
        regimes = item.get("market_regimes") if isinstance(item.get("market_regimes"), list) else []
        risk = str(item.get("risk_level") or "medium")
        validation = str(item.get("validation_status") or "research")
        tags = [
            f'{t("风险", "Risk")} {risk_labels.get(risk, risk)}',
            validation_labels.get(validation, validation),
            " / ".join(str(value) for value in intervals) or "-",
        ]
        cards.append(
            f"""
            <article class="strategy-template-card">
              <header>
                <span>{escape(str(item.get("style") or "strategy"))}</span>
                <strong>{escape(str(item.get("label") or template_id))}</strong>
              </header>
              <p>{escape(str(item.get("description") or ""))}</p>
              <div class="strategy-template-tags">{"".join(f'<span>{escape(tag)}</span>' for tag in tags)}</div>
              <small>{escape(t("适用行情", "Regimes"))}: {escape(" / ".join(str(value) for value in regimes) or "-")}</small>
              <div class="strategy-template-actions">
                <form method="post" action="/terminal/strategies/templates/compile">
                  {_hidden_lang_input(lang)}
                  <input type="hidden" name="template_id" value="{escape(template_id, quote=True)}" />
                  <button type="submit">{t("生成安全参数", "Compile Safe Parameters")}</button>
                </form>
                <a href="{escape(_url(f'/backtest?preset={preset_id}', lang), quote=True)}">{t("打开回测", "Open Backtest")}</a>
              </div>
            </article>
            """
        )
    return f"""
      <div class="strategy-template-toolbar">
        <span>{escape(t("模板只生成回测与 paper 参数，不会开启自动轮询或真实订单。", "Templates only generate backtest and paper parameters; they never activate polling or live orders."))}</span>
        <a href="{escape(_url('/api/strategy/templates', lang), quote=True)}">JSON API</a>
      </div>
      <div class="strategy-template-grid">{"".join(cards)}</div>
    """


def _stat_arb_backtest_panel(
    *,
    result: dict[str, object] | None,
    params: dict[str, object] | None,
    message: str | None,
    error: str | None,
    lang: str,
) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    values = {
        "archive_a": "",
        "archive_b": "",
        "lookback_bars": 120,
        "entry_z": 2.0,
        "exit_z": 0.4,
        "stop_z": 3.5,
        "max_holding_bars": 48,
        "min_correlation": 0.65,
        "notional_per_leg": 1000.0,
        "fee_bps_per_leg": 10.0,
        "slippage_bps_per_leg": 2.0,
    }
    if params:
        values.update(params)
    report = result.get("report") if isinstance(result, dict) and isinstance(result.get("report"), dict) else {}
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), dict) else {}
    trades = report.get("trades") if isinstance(report.get("trades"), list) else []
    equity_curve = report.get("equity_curve") if isinstance(report.get("equity_curve"), list) else []
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    result_html = ""
    if report:
        result_html = f"""
          <div class="mini-stat-grid compact-grid trading-risk-grid">
            <div class="mini-stat"><span>{t("交易次数", "Trades")}</span><strong>{int(metrics.get("trade_count") or 0)}</strong></div>
            <div class="mini-stat"><span>{t("胜率", "Win Rate")}</span><strong>{float(metrics.get("win_rate_pct") or 0):.2f}%</strong></div>
            <div class="mini-stat"><span>{t("净收益", "Net PnL")}</span><strong>{float(metrics.get("net_pnl") or 0):+.4f}</strong></div>
            <div class="mini-stat"><span>{t("总回报", "Return")}</span><strong>{float(metrics.get("total_return_pct") or 0):+.3f}%</strong></div>
            <div class="mini-stat"><span>{t("最大回撤", "Max Drawdown")}</span><strong>{float(metrics.get("max_drawdown_pct") or 0):.3f}%</strong></div>
            <div class="mini-stat"><span>{t("交易成本", "Costs")}</span><strong>{float(metrics.get("costs") or 0):.4f}</strong></div>
          </div>
          <h3>{t("配对诊断", "Pair Diagnostics")}</h3>
          {_terminal_rows([diagnostics], [(t("对冲比率", "Hedge Ratio"), "hedge_ratio"), (t("相关性", "Correlation"), "correlation"), (t("最新 Z 分数", "Latest Z"), "latest_z_score"), (t("半衰期 K 线", "Half-life Bars"), "half_life_bars"), (t("方法", "Method"), "method")], lang=lang)}
          <h3>{t("双腿成交", "Two-leg Trades")}</h3>
          {_terminal_rows(trades, [(t("开仓", "Opened"), "opened_at"), (t("方向", "Direction"), "direction"), (t("入场 Z", "Entry Z"), "entry_z"), (t("退出 Z", "Exit Z"), "exit_z"), (t("持有 K 线", "Bars Held"), "bars_held"), (t("退出原因", "Exit Reason"), "exit_reason"), (t("成本", "Costs"), "costs"), (t("净收益", "Net PnL"), "net_pnl")], lang=lang)}
          <h3>{t("资金曲线", "Equity Curve")}</h3>
          {_terminal_rows(equity_curve[-60:], [(t("时间", "Time"), "timestamp"), (t("权益", "Equity"), "equity"), (t("回撤 %", "Drawdown %"), "drawdown_pct")], lang=lang)}
          <h3>{t("研究警告", "Research Warnings")}</h3>
          {_terminal_rows([{"warning": warning} for warning in warnings], [(t("说明", "Warning"), "warning")], lang=lang)}
        """
    return f"""
      <form method="post" action="{_url('/terminal/strategies/stat-arb/run', lang)}" class="ant-form backtest-form settings-form">
        {_hidden_lang_input(lang)}
        <div class="settings-grid">
          <label class="full-span"><span>{t("标的 A 历史数据", "Archive A")}</span><input type="text" name="archive_a" value="{escape(str(values['archive_a']), quote=True)}" placeholder="data/tradingview_klines/BINANCE/BTCUSDT/1h.csv" required /></label>
          <label class="full-span"><span>{t("标的 B 历史数据", "Archive B")}</span><input type="text" name="archive_b" value="{escape(str(values['archive_b']), quote=True)}" placeholder="data/tradingview_klines/BINANCE/ETHUSDT/1h.csv" required /></label>
          <label><span>Lookback Bars</span><input type="number" name="lookback_bars" min="30" value="{int(float(values['lookback_bars']))}" /></label>
          <label><span>Entry Z</span><input type="number" name="entry_z" min="0.1" step="0.1" value="{float(values['entry_z']):.2f}" /></label>
          <label><span>Exit Z</span><input type="number" name="exit_z" min="0" step="0.1" value="{float(values['exit_z']):.2f}" /></label>
          <label><span>Stop Z</span><input type="number" name="stop_z" min="0.2" step="0.1" value="{float(values['stop_z']):.2f}" /></label>
          <label><span>Max Holding Bars</span><input type="number" name="max_holding_bars" min="1" value="{int(float(values['max_holding_bars']))}" /></label>
          <label><span>Min Correlation</span><input type="number" name="min_correlation" min="0" max="1" step="0.05" value="{float(values['min_correlation']):.2f}" /></label>
          <label><span>Notional Per Leg</span><input type="number" name="notional_per_leg" min="1" step="1" value="{float(values['notional_per_leg']):.2f}" /></label>
          <label><span>Fee bps / Leg</span><input type="number" name="fee_bps_per_leg" min="0" step="0.1" value="{float(values['fee_bps_per_leg']):.1f}" /></label>
          <label><span>Slippage bps / Leg</span><input type="number" name="slippage_bps_per_leg" min="0" step="0.1" value="{float(values['slippage_bps_per_leg']):.1f}" /></label>
        </div>
        <div class="settings-submit-bar"><button type="submit">{t("运行配对统计套利回测", "Run Pair Stat-arb Backtest")}</button></div>
      </form>
      {f'<div class="notice notice-success">{escape(message)}</div>' if message else ""}
      {f'<div class="notice notice-error">{escape(error)}</div>' if error else ""}
      <p class="helper-text">{t("研究回测采用滚动对数价格 OLS；相关性与残差半衰期仅用于诊断，不等同于协整检验结论。", "The research backtest uses rolling log-price OLS; correlation and residual half-life are diagnostics, not proof of cointegration.")}</p>
      {result_html}
    """


def _strategy_hit_columns(lang: str) -> list[tuple[str, str]]:
    return [
        (_text(lang, "标的", "Symbol"), "symbol"),
        (_text(lang, "策略", "Strategy"), "strategy"),
        (_text(lang, "评分", "Score"), "score"),
        (_text(lang, "等级", "Grade"), "grade"),
        (_text(lang, "动作", "Action"), "action"),
        ("24h %", "price_change_percent"),
        (_text(lang, "资金费率 bps", "Funding bps"), "funding_rate_bps"),
        (_text(lang, "价差 bps", "Basis bps"), "spread_bps"),
        (_text(lang, "来源", "Source"), "source"),
        (_text(lang, "原因", "Reasons"), "reasons"),
    ]


def _risk_gate_content(risk: dict[str, object], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    allowed_symbols = [str(symbol) for symbol in risk.get("allowed_symbols", [])] if isinstance(risk.get("allowed_symbols"), list) else []
    blocked_symbols = dict(risk.get("blocked_symbols") or {}) if isinstance(risk.get("blocked_symbols"), dict) else {}
    factors = risk.get("risk_factors") if isinstance(risk.get("risk_factors"), list) else []
    allowed_rows = [{"symbol": symbol, "decision": "allow", "reason": t("通过当前执行前风控", "Passed the current pre-trade gate")} for symbol in allowed_symbols]
    blocked_rows = [{"symbol": symbol, "decision": "block", "reason": reason} for symbol, reason in blocked_symbols.items()]
    empty = lambda zh, en: f'<p class="helper-text">{escape(t(zh, en))}</p>'
    allowed_html = (
        _terminal_rows(allowed_rows, [(t("标的", "Symbol"), "symbol"), (t("决策", "Decision"), "decision"), (t("说明", "Reason"), "reason")], lang=lang)
        if allowed_rows
        else empty("当前没有允许执行的策略候选。", "No strategy candidates are currently allowed.")
    )
    blocked_html = (
        _terminal_rows(blocked_rows, [(t("标的", "Symbol"), "symbol"), (t("决策", "Decision"), "decision"), (t("原因", "Reason"), "reason")], lang=lang)
        if blocked_rows
        else empty("当前无阻断标的。", "No symbols are currently blocked.")
    )
    factors_html = (
        _terminal_rows(factors, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("因子", "Factor"), "factor"), (t("值", "Value"), "value"), (t("严重度", "Severity"), "severity"), (t("决策", "Decision"), "decision"), (t("原因", "Reason"), "reason")], lang=lang)
        if factors
        else empty("暂无风险因子，等待行情、链上或策略数据刷新。", "No risk factors yet; waiting for market, on-chain, or strategy data.")
    )
    return f"""
      <div class="terminal-risk-board">
        <div class="mini-stat"><span>{t("状态", "Status")}</span><strong>{escape(_display_value(risk.get("status", ""), lang))}</strong></div>
        <div class="mini-stat"><span>{t("风险分", "Risk Score")}</span><strong>{float(risk.get("risk_score") or 0.0):.1f}</strong></div>
        <div class="mini-stat"><span>{t("允许", "Allowed")}</span><strong>{len(allowed_symbols)}</strong></div>
        <div class="mini-stat"><span>{t("阻断", "Blocked")}</span><strong>{len(blocked_symbols)}</strong></div>
      </div>
      <div class="terminal-risk-sections">
        <section>
          <h3>{t("允许候选", "Allowed Candidates")}</h3>
          {allowed_html}
        </section>
        <section>
          <h3>{t("阻断标的", "Blocked Symbols")}</h3>
          {blocked_html}
        </section>
      </div>
      <section class="terminal-risk-factors">
        <h3>{t("风险因子明细", "Risk Factor Details")}</h3>
        {factors_html}
      </section>
    """


def _llm_analysis_content(llm: dict[str, object], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    provider = _display_value(llm.get("provider", ""), lang)
    model = _display_value(llm.get("model", ""), lang)
    status = _display_value(llm.get("status", ""), lang)
    mode = _display_value(llm.get("analysis_mode", llm.get("status", "")), lang)
    metrics = llm.get("metrics") if isinstance(llm.get("metrics"), dict) else {}
    opportunities = [item for item in llm.get("opportunities", []) if isinstance(item, dict)] if isinstance(llm.get("opportunities"), list) else []
    risks = [item for item in llm.get("risks", []) if isinstance(item, dict)] if isinstance(llm.get("risks"), list) else []
    actions = [item for item in llm.get("actions", []) if isinstance(item, dict)] if isinstance(llm.get("actions"), list) else []
    summary = str(llm.get("summary") or t("等待模型或本地规则生成分析。", "Waiting for model or local rules analysis."))
    market_state = str(llm.get("market_state") or "")
    metrics_cards = [
        (t("状态", "Status"), status),
        (t("模式", "Mode"), mode),
        (t("策略命中", "Strategy Hits"), str(metrics.get("strategy_hits", "-"))),
        (t("风险分", "Risk Score"), str(metrics.get("risk_score", "-"))),
    ]
    return f"""
      <div class="llm-analysis">
        <div class="mini-stat-grid llm-stat-grid">
          <div class="mini-stat"><span>{t("Provider", "Provider")}</span><strong>{escape(provider or "-")}</strong></div>
          <div class="mini-stat"><span>{t("Model", "Model")}</span><strong>{escape(model or "-")}</strong></div>
          {"".join(f'<div class="mini-stat"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>' for label, value in metrics_cards)}
        </div>
        {f'<p class="llm-market-state">{escape(market_state)}</p>' if market_state else ''}
        <p class="terminal-insight">{escape(summary)}</p>
        <div class="llm-analysis-sections">
          <section>
            <h3>{t("机会判断", "Opportunity Readout")}</h3>
            {_terminal_rows(opportunities, [(t("标的", "Symbol"), "symbol"), (t("动作", "Action"), "action"), (t("评分", "Score"), "score"), (t("来源", "Source"), "source"), (t("原因", "Reason"), "reason")], lang=lang)}
          </section>
          <section>
            <h3>{t("风险提示", "Risk Notes")}</h3>
            {_terminal_rows(risks, [(t("标的", "Symbol"), "symbol"), (t("级别", "Level"), "level"), (t("来源", "Source"), "source"), (t("原因", "Reason"), "reason")], lang=lang)}
          </section>
          <section class="llm-actions">
            <h3>{t("执行建议", "Execution Suggestions")}</h3>
            {_terminal_rows(actions, [(t("优先级", "Priority"), "priority"), (t("建议", "Suggestion"), "action"), (t("原因", "Reason"), "reason")], lang=lang)}
          </section>
        </div>
      </div>
    """


def _onchain_overview_content(events: object, sources: object, lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    event_rows = events if isinstance(events, list) else []
    source_rows = sources if isinstance(sources, list) else []
    source_html = (
        _terminal_rows(source_rows, [(t("链", "Chain"), "chain"), (t("标的", "Symbol"), "symbol"), (t("来源", "Source"), "source"), (t("状态", "Status"), "status")], lang=lang)
        if source_rows
        else f'<p class="helper-text">{escape(t("链上数据源正在初始化。", "On-chain data sources are initializing."))}</p>'
    )
    event_html = (
        _terminal_rows(event_rows, [(t("链", "Chain"), "chain"), (t("标的", "Symbol"), "symbol"), (t("类型", "Type"), "event_type"), (t("来源", "Source"), "source"), ("USD", "amount_usd"), (t("方向", "Direction"), "direction"), (t("严重度", "Severity"), "severity")], lang=lang)
        if event_rows
        else f'<p class="helper-text">{escape(t("当前公开链上接口未返回达到阈值的异动；后台会继续刷新。", "No threshold-matching on-chain events returned yet; background refresh continues."))}</p>'
    )
    return f"""
      <section class="terminal-onchain-sources">
        <h3>{t("数据源状态", "Data Source Status")}</h3>
        {source_html}
      </section>
      <section class="terminal-onchain-events">
        <h3>{t("异动明细", "Event Details")}</h3>
        {event_html}
      </section>
    """


def _terminal_system_layers(lang: str = "zh") -> str:
    layers = [
        (_text(lang, "接入层", "Access Layer"), "Binance API", _text(lang, "OKX 就绪", "OKX Ready"), "Twitter/X", _text(lang, "链上 CSV", "On-chain CSV"), "OpenAI"),
        (_text(lang, "策略层", "Strategy Layer"), _text(lang, "信号评分", "Signal Scoring"), _text(lang, "趋势突破", "Trend Breakout"), _text(lang, "量价压力", "Volume Pressure"), _text(lang, "跨市价差", "Cross-market Basis"), _text(lang, "策略命中", "Strategy Hits")),
        (_text(lang, "执行层", "Execution Layer"), _text(lang, "模拟交易", "Paper Trading"), "Live Guard", "order/test", _text(lang, "仓位状态", "Position State"), _text(lang, "风控阈值", "Risk Limits")),
        (_text(lang, "数据层", "Data Layer"), _text(lang, "行情", "Market Data"), _text(lang, "社区情报", "Community Intel"), _text(lang, "链上异动", "On-chain Events"), _text(lang, "持仓", "Positions"), _text(lang, "交易日志", "Trade Logs")),
    ]
    return "".join(
        f"""
        <div class="terminal-layer">
          <strong>{escape(name)}</strong>
          {"".join(f"<span>{escape(item)}</span>" for item in items)}
        </div>
        """
        for name, *items in layers
    )


def _terminal_dashboard_value(value: object, lang: str) -> str:
    text = _display_value(value, lang)
    return text if text else "-"


def _terminal_status_chip(label: str, status: object, lang: str) -> str:
    raw_status = str(status or "").lower()
    if raw_status in {"ready", "configured", "ready_public", "api_live", "live", "enabled", "ok"}:
        chip_class = "ready"
    elif raw_status in {"guarded", "partial_configured", "fallback", "monitoring", "watch_only", "pending_scan", "wait_pullback", "wait_support", "wait_volatility"}:
        chip_class = "pending"
    elif raw_status in {"source_missing", "not_configured", "auth_failed", "empty", "error"}:
        chip_class = "blocked"
    else:
        chip_class = "neutral"
    return f"""
      <span class="terminal-status-chip {chip_class}">
        <i aria-hidden="true"></i>
        <strong>{escape(label)}</strong>
        <small>{escape(_terminal_dashboard_value(status, lang))}</small>
      </span>
    """


def _terminal_sparkline(values: list[float], *, accent: str = "blue") -> str:
    if not values:
        values = [28.0, 36.0, 32.0, 44.0, 39.0, 52.0, 48.0, 61.0]
    values = values[-14:]
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum or 1.0
    points = []
    bars = []
    for index, value in enumerate(values):
        x = 8 + index * (144 / max(1, len(values) - 1))
        y = 54 - ((value - minimum) / span) * 38
        points.append(f"{x:.1f},{y:.1f}")
        bar_height = max(4.0, 12 + ((value - minimum) / span) * 24)
        bars.append(f'<rect x="{x - 3:.1f}" y="{72 - bar_height:.1f}" width="6" height="{bar_height:.1f}" rx="2"></rect>')
    return f"""
      <svg class="terminal-dashboard-chart chart-{escape(accent)}" viewBox="0 0 164 78" preserveAspectRatio="none" aria-hidden="true">
        <path d="M8 54 H156 M8 36 H156 M8 18 H156" class="grid"></path>
        <g class="bars">{"".join(bars)}</g>
        <polyline points="{escape(" ".join(points))}"></polyline>
      </svg>
    """


def _terminal_dashboard_table(rows: list[dict[str, object]], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    if not rows:
        return f'<p class="helper-text">{escape(t("等待策略命中和交易事件刷新。", "Waiting for strategy hits and trading events."))}</p>'
    body = []
    for row in rows[:5]:
        pnl_value = row.get("pnl")
        pnl = _float_from_any(pnl_value)
        pnl_class = "positive" if pnl >= 0 else "negative"
        pnl_text = "-" if pnl_value is None else f"{pnl:+,.2f}"
        body.append(
            f"""
            <tr>
              <td><strong>{escape(str(row.get("name") or "-"))}</strong><span>{escape(str(row.get("meta") or ""))}</span></td>
              <td>{escape(_terminal_dashboard_value(row.get("status"), lang))}</td>
              <td>{escape(_terminal_dashboard_value(row.get("positions"), lang))}</td>
              <td class="{pnl_class}">{escape(pnl_text)}</td>
              <td>{escape(_terminal_dashboard_value(row.get("rate"), lang))}</td>
            </tr>
            """
        )
    return f"""
      <table class="terminal-dashboard-table">
        <thead>
          <tr>
            <th>{t("策略", "Strategy")}</th>
            <th>{t("状态", "Status")}</th>
            <th>{t("持仓", "Pos")}</th>
            <th>{t("今日盈亏", "PnL")}</th>
            <th>{t("胜率", "Win")}</th>
          </tr>
        </thead>
        <tbody>{"".join(body)}</tbody>
      </table>
    """


def _terminal_today_realized_pnl(events: list[dict[str, object]], symbol: str) -> float:
    today = now_app_time().date().isoformat()
    symbol = symbol.upper()
    total = 0.0
    for event in events:
        if str(event.get("symbol") or "").upper() != symbol:
            continue
        if not str(event.get("created_at") or "").startswith(today):
            continue
        total += _float_from_any(event.get("realized_pnl"))
    return total


def _terminal_closed_win_rate(events: list[dict[str, object]], symbol: str) -> str:
    symbol = symbol.upper()
    closed = [
        event
        for event in events
        if str(event.get("symbol") or "").upper() == symbol and event.get("realized_pnl") is not None
    ]
    if not closed:
        return "-"
    wins = sum(1 for event in closed if _float_from_any(event.get("realized_pnl")) > 0)
    return f"{(wins / len(closed)) * 100:.1f}%"


def _terminal_market_intel_content(items: list[dict[str, object]], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    rows = []
    for item in items[:6]:
        symbol = str(item.get("symbol") or "-")
        source = str(item.get("source") or "-")
        title = str(item.get("title") or "")
        severity = _float_from_any(item.get("severity"))
        rows.append(
            f"""
            <li>
              <button type="button" class="terminal-market-row" data-symbol="{escape(symbol, quote=True)}">
                <span>
                  <strong>{escape(symbol)}</strong>
                  <small>{escape(source)}</small>
                </span>
                <em>{severity:.1f}</em>
              </button>
              <p>{escape(title)}</p>
            </li>
            """
        )
    if not rows:
        return f'<p class="helper-text">{escape(t("暂无实时行情情报。", "No live market intelligence yet."))}</p>'
    return f"""
      <div class="terminal-market-live">
        <div class="terminal-market-live-head">
          <span>{t("实时 24h 行情", "Live 24h Market")}</span>
          <a href="/terminal/market">{t("查看完整市场页", "Open market page")}</a>
        </div>
        <ul>{"".join(rows)}</ul>
      </div>
    """


def _terminal_dashboard_feature_cards(lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    cards = [
        ("AT", t("自动交易", "Auto Trading"), t("策略信号驱动 paper/live 执行", "Strategy-driven paper/live execution"), "/terminal/trading"),
        ("RC", t("风险控制", "Risk Control"), t("执行前阻断与风险因子明细", "Pre-trade gates and factors"), "/terminal/risk"),
        ("OC", t("链上监控", "On-chain Monitor"), t("大额转账与交易所流向", "Large transfers and exchange flows"), "/terminal/onchain"),
        ("CI", t("社区情报", "Community Intel"), t("交易所热点与账号监控", "Exchange heat and tracked accounts"), "/terminal/community"),
        ("BT", t("回测分析", "Backtest"), t("策略参数和历史表现验证", "Strategy validation on history"), "/backtest"),
        ("MI", t("数据概览", "Market Data"), t("行情、资金费率和价差", "Market, funding, and basis"), "/terminal/market"),
    ]
    return "".join(
        f"""
        <a class="terminal-feature-card" href="{escape(href, quote=True)}">
          <span>{escape(icon)}</span>
          <strong>{escape(title)}</strong>
          <small>{escape(description)}</small>
        </a>
        """
        for icon, title, description, href in cards
    )


def _terminal_dashboard_showcase(snapshot: dict[str, object], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    platform = snapshot["platform"] if isinstance(snapshot.get("platform"), dict) else {}
    risk = snapshot["execution_risk"] if isinstance(snapshot.get("execution_risk"), dict) else {}
    strategy_hits = [item for item in snapshot.get("strategy_hits", []) if isinstance(item, dict)] if isinstance(snapshot.get("strategy_hits"), list) else []
    intel_items = [item for item in snapshot.get("intel_items", []) if isinstance(item, dict)] if isinstance(snapshot.get("intel_items"), list) else []
    accounts = [item for item in platform.get("accounts", []) if isinstance(item, dict)] if isinstance(platform.get("accounts"), list) else []
    components = [item for item in platform.get("components", []) if isinstance(item, dict)] if isinstance(platform.get("components"), list) else []
    strategies = [item for item in platform.get("strategies", []) if isinstance(item, dict)] if isinstance(platform.get("strategies"), list) else []
    source_rows = snapshot.get("market_sources", []) if isinstance(snapshot.get("market_sources"), list) else []
    recent_events = [item for item in platform.get("recent_events", []) if isinstance(item, dict)] if isinstance(platform.get("recent_events"), list) else []

    account_exposure = sum(_float_from_any(item.get("quote_exposure")) for item in accounts)
    account_pnl = sum(_float_from_any(item.get("realized_pnl")) for item in accounts)
    account_trades = sum(int(_float_from_any(item.get("total_trades"))) for item in accounts)
    account_events = sum(int(_float_from_any(item.get("event_count"))) for item in accounts)
    open_positions = sum(int(_float_from_any(item.get("open_positions"))) for item in accounts)
    max_win_rate = max([_float_from_any(item.get("win_rate_pct")) for item in accounts] or [0.0])
    max_profit_loss_ratio = max([_float_from_any(item.get("profit_loss_ratio")) for item in accounts] or [0.0])
    risk_score = _float_from_any(risk.get("risk_score"))
    allowed_symbols = risk.get("allowed_symbols") if isinstance(risk.get("allowed_symbols"), list) else []
    blocked_symbols = risk.get("blocked_symbols") if isinstance(risk.get("blocked_symbols"), dict) else {}
    market_values = [_float_from_any(item.get("severity")) for item in intel_items if _float_from_any(item.get("severity")) > 0]

    component_status = {str(item.get("name") or "").lower(): item.get("status") for item in components}
    exchange_chips = [
        _terminal_status_chip("BINANCE", component_status.get("binance api", "ready_public"), lang),
        _terminal_status_chip("OKX", component_status.get("okx api", "not_configured"), lang),
    ]
    source_chips = [
        _terminal_status_chip(str(item.get("source") or "-").upper(), item.get("status"), lang)
        for item in source_rows[:4]
        if isinstance(item, dict)
    ]

    strategy_rows: list[dict[str, object]] = []
    if strategy_hits:
        for item in strategy_hits[:5]:
            symbol = str(item.get("symbol") or "").upper()
            strategy_rows.append(
                {
                    "name": item.get("strategy") or item.get("symbol"),
                    "meta": symbol or item.get("source") or "",
                    "status": item.get("action") or "hit",
                    "positions": 0,
                    "pnl": _terminal_today_realized_pnl(recent_events, symbol) if symbol else None,
                    "rate": _terminal_closed_win_rate(recent_events, symbol) if symbol else "-",
                }
            )
    else:
        for index, item in enumerate(strategies[:5]):
            strategy_rows.append(
                {
                    "name": item.get("name") or item.get("strategy_id") or "-",
                    "meta": item.get("strategy_id") or "",
                    "status": item.get("status") or "-",
                    "positions": open_positions if index == 0 else "-",
                    "pnl": account_pnl if index == 0 else None,
                    "rate": f"{max_win_rate:.1f}%" if index == 0 else "-",
                }
            )

    kpis = [
        (t("今日信号", "Signals"), str(int(snapshot.get("returned_signals") or len(strategy_hits))), t("策略候选", "strategy candidates"), "blue"),
        (t("累计成交", "Fills"), str(account_trades), f"{t('执行事件', 'events')} {account_events}", "green"),
        (t("胜率", "Win Rate"), f"{max_win_rate:.1f}%", f"{t('盈亏比', 'P/L')} {max_profit_loss_ratio:.2f}", "cyan"),
        (t("账户盈亏", "Account PnL"), f"{account_pnl:+,.2f}", f"{t('敞口', 'exposure')} {account_exposure:,.2f}", "green"),
        (t("情报项", "Intel"), str(len(intel_items)), t("交易所/社区聚合", "exchange/community"), "cyan"),
        (t("风险评分", "Risk"), f"{risk_score:.0f}", _terminal_dashboard_value(risk.get("status"), lang), "amber"),
    ]
    kpi_html = "".join(
        f"""
        <article class="terminal-dashboard-kpi {escape(accent)}">
          <span>{escape(label)}</span>
          <strong>{escape(value)}</strong>
          <small>{escape(subtitle)}</small>
        </article>
        """
        for index, (label, value, subtitle, accent) in enumerate(kpis)
    )

    return f"""
      <section class="terminal-showcase" aria-label="{t("工作台总览", "Workbench Overview")}">
        <div class="terminal-showcase-body">
          <div class="terminal-showcase-content">
            <div class="terminal-dashboard-kpis">{kpi_html}</div>
            <div class="terminal-dashboard-main">
              <section class="terminal-dashboard-card strategy-card">
                <div class="terminal-dashboard-card-head">
                  <div>
                    <h3>{t("策略运行状态", "Strategy Runtime")}</h3>
                    <p>{t("命中候选、执行意图和账户表现。", "Hit candidates, execution intent, and account performance.")}</p>
                  </div>
                  <a href="/terminal/strategies">{t("查看策略", "View")}</a>
                </div>
                <div class="terminal-dashboard-scroll">{_terminal_dashboard_table(strategy_rows, lang)}</div>
              </section>
              <section class="terminal-dashboard-card market-card">
                <div class="terminal-dashboard-card-head">
                  <div>
                    <h3>{t("市场行情", "Market Tape")}</h3>
                    <p>{t("基于当前交易所实时 ticker 和情报接口。", "Backed by current exchange ticker and intelligence feeds.")}</p>
                  </div>
                </div>
                <div class="terminal-dashboard-scroll">{_terminal_market_intel_content(intel_items, lang)}</div>
              </section>
              <section class="terminal-dashboard-card side-card">
                <h3>{t("交易所连接", "Exchange Links")}</h3>
                <div class="terminal-dashboard-scroll side-card-scroll">
                  <div class="terminal-connection-list">{"".join(exchange_chips)}</div>
                  <h3>{t("风控概览", "Risk Summary")}</h3>
                  <dl class="terminal-risk-mini">
                    <div><dt>{t("总风险分", "Risk Score")}</dt><dd>{risk_score:.1f}</dd></div>
                    <div><dt>{t("允许候选", "Allowed")}</dt><dd>{len(allowed_symbols)}</dd></div>
                    <div><dt>{t("阻断标的", "Blocked")}</dt><dd>{len(blocked_symbols)}</dd></div>
                  </dl>
                </div>
              </section>
            </div>
          </div>
        </div>
        <div class="terminal-feature-strip">
          {_terminal_dashboard_feature_cards(lang)}
        </div>
      </section>
    """


def _terminal_panel(title: str, subtitle: str, body: str, *, wide: bool = False) -> str:
    panel_class = "terminal-panel wide" if wide else "terminal-panel"
    return f"""
      <article class="{panel_class}">
        <div class="section-heading">
          <h2>{escape(title)}</h2>
          <p>{escape(subtitle)}</p>
        </div>
        {body}
      </article>
    """


def _terminal_shell(active_module: str, body: str, lang: str = "zh") -> str:
    return f"""
      <section class="terminal-shell terminal-shell-single" data-module="{escape(active_module)}" data-lang="{escape(normalize_language(lang))}">
        <div class="terminal-main">
          <section class="terminal-grid">
            {body}
          </section>
        </div>
      </section>
    """


def render_terminal_page(
    snapshot: dict[str, object],
    *,
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    intel_items = snapshot["intel_items"]
    twitter_accounts = snapshot["twitter_accounts"]
    onchain_events = snapshot["onchain_events"]
    onchain_sources = snapshot.get("onchain_sources", [])
    spreads = snapshot["spreads"]
    funding_rates = snapshot.get("funding_rates", [])
    carry_paper = snapshot.get("carry_paper") if isinstance(snapshot.get("carry_paper"), dict) else {}
    market_sources = snapshot.get("market_sources", [])
    strategy_hits = snapshot["strategy_hits"]
    llm = snapshot["llm_insight"] if isinstance(snapshot.get("llm_insight"), dict) else {}
    risk = snapshot["execution_risk"]
    platform = snapshot["platform"]
    btc_trading = snapshot.get("btc_trading") if isinstance(snapshot.get("btc_trading"), dict) else {}
    hero_right = f"""
      {_terminal_card(t("扫描标的", "Scanned Symbols"), str(int(snapshot["scanned_symbols"])), "Binance Spot Universe", "cyan")}
      {_terminal_card(t("策略命中", "Strategy Hits"), str(len(strategy_hits)), t("含资金费率过滤", "with funding filters"), "green")}
      {_terminal_card(t("执行风控", "Execution Risk"), _display_value(risk["status"], active_lang).upper(), f'{t("风险分", "risk")} {float(risk["risk_score"]):.1f}', "amber")}
      {_terminal_card(t("可执行候选", "Allowed Candidates"), str(len(risk["allowed_symbols"])), f'{t("已阻断", "blocked")} {len(risk["blocked_symbols"])}', "green")}
    """
    panels = "".join(
        [
            _terminal_dashboard_showcase(snapshot, active_lang),
            _terminal_panel(t("BTC交易专区", "BTC Trading Zone"), t("BTC 专属信号、模拟账户 BTC 统计和执行建议。", "BTC-specific signal, paper BTC metrics, and execution plan."), _btc_trading_zone(btc_trading, active_lang), wide=True),
            _terminal_panel(t("功能实现状态", "Capability Status"), t("架构组件、API 入口和配置状态。", "Architecture components, API endpoints, and configuration state."), _terminal_rows(platform["components"], [(t("层级", "Layer"), "layer"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("能力", "Capability"), "capability"), (t("接口", "Endpoint"), "endpoint")], lang=active_lang), wide=True),
            _terminal_panel(t("交易账户概览", "Trading Accounts"), t("模拟交易和真实交易账户状态。", "Paper and live account state."), _terminal_rows(platform["accounts"], [(t("交易所", "Exchange"), "exchange"), (t("模式", "Mode"), "mode"), (t("状态", "Status"), "status"), (t("持仓数", "Positions"), "open_positions"), (t("敞口", "Exposure"), "quote_exposure"), (t("执行事件", "Events"), "event_count"), (t("累计成交", "Fills"), "total_trades"), (t("平仓数", "Closed"), "closed_trades"), (t("胜率", "Win Rate"), "win_rate_pct"), (t("盈亏比", "P/L Ratio"), "profit_loss_ratio"), (t("已实现盈亏", "Realized PnL"), "realized_pnl")], lang=active_lang), wide=True),
            _terminal_panel(t("大模型分析", "LLM Analysis"), t("基于行情、社区、链上、价差、资金费率和风控快照生成机会、风险和执行建议。", "Generates opportunity, risk, and execution suggestions from market, community, on-chain, basis, funding, and risk snapshots."), _llm_analysis_content(llm, active_lang), wide=True),
            _terminal_panel(
                t("执行前风控", "Pre-trade Risk Gate"),
                str(risk["summary"]),
                _risk_gate_content(risk, active_lang),
                wide=True,
            ),
            _terminal_panel(t("交易所与热门情报", "Exchange & Market Intelligence"), t("公告、新闻、社区热度与信号引擎聚合。", "Announcements, news, community heat, and signal-engine intelligence."), _terminal_rows(intel_items, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("标题", "Title"), "title"), (t("严重度", "Severity"), "severity")], lang=active_lang)),
            _terminal_panel(t("Twitter 账户监控", "Twitter Account Monitor"), t("运行配置中的 tracked accounts。", "Tracked accounts from runtime configuration."), _terminal_rows(twitter_accounts, [(t("账号", "Account"), "username"), (t("关注点", "Focus"), "focus"), (t("模式", "Mode"), "mode"), (t("状态", "Status"), "status")], lang=active_lang)),
            _terminal_panel(t("链上异动", "On-chain Events"), t("公开链上接口返回的大额转账、网络快照与风险代理。", "Large transfers, network snapshots, and risk proxies from public on-chain APIs."), _onchain_overview_content(onchain_events, onchain_sources, active_lang), wide=True),
            _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("用于套利、对冲和资金费率观察。", "Used for arbitrage, hedging, and funding-rate monitoring."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("合约", "Futures"), "futures_exchange"), ("Spread bps", "spread_bps"), (t("方向", "Direction"), "direction")], lang=active_lang)),
            _terminal_panel(t("合约资金费率", "Futures Funding"), t("小市值动量、末端分布和暴跌反弹策略会使用该因子过滤。", "Low-cap momentum, distribution, and capitulation strategies use this factor as a filter."), _terminal_rows(funding_rates, [(t("标的", "Symbol"), "symbol"), (t("合约", "Futures"), "futures_exchange"), ("Funding bps", "funding_rate_bps"), ("Annualized %", "annualized_pct"), (t("来源", "Source"), "source")], lang=active_lang)),
            _terminal_panel(t("策略命中", "Strategy Hits"), t("自动交易前的候选池、资金费率、价差和执行意图。", "Candidate pool, funding, basis, and execution intent before automated trading."), _terminal_rows(strategy_hits, _strategy_hit_columns(active_lang), lang=active_lang), wide=True),
            _terminal_panel(t("策略目录", "Strategy Catalog"), t("已实现策略、触发条件和执行方式。", "Implemented strategies, triggers, and execution methods."), _terminal_rows(platform["strategies"], [("ID", "strategy_id"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("触发条件", "Trigger"), "trigger"), (t("执行方式", "Execution"), "execution")], lang=active_lang)),
            _terminal_panel(t("风险规则", "Risk Rules"), t("执行层硬性约束和保护条件。", "Hard execution constraints and guardrails."), _terminal_rows(platform["risk_rules"], [(t("规则", "Rule"), "name"), (t("状态", "Status"), "status"), (t("阈值", "Threshold"), "threshold"), (t("动作", "Action"), "action")], lang=active_lang)),
            _terminal_panel(t("交易日志", "Trading Logs"), t("自动交易执行、跳过、阻断和下单事件。", "Automated trading execution, skip, block, and order events."), _terminal_rows(platform["recent_events"], [(t("时间", "Time"), "created_at"), (t("动作", "Action"), "action"), (t("标的", "Symbol"), "symbol"), (t("状态", "Status"), "status"), (t("消息", "Message"), "message")], lang=active_lang), wide=True),
        ]
    )
    content = _terminal_shell("overview", panels, active_lang)
    return _layout(
        page_title="AI Trade Command Center",
        active_page="terminal",
        hero_title=t("交易所、社区、链上、价差和策略执行的统一总控台。", "Unified command center for exchange, community, on-chain, basis, and strategy execution."),
        hero_text=t("将关键交易所信息、热门社区情报、Twitter 账号、链上异动、现货合约价差和策略命中集中分析，并可交给自动交易引擎执行。", "Centralize exchange intelligence, community signals, Twitter accounts, on-chain anomalies, spot/futures basis, and strategy hits, then hand execution intent to the automated trading engine."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/terminal",
        layout_context=layout_context,
    )


def render_terminal_module_page(
    *,
    snapshot: dict[str, object],
    module: str,
    trading_status: dict[str, object] | None = None,
    paper_auto_status: dict[str, object] | None = None,
    message: str | None = None,
    error: str | None = None,
    strategy_builder_result: dict[str, object] | None = None,
    strategy_builder_text: str = "",
    stat_arb_result: dict[str, object] | None = None,
    stat_arb_params: dict[str, object] | None = None,
    stat_arb_message: str | None = None,
    stat_arb_error: str | None = None,
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    intel_items = snapshot["intel_items"]
    twitter_accounts = snapshot["twitter_accounts"]
    onchain_events = snapshot["onchain_events"]
    onchain_sources = snapshot.get("onchain_sources", [])
    spreads = snapshot["spreads"]
    funding_rates = snapshot.get("funding_rates", [])
    carry_paper = snapshot.get("carry_paper") if isinstance(snapshot.get("carry_paper"), dict) else {}
    market_sources = snapshot.get("market_sources", [])
    strategy_hits = snapshot["strategy_hits"]
    strategy_templates = snapshot.get("strategy_templates", [])
    risk = snapshot["execution_risk"]
    platform = snapshot["platform"]
    trading_status = trading_status or {"config": {}, "open_positions": [], "events": []}
    warning = str(snapshot.get("warning") or "").strip()
    notice_html = f'<div class="notice notice-warning terminal-notice">{escape(warning)}</div>' if warning else ""

    module_titles = {
        "market": (t("交易市场", "Markets"), t("交易所关键情报、热门标的和信号引擎结果。", "Exchange intelligence, trending symbols, and signal-engine output.")),
        "community": (t("社区情报", "Community Intelligence"), t("Twitter/X tracked accounts、社区热度和行业信息源。", "Twitter/X tracked accounts, community heat, and industry information sources.")),
        "onchain": (t("链上监控", "On-chain Monitor"), t("链上大额异动、交易所流入流出和风险代理。", "Large on-chain movements, exchange flows, and risk proxies.")),
        "basis": (t("价差分析", "Basis Analysis"), t("现货、合约和跨市场 basis 机会。", "Spot, futures, and cross-market basis opportunities.")),
        "strategies": (t("策略命中", "Strategy Hits"), t("策略目录、命中候选和自动执行意图。", "Strategy catalog, hit candidates, and automated execution intent.")),
        "trading": (t("自动交易", "Auto Trading"), t("模拟账户、策略信号源和执行事件。", "Paper account, strategy signal source, and execution events.")),
        "risk": (t("风险控制", "Risk Control"), t("执行前风控、阻断原因和硬性风险规则。", "Pre-trade risk gate, block reasons, and hard risk rules.")),
    }
    title, subtitle = module_titles.get(module, module_titles["market"])

    if module == "market":
        panels = "".join(
            [
                notice_html,
                _terminal_panel(t("实时数据源", "Live Data Sources"), t("当前页面优先读取交易所公开接口，接口失败时才降级到本地 CSV。", "This page reads exchange public APIs first and falls back to local CSV only on failures."), _terminal_rows(market_sources if isinstance(market_sources, list) else [], [(t("来源", "Source"), "source"), (t("标的数", "Symbols"), "symbols"), (t("状态", "Status"), "status")], lang=active_lang), wide=True),
                _terminal_panel(t("交易所与热门情报", "Exchange & Market Intelligence"), t("公告、新闻、市场热度与信号引擎聚合。", "Announcements, news, market heat, and signal-engine intelligence."), _terminal_rows(intel_items, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("标题", "Title"), "title"), (t("严重度", "Severity"), "severity"), (t("情绪", "Sentiment"), "sentiment")], lang=active_lang), wide=True),
                _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("价差异常会参与执行前风控。", "Basis anomalies feed the pre-trade risk gate."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("现货价格", "Spot Price"), "spot_price"), (t("合约", "Futures"), "futures_exchange"), (t("合约价格", "Futures Price"), "futures_price"), ("Spread bps", "spread_bps")], lang=active_lang), wide=True),
                _terminal_panel(t("合约资金费率", "Futures Funding"), t("用于判断追多拥挤、空头拥挤和暴跌反弹质量。", "Used to detect crowded longs, crowded shorts, and capitulation-rebound quality."), _terminal_rows(funding_rates, [(t("标的", "Symbol"), "symbol"), (t("合约", "Futures"), "futures_exchange"), ("Funding bps", "funding_rate_bps"), ("Annualized %", "annualized_pct"), (t("下次结算", "Next Funding"), "next_funding_time")], lang=active_lang), wide=True),
            ]
        )
    elif module == "community":
        twitter_actions = f"""
          <div class="terminal-panel-actions">
            <a class="action-link" href="{escape(_url('/settings#settings-twitter', active_lang), quote=True)}">{t("开启/配置账户监控", "Enable / Configure Account Monitor")}</a>
            <a class="action-link" href="{escape(_url('/api/terminal/community', active_lang), quote=True)}">{t("查看 JSON", "View JSON")}</a>
          </div>
        """
        panels = "".join(
            [
                notice_html,
                _terminal_panel(t("社区数据源", "Community Data Sources"), t("交易所公开行情、X/Reddit 和本地数据源的当前读取状态。", "Current read state for exchange public feeds, X/Reddit, and local sources."), _terminal_rows(market_sources if isinstance(market_sources, list) else [], [(t("来源", "Source"), "source"), (t("标的数", "Symbols"), "symbols"), (t("状态", "Status"), "status")], lang=active_lang), wide=True),
                _terminal_panel(t("Twitter 账户监控", "Twitter Account Monitor"), t("运行配置中的 tracked accounts 和抓取状态。", "Tracked accounts and fetch state from runtime configuration."), twitter_actions + _terminal_rows(twitter_accounts, [(t("账号", "Account"), "username"), (t("关注点", "Focus"), "focus"), (t("模式", "Mode"), "mode"), (t("权重", "Weight"), "weight_pct"), (t("状态", "Status"), "status")], lang=active_lang), wide=True),
                _terminal_panel(t("社区/交易所情报", "Community / Exchange Intelligence"), t("X、Reddit、本地新闻、Telegram 与信号引擎信息统一入池。", "X, Reddit, local news, Telegram, and signal-engine items are merged into one intelligence pool."), _terminal_rows(intel_items, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("类别", "Category"), "category"), (t("标题", "Title"), "title"), (t("严重度", "Severity"), "severity")], lang=active_lang), wide=True),
            ]
        )
    elif module == "onchain":
        panels = "".join(
            [
                notice_html,
                _terminal_panel(t("链上异动", "On-chain Events"), t("默认通过公开接口读取 BTC、ETH、DOGE、SOL、ZEC、XRP 主链数据；本地 CSV 只作为降级。", "Reads BTC, ETH, DOGE, SOL, ZEC, and XRP public chain APIs by default; local CSV is fallback only."), _onchain_overview_content(onchain_events, onchain_sources, active_lang), wide=True),
                _terminal_panel(t("链上风控阻断", "On-chain Risk Blocks"), t("高严重度交易所流入会阻断自动开仓。", "High-severity exchange inflows block automated entries."), _terminal_rows([{"symbol": symbol, "reason": reason} for symbol, reason in dict(risk["blocked_symbols"]).items()], [(t("标的", "Symbol"), "symbol"), (t("原因", "Reason"), "reason")], lang=active_lang), wide=True),
            ]
        )
    elif module == "basis":
        carry_config = carry_paper.get("config") if isinstance(carry_paper.get("config"), dict) else {}
        carry_metrics = carry_paper.get("metrics") if isinstance(carry_paper.get("metrics"), dict) else {}
        carry_positions = carry_paper.get("open_positions") if isinstance(carry_paper.get("open_positions"), list) else []
        carry_events = carry_paper.get("recent_events") if isinstance(carry_paper.get("recent_events"), list) else []
        carry_command = f"""
          <div class="terminal-action-grid">
            <form method="post" action="{_url('/terminal/basis/carry/run', active_lang)}" class="inline-form">
              {_hidden_lang_input(active_lang)}
              <button type="submit">{t("运行 Carry 模拟轮询", "Run Carry Paper Cycle")}</button>
            </form>
            <a class="action-link" href="{escape(_url('/settings#settings-llm', active_lang), quote=True)}">{t("配置开仓与退出阈值", "Configure Entry and Exit Rules")}</a>
            <a class="action-link" href="{escape(_url('/api/research/carry/paper/status', active_lang), quote=True)}">{t("查看 JSON", "View JSON")}</a>
          </div>
          <div class="mini-stat-grid compact-grid trading-risk-grid">
            <div class="mini-stat"><span>{t("新开仓开关", "New Entries")}</span><strong>{t("已开启", "Enabled") if carry_paper.get("enabled") else t("已关闭", "Disabled")}</strong></div>
            <div class="mini-stat"><span>{t("模拟持仓", "Paper Positions")}</span><strong>{int(carry_metrics.get("open_positions") or 0)}</strong></div>
            <div class="mini-stat"><span>{t("总敞口", "Gross Exposure")}</span><strong>{float(carry_metrics.get("gross_exposure") or 0):.2f}</strong></div>
            <div class="mini-stat"><span>{t("累计已实现", "Realized PnL")}</span><strong>{float(carry_metrics.get("realized_pnl") or 0):+.4f}</strong></div>
            <div class="mini-stat"><span>{t("最小基差", "Min Basis")}</span><strong>{float(carry_config.get("min_basis_bps") or 0):.1f} bps</strong></div>
            <div class="mini-stat"><span>{t("最小资金费率", "Min Funding")}</span><strong>{float(carry_config.get("min_funding_bps") or 0):.1f} bps/8h</strong></div>
          </div>
          {f'<div class="notice notice-success">{escape(message)}</div>' if message else ""}
          <p class="helper-text">{t("严格限定为本地双腿模拟：现货做多 + 永续做空，不调用 Binance/OKX 下单接口。", "Strictly local two-leg simulation: long spot plus short perpetual, with no Binance/OKX order calls.")}</p>
        """
        panels = "".join(
            [
                notice_html,
                _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("用于套利、对冲、资金费率观察和异常价差阻断。", "Used for arbitrage, hedging, funding-rate monitoring, and basis anomaly blocks."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("现货价格", "Spot Price"), "spot_price"), (t("合约", "Futures"), "futures_exchange"), (t("合约价格", "Futures Price"), "futures_price"), ("Spread bps", "spread_bps"), (t("方向", "Direction"), "direction")], lang=active_lang), wide=True),
                _terminal_panel(t("合约资金费率", "Futures Funding"), t("极端正费率会参与执行前阻断，负费率可作为暴跌反弹的空头拥挤确认。", "Extreme positive funding feeds pre-trade blocks; negative funding confirms short-crowding rebounds."), _terminal_rows(funding_rates, [(t("标的", "Symbol"), "symbol"), (t("合约", "Futures"), "futures_exchange"), ("Funding bps", "funding_rate_bps"), ("Annualized %", "annualized_pct"), (t("来源", "Source"), "source")], lang=active_lang), wide=True),
                _terminal_panel(t("Carry 双腿模拟", "Carry Two-leg Paper Engine"), t("基差收敛、资金费率、双腿手续费和滑点统一计入净收益。", "Basis convergence, funding, two-leg fees, and slippage are included in net PnL."), carry_command + _terminal_rows(carry_positions, [(t("标的", "Symbol"), "symbol"), (t("开仓基差", "Entry Basis"), "entry_basis_bps"), (t("当前基差", "Current Basis"), "last_basis_bps"), (t("资金费率", "Funding"), "last_funding_rate_bps"), (t("资金收益", "Funding PnL"), "funding_pnl"), (t("净收益", "Net PnL"), "net_pnl"), (t("持有小时", "Held Hours"), "held_hours")], lang=active_lang), wide=True),
                _terminal_panel(t("Carry 模拟事件", "Carry Paper Events"), t("仅记录本地模拟开仓和平仓，不会混入自动交易真实订单日志。", "Local paper opens and closes only; real auto-trading order logs are kept separate."), _terminal_rows(carry_events, [(t("时间", "Time"), "created_at"), (t("动作", "Action"), "action"), (t("标的", "Symbol"), "symbol"), (t("状态", "Status"), "status"), (t("退出原因", "Exit Reason"), "exit_reason"), (t("已实现盈亏", "Realized PnL"), "realized_pnl")], lang=active_lang), wide=True),
                _terminal_panel(t("价差执行提示", "Basis Execution Notes"), t("极端 basis 不直接下单，会进入风控复核。", "Extreme basis does not trigger direct orders; it goes to risk review."), _terminal_rows(platform["risk_rules"], [(t("规则", "Rule"), "name"), (t("状态", "Status"), "status"), (t("阈值", "Threshold"), "threshold"), (t("动作", "Action"), "action")], lang=active_lang), wide=True),
            ]
        )
    elif module == "strategies":
        panels = "".join(
            [
                _terminal_panel(
                    t("参数预设与策略模板", "Parameter Presets & Strategy Templates"),
                    t("按风险、周期和市场状态选择模板，再进入回测或生成受限 paper 参数。", "Select by risk, interval, and market regime, then backtest or compile restricted paper parameters."),
                    _strategy_templates_panel(strategy_templates, active_lang),
                    wide=True,
                ),
                _terminal_panel(
                    t("自然语言策略编译器", "Natural-language Strategy Compiler"),
                    t("把策略描述拆解为回测参数和 paper 执行参数。", "Compile a strategy description into backtest and paper execution parameters."),
                    _strategy_builder_panel(
                        result=strategy_builder_result,
                        text=strategy_builder_text,
                        message=message,
                        error=error,
                        lang=active_lang,
                    ),
                    wide=True,
                ),
                _terminal_panel(
                    t("配对 / 统计套利回测", "Pair / Statistical Arbitrage Backtest"),
                    t("使用两组同周期本地 K 线完成滚动对冲与均值回归研究。", "Run rolling hedge and mean-reversion research on two aligned local K-line series."),
                    _stat_arb_backtest_panel(
                        result=stat_arb_result,
                        params=stat_arb_params,
                        message=stat_arb_message,
                        error=stat_arb_error,
                        lang=active_lang,
                    ),
                    wide=True,
                ),
                _terminal_panel(t("策略命中", "Strategy Hits"), t("自动交易前的候选池、资金费率、价差和执行意图。", "Candidate pool, funding, basis, and execution intent before automated trading."), _terminal_rows(strategy_hits, _strategy_hit_columns(active_lang), lang=active_lang), wide=True),
                _terminal_panel(t("策略目录", "Strategy Catalog"), t("已实现策略、触发条件、执行方式和风控依赖。", "Implemented strategies, triggers, execution methods, and risk dependencies."), _terminal_rows(platform["strategies"], [("ID", "strategy_id"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("触发条件", "Trigger"), "trigger"), (t("执行方式", "Execution"), "execution"), (t("风控", "Risk"), "risk_controls")], lang=active_lang), wide=True),
            ]
        )
    elif module == "trading":
        config = trading_status["config"]
        readiness = trading_status.get("readiness", {}) if isinstance(trading_status, dict) else {}
        exchange_status = readiness.get("exchange_status") if isinstance(readiness, dict) and isinstance(readiness.get("exchange_status"), dict) else {}
        positions = trading_status["open_positions"]
        events = trading_status["events"]
        account_metrics = trading_status.get("account_metrics") if isinstance(trading_status.get("account_metrics"), dict) else {}
        btc_trading = trading_status.get("btc_trading") if isinstance(trading_status.get("btc_trading"), dict) else {}
        event_summary = trading_status.get("event_summary") if isinstance(trading_status.get("event_summary"), dict) else {}
        event_summary_text = (
            t(
                f"当前展示 {int(_float_from_any(event_summary.get('returned_events')))} / 本地保留 {int(_float_from_any(event_summary.get('total_events')))} 条；成交 {int(_float_from_any(event_summary.get('filled_events')))} 条，诊断/预警 {int(_float_from_any(event_summary.get('diagnostic_events')))} 条。",
                f"Showing {int(_float_from_any(event_summary.get('returned_events')))} / {int(_float_from_any(event_summary.get('total_events')))} local events; {int(_float_from_any(event_summary.get('filled_events')))} fills and {int(_float_from_any(event_summary.get('diagnostic_events')))} diagnostic/warning events.",
            )
            if event_summary
            else ""
        )
        event_summary_html = (
            f'<p class="helper-text">{escape(event_summary_text)}</p>'
            if event_summary
            else ""
        )
        auto_status = paper_auto_status or {}
        auto_running = bool(auto_status.get("running"))
        auto_error = str(auto_status.get("last_error") or "")
        auto_force_paper = bool(auto_status.get("force_paper", True))
        auto_mode_text = (
            t("强制模拟", "Forced paper")
            if auto_force_paper
            else t("按配置：模拟/实盘", "Configured: paper/live")
        )
        auto_status_notice = f'<div class="notice notice-error">{escape(auto_error)}</div>' if auto_error else ""
        command = f"""
          <form method="post" action="{_url('/terminal/trading/run', active_lang)}" class="ant-form trading-command terminal-action-form">
            {_hidden_lang_input(active_lang)}
            <div>
              <h2>{t("模拟账户执行", "Paper Account Execution")}</h2>
              <p class="helper-text">{t("使用当前策略信号源和执行前风控，强制以 paper 模式运行一次。不会提交真实订单。", "Run the current strategy signal source and pre-trade risk gate once in forced paper mode. No live order will be submitted.")}</p>
            </div>
            <button type="submit">{t("运行模拟量化交易", "Run Paper Quant Trade")}</button>
          </form>
	          <div class="ant-card nested-panel auto-trading-panel">
	            <div class="section-heading compact-heading">
	              <h3>{t("策略信号自动交易", "Strategy Signal Auto Trading")}</h3>
	              <p>{t("按固定间隔自动扫描策略信号，并按当前 Auto Trade 开关执行。若同时开启模拟和实盘，且关闭订单预检/test，会在同一轮同时记录模拟单并提交真实订单。", "Automatically scan strategy signals on an interval and execute using current Auto Trade switches. If paper and live are both enabled and order precheck/test is disabled, the same run records paper fills and submits live orders.")}</p>
	            </div>
            <div class="terminal-action-grid">
              <form method="post" action="{_url('/terminal/trading/auto/start', active_lang)}" class="inline-form">
                {_hidden_lang_input(active_lang)}
                <label>
                  <span>{t("轮询间隔秒", "Interval seconds")}</span>
                  <input name="interval_seconds" type="number" min="30" step="30" value="{int(auto_status.get("interval_seconds") or 300)}" />
                </label>
                <button type="submit">{t("启动自动策略交易", "Start Auto Strategy Trading")}</button>
              </form>
              <form method="post" action="{_url('/terminal/trading/auto/stop', active_lang)}" class="inline-form">
                {_hidden_lang_input(active_lang)}
                <button type="submit" class="button-secondary">{t("停止自动策略交易", "Stop Auto Strategy Trading")}</button>
              </form>
            </div>
	            <div class="mini-stat-grid compact-grid trading-risk-grid">
	              <div class="mini-stat"><span>{t("自动循环", "Auto Loop")}</span><strong>{t("运行中", "Running") if auto_running else t("已停止", "Stopped")}</strong></div>
	              <div class="mini-stat"><span>{t("轮询模式", "Loop Mode")}</span><strong>{escape(auto_mode_text)}</strong></div>
	              <div class="mini-stat"><span>{t("运行次数", "Runs")}</span><strong>{int(auto_status.get("run_count") or 0)}</strong></div>
              <div class="mini-stat"><span>{t("最近运行", "Last Run")}</span><strong>{escape(_display_value(auto_status.get("last_run_at") or "-", active_lang))}</strong></div>
              <div class="mini-stat"><span>{t("最近错误", "Last Error")}</span><strong>{escape(auto_error or "-")}</strong></div>
            </div>
            {auto_status_notice}
          </div>
          <div class="mini-stat-grid compact-grid trading-risk-grid">
            <div class="mini-stat"><span>{t("模式", "Mode")}</span><strong>{escape(_display_value(config.get("mode", "paper"), active_lang))}</strong></div>
            <div class="mini-stat"><span>{t("启用", "Enabled")}</span><strong>{escape(_display_value(config.get("enabled", ""), active_lang))}</strong></div>
            <div class="mini-stat"><span>{t("评分阈值", "Score")}</span><strong>{float(config.get("score_threshold", 0) or 0):.1f}</strong></div>
            <div class="mini-stat"><span>Order Qty</span><strong>{float(config.get("quote_order_qty", 0) or 0):.2f}</strong></div>
            <div class="mini-stat"><span>{t("授权", "Auth")}</span><strong>{escape(_display_value(exchange_status.get("status", "not_configured"), active_lang))}</strong></div>
            <div class="mini-stat"><span>{t("实盘就绪", "Live Ready")}</span><strong>{t("是", "Yes") if readiness.get("live_ready") else t("否", "No")}</strong></div>
          </div>
          {_trading_account_metric_cards(account_metrics, active_lang)}
          {f'<div class="notice notice-success">{escape(message)}</div>' if message else ""}
        """
        panels = "".join(
            [
                _terminal_panel(t("模拟账户执行", "Paper Account Execution"), t("用策略信号源完成一轮 paper 自动交易。", "Complete one paper auto-trading run from the strategy signal source."), command, wide=True),
                _terminal_panel(t("BTC交易专区", "BTC Trading Zone"), t("BTC 专属信号、模拟账户 BTC 成交统计和执行建议。", "BTC-specific signal, paper BTC metrics, and execution plan."), _btc_trading_zone(btc_trading, active_lang), wide=True),
                _terminal_panel(t("账户表现", "Account Performance"), t("成交、执行事件、持仓敞口、盈亏比、胜率和已实现盈亏。", "Fills, execution events, exposure, P/L ratio, win rate, and realized PnL."), _terminal_rows(platform["accounts"], [(t("交易所", "Exchange"), "exchange"), (t("模式", "Mode"), "mode"), (t("持仓", "Positions"), "open_positions"), (t("敞口", "Exposure"), "quote_exposure"), (t("执行事件", "Events"), "event_count"), (t("累计成交", "Fills"), "total_trades"), (t("平仓数", "Closed"), "closed_trades"), (t("胜率", "Win Rate"), "win_rate_pct"), (t("盈亏比", "P/L Ratio"), "profit_loss_ratio"), ("Profit Factor", "profit_factor"), (t("已实现盈亏", "Realized PnL"), "realized_pnl")], lang=active_lang), wide=True),
                _terminal_panel(t("持仓状态", "Position State"), t("本地模拟账户持仓。", "Local paper account positions."), _trading_position_rows(positions, active_lang), wide=True),
                _terminal_panel(t("交易日志", "Trading Logs"), t("自动交易执行、跳过、阻断和下单事件；成交事件优先保留。", "Automated trading execution, skip, block, and order events; filled trades are retained first."), event_summary_html + _trading_event_rows(events, active_lang), wide=True),
            ]
        )
    else:
        panels = "".join(
            [
                _terminal_panel(
                    t("执行前风控", "Pre-trade Risk Gate"),
                    str(risk["summary"]),
                    _risk_gate_content(risk, active_lang),
                    wide=True,
                ),
                _terminal_panel(t("风险规则", "Risk Rules"), t("执行层硬性约束和保护条件。", "Hard execution constraints and guardrails."), _terminal_rows(platform["risk_rules"], [(t("规则", "Rule"), "name"), (t("状态", "Status"), "status"), (t("阈值", "Threshold"), "threshold"), (t("动作", "Action"), "action")], lang=active_lang), wide=True),
            ]
        )

    hero_right = f"""
      {_terminal_card(t("扫描标的", "Scanned Symbols"), str(int(snapshot["scanned_symbols"])), t("信号源", "signal source"), "cyan")}
      {_terminal_card(t("策略命中", "Strategy Hits"), str(len(strategy_hits)), t("含资金费率", "with funding"), "green")}
      {_terminal_card(t("执行风控", "Execution Risk"), _display_value(risk["status"], active_lang).upper(), f'{t("风险分", "risk")} {float(risk["risk_score"]):.1f}', "amber")}
    """
    return _layout(
        page_title=f"AI Trade {title}",
        active_page="terminal",
        hero_title=title,
        hero_text=subtitle,
        hero_right=hero_right,
        content=_terminal_shell(module, panels, active_lang),
        lang=active_lang,
        current_path=f"/terminal/{module}",
        layout_context=layout_context,
    )


__all__ = [
    '_terminal_card',
    '_strategy_hit_columns',
    '_risk_gate_content',
    '_llm_analysis_content',
    '_onchain_overview_content',
    '_terminal_system_layers',
    '_terminal_dashboard_value',
    '_terminal_status_chip',
    '_terminal_sparkline',
    '_terminal_dashboard_table',
    '_terminal_today_realized_pnl',
    '_terminal_closed_win_rate',
    '_terminal_market_intel_content',
    '_terminal_dashboard_feature_cards',
    '_terminal_dashboard_showcase',
    '_terminal_panel',
    '_terminal_shell',
    'render_terminal_page',
    'render_terminal_module_page',
]
