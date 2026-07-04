from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import zipfile

from trade_signal_app import __version__
from trade_signal_app.backtest import (
    archive_key,
    merge_candles,
    parse_args,
    resolve_archive_paths,
    resolve_commission_from_account_payload,
    resolve_commission_from_symbol_payload,
    resolve_execution_config_from_binance,
    resolve_slippage_bps,
    run_backtest_for_series,
    run_overnight_seasonality_backtest,
    run_portfolio_backtest,
    run_rebalance_premium_backtest,
    simulate_long_trade,
)
from trade_signal_app.models import BacktestReport, BacktestSignalEvent, Candlestick
from trade_signal_app.strategy import EntryRuleConfig, ExecutionConfig


def _make_backtest_candles() -> list[Candlestick]:
    candles: list[Candlestick] = []
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
        candles.append(
            Candlestick(
                open_time=start + timedelta(hours=4 * index),
                close_time=start + timedelta(hours=(4 * index) + 4) - timedelta(milliseconds=1),
                open_price=price - 0.55,
                high_price=price + 1.1,
                low_price=price - 0.95,
                close_price=price,
                volume=volume,
                quote_volume=volume * price,
                trade_count=150 + index * 4,
                taker_buy_base_volume=volume * taker_ratio,
                taker_buy_quote_volume=volume * price * taker_ratio,
            )
        )
    return candles


def _make_hourly_candles() -> list[Candlestick]:
    candles: list[Candlestick] = []
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    for index in range(72):
        open_time = start + timedelta(hours=index)
        close_time = open_time + timedelta(hours=1) - timedelta(milliseconds=1)
        if open_time.hour in {22, 23}:
            price += 0.35
        else:
            price += 0.02 if index % 3 else -0.01
        candles.append(
            Candlestick(
                open_time=open_time,
                close_time=close_time,
                open_price=price - 0.15,
                high_price=price + 0.4,
                low_price=price - 0.35,
                close_price=price,
                volume=1000 + index,
                quote_volume=(1000 + index) * price,
                trade_count=100 + index,
                taker_buy_base_volume=(1000 + index) * 0.55,
                taker_buy_quote_volume=(1000 + index) * price * 0.55,
            )
        )
    return candles


