# BTC Preset Validation

更新日期：2026-04-22

## 背景

这份笔记记录了 3 个 BTC 定向回测模板的首轮验证结果：

- `btc_cycle_trend`
- `btc_core_trading`
- `btc_compounding_risk_off`

这 3 个模板的设计思路，来自对公开 BTC 交易账户档案的研究归纳，目标不是复刻原账户，而是把其中较稳定的仓位管理和趋势执行风格，沉淀成可回测模板。

## 数据范围

本轮验证使用 Binance public data：

- 标的：`BTCUSDT`
- 周期：`4h`
- 样本区间：`2024-01` 到 `2025-12`

本地下载路径：

```text
data/spot/monthly/klines/BTCUSDT/4h/*.zip
```

说明：

- 这些 ZIP 只作为本地研究数据使用
- 已加入 `.gitignore`
- 不会被提交到仓库

## 初始模板结果

在 `2024-01 ~ 2025-12` 全样本上的首轮结果：

| preset | trades | final_equity | max_drawdown | win_rate | profit_factor |
|---|---:|---:|---:|---:|---:|
| `btc_cycle_trend` | 44 | 1.0247 | -16.47% | 52.27% | 1.0904 |
| `btc_core_trading` | 43 | 1.0485 | -12.88% | 55.81% | 1.1801 |
| `btc_compounding_risk_off` | 45 | 0.9474 | -10.03% | 46.67% | 0.8467 |

初步结论：

- `btc_core_trading` 最均衡
- `btc_cycle_trend` 能赚钱，但回撤明显偏大
- `btc_compounding_risk_off` 当前版本不成立

## btc_core_trading 优化

对 `btc_core_trading` 做了小规模参数扫描后，只保留一个低风险调整：

- `min_buy_pressure: 0.54 -> 0.56`

没有继续扩大调参范围，原因是：

- 这组样本只有两年
- 过度贴合 `2024-2025` 没意义
- 当前目标是先找出稳定改进，而不是追求局部最优

优化后全样本结果：

| preset | trades | final_equity | max_drawdown | win_rate | profit_factor |
|---|---:|---:|---:|---:|---:|
| `btc_core_trading` | 24 | 1.0782 | -5.34% | 66.67% | 1.7801 |

结论：

- 收紧主动买盘条件后，交易数下降
- 但收益质量和回撤控制同步改善
- 这个模板目前适合作为主推荐模板

## btc_cycle_trend 优化

对 `btc_cycle_trend` 做了更小范围的趋势参数扫描，最后只保留一组有效调整：

- `min_rsi: 48 -> 46`
- `max_rsi: 72 -> 74`

优化后全样本结果：

| preset | trades | final_equity | max_drawdown | win_rate | profit_factor |
|---|---:|---:|---:|---:|---:|
| `btc_cycle_trend` | 49 | 1.1158 | -13.55% | 55.10% | 1.2810 |

结论：

- 原版模板对 BTC 趋势段过于挑剔
- 适度放宽 RSI 区间后，趋势模板才真正工作起来
- 但它仍然比 `btc_core_trading` 更依赖行情结构

## 样本外验证

为了避免只看全样本结果，本轮额外做了简单的样本内 / 样本外切分：

- `2024` 作为 in-sample
- `2025` 作为 out-of-sample

### 2024 in-sample

| preset | trades | final_equity | max_drawdown | win_rate | profit_factor |
|---|---:|---:|---:|---:|---:|
| `btc_cycle_trend` | 26 | 1.2325 | -8.01% | 65.38% | 2.0890 |
| `btc_core_trading` | 8 | 1.0013 | -5.34% | 75.00% | 1.0452 |
| `btc_compounding_risk_off` | 22 | 1.0474 | -7.49% | 54.55% | 1.3553 |

### 2025 out-of-sample

| preset | trades | final_equity | max_drawdown | win_rate | profit_factor |
|---|---:|---:|---:|---:|---:|
| `btc_cycle_trend` | 23 | 0.9053 | -13.55% | 43.48% | 0.6244 |
| `btc_core_trading` | 16 | 1.0768 | -3.45% | 62.50% | 2.6487 |
| `btc_compounding_risk_off` | 22 | 0.9205 | -9.37% | 40.91% | 0.4871 |

## 最终判断

### 1. 主推荐模板：`btc_core_trading`

原因：

- 样本外结果最好
- 最大回撤最小
- 交易数不高，但质量高
- 更适合当前项目的研究型使用场景

### 2. 次推荐模板：`btc_cycle_trend`

原因：

- 在趋势年份里有进攻性
- `2024` 样本内表现明显更强
- 但 `2025` 样本外失效，说明它更吃环境

适用场景：

- 当你明确判断 BTC 处于强趋势阶段
- 并且愿意承担更高回撤

### 3. 观察模板：`btc_compounding_risk_off`

原因：

- 初衷合理
- 但当前约束过强，收益被压没
- 现阶段不建议作为默认模板

## 后续建议

后续研究可以继续沿这 3 条线推进：

1. 继续做多年份验证
   - 至少扩到 `2022-2025`
2. 把 `btc_core_trading` 做更细的样本外 walk-forward
   - 不再做一次性全样本扫描
3. 给 `btc_cycle_trend` 增加趋势环境过滤
   - 让它只在更明确的单边行情中启用

## 当前推荐顺序

1. `btc_core_trading`
2. `btc_cycle_trend`
3. `btc_compounding_risk_off`
