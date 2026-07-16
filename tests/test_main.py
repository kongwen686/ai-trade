from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse
import zipfile

import trade_signal_app.main_backtest as main_backtest
import trade_signal_app.main as app_main
from trade_signal_app import __version__
from trade_signal_app.main import (
    _backtest_payload,
    _backtest_export_csv,
    _backtest_export_html,
    _build_runtime_config,
    _compile_strategy_payload,
    _compile_strategy_template_payload,
    _export_runtime_config_template,
    _fast_market_module_payload,
    _health_payload,
    _import_runtime_config_template,
    _paper_auto_status_payload,
    _run_trading_once,
    _scan_payload,
    _serialize_trading_report,
    _serialize_trading_position,
    _start_paper_auto_trading,
    _stop_paper_auto_trading,
    _terminal_api_module_from_path,
    _terminal_module_payload,
    _trading_readiness_payload,
    _split_archives,
    main,
    parse_args,
    run,
)
from trade_signal_app.intelligence import FundingRateSnapshot
from trade_signal_app.onchain import OnchainMonitorEvent
from trade_signal_app.presets import list_backtest_presets
from trade_signal_app.runtime_config import RuntimeConfig
from trade_signal_app.storage import LocalDataStore
from trade_signal_app.trading import TradingEvent, TradingPosition, TradingRunReport, TradingStateStore
from trade_signal_app.views import (
    _benchmark_workbench,
    _parameter_heatmap,
    _portfolio_card,
    _rebalance_empty_card,
    _risk_return_scatter,
    render_backtest_page,
    render_btc_signal_page,
    render_index_page,
    render_settings_page,
    render_terminal_module_page,
    render_terminal_page,
    render_trading_page,
)
from trade_signal_app.views_backtest import BACKTEST_ADVANCED_HELP


