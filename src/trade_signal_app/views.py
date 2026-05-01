from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from .presets import get_backtest_preset


def _option(value: str, selected: str) -> str:
    is_selected = " selected" if value == selected else ""
    return f'<option value="{escape(value)}"{is_selected}>{escape(value)}</option>'


def _layout(*, page_title: str, active_page: str, hero_title: str, hero_text: str, hero_right: str, content: str) -> str:
    terminal_active = "nav-link active" if active_page == "terminal" else "nav-link"
    scan_active = "nav-link active" if active_page == "scan" else "nav-link"
    backtest_active = "nav-link active" if active_page == "backtest" else "nav-link"
    trading_active = "nav-link active" if active_page == "trading" else "nav-link"
    settings_active = "nav-link active" if active_page == "settings" else "nav-link"
    page_label = {
        "scan": "SIGNAL DESK",
        "backtest": "STRATEGY LAB",
        "trading": "AUTO TRADE",
        "terminal": "COMMAND CENTER",
        "settings": "OPS CONSOLE",
    }.get(
        active_page,
        "AI TRADE",
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(page_title)}</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='10' fill='%2307090a'/%3E%3Cpath d='M18 45 28 19l7 16 4-9 7 19' fill='none' stroke='%2350d7e8' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main class="page-shell">
      <header class="platform-header">
        <a class="brand-lockup" href="/">
          <span class="brand-mark">AT</span>
          <span>
            <strong>AI Trade Terminal</strong>
            <small>{escape(page_label)}</small>
          </span>
        </a>
        <nav class="top-nav" aria-label="Primary">
          <a class="{terminal_active}" href="/terminal"><span>Command</span><small>总控台</small></a>
          <a class="{scan_active}" href="/"><span>Signal Desk</span><small>实时扫描</small></a>
          <a class="{backtest_active}" href="/backtest"><span>Strategy Lab</span><small>历史回测</small></a>
          <a class="{trading_active}" href="/trading"><span>Auto Trade</span><small>自动量化</small></a>
          <a class="{settings_active}" href="/settings"><span>Ops Console</span><small>运行配置</small></a>
        </nav>
        <div class="session-status" aria-label="Runtime status">
          <span>LOCAL</span>
          <strong>Binance Spot</strong>
        </div>
      </header>

      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">{escape(page_label)}</p>
          <h1>{escape(hero_title)}</h1>
          <p class="hero-text">{escape(hero_text)}</p>
          <div class="platform-ribbon">
            <span>Market Intelligence</span>
            <span>Signal Scoring</span>
            <span>Portfolio Backtest</span>
            <span>Runtime Vault</span>
          </div>
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


def _terminal_card(title: str, value: str, subtitle: str, accent: str = "") -> str:
    return f"""
      <article class="terminal-kpi {escape(accent)}">
        <span>{escape(title)}</span>
        <strong>{escape(value)}</strong>
        <small>{escape(subtitle)}</small>
      </article>
    """


