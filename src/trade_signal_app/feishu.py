from __future__ import annotations

from datetime import datetime
import json
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ssl_compat import create_default_ssl_context

if TYPE_CHECKING:
    from .trading import TradingEvent, TradingPosition


class FeishuNotificationError(RuntimeError):
    pass


class FeishuTradeNotifier:
    def __init__(self, webhook_url: str, timeout: int = 10) -> None:
        self.webhook_url = webhook_url.strip()
        self.timeout = timeout
        self._ssl_context = create_default_ssl_context()

    def configured(self) -> bool:
        return bool(self.webhook_url)

    def notify_trade(self, *, event: TradingEvent, position: TradingPosition | None = None) -> bool:
        if not self.configured():
            return False
        if event.action not in {"BUY", "SELL"}:
            return False
        if event.status not in {"paper_filled", "filled"}:
            return False

        payload = build_feishu_trade_payload(event=event, position=position)
        request = Request(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "trade-signal-app/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:
                raw = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise FeishuNotificationError(f"HTTP {exc.code}") from exc
        except URLError as exc:
            raise FeishuNotificationError(str(exc.reason)) from exc

        if not raw.strip():
            return True
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return True
        code = data.get("code", data.get("StatusCode", 0))
        if str(code) not in {"0", ""}:
            message = str(data.get("msg") or data.get("StatusMessage") or code)
            raise FeishuNotificationError(message)
        return True


def build_feishu_trade_payload(*, event: TradingEvent, position: TradingPosition | None = None) -> dict[str, object]:
    action_label = _action_label(event)
    header_template = "green" if event.action == "BUY" else "red"
    fields = [
        _card_field("标的", event.symbol),
        _card_field("交易所", event.exchange.upper()),
        _card_field("模式", _mode_label(event.mode)),
        _card_field("状态", event.status),
        _card_field("成交时间", _format_time(event.created_at)),
        _card_field("成交价格", _format_decimal(event.price, 8)),
        _card_field("成交数量", _format_decimal(event.quantity, 8)),
        _card_field("名义金额", _format_decimal(event.quote_notional, 2)),
    ]
    if event.action == "BUY":
        fields.extend(
            [
                _card_field("信号评分", _format_decimal(event.score, 1)),
                _card_field("信号等级", position.grade if position is not None else "-"),
                _card_field("止损价格", _format_decimal(position.stop_price if position is not None else None, 8)),
                _card_field("止盈价格", _format_decimal(position.take_profit_price if position is not None else None, 8)),
            ]
        )
    else:
        fields.extend(
            [
                _card_field("退出原因", event.exit_reason or "-"),
                _card_field("已实现盈亏", _format_signed_decimal(event.realized_pnl, 2)),
                _card_field("收益率", _format_signed_decimal(event.realized_pnl_pct, 2, suffix="%")),
                _card_field("开仓价格", _format_decimal(position.entry_price if position is not None else None, 8)),
            ]
        )

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": header_template,
                "title": {"tag": "plain_text", "content": f"AI Trade {action_label}"},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**摘要**\n{event.message}"}},
                {"tag": "div", "fields": fields},
            ],
        },
    }


def _action_label(event: TradingEvent) -> str:
    if event.action == "BUY":
        return "模拟买入通知" if event.mode == "paper" else "买入通知"
    return "模拟卖出通知" if event.mode == "paper" else "卖出通知"


def _mode_label(value: str) -> str:
    return "模拟" if value == "paper" else "实盘" if value == "live" else value


def _format_time(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _card_field(label: str, value: str, *, short: bool = True) -> dict[str, object]:
    return {
        "is_short": short,
        "text": {"tag": "lark_md", "content": f"**{label}**\n{value or '-'}"},
    }


def _format_decimal(value: float | None, precision: int, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{float(value):.{precision}f}{suffix}"


def _format_signed_decimal(value: float | None, precision: int, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{float(value):+.{precision}f}{suffix}"
