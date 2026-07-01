# 项目进度文档

更新日期：2026-05-04

## 1. 项目目标

本项目是一个基于 Binance Spot 市场数据的本地交易信号与历史回测应用，目标是把：

- 实时市场信号
- 技术指标筛选
- X/Twitter 舆情情报
- 历史回测与策略验证
- 模拟交易、受保护实盘执行与执行后复盘

收敛到一个可直接操作的本地 Web 应用里。

## 2. 当前已完成能力

### 2.1 实时扫描

- 支持 Binance Spot 实时扫描
- 支持按计价币、周期、候选池、成交额、成交笔数过滤
- 计算并展示：
  - RSI(14)
  - EMA(20/50)
  - MACD
  - KDJ
  - 量能放大
  - 主动买盘占比
- 输出综合评分、等级、入场理由、风险提示

相关入口：

- Web：`/`
- API：`/api/scan`

## 2.2 社区热度与 Twitter 情报

- 支持本地 CSV 社区评分源
- 支持本地新闻情报 CSV 聚合源
- 支持本地 Telegram 情报 CSV 聚合源
- 支持 X/Twitter Bearer Token 实时舆情
- 支持 X/Twitter 三挡 provider：
  - `official_api`：官方 Bearer Token
  - `nitter_rss`：自建或可信 Nitter RSS 只读采集
  - `session_scrape`：本机命令适配器，兼容 twscrape / 本地会话采集工具
- 支持 Reddit 公开搜索舆情
- 支持社媒查询别名配置
- 支持情报账号列表
- 已内置默认 Twitter/X tracked accounts，覆盖链上异动、交易员、核心项目方、BTC 持仓大户和 ETF / 基金管理方
- 支持三种 Twitter 情报模式：
  - `off`
  - `blend`
  - `only`
- 支持将普通舆情与指定账号情报按权重混合
- 新增 Open Multi-chain Keyless 链上监控预设：
  - BTC：Blockstream Esplora 最新区块交易样本
  - ETH：PublicNode Ethereum JSON-RPC latest block
  - SOL：Solana public RPC confirmed block
  - XRP：XRPL public validated ledger
  - DOGE / ZEC：Blockchair stats 网络活跃度
  - 统一输出 `OnchainEvent`，叠加本地 CSV 后进入总控台和执行前风控

核心文件：

- `src/trade_signal_app/community.py`
- `src/trade_signal_app/onchain.py`
- `data/social_aliases.example.csv`
- `data/news_sentiment.example.csv`
- `data/telegram_sentiment.example.csv`

## 2.3 历史回测

- 支持 Binance public-data ZIP 历史 K 线读取
- 支持单币种回测
- 支持多币种横截面组合回测
- 支持真实交易逻辑：
  - 下一根 K 线开盘入场
  - 止损
  - 止盈
  - 最大持仓 bars
- 支持资金曲线、最大回撤、Profit Factor
- 支持手续费、滑点、动态滑点、最大暴露、最大并发持仓
- 回测页支持单币种 / 组合权益排名总览
- 支持回测结果 JSON / CSV 导出
- 支持内建回测参数预设与策略组合模板
- 新增 `crypto_rebalance_premium` 预设
- 新增 `btc_overnight_seasonality` 预设
- 新增加密资产等权再平衡溢价研究报告，对比定期等权再平衡组合和自然漂移组合
- 新增 BTC 隔夜季节性回测能力，研究 UTC 22:00 开仓、持有 2 小时时间窗口
- 新增 3 个 BTC 定向研究模板：周期趋势、核心仓交易、复利风控
- 已基于真实 BTCUSDT 4h 月度数据完成首轮模板验证与样本外检验
- 已沉淀独立研究笔记：`docs/research/btc-preset-validation.md`

相关入口：

- Web：`/backtest`
- API：`/api/backtest`
- CLI：`python3 -m trade_signal_app.backtest` / `run_backtest.py`

