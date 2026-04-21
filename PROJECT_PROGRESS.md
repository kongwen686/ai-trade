# 项目进度文档

更新日期：2026-04-21

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

相关入口：

- Web：`/backtest`
- API：`/api/backtest`
- CLI：`run_backtest.py`

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

## 4. 验证记录

2026-04-21 已执行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m compileall src run.py run_backtest.py
```

结果：

- 53 个测试通过
- 编译通过
- `/settings`
- `/`
- `/backtest`
- `/api/backtest`
- `/api/backtest/export`

均已做本地冒烟验证

## 5. 当前已知约束

- 默认仍兼容本地明文 `data/runtime_config.json`；只有在设置 `RUNTIME_CONFIG_PASSPHRASE` 后才会写入加密格式
- 未接入多用户权限体系
- 未接入真实下单，仅用于研究、筛选和回测
- Twitter/X 数据依赖 Bearer Token 和接口配额
- Binance 账户手续费依赖 API Key、权限与 IP 白名单

## 7. 发布状态

本地代码已整理完毕，适合进入 Git 版本管理并推送到远程仓库。

但当前环境存在两个阻塞：

- 当前目录还不是 Git 仓库
- 当前机器未安装 GitHub CLI `gh`

因此“新建远程 GitHub 项目并推送”这一步还不能直接完成。

完成发布所需的最小条件：

```bash
brew install gh
gh auth login
```

完成后建议：

```bash
git init
git add .
git commit -m "initial trade signal app"
gh repo create ai-trade --private --source=. --remote=origin --push
```

如果后续确定要继续由我接手发布，我可以在 `gh` 可用后直接完成：

- 初始化 Git
- 首次提交
- 新建远程仓库
- 推送到 `origin`
