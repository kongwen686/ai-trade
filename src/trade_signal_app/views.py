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
        "read_only": "只读",
        "auth_failed": "认证失败",
        "unchecked": "未检查",
        "configured_pending_connector": "待接入",
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
        "research": "研究中",
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
        "stop_loss": "止损",
        "take_profit": "止盈",
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
        "read_only": "Read Only",
        "auth_failed": "Auth Failed",
        "unchecked": "Unchecked",
        "configured_pending_connector": "Connector Pending",
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
        "research": "Research",
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
        "stop_loss": "Stop Loss",
        "take_profit": "Take Profit",
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
    "加密资产等权再平衡": "Crypto Equal-Weight Rebalance",
    "BTC 隔夜季节性": "BTC Overnight Seasonality",
    "paper/live 市价买入": "Paper/live market buy",
    "候选优先级提升": "Candidate priority boost",
    "套利/对冲观察": "Arbitrage/hedge watch",
    "回测研究 / 组合再平衡观察": "Backtest research / portfolio rebalance observation",
    "回测研究 / 时间窗口观察": "Backtest research / time-window observation",
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


def _option_with_label(value: str, label: str, selected: str) -> str:
    is_selected = " selected" if value == selected else ""
    return f'<option value="{escape(value)}"{is_selected}>{escape(label)}</option>'


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


def _market_ticker_message(lang: str, error: str = "", error_code: str = "") -> str:
    messages = {
        "cache_empty": _text(lang, "行情缓存为空，请先运行一次市场扫描加载实时行情。", "Ticker cache is empty. Run a market scan to load live ticker data."),
        "cache_unavailable": _text(lang, "当前扫描器未提供行情缓存。", "Ticker cache is unavailable for the current scanner."),
        "quote_empty": _text(lang, "当前计价币没有可展示的行情。", "No ticker data for the configured quote asset."),
        "error": _text(lang, "行情暂时不可用。", "Ticker is temporarily unavailable."),
    }
    return messages.get(error_code, error or _text(lang, "行情未加载", "Ticker unavailable"))


