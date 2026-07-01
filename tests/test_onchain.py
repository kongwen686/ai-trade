from __future__ import annotations

import unittest

from trade_signal_app.onchain import OpenMultiChainOnchainProvider


class OnchainProviderTests(unittest.TestCase):
    def test_fetches_blockstream_large_transfer(self) -> None:
        def fetcher(method, url, payload, headers, timeout):
            if url.endswith("/blocks/tip/hash"):
                return "block-hash"
            if url.endswith("/block/block-hash/txs/0"):
                return [
                    {"txid": "small", "vout": [{"value": 100_000_000}]},
                    {"txid": "large", "vout": [{"value": 900_000_000_000}]},
                ]
            return {}

        provider = OpenMultiChainOnchainProvider(
            whale_threshold_usd=5_000_000,
            fetcher=fetcher,
        )
        events = provider.fetch_events(["BTCUSDT"], {"BTCUSDT": 60_000.0})
        large_events = [event for event in events if event.event_type == "large_native_transfer"]

        self.assertEqual(large_events[0].symbol, "BTCUSDT")
        self.assertEqual(large_events[0].tx_hash, "large")
        self.assertGreater(large_events[0].amount_usd, 5_000_000)

    def test_fetches_evm_large_transfer(self) -> None:
        def fetcher(method, url, payload, headers, timeout):
            if isinstance(payload, dict) and payload.get("method") == "eth_getBlockByNumber":
                return {
                    "result": {
                        "transactions": [
                            {"hash": "0xsmall", "value": hex(10**18)},
                            {"hash": "0xlarge", "value": hex(3_000 * 10**18)},
                        ]
                    }
                }
            return {}

        provider = OpenMultiChainOnchainProvider(
            whale_threshold_usd=5_000_000,
            fetcher=fetcher,
        )
        events = provider.fetch_events(["ETHUSDT"], {"ETHUSDT": 2_000.0})

        self.assertTrue(any(event.symbol == "ETHUSDT" and event.tx_hash == "0xlarge" for event in events))

    def test_fetches_blockchair_network_snapshot(self) -> None:
        def fetcher(method, url, payload, headers, timeout):
            if url.endswith("/dogecoin/stats"):
                return {"data": {"transactions_24h": 180_000, "mempool_transactions": 4_000}}
            if url.endswith("/zcash/stats"):
                return {"data": {"transactions_24h": 8_000, "mempool_transactions": 20}}
            return {}

        provider = OpenMultiChainOnchainProvider(
            whale_threshold_usd=5_000_000,
            fetcher=fetcher,
        )
        events = provider.fetch_events(["DOGEUSDT", "ZECUSDT"], {})
        symbols = {event.symbol for event in events if event.event_type == "network_snapshot"}

        self.assertIn("DOGEUSDT", symbols)
        self.assertIn("ZECUSDT", symbols)


if __name__ == "__main__":
    unittest.main()
