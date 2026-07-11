from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
import unittest

from trade_signal_app.btc_signal import BTC_LEVERAGE_REFERENCE, build_btc_signal_from_candles
from trade_signal_app.models import Candlestick


def _build_candles(*, count: int, step_hours: int, mode: str) -> list[Candlestick]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    candles: list[Candlestick] = []
    previous_close = 100.0 if mode != "bear" else 220.0
    for index in range(count):
        if mode == "bear":
            close = 220.0 - (index * 0.32) + math.sin(index / 5) * 1.2
        elif index < count - 80:
            close = 100.0 + (index * 0.17) + math.sin(index / 7) * 1.1
        elif index < count - 30:
            close = 148.0 - ((index - (count - 80)) * 0.18) + math.sin(index / 6) * 0.9
        else:
            close = 139.0 + ((index - (count - 30)) * 0.12) + math.sin(index / 4) * 0.7
        close = max(close, 10.0)
        open_price = previous_close
        high = max(open_price, close) * (1.012 if mode != "bear" else 1.006)
        low = min(open_price, close) * (0.988 if mode != "bear" else 0.982)
        volume = 1000.0 + (index % 20) * 14.0
        if index == count - 1:
            volume *= 1.35
        taker_buy_ratio = 0.57 if mode != "bear" else 0.43
        open_time = start + timedelta(hours=step_hours * index)
        close_time = open_time + timedelta(hours=step_hours) - timedelta(milliseconds=1)
        candles.append(
            Candlestick(
                open_time=open_time,
                close_time=close_time,
                open_price=open_price,
                high_price=high,
                low_price=low,
                close_price=close,
                volume=volume,
                quote_volume=volume * close,
                trade_count=1000 + index,
                taker_buy_base_volume=volume * taker_buy_ratio,
                taker_buy_quote_volume=volume * close * taker_buy_ratio,
            )
        )
        previous_close = close
    return candles


class BtcSignalTests(unittest.TestCase):
    def test_build_btc_signal_contains_unique_levels_and_statistics(self) -> None:
        primary = _build_candles(count=360, step_hours=4, mode="bull")
        daily = primary[::6]
        entry = _build_candles(count=900, step_hours=1, mode="bull")

        summary = build_btc_signal_from_candles(
            primary_candles=primary,
            daily_candles=daily,
            entry_candles=entry,
            generated_at=datetime(2026, 7, 10, 22, 0, tzinfo=timezone.utc),
            include_backtests=False,
        )

        self.assertEqual(summary["symbol"], "BTCUSDT")
        self.assertIn(summary["action"], {"BUY", "HOLD", "SELL"})
        self.assertIn("btc_", summary["signal"])
        self.assertGreater(float(summary["score"]), 0.0)
        self.assertEqual(summary["trade_levels"]["leverage_reference"], BTC_LEVERAGE_REFERENCE)
        self.assertIn("leveraged_stop_roi_pct", summary["trade_levels"])
        self.assertIn("leveraged_take_profit_roi_pct", summary["trade_levels"])
        self.assertEqual(summary["price_source"], "cached_kline_close")
        self.assertEqual(summary["statistics"]["sample"]["primary_bars"], 360)
        self.assertIn("buy_hold_return_pct", summary["statistics"])
        self.assertIn("regime", summary)
        closes = summary["technical"]["indicator_snapshot"]["closes"]
        self.assertGreater(len(closes), 1)
        self.assertLessEqual(len(closes), 48)

    def test_build_btc_signal_can_use_live_market_price_for_trade_levels(self) -> None:
        primary = _build_candles(count=360, step_hours=4, mode="bull")
        live_price = primary[-1].close_price * 1.02
        primary[-10] = replace(primary[-10], high_price=live_price * 1.05)

        summary = build_btc_signal_from_candles(
            primary_candles=primary,
            daily_candles=primary[::6],
            entry_candles=_build_candles(count=900, step_hours=1, mode="bull"),
            include_backtests=False,
            market_price=live_price,
        )

        self.assertAlmostEqual(float(summary["price"]), live_price)
        self.assertAlmostEqual(float(summary["analysis_price"]), primary[-1].close_price)
        self.assertEqual(summary["price_source"], "live_market")
        self.assertAlmostEqual(float(summary["trade_levels"]["entry_price"]), live_price)
        self.assertAlmostEqual(summary["technical"]["indicator_snapshot"]["closes"][-1], live_price)
        self.assertGreater(float(summary["trade_levels"]["resistance_level"]), live_price)
        self.assertGreater(float(summary["trade_levels"]["resistance_distance_pct"]), 0.0)

    def test_build_btc_signal_marks_clear_bearish_regime_as_sell(self) -> None:
        primary = _build_candles(count=360, step_hours=4, mode="bear")
        daily = primary[::6]
        entry = _build_candles(count=900, step_hours=1, mode="bear")

        summary = build_btc_signal_from_candles(
            primary_candles=primary,
            daily_candles=daily,
            entry_candles=entry,
            include_backtests=False,
        )

        self.assertEqual(summary["action"], "SELL")
        self.assertEqual(summary["signal"], "btc_macro_risk_off_sell")


if __name__ == "__main__":
    unittest.main()
