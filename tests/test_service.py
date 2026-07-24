from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from trade_signal_app.binance_client import BinancePublicAPIError
from trade_signal_app.config import AppSettings
from trade_signal_app.models import Candlestick, MarketActivityProfile, MarketTicker
from trade_signal_app.service import (
    SignalScanner,
    activity_windows_for_interval,
    analyze_market_activity,
    filter_tickers_by_liquidity_tier,
    select_tickers_for_scan,
)


def _activity_candles(recent_quote_volumes: list[float], recent_trade_counts: list[int]) -> tuple[list[Candlestick], datetime]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quote_volumes = [100.0] * 48 + recent_quote_volumes
    trade_counts = [10] * 48 + recent_trade_counts
    candles = []
    for index, (quote_volume, trade_count) in enumerate(zip(quote_volumes, trade_counts)):
        open_time = start + timedelta(hours=index)
        candles.append(
            Candlestick(
                open_time=open_time,
                close_time=open_time + timedelta(hours=1) - timedelta(milliseconds=1),
                open_price=1.0,
                high_price=1.0,
                low_price=1.0,
                close_price=1.0,
                volume=quote_volume,
                quote_volume=quote_volume,
                trade_count=trade_count,
                taker_buy_base_volume=quote_volume / 2,
                taker_buy_quote_volume=quote_volume / 2,
            )
        )
    return candles, candles[-1].close_time + timedelta(seconds=1)


def _permissive_settings() -> AppSettings:
    return AppSettings(
        btc_min_quote_volume=1,
        btc_min_trade_count=1,
        eth_min_quote_volume=1,
        eth_min_trade_count=1,
        xrp_min_quote_volume=1,
        xrp_min_trade_count=1,
        sol_min_quote_volume=1,
        sol_min_trade_count=1,
        bnb_min_quote_volume=1,
        bnb_min_trade_count=1,
        top30_min_quote_volume=1,
        top30_min_trade_count=1,
    )


class NoopCommunityProvider:
    def prepare(self, symbols: list[str]) -> None:
        self.symbols = symbols

    def get(self, symbol: str) -> None:
        return None


class FallbackTickerGateway:
    def __init__(self, *, exchange_info_fails: bool = False, extra_symbol_count: int = 0) -> None:
        self.fallback_symbols: list[str] = []
        self.ticker24hr_calls = 0
        self.exchange_info_fails = exchange_info_fails
        self.extra_symbol_count = extra_symbol_count

    def exchange_info(self) -> dict:
        if self.exchange_info_fails:
            raise BinancePublicAPIError("exchangeInfo incomplete")
        symbols = [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
        ]
        symbols.extend(
            {
                "symbol": f"ALT{index}USDT",
                "baseAsset": f"ALT{index}",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
            }
            for index in range(self.extra_symbol_count)
        )
        return {"symbols": symbols}

    def ticker24hr(self) -> list[dict]:
        self.ticker24hr_calls += 1
        return []

    def ticker24hr_symbols(self, symbols: list[str]) -> list[dict]:
        self.fallback_symbols = symbols
        rows = [
            {"symbol": "BTCUSDT", "lastPrice": "100", "priceChangePercent": "1", "quoteVolume": "2000000", "volume": "100", "count": 200},
            {"symbol": "ETHUSDT", "lastPrice": "50", "priceChangePercent": "2", "quoteVolume": "1000000", "volume": "100", "count": 200},
        ]
        rows.extend(
            {
                "symbol": f"ALT{index}USDT",
                "lastPrice": "10",
                "priceChangePercent": "1",
                "quoteVolume": str(900000 - index),
                "volume": "100",
                "count": 200,
            }
            for index in range(self.extra_symbol_count)
        )
        wanted = set(symbols)
        return [row for row in rows if row["symbol"] in wanted]

    def map_klines(self, symbols: list[str], *, interval: str, limit: int, max_workers: int) -> dict[str, list]:
        return {}


