from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from trade_signal_app.storage import LocalDataStore


class LocalDataStoreTests(unittest.TestCase):
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
            status = store.status()

        self.assertEqual(len(run_uid), 64)
        self.assertEqual(status["backtest_runs"], 1)
        self.assertEqual(status["metric_snapshots"], 1)


if __name__ == "__main__":
    unittest.main()
