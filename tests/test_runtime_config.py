from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from trade_signal_app.config import AppSettings, DEFAULT_X_TRACKED_ACCOUNTS
from trade_signal_app.runtime_config import SCAN_LIQUIDITY_RECOMMENDED_PROFILE, RuntimeConfig, RuntimeConfigStore, ScanDefaults


class RuntimeConfigTests(unittest.TestCase):
    def test_scan_defaults_use_defensive_balanced_liquidity_profile(self) -> None:
        defaults = ScanDefaults()

        for key, expected in SCAN_LIQUIDITY_RECOMMENDED_PROFILE.items():
            self.assertEqual(getattr(defaults, key), expected)
        self.assertLess(defaults.min_quote_volume, defaults.top30_min_quote_volume)
        self.assertGreaterEqual(defaults.min_trade_count, defaults.top30_min_trade_count)

    def test_default_from_settings_includes_curated_x_accounts(self) -> None:
        config = RuntimeConfig.default_from_settings(AppSettings())

        self.assertEqual(config.x_tracked_accounts, list(DEFAULT_X_TRACKED_ACCOUNTS))
        self.assertIn("lookonchain", config.x_tracked_accounts)
        self.assertIn("Grayscale", config.x_tracked_accounts)
        self.assertIn("Strategy", config.x_tracked_accounts)

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
            config.scan_defaults.btc_min_quote_volume = 123_000_000
            config.scan_defaults.top30_min_trade_count = 6789
            config.backtest_defaults.score_threshold = 74.5
            config.carry_paper_defaults.enabled = True
            config.carry_paper_defaults.min_basis_bps = 32.0
            store.save(config)

            loaded = store.load(settings)
            self.assertEqual(loaded.binance_api_key, "binance-key")
            self.assertEqual(loaded.x_bearer_token, "x-token")
            self.assertEqual(loaded.x_tracked_accounts, ["lookonchain", "wu_blockchain"])
            self.assertEqual(loaded.reddit_user_agent, "trade-signal-app/test")
            self.assertEqual(loaded.backtest_defaults.preset, "balanced_swing")
            self.assertEqual(loaded.scan_defaults.quote_asset, "FDUSD")
            self.assertEqual(loaded.scan_defaults.btc_min_quote_volume, 123_000_000)
            self.assertEqual(loaded.scan_defaults.top30_min_trade_count, 6789)
            self.assertEqual(loaded.backtest_defaults.score_threshold, 74.5)
            self.assertTrue(loaded.carry_paper_defaults.enabled)
            self.assertEqual(loaded.carry_paper_defaults.min_basis_bps, 32.0)

    def test_legacy_scan_thresholds_migrate_to_every_liquidity_tier(self) -> None:
        config = RuntimeConfig.from_dict(
            {
                "scan_defaults": {
                    "min_quote_volume": 12_000_000,
                    "min_trade_count": 4321,
                }
            },
            AppSettings(),
        )

        for tier in ("btc", "eth", "xrp", "sol", "bnb", "top30"):
            self.assertEqual(getattr(config.scan_defaults, f"{tier}_min_quote_volume"), 12_000_000)
            self.assertEqual(getattr(config.scan_defaults, f"{tier}_min_trade_count"), 4321)

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
        config.okx_api_key = "okx-key"
        config.okx_api_secret = "okx-secret"
        config.okx_api_passphrase = "okx-pass"
        config.x_bearer_token = "x-token"
        config.onchain_api_key = "onchain-key"
        config.llm_api_key = "llm-key"
        config.openai_api_key = "openai-key"
        config.feishu_webhook_url = "https://open.feishu.cn/webhook/test"
        config.intelligence_defaults.llm_api_key = "nested-llm-key"

        payload = config.to_template_payload()

        self.assertEqual(payload["kind"], "runtime_config_template")
        self.assertFalse(payload["include_secrets"])
        self.assertEqual(payload["config"]["binance_api_key"], "")
        self.assertEqual(payload["config"]["binance_api_secret"], "")
        self.assertEqual(payload["config"]["okx_api_key"], "")
        self.assertEqual(payload["config"]["okx_api_secret"], "")
        self.assertEqual(payload["config"]["okx_api_passphrase"], "")
        self.assertEqual(payload["config"]["x_bearer_token"], "")
        self.assertEqual(payload["config"]["onchain_api_key"], "")
        self.assertEqual(payload["config"]["llm_api_key"], "")
        self.assertEqual(payload["config"]["openai_api_key"], "")
        self.assertEqual(payload["config"]["feishu_webhook_url"], "")
        self.assertEqual(payload["config"]["intelligence_defaults"]["llm_api_key"], "")
        self.assertEqual(payload["config"]["intelligence_defaults"]["openai_api_key"], "")

    def test_template_import_preserves_current_secrets_when_missing(self) -> None:
        settings = AppSettings()
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.okx_api_key = "keep-okx-key"
        current.okx_api_secret = "keep-okx-secret"
        current.okx_api_passphrase = "keep-okx-pass"
        current.x_bearer_token = "keep-token"
        current.onchain_api_key = "keep-onchain"
        current.llm_api_key = "keep-llm"
        current.openai_api_key = "keep-openai"
        current.feishu_webhook_url = "https://open.feishu.cn/webhook/keep"

        imported = RuntimeConfig.from_template_payload(
            {
                "kind": "runtime_config_template",
                "version": 1,
                "config": {
                    "binance_api_key": "",
                    "binance_api_secret": "",
                    "okx_api_key": "",
                    "okx_api_secret": "",
                    "okx_api_passphrase": "",
                    "x_bearer_token": "",
                    "onchain_api_key": "",
                    "llm_api_key": "",
                    "openai_api_key": "",
                    "feishu_webhook_url": "",
                    "scan_defaults": {"quote_asset": "FDUSD"},
                },
            },
            settings,
            current_config=current,
        )

        self.assertEqual(imported.binance_api_key, "keep-key")
        self.assertEqual(imported.binance_api_secret, "keep-secret")
        self.assertEqual(imported.okx_api_key, "keep-okx-key")
        self.assertEqual(imported.okx_api_secret, "keep-okx-secret")
        self.assertEqual(imported.okx_api_passphrase, "keep-okx-pass")
        self.assertEqual(imported.x_bearer_token, "keep-token")
        self.assertEqual(imported.onchain_api_key, "keep-onchain")
        self.assertEqual(imported.llm_api_key, "keep-llm")
        self.assertEqual(imported.openai_api_key, "keep-openai")
        self.assertEqual(imported.feishu_webhook_url, "https://open.feishu.cn/webhook/keep")
        self.assertEqual(imported.scan_defaults.quote_asset, "FDUSD")


if __name__ == "__main__":
    unittest.main()
