from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from trade_signal_app.main import _backtest_payload, _build_runtime_config, _split_archives
from trade_signal_app.runtime_config import RuntimeConfig
from trade_signal_app.views import render_backtest_page, render_settings_page


def _build_archive(path: Path) -> None:
    rows: list[str] = []
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    for index in range(180):
        if index < 50:
            price += 0.25
        elif index < 130:
            price += 0.85 if index % 8 != 0 else -0.12
        else:
            price += 0.45
        volume = 1000 + (index * 18)
        if index % 6 == 0:
            volume *= 1.35
        taker_ratio = 0.58 if index % 9 else 0.68
        open_time = start + timedelta(hours=4 * index)
        close_time = open_time + timedelta(hours=4) - timedelta(milliseconds=1)
        rows.append(
            ",".join(
                [
                    str(int(open_time.timestamp() * 1000)),
                    f"{price - 0.55:.4f}",
                    f"{price + 1.10:.4f}",
                    f"{price - 0.95:.4f}",
                    f"{price:.4f}",
                    f"{volume:.4f}",
                    str(int(close_time.timestamp() * 1000)),
                    f"{volume * price:.4f}",
                    str(150 + index * 4),
                    f"{volume * taker_ratio:.4f}",
                    f"{volume * price * taker_ratio:.4f}",
                    "0",
                ]
            )
        )

    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr(path.with_suffix(".csv").name, "\n".join(rows))


