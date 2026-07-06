from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from .presets import get_backtest_preset
from .views_common import _backtest_preset_options, _hidden_lang_input, _layout, _module_tabs, _option, _text, normalize_language


def _stats_table(rows: list[dict[str, object]], *, portfolio: bool = False) -> str:
    header = """
      <tr>
        <th>Horizon</th>
        <th>Avg</th>
        <th>Median</th>
        <th>Win</th>
        <th>Best</th>
        <th>Worst</th>
      </tr>
    """
    body = []
    for row in rows:
        avg_key = "avg_batch_return_pct" if portfolio else "avg_return_pct"
        best_key = "best_batch_return_pct" if portfolio else "best_return_pct"
        worst_key = "worst_batch_return_pct" if portfolio else "worst_return_pct"
        body.append(
            f"""
            <tr>
              <td>{int(row["horizon_bars"])}</td>
              <td>{float(row[avg_key]):+.2f}%</td>
              <td>{float(row["median_batch_return_pct"] if portfolio else row["median_return_pct"]):+.2f}%</td>
              <td>{float(row["win_rate_pct"]):.1f}%</td>
              <td>{float(row[best_key]):+.2f}%</td>
              <td>{float(row[worst_key]):+.2f}%</td>
            </tr>
            """
        )
    return f'<table class="ant-table data-table">{header}<tbody>{"".join(body)}</tbody></table>'


def _trade_pills(trade_stat: dict[str, object] | None, final_equity: float, max_drawdown_pct: float) -> str:
    if trade_stat is None:
        return ""
    pills = [
        ("Trades", f'{int(trade_stat["trade_count"])}'),
        ("Avg Return", f'{float(trade_stat["avg_return_pct"]):+.2f}%'),
        ("Win Rate", f'{float(trade_stat["win_rate_pct"]):.1f}%'),
        ("Profit Factor", f'{float(trade_stat["profit_factor"]):.2f}'),
        ("Final Equity", f"{final_equity:.3f}"),
        ("Max DD", f"{max_drawdown_pct:+.2f}%"),
    ]
    return "".join(
        f'<div class="mini-stat"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in pills
    )


def _fee_meta(report: dict[str, object]) -> str:
    source = f'[{escape(str(report["fee_source"]))}] '
    if report["fee_model"] == "maker_taker":
        discount = ""
        if float(report["fee_discount_pct"]) > 0:
            discount = f' · discount {float(report["fee_discount_pct"]):.1f}%'
        return (
            f'{source}Maker/Taker {float(report["maker_fee_bps"]):.2f}/{float(report["taker_fee_bps"]):.2f}bps'
            f' · entry {escape(str(report["entry_fee_role"]))}'
            f' · exit {escape(str(report["exit_fee_role"]))}{discount}'
        )
    discount = ""
    if float(report["fee_discount_pct"]) > 0:
        discount = f' · discount {float(report["fee_discount_pct"]):.1f}%'
    return f'{source}Flat fee {float(report["fee_bps"]):.2f}bps{discount}'


