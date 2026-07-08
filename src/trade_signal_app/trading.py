from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path

from .entry_filters import anti_chase_reason_from_config, structure_adjusted_exit_prices, structure_entry_reason_from_config
from .feishu import FeishuTradeNotifier
from .runtime_config import AutoTradeDefaults
from .service import SignalScanner
from .time_utils import now_app_time, to_app_time

LIVE_CONFIRM_VALUE = "I_UNDERSTAND_REAL_ORDERS"
MIN_EMERGENCY_ALERT_COOLDOWN_MINUTES = 30
EMERGENCY_DRAWDOWN_STATUS = "emergency_drawdown"


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
    exchange: str = "BINANCE"
    highest_price: float | None = None
    leverage: float = 1.0
    margin_notional: float | None = None


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
    realized_pnl: float | None = None
    realized_pnl_pct: float | None = None
    exit_reason: str = ""
    created_at: datetime = field(default_factory=now_app_time)
    response: dict[str, object] | None = None
    exchange: str = "BINANCE"


@dataclass
class TradingRunReport:
    enabled: bool
    mode: str
    scanned_symbols: int
    returned_signals: int
    open_positions: list[TradingPosition]
    events: list[TradingEvent]
    generated_at: datetime = field(default_factory=now_app_time)


class TradingStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[TradingPosition]:
        payload = self._load_payload()
        positions = payload.get("positions", [])
        if not isinstance(positions, list):
            return []
        return [self._position_from_dict(item) for item in positions if isinstance(item, dict)]

    def load_events(self) -> list[TradingEvent]:
        payload = self._load_payload()
        events = payload.get("events", [])
        if not isinstance(events, list):
            return []
        return [self._event_from_dict(item) for item in events if isinstance(item, dict)]

    def _load_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        text = self.path.read_text(encoding="utf-8")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            payload = self._recover_json_payload(text, exc)
        if not isinstance(payload, dict):
            return {}
        return payload

    def _recover_json_payload(self, text: str, exc: json.JSONDecodeError) -> object:
        decoder = json.JSONDecoder()
        try:
            payload, end = decoder.raw_decode(text)
        except json.JSONDecodeError:
            return {}
        if not text[end:].strip():
            return payload
        backup_path = self.path.with_suffix(f"{self.path.suffix}.corrupt-{now_app_time().strftime('%Y%m%d%H%M%S')}")
        try:
            backup_path.write_text(text, encoding="utf-8")
            if isinstance(payload, dict):
                self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return payload if isinstance(payload, dict) and exc.msg == "Extra data" else {}

    def save(self, positions: list[TradingPosition]) -> None:
        existing_events = self.load_events()
        self._write_state(positions, existing_events)

    def append_events(self, events: list[TradingEvent], *, limit: int = 200) -> None:
        if not events:
            return
        positions = self.load()
        existing_events = self.load_events()
        self._write_state(positions, [*existing_events, *events][-limit:])

    def _write_state(self, positions: list[TradingPosition], events: list[TradingEvent]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": "trading_state",
            "version": 1,
            "positions": [self._position_to_dict(position) for position in positions],
            "events": [self._event_to_dict(event) for event in events],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _position_from_dict(payload: dict[str, object]) -> TradingPosition:
        entry_price = float(payload["entry_price"])
        highest_price = payload.get("highest_price")
        return TradingPosition(
            symbol=str(payload["symbol"]),
            quantity=float(payload["quantity"]),
            entry_price=entry_price,
            quote_notional=float(payload["quote_notional"]),
            score=float(payload["score"]),
            grade=str(payload["grade"]),
            opened_at=to_app_time(datetime.fromisoformat(str(payload["opened_at"]))),
            stop_price=float(payload["stop_price"]),
            take_profit_price=float(payload["take_profit_price"]),
            mode=str(payload.get("mode", "paper")),
            client_order_id=str(payload.get("client_order_id", "")),
            exchange=str(payload.get("exchange", "BINANCE")).upper(),
            highest_price=float(highest_price) if highest_price is not None else entry_price,
            leverage=max(1.0, float(payload.get("leverage") or 1.0)),
            margin_notional=float(payload["margin_notional"]) if payload.get("margin_notional") is not None else None,
        )

    @staticmethod
    def _position_to_dict(position: TradingPosition) -> dict[str, object]:
        payload = asdict(position)
        payload["opened_at"] = to_app_time(position.opened_at).isoformat()
        return payload

    @staticmethod
    def _event_from_dict(payload: dict[str, object]) -> TradingEvent:
        created_at = payload.get("created_at")
        return TradingEvent(
            action=str(payload.get("action", "")),
            symbol=str(payload.get("symbol", "")),
            mode=str(payload.get("mode", "paper")),
            status=str(payload.get("status", "")),
            message=str(payload.get("message", "")),
            score=float(payload["score"]) if payload.get("score") is not None else None,
            price=float(payload["price"]) if payload.get("price") is not None else None,
            quantity=float(payload["quantity"]) if payload.get("quantity") is not None else None,
            quote_notional=float(payload["quote_notional"]) if payload.get("quote_notional") is not None else None,
            realized_pnl=float(payload["realized_pnl"]) if payload.get("realized_pnl") is not None else None,
            realized_pnl_pct=float(payload["realized_pnl_pct"]) if payload.get("realized_pnl_pct") is not None else None,
            exit_reason=str(payload.get("exit_reason", "")),
            created_at=to_app_time(datetime.fromisoformat(str(created_at))) if created_at else now_app_time(),
            response=payload.get("response") if isinstance(payload.get("response"), dict) else None,
            exchange=str(payload.get("exchange", "BINANCE")).upper(),
        )

    @staticmethod
    def _event_to_dict(event: TradingEvent) -> dict[str, object]:
        payload = asdict(event)
        payload["created_at"] = to_app_time(event.created_at).isoformat()
        return payload


class AutoTrader:
    def __init__(
        self,
        *,
        scanner: SignalScanner,
        state_store: TradingStateStore,
        blocked_symbols: dict[str, str] | None = None,
        trade_notifier: FeishuTradeNotifier | None = None,
    ) -> None:
        self.scanner = scanner
        self.execution_gateway = getattr(scanner, "gateway", None)
        self.state_store = state_store
        self.blocked_symbols = blocked_symbols or {}
        self.trade_notifier = trade_notifier

    def set_execution_gateway(self, gateway: object) -> None:
        self.execution_gateway = gateway

    def run_once(self, config: AutoTradeDefaults) -> TradingRunReport:
        positions = self.state_store.load()
        recent_events = self.state_store.load_events()
        events: list[TradingEvent] = []
        summary, signals = self.scanner.scan()
        now = now_app_time()

        latest_prices = self._latest_prices_for_positions(
            positions,
            {signal.symbol: signal.ticker.last_price for signal in signals},
        )
        positions = self._evaluate_exits(
            positions,
            config,
            events,
            latest_prices,
            signal_by_symbol={signal.symbol: signal for signal in signals},
            recent_events=recent_events,
        )
        if not config.enabled:
            self.state_store.save(positions)
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol="*",
                    mode=config.mode,
                    status="disabled",
                    message="自动交易未启用，仅完成信号扫描和仓位检查。",
                    exchange=config.execution_exchange.upper(),
                )
            )
            self.state_store.append_events(events)
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
                    exchange=config.execution_exchange.upper(),
                )
            )
            self.state_store.save(positions)
            self.state_store.append_events(events)
            return TradingRunReport(
                enabled=True,
                mode=config.mode,
                scanned_symbols=summary.scanned_symbols,
                returned_signals=summary.returned_signals,
                open_positions=positions,
                events=events,
            )

        open_symbols = {position.symbol for position in positions}
        exposure = sum(self._position_margin_notional(position) for position in positions)
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
            if signal.symbol in self.blocked_symbols:
                events.append(
                    TradingEvent(
                        action="SKIP",
                        symbol=signal.symbol,
                        mode=config.mode,
                        status="risk_blocked",
                        message=self.blocked_symbols[signal.symbol],
                        score=signal.score,
                        price=signal.ticker.last_price,
                        exchange=config.execution_exchange.upper(),
                    )
                )
                continue
            if signal.score < config.score_threshold:
                continue
            if signal.indicators.volume_ratio < config.min_volume_ratio:
                continue
            if signal.indicators.buy_pressure_ratio < config.min_buy_pressure:
                continue
            anti_chase = self._anti_chase_reason(signal, config)
            if anti_chase:
                events.append(
                    TradingEvent(
                        action="SKIP",
                        symbol=signal.symbol,
                        mode=config.mode,
                        status="wait_pullback",
                        message=anti_chase,
                        score=signal.score,
                        price=signal.ticker.last_price,
                        exchange=config.execution_exchange.upper(),
                    )
                )
                continue
            structure_issue = self._structure_entry_reason(signal, config)
            if structure_issue:
                events.append(
                    TradingEvent(
                        action="SKIP",
                        symbol=signal.symbol,
                        mode=config.mode,
                        status="wait_support",
                        message=structure_issue,
                        score=signal.score,
                        price=signal.ticker.last_price,
                        exchange=config.execution_exchange.upper(),
                    )
                )
                continue

            position, event = self._open_position(signal, config)
            events.append(event)
            if event.status in {"filled", "paper_filled"}:
                positions.append(position)
                self._notify_trade_event(event=event, position=position)
                open_symbols.add(position.symbol)
                exposure += self._position_margin_notional(position)

        self.state_store.save(positions)
        self.state_store.append_events(events)
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
        signal_by_symbol: dict[str, object] | None = None,
        recent_events: list[TradingEvent] | None = None,
    ) -> list[TradingPosition]:
        if not positions:
            return []
        signal_by_symbol = signal_by_symbol or {}
        recent_events = recent_events or []
        remaining: list[TradingPosition] = []
        for position in positions:
            price = latest_prices.get(position.symbol)
            if price is None:
                remaining.append(position)
                continue
            position = self._apply_profit_protection(position, price, config)
            emergency_event = self._emergency_drawdown_event(position, price, config)
            if emergency_event is not None and self._should_emit_emergency_drawdown_alert(
                event=emergency_event,
                config=config,
                recent_events=[*recent_events, *events],
            ):
                events.append(emergency_event)
                self._notify_trade_event(event=emergency_event, position=position)
            exit_reason = ""
            if price <= position.stop_price:
                exit_reason = "profit_protect_stop" if position.stop_price >= position.entry_price else "stop_loss"
            elif price >= position.take_profit_price:
                signal = signal_by_symbol.get(position.symbol)
                if self._should_trend_hold(position=position, price=price, config=config, signal=signal):
                    events.append(self._trend_hold_event(position=position, price=price, signal=signal))
                    remaining.append(position)
                    continue
                exit_reason = "take_profit"
            if not exit_reason:
                remaining.append(position)
                continue
            event = self._close_position(position, price, config, exit_reason)
            events.append(event)
            if event.status in {"filled", "paper_filled"}:
                self._notify_trade_event(event=event, position=position)
                continue
            remaining.append(position)
        return remaining

    def _notify_trade_event(
        self,
        *,
        event: TradingEvent,
        position: TradingPosition | None = None,
    ) -> None:
        if self.trade_notifier is None:
            return
        try:
            self.trade_notifier.notify_trade(event=event, position=position)
        except Exception as exc:  # noqa: BLE001
            print(f"Feishu trade notification failed for {event.action} {event.symbol}: {exc}")

    def _trend_hold_event(
        self,
        *,
        position: TradingPosition,
        price: float,
        signal: object | None,
    ) -> TradingEvent:
        score = self._signal_float(signal, "score")
        return TradingEvent(
            action="HOLD",
            symbol=position.symbol,
            mode=position.mode,
            status="trend_hold",
            message="已达到固定止盈，但趋势信号仍强，继续持有并用移动止损保护浮盈。",
            score=score,
            price=price,
            quantity=position.quantity,
            quote_notional=position.quote_notional,
            exchange=position.exchange,
        )

    def _should_trend_hold(
        self,
        *,
        position: TradingPosition,
        price: float,
        config: AutoTradeDefaults,
        signal: object | None,
    ) -> bool:
        if config.exit_profile != "trend_following" or not config.trend_hold_enabled:
            return False
        if signal is None or price < position.take_profit_price:
            return False
        score = self._signal_float(signal, "score")
        volume_ratio = self._signal_indicator_float(signal, "volume_ratio", 1.0)
        buy_pressure_ratio = self._signal_indicator_float(signal, "buy_pressure_ratio", 0.0)
        return (
            score >= config.trend_hold_min_score
            and volume_ratio >= config.trend_hold_min_volume_ratio
            and buy_pressure_ratio >= config.trend_hold_min_buy_pressure
        )

    def _emergency_drawdown_event(
        self,
        position: TradingPosition,
        price: float,
        config: AutoTradeDefaults,
    ) -> TradingEvent | None:
        if config.emergency_drawdown_pct <= 0 or price <= position.stop_price:
            return None
        high_price = position.highest_price or position.entry_price
        if high_price <= 0 or price >= high_price:
            return None
        drawdown_pct = ((high_price - price) / high_price) * 100
        if drawdown_pct < config.emergency_drawdown_pct:
            return None
        return TradingEvent(
            action="ALERT",
            symbol=position.symbol,
            mode=position.mode,
            status=EMERGENCY_DRAWDOWN_STATUS,
            message=f"价格较持仓最高价快速回撤 {drawdown_pct:.2f}%，请检查突发风险和盘口流动性。",
            price=price,
            quantity=position.quantity,
            quote_notional=position.quote_notional,
            exchange=position.exchange,
        )

    def _should_emit_emergency_drawdown_alert(
        self,
        *,
        event: TradingEvent,
        config: AutoTradeDefaults,
        recent_events: list[TradingEvent],
    ) -> bool:
        cooldown_minutes = max(
            MIN_EMERGENCY_ALERT_COOLDOWN_MINUTES,
            int(config.cooldown_minutes or 0),
        )
        cutoff = event.created_at - timedelta(minutes=cooldown_minutes)
        return not any(
            item.status == EMERGENCY_DRAWDOWN_STATUS
            and item.symbol == event.symbol
            and item.created_at >= cutoff
            for item in recent_events
        )

    @staticmethod
    def _signal_float(signal: object | None, key: str, default: float = 0.0) -> float:
        if signal is None:
            return default
        if isinstance(signal, dict):
            raw_value = signal.get(key, default)
        else:
            raw_value = getattr(signal, key, default)
        try:
            return float(raw_value or default)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _signal_indicator_float(cls, signal: object | None, key: str, default: float = 0.0) -> float:
        if signal is None:
            return default
        if isinstance(signal, dict):
            raw_value = signal.get(key, default)
        else:
            indicators = getattr(signal, "indicators", None)
            raw_value = getattr(indicators, key, default)
        try:
            return float(raw_value or default)
        except (TypeError, ValueError):
            return default

    def _anti_chase_reason(self, signal: object, config: AutoTradeDefaults) -> str:
        return anti_chase_reason_from_config(
            rsi=self._signal_indicator_float(signal, "rsi_14", 50.0),
            price_vs_ema20_pct=self._signal_indicator_float(signal, "price_vs_ema20_pct", 0.0),
            recent_change_pct=self._signal_indicator_float(signal, "recent_change_pct", 0.0),
            config=config,
        )

    def _structure_entry_reason(self, signal: object, config: AutoTradeDefaults) -> str:
        return structure_entry_reason_from_config(
            close_price=self._signal_price(signal),
            support_level=self._signal_indicator_float(signal, "support_level", 0.0),
            resistance_level=self._signal_indicator_float(signal, "resistance_level", 0.0),
            support_distance_pct=self._signal_indicator_float(signal, "support_distance_pct", 0.0),
            resistance_distance_pct=self._signal_indicator_float(signal, "resistance_distance_pct", 0.0),
            support_strength=self._signal_indicator_float(signal, "support_strength", 0.0),
            risk_reward_ratio=self._signal_indicator_float(signal, "structure_risk_reward", 0.0),
            volume_ratio=self._signal_indicator_float(signal, "volume_ratio", 1.0),
            buy_pressure_ratio=self._signal_indicator_float(signal, "buy_pressure_ratio", 0.0),
            community_score=self._signal_community_score(signal),
            config=config,
        )

    @staticmethod
    def _signal_price(signal: object | None) -> float:
        if signal is None:
            return 0.0
        if isinstance(signal, dict):
            raw_value = signal.get("last_price", signal.get("price", 0.0))
        else:
            ticker = getattr(signal, "ticker", None)
            raw_value = getattr(ticker, "last_price", 0.0)
        try:
            return float(raw_value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _signal_community_score(signal: object | None) -> float | None:
        if signal is None:
            return None
        if isinstance(signal, dict):
            raw_value = signal.get("community_score")
        else:
            community_signal = getattr(signal, "community_signal", None)
            raw_value = getattr(community_signal, "score", None)
        if raw_value is None:
            return None
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    def _latest_prices_for_positions(
        self,
        positions: list[TradingPosition],
        signal_prices: dict[str, float],
    ) -> dict[str, float]:
        latest_prices = dict(signal_prices)
        missing_symbols = {
            position.symbol
            for position in positions
            if position.symbol not in latest_prices
        }
        if not missing_symbols:
            return latest_prices
        try:
            ticker24hr_symbols = getattr(self.scanner.gateway, "ticker24hr_symbols", None)
            if not callable(ticker24hr_symbols):
                return latest_prices
            for row in ticker24hr_symbols(sorted(missing_symbols)):
                symbol = str(row.get("symbol", "")).upper()
                if symbol in missing_symbols:
                    latest_prices[symbol] = float(row["lastPrice"])
        except Exception:  # noqa: BLE001
            return latest_prices
        return latest_prices

    def _open_position(self, signal, config: AutoTradeDefaults) -> tuple[TradingPosition, TradingEvent]:
        now = now_app_time()
        price = signal.ticker.last_price
        leverage = config.leverage if config.mode == "paper" else 1.0
        margin_notional = config.quote_order_qty
        position_notional = margin_notional * leverage
        quantity = position_notional / price
        client_order_id = self._client_order_id("buy", signal.symbol, now)
        stop_price, take_profit_price = self._structured_exit_prices(signal, price, config)
        position = TradingPosition(
            exchange=config.execution_exchange.upper(),
            symbol=signal.symbol,
            quantity=quantity,
            entry_price=price,
            quote_notional=position_notional,
            score=signal.score,
            grade=signal.grade,
            opened_at=now,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            mode=config.mode,
            client_order_id=client_order_id,
            highest_price=price,
            leverage=leverage,
            margin_notional=margin_notional,
        )
        if config.mode == "paper":
            return position, TradingEvent(
                action="BUY",
                exchange=config.execution_exchange.upper(),
                symbol=signal.symbol,
                mode=config.mode,
                status="paper_filled",
                message="模拟买入已记录。",
                score=signal.score,
                price=price,
                quantity=quantity,
                quote_notional=position_notional,
            )

        try:
            response = self.execution_gateway.order_market_buy(
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
                exchange=config.execution_exchange.upper(),
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
            message=f"{config.execution_exchange.upper()} 市价买入请求已提交。",
            score=signal.score,
            price=price,
            quantity=position.quantity,
            quote_notional=position.quote_notional,
            response=response_payload,
            exchange=config.execution_exchange.upper(),
        )

    def _structured_exit_prices(self, signal: object, price: float, config: AutoTradeDefaults) -> tuple[float, float]:
        return structure_adjusted_exit_prices(
            entry_price=price,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            support_level=self._signal_indicator_float(signal, "support_level", 0.0),
            resistance_level=self._signal_indicator_float(signal, "resistance_level", 0.0),
            enabled=config.structure_filter_enabled,
            support_stop_buffer_pct=config.support_stop_buffer_pct,
            resistance_take_profit_buffer_pct=config.resistance_take_profit_buffer_pct,
        )

    @staticmethod
    def _position_margin_notional(position: TradingPosition) -> float:
        return position.margin_notional if position.margin_notional is not None else position.quote_notional

    def _close_position(
        self,
        position: TradingPosition,
        price: float,
        config: AutoTradeDefaults,
        exit_reason: str,
    ) -> TradingEvent:
        if position.mode == "paper":
            exit_notional, realized_pnl, realized_pnl_pct = self._calculate_exit_pnl(
                position=position,
                exit_price=price,
                executed_quantity=position.quantity,
            )
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="paper_filled",
                message=f"模拟卖出已记录：{exit_reason}。",
                price=price,
                quantity=position.quantity,
                quote_notional=exit_notional,
                realized_pnl=realized_pnl,
                realized_pnl_pct=realized_pnl_pct,
                exit_reason=exit_reason,
                exchange=position.exchange,
            )
        if config.mode != "live":
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="blocked",
                message="live 持仓不能在 paper 模式下模拟平仓，请切回 live 模式或人工处理。",
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
                exit_reason=exit_reason,
                exchange=position.exchange,
            )
        if not config.enabled:
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="blocked",
                message="自动交易未启用，live 持仓不会自动平仓。",
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
                exit_reason=exit_reason,
                exchange=position.exchange,
            )
        if not self._live_confirmed():
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="blocked",
                message=f"live 平仓需要环境变量 AI_TRADE_LIVE_CONFIRM={LIVE_CONFIRM_VALUE}。",
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
                exit_reason=exit_reason,
                exchange=position.exchange,
            )
        try:
            response = self.execution_gateway.order_market_sell(
                symbol=position.symbol,
                quantity=self._floor_quantity_for_symbol(position.symbol, position.quantity),
                test=config.order_test_only,
                client_order_id=self._client_order_id("sell", position.symbol, now_app_time()),
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
                exit_reason=exit_reason,
                exchange=position.exchange,
            )
        response_payload = response if isinstance(response, dict) else {"raw": response}
        executed_quantity = float(response_payload.get("executedQty") or position.quantity)
        exit_notional = float(response_payload.get("cummulativeQuoteQty") or executed_quantity * price)
        _, realized_pnl, realized_pnl_pct = self._calculate_exit_pnl(
            position=position,
            exit_price=price,
            executed_quantity=executed_quantity,
            exit_notional=exit_notional,
        )
        return TradingEvent(
            action="SELL",
            symbol=position.symbol,
            mode=config.mode,
            status="test_accepted" if config.order_test_only else "filled",
            message=f"{position.exchange.upper()} 市价卖出请求已提交：{exit_reason}。",
            price=price,
            quantity=executed_quantity,
            quote_notional=exit_notional,
            realized_pnl=None if config.order_test_only else realized_pnl,
            realized_pnl_pct=None if config.order_test_only else realized_pnl_pct,
            exit_reason=exit_reason,
            response=response_payload,
            exchange=position.exchange,
        )

    @staticmethod
    def _validate_config(config: AutoTradeDefaults) -> None:
        if config.mode not in {"paper", "live"}:
            raise ValueError("自动交易模式只能是 paper 或 live。")
        if config.execution_exchange.lower() not in {"binance", "okx"}:
            raise ValueError("自动交易执行交易所只能是 binance 或 okx。")
        if config.quote_order_qty <= 0:
            raise ValueError("单笔投入必须大于 0。")
        if config.max_open_positions < 1:
            raise ValueError("最大持仓数必须至少为 1。")
        if config.max_total_quote_exposure < config.quote_order_qty:
            raise ValueError("最大总敞口不能小于单笔投入。")
        if config.leverage < 1:
            raise ValueError("杠杆倍数不能小于 1。")
        if config.risk_per_trade_pct <= 0:
            raise ValueError("单笔风险比例必须大于 0。")
        if config.exit_profile not in {"balanced", "leveraged_conservative", "trend_following"}:
            raise ValueError("退出档位不受支持。")
        if config.stop_loss_pct <= 0 or config.take_profit_pct <= 0:
            raise ValueError("止损和止盈比例必须大于 0。")
        if config.max_entry_rsi < 0 or config.max_entry_rsi > 100:
            raise ValueError("反追高 RSI 上限必须在 0 到 100 之间。")
        if config.max_entry_price_vs_ema20_pct < 0:
            raise ValueError("反追高 EMA20 偏离上限不能小于 0。")
        if config.max_entry_recent_change_pct < 0:
            raise ValueError("反追高近端涨幅上限不能小于 0。")
        if config.max_entry_support_distance_pct < 0:
            raise ValueError("结构支撑距离上限不能小于 0。")
        if config.min_entry_support_strength < 0:
            raise ValueError("结构支撑强度下限不能小于 0。")
        if config.min_entry_risk_reward_ratio < 0:
            raise ValueError("结构盈亏比下限不能小于 0。")
        if config.min_entry_resistance_distance_pct < 0:
            raise ValueError("上方阻力空间下限不能小于 0。")
        if config.support_stop_buffer_pct < 0 or config.resistance_take_profit_buffer_pct < 0:
            raise ValueError("结构止损/止盈缓冲不能小于 0。")
        if config.profit_protection_trigger_pct < 0:
            raise ValueError("浮盈保护触发比例不能小于 0。")
        if config.profit_protection_lock_pct < 0:
            raise ValueError("浮盈保护锁盈比例不能小于 0。")
        if config.trailing_stop_pct < 0:
            raise ValueError("移动止损回撤比例不能小于 0。")
        if config.emergency_drawdown_pct < 0:
            raise ValueError("急跌预警回撤比例不能小于 0。")
        if config.profit_protection_enabled and config.profit_protection_lock_pct > config.profit_protection_trigger_pct:
            raise ValueError("浮盈保护锁盈比例不能大于触发比例。")

    @staticmethod
    def _live_confirmed() -> bool:
        return os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE

    @staticmethod
    def _client_order_id(side: str, symbol: str, now: datetime) -> str:
        return f"aitrade-{side}-{symbol.lower()}-{int(now.timestamp())}"

    def _floor_quantity_for_symbol(self, symbol: str, quantity: float) -> float:
        try:
            exchange_info = self.execution_gateway.exchange_info()
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
    def _calculate_exit_pnl(
        *,
        position: TradingPosition,
        exit_price: float,
        executed_quantity: float,
        exit_notional: float | None = None,
    ) -> tuple[float, float, float]:
        quantity = max(0.0, executed_quantity)
        if exit_notional is None:
            exit_notional = quantity * exit_price
        entry_notional = position.quote_notional
        if position.quantity > 0 and quantity != position.quantity:
            entry_notional = position.quote_notional * (quantity / position.quantity)
        margin_notional = position.margin_notional or entry_notional
        if position.quantity > 0 and quantity != position.quantity:
            margin_notional = margin_notional * (quantity / position.quantity)
        realized_pnl = exit_notional - entry_notional
        realized_pnl_pct = (realized_pnl / margin_notional) * 100 if margin_notional else 0.0
        return exit_notional, realized_pnl, realized_pnl_pct

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
            exchange=position.exchange,
            highest_price=entry_price,
            leverage=1.0,
            margin_notional=quote_notional,
        )

    @staticmethod
    def _apply_profit_protection(
        position: TradingPosition,
        price: float,
        config: AutoTradeDefaults,
    ) -> TradingPosition:
        highest_price = max(position.highest_price or position.entry_price, price)
        if not config.profit_protection_enabled or position.entry_price <= 0:
            position.highest_price = highest_price
            return position
        peak_return_pct = ((highest_price - position.entry_price) / position.entry_price) * 100
        if peak_return_pct < config.profit_protection_trigger_pct:
            position.highest_price = highest_price
            return position
        locked_stop = position.entry_price * (1 + config.profit_protection_lock_pct / 100)
        trailing_stop = highest_price * (1 - config.trailing_stop_pct / 100) if config.trailing_stop_pct > 0 else locked_stop
        position.highest_price = highest_price
        position.stop_price = max(position.stop_price, locked_stop, trailing_stop)
        return position
