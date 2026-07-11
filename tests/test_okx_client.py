from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import unittest
from unittest.mock import patch

from trade_signal_app.okx_client import OKXAPIError, OKXSpotGateway


class FakeResponse(io.StringIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class OKXClientTests(unittest.TestCase):
    def test_signed_balance_request_includes_okx_signature_headers(self) -> None:
        payload = {"code": "0", "data": [{"details": []}]}
        with patch.object(OKXSpotGateway, "_timestamp", return_value="2026-07-04T01:02:03.456Z"):
            with patch("trade_signal_app.okx_client.urlopen", return_value=FakeResponse(json.dumps(payload))) as mock_urlopen:
                gateway = OKXSpotGateway(api_key="okx-key", api_secret="okx-secret", passphrase="okx-pass")
                gateway.balance({"USDT"})

        request = mock_urlopen.call_args.args[0]
        expected_path = "/api/v5/account/balance?ccy=USDT"
        expected_signature = base64.b64encode(
            hmac.new(
                b"okx-secret",
                f"2026-07-04T01:02:03.456ZGET{expected_path}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        headers = dict(request.header_items())
        self.assertEqual(request.full_url, f"https://www.okx.com{expected_path}")
        self.assertEqual(headers["Ok-access-key"], "okx-key")
        self.assertEqual(headers["Ok-access-passphrase"], "okx-pass")
        self.assertEqual(headers["Ok-access-sign"], expected_signature)

    def test_account_status_summarizes_quote_balance(self) -> None:
        with patch.object(
            OKXSpotGateway,
            "balance",
            return_value={
                "code": "0",
                "data": [
                    {
                        "details": [
                            {"ccy": "USDT", "availBal": "45.5", "frozenBal": "1.2"},
                            {"ccy": "BTC", "availBal": "0.01", "frozenBal": "0"},
                        ]
                    }
                ],
            },
        ):
            gateway = OKXSpotGateway(api_key="okx-key", api_secret="okx-secret", passphrase="okx-pass")
            status = gateway.account_status({"USDT"})

        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["authenticated"])
        self.assertTrue(status["can_trade"])
        self.assertEqual(status["quote_available"], 45.5)
        self.assertEqual(len(status["balances"]), 2)

    def test_market_buy_uses_order_precheck_when_test_enabled(self) -> None:
        response = {"code": "0", "data": [{"sCode": "0", "ordId": "123"}]}
        with patch("trade_signal_app.okx_client.urlopen", return_value=FakeResponse(json.dumps(response))) as mock_urlopen:
            gateway = OKXSpotGateway(api_key="okx-key", api_secret="okx-secret", passphrase="okx-pass")
            payload = gateway.order_market_buy(symbol="BTCUSDT", quote_order_qty=25.5, test=True, client_order_id="cid")

        request = mock_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://www.okx.com/api/v5/trade/order-precheck")
        self.assertEqual(body["instId"], "BTC-USDT")
        self.assertEqual(body["side"], "buy")
        self.assertEqual(body["tgtCcy"], "quote_ccy")
        self.assertEqual(body["sz"], "25.5")
        self.assertEqual(payload["ordId"], "123")

    def test_order_rejects_nonzero_row_status_code(self) -> None:
        response = {"code": "0", "data": [{"sCode": "51008", "sMsg": "Insufficient balance"}]}
        with patch("trade_signal_app.okx_client.urlopen", return_value=FakeResponse(json.dumps(response))):
            gateway = OKXSpotGateway(api_key="okx-key", api_secret="okx-secret", passphrase="okx-pass")
            with self.assertRaisesRegex(OKXAPIError, "Insufficient balance"):
                gateway.order_market_buy(symbol="BTCUSDT", quote_order_qty=25.5, test=False)

    def test_ticker_shape_computes_24h_change_from_okx_payload(self) -> None:
        payload = OKXSpotGateway._ticker_to_binance_shape(
            {
                "instId": "BTC-USDT",
                "last": "105",
                "open24h": "100",
                "volCcy24h": "25000000",
                "vol24h": "240",
            }
        )

        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["lastPrice"], "105.0")
        self.assertAlmostEqual(float(payload["priceChangePercent"]), 5.0)
        self.assertEqual(payload["quoteVolume"], "25000000")


if __name__ == "__main__":
    unittest.main()
