from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from .presets import get_backtest_preset

SUPPORTED_LANGUAGES = {"zh", "en"}


def normalize_language(lang: str | None) -> str:
    return "en" if str(lang or "").lower().startswith("en") else "zh"


def _text(lang: str, zh: str, en: str) -> str:
    return en if normalize_language(lang) == "en" else zh


def _url(path: str, lang: str) -> str:
    if normalize_language(lang) == "zh":
        return path
    delimiter = "&" if "?" in path else "?"
    return f"{path}{delimiter}lang=en"


def _hidden_lang_input(lang: str) -> str:
    if normalize_language(lang) == "zh":
        return ""
    return '<input type="hidden" name="lang" value="en" />'


def _language_switch(lang: str, current_path: str) -> str:
    active_lang = normalize_language(lang)
    zh_class = "active" if active_lang == "zh" else ""
    en_class = "active" if active_lang == "en" else ""
    return f"""
      <div class="language-switch" aria-label="Language">
        <a class="{zh_class}" href="{escape(current_path)}?lang=zh">中文</a>
        <a class="{en_class}" href="{escape(current_path)}?lang=en">English</a>
      </div>
    """


def _tool_icon(name: str) -> str:
    icons = {
        "snapshot": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16M7 4v16M17 4v16"/></svg>',
        "settings": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="m19.4 15-.7 1.3 1 2-1.4 1.4-2-1-1.3.7-.7 2.1h-2l-.7-2.1-1.3-.7-2 1-1.4-1.4 1-2-.7-1.3-2.1-.7v-2l2.1-.7.7-1.3-1-2 1.4-1.4 2 1 1.3-.7.7-2.1h2l.7 2.1 1.3.7 2-1 1.4 1.4-1 2 .7 1.3 2.1.7v2l-2.1.7Z"/></svg>',
        "alerts": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 3 20h18L12 4Z"/><path d="M12 9v5M12 17h.01"/></svg>',
    }
    return icons[name]


_VALUE_LABELS = {
    "zh": {
        "ready": "就绪",
        "ready_public": "公开数据就绪",
        "configured": "已配置",
        "token_missing": "缺少令牌",
        "fallback": "本地规则",
        "guarded": "受保护",
        "active": "启用",
        "disabled": "停用",
        "not_configured": "未配置",
        "paper_ready": "模拟就绪",
        "watch_only": "仅观察",
        "enabled": "已启用",
        "monitoring": "监控中",
        "guarding": "风控中",
        "clear": "低风险",
        "caution": "谨慎",
        "blocked": "已阻断",
        "paper": "模拟",
        "live": "实盘",
        "paper_filled": "模拟成交",
        "risk_blocked": "风控阻断",
        "test_accepted": "测试通过",
        "filled": "已成交",
        "rejected": "已拒绝",
        "skipped": "已跳过",
        "BUY": "买入",
        "SELL": "卖出",
        "SKIP": "跳过",
        "candidate_buy": "候选买入",
        "watch": "观察",
        "priority_watch": "优先观察",
        "local": "本地规则",
        "rules": "规则引擎",
        "ok": "正常",
        "openai": "OpenAI",
    },
    "en": {
        "ready": "Ready",
        "ready_public": "Public Data Ready",
        "configured": "Configured",
        "token_missing": "Token Missing",
        "fallback": "Local Fallback",
        "guarded": "Guarded",
        "active": "Active",
        "disabled": "Disabled",
        "not_configured": "Not Configured",
        "paper_ready": "Paper Ready",
        "watch_only": "Watch Only",
        "enabled": "Enabled",
        "monitoring": "Monitoring",
        "guarding": "Guarding",
        "clear": "Clear",
        "caution": "Caution",
        "blocked": "Blocked",
        "paper": "Paper",
        "live": "Live",
        "paper_filled": "Paper Filled",
        "risk_blocked": "Risk Blocked",
        "test_accepted": "Test Accepted",
        "filled": "Filled",
        "rejected": "Rejected",
        "skipped": "Skipped",
        "BUY": "Buy",
        "SELL": "Sell",
        "SKIP": "Skip",
        "candidate_buy": "Candidate Buy",
        "watch": "Watch",
        "priority_watch": "Priority Watch",
        "local": "Local",
        "rules": "Rules Engine",
        "ok": "OK",
        "openai": "OpenAI",
    },
}


