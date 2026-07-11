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


EMERGENCY_DRAWDOWN_STATUS = "emergency_drawdown"
NOTIFIABLE_TRADE_STATUSES = {"paper_filled", "filled", EMERGENCY_DRAWDOWN_STATUS}
STATUS_LABELS = {
    "paper_filled": "模拟成交",
    "filled": "成交",
    EMERGENCY_DRAWDOWN_STATUS: "紧急回撤预警",
    "blocked": "已阻断",
    "risk_blocked": "风控阻断",
    "rejected": "已拒绝",
    "auth_failed": "授权失败",
    "wait_pullback": "等待回调",
    "wait_support": "等待支撑确认",
    "wait_volatility": "等待波动回落",
    "trend_hold": "趋势持有",
    "no_signal": "暂无信号",
}


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
        if event.status != EMERGENCY_DRAWDOWN_STATUS and event.action not in {"BUY", "SELL"}:
            return False
        if _requires_open_position(event) and not _has_open_position(position):
            return False

        return self._post_payload(build_feishu_trade_payload(event=event, position=position))

    def notify_daily_summary(self, *, summary: dict[str, object]) -> bool:
        if not self.configured():
            return False
        return self._post_payload(build_feishu_daily_summary_payload(summary=summary))

    def notify_btc_signal(self, *, summary: dict[str, object]) -> bool:
        if not self.configured():
            return False
        return self._post_payload(build_feishu_btc_signal_payload(summary=summary))

    def _post_payload(self, payload: dict[str, object]) -> bool:
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


def build_feishu_daily_summary_payload(*, summary: dict[str, object]) -> dict[str, object]:
    date_label = str(summary.get("date") or "-")
    generated_at = summary.get("generated_at")
    scan = summary.get("scan") if isinstance(summary.get("scan"), dict) else {}
    trading = summary.get("trading") if isinstance(summary.get("trading"), dict) else {}
    intelligence = summary.get("intelligence") if isinstance(summary.get("intelligence"), dict) else {}
    risk = summary.get("risk") if isinstance(summary.get("risk"), dict) else {}
    fields = [
        _card_field("统计日期", date_label),
        _card_field("生成时间", _format_optional_time(generated_at)),
        _card_field("信号", f"{_format_int(scan.get('returned_signals'))} / {_format_int(scan.get('scanned_symbols'))}"),
        _card_field("今日成交", _format_int(trading.get("today_trades"))),
        _card_field("当日已实现盈亏", _format_signed_decimal(trading.get("today_realized_pnl"), 2)),
        _card_field("累计成交", _format_int(trading.get("total_trades"))),
        _card_field("胜率", _format_decimal(trading.get("win_rate_pct"), 2, suffix="%")),
        _card_field("账户盈亏", _format_signed_decimal(trading.get("total_pnl"), 2)),
        _card_field("已实现盈亏", _format_signed_decimal(trading.get("realized_pnl"), 2)),
        _card_field("未实现盈亏", _format_signed_decimal(trading.get("unrealized_pnl"), 2)),
        _card_field("当前持仓", _format_int(trading.get("open_positions"))),
        _card_field("情报项", _intelligence_label(intelligence)),
        _card_field("风险评分", _format_decimal(risk.get("risk_score"), 1)),
        _card_field("风控状态", _risk_status_label(str(risk.get("status") or "-"))),
        _card_field("阻断标的", _format_int(risk.get("blocked"))),
    ]
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    if warnings:
        fields.append(_card_field("提示", "；".join(str(item) for item in warnings if str(item).strip()) or "-", short=False))
    top_symbols = scan.get("top_symbols") if isinstance(scan.get("top_symbols"), list) else []
    if top_symbols:
        fields.append(_card_field("高分信号", "、".join(str(item) for item in top_symbols[:8]), short=False))

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"AI Trade 每日数据统计 {date_label}"},
            },
            "elements": [
                {"tag": "div", "fields": fields},
            ],
        },
    }


