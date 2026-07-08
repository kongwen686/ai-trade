from __future__ import annotations

from datetime import datetime, timezone
import unittest

from trade_signal_app.platform import build_platform_snapshot
from trade_signal_app.runtime_config import RuntimeConfig
from trade_signal_app.trading import TradingEvent, TradingPosition


class PlatformTests(unittest.TestCase):
    def test_platform_snapshot_describes_core_capabilities(self) -> None:
        config = RuntimeConfig()
        config.binance_api_key = "binance-key"
        config.binance_api_secret = "binance-secret"
        config.okx_api_key = "okx-key"
        config.okx_api_secret = "okx-secret"
        config.okx_api_passphrase = "okx-pass"
        config.openai_api_key = "openai-key"
        config.x_bearer_token = "x-token"
        config.autotrade_defaults.enabled = True
        config.autotrade_defaults.mode = "paper"
        config.autotrade_defaults.max_total_quote_exposure = 500.0

        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=0.01,
            entry_price=60_000.0,
            quote_notional=600.0,
            score=82.0,
            grade="A",
            opened_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
            stop_price=57_600.0,
            take_profit_price=65_400.0,
        )
        event = TradingEvent(
            action="SELL",
            symbol="BTCUSDT",
            mode="paper",
            status="paper_filled",
            message="paper sell",
            realized_pnl=24.0,
            realized_pnl_pct=4.0,
            exit_reason="take_profit",
        )

        snapshot = build_platform_snapshot(config=config, positions=[position], events=[event])

        component_names = {component.name for component in snapshot.components}
        components = {component.name: component for component in snapshot.components}
        strategy_ids = {strategy.strategy_id for strategy in snapshot.strategies}
        risk_rule_ids = {rule.rule_id for rule in snapshot.risk_rules}
        accounts = {account.exchange: account for account in snapshot.accounts}

        self.assertIn("Binance API", component_names)
        self.assertIn("OKX API", component_names)
        self.assertIn("Twitter/X", component_names)
        self.assertIn("OpenAI", component_names)
        self.assertIn("Execution Risk Gate", component_names)
        self.assertEqual(components["Binance API"].status, "configured")
        self.assertIn("auto_score_breakout", strategy_ids)
        self.assertIn("trend_following", strategy_ids)
        self.assertIn("range_breakout", strategy_ids)
        self.assertIn("momentum_rotation", strategy_ids)
        self.assertIn("spot_futures_basis", strategy_ids)
        self.assertIn("low_float_momentum_long", strategy_ids)
        self.assertIn("blowoff_distribution_short", strategy_ids)
        self.assertIn("capitulation_rebound_long", strategy_ids)
        self.assertIn("intel_gate", risk_rule_ids)
        self.assertIn("funding_rate_guard", risk_rule_ids)
        self.assertIn("structure_filter", risk_rule_ids)
        self.assertEqual(accounts["BINANCE"].status, "configured")
        self.assertEqual(accounts["BINANCE"].open_positions, 1)
        self.assertEqual(accounts["BINANCE"].quote_exposure, 600.0)
        self.assertEqual(accounts["BINANCE"].realized_pnl, 24.0)
        self.assertEqual(accounts["BINANCE"].total_trades, 1)
        self.assertEqual(accounts["BINANCE"].sell_trades, 1)
        self.assertEqual(accounts["BINANCE"].closed_trades, 1)
        self.assertEqual(accounts["BINANCE"].winning_trades, 1)
        self.assertEqual(accounts["BINANCE"].win_rate_pct, 100.0)
        self.assertEqual(accounts["BINANCE"].profit_loss_ratio, 999.0)
        self.assertEqual(accounts["BINANCE"].profit_factor, 999.0)
        self.assertEqual(accounts["OKX"].status, "configured")
        self.assertEqual(snapshot.recent_events, [event])

    def test_binance_component_distinguishes_public_data_from_private_auth(self) -> None:
        snapshot = build_platform_snapshot(config=RuntimeConfig(), positions=[], events=[])
        components = {component.name: component for component in snapshot.components}

        self.assertEqual(components["Binance API"].status, "ready_public")
        self.assertFalse(components["Binance API"].configured)

    def test_okx_component_reports_partial_credentials(self) -> None:
        config = RuntimeConfig()
        config.okx_api_key = "okx-key"
        config.okx_api_secret = "okx-secret"

        snapshot = build_platform_snapshot(config=config, positions=[], events=[])
        components = {component.name: component for component in snapshot.components}
        accounts = {account.exchange: account for account in snapshot.accounts}

        self.assertEqual(components["OKX API"].status, "partial_configured")
        self.assertTrue(components["OKX API"].configured)
        self.assertIn("Passphrase", components["OKX API"].capability)
        self.assertEqual(accounts["OKX"].status, "partial_configured")

    def test_recent_events_are_newest_first(self) -> None:
        older = TradingEvent(
            action="BUY",
            symbol="BTCUSDT",
            mode="paper",
            status="paper_filled",
            message="older",
            created_at=datetime(2026, 4, 28, 1, tzinfo=timezone.utc),
        )
        newer = TradingEvent(
            action="SELL",
            symbol="ETHUSDT",
            mode="paper",
            status="paper_filled",
            message="newer",
            created_at=datetime(2026, 4, 28, 2, tzinfo=timezone.utc),
        )

        snapshot = build_platform_snapshot(config=RuntimeConfig(), positions=[], events=[older, newer])

        self.assertEqual([event.message for event in snapshot.recent_events], ["newer", "older"])


if __name__ == "__main__":
    unittest.main()
