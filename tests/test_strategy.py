from __future__ import annotations

import unittest

from trade_signal_app.models import IndicatorSnapshot
from trade_signal_app.strategy import EntryRuleConfig, evaluate_long_entry


def _indicators(
    *,
    rsi: float = 58.0,
    price_vs_ema20_pct: float = 2.0,
    recent_change_pct: float = 1.5,
    support_distance_pct: float = 1.2,
    support_strength: float = 3.0,
    resistance_distance_pct: float = 4.8,
    risk_reward: float = 2.2,
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        close_price=105.0,
        ema_20=102.0,
        ema_50=98.0,
        ema_spread_pct=4.0,
        price_vs_ema20_pct=price_vs_ema20_pct,
        rsi_14=rsi,
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
        recent_change_pct=recent_change_pct,
        support_level=103.8,
        resistance_level=110.0,
        support_distance_pct=support_distance_pct,
        resistance_distance_pct=resistance_distance_pct,
        support_strength=support_strength,
        resistance_strength=2.0,
        structure_risk_reward=risk_reward,
        pullback_from_high_pct=1.0,
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
    )


class StrategyEntryTests(unittest.TestCase):
    def test_long_entry_allows_confirmed_signal_without_chasing(self) -> None:
        decision = evaluate_long_entry(
            score=82.0,
            indicators=_indicators(),
            config=EntryRuleConfig(min_score=75.0),
        )

        self.assertTrue(decision.allowed)
        self.assertIn("MACD 动能确认", decision.reasons)

    def test_long_entry_blocks_short_term_spike_chase(self) -> None:
        decision = evaluate_long_entry(
            score=82.0,
            indicators=_indicators(rsi=78.0, price_vs_ema20_pct=8.0, recent_change_pct=6.0),
            config=EntryRuleConfig(min_score=75.0),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("等待回调", " ".join(decision.reasons))

    def test_long_entry_blocks_when_support_and_risk_reward_are_weak(self) -> None:
        decision = evaluate_long_entry(
            score=82.0,
            indicators=_indicators(support_distance_pct=4.2, support_strength=1.0, resistance_distance_pct=1.0, risk_reward=0.7),
            config=EntryRuleConfig(min_score=75.0, structure_filter_enabled=True),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("等待更合理买点", " ".join(decision.reasons))


if __name__ == "__main__":
    unittest.main()
