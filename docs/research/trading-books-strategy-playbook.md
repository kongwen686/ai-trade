# Trading Books and Strategy Playbook

本手册把已检索到的交易书籍压缩为工程化学习路线和策略实现清单。它不是任何书籍的复制或替代品；这里只保留可验证、可回测、可落到本项目的原则。

## 学习吸收顺序

| 顺序 | 书籍 / 作者 | 吸收重点 | 项目落点 |
| --- | --- | --- | --- |
| 1 | Trading in the Zone / Mark Douglas | 交易纪律、预期管理、避免单笔结果驱动决策 | 默认 paper 验证、实盘确认环境变量、阻断保证收益语义 |
| 2 | Market Wizards / Jack Schwager | 不同交易员的共同点是风控、仓位、适配自身周期 | 策略编译结果必须带 risk_controls 和 warnings |
| 3 | Technical Analysis of the Financial Markets / John Murphy | 趋势、动量、支撑阻力和多周期确认 | RSI、EMA、MACD、KDJ、量价评分 |
| 4 | Trading Systems and Methods / Perry Kaufman | 系统设计、参数测试、交易成本、稳健性 | 回测参数、滑点模型、手续费模型、预设模板 |
| 5 | Systematic Trading / Robert Carver | 规则化、仓位管理、分散、避免过度拟合 | portfolio_top_n、max_exposure、max_concurrent_positions |
| 6 | Quantitative Trading / Ernest Chan | 从想法到数据、回测、执行的闭环 | strategy_builder、backtest、paper autotrade |
| 7 | Algorithmic Trading / Ernest Chan | 均值回归、动量、协整和实现细节 | mean_reversion、momentum、pair/stat-arb research backtest |
| 8 | Trading and Exchanges / Larry Harris | 订单簿、市场微观结构、滑点和成交机制 | dynamic slippage、order/test、live readiness |
| 9 | Advances in Financial Machine Learning / Marcos Lopez de Prado | 数据泄漏、多重检验、标签、样本外验证 | 后续扩展 walk-forward、purged CV、策略稳定性报告 |
| 10 | Machine Learning for Trading / Stefan Jansen | 特征管线、模型验证、生产监控 | 后续扩展特征仓库、模型监控、信号漂移检查 |

## 策略实现原则

1. 每个策略先进入 `research` 或 `watch_only` 状态，不能默认开启实盘。
2. 每个策略必须定义入场、退出、风控、成本假设和适用市场。
3. 能用现货多头实现的策略，先接入回测和 paper 交易。
4. 需要做空、杠杆、期权或双腿交易的策略，先做监控和研究，不直接下单。
5. 每次新增策略都要至少覆盖自然语言编译测试和平台目录测试。

## 策略路线图

| 策略 | 当前状态 | 可落地范围 | 下一步 |
| --- | --- | --- | --- |
| 综合评分突破 | 已实现 | 现货多头扫描、paper/live guarded 执行 | 加强样本外稳定性报告 |
| 量价压力 | 已实现 | 候选排序和策略命中 | 独立回测模板 |
| 趋势跟随 | 已接入编译器和策略目录 | EMA 20/50 + score + volume 的现货多头版本 | 增加专用回测分析页说明 |
| 突破 | 已实现为 `breakout` | 阻力 / 区间突破、强量能、短持有 | 增加假突破统计和回踩确认 |
| 动量轮动 | 已实现为 `momentum` | 横截面相对强弱、组合轮动、中等持有 | 增加排名稳定性和换手成本报告 |
| 均值回归 | 已实现为 `mean_reversion` | RSI 低位反弹、冷却期、短持有 | 增加 z-score / Bollinger 版本 |
| 等权再平衡 | 已实现研究预设 | 多币种组合回测 | 增加调仓事件导出 |
| 时间季节性 | 已实现 BTC 隔夜研究预设 | BTC UTC 时间窗口回测 | 扩展到周内效应 |
| Basis / 套利 | 已接入 paper 双腿模拟 | 现货/合约价差观察、风险阻断、现货多腿 + 永续空腿模拟 | 累积不同市场状态的 paper 样本 |
| 配对交易 / 统计套利 | 已接入研究回测 | 滚动对数价格 OLS、动态对冲比率、z-score、下一根开盘双腿撮合 | 增加协整检验、walk-forward 和样本外淘汰门槛 |
| Carry / 资金费率 | 已接入 paper 双腿模拟 | 公开 funding/basis 数据、资金费率累计、基差收敛/止损/超时退出、双腿成本 | 增加历史 funding 序列回放和断线期间精确结算 |
| 波动率状态过滤 | 已实现 | 扫描标注、回测入场过滤、自动交易前阻断 | 增加分市场/分周期阈值校准 |
| 做市 | 仅保留研究状态 | 需要 L2 订单簿、队列成交、低延迟、库存管理和 kill switch | 完成仿真基础设施前不接报价或下单 |

## 趋势跟随策略规格

趋势跟随来自技术分析、系统交易和 CTA 类方法的共同框架：不预测顶部和底部，只在趋势结构成立后跟随，并接受震荡期小亏。

当前实现为现货多头受限版本：

- style: `trend_following`
- 默认触发语义：`趋势跟随`、`顺势`、`海龟`、`Donchian`、`trend-follow`
- 典型入场：EMA 20/50 多头结构、综合评分达到阈值、量能确认
- 典型退出：固定止损、固定止盈、最大持有 K 线、趋势转弱复核
- 默认风险：冷却期、并发限制、paper 验证、不开启实盘
- BTC 单标的默认使用 `btc_cycle_trend` 预设，多标的使用均衡波段预设

## 后续开发批次

### Batch 1: 已开始

- 文档化书籍和策略吸收结果
- 拆出 `trend_following`
- 在策略目录展示趋势跟随

### Batch 2: 已开始

- 拆分 `breakout` 与 `momentum`
- 给回测页增加策略解释字段
- 增加基础稳定性检查：交易次数、最大回撤、Profit Factor、成本敏感性提示
- 增加高级稳定性检查基础版：score threshold 邻域、滑点上调、滚动 walk-forward 验证窗口
- 待补充参数热力图和更完整的滚动窗口汇总

### Batch 3: 已完成基础版

- 已实现波动率状态过滤基础版
- 已增加 pair spread 数据结构和配对交易研究回测
- 已增加 funding/carry 公开数据接入、SQLite 状态和双腿 paper 引擎
- Bollinger 专用均值回归仍待补充

### Batch 4

- 引入 walk-forward 验证
- 引入样本外报告和策略过拟合提示
- 对自动交易候选增加策略来源解释