核心文件：

- `src/trade_signal_app/backtest.py`
- `src/trade_signal_app/strategy.py`
- `src/trade_signal_app/models.py`

## 2.4 Binance 真实手续费接入

- 支持 `fee_source=manual|account|symbol`
- 支持读取 Binance 账户级 commission
- 支持读取交易对级 commission
- 支持 maker/taker 费率与折扣回填回测
- 当前支持 HMAC key/secret
- 当前未支持 RSA / Ed25519

核心文件：

- `src/trade_signal_app/binance_client.py`
- `src/trade_signal_app/backtest.py`

## 2.5 运行配置页面

已实现统一运行配置页：`/settings`

当前可直接在界面配置：

- Binance API Key / Secret / RecvWindow
- X/Twitter Bearer Token
- Twitter 情报账号列表
- Twitter 情报模式和权重
- 实时扫描默认参数
- 历史回测默认参数

配置特性：

- 密钥通过 `POST /settings` 提交，不出现在 URL
- 配置保存到本地 `data/runtime_config.json`
- 支持通过 `RUNTIME_CONFIG_PASSPHRASE` 启用加密存储
- 保存后 `/` 与 `/backtest` 会自动使用新默认值
- 支持导出脱敏配置模板 JSON
- 支持导入配置模板 JSON，并在模板密钥为空时保留当前已保存密钥
- 支持 OKX 接入参数、公开数据源预设、通用 LLM / Intelligence 参数、Auto Trade 默认参数
- 已将 `data/runtime_config.json` 加入 `.gitignore`

核心文件：

- `src/trade_signal_app/views.py`
- `src/trade_signal_app/main.py`
- `src/trade_signal_app/runtime_config.py`
- `src/trade_signal_app/app_state.py`

## 2.6 智能总控台

- 新增统一总控台 `/terminal`
- 新增模块页：
  - `/terminal/market`
  - `/terminal/community`
  - `/terminal/onchain`
  - `/terminal/basis`
  - `/terminal/strategies`
  - `/terminal/trading`
  - `/terminal/risk`
- 支持平台能力、账户、策略、风控和日志 API
- 支持 Binance / OKX 接入状态、Twitter tracked accounts、链上公开数据预设 / CSV、现货 / 合约价差、策略命中和通用 LLM / 本地规则分析
- 支持中英文界面切换

核心文件：

- `src/trade_signal_app/intelligence.py`
- `src/trade_signal_app/platform.py`
- `src/trade_signal_app/views.py`

## 2.7 自动量化交易

- 支持 `/trading` 自动交易页面
- 支持 `POST /api/trading/run`
- 支持 `POST /api/trading/paper/run`
- 支持 `paper` 模拟交易和受保护 `live` 模式
- 支持 Binance Spot 市价买入 / 卖出与 `order/test`
- 支持止损、止盈、冷却、最大持仓、最大总敞口
- 止损 / 止盈检查会对未进入本轮候选榜的已持仓标的补拉 24h ticker 最新价
- 支持本地持仓和事件持久化
- 平仓事件已记录：
  - 退出原因
  - 已实现盈亏
  - 已实现盈亏百分比
- live 持仓不会在 paper / 强制 paper 模式下被模拟平仓，避免误删真实仓位记录
- live 平仓必须同时满足 Auto Trade 已启用、`mode=live`、`AI_TRADE_LIVE_CONFIRM` 已确认
- 平台账户快照已汇总：
  - 当前敞口
  - 已实现盈亏
  - 平仓次数
  - 平仓胜率

核心文件：

- `src/trade_signal_app/trading.py`
- `src/trade_signal_app/platform.py`
- `src/trade_signal_app/autotrade.py`

## 2.8 自然语言策略编译

- 总控台策略页 `/terminal/strategies` 新增自然语言策略编译器
- 新增 `POST /api/strategy/compile`
- 支持用户描述策略后拆解为：
  - 标的池、周期、策略风格
  - 入场规则、离场规则、风控规则
  - `/backtest` 可接收的回测参数
  - paper 自动交易参数
