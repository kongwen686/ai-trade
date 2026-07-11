from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import statistics
import unittest

from trade_signal_app.models import Candlestick, IndicatorSnapshot
from trade_signal_app.strategy import EntryRuleConfig, evaluate_long_entry
from trade_signal_app.volatility import _population_stddev, _rolling_volatilities, build_volatility_state


def _candles(returns_pct: list[float]) -> list[Candlestick]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    candles: list[Candlestick] = []
    for index, return_pct in enumerate(returns_pct):
        open_price = price
        price *= 1 + (return_pct / 100)
        range_pct = max(0.15, abs(return_pct) * 0.45)
        high = max(open_price, price) * (1 + range_pct / 100)
        low = min(open_price, price) * (1 - range_pct / 100)
        candles.append(
            Candlestick(
                open_time=start + timedelta(hours=index),
                close_time=start + timedelta(hours=index, minutes=59),
                open_price=open_price,
                high_price=high,
                low_price=low,
                close_price=price,
                volume=1_000.0,
                quote_volume=price * 1_000.0,
                trade_count=100,
                taker_buy_base_volume=550.0,
                taker_buy_quote_volume=price * 550.0,
            )
        )
    return candles


def _entry_indicators() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        close_price=105.0,
        ema_20=102.0,
        ema_50=98.0,
        ema_spread_pct=4.0,
        price_vs_ema20_pct=2.0,
        rsi_14=58.0,
        macd=1.8,
        macd_signal=1.1,
        macd_hist=0.7,
        bullish_macd_cross=False,
        macd_hist_rising=True,
        k_value=62.0,
        d_value=58.0,
        j_value=70.0,
        bullish_kdj_cross=False,
        volume_ratio=1.4,
        buy_pressure_ratio=0.62,
        recent_change_pct=1.5,
    )


class VolatilityStateTests(unittest.TestCase):
    def test_float_stddev_matches_standard_library_reference(self) -> None:
        values = [0.12, -0.33, 0.44, 1.02, -0.75, 0.08, 0.19, -0.21]

        self.assertAlmostEqual(_population_stddev(values), statistics.pstdev(values), places=12)
        rolling = _rolling_volatilities(values, window=4, baseline_window=8)
        expected = [statistics.pstdev(values[end - 4 : end]) for end in range(4, len(values) + 1)]
        self.assertEqual(len(rolling), len(expected))
        for actual, reference in zip(rolling, expected):
            self.assertAlmostEqual(actual, reference, places=12)

    def test_detects_compressed_volatility_after_quiet_period(self) -> None:
        returns = [1.4 if index % 2 == 0 else -1.3 for index in range(120)]
        returns.extend(0.04 if index % 2 == 0 else -0.04 for index in range(40))

        state = build_volatility_state(_candles(returns))

        self.assertEqual(state.regime, "compressed")
        self.assertLess(state.volatility_ratio, 0.85)
        self.assertLessEqual(state.volatility_percentile, 25.0)

    def test_detects_extreme_volatility_expansion(self) -> None:
        returns = [0.2 if index % 2 == 0 else -0.18 for index in range(130)]
        returns.extend(3.2 if index % 2 == 0 else -2.8 for index in range(30))

        state = build_volatility_state(_candles(returns))

        self.assertEqual(state.regime, "extreme")
        self.assertGreaterEqual(state.volatility_ratio, 2.0)
        self.assertGreater(state.atr_pct, 1.0)

    def test_entry_filter_blocks_extreme_regime(self) -> None:
        indicators = replace(
            _entry_indicators(),
            volatility_regime="extreme",
            volatility_label="极端波动",
            volatility_percentile=98.0,
            volatility_ratio=2.4,
            atr_pct=4.2,
        )

        decision = evaluate_long_entry(
            score=82.0,
            indicators=indicators,
            config=EntryRuleConfig(min_score=75.0),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("极端波动过滤", " ".join(decision.reasons))

    def test_entry_filter_can_be_disabled_for_comparison_backtests(self) -> None:
        indicators = replace(
            _entry_indicators(),
            volatility_regime="extreme",
            volatility_label="极端波动",
            volatility_percentile=98.0,
            volatility_ratio=2.4,
            atr_pct=4.2,
        )

        decision = evaluate_long_entry(
            score=82.0,
            indicators=indicators,
            config=EntryRuleConfig(min_score=75.0, volatility_filter_enabled=False),
        )

        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