_EN_VALUE_TRANSLATIONS = {
    "接入层": "Access Layer",
    "策略层": "Strategy Layer",
    "执行层": "Execution Layer",
    "数据层": "Data Layer",
    "风控层": "Risk Layer",
    "现货行情、账户费率、实盘市价单": "Spot market data, account fees, live market orders",
    "OKX 接入参数与后续跨交易所扩展": "OKX credentials and cross-exchange expansion",
    "热门社区和指定账号情报": "Community trends and tracked account intelligence",
    "链上异动、大额转账、交易所流入流出": "On-chain anomalies, large transfers, exchange flows",
    "综合指标分析和风险解释": "Composite signal analysis and risk explanation",
    "趋势、动量、量能、社区评分": "Trend, momentum, volume, and community scoring",
    "现货/合约价差和跨市场 basis": "Spot/futures spread and cross-market basis",
    "自动交易候选和策略命中": "Auto-trading candidates and strategy hits",
    "本地模拟交易和持仓状态": "Local paper trading and position state",
    "实盘环境变量、order/test 和密钥保护": "Live guardrails, order/test, and credential checks",
    "市价买入、卖出、客户端订单号": "Market buy/sell and client order IDs",
    "持仓、止损、止盈和冷却": "Positions, stop loss, take profit, and cooldown",
    "本地配置、模板导入导出、可选加密": "Local config, template import/export, optional encryption",
    "持仓和事件历史持久化": "Persistent positions and event history",
    "链上、价差、策略命中执行前阻断": "Pre-trade blocking from on-chain, basis, and strategy signals",
    "综合评分突破": "Composite Score Breakout",
    "量价压力策略": "Volume Pressure Strategy",
    "现货/合约价差策略": "Spot/Futures Basis Strategy",
    "链上大额异动风控": "On-chain Whale Guard",
    "paper/live 市价买入": "Paper/live market buy",
    "候选优先级提升": "Candidate priority boost",
    "套利/对冲观察": "Arbitrage/hedge watch",
    "阻断或降级自动开仓": "Block or downgrade automated entries",
    "最大持仓数": "Max Open Positions",
    "最大总敞口": "Max Total Exposure",
    "单仓止损": "Single-position Stop Loss",
    "单仓止盈": "Single-position Take Profit",
    "同标的冷却": "Symbol Cooldown",
    "实盘确认": "Live Confirmation",
    "仅校验不成交": "Validate only, no fill",
    "拒绝新开仓": "Reject new entries",
    "拒绝超额订单": "Reject over-limit orders",
    "触发平仓": "Trigger exit",
    "跳过重复开仓": "Skip duplicate entries",
    "阻断真实订单": "Block live orders",
    "阻断风险标的": "Block risky symbols",
    "智能执行风控": "Intelligent Execution Risk Gate",
    "模拟买入已记录。": "Paper buy recorded.",
    "模拟卖出已记录：stop_loss。": "Paper sell recorded: stop loss.",
    "模拟卖出已记录：take_profit。": "Paper sell recorded: take profit.",
}


def _display_value(value: object, lang: str) -> str:
    if isinstance(value, bool):
        return _text(lang, "是" if value else "否", "Yes" if value else "No")
    text = str(value)
    active_lang = normalize_language(lang)
    mapped = _VALUE_LABELS.get(active_lang, {}).get(text)
    if mapped:
        return mapped
    if active_lang == "en":
        return _EN_VALUE_TRANSLATIONS.get(text, text)
    return text


def _option(value: str, selected: str) -> str:
    is_selected = " selected" if value == selected else ""
    return f'<option value="{escape(value)}"{is_selected}>{escape(value)}</option>'


def _top_nav(active_page: str, lang: str) -> str:
    items = [
        ("terminal", _text(lang, "工作台", "Workspace"), _text(lang, "系统总览", "System Overview"), "/terminal"),
        ("backtest", _text(lang, "策略研究", "Strategy Research"), _text(lang, "历史回测", "Backtesting"), "/backtest"),
        ("scan", _text(lang, "回测分析", "Signal Analysis"), _text(lang, "实时扫描", "Live Signals"), "/"),
        ("trading", _text(lang, "交易执行", "Trade Execution"), _text(lang, "模拟/实盘", "Paper / Live"), "/trading"),
        ("risk", _text(lang, "风险管理", "Risk Management"), _text(lang, "执行风控", "Risk Gate"), "/terminal/risk"),
        ("settings", _text(lang, "系统管理", "System Admin"), _text(lang, "运行配置", "Runtime Config"), "/settings"),
    ]
    links = []
    for page_id, label, sublabel, href in items:
        active = " active" if page_id == active_page or (page_id == "risk" and active_page == "terminal") else ""
        links.append(
            f'<a class="nav-link{active}" href="{escape(_url(href, lang))}"><span>{escape(label)}</span><small>{escape(sublabel)}</small></a>'
        )
    return "".join(links)


def _sidebar_group(title: str, links: list[tuple[str, str]], lang: str, active_page: str, current_path: str) -> str:
    items = []
    current_path = current_path.split("?", 1)[0] or "/"
    for label, href in links:
        path = href.split("?", 1)[0]
        is_active = (
            path == current_path
            or (active_page == "terminal" and current_path == "/terminal" and path == "/terminal")
            or (active_page == "scan" and path == "/")
            or (active_page == "backtest" and path == "/backtest")
            or (active_page == "trading" and path == "/trading")
            or (active_page == "settings" and path == "/settings")
        )
        active = " active" if is_active else ""
        items.append(f'<a class="sidebar-link{active}" href="{escape(_url(href, lang))}"><span>{escape(label)}</span></a>')
    return f"""
      <div class="sidebar-group">
        <button type="button" class="sidebar-group-title">{escape(title)}<span></span></button>
        <div class="sidebar-links">{"".join(items)}</div>
      </div>
    """


