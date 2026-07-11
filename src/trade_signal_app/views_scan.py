from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from .views_common import _hidden_lang_input, _layout, _option, _text, _url, normalize_language


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
    return "".join(f'<span class="ant-tag chip {chip_class}">{escape(item)}</span>' for item in items)


def _table_warning_items(warnings: list[object], limit: int = 2) -> list[object]:
    selected = list(warnings[:limit])
    for warning in warnings[limit:]:
        if _is_scan_warning(warning) and warning not in selected:
            selected.append(warning)
    return selected


def _is_scan_warning(value: object) -> bool:
    return "完整扫描" in str(value)


def _table_warning_tag(value: object, lang: str) -> str:
    raw = str(value)
    class_name = "ant-tag table-tag warning"
    label = raw
    if _is_scan_warning(raw):
        class_name += " scan-warning"
        label = _text(lang, "完整扫描超时，已返回实时 ticker，后台刷新中", "Full scan timed out; live ticker fallback is refreshing")
    return f'<span class="{class_name}" title="{escape(raw)}">{escape(label)}</span>'


def _community_detail(signal: dict[str, object]) -> str:
    summary = str(signal.get("community_summary") or "").strip()
    drivers = [str(item) for item in signal.get("community_drivers") or [] if str(item).strip()]
    risks = [str(item) for item in signal.get("community_risks") or [] if str(item).strip()]
    samples = [str(item) for item in signal.get("community_samples") or [] if str(item).strip()]
    if not summary and not drivers and not risks and not samples:
        return ""
    driver_tags = _chips(drivers[:4], "positive") if drivers else '<span class="muted">暂无明确多头驱动词</span>'
    risk_tags = _chips(risks[:4], "warning") if risks else '<span class="muted">暂无明显风险词</span>'
    sample_items = "".join(f"<li>{escape(item)}</li>" for item in samples[:3])
    samples_html = f"<ul>{sample_items}</ul>" if sample_items else '<p class="muted">暂无可展示样本。</p>'
    return f"""
      <details class="community-detail">
        <summary>社区热度分析</summary>
        <div class="community-detail-body">
          {f'<p>{escape(summary)}</p>' if summary else ""}
          <div class="community-detail-grid">
            <div><strong>多头驱动</strong><div class="chips compact-chips">{driver_tags}</div></div>
            <div><strong>风险过滤</strong><div class="chips compact-chips">{risk_tags}</div></div>
          </div>
          <div class="community-samples">
            <strong>筛选后样本</strong>
            {samples_html}
          </div>
        </div>
      </details>
    """


def _community_badge(signal: dict[str, object], *, table: bool = False) -> str:
    if signal.get("community_score") is None:
        return ""
    mentions = ""
    if signal.get("community_mentions") is not None:
        mentions = f' · {int(signal["community_mentions"])} mentions'
    sentiment = ""
    if signal.get("community_sentiment") is not None:
        sentiment_value = float(signal["community_sentiment"])
        sentiment = f' · senti {sentiment_value:+.2f}'
    source = escape(str(signal.get("community_source") or "community"))
    if table:
        return (
            f'<div class="community-cell-main">{float(signal["community_score"]):.0f}'
            f'<span>{source}{mentions}{sentiment}</span></div>'
        )
    return (
        f'<span class="ant-tag chip neutral">社区 {float(signal["community_score"]):.0f} / 100 · '
        f'{source}{mentions}{sentiment}</span>'
    )


def _volatility_badge(signal: dict[str, object], lang: str) -> str:
    regime = str(signal.get("volatility_regime") or "normal")
    label = str(signal.get("volatility_label") or _text(lang, "常态波动", "Normal Volatility"))
    percentile = float(signal.get("volatility_percentile") or 0.0)
    ratio = float(signal.get("volatility_ratio") or 1.0)
    return (
        f'<span class="ant-tag volatility-tag volatility-{escape(regime)}" '
        f'title="percentile {percentile:.1f}% · ratio {ratio:.2f}x">{escape(label)} · P{percentile:.0f}</span>'
    )


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