def _event_rows(events: list[dict[str, object]]) -> str:
    rows = []
    for event in events:
        reasons = ", ".join(str(reason) for reason in event["reasons"])
        rows.append(
            f"""
            <tr>
              <td>{escape(str(event["entry_time"]))}</td>
              <td>{float(event["score"]):.2f}</td>
              <td>{escape(str(event["grade"]))}</td>
              <td>{escape(str(event["exit_reason"]))}</td>
              <td>{float(event["entry_fee_bps"] or 0.0):.2f}/{float(event["exit_fee_bps"] or 0.0):.2f}bps</td>
              <td>{float(event["gross_return_pct"] or 0.0):+.2f}%</td>
              <td>{float(event["realized_return_pct"] or 0.0):+.2f}%</td>
              <td>{float(event["effective_slippage_bps"] or 0.0):.2f}bps</td>
              <td>{escape(reasons)}</td>
            </tr>
            """
        )
    if not rows:
        return '<p class="helper-text">当前参数下没有触发任何交易。</p>'
    return f"""
      <table class="ant-table data-table">
        <tr>
          <th>Entry Time</th>
          <th>Score</th>
          <th>Grade</th>
          <th>Exit</th>
          <th>Fee</th>
          <th>Gross</th>
          <th>Net</th>
          <th>Slip</th>
          <th>Reasons</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _selection_rows(selections: list[dict[str, object]]) -> str:
    rows = []
    for selection in selections:
        picks = ", ".join(
            f'{pick["symbol"]}:{pick["grade"]}/{float(pick["score"]):.1f}'
            for pick in selection["picks"]
        )
        rows.append(
            f"""
            <tr>
              <td>{escape(str(selection["entry_time"]))}</td>
              <td>{escape(picks)}</td>
              <td>{float(selection["capital_fraction_pct"]):.1f}%</td>
              <td>{float(selection["gross_return_pct"] or 0.0):+.2f}%</td>
              <td>{float(selection["realized_return_pct"] or 0.0):+.2f}%</td>
            </tr>
            """
        )
    if not rows:
        return '<p class="helper-text">当前没有组合批次结果。</p>'
    return f"""
      <table class="ant-table data-table">
        <tr>
          <th>Entry Time</th>
          <th>Picks</th>
          <th>Alloc</th>
          <th>Gross</th>
          <th>Net</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _serialize_query_value(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _build_backtest_export_query(params: dict[str, object]) -> str:
    return urlencode({key: _serialize_query_value(value) for key, value in params.items()})


def _summary_bars(items: list[dict[str, object]], *, label_key: str) -> str:
    if not items:
        return '<p class="helper-text">当前没有可绘制的权益结果。</p>'

    max_equity = max(float(item["final_equity"]) for item in items) or 1.0
    bars = []
    for item in items[:10]:
        final_equity = float(item["final_equity"])
        max_drawdown_pct = float(item["max_drawdown_pct"])
        width_pct = max(8.0, (final_equity / max_equity) * 100)
        bars.append(
            f"""
            <div class="summary-bar-row">
              <div class="summary-bar-label">
                <strong>{escape(str(item[label_key]))}</strong>
                <span>Equity {final_equity:.3f} · Max DD {max_drawdown_pct:+.2f}%</span>
              </div>
              <div class="summary-bar-track">
                <i style="width: {width_pct:.2f}%"></i>
              </div>
            </div>
            """
        )
    return "".join(bars)


def _curve_values(values: object) -> list[float]:
    if isinstance(values, list):
        parsed = [float(value) for value in values if isinstance(value, int | float)]
        if parsed:
            return parsed
    return []


def _has_chartable_curve(values: list[float]) -> bool:
    return len(values) >= 2


def _benchmark_line_points(values: list[float], *, minimum: float, maximum: float, width: int = 860, height: int = 340) -> str:
    if len(values) < 2:
        values = [values[0] if values else 1.0, values[0] if values else 1.0]
    span = maximum - minimum or 1.0
    step = width / (len(values) - 1)
    points = []
    for index, value in enumerate(values):
        x = index * step
        y = height - (((value - minimum) / span) * height)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def _money_from_equity(equity: float, capital: float = 10_000.0) -> str:
    return f"${equity * capital:,.2f}"


def _return_from_equity(equity: float) -> str:
    return f"{((equity - 1.0) * 100):+.2f}%"


def _analysis_quality_label(final_equity: float, max_drawdown_pct: float, trade_count: int) -> tuple[str, str]:
    if trade_count <= 0:
        return "样本不足", "neutral"
    if final_equity > 1.15 and max_drawdown_pct > -12.0:
        return "表现强", "positive"
    if final_equity > 1.0 and max_drawdown_pct > -20.0:
        return "可观察", "warning"
    return "需复核", "negative"


def _backtest_result_rows(
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for report in series_reports:
        trade_stat = report.get("trade_stat") if isinstance(report.get("trade_stat"), dict) else {}
        final_equity = float(report.get("final_equity", 1.0))
        max_drawdown_pct = float(report.get("max_drawdown_pct", 0.0))
        trade_count = int(trade_stat.get("trade_count", report.get("signal_count", 0))) if isinstance(trade_stat, dict) else int(report.get("signal_count", 0))
        quality, tone = _analysis_quality_label(final_equity, max_drawdown_pct, trade_count)
        rows.append(
            {
                "kind": "单币种",
                "label": str(report.get("symbol", "")),
                "interval": str(report.get("interval", "")),
                "final_equity": final_equity,
                "return_pct": (final_equity - 1.0) * 100,
                "max_drawdown_pct": max_drawdown_pct,
                "trade_count": trade_count,
                "win_rate_pct": float(trade_stat.get("win_rate_pct", 0.0)) if isinstance(trade_stat, dict) else 0.0,
                "profit_factor": float(trade_stat.get("profit_factor", 0.0)) if isinstance(trade_stat, dict) else 0.0,
                "quality": quality,
                "tone": tone,
            }
        )
    for report in portfolio_reports:
        trade_stat = report.get("trade_stat") if isinstance(report.get("trade_stat"), dict) else {}
        final_equity = float(report.get("final_equity", 1.0))
        max_drawdown_pct = float(report.get("max_drawdown_pct", 0.0))
        trade_count = int(trade_stat.get("trade_count", report.get("batch_count", 0))) if isinstance(trade_stat, dict) else int(report.get("batch_count", 0))
        quality, tone = _analysis_quality_label(final_equity, max_drawdown_pct, trade_count)
        rows.append(
            {
                "kind": "组合",
                "label": f"Top {int(report.get('top_n', 0))}",
                "interval": str(report.get("interval", "")),
                "final_equity": final_equity,
                "return_pct": (final_equity - 1.0) * 100,
                "max_drawdown_pct": max_drawdown_pct,
                "trade_count": trade_count,
                "win_rate_pct": float(trade_stat.get("win_rate_pct", 0.0)) if isinstance(trade_stat, dict) else 0.0,
                "profit_factor": float(trade_stat.get("profit_factor", 0.0)) if isinstance(trade_stat, dict) else 0.0,
                "quality": quality,
                "tone": tone,
            }
        )
    return sorted(rows, key=lambda item: float(item["final_equity"]), reverse=True)


def _backtest_visual_analysis(
    *,
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
    rebalance_reports: list[dict[str, object]],
    strategy_explanation: dict[str, object] | None = None,
) -> str:
    rows = _backtest_result_rows(series_reports, portfolio_reports)
    diagnostics = []
    if isinstance(strategy_explanation, dict) and isinstance(strategy_explanation.get("diagnostics"), list):
        diagnostics = [str(item) for item in strategy_explanation["diagnostics"][:4]]
    if not rows:
        return """
          <section id="backtest-analysis" class="backtest-analysis-board empty backtest-compact-section">
            <div class="section-heading">
              <h2>结果分析看板</h2>
              <p>运行回测后会在这里展示收益、回撤、胜率、基准差值和组合稳定性。</p>
            </div>
            <div class="backtest-empty-strip">
              <article class="ant-empty-state empty-state compact backtest-empty-card">
                <span class="empty-state-icon">01</span>
                <div>
                  <h2>等待历史 K 线</h2>
                  <p>填入 Binance ZIP 或使用 TradingView 拉取 CSV 后，页面会自动生成收益、回撤、胜率和基准差值。</p>
                  <div class="empty-hints"><span>Archive Pattern</span><span>TradingView CSV</span><span>Run Backtest</span></div>
                </div>
              </article>
              <article class="ant-empty-state empty-state compact backtest-empty-card muted">
                <span class="empty-state-icon">02</span>
                <div>
                  <h2>分析维度已就绪</h2>
                  <p>看板会把单币种、组合、再平衡结果压缩成同一套矩阵，避免只看导出文件。</p>
                  <div class="empty-hints"><span>Equity</span><span>Drawdown</span><span>Win Rate</span></div>
                </div>
              </article>
            </div>
          </section>
        """

    best = rows[0]
    best_series = max(series_reports, key=lambda item: float(item.get("final_equity", 0.0)), default=None)
    best_portfolio = max(portfolio_reports, key=lambda item: float(item.get("final_equity", 0.0)), default=None)
    best_rebalance = max(rebalance_reports, key=lambda item: float(item.get("premium_pct", -999.0)), default=None)
    total_trades = sum(int(item["trade_count"]) for item in rows)
    avg_win_rate = sum(float(item["win_rate_pct"]) for item in rows if int(item["trade_count"]) > 0) / max(sum(1 for item in rows if int(item["trade_count"]) > 0), 1)
    avg_profit_factor = sum(float(item["profit_factor"]) for item in rows if float(item["profit_factor"]) > 0) / max(sum(1 for item in rows if float(item["profit_factor"]) > 0), 1)
    max_return = max(abs(float(item["return_pct"])) for item in rows) or 1.0
    max_drawdown = max(abs(float(item["max_drawdown_pct"])) for item in rows) or 1.0
    positive_count = sum(1 for item in rows if float(item["final_equity"]) > 1.0)
    sample_label = "样本偏少" if total_trades < 20 else "样本可用"
    sample_tone = "warning" if total_trades < 20 else "positive"
    hold_delta = 0.0
    hold_delta_label = "暂无单币种基准"
    if best_series is not None:
        final_equity = float(best_series.get("final_equity", 1.0))
        hold_equity = float(best_series.get("buy_hold_final_equity", 1.0))
        hold_delta = (final_equity - hold_equity) * 100
        hold_delta_label = f"{best_series.get('symbol', '')} 策略 vs 持有"
    if not diagnostics:
        diagnostics = [
            f"共 {len(rows)} 组结果，其中 {positive_count} 组最终权益高于 1.0。",
            "先用收益/回撤矩阵筛掉高回撤低收益组合，再看交易样本数。",
            "Profit Factor 和胜率需要结合交易数判断，少样本不宜直接上线。",
        ]
    portfolio_equity = float(best_portfolio.get("final_equity", 0.0)) if best_portfolio else 0.0
    portfolio_label = str(best_portfolio.get("interval", "")) if best_portfolio else "暂无组合结果"
    rebalance_premium = float(best_rebalance.get("premium_pct", 0.0)) if best_rebalance else 0.0
    rebalance_label = str(best_rebalance.get("interval", "")) if best_rebalance else "暂无再平衡结果"
    best_tone = "good" if float(best["final_equity"]) >= 1.0 else "warning"
    sample_card_tone = "warning" if total_trades < 20 else "good"
    hold_card_tone = "good" if hold_delta >= 0 else "warning"
    portfolio_card_tone = "good" if portfolio_equity >= 1.0 else "warning"
    rebalance_card_tone = "good" if rebalance_premium >= 0 else "warning"

    matrix_rows = []
    for item in rows[:8]:
        return_width = min(100.0, max(4.0, abs(float(item["return_pct"])) / max_return * 100))
        drawdown_width = min(100.0, max(4.0, abs(float(item["max_drawdown_pct"])) / max_drawdown * 100))
        return_tone = "positive" if float(item["return_pct"]) >= 0 else "negative"
        matrix_rows.append(
            f"""
            <div class="analysis-matrix-row">
              <div class="analysis-result-name">
                <strong>{escape(str(item["label"]))}</strong>
                <span>{escape(str(item["kind"]))} · {escape(str(item["interval"]))} · {int(item["trade_count"])} 次</span>
              </div>
              <div class="analysis-bar-stack">
                <div class="analysis-bar-line">
                  <span>收益 {_return_from_equity(float(item["final_equity"]))}</span>
                  <i class="{return_tone}" style="width: {return_width:.2f}%"></i>
                </div>
                <div class="analysis-bar-line drawdown">
                  <span>回撤 {float(item["max_drawdown_pct"]):+.2f}%</span>
                  <i style="width: {drawdown_width:.2f}%"></i>
                </div>
              </div>
              <div class="analysis-quality">
                <strong>{float(item["win_rate_pct"]):.1f}%</strong>
                <span class="analysis-tag {escape(str(item['tone']))}">{escape(str(item["quality"]))}</span>
              </div>
            </div>
            """
        )

    diagnostic_items = "".join(f"<li>{escape(item)}</li>" for item in diagnostics)
    return f"""
      <section id="backtest-analysis" class="backtest-analysis-board backtest-compact-section">
        <div class="section-heading">
          <h2>结果分析看板</h2>
          <p>把导出数据中的关键结论直接转成可视化判断：收益、回撤、胜率、样本量和基准差值。</p>
        </div>
        <div class="analysis-summary-grid">
          <article class="analysis-spotlight metric-card {best_tone}">
            <span>最佳结果</span>
            <strong>{escape(str(best["label"]))}</strong>
            <small>{escape(str(best["kind"]))} · Equity {float(best["final_equity"]):.3f} · {_return_from_equity(float(best["final_equity"]))}</small>
          </article>
          <article class="analysis-metric-card metric-card">
            <span>胜率均值</span>
            <strong>{avg_win_rate:.1f}%</strong>
            <small>PF {avg_profit_factor:.2f}</small>
          </article>
          <article class="analysis-metric-card metric-card {sample_card_tone}">
            <span>交易样本</span>
            <strong>{total_trades}</strong>
            <small><em class="{sample_tone}">{sample_label}</em></small>
          </article>
          <article class="analysis-metric-card metric-card {hold_card_tone}">
            <span>策略基准差</span>
            <strong>{hold_delta:+.2f}%</strong>
            <small>{escape(hold_delta_label)}</small>
          </article>
          <article class="analysis-metric-card metric-card {portfolio_card_tone}">
            <span>最佳组合</span>
            <strong>{portfolio_equity:.3f}</strong>
            <small>{escape(portfolio_label)}</small>
          </article>
          <article class="analysis-metric-card metric-card {rebalance_card_tone}">
            <span>再平衡溢价</span>
            <strong>{rebalance_premium:+.2f}%</strong>
            <small>{escape(rebalance_label)}</small>
          </article>
        </div>
        <div class="analysis-grid">
          <article class="analysis-panel matrix-panel">
            <div class="analysis-panel-head">
              <h3>收益 / 回撤矩阵</h3>
              <p>绿色为净收益表现，红色为负收益，灰色为最大回撤占比。</p>
            </div>
            <div class="analysis-matrix">{"".join(matrix_rows)}</div>
          </article>
          <article class="analysis-panel">
            <div class="analysis-panel-head">
              <h3>诊断提示</h3>
              <p>把结果转成下一步参数决策。</p>
            </div>
            <ul class="analysis-insight-list">{diagnostic_items}</ul>
          </article>
        </div>
      </section>
    """


def _benchmark_trade_feed(report: dict[str, object], *, capital: float = 10_000.0) -> str:
    events = report.get("events", [])
    if not isinstance(events, list) or not events:
        return '<p class="helper-text">当前回测没有已完成交易。</p>'
    order_capital = capital * (float(report.get("capital_fraction_pct", 100.0)) / 100)
    cards = []
    for event in reversed(events[-8:]):
        realized_return = float(event.get("realized_return_pct") or 0.0)
        pnl = order_capital * (realized_return / 100)
        pnl_class = "positive" if pnl >= 0 else "negative"
        cards.append(
            f"""
            <article class="benchmark-trade-card">
              <div class="benchmark-trade-head">
                <strong>策略完成一笔 <span>LONG</span> 交易，标的为 {escape(str(report.get("symbol", "")))}</strong>
                <time>{escape(str(event.get("exit_time") or event.get("entry_time") or ""))[:16]}</time>
              </div>
              <dl>
                <div><dt>价格</dt><dd>{float(event.get("entry_price") or 0.0):,.6g} -> {float(event.get("exit_price") or 0.0):,.6g}</dd></div>
                <div><dt>持仓</dt><dd>{int(event.get("bars_held") or 0)} bars</dd></div>
                <div><dt>退出</dt><dd>{escape(str(event.get("exit_reason") or ""))}</dd></div>
                <div><dt>净盈亏</dt><dd class="{pnl_class}">{pnl:+,.2f} ({realized_return:+.2f}%)</dd></div>
              </dl>
            </article>
            """
        )
    return "".join(cards)


def _benchmark_ai_notes(report: dict[str, object]) -> str:
    trade_stat = report.get("trade_stat") if isinstance(report.get("trade_stat"), dict) else {}
    final_equity = float(report.get("final_equity", 1.0))
    hold_equity = float(report.get("buy_hold_final_equity", 1.0))
    delta_pct = (final_equity - hold_equity) * 100
    win_rate = float(trade_stat.get("win_rate_pct", 0.0)) if isinstance(trade_stat, dict) else 0.0
    profit_factor = float(trade_stat.get("profit_factor", 0.0)) if isinstance(trade_stat, dict) else 0.0
    notes = [
        f"策略相对买入持有基准差值 {delta_pct:+.2f} 个权益点。",
        f"最近统计胜率 {win_rate:.1f}%，Profit Factor {profit_factor:.2f}。",
        "若交易数偏少，应先扩大样本或降低筛选阈值再比较。",
    ]
    return '<ul class="benchmark-note-list">' + "".join(f"<li>{escape(note)}</li>" for note in notes) + "</ul>"


def _benchmark_workbench(series_reports: list[dict[str, object]]) -> str:
    if not series_reports:
        return """
          <section id="backtest-benchmark" class="benchmark-workbench empty backtest-compact-section">
            <article class="ant-empty-state empty-state compact backtest-empty-card">
              <span class="empty-state-icon">B</span>
              <div>
                <h2>基准测试待生成</h2>
                <p>运行单币种回测后，这里会显示策略权益曲线、持有基准和最近交易流水。</p>
                <div class="empty-hints"><span>Strategy Equity</span><span>Buy & Hold</span><span>Trade Feed</span></div>
              </div>
            </article>
          </section>
        """

    ranked = sorted(series_reports, key=lambda item: float(item.get("final_equity", 1.0)), reverse=True)
    active = ranked[0]
    comparison = ranked[1] if len(ranked) > 1 else None
    strategy_values = _curve_values(active.get("equity_points"))
    hold_values = _curve_values(active.get("buy_hold_equity_points"))
    comparison_values = _curve_values(comparison.get("equity_points")) if comparison else []
    can_draw_strategy = _has_chartable_curve(strategy_values)
    can_draw_hold = _has_chartable_curve(hold_values)
    can_draw_comparison = _has_chartable_curve(comparison_values)
    all_values = []
    if can_draw_strategy:
        all_values.extend(strategy_values)
    if can_draw_hold:
        all_values.extend(hold_values)
    if can_draw_comparison:
        all_values.extend(comparison_values)
    final_equity = float(active.get("final_equity", 1.0))
    hold_equity = float(active.get("buy_hold_final_equity", 1.0))
    comparison_equity = float(comparison.get("final_equity", 1.0)) if comparison else None
    strategy_pnl = (final_equity - 1.0) * 10_000
    hold_pnl = (hold_equity - 1.0) * 10_000
    comparison_pnl = ((comparison_equity or 1.0) - 1.0) * 10_000
    if not can_draw_strategy and not can_draw_hold:
        return f"""
          <section id="backtest-benchmark" class="benchmark-workbench empty backtest-compact-section">
            <article class="ant-empty-state empty-state compact backtest-empty-card">
              <span class="empty-state-icon">B</span>
              <div>
                <h2>基准测试曲线不足</h2>
                <p>当前结果只有最终权益，没有真实的逐笔权益曲线。已停止绘制账户总价值图，避免展示伪造走势。</p>
                <div class="empty-hints">
                  <span>{escape(str(active.get("symbol", "")))}</span>
                  <span>Final Equity {final_equity:.3f}</span>
                  <span>Buy/Hold {hold_equity:.3f}</span>
                </div>
              </div>
            </article>
          </section>
        """
    minimum = min(all_values)
    maximum = max(all_values)
    padding = max((maximum - minimum) * 0.08, 0.02)
    minimum -= padding
    maximum += padding
    strategy_line = _benchmark_line_points(strategy_values, minimum=minimum, maximum=maximum) if can_draw_strategy else ""
    hold_line = _benchmark_line_points(hold_values, minimum=minimum, maximum=maximum) if can_draw_hold else ""
    comparison_line = _benchmark_line_points(comparison_values, minimum=minimum, maximum=maximum) if can_draw_comparison else ""
    legend_items = " ".join(
        item
        for item in [
            '<span class="legend-dot strategy"></span> 策略' if strategy_line else "",
            '<span class="legend-dot comparison"></span> V1' if comparison_line else "",
            '<span class="legend-dot hold"></span> 持有基准' if hold_line else "",
        ]
        if item
    )
    hold_line_svg = f'<polyline class="benchmark-line hold" points="{escape(hold_line)}"></polyline>' if hold_line else ""
    comparison_line_svg = f'<polyline class="benchmark-line comparison" points="{escape(comparison_line)}"></polyline>' if comparison_line else ""
    strategy_line_svg = f'<polyline class="benchmark-line strategy" points="{escape(strategy_line)}"></polyline>' if strategy_line else ""
    strategy_label = (
        f"""
        <div class="benchmark-floating-label primary">
          <span>Strategy Returns V2</span>
          <strong>{_money_from_equity(final_equity)}</strong>
          <small>{strategy_pnl:+,.2f} · {_return_from_equity(final_equity)}</small>
        </div>
        """
        if strategy_line
        else ""
    )
    comparison_label = (
        f"""
        <div class="benchmark-floating-label muted">
          <span>Strategy Returns V1</span>
          <strong>{_money_from_equity(comparison_equity or 1.0)}</strong>
          <small>{comparison_pnl:+,.2f} · {_return_from_equity(comparison_equity or 1.0)}</small>
        </div>
        """
        if comparison_line
        else ""
    )
    hold_label = (
        f"""
        <div class="benchmark-floating-label hold-label">
          <span>{escape(str(active.get("symbol", "BTC")))} Holding Returns</span>
          <strong>{_money_from_equity(hold_equity)}</strong>
          <small>{hold_pnl:+,.2f} · {_return_from_equity(hold_equity)}</small>
        </div>
        """
        if hold_line
        else ""
    )

    return f"""
      <section id="backtest-benchmark" class="benchmark-workbench backtest-compact-section">
        <div class="section-heading">
          <div>
            <h2>基准测试</h2>
            <p>对照策略权益、次优策略版本和买入持有基准。</p>
          </div>
          <div class="benchmark-toggle-row">
            <span class="active">{escape(str(active.get("symbol", "")))}</span>
            <span>{escape(str(active.get("interval", "")))}</span>
            <span>72h</span>
          </div>
        </div>
        <div class="benchmark-layout">
          <article class="benchmark-chart-panel">
            <div class="benchmark-chart-head">
              <strong>账户总价值</strong>
              <div>{legend_items}</div>
            </div>
            <div class="benchmark-chart">
              <svg viewBox="0 0 860 340" preserveAspectRatio="none" aria-hidden="true">
                <g class="benchmark-grid-lines">
                  <line x1="0" x2="860" y1="68" y2="68"></line>
                  <line x1="0" x2="860" y1="136" y2="136"></line>
                  <line x1="0" x2="860" y1="204" y2="204"></line>
                  <line x1="0" x2="860" y1="272" y2="272"></line>
                </g>
                {hold_line_svg}
                {comparison_line_svg}
                {strategy_line_svg}
              </svg>
              {strategy_label}
              {comparison_label}
              {hold_label}
            </div>
          </article>
          <aside class="benchmark-side-panel">
            <div class="benchmark-tabs">
              <span class="active">已完成交易</span>
              <span>AI 推理</span>
              <span>持仓</span>
              <span>说明</span>
            </div>
            <div class="benchmark-side-section">
              <div class="benchmark-subtabs">
                <span class="active">正盈利</span>
                <span>负盈利</span>
                <span>V2</span>
              </div>
              {_benchmark_trade_feed(active)}
            </div>
            <div class="benchmark-side-section compact">
              <h3>AI 推理</h3>
              {_benchmark_ai_notes(active)}
            </div>
          </aside>
        </div>
      </section>
    """


def _backtest_overview(
    *,
    params: dict[str, object],
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
    rebalance_reports: list[dict[str, object]],
    strategy_explanation: dict[str, object] | None = None,
) -> str:
    export_query = _build_backtest_export_query(params)
    total_series_trades = sum(int(report["signal_count"]) for report in series_reports)
    total_portfolio_batches = sum(int(report["batch_count"]) for report in portfolio_reports)
    best_series = max((float(report["final_equity"]) for report in series_reports), default=0.0)
    best_portfolio = max((float(report["final_equity"]) for report in portfolio_reports), default=0.0)
    best_rebalance_premium = max((float(report["premium_pct"]) for report in rebalance_reports), default=0.0)
    return f"""
      <section id="backtest-export" class="overview-grid backtest-compact-section">
        <article class="ant-card overview-card">
          <div class="section-heading">
            <div>
              <h2>Export</h2>
              <p>基于当前页面参数直接导出结果。</p>
            </div>
          </div>
          <div class="action-row">
            <a class="action-link" href="/api/backtest?{escape(export_query)}">导出 JSON</a>
            <a class="action-link" href="/api/backtest/export?format=csv&amp;{escape(export_query)}">导出 CSV</a>
          </div>
          <div class="mini-stat-grid compact-grid">
            <div class="mini-stat"><span>Series Trades</span><strong>{total_series_trades}</strong></div>
            <div class="mini-stat"><span>Portfolio Batches</span><strong>{total_portfolio_batches}</strong></div>
            <div class="mini-stat"><span>Best Series Equity</span><strong>{best_series:.3f}</strong></div>
            <div class="mini-stat"><span>Best Portfolio Equity</span><strong>{best_portfolio:.3f}</strong></div>
            <div class="mini-stat"><span>Rebalance Premium</span><strong>{best_rebalance_premium:+.2f}%</strong></div>
          </div>
        </article>
        {_strategy_explanation_card(strategy_explanation)}
        <article class="ant-card overview-card">
          <div class="section-heading">
            <div>
              <h2>Series Equity Rank</h2>
              <p>按最终权益对单币种结果做快速比较。</p>
            </div>
          </div>
          {_summary_bars(sorted(series_reports, key=lambda item: float(item["final_equity"]), reverse=True), label_key="symbol")}
        </article>
        <article class="ant-card overview-card">
          <div class="section-heading">
            <div>
              <h2>Portfolio Equity Rank</h2>
              <p>组合回测优先看权益，再结合回撤判断稳定性。</p>
            </div>
          </div>
          {_summary_bars(sorted(portfolio_reports, key=lambda item: float(item["final_equity"]), reverse=True), label_key="interval")}
        </article>
      </section>
    """


def _strategy_explanation_card(explanation: dict[str, object] | None) -> str:
    if not isinstance(explanation, dict):
        return ""
    sample = explanation.get("sample") if isinstance(explanation.get("sample"), dict) else {}
    best = explanation.get("best") if isinstance(explanation.get("best"), dict) else {}
    best_series = best.get("series") if isinstance(best.get("series"), dict) else None
    diagnostics = explanation.get("diagnostics") if isinstance(explanation.get("diagnostics"), list) else []
    notes = explanation.get("notes") if isinstance(explanation.get("notes"), list) else []
    stability_checks = explanation.get("stability_checks") if isinstance(explanation.get("stability_checks"), list) else []
    best_label = "暂无"
    if best_series:
        best_label = (
            f'{escape(str(best_series.get("symbol", "")))} '
            f'{float(best_series.get("final_equity", 0.0)):.3f} / '
            f'DD {float(best_series.get("max_drawdown_pct", 0.0)):+.2f}%'
        )
    diagnostic_items = "".join(f"<li>{escape(str(item))}</li>" for item in diagnostics[:5])
    note_items = "".join(f"<li>{escape(str(item))}</li>" for item in notes[:4])
    return f"""
        <article class="ant-card overview-card strategy-explain-card">
          <div class="section-heading">
            <div>
              <h2>策略解释</h2>
              <p>{escape(str(explanation.get("summary", "")))}</p>
            </div>
          </div>
          <div class="mini-stat-grid compact-grid">
            <div class="mini-stat"><span>Strategy Type</span><strong>{escape(str(explanation.get("strategy_type", "")))}</strong></div>
            <div class="mini-stat"><span>Series</span><strong>{int(sample.get("series_count", 0))}</strong></div>
            <div class="mini-stat"><span>Trades</span><strong>{int(sample.get("series_trades", 0))}</strong></div>
            <div class="mini-stat"><span>Best Series</span><strong>{best_label}</strong></div>
          </div>
          <div class="strategy-explain-grid">
            <div>
              <h3>稳定性检查</h3>
              <ul class="strategy-warning-list">{diagnostic_items or "<li>暂无诊断。</li>"}</ul>
            </div>
            <div>
              <h3>参数与成本假设</h3>
              <ul class="strategy-warning-list">{note_items or "<li>暂无说明。</li>"}</ul>
            </div>
          </div>
          <div class="ant-table-wrapper table-shell">
            <h3>高级稳定性复测</h3>
            {_stability_check_rows(stability_checks)}
          </div>
        </article>
    """


def _stability_check_rows(items: list[object]) -> str:
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "error":
            rows.append(
                f"""
                <tr>
                  <td>{escape(str(item.get("symbol", "")))}</td>
                  <td>{escape(str(item.get("check", "")))}</td>
                  <td colspan="7">{escape(str(item.get("message", "")))}</td>
                </tr>
                """
            )
            continue
        window = ""
        if item.get("train_bars") is not None:
            window = f'Train {int(item.get("train_bars", 0))} / Valid {int(item.get("validation_bars", 0))}'
        rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("symbol", "")))}</td>
              <td>{escape(str(item.get("check", "")))}</td>
              <td>{float(item.get("score_threshold", 0.0)):.1f}</td>
              <td>{float(item.get("slippage_bps", 0.0)):.1f}bps</td>
              <td>{float(item.get("final_equity", 1.0)):.3f}</td>
              <td>{float(item.get("max_drawdown_pct", 0.0)):+.2f}%</td>
              <td>{int(item.get("signal_count", 0))}</td>
              <td>{float(item.get("profit_factor", 0.0)):.2f}</td>
              <td>{escape(window)}</td>
            </tr>
            """
        )
    if not rows:
        return '<p class="helper-text">未运行高级稳定性复测。勾选 Stability Checks 后会额外运行参数邻域和滚动 walk-forward。</p>'
    return f"""
      <table class="ant-table data-table">
        <tr><th>Symbol</th><th>Check</th><th>Score</th><th>Slip</th><th>Equity</th><th>Max DD</th><th>Trades</th><th>PF</th><th>Window</th></tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _backtest_card(report: dict[str, object]) -> str:
    trade_pills = _trade_pills(report["trade_stat"], float(report["final_equity"]), float(report["max_drawdown_pct"]))
    equity_points = str(report["equity_sparkline"]).strip()
    equity_svg = (
        f"""
        <svg class="equityline" viewBox="0 0 220 56" preserveAspectRatio="none" aria-hidden="true">
          <polyline points="{escape(equity_points)}" />
        </svg>
        """
        if equity_points
        else ""
    )
    return f"""
      <article class="ant-card backtest-card">
        <div class="signal-topline">
          <div>
            <p class="symbol">{escape(str(report["symbol"]))}</p>
            <p class="subline">{escape(str(report["interval"]))} · {int(report["signal_count"])} trades · {int(report["candle_count"])} candles</p>
          </div>
          <div class="score-badge">
            <span>Equity</span>
            <strong>{float(report["final_equity"]):.3f}</strong>
          </div>
        </div>
        {equity_svg}
        <p class="helper-text">{escape(_fee_meta(report))}</p>
        <div class="mini-stat-grid">{trade_pills}</div>
        {_stats_table(report["stats"])}
        <div class="ant-table-wrapper table-shell">
          <h3>Recent Trades</h3>
          {_event_rows(report["events"])}
        </div>
      </article>
    """