def _app_sidebar(active_page: str, lang: str, current_path: str) -> str:
    return f"""
      <aside class="app-sidebar">
        <a class="sidebar-brand" href="{escape(_url('/terminal', lang))}">
          <span class="sidebar-logo">QT</span>
          <span>
            <strong>{_text(lang, "量化交易系统", "Quantitative Trading System")}</strong>
            <small>{_text(lang, "Quantitative Trading System", "Quant Platform")}</small>
          </span>
        </a>
        <nav class="sidebar-nav" aria-label="Sidebar">
          {_sidebar_group(_text(lang, "核心导航", "Core Navigation"), [
              (_text(lang, "工作台", "Workspace"), "/terminal"),
              (_text(lang, "信号扫描", "Signal Scanner"), "/"),
          ], lang, active_page, current_path)}
          {_sidebar_group(_text(lang, "数据中心", "Data Center"), [
              (_text(lang, "数据概览", "Data Overview"), "/terminal/market"),
              (_text(lang, "社区情报", "Community Intel"), "/terminal/community"),
              (_text(lang, "链上监控", "On-chain Monitor"), "/terminal/onchain"),
              (_text(lang, "价差分析", "Basis Analysis"), "/terminal/basis"),
          ], lang, active_page, current_path)}
          {_sidebar_group(_text(lang, "策略研究", "Strategy Research"), [
              (_text(lang, "策略命中", "Strategy Hits"), "/terminal/strategies"),
              (_text(lang, "回测分析", "Backtesting"), "/backtest"),
          ], lang, active_page, current_path)}
          {_sidebar_group(_text(lang, "交易执行", "Trade Execution"), [
              (_text(lang, "自动交易", "Auto Trading"), "/trading"),
              (_text(lang, "模拟账户", "Paper Account"), "/terminal/trading"),
              (_text(lang, "风险控制", "Risk Control"), "/terminal/risk"),
          ], lang, active_page, current_path)}
          {_sidebar_group(_text(lang, "系统管理", "System Admin"), [
              (_text(lang, "系统配置", "System Config"), "/settings"),
          ], lang, active_page, current_path)}
        </nav>
        <div class="sidebar-footer">
          <span>{_text(lang, "系统状态", "System Status")}</span>
          <strong>{_text(lang, "运行中", "Running")}</strong>
        </div>
      </aside>
    """


def _market_ticker(lang: str) -> str:
    labels = [
        ("BTC/USDT", "+1.56%"),
        ("ETH/USDT", "+2.34%"),
        ("BNB/USDT", "+1.12%"),
        ("SOL/USDT", "+3.45%"),
        ("XRP/USDT", "-0.23%"),
        ("IF2406", "+0.39%"),
    ]
    items = "".join(
        f'<span><strong>{escape(name)}</strong><em class="{"down" if value.startswith("-") else "up"}">{escape(value)}</em></span>'
        for name, value in labels
    )
    return f"""
      <footer class="market-ticker">
        <strong>{_text(lang, "市场行情", "Market Ticker")}</strong>
        <div>{items}</div>
        <a href="{escape(_url('/terminal/market', lang))}">{_text(lang, "更多", "More")}</a>
      </footer>
    """