class BacktestTests(unittest.TestCase):
    def test_parse_args_supports_version(self) -> None:
        buffer = io.StringIO()
        with self.assertRaises(SystemExit) as exc, redirect_stdout(buffer):
            parse_args(["--version"])

        self.assertEqual(exc.exception.code, 0)
        self.assertIn(__version__, buffer.getvalue())

    def test_archive_key(self) -> None:
        symbol, interval = archive_key(Path("BTCUSDT-4h-2025-01.zip"))
        self.assertEqual(symbol, "BTCUSDT")
        self.assertEqual(interval, "4h")

        symbol, interval = archive_key(Path("data/tradingview_klines/BINANCE/ETHUSDT/1h.csv"))
        self.assertEqual(symbol, "ETHUSDT")
        self.assertEqual(interval, "1h")

    def test_merge_candles_deduplicates(self) -> None:
        row1 = "1735689600000000,4.1,4.2,4.0,4.15,539.23,1735703999999999,2240.39,13,401.82,1669.98,0\n"
        row2 = "1735704000000000,4.15,4.3,4.1,4.25,640.00,1735718399999999,2720.00,18,480.00,2010.00,0\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "BTCUSDT-4h-2025-01.zip"
            second = Path(temp_dir) / "BTCUSDT-4h-2025-02.zip"
            with zipfile.ZipFile(first, "w") as handle:
                handle.writestr("BTCUSDT-4h-2025-01.csv", row1 + row2)
            with zipfile.ZipFile(second, "w") as handle:
                handle.writestr("BTCUSDT-4h-2025-02.csv", row2)

            candles = merge_candles([first, second])
            self.assertEqual(len(candles), 2)
            self.assertEqual(candles[0].close_price, 4.15)
            self.assertEqual(candles[1].close_price, 4.25)

    def test_resolve_and_merge_tradingview_csv(self) -> None:
        csv_rows = "\n".join(
            [
                "datetime,open,high,low,close,volume,quote_volume,trade_count",
                "2025-01-01T00:00:00+00:00,100,105,98,104,10,1040,20",
                "2025-01-01T04:00:00+00:00,104,108,102,107,12,1284,22",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "BINANCE" / "BTCUSDT" / "4h.csv"
            path.parent.mkdir(parents=True)
            path.write_text(csv_rows, encoding="utf-8")

            resolved = resolve_archive_paths([str(Path(temp_dir))])
            self.assertEqual(resolved, [path.resolve()])
            candles = merge_candles(resolved)
            self.assertEqual(len(candles), 2)
            self.assertEqual(candles[0].close_price, 104.0)
            self.assertEqual(candles[1].quote_volume, 1284.0)

    def test_run_backtest_generates_positive_forward_stats(self) -> None:
        report = run_backtest_for_series(
            symbol="TESTUSDT",
            interval="4h",
            candles=_make_backtest_candles(),
            lookback_bars=80,
            score_threshold=60.0,
            holding_periods=[3, 6, 12],
            entry_config=EntryRuleConfig(
                min_score=60.0,
                min_volume_ratio=1.0,
                min_buy_pressure_ratio=0.5,
                max_rsi=99.0,
                require_kdj_confirmation=False,
            ),
            execution_config=ExecutionConfig(fee_bps=0.0, slippage_bps=0.0, capital_fraction_pct=100.0),
            cooldown_bars=6,
        )
        self.assertGreater(report.signal_count, 0)
        self.assertEqual(len(report.stats), 3)
        self.assertGreater(report.stats[0].avg_return_pct, 0)
        self.assertTrue(any(event.grade in {"A", "B", "C"} for event in report.events))
        self.assertIsNotNone(report.trade_stat)
        self.assertGreater(len(report.equity_curve), 0)
        self.assertGreater(len(report.buy_hold_equity_curve), 0)
        self.assertGreater(report.buy_hold_equity_curve[-1].equity, 1.0)
        self.assertTrue(all(event.exit_reason is not None for event in report.events))

    def test_simulate_long_trade_hits_take_profit(self) -> None:
        candles = _make_backtest_candles()[:80]
        candles[61] = Candlestick(
            open_time=candles[61].open_time,
            close_time=candles[61].close_time,
            open_price=100.0,
            high_price=112.0,
            low_price=99.5,
            close_price=109.0,
            volume=candles[61].volume,
            quote_volume=candles[61].quote_volume,
            trade_count=candles[61].trade_count,
            taker_buy_base_volume=candles[61].taker_buy_base_volume,
            taker_buy_quote_volume=candles[61].taker_buy_quote_volume,
        )
        trade = simulate_long_trade(
            candles=candles,
            signal_index=60,
            max_holding_bars=6,
            stop_loss_pct=4.0,
            take_profit_pct=9.0,
            entry_fee_bps=0.0,
            exit_fee_bps=0.0,
            slippage_bps=0.0,
        )
        self.assertEqual(trade.exit_reason, "take_profit")
        self.assertGreater(trade.realized_return_pct, 8.9)
        self.assertAlmostEqual(trade.gross_return_pct, trade.realized_return_pct, places=4)

    def test_simulate_long_trade_costs_reduce_return(self) -> None:
        candles = _make_backtest_candles()[:80]
        trade = simulate_long_trade(
            candles=candles,
            signal_index=60,
            max_holding_bars=6,
            stop_loss_pct=20.0,
            take_profit_pct=20.0,
            entry_fee_bps=10.0,
            exit_fee_bps=10.0,
            slippage_bps=5.0,
        )
        self.assertLess(trade.realized_return_pct, trade.gross_return_pct)

    def test_maker_taker_fee_model_changes_realized_return(self) -> None:
        candles = _make_backtest_candles()[:80]
        flat = simulate_long_trade(
            candles=candles,
            signal_index=60,
            max_holding_bars=6,
            stop_loss_pct=20.0,
            take_profit_pct=20.0,
            entry_fee_bps=10.0,
            exit_fee_bps=10.0,
            slippage_bps=0.0,
        )
        discounted = simulate_long_trade(
            candles=candles,
            signal_index=60,
            max_holding_bars=6,
            stop_loss_pct=20.0,
            take_profit_pct=20.0,
            entry_fee_bps=6.0,
            exit_fee_bps=8.0,
            slippage_bps=0.0,
        )
        self.assertGreater(discounted.realized_return_pct, flat.realized_return_pct)

    def test_dynamic_slippage_rises_when_liquidity_is_thin(self) -> None:
        low = resolve_slippage_bps(
            base_slippage_bps=5.0,
            slippage_model="dynamic",
            signal_quote_volume=1000.0,
            reference_quote_volumes=[5000.0, 5200.0, 5100.0, 4800.0],
            min_slippage_bps=2.0,
            max_slippage_bps=25.0,
        )
        high = resolve_slippage_bps(
            base_slippage_bps=5.0,
            slippage_model="dynamic",
            signal_quote_volume=12000.0,
            reference_quote_volumes=[5000.0, 5200.0, 5100.0, 4800.0],
            min_slippage_bps=2.0,
            max_slippage_bps=25.0,
        )
        self.assertGreater(low, high)
        self.assertGreaterEqual(high, 2.0)

    def test_resolve_commission_from_account_payload(self) -> None:
        maker_fee_bps, taker_fee_bps, fee_discount_pct = resolve_commission_from_account_payload(
            {
                "commissionRates": {
                    "maker": "0.00060000",
                    "taker": "0.00100000",
                }
            }
        )
        self.assertEqual(maker_fee_bps, 6.0)
        self.assertEqual(taker_fee_bps, 10.0)
        self.assertEqual(fee_discount_pct, 0.0)

    def test_resolve_commission_from_symbol_payload_applies_discount(self) -> None:
        maker_fee_bps, taker_fee_bps, fee_discount_pct = resolve_commission_from_symbol_payload(
            {
                "standardCommission": {"maker": "0.00060000", "taker": "0.00100000"},
                "specialCommission": {"maker": "0.00010000", "taker": "0.00020000"},
                "taxCommission": {"maker": "0.00010000", "taker": "0.00010000"},
                "discount": {
                    "enabledForAccount": True,
                    "enabledForSymbol": True,
                    "discount": "0.25000000",
                },
            },
            apply_discount=True,
        )
        self.assertEqual(fee_discount_pct, 25.0)
        self.assertEqual(maker_fee_bps, 6.5)
        self.assertEqual(taker_fee_bps, 10.5)

    def test_resolve_execution_config_from_binance_symbol_source(self) -> None:
        class StubGateway:
            def has_user_data_auth(self) -> bool:
                return True

            def account_commission(self, symbol: str) -> dict:
                self.last_symbol = symbol
                return {
                    "standardCommission": {"maker": "0.00060000", "taker": "0.00100000"},
                    "specialCommission": {"maker": "0.00000000", "taker": "0.00000000"},
                    "taxCommission": {"maker": "0.00000000", "taker": "0.00000000"},
                    "discount": {
                        "enabledForAccount": True,
                        "enabledForSymbol": True,
                        "discount": "0.75000000",
                    },
                }

        gateway = StubGateway()
        config = resolve_execution_config_from_binance(
            gateway=gateway,  # type: ignore[arg-type]
            execution_config=ExecutionConfig(fee_source="symbol"),
            symbol="BTCUSDT",
        )
        self.assertEqual(config.fee_model, "maker_taker")
        self.assertEqual(config.maker_fee_bps, 4.5)
        self.assertEqual(config.taker_fee_bps, 7.5)
        self.assertEqual(config.fee_discount_pct, 25.0)

    def test_portfolio_backtest_selects_top_scores_per_timestamp(self) -> None:
        event_time = datetime(2025, 1, 10, tzinfo=timezone.utc)
        reports = [
            BacktestReport(
                symbol="BTCUSDT",
                interval="4h",
                candle_count=100,
                evaluated_bars=20,
                signal_count=2,
                lookback_bars=80,
                score_threshold=70,
                cooldown_bars=6,
                fee_bps=10.0,
                slippage_bps=5.0,
                capital_fraction_pct=100.0,
                generated_at=event_time,
                stats=[],
                events=[
                    BacktestSignalEvent(
                        symbol="BTCUSDT",
                        interval="4h",
                        entry_time=event_time,
                        entry_price=100,
                        score=85,
                        grade="A",
                        reasons=["a"],
                        forward_returns_pct={3: 2.0, 6: 4.0},
                        exit_time=event_time + timedelta(hours=8),
                        gross_return_pct=3.8,
                        realized_return_pct=3.5,
                        bars_held=2,
                        max_drawdown_pct=-1.1,
                    ),
                    BacktestSignalEvent(
                        symbol="BTCUSDT",
                        interval="4h",
                        entry_time=event_time + timedelta(hours=12),
                        entry_price=101,
                        score=75,
                        grade="B",
                        reasons=["a"],
                        forward_returns_pct={3: 1.0, 6: 2.0},
                        exit_time=event_time + timedelta(hours=20),
                        gross_return_pct=2.3,
                        realized_return_pct=2.0,
                        bars_held=2,
                        max_drawdown_pct=-0.8,
                    ),
                ],
            ),
            BacktestReport(
                symbol="ETHUSDT",
                interval="4h",
                candle_count=100,
                evaluated_bars=20,
                signal_count=1,
                lookback_bars=80,
                score_threshold=70,
                cooldown_bars=6,
                fee_bps=10.0,
                slippage_bps=5.0,
                capital_fraction_pct=100.0,
                generated_at=event_time,
                stats=[],
                events=[
                    BacktestSignalEvent(
                        symbol="ETHUSDT",
                        interval="4h",
                        entry_time=event_time,
                        entry_price=50,
                        score=90,
                        grade="A+",
                        reasons=["b"],
                        forward_returns_pct={3: 3.0, 6: 6.0},
                        exit_time=event_time + timedelta(hours=8),
                        gross_return_pct=4.4,
                        realized_return_pct=4.0,
                        bars_held=2,
                        max_drawdown_pct=-0.7,
                    )
                ],
            ),
            BacktestReport(
                symbol="SOLUSDT",
                interval="4h",
                candle_count=100,
                evaluated_bars=20,
                signal_count=1,
                lookback_bars=80,
                score_threshold=70,
                cooldown_bars=6,
                fee_bps=10.0,
                slippage_bps=5.0,
                capital_fraction_pct=100.0,
                generated_at=event_time,
                stats=[],
                events=[
                    BacktestSignalEvent(
                        symbol="SOLUSDT",
                        interval="4h",
                        entry_time=event_time,
                        entry_price=30,
                        score=80,
                        grade="A",
                        reasons=["c"],
                        forward_returns_pct={3: -1.0, 6: 1.0},
                        exit_time=event_time + timedelta(hours=8),
                        gross_return_pct=-1.2,
                        realized_return_pct=-1.5,
                        bars_held=2,
                        max_drawdown_pct=-2.5,
                    )
                ],
            ),
        ]

        portfolio = run_portfolio_backtest(reports, top_n=2)
        self.assertIsNotNone(portfolio)
        assert portfolio is not None
        self.assertEqual(portfolio.batch_count, 2)
        self.assertEqual(portfolio.pick_count, 3)
        self.assertEqual([pick.symbol for pick in portfolio.selections[0].picks], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual(portfolio.selections[0].average_forward_returns_pct[3], 2.5)
        self.assertEqual(portfolio.selections[0].realized_return_pct, 3.75)
        self.assertAlmostEqual(portfolio.stats[0].avg_batch_return_pct, 1.75, places=4)
        self.assertAlmostEqual(portfolio.trade_stat.avg_return_pct if portfolio.trade_stat else 0.0, 2.875, places=4)
        self.assertGreater(len(portfolio.equity_curve), 0)

    def test_portfolio_backtest_respects_position_cap(self) -> None:
        event_time = datetime(2025, 1, 10, tzinfo=timezone.utc)
        reports = []
        for idx, symbol in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
            reports.append(
                BacktestReport(
                    symbol=symbol,
                    interval="4h",
                    candle_count=100,
                    evaluated_bars=20,
                    signal_count=1,
                    lookback_bars=80,
                    score_threshold=70,
                    cooldown_bars=6,
                    fee_bps=10.0,
                    slippage_bps=5.0,
                    capital_fraction_pct=40.0,
                    generated_at=event_time,
                    stats=[],
                    events=[
                        BacktestSignalEvent(
                            symbol=symbol,
                            interval="4h",
                            entry_time=event_time,
                            entry_price=100 + idx,
                            score=90 - idx,
                            grade="A",
                            reasons=["x"],
                            forward_returns_pct={3: 2.0},
                            exit_time=event_time + timedelta(hours=8),
                            gross_return_pct=3.0,
                            realized_return_pct=2.5,
                            bars_held=2,
                            max_drawdown_pct=-1.0,
                        )
                    ],
                )
            )
        portfolio = run_portfolio_backtest(
            reports,
            top_n=3,
            max_concurrent_positions=2,
            max_portfolio_exposure_pct=60.0,
        )
        self.assertIsNotNone(portfolio)
        assert portfolio is not None
        self.assertEqual(len(portfolio.selections), 1)
        self.assertEqual(len(portfolio.selections[0].picks), 2)
        self.assertAlmostEqual(portfolio.selections[0].capital_fraction_pct, 60.0, places=4)

    def test_rebalance_premium_compares_equal_weight_and_drift_portfolios(self) -> None:
        base = _make_backtest_candles()[:90]
        alt = []
        for index, candle in enumerate(base):
            multiplier = 1.0 + (0.08 if index % 12 < 6 else -0.04)
            alt.append(
                Candlestick(
                    open_time=candle.open_time,
                    close_time=candle.close_time,
                    open_price=candle.open_price * multiplier,
                    high_price=candle.high_price * multiplier,
                    low_price=candle.low_price * multiplier,
                    close_price=candle.close_price * multiplier,
                    volume=candle.volume,
                    quote_volume=candle.quote_volume * multiplier,
                    trade_count=candle.trade_count,
                    taker_buy_base_volume=candle.taker_buy_base_volume,
                    taker_buy_quote_volume=candle.taker_buy_quote_volume * multiplier,
                )
            )

        report = run_rebalance_premium_backtest(
            {"BTCUSDT": base, "ETHUSDT": alt},
            interval="4h",
            rebalance_interval_bars=6,
            fee_bps=0.0,
            slippage_bps=0.0,
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.symbol_count, 2)
        self.assertEqual(report.rebalance_interval_bars, 6)
        self.assertGreater(report.rebalance_count, 0)
        self.assertGreater(len(report.equity_curve), 0)
        self.assertGreater(len(report.buy_hold_equity_curve), 0)

    def test_overnight_seasonality_enters_utc_22_and_holds_two_hours(self) -> None:
        report = run_overnight_seasonality_backtest(
            symbol="BTCUSDT",
            interval="1h",
            candles=_make_hourly_candles(),
            execution_config=ExecutionConfig(fee_bps=0.0, slippage_bps=0.0),
        )

        self.assertGreater(report.signal_count, 0)
        self.assertTrue(all(event.entry_time.hour == 22 for event in report.events))
        self.assertTrue(all(event.bars_held == 2 for event in report.events))
        self.assertTrue(all(event.exit_reason == "time_window_exit" for event in report.events))

    def test_capital_fraction_scales_equity_curve(self) -> None:
        full = run_backtest_for_series(
            symbol="TESTUSDT",
            interval="4h",
            candles=_make_backtest_candles(),
            lookback_bars=80,
            score_threshold=60.0,
            holding_periods=[3, 6, 12],
            entry_config=EntryRuleConfig(
                min_score=60.0,
                min_volume_ratio=1.0,
                min_buy_pressure_ratio=0.5,
                max_rsi=99.0,
                require_kdj_confirmation=False,
            ),
            execution_config=ExecutionConfig(fee_bps=0.0, slippage_bps=0.0, capital_fraction_pct=100.0),
            cooldown_bars=6,
        )
        partial = run_backtest_for_series(
            symbol="TESTUSDT",
            interval="4h",
            candles=_make_backtest_candles(),
            lookback_bars=80,
            score_threshold=60.0,
            holding_periods=[3, 6, 12],
            entry_config=EntryRuleConfig(
                min_score=60.0,
                min_volume_ratio=1.0,
                min_buy_pressure_ratio=0.5,
                max_rsi=99.0,
                require_kdj_confirmation=False,
            ),
            execution_config=ExecutionConfig(fee_bps=0.0, slippage_bps=0.0, capital_fraction_pct=50.0),
            cooldown_bars=6,
        )
        self.assertGreater(full.equity_curve[-1].equity, partial.equity_curve[-1].equity)

    def test_run_backtest_resolves_maker_taker_fees(self) -> None:
        report = run_backtest_for_series(
            symbol="TESTUSDT",
            interval="4h",
            candles=_make_backtest_candles(),
            lookback_bars=80,
            score_threshold=60.0,
            holding_periods=[3, 6, 12],
            entry_config=EntryRuleConfig(
                min_score=60.0,
                min_volume_ratio=1.0,
                min_buy_pressure_ratio=0.5,
                max_rsi=99.0,
                require_kdj_confirmation=False,
            ),
            execution_config=ExecutionConfig(
                fee_model="maker_taker",
                maker_fee_bps=6.0,
                taker_fee_bps=10.0,
                entry_fee_role="taker",
                exit_fee_role="maker",
                fee_discount_pct=20.0,
                slippage_bps=0.0,
                capital_fraction_pct=100.0,
            ),
            cooldown_bars=6,
        )
        self.assertEqual(report.fee_model, "maker_taker")
        self.assertEqual(report.entry_fee_role, "taker")
        self.assertEqual(report.exit_fee_role, "maker")
        self.assertEqual(report.fee_discount_pct, 20.0)
        self.assertTrue(all(event.entry_fee_bps == 8.0 for event in report.events))
        self.assertTrue(all(event.exit_fee_bps == 4.8 for event in report.events))


if __name__ == "__main__":
    unittest.main()