def _backtest_hint_card(icon: str, title: str, body: str, hints: list[str], action_html: str = "") -> str:
    hint_html = "".join(f"<span>{escape(item)}</span>" for item in hints if item)
    actions = f'<div class="empty-actions">{action_html}</div>' if action_html else ""
    return f"""
      <article class="ant-empty-state empty-state compact backtest-empty-card">
        <span class="empty-state-icon">{escape(icon)}</span>
        <div>
          <h2>{escape(title)}</h2>
          <p>{escape(body)}</p>
          <div class="empty-hints">{hint_html}</div>
          {actions}
        </div>
      </article>
    """


def _portfolio_card(report: dict[str, object]) -> str:
    if int(report.get("batch_count", 0)) <= 0 or int(report.get("pick_count", 0)) <= 0:
        return _portfolio_pending_card(report)
    trade_pills = _trade_pills(report["trade_stat"], float(report["final_equity"]), float(report["max_drawdown_pct"]))
    return f"""
      <article class="ant-card portfolio-card">
        <div class="signal-topline">
          <div>
            <p class="symbol">Portfolio {escape(str(report["interval"]))}</p>
            <p class="subline">top {int(report["top_n"])} · {int(report["batch_count"])} batches · {int(report["pick_count"])} picks</p>
          </div>
          <div class="score-badge">
            <span>Equity</span>
            <strong>{float(report["final_equity"]):.3f}</strong>
          </div>
        </div>
        <svg class="equityline" viewBox="0 0 220 56" preserveAspectRatio="none" aria-hidden="true">
          <polyline points="{escape(str(report["equity_sparkline"]))}" />
        </svg>
        <p class="helper-text">{escape(_fee_meta(report))}</p>
        <div class="mini-stat-grid">{trade_pills}</div>
        {_stats_table(report["stats"], portfolio=True)}
        <div class="ant-table-wrapper table-shell">
          <h3>Recent Batches</h3>
          {_selection_rows(report["selections"])}
        </div>
      </article>
    """