def _layout(
    *,
    page_title: str,
    active_page: str,
    hero_title: str,
    hero_text: str,
    hero_right: str,
    content: str,
    lang: str = "zh",
    current_path: str = "/",
) -> str:
    active_lang = normalize_language(lang)
    page_label = {
        "scan": _text(active_lang, "信号工作台", "SIGNAL DESK"),
        "backtest": _text(active_lang, "策略实验室", "STRATEGY LAB"),
        "trading": _text(active_lang, "自动量化", "AUTO TRADE"),
        "terminal": _text(active_lang, "总控台", "COMMAND CENTER"),
        "settings": _text(active_lang, "运行配置", "OPS CONSOLE"),
    }.get(
        active_page,
        "AI TRADE",
    )
    html_lang = "en" if active_lang == "en" else "zh-CN"
    return f"""<!DOCTYPE html>
<html lang="{html_lang}">
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
    <main class="app-shell">
      {_app_sidebar(active_page, active_lang, current_path)}
      <section class="workspace">
        <header class="platform-header">
          <nav class="top-nav" aria-label="Primary">
            {_top_nav(active_page, active_lang)}
          </nav>
          <div class="top-actions" aria-label="Runtime tools">
            <a class="tool-button" href="{escape(_url('/api/terminal/snapshot', active_lang))}" title="Snapshot" aria-label="Snapshot">{_tool_icon("snapshot")}</a>
            <a class="tool-button" href="{escape(_url('/settings', active_lang))}" title="Settings" aria-label="Settings">{_tool_icon("settings")}</a>
            <span class="tool-button is-alert" title="Alerts" aria-label="3 alerts">{_tool_icon("alerts")}<em>3</em></span>
            {_language_switch(active_lang, current_path)}
            <div class="user-chip">
              <span>quant_admin</span>
              <small>{_text(active_lang, "超级管理员", "Super Admin")}</small>
            </div>
          </div>
        </header>

        <section class="hero dashboard-hero">
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
        {_market_ticker(active_lang)}
      </section>
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
    lang: str = "zh",
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    cards = "".join(_signal_card(signal) for signal in signals)
    if not cards:
        cards = f"""
        <article class="empty-state">
          <h2>{t("当前条件下没有足够强的候选币种。", "No sufficiently strong candidates under the current filters.")}</h2>
          <p>{t("可以适当降低最小成交额或增大候选数，再重新扫描。", "Lower minimum quote volume or increase the candidate pool, then scan again.")}</p>
        </article>
        """

    options = "".join(_option(interval, str(params["interval"])) for interval in intervals)
    hero_right = f"""
      <div class="stat-card">
        <span>{t("扫描范围", "Scan Universe")}</span>
        <strong>{int(summary["scanned_symbols"])}</strong>
        <small>{escape(str(summary["quote_asset"]))} {t("现货交易对", "spot pairs")}</small>
      </div>
      <div class="stat-card">
        <span>{t("返回信号", "Returned Signals")}</span>
        <strong>{int(summary["returned_signals"])}</strong>
        <small>{escape(str(summary["interval"]))} {t("周期", "interval")}</small>
      </div>
      <div class="stat-card">
        <span>{t("最小成交额", "Min Quote Volume")}</span>
        <strong>{float(summary["min_quote_volume"]) / 1_000_000:.0f}M</strong>
        <small>Quote Volume</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        <form method="get" class="filters">
          {_hidden_lang_input(active_lang)}
          <label>
            <span>{t("计价币", "Quote Asset")}</span>
            <input type="text" name="quote_asset" value="{escape(str(params["quote_asset"]))}" />
          </label>
          <label>
            <span>{t("周期", "Interval")}</span>
            <select name="interval">{options}</select>
          </label>
          <label>
            <span>{t("候选数", "Candidate Pool")}</span>
            <input type="number" name="candidate_pool" min="5" max="40" value="{int(params["candidate_pool"])}" />
          </label>
          <label>
            <span>{t("最小成交额", "Min Quote Volume")}</span>
            <input type="number" name="min_quote_volume" min="1000000" step="1000000" value="{int(params["min_quote_volume"])}" />
          </label>
          <label>
            <span>{t("最小成交笔数", "Min Trades")}</span>
            <input type="number" name="min_trade_count" min="100" step="100" value="{int(params["min_trade_count"])}" />
          </label>
          <button type="submit">{t("刷新信号", "Refresh Signals")}</button>
        </form>
        <p class="helper-text">
          {t("数据来自 Binance Spot 市场接口。社区热度支持 X/Twitter Bearer Token 和本地", "Market data comes from Binance Spot APIs. Community heat supports X/Twitter Bearer Token and local")} <code>data/community_scores.csv</code>{t("，未配置时会自动忽略该维度。", "; this dimension is skipped when unconfigured.")}
        </p>
      </section>

      <section class="signal-grid">
        {cards}
      </section>
    """
    return _layout(
        page_title="Binance Signal Scanner",
        active_page="scan",
        hero_title=t("从高流动性币种里抓更像“可入手”的那一批。", "Find tradable candidates from high-liquidity spot markets."),
        hero_text=t("先用 24h 市场活跃度做初筛，再计算 RSI、EMA、MACD、KDJ、量能放大和可选的社区热度，输出一份偏实战的候选榜。", "Filter by 24h market activity, then score RSI, EMA, MACD, KDJ, volume expansion, buy pressure, and optional community heat."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/",
    )


def _terminal_card(title: str, value: str, subtitle: str, accent: str = "") -> str:
    return f"""
      <article class="terminal-kpi {escape(accent)}">
        <span>{escape(title)}</span>
        <strong>{escape(value)}</strong>
        <small>{escape(subtitle)}</small>
      </article>
    """


def _terminal_rows(items: list[dict[str, object]], columns: list[tuple[str, str]], *, lang: str = "zh") -> str:
    if not items:
        return f'<p class="helper-text">{escape(_text(lang, "暂无数据。配置本地 CSV 或外部数据源后会自动显示。", "No data yet. Configure local CSV or external data sources to populate this panel."))}</p>'
    header = "".join(f"<th>{escape(label)}</th>" for label, _ in columns)
    rows = []
    for item in items:
        cells = "".join(f"<td>{escape(_format_cell(item.get(key), lang))}</td>" for _, key in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="data-table terminal-table"><tr>{header}</tr><tbody>{"".join(rows)}</tbody></table>'


def _format_cell(value: object, lang: str = "zh") -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        return f"{value:.2f}"
    if isinstance(value, list):
        return " / ".join(_display_value(item, lang) for item in value[:3])
    return _display_value(value, lang)


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


def render_terminal_page(snapshot: dict[str, object], *, lang: str = "zh") -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    intel_items = snapshot["intel_items"]
    twitter_accounts = snapshot["twitter_accounts"]
    onchain_events = snapshot["onchain_events"]
    spreads = snapshot["spreads"]
    strategy_hits = snapshot["strategy_hits"]
    llm = snapshot["llm_insight"]
    risk = snapshot["execution_risk"]
    platform = snapshot["platform"]
    hero_right = f"""
      {_terminal_card(t("扫描标的", "Scanned Symbols"), str(int(snapshot["scanned_symbols"])), "Binance Spot Universe", "cyan")}
      {_terminal_card(t("策略命中", "Strategy Hits"), str(len(strategy_hits)), t("评分 / 量能 / 买压", "score / volume / pressure"), "green")}
      {_terminal_card(t("执行风控", "Execution Risk"), _display_value(risk["status"], active_lang).upper(), f'{t("风险分", "risk")} {float(risk["risk_score"]):.1f}', "amber")}
      {_terminal_card(t("可执行候选", "Allowed Candidates"), str(len(risk["allowed_symbols"])), f'{t("已阻断", "blocked")} {len(risk["blocked_symbols"])}', "green")}
    """
    panels = "".join(
        [
            _terminal_panel(t("系统架构", "System Architecture"), t("交易所、社区、链上、策略与执行层统一监控。", "Unified monitoring for exchange, community, on-chain, strategy, and execution layers."), f'<div class="terminal-layers">{_terminal_system_layers(active_lang)}</div>', wide=True),
            _terminal_panel(t("功能实现状态", "Capability Status"), t("架构组件、API 入口和配置状态。", "Architecture components, API endpoints, and configuration state."), _terminal_rows(platform["components"], [(t("层级", "Layer"), "layer"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("能力", "Capability"), "capability"), (t("接口", "Endpoint"), "endpoint")], lang=active_lang), wide=True),
            _terminal_panel(t("交易账户概览", "Trading Accounts"), t("模拟交易和真实交易账户状态。", "Paper and live account state."), _terminal_rows(platform["accounts"], [(t("交易所", "Exchange"), "exchange"), (t("模式", "Mode"), "mode"), (t("状态", "Status"), "status"), (t("持仓数", "Positions"), "open_positions"), (t("敞口", "Exposure"), "quote_exposure")], lang=active_lang)),
            _terminal_panel(t("大模型分析", "LLM Analysis"), f'{escape(_display_value(llm["provider"], active_lang))} / {escape(_display_value(llm["model"], active_lang))} / {escape(_display_value(llm["status"], active_lang))}', f'<p class="terminal-insight">{escape(str(llm["summary"]))}</p>'),
            _terminal_panel(
                t("执行前风控", "Pre-trade Risk Gate"),
                str(risk["summary"]),
                f"""
                <div class="terminal-risk-board">
                  <div class="mini-stat"><span>{t("状态", "Status")}</span><strong>{escape(_display_value(risk["status"], active_lang))}</strong></div>
                  <div class="mini-stat"><span>{t("风险分", "Risk Score")}</span><strong>{float(risk["risk_score"]):.1f}</strong></div>
                  <div class="mini-stat"><span>{t("允许", "Allowed")}</span><strong>{len(risk["allowed_symbols"])}</strong></div>
                  <div class="mini-stat"><span>{t("阻断", "Blocked")}</span><strong>{len(risk["blocked_symbols"])}</strong></div>
                </div>
                {_terminal_rows([{"symbol": symbol, "reason": reason} for symbol, reason in dict(risk["blocked_symbols"]).items()], [(t("标的", "Symbol"), "symbol"), (t("原因", "Reason"), "reason")], lang=active_lang)}
                """,
            ),
            _terminal_panel(t("交易所与热门情报", "Exchange & Market Intelligence"), t("公告、新闻、社区热度与信号引擎聚合。", "Announcements, news, community heat, and signal-engine intelligence."), _terminal_rows(intel_items, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("标题", "Title"), "title"), (t("严重度", "Severity"), "severity")], lang=active_lang)),
            _terminal_panel(t("Twitter 账户监控", "Twitter Account Monitor"), t("运行配置中的 tracked accounts。", "Tracked accounts from runtime configuration."), _terminal_rows(twitter_accounts, [(t("账号", "Account"), "username"), (t("关注点", "Focus"), "focus"), (t("模式", "Mode"), "mode"), (t("状态", "Status"), "status")], lang=active_lang)),
            _terminal_panel(t("链上异动", "On-chain Events"), t("大额转账、交易所流入流出和量能代理。", "Large transfers, exchange flows, and volume-based proxies."), _terminal_rows(onchain_events, [(t("链", "Chain"), "chain"), (t("标的", "Symbol"), "symbol"), (t("类型", "Type"), "event_type"), ("USD", "amount_usd"), (t("方向", "Direction"), "direction")], lang=active_lang)),
            _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("用于套利、对冲和资金费率观察。", "Used for arbitrage, hedging, and funding-rate monitoring."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("合约", "Futures"), "futures_exchange"), ("Spread bps", "spread_bps"), (t("方向", "Direction"), "direction")], lang=active_lang)),
            _terminal_panel(t("策略命中", "Strategy Hits"), t("自动交易前的候选池和执行意图。", "Candidate pool and execution intent before automated trading."), _terminal_rows(strategy_hits, [(t("标的", "Symbol"), "symbol"), (t("策略", "Strategy"), "strategy"), (t("评分", "Score"), "score"), (t("等级", "Grade"), "grade"), (t("动作", "Action"), "action"), (t("原因", "Reasons"), "reasons")], lang=active_lang), wide=True),
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
    )


def render_terminal_module_page(
    *,
    snapshot: dict[str, object],
    module: str,
    trading_status: dict[str, object] | None = None,
    message: str | None = None,
    lang: str = "zh",
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    intel_items = snapshot["intel_items"]
    twitter_accounts = snapshot["twitter_accounts"]
    onchain_events = snapshot["onchain_events"]
    spreads = snapshot["spreads"]
    strategy_hits = snapshot["strategy_hits"]
    risk = snapshot["execution_risk"]
    platform = snapshot["platform"]
    trading_status = trading_status or {"config": {}, "open_positions": [], "events": []}

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
                _terminal_panel(t("交易所与热门情报", "Exchange & Market Intelligence"), t("公告、新闻、市场热度与信号引擎聚合。", "Announcements, news, market heat, and signal-engine intelligence."), _terminal_rows(intel_items, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("标题", "Title"), "title"), (t("严重度", "Severity"), "severity"), (t("情绪", "Sentiment"), "sentiment")], lang=active_lang), wide=True),
                _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("价差异常会参与执行前风控。", "Basis anomalies feed the pre-trade risk gate."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("现货价格", "Spot Price"), "spot_price"), (t("合约", "Futures"), "futures_exchange"), (t("合约价格", "Futures Price"), "futures_price"), ("Spread bps", "spread_bps")], lang=active_lang), wide=True),
            ]
        )
    elif module == "community":
        panels = "".join(
            [
                _terminal_panel(t("Twitter 账户监控", "Twitter Account Monitor"), t("运行配置中的 tracked accounts 和抓取状态。", "Tracked accounts and fetch state from runtime configuration."), _terminal_rows(twitter_accounts, [(t("账号", "Account"), "username"), (t("关注点", "Focus"), "focus"), (t("模式", "Mode"), "mode"), (t("权重", "Weight"), "weight_pct"), (t("状态", "Status"), "status")], lang=active_lang), wide=True),
                _terminal_panel(t("社区/交易所情报", "Community / Exchange Intelligence"), t("X、Reddit、本地新闻、Telegram 与信号引擎信息统一入池。", "X, Reddit, local news, Telegram, and signal-engine items are merged into one intelligence pool."), _terminal_rows(intel_items, [(t("来源", "Source"), "source"), (t("标的", "Symbol"), "symbol"), (t("类别", "Category"), "category"), (t("标题", "Title"), "title"), (t("严重度", "Severity"), "severity")], lang=active_lang), wide=True),
            ]
        )
    elif module == "onchain":
        panels = "".join(
            [
                _terminal_panel(t("链上异动", "On-chain Events"), t("CSV 接入或量能代理生成的大额转账与流入流出事件。", "Large transfers and exchange-flow events from CSV or volume proxies."), _terminal_rows(onchain_events, [(t("链", "Chain"), "chain"), (t("标的", "Symbol"), "symbol"), (t("类型", "Type"), "event_type"), ("USD", "amount_usd"), (t("方向", "Direction"), "direction"), (t("严重度", "Severity"), "severity")], lang=active_lang), wide=True),
                _terminal_panel(t("链上风控阻断", "On-chain Risk Blocks"), t("高严重度交易所流入会阻断自动开仓。", "High-severity exchange inflows block automated entries."), _terminal_rows([{"symbol": symbol, "reason": reason} for symbol, reason in dict(risk["blocked_symbols"]).items()], [(t("标的", "Symbol"), "symbol"), (t("原因", "Reason"), "reason")], lang=active_lang), wide=True),
            ]
        )
    elif module == "basis":
        panels = "".join(
            [
                _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("用于套利、对冲、资金费率观察和异常价差阻断。", "Used for arbitrage, hedging, funding-rate monitoring, and basis anomaly blocks."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("现货价格", "Spot Price"), "spot_price"), (t("合约", "Futures"), "futures_exchange"), (t("合约价格", "Futures Price"), "futures_price"), ("Spread bps", "spread_bps"), (t("方向", "Direction"), "direction")], lang=active_lang), wide=True),
                _terminal_panel(t("价差执行提示", "Basis Execution Notes"), t("极端 basis 不直接下单，会进入风控复核。", "Extreme basis does not trigger direct orders; it goes to risk review."), _terminal_rows(platform["risk_rules"], [(t("规则", "Rule"), "name"), (t("状态", "Status"), "status"), (t("阈值", "Threshold"), "threshold"), (t("动作", "Action"), "action")], lang=active_lang), wide=True),
            ]
        )
    elif module == "strategies":
        panels = "".join(
            [
                _terminal_panel(t("策略命中", "Strategy Hits"), t("自动交易前的候选池和执行意图。", "Candidate pool and execution intent before automated trading."), _terminal_rows(strategy_hits, [(t("标的", "Symbol"), "symbol"), (t("策略", "Strategy"), "strategy"), (t("评分", "Score"), "score"), (t("等级", "Grade"), "grade"), (t("动作", "Action"), "action"), (t("原因", "Reasons"), "reasons")], lang=active_lang), wide=True),
                _terminal_panel(t("策略目录", "Strategy Catalog"), t("已实现策略、触发条件、执行方式和风控依赖。", "Implemented strategies, triggers, execution methods, and risk dependencies."), _terminal_rows(platform["strategies"], [("ID", "strategy_id"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("触发条件", "Trigger"), "trigger"), (t("执行方式", "Execution"), "execution"), (t("风控", "Risk"), "risk_controls")], lang=active_lang), wide=True),
            ]
        )
    elif module == "trading":
        config = trading_status["config"]
        positions = trading_status["open_positions"]
        events = trading_status["events"]
        command = f"""
          <form method="post" action="{_url('/terminal/trading/run', active_lang)}" class="trading-command terminal-action-form">
            {_hidden_lang_input(active_lang)}
            <div>
              <h2>{t("模拟账户执行", "Paper Account Execution")}</h2>
              <p class="helper-text">{t("使用当前策略信号源和执行前风控，强制以 paper 模式运行一次。不会提交真实订单。", "Run the current strategy signal source and pre-trade risk gate once in forced paper mode. No live order will be submitted.")}</p>
            </div>
            <button type="submit">{t("运行模拟量化交易", "Run Paper Quant Trade")}</button>
          </form>
          <div class="mini-stat-grid compact-grid trading-risk-grid">
            <div class="mini-stat"><span>{t("模式", "Mode")}</span><strong>{escape(_display_value(config.get("mode", "paper"), active_lang))}</strong></div>
            <div class="mini-stat"><span>{t("启用", "Enabled")}</span><strong>{escape(_display_value(config.get("enabled", ""), active_lang))}</strong></div>
            <div class="mini-stat"><span>{t("评分阈值", "Score")}</span><strong>{float(config.get("score_threshold", 0) or 0):.1f}</strong></div>
            <div class="mini-stat"><span>Order Qty</span><strong>{float(config.get("quote_order_qty", 0) or 0):.2f}</strong></div>
          </div>
          {f'<div class="notice notice-success">{escape(message)}</div>' if message else ""}
        """
        panels = "".join(
            [
                _terminal_panel(t("模拟账户执行", "Paper Account Execution"), t("用策略信号源完成一轮 paper 自动交易。", "Complete one paper auto-trading run from the strategy signal source."), command, wide=True),
                _terminal_panel(t("持仓状态", "Position State"), t("本地模拟账户持仓。", "Local paper account positions."), _trading_position_rows(positions, active_lang), wide=True),
                _terminal_panel(t("交易日志", "Trading Logs"), t("自动交易执行、跳过、阻断和下单事件。", "Automated trading execution, skip, block, and order events."), _trading_event_rows(events, active_lang), wide=True),
            ]
        )
    else:
        panels = "".join(
            [
                _terminal_panel(
                    t("执行前风控", "Pre-trade Risk Gate"),
                    str(risk["summary"]),
                    f"""
                    <div class="terminal-risk-board">
                      <div class="mini-stat"><span>{t("状态", "Status")}</span><strong>{escape(_display_value(risk["status"], active_lang))}</strong></div>
                      <div class="mini-stat"><span>{t("风险分", "Risk Score")}</span><strong>{float(risk["risk_score"]):.1f}</strong></div>
                      <div class="mini-stat"><span>{t("允许", "Allowed")}</span><strong>{len(risk["allowed_symbols"])}</strong></div>
                      <div class="mini-stat"><span>{t("阻断", "Blocked")}</span><strong>{len(risk["blocked_symbols"])}</strong></div>
                    </div>
                    {_terminal_rows([{"symbol": symbol, "reason": reason} for symbol, reason in dict(risk["blocked_symbols"]).items()], [(t("标的", "Symbol"), "symbol"), (t("原因", "Reason"), "reason")], lang=active_lang)}
                    """,
                    wide=True,
                ),
                _terminal_panel(t("风险规则", "Risk Rules"), t("执行层硬性约束和保护条件。", "Hard execution constraints and guardrails."), _terminal_rows(platform["risk_rules"], [(t("规则", "Rule"), "name"), (t("状态", "Status"), "status"), (t("阈值", "Threshold"), "threshold"), (t("动作", "Action"), "action")], lang=active_lang), wide=True),
            ]
        )

    hero_right = f"""
      {_terminal_card(t("扫描标的", "Scanned Symbols"), str(int(snapshot["scanned_symbols"])), t("信号源", "signal source"), "cyan")}
      {_terminal_card(t("策略命中", "Strategy Hits"), str(len(strategy_hits)), t("候选池", "candidate pool"), "green")}
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
    )


