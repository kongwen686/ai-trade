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
    resistance_level: float = 110.0,
    volume_ratio: float = 1.4,
    buy_pressure_ratio: float = 0.62,
    boll_mb: float = 102.0,
    boll_up: float = 106.0,
    boll_dn: float = 98.0,
    boll_position: float = 0.875,
    atr_pct: float = 1.0,
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
        volume_ratio=volume_ratio,
        buy_pressure_ratio=buy_pressure_ratio,
        recent_change_pct=recent_change_pct,
        boll_mb=boll_mb,
        boll_up=boll_up,
        boll_dn=boll_dn,
        boll_bandwidth_pct=((boll_up - boll_dn) / boll_mb) * 100,
        boll_position=boll_position,
        support_level=103.8,
        resistance_level=resistance_level,
        support_distance_pct=support_distance_pct,
        resistance_distance_pct=resistance_distance_pct,
        support_strength=support_strength,
        resistance_strength=2.0,
        structure_risk_reward=risk_reward,
        pullback_from_high_pct=1.0,
        atr_pct=atr_pct,
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

    def test_btc_major_breakout_can_use_fixed_risk_budget_when_upside_is_open(self) -> None:
        decision = evaluate_long_entry(
            symbol="BTCUSDT",
            score=91.0,
            indicators=_indicators(
                support_distance_pct=6.0,
                support_strength=1.0,
                resistance_level=0.0,
                resistance_distance_pct=0.0,
                risk_reward=0.4,
            ),
            config=EntryRuleConfig(min_score=75.0, structure_filter_enabled=True),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.setup, "major_trend_breakout")
        self.assertIn("开放上行突破", " ".join(decision.reasons))

    def test_altcoin_cannot_bypass_distant_support_with_boll_breakout(self) -> None:
        decision = evaluate_long_entry(
            symbol="ALTUSDT",
            score=89.0,
            indicators=_indicators(
                support_distance_pct=6.0,
                support_strength=1.0,
                resistance_level=0.0,
                resistance_distance_pct=0.0,
                risk_reward=0.4,
            ),
            config=EntryRuleConfig(min_score=75.0, structure_filter_enabled=True),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "wait_support")

    def test_btc_does_not_fall_back_to_general_entry_below_breakout_score(self) -> None:
        decision = evaluate_long_entry(
            symbol="BTCUSDT",
            score=84.0,
            indicators=_indicators(),
            config=EntryRuleConfig(min_score=75.0),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "wait_score")

    def test_eth_pullback_uses_boll_and_ema_as_dynamic_support(self) -> None:
        decision = evaluate_long_entry(
            symbol="ETHUSDT",
            score=91.0,
            indicators=_indicators(
                support_distance_pct=6.0,
                support_strength=1.0,
                resistance_level=0.0,
                resistance_distance_pct=0.0,
                risk_reward=0.4,
                boll_mb=103.0,
                boll_up=108.0,
                boll_dn=98.0,
                boll_position=0.70,
            ),
            config=EntryRuleConfig(min_score=75.0, structure_filter_enabled=True),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.setup, "major_trend_pullback")
        self.assertIn("动态支撑", " ".join(decision.reasons))

    def test_eth_does_not_fall_back_to_general_entry_below_pullback_score(self) -> None:
        decision = evaluate_long_entry(
            symbol="ETHUSDT",
            score=89.0,
            indicators=_indicators(boll_position=0.70),
            config=EntryRuleConfig(min_score=75.0),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "wait_score")

    def test_eth_pullback_blocks_excessive_four_hour_atr(self) -> None:
        decision = evaluate_long_entry(
            symbol="ETHUSDT",
            score=91.0,
            indicators=_indicators(boll_position=0.70, atr_pct=2.2),
            config=EntryRuleConfig(min_score=75.0),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "wait_volatility")

    def test_major_breakout_still_requires_volume_confirmation(self) -> None:
        decision = evaluate_long_entry(
            symbol="BTCUSDT",
            score=91.0,
            indicators=_indicators(volume_ratio=0.8, resistance_level=0.0),
            config=EntryRuleConfig(min_score=75.0, structure_filter_enabled=True),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "wait_volume")

    def test_boll_upper_overextension_waits_for_pullback(self) -> None:
        decision = evaluate_long_entry(
            symbol="BTCUSDT",
            score=89.0,
            indicators=_indicators(boll_position=1.18, resistance_level=0.0),
            config=EntryRuleConfig(min_score=75.0, structure_filter_enabled=True),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "wait_pullback")
        self.assertIn("BOLL 上轨", " ".join(decision.reasons))


if __name__ == "__main__":
    unittest.main()
