# AI Trade

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/kongwen686/ai-trade)](./LICENSE)
[![Repo](https://img.shields.io/badge/repo-public-1f8f57)](https://github.com/kongwen686/ai-trade)

本项目是一个面向数字货币市场的本地量化交易工作台。

它把研究、监控、回测、模拟交易和受保护的实盘执行放进同一套工具里：

- 实时扫描高流动性币种
- 计算技术指标并打分
- 接入 X/Twitter 舆情与指定情报账号
- 用 Binance 历史 K 线做策略回测
- 基于预测分数自动筛选策略命中并执行模拟交易
- 在实盘保护条件满足时调用 Binance Spot 下单接口
- 在 Web 界面里直接配置交易所密钥、情报源和策略参数

如果你想要的是一个“可研究、可筛选、可验证、可控执行”的本地量化系统，而不是黑盒喊单机器人，这个项目就是为这个方向写的。

## 功能概览

- 实时扫描
  - Binance Spot 交易对筛选
  - Binance 公开 `miniTicker` WebSocket：扫描页可见标的价格与 24h 涨跌约每秒更新
  - WebSocket 断线自动重连，并降级到本地只读 REST 实时价格接口
  - 支持计价币、周期、候选池、成交额、成交笔数过滤
- 技术指标
  - RSI(14)
  - EMA(20/50)
  - MACD(12, 26, 9)
  - KDJ(9, 3, 3)
  - 量能放大
  - 主动买盘占比
  - 波动率状态：已实现波动率、历史分位、波动率倍数、ATR 和冲击强度
- 社区与情报
  - X/Twitter 实时舆情
  - 指定账号情报模式：`off` / `blend` / `only`
  - 本地 CSV 社区分数
  - 本地新闻情报 CSV 聚合
  - 本地 Telegram 情报 CSV 聚合
  - Reddit 公开搜索舆情
  - 社媒查询别名
- 智能总控台
  - 平台能力总览：接入层、策略层、执行层、数据层、风控层
  - 交易所关键情报与热门信息监控
  - Twitter/X tracked accounts 配置画像
  - 链上大额异动和交易所流入 / 流出监控
  - 现货 / 合约价差与跨市场 basis 分析
  - Carry 双腿 paper 引擎：模拟现货做多 + 永续做空，统一核算基差、资金费率、手续费和滑点
  - 配对 / 统计套利回测：滚动对数价格 OLS、动态对冲比率、z-score、下一根开盘撮合
  - 自然语言策略编译：把用户描述拆解为回测参数和 paper 自动交易参数
  - 支持趋势跟随、均值回归、动量突破、再平衡、季节性和 basis 监控等策略语义
  - 策略命中、自动交易候选和风控意图聚合
  - Binance / OKX 账户接入状态与策略目录
  - 支持 OpenAI、Anthropic、Gemini、DeepSeek、xAI、Mistral、Qwen、Kimi 等模型做综合指标分析，未配置时自动使用本地规则
  - 交易账户概览展示当前敞口、已实现盈亏和平仓胜率
- 自动量化交易
  - 根据综合评分、量能、买盘压力和智能风控生成候选
  - 支持本地 paper 模拟交易
  - 支持 Binance Spot live 市价单
  - 支持 `order/test` 先校验订单参数
  - 支持持仓持久化、止损、止盈、冷却、最大持仓和最大敞口
  - 已持仓标的即使未进入本轮信号榜，也会补拉 ticker 最新价检查止损 / 止盈
  - live 持仓不会在 paper 模式下被模拟平仓
  - live 平仓必须满足 Auto Trade 已启用、`mode=live` 和 `AI_TRADE_LIVE_CONFIRM`
  - 平仓事件记录退出原因、已实现盈亏和已实现盈亏百分比
- 历史回测
  - Binance public-data ZIP 读取
  - 单币种回测
  - 多币种横截面组合回测
  - Benchmark Workbench：策略权益、次优版本和买入持有基准同屏对比
  - 已完成交易流水、AI 推理摘要和关键参数说明
  - 止损 / 止盈 / 最大持仓 bars
  - 手续费 / maker-taker / Binance 账户真实 commission
  - 固定滑点 / 动态滑点
  - 资金曲线 / 最大回撤 / Profit Factor
  - 页面级权益对比图、风险收益散点图、参数热力图和 JSON / CSV / HTML 结果导出
  - 内建参数预设与策略组合模板
  - 加密资产等权再平衡溢价研究：比较定期再平衡组合和自然漂移组合
  - 配对 / 统计套利研究：双腿成交、相关性、残差半衰期、成本、净收益和资金曲线
- 运行配置
  - Web 页面直接配置 Binance key、OKX key、X token、链上数据 key、LLM key、情报账号和策略默认值
  - 保存后自动应用到扫描页、总控台、自动交易页和回测页
  - 支持配置模板 JSON 导出 / 导入

## Web 入口

启动后默认地址：

- 实时扫描：`http://127.0.0.1:8000/`
- 智能总控台：`http://127.0.0.1:8000/terminal`
- 总控台模块：
  - `http://127.0.0.1:8000/terminal/market`
  - `http://127.0.0.1:8000/terminal/community`
  - `http://127.0.0.1:8000/terminal/onchain`
  - `http://127.0.0.1:8000/terminal/basis`
  - `http://127.0.0.1:8000/terminal/strategies`
  - `http://127.0.0.1:8000/terminal/trading`
  - `http://127.0.0.1:8000/terminal/risk`
- 历史回测：`http://127.0.0.1:8000/backtest`
- 运行配置：`http://127.0.0.1:8000/settings`
- 自动量化：`http://127.0.0.1:8000/trading`
- 本地健康检查 API：`http://127.0.0.1:8000/api/health`
- 扫描 API：`http://127.0.0.1:8000/api/scan`
- 只读实时价格 API：`http://127.0.0.1:8000/api/market/realtime?symbols=BTCUSDT,ETHUSDT`
- 智能总控台 API：`http://127.0.0.1:8000/api/terminal/snapshot`
- 平台能力 API：`http://127.0.0.1:8000/api/platform/capabilities`
- 平台账户 API：`http://127.0.0.1:8000/api/platform/accounts`
- 平台策略 API：`http://127.0.0.1:8000/api/platform/strategies`
- 平台风控 API：`http://127.0.0.1:8000/api/platform/risk`
- 平台日志 API：`http://127.0.0.1:8000/api/platform/logs`
- 总控台模块 API：`http://127.0.0.1:8000/api/terminal/modules/{market|community|onchain|basis|strategies|trading|risk}`
- 自然语言策略编译 API：`POST http://127.0.0.1:8000/api/strategy/compile`
- 回测 API：`http://127.0.0.1:8000/api/backtest`
- 自动交易 API：`POST http://127.0.0.1:8000/api/trading/run`
- 模拟交易 API：`POST http://127.0.0.1:8000/api/trading/paper/run`
- Carry 模拟状态：`GET http://127.0.0.1:8000/api/research/carry/paper/status`
- Carry 模拟轮询：`POST http://127.0.0.1:8000/api/research/carry/paper/run`
- 配对回测默认值：`GET http://127.0.0.1:8000/api/research/stat-arb/defaults`
- 配对回测执行：`POST http://127.0.0.1:8000/api/research/stat-arb/backtest`

## 中英文界面

页面右上角提供 `中文 / English` 切换。中文版本会把关键指标、状态、菜单和操作说明翻译成通俗中文；英文版本使用交易系统常见的专业术语，例如 `Strategy Hits`、`Pre-trade Risk Gate`、`Paper Filled`、`Risk Blocked`。

当前界面采用统一交易终端布局：左侧模块菜单、顶部功能导航、暗色数据面板、总控台二级菜单和底部行情条会在扫描、回测、自动交易、总控台和设置页之间保持一致。

也可以直接通过 URL 切换：

- 中文：`http://127.0.0.1:8000/terminal?lang=zh`
- English：`http://127.0.0.1:8000/terminal?lang=en`

## 快速开始

### 1. 从源码目录直接运行

未安装时，`src/` 布局需要显式带上 `PYTHONPATH`：

```bash
PYTHONPATH=src python3 -m trade_signal_app
```

自定义监听地址示例：

```bash
PYTHONPATH=src python3 -m trade_signal_app --host 0.0.0.0 --port 8000
```

然后打开：

```text
http://127.0.0.1:8000/settings
```

建议第一次先在 `/settings` 完成这几步：

1. 配置 `Binance API Key / Secret`，如果你需要账户真实手续费
2. 配置 `X Bearer Token`，如果你需要实时舆情
3. 填写 `Tracked Accounts`，如果你想跟踪特定 Twitter 情报账号
4. 设置扫描默认参数和回测默认参数

源码目录下运行回测 CLI：

```bash
PYTHONPATH=src python3 -m trade_signal_app.backtest "data/spot/monthly/klines/*/4h/*.zip" \
  --score-threshold 72 \
  --portfolio-top-n 2
```

### 2. 安装后运行

如果你希望直接使用模块入口或 console scripts，先安装：

```bash
python3 -m pip install -e .
```

安装完成后，可以直接使用：

```bash
python3 -m trade_signal_app
python3 -m trade_signal_app.backtest "data/spot/monthly/klines/*/4h/*.zip"
python3 -m trade_signal_app.autotrade
python3 -m trade_signal_app.autotrade --paper
trade-signal-web
trade-signal-backtest "data/spot/monthly/klines/*/4h/*.zip"
trade-signal-autotrade
```

安装后的 Web 入口同样支持：

```bash
trade-signal-web --host 0.0.0.0 --port 8000
```

如果你处在离线或受限环境，优先使用上面的源码目录运行方式。

查看当前版本：

```bash
PYTHONPATH=src python3 -m trade_signal_app --version
PYTHONPATH=src python3 -m trade_signal_app.backtest --version
```

## 为什么这个项目有用

很多交易工具只做其中一部分：

- 要么只看图
- 要么只看情绪
- 要么只做回测
- 要么只是一层 API 封装

这个项目把“筛选、解释、回测、配置”放在了一起：

- 扫描页负责找当前值得看的标的
- 回测页负责验证这套规则过去是否有效
- 设置页负责把数据源、密钥和策略变成可直接组合的运行时参数

它更像一个研究型终端，而不是一个下单脚本。

## 运行配置页

`/settings` 现在已经支持直接配置：

- Binance API Key / Secret / RecvWindow
- 公开行情预设：Binance Public、OKX Public、CoinGecko Keyless
- 链上数据预设：Open Multi-chain Keyless、DefiLlama Free、GeckoTerminal Keyless、本地 CSV
- 可选链上数据 API Key / 自定义 Base URL
- X/Twitter Provider、Bearer Token、Nitter RSS 或本地会话命令
- Twitter 情报账号列表
- 情报模式与权重
- LLM Provider / API Key / Base URL / Model
- 实时扫描默认参数
- 历史回测默认参数
- 配置模板 JSON 导出 / 导入

保存机制：

- 表单通过 `POST /settings` 提交
- 不会把密钥放进 URL
- 会持久化到本地 `data/runtime_config.json`
- 保存后 `/` 和 `/backtest` 会自动使用新的默认值

模板流转：

- `GET /api/settings/export`
  - 导出脱敏模板，默认清空 Binance / X 密钥
- `GET /api/settings/export?include_secrets=1`
  - 导出完整配置，适合你自己的本地完整备份
- `POST /settings/import`
  - 从设置页粘贴 JSON 模板导入
  - 如果模板里的密钥字段为空，会自动保留当前本机已保存的密钥

安全边界：

- 默认仍兼容本地明文 `data/runtime_config.json`
- 如果设置环境变量 `RUNTIME_CONFIG_PASSPHRASE`，后续保存会自动写成加密格式
- 已加密配置文件在缺少口令时不会被读取
- 当前实现适合个人单机使用；如果要做多用户部署，仍建议切换到数据库或专用密钥存储

## 自动量化交易

`/trading` 页面会把实时预测信号接入一个单次执行循环：

- 扫描当前市场信号
- 检查已有持仓的止损 / 止盈
- 对未进入本轮信号榜的持仓补拉 24h ticker 最新价
- live 持仓必须在 live 模式下真实平仓，paper 模式只会记录阻断事件
- 自动交易关闭或缺少 `AI_TRADE_LIVE_CONFIRM` 时，live 持仓触发止损 / 止盈也不会提交真实卖单
- 按分数阈值、量比、买盘压力筛选新仓
- 按单笔投入、最大持仓数、最大总敞口做风控
- 平仓时记录退出原因、已实现盈亏和盈亏百分比
- 在本地 `data/trading_state.json` 记录持仓状态

默认模式是 `paper`，只模拟记录持仓，不会向 Binance 提交真实订单。
模拟或实盘平仓事件会进入执行日志，并在 `/trading`、`/terminal/trading` 和 `/api/platform/accounts` 中汇总为账户表现指标。

如需实盘，必须同时满足：

1. `/settings` 中启用 Auto Trade，并把 Execution Mode 设为 `live`
2. 配置 Binance API Key / Secret，且 API 权限允许 Spot Trading
3. 服务端环境变量设置为：

```bash
export AI_TRADE_LIVE_CONFIRM="I_UNDERSTAND_REAL_ORDERS"
```

默认还会勾选 `Use Binance order/test`，这只校验订单参数，不会真实成交。只有关闭该选项，并满足上面的实盘确认后，系统才会调用 Binance Spot `POST /api/v3/order` 提交市价单。

交易前可以先检查真实授权状态：

- `GET /api/platform/exchange-auth`：调用 Binance 账户接口，返回 API 是否已认证、是否可交易、非零余额和报价资产可用余额；OKX 会明确显示为未配置或待接入 connector，不会被当作可自动交易通道。
- `GET /api/trading/readiness`：返回当前自动交易模式、`AI_TRADE_LIVE_CONFIRM`、Binance 授权、交易权限、报价资产余额和阻断原因。
- `GET /api/trading/status`：包含当前配置、readiness、持仓和执行事件。
- `GET /api/health`：只做本地健康检查，不访问外部交易所，适合启动后确认配置文件、交易状态文件和本地 live 阻断项。
- `GET /api/notifications/feishu/daily/status`：返回 22:00 日报调度线程、下次执行时间、最近发送结果和 SQLite 投递记录。
- `POST /api/notifications/feishu/daily/run`：手动补发日报；可传 `report_date=YYYY-MM-DD`，不传时优先执行当前待补发日期。

飞书日报按 `UTC+8` 每天 22:00 执行。失败后每 300 秒重试，服务在次日 10:00 前恢复时会补发前一日任务；日报与 BTC 专属信号分别去重，单项失败不会重复发送已成功的另一项。

当 `mode=live` 且关闭 `order/test` 准备真实成交时，系统会先检查 readiness。授权失败、缺少交易权限、缺少确认环境变量或报价资产余额不足时，会写入 `blocked` 事件并直接返回，不会继续扫描并尝试下单。

自动运行示例：

```bash
PYTHONPATH=src python3 -m trade_signal_app.autotrade --loop --interval-seconds 300
```

安装后也可以使用：

```bash
trade-signal-autotrade --loop --interval-seconds 300
```

命令行自动交易与 Web/API 使用同一个 readiness 和执行前风控入口。需要强制跑一轮模拟执行时可以加 `--paper`：

```bash
trade-signal-autotrade --paper
```

## 智能总控台与外部情报

`/terminal` 会把平台架构、功能实现状态、交易所信息、热门社区情报、Twitter/X 账号、链上异动、现货/合约价差、策略命中、自动交易意图、账户概览和风控规则放在同一个总控台里。左侧模块菜单均为可点击入口，每个模块都有独立页面和对应 API。

`/terminal/trading` 提供模拟账户执行入口，会强制使用 `paper` 模式运行一次策略信号源、执行前风控和自动交易引擎，不会提交真实订单。

本地数据源采用 CSV 插拔，复制示例文件即可启用：

- `data/exchange_intel.example.csv` -> `data/exchange_intel.csv`
- `data/onchain_events.example.csv` -> `data/onchain_events.csv`
- `data/futures_basis.example.csv` -> `data/futures_basis.csv`

对应环境变量：

```bash
export EXCHANGE_INTEL_CSV="data/exchange_intel.csv"
export ONCHAIN_EVENTS_CSV="data/onchain_events.csv"
export FUTURES_BASIS_CSV="data/futures_basis.csv"
```

如果没有配置真实的 `onchain_events.csv` 或 `futures_basis.csv`，对应模块会返回空数据并在本地规则摘要中说明该风控源未参与阻断；系统不会再用成交量或技术指标合成“链上事件”或“合约价差”。策略命中仍来自实时 Binance 行情和指标扫描。

大模型分析默认关闭。启用后会调用 `/settings` 中选择的 LLM Provider。系统内置 8 个主流供应商预设：

- `openai`：OpenAI Responses API
- `anthropic`：Anthropic Messages API
- `google`：Gemini OpenAI-compatible endpoint
- `deepseek`：DeepSeek OpenAI-compatible endpoint
- `xai`：xAI OpenAI-compatible endpoint
- `mistral`：Mistral chat completions endpoint
- `qwen`：Alibaba DashScope OpenAI-compatible endpoint
- `moonshot`：Moonshot Kimi OpenAI-compatible endpoint

环境变量示例：

```bash
export LLM_PROVIDER="deepseek"
export LLM_API_KEY="your-provider-api-key"
export LLM_MODEL="deepseek-chat"
```

OpenAI 旧环境变量仍兼容：

```bash
export OPENAI_API_KEY="your-openai-api-key"
export OPENAI_MODEL="gpt-5.5"
```

也可以在 `/settings` 中配置 LLM Provider、API Key、Base URL、模型、情报严重度、最小价差和链上大额阈值。未配置 LLM Key 或调用失败时，系统会自动使用本地规则分析，不影响总控台运行。

公开数据源预设：

- Binance Public Market Data：公开行情无需 key；账户、费率和交易仍需要 Binance API Key / Secret。
- OKX Public Market Data：公开产品、行情和 K 线无需 key；私有账户和交易仍需要 OKX Key / Secret / Passphrase。
- CoinGecko Keyless：价格、市场和趋势数据无需 key，适合补充市场视图。
- Open Multi-chain Keyless：组合 Blockstream、PublicNode、Solana public RPC、XRPL public RPC 和 Blockchair stats，默认覆盖 `BTC / ETH / DOGE / SOL / ZEC / XRP`。
- DefiLlama Free API：TVL、DeFi、稳定币、收益、链数据无需 key。
- GeckoTerminal Keyless：DEX 池子、链上 OHLCV 和交易数据无需 key。
- Local CSV：读取 `data/onchain_events.csv`，适合个人自定义或离线链上数据。

### 链上主流币监控

`Open Multi-chain Keyless` 是当前默认链上监控预设。它不依赖付费 key，按链采用不同开放数据源：

- `BTC`：Blockstream Esplora API，读取最新区块交易样本，识别大额原生 BTC 转账。
- `ETH`：PublicNode Ethereum JSON-RPC，读取 latest block 交易，识别大额 ETH 转账。
- `SOL`：Solana public JSON-RPC，读取 confirmed slot / block，估算大额 SOL 余额变化。
- `XRP`：XRPL public JSON-RPC，读取 validated ledger Payment 交易。
- `DOGE / ZEC`：Blockchair stats，读取 24h 交易数和 mempool 指标作为网络活跃度代理。

处理方式：

- 所有源会归一化成 `OnchainEvent`：`chain / symbol / event_type / amount_usd / direction / severity / tx_hash`。
- 大额转账按 `Whale Threshold USD` 计算严重度，超过阈值会进入总控台链上异动。
- 网络快照不会直接阻断交易，只作为风险分和链上活跃度提示。
- 本地 `data/onchain_events.csv` 仍会叠加进入同一个事件流，方便你后续接入自建节点、Arkham、Etherscan、Helius、Moralis 或手工标注的钱包流向。

OKX 当前用于接入状态、账户配置、跨交易所监控和现货 / 合约价差观察；自动实盘下单走 Binance Spot 执行通道。实盘模式需要同时满足 API key、`AI_TRADE_LIVE_CONFIRM` 和关闭 `order/test` 保护。

启用示例：

```bash
export RUNTIME_CONFIG_PASSPHRASE="your-strong-passphrase"
python3 -m trade_signal_app
```

## 信号维度

当前综合评分主要由这些维度构成：

- 趋势结构
- 动量状态
- 时机确认
- 成交量放大
- 流动性质量
- 市场强弱
- 社区热度

这套评分不是“绝对预测涨跌”，而是为了回答一个更实际的问题：

> 在当前这一批高流动性币种里，哪几个更像值得进一步观察或准备入场的候选。

## 交易书籍与策略路线图

项目会把交易书籍中的方法论转成可回测、可验证、可受控执行的工程清单，而不是直接照搬书中策略。

- 学习/实现手册：[docs/research/trading-books-strategy-playbook.md](docs/research/trading-books-strategy-playbook.md)
- 已接入：波动率状态过滤（扫描、回测、自动入场风控）、Carry/资金费率双腿 paper 模拟、配对/统计套利历史回测
- 已接入策略语义：综合评分突破、量价压力、趋势跟随、区间突破、动量轮动、均值回归、等权再平衡、BTC 隔夜季节性、现货/合约 basis 监控
- 仍处于研究阶段：做市。当前尚未接入 L2 队列仿真、库存偏斜、撤改单延迟和 kill switch，因此不会生成做市订单

所有新增策略默认先进入 `research`、`watch_only` 或 `paper`，不会自动开启实盘。Carry 引擎与配对回测均不调用 Binance/OKX 下单接口，即使主自动交易开启实盘也不会改变这一边界。

## 社区热度与 Twitter 情报

### X / Twitter

支持三挡 X / Twitter provider。`Community Provider` 里仍使用 `x` 代表 X/Twitter 数据源，具体采集方式由 `X Provider` 决定。

可直接通过 `/settings` 填写，或者继续用环境变量：

```bash
export X_PROVIDER="official_api"
export X_BEARER_TOKEN="your-bearer-token"
python3 -m trade_signal_app
```

三挡 provider：

- `official_api`
  - 使用官方 X API Bearer Token
  - 适合稳定、合规、可审计的数据采集
- `nitter_rss`
  - 使用自建或可信的 Nitter RSS 服务
  - 需要配置 `X_NITTER_BASE_URL`，例如 `http://127.0.0.1:8788`
  - 适合只读轮询公开搜索和指定账号 RSS
- `session_scrape`
  - 使用本机命令适配器采集
  - 需要配置 `X_SESSION_COMMAND`，命令输出 JSON / JSONL / 文本行
  - 支持 `{query}`、`{raw_query}`、`{limit}`、`{hours}` 占位符，例如：

```bash
export X_PROVIDER="session_scrape"
export X_SESSION_COMMAND='twscrape search {query} --limit {limit}'
```

`session_scrape` 只调用本机已配置好的只读采集命令，应用本身不保存 X 密码、Cookie 或登录态；不要把该能力暴露给不可信用户提交命令。

默认 `Tracked Accounts` 会内置一批已核验的高信号账号，覆盖链上异动、交易员观点、核心项目方、BTC 持仓大户和 ETF / 基金管理方。也可以用环境变量整体替换：

```bash
export X_TRACKED_ACCOUNTS="lookonchain,WuBlockchain,Grayscale,saylor,Strategy"
```

默认账号分组：

- 链上 / 新闻 / 数据：`lookonchain`、`WuBlockchain`、`whale_alert`、`BTCtreasuries`、`arkham`、`glassnode`、`cryptoquant_com`、`ki_young_ju`、`SantimentData`、`tier10k`、`WatcherGuru`
- ETF / 基金：`Grayscale`、`iShares`、`vaneck_us`、`ARKInvest`、`21shares_us`
- BTC 持仓大户：`saylor`、`Strategy`
- 核心项目方：`Bitcoin`、`ethereum`、`solana`、`BNBCHAIN`、`Ripple`、`chainlink`、`SuiNetwork`、`ton_blockchain`
- 交易员 / 宏观观点：`CryptoCred`、`Pentosh1`、`DaanCrypto`、`scottmelker`、`BobLoukas`、`CryptoHayes`、`APompliano`

支持模式：

- `off`
  - 只看普通全市场舆情
- `blend`
  - 普通舆情 + 指定账号情报按权重混合
- `only`
  - 只看指定账号内容

`Community Provider` 现在支持：

- `x`
- `csv`
- `news`
- `telegram`
- `reddit`
- `x,csv`
- `x,news`
- `x,telegram`
- `x,reddit`
- `csv,news`
- `csv,telegram`
- `csv,reddit`
- `news,telegram`
- `news,reddit`
- `telegram,reddit`
- `x,csv,news`
- `x,csv,telegram`
- `x,csv,reddit`
- `x,news,telegram`
- `x,news,reddit`
- `x,telegram,reddit`
- `csv,news,telegram`
- `csv,news,reddit`
- `csv,telegram,reddit`
- `news,telegram,reddit`
- `x,csv,news,telegram`
- `x,csv,news,reddit`
- `x,csv,telegram,reddit`
- `x,news,telegram,reddit`
- `csv,news,telegram,reddit`
- `x,csv,news,telegram,reddit`
- `auto`
  - 自动尝试可用的 `x + csv + news`
  - 为了避免无意增加网络依赖，`telegram` 和 `reddit` 需要显式选择

示例账号：

```text
lookonchain
WuBlockchain
Grayscale
saylor
Strategy
```

### CSV 社区分数

如果你有自己的研究结论，可以直接使用本地 CSV：

```bash
cp data/community_scores.example.csv data/community_scores.csv
```

格式：

```csv
symbol,score,mentions,sentiment,source
BTCUSDT,82,1240,0.78,manual-research
ETHUSDT,76,890,0.72,manual-research
```

### 新闻情报 CSV

如果你有本地整理的新闻研究结果，可以直接使用：

```bash
cp data/news_sentiment.example.csv data/news_sentiment.csv
```

格式：

```csv
symbol,headline,sentiment,source,published_at,url
BTCUSDT,US spot BTC ETF inflows extend for fifth session,0.72,newsdesk,2026-04-20T08:30:00Z,https://example.com/btc-etf-inflows
ETHUSDT,Ethereum scaling upgrade attracts renewed developer activity,0.68,blockwire,2026-04-20T09:10:00Z,https://example.com/eth-upgrade
```

说明：

- `sentiment` 建议使用 `-1` 到 `1`
- 同一 `symbol` 的多条新闻会按平均情绪和样本数聚合
- 聚合后会和 X / CSV 社区分数一起参与最终社区评分

### Telegram 情报 CSV

如果你有自己整理的频道消息，也可以直接使用：

```bash
cp data/telegram_sentiment.example.csv data/telegram_sentiment.csv
```

格式：

```csv
symbol,channel,message,sentiment,published_at,url
BTCUSDT,whalewatch,Large wallets keep adding BTC on pullbacks,0.66,2026-04-20T07:20:00Z,https://t.me/example_btc
ETHUSDT,defialpha,Layer2 activity expands after new upgrade cycle,0.62,2026-04-20T10:45:00Z,https://t.me/example_eth
```

说明：

- `sentiment` 建议使用 `-1` 到 `1`
- 同一 `symbol` 的多条频道消息会按平均情绪和样本数聚合
- 聚合后会和 X / 新闻 / CSV / Reddit 一起参与最终社区评分

### Reddit

Reddit 走公开搜索接口，不需要单独秘钥。可在 `/settings` 中配置：

- `Reddit API Base URL`
- `Reddit Window Hours`
- `Reddit Max Results`
- `Reddit User-Agent`

实现方式：

- 根据交易对和别名生成搜索词
- 读取最近帖子标题和正文
- 按最近时间窗过滤
- 用帖子数和文本情绪生成 `reddit` 社区分数

### 社媒查询别名

对于 `LINK`、`ONE`、`GAS` 这类易歧义 ticker，可以配置查询别名：

```bash
cp data/social_aliases.example.csv data/social_aliases.csv
```

格式：

```csv
symbol,query
LINKUSDT,($LINK OR #LINK OR Chainlink OR #Chainlink) lang:en -is:retweet
ONEUSDT,($ONE OR #HarmonyONE OR "Harmony One") lang:en -is:retweet
```

## 历史回测

历史回测基于 Binance `binance-public-data` 格式的 K 线 ZIP。

### 下载示例数据

```bash
curl -L "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-2025-01.zip" -o BTCUSDT-4h-2025-01.zip
curl -L "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-2025-02.zip" -o BTCUSDT-4h-2025-02.zip
```

### 单币种回测

```bash
python3 -m trade_signal_app.backtest "BTCUSDT-4h-2025-*.zip" \
  --score-threshold 70 \
  --holding-periods 3,6,12
```

### 多币种组合回测

```bash
python3 -m trade_signal_app.backtest "data/spot/monthly/klines/*/4h/*.zip" \
  --score-threshold 70 \
  --holding-periods 3,6,12 \
  --portfolio-top-n 2
```

### Web 结果导出

回测页现在支持基于当前筛选参数直接导出：

- `GET /api/backtest`
  - 返回完整 JSON 结果
- `GET /api/backtest/export?format=csv`
  - 返回扁平化 CSV 摘要，适合后续表格分析
- `GET /api/backtest/export?format=json`
  - 返回带缩进的导出 JSON
- `GET /api/backtest/export?format=html`
  - 返回可独立保存和打开的 HTML 研究报告，包含结果摘要、参数表和参数热力图

CSV 会同时写入单币种、组合、稳健性检查和参数敏感度明细；JSON 会保留完整结构化结果。三个导出端点均返回附件文件名，避免浏览器只把结果展示为临时页面。

### 参数敏感度

回测高级条件中的 `Parameter Sweep` 默认关闭。开启后系统会：

- 选取首个有效币种/周期，并使用与主回测一致的完整历史样本
- 对 `score_threshold` 的 `-4 / 当前 / +4` 和 `stop_loss_pct` 的 `0.75x / 当前 / 1.25x` 运行 3×3 扫描
- 返回每个组合的最终权益、收益率、最大回撤、Profit Factor、交易数和风险调整收益
- 在回测页绘制真实参数热力图，并标记当前参数和风险调整收益最佳的邻域组合

扫描是额外的 9 次单序列回测，因此不会默认执行。`btc_overnight_seasonality` 和 `crypto_rebalance_premium` 有独立执行语义，不套用评分阈值 × 止损比例热力图。

### 回测预设

回测页和设置页现在支持内建策略模板：

- `custom`
- `balanced_swing`
- `breakout_aggressive`
- `portfolio_rotation`
- `trend_pullback_conservative`
- `breakout_confirmed`
- `mean_reversion_guarded`
- `quality_rotation`
- `crypto_rebalance_premium`
- `btc_overnight_seasonality`
- `btc_cycle_trend`
- `btc_core_trading`
- `btc_compounding_risk_off`

用途：

- 在 `/backtest` 里快速套用一组参数
- 在 `/settings` 里把某个 preset 保存成默认回测模板
- 通过 `GET /api/backtest/presets` 查看模板清单和参数

每个预设同时返回风险等级、验证阶段、建议周期和适用市场状态。新增的四组执行型预设默认启用波动率状态过滤，并显式限制资金暴露与最大并发：

- `trend_pullback_conservative`：等待顺势回踩和量价恢复，减少追涨
- `breakout_confirmed`：评分、量能、买压和波动率共同确认突破
- `mean_reversion_guarded`：超卖反弹确认、短持仓和严格冷却
- `quality_rotation`：主流高流动性标的质量轮动

### 策略模板注册表

`/terminal/strategies` 提供可直接选择的策略模板。模板把策略语义、回测 preset、安全的 paper 参数和适用条件绑定在一起：

- `quality_trend_pullback`
- `confirmed_breakout`
- `guarded_mean_reversion`
- `quality_asset_rotation`
- `btc_cycle_trend`
- `btc_core_trading`
- `equal_weight_rebalance`
- `btc_overnight_window`

相关 API：

- `GET /api/strategy/templates`：返回模板目录和选择元数据
- `POST /api/strategy/templates/compile`：提交 `{"template_id":"quality_trend_pullback"}`，生成确定性的回测与 paper 参数

策略模板编译不会读取或修改当前自动交易运行状态，并强制输出 `enabled=false`、`paper_enabled=false`、`live_enabled=false`、`order_test_only=true`。模板只能用于回测或后续人工确认后的模拟配置，不会自动触发真实订单。

`crypto_rebalance_premium` 来自对 Quant Wiki crypto 策略的 spot-only 改造：

- 原始思想是定期把一篮子加密资产拉回等权，并与买入后自然漂移的组合对照
- 本项目不做空漂移组合，直接输出等权再平衡组合、自然漂移组合和二者的 premium
- 再平衡报告会计入手续费、滑点和 turnover，结果显示在 `/backtest` 的 `Rebalance Premium` 区块

`btc_overnight_seasonality` 来自对 Quant Wiki Bitcoin 隔夜季节性策略的 spot-only 改造：

- 研究 UTC 22:00 开多 BTC、持有 2 小时后退出的时间窗口
- 适合用 `BTCUSDT 1h` 或更细周期数据验证；`4h` 数据通常无法精确命中 22:00 UTC
- 结果作为普通 series backtest 展示，会计入手续费、滑点和资金曲线

研究笔记：

- [Crypto Rebalance Premium Adaptation](docs/research/crypto-rebalance-premium.md)

其中 3 个 BTC 定向模板，是基于对公开 BTC 交易账户档案的研究思路提炼出来的：

- `btc_cycle_trend`
  - 更偏 BTC 周期趋势跟随，强调顺势和中等持仓周期
- `btc_core_trading`
  - 更偏核心仓 + 交易仓，允许围绕主方向做更积极的仓位管理
- `btc_compounding_risk_off`
  - 更偏复利与回撤控制，主动压低暴露和并发

当前建议的使用顺序：

1. `btc_core_trading`
   - 当前是主推荐模板
   - 在 `BTCUSDT 4h / 2025` 的样本外验证里最稳，收益和回撤比最好
2. `btc_cycle_trend`
   - 更适合强趋势年份
   - 在 `2024` 样本内表现强，但在 `2025` 样本外明显转弱
3. `btc_compounding_risk_off`
   - 当前版本先作为观察模板
   - 回撤控制思路合理，但现阶段收益端还不成立

相关研究笔记：

- [BTC Preset Validation](docs/research/btc-preset-validation.md)
  - 记录了 `BTCUSDT 4h / 2024-2025` 的首轮全样本验证、参数收敛和 `2024/2025` 样本外检验结果

### 当前默认入场逻辑

- 综合分数大于等于阈值
- `close > EMA20 > EMA50`
- `RSI` 在允许区间
- 最近一根量能放大达到阈值
- 主动买盘占比达到阈值
- `MACD` 位于多头动能区
- 默认要求 `KDJ` 进一步确认

### 当前默认出场逻辑

- `stop loss`
- `take profit`
- `max holding bars`

### 执行成本支持

- `fee_source=manual`
- `fee_source=account`
- `fee_source=symbol`
- `fee_model=flat`
- `fee_model=maker_taker`
- `slippage_model=fixed`
- `slippage_model=dynamic`
- `capital_fraction_pct`
- `max_portfolio_exposure_pct`
- `max_concurrent_positions`

说明：

- 历史回测默认不混入实时 X/Twitter 舆情，这样结果更严谨
- 如果默认手续费源设成 `account` 或 `symbol`，页面会尝试读取 Binance 真实手续费
- 如果 key 无效、权限不足或 IP 白名单不匹配，页面会返回可读错误，而不是直接 500

## Binance 账户手续费

如果你希望回测读取真实账户或交易对 commission，可配置：

```bash
export BINANCE_API_KEY="your-api-key"
export BINANCE_API_SECRET="your-api-secret"
export BINANCE_RECV_WINDOW_MS="5000"
```

当前实现范围：

- 支持 HMAC API key / secret
- 当前不支持 RSA / Ed25519
- `fee_source=account` 读取账户级 `commissionRates`
- `fee_source=symbol` 读取交易对级 `/api/v3/account/commission`
- `symbol` 级费率按 `discounted standard + special + tax` 口径估算

## 这个项目如何利用 Binance 的开源仓库

项目的设计参考了你提到的三个 Binance 仓库：

- `binance-spot-api-docs`
  - 用来确认 Spot REST 接口能力和字段结构
- `binance-public-data`
  - 用来读取历史 K 线 ZIP 并驱动回测
- `binance-connector-python`
  - 用来参考 Python 接入层的接口组织方式

它们足够支撑：

- 实时市场扫描
- 历史数据回放
- Python 程序化接入

但它们本身不包含“社区热度”或“社交情绪”数据，所以这部分被设计成了可插拔数据源。

## 项目结构

```text
.
├── data/                     # 社区分数与社媒别名示例
├── src/trade_signal_app/     # 核心应用代码
├── static/                   # Web 样式
├── tests/                    # 单元测试
├── run.py                    # Web 服务兼容入口
├── run_backtest.py           # 回测 CLI 兼容入口
├── PROJECT_PROGRESS.md       # 当前进度与后续跟进文档
└── README.md
```

## 验证

```bash
pytest -q
python3 -m compileall src run.py run_backtest.py tests
```

当前版本在本地已经完成：

- Web 页面冒烟验证
- 扫描接口验证
- 回测接口验证
- 运行配置持久化验证

## 路线图

- [x] 接入 Binance 公开 `miniTicker` WebSocket，支持扫描页可见价格与 24h 涨跌实时刷新；评分仍以最近一次完整扫描为准
- [x] 增加更完整的参数预设与策略模板：统一注册表、选择元数据、安全模板编译 API 和策略库入口
- [x] 给回测页补更完整的图形化结果、参数热力图和导出能力：风险收益地图、3×3 参数扫描、CSV/JSON/HTML 报告
- [ ] 增加更多样本区间、多交易对和 walk-forward 样本外验证
- [ ] 完善安装、升级和发布体验

WebSocket 使用 Binance 官方公开市场流，不携带 API Key，也不连接用户数据流或订单接口。连接按官方 24 小时生命周期自动重建；具体协议参考 [Binance Spot WebSocket Streams](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams)。

## 项目状态

当前项目处于“可运行的本地研究工具”阶段：

- 已具备核心功能
- 已适合个人研究与参数验证
- 还没有做成可直接实盘托管的交易系统

更细的交付进度见：

- [PROJECT_PROGRESS.md](./PROJECT_PROGRESS.md)

## 开源说明

- License: MIT
- 欢迎提交 issue 和 PR
- 适合做研究、学习和二次开发

## 免责声明

本项目仅用于研究、学习和策略验证，不构成投资建议。

加密资产交易风险较高，任何信号、回测结果或情绪指标都不应被视为收益保证。请自行评估风险，并对自己的资金决策负责。
