# Binance Signal Scanner

一个基于 Binance 官方 Spot API 设计的本地交易信号 APP 原型。

它的目标不是“自动下单”，而是先把高流动性币种里更值得关注的入场候选筛出来，再把原因拆给你看。

## 这个版本如何利用你提到的三个仓库

- `binance-spot-api-docs`
  - 用来确认 Spot 市场接口能力：`/api/v3/exchangeInfo`、`/api/v3/klines`、`/api/v3/ticker/24hr`、WebSocket Kline Streams。
- `binance-connector-python`
  - 我参考了它的 `exchange_info / klines / ticker24hr` 接口组织方式，当前代码保留同样的网关方法命名，后续可以无缝切回官方 SDK。
- `binance-public-data`
  - 代码里内置了 Binance 公共 K 线归档 ZIP 的读取器，后续可以直接接历史归档做回测或离线筛选。

## 当前实现

- 只扫描 `USDT` 计价的 Spot 交易对，可通过页面参数修改
- 用 24h 成交额和成交笔数做第一层流动性过滤
- 对候选币种拉 K 线并计算：
  - RSI(14)
  - EMA(20/50)
  - MACD(12, 26, 9)
  - KDJ(9, 3, 3)
  - 最近一根量能放大
  - 主动买盘占比
- 支持一个可插拔的“社区热度”适配层
  - 支持 X/Twitter 实时舆情抓取
  - 若存在 `data/community_scores.csv`，会和实时源一起并入综合评分
  - 若未配置任何社区源，则自动忽略该维度并重算权重
- 提供两个入口：
  - Web 页面：`/`
  - JSON API：`/api/scan`
- 提供两套历史回测入口：
  - Web 页面：`/backtest`
  - JSON API：`/api/backtest`
  - CLI：`run_backtest.py`

## 为什么能做，但要说明一个边界

Binance 官方这三个仓库足够支撑：

- 实时市场扫描
- 历史数据回放
- Python 程序化接入

但它们**不包含真实的社区热度数据**。所以“社区热度”必须来自额外来源，例如：

- X / Twitter
- 你自己的研究 CSV
- Reddit / Telegram / News 数据聚合服务
- 第三方情绪 API

这个项目已经把接口留好了，不会把核心策略和外部情绪数据耦死。

## 运行

```bash
python3 run.py
```

打开 `http://127.0.0.1:8000`

回测页：

- `http://127.0.0.1:8000/backtest`

运行配置页：

- `http://127.0.0.1:8000/settings`

## 在界面里直接配置密钥、情报源和策略

现在可以直接在 `/settings` 页面里维护这几类运行参数：

- Binance API Key / Secret / RecvWindow
- X / Twitter Bearer Token
- Twitter 情报监控账号列表
- 情报模式
  - `off`
  - `blend`
  - `only`
- 实时扫描默认参数
- 历史回测默认策略参数

保存后：

- `/` 会直接使用新的扫描默认值
- `/backtest` 会直接使用新的回测默认值
- 配置会写入本地 `data/runtime_config.json`

说明：

- 密钥通过 `POST /settings` 提交，不会出现在 URL 查询参数里
- 当前 `data/runtime_config.json` 是本地明文存储，适合个人本机使用
- 如果你后面要做多用户部署，建议把它切到数据库或专门的加密密钥存储

## 接入 X / Twitter

先准备一个 X Developer App 的 Bearer Token。你可以继续用环境变量，也可以直接在 `/settings` 页面里填写：

```bash
export X_BEARER_TOKEN="你的 Bearer Token"
python3 run.py
```

可选环境变量：

```bash
export COMMUNITY_PROVIDER="auto"
export X_RECENT_WINDOW_HOURS="24"
export X_RECENT_MAX_RESULTS="25"
export X_LANGUAGE="en"
```

默认策略：

- `COMMUNITY_PROVIDER=auto`
  - 有 `X_BEARER_TOKEN` 就启用 X
  - 有 `data/community_scores.csv` 就同时并入 CSV
- `COMMUNITY_PROVIDER=x`
  - 只使用 X / Twitter
