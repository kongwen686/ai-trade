from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import unittest
from unittest.mock import patch

from trade_signal_app.feishu import FeishuTradeNotifier, build_feishu_trade_payload
from trade_signal_app.trading import TradingEvent, TradingPosition


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class FeishuTests(unittest.TestCase):
    def test_build_trade_payload_contains_buy_structure(self) -> None:
        event = TradingEvent(
            action="BUY",
            symbol="BTCUSDT",
            mode="paper",
            status="paper_filled",
            message="模拟买入已记录。",
            score=82.5,
            price=100.0,
            quantity=1.25,
            quote_notional=125.0,
            created_at=datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc),
            exchange="BINANCE",
        )
        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=1.25,
            entry_price=100.0,
            quote_notional=125.0,
            score=82.5,
            grade="A",
            opened_at=datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc),
            stop_price=96.0,
            take_profit_price=109.0,
            leverage=5.0,
            margin_notional=25.0,
        )

        payload = build_feishu_trade_payload(event=event, position=position)

        self.assertEqual(payload["msg_type"], "interactive")
        card = payload["card"]
        self.assertIn("AI Trade 模拟买入通知", card["header"]["title"]["content"])
        fields = card["elements"][0]["fields"]
        rendered = "\n".join(str(item["text"]["content"]) for item in fields)
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("**标的**\nBTCUSDT", rendered)
        self.assertIn("**成交时间**\n2026-07-06 14:00:00 UTC+8", rendered)
        self.assertIn("**保证金/杠杆**\n25.00 / 5.0x", rendered)
        self.assertIn("**杠杆止损价**\n96.00000000 (5.0x ≈ -20.00% ROI)", rendered)
        self.assertIn("**杠杆止盈价**\n109.00000000 (5.0x ≈ +45.00% ROI)", rendered)
        self.assertNotIn("**摘要**", payload_text)
        self.assertNotIn("**交易所**", payload_text)
        self.assertNotIn("**模式**", payload_text)
        self.assertNotIn("**状态**", payload_text)

    def test_notifier_posts_trade_card(self) -> None:
        notifier = FeishuTradeNotifier("https://open.feishu.cn/test-webhook")
        event = TradingEvent(
            action="SELL",
            symbol="ETHUSDT",
            mode="paper",
            status="paper_filled",
            message="模拟卖出已记录：take_profit。",
            price=120.0,
            quantity=0.25,
            quote_notional=30.0,
            realized_pnl=5.0,
            realized_pnl_pct=20.0,
            exit_reason="take_profit",
            created_at=datetime(2026, 7, 6, 6, 5, tzinfo=timezone.utc),
            exchange="BINANCE",
        )
        position = TradingPosition(
            symbol="ETHUSDT",
            quantity=0.25,
            entry_price=100.0,
            quote_notional=25.0,
            score=80.0,
            grade="A",
            opened_at=datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc),
            stop_price=96.0,
            take_profit_price=109.0,
            leverage=5.0,
            margin_notional=25.0,
        )
        with patch(
            "trade_signal_app.feishu.urlopen",
            return_value=FakeResponse(json.dumps({"StatusCode": 0, "StatusMessage": "success"}).encode("utf-8")),
        ) as mock_urlopen:
            sent = notifier.notify_trade(event=event, position=position)

        self.assertTrue(sent)
        request = mock_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["msg_type"], "interactive")
        self.assertIn("AI Trade 模拟卖出通知", body["card"]["header"]["title"]["content"])
        rendered = json.dumps(body, ensure_ascii=False)
        self.assertIn("杠杆止损价", rendered)
        self.assertIn("杠杆止盈价", rendered)
        self.assertNotIn("**摘要**", rendered)
        self.assertNotIn("**交易所**", rendered)
        self.assertNotIn("**模式**", rendered)
        self.assertNotIn("**状态**", rendered)


if __name__ == "__main__":
    unittest.main()
