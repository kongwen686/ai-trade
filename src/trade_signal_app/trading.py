from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path

from .runtime_config import AutoTradeDefaults
from .service import SignalScanner

LIVE_CONFIRM_VALUE = "I_UNDERSTAND_REAL_ORDERS"


@dataclass
class TradingPosition:
    symbol: str
    quantity: float
    entry_price: float
    quote_notional: float
    score: float
    grade: str
    opened_at: datetime
    stop_price: float
    take_profit_price: float
    mode: str = "paper"
    client_order_id: str = ""


@dataclass
class TradingEvent:
    action: str
    symbol: str
    mode: str
    status: str
    message: str
    score: float | None = None
    price: float | None = None
    quantity: float | None = None
    quote_notional: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    response: dict[str, object] | None = None


@dataclass
class TradingRunReport:
    enabled: bool
    mode: str
    scanned_symbols: int
    returned_signals: int
    open_positions: list[TradingPosition]
    events: list[TradingEvent]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TradingStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[TradingPosition]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return []
        positions = payload.get("positions", [])
        if not isinstance(positions, list):
            return []
        return [self._position_from_dict(item) for item in positions if isinstance(item, dict)]

    def save(self, positions: list[TradingPosition]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": "trading_state",
            "version": 1,
            "positions": [self._position_to_dict(position) for position in positions],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _position_from_dict(payload: dict[str, object]) -> TradingPosition:
        return TradingPosition(
            symbol=str(payload["symbol"]),
            quantity=float(payload["quantity"]),
            entry_price=float(payload["entry_price"]),
            quote_notional=float(payload["quote_notional"]),
            score=float(payload["score"]),
            grade=str(payload["grade"]),
            opened_at=datetime.fromisoformat(str(payload["opened_at"])),
            stop_price=float(payload["stop_price"]),
            take_profit_price=float(payload["take_profit_price"]),
            mode=str(payload.get("mode", "paper")),
            client_order_id=str(payload.get("client_order_id", "")),
        )

    @staticmethod
    def _position_to_dict(position: TradingPosition) -> dict[str, object]:
        payload = asdict(position)
        payload["opened_at"] = position.opened_at.isoformat()
        return payload


class AutoTrader:
    def __init__(self, *, scanner: SignalScanner, state_store: TradingStateStore) -> None:
        self.scanner = scanner
        self.state_store = state_store

    def run_once(self, config: AutoTradeDefaults) -> TradingRunReport:
        positions = self.state_store.load()
        events: list[TradingEvent] = []
        summary, signals = self.scanner.scan()
        now = datetime.now(timezone.utc)

        latest_prices = {signal.symbol: signal.ticker.last_price for signal in signals}
        positions = self._evaluate_exits(positions, config, events, latest_prices)
        if not config.enabled:
            self.state_store.save(positions)
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol="*",
                    mode=config.mode,
                    status="disabled",
                    message="自动交易未启用，仅完成信号扫描和仓位检查。",
                )
            )
            return TradingRunReport(
                enabled=False,
                mode=config.mode,
                scanned_symbols=summary.scanned_symbols,
                returned_signals=summary.returned_signals,
                open_positions=positions,
                events=events,
            )

        self._validate_config(config)
        live_allowed = config.mode == "live" and self._live_confirmed()
        if config.mode == "live" and not live_allowed:
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol="*",
                    mode=config.mode,
                    status="blocked",
                    message=f"实盘模式需要环境变量 AI_TRADE_LIVE_CONFIRM={LIVE_CONFIRM_VALUE}。",
                )
            )
            self.state_store.save(positions)
            return TradingRunReport(
                enabled=True,
                mode=config.mode,
                scanned_symbols=summary.scanned_symbols,
                returned_signals=summary.returned_signals,
                open_positions=positions,
                events=events,
            )

        open_symbols = {position.symbol for position in positions}
        exposure = sum(position.quote_notional for position in positions)
        cooldown_after = now - timedelta(minutes=config.cooldown_minutes)
        recent_symbols = {
            position.symbol
            for position in positions
            if position.opened_at > cooldown_after
        }

        for signal in signals:
            if len(positions) >= config.max_open_positions:
                break
            if exposure + config.quote_order_qty > config.max_total_quote_exposure:
                break
            if signal.symbol in open_symbols or signal.symbol in recent_symbols:
                continue
            if signal.score < config.score_threshold:
                continue
            if signal.indicators.volume_ratio < config.min_volume_ratio:
                continue
            if signal.indicators.buy_pressure_ratio < config.min_buy_pressure:
                continue

            position, event = self._open_position(signal, config)
            events.append(event)
            if event.status in {"filled", "paper_filled"}:
                positions.append(position)
                open_symbols.add(position.symbol)
                exposure += position.quote_notional

        self.state_store.save(positions)
        return TradingRunReport(
            enabled=True,
            mode=config.mode,
            scanned_symbols=summary.scanned_symbols,
            returned_signals=summary.returned_signals,
            open_positions=positions,
            events=events,
        )

    def _evaluate_exits(
        self,
        positions: list[TradingPosition],
        config: AutoTradeDefaults,
        events: list[TradingEvent],
        latest_prices: dict[str, float],
    ) -> list[TradingPosition]:
        if not positions:
            return []
        remaining: list[TradingPosition] = []
        for position in positions:
            price = latest_prices.get(position.symbol)
            if price is None:
                remaining.append(position)
                continue
            exit_reason = ""
            if price <= position.stop_price:
                exit_reason = "stop_loss"
            elif price >= position.take_profit_price:
                exit_reason = "take_profit"
            if not exit_reason:
                remaining.append(position)
                continue
            event = self._close_position(position, price, config, exit_reason)
            events.append(event)
            if event.status in {"filled", "paper_filled"}:
                continue
            remaining.append(position)
        return remaining

    def _open_position(self, signal, config: AutoTradeDefaults) -> tuple[TradingPosition, TradingEvent]:
        now = datetime.now(timezone.utc)
        price = signal.ticker.last_price
        quantity = config.quote_order_qty / price
        client_order_id = self._client_order_id("buy", signal.symbol, now)
        position = TradingPosition(
            symbol=signal.symbol,
            quantity=quantity,
            entry_price=price,
            quote_notional=config.quote_order_qty,
            score=signal.score,
            grade=signal.grade,
            opened_at=now,
            stop_price=price * (1 - config.stop_loss_pct / 100),
            take_profit_price=price * (1 + config.take_profit_pct / 100),
            mode=config.mode,
            client_order_id=client_order_id,
        )
        if config.mode == "paper":
            return position, TradingEvent(
                action="BUY",
                symbol=signal.symbol,
                mode=config.mode,
                status="paper_filled",
                message="模拟买入已记录。",
                score=signal.score,
                price=price,
                quantity=quantity,
                quote_notional=config.quote_order_qty,
            )

        try:
            response = self.scanner.gateway.order_market_buy(
                symbol=signal.symbol,
                quote_order_qty=config.quote_order_qty,
                test=config.order_test_only,
                client_order_id=client_order_id,
            )
        except Exception as exc:  # noqa: BLE001
            return position, TradingEvent(
                action="BUY",
                symbol=signal.symbol,
                mode=config.mode,
                status="rejected",
                message=str(exc),
                score=signal.score,
                price=price,
                quantity=quantity,
                quote_notional=config.quote_order_qty,
            )
        response_payload = response if isinstance(response, dict) else {"raw": response}
        if not config.order_test_only:
            position = self._position_from_order_response(
                position=position,
                response=response_payload,
                fallback_price=price,
            )
        return position, TradingEvent(
            action="BUY",
            symbol=signal.symbol,
            mode=config.mode,
            status="test_accepted" if config.order_test_only else "filled",
            message="Binance 市价买入请求已提交。",
            score=signal.score,
            price=price,
            quantity=position.quantity,
            quote_notional=position.quote_notional,
            response=response_payload,
        )

    def _close_position(
        self,
        position: TradingPosition,
        price: float,
        config: AutoTradeDefaults,
        exit_reason: str,
    ) -> TradingEvent:
        if position.mode == "paper" or config.mode == "paper":
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="paper_filled",
                message=f"模拟卖出已记录：{exit_reason}。",
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
            )
        try:
            response = self.scanner.gateway.order_market_sell(
                symbol=position.symbol,
                quantity=self._floor_quantity_for_symbol(position.symbol, position.quantity),
                test=config.order_test_only,
                client_order_id=self._client_order_id("sell", position.symbol, datetime.now(timezone.utc)),
            )
        except Exception as exc:  # noqa: BLE001
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=config.mode,
                status="rejected",
                message=str(exc),
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
            )
        return TradingEvent(
            action="SELL",
            symbol=position.symbol,
            mode=config.mode,
            status="test_accepted" if config.order_test_only else "filled",
            message=f"Binance 市价卖出请求已提交：{exit_reason}。",
            price=price,
            quantity=position.quantity,
            quote_notional=position.quantity * price,
            response=response if isinstance(response, dict) else {"raw": response},
        )

    @staticmethod
    def _validate_config(config: AutoTradeDefaults) -> None:
        if config.mode not in {"paper", "live"}:
            raise ValueError("自动交易模式只能是 paper 或 live。")
        if config.quote_order_qty <= 0:
            raise ValueError("单笔投入必须大于 0。")
        if config.max_open_positions < 1:
            raise ValueError("最大持仓数必须至少为 1。")
        if config.max_total_quote_exposure < config.quote_order_qty:
            raise ValueError("最大总敞口不能小于单笔投入。")
        if config.stop_loss_pct <= 0 or config.take_profit_pct <= 0:
            raise ValueError("止损和止盈比例必须大于 0。")

    @staticmethod
    def _live_confirmed() -> bool:
        return os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE

    @staticmethod
    def _client_order_id(side: str, symbol: str, now: datetime) -> str:
        return f"aitrade-{side}-{symbol.lower()}-{int(now.timestamp())}"

    def _floor_quantity_for_symbol(self, symbol: str, quantity: float) -> float:
        try:
            exchange_info = self.scanner.gateway.exchange_info()
            for item in exchange_info.get("symbols", []):
                if item.get("symbol") != symbol:
                    continue
                for filter_item in item.get("filters", []):
                    if filter_item.get("filterType") == "LOT_SIZE":
                        return self._floor_quantity(quantity, str(filter_item["stepSize"]))
        except Exception:  # noqa: BLE001
            pass
        return self._floor_quantity(quantity, "0.00000001")

    @staticmethod
    def _floor_quantity(quantity: float, step_size: str) -> float:
        step = float(step_size)
        if step <= 0:
            return quantity
        precision = 0
        if "." in step_size:
            precision = len(step_size.rstrip("0").split(".")[-1])
        return round(math.floor(quantity / step) * step, precision)

    @staticmethod
    def _position_from_order_response(
        *,
        position: TradingPosition,
        response: dict[str, object],
        fallback_price: float,
    ) -> TradingPosition:
        executed_qty = float(response.get("executedQty") or position.quantity)
        quote_notional = float(response.get("cummulativeQuoteQty") or position.quote_notional)
        entry_price = quote_notional / executed_qty if executed_qty > 0 else fallback_price
        return TradingPosition(
            symbol=position.symbol,
            quantity=executed_qty,
            entry_price=entry_price,
            quote_notional=quote_notional,
            score=position.score,
            grade=position.grade,
            opened_at=position.opened_at,
            stop_price=entry_price * (1 - (position.entry_price - position.stop_price) / position.entry_price),
            take_profit_price=entry_price * (1 + (position.take_profit_price - position.entry_price) / position.entry_price),
            mode=position.mode,
            client_order_id=position.client_order_id,
        )