class SignalScannerTests(unittest.TestCase):
    def test_activity_windows_follow_selected_scan_interval(self) -> None:
        self.assertEqual(activity_windows_for_interval("4h"), (1, 2, 4))
        self.assertEqual(activity_windows_for_interval("8h"), (1, 2, 4, 8))
        self.assertEqual(activity_windows_for_interval("12h"), (1, 2, 4, 8, 12))
        self.assertEqual(activity_windows_for_interval("1d"), (1, 2, 4, 8, 12))

    def test_market_activity_detects_consecutive_4h_volume_surge(self) -> None:
        candles, now = _activity_candles([170, 180, 220, 260], [14, 15, 18, 22])

        profile = analyze_market_activity(
            candles,
            interval="4h",
            baseline_hours=48,
            surge_ratio=1.6,
            trade_surge_ratio=1.25,
            contraction_ratio=0.65,
            trade_contraction_ratio=0.75,
            min_consecutive_windows=2,
            now=now,
        )

        self.assertEqual(profile.regime, "surge")
        self.assertEqual(profile.matched_windows, [1, 2, 4])
        self.assertEqual(profile.consecutive_windows, 3)
        self.assertGreater(profile.normalized_quote_volume_24h, 4_000)

    def test_market_activity_detects_consecutive_contraction_as_observation(self) -> None:
        candles, now = _activity_candles([60, 55, 45, 40], [7, 6, 5, 4])

        profile = analyze_market_activity(
            candles,
            interval="4h",
            baseline_hours=48,
            surge_ratio=1.6,
            trade_surge_ratio=1.25,
            contraction_ratio=0.65,
            trade_contraction_ratio=0.75,
            min_consecutive_windows=2,
            now=now,
        )

        self.assertEqual(profile.regime, "contraction")
        self.assertEqual(profile.matched_windows, [1, 2, 4])

    def test_dynamic_surge_can_replace_fixed_gate_above_both_safety_floors(self) -> None:
        fixed = MarketTicker("FIXEDUSDT", 1.0, 0.0, 1_100.0, 100.0, 110)
        surge = MarketTicker("SURGEUSDT", 1.0, 0.0, 300.0, 100.0, 30)
        activity = MarketActivityProfile(
            regime="surge",
            label="连续放量 1H/2H/4H",
            windows_hours=[1, 2, 4],
            matched_windows=[1, 2, 4],
            consecutive_windows=3,
            max_volume_ratio=2.4,
            max_trade_ratio=2.0,
            normalized_quote_volume_24h=600.0,
            normalized_trade_count_24h=60,
        )
        profiles = {
            "min_quote_volume": 1_000,
            "min_trade_count": 100,
            "top30_min_quote_volume": 1_000,
            "top30_min_trade_count": 100,
        }

        selected, _, _, stats, status = select_tickers_for_scan(
            [fixed, surge],
            eligible_symbols={fixed.symbol, surge.symbol},
            quote_asset="USDT",
            profile_source=profiles,
            candidate_pool=2,
            activity_by_symbol={surge.symbol: activity},
            dynamic_activity_enabled=True,
            activity_liquidity_floor_ratio=0.2,
            activity_normalized_threshold_ratio=0.5,
        )

        self.assertEqual(selected[0].symbol, surge.symbol)
        self.assertTrue(status[surge.symbol]["eligible"])
        self.assertTrue(status[surge.symbol]["dynamic_override"])
        self.assertEqual(stats["top30"]["dynamic_eligible"], 1)

    def test_dynamic_surge_below_absolute_floor_remains_observation_only(self) -> None:
        surge = MarketTicker("THINUSDT", 1.0, 0.0, 100.0, 100.0, 10)
        activity = MarketActivityProfile(
            regime="surge",
            label="连续放量 1H/2H",
            windows_hours=[1, 2, 4],
            matched_windows=[1, 2],
            consecutive_windows=2,
            max_volume_ratio=3.0,
            max_trade_ratio=3.0,
            normalized_quote_volume_24h=800.0,
            normalized_trade_count_24h=80,
        )

        selected, _, _, _, status = select_tickers_for_scan(
            [surge],
            eligible_symbols={surge.symbol},
            quote_asset="USDT",
            profile_source={
                "min_quote_volume": 1_000,
                "min_trade_count": 100,
                "top30_min_quote_volume": 1_000,
                "top30_min_trade_count": 100,
            },
            candidate_pool=1,
            activity_by_symbol={surge.symbol: activity},
            dynamic_activity_enabled=True,
            activity_liquidity_floor_ratio=0.2,
            activity_normalized_threshold_ratio=0.5,
        )

        self.assertFalse(status[selected[0].symbol]["eligible"])
        self.assertIn("动态安全底线", str(status[selected[0].symbol]["message"]))

    def test_scan_uses_chunked_tickers_to_avoid_large_ticker_response(self) -> None:
        gateway = FallbackTickerGateway()
        scanner = SignalScanner(gateway=gateway, community_provider=NoopCommunityProvider(), settings=_permissive_settings())

        summary, signals = scanner.scan(candidate_pool=2, min_quote_volume=1, min_trade_count=1)

        self.assertEqual(gateway.ticker24hr_calls, 0)
        self.assertEqual(gateway.fallback_symbols, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(summary.scanned_symbols, 2)
        self.assertEqual(signals, [])

    def test_scan_summary_distinguishes_candidate_pool_from_eligible_universe(self) -> None:
        gateway = FallbackTickerGateway(extra_symbol_count=4)
        scanner = SignalScanner(gateway=gateway, community_provider=NoopCommunityProvider(), settings=_permissive_settings())

        summary, signals = scanner.scan(candidate_pool=2, min_quote_volume=1, min_trade_count=1)

        self.assertEqual(summary.eligible_symbols, 6)
        self.assertEqual(summary.candidate_pool, 2)
        self.assertEqual(summary.candidate_symbols, 2)
        self.assertEqual(summary.scanned_symbols, 2)
        self.assertEqual(signals, [])

    def test_scan_uses_real_symbol_universe_when_exchange_info_fails(self) -> None:
        gateway = FallbackTickerGateway(exchange_info_fails=True)
        scanner = SignalScanner(gateway=gateway, community_provider=NoopCommunityProvider(), settings=_permissive_settings())

        summary, signals = scanner.scan(candidate_pool=2, min_quote_volume=1, min_trade_count=1)

        self.assertIn("BTCUSDT", gateway.fallback_symbols)
        self.assertIn("ETHUSDT", gateway.fallback_symbols)
        self.assertEqual(summary.scanned_symbols, 2)
        self.assertEqual(signals, [])

    def test_eligible_symbols_excludes_current_stablecoin_bases(self) -> None:
        exchange_info = {
            "symbols": [
                {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "USDEUSDT", "baseAsset": "USDE", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "USD1USDT", "baseAsset": "USD1", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "RLUSDUSDT", "baseAsset": "RLUSD", "quoteAsset": "USDT", "status": "TRADING"},
            ]
        }

        eligible = SignalScanner._eligible_symbols(exchange_info, "USDT")

        self.assertEqual(eligible, {"BTCUSDT"})

    def test_liquidity_filter_applies_symbol_top30_and_alt_profiles(self) -> None:
        symbols = ["BTC", "ETH", "XRP", "SOL", "BNB", *[f"ALT{index}" for index in range(35)]]
        tickers = [
            MarketTicker(
                symbol=f"{symbol}USDT",
                last_price=1.0,
                price_change_percent=0.0,
                quote_volume=1000.0 - index,
                volume=100.0,
                trade_count=100,
            )
            for index, symbol in enumerate(symbols)
        ]
        profiles = {
            "min_quote_volume": 2000,
            "min_trade_count": 1,
            "btc_min_quote_volume": 2000,
            "btc_min_trade_count": 1,
            "eth_min_quote_volume": 0,
            "eth_min_trade_count": 1,
            "xrp_min_quote_volume": 0,
            "xrp_min_trade_count": 1,
            "sol_min_quote_volume": 0,
            "sol_min_trade_count": 1,
            "bnb_min_quote_volume": 0,
            "bnb_min_trade_count": 1,
            "top30_min_quote_volume": 800,
            "top30_min_trade_count": 1,
        }

        filtered, applied_profiles, stats = filter_tickers_by_liquidity_tier(
            tickers,
            eligible_symbols={ticker.symbol for ticker in tickers},
            quote_asset="USDT",
            profile_source=profiles,
        )

        self.assertNotIn("BTCUSDT", {ticker.symbol for ticker in filtered})
        self.assertTrue({"ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"}.issubset({ticker.symbol for ticker in filtered}))
        self.assertEqual(stats["BTC"], {"universe": 1, "eligible": 0})
        self.assertEqual(stats["top30"], {"universe": 25, "eligible": 25})
        self.assertEqual(stats["alt"], {"universe": 10, "eligible": 0})
        self.assertEqual(applied_profiles["top30"]["min_quote_volume"], 800.0)

    def test_scan_selection_backfills_observation_candidates_to_target_size(self) -> None:
        tickers = [
            MarketTicker(
                symbol=f"ALT{index}USDT",
                last_price=1.0,
                price_change_percent=0.0,
                quote_volume=1_000.0 - index * 100,
                volume=100.0,
                trade_count=100,
            )
            for index in range(5)
        ]
        profiles = {
            "min_quote_volume": 900,
            "min_trade_count": 1,
            "top30_min_quote_volume": 900,
            "top30_min_trade_count": 1,
        }

        selected, qualified, _, _, status = select_tickers_for_scan(
            tickers,
            eligible_symbols={ticker.symbol for ticker in tickers},
            quote_asset="USDT",
            profile_source=profiles,
            candidate_pool=4,
        )

        self.assertEqual(len(selected), 4)
        self.assertEqual([ticker.symbol for ticker in qualified], ["ALT0USDT", "ALT1USDT"])
        self.assertEqual(sum(bool(status[ticker.symbol]["eligible"]) for ticker in selected), 2)
        self.assertIn("仅扫描观察", str(status["ALT2USDT"]["message"]))


if __name__ == "__main__":
    unittest.main()
