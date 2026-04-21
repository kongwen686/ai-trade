from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from trade_signal_app.config import AppSettings
from trade_signal_app.runtime_config import RuntimeConfig, RuntimeConfigStore


class RuntimeConfigTests(unittest.TestCase):
    def test_store_round_trip(self) -> None:
        settings = AppSettings()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime_config.json"
            store = RuntimeConfigStore(path)
            config = RuntimeConfig.default_from_settings(settings)
            config.binance_api_key = "binance-key"
            config.x_bearer_token = "x-token"
            config.x_tracked_accounts = ["lookonchain", "wu_blockchain"]
            config.scan_defaults.quote_asset = "FDUSD"
            config.backtest_defaults.score_threshold = 74.5
            store.save(config)

            loaded = store.load(settings)
            self.assertEqual(loaded.binance_api_key, "binance-key")
            self.assertEqual(loaded.x_bearer_token, "x-token")
            self.assertEqual(loaded.x_tracked_accounts, ["lookonchain", "wu_blockchain"])
            self.assertEqual(loaded.scan_defaults.quote_asset, "FDUSD")
            self.assertEqual(loaded.backtest_defaults.score_threshold, 74.5)


if __name__ == "__main__":
    unittest.main()