def _portfolio_pending_card(report: dict[str, object]) -> str:
    top_n = int(report.get("top_n", 0) or 0)
    symbol_count = int(report.get("symbol_count", 0) or 0)
    score_threshold = float(report.get("score_threshold", 0.0) or 0.0)
    reasons = []
    if symbol_count < 2:
        reasons.append("需要至少 2 个同周期币种才能形成组合。")
    if top_n <= 0:
        reasons.append("Portfolio Top N 当前为 0，组合回测未启用。")
    reasons.append("当前单币种信号没有在同一入场时间形成可选批次。")
    return _backtest_hint_card(
        "P",
        f"Portfolio {report.get('interval', '')} 暂无可执行组合批次",
        "；".join(reasons),
        [
            f"Top N = {top_n}",
            f"Symbols = {symbol_count}",
            f"Score >= {score_threshold:.1f}",
            "降低阈值或增加历史样本",
        ],
        '<a href="#backtest-data">调整数据和参数</a>',
    )


def _rebalance_card(report: dict[str, object]) -> str:
    return f"""
      <article class="ant-card portfolio-card">
        <div class="signal-topline">
          <div>
            <p class="symbol">Crypto Rebalance Premium {escape(str(report["interval"]))}</p>
            <p class="subline">{int(report["symbol_count"])} symbols · every {int(report["rebalance_interval_bars"])} bars · {int(report["rebalance_count"])} rebalances</p>
          </div>
          <div class="score-badge">
            <span>Premium</span>
            <strong>{float(report["premium_pct"]):+.2f}%</strong>
          </div>
        </div>
        <svg class="equityline" viewBox="0 0 220 56" preserveAspectRatio="none" aria-hidden="true">
          <polyline points="{escape(str(report["equity_sparkline"]))}" />
        </svg>
        <p class="helper-text">Equal-weight rebalance equity {float(report["rebalanced_final_equity"]):.3f} vs buy-and-hold drift {float(report["buy_hold_final_equity"]):.3f}. Costs: fee {float(report["fee_bps"]):.1f}bps + slippage {float(report["slippage_bps"]):.1f}bps.</p>
        <div class="mini-stat-grid">
          <div class="mini-stat"><span>Rebalanced Equity</span><strong>{float(report["rebalanced_final_equity"]):.3f}</strong></div>
          <div class="mini-stat"><span>Buy/Hold Equity</span><strong>{float(report["buy_hold_final_equity"]):.3f}</strong></div>
          <div class="mini-stat"><span>Max DD</span><strong>{float(report["max_drawdown_pct"]):+.2f}%</strong></div>
          <div class="mini-stat"><span>Avg Turnover</span><strong>{float(report["avg_turnover_pct"]):.2f}%</strong></div>
        </div>
        <div class="ant-table-wrapper table-shell">
          <h3>Recent Rebalances</h3>
          {_rebalance_rows(report["snapshots"])}
        </div>
      </article>
    """


