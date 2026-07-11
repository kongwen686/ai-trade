from __future__ import annotations

import unittest

from trade_signal_app.presets import (
    BACKTEST_PRESETS,
    STRATEGY_TEMPLATES,
    apply_backtest_preset,
    backtest_preset_ids,
    list_backtest_presets,
    list_strategy_templates,
)


class PresetRegistryTests(unittest.TestCase):
    def test_preset_and_template_ids_are_unique(self) -> None:
        preset_ids = [preset.preset_id for preset in BACKTEST_PRESETS]
        template_ids = [template.template_id for template in STRATEGY_TEMPLATES]

        self.assertEqual(len(preset_ids), len(set(preset_ids)))
        self.assertEqual(len(template_ids), len(set(template_ids)))

    def test_every_template_references_an_existing_preset_and_is_paper_only(self) -> None:
        preset_ids = backtest_preset_ids()

        for template in STRATEGY_TEMPLATES:
            self.assertIn(template.preset_id, preset_ids)
            self.assertTrue(template.paper_only)

    def test_conservative_pullback_preset_applies_complete_risk_filters(self) -> None:
        params = apply_backtest_preset({}, "trend_pullback_conservative")

        self.assertEqual(params["preset"], "trend_pullback_conservative")
        self.assertEqual(params["max_concurrent_positions"], 1)
        self.assertTrue(params["volatility_filter_enabled"])
        self.assertTrue(params["block_extreme_volatility"])
        self.assertEqual(params["max_entry_volatility_ratio"], 1.55)

    def test_public_registry_payload_exposes_selection_metadata(self) -> None:
        presets = list_backtest_presets()
        templates = list_strategy_templates()

        self.assertTrue(all("risk_level" in item for item in presets))
        self.assertTrue(all("recommended_intervals" in item for item in presets))
        self.assertTrue(all("market_regimes" in item for item in templates))
        self.assertTrue(all(item["paper_only"] for item in templates))


if __name__ == "__main__":
    unittest.main()
