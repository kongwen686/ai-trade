from __future__ import annotations

from pathlib import Path
import json
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
            config.reddit_user_agent = "trade-signal-app/test"
            config.backtest_defaults.preset = "balanced_swing"
            config.scan_defaults.quote_asset = "FDUSD"
            config.backtest_defaults.score_threshold = 74.5
            store.save(config)

            loaded = store.load(settings)
            self.assertEqual(loaded.binance_api_key, "binance-key")
            self.assertEqual(loaded.x_bearer_token, "x-token")
            self.assertEqual(loaded.x_tracked_accounts, ["lookonchain", "wu_blockchain"])
            self.assertEqual(loaded.reddit_user_agent, "trade-signal-app/test")
            self.assertEqual(loaded.backtest_defaults.preset, "balanced_swing")
            self.assertEqual(loaded.scan_defaults.quote_asset, "FDUSD")
            self.assertEqual(loaded.backtest_defaults.score_threshold, 74.5)

    def test_store_encrypts_when_passphrase_is_set(self) -> None:
        settings = AppSettings()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime_config.json"
            store = RuntimeConfigStore(path, passphrase="test-passphrase")
            config = RuntimeConfig.default_from_settings(settings)
            config.binance_api_key = "binance-key"
            store.save(config)

            raw_payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw_payload["kind"], "runtime_config_encrypted")
            self.assertNotIn("binance-key", path.read_text(encoding="utf-8"))

            loaded = store.load(settings)
            self.assertEqual(loaded.binance_api_key, "binance-key")

    def test_store_raises_clear_error_for_encrypted_file_without_passphrase(self) -> None:
        settings = AppSettings()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime_config.json"
            encrypted_store = RuntimeConfigStore(path, passphrase="test-passphrase")
            encrypted_store.save(RuntimeConfig.default_from_settings(settings))

            plain_store = RuntimeConfigStore(path)
            with self.assertRaisesRegex(ValueError, "RUNTIME_CONFIG_PASSPHRASE"):
                plain_store.load(settings)

    def test_template_export_redacts_secrets_by_default(self) -> None:
        config = RuntimeConfig()
        config.binance_api_key = "binance-key"
        config.binance_api_secret = "binance-secret"
        config.x_bearer_token = "x-token"

        payload = config.to_template_payload()

        self.assertEqual(payload["kind"], "runtime_config_template")
        self.assertFalse(payload["include_secrets"])
        self.assertEqual(payload["config"]["binance_api_key"], "")
        self.assertEqual(payload["config"]["binance_api_secret"], "")
        self.assertEqual(payload["config"]["x_bearer_token"], "")

    def test_template_import_preserves_current_secrets_when_missing(self) -> None:
        settings = AppSettings()
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.x_bearer_token = "keep-token"

        imported = RuntimeConfig.from_template_payload(
            {
                "kind": "runtime_config_template",
                "version": 1,
                "config": {
                    "binance_api_key": "",
                    "binance_api_secret": "",
                    "x_bearer_token": "",
                    "scan_defaults": {"quote_asset": "FDUSD"},
                },
            },
            settings,
            current_config=current,
        )

        self.assertEqual(imported.binance_api_key, "keep-key")
        self.assertEqual(imported.binance_api_secret, "keep-secret")
        self.assertEqual(imported.x_bearer_token, "keep-token")
        self.assertEqual(imported.scan_defaults.quote_asset, "FDUSD")


if __name__ == "__main__":
    unittest.main()
