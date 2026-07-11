from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import unittest
from unittest.mock import patch

from trade_signal_app.feishu import (
    FeishuTradeNotifier,
    build_feishu_btc_signal_payload,
    build_feishu_daily_summary_payload,
    build_feishu_trade_payload,
)
from trade_signal_app.trading import TradingEvent, TradingPosition


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class FeishuTests(unittest.TestCase):
    def test_build_btc_signal_payload_contains_structured_btc_metrics(self) -> None:
        payload = build_feishu_btc_signal_payload(
            summary={
                "symbol": "BTCUSDT",
                "action": "BUY",
                "action_label": "买入",
                "signal": "btc_regime_trend_pullback_buy",
                "generated_at": "2026-07-10T22:00:00+08:00",
                "price": 118000.0,
                "score": 82.35,
                "grade": "A",
                "confidence": "高",
                "regime": {"label": "多头趋势", "entry_rsi_14": 58.2},
                "trade_levels": {
                    "support_level": 115500.0,
                    "resistance_level": 126000.0,
                    "stop_price": 114900.0,
                    "take_profit_price": 125496.0,
                    "stop_pct": 2.6271,
                    "take_profit_pct": 6.3525,
                    "risk_reward_ratio": 2.42,
                    "leverage_reference": 5.0,
                    "leveraged_stop_roi_pct": -13.1355,
                    "leveraged_take_profit_roi_pct": 31.7625,
                },
                "selected_preset": {"label": "BTC Core Trading", "win_rate_pct": 62.5, "profit_factor": 1.8},
                "preset_backtests": [
                    {"status": "ok", "label": "BTC Core Trading", "signal_count": 31, "win_rate_pct": 62.5, "profit_factor": 1.8}
                ],
                "statistics": {
                    "sample": {"primary_bars": 19476},
                    "buy_hold_return_pct": 2600.0,
                    "max_drawdown_pct": -76.2,
                    "return_90d_pct": 18.5,
                },
                "reasons": ["1d 收盘价位于 EMA200 上方"],
                "warnings": ["1h RSI 偏热时不追价"],
                "advice": "分批试多。",
            }
        )

        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["msg_type"], "interactive")
        self.assertIn("AI Trade BTC 专属买入信号", rendered)
        self.assertIn("btc_regime_trend_pullback_buy", rendered)
        self.assertIn("**5x 止损参考**", rendered)
        self.assertIn("5.0x ≈ -13.14% ROI", rendered)
        self.assertIn("**10年持有收益**", rendered)
        self.assertIn("+2600.00%", rendered)
        self.assertIn("BTC Core Trading", rendered)

    def test_build_daily_summary_payload_contains_structured_metrics(self) -> None:
        payload = build_feishu_daily_summary_payload(
            summary={
                "date": "2026-07-10",
                "generated_at": "2026-07-10T22:00:00+08:00",
                "scan": {"returned_signals": 6, "scanned_symbols": 30, "top_symbols": ["BTCUSDT", "ETHUSDT"]},
                "trading": {
                    "today_trades": 3,
                    "today_realized_pnl": 2.75,
                    "total_trades": 42,
                    "win_rate_pct": 61.9,
                    "total_pnl": 18.5,
                    "realized_pnl": 12.0,
                    "unrealized_pnl": 6.5,
                    "open_positions": 4,
                },
                "intelligence": {"intel_items": 5, "onchain_events": 2, "strategy_hits": 7},
                "risk": {"risk_score": 32.5, "status": "clear", "blocked": 0},
                "warnings": ["本地缓存数据参与统计"],
            }
        )

        self.assertEqual(payload["msg_type"], "interactive")
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertIn("AI Trade 每日数据统计 2026-07-10", rendered)
        self.assertIn("**信号**", rendered)
        self.assertIn("6 / 30", rendered)
        self.assertIn("**累计成交**", rendered)
        self.assertIn("42", rendered)
        self.assertIn("**当日已实现盈亏**", rendered)
        self.assertIn("+2.75", rendered)
        self.assertIn("**胜率**", rendered)
        self.assertIn("61.90%", rendered)
        self.assertIn("**账户盈亏**", rendered)
        self.assertIn("+18.50", rendered)
        self.assertIn("市场 5 / 链上 2 / 策略 7", rendered)
        self.assertIn("**风险评分**", rendered)
        self.assertIn("32.5", rendered)
        self.assertIn("正常", rendered)
        self.assertIn("BTCUSDT、ETHUSDT", rendered)

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
        self.assertIn("**消息**\n模拟买入已记录。", rendered)
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
        self.assertIn("**消息**", rendered)
        self.assertIn("模拟卖出已记录：take_profit。", rendered)
        self.assertNotIn("**摘要**", rendered)
        self.assertNotIn("**交易所**", rendered)
        self.assertNotIn("**模式**", rendered)
        self.assertNotIn("**状态**", rendered)

    def test_notifier_posts_emergency_drawdown_alert_with_chinese_status(self) -> None:
        notifier = FeishuTradeNotifier("https://open.feishu.cn/test-webhook")
        event = TradingEvent(
            action="ALERT",
            symbol="BTCUSDT",
            mode="paper",
            status="emergency_drawdown",
            message="价格较持仓最高价快速回撤 3.64%，请检查突发风险和盘口流动性。",
            price=106.0,
            quantity=1.0,
            quote_notional=100.0,
            created_at=datetime(2026, 7, 6, 6, 10, tzinfo=timezone.utc),
            exchange="BINANCE",
        )
        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=1.0,
            entry_price=100.0,
            quote_notional=100.0,
            score=82.0,
            grade="A",
            opened_at=datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc),
            stop_price=96.0,
            take_profit_price=109.0,
            leverage=5.0,
            margin_notional=20.0,
            highest_price=110.0,
        )
        with patch(
            "trade_signal_app.feishu.urlopen",
            return_value=FakeResponse(json.dumps({"code": 0, "msg": "success"}).encode("utf-8")),
        ) as mock_urlopen:
            sent = notifier.notify_trade(event=event, position=position)

        self.assertTrue(sent)
        request = mock_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        rendered = json.dumps(body, ensure_ascii=False)
        self.assertIn("AI Trade 紧急回撤预警", body["card"]["header"]["title"]["content"])
        self.assertIn("**消息**", rendered)
        self.assertIn("紧急回撤预警：价格较持仓最高价快速回撤 3.64%", rendered)
        self.assertIn("**当前价格**", rendered)
        self.assertIn("**持仓数量**", rendered)
        self.assertIn("**杠杆止损价**", rendered)
        self.assertNotIn("emergency_drawdown", rendered)
        self.assertNotIn("**状态**", rendered)

    def test_notifier_skips_emergency_drawdown_without_position(self) -> None:
        notifier = FeishuTradeNotifier("https://open.feishu.cn/test-webhook")
        event = TradingEvent(
            action="ALERT",
            symbol="BTCUSDT",
            mode="paper",
            status="emergency_drawdown",
            message="价格快速回撤，请检查风险。",
            price=106.0,
            quantity=1.0,
            quote_notional=100.0,
            created_at=datetime(2026, 7, 6, 6, 10, tzinfo=timezone.utc),
            exchange="BINANCE",
        )

        with patch("trade_signal_app.feishu.urlopen") as mock_urlopen:
            sent = notifier.notify_trade(event=event, position=None)

        self.assertFalse(sent)
        mock_urlopen.assert_not_called()

    def test_notifier_skips_emergency_drawdown_with_empty_position(self) -> None:
        notifier = FeishuTradeNotifier("https://open.feishu.cn/test-webhook")
        event = TradingEvent(
            action="ALERT",
            symbol="BTCUSDT",
            mode="paper",
            status="emergency_drawdown",
            message="价格快速回撤，请检查风险。",
            price=106.0,
            quantity=0.0,
            quote_notional=0.0,
            created_at=datetime(2026, 7, 6, 6, 10, tzinfo=timezone.utc),
            exchange="BINANCE",
        )
        position = TradingPosition(
            symbol="BTCUSDT",
            quantity=0.0,
            entry_price=100.0,
            quote_notional=0.0,
            score=82.0,
            grade="A",
            opened_at=datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc),
            stop_price=96.0,
            take_profit_price=109.0,
            leverage=5.0,
            margin_notional=0.0,
        )

        with patch("trade_signal_app.feishu.urlopen") as mock_urlopen:
            sent = notifier.notify_trade(event=event, position=position)

        self.assertFalse(sent)
        mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