def _build_archive(path: Path, *, start: datetime | None = None, bars: int = 180) -> None:
    rows: list[str] = []
    start = start or datetime(2026, 7, 6, 0, 0, tzinfo=timezone.utc)
    price = 100.0
    for index in range(bars):
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
    def _btc_trading_fixture(self) -> dict[str, object]:
        return {
            "symbol": "BTCUSDT",
            "metrics": {
                "open_positions": 1,
                "quote_exposure": 120.0,
                "total_trades": 6,
                "buy_trades": 3,
                "sell_trades": 3,
                "closed_trades": 3,
                "winning_trades": 2,
                "losing_trades": 1,
                "win_rate_pct": 66.67,
                "profit_loss_ratio": 2.4,
                "realized_pnl": 18.0,
                "unrealized_pnl": 3.5,
                "total_pnl": 21.5,
            },
            "signal": {
                "symbol": "BTCUSDT",
                "action": "BUY",
                "action_label": "买入",
                "signal": "btc_regime_trend_pullback_buy",
                "score": 82.35,
                "grade": "A",
                "confidence": "高",
                "price": 118000.0,
                "advice": "分批试多，止损放在结构支撑下方。",
                "regime": {"label": "多头趋势"},
                "trade_levels": {
                    "stop_price": 114900.0,
                    "take_profit_price": 125496.0,
                    "risk_reward_ratio": 2.42,
                    "support_distance_pct": 2.1,
                    "leveraged_stop_roi_pct": -13.14,
                    "leveraged_take_profit_roi_pct": 31.76,
                },
                "statistics": {"return_365d_pct": 48.2, "max_drawdown_pct": -76.2},
                "reasons": ["1d 收盘价位于 EMA200 上方"],
                "warnings": ["1h RSI 偏热时不追价"],
            },
            "open_positions": [],
            "recent_events": [],
            "signal_error": "",
        }

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
        with (
            patch("trade_signal_app.main.ThreadingHTTPServer", return_value=server) as server_factory,
            patch("trade_signal_app.main._start_feishu_daily_report_scheduler") as scheduler_start,
            patch("trade_signal_app.main._stop_feishu_daily_report_scheduler") as scheduler_stop,
        ):
            main(["--host", "0.0.0.0", "--port", "9000"])

        server_factory.assert_called_once()
        self.assertEqual(server_factory.call_args.args[0], ("0.0.0.0", 9000))
        self.assertEqual(server_factory.call_args.args[1].__name__, "RequestHandler")
        server.serve_forever.assert_called_once_with()
        scheduler_start.assert_called_once_with()
        scheduler_stop.assert_called_once_with()

    def test_tradingview_fetch_result_uses_injected_cache_dir(self) -> None:
        cache_dir = Path("/tmp/custom-tradingview-cache")
        cache_path = cache_dir / "BINANCE_ETHUSDT_1h.csv"
        with patch(
            "trade_signal_app.main_backtest.fetch_tradingview_history",
            return_value=SimpleNamespace(
                exchange="BINANCE",
                symbol="ETHUSDT",
                interval="1h",
                candle_count=1200,
                source="cache",
                cache_path=cache_path,
            ),
        ) as fetch_history:
            result = main_backtest._tradingview_fetch_result(
                {
                    "tradingview_symbol": ["ethusdt"],
                    "tradingview_exchange": ["binance"],
                    "tradingview_interval": ["1h"],
                    "tradingview_bars": ["1200"],
                },
                runtime_config=RuntimeConfig(),
                tradingview_cache_dir=cache_dir,
            )

        self.assertEqual(fetch_history.call_args.kwargs["cache_root"], cache_dir)
        self.assertEqual(fetch_history.call_args.kwargs["symbol"], "ETHUSDT")
        self.assertEqual(result["cache_path"], str(cache_path))

    def test_tradingview_fetch_result_defaults_to_ten_thousand_bars(self) -> None:
        cache_dir = Path("/tmp/custom-tradingview-cache")
        cache_path = cache_dir / "BINANCE_BTCUSDT_4h.csv"
        with patch(
            "trade_signal_app.main_backtest.fetch_tradingview_history",
            return_value=SimpleNamespace(
                exchange="BINANCE",
                symbol="BTCUSDT",
                interval="4h",
                candle_count=10000,
                source="cache",
                cache_path=cache_path,
            ),
        ) as fetch_history:
            result = main_backtest._tradingview_fetch_result(
                {},
                runtime_config=RuntimeConfig(),
                tradingview_cache_dir=cache_dir,
            )

        self.assertEqual(fetch_history.call_args.kwargs["bars"], 10000)
        self.assertEqual(result["bars"], 10000)

    def test_tradingview_fetch_result_accepts_one_hundred_thousand_bars(self) -> None:
        cache_dir = Path("/tmp/custom-tradingview-cache")
        cache_path = cache_dir / "BINANCE_BTCUSDT_4h.csv"
        with patch(
            "trade_signal_app.main_backtest.fetch_tradingview_history",
            return_value=SimpleNamespace(
                exchange="BINANCE",
                symbol="BTCUSDT",
                interval="4h",
                candle_count=100000,
                source="cache",
                cache_path=cache_path,
            ),
        ) as fetch_history:
            result = main_backtest._tradingview_fetch_result(
                {"tradingview_bars": ["100000"]},
                runtime_config=RuntimeConfig(),
                tradingview_cache_dir=cache_dir,
            )

        self.assertEqual(fetch_history.call_args.kwargs["bars"], 100000)
        self.assertEqual(result["bars"], 100000)

    def test_tradingview_fetch_result_rejects_more_than_one_hundred_thousand_bars(self) -> None:
        with patch("trade_signal_app.main_backtest.fetch_tradingview_history") as fetch_history:
            with self.assertRaises(ValueError):
                main_backtest._tradingview_fetch_result(
                    {"tradingview_bars": ["100001"]},
                    runtime_config=RuntimeConfig(),
                    tradingview_cache_dir=Path("/tmp/custom-tradingview-cache"),
                )

        fetch_history.assert_not_called()

    def test_tradingview_backtest_redirect_uses_injected_runtime_config(self) -> None:
        runtime_config = RuntimeConfig()
        runtime_config.backtest_defaults.lookback_bars = 180
        cache_dir = Path("/tmp/custom-tradingview-cache")
        cache_path = cache_dir / "BINANCE_ETHUSDT_1h.csv"

        with patch(
            "trade_signal_app.main_backtest._tradingview_fetch_result",
            return_value={
                "exchange": "BINANCE",
                "symbol": "ETHUSDT",
                "interval": "1h",
                "bars": 1200,
                "cache_path": str(cache_path),
            },
        ) as fetch_result:
            redirect_url = main_backtest._tradingview_backtest_redirect(
                {},
                "en",
                runtime_config=runtime_config,
                tradingview_cache_dir=cache_dir,
            )

        fetch_result.assert_called_once_with({}, runtime_config=runtime_config, tradingview_cache_dir=cache_dir)
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/backtest")
        self.assertEqual(query["archives"], [str(cache_path)])
        self.assertEqual(query["lookback_bars"], ["180"])
        self.assertEqual(query["tradingview_symbol"], ["ETHUSDT"])
        self.assertEqual(query["lang"], ["en"])

    def test_run_uses_explicit_host_and_port_over_defaults(self) -> None:
        server = Mock()
        with (
            patch("trade_signal_app.main.ThreadingHTTPServer", return_value=server) as server_factory,
            patch("trade_signal_app.main._start_feishu_daily_report_scheduler"),
            patch("trade_signal_app.main._stop_feishu_daily_report_scheduler"),
        ):
            run(host="127.0.0.2", port=8100)

        self.assertEqual(server_factory.call_args.args[0], ("127.0.0.2", 8100))
        server.serve_forever.assert_called_once_with()

    def test_next_feishu_daily_report_uses_ten_pm_app_timezone(self) -> None:
        before = datetime(2026, 7, 10, 21, 59, tzinfo=app_main.APP_TIMEZONE)
        exact = datetime(2026, 7, 10, 22, 0, tzinfo=app_main.APP_TIMEZONE)
        after = datetime(2026, 7, 10, 22, 1, tzinfo=app_main.APP_TIMEZONE)

        self.assertEqual(app_main._next_feishu_daily_report_at(before), exact)
        self.assertEqual(app_main._next_feishu_daily_report_at(exact), exact)
        self.assertEqual(app_main._next_feishu_daily_report_at(after), exact + timedelta(days=1))

    def test_pending_feishu_daily_report_catches_up_previous_day_until_ten_am(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalDataStore(Path(temp_dir) / "ai_trade.sqlite3")
            with patch("trade_signal_app.main._local_data_store", return_value=store):
                before_cutoff = datetime(2026, 7, 11, 9, 59, tzinfo=app_main.APP_TIMEZONE)
                after_cutoff = datetime(2026, 7, 11, 10, 1, tzinfo=app_main.APP_TIMEZONE)

                self.assertEqual(
                    app_main._pending_feishu_daily_report_at(before_cutoff),
                    datetime(2026, 7, 10, 22, 0, tzinfo=app_main.APP_TIMEZONE),
                )
                self.assertEqual(
                    app_main._pending_feishu_daily_report_at(after_cutoff),
                    datetime(2026, 7, 11, 22, 0, tzinfo=app_main.APP_TIMEZONE),
                )

    def test_build_feishu_daily_summary_combines_daily_metrics(self) -> None:
        now = datetime(2026, 7, 10, 22, 0, tzinfo=app_main.APP_TIMEZONE)
        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=1.0,
            entry_price=100.0,
            quote_notional=100.0,
            score=80.0,
            grade="A",
            opened_at=now - timedelta(hours=3),
            stop_price=96.0,
            take_profit_price=110.0,
            mode="paper",
        )
        events = [
            TradingEvent(action="BUY", symbol="BTCUSDT", mode="paper", status="paper_filled", message="buy", created_at=now - timedelta(hours=2)),
            TradingEvent(
                action="SELL",
                symbol="BTCUSDT",
                mode="paper",
                status="paper_filled",
                message="sell",
                realized_pnl=5.0,
                realized_pnl_pct=5.0,
                created_at=now - timedelta(hours=1),
            ),
            TradingEvent(action="SKIP", symbol="*", mode="paper", status="no_signal", message="skip", created_at=now - timedelta(minutes=30)),
        ]
        store = SimpleNamespace(load=Mock(return_value=[position]), load_events=Mock(return_value=events))
        config = RuntimeConfig()
        scanner = SimpleNamespace(gateway=SimpleNamespace())

        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
            patch(
                "trade_signal_app.main.scan_handlers._scan_payload",
                return_value=(
                    {
                        "summary": {"scanned_symbols": 30, "returned_signals": 2},
                        "signals": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
                    },
                    {},
                ),
            ),
            patch("trade_signal_app.main._trading_store", return_value=store),
            patch("trade_signal_app.main._latest_prices_for_open_positions", return_value={"BTCUSDT": 110.0}),
            patch(
                "trade_signal_app.main._fast_terminal_payload",
                return_value={
                    "llm_insight": {"metrics": {"intel_items": 4, "onchain_events": 2, "strategy_hits": 3, "spreads": 1, "funding_rates": 1}},
                    "execution_risk": {"status": "caution", "risk_score": 66.5, "allowed_symbols": ["BTCUSDT"], "blocked_symbols": {"ETHUSDT": "risk"}},
                },
            ),
        ):
            summary = app_main._build_feishu_daily_summary(now=now)

        self.assertEqual(summary["date"], "2026-07-10")
        self.assertEqual(summary["scan"]["returned_signals"], 2)
        self.assertEqual(summary["scan"]["top_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(summary["trading"]["today_trades"], 2)
        self.assertEqual(summary["trading"]["total_trades"], 2)
        self.assertEqual(summary["trading"]["win_rate_pct"], 100.0)
        self.assertEqual(summary["trading"]["total_pnl"], 15.0)
        self.assertEqual(summary["intelligence"]["intel_items"], 4)
        self.assertEqual(summary["intelligence"]["onchain_events"], 2)
        self.assertEqual(summary["risk"]["risk_score"], 66.5)
        self.assertEqual(summary["risk"]["blocked"], 1)

    def test_run_feishu_daily_report_once_sends_only_once_per_day(self) -> None:
        now = datetime(2026, 7, 10, 22, 0, tzinfo=app_main.APP_TIMEZONE)
        config = RuntimeConfig()
        config.feishu_webhook_url = "https://open.feishu.cn/test-webhook"
        notifier = Mock()
        notifier.notify_daily_summary.return_value = True
        notifier.notify_btc_signal.return_value = True
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalDataStore(Path(temp_dir) / "ai_trade.sqlite3")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, None)),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch("trade_signal_app.main._build_feishu_daily_summary", return_value={"date": "2026-07-10"}),
                patch("trade_signal_app.main._build_btc_signal_summary", return_value={"symbol": "BTCUSDT", "action": "HOLD"}),
                patch("trade_signal_app.main._local_data_store", return_value=store),
            ):
                first = app_main._run_feishu_daily_report_once(now=now)
                second = app_main._run_feishu_daily_report_once(now=now + timedelta(minutes=5))

        self.assertTrue(first["sent"])
        self.assertTrue(first["complete"])
        self.assertFalse(second["sent"])
        self.assertEqual(second["reason"], "already_sent")
        notifier.notify_daily_summary.assert_called_once_with(summary={"date": "2026-07-10"})
        notifier.notify_btc_signal.assert_called_once_with(summary={"symbol": "BTCUSDT", "action": "HOLD"})

    def test_run_feishu_daily_report_retries_only_failed_component(self) -> None:
        now = datetime(2026, 7, 11, 22, 0, tzinfo=app_main.APP_TIMEZONE)
        config = RuntimeConfig()
        config.feishu_webhook_url = "https://open.feishu.cn/test-webhook"
        notifier = Mock()
        notifier.notify_daily_summary.return_value = True
        notifier.notify_btc_signal.side_effect = [app_main.FeishuNotificationError("temporary failure"), True]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalDataStore(Path(temp_dir) / "ai_trade.sqlite3")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, None)),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch("trade_signal_app.main._build_feishu_daily_summary", return_value={"date": "2026-07-11"}),
                patch("trade_signal_app.main._build_btc_signal_summary", return_value={"symbol": "BTCUSDT", "action": "HOLD"}),
                patch("trade_signal_app.main._local_data_store", return_value=store),
            ):
                first = app_main._run_feishu_daily_report_once(now=now)
                second = app_main._run_feishu_daily_report_once(now=now + timedelta(minutes=5))

        self.assertTrue(first["daily_sent"])
        self.assertFalse(first["complete"])
        self.assertFalse(second["daily_sent"])
        self.assertTrue(second["btc_sent"])
        self.assertTrue(second["complete"])
        notifier.notify_daily_summary.assert_called_once_with(summary={"date": "2026-07-11"})
        self.assertEqual(notifier.notify_btc_signal.call_count, 2)

    def test_btc_signal_payload_uses_runtime_exchange_and_fast_flag(self) -> None:
        config = RuntimeConfig()
        config.tradingview_exchange = "BINANCE"
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, None)),
            patch("trade_signal_app.main.build_btc_signal_summary", return_value={"symbol": "BTCUSDT", "action": "HOLD"}) as builder,
        ):
            payload = app_main._btc_signal_payload({"fast": ["1"]})

        self.assertEqual(payload["summary"]["symbol"], "BTCUSDT")
        builder.assert_called_once_with(
            cache_root=app_main.TRADINGVIEW_CACHE_DIR,
            exchange="BINANCE",
            generated_at=None,
            include_backtests=False,
            market_price=0.0,
        )

    def test_latest_prices_for_positions_prefers_live_ticker_price_over_signal_price(self) -> None:
        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=0.01,
            entry_price=100.0,
            quote_notional=1.0,
            score=82.0,
            grade="A",
            opened_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            stop_price=96.0,
            take_profit_price=108.0,
        )
        gateway = SimpleNamespace(ticker_price=Mock(return_value=123.45))
        scanner = SimpleNamespace(gateway=gateway)

        prices = app_main._latest_prices_for_open_positions([position], scanner, {"BTCUSDT": 100.0})

        self.assertEqual(prices["BTCUSDT"], 123.45)
        gateway.ticker_price.assert_called_once_with("BTCUSDT")

    def test_terminal_module_api_accepts_legacy_and_direct_paths(self) -> None:
        self.assertEqual(_terminal_api_module_from_path("/api/terminal/modules/community"), "community")
        self.assertEqual(_terminal_api_module_from_path("/api/terminal/community"), "community")
        self.assertIsNone(_terminal_api_module_from_path("/api/terminal/snapshot"))

    def test_split_archives_supports_commas_and_lines(self) -> None:
        self.assertEqual(
            _split_archives("data/a.zip, data/b.zip\n\ndata/c.zip"),
            ["data/a.zip", "data/b.zip", "data/c.zip"],
        )

    def test_health_payload_is_local_and_reports_live_blockers(self) -> None:
        config = RuntimeConfig()
        config.autotrade_defaults.mode = "live"
        config.autotrade_defaults.live_enabled = True
        config.autotrade_defaults.order_test_only = False
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, object())),
            patch("trade_signal_app.main.APP_STATE.storage_mode_label", return_value="Plain JSON"),
            patch("trade_signal_app.main.TradingStateStore.load", return_value=[]),
            patch("trade_signal_app.main.TradingStateStore.load_events", return_value=[]),
            patch("trade_signal_app.main.TradingStateStore.database_status", return_value={"path": "/tmp/ai_trade.sqlite3", "trading_events": 0}),
            patch.dict("os.environ", {}, clear=True),
        ):
            payload = _health_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(datetime.fromisoformat(str(payload["generated_at"])).utcoffset(), timedelta(hours=8))
        self.assertEqual(payload["database"]["trading_events"], 0)
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

    def test_trading_readiness_reports_temporary_account_check_error(self) -> None:
        config = RuntimeConfig()
        config.binance_api_key = "key"
        config.binance_api_secret = "secret"
        config.autotrade_defaults.live_enabled = True
        config.autotrade_defaults.order_test_only = False
        gateway = Mock()
        gateway.account_status.return_value = {
            "configured": True,
            "authenticated": False,
            "can_trade": False,
            "quote_available": 0.0,
            "status": "error",
            "message": "temporary DNS failure",
        }
        scanner = SimpleNamespace(gateway=gateway)
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
            patch.dict("os.environ", {"AI_TRADE_LIVE_CONFIRM": "I_UNDERSTAND_REAL_ORDERS"}),
        ):
            payload = _trading_readiness_payload(check_account=True)

        self.assertFalse(payload["live_ready"])
        self.assertEqual(payload["blockers"], ["BINANCE 账户检查暂时不可用：temporary DNS failure"])

    def test_trading_readiness_uses_okx_when_selected(self) -> None:
        config = RuntimeConfig()
        config.okx_api_key = "okx-key"
        config.okx_api_secret = "okx-secret"
        config.okx_api_passphrase = "okx-pass"
        config.autotrade_defaults.execution_exchange = "okx"
        okx_gateway = Mock()
        okx_gateway.account_status.return_value = {
            "exchange": "OKX",
            "configured": True,
            "authenticated": True,
            "can_trade": True,
            "quote_available": 100.0,
            "status": "ready",
        }
        scanner = SimpleNamespace(gateway=Mock())
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
            patch("trade_signal_app.main._okx_gateway", return_value=okx_gateway),
        ):
            payload = _trading_readiness_payload(check_account=True)

        self.assertEqual(payload["execution_exchange"], "okx")
        self.assertEqual(payload["exchange_status"]["exchange"], "OKX")
        okx_gateway.account_status.assert_called_once_with({"USDT"})
        scanner.gateway.account_status.assert_not_called()

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
        config = RuntimeConfig()
        config.community_provider = "x,csv"
        config.x_provider = "nitter_rss"
        config.x_nitter_base_url = "https://nitter.example.test"
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)):
            _, params = _scan_payload({"view_mode": ["table"]})

        self.assertEqual(params["view_mode"], "table")
        self.assertEqual(params["community_provider"], "x,csv")
        self.assertEqual(params["x_provider"], "nitter_rss")
        self.assertTrue(params["x_provider_configured"])

    def test_scan_payload_force_refresh_ignores_cached_payload(self) -> None:
        scanner = Mock()
        scanner.scan.side_effect = [
            ({"scanned_symbols": 1, "returned_signals": 0, "quote_asset": "USDT", "interval": "4h", "min_quote_volume": 0}, []),
            ({"scanned_symbols": 2, "returned_signals": 0, "quote_asset": "USDT", "interval": "4h", "min_quote_volume": 0}, []),
        ]
        config = RuntimeConfig()
        with app_main._SCAN_CACHE_LOCK:
            app_main._SCAN_PAYLOAD_CACHE.clear()
            app_main._SCAN_INFLIGHT.clear()
        try:
            with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)):
                first_payload, _ = _scan_payload({})
                refreshed_payload, _ = _scan_payload({}, force_refresh=True)
                cached_payload, _ = _scan_payload({})
        finally:
            with app_main._SCAN_CACHE_LOCK:
                app_main._SCAN_PAYLOAD_CACHE.clear()
                app_main._SCAN_INFLIGHT.clear()

        self.assertEqual(first_payload["summary"]["scanned_symbols"], 1)
        self.assertEqual(refreshed_payload["summary"]["scanned_symbols"], 2)
        self.assertEqual(cached_payload["summary"]["scanned_symbols"], 2)
        self.assertTrue(cached_payload["cached"])
        self.assertEqual(scanner.scan.call_count, 2)

    def test_fallback_scan_payload_honors_candidate_pool_above_default_tickers(self) -> None:
        rows = [
            {
                "symbol": f"TEST{index:02d}USDT",
                "lastPrice": str(100 + index),
                "priceChangePercent": "1.2",
                "quoteVolume": str(100_000_000 - index),
                "volume": "10000",
                "count": "5000",
            }
            for index in range(35)
        ]
        scanner = SimpleNamespace(gateway=SimpleNamespace(ticker24hr=lambda: rows))
        params = {
            "quote_asset": "USDT",
            "interval": "4h",
            "candidate_pool": 30,
            "min_quote_volume": 1_000_000,
            "min_trade_count": 100,
        }

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), scanner)):
            payload = app_main._fallback_scan_payload(params, "完整扫描超时")

        self.assertEqual(payload["summary"]["candidate_pool"], 30)
        self.assertEqual(payload["summary"]["returned_signals"], 30)
        self.assertEqual(len(payload["signals"]), 30)
        self.assertEqual(payload["signals"][0]["symbol"], "TEST00USDT")
        self.assertTrue(all(float(signal["score"]) < 70.0 for signal in payload["signals"]))

    def test_scan_payload_sorts_signals_by_score_descending(self) -> None:
        def signal(symbol: str, score: float, quote_volume: float) -> SimpleNamespace:
            return SimpleNamespace(
                symbol=symbol,
                score=score,
                grade="B",
                reasons=[],
                warnings=[],
                ticker=SimpleNamespace(
                    last_price=100.0,
                    price_change_percent=1.0,
                    quote_volume=quote_volume,
                ),
                indicators=SimpleNamespace(
                    rsi_14=55.0,
                    ema_spread_pct=0.5,
                    volume_ratio=1.2,
                    macd_hist=0.01,
                ),
            )

        scanner = Mock()
        scanner.scan.return_value = (
            {"scanned_symbols": 3, "returned_signals": 3, "quote_asset": "USDT", "interval": "4h", "min_quote_volume": 0},
            [
                signal("MIDUSDT", 72.0, 30_000_000.0),
                signal("HIGHUSDT", 86.0, 10_000_000.0),
                signal("LOWUSDT", 61.0, 50_000_000.0),
            ],
        )
        config = RuntimeConfig()
        with app_main._SCAN_CACHE_LOCK:
            app_main._SCAN_PAYLOAD_CACHE.clear()
            app_main._SCAN_INFLIGHT.clear()
        try:
            with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)):
                payload, _ = _scan_payload({}, force_refresh=True)
        finally:
            with app_main._SCAN_CACHE_LOCK:
                app_main._SCAN_PAYLOAD_CACHE.clear()
                app_main._SCAN_INFLIGHT.clear()

        self.assertEqual([item["symbol"] for item in payload["signals"]], ["HIGHUSDT", "MIDUSDT", "LOWUSDT"])

    def test_render_index_page_supports_table_view_mode(self) -> None:
        html = render_index_page(
            summary={
                "scanned_symbols": 12,
                "returned_signals": 1,
                "eligible_symbols": 42,
                "candidate_symbols": 12,
                "candidate_pool": 12,
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
                    "warnings": ["追高风险", "量能不足", "完整扫描超过 8 秒，已返回实时 ticker 快速结果，后台继续刷新。"],
                    "last_price": 68000.0,
                    "quote_volume_m": 1200.0,
                    "price_change_percent": 2.4,
                    "rsi_14": 58.2,
                    "ema_spread_pct": 1.3,
                    "volume_ratio": 1.8,
                    "macd_hist": 0.0234,
                    "community_score": 76,
                    "community_source": "local",
                    "community_mentions": 240,
                    "community_sentiment": 0.45,
                    "community_summary": "BTC 近端社区消息偏多，主要由 bullish x2 驱动。",
                    "community_drivers": ["bullish x2", "breakout x1"],
                    "community_risks": ["liquidation x1"],
                    "community_samples": ["BTC bullish breakout from tracked account"],
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
        self.assertIn("评分候选", html)
        self.assertIn("流动性合格", html)
        self.assertIn("signal-table", html)
        self.assertIn("BTCUSDT", html)
        self.assertIn("社区热度分析", html)
        self.assertIn('action="/scan/community/update"', html)
        self.assertIn("保存并重扫", html)
        self.assertIn("/terminal/community", html)
        self.assertIn("最新价", html)
        self.assertIn("完整扫描超过 8 秒", html)
        self.assertIn("BTC 近端社区消息偏多", html)
        self.assertIn("BTC bullish breakout from tracked account", html)
        self.assertIn("senti", html)
        self.assertIn("PAGE_SIZE = 15", html)
        self.assertIn('document.querySelectorAll("table.data-table")', html)
        self.assertIn('document.querySelectorAll(".signal-grid")', html)
        self.assertIn("data-live-market", html)
        self.assertIn('data-live-symbol="BTCUSDT"', html)
        self.assertIn("data-live-price", html)
        self.assertIn("data-live-change", html)
        self.assertIn('/static/scan_live.js', html)
        self.assertIn("评分、支撑阻力和波动状态来自最近一次完整扫描", html)

    def test_realtime_market_payload_uses_public_tickers_only(self) -> None:
        gateway = Mock()
        gateway.ticker_prices.return_value = {"BTCUSDT": 63251.1, "ETHUSDT": 3210.5}
        gateway.ticker24hr_symbols.return_value = [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "63251.10",
                "priceChangePercent": "1.25",
                "quoteVolume": "1200000000",
                "volume": "19000",
                "count": 100000,
            },
            {
                "symbol": "ETHUSDT",
                "lastPrice": "3210.50",
                "priceChangePercent": "-0.75",
                "quoteVolume": "800000000",
                "volume": "250000",
                "count": 80000,
            },
        ]
        scanner = SimpleNamespace(gateway=gateway)

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), scanner)):
            payload = app_main._realtime_market_payload({"symbols": ["btcusdt,ETHUSDT,btcusdt"]})

        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["source"], "binance_spot_rest")
        self.assertEqual(payload["requested_symbols"], 2)
        self.assertEqual(payload["returned_symbols"], 2)
        self.assertEqual(payload["items"][0]["price"], 63251.1)
        self.assertEqual(payload["items"][0]["change_pct"], 1.25)
        gateway.order_market_buy.assert_not_called()
        gateway.order_market_sell.assert_not_called()

    def test_realtime_market_symbols_validate_input_and_limit(self) -> None:
        self.assertEqual(
            app_main._realtime_market_symbols({"symbols": ["btcusdt, ETHUSDT", "BTCUSDT"]}),
            ["BTCUSDT", "ETHUSDT"],
        )
        with self.assertRaisesRegex(ValueError, "无效实时行情标的"):
            app_main._realtime_market_symbols({"symbols": ["BTC/USDT"]})
        with self.assertRaisesRegex(ValueError, "最多查询"):
            app_main._realtime_market_symbols(
                {"symbols": [",".join(f"ASSET{index}USDT" for index in range(41))]}
            )

    def test_scan_live_script_has_websocket_reconnect_and_rest_fallback(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "static" / "scan_live.js").read_text(encoding="utf-8")

        self.assertIn("wss://stream.binance.com:9443", script)
        self.assertIn("@miniTicker", script)
        self.assertIn("/api/market/realtime", script)
        self.assertIn("scheduleReconnect", script)
        self.assertNotIn("order_market_buy", script)

    def test_render_index_page_orders_cards_and_table_by_score(self) -> None:
        def signal(symbol: str, score: float) -> dict[str, object]:
            return {
                "symbol": symbol,
                "grade": "B",
                "score": score,
                "reasons": ["reason"],
                "warnings": [],
                "last_price": 100.0,
                "quote_volume_m": 10.0,
                "price_change_percent": 1.0,
                "rsi_14": 55.0,
                "ema_spread_pct": 0.5,
                "volume_ratio": 1.2,
                "macd_hist": 0.01,
                "community_score": None,
                "community_source": None,
                "community_mentions": None,
                "community_sentiment": None,
                "community_summary": "",
                "community_drivers": [],
                "community_risks": [],
                "community_samples": [],
                "breakdown": {"trend": 60, "momentum": 50},
                "sparkline_points": "0,20 80,10 160,4",
            }

        summary = {
            "scanned_symbols": 3,
            "returned_signals": 3,
            "eligible_symbols": 3,
            "candidate_symbols": 3,
            "candidate_pool": 3,
            "quote_asset": "USDT",
            "interval": "4h",
            "min_quote_volume": 0,
        }
        params = {
            "quote_asset": "USDT",
            "interval": "4h",
            "candidate_pool": 5,
            "min_quote_volume": 0,
            "min_trade_count": 0,
            "view_mode": "cards",
        }
        signals = [signal("LOWUSDT", 61.0), signal("HIGHUSDT", 86.0), signal("MIDUSDT", 72.0)]

        cards_html = render_index_page(summary=summary, signals=signals, params=params, intervals=["4h"])
        table_html = render_index_page(summary=summary, signals=signals, params={**params, "view_mode": "table"}, intervals=["4h"])

        self.assertLess(cards_html.find("HIGHUSDT"), cards_html.find("MIDUSDT"))
        self.assertLess(cards_html.find("MIDUSDT"), cards_html.find("LOWUSDT"))
        self.assertLess(table_html.find("HIGHUSDT"), table_html.find("MIDUSDT"))
        self.assertLess(table_html.find("MIDUSDT"), table_html.find("LOWUSDT"))

    def test_render_index_page_shows_token_community_detail_on_cards(self) -> None:
        html = render_index_page(
            summary={
                "scanned_symbols": 12,
                "returned_signals": 1,
                "eligible_symbols": 42,
                "candidate_symbols": 12,
                "candidate_pool": 12,
                "quote_asset": "USDT",
                "interval": "4h",
                "min_quote_volume": 1_000_000,
            },
            signals=[
                {
                    "symbol": "BTCUSDT",
                    "grade": "A",
                    "score": 82.5,
                    "reasons": ["趋势向上"],
                    "warnings": [],
                    "quote_volume_m": 1200.0,
                    "price_change_percent": 2.4,
                    "rsi_14": 58.2,
                    "ema_spread_pct": 1.3,
                    "volume_ratio": 1.8,
                    "macd_hist": 0.0234,
                    "community_score": 76,
                    "community_source": "x+x_accounts",
                    "community_mentions": 240,
                    "community_sentiment": 0.45,
                    "community_summary": "BTC 近端社区消息偏多，主要由 bullish x2 驱动。",
                    "community_drivers": ["bullish x2", "breakout x1"],
                    "community_risks": ["liquidation x1"],
                    "community_samples": ["BTC bullish breakout from tracked account"],
                    "breakdown": {"trend": 80, "momentum": 75, "volume": 70, "community": 76},
                    "sparkline_points": "0,20 80,10 160,4",
                }
            ],
            params={
                "quote_asset": "USDT",
                "interval": "4h",
                "candidate_pool": 5,
                "min_quote_volume": 1_000_000,
                "min_trade_count": 100,
                "view_mode": "cards",
            },
            intervals=["4h"],
        )

        self.assertIn("社区热度分析", html)
        self.assertIn("多头驱动", html)
        self.assertIn("风险过滤", html)
        self.assertIn("BTC bullish breakout from tracked account", html)

    def test_render_index_page_has_pagination_for_large_signal_sets(self) -> None:
        base_signal = {
            "symbol": "BTCUSDT",
            "grade": "A",
            "score": 82.5,
            "reasons": ["趋势向上", "量能放大"],
            "warnings": [],
            "quote_volume_m": 1200.0,
            "price_change_percent": 2.4,
            "rsi_14": 58.2,
            "ema_spread_pct": 1.3,
            "volume_ratio": 1.8,
            "macd_hist": 0.0234,
            "community_score": None,
            "community_source": None,
            "breakdown": {"trend": 80, "momentum": 75, "volume": 70},
            "sparkline_points": "0,20 80,10 160,4",
        }
        signals = [{**base_signal, "symbol": f"TEST{index}USDT"} for index in range(16)]

        html = render_index_page(
            summary={
                "scanned_symbols": 16,
                "returned_signals": 16,
                "eligible_symbols": 40,
                "candidate_symbols": 16,
                "candidate_pool": 16,
                "quote_asset": "USDT",
                "interval": "4h",
                "min_quote_volume": 1_000_000,
            },
            signals=signals,
            params={
                "quote_asset": "USDT",
                "interval": "4h",
                "candidate_pool": 16,
                "min_quote_volume": 1_000_000,
                "min_trade_count": 100,
                "view_mode": "table",
            },
            intervals=["4h"],
        )

        self.assertIn("TEST15USDT", html)
        self.assertIn("table-pagination", html)
        self.assertIn("PAGE_SIZE = 15", html)
        self.assertIn("view_mode=cards", html)

    def test_render_index_page_shows_fast_scan_warning(self) -> None:
        html = render_index_page(
            summary={
                "scanned_symbols": 0,
                "returned_signals": 0,
                "eligible_symbols": 0,
                "candidate_symbols": 0,
                "candidate_pool": 5,
                "quote_asset": "USDT",
                "interval": "4h",
                "min_quote_volume": 1_000_000,
                "fallback": True,
                "warning": "完整扫描超过 8 秒，已返回实时 ticker 快速结果，后台继续刷新。",
            },
            signals=[],
            params={
                "quote_asset": "USDT",
                "interval": "4h",
                "candidate_pool": 5,
                "min_quote_volume": 1_000_000,
                "min_trade_count": 100,
                "view_mode": "cards",
            },
            intervals=["4h"],
        )

        self.assertIn("notice-warning", html)
        self.assertIn("实时 ticker 快速结果", html)
        self.assertIn('data-scan-fallback="true"', html)
        self.assertIn('name="refresh" value="1"', html)

    def test_terminal_payload_returns_fast_snapshot_when_refresh_times_out(self) -> None:
        runtime_config = RuntimeConfig()
        cache_key = app_main._terminal_cache_key(runtime_config)
        app_main._TERMINAL_CACHE.update(
            {
                "key": None,
                "expires_at": datetime.min.replace(tzinfo=timezone.utc),
                "payload": None,
            }
        )
        app_main._TERMINAL_INFLIGHT.clear()

        def slow_refresh(_: tuple[object, ...]) -> dict[str, object]:
            time.sleep(0.2)
            payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "cached": True}
            app_main._store_terminal_payload(cache_key, payload)
            return payload

        fast_payload = {"generated_at": "fast", "cached": False}
        try:
            with patch("trade_signal_app.main.TERMINAL_SYNC_TIMEOUT_SECONDS", 0.02):
                with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(runtime_config, Mock())):
                    with patch("trade_signal_app.main._build_terminal_payload_for_cache", side_effect=slow_refresh):
                        with patch("trade_signal_app.main._fast_terminal_payload", return_value=dict(fast_payload)):
                            started_at = time.monotonic()
                            payload = app_main._terminal_payload()
                            elapsed = time.monotonic() - started_at
        finally:
            time.sleep(0.25)
            app_main._TERMINAL_CACHE.update(
                {
                    "key": None,
                    "expires_at": datetime.min.replace(tzinfo=timezone.utc),
                    "payload": None,
                }
            )
            app_main._TERMINAL_INFLIGHT.clear()

        self.assertLess(elapsed, 0.15)
        self.assertTrue(payload["fallback"])
        self.assertIn("后台刷新", str(payload["warning"]))

    def test_onchain_module_waits_for_api_snapshot_when_refresh_completes(self) -> None:
        runtime_config = RuntimeConfig()
        cache_key = app_main._onchain_module_cache_key(runtime_config)
        app_main._ONCHAIN_MODULE_CACHE.update(
            {
                "key": None,
                "expires_at": datetime.min.replace(tzinfo=timezone.utc),
                "payload": None,
            }
        )
        app_main._ONCHAIN_INFLIGHT.clear()

        def slow_refresh(_: tuple[object, ...]) -> dict[str, object]:
            time.sleep(0.2)
            payload = {
                "module": "onchain",
                "onchain_events": [
                    {
                        "chain": "bitcoin",
                        "symbol": "BTCUSDT",
                        "event_type": "network_snapshot",
                        "amount_usd": 0.0,
                        "direction": "latest_block_txs=25",
                        "severity": 50.0,
                    }
                ],
                "onchain_sources": [{"chain": "bitcoin", "symbol": "BTCUSDT", "source": "blockstream", "status": "api_live"}],
                "blocked_symbols": {},
                "fallback": False,
                "warning": "",
            }
            app_main._store_onchain_module_payload(cache_key, payload)
            return payload

        try:
            with patch("trade_signal_app.main.ONCHAIN_SYNC_TIMEOUT_SECONDS", 0.5):
                with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(runtime_config, Mock())):
                    with patch("trade_signal_app.main._build_onchain_module_payload_for_cache", side_effect=slow_refresh):
                        with patch("trade_signal_app.main._local_onchain_events_payload", return_value=[]):
                            started_at = time.monotonic()
                            payload = app_main._onchain_only_module_payload()
                            elapsed = time.monotonic() - started_at
        finally:
            time.sleep(0.25)
            app_main._ONCHAIN_MODULE_CACHE.update(
                {
                    "key": None,
                    "expires_at": datetime.min.replace(tzinfo=timezone.utc),
                    "payload": None,
                }
            )
            app_main._ONCHAIN_INFLIGHT.clear()

        self.assertGreaterEqual(elapsed, 0.18)
        self.assertFalse(payload["fallback"])
        self.assertEqual(payload["onchain_events"][0]["symbol"], "BTCUSDT")
        self.assertEqual(payload["onchain_sources"][0]["status"], "api_live")

    def test_fast_terminal_payload_uses_onchain_api_snapshot_without_cache(self) -> None:
        runtime_config = RuntimeConfig()
        app_main._ONCHAIN_MODULE_CACHE.update(
            {
                "key": None,
                "expires_at": datetime.min.replace(tzinfo=timezone.utc),
                "payload": None,
            }
        )
        app_main._ONCHAIN_INFLIGHT.clear()
        onchain_payload = {
            "module": "onchain",
            "onchain_events": [
                {
                    "chain": "ethereum",
                    "symbol": "ETHUSDT",
                    "event_type": "network_snapshot",
                    "amount_usd": 0.0,
                    "direction": "latest_block_txs=120",
                    "severity": 55.0,
                    "source": "evm_rpc",
                }
            ],
            "onchain_sources": [{"chain": "ethereum", "symbol": "ETHUSDT", "source": "evm_rpc", "status": "api_live"}],
            "blocked_symbols": {},
            "fallback": False,
            "warning": "",
        }

        try:
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(runtime_config, object())),
                patch("trade_signal_app.main._cached_terminal_payload", return_value=None),
                patch("trade_signal_app.main._platform_payload", return_value={"components": [], "accounts": [], "strategies": [], "risk_rules": [], "recent_events": []}),
                patch("trade_signal_app.main._fast_market_module_payload", return_value={"intel_items": [], "spreads": [], "funding_rates": [], "market_sources": []}),
                patch("trade_signal_app.main._community_only_module_payload", return_value={"twitter_accounts": [], "intel_items": []}),
                patch("trade_signal_app.main._fast_strategies_module_payload", return_value={"strategy_hits": []}),
                patch("trade_signal_app.main._fast_risk_module_payload", return_value={"execution_risk": {"status": "clear", "risk_score": 0.0, "allowed_symbols": [], "blocked_symbols": {}, "summary": "ok"}}),
                patch("trade_signal_app.main._build_onchain_module_payload_for_cache", return_value=onchain_payload),
            ):
                payload = app_main._fast_terminal_payload()
        finally:
            app_main._ONCHAIN_MODULE_CACHE.update(
                {
                    "key": None,
                    "expires_at": datetime.min.replace(tzinfo=timezone.utc),
                    "payload": None,
                }
            )
            app_main._ONCHAIN_INFLIGHT.clear()

        self.assertEqual(payload["onchain_events"][0]["symbol"], "ETHUSDT")
        self.assertEqual(payload["onchain_sources"][0]["status"], "api_live")
        self.assertEqual(payload["llm_insight"]["status"], "local_rules")
        self.assertIn("market_state", payload["llm_insight"])
        self.assertIn("actions", payload["llm_insight"])

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

    def test_backtest_payload_runs_bounded_parameter_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)
            payload, params, error = _backtest_payload(
                {
                    "archives": [str(archive)],
                    "score_threshold": ["60"],
                    "stop_loss_pct": ["4"],
                    "portfolio_top_n": ["0"],
                    "min_volume_ratio": ["1.0"],
                    "min_buy_pressure": ["0.5"],
                    "max_rsi": ["99"],
                    "no_kdj_confirmation": ["1"],
                    "parameter_sweep": ["on"],
                }
            )

        self.assertIsNone(error)
        self.assertTrue(params["parameter_sweep"])
        self.assertEqual(len(payload["parameter_sweep"]), 9)
        self.assertEqual({item["score_threshold"] for item in payload["parameter_sweep"]}, {56.0, 60.0, 64.0})
        self.assertEqual({item["stop_loss_pct"] for item in payload["parameter_sweep"]}, {3.0, 4.0, 5.0})
        self.assertEqual(sum(1 for item in payload["parameter_sweep"] if item["base_cell"]), 1)
        self.assertTrue(all(item["scope"] == "first_series_full_history" for item in payload["parameter_sweep"]))
        self.assertTrue(payload["strategy_explanation"]["parameter_sweep_enabled"])
        self.assertIsNotNone(payload["strategy_explanation"]["best_parameter_cell"])

    def test_backtest_payload_uses_selected_local_cache_for_submitted_empty_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)
            archive_path = archive.resolve()
            selected_cache = "data/tradingview_klines/BINANCE/BTCUSDT/4h.csv"

            def fake_resolve(inputs: list[str]) -> list[Path]:
                if inputs == [selected_cache]:
                    return [archive_path]
                return [archive_path] if str(archive_path) in inputs else []

            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)),
                patch("trade_signal_app.main_backtest.resolve_archive_paths", side_effect=fake_resolve),
            ):
                payload, params, error = _backtest_payload(
                    {
                        "lookback_bars": ["120"],
                        "score_threshold": ["60"],
                        "portfolio_top_n": ["0"],
                    }
                )

        self.assertIsNone(error)
        self.assertEqual(params["archives"], selected_cache)
        self.assertEqual(len(payload["series_reports"]), 1)

    def test_backtest_background_job_returns_status_and_reuses_completed_result(self) -> None:
        payload = {
            "series_reports": [],
            "portfolio_reports": [],
            "rebalance_reports": [],
            "parameter_sweep": [],
            "performance": {"total_seconds": 0.25, "candle_count": 180},
            "strategy_explanation": {},
        }
        params = {"archives": "sample.csv", "preset": "balanced_swing"}
        with app_main._BACKTEST_JOB_LOCK:
            app_main._BACKTEST_JOBS.clear()
            app_main._BACKTEST_JOB_RESULTS.clear()

        try:
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), SimpleNamespace(gateway=object()))),
                patch("trade_signal_app.main.backtest_handlers._backtest_payload", return_value=(payload, params, None)),
                patch("trade_signal_app.main._record_backtest_run") as record_run,
            ):
                submitted = app_main._start_backtest_job({"archives": ["sample.csv"]})
                deadline = time.monotonic() + 2.0
                status = submitted
                while status["status"] in {"queued", "running"} and time.monotonic() < deadline:
                    time.sleep(0.01)
                    status = app_main._backtest_job_status(str(submitted["job_id"])) or {}

                result = _backtest_payload({"job_id": [str(submitted["job_id"])]})

            self.assertEqual(status["status"], "completed")
            self.assertTrue(status["result_available"])
            self.assertEqual(status["performance"]["candle_count"], 180)
            self.assertIn(f"job_id={submitted['job_id']}", status["redirect_url"])
            self.assertEqual(result, (payload, params, None))
            record_run.assert_called_once_with(params, payload, None)
        finally:
            with app_main._BACKTEST_JOB_LOCK:
                app_main._BACKTEST_JOBS.clear()
                app_main._BACKTEST_JOB_RESULTS.clear()

    def test_backtest_background_job_rejects_an_unbounded_active_queue(self) -> None:
        with app_main._BACKTEST_JOB_LOCK:
            app_main._BACKTEST_JOBS.clear()
            app_main._BACKTEST_JOB_RESULTS.clear()
            for index in range(app_main.BACKTEST_JOB_ACTIVE_LIMIT):
                app_main._BACKTEST_JOBS[str(index)] = {"status": "queued", "_query_key": str(index)}

        try:
            with self.assertRaisesRegex(ValueError, "回测任务正在执行或排队"):
                app_main._start_backtest_job({"archives": ["new.csv"]})
        finally:
            with app_main._BACKTEST_JOB_LOCK:
                app_main._BACKTEST_JOBS.clear()
                app_main._BACKTEST_JOB_RESULTS.clear()

    def test_backtest_payload_reports_timing_and_reuses_manual_fee_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)
            query = {
                "archives": [str(archive)],
                "lookback_bars": ["120"],
                "score_threshold": ["60"],
                "portfolio_top_n": ["0"],
                "fee_source": ["manual"],
            }
            with main_backtest._BACKTEST_RESULT_CACHE_LOCK:
                main_backtest._BACKTEST_RESULT_CACHE.clear()

            first, _, first_error = _backtest_payload(query)
            second, _, second_error = _backtest_payload(query)

        self.assertIsNone(first_error)
        self.assertIsNone(second_error)
        self.assertFalse(first["performance"]["cache_hit"])
        self.assertTrue(second["performance"]["cache_hit"])
        self.assertEqual(first["performance"]["candle_count"], 180)
        self.assertGreaterEqual(first["performance"]["series_backtest_seconds"], 0.0)
        self.assertLess(second["performance"]["total_seconds"], first["performance"]["total_seconds"])

    def test_backtest_payload_diagnoses_history_shorter_than_lookback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            _build_archive(archive)
            with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)):
                payload, _, error = _backtest_payload(
                    {
                        "archives": [str(archive)],
                        "lookback_bars": ["240"],
                        "score_threshold": ["60"],
                        "portfolio_top_n": ["0"],
                    }
                )

        diagnostics = " ".join(payload["strategy_explanation"]["diagnostics"])
        self.assertIsNone(error)
        self.assertIn("只有 180 根 K 线", diagnostics)
        self.assertIn("低于当前 lookback 240", diagnostics)

    def test_backtest_payload_keeps_candles_before_sample_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "BTCUSDT-4h-2026-07.zip"
            sample_start_utc = datetime(2026, 7, 6, 0, 0, tzinfo=timezone.utc)
            _build_archive(archive, start=sample_start_utc - timedelta(hours=16))
            payload, _, error = _backtest_payload(
                {
                    "archives": [str(archive)],
                    "lookback_bars": ["80"],
                    "score_threshold": ["60"],
                    "holding_periods": ["3,6"],
                    "portfolio_top_n": ["0"],
                    "min_volume_ratio": ["1.0"],
                    "min_buy_pressure": ["0.5"],
                    "max_rsi": ["99"],
                    "no_kdj_confirmation": ["1"],
                }
            )

        self.assertIsNone(error)
        report = payload["series_reports"][0]
        self.assertEqual(report["candle_count"], 180)
        diagnostics = " ".join(payload["strategy_explanation"]["diagnostics"])
        self.assertNotIn("已排除", diagnostics)
        notes = " ".join(payload["strategy_explanation"]["notes"])
        self.assertIn("全部历史 K 线", notes)

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
        self.assertIn("结果分析看板", html)
        self.assertIn("等待历史 K 线", html)
        self.assertIn("回测工作台", html)
        self.assertIn("ant-tabs module-tabs", html)
        self.assertIn('href="#backtest-analysis"', html)
        self.assertIn('id="backtest-portfolio"', html)
        self.assertIn("backtest-command-grid", html)
        self.assertIn("Series Equity Rank", html)
        self.assertIn("策略解释", html)
        self.assertIn("稳定性检查", html)
        self.assertIn("均衡波段模板", html)
        self.assertIn("Stability Checks", html)
        self.assertIn("Parameter Sweep", html)
        self.assertIn('id="backtest-sensitivity"', html)
        self.assertIn("风险收益地图", html)
        self.assertIn("参数热力图尚未运行", html)
        self.assertIn("/api/backtest/export?format=csv", html)
        self.assertIn("/api/backtest/export?format=html", html)
        self.assertIn("Balanced Swing", html)
        self.assertIn("/api/backtest/presets", html)
        self.assertIn("data-backtest-job-status", html)
        self.assertIn('src="/static/backtest.js"', html)
        self.assertIn("等待单币种回测结果", html)
        self.assertIn("切换到再平衡模板后显示", html)
        self.assertIn("切换到加密资产等权再平衡", html)
        self.assertIn('max="100000" step="100" name="tradingview_bars" value="10000"', html)
        for description in BACKTEST_ADVANCED_HELP.values():
            self.assertIn(description, html)

    def test_backtest_empty_portfolio_and_rebalance_cards_explain_next_steps(self) -> None:
        portfolio_html = _portfolio_card(
            {
                "interval": "4h",
                "top_n": 2,
                "symbol_count": 1,
                "batch_count": 0,
                "pick_count": 0,
                "score_threshold": 70.0,
            }
        )
        self.assertIn("暂无可执行组合批次", portfolio_html)
        self.assertIn("Symbols = 1", portfolio_html)
        self.assertIn("调整数据和参数", portfolio_html)

        rebalance_html = _rebalance_empty_card(
            {"preset": "crypto_rebalance_premium"},
            [{"symbol": "BTCUSDT", "interval": "4h"}],
        )
        self.assertIn("再平衡样本不足", rebalance_html)
        self.assertIn("补充多币种同周期数据", rebalance_html)

    def test_benchmark_workbench_does_not_draw_fake_equity_curve(self) -> None:
        html = _benchmark_workbench(
            [
                {
                    "symbol": "BTCUSDT",
                    "interval": "4h",
                    "final_equity": 1.23,
                    "buy_hold_final_equity": 1.08,
                    "events": [],
                    "trade_stat": {},
                }
            ]
        )

        self.assertIn("基准测试曲线不足", html)
        self.assertIn("避免展示伪造走势", html)
        self.assertNotIn("benchmark-line strategy", html)
        self.assertNotIn("benchmark-chart", html)
        self.assertNotIn("<svg", html)

    def test_benchmark_workbench_draws_only_real_equity_points(self) -> None:
        html = _benchmark_workbench(
            [
                {
                    "symbol": "BTCUSDT",
                    "interval": "4h",
                    "final_equity": 1.23,
                    "buy_hold_final_equity": 1.08,
                    "equity_points": [1.0, 1.05, 1.23],
                    "buy_hold_equity_points": [1.0, 1.02, 1.08],
                    "events": [],
                    "trade_stat": {},
                }
            ]
        )

        self.assertIn("账户总价值", html)
        self.assertIn("benchmark-line strategy", html)
        self.assertIn("benchmark-line hold", html)
        self.assertNotIn("基准测试曲线不足", html)

    def test_parameter_heatmap_and_risk_scatter_use_real_results(self) -> None:
        sweep = []
        for stop in (3.0, 4.0, 5.0):
            for score in (66.0, 70.0, 74.0):
                sweep.append(
                    {
                        "symbol": "BTCUSDT",
                        "interval": "4h",
                        "status": "ok",
                        "score_threshold": score,
                        "stop_loss_pct": stop,
                        "base_cell": score == 70.0 and stop == 4.0,
                        "final_equity": 1.0 + ((74.0 - score + stop) / 100),
                        "return_pct": 74.0 - score + stop,
                        "max_drawdown_pct": -stop,
                        "profit_factor": 1.4,
                        "signal_count": 12,
                        "risk_adjusted_return": (74.0 - score + stop) / stop,
                    }
                )

        heatmap = _parameter_heatmap({"parameter_sweep": True}, sweep)
        scatter = _risk_return_scatter(
            [
                {
                    "symbol": "BTCUSDT",
                    "interval": "4h",
                    "final_equity": 1.12,
                    "max_drawdown_pct": -4.0,
                    "signal_count": 12,
                    "trade_stat": {"trade_count": 12, "win_rate_pct": 58.0, "profit_factor": 1.4},
                },
                {
                    "symbol": "ETHUSDT",
                    "interval": "4h",
                    "final_equity": 0.96,
                    "max_drawdown_pct": -7.5,
                    "signal_count": 8,
                    "trade_stat": {"trade_count": 8, "win_rate_pct": 37.5, "profit_factor": 0.8},
                }
            ],
            [
                {
                    "top_n": 2,
                    "interval": "4h",
                    "final_equity": 1.08,
                    "max_drawdown_pct": -3.0,
                    "batch_count": 6,
                    "trade_stat": {"trade_count": 6, "win_rate_pct": 66.7, "profit_factor": 1.6},
                }
            ],
        )

        self.assertIn("parameter-heatmap", heatmap)
        self.assertIn("base-cell", heatmap)
        self.assertIn("+11.00%", heatmap)
        self.assertIn("risk-return-chart", scatter)
        self.assertIn("chart-opportunity-zone", scatter)
        self.assertIn("chart-grid-line", scatter)
        self.assertIn("risk-return-summary", scatter)
        self.assertIn("risk-return-results", scatter)
        self.assertIn("横向滑动查看完整风险区间", scatter)
        self.assertIn("风险效率最佳", scatter)
        self.assertIn("收益 +12.00%", scatter)
        self.assertIn("portfolio", scatter)
        self.assertIn("交易 / PF", scatter)

    def test_render_settings_page_includes_runtime_controls(self) -> None:
        html = render_settings_page(
            params={
                "binance_recv_window_ms": 5000.0,
                "market_data_preset": "binance_public",
                "tradingview_username": "",
                "tradingview_exchange": "BINANCE",
                "tradingview_symbols": ["BTCUSDT", "ETHUSDT"],
                "tradingview_interval": "4h",
                "tradingview_bars": 5000,
                "tradingview_cache_enabled": True,
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
                "feishu_webhook_configured": True,
                "x_account_mode": "blend",
                "x_account_weight_pct": 35.0,
                "x_tracked_accounts": ["lookonchain", "wu_blockchain"],
                "scan_quote_asset": "USDT",
                "scan_interval": "4h",
                "scan_candidate_pool": 18,
                "scan_min_quote_volume": 10_000_000,
                "scan_min_trade_count": 3000,
                "scan_btc_min_quote_volume": 100_000_000,
                "scan_btc_min_trade_count": 50_000,
                "scan_eth_min_quote_volume": 80_000_000,
                "scan_eth_min_trade_count": 40_000,
                "scan_xrp_min_quote_volume": 30_000_000,
                "scan_xrp_min_trade_count": 15_000,
                "scan_sol_min_quote_volume": 50_000_000,
                "scan_sol_min_trade_count": 25_000,
                "scan_bnb_min_quote_volume": 30_000_000,
                "scan_bnb_min_trade_count": 15_000,
                "scan_top30_min_quote_volume": 15_000_000,
                "scan_top30_min_trade_count": 5000,
                "autotrade_enabled": False,
                "autotrade_mode": "paper",
                "autotrade_paper_enabled": False,
                "autotrade_live_enabled": False,
                "autotrade_execution_exchange": "binance",
                "autotrade_quote_order_qty": 25.0,
                "autotrade_max_open_positions": 3,
                "autotrade_max_total_quote_exposure": 100.0,
                "autotrade_score_threshold": 75.0,
                "autotrade_min_volume_ratio": 1.1,
                "autotrade_min_buy_pressure": 0.52,
                "autotrade_anti_chase_enabled": True,
                "autotrade_max_entry_rsi": 72.0,
                "autotrade_max_entry_price_vs_ema20_pct": 5.0,
                "autotrade_max_entry_recent_change_pct": 4.0,
                "autotrade_structure_filter_enabled": True,
                "autotrade_max_entry_support_distance_pct": 2.5,
                "autotrade_min_entry_support_strength": 2.0,
                "autotrade_min_entry_risk_reward_ratio": 1.4,
                "autotrade_min_entry_resistance_distance_pct": 2.0,
                "autotrade_support_stop_buffer_pct": 0.6,
                "autotrade_resistance_take_profit_buffer_pct": 0.4,
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
                "okx_auth_partial": True,
                "okx_auth_status": "partial_configured",
                "okx_auth_label": "部分配置",
                "okx_auth_message": "OKX 凭据已部分保存，缺少：Passphrase",
                "x_auth_configured": True,
                "x_provider": "official_api",
                "x_provider_configured": True,
                "tracked_account_count": 2,
                "tradingview_auth_configured": False,
                "tradingview_cache_dir": "data/tradingview_klines",
                "storage_mode": "Encrypted",
                "autotrade_enabled": False,
                "autotrade_mode": "paper",
                "autotrade_paper_enabled": False,
                "autotrade_live_enabled": False,
                "feishu_webhook_configured": True,
                "intelligence_enabled": True,
                "llm_enabled": False,
                "llm_provider": "openai",
                "llm_configured": False,
                "public_data_presets": [
                    {"preset_id": "binance_public", "name": "Binance Public Market Data", "category": "market"},
                    {"preset_id": "tradingview_unofficial", "name": "TradingView Unofficial", "category": "market"},
                    {"preset_id": "defillama_free", "name": "DefiLlama Free API", "category": "onchain"},
                ],
                "llm_provider_presets": [
                    {"provider_id": "openai", "name": "OpenAI", "base_url": "https://api.openai.com/v1", "default_model": "gpt-5.5"},
                    {"provider_id": "anthropic", "name": "Anthropic Claude", "base_url": "https://api.anthropic.com/v1", "default_model": "claude-sonnet-4-6"},
                    {"provider_id": "google", "name": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "default_model": "gemini-3.5-flash"},
                    {"provider_id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"},
                    {"provider_id": "xai", "name": "xAI Grok", "base_url": "https://api.x.ai/v1", "default_model": "grok-4"},
                    {"provider_id": "mistral", "name": "Mistral AI", "base_url": "https://api.mistral.ai/v1", "default_model": "mistral-large-latest"},
                    {"provider_id": "qwen", "name": "Alibaba Qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "default_model": "qwen-plus"},
                    {"provider_id": "moonshot", "name": "Moonshot Kimi", "base_url": "https://api.moonshot.cn/v1", "default_model": "kimi-k2-latest"},
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
        self.assertIn("TradingView Username", html)
        self.assertIn("TradingView Symbols", html)
        self.assertIn('max="100000" step="100" name="tradingview_bars" value="5000"', html)
        self.assertIn("Enable anti-chase filter", html)
        self.assertIn("Enable paper trading", html)
        self.assertIn("Enable live trading", html)
        self.assertIn("Max EMA20 Deviation %", html)
        self.assertIn("Enable structure filter", html)
        self.assertIn("Min Structure R/R", html)
        self.assertIn("TradingView 为非官方补充源", html)
        self.assertIn("On-chain Data Preset", html)
        self.assertIn("DefiLlama", html)
        self.assertIn("LLM Provider", html)
        self.assertIn("ant-tabs module-tabs", html)
        self.assertIn('href="#settings-llm"', html)
        self.assertIn('id="settings-transfer"', html)
        self.assertIn('data-llm-provider-select', html)
        self.assertIn('data-default-base-url="https://api.deepseek.com/v1"', html)
        self.assertIn('data-default-model="deepseek-chat"', html)
        self.assertIn('data-llm-base-url', html)
        self.assertIn('data-llm-model', html)
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
        self.assertIn("Feishu Webhook URL", html)
        self.assertIn("Clear Feishu webhook", html)
        self.assertIn("买入成交和卖出执行后", html)
        self.assertIn("运行配置已保存", html)
        self.assertIn("导出模板 JSON", html)
        self.assertIn("导入配置模板", html)
        self.assertIn("OKX 凭据已部分保存，缺少：Passphrase", html)
        self.assertIn("2 个 X 跟踪账号", html)
        self.assertIn("Reddit API Base URL", html)
        self.assertIn("Reddit User-Agent", html)
        self.assertIn("Default Preset", html)
        self.assertIn("均衡波段 · balanced_swing", html)
        self.assertIn("加密资产等权再平衡 · crypto_rebalance_premium", html)
        self.assertIn("Auto Trade Defaults", html)
        self.assertIn("分类流动性门槛", html)
        self.assertIn("防守均衡推荐", html)
        self.assertIn("其他山寨币 5M/30K", html)
        self.assertIn("实际买入仍需通过评分、量比、买压、反追高、支撑结构与波动率过滤", html)
        self.assertIn('name="scan_btc_min_quote_volume" value="100000000"', html)
        self.assertIn('name="scan_top30_min_trade_count" value="5000"', html)
        self.assertIn("其他山寨币最低24H成交额", html)
        self.assertIn("Intelligence & LLM", html)
        self.assertIn("settings-section-form", html)
        self.assertIn("保存访问凭据", html)
        self.assertIn("保存回测默认值", html)
        self.assertEqual(html.count('name="settings_section"'), 6)
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
                "llm_insight": {
                    "provider": "local",
                    "model": "rules",
                    "status": "local_rules",
                    "analysis_mode": "local_rules",
                    "market_state": "机会可执行：策略命中已通过当前执行前风控。",
                    "summary": "综合监控正常。",
                    "metrics": {"strategy_hits": 1, "risk_score": 22.0},
                    "opportunities": [
                        {
                            "symbol": "BTCUSDT",
                            "action": "watch",
                            "score": 82.0,
                            "source": "auto_score_breakout",
                            "reason": "趋势结构改善",
                        }
                    ],
                    "risks": [
                        {
                            "symbol": "BTCUSDT",
                            "level": "monitor",
                            "source": "onchain",
                            "reason": "链上异动需复核",
                        }
                    ],
                    "actions": [
                        {
                            "priority": "medium",
                            "action": "用 paper 模式执行允许候选",
                            "reason": "当前允许候选：BTCUSDT。",
                        }
                    ],
                },
                "execution_risk": {
                    "status": "clear",
                    "risk_score": 22.0,
                    "allowed_symbols": ["BTCUSDT"],
                    "blocked_symbols": {},
                    "risk_factors": [
                        {
                            "source": "strategy",
                            "symbol": "BTCUSDT",
                            "factor": "market_momentum_watch",
                            "value": 82.0,
                            "severity": 18.0,
                            "decision": "allow",
                            "reason": "策略候选进入执行前风控",
                        }
                    ],
                    "summary": "执行前风控：允许 1 个候选。",
                },
                "btc_trading": self._btc_trading_fixture(),
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
        self.assertIn("数据源状态", html)
        self.assertIn("异动明细", html)
        self.assertIn("现货 / 合约价差", html)
        self.assertIn("BTC交易专区", html)
        self.assertIn("BTC累计成交", html)
        self.assertIn("btc_regime_trend_pullback_buy", html)
        self.assertIn("策略命中", html)
        self.assertIn("大模型分析", html)
        self.assertIn("机会判断", html)
        self.assertIn("风险提示", html)
        self.assertIn("执行建议", html)
        self.assertIn("机会可执行", html)
        self.assertIn("执行前风控", html)
        self.assertIn("风险因子明细", html)
        self.assertIn("允许候选", html)
        self.assertIn("功能实现状态", html)
        self.assertIn("交易账户概览", html)
        self.assertIn("策略目录", html)
        self.assertIn('href="/terminal/market"', html)
        self.assertIn('href="/terminal/community"', html)
        self.assertIn('href="/terminal/trading"', html)
        self.assertIn("2026-04-28 08:00:00", html)
        self.assertNotIn("2026-04-28T00:00:00+00:00", html)

    def test_fast_market_module_payload_uses_live_exchange_interfaces(self) -> None:
        config = RuntimeConfig()
        config.intelligence_defaults.min_spread_bps = 10.0

        class FakeBinanceGateway:
            def ticker24hr_symbols(self, symbols):
                self.symbols = symbols
                return [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "100",
                        "priceChangePercent": "2.5",
                        "quoteVolume": "120000000",
                        "volume": "1200",
                        "count": "1000",
                    }
                ]

        class FakeOKXGateway:
            def ticker24hr_symbols(self, symbols):
                self.symbols = symbols
                return [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "101",
                        "priceChangePercent": "1.2",
                        "quoteVolume": "80000000",
                        "volume": "790",
                        "count": "0",
                    }
                ]

        funding = FundingRateSnapshot(
            symbol="BTCUSDT",
            futures_exchange="BINANCE-PERP",
            funding_rate=0.0002,
            funding_rate_bps=2.0,
            annualized_pct=21.9,
            mark_price=100.8,
            index_price=100.6,
            next_funding_time="2026-07-04T16:00:00+00:00",
            source="binance_futures_public",
        )

        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, SimpleNamespace(gateway=FakeBinanceGateway()))),
            patch("trade_signal_app.main._okx_gateway", return_value=FakeOKXGateway()),
            patch("trade_signal_app.main.IntelligenceHub._fetch_binance_funding_rate", side_effect=lambda symbol: funding if symbol == "BTCUSDT" else None),
        ):
            payload = _fast_market_module_payload()

        self.assertEqual(payload["module"], "market")
        self.assertGreaterEqual(len(payload["intel_items"]), 2)
        self.assertEqual({item["source"] for item in payload["market_sources"]}, {"binance", "okx"})
        self.assertEqual(payload["funding_rates"][0]["source"], "binance_futures_public")
        self.assertEqual(payload["spreads"][0]["symbol"], "BTCUSDT")
        self.assertAlmostEqual(payload["spreads"][0]["spread_bps"], 80.0)
        self.assertTrue(any("Binance BTCUSDT 最新价" in item["title"] for item in payload["intel_items"]))

    def test_community_module_payload_uses_live_exchange_intel_when_csv_empty(self) -> None:
        config = RuntimeConfig()
        config.intelligence_defaults.min_intel_severity = 60.0

        class FakeCommunityProvider:
            def prepare(self, symbols):
                self.symbols = symbols

            def get(self, symbol):
                return None

        class FakeBinanceGateway:
            def ticker24hr_symbols(self, symbols):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "100",
                        "priceChangePercent": "4.5",
                        "quoteVolume": "500000000",
                        "volume": "5000",
                        "count": "1000",
                    }
                ]

        class FakeOKXGateway:
            def ticker24hr_symbols(self, symbols):
                return [
                    {
                        "symbol": "ETHUSDT",
                        "lastPrice": "200",
                        "priceChangePercent": "-3.0",
                        "quoteVolume": "250000000",
                        "volume": "1250",
                        "count": "0",
                    }
                ]

        scanner = SimpleNamespace(gateway=FakeBinanceGateway(), community_provider=FakeCommunityProvider())
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
            patch("trade_signal_app.main._okx_gateway", return_value=FakeOKXGateway()),
            patch("trade_signal_app.main.IntelligenceHub._read_exchange_intel_csv", return_value=[]),
            patch("trade_signal_app.main.IntelligenceHub._fetch_binance_funding_rate", return_value=None),
        ):
            payload = app_main._community_only_module_payload()

        self.assertEqual(payload["module"], "community")
        self.assertGreaterEqual(len(payload["intel_items"]), 2)
        self.assertTrue(any("Binance BTCUSDT 最新价" in item["title"] for item in payload["intel_items"]))
        self.assertTrue(any("OKX ETHUSDT 最新价" in item["title"] for item in payload["intel_items"]))
        self.assertEqual({item["source"] for item in payload["market_sources"]}, {"binance", "okx"})

    def test_fast_strategies_module_builds_hits_from_live_ticker_without_scan_cache(self) -> None:
        config = RuntimeConfig()
        config.scan_defaults.min_quote_volume = 1_000_000
        config.scan_defaults.min_trade_count = 1

        class FakeBinanceGateway:
            def ticker24hr_symbols(self, symbols):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "101",
                        "priceChangePercent": "8.5",
                        "quoteVolume": "180000000",
                        "volume": "1800",
                        "count": "120000",
                    }
                ]

        scanner = SimpleNamespace(gateway=FakeBinanceGateway())
        app_main._SCAN_PAYLOAD_CACHE.clear()
        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
            patch("trade_signal_app.main._cached_terminal_payload", return_value=None),
            patch(
                "trade_signal_app.main._platform_payload",
                return_value={"strategies": [{"strategy_id": "market_momentum_watch", "name": "行情动量观察"}]},
            ),
            patch(
                "trade_signal_app.main._realtime_market_sections",
                return_value={
                    "funding_rates": [
                        {
                            "symbol": "BTCUSDT",
                            "funding_rate": 0.0003,
                            "funding_rate_bps": 3.0,
                            "annualized_pct": 32.85,
                        }
                    ],
                    "spreads": [{"symbol": "BTCUSDT", "spread_bps": 12.5}],
                    "warning": "",
                },
            ),
        ):
            payload = app_main._fast_strategies_module_payload()

        self.assertGreaterEqual(len(payload["strategy_hits"]), 1)
        hit = payload["strategy_hits"][0]
        self.assertEqual(hit["symbol"], "BTCUSDT")
        self.assertEqual(hit["source"], "live_ticker")
        self.assertIn(
            hit["strategy"],
            {"auto_score_breakout", "market_momentum_watch", "blowoff_distribution_short"},
        )
        self.assertEqual(hit["funding_rate_bps"], 3.0)
        self.assertEqual(hit["spread_bps"], 12.5)

    def test_fast_risk_module_builds_live_decision_without_terminal_cache(self) -> None:
        config = RuntimeConfig()
        config.intelligence_defaults.min_spread_bps = 10.0
        market_payload = {
            "spreads": [
                {"symbol": "BTCUSDT", "spread_bps": 120.0},
                {"symbol": "XRPUSDT", "spread_bps": 8.0},
            ],
            "funding_rates": [
                {"symbol": "BTCUSDT", "funding_rate": 0.0002, "funding_rate_bps": 2.0},
                {"symbol": "XRPUSDT", "funding_rate": -0.0001, "funding_rate_bps": -1.0},
            ],
            "warning": "",
        }
        strategies_payload = {
            "strategy_hits": [
                {"symbol": "BTCUSDT", "strategy": "market_momentum_watch", "score": 74.0},
                {"symbol": "XRPUSDT", "strategy": "market_momentum_watch", "score": 66.0},
            ],
            "warning": "",
        }
        onchain_payload = {
            "onchain_events": [
                {
                    "symbol": "DOGEUSDT",
                    "event_type": "exchange_inflow",
                    "direction": "exchange_inflow",
                    "severity": 92.0,
                    "amount_usd": 8_000_000.0,
                }
            ],
            "warning": "",
        }

        with (
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, object())),
            patch("trade_signal_app.main._cached_terminal_payload", return_value=None),
            patch("trade_signal_app.main._platform_payload", return_value={"risk_rules": []}),
        ):
            payload = app_main._fast_risk_module_payload(
                market_payload=market_payload,
                strategies_payload=strategies_payload,
                onchain_payload=onchain_payload,
            )

        risk = payload["execution_risk"]
        self.assertEqual(risk["status"], "caution")
        self.assertIn("XRPUSDT", risk["allowed_symbols"])
        self.assertIn("BTCUSDT", risk["blocked_symbols"])
        self.assertIn("DOGEUSDT", risk["blocked_symbols"])
        self.assertGreaterEqual(len(risk["risk_factors"]), 5)
        self.assertIn("策略候选", risk["summary"])

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
                    "accounts": [
                        {
                            "exchange": "BINANCE",
                            "mode": "paper",
                            "status": "paper_ready",
                            "open_positions": 0,
                            "quote_exposure": 0.0,
                            "total_trades": 8,
                            "closed_trades": 4,
                            "win_rate_pct": 75.0,
                            "profit_loss_ratio": 2.5,
                            "profit_factor": 3.0,
                            "realized_pnl": 16.0,
                        }
                    ],
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
                "open_positions": [
                    {
                        "symbol": "BTCUSDT",
                        "quantity": 0.25,
                        "entry_price": 100.0,
                        "last_price": 112.0,
                        "quote_notional": 25.0,
                        "current_notional": 28.0,
                        "unrealized_pnl": 3.0,
                        "unrealized_pnl_pct": 12.0,
                        "score": 82.0,
                        "grade": "A",
                        "opened_at": "2026-04-28T00:00:00+00:00",
                        "stop_price": 96.0,
                        "take_profit_price": 109.0,
                        "mode": "paper",
                        "client_order_id": "aitrade-paper-btcusdt-1",
                    }
                ],
                "events": [],
                "account_metrics": {
                    "total_trades": 8,
                    "buy_trades": 4,
                    "sell_trades": 4,
                    "closed_trades": 4,
                    "winning_trades": 3,
                    "losing_trades": 1,
                    "breakeven_trades": 0,
                    "win_rate_pct": 75.0,
                    "profit_loss_ratio": 2.5,
                    "profit_factor": 3.0,
                    "realized_pnl": 16.0,
                    "unrealized_pnl": 3.0,
                    "total_pnl": 19.0,
                },
                "btc_trading": self._btc_trading_fixture(),
            },
            message="模拟量化交易已执行",
            paper_auto_status={
                "running": False,
                "interval_seconds": 300,
                "run_count": 0,
                "last_run_at": None,
                "last_error": "",
            },
        )

        self.assertIn("模拟账户执行", html)
        self.assertIn('action="/terminal/trading/run"', html)
        self.assertIn("运行模拟量化交易", html)
        self.assertIn("策略信号自动交易", html)
        self.assertIn("BTC交易专区", html)
        self.assertIn("BTC累计成交", html)
        self.assertIn("btc_regime_trend_pullback_buy", html)
        self.assertIn('action="/terminal/trading/auto/start"', html)
        self.assertIn('action="/terminal/trading/auto/stop"', html)
        self.assertIn("启动自动策略交易", html)
        self.assertIn("累计成交次数", html)
        self.assertIn("盈亏比", html)
        self.assertIn("75.0%", html)
        self.assertIn("收益率", html)
        self.assertIn("+12.00%", html)
        self.assertIn('sidebar-link active" href="/terminal/trading"', html)
        self.assertNotIn("terminal-sidebar", html)

    def test_render_terminal_community_module_exposes_monitor_configuration(self) -> None:
        html = render_terminal_module_page(
            snapshot={
                "generated_at": "2026-04-28T00:00:00+00:00",
                "scanned_symbols": 12,
                "returned_signals": 4,
                "intel_items": [],
                "twitter_accounts": [{"username": "lookonchain", "focus": "链上异动", "mode": "off", "weight_pct": 35.0, "status": "nitter_missing"}],
                "onchain_events": [],
                "spreads": [],
                "strategy_hits": [],
                "llm_insight": {"provider": "local", "model": "rules", "status": "ok", "summary": "综合监控正常。"},
                "execution_risk": {"status": "clear", "risk_score": 22.0, "allowed_symbols": [], "blocked_symbols": {}, "summary": "执行前风控正常。"},
                "platform": {"generated_at": "2026-04-28T00:00:00+00:00", "components": [], "accounts": [], "strategies": [], "risk_rules": [], "recent_events": []},
            },
            module="community",
        )

        self.assertIn("Twitter 账户监控", html)
        self.assertIn("开启/配置账户监控", html)
        self.assertIn("/settings#settings-twitter", html)
        self.assertIn("/api/terminal/community", html)

    def test_render_terminal_basis_module_reads_carry_paper_snapshot(self) -> None:
        html = render_terminal_module_page(
            snapshot={
                "scanned_symbols": 0,
                "intel_items": [],
                "twitter_accounts": [],
                "onchain_events": [],
                "spreads": [],
                "funding_rates": [],
                "strategy_hits": [],
                "execution_risk": {
                    "status": "clear",
                    "risk_score": 0.0,
                    "allowed_symbols": [],
                    "blocked_symbols": {},
                    "summary": "执行前风控正常。",
                },
                "platform": {"accounts": [], "strategies": [], "risk_rules": [], "recent_events": []},
                "carry_paper": {
                    "enabled": False,
                    "config": {"min_basis_bps": 25.0, "min_funding_bps": 1.0},
                    "metrics": {"open_positions": 0, "gross_exposure": 0.0, "realized_pnl": 0.0},
                    "open_positions": [],
                    "recent_events": [],
                },
            },
            module="basis",
        )

        self.assertIn("Carry 双腿模拟", html)
        self.assertIn("已关闭", html)
        self.assertIn("25.0 bps", html)

    def test_paper_auto_trading_loop_runs_forced_paper_strategy_signals(self) -> None:
        _stop_paper_auto_trading()
        before = int(_paper_auto_status_payload().get("run_count") or 0)
        result = {
            "enabled": True,
            "mode": "paper",
            "scanned_symbols": 10,
            "returned_signals": 1,
            "open_positions": [],
            "events": [{"status": "paper_filled", "symbol": "BTCUSDT"}],
        }
        with patch("trade_signal_app.main._run_trading_once", return_value=result) as runner:
            try:
                status = _start_paper_auto_trading(30)
                self.assertTrue(status["running"])
                self.assertGreaterEqual(int(status["run_count"] or 0), before + 1)
                self.assertEqual(status["last_result"]["mode"], "paper")
                status = _paper_auto_status_payload()
                for _ in range(50):
                    status = _paper_auto_status_payload()
                    if int(status["run_count"] or 0) >= before + 1:
                        break
                    time.sleep(0.02)
                self.assertTrue(runner.called)
                runner.assert_called_with(force_paper=True)
                self.assertTrue(status["force_paper"])
                self.assertEqual(status["mode_label"], "paper_only")
                self.assertTrue(status["running"])
                self.assertGreaterEqual(int(status["run_count"] or 0), before + 1)
                self.assertEqual(status["last_result"]["mode"], "paper")
            finally:
                stopped = _stop_paper_auto_trading()
        self.assertFalse(stopped["running"])

    def test_strategy_auto_trading_loop_runs_configured_paper_live_modes(self) -> None:
        _stop_paper_auto_trading()
        before = int(_paper_auto_status_payload().get("run_count") or 0)
        result = {
            "enabled": True,
            "mode": "paper+live",
            "scanned_symbols": 20,
            "returned_signals": 2,
            "open_positions": [],
            "events": [{"status": "paper_filled", "symbol": "BTCUSDT"}, {"status": "filled", "symbol": "BTCUSDT"}],
        }
        with patch("trade_signal_app.main._run_trading_once", return_value=result) as runner:
            try:
                status = _start_paper_auto_trading(30, force_paper=False)
                self.assertTrue(status["running"])
                self.assertGreaterEqual(int(status["run_count"] or 0), before + 1)
                self.assertEqual(status["last_result"]["mode"], "paper+live")
                runner.assert_called_with(force_paper=False)
                self.assertFalse(status["force_paper"])
                self.assertEqual(status["mode_label"], "configured_paper_live")
            finally:
                stopped = _stop_paper_auto_trading()
        self.assertFalse(stopped["running"])

    def test_strategy_auto_trading_can_defer_first_run(self) -> None:
        _stop_paper_auto_trading()
        with patch("trade_signal_app.main._run_trading_once") as runner:
            try:
                status = _start_paper_auto_trading(30, force_paper=False, run_immediately=False)
                self.assertTrue(status["running"])
                self.assertFalse(status["force_paper"])
                runner.assert_not_called()
            finally:
                stopped = _stop_paper_auto_trading()
        self.assertFalse(stopped["running"])

    def test_serialize_trading_position_includes_unrealized_return(self) -> None:
        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=0.5,
            entry_price=100.0,
            quote_notional=50.0,
            score=82.0,
            grade="A",
            opened_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
            stop_price=96.0,
            take_profit_price=109.0,
            mode="paper",
        )

        payload = _serialize_trading_position(position, latest_price=112.0)

        self.assertEqual(payload["last_price"], 112.0)
        self.assertAlmostEqual(payload["current_notional"], 56.0)
        self.assertAlmostEqual(payload["unrealized_pnl"], 6.0)
        self.assertAlmostEqual(payload["unrealized_pnl_pct"], 12.0)

    def test_serialize_trading_report_orders_events_newest_first(self) -> None:
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

        payload = _serialize_trading_report(
            TradingRunReport(
                enabled=True,
                mode="paper",
                scanned_symbols=2,
                returned_signals=2,
                open_positions=[],
                events=[older, newer],
            )
        )

        self.assertEqual([event["message"] for event in payload["events"]], ["newer", "older"])

    def test_serialize_trading_report_includes_paper_account_metrics(self) -> None:
        buy = TradingEvent(
            action="BUY",
            symbol="BTCUSDT",
            mode="paper",
            status="paper_filled",
            message="buy",
            created_at=datetime(2026, 4, 28, 1, tzinfo=timezone.utc),
        )
        win = TradingEvent(
            action="SELL",
            symbol="BTCUSDT",
            mode="paper",
            status="paper_filled",
            message="win",
            realized_pnl=10.0,
            realized_pnl_pct=10.0,
            created_at=datetime(2026, 4, 28, 2, tzinfo=timezone.utc),
        )
        loss = TradingEvent(
            action="SELL",
            symbol="ETHUSDT",
            mode="paper",
            status="paper_filled",
            message="loss",
            realized_pnl=-4.0,
            realized_pnl_pct=-4.0,
            created_at=datetime(2026, 4, 28, 3, tzinfo=timezone.utc),
        )

        payload = _serialize_trading_report(
            TradingRunReport(
                enabled=True,
                mode="paper",
                scanned_symbols=2,
                returned_signals=2,
                open_positions=[],
                events=[buy, win, loss],
            )
        )

        metrics = payload["account_metrics"]
        self.assertEqual(metrics["event_count"], 3)
        self.assertEqual(metrics["diagnostic_event_count"], 0)
        self.assertEqual(metrics["total_trades"], 3)
        self.assertEqual(metrics["closed_trades"], 2)
        self.assertEqual(metrics["winning_trades"], 1)
        self.assertEqual(metrics["losing_trades"], 1)
        self.assertEqual(metrics["win_rate_pct"], 50.0)
        self.assertEqual(metrics["profit_loss_ratio"], 2.5)
        self.assertEqual(metrics["profit_factor"], 2.5)
        self.assertEqual(metrics["realized_pnl"], 6.0)
        btc_metrics = payload["btc_trading"]["metrics"]
        self.assertEqual(btc_metrics["symbol"], "BTCUSDT")
        self.assertEqual(btc_metrics["total_trades"], 2)
        self.assertEqual(btc_metrics["closed_trades"], 1)
        self.assertEqual(btc_metrics["winning_trades"], 1)
        self.assertEqual(btc_metrics["losing_trades"], 0)
        self.assertEqual(btc_metrics["realized_pnl"], 10.0)

    def test_trading_status_payload_returns_retained_trade_history_beyond_thirty_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            started_at = datetime(2026, 7, 6, 0, tzinfo=timezone.utc)
            events = [
                TradingEvent(
                    action="BUY" if index % 2 == 0 else "SELL",
                    symbol=f"TEST{index:02d}USDT",
                    mode="paper",
                    status="paper_filled",
                    message=f"filled {index}",
                    realized_pnl=1.0 if index % 2 else None,
                    created_at=started_at + timedelta(minutes=index),
                )
                for index in range(40)
            ]
            events.extend(
                TradingEvent(
                    action="SKIP",
                    symbol="*",
                    mode="paper",
                    status="no_signal",
                    message=f"skip {index}",
                    created_at=started_at + timedelta(hours=1, minutes=index),
                )
                for index in range(520)
            )
            store.append_events(events, limit=1000)
            config = RuntimeConfig()
            scanner = SimpleNamespace(gateway=SimpleNamespace())

            with (
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
            ):
                payload = app_main._trading_status_payload()

        self.assertEqual(payload["event_summary"]["total_events"], 560)
        self.assertEqual(payload["event_summary"]["filled_events"], 40)
        self.assertEqual(payload["event_summary"]["diagnostic_events"], 520)
        self.assertEqual(payload["event_summary"]["returned_events"], 540)
        self.assertEqual(payload["storage"]["trading_events"], 560)
        self.assertEqual(payload["storage"]["metric_snapshots"], 1)
        self.assertEqual(payload["account_metrics"]["event_count"], 560)
        self.assertEqual(payload["account_metrics"]["diagnostic_event_count"], 520)
        self.assertEqual(sum(1 for event in payload["events"] if event["status"] == "paper_filled"), 40)
        self.assertGreater(len(payload["events"]), 30)

    def test_onchain_module_loads_without_terminal_scan(self) -> None:
        config = RuntimeConfig()
        config.onchain_data_preset = "open_multichain_keyless"
        with (
            patch("trade_signal_app.main._terminal_payload", side_effect=RuntimeError("scan failed")),
            patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, None)),
            patch("trade_signal_app.main._onchain_price_map", return_value={"BTCUSDT": 60_000.0}),
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
            ) as fetch_events,
        ):
            payload = _terminal_module_payload("onchain")

        self.assertFalse(payload["fallback"])
        self.assertEqual(payload["onchain_events"][0]["symbol"], "BTCUSDT")
        self.assertEqual(payload["onchain_sources"][0]["status"], "api_live")
        self.assertEqual(payload["warning"], "")
        self.assertEqual(fetch_events.call_args.args[1], {"BTCUSDT": 60_000.0})

    def test_compile_strategy_payload_returns_run_urls_without_llm(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), object())):
            payload = _compile_strategy_payload("BTC 15m RSI 超卖反弹，止损3%，止盈6%")

        self.assertEqual(payload["source"], "local_rules")
        self.assertEqual(payload["style"], "mean_reversion")
        self.assertEqual(payload["symbols"], ["BTCUSDT"])
        self.assertIn("/backtest?", payload["run_urls"]["backtest"])
        self.assertEqual(payload["run_urls"]["paper_trading"], "/terminal/trading")

    def test_compile_strategy_template_payload_preserves_live_safety_boundary(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), object())):
            payload = _compile_strategy_template_payload("quality_trend_pullback")

        self.assertEqual(payload["template"]["preset_id"], "trend_pullback_conservative")
        self.assertTrue(payload["template"]["paper_only"])
        self.assertFalse(payload["autotrade_defaults"]["enabled"])
        self.assertFalse(payload["autotrade_defaults"]["live_enabled"])
        self.assertTrue(payload["autotrade_defaults"]["order_test_only"])
        query = parse_qs(urlparse(payload["run_urls"]["backtest"]).query)
        self.assertEqual(query["max_entry_volatility_ratio"], ["1.55"])

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
                "strategy_templates": [
                    {
                        "template_id": "quality_trend_pullback",
                        "label": "趋势回踩确认",
                        "description": "等待趋势回踩后确认。",
                        "style": "trend_following",
                        "preset_id": "trend_pullback_conservative",
                        "risk_level": "low",
                        "validation_status": "paper_candidate",
                        "recommended_intervals": ["1h", "4h"],
                        "market_regimes": ["trend_pullback"],
                    }
                ],
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
        self.assertIn("参数预设与策略模板", html)
        self.assertIn("趋势回踩确认", html)
        self.assertIn('action="/terminal/strategies/templates/compile"', html)
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
            account_metrics={
                "total_trades": 12,
                "buy_trades": 7,
                "sell_trades": 5,
                "closed_trades": 5,
                "winning_trades": 3,
                "losing_trades": 2,
                "breakeven_trades": 0,
                "win_rate_pct": 60.0,
                "profit_loss_ratio": 1.8,
                "profit_factor": 2.2,
                "realized_pnl": 18.0,
                "unrealized_pnl": 3.0,
                "total_pnl": 21.0,
            },
            btc_trading=self._btc_trading_fixture(),
        )

        self.assertIn("AI Trade Auto Execution", html)
        self.assertIn("运行一次自动交易", html)
        self.assertIn("BTC交易专区", html)
        self.assertIn("BTC累计成交", html)
        self.assertIn("btc_regime_trend_pullback_buy", html)
        self.assertIn("完整 BTC 图表视图", html)
        self.assertIn('href="/btc/signal"', html)
        self.assertIn('href="/btc/signal?fast=1"', html)
        self.assertIn("累计成交次数", html)
        self.assertIn("盈亏比", html)
        self.assertIn("60.0%", html)
        self.assertIn("持仓", html)
        self.assertIn("执行事件", html)
        self.assertIn('href="#trading-positions"', html)
        self.assertIn('id="trading-events"', html)

    def test_render_btc_signal_page_shows_visual_chart_and_tables(self) -> None:
        summary = dict(self._btc_trading_fixture()["signal"])
        summary["price"] = 119250.0
        summary["analysis_price"] = 118000.0
        summary["price_source"] = "live_market"
        summary["technical"] = {"indicator_snapshot": {"closes": [112000.0, 113500.0, 114200.0, 118000.0]}}
        summary["preset_backtests"] = [
            {
                "label": "BTC Core Trading",
                "signal_count": 18,
                "win_rate_pct": 61.1,
                "profit_factor": 1.8,
                "max_drawdown_pct": -8.5,
                "quality_score": 74.2,
            }
        ]
        summary["selected_preset"] = {"label": "BTC Core Trading", "win_rate_pct": 61.1}

        html = render_btc_signal_page(summary=summary, fast=False)

        self.assertIn("BTC 专属信号可视化", html)
        self.assertIn("BTC信号走势图", html)
        self.assertIn("btc-visual-chart", html)
        self.assertIn("btc-chart-area", html)
        self.assertIn("btc-chart-level-label", html)
        self.assertIn("btc-chart-connector", html)
        self.assertIn("最近48根K线 + 实时价", html)
        self.assertIn("当前价 119,250.00", html)
        self.assertIn("K线收盘 118,000.00", html)
        self.assertIn("关键价位", html)
        self.assertIn("信号与统计", html)
        self.assertIn("BTC预设回测", html)
        self.assertIn("BTC Core Trading", html)
        self.assertIn('href="/api/btc/signal"', html)
        self.assertIn('href="/btc/signal?fast=1"', html)

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
        self.assertIn("2026-04-28 08:00:00", html)
        self.assertNotIn("2026-04-28T00:00:00+00:00", html)

    def test_render_trading_page_shows_latest_events_first(self) -> None:
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
            events=[
                {"created_at": "2026-04-28T01:00:00+00:00", "action": "BUY", "symbol": "BTCUSDT", "status": "paper_filled", "message": "旧事件"},
                {"created_at": "2026-04-28T02:00:00+00:00", "action": "SELL", "symbol": "ETHUSDT", "status": "paper_filled", "message": "新事件"},
            ],
        )

        self.assertLess(html.index("新事件"), html.index("旧事件"))

    def test_render_trading_page_paginates_large_event_tables(self) -> None:
        events = [
            {
                "created_at": f"2026-04-28T00:{index:02d}:00+00:00",
                "action": "BUY",
                "symbol": f"TEST{index}USDT",
                "status": "paper_filled",
                "message": "模拟买入已记录。",
                "score": 82.0,
                "quote_notional": 25.0,
            }
            for index in range(16)
        ]

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
            events=events,
        )

        self.assertIn("TEST15USDT", html)
        self.assertIn("table-pagination", html)
        self.assertIn("PAGE_SIZE = 15", html)

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
        notifier = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
            ):
                payload = _run_trading_once(force_paper=True)

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["events"][0]["status"], "paper_filled")
        self.assertEqual(payload["open_positions"][0]["symbol"], "BTCUSDT")
        notifier.notify_trade.assert_called_once()

    def test_run_trading_once_dispatches_paper_and_live_when_both_switches_enabled(self) -> None:
        config = RuntimeConfig()
        config.autotrade_defaults.enabled = True
        config.autotrade_defaults.paper_enabled = True
        config.autotrade_defaults.live_enabled = True
        config.autotrade_defaults.order_test_only = True
        shared_scan_result = (SimpleNamespace(scanned_symbols=1, returned_signals=1), [])
        scanner = SimpleNamespace(gateway=object(), scan=Mock(return_value=shared_scan_result))
        calls: list[tuple[str, bool]] = []
        isolate_flags: list[bool] = []
        scan_results: list[object] = []
        metric_snapshots: list[tuple[str, dict[str, object]]] = []

        class FakeAutoTrader:
            def __init__(self, **kwargs):
                isolate_flags.append(bool(kwargs.get("isolate_mode")))
                scan_results.append(kwargs.get("scan_result"))

            def set_execution_gateway(self, gateway):
                return None

            def run_once(self, run_config):
                calls.append((run_config.mode, run_config.enabled))
                return TradingRunReport(
                    enabled=True,
                    mode=run_config.mode,
                    scanned_symbols=1,
                    returned_signals=1,
                    open_positions=[],
                    events=[
                        TradingEvent(
                            action="SKIP",
                            symbol="*",
                            mode=run_config.mode,
                            status=f"{run_config.mode}_done",
                            message="test",
                        )
                    ],
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=None),
                patch("trade_signal_app.main._execution_gateway", return_value=object()),
                patch.object(
                    store,
                    "record_metric_snapshot",
                    side_effect=lambda scope, metrics: metric_snapshots.append((scope, metrics)),
                ),
                patch("trade_signal_app.main.IntelligenceHub") as hub_cls,
                patch("trade_signal_app.main.AutoTrader", FakeAutoTrader),
            ):
                hub_cls.return_value.snapshot.return_value = SimpleNamespace(
                    execution_risk=SimpleNamespace(blocked_symbols={})
                )
                payload = _run_trading_once()

        self.assertEqual(calls, [("paper", True), ("live", True)])
        self.assertEqual(isolate_flags, [True, True])
        self.assertEqual(scan_results, [shared_scan_result, shared_scan_result])
        scanner.scan.assert_called_once_with()
        self.assertEqual(payload["mode"], "paper+live")
        self.assertEqual(payload["scanned_symbols"], 1)
        self.assertEqual({event["status"] for event in payload["events"]}, {"paper_done", "live_done"})
        self.assertEqual(metric_snapshots[0][0], "signal_scan")
        self.assertEqual(metric_snapshots[0][1]["returned_signals"], 1)

    def test_live_insufficient_balance_does_not_block_paper_fill(self) -> None:
        signal = SimpleNamespace(
            symbol="BTCUSDT",
            score=84.0,
            grade="A",
            ticker=SimpleNamespace(last_price=100.0, quote_volume=20_000_000.0),
            indicators=SimpleNamespace(
                volume_ratio=1.6,
                buy_pressure_ratio=0.63,
                rsi_14=55.0,
                price_vs_ema20_pct=1.0,
                recent_change_pct=1.0,
                support_level=99.0,
                resistance_level=115.0,
                support_distance_pct=1.0,
                resistance_distance_pct=15.0,
                support_strength=3.0,
                structure_risk_reward=3.0,
            ),
        )
        gateway = SimpleNamespace(ticker_price=Mock(return_value=100.0))
        scanner = SimpleNamespace(
            gateway=gateway,
            scan=lambda: (SimpleNamespace(scanned_symbols=10, returned_signals=1), [signal]),
        )
        config = RuntimeConfig()
        config.autotrade_defaults.enabled = True
        config.autotrade_defaults.paper_enabled = True
        config.autotrade_defaults.live_enabled = True
        config.autotrade_defaults.order_test_only = False
        config.autotrade_defaults.quote_order_qty = 25.0
        config.autotrade_defaults.score_threshold = 75.0
        notifier = Mock()

        def insufficient_readiness():
            self.assertEqual(notifier.notify_trade.call_count, 1)
            return {
                "live_ready": False,
                "blockers": ["USDT 可用余额不足"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch(
                    "trade_signal_app.main._trading_readiness_payload",
                    side_effect=insufficient_readiness,
                ),
                patch("trade_signal_app.main.IntelligenceHub") as hub_cls,
            ):
                hub_cls.return_value.snapshot.return_value = SimpleNamespace(
                    execution_risk=SimpleNamespace(blocked_symbols={})
                )
                payload = _run_trading_once()
                stored_positions = store.load()

        statuses = {event["status"] for event in payload["events"]}
        self.assertIn("blocked", statuses)
        self.assertIn("paper_filled", statuses)
        self.assertIn("USDT 可用余额不足", " ".join(str(event["message"]) for event in payload["events"]))
        self.assertEqual([(position.symbol, position.mode) for position in stored_positions], [("BTCUSDT", "paper")])
        self.assertGreaterEqual(gateway.ticker_price.call_count, 1)
        notified_event = notifier.notify_trade.call_args.kwargs["event"]
        self.assertEqual((notified_event.action, notified_event.mode, notified_event.status), ("BUY", "paper", "paper_filled"))

    def test_live_order_insufficient_balance_does_not_rollback_paper_fill_or_notification(self) -> None:
        signal = SimpleNamespace(
            symbol="BTCUSDT",
            score=84.0,
            grade="A",
            ticker=SimpleNamespace(last_price=100.0, quote_volume=20_000_000.0),
            indicators=SimpleNamespace(
                volume_ratio=1.6,
                buy_pressure_ratio=0.63,
                rsi_14=55.0,
                price_vs_ema20_pct=1.0,
                recent_change_pct=1.0,
                support_level=99.0,
                resistance_level=115.0,
                support_distance_pct=1.0,
                resistance_distance_pct=15.0,
                support_strength=3.0,
                structure_risk_reward=3.0,
            ),
        )
        gateway = SimpleNamespace(
            ticker_price=Mock(return_value=100.0),
            order_market_buy=Mock(
                side_effect=ValueError(
                    "Binance SIGNED 接口请求失败：HTTP 400，Account has insufficient balance for requested action."
                )
            ),
        )
        scanner = SimpleNamespace(
            gateway=gateway,
            scan=Mock(return_value=(SimpleNamespace(scanned_symbols=10, returned_signals=1), [signal])),
        )
        config = RuntimeConfig()
        config.autotrade_defaults.enabled = True
        config.autotrade_defaults.paper_enabled = True
        config.autotrade_defaults.live_enabled = True
        config.autotrade_defaults.order_test_only = False
        config.autotrade_defaults.quote_order_qty = 25.0
        config.autotrade_defaults.score_threshold = 75.0
        notifier = Mock()

        def ready_after_paper_notification():
            self.assertEqual(notifier.notify_trade.call_count, 1)
            return {"live_ready": True, "blockers": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch("trade_signal_app.main._trading_readiness_payload", side_effect=ready_after_paper_notification),
                patch("trade_signal_app.main.IntelligenceHub") as hub_cls,
                patch.dict("os.environ", {"AI_TRADE_LIVE_CONFIRM": "I_UNDERSTAND_REAL_ORDERS"}),
            ):
                hub_cls.return_value.snapshot.return_value = SimpleNamespace(
                    execution_risk=SimpleNamespace(blocked_symbols={})
                )
                payload = _run_trading_once()
                stored_positions = store.load()

        statuses = {event["status"] for event in payload["events"]}
        self.assertEqual(statuses, {"paper_filled", "rejected"})
        self.assertEqual([(position.symbol, position.mode) for position in stored_positions], [("BTCUSDT", "paper")])
        self.assertEqual(notifier.notify_trade.call_count, 1)
        gateway.order_market_buy.assert_called_once()
        self.assertIn("insufficient balance", " ".join(str(event["message"]) for event in payload["events"]))

    def test_live_readiness_error_does_not_block_paper_dispatch(self) -> None:
        config = RuntimeConfig()
        config.autotrade_defaults.enabled = True
        config.autotrade_defaults.paper_enabled = True
        config.autotrade_defaults.live_enabled = True
        config.autotrade_defaults.order_test_only = False
        scanner = SimpleNamespace(
            gateway=object(),
            scan=Mock(return_value=(SimpleNamespace(scanned_symbols=1, returned_signals=1), [])),
        )
        calls: list[str] = []

        class FakeAutoTrader:
            def __init__(self, **kwargs):
                return None

            def set_execution_gateway(self, gateway):
                return None

            def run_once(self, run_config):
                calls.append(run_config.mode)
                return TradingRunReport(
                    enabled=True,
                    mode=run_config.mode,
                    scanned_symbols=1,
                    returned_signals=1,
                    open_positions=[],
                    events=[
                        TradingEvent(
                            action="SKIP",
                            symbol="*",
                            mode=run_config.mode,
                            status=f"{run_config.mode}_done",
                            message="test",
                        )
                    ],
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=None),
                patch("trade_signal_app.main._execution_gateway", return_value=object()),
                patch("trade_signal_app.main._trading_readiness_payload", side_effect=RuntimeError("balance endpoint timeout")),
                patch("trade_signal_app.main.IntelligenceHub") as hub_cls,
                patch("trade_signal_app.main.AutoTrader", FakeAutoTrader),
            ):
                hub_cls.return_value.snapshot.return_value = SimpleNamespace(
                    execution_risk=SimpleNamespace(blocked_symbols={})
                )
                payload = _run_trading_once()

        self.assertEqual(calls, ["paper"])
        self.assertEqual(payload["mode"], "paper+live")
        self.assertEqual({event["status"] for event in payload["events"]}, {"blocked", "paper_done"})
        self.assertIn("实盘就绪检查异常：balance endpoint timeout", " ".join(str(event["message"]) for event in payload["events"]))

    def test_forced_paper_trading_run_waits_for_pullback_on_spike(self) -> None:
        signal = SimpleNamespace(
            symbol="BTCUSDT",
            score=84.0,
            grade="A",
            reasons=["EMA20/EMA50 多头排列", "MACD 动能转强"],
            ticker=SimpleNamespace(
                last_price=100.0,
                price_change_percent=8.0,
                quote_volume=20_000_000.0,
            ),
            indicators=SimpleNamespace(
                volume_ratio=1.6,
                buy_pressure_ratio=0.63,
                ema_spread_pct=1.2,
                rsi_14=78.0,
                price_vs_ema20_pct=8.0,
                recent_change_pct=6.0,
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
        notifier = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch("trade_signal_app.main._fast_risk_module_payload", return_value={"execution_risk": {"blocked_symbols": {}}}),
            ):
                payload = _run_trading_once(force_paper=True)

        self.assertEqual(payload["open_positions"], [])
        self.assertEqual(payload["events"][0]["status"], "wait_pullback")
        self.assertIn("等待回调", payload["events"][0]["message"])
        notifier.notify_trade.assert_not_called()

    def test_forced_paper_trading_run_waits_for_support_on_poor_structure(self) -> None:
        signal = SimpleNamespace(
            symbol="BTCUSDT",
            score=84.0,
            grade="A",
            reasons=["EMA20/EMA50 多头排列", "MACD 动能转强"],
            ticker=SimpleNamespace(
                last_price=100.0,
                price_change_percent=2.0,
                quote_volume=20_000_000.0,
            ),
            indicators=SimpleNamespace(
                volume_ratio=1.6,
                buy_pressure_ratio=0.63,
                ema_spread_pct=1.2,
                rsi_14=58.0,
                price_vs_ema20_pct=1.5,
                recent_change_pct=1.0,
                support_level=94.0,
                resistance_level=101.0,
                support_distance_pct=6.0,
                resistance_distance_pct=1.0,
                support_strength=1.0,
                structure_risk_reward=0.4,
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
        notifier = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch("trade_signal_app.main._fast_risk_module_payload", return_value={"execution_risk": {"blocked_symbols": {}}}),
            ):
                payload = _run_trading_once(force_paper=True)

        self.assertEqual(payload["open_positions"], [])
        self.assertEqual(payload["events"][0]["status"], "wait_support")
        self.assertIn("等待更合理买点", payload["events"][0]["message"])
        notifier.notify_trade.assert_not_called()

    def test_forced_paper_trading_run_closes_positions_on_exit_rules(self) -> None:
        def signal(symbol: str, price: float) -> SimpleNamespace:
            return SimpleNamespace(
                symbol=symbol,
                score=10.0,
                grade="C",
                reasons=[],
                ticker=SimpleNamespace(
                    last_price=price,
                    price_change_percent=0.0,
                    quote_volume=20_000_000.0,
                ),
                indicators=SimpleNamespace(
                    volume_ratio=1.0,
                    buy_pressure_ratio=0.5,
                    ema_spread_pct=0.0,
                ),
            )

        scanner = SimpleNamespace(
            scan=lambda: (
                SimpleNamespace(scanned_symbols=10, returned_signals=2),
                [signal("BTCUSDT", 105.0), signal("ETHUSDT", 95.0)],
            ),
        )
        config = RuntimeConfig()
        config.autotrade_defaults.enabled = False
        config.autotrade_defaults.mode = "live"
        config.autotrade_defaults.score_threshold = 75.0
        config.autotrade_defaults.take_profit_pct = 4.0
        config.autotrade_defaults.stop_loss_pct = 4.0
        notifier = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=1.0,
                        entry_price=100.0,
                        quote_notional=100.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=104.0,
                        mode="paper",
                    ),
                    TradingPosition(
                        symbol="ETHUSDT",
                        quantity=1.0,
                        entry_price=100.0,
                        quote_notional=100.0,
                        score=80.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=104.0,
                        mode="paper",
                    ),
                ]
            )
            with (
                patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(config, scanner)),
                patch("trade_signal_app.main._trading_store", return_value=store),
                patch("trade_signal_app.main._feishu_trade_notifier", return_value=notifier),
                patch("trade_signal_app.main._fast_risk_module_payload", return_value={"execution_risk": {"blocked_symbols": {}}}),
            ):
                payload = _run_trading_once(force_paper=True)
                stored_positions = store.load()
                stored_events = store.load_events()

        self.assertEqual(payload["open_positions"], [])
        self.assertEqual(stored_positions, [])
        exit_reasons = {event.symbol: event.exit_reason for event in stored_events}
        self.assertEqual(exit_reasons["BTCUSDT"], "take_profit")
        self.assertEqual(exit_reasons["ETHUSDT"], "stop_loss")
        self.assertTrue(all(event.status == "paper_filled" for event in stored_events))
        self.assertEqual(notifier.notify_trade.call_count, 2)

    def test_build_runtime_config_parses_runtime_form(self) -> None:
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.okx_api_key = "keep-okx-key"
        current.okx_api_secret = "keep-okx-secret"
        current.okx_api_passphrase = "keep-okx-pass"
        current.x_bearer_token = "keep-x-token"
        current.onchain_api_key = "keep-onchain-key"
        current.tradingview_password = "keep-tv-password"
        current.llm_api_key = "keep-llm-key"
        current.feishu_webhook_url = "https://open.feishu.cn/webhook/keep"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            config = _build_runtime_config(
                {
                    "binance_recv_window_ms": ["6000"],
                    "market_data_preset": ["tradingview_unofficial"],
                    "tradingview_username": ["tv-user"],
                    "tradingview_exchange": ["binance"],
                    "tradingview_symbols": ["btcusdt\nethusdt"],
                    "tradingview_interval": ["1h"],
                    "tradingview_bars": ["1200"],
                    "tradingview_cache_enabled": ["on"],
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
                    "scan_btc_min_quote_volume": ["101000000"],
                    "scan_btc_min_trade_count": ["51000"],
                    "scan_eth_min_quote_volume": ["81000000"],
                    "scan_eth_min_trade_count": ["41000"],
                    "scan_xrp_min_quote_volume": ["31000000"],
                    "scan_xrp_min_trade_count": ["16000"],
                    "scan_sol_min_quote_volume": ["51000000"],
                    "scan_sol_min_trade_count": ["26000"],
                    "scan_bnb_min_quote_volume": ["31000000"],
                    "scan_bnb_min_trade_count": ["16000"],
                    "scan_top30_min_quote_volume": ["16000000"],
                    "scan_top30_min_trade_count": ["6000"],
                    "autotrade_enabled": ["on"],
                    "autotrade_mode": ["paper"],
                    "autotrade_paper_enabled": ["on"],
                    "autotrade_live_enabled": ["on"],
                    "autotrade_execution_exchange": ["okx"],
                    "autotrade_quote_order_qty": ["30"],
                    "autotrade_leverage": ["5"],
                    "autotrade_risk_per_trade_pct": ["6"],
                    "autotrade_exit_profile": ["trend_following"],
                    "autotrade_max_open_positions": ["2"],
                    "autotrade_max_total_quote_exposure": ["90"],
                    "autotrade_score_threshold": ["78"],
                    "autotrade_min_volume_ratio": ["1.2"],
                    "autotrade_min_buy_pressure": ["0.58"],
                    "autotrade_anti_chase_enabled": ["on"],
                    "autotrade_max_entry_rsi": ["70"],
                    "autotrade_max_entry_price_vs_ema20_pct": ["4.5"],
                    "autotrade_max_entry_recent_change_pct": ["3.5"],
                    "autotrade_structure_filter_enabled": ["on"],
                    "autotrade_max_entry_support_distance_pct": ["2.2"],
                    "autotrade_min_entry_support_strength": ["2.5"],
                    "autotrade_min_entry_risk_reward_ratio": ["1.8"],
                    "autotrade_min_entry_resistance_distance_pct": ["2.8"],
                    "autotrade_support_stop_buffer_pct": ["0.7"],
                    "autotrade_resistance_take_profit_buffer_pct": ["0.5"],
                    "autotrade_stop_loss_pct": ["3"],
                    "autotrade_take_profit_pct": ["8"],
                    "autotrade_trend_hold_enabled": ["on"],
                    "autotrade_trend_hold_min_score": ["86"],
                    "autotrade_trend_hold_min_volume_ratio": ["1.4"],
                    "autotrade_trend_hold_min_buy_pressure": ["0.61"],
                    "autotrade_emergency_drawdown_pct": ["1.8"],
                    "autotrade_emergency_alert_global_cooldown_minutes": ["90"],
                    "autotrade_emergency_alert_symbol_cooldown_minutes": ["1440"],
                    "autotrade_emergency_low_liquidity_quote_volume": ["10000000"],
                    "autotrade_emergency_low_liquidity_drawdown_multiplier": ["2.5"],
                    "autotrade_emergency_low_liquidity_min_score": ["88"],
                    "autotrade_cooldown_minutes": ["180"],
                    "autotrade_order_test_only": ["on"],
                    "feishu_webhook_url": ["https://open.feishu.cn/webhook/new"],
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
        self.assertEqual(config.market_data_preset, "tradingview_unofficial")
        self.assertEqual(config.tradingview_username, "tv-user")
        self.assertEqual(config.tradingview_password, "keep-tv-password")
        self.assertEqual(config.tradingview_exchange, "BINANCE")
        self.assertEqual(config.tradingview_symbols, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(config.tradingview_interval, "1h")
        self.assertEqual(config.tradingview_bars, 1200)
        self.assertTrue(config.tradingview_cache_enabled)
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
        self.assertEqual(config.feishu_webhook_url, "https://open.feishu.cn/webhook/new")
        self.assertEqual(config.backtest_defaults.preset, "portfolio_rotation")
        self.assertEqual(config.scan_defaults.quote_asset, "FDUSD")
        self.assertTrue(config.autotrade_defaults.enabled)
        self.assertTrue(config.autotrade_defaults.paper_enabled)
        self.assertTrue(config.autotrade_defaults.live_enabled)
        self.assertEqual(config.autotrade_defaults.mode, "live")
        self.assertEqual(config.autotrade_defaults.execution_exchange, "okx")
        self.assertEqual(config.autotrade_defaults.quote_order_qty, 30.0)
        self.assertEqual(config.autotrade_defaults.leverage, 5.0)
        self.assertEqual(config.autotrade_defaults.risk_per_trade_pct, 6.0)
        self.assertEqual(config.autotrade_defaults.exit_profile, "trend_following")
        self.assertEqual(config.autotrade_defaults.max_open_positions, 2)
        self.assertTrue(config.autotrade_defaults.anti_chase_enabled)
        self.assertEqual(config.autotrade_defaults.max_entry_rsi, 70.0)
        self.assertEqual(config.autotrade_defaults.max_entry_price_vs_ema20_pct, 4.5)
        self.assertEqual(config.autotrade_defaults.max_entry_recent_change_pct, 3.5)
        self.assertTrue(config.autotrade_defaults.structure_filter_enabled)
        self.assertEqual(config.autotrade_defaults.max_entry_support_distance_pct, 2.2)
        self.assertEqual(config.autotrade_defaults.min_entry_support_strength, 2.5)
        self.assertEqual(config.autotrade_defaults.min_entry_risk_reward_ratio, 1.8)
        self.assertEqual(config.autotrade_defaults.min_entry_resistance_distance_pct, 2.8)
        self.assertEqual(config.autotrade_defaults.support_stop_buffer_pct, 0.7)
        self.assertEqual(config.autotrade_defaults.resistance_take_profit_buffer_pct, 0.5)
        self.assertTrue(config.autotrade_defaults.trend_hold_enabled)
        self.assertEqual(config.autotrade_defaults.trend_hold_min_score, 86.0)
        self.assertEqual(config.autotrade_defaults.trend_hold_min_volume_ratio, 1.4)
        self.assertEqual(config.autotrade_defaults.trend_hold_min_buy_pressure, 0.61)
        self.assertEqual(config.autotrade_defaults.emergency_drawdown_pct, 1.8)
        self.assertEqual(config.autotrade_defaults.emergency_alert_global_cooldown_minutes, 90)
        self.assertEqual(config.autotrade_defaults.emergency_alert_symbol_cooldown_minutes, 1440)
        self.assertEqual(config.autotrade_defaults.emergency_low_liquidity_quote_volume, 10_000_000)
        self.assertEqual(config.autotrade_defaults.emergency_low_liquidity_drawdown_multiplier, 2.5)
        self.assertEqual(config.autotrade_defaults.emergency_low_liquidity_min_score, 88.0)
        self.assertTrue(config.intelligence_defaults.enabled)
        self.assertTrue(config.intelligence_defaults.llm_enabled)
        self.assertEqual(config.intelligence_defaults.llm_provider, "deepseek")
        self.assertEqual(config.intelligence_defaults.llm_api_key, "test-llm-key")
        self.assertEqual(config.intelligence_defaults.llm_model, "deepseek-chat")
        self.assertEqual(config.intelligence_defaults.min_spread_bps, 15.0)
        self.assertEqual(config.backtest_defaults.fee_source, "account")
        self.assertTrue(config.backtest_defaults.no_binance_discount)
        self.assertTrue(config.backtest_defaults.no_kdj_confirmation)

    def test_build_runtime_config_accepts_partial_okx_credentials(self) -> None:
        current = RuntimeConfig()
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            config = _build_runtime_config(
                {
                    "okx_api_key": ["new-okx-key"],
                    "okx_api_secret": ["new-okx-secret"],
                }
            )

        self.assertEqual(config.okx_api_key, "new-okx-key")
        self.assertEqual(config.okx_api_secret, "new-okx-secret")
        self.assertEqual(config.okx_api_passphrase, "")

    def test_runtime_config_migrates_legacy_autotrade_mode_switch(self) -> None:
        config = RuntimeConfig.from_dict(
            {
                "autotrade_defaults": {
                    "enabled": True,
                    "mode": "live",
                    "order_test_only": False,
                }
            },
            app_main.SETTINGS,
        )

        self.assertTrue(config.autotrade_defaults.enabled)
        self.assertFalse(config.autotrade_defaults.paper_enabled)
        self.assertTrue(config.autotrade_defaults.live_enabled)
        self.assertEqual(config.autotrade_defaults.mode, "live")

    def test_build_runtime_config_preserves_unsubmitted_module_booleans(self) -> None:
        current = RuntimeConfig()
        current.tradingview_cache_enabled = True
        current.autotrade_defaults.enabled = True
        current.autotrade_defaults.paper_enabled = True
        current.autotrade_defaults.order_test_only = True
        current.feishu_webhook_url = "https://open.feishu.cn/webhook/keep"
        current.intelligence_defaults.enabled = True
        current.intelligence_defaults.llm_enabled = True
        current.backtest_defaults.no_binance_discount = True
        current.backtest_defaults.no_kdj_confirmation = True

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            scan_config = _build_runtime_config(
                {
                    "settings_section": ["scan"],
                    "scan_quote_asset": ["FDUSD"],
                    "scan_interval": ["1h"],
                    "scan_candidate_pool": ["12"],
                    "scan_min_quote_volume": ["2000000"],
                    "scan_min_trade_count": ["800"],
                    "scan_btc_min_quote_volume": ["101000000"],
                    "scan_btc_min_trade_count": ["51000"],
                    "scan_eth_min_quote_volume": ["81000000"],
                    "scan_eth_min_trade_count": ["41000"],
                    "scan_xrp_min_quote_volume": ["31000000"],
                    "scan_xrp_min_trade_count": ["16000"],
                    "scan_sol_min_quote_volume": ["51000000"],
                    "scan_sol_min_trade_count": ["26000"],
                    "scan_bnb_min_quote_volume": ["31000000"],
                    "scan_bnb_min_trade_count": ["16000"],
                    "scan_top30_min_quote_volume": ["16000000"],
                    "scan_top30_min_trade_count": ["6000"],
                }
            )

        self.assertEqual(scan_config.scan_defaults.quote_asset, "FDUSD")
        self.assertEqual(scan_config.scan_defaults.btc_min_quote_volume, 101_000_000)
        self.assertEqual(scan_config.scan_defaults.eth_min_trade_count, 41_000)
        self.assertEqual(scan_config.scan_defaults.xrp_min_quote_volume, 31_000_000)
        self.assertEqual(scan_config.scan_defaults.sol_min_trade_count, 26_000)
        self.assertEqual(scan_config.scan_defaults.bnb_min_quote_volume, 31_000_000)
        self.assertEqual(scan_config.scan_defaults.top30_min_trade_count, 6000)
        self.assertTrue(scan_config.tradingview_cache_enabled)
        self.assertTrue(scan_config.autotrade_defaults.enabled)
        self.assertTrue(scan_config.autotrade_defaults.paper_enabled)
        self.assertTrue(scan_config.autotrade_defaults.order_test_only)
        self.assertEqual(scan_config.feishu_webhook_url, "https://open.feishu.cn/webhook/keep")
        self.assertTrue(scan_config.intelligence_defaults.enabled)
        self.assertTrue(scan_config.intelligence_defaults.llm_enabled)
        self.assertTrue(scan_config.backtest_defaults.no_binance_discount)
        self.assertTrue(scan_config.backtest_defaults.no_kdj_confirmation)

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            autotrade_config = _build_runtime_config(
                {
                    "settings_section": ["autotrade"],
                    "autotrade_enabled": ["0"],
                    "autotrade_order_test_only": ["0"],
                    "autotrade_mode": ["paper"],
                }
            )

        self.assertFalse(autotrade_config.autotrade_defaults.enabled)
        self.assertFalse(autotrade_config.autotrade_defaults.paper_enabled)
        self.assertFalse(autotrade_config.autotrade_defaults.live_enabled)
        self.assertFalse(autotrade_config.autotrade_defaults.order_test_only)
        self.assertTrue(autotrade_config.tradingview_cache_enabled)
        self.assertTrue(autotrade_config.intelligence_defaults.enabled)
        self.assertTrue(autotrade_config.backtest_defaults.no_binance_discount)

    def test_build_runtime_config_rejects_invalid_choices(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)):
            with self.assertRaisesRegex(ValueError, "Auto Trade Mode"):
                _build_runtime_config({"autotrade_mode": ["real"]})

    def test_build_runtime_config_rejects_invalid_feishu_webhook(self) -> None:
        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(RuntimeConfig(), None)):
            with self.assertRaisesRegex(ValueError, "Feishu Webhook URL"):
                _build_runtime_config({"feishu_webhook_url": ["open.feishu.cn/webhook/test"]})

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
        current.feishu_webhook_url = "https://open.feishu.cn/webhook/keep"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            imported = _import_runtime_config_template(
                {
                    "config_template": [
                        '{"kind":"runtime_config_template","version":1,"config":{"binance_api_key":"","binance_api_secret":"","x_bearer_token":"","feishu_webhook_url":"","scan_defaults":{"quote_asset":"FDUSD"}}}'
                    ]
                }
            )

        self.assertEqual(imported.binance_api_key, "keep-key")
        self.assertEqual(imported.binance_api_secret, "keep-secret")
        self.assertEqual(imported.okx_api_key, "keep-okx-key")
        self.assertEqual(imported.okx_api_secret, "keep-okx-secret")
        self.assertEqual(imported.okx_api_passphrase, "keep-okx-pass")
        self.assertEqual(imported.x_bearer_token, "keep-token")
        self.assertEqual(imported.feishu_webhook_url, "https://open.feishu.cn/webhook/keep")
        self.assertEqual(imported.scan_defaults.quote_asset, "FDUSD")

    def test_export_runtime_config_template_redacts_secrets(self) -> None:
        current = RuntimeConfig()
        current.binance_api_key = "keep-key"
        current.binance_api_secret = "keep-secret"
        current.okx_api_key = "keep-okx-key"
        current.okx_api_secret = "keep-okx-secret"
        current.okx_api_passphrase = "keep-okx-pass"
        current.x_bearer_token = "keep-token"
        current.feishu_webhook_url = "https://open.feishu.cn/webhook/keep"

        with patch("trade_signal_app.main.APP_STATE.snapshot", return_value=(current, None)):
            payload = _export_runtime_config_template(include_secrets=False)

        self.assertEqual(payload["config"]["binance_api_key"], "")
        self.assertEqual(payload["config"]["binance_api_secret"], "")
        self.assertEqual(payload["config"]["okx_api_key"], "")
        self.assertEqual(payload["config"]["okx_api_secret"], "")
        self.assertEqual(payload["config"]["okx_api_passphrase"], "")
        self.assertEqual(payload["config"]["x_bearer_token"], "")
        self.assertEqual(payload["config"]["feishu_webhook_url"], "")

    def test_backtest_export_csv_contains_core_rows(self) -> None:
        csv_text = _backtest_export_csv(
            payload={
                "strategy_explanation": {
                    "strategy_type": "balanced_swing",
                    "summary": "均衡波段模板",
                    "notes": ["成本假设：fee_model=flat"],
                },
                "parameter_sweep": [
                    {
                        "symbol": "BTCUSDT",
                        "interval": "4h",
                        "status": "ok",
                        "score_threshold": 70.0,
                        "stop_loss_pct": 4.0,
                        "final_equity": 1.18,
                        "return_pct": 18.0,
                        "max_drawdown_pct": -5.0,
                        "profit_factor": 1.7,
                        "signal_count": 8,
                        "risk_adjusted_return": 3.6,
                        "base_cell": True,
                    }
                ],
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
        self.assertIn("sensitivity,score_70.0_stop_4.0,4h,return_pct,18.0", csv_text)

    def test_backtest_html_export_contains_heatmap_and_escapes_params(self) -> None:
        html = _backtest_export_html(
            payload={
                "strategy_explanation": {"summary": "参数研究", "notes": ["仅用于回测"]},
                "series_reports": [],
                "portfolio_reports": [],
                "parameter_sweep": [
                    {
                        "status": "ok",
                        "score_threshold": 70.0,
                        "stop_loss_pct": 4.0,
                        "final_equity": 1.08,
                        "return_pct": 8.0,
                        "max_drawdown_pct": -3.0,
                    }
                ],
            },
            params={"archives": "<script>alert(1)</script>"},
            error=None,
        )

        self.assertIn("AI Trade 回测研究报告", html)
        self.assertIn("参数敏感度热力图", html)
        self.assertIn("+8.00%", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

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