- `COMMUNITY_PROVIDER=csv`
  - 只使用本地 CSV

如果你希望把某些账号作为“情报源”单独观察，可以在 `/settings` 里填 `Tracked Accounts`，一行一个，例如：

```text
lookonchain
wu_blockchain
TheBlock__
```

对应模式：

- `off`
  - 只看全市场普通舆情
- `blend`
  - 把全市场舆情和指定账号情报按权重混合
- `only`
  - 只看指定账号发出的内容

## 可选：接入 Binance 账户手续费

如果你想让回测直接读取你当前账户或交易对的实际 commission，先配置：

```bash
export BINANCE_API_KEY="你的 API Key"
export BINANCE_API_SECRET="你的 API Secret"
export BINANCE_RECV_WINDOW_MS="5000"
```

当前实现说明：

- 只支持 HMAC API key / secret 这一路签名
- 当前还不支持 RSA / Ed25519 key
- `fee_source=account` 会读取当前账户的 `commissionRates`
- `fee_source=symbol` 会读取 `/api/v3/account/commission?symbol=...`
- `symbol` 级费率当前按 `discounted standard + special + tax` 口径估算
  - 这里的折扣只作用在 `standardCommission`
  - 这是基于 Binance 文档字段结构做的工程化推断

## 可选：社区热度 CSV

复制示例文件：

```bash
cp data/community_scores.example.csv data/community_scores.csv
```

字段格式：

```csv
symbol,score,mentions,sentiment,source
BTCUSDT,82,1240,0.78,manual-research
ETHUSDT,76,890,0.72,manual-research
```

其中 `score` 建议使用 `0-100`。

## 可选：社媒查询别名

有些 ticker 本身有歧义，例如 `LINK`、`ONE`、`GAS`。这时建议提供别名查询：

```bash
cp data/social_aliases.example.csv data/social_aliases.csv
```

格式：

```csv
symbol,query
LINKUSDT,($LINK OR #LINK OR Chainlink OR #Chainlink) lang:en -is:retweet
ONEUSDT,($ONE OR #HarmonyONE OR "Harmony One") lang:en -is:retweet
```

如果 `data/social_aliases.csv` 存在，系统会优先使用你定义的查询。

## 用 Binance 公共 K 线做回测

先下载 `binance-public-data` 的 ZIP，例如：

```bash
curl -L "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-2025-01.zip" -o BTCUSDT-4h-2025-01.zip
curl -L "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-2025-02.zip" -o BTCUSDT-4h-2025-02.zip
```

然后运行：

```bash
python3 run_backtest.py "BTCUSDT-4h-2025-*.zip" --score-threshold 70 --holding-periods 3,6,12
```

如果你更想直接在页面里调参数，可以打开：

```text
http://127.0.0.1:8000/backtest?archives=BTCUSDT-4h-2025-*.zip&score_threshold=70&holding_periods=3,6,12
```

页面版支持和 CLI 基本一致的核心参数，包括：

- `lookback_bars`
- `score_threshold`
- `holding_periods`
- `cooldown_bars`
- `stop_loss_pct`
- `take_profit_pct`
- `max_holding_bars`
- `fee_bps`
- `fee_model`
- `fee_source`
- `maker_fee_bps`
- `taker_fee_bps`
- `entry_fee_role`
- `exit_fee_role`
- `fee_discount_pct`
- `no_binance_discount`
- `slippage_bps`
- `slippage_model`
- `min_slippage_bps`
- `max_slippage_bps`
- `slippage_window_bars`
- `capital_fraction_pct`
- `max_portfolio_exposure_pct`
- `max_concurrent_positions`
- `min_volume_ratio`
- `min_buy_pressure`
- `min_rsi`
- `max_rsi`
- `no_kdj_confirmation`
- `portfolio_top_n`

如果你想做多币种横截面组合回测，例如每个时间点只拿分数最高的 2 个币种：

```bash
python3 run_backtest.py "data/spot/monthly/klines/*/4h/*.zip" --score-threshold 70 --holding-periods 3,6,12 --portfolio-top-n 2
```