def _community_operation_panel(params: dict[str, object], signals: list[dict[str, object]], lang: str) -> str:
    t = lambda zh, en: _text(lang, zh, en)
    provider = str(params.get("community_provider") or "auto")
    x_provider = str(params.get("x_provider") or "official_api")
    x_account_mode = str(params.get("x_account_mode") or "off")
    x_configured = bool(params.get("x_provider_configured"))
    local_configured = bool(params.get("community_local_configured"))
    exchange_configured = bool(params.get("exchange_community_configured"))
    tracked_count = int(params.get("tracked_account_count") or 0)
    has_token_analysis = any(signal.get("community_score") is not None for signal in signals)
    if has_token_analysis:
        status = t("已生成 token 级社区热度分析", "Token-level community analysis generated")
        status_class = "ready"
    elif x_configured or local_configured or exchange_configured:
        status = t("已开启，等待完整扫描匹配社区消息", "Enabled, waiting for full scan to match community messages")
        status_class = "pending"
    else:
        status = t("未接入可用社区数据源", "No usable community data source configured")
        status_class = "muted"
    provider_options = ["auto", "exchange", "x", "csv", "news", "telegram", "reddit", "exchange,x", "exchange,reddit", "x,csv", "x,reddit", "exchange,x,csv,news,telegram,reddit"]
    x_provider_options = ["official_api", "nitter_rss", "session_scrape"]
    account_mode_options = ["off", "blend", "only"]
    return f"""
      <section class="community-ops" aria-label="{t("社区热度分析", "Community heat analysis")}">
        <div class="community-ops-copy">
          <span class="eyebrow">{t("社区热度分析", "Community Heat")}</span>
          <strong>{escape(status)}</strong>
          <small>
            Provider {escape(provider)} · X {escape(x_provider)} · {t("跟踪账号", "tracked accounts")} {tracked_count}
          </small>
        </div>
        <form method="post" action="{_url('/scan/community/update', lang)}" class="community-ops-form">
          {_hidden_lang_input(lang)}
          <label>
            <span>{t("社区来源", "Community Source")}</span>
            <select name="community_provider">{''.join(_option(item, provider) for item in provider_options)}</select>
          </label>
          <label>
            <span>X Provider</span>
            <select name="x_provider">{''.join(_option(item, x_provider) for item in x_provider_options)}</select>
          </label>
          <label>
            <span>{t("账号模式", "Account Mode")}</span>
            <select name="x_account_mode">{''.join(_option(item, x_account_mode) for item in account_mode_options)}</select>
          </label>
          <button type="submit">{t("保存并重扫", "Save & Rescan")}</button>
        </form>
        <div class="community-ops-links">
          <span class="status-dot {status_class}"></span>
          <a href="{escape(_url('/settings#settings-twitter', lang), quote=True)}">{t("配置账号/API", "Configure Accounts/API")}</a>
          <a href="{escape(_url('/terminal/community', lang), quote=True)}">{t("查看社区情报", "View Community Intel")}</a>
        </div>
      </section>
    """


def _signal_empty_state(lang: str) -> str:
    return f"""
    <article class="ant-empty-state empty-state">
      <h2>{_text(lang, "当前条件下没有足够强的候选币种。", "No sufficiently strong candidates under the current filters.")}</h2>
      <p>{_text(lang, "可以适当降低最小成交额或增大候选数，再重新扫描。", "Lower minimum quote volume or increase the candidate pool, then scan again.")}</p>
    </article>
    """


