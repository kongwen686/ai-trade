# Crypto Rebalance Premium Adaptation

更新日期：2026-05-04

## 来源

- Quant Wiki: `https://quant-wiki.com/repo/quant_learn/#cryptos`
- Quant Wiki strategy source: `rebalancing-premium-in-cryptocurrencies.py`

## 策略精华

Quant Wiki 的 Cryptos 小节包含两个策略：

- `Overnight Seasonality in Bitcoin`
- `Rebalancing Premium in Cryptocurrencies`

其中再平衡策略的核心是加密资产多币种等权组合的再平衡溢价：

- 先构建一篮子加密资产等权组合
- 定期把组合权重拉回等权
- 与买入后不再再平衡、任由权重漂移的组合对照
- 原策略还构造了 long rebalanced / short drift 的多空表达

本项目当前以 Binance Spot 研究和受保护执行为主，因此先落地 spot-only 版本：

- 不做空漂移组合
- 直接比较等权再平衡组合和买入持有漂移组合
- 显式计入再平衡 turnover 的手续费与滑点成本
- 输出再平衡相对漂移组合的 premium

## 系统落地

新增回测预设：

- `crypto_rebalance_premium`
- `btc_overnight_seasonality`

新增回测报告：

- `rebalance_reports`
- `rebalanced_final_equity`
- `buy_hold_final_equity`
- `premium_pct`
- `avg_turnover_pct`
- `rebalance_count`

使用方式：

```bash
PYTHONPATH=src python3 -m trade_signal_app
```

打开 `/backtest`，选择 `Crypto Rebalance Premium` 预设，并输入多个币种同周期 ZIP pattern，例如：

```text
data/spot/monthly/klines/*/4h/*.zip
```

如果至少两个币种有共同时间戳，页面会显示 `Rebalance Premium` 报告。

`btc_overnight_seasonality` 用于研究 UTC 22:00 开多 BTC、持有 2 小时后退出的时间窗口。该模板更适合 `BTCUSDT 1h` 或更细周期数据。

## 注意

- 这是研究模板，不是自动下单策略
- 等权再平衡在高波动资产中可能带来收益平滑，也可能被高换手成本吞噬
- 实盘前必须用目标交易对、周期、费率和滑点做样本外验证
