from __future__ import annotations

import unittest
from trade_signal_app.binance_client import BinancePublicAPIError
from trade_signal_app.config import AppSettings
from trade_signal_app.service import SignalScanner


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
        scanner = SignalScanner(gateway=gateway, community_provider=NoopCommunityProvider(), settings=AppSettings())

        summary, signals = scanner.scan(candidate_pool=2, min_quote_volume=1, min_trade_count=1)

        self.assertEqual(gateway.ticker24hr_calls, 0)
        self.assertEqual(gateway.fallback_symbols, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(summary.scanned_symbols, 2)
        self.assertEqual(signals, [])

    def test_scan_summary_distinguishes_candidate_pool_from_eligible_universe(self) -> None:
        gateway = FallbackTickerGateway(extra_symbol_count=4)
        scanner = SignalScanner(gateway=gateway, community_provider=NoopCommunityProvider(), settings=AppSettings())

        summary, signals = scanner.scan(candidate_pool=2, min_quote_volume=1, min_trade_count=1)

        self.assertEqual(summary.eligible_symbols, 6)
        self.assertEqual(summary.candidate_pool, 2)
        self.assertEqual(summary.candidate_symbols, 2)
        self.assertEqual(summary.scanned_symbols, 2)
        self.assertEqual(signals, [])

    def test_scan_uses_real_symbol_universe_when_exchange_info_fails(self) -> None:
        gateway = FallbackTickerGateway(exchange_info_fails=True)
        scanner = SignalScanner(gateway=gateway, community_provider=NoopCommunityProvider(), settings=AppSettings())

        summary, signals = scanner.scan(candidate_pool=2, min_quote_volume=1, min_trade_count=1)

        self.assertIn("BTCUSDT", gateway.fallback_symbols)
        self.assertIn("ETHUSDT", gateway.fallback_symbols)
        self.assertEqual(summary.scanned_symbols, 2)
        self.assertEqual(signals, [])


if __name__ == "__main__":
    unittest.main()
