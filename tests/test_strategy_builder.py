from __future__ import annotations

import unittest

from trade_signal_app.runtime_config import BacktestDefaults, RuntimeConfig, ScanDefaults
from trade_signal_app.strategy_builder import _compiled_from_payload, compile_strategy


class StrategyBuilderTests(unittest.TestCase):
    def test_compiles_rsi_mean_reversion_strategy(self) -> None:
        strategy = compile_strategy(
            "BTC 15m RSI 超卖反弹，止损3%，止盈6%，最多持有8根K线",
            RuntimeConfig(),
        )

        self.assertEqual(strategy.source, "local_rules")
        self.assertEqual(strategy.style, "mean_reversion")
        self.assertEqual(strategy.symbols, ["BTCUSDT"])
        self.assertEqual(strategy.interval, "15m")
        self.assertEqual(strategy.backtest_defaults["stop_loss_pct"], 3.0)
        self.assertEqual(strategy.backtest_defaults["take_profit_pct"], 6.0)
        self.assertEqual(strategy.backtest_defaults["max_rsi"], 35.0)
        self.assertFalse(strategy.autotrade_defaults["enabled"])
        self.assertEqual(strategy.autotrade_defaults["mode"], "paper")

    def test_compiles_crypto_rebalance_premium_strategy(self) -> None:
        strategy = compile_strategy(
            "BTC ETH SOL 等权再平衡，每天调仓，比较自然漂移组合",
            RuntimeConfig(),
        )

        self.assertEqual(strategy.style, "rebalance")
        self.assertEqual(strategy.symbols, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.assertEqual(strategy.backtest_defaults["preset"], "crypto_rebalance_premium")
        self.assertEqual(strategy.backtest_defaults["portfolio_top_n"], 0)
        self.assertIn("等权", " ".join(strategy.entry_rules))

    def test_compiles_btc_overnight_seasonality_strategy(self) -> None:
        strategy = compile_strategy(
            "UTC 22:00 BTC 隔夜季节性策略，持有2小时",
            RuntimeConfig(scan_defaults=ScanDefaults(interval="1h")),
        )

        self.assertEqual(strategy.style, "seasonality")
        self.assertEqual(strategy.symbols, ["BTCUSDT"])
        self.assertEqual(strategy.interval, "1h")
        self.assertEqual(strategy.backtest_defaults["preset"], "btc_overnight_seasonality")
        self.assertEqual(strategy.backtest_defaults["max_holding_bars"], 2)

    def test_compiles_trend_following_strategy(self) -> None:
        strategy = compile_strategy(
            "BTC 4h 趋势跟随策略，EMA 20/50 多头，止损4%，止盈12%，最多持有20根K线",
            RuntimeConfig(scan_defaults=ScanDefaults(interval="4h")),
        )

        self.assertEqual(strategy.style, "trend_following")
        self.assertEqual(strategy.backtest_defaults["preset"], "btc_cycle_trend")
        self.assertEqual(strategy.backtest_defaults["holding_periods"], "6,12,24")
        self.assertEqual(strategy.backtest_defaults["max_holding_bars"], 20)
        self.assertIn("趋势", strategy.name)
        self.assertIn("EMA", " ".join(strategy.entry_rules))

    def test_compiles_breakout_strategy_separately_from_momentum(self) -> None:
        strategy = compile_strategy(
            "BTC 15m 箱体突破放量买入，止损3%，止盈8%，最多持有6根K线",
            RuntimeConfig(),
        )

        self.assertEqual(strategy.style, "breakout")
        self.assertEqual(strategy.interval, "15m")
        self.assertEqual(strategy.backtest_defaults["preset"], "breakout_aggressive")
        self.assertEqual(strategy.backtest_defaults["score_threshold"], 78.0)
        self.assertEqual(strategy.backtest_defaults["min_volume_ratio"], 1.35)
        self.assertEqual(strategy.backtest_defaults["stop_loss_pct"], 4.5)
        self.assertIn("突破", strategy.name)

    def test_compiles_momentum_rotation_strategy(self) -> None:
        strategy = compile_strategy(
            "ETH SOL 4h 动量轮动，选择相对强弱排名靠前的币，止损3%，止盈8%",
            RuntimeConfig(),
        )

        self.assertEqual(strategy.style, "momentum")
        self.assertEqual(strategy.symbols, ["ETHUSDT", "SOLUSDT"])
        self.assertEqual(strategy.backtest_defaults["preset"], "portfolio_rotation")
        self.assertEqual(strategy.backtest_defaults["portfolio_top_n"], 2)
        self.assertEqual(strategy.backtest_defaults["take_profit_pct"], 9.0)
        self.assertIn("动量", strategy.name)

    def test_llm_string_false_booleans_are_sanitized(self) -> None:
        base = compile_strategy("BTC 15m RSI 超卖反弹", RuntimeConfig())

        strategy = _compiled_from_payload(
            {
                "backtest_defaults": {
                    "no_kdj_confirmation": "false",
                    "no_binance_discount": "0",
                },
                "autotrade_defaults": {
                    "enabled": "true",
                    "mode": "live",
                    "order_test_only": "false",
                },
            },
            base=base,
            model="test-model",
        )

        self.assertFalse(strategy.backtest_defaults["no_kdj_confirmation"])
        self.assertFalse(strategy.backtest_defaults["no_binance_discount"])
        self.assertFalse(strategy.autotrade_defaults["enabled"])
        self.assertEqual(strategy.autotrade_defaults["mode"], "paper")
        self.assertTrue(strategy.autotrade_defaults["order_test_only"])

    def test_runtime_risk_defaults_are_clamped(self) -> None:
        strategy = compile_strategy(
            "BTC 15m 综合评分策略",
            RuntimeConfig(
                backtest_defaults=BacktestDefaults(
                    stop_loss_pct=-5.0,
                    take_profit_pct=250.0,
                    max_holding_bars=0,
                )
            ),
        )

        self.assertEqual(strategy.backtest_defaults["stop_loss_pct"], 0.1)
        self.assertEqual(strategy.backtest_defaults["take_profit_pct"], 100.0)
        self.assertEqual(strategy.backtest_defaults["max_holding_bars"], 3)


if __name__ == "__main__":
    unittest.main()