- LLM Provider / 模型名称沿用 `/settings` 的 Intelligence & LLM 配置
- 未配置或未启用 LLM 时自动使用本地规则编译
- 编译结果默认保持 `autotrade.enabled=false`、`mode=paper`，不会自动开启实盘
- 内置识别均值回归、动量突破、等权再平衡、BTC 隔夜季节性和 basis 监控语义

核心文件：

- `src/trade_signal_app/strategy_builder.py`
- `src/trade_signal_app/main.py`
- `src/trade_signal_app/views.py`

## 2.9 基准测试工作台

- `/backtest` 新增 Benchmark Workbench 区块
- 单币种回测报告新增买入持有基准权益曲线
- 页面可同屏比较：
  - Strategy Returns V2：当前最佳策略权益
  - Strategy Returns V1：次优策略版本权益
  - Holding Returns：标的买入持有基准
- 右侧面板展示已完成交易流水、AI 推理摘要和关键说明
- `/api/backtest` 和 CSV 导出包含 `buy_hold_final_equity` 与 `buy_hold_return_pct`

核心文件：

- `src/trade_signal_app/backtest.py`
- `src/trade_signal_app/ui.py`
- `src/trade_signal_app/views.py`

## 3. 最近一轮完成内容

最近新增和收口内容：

- 新增智能总控台 `/terminal` 与 7 个模块页
- 新增平台能力、账户、策略、风控、日志 API
- 新增自动交易页 `/trading`、自动交易 API 与自动交易 CLI
- 新增 paper / live 执行模式，live 模式通过环境变量和 `order/test` 保护
- 新增 OKX、公开数据源预设、通用 LLM、Intelligence、Auto Trade 运行配置项
- 新增 OpenAI / Anthropic / Gemini / DeepSeek / xAI / Mistral / Qwen / Kimi 综合分析兼容层，未配置时自动回退本地规则
- 新增自然语言策略编译器：用户描述交易策略后，系统生成回测参数、paper 执行参数和风险提示
- 新增 `POST /api/strategy/compile`
- 新增基准测试工作台：策略权益、次优版本、买入持有基准和已完成交易流水同屏展示
- 单币种回测报告新增 buy-and-hold 基准曲线，并进入 `/api/backtest` 与 CSV 导出
- 新增中英文界面切换
- 新增交易终端式全局 UI：左侧模块菜单、顶部功能导航、暗色数据面板和底部行情条
- 新增平仓事件 PnL 记录，并在交易页、总控台账户概览和平台账户 API 中展示已实现盈亏 / 平仓胜率
- 修正自动交易退出检查：已持仓但未进入本轮扫描信号榜的标的，也会通过 Binance 24h ticker 补价后判断止损 / 止盈
- 强化执行安全边界：live 持仓必须在 live 模式下真实平仓，paper 模式只会保留仓位并记录阻断事件
- 修正 live 平仓护栏：自动交易关闭或缺少 `AI_TRADE_LIVE_CONFIRM` 时，即使触发止损 / 止盈也不会提交真实卖单
- 学习并吸收 Quant Wiki crypto 策略，新增 spot-only 等权再平衡溢价研究能力：
  - `crypto_rebalance_premium` 预设
  - `btc_overnight_seasonality` 预设
  - `rebalance_reports` API 输出
  - `/backtest` Rebalance Premium 页面区块
  - 研究笔记 `docs/research/crypto-rebalance-premium.md`

- 增加根级运行配置页 `/settings`
- 把 Binance / X / Twitter / 策略参数统一成运行时配置
- 将运行配置持久化到本地 JSON
- 扫描页与回测页接入运行配置默认值
- Twitter 情报账号支持 `off / blend / only`
- Binance SIGNED 接口失败时，页面和 API 返回可读错误，不再直接 500
- 新增与更新测试覆盖：
  - `tests/test_main.py`
  - `tests/test_runtime_config.py`
  - `tests/test_community.py`
  - `tests/test_binance_client.py`