def _market_ticker(lang: str, items: list[dict[str, object]] | None = None, error: str = "", error_code: str = "") -> str:
    items = items or []
    if items:
        ticker_items = "".join(
            f'<span><strong>{escape(str(item["label"]))}</strong><em class="{"down" if float(item["change_pct"]) < 0 else "up"}">{float(item["change_pct"]):+.2f}%</em></span>'
            for item in items[:8]
        )
    else:
        message = _market_ticker_message(lang, error, error_code)
        ticker_items = f'<span><strong>{escape(message)}</strong></span>'
    return f"""
      <footer class="market-ticker">
        <strong>{_text(lang, "市场行情", "Market Ticker")}</strong>
        <div>{ticker_items}</div>
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
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    layout_context = layout_context or {}
    alert_count = int(layout_context.get("alert_count", 0) or 0)
    ticker_payload = layout_context.get("market_ticker") if isinstance(layout_context.get("market_ticker"), dict) else {}
    ticker_items = ticker_payload.get("items", []) if isinstance(ticker_payload, dict) else []
    ticker_error = str(ticker_payload.get("error", "")) if isinstance(ticker_payload, dict) else ""
    ticker_error_code = str(ticker_payload.get("error_code", "")) if isinstance(ticker_payload, dict) else ""
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
            <span class="tool-button is-alert" title="Alerts" aria-label="{alert_count} alerts">{_tool_icon("alerts")}<em>{alert_count}</em></span>
            {_language_switch(active_lang, current_path)}
            <div class="user-chip">
              <span>local_runtime</span>
              <small>{_text(active_lang, "本地会话", "Local Session")}</small>
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
      {_market_ticker(active_lang, ticker_items if isinstance(ticker_items, list) else [], ticker_error, ticker_error_code)}
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


def _scan_view_url(params: dict[str, object], lang: str, view_mode: str) -> str:
    query = {
        "quote_asset": params.get("quote_asset", ""),
        "interval": params.get("interval", ""),
        "candidate_pool": params.get("candidate_pool", ""),
        "min_quote_volume": params.get("min_quote_volume", ""),
        "min_trade_count": params.get("min_trade_count", ""),
        "view_mode": view_mode,
    }
    if normalize_language(lang) == "en":
        query["lang"] = "en"
    return f"/?{urlencode(query)}"


def _signal_empty_state(lang: str) -> str:
    return f"""
    <article class="empty-state">
      <h2>{_text(lang, "当前条件下没有足够强的候选币种。", "No sufficiently strong candidates under the current filters.")}</h2>
      <p>{_text(lang, "可以适当降低最小成交额或增大候选数，再重新扫描。", "Lower minimum quote volume or increase the candidate pool, then scan again.")}</p>
    </article>
    """


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


def _signal_table(signals: list[dict[str, object]], lang: str) -> str:
    if not signals:
        return _signal_empty_state(lang)

    headers = [
        _text(lang, "标的", "Symbol"),
        _text(lang, "等级", "Grade"),
        _text(lang, "分数", "Score"),
        "24h",
        _text(lang, "成交额", "Quote Vol"),
        "RSI",
        _text(lang, "量比", "Vol Ratio"),
        "EMA",
        "MACD",
        _text(lang, "社区", "Community"),
        _text(lang, "原因", "Reasons"),
    ]
    header = "".join(f"<th>{escape(item)}</th>" for item in headers)
    rows = []
    for signal in signals:
        grade = str(signal["grade"])
        grade_class = grade.lower().replace("+", "-plus")
        community = _text(lang, "未接入", "Not configured")
        if signal.get("community_score") is not None:
            source = escape(str(signal.get("community_source") or "community"))
            community = f'{float(signal["community_score"]):.0f}<span>{source}</span>'
        reasons = list(signal.get("reasons") or [])[:3]
        warnings = list(signal.get("warnings") or [])[:2]
        reason_tags = "".join(f'<span class="table-tag positive">{escape(str(item))}</span>' for item in reasons)
        warning_tags = "".join(f'<span class="table-tag warning">{escape(str(item))}</span>' for item in warnings)
        rows.append(
            f"""
            <tr>
              <td><strong class="table-symbol">{escape(str(signal["symbol"]))}</strong></td>
              <td><span class="table-grade grade-{grade_class}">{escape(grade)}</span></td>
              <td class="numeric strong">{float(signal["score"]):.1f}</td>
              <td class="numeric">{float(signal["price_change_percent"]):+.2f}%</td>
              <td class="numeric">{float(signal["quote_volume_m"]):.1f}M</td>
              <td class="numeric">{float(signal["rsi_14"]):.1f}</td>
              <td class="numeric">{float(signal["volume_ratio"]):.2f}x</td>
              <td class="numeric">{float(signal["ema_spread_pct"]):+.2f}%</td>
              <td class="numeric">{float(signal["macd_hist"]):+.4f}</td>
              <td class="community-cell">{community}</td>
              <td><div class="table-tags">{reason_tags}{warning_tags}</div></td>
            </tr>
            """
        )
    return f"""
      <section class="signal-table-shell table-shell" aria-label="{escape(_text(lang, "信号表格", "Signal table"))}">
        <table class="data-table signal-table">
          <thead><tr>{header}</tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </section>
    """


def render_index_page(
    summary: dict[str, object],
    signals: list[dict[str, object]],
    params: dict[str, object],
    intervals: list[str],
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    view_mode = str(params.get("view_mode", "cards"))
    if view_mode not in {"cards", "table"}:
        view_mode = "cards"
    cards_class = "active" if view_mode == "cards" else ""
    table_class = "active" if view_mode == "table" else ""
    signal_results = (
        _signal_table(signals, active_lang)
        if view_mode == "table"
        else f'<section class="signal-grid">{"".join(_signal_card(signal) for signal in signals) or _signal_empty_state(active_lang)}</section>'
    )

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
          <input type="hidden" name="view_mode" value="{escape(view_mode)}" />
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
        <div class="scan-view-bar">
          <span>{t("展示模式", "View Mode")}</span>
          <div class="view-toggle" aria-label="{t("展示模式", "View mode")}">
            <a class="{cards_class}" href="{escape(_scan_view_url(params, active_lang, "cards"))}">{t("卡片", "Cards")}</a>
            <a class="{table_class}" href="{escape(_scan_view_url(params, active_lang, "table"))}">{t("表格", "Table")}</a>
          </div>
        </div>
      </section>

      {signal_results}
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
        layout_context=layout_context,
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
            _terminal_panel(t("交易账户概览", "Trading Accounts"), t("模拟交易和真实交易账户状态。", "Paper and live account state."), _terminal_rows(platform["accounts"], [(t("交易所", "Exchange"), "exchange"), (t("模式", "Mode"), "mode"), (t("状态", "Status"), "status"), (t("持仓数", "Positions"), "open_positions"), (t("敞口", "Exposure"), "quote_exposure"), (t("已实现盈亏", "Realized PnL"), "realized_pnl"), (t("胜率", "Win Rate"), "win_rate_pct")], lang=active_lang)),
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
            _terminal_panel(t("链上异动", "On-chain Events"), t("来自真实 CSV/外部源的大额转账和交易所流入流出。", "Large transfers and exchange flows from real CSV or external sources."), _terminal_rows(onchain_events, [(t("链", "Chain"), "chain"), (t("标的", "Symbol"), "symbol"), (t("类型", "Type"), "event_type"), ("USD", "amount_usd"), (t("方向", "Direction"), "direction")], lang=active_lang)),
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
        layout_context=layout_context,
    )


def render_terminal_module_page(
    *,
    snapshot: dict[str, object],
    module: str,
    trading_status: dict[str, object] | None = None,
    message: str | None = None,
    error: str | None = None,
    strategy_builder_result: dict[str, object] | None = None,
    strategy_builder_text: str = "",
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
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
                _terminal_panel(t("链上异动", "On-chain Events"), t("CSV 或外部数据源接入的大额转账与流入流出事件。", "Large transfers and exchange-flow events from CSV or external data sources."), _terminal_rows(onchain_events, [(t("链", "Chain"), "chain"), (t("标的", "Symbol"), "symbol"), (t("类型", "Type"), "event_type"), ("USD", "amount_usd"), (t("方向", "Direction"), "direction"), (t("严重度", "Severity"), "severity")], lang=active_lang), wide=True),
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
                _terminal_panel(t("策略命中", "Strategy Hits"), t("自动交易前的候选池和执行意图。", "Candidate pool and execution intent before automated trading."), _terminal_rows(strategy_hits, [(t("标的", "Symbol"), "symbol"), (t("策略", "Strategy"), "strategy"), (t("评分", "Score"), "score"), (t("等级", "Grade"), "grade"), (t("动作", "Action"), "action"), (t("原因", "Reasons"), "reasons")], lang=active_lang), wide=True),
                _terminal_panel(t("策略目录", "Strategy Catalog"), t("已实现策略、触发条件、执行方式和风控依赖。", "Implemented strategies, triggers, execution methods, and risk dependencies."), _terminal_rows(platform["strategies"], [("ID", "strategy_id"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("触发条件", "Trigger"), "trigger"), (t("执行方式", "Execution"), "execution"), (t("风控", "Risk"), "risk_controls")], lang=active_lang), wide=True),
            ]
        )
    elif module == "trading":
        config = trading_status["config"]
        readiness = trading_status.get("readiness", {}) if isinstance(trading_status, dict) else {}
        exchange_status = readiness.get("exchange_status") if isinstance(readiness, dict) and isinstance(readiness.get("exchange_status"), dict) else {}
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
            <div class="mini-stat"><span>{t("授权", "Auth")}</span><strong>{escape(_display_value(exchange_status.get("status", "not_configured"), active_lang))}</strong></div>
            <div class="mini-stat"><span>{t("实盘就绪", "Live Ready")}</span><strong>{t("是", "Yes") if readiness.get("live_ready") else t("否", "No")}</strong></div>
          </div>
          {f'<div class="notice notice-success">{escape(message)}</div>' if message else ""}
        """
        panels = "".join(
            [
                _terminal_panel(t("模拟账户执行", "Paper Account Execution"), t("用策略信号源完成一轮 paper 自动交易。", "Complete one paper auto-trading run from the strategy signal source."), command, wide=True),
                _terminal_panel(t("账户表现", "Account Performance"), t("持仓敞口、已实现盈亏和最近平仓胜率。", "Open exposure, realized PnL, and recent closed-trade win rate."), _terminal_rows(platform["accounts"], [(t("交易所", "Exchange"), "exchange"), (t("模式", "Mode"), "mode"), (t("持仓", "Positions"), "open_positions"), (t("敞口", "Exposure"), "quote_exposure"), (t("已实现盈亏", "Realized PnL"), "realized_pnl"), (t("平仓数", "Closed"), "closed_trades"), (t("胜率", "Win Rate"), "win_rate_pct")], lang=active_lang), wide=True),
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
        layout_context=layout_context,
    )


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
      <form method="post" action="{_url('/terminal/strategies/compile', lang)}" class="strategy-builder-form">
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
            {_strategy_param_table(autotrade_defaults, ["enabled", "mode", "quote_order_qty", "max_open_positions", "max_total_quote_exposure", "score_threshold", "min_volume_ratio", "min_buy_pressure", "stop_loss_pct", "take_profit_pct", "cooldown_minutes", "order_test_only"], lang)}
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
              <td>{escape(_display_value(event.get("exit_reason", ""), lang))}</td>
              <td>{'' if event.get("realized_pnl") is None else f'{float(event["realized_pnl"]):+.2f}'}</td>
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
          <th>{t("退出", "Exit")}</th>
          <th>{t("盈亏", "PnL")}</th>
        </tr>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _settings_description_map(lang: str) -> dict[str, str]:
    pairs = {
        "Binance API Key": ("用于读取 Binance 账户权限、费率和提交受保护的实盘订单。留空会保留原值。", "Used for Binance account checks, fees, and guarded live orders. Leave blank to keep the saved value."),
        "Binance API Secret": ("用于签名 Binance 私有接口请求，不会显示在页面或 URL 中。", "Signs Binance private API requests; it is never shown in the page or URL."),
        "Binance RecvWindow": ("Binance 签名请求允许的时间窗口，网络较慢时可适当调大。", "Allowed timing window for signed Binance requests; increase it if your network is slow."),
        "Clear Binance auth": ("勾选后保存会清空已保存的 Binance key 和 secret。", "When checked, saving clears the saved Binance key and secret."),
        "OKX API Key": ("保存 OKX 凭据用于状态展示和后续跨交易所接入；当前不会自动用 OKX 下单。", "Stores OKX credentials for status and future connector work; OKX is not used for automated orders yet."),
        "OKX API Secret": ("OKX 私有接口签名密钥；未接入交易 connector 前只作为配置状态保存。", "OKX private API signing secret; currently stored only as connector status."),
        "OKX Passphrase": ("OKX API 创建时设置的 passphrase，需与 key/secret 配套。", "Passphrase configured when creating the OKX API key."),
        "Clear OKX auth": ("勾选后保存会清空已保存的 OKX 三项凭据。", "When checked, saving clears the saved OKX credentials."),
        "Market Data Preset": ("默认公开行情服务。Binance/OKX/CoinGecko 公开端点不需要 key，但只能读取公开数据。", "Default public market data service. Binance/OKX/CoinGecko public endpoints need no key, but only expose public data."),
        "On-chain Data Preset": ("默认链上/DeFi 数据服务。Open Multi-chain、DefiLlama 和 GeckoTerminal 可无密钥使用；本地 CSV 适合私有数据。", "Default on-chain/DeFi data service. Open Multi-chain, DefiLlama, and GeckoTerminal can be used keylessly; local CSV is for private data."),
        "On-chain API Key": ("可选链上数据 Key；当前公开预设可留空，付费或自建网关需要时再填写。", "Optional on-chain data key; keyless presets can leave it blank, paid or private gateways can use it."),
        "On-chain API Base URL": ("可选链上数据自定义网关地址；留空时使用预设服务的默认地址。", "Optional custom on-chain gateway URL; blank uses the preset default."),
        "Clear On-chain auth": ("勾选后保存会清空已保存的链上数据 API Key。", "When checked, saving clears the saved on-chain API key."),
        "X Bearer Token": ("用于调用 X/Twitter API 拉取社区热度和指定账号情报。", "Used to call X/Twitter APIs for community heat and tracked-account intelligence."),
        "X Provider": ("选择 X/Twitter 数据来源：official_api 使用 Bearer Token；nitter_rss 使用 Nitter RSS；session_scrape 使用本地只读抓取命令。", "Select X/Twitter source: official_api uses Bearer Token; nitter_rss uses Nitter RSS; session_scrape uses a local read-only scraper command."),
        "Community Provider": ("选择社区数据来源；auto 会按已配置凭据和本地 CSV 自动组合。", "Select community data sources; auto combines configured credentials and local CSV files."),
        "X API Base URL": ("X API 网关地址，通常保持默认；代理环境可改成内部转发地址。", "X API gateway URL; keep default unless you route through an internal proxy."),
        "X Nitter Base URL": ("自建 Nitter 实例地址，例如 http://127.0.0.1:8788；公共实例不稳定，不建议重度依赖。", "Self-hosted Nitter base URL, e.g. http://127.0.0.1:8788; public instances are unreliable."),
        "X Session Command": ("本地只读抓取命令模板，支持 {query}、{raw_query}、{limit}、{hours} 占位符，输出 JSON/JSONL。", "Local read-only scraper command template. Supports {query}, {raw_query}, {limit}, {hours}; output JSON/JSONL."),
        "Clear X auth": ("勾选后保存会清空已保存的 X Bearer Token。", "When checked, saving clears the saved X Bearer Token."),
        "Enable intelligence center": ("开启总控台情报聚合、链上/价差风控和策略命中解释。", "Enables intelligence aggregation, on-chain/basis risk gates, and strategy explanations."),
        "Enable LLM analysis": ("开启后会调用所选大模型生成综合分析；未开启或失败时使用本地规则。", "Calls the selected LLM for synthesized analysis; local rules are used when disabled or failed."),
        "LLM Provider": ("选择模型供应商；OpenAI、Anthropic、Gemini、DeepSeek、xAI、Mistral、Qwen、Kimi 已预设。", "Select model provider; OpenAI, Anthropic, Gemini, DeepSeek, xAI, Mistral, Qwen, and Kimi are preset."),
        "LLM API Key": ("所选模型供应商的 API Key。留空会保留原值，不会显示在页面或 URL 中。", "API key for the selected provider. Leave blank to keep the saved value; it is not shown in the page or URL."),
        "LLM Base URL": ("可选自定义模型网关；留空时使用供应商预设地址。", "Optional custom model gateway; blank uses the provider preset URL."),
        "LLM Model": ("模型名称，默认使用当前 provider 的推荐值，可按实际账号可用模型修改。", "Model name; defaults to the provider recommendation and can be changed to any model available to your account."),
        "Clear LLM auth": ("勾选后保存会清空已保存的大模型 API Key。", "When checked, saving clears the saved LLM API key."),
        "OpenAI API Key": ("兼容旧配置字段；新配置请使用 LLM API Key。", "Legacy compatibility field; use LLM API Key for new configuration."),
        "OpenAI Model": ("兼容旧配置字段；新配置请使用 LLM Model。", "Legacy compatibility field; use LLM Model for new configuration."),
        "Min Intel Severity": ("情报严重度低于该值时不会显著影响风控判断。", "Intelligence below this severity has limited impact on risk decisions."),
        "Min Spread bps": ("现货/合约价差超过该阈值才进入 basis 风控观察。", "Spot/futures basis above this threshold enters risk monitoring."),
        "Whale Threshold USD": ("链上大额转账金额阈值，超过后会提高事件严重度。", "USD threshold for large on-chain transfers; higher values raise severity."),
        "X Window Hours": ("X/Twitter 查询回看窗口，只统计最近多少小时的内容。", "Lookback window for X/Twitter queries, in hours."),
        "X Max Results": ("每次 X 查询最多读取的帖子数量，越高越慢。", "Maximum posts to read per X query; higher values are slower."),
        "X Language": ("X 搜索语言过滤，例如 en、zh；留空会降低过滤强度。", "Language filter for X search, such as en or zh."),
        "Account Mode": ("off 关闭指定账号；blend 混合普通热度；only 只看指定账号。", "off disables tracked accounts; blend mixes them; only uses tracked accounts."),
        "Account Weight %": ("blend 模式下指定账号情报在社区分数中的权重。", "Tracked-account weight in blended community scoring."),
        "Tracked Accounts": ("一行一个 X 用户名；可写 @ 前缀，也可只写用户名。", "One X username per line; @ prefix is optional."),
        "Reddit API Base URL": ("Reddit 公开接口地址；代理环境可改为内部网关。", "Reddit public API base URL; change only for proxy/internal gateways."),
        "Reddit Window Hours": ("Reddit 搜索回看窗口，只统计最近多少小时的帖子。", "Lookback window for Reddit posts, in hours."),
        "Reddit Max Results": ("每个 Reddit 查询最多读取的结果数。", "Maximum Reddit results per query."),
        "Reddit User-Agent": ("Reddit 请求要求带 User-Agent，建议保留可识别名称。", "Reddit requests require a User-Agent; keep it identifiable."),
        "Quote Asset": ("实时扫描使用的计价资产，例如 USDT、FDUSD。", "Quote asset for live scans, such as USDT or FDUSD."),
        "Scan Interval": ("实时扫描使用的 K 线周期。", "Kline interval used by live scans."),
        "Candidate Pool": ("先按 24h 活跃度选出的候选交易对数量。", "Number of active pairs selected before scoring."),
        "Min Quote Volume": ("低于该 24h 成交额的交易对会被过滤。", "Pairs below this 24h quote volume are filtered out."),
        "Min Trade Count": ("低于该 24h 成交笔数的交易对会被过滤。", "Pairs below this 24h trade count are filtered out."),
        "Enable auto trade": ("开启后自动交易入口会按配置扫描、风控和执行。", "When enabled, the engine scans, risk-checks, and executes by configuration."),
        "Execution Mode": ("paper 只写本地模拟持仓；live 才可能触发真实订单。", "paper writes local simulated positions; live may submit real orders."),
        "Quote Order Qty": ("每次开仓投入的计价资产金额。", "Quote-asset amount allocated to each entry."),
        "Max Open Positions": ("自动交易最多同时持有的仓位数量。", "Maximum number of simultaneous automated positions."),
        "Max Total Exposure": ("自动交易允许占用的最大计价资产敞口。", "Maximum quote exposure allowed for automated trading."),
        "Score Threshold": ("信号分数达到该阈值才允许进入候选或回测交易。", "Signal score must reach this threshold before trading or backtesting entries."),
        "Min Volume Ratio": ("量能放大倍数门槛，低于该值会过滤。", "Minimum volume expansion ratio."),
        "Min Buy Pressure": ("主动买入占比门槛，用于过滤买盘不足的信号。", "Minimum taker-buy pressure ratio."),
        "Stop Loss %": ("价格相对入场价下跌到该比例时触发止损。", "Stop loss percentage from entry price."),
        "Take Profit %": ("价格相对入场价上涨到该比例时触发止盈。", "Take profit percentage from entry price."),
        "Cooldown Minutes": ("自动交易开仓或平仓后的冷却时间，避免连续追单。", "Cooldown after automated trades to avoid repeated entries."),
        "Use Binance order/test": ("勾选时 live 模式只校验订单参数，不会真实成交。", "When checked, live mode validates orders without filling them."),
        "Default Preset": ("回测页默认使用的策略参数模板。", "Default strategy preset for the backtest page."),
        "Default Archives": ("本地 Binance public-data ZIP 路径或 glob，可多行填写。", "Local Binance public-data ZIP paths or globs; multiple lines are supported."),
        "Lookback Bars": ("计算指标时使用的历史 K 线数量。", "Number of historical bars used for indicators."),
        "Holding Periods": ("回测观察的持仓周期列表，用逗号分隔。", "Comma-separated holding periods for backtest analysis."),
        "Portfolio Top N": ("组合回测每期选择分数最高的前 N 个标的；0 表示不跑组合。", "Top N symbols per portfolio batch; 0 disables portfolio backtest."),
        "Cooldown Bars": ("回测平仓后等待多少根 K 线才允许再次入场。", "Bars to wait after an exit before re-entry."),
        "Max Holding Bars": ("单笔交易最多持有的 K 线数量。", "Maximum bars a single trade can stay open."),
        "Fee Source": ("manual 用页面费率；account/symbol 会尝试读取 Binance 账户或交易对费率。", "manual uses form fees; account/symbol reads Binance account or symbol fees."),
        "Fee Model": ("flat 使用统一费率；maker_taker 区分挂单和吃单。", "flat uses one fee; maker_taker separates maker and taker fees."),
        "Fee bps": ("统一手续费，单位 bps，10 bps 等于 0.10%。", "Flat fee in bps; 10 bps equals 0.10%."),
        "Maker Fee bps": ("maker_taker 模型下的挂单费率。", "Maker fee for maker_taker mode."),
        "Taker Fee bps": ("maker_taker 模型下的吃单费率。", "Taker fee for maker_taker mode."),
        "Entry Role": ("回测入场时按 maker 还是 taker 费率计费。", "Fee role used for entries."),
        "Exit Role": ("回测出场时按 maker 还是 taker 费率计费。", "Fee role used for exits."),
        "Fee Discount %": ("手续费折扣百分比，例如 BNB 抵扣。", "Fee discount percentage, such as BNB discount."),
        "Disable Binance discount": ("勾选后即使 Binance 返回折扣信息也不应用。", "Ignore Binance discount data even when returned."),
        "Slippage bps": ("固定滑点或动态滑点基础值，单位 bps。", "Base fixed or dynamic slippage in bps."),
        "Slippage Model": ("fixed 使用固定滑点；dynamic 会按成交量状态调整。", "fixed uses constant slippage; dynamic adjusts by liquidity."),
        "Min Slippage": ("动态滑点模型允许的最小滑点。", "Minimum slippage in dynamic mode."),
        "Max Slippage": ("动态滑点模型允许的最大滑点。", "Maximum slippage in dynamic mode."),
        "Slip Window": ("动态滑点计算使用的成交量窗口长度。", "Volume window used for dynamic slippage."),
        "Capital %": ("每笔交易可动用的资金比例。", "Capital fraction available per trade."),
        "Max Exposure %": ("组合层允许同时暴露的最大资金比例。", "Maximum portfolio exposure percentage."),
        "Max Concurrent": ("组合回测允许同时持有的最大标的数；0 表示不限制。", "Maximum concurrent holdings; 0 means unlimited."),
        "Min RSI": ("入场允许的最低 RSI。", "Minimum RSI allowed for entries."),
        "Max RSI": ("入场允许的最高 RSI。", "Maximum RSI allowed for entries."),
        "Disable KDJ confirmation": ("勾选后回测入场不再要求 KDJ 方向确认。", "Disable KDJ confirmation for backtest entries."),
        "Template JSON": ("粘贴从导出功能得到的配置模板 JSON。", "Paste a configuration template exported from this app."),
    }
    return {label: _text(lang, zh, en) for label, (zh, en) in pairs.items()}


def _with_settings_descriptions(html: str, lang: str) -> str:
    for label, description in _settings_description_map(lang).items():
        marker = f"<span>{label}</span>"
        replacement = f'<span>{label}</span><small class="settings-description">{escape(description)}</small>'
        html = html.replace(marker, replacement)
    return html


def render_trading_page(
    *,
    config: dict[str, object],
    positions: list[dict[str, object]],
    events: list[dict[str, object]],
    readiness: dict[str, object] | None = None,
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
) -> str:
    active_lang = normalize_language(lang)
    t = lambda zh, en: _text(active_lang, zh, en)
    exposure = sum(float(position["quote_notional"]) for position in positions)
    realized_pnl = sum(float(event["realized_pnl"]) for event in events if event.get("realized_pnl") is not None)
    readiness = readiness or {}
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    exchange_status = readiness.get("exchange_status") if isinstance(readiness.get("exchange_status"), dict) else {}
    live_ready = bool(readiness.get("live_ready"))
    auth_status = str(exchange_status.get("status", "unknown"))
    readiness_notice = ""
    if str(config["mode"]) == "live":
        if live_ready:
            readiness_notice = f'<div class="notice notice-success">{t("实盘自动交易准备就绪。", "Live auto trading is ready.")}</div>'
        else:
            blocker_items = "".join(f"<li>{escape(str(item))}</li>" for item in blockers)
            readiness_notice = f"""
              <div class="notice notice-error">
                <strong>{t("实盘自动交易未就绪。", "Live auto trading is not ready.")}</strong>
                <ul class="strategy-warning-list">{blocker_items}</ul>
              </div>
            """
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
      <div class="stat-card">
        <span>{t("已实现盈亏", "Realized PnL")}</span>
        <strong>{realized_pnl:+.2f}</strong>
        <small>{t("最近事件", "recent events")}</small>
      </div>
      <div class="stat-card">
        <span>{t("交易所授权", "Exchange Auth")}</span>
        <strong>{escape(_display_value(auth_status, active_lang))}</strong>
        <small>{t("可用", "available")} {float(readiness.get("quote_available") or 0.0):.2f} {escape(str(readiness.get("quote_asset", "")))}</small>
      </div>
    """
    content = f"""
      <section class="control-panel">
        {readiness_notice}
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
        layout_context=layout_context,
    )


