from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
import zipfile

from trade_signal_app.archive_loader import load_public_data_klines
from trade_signal_app.indicators import build_indicator_snapshot
from trade_signal_app.models import Candlestick, MarketTicker
from trade_signal_app.scoring import build_subscores, composite_score


def _make_candles() -> list[Candlestick]:
    candles = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    for index in range(80):
        price += 0.7 if index < 70 else 1.2
        volume = 1000 + (index * 15)
        if index == 79:
            volume *= 1.8
        candles.append(
            Candlestick(
                open_time=start + timedelta(hours=index),
                close_time=start + timedelta(hours=index, minutes=59),
                open_price=price - 0.4,
                high_price=price + 0.8,
                low_price=price - 0.9,
                close_price=price,
                volume=volume,
                quote_volume=volume * price,
                trade_count=120 + index,
                taker_buy_base_volume=volume * 0.6,
                taker_buy_quote_volume=volume * price * 0.6,
            )
        )
    return candles


class IndicatorTests(unittest.TestCase):
    def test_indicator_snapshot_detects_bullish_profile(self) -> None:
        snapshot = build_indicator_snapshot(_make_candles())
        self.assertGreater(snapshot.ema_20, snapshot.ema_50)
        self.assertGreater(snapshot.rsi_14, 55)
        self.assertGreater(snapshot.volume_ratio, 1.2)
        self.assertGreater(snapshot.buy_pressure_ratio, 0.55)

    def test_composite_score_rewards_bullish_setup(self) -> None:
        snapshot = build_indicator_snapshot(_make_candles())
        ticker = MarketTicker(
            symbol="TESTUSDT",
            last_price=snapshot.close_price,
            price_change_percent=4.5,
            quote_volume=24_000_000,
            volume=300_000,
            trade_count=12_000,
        )
        breakdown = build_subscores(
            ticker=ticker,
            indicators=snapshot,
            liquidity_score=82.0,
            community_signal=None,
        )
        self.assertGreaterEqual(composite_score(breakdown), 70)

    def test_public_data_loader_accepts_microsecond_timestamps(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-1h-2026-01.zip"
            row = "1735689600000000,4.1,4.2,4.0,4.15,539.23,1735693199999999,2240.39,13,401.82,1669.98,0\n"

            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("BTCUSDT-1h-2026-01.csv", row)

            candles = load_public_data_klines(archive)
            self.assertEqual(len(candles), 1)
            self.assertEqual(candles[0].open_time.year, 2025)
            self.assertEqual(candles[0].close_price, 4.15)


if __name__ == "__main__":
    unittest.main()
