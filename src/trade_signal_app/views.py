from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from urllib.parse import urlencode

from .presets import get_backtest_preset, list_backtest_presets

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

    return f"""
    <article class="ant-card signal-card grade-{grade_class}">
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
          <span>最新价</span>
          <strong>{float(signal.get("last_price") or 0.0):.6g}</strong>
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
        _text(lang, "最新价", "Last Price"),
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
        community_badge = _community_badge(signal, table=True)
        community_detail = _community_detail(signal)
        community = (
            f"{community_badge}{community_detail}"
            if community_badge or community_detail
            else _text(lang, "未接入", "Not configured")
        )
        reasons = list(signal.get("reasons") or [])[:3]
        warnings = list(signal.get("warnings") or [])[:2]
        reason_tags = "".join(f'<span class="ant-tag table-tag positive">{escape(str(item))}</span>' for item in reasons)
        warning_tags = "".join(f'<span class="ant-tag table-tag warning">{escape(str(item))}</span>' for item in warnings)
        rows.append(
            f"""
            <tr>
              <td><strong class="table-symbol">{escape(str(signal["symbol"]))}</strong></td>
              <td><span class="table-grade grade-{grade_class}">{escape(grade)}</span></td>
              <td class="numeric strong">{float(signal["score"]):.1f}</td>
              <td class="numeric">{float(signal.get("last_price") or 0.0):.6g}</td>
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
      <section class="ant-table-wrapper signal-table-shell table-shell" aria-label="{escape(_text(lang, "信号表格", "Signal table"))}">
        <table class="ant-table data-table signal-table">
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
    scan_warning = str(summary.get("warning") or "")
    scan_notice = ""
    if bool(summary.get("fallback")) or scan_warning:
        notice_text = scan_warning or t(
            "当前为快速扫描结果，完整技术指标扫描仍在后台刷新。",
            "Current results are from the fast scanner while the full indicator scan refreshes in the background.",
        )
        scan_notice = f'<div class="notice notice-warning">{escape(notice_text)}</div>'

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
        {_community_operation_panel(params, signals, active_lang)}
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
        cells = "".join(f"<td>{escape(_format_cell(item.get(key), lang, key=key))}</td>" for _, key in columns)
        rows.append(f"<tr>{cells}</tr>")
    column_count = max(1, len(columns))
    width_class = "terminal-table-compact" if column_count <= 3 else "terminal-table-medium" if column_count <= 5 else "terminal-table-wide"
    return f'<div class="terminal-table-shell"><table class="ant-table data-table terminal-table {width_class}"><tr>{header}</tr><tbody>{"".join(rows)}</tbody></table></div>'


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


_DATETIME_FIELD_KEYS = {
    "created_at",
    "updated_at",
    "entry_time",
    "exit_time",
    "opened_at",
    "closed_at",
    "next_funding_time",
}