def _portfolio_empty_card(params: dict[str, object], series_reports: list[dict[str, object]]) -> str:
    top_n = int(params.get("portfolio_top_n", 0) or 0)
    series_count = len(series_reports)
    symbol_count = len({str(report.get("symbol", "")).upper() for report in series_reports if report.get("symbol")})
    if top_n <= 0:
        title = "组合回测未启用"
        body = "将 Portfolio Top N 设置为大于 0 后，系统会按同一时间点的信号分数选出组合。"
    elif series_count == 0:
        title = "等待单币种回测结果"
        body = "先提供 ZIP/CSV 或 TradingView 历史 K 线，生成单币种信号后才能进行组合选择。"
    elif symbol_count < 2:
        title = "需要多币种历史样本"
        body = "当前只有一个可用币种，组合回测需要多个同周期标的用于横截面筛选。"
    else:
        title = "组合批次尚未形成"
        body = "已有单币种结果，但没有同一入场时间下满足阈值的候选批次，可降低分数阈值或增加样本。"
    return _backtest_hint_card(
        "P",
        title,
        body,
        [
            f"Top N = {top_n}",
            f"Series = {series_count}",
            f"Symbols = {symbol_count}",
            "多币种同周期",
        ],
        '<a href="#backtest-data">调整 Portfolio Top N / 阈值</a>',
    )


