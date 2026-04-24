# 项目进度文档

更新日期：2026-04-24

## 1. 项目目标

本项目是一个基于 Binance Spot 市场数据的本地交易信号与历史回测应用，目标是把：

- 实时市场信号
- 技术指标筛选
- X/Twitter 舆情情报
- 历史回测与策略验证

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
- 支持 Reddit 公开搜索舆情
- 支持社媒查询别名配置
- 支持情报账号列表
- 支持三种 Twitter 情报模式：
  - `off`
  - `blend`
  - `only`
- 支持将普通舆情与指定账号情报按权重混合

核心文件：

- `src/trade_signal_app/community.py`
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
- 已将 `data/runtime_config.json` 加入 `.gitignore`

核心文件：

- `src/trade_signal_app/views.py`
- `src/trade_signal_app/main.py`
- `src/trade_signal_app/runtime_config.py`
- `src/trade_signal_app/app_state.py`

## 3. 最近一轮完成内容

本轮新增和收口内容：

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

2026-04-24 已执行：

```bash
pytest -q
python3 -m compileall src run.py run_backtest.py tests
```

结果：

- 60 个测试通过
- 编译通过
- `/settings`
- `/`
- `/backtest`
- `/api/backtest`
- `/api/backtest/export`
- `/api/backtest/presets`
- `python3 -m trade_signal_app --help`
- `python3 -m trade_signal_app --version`
- `python3 -m trade_signal_app.backtest --help`
- `python3 -m trade_signal_app.backtest --version`

均已做本地冒烟验证

## 5. 当前已知约束

- 默认仍兼容本地明文 `data/runtime_config.json`；只有在设置 `RUNTIME_CONFIG_PASSPHRASE` 后才会写入加密格式
- 未接入多用户权限体系
- 未接入真实下单，仅用于研究、筛选和回测
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