class MainTests(unittest.TestCase):
    def test_split_archives_supports_commas_and_lines(self) -> None:
        self.assertEqual(
            _split_archives("data/a.zip, data/b.zip\n\ndata/c.zip"),
            ["data/a.zip", "data/b.zip", "data/c.zip"],
        )

    def test_backtest_payload_runs_with_web_only_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)
            payload, params, error = _backtest_payload(
                {
                    "archives": [str(archive)],
                    "lookback_bars": ["120"],
                    "score_threshold": ["60"],
                    "holding_periods": ["3,6"],
                    "portfolio_top_n": ["1"],
                    "cooldown_bars": ["4"],
                    "stop_loss_pct": ["4"],
                    "take_profit_pct": ["9"],
                    "max_holding_bars": ["12"],
                    "fee_bps": ["8"],
                    "fee_model": ["maker_taker"],
                    "fee_source": ["manual"],
                    "maker_fee_bps": ["6"],
                    "taker_fee_bps": ["10"],
                    "entry_fee_role": ["taker"],
                    "exit_fee_role": ["maker"],
                    "fee_discount_pct": ["20"],
                    "no_binance_discount": ["1"],
                    "slippage_bps": ["4"],
                    "slippage_model": ["dynamic"],
                    "min_slippage_bps": ["1.5"],
                    "max_slippage_bps": ["18"],
                    "slippage_window_bars": ["12"],
                    "capital_fraction_pct": ["70"],
                    "max_portfolio_exposure_pct": ["80"],
                    "max_concurrent_positions": ["1"],
                    "min_volume_ratio": ["1.0"],
                    "min_buy_pressure": ["0.5"],
                    "min_rsi": ["40"],
                    "max_rsi": ["99"],
                    "no_kdj_confirmation": ["1"],
                }
            )

        self.assertIsNone(error)
        self.assertEqual(params["lookback_bars"], 120)
        self.assertEqual(params["cooldown_bars"], 4)
        self.assertEqual(params["fee_model"], "maker_taker")
        self.assertEqual(params["fee_source"], "manual")
        self.assertEqual(params["maker_fee_bps"], 6.0)
        self.assertEqual(params["taker_fee_bps"], 10.0)
        self.assertEqual(params["entry_fee_role"], "taker")
        self.assertEqual(params["exit_fee_role"], "maker")
        self.assertEqual(params["fee_discount_pct"], 20.0)
        self.assertTrue(params["no_binance_discount"])
        self.assertEqual(params["min_rsi"], 40.0)
        self.assertEqual(params["min_slippage_bps"], 1.5)
        self.assertEqual(params["max_slippage_bps"], 18.0)
        self.assertEqual(params["slippage_window_bars"], 12)
        self.assertEqual(len(payload["series_reports"]), 1)
        self.assertEqual(len(payload["portfolio_reports"]), 1)
        self.assertGreater(payload["series_reports"][0]["signal_count"], 0)
        self.assertEqual(payload["portfolio_reports"][0]["top_n"], 1)

    def test_render_backtest_page_includes_extended_controls(self) -> None:
        params = {
            "archives": "data/spot/monthly/klines/*/4h/*.zip",
            "lookback_bars": 240,
            "score_threshold": 70.0,
            "holding_periods": "3,6,12",
            "portfolio_top_n": 2,
            "cooldown_bars": 0,
            "stop_loss_pct": 4.0,
            "take_profit_pct": 9.0,
            "max_holding_bars": 12,
            "fee_bps": 10.0,
            "fee_model": "maker_taker",
            "fee_source": "manual",
            "maker_fee_bps": 6.0,
            "taker_fee_bps": 10.0,
            "entry_fee_role": "taker",
            "exit_fee_role": "maker",
            "fee_discount_pct": 20.0,
            "no_binance_discount": True,
            "slippage_bps": 5.0,
            "slippage_model": "dynamic",
            "min_slippage_bps": 2.0,
            "max_slippage_bps": 25.0,
            "slippage_window_bars": 20,
            "capital_fraction_pct": 100.0,
            "max_portfolio_exposure_pct": 100.0,
            "max_concurrent_positions": 0,
            "min_volume_ratio": 1.1,
            "min_buy_pressure": 0.52,
            "min_rsi": 45.0,
            "max_rsi": 72.0,
            "no_kdj_confirmation": False,
        }
        html = render_backtest_page(params=params, series_reports=[], portfolio_reports=[], error=None)

        self.assertIn("Lookback Bars", html)
        self.assertIn("Cooldown Bars", html)
        self.assertIn("Min Slippage", html)
        self.assertIn("Max Slippage", html)
        self.assertIn("Slip Window", html)
        self.assertIn("Min RSI", html)
        self.assertIn("Fee Model", html)
        self.assertIn("Fee Source", html)
        self.assertIn("Maker Fee bps", html)
        self.assertIn("Entry Fee Role", html)

    def test_render_settings_page_includes_runtime_controls(self) -> None:
        html = render_settings_page(
            params={
                "binance_recv_window_ms": 5000.0,
                "community_provider": "x",
                "x_api_base_url": "https://api.x.com",
                "x_recent_window_hours": 24,
                "x_recent_max_results": 25,
                "x_language": "en",
                "x_account_mode": "blend",
                "x_account_weight_pct": 35.0,
                "x_tracked_accounts": ["lookonchain", "wu_blockchain"],
                "scan_quote_asset": "USDT",
                "scan_interval": "4h",
                "scan_candidate_pool": 18,
                "scan_min_quote_volume": 10_000_000,
                "scan_min_trade_count": 3000,
                "backtest_archives": "data/spot/monthly/klines/*/4h/*.zip",
                "backtest_lookback_bars": 240,
                "backtest_score_threshold": 70.0,
                "backtest_holding_periods": "3,6,12",
                "backtest_portfolio_top_n": 2,
                "backtest_cooldown_bars": 0,
                "backtest_stop_loss_pct": 4.0,
                "backtest_take_profit_pct": 9.0,
                "backtest_max_holding_bars": 12,
                "backtest_fee_bps": 10.0,
                "backtest_fee_model": "maker_taker",
                "backtest_fee_source": "symbol",
                "backtest_maker_fee_bps": 6.0,
                "backtest_taker_fee_bps": 10.0,
                "backtest_entry_fee_role": "taker",
                "backtest_exit_fee_role": "maker",
                "backtest_fee_discount_pct": 20.0,
                "backtest_no_binance_discount": False,
                "backtest_slippage_bps": 5.0,
                "backtest_slippage_model": "dynamic",
                "backtest_min_slippage_bps": 2.0,
                "backtest_max_slippage_bps": 25.0,
                "backtest_slippage_window_bars": 20,
                "backtest_capital_fraction_pct": 100.0,
                "backtest_max_portfolio_exposure_pct": 100.0,
                "backtest_max_concurrent_positions": 0,
                "backtest_min_volume_ratio": 1.1,
                "backtest_min_buy_pressure": 0.52,
                "backtest_min_rsi": 45.0,
                "backtest_max_rsi": 72.0,
                "backtest_no_kdj_confirmation": False,
            },
            status={
                "binance_auth_configured": True,
                "binance_auth_label": "API key + secret 已配置",
                "x_auth_configured": True,
                "tracked_account_count": 2,
            },
            message="运行配置已保存。",
            error=None,
        )

        self.assertIn("Runtime Settings", html)
        self.assertIn("Binance API Key", html)
        self.assertIn("Twitter Intel", html)
        self.assertIn("Tracked Accounts", html)
        self.assertIn("Backtest Defaults", html)
        self.assertIn("运行配置已保存", html)

    def test_build_runtime_config_parses_runtime_form(self) -> None:
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.x_bearer_token = "keep-x-token"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            config = _build_runtime_config(
                {
                    "binance_recv_window_ms": ["6000"],
                    "community_provider": ["x"],
                    "x_api_base_url": ["https://api.x.com"],
                    "x_recent_window_hours": ["12"],
                    "x_recent_max_results": ["20"],
                    "x_language": ["en"],
                    "x_account_mode": ["blend"],
                    "x_account_weight_pct": ["40"],
                    "x_tracked_accounts": ["@lookonchain\nwu_blockchain"],
                    "scan_quote_asset": ["FDUSD"],
                    "scan_interval": ["1h"],
                    "scan_candidate_pool": ["12"],
                    "scan_min_quote_volume": ["2000000"],
                    "scan_min_trade_count": ["800"],
                    "backtest_archives": ["/tmp/example.zip"],
                    "backtest_lookback_bars": ["120"],
                    "backtest_score_threshold": ["66"],
                    "backtest_holding_periods": ["3,6"],
                    "backtest_portfolio_top_n": ["1"],
                    "backtest_cooldown_bars": ["2"],
                    "backtest_stop_loss_pct": ["3.5"],
                    "backtest_take_profit_pct": ["8.5"],
                    "backtest_max_holding_bars": ["10"],
                    "backtest_fee_source": ["account"],
                    "backtest_fee_model": ["maker_taker"],
                    "backtest_fee_bps": ["8"],
                    "backtest_maker_fee_bps": ["5"],
                    "backtest_taker_fee_bps": ["9"],
                    "backtest_entry_fee_role": ["taker"],
                    "backtest_exit_fee_role": ["maker"],
                    "backtest_fee_discount_pct": ["20"],
                    "backtest_no_binance_discount": ["on"],
                    "backtest_slippage_bps": ["4"],
                    "backtest_slippage_model": ["dynamic"],
                    "backtest_min_slippage_bps": ["1.5"],
                    "backtest_max_slippage_bps": ["18"],
                    "backtest_slippage_window_bars": ["12"],
                    "backtest_capital_fraction_pct": ["60"],
                    "backtest_max_portfolio_exposure_pct": ["75"],
                    "backtest_max_concurrent_positions": ["2"],
                    "backtest_min_volume_ratio": ["1.02"],
                    "backtest_min_buy_pressure": ["0.55"],
                    "backtest_min_rsi": ["41"],
                    "backtest_max_rsi": ["77"],
                    "backtest_no_kdj_confirmation": ["on"],
                }
            )

        self.assertEqual(config.binance_api_key, "keep-key")
        self.assertEqual(config.binance_api_secret, "keep-secret")
        self.assertEqual(config.x_bearer_token, "keep-x-token")
        self.assertEqual(config.x_account_mode, "blend")
        self.assertEqual(config.x_tracked_accounts, ["@lookonchain", "wu_blockchain"])
        self.assertEqual(config.scan_defaults.quote_asset, "FDUSD")
        self.assertEqual(config.backtest_defaults.fee_source, "account")
        self.assertTrue(config.backtest_defaults.no_binance_discount)
        self.assertTrue(config.backtest_defaults.no_kdj_confirmation)

    def test_backtest_payload_returns_error_for_binance_fee_resolution_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)
            with patch(
                "trade_signal_app.main.resolve_execution_config_from_binance",
                side_effect=ValueError("Binance SIGNED 接口请求失败：HTTP 401"),
            ):
                payload, _, error = _backtest_payload(
                    {
                        "archives": [str(archive)],
                        "fee_source": ["account"],
                    }
                )

        self.assertEqual(payload["series_reports"], [])
        self.assertEqual(payload["portfolio_reports"], [])
        self.assertEqual(error, "Binance SIGNED 接口请求失败：HTTP 401")


if __name__ == "__main__":
    unittest.main()