def _rebalance_empty_card(params: dict[str, object], series_reports: list[dict[str, object]]) -> str:
    preset = str(params.get("preset", "custom"))
    symbol_count = len({str(report.get("symbol", "")).upper() for report in series_reports if report.get("symbol")})
    intervals = {str(report.get("interval", "")) for report in series_reports if report.get("interval")}
    if preset != "crypto_rebalance_premium":
        title = "切换到再平衡模板后显示"
        body = "选择“加密资产等权再平衡”预设后，会比较定期等权再平衡与买入后自然漂移组合。"
        rebalance_params = {**params, "preset": "crypto_rebalance_premium"}
        action_html = (
            '<a href="/backtest?'
            f'{escape(_build_backtest_export_query(rebalance_params), quote=True)}#backtest-rebalance">'
            "切换到加密资产等权再平衡</a>"
        )
    elif symbol_count < 2:
        title = "再平衡样本不足"
        body = "该报告需要至少两个币种的同周期历史 K 线，且时间戳需要有重叠。"
        action_html = '<a href="#backtest-data">补充多币种同周期数据</a>'
    else:
        title = "暂未形成再平衡快照"
        body = "已有多个币种结果，但时间戳可能未对齐或样本不足，建议使用同一交易所、同一周期的数据源。"
        action_html = '<a href="#backtest-data">检查周期和时间戳</a>'
    return _backtest_hint_card(
        "R",
        title,
        body,
        [
            f"Preset = {preset}",
            f"Symbols = {symbol_count}",
            f"Intervals = {len(intervals)}",
            "同周期时间戳对齐",
        ],
        action_html,
    )


