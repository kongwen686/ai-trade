from __future__ import annotations

from html import escape

from .views_common import _backtest_preset_options, _display_value, _hidden_lang_input, _layout, _module_tabs, _option, _option_with_label, _text, _url, normalize_language
from .views_components import _trading_event_rows, _trading_position_rows


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
        "Leverage": ("paper 模拟中用于放大名义仓位；live 现货执行仍按 1 倍处理。", "Leverage used for paper notional sizing; live spot execution remains 1x."),
        "Risk Per Trade %": ("单笔可承受保证金风险目标，用于杠杆口径提示和后续自动调参。", "Target margin risk per trade for leveraged risk hints and future auto-tuning."),
        "Exit Profile": ("balanced 保持固定止盈；trend_following 到达止盈且趋势强时继续持有并移动止损。", "balanced keeps fixed take profit; trend_following can hold winners with trailing protection."),
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
        "Enable trend hold": ("启用后，趋势跟随档位可在达到止盈但趋势仍强时继续持有。", "Allows trend_following profile to keep holding after take-profit when signal remains strong."),
        "Trend Hold Score": ("趋势持有要求的最低信号分，只有 exit profile 为 trend_following 时生效。", "Minimum score for trend hold; only active when exit profile is trend_following."),
        "Trend Hold Volume": ("趋势持有要求的最低量能放大倍数。", "Minimum volume expansion for trend hold."),
        "Trend Hold Buy Pressure": ("趋势持有要求的最低主动买入占比。", "Minimum buy pressure for trend hold."),
        "Emergency Drawdown %": ("价格从持仓最高价快速回撤超过该比例但尚未触发止损时记录预警。", "Warn when price pulls back from position high by this percentage before stop is hit."),
        "Cooldown Minutes": ("自动交易开仓或平仓后的冷却时间，避免连续追单。", "Cooldown after automated trades to avoid repeated entries."),
        "Use exchange order precheck/test": ("勾选时 live 模式只做交易所订单预检或测试，不会真实成交。", "When checked, live mode uses exchange order precheck/test without filling real orders."),
        "Feishu Webhook URL": ("飞书机器人 Webhook 地址。留空会保留原值；在买入成交和卖出执行时推送结构化消息。", "Feishu bot webhook URL. Leave blank to keep the saved value; filled buy and sell trades send structured notifications."),
        "Clear Feishu webhook": ("勾选后保存会清空已保存的飞书机器人 Webhook。", "When checked, saving clears the saved Feishu bot webhook."),
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
    leverage = max(1.0, float(config.get("leverage", 1.0) or 1.0))
    stop_loss_roi = float(config["stop_loss_pct"]) * leverage
    take_profit_roi = float(config["take_profit_pct"]) * leverage
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
          <div class="mini-stat"><span>{t("杠杆", "Leverage")}</span><strong>{leverage:.1f}x</strong><small>{escape(str(config.get("exit_profile", "balanced")))}</small></div>
          <div class="mini-stat"><span>{t("止损", "Stop Loss")}</span><strong>{float(config["stop_loss_pct"]):.1f}%</strong><small>{t("约", "approx")} {stop_loss_roi:.1f}% ROI</small></div>
          <div class="mini-stat"><span>{t("止盈", "Take Profit")}</span><strong>{float(config["take_profit_pct"]):.1f}%</strong><small>{t("约", "approx")} {take_profit_roi:.1f}% ROI</small></div>
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
          <label><span>Leverage</span><input type="number" step="0.1" min="1" max="20" name="autotrade_leverage" value="{float(params.get('autotrade_leverage', 1.0)):.1f}" /></label>
          <label><span>Risk Per Trade %</span><input type="number" step="0.1" min="0.1" max="100" name="autotrade_risk_per_trade_pct" value="{float(params.get('autotrade_risk_per_trade_pct', 4.0)):.1f}" /></label>
          <label><span>Exit Profile</span><select name="autotrade_exit_profile">{_option_with_label("balanced", "balanced", str(params.get("autotrade_exit_profile", "balanced")))}{_option_with_label("leveraged_conservative", "leveraged conservative", str(params.get("autotrade_exit_profile", "balanced")))}{_option_with_label("trend_following", "trend following", str(params.get("autotrade_exit_profile", "balanced")))}</select></label>
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
          <label class="inline-check"><input type="hidden" name="autotrade_trend_hold_enabled" value="0" /><input type="checkbox" name="autotrade_trend_hold_enabled" value="1" {"checked" if params.get("autotrade_trend_hold_enabled") else ""} /><span>Enable trend hold</span></label>
          <label><span>Trend Hold Score</span><input type="number" step="0.1" min="0" max="100" name="autotrade_trend_hold_min_score" value="{float(params.get('autotrade_trend_hold_min_score', 82.0)):.1f}" /></label>
          <label><span>Trend Hold Volume</span><input type="number" step="0.01" min="0" name="autotrade_trend_hold_min_volume_ratio" value="{float(params.get('autotrade_trend_hold_min_volume_ratio', 1.25)):.2f}" /></label>
          <label><span>Trend Hold Buy Pressure</span><input type="number" step="0.01" min="0" max="1" name="autotrade_trend_hold_min_buy_pressure" value="{float(params.get('autotrade_trend_hold_min_buy_pressure', 0.56)):.2f}" /></label>
          <label><span>Emergency Drawdown %</span><input type="number" step="0.1" min="0" max="50" name="autotrade_emergency_drawdown_pct" value="{float(params.get('autotrade_emergency_drawdown_pct', 2.5)):.1f}" /></label>
          <label><span>Cooldown Minutes</span><input type="number" min="0" name="autotrade_cooldown_minutes" value="{int(params['autotrade_cooldown_minutes'])}" /></label>
          <label class="inline-check"><input type="hidden" name="autotrade_order_test_only" value="0" /><input type="checkbox" name="autotrade_order_test_only" value="1" {"checked" if params["autotrade_order_test_only"] else ""} /><span>Use exchange order precheck/test</span></label>
          </div>
          </div>
          <div class="settings-group">
          <div class="settings-group-head"><h3>消息推送</h3><p>买入成交和卖出执行后，会把标的、价格、仓位、盈亏等关键信息推送给飞书机器人。当前状态：{"已配置" if status.get("feishu_webhook_configured") else "未配置"}。</p></div>
          <div class="settings-grid">
          <label class="full-span"><span>Feishu Webhook URL</span><input type="password" name="feishu_webhook_url" value="" placeholder="留空保持当前" autocomplete="off" /></label>
          <label class="inline-check"><input type="checkbox" name="clear_feishu_webhook" /><span>Clear Feishu webhook</span></label>
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


__all__ = [
    '_settings_description_map',
    '_with_settings_descriptions',
    'render_trading_page',
    'render_settings_page',
]