def _format_datetime_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


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
    elif raw_status in {"guarded", "partial_configured", "fallback", "monitoring", "watch_only", "pending_scan"}:
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
    today = datetime.now(timezone.utc).date().isoformat()
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
    open_positions = sum(int(_float_from_any(item.get("open_positions"))) for item in accounts)
    max_win_rate = max([_float_from_any(item.get("win_rate_pct")) for item in accounts] or [0.0])
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
        (t("账户权益", "Exposure"), f"{account_exposure:,.2f}", t("已用敞口 USDT", "used exposure USDT"), "green"),
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
    market_sources = snapshot.get("market_sources", [])
    strategy_hits = snapshot["strategy_hits"]
    llm = snapshot["llm_insight"] if isinstance(snapshot.get("llm_insight"), dict) else {}
    risk = snapshot["execution_risk"]
    platform = snapshot["platform"]
    hero_right = f"""
      {_terminal_card(t("扫描标的", "Scanned Symbols"), str(int(snapshot["scanned_symbols"])), "Binance Spot Universe", "cyan")}
      {_terminal_card(t("策略命中", "Strategy Hits"), str(len(strategy_hits)), t("含资金费率过滤", "with funding filters"), "green")}
      {_terminal_card(t("执行风控", "Execution Risk"), _display_value(risk["status"], active_lang).upper(), f'{t("风险分", "risk")} {float(risk["risk_score"]):.1f}', "amber")}
      {_terminal_card(t("可执行候选", "Allowed Candidates"), str(len(risk["allowed_symbols"])), f'{t("已阻断", "blocked")} {len(risk["blocked_symbols"])}', "green")}
    """
    panels = "".join(
        [
            _terminal_dashboard_showcase(snapshot, active_lang),
            _terminal_panel(t("功能实现状态", "Capability Status"), t("架构组件、API 入口和配置状态。", "Architecture components, API endpoints, and configuration state."), _terminal_rows(platform["components"], [(t("层级", "Layer"), "layer"), (t("名称", "Name"), "name"), (t("状态", "Status"), "status"), (t("能力", "Capability"), "capability"), (t("接口", "Endpoint"), "endpoint")], lang=active_lang), wide=True),
            _terminal_panel(t("交易账户概览", "Trading Accounts"), t("模拟交易和真实交易账户状态。", "Paper and live account state."), _terminal_rows(platform["accounts"], [(t("交易所", "Exchange"), "exchange"), (t("模式", "Mode"), "mode"), (t("状态", "Status"), "status"), (t("持仓数", "Positions"), "open_positions"), (t("敞口", "Exposure"), "quote_exposure"), (t("已实现盈亏", "Realized PnL"), "realized_pnl"), (t("胜率", "Win Rate"), "win_rate_pct")], lang=active_lang), wide=True),
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
    market_sources = snapshot.get("market_sources", [])
    strategy_hits = snapshot["strategy_hits"]
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
        panels = "".join(
            [
                notice_html,
                _terminal_panel(t("现货 / 合约价差", "Spot / Futures Basis"), t("用于套利、对冲、资金费率观察和异常价差阻断。", "Used for arbitrage, hedging, funding-rate monitoring, and basis anomaly blocks."), _terminal_rows(spreads, [(t("标的", "Symbol"), "symbol"), (t("现货", "Spot"), "spot_exchange"), (t("现货价格", "Spot Price"), "spot_price"), (t("合约", "Futures"), "futures_exchange"), (t("合约价格", "Futures Price"), "futures_price"), ("Spread bps", "spread_bps"), (t("方向", "Direction"), "direction")], lang=active_lang), wide=True),
                _terminal_panel(t("合约资金费率", "Futures Funding"), t("极端正费率会参与执行前阻断，负费率可作为暴跌反弹的空头拥挤确认。", "Extreme positive funding feeds pre-trade blocks; negative funding confirms short-crowding rebounds."), _terminal_rows(funding_rates, [(t("标的", "Symbol"), "symbol"), (t("合约", "Futures"), "futures_exchange"), ("Funding bps", "funding_rate_bps"), ("Annualized %", "annualized_pct"), (t("来源", "Source"), "source")], lang=active_lang), wide=True),
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
        auto_status = paper_auto_status or {}
        auto_running = bool(auto_status.get("running"))
        auto_error = str(auto_status.get("last_error") or "")
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
              <p>{t("按固定间隔自动扫描策略信号并以 paper 模式执行开仓、止盈和止损。不会提交真实订单。", "Automatically scan strategy signals on an interval and execute entries, take profit, and stop loss in paper mode. No live orders are submitted.")}</p>
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
        last_price_text = t("待刷新", "Pending") if last_price is None else f'{float(last_price):.8f}'
        pnl_text = t("待刷新", "Pending") if unrealized_pnl is None else f'{float(unrealized_pnl):+.2f}'
        return_text = t("待刷新", "Pending") if unrealized_pnl_pct is None else f'{float(unrealized_pnl_pct):+.2f}%'
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
              <td class="pnl-cell{return_class}">{escape(pnl_text)}</td>
              <td class="pnl-cell{return_class}">{escape(return_text)}</td>
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
          <th>{t("浮动盈亏", "Unrealized PnL")}</th>
          <th>{t("收益率", "Return")}</th>
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


def _settings_description_map(lang: str) -> dict[str, str]:
    pairs = {
        "Binance API Key": ("用于读取 Binance 账户权限、费率和提交受保护的实盘订单。留空会保留原值。", "Used for Binance account checks, fees, and guarded live orders. Leave blank to keep the saved value."),
        "Binance API Secret": ("用于签名 Binance 私有接口请求，不会显示在页面或 URL 中。", "Signs Binance private API requests; it is never shown in the page or URL."),
        "Binance RecvWindow": ("Binance 签名请求允许的时间窗口，网络较慢时可适当调大。", "Allowed timing window for signed Binance requests; increase it if your network is slow."),
        "Clear Binance auth": ("勾选后保存会清空已保存的 Binance key 和 secret。", "When checked, saving clears the saved Binance key and secret."),
        "OKX API Key": ("用于读取 OKX 账户余额、执行订单预检和提交受保护的实盘订单。留空会保留原值。", "Used for OKX balances, order precheck, and guarded live orders. Leave blank to keep the saved value."),
        "OKX API Secret": ("用于签名 OKX 私有接口请求，不会显示在页面或 URL 中。", "Signs OKX private API requests; it is never shown in the page or URL."),
        "OKX Passphrase": ("OKX API 创建时设置的 passphrase，需与 key/secret 配套。", "Passphrase configured when creating the OKX API key."),
        "Clear OKX auth": ("勾选后保存会清空已保存的 OKX 三项凭据。", "When checked, saving clears the saved OKX credentials."),
        "Market Data Preset": ("默认公开行情服务。TradingView 为非官方补充源，会缓存为本地 CSV 后再回测。", "Default public market data service. TradingView is an unofficial supplemental source cached to local CSV before backtesting."),
        "TradingView Username": ("可选 TradingView 用户名；留空时尝试匿名非官方会话。", "Optional TradingView username; blank attempts an anonymous unofficial session."),
        "TradingView Password": ("可选 TradingView 密码。留空会保留原值，不会显示在页面或 URL 中。", "Optional TradingView password. Leave blank to keep the saved value; it is not shown in the page or URL."),
        "TradingView Exchange": ("TradingView 交易所代码，例如 BINANCE、OKX、COINBASE。", "TradingView exchange code, such as BINANCE, OKX, or COINBASE."),
        "TradingView Symbols": ("默认拉取的 TradingView 标的，一行一个，例如 BTCUSDT。", "Default TradingView symbols to fetch, one per line, such as BTCUSDT."),
        "TradingView Interval": ("TradingView 历史 K 线周期；拉取后会保存到 data/tradingview_klines。", "TradingView historical candle interval; fetched data is saved under data/tradingview_klines."),
        "TradingView Bars": ("每次拉取的 K 线数量；数值越大越慢，也更容易触发非官方源限制。", "Number of candles per fetch; larger values are slower and more likely to hit unofficial source limits."),
        "TradingView cache": ("勾选后把拉取结果写入本地 CSV 缓存，回测会直接读取该缓存。", "When checked, fetched data is written to local CSV cache for backtesting."),
        "Clear TradingView auth": ("勾选后保存会清空已保存的 TradingView 密码。", "When checked, saving clears the saved TradingView password."),
        "On-chain Data Preset": ("默认链上/DeFi 数据服务。Open Multi-chain、DefiLlama 和 GeckoTerminal 可无密钥使用；本地 CSV 适合私有数据。", "Default on-chain/DeFi data service. Open Multi-chain, DefiLlama, and GeckoTerminal can be used keylessly; local CSV is for private data."),
        "On-chain API Key": ("可选链上数据 Key；当前公开预设可留空，付费或自建网关需要时再填写。", "Optional on-chain data key; keyless presets can leave it blank, paid or private gateways can use it."),
        "On-chain API Base URL": ("可选链上数据自定义网关地址；留空时使用预设服务的默认地址。", "Optional custom on-chain gateway URL; blank uses the preset default."),
        "Clear On-chain auth": ("勾选后保存会清空已保存的链上数据 API Key。", "When checked, saving clears the saved on-chain API key."),
        "X Bearer Token": ("用于调用 X/Twitter API 拉取社区热度和指定账号情报。", "Used to call X/Twitter APIs for community heat and tracked-account intelligence."),
        "X Provider": ("选择 X/Twitter 数据来源：official_api 使用 Bearer Token；nitter_rss 使用 Nitter RSS；session_scrape 使用本地只读抓取命令。", "Select X/Twitter source: official_api uses Bearer Token; nitter_rss uses Nitter RSS; session_scrape uses a local read-only scraper command."),
        "Community Provider": ("选择社区数据来源；auto 会组合 Binance/OKX 官方热点、已配置凭据和本地 CSV。", "Select community data sources; auto combines Binance/OKX official trends, configured credentials, and local CSV files."),
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
        "Execution Exchange": ("选择自动交易执行账户。扫描行情仍使用当前公开行情源，订单会提交到所选交易所。", "Select the account used for execution. Scanning still uses the configured public market source; orders use the selected exchange."),
        "Quote Order Qty": ("每次开仓投入的计价资产金额。", "Quote-asset amount allocated to each entry."),
        "Max Open Positions": ("自动交易最多同时持有的仓位数量。", "Maximum number of simultaneous automated positions."),
        "Max Total Exposure": ("自动交易允许占用的最大计价资产敞口。", "Maximum quote exposure allowed for automated trading."),
        "Score Threshold": ("信号分数达到该阈值才允许进入候选或回测交易。", "Signal score must reach this threshold before trading or backtesting entries."),
        "Min Volume Ratio": ("量能放大倍数门槛，低于该值会过滤。", "Minimum volume expansion ratio."),
        "Min Buy Pressure": ("主动买入占比门槛，用于过滤买盘不足的信号。", "Minimum taker-buy pressure ratio."),
        "Stop Loss %": ("价格相对入场价下跌到该比例时触发止损。", "Stop loss percentage from entry price."),
        "Take Profit %": ("价格相对入场价上涨到该比例时触发止盈。", "Take profit percentage from entry price."),
        "Enable profit protection": ("开启后，浮盈达到触发阈值会自动抬高止损，避免盈利单回撤成亏损单。", "Raises the stop after a profit threshold so winners do not fall back into losing trades."),
        "Profit Guard Trigger %": ("浮盈达到该比例后启动保护止损。", "Unrealized gain required before protected stop starts."),
        "Profit Lock %": ("保护启动后，止损至少抬到入场价上方的锁盈比例。", "Minimum locked profit once protection starts."),
        "Trailing Stop %": ("按持仓最高价回撤该比例移动保护止损；值越小越容易提前落袋。", "Trailing pullback from the highest price; smaller values exit sooner."),
        "Cooldown Minutes": ("自动交易开仓或平仓后的冷却时间，避免连续追单。", "Cooldown after automated trades to avoid repeated entries."),
        "Use exchange order precheck/test": ("勾选时 live 模式只做交易所订单预检或测试，不会真实成交。", "When checked, live mode uses exchange order precheck/test without filling real orders."),
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
      <div class="ant-statistic-card stat-card">
        <span>{t("自动引擎", "Auto Engine")}</span>
        <strong>{t("开启", "On") if config["enabled"] else t("关闭", "Off")}</strong>
        <small>{escape(_display_value(config["mode"], active_lang))} {t("模式", "mode")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>{t("当前持仓", "Open Positions")}</span>
        <strong>{len(positions)}</strong>
        <small>{t("上限", "max")} {int(config["max_open_positions"])}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>{t("账户敞口", "Exposure")}</span>
        <strong>{exposure:.0f}</strong>
        <small>{t("上限", "limit")} {float(config["max_total_quote_exposure"]):.0f}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>{t("已实现盈亏", "Realized PnL")}</span>
        <strong>{realized_pnl:+.2f}</strong>
        <small>{t("最近事件", "recent events")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>{t("交易所授权", "Exchange Auth")}</span>
        <strong>{escape(_display_value(auth_status, active_lang))}</strong>
        <small>{t("可用", "available")} {float(readiness.get("quote_available") or 0.0):.2f} {escape(str(readiness.get("quote_asset", "")))}</small>
      </div>
    """
    module_tabs = _module_tabs(
        [
            ("#trading-execution", t("执行", "Execution")),
            ("#trading-positions", t("持仓", "Positions")),
            ("#trading-events", t("事件", "Events")),
        ],
        active_index=0,
        label=t("交易执行模块", "Trading execution modules"),
    )
    content = f"""
      <div class="page-section-stack">
      {module_tabs}
      <section id="trading-execution" class="ant-card control-panel">
        {readiness_notice}
        <form method="post" action="{_url('/trading/run', active_lang)}" class="ant-form trading-command">
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
          <div class="mini-stat"><span>{t("浮盈保护", "Profit Guard")}</span><strong>{float(config.get("profit_protection_trigger_pct", 0)):.1f}%</strong><small>{t("锁盈", "lock")} {float(config.get("profit_protection_lock_pct", 0)):.1f}%</small></div>
          <div class="mini-stat"><span>{t("移动止损", "Trailing Stop")}</span><strong>{float(config.get("trailing_stop_pct", 0)):.1f}%</strong></div>
        </div>
      </section>

      <section id="trading-positions" class="ant-section section-block">
        <div class="section-heading">
          <h2>{t("持仓", "Positions")}</h2>
          <p>{t("自动交易状态保存在本机", "Auto trading state is stored locally at")} <code>data/trading_state.json</code>。</p>
        </div>
        <article class="ant-card portfolio-card table-shell">{_trading_position_rows(positions, active_lang)}</article>
      </section>

      <section id="trading-events" class="ant-section section-block">
        <div class="section-heading">
          <h2>{t("执行事件", "Execution Events")}</h2>
          <p>{t("本次运行的下单、风控和跳过原因。", "Orders, risk checks, and skip reasons from this run.")}</p>
        </div>
        <article class="ant-card backtest-card table-shell">{_trading_event_rows(events, active_lang)}</article>
      </section>
      </div>
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
    tradingview_symbols = "\n".join(str(item) for item in params.get("tradingview_symbols", []))
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
        (
            f'<option value="{escape(str(item.get("provider_id", "")))}"'
            f' data-default-base-url="{escape(str(item.get("base_url", "")), quote=True)}"'
            f' data-default-model="{escape(str(item.get("default_model", "")), quote=True)}"'
            f' {"selected" if str(item.get("provider_id", "")) == str(params["intelligence_llm_provider"]) else ""}>'
            f'{escape(str(item.get("name", item.get("provider_id", ""))))}</option>'
        )
        for item in llm_presets
        if isinstance(item, dict)
    )
    provider_names = {
        str(item.get("provider_id", "")): str(item.get("name", ""))
        for item in llm_presets
        if isinstance(item, dict)
    }
    okx_label = (
        t("开启", "On")
        if status["okx_auth_configured"]
        else t("部分", "Partial")
        if status.get("okx_auth_partial")
        else t("关闭", "Off")
    )
    okx_message = str(status.get("okx_auth_message") or "")
    hero_right = f"""
      <div class="ant-statistic-card stat-card">
        <span>Binance Auth</span>
        <strong>{t("开启", "On") if status["binance_auth_configured"] else t("关闭", "Off")}</strong>
        <small>{escape(str(status["binance_auth_label"]))}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>OKX Auth</span>
        <strong>{escape(okx_label)}</strong>
        <small>{escape(okx_message or t("未配置 OKX 凭据", "OKX credentials not configured"))}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>TradingView</span>
        <strong>{escape(str(params.get("tradingview_exchange", "BINANCE")))}</strong>
        <small>{escape(str(params.get("tradingview_interval", "4h")))} · {int(params.get("tradingview_bars", 0) or 0)} bars</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>X / Reddit</span>
        <strong>{t("开启", "On") if status["x_auth_configured"] else t("本地/公开", "Local/Public")}</strong>
        <small>{int(status["tracked_account_count"])} {t("个 X 跟踪账号", "tracked X accounts")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>Storage</span>
        <strong>{escape(str(status["storage_mode"]))}</strong>
        <small>{t("已启用口令保护", "passphrase protection enabled") if str(status["storage_mode"]) == "Encrypted" else t("配置保存到本地 JSON", "config saved to local JSON")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>Auto Trade</span>
        <strong>{t("开启", "On") if status["autotrade_enabled"] else t("关闭", "Off")}</strong>
        <small>{escape(_display_value(status["autotrade_mode"], active_lang))} {t("执行", "execution")}</small>
      </div>
      <div class="ant-statistic-card stat-card">
        <span>Intelligence</span>
        <strong>{t("开启", "On") if status["intelligence_enabled"] else t("关闭", "Off")}</strong>
        <small>{escape(provider_names.get(str(status.get("llm_provider", "")), str(status.get("llm_provider", "local")))) if status["llm_enabled"] else t("本地规则", "local rules")}</small>
      </div>
    """
    module_tabs = _module_tabs(
        [
            ("#settings-access", "访问凭据"),
            ("#settings-llm", "LLM"),
            ("#settings-twitter", "Twitter"),
            ("#settings-scan", "扫描"),
            ("#settings-autotrade", "自动交易"),
            ("#settings-backtest", "回测"),
            ("#settings-transfer", "导入导出"),
        ],
        active_index=0,
        label="系统配置模块",
    )
    content = f"""
      <div class="page-section-stack">
      {module_tabs}
      <section class="ant-card control-panel">
        {"".join(notices)}
        <div class="settings-form-stack">
          <section id="settings-access" class="settings-tab-panel">
          <form method="post" action="{_url('/settings', active_lang)}" class="ant-form backtest-form settings-form settings-section-form">
          {_hidden_lang_input(active_lang)}
          <input type="hidden" name="settings_section" value="access" />
          <div class="settings-heading full-span">
            <h2>Access</h2>
            <p>密钥通过 POST 提交，不会出现在 URL。留空表示保持当前值。</p>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>交易所授权</h3><p>保存私有接口凭据与签名窗口，所有密钥字段留空会保留当前值。</p></div>
          <div class="settings-grid">
          <label><span>Binance API Key</span><input type="password" name="binance_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>Binance API Secret</span><input type="password" name="binance_api_secret" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>Binance RecvWindow</span><input type="number" step="1" min="1" name="binance_recv_window_ms" value="{float(params['binance_recv_window_ms']):.0f}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_binance_auth" /><span>Clear Binance auth</span></label>
          <label><span>OKX API Key</span><input type="password" name="okx_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>OKX API Secret</span><input type="password" name="okx_api_secret" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>OKX Passphrase</span><input type="password" name="okx_api_passphrase" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_okx_auth" /><span>Clear OKX auth</span></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>行情与 TradingView</h3><p>公开行情、非官方 TradingView 拉取和本地 K 线缓存统一在这里配置。</p></div>
          <div class="settings-grid">
          <label><span>Market Data Preset</span><select name="market_data_preset">{market_options}</select></label>
          <label><span>TradingView Username</span><input type="text" name="tradingview_username" value="{escape(str(params.get('tradingview_username', '')))}" placeholder="可留空使用匿名会话" autocomplete="username" /></label>
          <label><span>TradingView Password</span><input type="password" name="tradingview_password" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>TradingView Exchange</span><input type="text" name="tradingview_exchange" value="{escape(str(params.get('tradingview_exchange', 'BINANCE')))}" /></label>
          <label><span>TradingView Interval</span><select name="tradingview_interval">{''.join(_option(item, str(params.get('tradingview_interval', '4h'))) for item in ['1m', '3m', '5m', '15m', '30m', '45m', '1h', '2h', '3h', '4h', '1d', '1w', '1M'])}</select></label>
          <label><span>TradingView Bars</span><input type="number" min="100" max="50000" step="100" name="tradingview_bars" value="{int(params.get('tradingview_bars', 5000) or 5000)}" /></label>
          <label class="inline-check"><input type="hidden" name="tradingview_cache_enabled" value="0" /><input type="checkbox" name="tradingview_cache_enabled" value="1" {"checked" if params.get("tradingview_cache_enabled") else ""} /><span>TradingView cache</span></label>
          <label class="full-span"><span>TradingView Symbols</span><textarea name="tradingview_symbols" rows="3" placeholder="BTCUSDT&#10;ETHUSDT&#10;SOLUSDT">{escape(tradingview_symbols)}</textarea></label>
          <label class="inline-check"><input type="checkbox" name="clear_tradingview_auth" /><span>Clear TradingView auth</span></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>链上与社区数据</h3><p>链上数据源、X/Twitter 三档 provider 和社区数据组合模式。</p></div>
          <div class="settings-grid">
          <label><span>On-chain Data Preset</span><select name="onchain_data_preset">{onchain_options}</select></label>
          <label><span>On-chain API Key</span><input type="password" name="onchain_api_key" value="" placeholder="公开预设可留空" autocomplete="new-password" /></label>
          <label><span>On-chain API Base URL</span><input type="text" name="onchain_api_base_url" value="{escape(str(params['onchain_api_base_url']))}" placeholder="留空使用预设地址" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_onchain_auth" /><span>Clear On-chain auth</span></label>
          <label><span>X Bearer Token</span><input type="password" name="x_bearer_token" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>X Provider</span><select name="x_provider">{''.join(_option(item, str(params['x_provider'])) for item in ['official_api', 'nitter_rss', 'session_scrape'])}</select></label>
          <label><span>Community Provider</span><select name="community_provider">{''.join(_option(item, str(params['community_provider'])) for item in ['auto', 'exchange', 'x', 'csv', 'news', 'telegram', 'reddit', 'exchange,x', 'exchange,news', 'exchange,reddit', 'exchange,x,csv', 'exchange,x,reddit', 'x,csv', 'x,news', 'x,telegram', 'x,reddit', 'csv,news', 'csv,telegram', 'csv,reddit', 'news,telegram', 'news,reddit', 'telegram,reddit', 'x,csv,news', 'x,csv,telegram', 'x,csv,reddit', 'x,news,telegram', 'x,news,reddit', 'x,telegram,reddit', 'csv,news,telegram', 'csv,news,reddit', 'csv,telegram,reddit', 'news,telegram,reddit', 'exchange,x,csv,news,telegram,reddit', 'x,csv,news,telegram', 'x,csv,news,reddit', 'x,csv,telegram,reddit', 'x,news,telegram,reddit', 'csv,news,telegram,reddit', 'x,csv,news,telegram,reddit'])}</select></label>
          <label><span>X API Base URL</span><input type="text" name="x_api_base_url" value="{escape(str(params['x_api_base_url']))}" /></label>
          <label><span>X Nitter Base URL</span><input type="text" name="x_nitter_base_url" value="{escape(str(params['x_nitter_base_url']))}" placeholder="http://127.0.0.1:8788" /></label>
          <label class="full-span"><span>X Session Command</span><input type="text" name="x_session_command" value="{escape(str(params['x_session_command']))}" placeholder='twscrape search {{query}} --limit {{limit}} --json' /></label>
          <label class="inline-check"><input type="checkbox" name="clear_x_auth" /><span>Clear X auth</span></label>
          </div>
          </div>
          <div class="settings-submit-bar">
            <button type="submit">保存访问凭据</button>
          </div>
          </form>
          </section>

          <section id="settings-llm" class="settings-tab-panel">
          <form method="post" action="{_url('/settings', active_lang)}" class="ant-form backtest-form settings-form settings-section-form">
          {_hidden_lang_input(active_lang)}
          <input type="hidden" name="settings_section" value="llm" />
          <div class="settings-heading full-span">
            <h2>Intelligence & LLM</h2>
            <p>总控台会聚合交易所情报、Twitter 账号、链上异动、现货/合约价差和策略命中。未配置 OpenAI 时使用本地规则分析。</p>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>模型开关与供应商</h3><p>选择 provider 后会自动带出默认 Base URL 和推荐模型，仍可手动覆盖。</p></div>
          <div class="settings-grid">
          <label class="inline-check"><input type="hidden" name="intelligence_enabled" value="0" /><input type="checkbox" name="intelligence_enabled" value="1" {"checked" if params["intelligence_enabled"] else ""} /><span>Enable intelligence center</span></label>
          <label class="inline-check"><input type="hidden" name="intelligence_llm_enabled" value="0" /><input type="checkbox" name="intelligence_llm_enabled" value="1" {"checked" if params["intelligence_llm_enabled"] else ""} /><span>Enable LLM analysis</span></label>
          <label><span>LLM Provider</span><select name="llm_provider" data-llm-provider-select>{llm_options}</select></label>
          <label><span>LLM API Key</span><input type="password" name="llm_api_key" value="" placeholder="留空保持当前" autocomplete="new-password" /></label>
          <label><span>LLM Base URL</span><input type="text" name="llm_base_url" value="{escape(str(params['intelligence_llm_base_url']))}" placeholder="留空使用预设地址" data-llm-base-url data-initial-value="{escape(str(params['intelligence_llm_base_url']), quote=True)}" /></label>
          <label><span>LLM Model</span><input type="text" name="llm_model" value="{escape(str(params['intelligence_llm_model']))}" data-llm-model data-initial-value="{escape(str(params['intelligence_llm_model']), quote=True)}" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_llm_auth" /><span>Clear LLM auth</span></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>情报阈值</h3><p>控制总控台情报进入风险判断和策略解释的最低强度。</p></div>
          <div class="settings-grid settings-grid-compact">
          <label><span>Min Intel Severity</span><input type="number" step="0.1" min="0" max="100" name="intelligence_min_intel_severity" value="{float(params['intelligence_min_intel_severity']):.1f}" /></label>
          <label><span>Min Spread bps</span><input type="number" step="0.1" min="0" name="intelligence_min_spread_bps" value="{float(params['intelligence_min_spread_bps']):.1f}" /></label>
          <label><span>Whale Threshold USD</span><input type="number" step="100000" min="0" name="intelligence_whale_transfer_threshold_usd" value="{float(params['intelligence_whale_transfer_threshold_usd']):.0f}" /></label>
          </div>
          </div>
          <div class="settings-submit-bar">
            <button type="submit">保存 LLM 与情报配置</button>
          </div>
          </form>
          </section>

          <section id="settings-twitter" class="settings-tab-panel">
          <form method="post" action="{_url('/settings', active_lang)}" class="ant-form backtest-form settings-form settings-section-form">
          {_hidden_lang_input(active_lang)}
          <input type="hidden" name="settings_section" value="twitter" />
          <div class="settings-heading full-span">
            <h2>Twitter Intel</h2>
            <p>账号列表支持一行一个用户名。`blend` 会把普通舆情和指定账号情报按权重混合，`only` 只看指定账号。本地新闻与 Telegram 情报可分别通过 <code>data/news_sentiment.csv</code> 和 <code>data/telegram_sentiment.csv</code> 参与混合。</p>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>X/Twitter 账户监控</h3><p>控制搜索窗口、返回数量、语言过滤和核心账号权重。</p></div>
          <div class="settings-grid">
          <label><span>X Window Hours</span><input type="number" min="1" name="x_recent_window_hours" value="{int(params['x_recent_window_hours'])}" /></label>
          <label><span>X Max Results</span><input type="number" min="10" max="100" name="x_recent_max_results" value="{int(params['x_recent_max_results'])}" /></label>
          <label><span>X Language</span><input type="text" name="x_language" value="{escape(str(params['x_language']))}" /></label>
          <label><span>Account Mode</span><select name="x_account_mode">{''.join(_option(item, str(params['x_account_mode'])) for item in ['off', 'blend', 'only'])}</select></label>
          <label><span>Account Weight %</span><input type="number" step="0.1" min="0" max="100" name="x_account_weight_pct" value="{float(params['x_account_weight_pct']):.1f}" /></label>
          <label class="full-span"><span>Tracked Accounts</span><textarea name="x_tracked_accounts" rows="5" placeholder="@lookonchain&#10;wu_blockchain&#10;TheBlock__">{escape(tracked_accounts)}</textarea></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>Reddit 公共舆情</h3><p>作为社区情绪的补充来源，适合追踪英文热帖和项目讨论。</p></div>
          <div class="settings-grid">
          <label><span>Reddit API Base URL</span><input type="text" name="reddit_api_base_url" value="{escape(str(params['reddit_api_base_url']))}" /></label>
          <label><span>Reddit Window Hours</span><input type="number" min="1" name="reddit_recent_window_hours" value="{int(params['reddit_recent_window_hours'])}" /></label>
          <label><span>Reddit Max Results</span><input type="number" min="5" max="100" name="reddit_max_results" value="{int(params['reddit_max_results'])}" /></label>
          <label class="full-span"><span>Reddit User-Agent</span><input type="text" name="reddit_user_agent" value="{escape(str(params['reddit_user_agent']))}" /></label>
          </div>
          </div>
          <div class="settings-submit-bar">
            <button type="submit">保存 Twitter / Reddit 配置</button>
          </div>
          </form>
          </section>

          <section id="settings-scan" class="settings-tab-panel">
          <form method="post" action="{_url('/settings', active_lang)}" class="ant-form backtest-form settings-form settings-section-form">
          {_hidden_lang_input(active_lang)}
          <input type="hidden" name="settings_section" value="scan" />
          <div class="settings-heading full-span">
            <h2>Scan Defaults</h2>
            <p>这些值会成为实时扫描页的默认参数，你仍然可以在扫描页临时改动。</p>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>扫描候选池</h3><p>控制扫描范围、周期和基础流动性过滤，避免低质量标的拖慢页面。</p></div>
          <div class="settings-grid settings-grid-compact">
          <label><span>Quote Asset</span><input type="text" name="scan_quote_asset" value="{escape(str(params['scan_quote_asset']))}" /></label>
          <label><span>Scan Interval</span><select name="scan_interval">{''.join(_option(item, str(params['scan_interval'])) for item in ['15m', '1h', '4h', '1d'])}</select></label>
          <label><span>Candidate Pool</span><input type="number" min="5" max="40" name="scan_candidate_pool" value="{int(params['scan_candidate_pool'])}" /></label>
          <label><span>Min Quote Volume</span><input type="number" min="1000000" step="1000000" name="scan_min_quote_volume" value="{int(params['scan_min_quote_volume'])}" /></label>
          <label><span>Min Trade Count</span><input type="number" min="100" step="100" name="scan_min_trade_count" value="{int(params['scan_min_trade_count'])}" /></label>
          </div>
          </div>
          <div class="settings-submit-bar">
            <button type="submit">保存扫描默认值</button>
          </div>
          </form>
          </section>

          <section id="settings-autotrade" class="settings-tab-panel">
          <form method="post" action="{_url('/settings', active_lang)}" class="ant-form backtest-form settings-form settings-section-form">
          {_hidden_lang_input(active_lang)}
          <input type="hidden" name="settings_section" value="autotrade" />
          <div class="settings-heading full-span">
            <h2>Auto Trade Defaults</h2>
            <p>自动交易会根据实时扫描分数生成市价单。默认 paper 模式只记录模拟持仓；live 模式还需要服务端环境变量确认才会提交真实订单。</p>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>执行与仓位上限</h3><p>控制自动执行开关、模式、单笔金额和组合敞口。</p></div>
          <div class="settings-grid">
          <label class="inline-check"><input type="hidden" name="autotrade_enabled" value="0" /><input type="checkbox" name="autotrade_enabled" value="1" {"checked" if params["autotrade_enabled"] else ""} /><span>Enable auto trade</span></label>
          <label><span>Execution Mode</span><select name="autotrade_mode">{''.join(_option(item, str(params['autotrade_mode'])) for item in ['paper', 'live'])}</select></label>
          <label><span>Execution Exchange</span><select name="autotrade_execution_exchange">{''.join(_option(item, str(params.get('autotrade_execution_exchange', 'binance'))) for item in ['binance', 'okx'])}</select></label>
          <label><span>Quote Order Qty</span><input type="number" step="0.01" min="0.01" name="autotrade_quote_order_qty" value="{float(params['autotrade_quote_order_qty']):.2f}" /></label>
          <label><span>Max Open Positions</span><input type="number" min="1" name="autotrade_max_open_positions" value="{int(params['autotrade_max_open_positions'])}" /></label>
          <label><span>Max Total Exposure</span><input type="number" step="0.01" min="0.01" name="autotrade_max_total_quote_exposure" value="{float(params['autotrade_max_total_quote_exposure']):.2f}" /></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>信号与风控阈值</h3><p>只有满足分数、量能和买盘条件的信号才会进入自动执行。</p></div>
          <div class="settings-grid">
          <label><span>Score Threshold</span><input type="number" step="0.1" min="0" max="100" name="autotrade_score_threshold" value="{float(params['autotrade_score_threshold']):.1f}" /></label>
          <label><span>Min Volume Ratio</span><input type="number" step="0.01" min="0" name="autotrade_min_volume_ratio" value="{float(params['autotrade_min_volume_ratio']):.2f}" /></label>
          <label><span>Min Buy Pressure</span><input type="number" step="0.01" min="0" max="1" name="autotrade_min_buy_pressure" value="{float(params['autotrade_min_buy_pressure']):.2f}" /></label>
          <label><span>Stop Loss %</span><input type="number" step="0.1" min="0.1" name="autotrade_stop_loss_pct" value="{float(params['autotrade_stop_loss_pct']):.1f}" /></label>
          <label><span>Take Profit %</span><input type="number" step="0.1" min="0.1" name="autotrade_take_profit_pct" value="{float(params['autotrade_take_profit_pct']):.1f}" /></label>
          <label class="inline-check"><input type="hidden" name="autotrade_profit_protection_enabled" value="0" /><input type="checkbox" name="autotrade_profit_protection_enabled" value="1" {"checked" if params.get("autotrade_profit_protection_enabled") else ""} /><span>Enable profit protection</span></label>
          <label><span>Profit Guard Trigger %</span><input type="number" step="0.1" min="0" name="autotrade_profit_protection_trigger_pct" value="{float(params.get('autotrade_profit_protection_trigger_pct', 3.0)):.1f}" /></label>
          <label><span>Profit Lock %</span><input type="number" step="0.1" min="0" name="autotrade_profit_protection_lock_pct" value="{float(params.get('autotrade_profit_protection_lock_pct', 0.5)):.1f}" /></label>
          <label><span>Trailing Stop %</span><input type="number" step="0.1" min="0" name="autotrade_trailing_stop_pct" value="{float(params.get('autotrade_trailing_stop_pct', 2.0)):.1f}" /></label>
          <label><span>Cooldown Minutes</span><input type="number" min="0" name="autotrade_cooldown_minutes" value="{int(params['autotrade_cooldown_minutes'])}" /></label>
          <label class="inline-check"><input type="hidden" name="autotrade_order_test_only" value="0" /><input type="checkbox" name="autotrade_order_test_only" value="1" {"checked" if params["autotrade_order_test_only"] else ""} /><span>Use exchange order precheck/test</span></label>
          </div>
          </div>
          <div class="settings-submit-bar">
            <button type="submit">保存自动交易配置</button>
          </div>
          </form>
          </section>

          <section id="settings-backtest" class="settings-tab-panel">
          <form method="post" action="{_url('/settings', active_lang)}" class="ant-form backtest-form settings-form settings-section-form">
          {_hidden_lang_input(active_lang)}
          <input type="hidden" name="settings_section" value="backtest" />
          <div class="settings-heading full-span">
            <h2>Backtest Defaults</h2>
            <p>这些值会作为回测页的默认策略参数。你可以把实盘偏好先固定下来，再按每次任务微调。</p>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>策略模板与样本</h3><p>默认策略、历史数据路径和入场基础条件。</p></div>
          <div class="settings-grid">
          <label><span>Default Preset</span><select name="backtest_preset">{_backtest_preset_options(str(params['backtest_preset']))}</select></label>
          <label class="full-span"><span>Default Archives</span><textarea name="backtest_archives" rows="4" placeholder="data/spot/monthly/klines/*/4h/*.zip">{escape(str(params['backtest_archives']))}</textarea></label>
          <label><span>Lookback Bars</span><input type="number" min="60" name="backtest_lookback_bars" value="{int(params['backtest_lookback_bars'])}" /></label>
          <label><span>Score Threshold</span><input type="number" step="0.1" name="backtest_score_threshold" value="{float(params['backtest_score_threshold']):.1f}" /></label>
          <label><span>Holding Periods</span><input type="text" name="backtest_holding_periods" value="{escape(str(params['backtest_holding_periods']))}" /></label>
          <label><span>Portfolio Top N</span><input type="number" min="0" name="backtest_portfolio_top_n" value="{int(params['backtest_portfolio_top_n'])}" /></label>
          <label><span>Cooldown Bars</span><input type="number" min="0" name="backtest_cooldown_bars" value="{int(params['backtest_cooldown_bars'])}" /></label>
          <label><span>Stop Loss %</span><input type="number" step="0.1" name="backtest_stop_loss_pct" value="{float(params['backtest_stop_loss_pct']):.1f}" /></label>
          <label><span>Take Profit %</span><input type="number" step="0.1" name="backtest_take_profit_pct" value="{float(params['backtest_take_profit_pct']):.1f}" /></label>
          <label><span>Max Holding Bars</span><input type="number" min="1" name="backtest_max_holding_bars" value="{int(params['backtest_max_holding_bars'])}" /></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>手续费模型</h3><p>统一费率或 maker/taker 分离计费，支持账户费率来源。</p></div>
          <div class="settings-grid">
          <label><span>Fee Source</span><select name="backtest_fee_source">{''.join(_option(item, str(params['backtest_fee_source'])) for item in ['manual', 'account', 'symbol'])}</select></label>
          <label><span>Fee Model</span><select name="backtest_fee_model">{''.join(_option(item, str(params['backtest_fee_model'])) for item in ['flat', 'maker_taker'])}</select></label>
          <label><span>Fee bps</span><input type="number" step="0.1" name="backtest_fee_bps" value="{float(params['backtest_fee_bps']):.1f}" /></label>
          <label><span>Maker Fee bps</span><input type="number" step="0.1" name="backtest_maker_fee_bps" value="{float(params['backtest_maker_fee_bps']):.1f}" /></label>
          <label><span>Taker Fee bps</span><input type="number" step="0.1" name="backtest_taker_fee_bps" value="{float(params['backtest_taker_fee_bps']):.1f}" /></label>
          <label><span>Entry Role</span><select name="backtest_entry_fee_role">{''.join(_option(item, str(params['backtest_entry_fee_role'])) for item in ['maker', 'taker'])}</select></label>
          <label><span>Exit Role</span><select name="backtest_exit_fee_role">{''.join(_option(item, str(params['backtest_exit_fee_role'])) for item in ['maker', 'taker'])}</select></label>
          <label><span>Fee Discount %</span><input type="number" step="0.1" name="backtest_fee_discount_pct" value="{float(params['backtest_fee_discount_pct']):.1f}" /></label>
          <label class="inline-check"><input type="hidden" name="backtest_no_binance_discount" value="0" /><input type="checkbox" name="backtest_no_binance_discount" value="1" {"checked" if params["backtest_no_binance_discount"] else ""} /><span>Disable Binance discount</span></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>滑点、资金与过滤器</h3><p>把流动性、资金占用、RSI/KDJ 约束集中放在最后一组，便于快速排查。</p></div>
          <div class="settings-grid">
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
          <label class="inline-check"><input type="hidden" name="backtest_no_kdj_confirmation" value="0" /><input type="checkbox" name="backtest_no_kdj_confirmation" value="1" {"checked" if params["backtest_no_kdj_confirmation"] else ""} /><span>Disable KDJ confirmation</span></label>
          </div>
          </div>
          <div class="settings-submit-bar">
            <button type="submit">保存回测默认值</button>
          </div>
          </form>
          </section>
        </div>
        <div id="settings-transfer" class="settings-transfer">
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
      </div>
    """
    content = _with_settings_descriptions(content, active_lang)
    return _layout(
        page_title="Runtime Settings",
        active_page="settings",
        hero_title=t("运行时配置面板", "Runtime Configuration"),
        hero_text=t("集中管理密钥、数据源、Twitter 监控账号、扫描默认值和回测策略。保存后，扫描页和回测页会直接使用新的默认配置。", "Manage credentials, data sources, Twitter tracked accounts, scan defaults, and backtest strategy defaults. Saved changes are applied directly across the system."),
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


def _module_tabs(items: list[tuple[str, str]], *, active_index: int = 0, label: str = "页面模块") -> str:
    links = []
    for index, (href, title) in enumerate(items, start=1):
        active_class = " active" if index - 1 == active_index else ""
        links.append(
            f'<a class="ant-tabs-tab module-tab{active_class}" href="{escape(href)}">'
            f'<span class="module-tab-index">{index}</span>{escape(title)}</a>'
        )
    return f'<nav class="ant-tabs module-tabs" aria-label="{escape(label)}">{"".join(links)}</nav>'


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