def build_feishu_btc_signal_payload(*, summary: dict[str, object]) -> dict[str, object]:
    action = str(summary.get("action") or "HOLD").upper()
    action_label = str(summary.get("action_label") or _btc_action_label(action))
    generated_at = summary.get("generated_at")
    trade_levels = summary.get("trade_levels") if isinstance(summary.get("trade_levels"), dict) else {}
    regime = summary.get("regime") if isinstance(summary.get("regime"), dict) else {}
    statistics = summary.get("statistics") if isinstance(summary.get("statistics"), dict) else {}
    sample = statistics.get("sample") if isinstance(statistics.get("sample"), dict) else {}
    selected_preset = summary.get("selected_preset") if isinstance(summary.get("selected_preset"), dict) else {}
    reasons = summary.get("reasons") if isinstance(summary.get("reasons"), list) else []
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    preset_backtests = summary.get("preset_backtests") if isinstance(summary.get("preset_backtests"), list) else []
    fields = [
        _card_field("标的", str(summary.get("symbol") or "BTCUSDT")),
        _card_field("信号", f"{action_label} / {summary.get('signal') or '-'}"),
        _card_field("生成时间", _format_optional_time(generated_at)),
        _card_field("当前价格", _format_decimal(_float_or_none(summary.get("price")), 8)),
        _card_field("评分", f"{_format_decimal(_float_or_none(summary.get('score')), 2)} / {summary.get('grade') or '-'}"),
        _card_field("置信度", str(summary.get("confidence") or "-")),
        _card_field("趋势状态", str(regime.get("label") or "-")),
        _card_field("1h RSI", _format_decimal(_float_or_none(regime.get("entry_rsi_14")), 2)),
        _card_field("4h 支撑", _format_decimal(_float_or_none(trade_levels.get("support_level")), 8)),
        _card_field("4h 阻力", _format_decimal(_float_or_none(trade_levels.get("resistance_level")), 8)),
        _card_field("止损价", _format_exit_price(trade_levels, "stop")),
        _card_field("止盈价", _format_exit_price(trade_levels, "take_profit")),
        _card_field("5x 止损参考", _format_leveraged_roi(trade_levels, "stop")),
        _card_field("5x 止盈参考", _format_leveraged_roi(trade_levels, "take_profit")),
        _card_field("结构盈亏比", _format_decimal(_float_or_none(trade_levels.get("risk_reward_ratio")), 2)),
        _card_field("最佳预设", _btc_preset_label(selected_preset)),
        _card_field("历史样本", f"{_format_int(sample.get('primary_bars'))} 根 4h K线", short=False),
        _card_field("10年持有收益", _format_signed_decimal(_float_or_none(statistics.get("buy_hold_return_pct")), 2, suffix="%")),
        _card_field("最大回撤", _format_signed_decimal(_float_or_none(statistics.get("max_drawdown_pct")), 2, suffix="%")),
        _card_field("近90天收益", _format_signed_decimal(_float_or_none(statistics.get("return_90d_pct")), 2, suffix="%")),
    ]
    if preset_backtests:
        fields.append(_card_field("BTC预设回测", _btc_backtest_digest(preset_backtests), short=False))
    if reasons:
        fields.append(_card_field("理由", "；".join(str(item) for item in reasons[:5]), short=False))
    if warnings:
        fields.append(_card_field("风险", "；".join(str(item) for item in warnings[:5]), short=False))
    if summary.get("advice"):
        fields.append(_card_field("操作建议", str(summary.get("advice")), short=False))

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": _btc_header_template(action),
                "title": {"tag": "plain_text", "content": f"AI Trade BTC 专属{action_label}信号"},
            },
            "elements": [
                {"tag": "div", "fields": fields},
            ],
        },
    }


