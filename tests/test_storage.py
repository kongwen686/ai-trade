from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from trade_signal_app.storage import LocalDataStore


class LocalDataStoreTests(unittest.TestCase):
    def test_concurrent_initialization_is_serialized_and_uses_wal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ai_trade.sqlite3"
            with ThreadPoolExecutor(max_workers=12) as executor:
                statuses = list(executor.map(lambda _: LocalDataStore(path).status(), range(24)))
            with LocalDataStore(path)._connect() as connection:
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertTrue(all(status["schema_version"] == 3 for status in statuses))
        self.assertEqual(journal_mode.lower(), "wal")
        self.assertEqual(busy_timeout, 10_000)

    def test_records_backtest_runs_and_metric_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalDataStore(Path(temp_dir) / "ai_trade.sqlite3")
            run_uid = store.record_backtest_run(
                params={"preset": "balanced_swing"},
                payload={
                    "series_reports": [
                        {"symbol": "BTCUSDT", "interval": "4h", "signal_count": 3, "final_equity": 1.08}
                    ],
                    "portfolio_reports": [],
                    "rebalance_reports": [],
                },
                error=None,
            )
            store.record_metric_snapshot("paper_account", {"total_trades": 3})
            store.record_notification_delivery(
                notification_key="feishu_daily_summary:2026-07-10",
                channel="feishu_daily_summary",
                report_date="2026-07-10",
                status="failed",
                error="temporary network error",
            )
            delivery = store.record_notification_delivery(
                notification_key="feishu_daily_summary:2026-07-10",
                channel="feishu_daily_summary",
                report_date="2026-07-10",
                status="sent",
                metadata={"today_trades": 3},
            )
            store.replace_carry_paper_positions(
                [
                    {
                        "position_id": "carry-paper-btc-1",
                        "symbol": "BTCUSDT",
                        "opened_at": "2026-07-11T08:00:00+08:00",
                    }
                ]
            )
            store.append_carry_paper_events(
                [
                    {
                        "position_id": "carry-paper-btc-1",
                        "action": "OPEN",
                        "symbol": "BTCUSDT",
                        "status": "paper_opened",
                        "created_at": "2026-07-11T08:00:00+08:00",
                    }
                ]
            )
            research_uid = store.record_research_backtest_run(
                strategy="pair_stat_arb",
                params={"symbols": ["BTCUSDT", "ETHUSDT"]},
                payload={"trade_count": 4},
            )
            carry_positions = store.load_carry_paper_position_payloads()
            carry_events = store.load_carry_paper_event_payloads()
            status = store.status()

        self.assertEqual(len(run_uid), 64)
        self.assertEqual(status["backtest_runs"], 1)
        self.assertEqual(status["metric_snapshots"], 1)
        self.assertEqual(status["notification_deliveries"], 1)
        self.assertEqual(status["carry_paper_positions"], 1)
        self.assertEqual(status["carry_paper_events"], 1)
        self.assertEqual(status["research_backtest_runs"], 1)
        self.assertEqual(len(research_uid), 64)
        self.assertEqual(carry_positions[0]["symbol"], "BTCUSDT")
        self.assertEqual(carry_events[0]["action"], "OPEN")
        self.assertEqual(delivery["status"], "sent")
        self.assertEqual(delivery["attempt_count"], 2)
        self.assertEqual(delivery["metadata"], {"today_trades": 3})
        self.assertTrue(delivery["sent_at"])


if __name__ == "__main__":
    unittest.main()
