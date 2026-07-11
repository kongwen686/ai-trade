from __future__ import annotations

import unittest
from trade_signal_app.binance_client import BinancePublicAPIError
from trade_signal_app.config import AppSettings
from trade_signal_app.models import MarketTicker
from trade_signal_app.service import SignalScanner, filter_tickers_by_liquidity_tier


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


if __name__ == "__main__":
    unittest.main()
