from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from trade_signal_app.runtime_config import AutoTradeDefaults
from trade_signal_app.trading import AutoTrader, LIVE_CONFIRM_VALUE, TradingPosition, TradingStateStore


def _signal(symbol: str = "BTCUSDT", score: float = 82.0, price: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        score=score,
        grade="A",
        ticker=SimpleNamespace(last_price=price),
        indicators=SimpleNamespace(volume_ratio=1.4, buy_pressure_ratio=0.62),
    )


class FakeGateway:
    def __init__(self, buy_response=None, ticker_rows=None) -> None:
        self.buy_calls = []
        self.sell_calls = []
        self.ticker24hr_calls = 0
        self.ticker24hr_symbols_calls: list[list[str]] = []
        self.buy_response = buy_response or {"orderId": 123}
        self.ticker_rows = ticker_rows or []

    def order_market_buy(self, **kwargs):
        self.buy_calls.append(kwargs)
        return self.buy_response

    def order_market_sell(self, **kwargs):
        self.sell_calls.append(kwargs)
        return {"orderId": 456, "executedQty": str(kwargs.get("quantity", 0)), "cummulativeQuoteQty": "55.0"}

    def ticker24hr(self):
        self.ticker24hr_calls += 1
        return self.ticker_rows

    def ticker24hr_symbols(self, symbols):
        self.ticker24hr_symbols_calls.append(symbols)
        wanted = {symbol.upper() for symbol in symbols}
        return [row for row in self.ticker_rows if str(row.get("symbol", "")).upper() in wanted]

    def exchange_info(self):
        return {"symbols": []}


class FakeScanner:
    def __init__(self, signals, gateway=None) -> None:
        self.gateway = gateway or FakeGateway()
        self.signals = signals

    def scan(self):
        return SimpleNamespace(scanned_symbols=10, returned_signals=len(self.signals)), self.signals