def build_feishu_trade_payload(*, event: TradingEvent, position: TradingPosition | None = None) -> dict[str, object]:
    action_label = _action_label(event)
    header_template = _header_template(event)
    fields = [
        _card_field("标的", event.symbol),
        _card_field("触发时间" if event.status == EMERGENCY_DRAWDOWN_STATUS else "成交时间", _format_time(event.created_at)),
        _card_field("当前价格" if event.status == EMERGENCY_DRAWDOWN_STATUS else "成交价格", _format_decimal(event.price, 8)),
        _card_field("持仓数量" if event.status == EMERGENCY_DRAWDOWN_STATUS else "成交数量", _format_decimal(event.quantity, 8)),
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
    elif event.status == EMERGENCY_DRAWDOWN_STATUS:
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
    if event.status == EMERGENCY_DRAWDOWN_STATUS:
        return _status_label(event.status)
    if event.action == "BUY":
        return "模拟买入通知" if event.mode == "paper" else "买入通知"
    return "模拟卖出通知" if event.mode == "paper" else "卖出通知"


def _header_template(event: TradingEvent) -> str:
    if event.status == EMERGENCY_DRAWDOWN_STATUS:
        return "orange"
    return "green" if event.action == "BUY" else "red"


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _message_label(event: TradingEvent) -> str:
    message = event.message or "-"
    if event.status == EMERGENCY_DRAWDOWN_STATUS:
        return f"{_status_label(event.status)}：{message}"
    return message


def _requires_open_position(event: TradingEvent) -> bool:
    return event.status == EMERGENCY_DRAWDOWN_STATUS or event.action == "ALERT"


def _has_open_position(position: TradingPosition | None) -> bool:
    return position is not None and position.quantity > 0


def _mode_label(value: str) -> str:
    return "模拟" if value == "paper" else "实盘" if value == "live" else value


def _format_time(value: datetime) -> str:
    return format_app_datetime(value, include_timezone=True)


def _format_optional_time(value: object) -> str:
    if isinstance(value, datetime):
        return _format_time(value)
    if isinstance(value, str) and value.strip():
        try:
            return _format_time(datetime.fromisoformat(value))
        except ValueError:
            return value
    return "-"


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


def _format_int(value: object) -> str:
    try:
        return str(int(float(value or 0)))
    except (TypeError, ValueError):
        return "0"


def _intelligence_label(intelligence: dict[str, object]) -> str:
    return (
        f"市场 {_format_int(intelligence.get('intel_items'))} / "
        f"链上 {_format_int(intelligence.get('onchain_events'))} / "
        f"策略 {_format_int(intelligence.get('strategy_hits'))}"
    )


def _risk_status_label(status: str) -> str:
    labels = {
        "clear": "正常",
        "caution": "注意",
        "blocked": "阻断",
        "fallback": "降级",
        "unknown": "未知",
    }
    return labels.get(status, status or "-")


def _btc_action_label(action: str) -> str:
    labels = {
        "BUY": "买入",
        "SELL": "卖出/减仓",
        "HOLD": "观察",
    }
    return labels.get(action, action or "-")


def _btc_header_template(action: str) -> str:
    if action == "BUY":
        return "green"
    if action == "SELL":
        return "red"
    return "blue"


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_exit_price(trade_levels: dict[str, object], kind: str) -> str:
    key = "stop_price" if kind == "stop" else "take_profit_price"
    pct_key = "stop_pct" if kind == "stop" else "take_profit_pct"
    price = _format_decimal(_float_or_none(trade_levels.get(key)), 8)
    pct = _format_decimal(_float_or_none(trade_levels.get(pct_key)), 2, suffix="%")
    return f"{price} ({pct})"


def _format_leveraged_roi(trade_levels: dict[str, object], kind: str) -> str:
    leverage = _float_or_none(trade_levels.get("leverage_reference")) or 5.0
    roi_key = "leveraged_stop_roi_pct" if kind == "stop" else "leveraged_take_profit_roi_pct"
    return f"{leverage:.1f}x ≈ {_format_signed_decimal(_float_or_none(trade_levels.get(roi_key)), 2, suffix='%')} ROI"


def _btc_preset_label(selected_preset: dict[str, object]) -> str:
    if not selected_preset:
        return "-"
    label = str(selected_preset.get("label") or selected_preset.get("preset_id") or "-")
    win_rate = _float_or_none(selected_preset.get("win_rate_pct"))
    profit_factor = _float_or_none(selected_preset.get("profit_factor"))
    if win_rate is None and profit_factor is None:
        return label
    return f"{label} / 胜率 {_format_decimal(win_rate, 2, suffix='%')} / PF {_format_decimal(profit_factor, 2)}"


def _btc_backtest_digest(preset_backtests: list[object]) -> str:
    rows: list[str] = []
    for item in preset_backtests:
        if not isinstance(item, dict) or item.get("status") != "ok":
            continue
        rows.append(
            f"{item.get('label') or item.get('preset_id')}: "
            f"信号 {_format_int(item.get('signal_count'))}, "
            f"胜率 {_format_decimal(_float_or_none(item.get('win_rate_pct')), 2, suffix='%')}, "
            f"PF {_format_decimal(_float_or_none(item.get('profit_factor')), 2)}"
        )
    return "；".join(rows[:4]) or "-"