def _signal_card(signal: dict[str, object]) -> str:
    grade_class = str(signal["grade"]).lower().replace("+", "-plus")
    community = _community_badge(signal)
    change_pct = float(signal["price_change_percent"])

    return f"""
    <article class="ant-card signal-card grade-{grade_class}" data-live-symbol="{escape(str(signal['symbol']))}">
      <div class="signal-topline">
        <div>
          <p class="symbol">{escape(str(signal["symbol"]))}</p>
          <p class="subline">24h <span data-live-change class="{'positive' if change_pct >= 0 else 'negative'}">{change_pct:+.2f}%</span></p>
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
          <span>最新价</span>
          <strong data-live-price data-live-value="{float(signal.get('last_price') or 0.0):.12g}">{float(signal.get("last_price") or 0.0):.6g}</strong>
        </div>
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

      {_community_detail(signal)}

      <footer class="card-footer">
        <span>24h 成交额 {float(signal["quote_volume_m"]):.1f}M</span>
        <span>{_volatility_badge(signal, "zh")} · ATR {float(signal.get("atr_pct") or 0.0):.2f}%</span>
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
        _text(lang, "最新价", "Last Price"),
        "24h",
        _text(lang, "成交额", "Quote Vol"),
        "RSI",
        _text(lang, "量比", "Vol Ratio"),
        _text(lang, "波动状态", "Volatility"),
        "EMA",
        "MACD",
        _text(lang, "社区", "Community"),
        _text(lang, "原因", "Reasons"),
    ]
    header = "".join(f"<th>{escape(item)}</th>" for item in headers)
    column_group = """
          <colgroup>
            <col class="col-symbol" />
            <col class="col-grade" />
            <col class="col-score" />
            <col class="col-price" />
            <col class="col-change" />
            <col class="col-volume" />
            <col class="col-rsi" />
            <col class="col-volume-ratio" />
            <col class="col-volatility" />
            <col class="col-ema" />
            <col class="col-macd" />
            <col class="col-community" />
            <col class="col-reasons" />
          </colgroup>
        """
    rows = []
    for signal in signals:
        grade = str(signal["grade"])
        grade_class = grade.lower().replace("+", "-plus")
        community_badge = _community_badge(signal, table=True)
        community_detail = _community_detail(signal)
        community = (
            f"{community_badge}{community_detail}"
            if community_badge or community_detail
            else _text(lang, "未接入", "Not configured")
        )
        reasons = list(signal.get("reasons") or [])[:3]
        warnings = _table_warning_items(list(signal.get("warnings") or []))
        reason_tags = "".join(f'<span class="ant-tag table-tag positive">{escape(str(item))}</span>' for item in reasons)
        warning_tags = "".join(_table_warning_tag(item, lang) for item in warnings)
        rows.append(
            f"""
            <tr data-live-symbol="{escape(str(signal['symbol']))}">
              <td><strong class="table-symbol">{escape(str(signal["symbol"]))}</strong></td>
              <td><span class="table-grade grade-{grade_class}">{escape(grade)}</span></td>
              <td class="numeric strong">{float(signal["score"]):.1f}</td>
              <td class="numeric"><span data-live-price data-live-value="{float(signal.get('last_price') or 0.0):.12g}">{float(signal.get("last_price") or 0.0):.6g}</span></td>
              <td class="numeric"><span data-live-change class="{'positive' if float(signal['price_change_percent']) >= 0 else 'negative'}">{float(signal["price_change_percent"]):+.2f}%</span></td>
              <td class="numeric">{float(signal["quote_volume_m"]):.1f}M</td>
              <td class="numeric">{float(signal["rsi_14"]):.1f}</td>
              <td class="numeric">{float(signal["volume_ratio"]):.2f}x</td>
              <td>{_volatility_badge(signal, lang)}</td>
              <td class="numeric">{float(signal["ema_spread_pct"]):+.2f}%</td>
              <td class="numeric">{float(signal["macd_hist"]):+.4f}</td>
              <td class="community-cell">{community}</td>
              <td><div class="table-tags">{reason_tags}{warning_tags}</div></td>
            </tr>
            """
        )
    return f"""
      <section class="ant-table-wrapper signal-table-shell table-shell" aria-label="{escape(_text(lang, "信号表格", "Signal table"))}">
        <table class="ant-table data-table signal-table">
          {column_group}
          <thead><tr>{header}</tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </section>
    """


def _signal_score_sort_key(signal: dict[str, object]) -> tuple[float, float, str]:
    try:
        score = float(signal.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        quote_volume_m = float(signal.get("quote_volume_m") or 0.0)
    except (TypeError, ValueError):
        quote_volume_m = 0.0
    return (-score, -quote_volume_m, str(signal.get("symbol") or ""))


def _sort_signals_by_score(signals: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(signals, key=_signal_score_sort_key)


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
    ordered_signals = _sort_signals_by_score(signals)
    signal_results = (
        _signal_table(ordered_signals, active_lang)
        if view_mode == "table"
        else f'<section class="signal-grid">{"".join(_signal_card(signal) for signal in ordered_signals) or _signal_empty_state(active_lang)}</section>'
    )
    scan_warning = str(summary.get("warning") or "")
    scan_notice = ""
    if bool(summary.get("fallback")) or scan_warning:
        notice_text = scan_warning or t(
            "当前为快速扫描结果，完整技术指标扫描仍在后台刷新。",
            "Current results are from the fast scanner while the full indicator scan refreshes in the background.",
        )
        scan_notice = f'<div class="notice notice-warning">{escape(notice_text)}</div>'

    live_market = f"""
      <section
        class="scan-live-market"
        data-live-market
        data-live-state="connecting"
        data-label-connecting="{escape(t('正在连接实时行情', 'Connecting live market'), quote=True)}"
        data-label-live="{escape(t('实时行情在线', 'Live market online'), quote=True)}"
        data-label-fallback="{escape(t('WebSocket 不可用，已切换 REST', 'WebSocket unavailable, using REST'), quote=True)}"
        data-label-retry="{escape(t('实时行情重连中', 'Reconnecting live market'), quote=True)}"
        data-label-websocket="Binance WebSocket"
        data-label-rest="Binance REST"
        aria-live="polite"
      >
        <div class="scan-live-state">
          <span class="live-status-dot" aria-hidden="true"></span>
          <div>
            <strong data-live-status>{t("正在连接实时行情", "Connecting live market")}</strong>
            <small>{t("价格与 24h 涨跌实时更新；评分、支撑阻力和波动状态来自最近一次完整扫描。", "Price and 24h change update live; scores, structure, and volatility remain from the latest full scan.")}</small>
          </div>
        </div>
        <div class="scan-live-meta">
          <span>{t("来源", "Source")} <strong data-live-source>Binance WebSocket</strong></span>
          <span>{t("最近更新", "Updated")} <strong data-live-updated>-</strong></span>
          <button type="button" class="button-secondary" data-live-reconnect>{t("重新连接", "Reconnect")}</button>
        </div>
      </section>
    """

    options = "".join(_option(interval, str(params["interval"])) for interval in intervals)
    candidate_symbols = int(summary.get("candidate_symbols") or summary["scanned_symbols"])
    eligible_symbols = int(summary.get("eligible_symbols") or summary["scanned_symbols"])
    candidate_pool = int(summary.get("candidate_pool") or params["candidate_pool"])
    hero_right = f"""
      <div class="ant-statistic-card stat-card">
        <span>{t("评分候选", "Scored Candidates")}</span>
        <strong>{candidate_symbols}</strong>
        <small>{t("候选设置", "configured")} {candidate_pool} · {t("可选池", "eligible")} {eligible_symbols}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>{t("返回信号", "Returned Signals")}</span>
        <strong>{int(summary["returned_signals"])}</strong>
        <small>{escape(str(summary["interval"]))} {t("周期", "interval")} · ≤ {candidate_symbols}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>{t("最小成交额", "Min Quote Volume")}</span>
        <strong>{float(summary["min_quote_volume"]) / 1_000_000:.0f}M</strong>
        <small>Quote Volume</small>
      </div>
    """
    content = f"""
      <section class="ant-card control-panel">
        {scan_notice}
        {live_market}
        <form method="get" class="ant-form filters">
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
          {t("数据来自 Binance Spot 市场接口。社区热度支持 Binance/OKX 官方热点、X/Twitter、Reddit 和本地", "Market data comes from Binance Spot APIs. Community heat supports Binance/OKX official trends, X/Twitter, Reddit, and local")} <code>data/community_scores.csv</code>{t("，未配置时会自动忽略不可用来源。", "; unavailable sources are skipped automatically.")}
        </p>
        {_community_operation_panel(params, ordered_signals, active_lang)}
        <div class="scan-view-bar">
          <span>{t("展示模式", "View Mode")}</span>
          <div class="view-toggle" aria-label="{t("展示模式", "View mode")}">
            <a class="{cards_class}" href="{escape(_scan_view_url(params, active_lang, "cards"))}">{t("卡片", "Cards")}</a>
            <a class="{table_class}" href="{escape(_scan_view_url(params, active_lang, "table"))}">{t("表格", "Table")}</a>
          </div>
        </div>
      </section>

      {signal_results}
      <script src="/static/scan_live.js" defer></script>
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


__all__ = [
    '_breakdown_bars',
    '_chips',
    '_community_detail',
    '_community_badge',
    '_scan_view_url',
    '_community_operation_panel',
    '_signal_empty_state',
    '_signal_card',
    '_signal_table',
    '_sort_signals_by_score',
    'render_index_page',
]
