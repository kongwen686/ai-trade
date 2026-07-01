from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
import zipfile

from trade_signal_app import __version__
from trade_signal_app.main import (
    _backtest_payload,
    _backtest_export_csv,
    _build_runtime_config,
    _compile_strategy_payload,
    _export_runtime_config_template,
    _health_payload,
    _import_runtime_config_template,
    _run_trading_once,
    _scan_payload,
    _terminal_module_payload,
    _trading_readiness_payload,
    _split_archives,
    main,
    parse_args,
    run,
)
from trade_signal_app.onchain import OnchainMonitorEvent
from trade_signal_app.presets import list_backtest_presets
from trade_signal_app.runtime_config import RuntimeConfig
from trade_signal_app.trading import TradingStateStore
from trade_signal_app.views import (
    render_backtest_page,
    render_index_page,
    render_settings_page,
    render_terminal_module_page,
    render_terminal_page,
    render_trading_page,
)


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
    def test_parse_args_supports_host_and_port(self) -> None:
        args = parse_args(["--host", "0.0.0.0", "--port", "9000"])

        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9000)

    def test_parse_args_supports_version(self) -> None:
        buffer = io.StringIO()
        with self.assertRaises(SystemExit) as exc, redirect_stdout(buffer):
            parse_args(["--version"])

        self.assertEqual(exc.exception.code, 0)
        self.assertIn(__version__, buffer.getvalue())

    def test_main_runs_server_with_cli_arguments(self) -> None:
        server = Mock()
        with patch("trade_signal_app.main.ThreadingHTTPServer", return_value=server) as server_factory:
            main(["--host", "0.0.0.0", "--port", "9000"])

        server_factory.assert_called_once()
        self.assertEqual(server_factory.call_args.args[0], ("0.0.0.0", 9000))
        self.assertEqual(server_factory.call_args.args[1].__name__, "RequestHandler")
        server.serve_forever.assert_called_once_with()

    def test_run_uses_explicit_host_and_port_over_defaults(self) -> None:
        server = Mock()
        with patch("trade_signal_app.main.ThreadingHTTPServer", return_value=server) as server_factory:
            run(host="127.0.0.2", port=8100)

        self.assertEqual(server_factory.call_args.args[0], ("127.0.0.2", 8100))
        server.serve_forever.assert_called_once_with()

    def test_split_archives_supports_commas_and_lines(self) -> None:
        self.assertEqual(
            _split_archives("data/a.zip, data/b.zip\n\ndata/c.zip"),
            ["data/a.zip", "data/b.zip", "data/c.zip"],
        )

    def test_health_payload_is_local_and_reports_live_blockers(self) -> None:
        config = RuntimeConfig()
        config.autotrade_defaults.mode = "live"
        config.autotrade_defaults.order_test_only = False
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, object())),
            patch("trade_signal_app.main.APP_STATE.storage_mode_label", return_value="Plain JSON"),
            patch("trade_signal_app.main.TradingStateStore.load", return_value=[]),
            patch("trade_signal_app.main.TradingStateStore.load_events", return_value=[]),
            patch.dict("os.environ", {}, clear=True),
        ):
            payload = _health_payload()

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["external_checks"]["performed"])
        self.assertIn("Binance API key/secret 未配置", payload["autotrade"]["local_blockers"])
        self.assertIn("AI_TRADE_LIVE_CONFIRM", payload["autotrade"]["local_blockers"][1])

    def test_trading_readiness_skips_account_check_for_paper_status(self) -> None:
        config = RuntimeConfig()
        config.binance_api_key = "key"
        config.binance_api_secret = "secret"
        gateway = Mock()
        gateway.account_status.side_effect = AssertionError("account check should not run")
        scanner = SimpleNamespace(gateway=gateway)
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)):
            payload = _trading_readiness_payload()

        self.assertFalse(payload["account_check_performed"])
        self.assertEqual(payload["exchange_status"]["status"], "unchecked")

    def test_trading_readiness_can_force_account_check(self) -> None:
        config = RuntimeConfig()
        config.binance_api_key = "key"
        config.binance_api_secret = "secret"
        gateway = Mock()
        gateway.account_status.return_value = {
            "configured": True,
            "authenticated": True,
            "can_trade": True,
            "quote_available": 100.0,
            "status": "ready",
        }
        scanner = SimpleNamespace(gateway=gateway)
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)):
            payload = _trading_readiness_payload(check_account=True)

        self.assertTrue(payload["account_check_performed"])
        gateway.account_status.assert_called_once_with({"USDT"})

    def test_scan_payload_rejects_invalid_query_parameters(self) -> None:
        scanner = Mock()
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), scanner)):
            with self.assertRaisesRegex(ValueError, "Candidate Pool"):
                _scan_payload({"candidate_pool": ["many"]})

        scanner.scan.assert_not_called()

    def test_scan_payload_preserves_table_view_mode(self) -> None:
        scanner = Mock()
        scanner.scan.return_value = (
            {"scanned_symbols": 0, "returned_signals": 0, "quote_asset": "USDT", "interval": "4h", "min_quote_volume": 0},
            [],
        )
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), scanner)):
            _, params = _scan_payload({"view_mode": ["table"]})

        self.assertEqual(params["view_mode"], "table")

    def test_render_index_page_supports_table_view_mode(self) -> None:
        html = render_index_page(
            summary={
                "scanned_symbols": 12,
                "returned_signals": 1,
                "quote_asset": "USDT",
                "interval": "4h",
                "min_quote_volume": 1_000_000,
            },
            signals=[
                {
                    "symbol": "BTCUSDT",
                    "grade": "A",
                    "score": 82.5,
                    "reasons": ["趋势向上", "量能放大"],
                    "warnings": ["追高风险"],
                    "quote_volume_m": 1200.0,
                    "price_change_percent": 2.4,
                    "rsi_14": 58.2,
                    "ema_spread_pct": 1.3,
                    "volume_ratio": 1.8,
                    "macd_hist": 0.0234,
                    "community_score": 76,
                    "community_source": "local",
                    "breakdown": {"trend": 80, "momentum": 75, "volume": 70},
                    "sparkline_points": "0,20 80,10 160,4",
                }
            ],
            params={
                "quote_asset": "USDT",
                "interval": "4h",
                "candidate_pool": 5,
                "min_quote_volume": 1_000_000,
                "min_trade_count": 100,
                "view_mode": "table",
            },
            intervals=["4h"],
        )

        self.assertIn("展示模式", html)
        self.assertIn("signal-table", html)
        self.assertIn("BTCUSDT", html)
        self.assertIn("view_mode=cards", html)

    def test_backtest_payload_rejects_invalid_query_parameters(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)):
            with self.assertRaisesRegex(ValueError, "Lookback Bars"):
                _backtest_payload({"lookback_bars": ["soon"]})

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
        self.assertGreater(payload["series_reports"][0]["buy_hold_final_equity"], 1.0)
        self.assertEqual(payload["portfolio_reports"][0]["top_n"], 1)

    def test_render_backtest_page_includes_extended_controls(self) -> None:
        params = {
            "archives": "data/spot/monthly/klines/*/4h/*.zip",
            "preset": "balanced_swing",
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
        html = render_backtest_page(
            params=params,
            series_reports=[],
            portfolio_reports=[],
            error=None,
            presets=list_backtest_presets(),
            strategy_explanation={
                "strategy_type": "balanced_swing",
                "summary": "均衡波段模板，在趋势、动量、量能和买压之间取折中。",
                "sample": {"series_count": 0, "series_trades": 0},
                "best": {"series": None, "portfolio": None},
                "diagnostics": ["尚未产生单币种回测结果；需要先提供本地历史 K 线 ZIP。"],
                "notes": ["成本假设：fee_model=maker_taker, fee_source=manual, slippage_model=dynamic。"],
            },
        )

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
        self.assertIn("基准测试", html)
        self.assertIn("Series Equity Rank", html)
        self.assertIn("策略解释", html)
        self.assertIn("稳定性检查", html)
        self.assertIn("均衡波段模板", html)
        self.assertIn("Stability Checks", html)
        self.assertIn("/api/backtest/export?format=csv", html)
        self.assertIn("Balanced Swing", html)
        self.assertIn("/api/backtest/presets", html)

    def test_render_settings_page_includes_runtime_controls(self) -> None:
        html = render_settings_page(
            params={
                "binance_recv_window_ms": 5000.0,
                "market_data_preset": "binance_public",
                "onchain_data_preset": "defillama_free",
                "onchain_api_base_url": "",
                "community_provider": "x",
                "x_provider": "official_api",
                "x_api_base_url": "https://api.x.com",
                "x_nitter_base_url": "",
                "x_session_command": "",
                "x_recent_window_hours": 24,
                "x_recent_max_results": 25,
                "x_language": "en",
                "reddit_api_base_url": "https://www.reddit.com",
                "reddit_recent_window_hours": 24,
                "reddit_max_results": 25,
                "reddit_user_agent": "trade-signal-app/0.2",
                "llm_provider": "openai",
                "llm_base_url": "",
                "llm_model": "gpt-5.5",
                "openai_model": "gpt-5.5",
                "x_account_mode": "blend",
                "x_account_weight_pct": 35.0,
                "x_tracked_accounts": ["lookonchain", "wu_blockchain"],
                "scan_quote_asset": "USDT",
                "scan_interval": "4h",
                "scan_candidate_pool": 18,
                "scan_min_quote_volume": 10_000_000,
                "scan_min_trade_count": 3000,
                "autotrade_enabled": False,
                "autotrade_mode": "paper",
                "autotrade_quote_order_qty": 25.0,
                "autotrade_max_open_positions": 3,
                "autotrade_max_total_quote_exposure": 100.0,
                "autotrade_score_threshold": 75.0,
                "autotrade_min_volume_ratio": 1.1,
                "autotrade_min_buy_pressure": 0.52,
                "autotrade_stop_loss_pct": 4.0,
                "autotrade_take_profit_pct": 9.0,
                "autotrade_cooldown_minutes": 240,
                "autotrade_order_test_only": True,
                "intelligence_enabled": True,
                "intelligence_llm_enabled": False,
                "intelligence_llm_provider": "openai",
                "intelligence_llm_base_url": "",
                "intelligence_llm_model": "gpt-5.5",
                "intelligence_openai_model": "gpt-5.5",
                "intelligence_min_intel_severity": 60.0,
                "intelligence_min_spread_bps": 12.0,
                "intelligence_whale_transfer_threshold_usd": 5_000_000.0,
                "backtest_archives": "data/spot/monthly/klines/*/4h/*.zip",
                "backtest_preset": "balanced_swing",
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
                "okx_auth_configured": False,
                "x_auth_configured": True,
                "x_provider": "official_api",
                "x_provider_configured": True,
                "tracked_account_count": 2,
                "storage_mode": "Encrypted",
                "autotrade_enabled": False,
                "autotrade_mode": "paper",
                "intelligence_enabled": True,
                "llm_enabled": False,
                "llm_provider": "openai",
                "llm_configured": False,
                "public_data_presets": [
                    {"preset_id": "binance_public", "name": "Binance Public Market Data", "category": "market"},
                    {"preset_id": "defillama_free", "name": "DefiLlama Free API", "category": "onchain"},
                ],
                "llm_provider_presets": [
                    {"provider_id": "openai", "name": "OpenAI"},
                    {"provider_id": "anthropic", "name": "Anthropic Claude"},
                    {"provider_id": "google", "name": "Google Gemini"},
                    {"provider_id": "deepseek", "name": "DeepSeek"},
                    {"provider_id": "xai", "name": "xAI Grok"},
                    {"provider_id": "mistral", "name": "Mistral AI"},
                    {"provider_id": "qwen", "name": "Alibaba Qwen"},
                    {"provider_id": "moonshot", "name": "Moonshot Kimi"},
                ],
            },
            message="运行配置已保存。",
            error=None,
            import_payload_text=None,
            layout_context={"market_ticker": {"items": [], "error": "Ticker cache is empty. Run a market scan to load live ticker data.", "error_code": "cache_empty"}},
        )

        self.assertIn("Runtime Settings", html)
        self.assertIn("Binance API Key", html)
        self.assertIn("OKX API Key", html)
        self.assertIn("Market Data Preset", html)
        self.assertIn("On-chain Data Preset", html)
        self.assertIn("DefiLlama", html)
        self.assertIn("LLM Provider", html)
        self.assertIn("DeepSeek", html)
        self.assertIn("Moonshot", html)
        self.assertIn("X Provider", html)
        self.assertIn("nitter_rss", html)
        self.assertIn("session_scrape", html)
        self.assertIn("X Nitter Base URL", html)
        self.assertIn("X Session Command", html)
        self.assertIn("Twitter Intel", html)
        self.assertIn("Tracked Accounts", html)
        self.assertIn("Backtest Defaults", html)
        self.assertIn("运行配置已保存", html)
        self.assertIn("导出模板 JSON", html)
        self.assertIn("导入配置模板", html)
        self.assertIn("未配置 OKX 凭据", html)
        self.assertIn("2 个 X 跟踪账号", html)
        self.assertIn("Reddit API Base URL", html)
        self.assertIn("Reddit User-Agent", html)
        self.assertIn("Default Preset", html)
        self.assertIn("Auto Trade Defaults", html)
        self.assertIn("Intelligence & LLM", html)
        self.assertIn("Encrypted", html)
        self.assertIn("RUNTIME_CONFIG_PASSPHRASE", html)
        self.assertIn("用于读取 Binance 账户权限、费率和提交受保护的实盘订单", html)
        self.assertIn("自动交易最多同时持有的仓位数量", html)
        self.assertIn("本地 Binance public-data ZIP 路径或 glob", html)
        self.assertIn("粘贴从导出功能得到的配置模板 JSON", html)
        self.assertIn("行情缓存为空，请先运行一次市场扫描加载实时行情。", html)
        self.assertNotIn("Ticker cache is empty", html)

    def test_render_terminal_page_includes_intelligence_sections(self) -> None:
        html = render_terminal_page(
            {
                "generated_at": "2026-04-28T00:00:00+00:00",
                "scanned_symbols": 12,
                "returned_signals": 4,
                "intel_items": [{"source": "binance", "symbol": "BTCUSDT", "title": "Key market update", "severity": 88.0}],
                "twitter_accounts": [{"username": "lookonchain", "focus": "链上异动", "mode": "blend", "status": "configured"}],
                "onchain_events": [{"chain": "bitcoin", "symbol": "BTCUSDT", "event_type": "whale", "amount_usd": 9_000_000.0, "direction": "outflow"}],
                "spreads": [{"symbol": "BTCUSDT", "spot_exchange": "BINANCE", "futures_exchange": "BINANCE-PERP", "spread_bps": 18.0, "direction": "basis"}],
                "strategy_hits": [{"symbol": "BTCUSDT", "strategy": "auto_score_breakout", "score": 82.0, "grade": "A", "action": "watch", "reasons": ["趋势结构改善"]}],
                "llm_insight": {"provider": "local", "model": "rules", "status": "ok", "summary": "综合监控正常。"},
                "execution_risk": {
                    "status": "clear",
                    "risk_score": 22.0,
                    "allowed_symbols": ["BTCUSDT"],
                    "blocked_symbols": {},
                    "summary": "执行前风控：允许 1 个候选。",
                },
                "platform": {
                    "generated_at": "2026-04-28T00:00:00+00:00",
                    "components": [
                        {
                            "layer": "接入层",
                            "name": "Binance API",
                            "status": "ready",
                            "capability": "现货行情、账户费率、实盘市价单",
                            "endpoint": "/api/scan",
                        }
                    ],
                    "accounts": [
                        {
                            "exchange": "BINANCE",
                            "mode": "paper",
                            "status": "paper_ready",
                            "open_positions": 0,
                            "quote_exposure": 0.0,
                        }
                    ],
                    "strategies": [
                        {
                            "strategy_id": "auto_score_breakout",
                            "name": "综合评分突破",
                            "status": "watch_only",
                            "trigger": "score >= 75.0",
                            "execution": "paper/live 市价买入",
                        }
                    ],
                    "risk_rules": [
                        {
                            "name": "最大持仓数",
                            "status": "active",
                            "threshold": "3",
                            "action": "拒绝新开仓",
                        }
                    ],
                    "recent_events": [
                        {
                            "created_at": "2026-04-28T00:00:00+00:00",
                            "action": "watch",
                            "symbol": "BTCUSDT",
                            "status": "skipped",
                            "message": "risk gate clear",
                        }
                    ],
                },
            }
        )

        self.assertIn("AI Trade Command Center", html)
        self.assertIn("app-shell", html)
        self.assertIn("app-sidebar", html)
        self.assertIn("market-ticker", html)
        self.assertIn("量化交易系统", html)
        self.assertIn("交易所与热门情报", html)
        self.assertIn("链上异动", html)
        self.assertIn("现货 / 合约价差", html)
        self.assertIn("策略命中", html)
        self.assertIn("执行前风控", html)
        self.assertIn("功能实现状态", html)
        self.assertIn("交易账户概览", html)
        self.assertIn("策略目录", html)
        self.assertIn('href="/terminal/market"', html)
        self.assertIn('href="/terminal/community"', html)
        self.assertIn('href="/terminal/trading"', html)

    def test_render_terminal_module_page_exposes_paper_trading_action(self) -> None:
        html = render_terminal_module_page(
            snapshot={
                "generated_at": "2026-04-28T00:00:00+00:00",
                "scanned_symbols": 12,
                "returned_signals": 4,
                "intel_items": [{"source": "binance", "symbol": "BTCUSDT", "title": "Key market update", "category": "market", "severity": 88.0, "sentiment": 0.4}],
                "twitter_accounts": [{"username": "lookonchain", "focus": "链上异动", "mode": "blend", "weight_pct": 35.0, "status": "configured"}],
                "onchain_events": [{"chain": "bitcoin", "symbol": "BTCUSDT", "event_type": "whale", "amount_usd": 9_000_000.0, "direction": "outflow", "severity": 82.0}],
                "spreads": [{"symbol": "BTCUSDT", "spot_exchange": "BINANCE", "futures_exchange": "BINANCE-PERP", "spot_price": 100.0, "futures_price": 100.2, "spread_bps": 20.0, "direction": "basis"}],
                "strategy_hits": [{"symbol": "BTCUSDT", "strategy": "auto_score_breakout", "score": 82.0, "grade": "A", "action": "watch", "reasons": ["趋势结构改善"]}],
                "llm_insight": {"provider": "local", "model": "rules", "status": "ok", "summary": "综合监控正常。"},
                "execution_risk": {
                    "status": "clear",
                    "risk_score": 22.0,
                    "allowed_symbols": ["BTCUSDT"],
                    "blocked_symbols": {},
                    "summary": "执行前风控：允许 1 个候选。",
                },
                "platform": {
                    "generated_at": "2026-04-28T00:00:00+00:00",
                    "components": [],
                    "accounts": [{"exchange": "BINANCE", "mode": "paper", "status": "paper_ready", "open_positions": 0, "quote_exposure": 0.0}],
                    "strategies": [{"strategy_id": "auto_score_breakout", "name": "综合评分突破", "status": "watch_only", "trigger": "score >= 75.0", "execution": "paper/live 市价买入", "risk_controls": ["risk_gate"]}],
                    "risk_rules": [{"name": "最大持仓数", "status": "active", "threshold": "3", "action": "拒绝新开仓"}],
                    "recent_events": [],
                },
            },
            module="trading",
            trading_status={
                "config": {
                    "enabled": False,
                    "mode": "paper",
                    "quote_order_qty": 25.0,
                    "score_threshold": 75.0,
                },
                "open_positions": [],
                "events": [],
            },
            message="模拟量化交易已执行",
        )

        self.assertIn("模拟账户执行", html)
        self.assertIn('action="/terminal/trading/run"', html)
        self.assertIn("运行模拟量化交易", html)
        self.assertIn('class="sidebar-link active" href="/terminal/trading"', html)
        self.assertNotIn("terminal-sidebar", html)

    def test_onchain_module_loads_without_terminal_scan(self) -> None:
        config = RuntimeConfig()
        config.onchain_data_preset = "open_multichain_keyless"
        with (
            patch("trade_signal_app.main._terminal_payload", side_effect=RuntimeError("scan failed")),
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, None)),
            patch(
                "trade_signal_app.main.OpenMultiChainOnchainProvider.fetch_events",
                return_value=[
                    OnchainMonitorEvent(
                        chain="bitcoin",
                        symbol="BTCUSDT",
                        event_type="network_snapshot",
                        amount_usd=0.0,
                        direction="latest_block_txs=25",
                        severity=50.0,
                    )
                ],
            ),
        ):
            payload = _terminal_module_payload("onchain")

        self.assertFalse(payload["fallback"])
        self.assertEqual(payload["onchain_events"][0]["symbol"], "BTCUSDT")
        self.assertEqual(payload["warning"], "")

    def test_compile_strategy_payload_returns_run_urls_without_llm(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), object())):
            payload = _compile_strategy_payload("BTC 15m RSI 超卖反弹，止损3%，止盈6%")

        self.assertEqual(payload["source"], "local_rules")
        self.assertEqual(payload["style"], "mean_reversion")
        self.assertEqual(payload["symbols"], ["BTCUSDT"])
        self.assertIn("/backtest?", payload["run_urls"]["backtest"])
        self.assertEqual(payload["run_urls"]["paper_trading"], "/terminal/trading")

    def test_render_strategy_module_includes_natural_language_compiler(self) -> None:
        html = render_terminal_module_page(
            snapshot={
                "generated_at": "2026-04-28T00:00:00+00:00",
                "scanned_symbols": 12,
                "returned_signals": 4,
                "intel_items": [],
                "twitter_accounts": [],
                "onchain_events": [],
                "spreads": [],
                "strategy_hits": [{"symbol": "BTCUSDT", "strategy": "auto_score_breakout", "score": 82.0, "grade": "A", "action": "watch", "reasons": ["趋势结构改善"]}],
                "llm_insight": {"provider": "local", "model": "rules", "status": "ok", "summary": "综合监控正常。"},
                "execution_risk": {
                    "status": "clear",
                    "risk_score": 22.0,
                    "allowed_symbols": ["BTCUSDT"],
                    "blocked_symbols": {},
                    "summary": "执行前风控：允许 1 个候选。",
                },
                "platform": {
                    "generated_at": "2026-04-28T00:00:00+00:00",
                    "components": [],
                    "accounts": [],
                    "strategies": [{"strategy_id": "auto_score_breakout", "name": "综合评分突破", "status": "watch_only", "trigger": "score >= 75.0", "execution": "paper/live 市价买入", "risk_controls": ["risk_gate"]}],
                    "risk_rules": [],
                    "recent_events": [],
                },
            },
            module="strategies",
            strategy_builder_text="BTC 15m RSI 超卖反弹",
            strategy_builder_result={
                "name": "BTC 15m 均值回归策略",
                "description": "BTC 15m RSI 超卖反弹",
                "symbols": ["BTCUSDT"],
                "quote_asset": "USDT",
                "interval": "15m",
                "style": "mean_reversion",
                "entry_rules": ["RSI 低位反弹"],
                "exit_rules": ["止损 3%"],
                "risk_controls": ["paper 模式验证"],
                "backtest_defaults": {"preset": "custom", "score_threshold": 62.0, "stop_loss_pct": 3.0, "take_profit_pct": 6.0},
                "autotrade_defaults": {"enabled": False, "mode": "paper", "score_threshold": 68.0, "order_test_only": True},
                "source": "local_rules",
                "model": "rules",
                "warnings": ["先回测。"],
                "run_urls": {"backtest": "/backtest?preset=custom", "paper_trading": "/terminal/trading"},
            },
            message="策略已编译为可回测和 paper 自动交易参数。",
        )

        self.assertIn("自然语言策略编译器", html)
        self.assertIn('action="/terminal/strategies/compile"', html)
        self.assertIn("BTCUSDT", html)
        self.assertIn("打开回测", html)

    def test_render_trading_page_includes_execution_controls(self) -> None:
        html = render_trading_page(
            config={
                "enabled": True,
                "mode": "paper",
                "quote_order_qty": 25.0,
                "max_open_positions": 3,
                "max_total_quote_exposure": 100.0,
                "score_threshold": 75.0,
                "min_volume_ratio": 1.1,
                "min_buy_pressure": 0.52,
                "stop_loss_pct": 4.0,
                "take_profit_pct": 9.0,
                "cooldown_minutes": 240,
                "order_test_only": True,
            },
            positions=[],
            events=[],
        )

        self.assertIn("AI Trade Auto Execution", html)
        self.assertIn("运行一次自动交易", html)
        self.assertIn("持仓", html)
        self.assertIn("执行事件", html)

    def test_render_trading_page_supports_english_labels(self) -> None:
        html = render_trading_page(
            config={
                "enabled": True,
                "mode": "paper",
                "quote_order_qty": 25.0,
                "max_open_positions": 3,
                "max_total_quote_exposure": 100.0,
                "score_threshold": 75.0,
                "min_volume_ratio": 1.1,
                "min_buy_pressure": 0.52,
                "stop_loss_pct": 4.0,
                "take_profit_pct": 9.0,
                "cooldown_minutes": 240,
                "order_test_only": True,
            },
            positions=[],
            events=[{"created_at": "2026-04-28T00:00:00+00:00", "action": "BUY", "symbol": "BTCUSDT", "status": "paper_filled", "message": "模拟买入已记录。", "score": 82.0, "quote_notional": 25.0}],
            lang="en",
        )

        self.assertIn('html lang="en"', html)
        self.assertIn("app-shell", html)
        self.assertIn("Run Auto Trade Once", html)
        self.assertIn("Paper Filled", html)
        self.assertIn("Paper buy recorded.", html)

    def test_forced_paper_trading_run_uses_signal_source_when_autotrade_disabled(self) -> None:
        signal = SimpleNamespace(
            symbol="BTCUSDT",
            score=84.0,
            grade="A",
            reasons=["EMA20/EMA50 多头排列", "MACD 动能转强"],
            ticker=SimpleNamespace(
                last_price=100.0,
                price_change_percent=2.1,
                quote_volume=20_000_000.0,
            ),
            indicators=SimpleNamespace(
                volume_ratio=1.6,
                buy_pressure_ratio=0.63,
                ema_spread_pct=1.2,
            ),
        )
        scanner = SimpleNamespace(
            scan=lambda: (SimpleNamespace(scanned_symbols=10, returned_signals=1), [signal]),
        )
        config = RuntimeConfig()
        config.autotrade_defaults.enabled = False
        config.autotrade_defaults.mode = "live"
        config.autotrade_defaults.quote_order_qty = 25.0
        config.autotrade_defaults.score_threshold = 75.0
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
            ):
                payload = _run_trading_once(force_paper=True)

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["events"][0]["status"], "paper_filled")
        self.assertEqual(payload["open_positions"][0]["symbol"], "BTCUSDT")

    def test_build_runtime_config_parses_runtime_form(self) -> None:
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.okx_api_key = "keep-okx-key"
        current.okx_api_secret = "keep-okx-secret"
        current.okx_api_passphrase = "keep-okx-pass"
        current.x_bearer_token = "keep-x-token"
        current.onchain_api_key = "keep-onchain-key"
        current.llm_api_key = "keep-llm-key"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            config = _build_runtime_config(
                {
                    "binance_recv_window_ms": ["6000"],
                    "market_data_preset": ["okx_public"],
                    "onchain_data_preset": ["geckoterminal_keyless"],
                    "onchain_api_key": ["test-onchain-key"],
                    "onchain_api_base_url": ["https://onchain.example.test"],
                    "community_provider": ["x"],
                    "x_provider": ["nitter_rss"],
                    "x_api_base_url": ["https://api.x.com"],
                    "x_nitter_base_url": ["http://127.0.0.1:8788"],
                    "x_session_command": ["twscrape search {query} --limit {limit}"],
                    "x_recent_window_hours": ["12"],
                    "x_recent_max_results": ["20"],
                    "x_language": ["en"],
                    "reddit_api_base_url": ["https://www.reddit.com"],
                    "reddit_recent_window_hours": ["18"],
                    "reddit_max_results": ["15"],
                    "reddit_user_agent": ["trade-signal-app/test"],
                    "x_account_mode": ["blend"],
                    "x_account_weight_pct": ["40"],
                    "x_tracked_accounts": ["@lookonchain\nwu_blockchain"],
                    "scan_quote_asset": ["FDUSD"],
                    "scan_interval": ["1h"],
                    "scan_candidate_pool": ["12"],
                    "scan_min_quote_volume": ["2000000"],
                    "scan_min_trade_count": ["800"],
                    "autotrade_enabled": ["on"],
                    "autotrade_mode": ["paper"],
                    "autotrade_quote_order_qty": ["30"],
                    "autotrade_max_open_positions": ["2"],
                    "autotrade_max_total_quote_exposure": ["90"],
                    "autotrade_score_threshold": ["78"],
                    "autotrade_min_volume_ratio": ["1.2"],
                    "autotrade_min_buy_pressure": ["0.58"],
                    "autotrade_stop_loss_pct": ["3"],
                    "autotrade_take_profit_pct": ["8"],
                    "autotrade_cooldown_minutes": ["180"],
                    "autotrade_order_test_only": ["on"],
                    "intelligence_enabled": ["on"],
                    "intelligence_llm_enabled": ["on"],
                    "llm_provider": ["deepseek"],
                    "llm_api_key": ["test-llm-key"],
                    "llm_base_url": ["https://llm.example.test/v1"],
                    "llm_model": ["deepseek-chat"],
                    "intelligence_min_intel_severity": ["68"],
                    "intelligence_min_spread_bps": ["15"],
                    "intelligence_whale_transfer_threshold_usd": ["7000000"],
                    "backtest_archives": ["/tmp/example.zip"],
                    "backtest_preset": ["portfolio_rotation"],
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
        self.assertEqual(config.okx_api_key, "keep-okx-key")
        self.assertEqual(config.okx_api_secret, "keep-okx-secret")
        self.assertEqual(config.okx_api_passphrase, "keep-okx-pass")
        self.assertEqual(config.x_bearer_token, "keep-x-token")
        self.assertEqual(config.market_data_preset, "okx_public")
        self.assertEqual(config.onchain_data_preset, "geckoterminal_keyless")
        self.assertEqual(config.onchain_api_key, "test-onchain-key")
        self.assertEqual(config.onchain_api_base_url, "https://onchain.example.test")
        self.assertEqual(config.llm_provider, "deepseek")
        self.assertEqual(config.llm_api_key, "test-llm-key")
        self.assertEqual(config.llm_base_url, "https://llm.example.test/v1")
        self.assertEqual(config.llm_model, "deepseek-chat")
        self.assertEqual(config.x_provider, "nitter_rss")
        self.assertEqual(config.x_nitter_base_url, "http://127.0.0.1:8788")
        self.assertEqual(config.x_session_command, "twscrape search {query} --limit {limit}")
        self.assertEqual(config.x_account_mode, "blend")
        self.assertEqual(config.x_tracked_accounts, ["@lookonchain", "wu_blockchain"])
        self.assertEqual(config.reddit_recent_window_hours, 18)
        self.assertEqual(config.reddit_max_results, 15)
        self.assertEqual(config.reddit_user_agent, "trade-signal-app/test")
        self.assertEqual(config.backtest_defaults.preset, "portfolio_rotation")
        self.assertEqual(config.scan_defaults.quote_asset, "FDUSD")
        self.assertTrue(config.autotrade_defaults.enabled)
        self.assertEqual(config.autotrade_defaults.quote_order_qty, 30.0)
        self.assertEqual(config.autotrade_defaults.max_open_positions, 2)
        self.assertTrue(config.intelligence_defaults.enabled)
        self.assertTrue(config.intelligence_defaults.llm_enabled)
        self.assertEqual(config.intelligence_defaults.llm_provider, "deepseek")
        self.assertEqual(config.intelligence_defaults.llm_api_key, "test-llm-key")
        self.assertEqual(config.intelligence_defaults.llm_model, "deepseek-chat")
        self.assertEqual(config.intelligence_defaults.min_spread_bps, 15.0)
        self.assertEqual(config.backtest_defaults.fee_source, "account")
        self.assertTrue(config.backtest_defaults.no_binance_discount)
        self.assertTrue(config.backtest_defaults.no_kdj_confirmation)

    def test_build_runtime_config_rejects_invalid_choices(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)):
            with self.assertRaisesRegex(ValueError, "Auto Trade Mode"):
                _build_runtime_config({"autotrade_mode": ["real"]})

    def test_import_runtime_config_template_rejects_invalid_ranges(self) -> None:
        current = RuntimeConfig()
        config_payload = current.to_dict()
        config_payload["backtest_defaults"] = {
            **config_payload["backtest_defaults"],
            "min_rsi": 80,
            "max_rsi": 20,
        }
        payload = {"kind": "runtime_config_template", "version": 1, "config": config_payload}
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            with self.assertRaisesRegex(ValueError, "Min RSI"):
                _import_runtime_config_template({"config_template": [json.dumps(payload)]})

    def test_import_runtime_config_template_preserves_existing_secrets(self) -> None:
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.okx_api_key = "keep-okx-key"
        current.okx_api_secret = "keep-okx-secret"
        current.okx_api_passphrase = "keep-okx-pass"
        current.x_bearer_token = "keep-token"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            imported = _import_runtime_config_template(
                {
                    "config_template": [
                        '{"kind":"runtime_config_template","version":1,"config":{"binance_api_key":"","binance_api_secret":"","x_bearer_token":"","scan_defaults":{"quote_asset":"FDUSD"}}}'
                    ]
                }
            )

        self.assertEqual(imported.binance_api_key, "keep-key")
        self.assertEqual(imported.binance_api_secret, "keep-secret")
        self.assertEqual(imported.okx_api_key, "keep-okx-key")
        self.assertEqual(imported.okx_api_secret, "keep-okx-secret")
        self.assertEqual(imported.okx_api_passphrase, "keep-okx-pass")
        self.assertEqual(imported.x_bearer_token, "keep-token")
        self.assertEqual(imported.scan_defaults.quote_asset, "FDUSD")

    def test_export_runtime_config_template_redacts_secrets(self) -> None:
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.okx_api_key = "keep-okx-key"
        current.okx_api_secret = "keep-okx-secret"
        current.okx_api_passphrase = "keep-okx-pass"
        current.x_bearer_token = "keep-token"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            payload = _export_runtime_config_template(include_secrets=False)

        self.assertEqual(payload["config"]["binance_api_key"], "")
        self.assertEqual(payload["config"]["binance_api_secret"], "")
        self.assertEqual(payload["config"]["okx_api_key"], "")
        self.assertEqual(payload["config"]["okx_api_secret"], "")
        self.assertEqual(payload["config"]["okx_api_passphrase"], "")
        self.assertEqual(payload["config"]["x_bearer_token"], "")

    def test_backtest_export_csv_contains_core_rows(self) -> None:
        csv_text = _backtest_export_csv(
            payload={
                "strategy_explanation": {
                    "strategy_type": "balanced_swing",
                    "summary": "均衡波段模板",
                    "notes": ["成本假设：fee_model=flat"],
                },
                "series_reports": [
                    {
                        "symbol": "BTCUSDT",
                        "interval": "4h",
                        "final_equity": 1.23,
                        "max_drawdown_pct": -4.5,
                        "signal_count": 6,
                        "trade_stat": {"win_rate_pct": 66.7, "profit_factor": 1.8},
                    }
                ],
                "portfolio_reports": [
                    {
                        "top_n": 2,
                        "interval": "4h",
                        "final_equity": 1.15,
                        "max_drawdown_pct": -3.2,
                        "batch_count": 4,
                        "trade_stat": {"win_rate_pct": 75.0, "profit_factor": 2.1},
                    }
                ],
            },
            params={"lookback_bars": 240, "portfolio_top_n": 2},
            error=None,
        )

        self.assertIn("section,name,interval,metric,value", csv_text)
        self.assertIn("meta,strategy,,strategy_type,balanced_swing", csv_text)
        self.assertIn("param,backtest,,lookback_bars,240", csv_text)
        self.assertIn("series,BTCUSDT,4h,final_equity,1.23", csv_text)
        self.assertIn("portfolio,portfolio_top_2,4h,profit_factor,2.1", csv_text)

    def test_backtest_payload_applies_preset_defaults(self) -> None:
        current = RuntimeConfig()
        current.backtest_defaults.preset = "portfolio_rotation"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            _, params, _ = _backtest_payload({})

        self.assertEqual(params["preset"], "portfolio_rotation")
        self.assertEqual(params["portfolio_top_n"], 3)
        self.assertEqual(params["capital_fraction_pct"], 60.0)

    def test_backtest_payload_includes_strategy_explanation_without_archives(self) -> None:
        current = RuntimeConfig()
        current.backtest_defaults.preset = "breakout_aggressive"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            payload, _, error = _backtest_payload({})

        self.assertIsNone(error)
        self.assertEqual(payload["strategy_explanation"]["strategy_type"], "breakout")
        self.assertIn("尚未产生", " ".join(payload["strategy_explanation"]["diagnostics"]))

    def test_backtest_payload_runs_optional_stability_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)

            with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)):
                payload, _, error = _backtest_payload(
                    {
                        "archives": [str(archive)],
                        "portfolio_top_n": ["0"],
                        "stability_checks": ["on"],
                    }
                )

        self.assertIsNone(error)
        explanation = payload["strategy_explanation"]
        self.assertTrue(explanation["stability_enabled"])
        self.assertTrue(explanation["stability_checks"])
        check_names = {item["check"] for item in explanation["stability_checks"]}
        self.assertIn("score_minus_3", check_names)
        self.assertIn("score_plus_3", check_names)
        self.assertIn("slippage_plus_5bps", check_names)
        self.assertIn("walk_forward_fold_1", check_names)

    def test_backtest_payload_applies_btc_cycle_trend_preset(self) -> None:
        current = RuntimeConfig()
        current.backtest_defaults.preset = "btc_cycle_trend"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            _, params, _ = _backtest_payload({})

        self.assertEqual(params["preset"], "btc_cycle_trend")
        self.assertEqual(params["portfolio_top_n"], 1)
        self.assertEqual(params["min_rsi"], 46.0)
        self.assertEqual(params["max_rsi"], 74.0)
        self.assertEqual(params["max_concurrent_positions"], 1)

    def test_backtest_payload_applies_btc_core_trading_preset(self) -> None:
        current = RuntimeConfig()
        current.backtest_defaults.preset = "btc_core_trading"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            _, params, _ = _backtest_payload({})

        self.assertEqual(params["preset"], "btc_core_trading")
        self.assertEqual(params["min_buy_pressure"], 0.56)
        self.assertEqual(params["max_rsi"], 74.0)
        self.assertTrue(params["no_kdj_confirmation"])

    def test_backtest_payload_applies_crypto_rebalance_premium_preset(self) -> None:
        current = RuntimeConfig()
        current.backtest_defaults.preset = "crypto_rebalance_premium"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            _, params, _ = _backtest_payload({})

        self.assertEqual(params["preset"], "crypto_rebalance_premium")
        self.assertEqual(params["portfolio_top_n"], 0)
        self.assertEqual(params["capital_fraction_pct"], 100.0)
        self.assertTrue(params["no_kdj_confirmation"])

    def test_backtest_payload_applies_btc_overnight_seasonality_preset(self) -> None:
        current = RuntimeConfig()
        current.backtest_defaults.preset = "btc_overnight_seasonality"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            _, params, _ = _backtest_payload({})

        self.assertEqual(params["preset"], "btc_overnight_seasonality")
        self.assertEqual(params["score_threshold"], 0.0)
        self.assertEqual(params["max_holding_bars"], 2)
        self.assertTrue(params["no_kdj_confirmation"])

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