def _trading_position_rows(positions: list[dict[str, object]], lang: str = "zh") -> str:
    t = lambda zh, en: _text(lang, zh, en)
    if not positions:
        return f'<p class="helper-text">{escape(t("当前没有自动交易持仓。", "No automated trading positions are open."))}</p>'
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
              <td>{escape(_display_value(position["mode"], lang))}</td>
            </tr>
            """
        )
    return f"""
      <table class="data-table">
        <tr>
          <th>{t("标的", "Symbol")}</th>
          <th>Qty</th>
          <th>{t("开仓价", "Entry")}</th>
          <th>{t("名义金额", "Notional")}</th>
          <th>{t("信号", "Signal")}</th>
          <th>{t("止损", "Stop")}</th>
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
    for event in events:
        rows.append(
            f"""
            <tr>
              <td>{escape(str(event["created_at"]))}</td>
              <td>{escape(_display_value(event["action"], lang))}</td>
              <td>{escape(str(event["symbol"]))}</td>
              <td>{escape(_display_value(event["status"], lang))}</td>
              <td>{escape(_display_value(event["message"], lang))}</td>
              <td>{'' if event.get("score") is None else f'{float(event["score"]):.1f}'}</td>
              <td>{'' if event.get("quote_notional") is None else f'{float(event["quote_notional"]):.2f}'}</td>
            </tr>
            """
        )
    return f"""
      <table class="data-table">
        <tr>
          <th>{t("时间", "Time")}</th>
          <th>{t("动作", "Action")}</th>
          <th>{t("标的", "Symbol")}</th>
          <th>{t("状态", "Status")}</th>
          <th>{t("消息", "Message")}</th>
          <th>{t("评分", "Score")}</th>
          <th>{t("名义金额", "Notional")}</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def render_trading_page(
    *,
    config: dict[str, object],
    positions: list[dict[str, object]],
    events: list[dict[str, object]],
    lang: str = "zh",
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    exposure = sum(float(position["quote_notional"]) for position in positions)
    hero_right = f"""
      <div class="stat-card">
        <span>{t("自动引擎", "Auto Engine")}</span>
        <strong>{t("开启", "On") if config["enabled"] else t("关闭", "Off")}</strong>
        <small>{escape(_display_value(config["mode"], active_lang))} {t("模式", "mode")}</small>
      </div>
      <div class="stat-card">
        <span>{t("当前持仓", "Open Positions")}</span>
        <strong>{len(positions)}</strong>
        <small>{t("上限", "max")} {int(config["max_open_positions"])}</small>
      </div>
      <div class="stat-card">
        <span>{t("账户敞口", "Exposure")}</span>
        <strong>{exposure:.0f}</strong>
        <small>{t("上限", "limit")} {float(config["max_total_quote_exposure"]):.0f}</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        <form method="post" action="{_url('/trading/run', active_lang)}" class="trading-command">
          {_hidden_lang_input(active_lang)}
          <div>
            <h2>{t("执行循环", "Execution Loop")}</h2>
            <p class="helper-text">{t("运行一次会扫描当前市场、检查止盈止损、再按分数阈值打开新仓。paper 模式只写入本地持仓；live 模式会被环境变量和 order/test 双重保护。", "One run scans the current market, checks stop loss and take profit, then opens new positions by score threshold. Paper mode only writes local positions; live mode is guarded by environment confirmation and order/test.")}</p>
          </div>
          <button type="submit">{t("运行一次自动交易", "Run Auto Trade Once")}</button>
        </form>
        <div class="mini-stat-grid compact-grid trading-risk-grid">
          <div class="mini-stat"><span>{t("评分阈值", "Score Threshold")}</span><strong>{float(config["score_threshold"]):.1f}</strong></div>
          <div class="mini-stat"><span>{t("单笔金额", "Order Qty")}</span><strong>{float(config["quote_order_qty"]):.2f}</strong></div>
          <div class="mini-stat"><span>{t("止损", "Stop Loss")}</span><strong>{float(config["stop_loss_pct"]):.1f}%</strong></div>
          <div class="mini-stat"><span>{t("止盈", "Take Profit")}</span><strong>{float(config["take_profit_pct"]):.1f}%</strong></div>
        </div>
      </section>

      <section class="section-block">
        <div class="section-heading">
          <h2>{t("持仓", "Positions")}</h2>
          <p>{t("自动交易状态保存在本机", "Auto trading state is stored locally at")} <code>data/trading_state.json</code>。</p>
        </div>
        <article class="portfolio-card table-shell">{_trading_position_rows(positions, active_lang)}</article>
      </section>

      <section class="section-block">
        <div class="section-heading">
          <h2>{t("执行事件", "Execution Events")}</h2>
          <p>{t("本次运行的下单、风控和跳过原因。", "Orders, risk checks, and skip reasons from this run.")}</p>
        </div>
        <article class="backtest-card table-shell">{_trading_event_rows(events, active_lang)}</article>
      </section>
    """
    return _layout(
        page_title="AI Trade Auto Execution",
        active_page="trading",
        hero_title=t("把预测信号接入自动量化执行循环。", "Connect predictive signals to the automated quant execution loop."),
        hero_text=t("系统会根据实时评分、量能、买盘压力和持仓风控生成订单意图，并在 paper 或受保护的 live 模式下执行。", "The system converts live score, volume, buy pressure, and position risk into order intent, then executes in paper mode or guarded live mode."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/trading",
    )


def render_settings_page(
    *,
    params: dict[str, object],
    status: dict[str, object],
    message: str | None,
    error: str | None,
    import_payload_text: str | None,
    lang: str = "zh",
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
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
        <strong>{t("开启", "On") if status["binance_auth_configured"] else t("关闭", "Off")}</strong>
        <small>{escape(str(status["binance_auth_label"]))}</small>
      </div>
      <div class="stat-card">
        <span>OKX Auth</span>
        <strong>{t("开启", "On") if status["okx_auth_configured"] else t("关闭", "Off")}</strong>
        <small>{t("跨交易所就绪", "cross-exchange ready")}</small>
      </div>
      <div class="stat-card">
        <span>X / Reddit</span>
        <strong>{t("开启", "On") if status["x_auth_configured"] else t("混合", "Mixed")}</strong>
        <small>{int(status["tracked_account_count"])} {t("个跟踪账号", "tracked accounts")}</small>
      </div>
      <div class="stat-card">
        <span>Storage</span>
        <strong>{escape(str(status["storage_mode"]))}</strong>
        <small>{t("已启用口令保护", "passphrase protection enabled") if str(status["storage_mode"]) == "Encrypted" else t("配置保存到本地 JSON", "config saved to local JSON")}</small>
      </div>
      <div class="stat-card">
        <span>Auto Trade</span>
        <strong>{t("开启", "On") if status["autotrade_enabled"] else t("关闭", "Off")}</strong>
        <small>{escape(_display_value(status["autotrade_mode"], active_lang))} {t("执行", "execution")}</small>
      </div>
      <div class="stat-card">
        <span>Intelligence</span>
        <strong>{t("开启", "On") if status["intelligence_enabled"] else t("关闭", "Off")}</strong>
        <small>{t("大模型启用", "LLM enabled") if status["llm_enabled"] else t("本地规则", "local rules")}</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        {"".join(notices)}
        <form method="post" action="{_url('/settings', active_lang)}" class="backtest-form">
          {_hidden_lang_input(active_lang)}
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
          <form method="post" action="{_url('/settings/import', active_lang)}" class="settings-transfer-card import-form">
            {_hidden_lang_input(active_lang)}
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
        hero_title=t("把数据源、情报源和策略参数都收进一个运行时配置面板。", "Manage data sources, intelligence sources, and strategy parameters in one runtime console."),
        hero_text=t("密钥、Twitter 监控账号、扫描默认值和回测默认策略都可以在这里改。保存后，扫描页和回测页会直接吃新的默认配置。", "Configure credentials, Twitter tracked accounts, scan defaults, and backtest strategy defaults. Saved changes are applied directly across the system."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/settings",
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
    lang: str = "zh",
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    archive_value = escape(str(params["archives"]))
    current_preset = get_backtest_preset(str(params["preset"]))
    preset_options = "".join(_option(str(preset["preset_id"]), str(params["preset"])) for preset in presets)
    hero_right = f"""
      <div class="stat-card">
        <span>Series Reports</span>
        <strong>{len(series_reports)}</strong>
        <small>{t("单币种回测", "single-symbol backtests")}</small>
      </div>
      <div class="stat-card">
        <span>Portfolio Reports</span>
        <strong>{len(portfolio_reports)}</strong>
        <small>{t("组合结果", "portfolio results")}</small>
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
          {_hidden_lang_input(active_lang)}
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
        hero_title=t("把本地 Binance 历史 K 线直接拉进页面里回测。", "Run backtests directly from local Binance historical kline archives."),
        hero_text=t("同一页里调整分数阈值、止盈止损、滑点模型和组合仓位约束，直接看单币种与组合结果。", "Tune score thresholds, stop loss, take profit, slippage model, and portfolio exposure constraints on one page."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/backtest",
    )