def _terminal_rows(items: list[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    if not items:
        return '<p class="helper-text">暂无数据。配置本地 CSV 或外部数据源后会自动显示。</p>'
    header = "".join(f"<th>{escape(label)}</th>" for label, _ in columns)
    rows = []
    for item in items:
        cells = "".join(f"<td>{escape(_format_cell(item.get(key)))}</td>" for _, key in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="data-table terminal-table"><tr>{header}</tr><tbody>{"".join(rows)}</tbody></table>'


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        return f"{value:.2f}"
    if isinstance(value, list):
        return " / ".join(str(item) for item in value[:3])
    return str(value)


def _terminal_system_layers() -> str:
    layers = [
        ("接入层", "Binance API", "OKX Ready", "Twitter/X", "On-chain CSV", "OpenAI"),
        ("策略层", "信号评分", "趋势突破", "量价压力", "跨市价差", "策略命中"),
        ("执行层", "Paper", "Live Guard", "order/test", "仓位状态", "风控阈值"),
        ("数据层", "行情", "社区情报", "链上异动", "持仓", "交易日志"),
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


def render_terminal_page(snapshot: dict[str, object]) -> str:
    intel_items = snapshot["intel_items"]
    twitter_accounts = snapshot["twitter_accounts"]
    onchain_events = snapshot["onchain_events"]
    spreads = snapshot["spreads"]
    strategy_hits = snapshot["strategy_hits"]
    llm = snapshot["llm_insight"]
    risk = snapshot["execution_risk"]
    platform = snapshot["platform"]
    hero_right = f"""
      {_terminal_card("扫描标的", str(int(snapshot["scanned_symbols"])), "Binance Spot Universe", "cyan")}
      {_terminal_card("策略命中", str(len(strategy_hits)), "score / volume / pressure", "green")}
      {_terminal_card("执行风控", str(risk["status"]).upper(), f'risk {float(risk["risk_score"]):.1f}', "amber")}
      {_terminal_card("可执行候选", str(len(risk["allowed_symbols"])), f'blocked {len(risk["blocked_symbols"])}', "green")}
    """
    content = f"""
      <section class="terminal-shell">
        <aside class="terminal-sidebar">
          <div class="terminal-brand-block">
            <strong>BINANCE</strong>
            <span>OKX Ready</span>
          </div>
          <div class="terminal-menu">
            <span class="active">控制台</span>
            <span>交易市场</span>
            <span>社区情报</span>
            <span>链上监控</span>
            <span>价差分析</span>
            <span>策略命中</span>
            <span>自动交易</span>
            <span>风险控制</span>
          </div>
        </aside>
        <div class="terminal-main">
          <section class="terminal-grid">
            <article class="terminal-panel wide">
              <div class="section-heading">
                <h2>系统架构</h2>
                <p>交易所、社区、链上、策略与执行层统一监控。</p>
              </div>
              <div class="terminal-layers">{_terminal_system_layers()}</div>
            </article>
            <article class="terminal-panel wide">
              <div class="section-heading">
                <h2>功能实现状态</h2>
                <p>架构组件、API 入口和配置状态。</p>
              </div>
              {_terminal_rows(platform["components"], [("Layer", "layer"), ("Name", "name"), ("Status", "status"), ("Capability", "capability"), ("Endpoint", "endpoint")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>交易账户概览</h2>
                <p>模拟交易和真实交易账户状态。</p>
              </div>
              {_terminal_rows(platform["accounts"], [("Exchange", "exchange"), ("Mode", "mode"), ("Status", "status"), ("Positions", "open_positions"), ("Exposure", "quote_exposure")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>大模型分析</h2>
                <p>{escape(str(llm["provider"]))} / {escape(str(llm["model"]))} / {escape(str(llm["status"]))}</p>
              </div>
              <p class="terminal-insight">{escape(str(llm["summary"]))}</p>
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>执行前风控</h2>
                <p>{escape(str(risk["summary"]))}</p>
              </div>
              <div class="terminal-risk-board">
                <div class="mini-stat"><span>Status</span><strong>{escape(str(risk["status"]))}</strong></div>
                <div class="mini-stat"><span>Risk Score</span><strong>{float(risk["risk_score"]):.1f}</strong></div>
                <div class="mini-stat"><span>Allowed</span><strong>{len(risk["allowed_symbols"])}</strong></div>
                <div class="mini-stat"><span>Blocked</span><strong>{len(risk["blocked_symbols"])}</strong></div>
              </div>
              {_terminal_rows([{"symbol": symbol, "reason": reason} for symbol, reason in dict(risk["blocked_symbols"]).items()], [("Symbol", "symbol"), ("Reason", "reason")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>交易所与热门情报</h2>
                <p>公告、新闻、社区热度与信号引擎聚合。</p>
              </div>
              {_terminal_rows(intel_items, [("Source", "source"), ("Symbol", "symbol"), ("Title", "title"), ("Severity", "severity")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>Twitter 账户监控</h2>
                <p>运行配置中的 tracked accounts。</p>
              </div>
              {_terminal_rows(twitter_accounts, [("Account", "username"), ("Focus", "focus"), ("Mode", "mode"), ("Status", "status")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>链上异动</h2>
                <p>大额转账、交易所流入流出和量能代理。</p>
              </div>
              {_terminal_rows(onchain_events, [("Chain", "chain"), ("Symbol", "symbol"), ("Type", "event_type"), ("USD", "amount_usd"), ("Direction", "direction")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>现货 / 合约价差</h2>
                <p>用于套利、对冲和资金费率观察。</p>
              </div>
              {_terminal_rows(spreads, [("Symbol", "symbol"), ("Spot", "spot_exchange"), ("Futures", "futures_exchange"), ("Spread bps", "spread_bps"), ("Direction", "direction")])}
            </article>
            <article class="terminal-panel wide">
              <div class="section-heading">
                <h2>策略命中</h2>
                <p>自动交易前的候选池和执行意图。</p>
              </div>
              {_terminal_rows(strategy_hits, [("Symbol", "symbol"), ("Strategy", "strategy"), ("Score", "score"), ("Grade", "grade"), ("Action", "action"), ("Reasons", "reasons")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>策略目录</h2>
                <p>已实现策略、触发条件和执行方式。</p>
              </div>
              {_terminal_rows(platform["strategies"], [("ID", "strategy_id"), ("Name", "name"), ("Status", "status"), ("Trigger", "trigger"), ("Execution", "execution")])}
            </article>
            <article class="terminal-panel">
              <div class="section-heading">
                <h2>风险规则</h2>
                <p>执行层硬性约束和保护条件。</p>
              </div>
              {_terminal_rows(platform["risk_rules"], [("Rule", "name"), ("Status", "status"), ("Threshold", "threshold"), ("Action", "action")])}
            </article>
            <article class="terminal-panel wide">
              <div class="section-heading">
                <h2>交易日志</h2>
                <p>自动交易执行、跳过、阻断和下单事件。</p>
              </div>
              {_terminal_rows(platform["recent_events"], [("Time", "created_at"), ("Action", "action"), ("Symbol", "symbol"), ("Status", "status"), ("Message", "message")])}
            </article>
          </section>
        </div>
      </section>
    """
    return _layout(
        page_title="AI Trade Command Center",
        active_page="terminal",
        hero_title="交易所、社区、链上、价差和策略执行的统一总控台。",
        hero_text="将关键交易所信息、热门社区情报、Twitter 账号、链上异动、现货合约价差和策略命中集中分析，并可交给自动交易引擎执行。",
        hero_right=hero_right,
        content=content,
    )


def _trading_position_rows(positions: list[dict[str, object]]) -> str:
    if not positions:
        return '<p class="helper-text">当前没有自动交易持仓。</p>'
    rows = []
    for position in positions:
        rows.append(
            f"""
            <tr>
              <td>{escape(str(position["symbol"]))}</td>
              <td>{float(position["quantity"]):.8f}</td>
              <td>{float(position["entry_price"]):.8f}</td>
              <td>{float(position["quote_notional"]):.2f}</td>
              <td>{float(position["score"]):.1f} / {escape(str(position["grade"]))}</td>
              <td>{float(position["stop_price"]):.8f}</td>
              <td>{float(position["take_profit_price"]):.8f}</td>
              <td>{escape(str(position["mode"]))}</td>
            </tr>
            """
        )
    return f"""
      <table class="data-table">
        <tr>
          <th>Symbol</th>
          <th>Qty</th>
          <th>Entry</th>
          <th>Notional</th>
          <th>Signal</th>
          <th>Stop</th>
          <th>Take Profit</th>
          <th>Mode</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _trading_event_rows(events: list[dict[str, object]]) -> str:
    if not events:
        return '<p class="helper-text">还没有本次执行事件。点击运行后会显示买入、卖出或跳过原因。</p>'
    rows = []
    for event in events:
        rows.append(
            f"""
            <tr>
              <td>{escape(str(event["created_at"]))}</td>
              <td>{escape(str(event["action"]))}</td>
              <td>{escape(str(event["symbol"]))}</td>
              <td>{escape(str(event["status"]))}</td>
              <td>{escape(str(event["message"]))}</td>
              <td>{'' if event.get("score") is None else f'{float(event["score"]):.1f}'}</td>
              <td>{'' if event.get("quote_notional") is None else f'{float(event["quote_notional"]):.2f}'}</td>
            </tr>
            """
        )
    return f"""
      <table class="data-table">
        <tr>
          <th>Time</th>
          <th>Action</th>
          <th>Symbol</th>
          <th>Status</th>
          <th>Message</th>
          <th>Score</th>
          <th>Notional</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def render_trading_page(
    *,
    config: dict[str, object],
    positions: list[dict[str, object]],
    events: list[dict[str, object]],
) -> str:
    exposure = sum(float(position["quote_notional"]) for position in positions)
    hero_right = f"""
      <div class="stat-card">
        <span>Auto Engine</span>
        <strong>{"On" if config["enabled"] else "Off"}</strong>
        <small>{escape(str(config["mode"]))} mode</small>
      </div>
      <div class="stat-card">
        <span>Open Positions</span>
        <strong>{len(positions)}</strong>
        <small>max {int(config["max_open_positions"])}</small>
      </div>
      <div class="stat-card">
        <span>Exposure</span>
        <strong>{exposure:.0f}</strong>
        <small>limit {float(config["max_total_quote_exposure"]):.0f}</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        <form method="post" action="/trading/run" class="trading-command">
          <div>
            <h2>Execution Loop</h2>
            <p class="helper-text">运行一次会扫描当前市场、检查止盈止损、再按分数阈值打开新仓。paper 模式只写入本地持仓；live 模式会被环境变量和 order/test 双重保护。</p>
          </div>
          <button type="submit">运行一次自动交易</button>
        </form>
        <div class="mini-stat-grid compact-grid trading-risk-grid">
          <div class="mini-stat"><span>Score Threshold</span><strong>{float(config["score_threshold"]):.1f}</strong></div>
          <div class="mini-stat"><span>Order Qty</span><strong>{float(config["quote_order_qty"]):.2f}</strong></div>
          <div class="mini-stat"><span>Stop Loss</span><strong>{float(config["stop_loss_pct"]):.1f}%</strong></div>
          <div class="mini-stat"><span>Take Profit</span><strong>{float(config["take_profit_pct"]):.1f}%</strong></div>
        </div>
      </section>

      <section class="section-block">
        <div class="section-heading">
          <h2>Positions</h2>
          <p>自动交易状态保存在本机 <code>data/trading_state.json</code>。</p>
        </div>
        <article class="portfolio-card table-shell">{_trading_position_rows(positions)}</article>
      </section>

      <section class="section-block">
        <div class="section-heading">
          <h2>Execution Events</h2>
          <p>本次运行的下单、风控和跳过原因。</p>
        </div>
        <article class="backtest-card table-shell">{_trading_event_rows(events)}</article>
      </section>
    """
    return _layout(
        page_title="AI Trade Auto Execution",
        active_page="trading",
        hero_title="把预测信号接入自动量化执行循环。",
        hero_text="系统会根据实时评分、量能、买盘压力和持仓风控生成订单意图，并在 paper 或受保护的 live 模式下执行。",
        hero_right=hero_right,
        content=content,
    )


def render_settings_page(
    *,
    params: dict[str, object],
    status: dict[str, object],
    message: str | None,
    error: str | None,
    import_payload_text: str | None,
) -> str:
    notices = []
    if message:
        notices.append(f'<div class="notice notice-success">{escape(message)}</div>')
    if error:
        notices.append(f'<div class="notice notice-error">{escape(error)}</div>')

    tracked_accounts = "\n".join(str(item) for item in params["x_tracked_accounts"])
    import_template = import_payload_text or ""
    hero_right = f"""
      <div class="stat-card">
        <span>Binance Auth</span>
        <strong>{"On" if status["binance_auth_configured"] else "Off"}</strong>
        <small>{escape(str(status["binance_auth_label"]))}</small>
      </div>
      <div class="stat-card">
        <span>OKX Auth</span>
        <strong>{"On" if status["okx_auth_configured"] else "Off"}</strong>
        <small>cross-exchange ready</small>
      </div>
      <div class="stat-card">
        <span>X / Reddit</span>
        <strong>{"On" if status["x_auth_configured"] else "Mixed"}</strong>
        <small>{int(status["tracked_account_count"])} tracked accounts</small>
      </div>
      <div class="stat-card">
        <span>Storage</span>
        <strong>{escape(str(status["storage_mode"]))}</strong>
        <small>{"已启用口令保护" if str(status["storage_mode"]) == "Encrypted" else "配置保存到本地 JSON"}</small>
      </div>
      <div class="stat-card">
        <span>Auto Trade</span>
        <strong>{"On" if status["autotrade_enabled"] else "Off"}</strong>
        <small>{escape(str(status["autotrade_mode"]))} execution</small>
      </div>
      <div class="stat-card">
        <span>Intelligence</span>
        <strong>{"On" if status["intelligence_enabled"] else "Off"}</strong>
        <small>{"LLM enabled" if status["llm_enabled"] else "local rules"}</small>
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
          <label><span>Binance API Key</span><input type="password" name="binance_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>Binance API Secret</span><input type="password" name="binance_api_secret" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>Binance RecvWindow</span><input type="number" step="1" min="1" name="binance_recv_window_ms" value="{float(params['binance_recv_window_ms']):.0f}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_binance_auth" /><span>Clear Binance auth</span></label>
          <label><span>OKX API Key</span><input type="password" name="okx_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>OKX API Secret</span><input type="password" name="okx_api_secret" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>OKX Passphrase</span><input type="password" name="okx_api_passphrase" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_okx_auth" /><span>Clear OKX auth</span></label>
          <label><span>X Bearer Token</span><input type="password" name="x_bearer_token" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>Community Provider</span><select name="community_provider">{''.join(_option(item, str(params['community_provider'])) for item in ['auto', 'x', 'csv', 'news', 'telegram', 'reddit', 'x,csv', 'x,news', 'x,telegram', 'x,reddit', 'csv,news', 'csv,telegram', 'csv,reddit', 'news,telegram', 'news,reddit', 'telegram,reddit', 'x,csv,news', 'x,csv,telegram', 'x,csv,reddit', 'x,news,telegram', 'x,news,reddit', 'x,telegram,reddit', 'csv,news,telegram', 'csv,news,reddit', 'csv,telegram,reddit', 'news,telegram,reddit', 'x,csv,news,telegram', 'x,csv,news,reddit', 'x,csv,telegram,reddit', 'x,news,telegram,reddit', 'csv,news,telegram,reddit', 'x,csv,news,telegram,reddit'])}</select></label>
          <label><span>X API Base URL</span><input type="text" name="x_api_base_url" value="{escape(str(params['x_api_base_url']))}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_x_auth" /><span>Clear X auth</span></label>

          <div class="settings-heading full-span">
            <h2>Intelligence & LLM</h2>
            <p>总控台会聚合交易所情报、Twitter 账号、链上异动、现货/合约价差和策略命中。未配置 OpenAI 时使用本地规则分析。</p>
          </div>
          <label class="inline-check"><input type="checkbox" name="intelligence_enabled" {"checked" if params["intelligence_enabled"] else ""} /><span>Enable intelligence center</span></label>
          <label class="inline-check"><input type="checkbox" name="intelligence_llm_enabled" {"checked" if params["intelligence_llm_enabled"] else ""} /><span>Enable LLM analysis</span></label>
          <label><span>OpenAI API Key</span><input type="password" name="openai_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>OpenAI Model</span><input type="text" name="intelligence_openai_model" value="{escape(str(params['intelligence_openai_model']))}" /></label>
          <label><span>Min Intel Severity</span><input type="number" step="0.1" min="0" max="100" name="intelligence_min_intel_severity" value="{float(params['intelligence_min_intel_severity']):.1f}" /></label>
          <label><span>Min Spread bps</span><input type="number" step="0.1" min="0" name="intelligence_min_spread_bps" value="{float(params['intelligence_min_spread_bps']):.1f}" /></label>
          <label><span>Whale Threshold USD</span><input type="number" step="100000" min="0" name="intelligence_whale_transfer_threshold_usd" value="{float(params['intelligence_whale_transfer_threshold_usd']):.0f}" /></label>

          <div class="settings-heading full-span">
            <h2>Twitter Intel</h2>
            <p>账号列表支持一行一个用户名。`blend` 会把普通舆情和指定账号情报按权重混合，`only` 只看指定账号。本地新闻与 Telegram 情报可分别通过 <code>data/news_sentiment.csv</code> 和 <code>data/telegram_sentiment.csv</code> 参与混合。</p>
          </div>
          <label><span>X Window Hours</span><input type="number" min="1" name="x_recent_window_hours" value="{int(params['x_recent_window_hours'])}" /></label>
          <label><span>X Max Results</span><input type="number" min="10" max="100" name="x_recent_max_results" value="{int(params['x_recent_max_results'])}" /></label>
          <label><span>X Language</span><input type="text" name="x_language" value="{escape(str(params['x_language']))}" /></label>
          <label><span>Account Mode</span><select name="x_account_mode">{''.join(_option(item, str(params['x_account_mode'])) for item in ['off', 'blend', 'only'])}</select></label>
          <label><span>Account Weight %</span><input type="number" step="0.1" min="0" max="100" name="x_account_weight_pct" value="{float(params['x_account_weight_pct']):.1f}" /></label>
          <label class="full-span"><span>Tracked Accounts</span><textarea name="x_tracked_accounts" rows="5" placeholder="@lookonchain&#10;wu_blockchain&#10;TheBlock__">{escape(tracked_accounts)}</textarea></label>
          <label><span>Reddit API Base URL</span><input type="text" name="reddit_api_base_url" value="{escape(str(params['reddit_api_base_url']))}" /></label>
          <label><span>Reddit Window Hours</span><input type="number" min="1" name="reddit_recent_window_hours" value="{int(params['reddit_recent_window_hours'])}" /></label>
          <label><span>Reddit Max Results</span><input type="number" min="5" max="100" name="reddit_max_results" value="{int(params['reddit_max_results'])}" /></label>
          <label class="full-span"><span>Reddit User-Agent</span><input type="text" name="reddit_user_agent" value="{escape(str(params['reddit_user_agent']))}" /></label>

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
            <h2>Auto Trade Defaults</h2>
            <p>自动交易会根据实时扫描分数生成市价单。默认 paper 模式只记录模拟持仓；live 模式还需要服务端环境变量确认才会提交真实订单。</p>
          </div>
          <label class="inline-check"><input type="checkbox" name="autotrade_enabled" {"checked" if params["autotrade_enabled"] else ""} /><span>Enable auto trade</span></label>
          <label><span>Execution Mode</span><select name="autotrade_mode">{''.join(_option(item, str(params['autotrade_mode'])) for item in ['paper', 'live'])}</select></label>
          <label><span>Quote Order Qty</span><input type="number" step="0.01" min="0.01" name="autotrade_quote_order_qty" value="{float(params['autotrade_quote_order_qty']):.2f}" /></label>
          <label><span>Max Open Positions</span><input type="number" min="1" name="autotrade_max_open_positions" value="{int(params['autotrade_max_open_positions'])}" /></label>
          <label><span>Max Total Exposure</span><input type="number" step="0.01" min="0.01" name="autotrade_max_total_quote_exposure" value="{float(params['autotrade_max_total_quote_exposure']):.2f}" /></label>
          <label><span>Score Threshold</span><input type="number" step="0.1" min="0" max="100" name="autotrade_score_threshold" value="{float(params['autotrade_score_threshold']):.1f}" /></label>
          <label><span>Min Volume Ratio</span><input type="number" step="0.01" min="0" name="autotrade_min_volume_ratio" value="{float(params['autotrade_min_volume_ratio']):.2f}" /></label>
          <label><span>Min Buy Pressure</span><input type="number" step="0.01" min="0" max="1" name="autotrade_min_buy_pressure" value="{float(params['autotrade_min_buy_pressure']):.2f}" /></label>
          <label><span>Stop Loss %</span><input type="number" step="0.1" min="0.1" name="autotrade_stop_loss_pct" value="{float(params['autotrade_stop_loss_pct']):.1f}" /></label>
          <label><span>Take Profit %</span><input type="number" step="0.1" min="0.1" name="autotrade_take_profit_pct" value="{float(params['autotrade_take_profit_pct']):.1f}" /></label>
          <label><span>Cooldown Minutes</span><input type="number" min="0" name="autotrade_cooldown_minutes" value="{int(params['autotrade_cooldown_minutes'])}" /></label>
          <label class="inline-check"><input type="checkbox" name="autotrade_order_test_only" {"checked" if params["autotrade_order_test_only"] else ""} /><span>Use Binance order/test</span></label>

          <div class="settings-heading full-span">
            <h2>Backtest Defaults</h2>
            <p>这些值会作为回测页的默认策略参数。你可以把实盘偏好先固定下来，再按每次任务微调。</p>
          </div>
          <label><span>Default Preset</span><select name="backtest_preset">{''.join(_option(item, str(params['backtest_preset'])) for item in ['custom', 'balanced_swing', 'breakout_aggressive', 'portfolio_rotation', 'btc_cycle_trend', 'btc_core_trading', 'btc_compounding_risk_off'])}</select></label>
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
        <div class="settings-transfer">
          <div class="settings-transfer-card">
            <div class="settings-heading">
              <h2>Config Export</h2>
              <p>模板导出默认会清空密钥字段，适合备份参数或跨机器迁移。需要完整备份时再导出包含密钥的版本。</p>
            </div>
            <div class="action-row">
              <a class="action-link" href="/api/settings/export">导出模板 JSON</a>
              <a class="action-link" href="/api/settings/export?include_secrets=1">导出完整配置</a>
            </div>
          </div>
          <form method="post" action="/settings/import" class="settings-transfer-card import-form">
            <div class="settings-heading">
              <h2>Config Import</h2>
              <p>支持粘贴导出的模板 JSON。若模板中的密钥为空，当前已保存的密钥会自动保留。</p>
            </div>
            <label>
              <span>Template JSON</span>
              <textarea name="config_template" rows="10" placeholder='{{"kind":"runtime_config_template","version":1,"config":{{...}}}}'>{escape(import_template)}</textarea>
            </label>
            <button type="submit">导入配置模板</button>
          </form>
        </div>
        <p class="helper-text">
          当前实现支持本地 JSON 存储；如果设置环境变量 <code>RUNTIME_CONFIG_PASSPHRASE</code>，后续保存会自动写成加密格式。未设置时仍保持明文 JSON，适合单机研究使用。
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


def _backtest_overview(
    *,
    params: dict[str, object],
    series_reports: list[dict[str, object]],
    portfolio_reports: list[dict[str, object]],
) -> str:
    export_query = _build_backtest_export_query(params)
    total_series_trades = sum(int(report["signal_count"]) for report in series_reports)
    total_portfolio_batches = sum(int(report["batch_count"]) for report in portfolio_reports)
    best_series = max((float(report["final_equity"]) for report in series_reports), default=0.0)
    best_portfolio = max((float(report["final_equity"]) for report in portfolio_reports), default=0.0)
    return f"""
      <section class="overview-grid">
        <article class="overview-card">
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
          </div>
        </article>
        <article class="overview-card">
          <div class="section-heading">
            <div>
              <h2>Series Equity Rank</h2>
              <p>按最终权益对单币种结果做快速比较。</p>
            </div>
          </div>
          {_summary_bars(sorted(series_reports, key=lambda item: float(item["final_equity"]), reverse=True), label_key="symbol")}
        </article>
        <article class="overview-card">
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
    presets: list[dict[str, object]],
) -> str:
    archive_value = escape(str(params["archives"]))
    current_preset = get_backtest_preset(str(params["preset"]))
    preset_options = "".join(_option(str(preset["preset_id"]), str(params["preset"])) for preset in presets)
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
          <label><span>Preset</span><select name="preset">{preset_options}</select></label>
          <div class="preset-note">
            <strong>{escape(current_preset.label)}</strong>
            <span>{escape(current_preset.description)}</span>
            <a href="/api/backtest/presets">查看模板清单</a>
          </div>
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

      {_backtest_overview(params=params, series_reports=series_reports, portfolio_reports=portfolio_reports)}

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
