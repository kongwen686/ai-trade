from __future__ import annotations

from datetime import datetime
import json
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ssl_compat import create_default_ssl_context
from .time_utils import format_app_datetime

if TYPE_CHECKING:
    from .trading import TradingEvent, TradingPosition


NOTIFIABLE_TRADE_STATUSES = {"paper_filled", "filled", "emergency_drawdown"}


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
        if event.status not in NOTIFIABLE_TRADE_STATUSES:
            return False
        if event.status != "emergency_drawdown" and event.action not in {"BUY", "SELL"}:
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
    header_template = _header_template(event)
    fields = [
        _card_field("标的", event.symbol),
        _card_field("触发时间" if event.status == "emergency_drawdown" else "成交时间", _format_time(event.created_at)),
        _card_field("当前价格" if event.status == "emergency_drawdown" else "成交价格", _format_decimal(event.price, 8)),
        _card_field("持仓数量" if event.status == "emergency_drawdown" else "成交数量", _format_decimal(event.quantity, 8)),
        _card_field("名义金额", _format_decimal(event.quote_notional, 2)),
        _card_field("消息", _message_label(event), short=False),
    ]
    if event.action == "BUY":
        fields.extend(
            [
                _card_field("信号评分", _format_decimal(event.score, 1)),
                _card_field("信号等级", position.grade if position is not None else "-"),
                _card_field("保证金/杠杆", _margin_leverage_label(position)),
                _card_field("杠杆止损价", _leveraged_exit_price_label(position, "stop")),
                _card_field("杠杆止盈价", _leveraged_exit_price_label(position, "take_profit")),
            ]
        )
    elif event.status == "emergency_drawdown":
        fields.extend(
            [
                _card_field("保证金/杠杆", _margin_leverage_label(position)),
                _card_field("开仓价格", _format_decimal(position.entry_price if position is not None else None, 8)),
                _card_field("杠杆止损价", _leveraged_exit_price_label(position, "stop")),
                _card_field("杠杆止盈价", _leveraged_exit_price_label(position, "take_profit")),
            ]
        )
    else:
        fields.extend(
            [
                _card_field("退出原因", event.exit_reason or "-"),
                _card_field("已实现盈亏", _format_signed_decimal(event.realized_pnl, 2)),
                _card_field("保证金收益率", _format_signed_decimal(event.realized_pnl_pct, 2, suffix="%")),
                _card_field("保证金/杠杆", _margin_leverage_label(position)),
                _card_field("开仓价格", _format_decimal(position.entry_price if position is not None else None, 8)),
                _card_field("杠杆止损价", _leveraged_exit_price_label(position, "stop")),
                _card_field("杠杆止盈价", _leveraged_exit_price_label(position, "take_profit")),
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
                {"tag": "div", "fields": fields},
            ],
        },
    }


def _action_label(event: TradingEvent) -> str:
    if event.status == "emergency_drawdown":
        return _status_label(event.status)
    if event.action == "BUY":
        return "模拟买入通知" if event.mode == "paper" else "买入通知"
    return "模拟卖出通知" if event.mode == "paper" else "卖出通知"


def _header_template(event: TradingEvent) -> str:
    if event.status == "emergency_drawdown":
        return "orange"
    return "green" if event.action == "BUY" else "red"


def _status_label(status: str) -> str:
    labels = {
        "paper_filled": "模拟成交",
        "filled": "成交",
        "emergency_drawdown": "紧急回撤预警",
    }
    return labels.get(status, status)


def _message_label(event: TradingEvent) -> str:
    message = event.message or "-"
    if event.status == "emergency_drawdown":
        return f"{_status_label(event.status)}：{message}"
    return message


def _mode_label(value: str) -> str:
    return "模拟" if value == "paper" else "实盘" if value == "live" else value


def _format_time(value: datetime) -> str:
    return format_app_datetime(value, include_timezone=True)


def _card_field(label: str, value: str, *, short: bool = True) -> dict[str, object]:
    return {
        "is_short": short,
        "text": {"tag": "lark_md", "content": f"**{label}**\n{value or '-'}"},
    }


def _margin_leverage_label(position: TradingPosition | None) -> str:
    if position is None:
        return "-"
    margin_notional = position.margin_notional if position.margin_notional is not None else position.quote_notional
    return f"{margin_notional:.2f} / {position.leverage:.1f}x"


def _leveraged_exit_price_label(position: TradingPosition | None, kind: str) -> str:
    if position is None or position.entry_price <= 0:
        return "-"
    target_price = position.stop_price if kind == "stop" else position.take_profit_price
    price_return_pct = ((target_price - position.entry_price) / position.entry_price) * 100
    margin_roi_pct = price_return_pct * position.leverage
    return f"{target_price:.8f} ({position.leverage:.1f}x ≈ {margin_roi_pct:+.2f}% ROI)"


def _format_decimal(value: float | None, precision: int, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{float(value):.{precision}f}{suffix}"


def _format_signed_decimal(value: float | None, precision: int, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{float(value):+.{precision}f}{suffix}"