- 新增配置模板导出接口：`/api/settings/export`
- 新增设置页模板导入能力：`POST /settings/import`
- 回测页新增结果导出入口
- 新增回测导出接口：`/api/backtest/export?format=csv|json`
- 回测页新增单币种 / 组合权益排名总览
- 新增本地新闻情报 CSV provider，可与 X / CSV 社区评分混合
- 新增 Reddit provider 与运行配置项，可显式加入社区评分混合
- 新增本地 Telegram 情报 CSV provider，可显式加入社区评分混合
- 新增内建回测 preset 与模板 API：`/api/backtest/presets`
- 新增可选加密配置存储，支持对 `runtime_config.json` 做口令保护
- 新增 3 个 BTC 专用回测 preset，可直接用于策略验证
- 使用 Binance public-data 真实 BTCUSDT 4h ZIP 对 3 个 BTC 模板完成实测
- 已优化 `btc_cycle_trend`：
  - `min_rsi: 48 -> 46`
  - `max_rsi: 72 -> 74`
- 已验证 `btc_core_trading` 是当前更稳的主模板：
  - 2024-2025 全样本：`final_equity 1.0782`、`max_drawdown -5.34%`
  - 2025 样本外：`final_equity 1.0768`、`max_drawdown -3.45%`
- 已验证 `btc_cycle_trend` 更适合作为趋势年份进攻模板：
  - 2024 样本内：`final_equity 1.2325`
  - 2025 样本外：`final_equity 0.9053`
- 收口默认测试入口，仓库根目录直接执行 `pytest -q` 即可完成测试发现
- 增加包级模块入口：`python3 -m trade_signal_app`
- 增加安装后 CLI 入口：`trade-signal-web`、`trade-signal-backtest`
- Web CLI 新增 `--host`、`--port`、`--version`
- Backtest CLI 新增 `--version`，并统一版本输出
- README 已区分“源码目录运行”和“安装后运行”两条路径
- 版本号改为以 `src/trade_signal_app/__init__.py` 为单一来源

## 4. 验证记录

2026-05-04 已执行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall src run.py run_backtest.py tests
```

结果：

- 86 个测试通过
- 编译通过
- `/settings`
- `/`
- `/backtest`
- `/trading`
- `/terminal`
- `/api/backtest`
- `/api/backtest/export`
- `/api/backtest/presets`
- `/api/trading/status`
- `/api/platform/accounts`
- `python3 -m trade_signal_app --help`
- `python3 -m trade_signal_app --version`
- `python3 -m trade_signal_app.backtest --help`
- `python3 -m trade_signal_app.backtest --version`

均已做本地冒烟验证

## 5. 当前已知约束

- 默认仍兼容本地明文 `data/runtime_config.json`；只有在设置 `RUNTIME_CONFIG_PASSPHRASE` 后才会写入加密格式
- 未接入多用户权限体系
- 已接入受保护 Binance Spot live 下单通道，但默认 paper / order-test；不适合无人值守实盘托管
- Twitter/X 数据依赖 Bearer Token 和接口配额
- Binance 账户手续费依赖 API Key、权限与 IP 白名单
- 当前 BTC 模板验证仅覆盖 `BTCUSDT 4h / 2024-01 ~ 2025-12` 这一组样本，尚未扩展到更多年份与多交易对

## 7. 发布状态

当前仓库已完成 Git 初始化、远端绑定、首个 release 发布与主分支同步。

当前状态：

- Git 仓库已初始化
- `origin` 已绑定 `https://github.com/kongwen686/ai-trade.git`
- `main` 已推送
- 已发布 release：`v0.1.0`
- 当前代码版本：`v0.3.0`