class TradingTests(unittest.TestCase):
    def test_state_store_recovers_trailing_json_garbage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            path.write_text(
                '{"kind":"trading_state","version":1,"positions":[],"events":[]}'
                '自动交易未启用，仅完成信号扫描和仓位检查。',
                encoding="utf-8",
            )
            store = TradingStateStore(path)

            events = store.load_events()
            repaired = path.read_text(encoding="utf-8")
            backups = list(Path(temp_dir).glob("state.json.corrupt-*"))

        self.assertEqual(events, [])
        self.assertIn('"events": []', repaired)
        self.assertEqual(len(backups), 1)

    def test_paper_run_opens_position_from_high_score_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner([_signal()])
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                )
            )
            stored_events = store.load_events()

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.open_positions[0].symbol, "BTCUSDT")
        self.assertEqual(report.events[0].status, "paper_filled")
        self.assertEqual(stored_events[0].status, "paper_filled")
        self.assertEqual(scanner.gateway.buy_calls, [])

    def test_risk_blocked_symbol_does_not_open_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner([_signal()])
            trader = AutoTrader(
                scanner=scanner,
                state_store=store,
                blocked_symbols={"BTCUSDT": "链上高严重度交易所流入"},
            )

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                )
            )
            stored_events = store.load_events()

        self.assertEqual(len(report.open_positions), 0)
        self.assertEqual(report.events[0].status, "risk_blocked")
        self.assertEqual(stored_events[0].status, "risk_blocked")

    def test_live_run_is_blocked_without_confirmation_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner([_signal()])
            trader = AutoTrader(scanner=scanner, state_store=store)

            with patch.dict("os.environ", {}, clear=True):
                report = trader.run_once(
                    AutoTradeDefaults(
                        enabled=True,
                        mode="live",
                        order_test_only=False,
                    )
                )

        self.assertEqual(report.events[0].status, "blocked")
        self.assertEqual(len(report.open_positions), 0)
        self.assertEqual(scanner.gateway.buy_calls, [])

    def test_live_order_test_does_not_record_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner([_signal()])
            trader = AutoTrader(scanner=scanner, state_store=store)

            with patch.dict("os.environ", {"AI_TRADE_LIVE_CONFIRM": LIVE_CONFIRM_VALUE}):
                report = trader.run_once(
                    AutoTradeDefaults(
                        enabled=True,
                        mode="live",
                        order_test_only=True,
                    )
                )

        self.assertEqual(report.events[0].status, "test_accepted")
        self.assertEqual(len(report.open_positions), 0)
        self.assertEqual(scanner.gateway.buy_calls[0]["test"], True)

    def test_live_filled_position_uses_exchange_executed_quantity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            gateway = FakeGateway({"orderId": 123, "executedQty": "0.40000000", "cummulativeQuoteQty": "48.00000000"})
            scanner = FakeScanner([_signal(price=100.0)], gateway=gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)

            with patch.dict("os.environ", {"AI_TRADE_LIVE_CONFIRM": LIVE_CONFIRM_VALUE}):
                report = trader.run_once(
                    AutoTradeDefaults(
                        enabled=True,
                        mode="live",
                        quote_order_qty=50.0,
                        order_test_only=False,
                    )
                )

        self.assertEqual(report.events[0].status, "filled")
        self.assertEqual(report.open_positions[0].quantity, 0.4)
        self.assertEqual(report.open_positions[0].entry_price, 120.0)

    def test_quantity_floor_respects_step_size(self) -> None:
        self.assertEqual(AutoTrader._floor_quantity(1.234567, "0.00100000"), 1.234)
        self.assertEqual(AutoTrader._floor_quantity(1.234567, "0.01000000"), 1.23)

    def test_paper_exit_records_realized_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=0.5,
                        entry_price=100.0,
                        quote_notional=50.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=109.0,
                        mode="paper",
                    )
                ]
            )
            scanner = FakeScanner([_signal(price=110.0)])
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(AutoTradeDefaults(enabled=True, mode="paper", score_threshold=99.0))
            stored_events = store.load_events()

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].action, "SELL")
        self.assertEqual(report.events[0].exit_reason, "take_profit")
        self.assertAlmostEqual(report.events[0].realized_pnl, 5.0)
        self.assertAlmostEqual(report.events[0].realized_pnl_pct, 10.0)
        self.assertEqual(stored_events[0].realized_pnl, 5.0)

    def test_profit_protection_moves_stop_and_exits_before_winner_turns_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=0.5,
                        entry_price=100.0,
                        quote_notional=50.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=109.0,
                        mode="paper",
                    )
                ]
            )

            trader = AutoTrader(scanner=FakeScanner([_signal(price=104.0)]), state_store=store)
            first_report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_trigger_pct=3.0,
                    profit_protection_lock_pct=0.5,
                    trailing_stop_pct=2.0,
                )
            )
            protected_position = store.load()[0]

            trader = AutoTrader(scanner=FakeScanner([_signal(price=101.5)]), state_store=store)
            second_report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_trigger_pct=3.0,
                    profit_protection_lock_pct=0.5,
                    trailing_stop_pct=2.0,
                )
            )

        self.assertEqual(len(first_report.open_positions), 1)
        self.assertAlmostEqual(protected_position.highest_price or 0.0, 104.0)
        self.assertAlmostEqual(protected_position.stop_price, 101.92)
        self.assertEqual(second_report.open_positions, [])
        self.assertEqual(second_report.events[0].exit_reason, "profit_protect_stop")
        self.assertAlmostEqual(second_report.events[0].realized_pnl, 0.75)
        self.assertGreater(second_report.events[0].realized_pnl or 0.0, 0.0)

    def test_exit_check_uses_ticker_price_for_positions_outside_signal_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="ETHUSDT",
                        quantity=1.0,
                        entry_price=100.0,
                        quote_notional=100.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=108.0,
                        mode="paper",
                    )
                ]
            )
            gateway = FakeGateway(ticker_rows=[{"symbol": "ETHUSDT", "lastPrice": "110.0"}])
            scanner = FakeScanner([_signal(symbol="BTCUSDT", price=100.0)], gateway=gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(AutoTradeDefaults(enabled=True, mode="paper", score_threshold=99.0))

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].symbol, "ETHUSDT")
        self.assertEqual(report.events[0].exit_reason, "take_profit")
        self.assertEqual(gateway.ticker24hr_calls, 0)
        self.assertEqual(gateway.ticker24hr_symbols_calls, [["ETHUSDT"]])

    def test_paper_mode_does_not_simulate_close_for_live_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=0.5,
                        entry_price=100.0,
                        quote_notional=50.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=109.0,
                        mode="live",
                    )
                ]
            )
            scanner = FakeScanner([_signal(price=110.0)])
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(AutoTradeDefaults(enabled=True, mode="paper", score_threshold=99.0))
            stored_positions = store.load()

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.events[0].status, "blocked")
        self.assertEqual(stored_positions[0].mode, "live")

    def test_disabled_autotrade_does_not_live_close_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=0.5,
                        entry_price=100.0,
                        quote_notional=50.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=109.0,
                        mode="live",
                    )
                ]
            )
            gateway = FakeGateway()
            scanner = FakeScanner([_signal(price=110.0)], gateway=gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)

            with patch.dict("os.environ", {"AI_TRADE_LIVE_CONFIRM": LIVE_CONFIRM_VALUE}):
                report = trader.run_once(AutoTradeDefaults(enabled=False, mode="live", score_threshold=99.0))

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.events[0].status, "blocked")
        self.assertIn("未启用", report.events[0].message)
        self.assertEqual(gateway.sell_calls, [])

    def test_live_close_requires_confirmation_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=0.5,
                        entry_price=100.0,
                        quote_notional=50.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=109.0,
                        mode="live",
                    )
                ]
            )
            gateway = FakeGateway()
            scanner = FakeScanner([_signal(price=110.0)], gateway=gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)

            with patch.dict("os.environ", {}, clear=True):
                report = trader.run_once(AutoTradeDefaults(enabled=True, mode="live", score_threshold=99.0))

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.events[0].status, "blocked")
        self.assertIn("AI_TRADE_LIVE_CONFIRM", report.events[0].message)
        self.assertEqual(gateway.sell_calls, [])

    def test_confirmed_live_close_submits_sell_and_records_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=0.5,
                        entry_price=100.0,
                        quote_notional=50.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=109.0,
                        mode="live",
                    )
                ]
            )
            gateway = FakeGateway()
            scanner = FakeScanner([_signal(price=110.0)], gateway=gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)

            with patch.dict("os.environ", {"AI_TRADE_LIVE_CONFIRM": LIVE_CONFIRM_VALUE}):
                report = trader.run_once(
                    AutoTradeDefaults(enabled=True, mode="live", order_test_only=False, score_threshold=99.0)
                )

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].status, "filled")
        self.assertEqual(gateway.sell_calls[0]["symbol"], "BTCUSDT")
        self.assertAlmostEqual(report.events[0].realized_pnl, 5.0)


if __name__ == "__main__":
    unittest.main()
