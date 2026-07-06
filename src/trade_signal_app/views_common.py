from __future__ import annotations

from html import escape

from .presets import list_backtest_presets


SUPPORTED_LANGUAGES = {"zh", "en"}


_VALUE_LABELS = {
    "zh": {
        "ready": "就绪",
        "read_only": "只读",
        "auth_failed": "认证失败",
        "unchecked": "未检查",
        "configured_pending_connector": "待接入",
        "ready_public": "公开数据就绪",
        "configured": "已配置",
        "api_configured": "接口已配置",
        "api_live": "接口在线",
        "empty": "暂无数据",
        "allow": "允许",
        "block": "阻断",
        "blocked_by_risk": "被风控阻断",
        "monitor": "观察",
        "pass": "通过",
        "basis": "价差",
        "funding": "资金费率",
        "onchain": "链上",
        "strategy": "策略",
        "spot_futures_basis": "现货/合约价差",
        "funding_rate": "合约资金费率",
        "network_snapshot": "网络快照",
        "large_native_transfer": "大额原生资产转账",
        "exchange_inflow": "交易所流入",
        "whale_transfer": "大额转账",
        "blockstream": "Blockstream",
        "evm_rpc": "EVM RPC",
        "blockchair_stats": "Blockchair",
        "solana_rpc": "Solana RPC",
        "xrpl_rpc": "XRPL RPC",
        "token_missing": "缺少令牌",
        "fallback": "本地规则",
        "local_csv": "本地 CSV",
        "guarded": "受保护",
        "active": "启用",
        "disabled": "停用",
        "not_configured": "未配置",
        "paper_ready": "模拟就绪",
        "pending_scan": "待扫描",
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
        "profit_protect_stop": "浮盈保护止损",
        "candidate_buy": "候选买入",
        "watch": "观察",
        "priority_watch": "优先观察",
        "short_watch": "空头观察",
        "rebound_long_watch": "反弹多头观察",
        "watch_requires_funding": "待资金费率确认",
        "auto_score_breakout": "综合评分突破",
        "volume_pressure": "量价压力",
        "market_momentum_watch": "行情动量观察",
        "low_float_momentum_long": "小市值动量多头",
        "blowoff_distribution_short": "末端分布空头",
        "capitulation_rebound_long": "暴跌反弹多头",
        "scan_cache": "扫描缓存",
        "live_ticker": "实时行情",
        "local": "本地规则",
        "rules": "规则引擎",
        "local_rules": "本地规则",
        "llm": "大模型",
        "high": "高",
        "medium": "中",
        "low": "低",
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
        "api_configured": "API Configured",
        "api_live": "API Live",
        "empty": "Empty",
        "allow": "Allow",
        "block": "Block",
        "blocked_by_risk": "Blocked by Risk",
        "monitor": "Monitor",
        "pass": "Pass",
        "basis": "Basis",
        "funding": "Funding",
        "onchain": "On-chain",
        "strategy": "Strategy",
        "spot_futures_basis": "Spot/Futures Basis",
        "funding_rate": "Funding Rate",
        "network_snapshot": "Network Snapshot",
        "large_native_transfer": "Large Native Transfer",
        "exchange_inflow": "Exchange Inflow",
        "whale_transfer": "Whale Transfer",
        "blockstream": "Blockstream",
        "evm_rpc": "EVM RPC",
        "blockchair_stats": "Blockchair",
        "solana_rpc": "Solana RPC",
        "xrpl_rpc": "XRPL RPC",
        "token_missing": "Token Missing",
        "fallback": "Local Fallback",
        "local_csv": "Local CSV",
        "guarded": "Guarded",
        "active": "Active",
        "disabled": "Disabled",
        "not_configured": "Not Configured",
        "paper_ready": "Paper Ready",
        "pending_scan": "Pending Scan",
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
        "profit_protect_stop": "Profit Protection Stop",
        "candidate_buy": "Candidate Buy",
        "watch": "Watch",
        "priority_watch": "Priority Watch",
        "short_watch": "Short Watch",
        "rebound_long_watch": "Rebound Long Watch",
        "watch_requires_funding": "Needs Funding Check",
        "auto_score_breakout": "Score Breakout",
        "volume_pressure": "Volume Pressure",
        "market_momentum_watch": "Market Momentum Watch",
        "low_float_momentum_long": "Low-float Momentum Long",
        "blowoff_distribution_short": "Blow-off Distribution Short",
        "capitulation_rebound_long": "Capitulation Rebound Long",
        "scan_cache": "Scan Cache",
        "live_ticker": "Live Ticker",
        "local": "Local",
        "rules": "Rules Engine",
        "local_rules": "Local Rules",
        "llm": "LLM",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
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


BACKTEST_PRESET_ZH_LABELS = {
    "custom": "自定义参数",
    "balanced_swing": "均衡波段",
    "breakout_aggressive": "激进突破",
    "portfolio_rotation": "组合轮动",
    "crypto_rebalance_premium": "加密资产等权再平衡",
    "btc_overnight_seasonality": "BTC 隔夜季节性",
    "btc_cycle_trend": "BTC 周期趋势",
    "btc_core_trading": "BTC 核心交易",
    "btc_compounding_risk_off": "BTC 复利风控",
}


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
      <div class="ant-segmented language-switch" aria-label="Language">
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


def _backtest_preset_options(selected: str) -> str:
    options: list[str] = []
    for preset in list_backtest_presets():
        preset_id = str(preset["preset_id"])
        zh_label = BACKTEST_PRESET_ZH_LABELS.get(preset_id, str(preset.get("label") or preset_id))
        label = f"{zh_label} · {preset_id}"
        options.append(_option_with_label(preset_id, label, selected))
    return "".join(options)


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
            f'<a class="ant-tabs-tab nav-link{active}" href="{escape(_url(href, lang))}"><span>{escape(label)}</span><small>{escape(sublabel)}</small></a>'
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
        items.append(f'<a class="ant-menu-item sidebar-link{active}" href="{escape(_url(href, lang))}"><span>{escape(label)}</span></a>')
    return f"""
      <div class="ant-menu-item-group sidebar-group">
        <button type="button" class="ant-menu-item-group-title sidebar-group-title">{escape(title)}<span></span></button>
        <div class="ant-menu sidebar-links">{"".join(items)}</div>
      </div>
    """


def _app_sidebar(active_page: str, lang: str, current_path: str) -> str:
    return f"""
      <aside class="ant-layout-sider app-sidebar">
        <a class="ant-sider-brand sidebar-brand" href="{escape(_url('/terminal', lang))}">
          <span class="sidebar-logo">QT</span>
          <span>
            <strong>{_text(lang, "量化交易系统", "Quantitative Trading System")}</strong>
            <small>{_text(lang, "Quantitative Trading System", "Quant Platform")}</small>
          </span>
        </a>
        <nav class="ant-menu sidebar-nav" aria-label="Sidebar">
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
        <div class="ant-card sidebar-footer">
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
      <footer class="ant-affix market-ticker">
        <strong>{_text(lang, "市场行情", "Market Ticker")}</strong>
        <div>{ticker_items}</div>
        <a href="{escape(_url('/terminal/market', lang))}">{_text(lang, "更多", "More")}</a>
      </footer>
    """


def _runtime_scripts() -> str:
    return """
    <script>
      (() => {
        const providerSelect = document.querySelector("[data-llm-provider-select]");
        const baseInput = document.querySelector("[data-llm-base-url]");
        const modelInput = document.querySelector("[data-llm-model]");
        if (!providerSelect || !baseInput || !modelInput) return;

        const optionDefaults = (option) => ({
          baseUrl: option?.dataset.defaultBaseUrl || "",
          model: option?.dataset.defaultModel || "",
        });
        let previous = optionDefaults(providerSelect.selectedOptions[0]);

        const shouldReplace = (input, previousValue) => {
          const initialValue = input.dataset.initialValue || "";
          return !input.value.trim() || input.value.trim() === previousValue || input.value.trim() === initialValue;
        };

        const applyDefaults = () => {
          const option = providerSelect.selectedOptions[0];
          const next = optionDefaults(option);
          if (shouldReplace(baseInput, previous.baseUrl) && next.baseUrl) {
            baseInput.value = next.baseUrl;
          }
          if (shouldReplace(modelInput, previous.model) && next.model) {
            modelInput.value = next.model;
          }
          baseInput.dataset.initialValue = baseInput.value;
          modelInput.dataset.initialValue = modelInput.value;
          previous = next;
        };

        providerSelect.addEventListener("change", applyDefaults);
        applyDefaults();
      })();

      (() => {
        const PAGE_SIZE = 15;
        const label = document.documentElement.lang === "en" ? {
          previous: "Previous",
          next: "Next",
          page: "Page",
          total: "Total",
        } : {
          previous: "上一页",
          next: "下一页",
          page: "第",
          total: "共",
        };

        const buildPager = ({ total, page, onPage }) => {
          const pageCount = Math.ceil(total / PAGE_SIZE);
          const pager = document.createElement("nav");
          pager.className = "table-pagination";
          pager.setAttribute("aria-label", "Pagination");

          const summary = document.createElement("span");
          summary.className = "pagination-summary";
          summary.textContent = `${label.total} ${total} · ${label.page} ${page + 1}/${pageCount}`;
          pager.appendChild(summary);

          const previous = document.createElement("button");
          previous.type = "button";
          previous.textContent = label.previous;
          previous.disabled = page <= 0;
          previous.addEventListener("click", () => onPage(page - 1));
          pager.appendChild(previous);

          const start = Math.max(0, Math.min(page - 2, pageCount - 5));
          const end = Math.min(pageCount, start + 5);
          for (let index = start; index < end; index += 1) {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = String(index + 1);
            button.className = index === page ? "active" : "";
            button.setAttribute("aria-current", index === page ? "page" : "false");
            button.addEventListener("click", () => onPage(index));
            pager.appendChild(button);
          }

          const next = document.createElement("button");
          next.type = "button";
          next.textContent = label.next;
          next.disabled = page >= pageCount - 1;
          next.addEventListener("click", () => onPage(page + 1));
          pager.appendChild(next);
          return pager;
        };

        const paginateRows = (table) => {
          const rows = Array.from(table.querySelectorAll("tbody tr")).filter((row) => !row.querySelector("th"));
          if (rows.length <= PAGE_SIZE || table.dataset.paginationReady === "1") return;
          table.dataset.paginationReady = "1";
          let page = 0;
          const wrapper = table.closest(".table-shell, .ant-table-wrapper") || table.parentElement;
          const render = (nextPage) => {
            const pageCount = Math.ceil(rows.length / PAGE_SIZE);
            page = Math.max(0, Math.min(nextPage, pageCount - 1));
            const start = page * PAGE_SIZE;
            const end = start + PAGE_SIZE;
            rows.forEach((row, index) => {
              row.hidden = index < start || index >= end;
            });
            wrapper.querySelector(":scope > .table-pagination")?.remove();
            wrapper.appendChild(buildPager({ total: rows.length, page, onPage: render }));
          };
          render(0);
        };

        const paginateCards = (grid) => {
          const items = Array.from(grid.children).filter((item) => item.nodeType === 1);
          if (items.length <= PAGE_SIZE || grid.dataset.paginationReady === "1") return;
          grid.dataset.paginationReady = "1";
          let page = 0;
          const render = (nextPage) => {
            const pageCount = Math.ceil(items.length / PAGE_SIZE);
            page = Math.max(0, Math.min(nextPage, pageCount - 1));
            const start = page * PAGE_SIZE;
            const end = start + PAGE_SIZE;
            items.forEach((item, index) => {
              item.hidden = index < start || index >= end;
            });
            grid.parentElement.querySelector(":scope > .table-pagination")?.remove();
            grid.insertAdjacentElement("afterend", buildPager({ total: items.length, page, onPage: render }));
          };
          render(0);
        };

        document.querySelectorAll("table.data-table").forEach(paginateRows);
        document.querySelectorAll(".signal-grid").forEach(paginateCards);
      })();
    </script>
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
  <body class="body-{escape(active_page)}">
    <main class="ant-layout app-shell">
      {_app_sidebar(active_page, active_lang, current_path)}
      <section class="ant-layout-content workspace page-{escape(active_page)}">
        <header class="ant-layout-header platform-header">
          <nav class="ant-tabs top-nav" aria-label="Primary">
            {_top_nav(active_page, active_lang)}
          </nav>
          <div class="ant-space top-actions" aria-label="Runtime tools">
            <a class="ant-btn ant-btn-default ant-btn-icon-only tool-button" href="{escape(_url('/api/terminal/snapshot', active_lang))}" title="Snapshot" aria-label="Snapshot">{_tool_icon("snapshot")}</a>
            <a class="ant-btn ant-btn-default ant-btn-icon-only tool-button" href="{escape(_url('/settings', active_lang))}" title="Settings" aria-label="Settings">{_tool_icon("settings")}</a>
            <span class="ant-btn ant-btn-default ant-btn-icon-only tool-button is-alert" title="Alerts" aria-label="{alert_count} alerts">{_tool_icon("alerts")}<em>{alert_count}</em></span>
            {_language_switch(active_lang, current_path)}
            <div class="ant-tag user-chip">
              <span>local_runtime</span>
              <small>{_text(active_lang, "本地会话", "Local Session")}</small>
            </div>
          </div>
        </header>

        <section class="ant-page-header hero dashboard-hero">
          <div class="ant-card ant-page-header-heading hero-copy">
            <p class="eyebrow">{escape(page_label)}</p>
            <h1>{escape(hero_title)}</h1>
            <p class="hero-text">{escape(hero_text)}</p>
            <div class="ant-space platform-ribbon">
              <span>Market Intelligence</span>
              <span>Signal Scoring</span>
              <span>Portfolio Backtest</span>
              <span>Runtime Vault</span>
            </div>
          </div>
          <div class="ant-row hero-meta">{hero_right}</div>
        </section>

        {content}
      {_market_ticker(active_lang, ticker_items if isinstance(ticker_items, list) else [], ticker_error, ticker_error_code)}
      </section>
    </main>
    {_runtime_scripts()}
  </body>
</html>
"""


def _module_tabs(items: list[tuple[str, str]], *, active_index: int = 0, label: str = "页面模块") -> str:
    links = []
    for index, (href, title) in enumerate(items, start=1):
        active_class = " active" if index - 1 == active_index else ""
        links.append(
            f'<a class="ant-tabs-tab module-tab{active_class}" href="{escape(href)}">'
            f'<span class="module-tab-index">{index}</span>{escape(title)}</a>'
        )
    return f'<nav class="ant-tabs module-tabs" aria-label="{escape(label)}">{"".join(links)}</nav>'


__all__ = [
    'SUPPORTED_LANGUAGES',
    '_VALUE_LABELS',
    '_EN_VALUE_TRANSLATIONS',
    'BACKTEST_PRESET_ZH_LABELS',
    'normalize_language',
    '_text',
    '_url',
    '_hidden_lang_input',
    '_language_switch',
    '_tool_icon',
    '_display_value',
    '_option',
    '_option_with_label',
    '_backtest_preset_options',
    '_top_nav',
    '_sidebar_group',
    '_app_sidebar',
    '_market_ticker_message',
    '_market_ticker',
    '_runtime_scripts',
    '_layout',
    '_module_tabs',
]
