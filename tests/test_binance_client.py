from __future__ import annotations

import hashlib
import hmac
import io
import json
import unittest
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError

from trade_signal_app.binance_client import BinancePublicAPIError, BinanceSpotGateway


class FakeResponse(io.StringIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class BinanceClientTests(unittest.TestCase):
    def test_signed_account_request_includes_signature_and_api_key(self) -> None:
        with patch("trade_signal_app.binance_client.time.time", return_value=1_700_000_000.0):
            with patch(
                "trade_signal_app.binance_client.urlopen",
                return_value=FakeResponse(json.dumps({"commissionRates": {"maker": "0.00060000", "taker": "0.00100000"}})),
            ) as mock_urlopen:
                gateway = BinanceSpotGateway(
                    api_key="test-key",
                    api_secret="test-secret",
                    recv_window_ms=5000,
                )
                gateway.account()

        request = mock_urlopen.call_args.args[0]
        expected_query = "omitZeroBalances=true&recvWindow=5000&timestamp=1700000000000"
        expected_signature = hmac.new(
            b"test-secret",
            expected_query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertIn(expected_query, request.full_url)
        self.assertIn(f"signature={expected_signature}", request.full_url)
        self.assertEqual(dict(request.header_items())["X-mbx-apikey"], "test-key")

    def test_signed_endpoints_require_credentials(self) -> None:
        gateway = BinanceSpotGateway()
        with self.assertRaisesRegex(ValueError, "BINANCE_API_KEY / BINANCE_API_SECRET"):
            gateway.account_commission("BTCUSDT")

    def test_account_status_reports_not_configured_without_credentials(self) -> None:
        gateway = BinanceSpotGateway()

        status = gateway.account_status({"USDT"})

        self.assertEqual(status["status"], "not_configured")
        self.assertFalse(status["authenticated"])
        self.assertFalse(status["can_trade"])

    def test_account_status_summarizes_authenticated_balances(self) -> None:
        with patch.object(
            BinanceSpotGateway,
            "account",
            return_value={
                "canTrade": True,
                "balances": [
                    {"asset": "USDT", "free": "120.5", "locked": "0"},
                    {"asset": "BTC", "free": "0.01", "locked": "0.02"},
                    {"asset": "ETH", "free": "0", "locked": "0"},
                ],
            },
        ):
            gateway = BinanceSpotGateway(api_key="test-key", api_secret="test-secret")
            status = gateway.account_status({"USDT"})

        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["authenticated"])
        self.assertTrue(status["can_trade"])
        self.assertEqual(status["quote_available"], 120.5)
        self.assertEqual(len(status["balances"]), 2)

    def test_public_get_retries_incomplete_read(self) -> None:
        with patch(
            "trade_signal_app.binance_client.urlopen",
            side_effect=[
                IncompleteRead(b'{"symbol"', 10),
                FakeResponse(json.dumps([{"symbol": "BTCUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "1", "volume": "1", "count": 1}])),
            ],
        ) as mock_urlopen:
            gateway = BinanceSpotGateway()
            payload = gateway.ticker24hr()

        self.assertEqual(payload[0]["symbol"], "BTCUSDT")
        self.assertEqual(mock_urlopen.call_count, 2)

    def test_ticker24hr_symbols_fetches_chunked_tickers(self) -> None:
        with patch(
            "trade_signal_app.binance_client.urlopen",
            side_effect=[
                FakeResponse(json.dumps([{"symbol": "BTCUSDT"}])),
                FakeResponse(json.dumps([{"symbol": "ETHUSDT"}])),
            ],
        ) as mock_urlopen:
            gateway = BinanceSpotGateway()
            payload = gateway.ticker24hr_symbols(["BTCUSDT", "ETHUSDT"], chunk_size=1)

        self.assertEqual([row["symbol"] for row in payload], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertIn("symbols=", mock_urlopen.call_args.args[0].full_url)

    def test_ticker24hr_symbols_splits_failed_large_chunk(self) -> None:
        gateway = BinanceSpotGateway()
        with patch.object(
            gateway,
            "_get_json",
            side_effect=[
                BinancePublicAPIError("HTTP 400"),
                [{"symbol": "BTCUSDT"}],
                [{"symbol": "ETHUSDT"}],
            ],
        ) as mock_get_json:
            payload = gateway.ticker24hr_symbols(["BTCUSDT", "ETHUSDT"], chunk_size=2)

        self.assertEqual([row["symbol"] for row in payload], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(mock_get_json.call_count, 3)

    def test_signed_endpoint_surfaces_http_error_details(self) -> None:
        response = io.BytesIO(b'{"msg":"Invalid API-key, IP, or permissions for action."}')
        error = HTTPError(
            url="https://api.binance.com/api/v3/account",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=response,
        )
        with patch("trade_signal_app.binance_client.urlopen", side_effect=error):
            gateway = BinanceSpotGateway(api_key="test-key", api_secret="test-secret")
            with self.assertRaisesRegex(ValueError, "HTTP 401"):
                gateway.account()

    def test_market_buy_uses_signed_post_body(self) -> None:
        with patch("trade_signal_app.binance_client.time.time", return_value=1_700_000_000.0):
            with patch(
                "trade_signal_app.binance_client.urlopen",
                return_value=FakeResponse(json.dumps({"orderId": 123})),
            ) as mock_urlopen:
                gateway = BinanceSpotGateway(
                    api_key="test-key",
                    api_secret="test-secret",
                    recv_window_ms=5000,
                )
                payload = gateway.order_market_buy(symbol="BTCUSDT", quote_order_qty=25.5, test=False)

        request = mock_urlopen.call_args.args[0]
        body = request.data.decode("utf-8")
        self.assertEqual(payload["orderId"], 123)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://api.binance.com/api/v3/order")
        self.assertIn("symbol=BTCUSDT", body)
        self.assertIn("side=BUY", body)
        self.assertIn("type=MARKET", body)
        self.assertIn("quoteOrderQty=25.5", body)
        self.assertIn("signature=", body)


if __name__ == "__main__":
    unittest.main()
