from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from trade_signal_app.models import Candlestick
from trade_signal_app.tradingview_data import (
    fetch_tradingview_history,
    load_tradingview_csv,
    normalize_tradingview_interval,
    tradingview_cache_path,
    write_tradingview_csv,
)


class TradingViewDataTests(unittest.TestCase):
    def test_normalize_tradingview_interval_aliases(self) -> None:
        self.assertEqual(normalize_tradingview_interval("240"), "4h")
        self.assertEqual(normalize_tradingview_interval("D"), "1d")

    def test_cache_path_uses_exchange_symbol_interval_layout(self) -> None:
        path = tradingview_cache_path(Path("/tmp/cache"), "binance", "btcusdt", "4h")
        self.assertEqual(path, Path("/tmp/cache/BINANCE/BTCUSDT/4h.csv"))

    def test_load_and_write_tradingview_csv_roundtrip(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = [
            Candlestick(
                open_time=start,
                close_time=start + timedelta(hours=4) - timedelta(milliseconds=1),
                open_price=100.0,
                high_price=105.0,
                low_price=98.0,
                close_price=104.0,
                volume=10.0,
                quote_volume=1040.0,
                trade_count=20,
                taker_buy_base_volume=5.0,
                taker_buy_quote_volume=520.0,
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "BINANCE" / "BTCUSDT" / "4h.csv"
            write_tradingview_csv(path, candles)
            loaded = load_tradingview_csv(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].open_time, start)
        self.assertEqual(loaded[0].close_price, 104.0)
        self.assertEqual(loaded[0].taker_buy_quote_volume, 520.0)

    def test_fetch_uses_binance_fallback_when_tvdatafeed_missing(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = [
            Candlestick(
                open_time=start,
                close_time=start + timedelta(hours=4) - timedelta(milliseconds=1),
                open_price=100.0,
                high_price=105.0,
                low_price=98.0,
                close_price=104.0,
                volume=10.0,
                quote_volume=1040.0,
                trade_count=20,
                taker_buy_base_volume=5.0,
                taker_buy_quote_volume=520.0,
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            with (
                unittest.mock.patch("trade_signal_app.tradingview_data._load_tvdatafeed", side_effect=ValueError("missing tvdatafeed")),
                unittest.mock.patch("trade_signal_app.tradingview_data._fetch_binance_public_history", return_value=candles) as fetch_binance,
            ):
                result = fetch_tradingview_history(
                    cache_root=cache_root,
                    exchange="binance",
                    symbol="btcusdt",
                    interval="240",
                    bars=5000,
                )

            cached = load_tradingview_csv(result.cache_path, interval=result.interval)

        fetch_binance.assert_called_once_with(symbol="btcusdt", interval="4h", bars=5000)
        self.assertEqual(result.source, "binance_public_fallback")
        self.assertEqual(result.candle_count, 1)
        self.assertEqual(cached[0].close_price, 104.0)

    def test_fetch_refreshes_underfilled_cache(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        stale_candles = [
            Candlestick(
                open_time=start,
                close_time=start + timedelta(hours=4) - timedelta(milliseconds=1),
                open_price=100.0,
                high_price=105.0,
                low_price=98.0,
                close_price=104.0,
                volume=10.0,
                quote_volume=1040.0,
                trade_count=20,
                taker_buy_base_volume=5.0,
                taker_buy_quote_volume=520.0,
            )
        ]
        refreshed_candles = [
            *stale_candles,
            Candlestick(
                open_time=start + timedelta(hours=4),
                close_time=start + timedelta(hours=8) - timedelta(milliseconds=1),
                open_price=104.0,
                high_price=109.0,
                low_price=103.0,
                close_price=108.0,
                volume=12.0,
                quote_volume=1296.0,
                trade_count=24,
                taker_buy_base_volume=7.0,
                taker_buy_quote_volume=756.0,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            cache_path = tradingview_cache_path(cache_root, "BINANCE", "BTCUSDT", "4h")
            write_tradingview_csv(cache_path, stale_candles)
            with (
                unittest.mock.patch("trade_signal_app.tradingview_data._load_tvdatafeed", side_effect=ValueError("missing tvdatafeed")),
                unittest.mock.patch("trade_signal_app.tradingview_data._fetch_binance_public_history", return_value=refreshed_candles) as fetch_binance,
            ):
                result = fetch_tradingview_history(
                    cache_root=cache_root,
                    exchange="BINANCE",
                    symbol="BTCUSDT",
                    interval="4h",
                    bars=2,
                )

            cached = load_tradingview_csv(result.cache_path, interval=result.interval)

        fetch_binance.assert_called_once_with(symbol="BTCUSDT", interval="4h", bars=2)
        self.assertEqual(result.source, "binance_public_fallback")
        self.assertEqual(result.candle_count, 2)
        self.assertEqual(len(cached), 2)
        self.assertEqual(cached[-1].close_price, 108.0)


if __name__ == "__main__":
    unittest.main()
