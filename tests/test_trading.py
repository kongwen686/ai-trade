from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from trade_signal_app.runtime_config import AutoTradeDefaults
from trade_signal_app.time_utils import now_app_time
from trade_signal_app.trading import AutoTrader, LIVE_CONFIRM_VALUE, TradingEvent, TradingPosition, TradingStateStore


def _signal(
    symbol: str = "BTCUSDT",
    score: float = 82.0,
    price: float = 100.0,
    quote_volume: float = 20_000_000.0,
    *,
    rsi: float = 50.0,
    price_vs_ema20_pct: float = 0.0,
    recent_change_pct: float = 0.0,
    support_level: float = 0.0,
    resistance_level: float = 0.0,
    support_distance_pct: float = 0.0,
    resistance_distance_pct: float = 0.0,
    support_strength: float = 0.0,
    structure_risk_reward: float = 0.0,
    volatility_regime: str = "normal",
    volatility_percentile: float = 50.0,
    volatility_ratio: float = 1.0,
    atr_pct: float = 1.0,
    volume_ratio: float = 1.4,
    buy_pressure_ratio: float = 0.62,
) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        score=score,
        grade="A",
        ticker=SimpleNamespace(last_price=price, quote_volume=quote_volume),
        indicators=SimpleNamespace(
            volume_ratio=volume_ratio,
            buy_pressure_ratio=buy_pressure_ratio,
            rsi_14=rsi,
            price_vs_ema20_pct=price_vs_ema20_pct,
            recent_change_pct=recent_change_pct,
            support_level=support_level,
            resistance_level=resistance_level,
            support_distance_pct=support_distance_pct,
            resistance_distance_pct=resistance_distance_pct,
            support_strength=support_strength,
            structure_risk_reward=structure_risk_reward,
            volatility_regime=volatility_regime,
            volatility_percentile=volatility_percentile,
            volatility_ratio=volatility_ratio,
            atr_pct=atr_pct,
        ),
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


class FakeTradeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def notify_trade(self, *, event, position=None) -> bool:
        self.calls.append((event.action, event.symbol, position.symbol if position is not None else ""))
        return True


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

    def test_state_store_keeps_full_sqlite_history_when_json_snapshot_rolls_over(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            store = TradingStateStore(path)
            store.append_events(
                [
                    TradingEvent(action="BUY", symbol="BTCUSDT", mode="paper", status="paper_filled", message="buy"),
                    *[
                        TradingEvent(action="SKIP", symbol="*", mode="paper", status="no_signal", message=f"skip {index}")
                        for index in range(6)
                    ],
                    TradingEvent(
                        action="SELL",
                        symbol="BTCUSDT",
                        mode="paper",
                        status="paper_filled",
                        message="sell",
                        realized_pnl=4.0,
                    ),
                    *[
                        TradingEvent(action="ALERT", symbol="BTCUSDT", mode="paper", status="emergency_drawdown", message=f"alert {index}")
                        for index in range(6)
                    ],
                ],
                limit=5,
            )
            stored_events = store.load_events()
            json_events = json.loads(path.read_text(encoding="utf-8"))["events"]

        self.assertEqual(len(stored_events), 14)
        self.assertEqual(len(json_events), 5)
        self.assertEqual(
            [(event.action, event.status, event.message) for event in stored_events if event.status == "paper_filled"],
            [("BUY", "paper_filled", "buy"), ("SELL", "paper_filled", "sell")],
        )
        self.assertEqual([event["message"] for event in json_events[-3:]], ["alert 3", "alert 4", "alert 5"])

    def test_paper_run_opens_position_from_high_score_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner([_signal()])
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

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
        self.assertEqual(notifier.calls, [("BUY", "BTCUSDT", "BTCUSDT")])

    def test_filtered_candidates_return_limited_chinese_summary_log(self) -> None:
        signals = [
            _signal(symbol="LOWUSDT", score=70.0),
            _signal(symbol="VOLUMEUSDT", score=82.0, volume_ratio=0.8),
            _signal(symbol="PRESSUREUSDT", score=82.0, buy_pressure_ratio=0.4),
        ]
        config = AutoTradeDefaults(
            enabled=True,
            mode="paper",
            score_threshold=75.0,
            min_volume_ratio=1.1,
            min_buy_pressure=0.52,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            trader = AutoTrader(scanner=FakeScanner(signals), state_store=store)

            first = trader.run_once(config)
            first_persisted = store.load_events()
            second = trader.run_once(config)
            second_persisted = store.load_events()

        self.assertEqual(first.events[0].status, "no_eligible_signal")
        self.assertIn("本轮扫描 3 个候选，未产生订单", first.events[0].message)
        self.assertIn("评分低于 75.0 的 1 个", first.events[0].message)
        self.assertIn("量比低于 1.10 的 1 个", first.events[0].message)
        self.assertIn("买压低于 0.52 的 1 个", first.events[0].message)
        self.assertEqual(second.events[0].status, "no_eligible_signal")
        self.assertEqual(len(first_persisted), 1)
        self.assertEqual(len(second_persisted), 1)

    def test_isolated_paper_mode_can_open_same_symbol_as_live_position(self) -> None:
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
                        stop_price=90.0,
                        take_profit_price=120.0,
                        mode="live",
                    )
                ]
            )
            scanner = FakeScanner([_signal(symbol="BTCUSDT", price=100.0)])
            trader = AutoTrader(scanner=scanner, state_store=store, isolate_mode=True)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                )
            )
            stored_positions = store.load()

        paper_positions = [position for position in stored_positions if position.mode == "paper"]
        live_positions = [position for position in stored_positions if position.mode == "live"]
        self.assertEqual(len(paper_positions), 1)
        self.assertEqual(len(live_positions), 1)
        self.assertEqual(paper_positions[0].symbol, "BTCUSDT")
        self.assertEqual(live_positions[0].symbol, "BTCUSDT")
        self.assertEqual(report.events[0].status, "paper_filled")
        self.assertEqual(scanner.gateway.buy_calls, [])

    def test_paper_entry_prefers_live_ticker_price_over_signal_price(self) -> None:
        class LivePriceGateway(FakeGateway):
            def ticker_price(self, symbol):
                self.ticker24hr_symbols_calls.append([symbol])
                return 125.0

        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            gateway = LivePriceGateway()
            scanner = FakeScanner([_signal(price=100.0)], gateway=gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(AutoTradeDefaults(enabled=True, mode="paper", quote_order_qty=50.0, score_threshold=75.0))

        self.assertEqual(len(report.open_positions), 1)
        self.assertAlmostEqual(report.open_positions[0].entry_price, 125.0)
        self.assertAlmostEqual(report.open_positions[0].quantity, 0.4)
        self.assertEqual(gateway.ticker24hr_symbols_calls, [["BTCUSDT"]])

    def test_entry_price_prefers_execution_gateway_over_scanner_gateway(self) -> None:
        class LivePriceGateway(FakeGateway):
            def __init__(self, price: float) -> None:
                super().__init__()
                self.price = price

            def ticker_price(self, symbol):
                self.ticker24hr_symbols_calls.append([symbol])
                return self.price

        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner_gateway = LivePriceGateway(101.0)
            execution_gateway = LivePriceGateway(130.0)
            scanner = FakeScanner([_signal(price=100.0)], gateway=scanner_gateway)
            trader = AutoTrader(scanner=scanner, state_store=store)
            trader.set_execution_gateway(execution_gateway)

            report = trader.run_once(AutoTradeDefaults(enabled=True, mode="paper", quote_order_qty=65.0, score_threshold=75.0))

        self.assertEqual(len(report.open_positions), 1)
        self.assertAlmostEqual(report.open_positions[0].entry_price, 130.0)
        self.assertEqual(scanner_gateway.ticker24hr_symbols_calls, [])
        self.assertEqual(execution_gateway.ticker24hr_symbols_calls, [["BTCUSDT"]])

    def test_paper_leverage_scales_notional_and_margin_roi(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            trader = AutoTrader(scanner=FakeScanner([_signal(price=100.0)]), state_store=store)

            first_report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=25.0,
                    leverage=5.0,
                    score_threshold=75.0,
                    take_profit_pct=2.0,
                )
            )

            trader = AutoTrader(scanner=FakeScanner([_signal(price=102.0, score=10.0)]), state_store=store)
            second_report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=25.0,
                    leverage=5.0,
                    score_threshold=99.0,
                    take_profit_pct=2.0,
                )
            )

        self.assertAlmostEqual(first_report.open_positions[0].quantity, 1.25)
        self.assertAlmostEqual(first_report.open_positions[0].quote_notional, 125.0)
        self.assertAlmostEqual(first_report.open_positions[0].margin_notional or 0.0, 25.0)
        self.assertEqual(first_report.open_positions[0].leverage, 5.0)
        self.assertEqual(second_report.open_positions, [])
        self.assertEqual(second_report.events[0].exit_reason, "take_profit")
        self.assertAlmostEqual(second_report.events[0].realized_pnl, 2.5)
        self.assertAlmostEqual(second_report.events[0].realized_pnl_pct, 10.0)

    def test_trend_following_profile_holds_winner_with_strong_signal(self) -> None:
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
                    )
                ]
            )
            scanner = FakeScanner([_signal(score=90.0, price=105.0)])
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    exit_profile="trend_following",
                    trend_hold_min_score=85.0,
                    trend_hold_min_volume_ratio=1.2,
                    trend_hold_min_buy_pressure=0.55,
                )
            )

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.events[0].action, "HOLD")
        self.assertEqual(report.events[0].status, "trend_hold")
        self.assertGreater(report.open_positions[0].stop_price, 100.0)

    def test_emergency_drawdown_records_alert_before_stop_loss(self) -> None:
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
                        take_profit_price=120.0,
                        mode="paper",
                        highest_price=110.0,
                    )
                ]
            )
            scanner = FakeScanner([_signal(score=10.0, price=106.0)])
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_enabled=False,
                    emergency_drawdown_pct=2.5,
                )
            )

        self.assertEqual(len(report.open_positions), 1)
        self.assertEqual(report.events[0].action, "ALERT")
        self.assertEqual(report.events[0].status, "emergency_drawdown")
        self.assertEqual(notifier.calls, [("ALERT", "BTCUSDT", "BTCUSDT")])

    def test_emergency_drawdown_alert_respects_cooldown(self) -> None:
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
                        take_profit_price=120.0,
                        mode="paper",
                        highest_price=110.0,
                    )
                ]
            )
            store.append_events(
                [
                    TradingEvent(
                        action="ALERT",
                        symbol="BTCUSDT",
                        mode="paper",
                        status="emergency_drawdown",
                        message="recent alert",
                        price=107.0,
                        quantity=1.0,
                        quote_notional=100.0,
                        created_at=now_app_time(),
                    )
                ]
            )
            scanner = FakeScanner([_signal(score=10.0, price=106.0)])
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_enabled=False,
                    emergency_drawdown_pct=2.5,
                    cooldown_minutes=240,
                )
            )

        self.assertEqual(report.open_positions[0].symbol, "BTCUSDT")
        self.assertEqual([event.status for event in report.events], ["no_eligible_signal"])
        self.assertIn("敞口上限阻断 1 个", report.events[0].message)
        self.assertEqual(notifier.calls, [])

    def test_emergency_drawdown_alert_respects_global_cooldown_across_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="BTCUSDT",
                        quantity=1.0,
                        entry_price=100.0,
                        quote_notional=100.0,
                        score=90.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=120.0,
                        mode="paper",
                        highest_price=110.0,
                    )
                ]
            )
            store.append_events(
                [
                    TradingEvent(
                        action="ALERT",
                        symbol="ETHUSDT",
                        mode="paper",
                        status="emergency_drawdown",
                        message="recent alert",
                        created_at=now_app_time(),
                    )
                ]
            )
            trader = AutoTrader(scanner=FakeScanner([_signal(score=90.0, price=106.0)]), state_store=store, trade_notifier=FakeTradeNotifier())

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_enabled=False,
                    emergency_alert_global_cooldown_minutes=60,
                    emergency_alert_symbol_cooldown_minutes=0,
                )
            )

        self.assertEqual([event.status for event in report.events], ["no_eligible_signal"])
        self.assertNotIn("emergency_drawdown", {event.status for event in report.events})

    def test_low_liquidity_emergency_drawdown_requires_clear_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="MICROUSDT",
                        quantity=1.0,
                        entry_price=100.0,
                        quote_notional=100.0,
                        score=82.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=120.0,
                        mode="paper",
                        highest_price=110.0,
                    )
                ]
            )
            notifier = FakeTradeNotifier()
            trader = AutoTrader(
                scanner=FakeScanner([_signal(symbol="MICROUSDT", score=82.0, price=104.0, quote_volume=5_000_000.0)]),
                state_store=store,
                trade_notifier=notifier,
            )

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_enabled=False,
                    emergency_drawdown_pct=2.5,
                    emergency_low_liquidity_quote_volume=10_000_000,
                    emergency_low_liquidity_drawdown_multiplier=2.0,
                    emergency_low_liquidity_min_score=85.0,
                )
            )

        self.assertEqual([event.status for event in report.events], ["no_eligible_signal"])
        self.assertNotIn("emergency_drawdown", {event.status for event in report.events})
        self.assertEqual(notifier.calls, [])

    def test_low_liquidity_emergency_drawdown_allows_strong_deep_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            store.save(
                [
                    TradingPosition(
                        symbol="MICROUSDT",
                        quantity=1.0,
                        entry_price=100.0,
                        quote_notional=100.0,
                        score=90.0,
                        grade="A",
                        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                        stop_price=96.0,
                        take_profit_price=120.0,
                        mode="paper",
                        highest_price=110.0,
                    )
                ]
            )
            notifier = FakeTradeNotifier()
            trader = AutoTrader(
                scanner=FakeScanner([_signal(symbol="MICROUSDT", score=90.0, price=104.0, quote_volume=5_000_000.0)]),
                state_store=store,
                trade_notifier=notifier,
            )

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    score_threshold=99.0,
                    profit_protection_enabled=False,
                    emergency_drawdown_pct=2.5,
                    emergency_low_liquidity_quote_volume=10_000_000,
                    emergency_low_liquidity_drawdown_multiplier=2.0,
                    emergency_low_liquidity_min_score=85.0,
                )
            )

        self.assertEqual(report.events[0].status, "emergency_drawdown")
        self.assertEqual(notifier.calls, [("ALERT", "MICROUSDT", "MICROUSDT")])

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

    def test_paper_run_waits_for_pullback_after_short_term_spike(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner(
                [
                    _signal(
                        rsi=78.0,
                        price_vs_ema20_pct=8.0,
                        recent_change_pct=6.2,
                    )
                ]
            )
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                )
            )
            stored_events = store.load_events()

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].status, "wait_pullback")
        self.assertIn("等待回调", report.events[0].message)
        self.assertEqual(stored_events[0].status, "wait_pullback")
        self.assertEqual(notifier.calls, [])

    def test_paper_run_waits_for_extreme_volatility_to_cool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner(
                [
                    _signal(
                        volatility_regime="extreme",
                        volatility_percentile=98.0,
                        volatility_ratio=2.4,
                        atr_pct=4.2,
                    )
                ]
            )
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                )
            )

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].status, "wait_volatility")
        self.assertIn("极端波动过滤", report.events[0].message)
        self.assertEqual(notifier.calls, [])

    def test_paper_run_waits_for_support_when_structure_risk_reward_is_weak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner(
                [
                    _signal(
                        support_level=94.0,
                        resistance_level=101.0,
                        support_distance_pct=6.0,
                        resistance_distance_pct=1.0,
                        support_strength=1.0,
                        structure_risk_reward=0.4,
                    )
                ]
            )
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                )
            )

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].status, "wait_support")
        self.assertIn("等待更合理买点", report.events[0].message)
        self.assertEqual(notifier.calls, [])

    def test_paper_entry_uses_structure_stop_and_resistance_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingStateStore(Path(temp_dir) / "state.json")
            scanner = FakeScanner(
                [
                    _signal(
                        price=100.0,
                        support_level=98.0,
                        resistance_level=106.0,
                        support_distance_pct=2.0,
                        resistance_distance_pct=6.0,
                        support_strength=3.0,
                        structure_risk_reward=2.0,
                    )
                ]
            )
            trader = AutoTrader(scanner=scanner, state_store=store)

            report = trader.run_once(
                AutoTradeDefaults(
                    enabled=True,
                    mode="paper",
                    quote_order_qty=50.0,
                    score_threshold=75.0,
                    stop_loss_pct=4.0,
                    take_profit_pct=9.0,
                )
            )

        self.assertEqual(len(report.open_positions), 1)
        self.assertAlmostEqual(report.open_positions[0].stop_price, 97.412)
        self.assertAlmostEqual(report.open_positions[0].take_profit_price, 105.576)

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
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

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
        self.assertEqual(notifier.calls, [])

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
            notifier = FakeTradeNotifier()
            trader = AutoTrader(scanner=scanner, state_store=store, trade_notifier=notifier)

            report = trader.run_once(AutoTradeDefaults(enabled=True, mode="paper", score_threshold=99.0))
            stored_events = store.load_events()

        self.assertEqual(report.open_positions, [])
        self.assertEqual(report.events[0].action, "SELL")
        self.assertEqual(report.events[0].exit_reason, "take_profit")
        self.assertAlmostEqual(report.events[0].realized_pnl, 5.0)
        self.assertAlmostEqual(report.events[0].realized_pnl_pct, 10.0)
        self.assertEqual(stored_events[0].realized_pnl, 5.0)
        self.assertEqual(notifier.calls, [("SELL", "BTCUSDT", "BTCUSDT")])

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
