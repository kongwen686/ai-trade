from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import trade_signal_app.main as app_main
import trade_signal_app.stat_arb as stat_arb
from trade_signal_app.models import Candlestick
from trade_signal_app.stat_arb import (
    PairStatArbConfig,
    align_pair_candles,
    run_pair_stat_arb_backtest,
)


def _candle(timestamp: datetime, open_price: float, close_price: float) -> Candlestick:
    return Candlestick(
        open_time=timestamp,
        close_time=timestamp + timedelta(hours=1) - timedelta(milliseconds=1),
        open_price=open_price,
        high_price=max(open_price, close_price) * 1.002,
        low_price=min(open_price, close_price) * 0.998,
        close_price=close_price,
        volume=1000.0,
        quote_volume=1000.0 * close_price,
        trade_count=100,
        taker_buy_base_volume=520.0,
        taker_buy_quote_volume=520.0 * close_price,
    )


def _pair_series(count: int = 320) -> tuple[list[Candlestick], list[Candlestick]]:
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles_a: list[Candlestick] = []
    candles_b: list[Candlestick] = []
    previous_a = 100.0
    previous_b = 100.0
    residual = 0.0
    shocks = {85: 0.055, 145: -0.05, 205: 0.06, 265: -0.055}
    for index in range(count):
        residual *= 0.78
        residual += shocks.get(index, 0.0)
        close_b = 100.0 * math.exp(index * 0.0012)
        close_a = close_b * math.exp(residual)
        timestamp = started_at + timedelta(hours=index)
        candles_a.append(_candle(timestamp, previous_a, close_a))
        candles_b.append(_candle(timestamp, previous_b, close_b))
        previous_a = close_a
        previous_b = close_b
    return candles_a, candles_b


class PairStatArbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candles_a, self.candles_b = _pair_series()
        self.config = PairStatArbConfig(
            lookback_bars=60,
            entry_z=1.8,
            exit_z=0.35,
            stop_z=4.5,
            max_holding_bars=30,
            min_correlation=0.35,
            max_hedge_ratio=3.0,
            notional_per_leg=1000.0,
            initial_equity=10_000.0,
            fee_bps_per_leg=0.0,
            slippage_bps_per_leg=0.0,
        )

    def test_aligns_candles_by_open_time(self) -> None:
        aligned = align_pair_candles(self.candles_a, self.candles_b[1:])

        self.assertEqual(len(aligned), len(self.candles_a) - 1)
        self.assertEqual(aligned[0].open_time, self.candles_a[1].open_time)

    def test_parses_nested_and_legacy_tradingview_cache_names(self) -> None:
        self.assertEqual(
            stat_arb._stat_arb_archive_key(Path("data/tradingview_klines/BINANCE/BTCUSDT/1h.csv")),
            ("BTCUSDT", "1h"),
        )
        self.assertEqual(
            stat_arb._stat_arb_archive_key(Path("BINANCE_ETHUSDT_4h.csv")),
            ("ETHUSDT", "4h"),
        )

    def test_runs_next_open_pair_backtest_with_mean_reversion_trades(self) -> None:
        report = run_pair_stat_arb_backtest(
            symbol_a="BTCUSDT",
            symbol_b="ETHUSDT",
            interval="1h",
            candles_a=self.candles_a,
            candles_b=self.candles_b,
            config=self.config,
        )

        self.assertTrue(report.research_only)
        self.assertGreater(report.metrics["trade_count"], 0)
        self.assertGreater(report.metrics["net_pnl"], 0)
        self.assertTrue(all(trade.opened_at > trade.signal_at for trade in report.trades))
        self.assertIn("method", report.diagnostics)

    def test_two_leg_costs_reduce_net_pnl(self) -> None:
        free = run_pair_stat_arb_backtest(
            symbol_a="BTCUSDT",
            symbol_b="ETHUSDT",
            interval="1h",
            candles_a=self.candles_a,
            candles_b=self.candles_b,
            config=self.config,
        )
        paid = run_pair_stat_arb_backtest(
            symbol_a="BTCUSDT",
            symbol_b="ETHUSDT",
            interval="1h",
            candles_a=self.candles_a,
            candles_b=self.candles_b,
            config=replace(self.config, fee_bps_per_leg=10.0, slippage_bps_per_leg=5.0),
        )

        self.assertEqual(free.metrics["trade_count"], paid.metrics["trade_count"])
        self.assertGreater(paid.metrics["costs"], 0)
        self.assertLess(paid.metrics["net_pnl"], free.metrics["net_pnl"])

    def test_rejects_insufficient_aligned_history(self) -> None:
        with self.assertRaisesRegex(ValueError, "Not enough aligned candles"):
            run_pair_stat_arb_backtest(
                symbol_a="BTCUSDT",
                symbol_b="ETHUSDT",
                interval="1h",
                candles_a=self.candles_a[:70],
                candles_b=self.candles_b[:70],
                config=self.config,
            )

    def test_main_payload_persists_research_backtest(self) -> None:
        report = run_pair_stat_arb_backtest(
            symbol_a="BTCUSDT",
            symbol_b="ETHUSDT",
            interval="1h",
            candles_a=self.candles_a,
            candles_b=self.candles_b,
            config=self.config,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "trade_signal_app.main.LOCAL_DATABASE_PATH",
            Path(temp_dir) / "ai_trade.sqlite3",
        ), patch(
            "trade_signal_app.main.run_pair_stat_arb_from_archives",
            return_value=(report, {"resolved_paths_a": ["a.csv"], "resolved_paths_b": ["b.csv"]}),
        ):
            payload = app_main._run_stat_arb_backtest_payload(
                {
                    "archive_a": "a.csv",
                    "archive_b": "b.csv",
                    "lookback_bars": "60",
                    "entry_z": "1.8",
                    "exit_z": "0.35",
                    "stop_z": "4.5",
                    "max_holding_bars": "30",
                    "min_correlation": "0.35",
                    "fee_bps_per_leg": "0",
                    "slippage_bps_per_leg": "0",
                }
            )
            status = app_main._local_data_store().status()

        self.assertEqual(len(payload["run_uid"]), 64)
        self.assertEqual(payload["report"]["strategy"], "pair_stat_arb")
        self.assertEqual(status["research_backtest_runs"], 1)


if __name__ == "__main__":
    unittest.main()
