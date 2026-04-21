# AI Trade

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/kongwen686/ai-trade)](./LICENSE)
[![Repo](https://img.shields.io/badge/repo-public-1f8f57)](https://github.com/kongwen686/ai-trade)

本项目是一个面向 Binance Spot 市场的本地交易信号与回测工作台。

它不负责自动下单，而是把这几件事放进同一套工具里：

- 实时扫描高流动性币种
- 计算技术指标并打分
- 接入 X/Twitter 舆情与指定情报账号
- 用 Binance 历史 K 线做策略回测
- 在 Web 界面里直接配置密钥、情报源和策略参数

如果你想要的是一个“可研究、可筛选、可验证”的本地信号系统，而不是黑盒喊单机器人，这个项目就是为这个方向写的。

## 功能概览

- 实时扫描
  - Binance Spot 交易对筛选
  - 支持计价币、周期、候选池、成交额、成交笔数过滤
- 技术指标
  - RSI(14)
  - EMA(20/50)
  - MACD(12, 26, 9)
  - KDJ(9, 3, 3)
  - 量能放大
  - 主动买盘占比
- 社区与情报
  - X/Twitter 实时舆情
  - 指定账号情报模式：`off` / `blend` / `only`
  - 本地 CSV 社区分数
  - 社媒查询别名
- 历史回测
  - Binance public-data ZIP 读取
  - 单币种回测
  - 多币种横截面组合回测
  - 止损 / 止盈 / 最大持仓 bars
  - 手续费 / maker-taker / Binance 账户真实 commission
  - 固定滑点 / 动态滑点
  - 资金曲线 / 最大回撤 / Profit Factor
- 运行配置
  - Web 页面直接配置 Binance key、X token、情报账号和策略默认值
  - 保存后自动应用到扫描页和回测页

## Web 入口

启动后默认地址：

- 实时扫描：`http://127.0.0.1:8000/`
- 历史回测：`http://127.0.0.1:8000/backtest`
- 运行配置：`http://127.0.0.1:8000/settings`
- 扫描 API：`http://127.0.0.1:8000/api/scan`
- 回测 API：`http://127.0.0.1:8000/api/backtest`

## 快速开始

### 1. 运行 Web 应用

```bash
python3 run.py
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

### 2. 运行回测 CLI

```bash
python3 run_backtest.py "data/spot/monthly/klines/*/4h/*.zip" \
  --score-threshold 72 \
  --portfolio-top-n 2
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
- X/Twitter Bearer Token
- Twitter 情报账号列表
- 情报模式与权重
- 实时扫描默认参数
- 历史回测默认参数

保存机制：

- 表单通过 `POST /settings` 提交
- 不会把密钥放进 URL
- 会持久化到本地 `data/runtime_config.json`
- 保存后 `/` 和 `/backtest` 会自动使用新的默认值

安全边界：

- `data/runtime_config.json` 当前是本地明文存储
- 适合个人单机使用
- 如果要做多用户部署，建议切换到数据库或专用密钥存储

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

## 社区热度与 Twitter 情报

### X / Twitter

支持 X Developer Bearer Token。

可直接通过 `/settings` 填写，或者继续用环境变量：

```bash
export X_BEARER_TOKEN="your-bearer-token"
python3 run.py
```

支持模式：

- `off`
  - 只看普通全市场舆情
- `blend`
  - 普通舆情 + 指定账号情报按权重混合
- `only`
  - 只看指定账号内容

示例账号：

```text
lookonchain
wu_blockchain
TheBlock__
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
python3 run_backtest.py "BTCUSDT-4h-2025-*.zip" \
  --score-threshold 70 \
  --holding-periods 3,6,12
```

### 多币种组合回测

```bash
python3 run_backtest.py "data/spot/monthly/klines/*/4h/*.zip" \
  --score-threshold 70 \
  --holding-periods 3,6,12 \
  --portfolio-top-n 2
```

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
├── run.py                    # Web 服务入口
├── run_backtest.py           # 回测 CLI 入口
├── PROJECT_PROGRESS.md       # 当前进度与后续跟进文档
└── README.md
```

## 验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m compileall src run.py run_backtest.py
```

当前版本在本地已经完成：

- Web 页面冒烟验证
- 扫描接口验证
- 回测接口验证
- 运行配置持久化验证

## 路线图

- 接入 Binance WebSocket，支持更接近实时的刷新
- 增加更完整的参数预设与策略模板
- 给回测页补更完整的图形化结果和导出能力
- 接入更多情报源，例如新闻、Telegram、Reddit
- 评估将本地明文配置升级为加密存储

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