def render_settings_page(
    *,
    params: dict[str, object],
    status: dict[str, object],
    message: str | None,
    error: str | None,
    import_payload_text: str | None,
    lang: str = "zh",
    layout_context: dict[str, object] | None = None,
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
    public_presets = status.get("public_data_presets") if isinstance(status.get("public_data_presets"), list) else []
    llm_presets = status.get("llm_provider_presets") if isinstance(status.get("llm_provider_presets"), list) else []
    market_options = "".join(
        _option_with_label(str(item.get("preset_id", "")), str(item.get("name", item.get("preset_id", ""))), str(params["market_data_preset"]))
        for item in public_presets
        if isinstance(item, dict) and item.get("category") == "market"
    )
    onchain_options = "".join(
        _option_with_label(str(item.get("preset_id", "")), str(item.get("name", item.get("preset_id", ""))), str(params["onchain_data_preset"]))
        for item in public_presets
        if isinstance(item, dict) and item.get("category") == "onchain"
    )
    llm_options = "".join(
        _option_with_label(str(item.get("provider_id", "")), str(item.get("name", item.get("provider_id", ""))), str(params["intelligence_llm_provider"]))
        for item in llm_presets
        if isinstance(item, dict)
    )
    provider_names = {
        str(item.get("provider_id", "")): str(item.get("name", ""))
        for item in llm_presets
        if isinstance(item, dict)
    }
    hero_right = f"""
      <div class="stat-card">
        <span>Binance Auth</span>
        <strong>{t("开启", "On") if status["binance_auth_configured"] else t("关闭", "Off")}</strong>
        <small>{escape(str(status["binance_auth_label"]))}</small>
      </div>
      <div class="stat-card">
        <span>OKX Auth</span>
        <strong>{t("开启", "On") if status["okx_auth_configured"] else t("关闭", "Off")}</strong>
        <small>{t("凭据已保存，私有交易接口待接入", "credentials saved, private connector pending") if status["okx_auth_configured"] else t("未配置 OKX 凭据", "OKX credentials not configured")}</small>
      </div>
      <div class="stat-card">
        <span>X / Reddit</span>
        <strong>{t("开启", "On") if status["x_auth_configured"] else t("本地/公开", "Local/Public")}</strong>
        <small>{int(status["tracked_account_count"])} {t("个 X 跟踪账号", "tracked X accounts")}</small>
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
        <small>{escape(provider_names.get(str(status.get("llm_provider", "")), str(status.get("llm_provider", "local")))) if status["llm_enabled"] else t("本地规则", "local rules")}</small>
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
          <label><span>Market Data Preset</span><select name="market_data_preset">{market_options}</select></label>
          <label><span>On-chain Data Preset</span><select name="onchain_data_preset">{onchain_options}</select></label>
          <label><span>On-chain API Key</span><input type="password" name="onchain_api_key" value="" placeholder="公开预设可留空" autocomplete="new-password" /></label>
          <label><span>On-chain API Base URL</span><input type="text" name="onchain_api_base_url" value="{escape(str(params['onchain_api_base_url']))}" placeholder="留空使用预设地址" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_onchain_auth" /><span>Clear On-chain auth</span></label>
          <label><span>X Bearer Token</span><input type="password" name="x_bearer_token" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>X Provider</span><select name="x_provider">{''.join(_option(item, str(params['x_provider'])) for item in ['official_api', 'nitter_rss', 'session_scrape'])}</select></label>
          <label><span>Community Provider</span><select name="community_provider">{''.join(_option(item, str(params['community_provider'])) for item in ['auto', 'x', 'csv', 'news', 'telegram', 'reddit', 'x,csv', 'x,news', 'x,telegram', 'x,reddit', 'csv,news', 'csv,telegram', 'csv,reddit', 'news,telegram', 'news,reddit', 'telegram,reddit', 'x,csv,news', 'x,csv,telegram', 'x,csv,reddit', 'x,news,telegram', 'x,news,reddit', 'x,telegram,reddit', 'csv,news,telegram', 'csv,news,reddit', 'csv,telegram,reddit', 'news,telegram,reddit', 'x,csv,news,telegram', 'x,csv,news,reddit', 'x,csv,telegram,reddit', 'x,news,telegram,reddit', 'csv,news,telegram,reddit', 'x,csv,news,telegram,reddit'])}</select></label>
          <label><span>X API Base URL</span><input type="text" name="x_api_base_url" value="{escape(str(params['x_api_base_url']))}" /></label>
          <label><span>X Nitter Base URL</span><input type="text" name="x_nitter_base_url" value="{escape(str(params['x_nitter_base_url']))}" placeholder="http://127.0.0.1:8788" /></label>
          <label class="full-span"><span>X Session Command</span><input type="text" name="x_session_command" value="{escape(str(params['x_session_command']))}" placeholder='twscrape search {{query}} --limit {{limit}} --json' /></label>
          <label class="inline-check"><input type="checkbox" name="clear_x_auth" /><span>Clear X auth</span></label>

          <div class="settings-heading full-span">
            <h2>Intelligence & LLM</h2>
            <p>总控台会聚合交易所情报、Twitter 账号、链上异动、现货/合约价差和策略命中。未配置 OpenAI 时使用本地规则分析。</p>
          </div>
          <label class="inline-check"><input type="checkbox" name="intelligence_enabled" {"checked" if params["intelligence_enabled"] else ""} /><span>Enable intelligence center</span></label>
          <label class="inline-check"><input type="checkbox" name="intelligence_llm_enabled" {"checked" if params["intelligence_llm_enabled"] else ""} /><span>Enable LLM analysis</span></label>
          <label><span>LLM Provider</span><select name="llm_provider">{llm_options}</select></label>
          <label><span>LLM API Key</span><input type="password" name="llm_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>LLM Base URL</span><input type="text" name="llm_base_url" value="{escape(str(params['intelligence_llm_base_url']))}" placeholder="留空使用预设地址" /></label>
          <label><span>LLM Model</span><input type="text" name="llm_model" value="{escape(str(params['intelligence_llm_model']))}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_llm_auth" /><span>Clear LLM auth</span></label>
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
          <label><span>Default Preset</span><select name="backtest_preset">{''.join(_option(item, str(params['backtest_preset'])) for item in ['custom', 'balanced_swing', 'breakout_aggressive', 'portfolio_rotation', 'crypto_rebalance_premium', 'btc_overnight_seasonality', 'btc_cycle_trend', 'btc_core_trading', 'btc_compounding_risk_off'])}</select></label>
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
    content = _with_settings_descriptions(content, active_lang)
    return _layout(
        page_title="Runtime Settings",
        active_page="settings",
        hero_title=t("把数据源、情报源和策略参数都收进一个运行时配置面板。", "Manage data sources, intelligence sources, and strategy parameters in one runtime console."),
        hero_text=t("密钥、Twitter 监控账号、扫描默认值和回测默认策略都可以在这里改。保存后，扫描页和回测页会直接吃新的默认配置。", "Configure credentials, Twitter tracked accounts, scan defaults, and backtest strategy defaults. Saved changes are applied directly across the system."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/settings",
        layout_context=layout_context,
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


def _curve_values(values: object, fallback: float = 1.0) -> list[float]:
    if isinstance(values, list):
        parsed = [float(value) for value in values if isinstance(value, int | float)]
        if parsed:
            return parsed
    return [1.0, fallback]


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
          <section class="benchmark-workbench empty">
            <article class="empty-state compact">
              <h2>基准测试</h2>
              <p>运行单币种回测后会显示策略权益、BTC/标的持有基准和交易流水。</p>
            </article>
          </section>
        """

    ranked = sorted(series_reports, key=lambda item: float(item.get("final_equity", 1.0)), reverse=True)
    active = ranked[0]
    comparison = ranked[1] if len(ranked) > 1 else None
    strategy_values = _curve_values(active.get("equity_points"), float(active.get("final_equity", 1.0)))
    hold_values = _curve_values(active.get("buy_hold_equity_points"), float(active.get("buy_hold_final_equity", 1.0)))
    comparison_values = _curve_values(comparison.get("equity_points"), float(comparison.get("final_equity", 1.0))) if comparison else []
    all_values = [*strategy_values, *hold_values, *comparison_values]
    minimum = min(all_values)
    maximum = max(all_values)
    padding = max((maximum - minimum) * 0.08, 0.02)
    minimum -= padding
    maximum += padding
    strategy_line = _benchmark_line_points(strategy_values, minimum=minimum, maximum=maximum)
    hold_line = _benchmark_line_points(hold_values, minimum=minimum, maximum=maximum)
    comparison_line = _benchmark_line_points(comparison_values, minimum=minimum, maximum=maximum) if comparison else ""
    final_equity = float(active.get("final_equity", 1.0))
    hold_equity = float(active.get("buy_hold_final_equity", 1.0))
    comparison_equity = float(comparison.get("final_equity", 1.0)) if comparison else None
    strategy_pnl = (final_equity - 1.0) * 10_000
    hold_pnl = (hold_equity - 1.0) * 10_000
    comparison_pnl = ((comparison_equity or 1.0) - 1.0) * 10_000
    comparison_label = (
        f"""
        <div class="benchmark-floating-label muted">
          <span>Strategy Returns V1</span>
          <strong>{_money_from_equity(comparison_equity or 1.0)}</strong>
          <small>{comparison_pnl:+,.2f} · {_return_from_equity(comparison_equity or 1.0)}</small>
        </div>
        """
        if comparison
        else ""
    )

    return f"""
      <section class="benchmark-workbench">
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
              <div>
                <span class="legend-dot strategy"></span> 策略
                <span class="legend-dot comparison"></span> V1
                <span class="legend-dot hold"></span> 持有基准
              </div>
            </div>
            <div class="benchmark-chart">
              <svg viewBox="0 0 860 340" preserveAspectRatio="none" aria-hidden="true">
                <g class="benchmark-grid-lines">
                  <line x1="0" x2="860" y1="68" y2="68"></line>
                  <line x1="0" x2="860" y1="136" y2="136"></line>
                  <line x1="0" x2="860" y1="204" y2="204"></line>
                  <line x1="0" x2="860" y1="272" y2="272"></line>
                </g>
                <polyline class="benchmark-line hold" points="{escape(hold_line)}"></polyline>
                {f'<polyline class="benchmark-line comparison" points="{escape(comparison_line)}"></polyline>' if comparison_line else ''}
                <polyline class="benchmark-line strategy" points="{escape(strategy_line)}"></polyline>
              </svg>
              <div class="benchmark-floating-label primary">
                <span>Strategy Returns V2</span>
                <strong>{_money_from_equity(final_equity)}</strong>
                <small>{strategy_pnl:+,.2f} · {_return_from_equity(final_equity)}</small>
              </div>
              {comparison_label}
              <div class="benchmark-floating-label hold-label">
                <span>{escape(str(active.get("symbol", "BTC")))} Holding Returns</span>
                <strong>{_money_from_equity(hold_equity)}</strong>
                <small>{hold_pnl:+,.2f} · {_return_from_equity(hold_equity)}</small>
              </div>
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
            <div class="mini-stat"><span>Rebalance Premium</span><strong>{best_rebalance_premium:+.2f}%</strong></div>
          </div>
        </article>
        {_strategy_explanation_card(strategy_explanation)}
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
        <article class="overview-card strategy-explain-card">
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
          <div class="table-shell">
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
      <table class="data-table">
        <tr><th>Symbol</th><th>Check</th><th>Score</th><th>Slip</th><th>Equity</th><th>Max DD</th><th>Trades</th><th>PF</th><th>Window</th></tr>
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


def _rebalance_card(report: dict[str, object]) -> str:
    return f"""
      <article class="portfolio-card">
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
        <div class="table-shell">
          <h3>Recent Rebalances</h3>
          {_rebalance_rows(report["snapshots"])}
        </div>
      </article>
    """


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
      <table class="data-table">
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
    rebalance_reports = rebalance_reports or []
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
        <span>Rebalance Reports</span>
        <strong>{len(rebalance_reports)}</strong>
        <small>{t("等权再平衡", "equal-weight rebalance")}</small>
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
    rebalance_html = "".join(_rebalance_card(report) for report in rebalance_reports)
    series_html = "".join(_backtest_card(report) for report in series_reports)
    if not portfolio_html:
        portfolio_html = '<article class="empty-state compact"><h2>还没有组合结果。</h2><p>传入多个币种 ZIP 并启用 top N，才会看到组合回测。</p></article>'
    if not series_html:
        series_html = '<article class="empty-state compact"><h2>还没有回测结果。</h2><p>输入本地 ZIP pattern 后提交，页面会直接运行历史回测。</p></article>'
    if not rebalance_html and str(params["preset"]) == "crypto_rebalance_premium":
        rebalance_html = '<article class="empty-state compact"><h2>还没有再平衡报告。</h2><p>需要至少两个币种有相同时间戳的历史 K 线。</p></article>'

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
          <label class="inline-check"><input type="checkbox" name="stability_checks" {"checked" if params.get("stability_checks") else ""} /><span>Stability Checks</span><small class="settings-description">额外运行 score±3、滑点上调和滚动 walk-forward 复测。</small></label>
          <button type="submit">运行回测</button>
        </form>
        <p class="helper-text">
          页面会直接读取你本机上的 Binance public-data ZIP。支持 glob pattern、多个 pattern 换行，以及组合层 top N 回测。
        </p>
      </section>

      {_benchmark_workbench(series_reports)}

      {_backtest_overview(params=params, series_reports=series_reports, portfolio_reports=portfolio_reports, rebalance_reports=rebalance_reports, strategy_explanation=strategy_explanation)}

      <section class="section-block">
        <div class="section-heading">
          <h2>Rebalance Premium</h2>
          <p>比较等权定期再平衡组合和买入后自然漂移组合。</p>
        </div>
        <div class="portfolio-grid">{rebalance_html or '<article class="empty-state compact"><h2>选择 Crypto Rebalance Premium 预设后显示。</h2><p>该报告用于研究加密资产等权再平衡溢价。</p></article>'}</div>
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
        hero_title=t("把本地 Binance 历史 K 线直接拉进页面里回测。", "Run backtests directly from local Binance historical kline archives."),
        hero_text=t("同一页里调整分数阈值、止盈止损、滑点模型和组合仓位约束，直接看单币种与组合结果。", "Tune score thresholds, stop loss, take profit, slippage model, and portfolio exposure constraints on one page."),
        hero_right=hero_right,
        content=content,
        lang=active_lang,
        current_path="/backtest",
        layout_context=layout_context,
    )
