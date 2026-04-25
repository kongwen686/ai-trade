from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from trade_signal_app.runtime_config import AutoTradeDefaults
from trade_signal_app.trading import AutoTrader, LIVE_CONFIRM_VALUE, TradingStateStore


def _signal(symbol: str = "BTCUSDT", score: float = 82.0, price: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        score=score,
        grade="A",
        ticker=SimpleNamespace(last_price=price),
        indicators=SimpleNamespace(volume_ratio=1.4, buy_pressure_ratio=0.62),
    )


class FakeGateway:
    def __init__(self, buy_response=None) -> None:
        self.buy_calls = []
        self.buy_response = buy_response or {"orderId": 123}

    def order_market_buy(self, **kwargs):
        self.buy_calls.append(kwargs)
        return self.buy_response


class FakeScanner:
    def __init__(self, signals, gateway=None) -> None:
        self.gateway = gateway or FakeGateway()
        self.signals = signals

    def scan(self):
        return SimpleNamespace(scanned_symbols=10, returned_signals=len(self.signals)), self.signals


class TradingTests(unittest.TestCase):
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

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.open_positions[0].symbol, "BTCUSDT")
        self.assertEqual(report.events[0].status, "paper_filled")
        self.assertEqual(scanner.gateway.buy_calls, [])

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


if __name__ == "__main__":
    unittest.main()