def _rebalance_rows(snapshots: list[dict[str, object]]) -> str:
    if not snapshots:
        return '<p class="helper-text">暂无再平衡快照。</p>'
    rows = []
    for item in snapshots:
        rows.append(
            f"""
            <tr>
              <td>{escape(str(item["time"]))}</td>
              <td>{float(item["rebalanced_equity"]):.4f}</td>
              <td>{float(item["buy_hold_equity"]):.4f}</td>
              <td>{float(item["premium_pct"]):+.2f}%</td>
              <td>{float(item["turnover_pct"]):.2f}%</td>
            </tr>
            """
        )
    return f"""
      <table class="ant-table data-table">
        <tr><th>Time</th><th>Rebalanced</th><th>Buy/Hold</th><th>Premium</th><th>Turnover</th></tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def render_backtest_page(
    *,
    params: dict[str, object],
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
    error: str | None,
    presets: list[dict[str, object]],
    rebalance_reports: list[dict[str, object]] | None = None,
    strategy_explanation: dict[str, object] | None = None,
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    archive_value = escape(str(params["archives"]))
    tradingview_exchange = escape(str(params.get("tradingview_exchange", "BINANCE")))
    tradingview_symbol = escape(str(params.get("tradingview_symbol", "BTCUSDT")))
    tradingview_interval = str(params.get("tradingview_interval", "4h"))
    tradingview_bars = int(params.get("tradingview_bars", 5000) or 5000)
    rebalance_reports = rebalance_reports or []
    current_preset = get_backtest_preset(str(params["preset"]))
    preset_options = _backtest_preset_options(str(params["preset"]))
    hero_right = f"""
      <div class="ant-statistic-card stat-card">
        <span>Series Reports</span>
        <strong>{len(series_reports)}</strong>
        <small>{t("单币种回测", "single-symbol backtests")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>Portfolio Reports</span>
        <strong>{len(portfolio_reports)}</strong>
        <small>{t("组合结果", "portfolio results")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>Rebalance Reports</span>
        <strong>{len(rebalance_reports)}</strong>
        <small>{t("等权再平衡", "equal-weight rebalance")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>Lookback</span>
        <strong>{int(params["lookback_bars"])}</strong>
        <small>{escape(str(params["slippage_model"]))} slippage · cooldown {int(params["cooldown_bars"])}</small>
      </div>
    """

    error_html = ""
    if error:
        error_html = f'<div class="notice notice-error">{escape(error)}</div>'
    elif params.get("tv_fetched"):
        error_html = '<div class="notice notice-success">TradingView 历史 K 线已缓存为 CSV，并已进入回测分析。</div>'

    portfolio_html = "".join(_portfolio_card(report) for report in portfolio_reports)
    rebalance_html = "".join(_rebalance_card(report) for report in rebalance_reports)
    series_html = "".join(_backtest_card(report) for report in series_reports)
    if not portfolio_html:
        portfolio_html = _portfolio_empty_card(params, series_reports)
    if not series_html:
        series_html = _backtest_hint_card(
            "S",
            "单币种结果待生成",
            "输入本地 ZIP/CSV pattern，或先用 TradingView 拉取历史 K 线，提交后会生成每个标的的权益和交易明细。",
            ["ZIP/CSV", "Score", "Signals"],
        )
    if not rebalance_html:
        rebalance_html = _rebalance_empty_card(params, series_reports)

    module_tabs = _module_tabs(
        [
            ("#backtest-data", "数据源"),
            ("#backtest-benchmark", "基准"),
            ("#backtest-analysis", "分析"),
            ("#backtest-export", "导出"),
            ("#backtest-rebalance", "再平衡"),
            ("#backtest-portfolio", "组合"),
            ("#backtest-series", "明细"),
        ],
        active_index=0,
        label="回测分析模块",
    )

    content = f"""
      <div class="backtest-workspace">
        {module_tabs}
        <section id="backtest-data" class="ant-card control-panel backtest-control-panel">
          {error_html}
          <div class="section-heading backtest-control-heading">
            <div>
              <h2>回测工作台</h2>
              <p>配置参数、选择历史数据源，然后直接生成分析看板。</p>
            </div>
            <span class="backtest-source-badge">ZIP / CSV / TradingView</span>
          </div>
          <div class="backtest-command-grid">
            <form method="get" action="/backtest" class="ant-form backtest-form backtest-main-form">
              {_hidden_lang_input(active_lang)}
              <label><span>Preset</span><select name="preset">{preset_options}</select></label>
              <div class="preset-note">
                <strong>{escape(current_preset.label)}</strong>
                <span>{escape(current_preset.description)}</span>
                <a href="/api/backtest/presets">查看模板清单</a>
              </div>
              <label class="full-span">
                <span>Archive Patterns</span>
                <textarea name="archives" rows="3" placeholder="例如：data/spot/monthly/klines/*/4h/*.zip">{archive_value}</textarea>
              </label>
              <label><span>Lookback Bars</span><input type="number" min="60" name="lookback_bars" value="{int(params['lookback_bars'])}" /></label>
              <label><span>Score Threshold</span><input type="number" step="0.1" name="score_threshold" value="{float(params['score_threshold']):.1f}" /></label>
              <label><span>Holding Periods</span><input type="text" name="holding_periods" value="{escape(str(params['holding_periods']))}" /></label>
              <label><span>Portfolio Top N</span><input type="number" min="0" name="portfolio_top_n" value="{int(params['portfolio_top_n'])}" /></label>
              <label><span>Cooldown Bars</span><input type="number" min="0" name="cooldown_bars" value="{int(params['cooldown_bars'])}" /></label>
              <label><span>Stop Loss %</span><input type="number" step="0.1" name="stop_loss_pct" value="{float(params['stop_loss_pct']):.1f}" /></label>
              <label><span>Take Profit %</span><input type="number" step="0.1" name="take_profit_pct" value="{float(params['take_profit_pct']):.1f}" /></label>
              <label><span>Max Holding Bars</span><input type="number" min="1" name="max_holding_bars" value="{int(params['max_holding_bars'])}" /></label>
              <details class="backtest-advanced-options">
                <summary>
                  <span>高级成本 / 风控参数</span>
                  <small>手续费、滑点、资金暴露、量能与 RSI 过滤</small>
                </summary>
                <div class="backtest-advanced-grid">
                  <label><span>Fee bps</span><input type="number" step="0.1" name="fee_bps" value="{float(params['fee_bps']):.1f}" /></label>
                  <label><span>Fee Model</span><select name="fee_model">{''.join(_option(item, str(params['fee_model'])) for item in ['flat', 'maker_taker'])}</select></label>
                  <label><span>Fee Source</span><select name="fee_source">{''.join(_option(item, str(params['fee_source'])) for item in ['manual', 'account', 'symbol'])}</select></label>
                  <label><span>Maker Fee bps</span><input type="number" step="0.1" name="maker_fee_bps" value="{float(params['maker_fee_bps']):.1f}" /></label>
                  <label><span>Taker Fee bps</span><input type="number" step="0.1" name="taker_fee_bps" value="{float(params['taker_fee_bps']):.1f}" /></label>
                  <label><span>Entry Fee Role</span><select name="entry_fee_role">{''.join(_option(item, str(params['entry_fee_role'])) for item in ['maker', 'taker'])}</select></label>
                  <label><span>Exit Fee Role</span><select name="exit_fee_role">{''.join(_option(item, str(params['exit_fee_role'])) for item in ['maker', 'taker'])}</select></label>
                  <label><span>Fee Discount %</span><input type="number" step="0.1" name="fee_discount_pct" value="{float(params['fee_discount_pct']):.1f}" /></label>
                  <label><span>Slippage bps</span><input type="number" step="0.1" name="slippage_bps" value="{float(params['slippage_bps']):.1f}" /></label>
                  <label><span>Slippage Model</span><select name="slippage_model">{''.join(_option(item, str(params['slippage_model'])) for item in ['fixed', 'dynamic'])}</select></label>
                  <label><span>Min Slippage</span><input type="number" step="0.1" name="min_slippage_bps" value="{float(params['min_slippage_bps']):.1f}" /></label>
                  <label><span>Max Slippage</span><input type="number" step="0.1" name="max_slippage_bps" value="{float(params['max_slippage_bps']):.1f}" /></label>
                  <label><span>Slip Window</span><input type="number" min="1" name="slippage_window_bars" value="{int(params['slippage_window_bars'])}" /></label>
                  <label><span>Capital %</span><input type="number" step="0.1" name="capital_fraction_pct" value="{float(params['capital_fraction_pct']):.1f}" /></label>
                  <label><span>Max Exposure %</span><input type="number" step="0.1" name="max_portfolio_exposure_pct" value="{float(params['max_portfolio_exposure_pct']):.1f}" /></label>
                  <label><span>Max Concurrent</span><input type="number" min="0" name="max_concurrent_positions" value="{int(params['max_concurrent_positions'])}" /></label>
                  <label><span>Min Volume Ratio</span><input type="number" step="0.01" name="min_volume_ratio" value="{float(params['min_volume_ratio']):.2f}" /></label>
                  <label><span>Min Buy Pressure</span><input type="number" step="0.01" name="min_buy_pressure" value="{float(params['min_buy_pressure']):.2f}" /></label>
                  <label><span>Min RSI</span><input type="number" step="0.1" name="min_rsi" value="{float(params['min_rsi']):.1f}" /></label>
                  <label><span>Max RSI</span><input type="number" step="0.1" name="max_rsi" value="{float(params['max_rsi']):.1f}" /></label>
                  <label class="inline-check"><input type="checkbox" name="no_binance_discount" {"checked" if params["no_binance_discount"] else ""} /><span>Disable Binance discount</span></label>
                  <label class="inline-check"><input type="checkbox" name="no_kdj_confirmation" {"checked" if params["no_kdj_confirmation"] else ""} /><span>Disable KDJ confirmation</span></label>
                  <label class="inline-check"><input type="checkbox" name="stability_checks" {"checked" if params.get("stability_checks") else ""} /><span>Stability Checks</span><small class="settings-description">额外运行 score±3、滑点上调和滚动 walk-forward 复测。</small></label>
                </div>
              </details>
              <button type="submit">运行回测</button>
            </form>
            <aside class="backtest-data-source">
              <form method="post" action="/backtest/tradingview/fetch" class="ant-form backtest-form tradingview-fetch-form">
                {_hidden_lang_input(active_lang)}
                <input type="hidden" name="preset" value="{escape(str(params['preset']), quote=True)}" />
                <input type="hidden" name="lookback_bars" value="{int(params['lookback_bars'])}" />
                <input type="hidden" name="score_threshold" value="{float(params['score_threshold']):.1f}" />
                <input type="hidden" name="holding_periods" value="{escape(str(params['holding_periods']), quote=True)}" />
                <input type="hidden" name="portfolio_top_n" value="{int(params['portfolio_top_n'])}" />
                <div class="preset-note full-span">
                  <strong>TradingView 历史 K 线</strong>
                  <span>拉取后缓存为本地 CSV，立刻交给当前参数回测。</span>
                  <a href="/api/backtest/tradingview/fetch?tradingview_exchange={tradingview_exchange}&amp;tradingview_symbol={tradingview_symbol}&amp;tradingview_interval={escape(tradingview_interval)}&amp;tradingview_bars={tradingview_bars}">JSON 拉取</a>
                </div>
                <label><span>TV Exchange</span><input type="text" name="tradingview_exchange" value="{tradingview_exchange}" /></label>
                <label><span>TV Symbol</span><input type="text" name="tradingview_symbol" value="{tradingview_symbol}" /></label>
                <label><span>TV Interval</span><select name="tradingview_interval">{''.join(_option(item, tradingview_interval) for item in ['1m', '3m', '5m', '15m', '30m', '45m', '1h', '2h', '3h', '4h', '1d', '1w', '1M'])}</select></label>
                <label><span>TV Bars</span><input type="number" min="100" max="50000" step="100" name="tradingview_bars" value="{tradingview_bars}" /></label>
                <button type="submit">拉取并回测</button>
              </form>
              <div class="backtest-source-note">
                <strong>数据读取规则</strong>
                <span>支持本地 Binance ZIP、TradingView CSV、目录和 glob pattern。多行输入会自动合并去重。</span>
              </div>
            </aside>
          </div>
        </section>

        <div class="backtest-result-stack">
          {_benchmark_workbench(series_reports)}
          {_backtest_visual_analysis(series_reports=series_reports, portfolio_reports=portfolio_reports, rebalance_reports=rebalance_reports, strategy_explanation=strategy_explanation)}
          {_backtest_overview(params=params, series_reports=series_reports, portfolio_reports=portfolio_reports, rebalance_reports=rebalance_reports, strategy_explanation=strategy_explanation)}
        </div>

      <section id="backtest-rebalance" class="ant-section section-block backtest-compact-section">
        <div class="section-heading">
          <h2>Rebalance Premium</h2>
          <p>比较等权定期再平衡组合和买入后自然漂移组合。</p>
        </div>
        <div class="portfolio-grid">{rebalance_html}</div>
      </section>

      <section id="backtest-portfolio" class="ant-section section-block backtest-compact-section">
        <div class="section-heading">
          <h2>Portfolio</h2>
          <p>先看组合，再看各币种明细。</p>
        </div>
        <div class="portfolio-grid">{portfolio_html}</div>
      </section>

      <section id="backtest-series" class="ant-section section-block backtest-compact-section">
        <div class="section-heading">
          <h2>Series</h2>
          <p>每个币种各自的交易、收益和资金曲线。</p>
        </div>
        <div class="backtest-grid">{series_html}</div>
      </section>
      </div>
    """

    return _layout(
        page_title="Binance Signal Backtest",
        active_page="backtest",
        hero_title=t("把本地 Binance 历史 K 线直接拉进页面里回测。", "Run backtests directly from local Binance historical kline archives."),
        hero_text=t("同一页里调整分数阈值、止盈止损、滑点模型和组合仓位约束，直接看单币种与组合结果。", "Tune score thresholds, stop loss, take profit, slippage model, and portfolio exposure constraints on one page."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/backtest",
        layout_context=layout_context,
    )


__all__ = [
    '_stats_table',
    '_trade_pills',
    '_fee_meta',
    '_event_rows',
    '_selection_rows',
    '_serialize_query_value',
    '_build_backtest_export_query',
    '_summary_bars',
    '_curve_values',
    '_has_chartable_curve',
    '_benchmark_line_points',
    '_money_from_equity',
    '_return_from_equity',
    '_analysis_quality_label',
    '_backtest_result_rows',
    '_backtest_visual_analysis',
    '_benchmark_trade_feed',
    '_benchmark_ai_notes',
    '_benchmark_workbench',
    '_backtest_overview',
    '_strategy_explanation_card',
    '_stability_check_rows',
    '_backtest_card',
    '_backtest_hint_card',
    '_portfolio_card',
    '_portfolio_pending_card',
    '_rebalance_card',
    '_portfolio_empty_card',
    '_rebalance_empty_card',
    '_rebalance_rows',
    'render_backtest_page',
]
