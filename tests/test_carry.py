from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import trade_signal_app.main as app_main
from trade_signal_app.carry import (
    build_carry_market_snapshots,
    run_carry_paper_cycle,
)
from trade_signal_app.runtime_config import CarryPaperDefaults
from trade_signal_app.time_utils import APP_TIMEZONE


class CarryPaperEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.started_at = datetime(2026, 7, 11, 8, 0, tzinfo=APP_TIMEZONE)
        self.config = CarryPaperDefaults(
            enabled=True,
            notional_per_leg=100.0,
            min_basis_bps=25.0,
            min_funding_bps=1.0,
            exit_basis_bps=10.0,
            exit_funding_bps=0.0,
            stop_basis_bps=35.0,
            max_holding_hours=168,
            max_positions=2,
            fee_bps_per_leg=0.0,
            slippage_bps_per_leg=0.0,
        )

    def _snapshots(
        self,
        *,
        observed_at: datetime,
        spot_price: float = 100.0,
        futures_price: float = 101.0,
        spread_bps: float = 100.0,
        funding_bps: float = 10.0,
    ):
        return build_carry_market_snapshots(
            [
                {
                    "symbol": "BTCUSDT",
                    "spot_exchange": "BINANCE",
                    "futures_exchange": "BINANCE-PERP",
                    "spot_price": spot_price,
                    "futures_price": futures_price,
                    "spread_bps": spread_bps,
                }
            ],
            [
                {
                    "symbol": "BTCUSDT",
                    "futures_exchange": "BINANCE-PERP",
                    "funding_rate_bps": funding_bps,
                }
            ],
            observed_at=observed_at,
        )

    def test_merges_basis_and_funding_market_rows(self) -> None:
        snapshots = self._snapshots(observed_at=self.started_at)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].symbol, "BTCUSDT")
        self.assertEqual(snapshots[0].basis_bps, 100.0)
        self.assertEqual(snapshots[0].funding_rate_bps, 10.0)

    def test_opens_long_spot_and_short_perpetual_paper_position(self) -> None:
        report = run_carry_paper_cycle(
            snapshots=self._snapshots(observed_at=self.started_at),
            positions=[],
            config=self.config,
        )

        self.assertTrue(report.research_only)
        self.assertEqual(report.mode, "paper")
        self.assertEqual(report.opened_count, 1)
        self.assertEqual(report.events[0].status, "paper_opened")
        position = report.positions[0]
        self.assertAlmostEqual(position.spot_quantity, 1.0)
        self.assertAlmostEqual(position.futures_quantity, 100 / 101)

    def test_closes_on_basis_convergence_and_counts_funding_income(self) -> None:
        opened = run_carry_paper_cycle(
            snapshots=self._snapshots(observed_at=self.started_at),
            positions=[],
            config=self.config,
        ).positions
        closed = run_carry_paper_cycle(
            snapshots=self._snapshots(
                observed_at=self.started_at + timedelta(hours=8),
                spot_price=102.0,
                futures_price=102.08,
                spread_bps=7.84,
                funding_bps=10.0,
            ),
            positions=opened,
            config=self.config,
        )

        self.assertEqual(closed.closed_count, 1)
        self.assertEqual(closed.positions, [])
        event = closed.events[0]
        self.assertEqual(event.exit_reason, "basis_converged")
        self.assertGreater(event.funding_pnl, 0)
        self.assertGreater(event.realized_pnl, 0)

    def test_disabled_entries_still_manage_existing_position(self) -> None:
        opened = run_carry_paper_cycle(
            snapshots=self._snapshots(observed_at=self.started_at),
            positions=[],
            config=self.config,
        ).positions
        disabled = replace(self.config, enabled=False)
        report = run_carry_paper_cycle(
            snapshots=self._snapshots(
                observed_at=self.started_at + timedelta(hours=8),
                spread_bps=5.0,
            ),
            positions=opened,
            config=disabled,
        )

        self.assertFalse(report.enabled)
        self.assertEqual(report.closed_count, 1)
        self.assertEqual(report.opened_count, 0)

    def test_stops_when_basis_expands_adversely(self) -> None:
        opened = run_carry_paper_cycle(
            snapshots=self._snapshots(observed_at=self.started_at),
            positions=[],
            config=self.config,
        ).positions
        report = run_carry_paper_cycle(
            snapshots=self._snapshots(
                observed_at=self.started_at + timedelta(hours=1),
                futures_price=102.0,
                spread_bps=140.0,
            ),
            positions=opened,
            config=self.config,
        )

        self.assertEqual(report.events[0].exit_reason, "basis_stop")
        self.assertEqual(report.opened_count, 0)
        self.assertEqual(report.positions, [])

    def test_main_cycle_never_calls_exchange_order_gateway(self) -> None:
        config = replace(app_main.RuntimeConfig(), carry_paper_defaults=self.config)
        gateway = Mock()
        scanner = SimpleNamespace(gateway=gateway)
        market_sections = {
            "spreads": [
                {
                    "symbol": "BTCUSDT",
                    "spot_price": 100.0,
                    "futures_price": 101.0,
                    "spread_bps": 100.0,
                }
            ],
            "funding_rates": [{"symbol": "BTCUSDT", "funding_rate_bps": 10.0}],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "trade_signal_app.main.APP_STATE.snapshot",
            return_value=(config, scanner),
        ), patch(
            "trade_signal_app.main.LOCAL_DATABASE_PATH",
            Path(temp_dir) / "ai_trade.sqlite3",
        ):
            payload = app_main._run_carry_paper_once(
                market_sections=market_sections,
                observed_at=self.started_at,
            )
            repeated = app_main._run_carry_paper_once(
                market_sections=market_sections,
                observed_at=self.started_at,
            )

        self.assertEqual(payload["opened_count"], 1)
        self.assertEqual(repeated["opened_count"], 0)
        self.assertEqual(repeated["status"]["metrics"]["open_positions"], 1)
        gateway.market_buy.assert_not_called()
        gateway.market_sell.assert_not_called()
        gateway.create_order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