输出会给你：

- 信号数量
- 3 / 6 / 12 根 K 线后的平均收益、中位数收益、胜率
- 最近几次触发信号的时间、分数和远期收益
- 如果启用 `--portfolio-top-n`
  - 同一时间点 top N 币种的等权组合收益
  - 组合批次的胜率和平均收益
- 每笔真实交易的结果
  - 入场后按止损、止盈或时间出场
  - 平均收益、胜率、Profit Factor、平均持仓 bars、平均最大回撤
  - 资金曲线终值和最大回撤

说明：

- 回测默认**不混入实时 X/Twitter 舆情**，因为那样对历史不严谨
- 当前版本适合先验证 `4h`、`1d` 这类中高周期
- 如果你把同一币种同一周期的多个月 ZIP 一起传入，程序会自动合并并去重
- 如果你传入多个币种同一周期的 ZIP，并启用 `--portfolio-top-n`，程序会额外输出横截面组合回测结果

当前默认的入场规则是：

- 综合分数大于等于 `--score-threshold`
- `close > EMA20 > EMA50`
- `RSI` 位于允许区间
- 最近一根 K 线量能放大达到 `--min-volume-ratio`
- 主动买盘占比达到 `--min-buy-pressure`
- `MACD` 位于多头动能区
- 默认要求 `KDJ` 也确认，若不需要可加 `--no-kdj-confirmation`

默认的出场规则是：

- `--stop-loss-pct 4`
- `--take-profit-pct 9`
- `--max-holding-bars 12`
- 默认还会计入执行成本：
  - `--fee-bps 10`
  - `--fee-model flat`
  - `--fee-source manual`
  - `--slippage-bps 5`
  - 若要按流动性动态调节滑点，可用 `--slippage-model dynamic`
- 如果你想手工把回测成本改成 maker/taker 结构，而不是单一费率：
  - `--fee-model maker_taker`
  - `--maker-fee-bps`
  - `--taker-fee-bps`
  - `--entry-fee-role maker|taker`
  - `--exit-fee-role maker|taker`
  - `--fee-discount-pct`
- 如果你想直接读取 Binance 当前账户或交易对 commission：
  - `--fee-source account`
  - `--fee-source symbol`
  - `--no-binance-discount`
  - 需要先设置 `BINANCE_API_KEY` 和 `BINANCE_API_SECRET`
- 资金曲线默认每次使用 `100%` 资金，可用 `--capital-fraction-pct` 调低，例如只出 `50%`
- 组合层还支持：
  - `--max-portfolio-exposure-pct`
  - `--max-concurrent-positions`

例如：

```bash
python3 run_backtest.py "data/spot/monthly/klines/*/4h/*.zip" \
  --score-threshold 72 \
  --min-volume-ratio 1.15 \
  --min-buy-pressure 0.55 \
  --stop-loss-pct 4 \
  --take-profit-pct 10 \
  --max-holding-bars 12 \
  --fee-source symbol \
  --entry-fee-role taker \
  --exit-fee-role maker \
  --slippage-bps 5 \
  --slippage-model dynamic \
  --capital-fraction-pct 75 \
  --max-portfolio-exposure-pct 100 \
  --max-concurrent-positions 3 \
  --portfolio-top-n 2
```

页面版回测也已经支持同样的手续费参数，并会在结果卡片里显示本轮使用的成本假设。

如果你把默认 `fee_source` 设成 `account` 或 `symbol`，页面会尝试调用 Binance 账户接口读取真实手续费；如果 key 无效、权限不足或 IP 白名单不匹配，页面会直接显示错误文案，而不是返回 500。

## 下一步建议

- 接入 Binance WebSocket Kline Stream，做准实时刷新
- 引入止损位、波动率过滤、结构位突破等风险控制
- 把组合回测继续扩成带仓位约束、手续费、滑点和完整资金管理的策略回测
- 接 Binance 账户资产和持仓快照，让回测能以你当前账户结构做更贴近实盘的资金分配
