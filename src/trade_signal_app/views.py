from __future__ import annotations

from html import escape


def _option(value: str, selected: str) -> str:
    is_selected = " selected" if value == selected else ""
    return f'<option value="{escape(value)}"{is_selected}>{escape(value)}</option>'


def _layout(*, page_title: str, active_page: str, hero_title: str, hero_text: str, hero_right: str, content: str) -> str:
    scan_active = "nav-link active" if active_page == "scan" else "nav-link"
    backtest_active = "nav-link active" if active_page == "backtest" else "nav-link"
    settings_active = "nav-link active" if active_page == "settings" else "nav-link"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(page_title)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main class="page-shell">
      <nav class="top-nav">
        <a class="{scan_active}" href="/">实时扫描</a>
        <a class="{backtest_active}" href="/backtest">历史回测</a>
        <a class="{settings_active}" href="/settings">运行配置</a>
      </nav>

      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">Binance Spot Signal Scanner</p>
          <h1>{escape(hero_title)}</h1>
          <p class="hero-text">{escape(hero_text)}</p>
        </div>
        <div class="hero-meta">{hero_right}</div>
      </section>

      {content}
    </main>
  </body>
</html>
"""


def _breakdown_bars(breakdown: dict[str, float | None]) -> str:
    parts: list[str] = []
    for label, value in breakdown.items():
        if value is None:
            continue
        parts.append(
            f"""
            <div class="bar">
              <span>{escape(label)}</span>
              <div class="track"><i style="width: {value:.2f}%"></i></div>
            </div>
            """
        )
    return "".join(parts)


def _chips(items: list[str], chip_class: str) -> str:
    return "".join(f'<span class="chip {chip_class}">{escape(item)}</span>' for item in items)


def _signal_card(signal: dict[str, object]) -> str:
    grade_class = str(signal["grade"]).lower().replace("+", "-plus")
    community = ""
    if signal.get("community_score") is not None:
        mentions = ""
        if signal.get("community_mentions") is not None:
            mentions = f' · {int(signal["community_mentions"])} mentions'
        sentiment = ""
        if signal.get("community_sentiment") is not None:
            sentiment_value = float(signal["community_sentiment"])
            sentiment = f' · senti {sentiment_value:+.2f}'
        community = (
            f'<span class="chip neutral">社区 {float(signal["community_score"]):.0f} / 100 · '
            f'{escape(str(signal["community_source"]))}{mentions}{sentiment}</span>'
        )

    return f"""
    <article class="signal-card grade-{grade_class}">
      <div class="signal-topline">
        <div>
          <p class="symbol">{escape(str(signal["symbol"]))}</p>
          <p class="subline">24h {float(signal["price_change_percent"]):+.2f}%</p>
        </div>
        <div class="score-badge">
          <span>{escape(str(signal["grade"]))}</span>
          <strong>{float(signal["score"]):.1f}</strong>
        </div>
      </div>

      <svg class="sparkline" viewBox="0 0 160 44" preserveAspectRatio="none" aria-hidden="true">
        <polyline points="{escape(str(signal["sparkline_points"]))}" />
      </svg>

      <div class="metric-row">
        <div>
          <span>RSI</span>
          <strong>{float(signal["rsi_14"]):.1f}</strong>
        </div>
        <div>
          <span>量比</span>
          <strong>{float(signal["volume_ratio"]):.2f}x</strong>
        </div>
        <div>
          <span>EMA Spread</span>
          <strong>{float(signal["ema_spread_pct"]):+.2f}%</strong>
        </div>
      </div>

      <div class="breakdowns">
        {_breakdown_bars(signal["breakdown"])}
      </div>

      <div class="chips">
        {_chips(signal["reasons"], "positive")}
        {_chips(signal["warnings"], "warning")}
        {community}
      </div>

      <footer class="card-footer">
        <span>24h 成交额 {float(signal["quote_volume_m"]):.1f}M</span>
        <span>MACD Hist {float(signal["macd_hist"]):+.4f}</span>
      </footer>
    </article>
    """


def render_index_page(
    summary: dict[str, object],
    signals: list[dict[str, object]],
    params: dict[str, object],
    intervals: list[str],
) -> str:
    cards = "".join(_signal_card(signal) for signal in signals)
    if not cards:
        cards = """
        <article class="empty-state">
          <h2>当前条件下没有足够强的候选币种。</h2>
          <p>可以适当降低最小成交额或增大候选数，再重新扫描。</p>
        </article>
        """

    options = "".join(_option(interval, str(params["interval"])) for interval in intervals)
    hero_right = f"""
      <div class="stat-card">
        <span>扫描范围</span>
        <strong>{int(summary["scanned_symbols"])}</strong>
        <small>{escape(str(summary["quote_asset"]))} 现货交易对</small>
      </div>
      <div class="stat-card">
        <span>返回信号</span>
        <strong>{int(summary["returned_signals"])}</strong>
        <small>{escape(str(summary["interval"]))} 周期</small>
      </div>
      <div class="stat-card">
        <span>最小成交额</span>
        <strong>{float(summary["min_quote_volume"]) / 1_000_000:.0f}M</strong>
        <small>Quote Volume</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        <form method="get" class="filters">
          <label>
            <span>计价币</span>
            <input type="text" name="quote_asset" value="{escape(str(params["quote_asset"]))}" />
          </label>
          <label>
            <span>周期</span>
            <select name="interval">{options}</select>
          </label>
          <label>
            <span>候选数</span>
            <input type="number" name="candidate_pool" min="5" max="40" value="{int(params["candidate_pool"])}" />
          </label>
          <label>
            <span>最小成交额</span>
            <input type="number" name="min_quote_volume" min="1000000" step="1000000" value="{int(params["min_quote_volume"])}" />
          </label>
          <label>
            <span>最小成交笔数</span>
            <input type="number" name="min_trade_count" min="100" step="100" value="{int(params["min_trade_count"])}" />
          </label>
          <button type="submit">刷新信号</button>
        </form>
        <p class="helper-text">
          数据来自 Binance Spot 市场接口。社区热度支持 X/Twitter Bearer Token 和本地 <code>data/community_scores.csv</code>，未配置时会自动忽略该维度。
        </p>
      </section>

      <section class="signal-grid">
        {cards}
      </section>
    """
    return _layout(
        page_title="Binance Signal Scanner",
        active_page="scan",
        hero_title="从高流动性币种里抓更像“可入手”的那一批。",
        hero_text="先用 24h 市场活跃度做初筛，再计算 RSI、EMA、MACD、KDJ、量能放大和可选的社区热度，输出一份偏实战的候选榜。",
        hero_right=hero_right,
        content=content,
    )


def render_settings_page(
    *,
    params: dict[str, object],
    status: dict[str, object],
    message: str | None,
    error: str | None,
) -> str:
    notices = []
    if message:
        notices.append(f'<div class="notice notice-success">{escape(message)}</div>')
    if error:
        notices.append(f'<div class="notice notice-error">{escape(error)}</div>')

    tracked_accounts = "\n".join(str(item) for item in params["x_tracked_accounts"])
    hero_right = f"""
      <div class="stat-card">
        <span>Binance Auth</span>
        <strong>{"On" if status["binance_auth_configured"] else "Off"}</strong>
        <small>{escape(str(status["binance_auth_label"]))}</small>
      </div>
      <div class="stat-card">
        <span>X / Twitter</span>
        <strong>{"On" if status["x_auth_configured"] else "Off"}</strong>
        <small>{int(status["tracked_account_count"])} tracked accounts</small>
      </div>
      <div class="stat-card">
        <span>Storage</span>
        <strong>Local</strong>
        <small>配置保存到本地 JSON</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        {"".join(notices)}
        <form method="post" action="/settings" class="backtest-form">
          <div class="settings-heading full-span">
            <h2>Access</h2>
            <p>密钥通过 POST 提交，不会出现在 URL。留空表示保持当前值。</p>
          </div>
          <label><span>Binance API Key</span><input type="password" name="binance_api_key" value="" placeholder="留空保持当前" /></label>
          <label><span>Binance API Secret</span><input type="password" name="binance_api_secret" value="" placeholder="留空保持当前" /></label>
          <label><span>Binance RecvWindow</span><input type="number" step="1" min="1" name="binance_recv_window_ms" value="{float(params['binance_recv_window_ms']):.0f}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_binance_auth" /><span>Clear Binance auth</span></label>
          <label><span>X Bearer Token</span><input type="password" name="x_bearer_token" value="" placeholder="留空保持当前" /></label>
          <label><span>Community Provider</span><select name="community_provider">{''.join(_option(item, str(params['community_provider'])) for item in ['auto', 'x', 'csv', 'x,csv'])}</select></label>
          <label><span>X API Base URL</span><input type="text" name="x_api_base_url" value="{escape(str(params['x_api_base_url']))}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_x_auth" /><span>Clear X auth</span></label>

          <div class="settings-heading full-span">
            <h2>Twitter Intel</h2>
            <p>账号列表支持一行一个用户名。`blend` 会把普通舆情和指定账号情报按权重混合，`only` 只看指定账号。</p>
          </div>
          <label><span>X Window Hours</span><input type="number" min="1" name="x_recent_window_hours" value="{int(params['x_recent_window_hours'])}" /></label>
          <label><span>X Max Results</span><input type="number" min="10" max="100" name="x_recent_max_results" value="{int(params['x_recent_max_results'])}" /></label>
          <label><span>X Language</span><input type="text" name="x_language" value="{escape(str(params['x_language']))}" /></label>
          <label><span>Account Mode</span><select name="x_account_mode">{''.join(_option(item, str(params['x_account_mode'])) for item in ['off', 'blend', 'only'])}</select></label>
          <label><span>Account Weight %</span><input type="number" step="0.1" min="0" max="100" name="x_account_weight_pct" value="{float(params['x_account_weight_pct']):.1f}" /></label>
          <label class="full-span"><span>Tracked Accounts</span><textarea name="x_tracked_accounts" rows="5" placeholder="@lookonchain&#10;wu_blockchain&#10;TheBlock__">{escape(tracked_accounts)}</textarea></label>

          <div class="settings-heading full-span">
            <h2>Scan Defaults</h2>
            <p>这些值会成为实时扫描页的默认参数，你仍然可以在扫描页临时改动。</p>
          </div>
          <label><span>Quote Asset</span><input type="text" name="scan_quote_asset" value="{escape(str(params['scan_quote_asset']))}" /></label>
          <label><span>Scan Interval</span><select name="scan_interval">{''.join(_option(item, str(params['scan_interval'])) for item in ['15m', '1h', '4h', '1d'])}</select></label>
          <label><span>Candidate Pool</span><input type="number" min="5" max="40" name="scan_candidate_pool" value="{int(params['scan_candidate_pool'])}" /></label>
          <label><span>Min Quote Volume</span><input type="number" min="1000000" step="1000000" name="scan_min_quote_volume" value="{int(params['scan_min_quote_volume'])}" /></label>
          <label><span>Min Trade Count</span><input type="number" min="100" step="100" name="scan_min_trade_count" value="{int(params['scan_min_trade_count'])}" /></label>

          <div class="settings-heading full-span">
            <h2>Backtest Defaults</h2>
            <p>这些值会作为回测页的默认策略参数。你可以把实盘偏好先固定下来，再按每次任务微调。</p>
          </div>
          <label class="full-span"><span>Default Archives</span><textarea name="backtest_archives" rows="4" placeholder="data/spot/monthly/klines/*/4h/*.zip">{escape(str(params['backtest_archives']))}</textarea></label>
          <label><span>Lookback Bars</span><input type="number" min="60" name="backtest_lookback_bars" value="{int(params['backtest_lookback_bars'])}" /></label>
          <label><span>Score Threshold</span><input type="number" step="0.1" name="backtest_score_threshold" value="{float(params['backtest_score_threshold']):.1f}" /></label>
          <label><span>Holding Periods</span><input type="text" name="backtest_holding_periods" value="{escape(str(params['backtest_holding_periods']))}" /></label>
          <label><span>Portfolio Top N</span><input type="number" min="0" name="backtest_portfolio_top_n" value="{int(params['backtest_portfolio_top_n'])}" /></label>
          <label><span>Cooldown Bars</span><input type="number" min="0" name="backtest_cooldown_bars" value="{int(params['backtest_cooldown_bars'])}" /></label>
          <label><span>Stop Loss %</span><input type="number" step="0.1" name="backtest_stop_loss_pct" value="{float(params['backtest_stop_loss_pct']):.1f}" /></label>
          <label><span>Take Profit %</span><input type="number" step="0.1" name="backtest_take_profit_pct" value="{float(params['backtest_take_profit_pct']):.1f}" /></label>
          <label><span>Max Holding Bars</span><input type="number" min="1" name="backtest_max_holding_bars" value="{int(params['backtest_max_holding_bars'])}" /></label>
          <label><span>Fee Source</span><select name="backtest_fee_source">{''.join(_option(item, str(params['backtest_fee_source'])) for item in ['manual', 'account', 'symbol'])}</select></label>
          <label><span>Fee Model</span><select name="backtest_fee_model">{''.join(_option(item, str(params['backtest_fee_model'])) for item in ['flat', 'maker_taker'])}</select></label>
          <label><span>Fee bps</span><input type="number" step="0.1" name="backtest_fee_bps" value="{float(params['backtest_fee_bps']):.1f}" /></label>
          <label><span>Maker Fee bps</span><input type="number" step="0.1" name="backtest_maker_fee_bps" value="{float(params['backtest_maker_fee_bps']):.1f}" /></label>
          <label><span>Taker Fee bps</span><input type="number" step="0.1" name="backtest_taker_fee_bps" value="{float(params['backtest_taker_fee_bps']):.1f}" /></label>
          <label><span>Entry Role</span><select name="backtest_entry_fee_role">{''.join(_option(item, str(params['backtest_entry_fee_role'])) for item in ['maker', 'taker'])}</select></label>
          <label><span>Exit Role</span><select name="backtest_exit_fee_role">{''.join(_option(item, str(params['backtest_exit_fee_role'])) for item in ['maker', 'taker'])}</select></label>
          <label><span>Fee Discount %</span><input type="number" step="0.1" name="backtest_fee_discount_pct" value="{float(params['backtest_fee_discount_pct']):.1f}" /></label>
          <label class="inline-check"><input type="checkbox" name="backtest_no_binance_discount" {"checked" if params["backtest_no_binance_discount"] else ""} /><span>Disable Binance discount</span></label>
          <label><span>Slippage bps</span><input type="number" step="0.1" name="backtest_slippage_bps" value="{float(params['backtest_slippage_bps']):.1f}" /></label>
          <label><span>Slippage Model</span><select name="backtest_slippage_model">{''.join(_option(item, str(params['backtest_slippage_model'])) for item in ['fixed', 'dynamic'])}</select></label>
          <label><span>Min Slippage</span><input type="number" step="0.1" name="backtest_min_slippage_bps" value="{float(params['backtest_min_slippage_bps']):.1f}" /></label>
          <label><span>Max Slippage</span><input type="number" step="0.1" name="backtest_max_slippage_bps" value="{float(params['backtest_max_slippage_bps']):.1f}" /></label>
          <label><span>Slip Window</span><input type="number" min="1" name="backtest_slippage_window_bars" value="{int(params['backtest_slippage_window_bars'])}" /></label>
          <label><span>Capital %</span><input type="number" step="0.1" name="backtest_capital_fraction_pct" value="{float(params['backtest_capital_fraction_pct']):.1f}" /></label>
          <label><span>Max Exposure %</span><input type="number" step="0.1" name="backtest_max_portfolio_exposure_pct" value="{float(params['backtest_max_portfolio_exposure_pct']):.1f}" /></label>
          <label><span>Max Concurrent</span><input type="number" min="0" name="backtest_max_concurrent_positions" value="{int(params['backtest_max_concurrent_positions'])}" /></label>
          <label><span>Min Volume Ratio</span><input type="number" step="0.01" name="backtest_min_volume_ratio" value="{float(params['backtest_min_volume_ratio']):.2f}" /></label>
          <label><span>Min Buy Pressure</span><input type="number" step="0.01" name="backtest_min_buy_pressure" value="{float(params['backtest_min_buy_pressure']):.2f}" /></label>
          <label><span>Min RSI</span><input type="number" step="0.1" name="backtest_min_rsi" value="{float(params['backtest_min_rsi']):.1f}" /></label>
          <label><span>Max RSI</span><input type="number" step="0.1" name="backtest_max_rsi" value="{float(params['backtest_max_rsi']):.1f}" /></label>
          <label class="inline-check"><input type="checkbox" name="backtest_no_kdj_confirmation" {"checked" if params["backtest_no_kdj_confirmation"] else ""} /><span>Disable KDJ confirmation</span></label>

          <button type="submit">保存运行配置</button>
        </form>
        <p class="helper-text">
          当前实现会把配置写入本地 JSON 文件。适合你自己本机使用；如果后面要多用户部署，需要再把密钥存储切到加密后端。
        </p>
      </section>
    """
    return _layout(
        page_title="Runtime Settings",
        active_page="settings",
        hero_title="把数据源、情报源和策略参数都收进一个运行时配置面板。",
        hero_text="密钥、Twitter 监控账号、扫描默认值和回测默认策略都可以在这里改。保存后，扫描页和回测页会直接吃新的默认配置。",
        hero_right=hero_right,
        content=content,
    )


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
    return f'<table class="data-table">{header}<tbody>{"".join(body)}</tbody></table>'


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
      <table class="data-table">
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
      <table class="data-table">
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


def _backtest_card(report: dict[str, object]) -> str:
    trade_pills = _trade_pills(report["trade_stat"], float(report["final_equity"]), float(report["max_drawdown_pct"]))
    return f"""
      <article class="backtest-card">
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
        <svg class="equityline" viewBox="0 0 220 56" preserveAspectRatio="none" aria-hidden="true">
          <polyline points="{escape(str(report["equity_sparkline"]))}" />
        </svg>
        <p class="helper-text">{escape(_fee_meta(report))}</p>
        <div class="mini-stat-grid">{trade_pills}</div>
        {_stats_table(report["stats"])}
        <div class="table-shell">
          <h3>Recent Trades</h3>
          {_event_rows(report["events"])}
        </div>
      </article>
    """


def _portfolio_card(report: dict[str, object]) -> str:
    trade_pills = _trade_pills(report["trade_stat"], float(report["final_equity"]), float(report["max_drawdown_pct"]))
    return f"""
      <article class="portfolio-card">
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
        <div class="table-shell">
          <h3>Recent Batches</h3>
          {_selection_rows(report["selections"])}
        </div>
      </article>
    """


def render_backtest_page(
    *,
    params: dict[str, object],
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
    error: str | None,
) -> str:
    archive_value = escape(str(params["archives"]))
    hero_right = f"""
      <div class="stat-card">
        <span>Series Reports</span>
        <strong>{len(series_reports)}</strong>
        <small>单币种回测</small>
      </div>
      <div class="stat-card">
        <span>Portfolio Reports</span>
        <strong>{len(portfolio_reports)}</strong>
        <small>组合结果</small>
      </div>
      <div class="stat-card">
        <span>Lookback</span>
        <strong>{int(params["lookback_bars"])}</strong>
        <small>{escape(str(params["slippage_model"]))} slippage · cooldown {int(params["cooldown_bars"])}</small>
      </div>
    """

    error_html = ""
    if error:
        error_html = f'<div class="notice notice-error">{escape(error)}</div>'

    portfolio_html = "".join(_portfolio_card(report) for report in portfolio_reports)
    series_html = "".join(_backtest_card(report) for report in series_reports)
    if not portfolio_html:
        portfolio_html = '<article class="empty-state compact"><h2>还没有组合结果。</h2><p>传入多个币种 ZIP 并启用 top N，才会看到组合回测。</p></article>'
    if not series_html:
        series_html = '<article class="empty-state compact"><h2>还没有回测结果。</h2><p>输入本地 ZIP pattern 后提交，页面会直接运行历史回测。</p></article>'

    content = f"""
      <section class="control-panel">
        {error_html}
        <form method="get" action="/backtest" class="backtest-form">
          <label class="full-span">
            <span>Archive Patterns</span>
            <textarea name="archives" rows="4" placeholder="例如：data/spot/monthly/klines/*/4h/*.zip">{archive_value}</textarea>
          </label>
          <label><span>Lookback Bars</span><input type="number" min="60" name="lookback_bars" value="{int(params['lookback_bars'])}" /></label>
          <label><span>Score Threshold</span><input type="number" step="0.1" name="score_threshold" value="{float(params['score_threshold']):.1f}" /></label>
          <label><span>Holding Periods</span><input type="text" name="holding_periods" value="{escape(str(params['holding_periods']))}" /></label>
          <label><span>Portfolio Top N</span><input type="number" min="0" name="portfolio_top_n" value="{int(params['portfolio_top_n'])}" /></label>
          <label><span>Cooldown Bars</span><input type="number" min="0" name="cooldown_bars" value="{int(params['cooldown_bars'])}" /></label>
          <label><span>Stop Loss %</span><input type="number" step="0.1" name="stop_loss_pct" value="{float(params['stop_loss_pct']):.1f}" /></label>
          <label><span>Take Profit %</span><input type="number" step="0.1" name="take_profit_pct" value="{float(params['take_profit_pct']):.1f}" /></label>
          <label><span>Max Holding Bars</span><input type="number" min="1" name="max_holding_bars" value="{int(params['max_holding_bars'])}" /></label>
          <label><span>Fee bps</span><input type="number" step="0.1" name="fee_bps" value="{float(params['fee_bps']):.1f}" /></label>
          <label><span>Fee Model</span><select name="fee_model">{''.join(_option(item, str(params['fee_model'])) for item in ['flat', 'maker_taker'])}</select></label>
          <label><span>Fee Source</span><select name="fee_source">{''.join(_option(item, str(params['fee_source'])) for item in ['manual', 'account', 'symbol'])}</select></label>
          <label><span>Maker Fee bps</span><input type="number" step="0.1" name="maker_fee_bps" value="{float(params['maker_fee_bps']):.1f}" /></label>
          <label><span>Taker Fee bps</span><input type="number" step="0.1" name="taker_fee_bps" value="{float(params['taker_fee_bps']):.1f}" /></label>
          <label><span>Entry Fee Role</span><select name="entry_fee_role">{''.join(_option(item, str(params['entry_fee_role'])) for item in ['maker', 'taker'])}</select></label>
          <label><span>Exit Fee Role</span><select name="exit_fee_role">{''.join(_option(item, str(params['exit_fee_role'])) for item in ['maker', 'taker'])}</select></label>
          <label><span>Fee Discount %</span><input type="number" step="0.1" name="fee_discount_pct" value="{float(params['fee_discount_pct']):.1f}" /></label>
          <label class="inline-check"><input type="checkbox" name="no_binance_discount" {"checked" if params["no_binance_discount"] else ""} /><span>Disable Binance discount</span></label>
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
          <label class="inline-check"><input type="checkbox" name="no_kdj_confirmation" {"checked" if params["no_kdj_confirmation"] else ""} /><span>Disable KDJ confirmation</span></label>
          <button type="submit">运行回测</button>
        </form>
        <p class="helper-text">
          页面会直接读取你本机上的 Binance public-data ZIP。支持 glob pattern、多个 pattern 换行，以及组合层 top N 回测。
        </p>
      </section>

      <section class="section-block">
        <div class="section-heading">
          <h2>Portfolio</h2>
          <p>先看组合，再看各币种明细。</p>
        </div>
        <div class="portfolio-grid">{portfolio_html}</div>
      </section>

      <section class="section-block">
        <div class="section-heading">
          <h2>Series</h2>
          <p>每个币种各自的交易、收益和资金曲线。</p>
        </div>
        <div class="backtest-grid">{series_html}</div>
      </section>
    """

    return _layout(
        page_title="Binance Signal Backtest",
        active_page="backtest",
        hero_title="把本地 Binance 历史 K 线直接拉进页面里回测。",
        hero_text="同一页里调整分数阈值、止盈止损、滑点模型和组合仓位约束，直接看单币种与组合结果。",
        hero_right=hero_right,
        content=content,
    )
