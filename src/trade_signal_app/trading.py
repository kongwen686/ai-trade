from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path

from .binance_client import BinanceOrderStatusUnknown
from .entry_filters import (
    anti_chase_reason_from_config,
    structure_adjusted_exit_prices,
    structure_entry_reason_from_config,
)
from .feishu import FeishuTradeNotifier
from .runtime_config import AutoTradeDefaults
from .service import SignalScanner
from .storage import LocalDataStore
from .strategy import entry_rule_config_from_runtime, evaluate_long_entry
from .time_utils import now_app_time, to_app_time
from .volatility import volatility_entry_reason

LIVE_CONFIRM_VALUE = "I_UNDERSTAND_REAL_ORDERS"
MIN_EMERGENCY_ALERT_COOLDOWN_MINUTES = 30
EMERGENCY_DRAWDOWN_STATUS = "emergency_drawdown"
FILLED_TRADE_STATUSES = {"filled", "paper_filled", "partially_filled", "reconciled_filled"}
INFLIGHT_TRADE_STATUSES = {"order_pending", "status_unknown"}
EXTERNAL_POSITION_CLOSED_STATUS = "external_closed"
TRADE_EVENT_ACTIONS = {"BUY", "SELL"}
TRADING_EVENT_RETENTION_LIMIT = 5000
NO_ELIGIBLE_SIGNAL_STATUS = "no_eligible_signal"
NO_ELIGIBLE_SIGNAL_LOG_COOLDOWN_MINUTES = 60


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
    position_id: str = ""
    entry_order_id: str = ""
    entry_fee_quote: float = 0.0
    protection_order_id: str = ""
    protection_client_order_id: str = ""
    protection_stop_price: float | None = None
    protection_status: str = ""
    protection_executed_quantity: float = 0.0
    pending_exit_order_id: str = ""
    pending_exit_client_order_id: str = ""


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
    gross_pnl: float | None = None
    fees_quote: float = 0.0
    exit_reason: str = ""
    created_at: datetime = field(default_factory=now_app_time)
    response: dict[str, object] | None = None
    exchange: str = "BINANCE"
    position_id: str = ""
    client_order_id: str = ""
    exchange_order_id: str = ""


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
    def __init__(self, path: Path, database_path: Path | None = None) -> None:
        self.path = path
        self.data_store = LocalDataStore(database_path or path.with_name("ai_trade.sqlite3"))

    def load(self) -> list[TradingPosition]:
        payload = self._load_payload()
        raw_positions = payload.get("positions", [])
        positions = (
            [self._position_from_dict(item) for item in raw_positions if isinstance(item, dict)]
            if isinstance(raw_positions, list)
            else []
        )
        try:
            if positions:
                self.data_store.replace_trading_positions([self._position_to_dict(position) for position in positions])
                return positions
            stored_positions = [
                self._position_from_dict(item)
                for item in self.data_store.load_trading_position_payloads()
                if isinstance(item, dict)
            ]
            return stored_positions
        except Exception:  # noqa: BLE001
            return positions

    def load_events(self) -> list[TradingEvent]:
        payload = self._load_payload()
        raw_events = payload.get("events", [])
        events = (
            [self._event_from_dict(item) for item in raw_events if isinstance(item, dict)]
            if isinstance(raw_events, list)
            else []
        )
        try:
            if events:
                self.data_store.upsert_trading_events([self._event_to_dict(event) for event in events])
            stored_events = [
                self._event_from_dict(item)
                for item in self.data_store.load_trading_event_payloads()
                if isinstance(item, dict)
            ]
            return stored_events or events
        except Exception:  # noqa: BLE001
            return events

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
        self._write_state(
            positions,
            self._retained_events(existing_events, limit=TRADING_EVENT_RETENTION_LIMIT),
            database_events=existing_events,
        )

    def append_events(self, events: list[TradingEvent], *, limit: int = TRADING_EVENT_RETENTION_LIMIT) -> None:
        if not events:
            return
        positions = self.load()
        existing_events = self.load_events()
        database_events = [*existing_events, *events]
        self._write_state(positions, self._retained_events(database_events, limit=limit), database_events=database_events)

    @staticmethod
    def _is_filled_trade_event(event: TradingEvent) -> bool:
        return event.action in TRADE_EVENT_ACTIONS and event.status in FILLED_TRADE_STATUSES

    @classmethod
    def _retained_events(cls, events: list[TradingEvent], *, limit: int) -> list[TradingEvent]:
        if limit <= 0 or len(events) <= limit:
            return events

        indexed_events = list(enumerate(events))
        filled_indexes = [index for index, event in indexed_events if cls._is_filled_trade_event(event)]
        filled_index_set = set(filled_indexes)
        retained_indexes = set(filled_indexes[-limit:])
        remaining = max(0, limit - len(retained_indexes))
        if remaining:
            diagnostic_indexes = [index for index, _ in indexed_events if index not in filled_index_set]
            retained_indexes.update(diagnostic_indexes[-remaining:])
        return [event for index, event in indexed_events if index in retained_indexes]

    def _write_state(
        self,
        positions: list[TradingPosition],
        events: list[TradingEvent],
        *,
        database_events: list[TradingEvent] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sync_database(positions, database_events or events)
        payload = {
            "kind": "trading_state",
            "version": 1,
            "positions": [self._position_to_dict(position) for position in positions],
            "events": [self._event_to_dict(event) for event in events],
        }
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(self.path)

    def _sync_database(self, positions: list[TradingPosition], events: list[TradingEvent]) -> None:
        try:
            self.data_store.replace_trading_positions([self._position_to_dict(position) for position in positions])
            self.data_store.upsert_trading_events([self._event_to_dict(event) for event in events])
        except Exception:  # noqa: BLE001
            return

    def database_status(self) -> dict[str, object]:
        self._migrate_payload_to_database()
        return self.data_store.status()

    def record_metric_snapshot(self, scope: str, metrics: dict[str, object]) -> None:
        try:
            self.data_store.record_metric_snapshot(scope, metrics)
        except Exception:  # noqa: BLE001
            return

    def _migrate_payload_to_database(self) -> None:
        payload = self._load_payload()
        raw_positions = payload.get("positions", [])
        raw_events = payload.get("events", [])
        try:
            if isinstance(raw_positions, list):
                positions = [self._position_from_dict(item) for item in raw_positions if isinstance(item, dict)]
                if positions:
                    self.data_store.replace_trading_positions([self._position_to_dict(position) for position in positions])
            if isinstance(raw_events, list):
                events = [self._event_from_dict(item) for item in raw_events if isinstance(item, dict)]
                if events:
                    self.data_store.upsert_trading_events([self._event_to_dict(event) for event in events])
        except Exception:  # noqa: BLE001
            return

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
            position_id=str(payload.get("position_id") or payload.get("client_order_id") or ""),
            entry_order_id=str(payload.get("entry_order_id") or ""),
            entry_fee_quote=float(payload.get("entry_fee_quote") or 0.0),
            protection_order_id=str(payload.get("protection_order_id") or ""),
            protection_client_order_id=str(payload.get("protection_client_order_id") or ""),
            protection_stop_price=(
                float(payload["protection_stop_price"])
                if payload.get("protection_stop_price") is not None
                else None
            ),
            protection_status=str(payload.get("protection_status") or ""),
            protection_executed_quantity=float(payload.get("protection_executed_quantity") or 0.0),
            pending_exit_order_id=str(payload.get("pending_exit_order_id") or ""),
            pending_exit_client_order_id=str(payload.get("pending_exit_client_order_id") or ""),
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
            gross_pnl=float(payload["gross_pnl"]) if payload.get("gross_pnl") is not None else None,
            fees_quote=float(payload.get("fees_quote") or 0.0),
            exit_reason=str(payload.get("exit_reason", "")),
            created_at=to_app_time(datetime.fromisoformat(str(created_at))) if created_at else now_app_time(),
            response=payload.get("response") if isinstance(payload.get("response"), dict) else None,
            exchange=str(payload.get("exchange", "BINANCE")).upper(),
            position_id=str(payload.get("position_id") or ""),
            client_order_id=str(payload.get("client_order_id") or ""),
            exchange_order_id=str(payload.get("exchange_order_id") or ""),
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
        isolate_mode: bool = False,
        scan_result: tuple[object, list[object]] | None = None,
    ) -> None:
        self.scanner = scanner
        self.execution_gateway = getattr(scanner, "gateway", None)
        self.state_store = state_store
        self.blocked_symbols = blocked_symbols or {}
        self.trade_notifier = trade_notifier
        self.isolate_mode = isolate_mode
        self.scan_result = scan_result

    def set_execution_gateway(self, gateway: object) -> None:
        self.execution_gateway = gateway

    def run_once(self, config: AutoTradeDefaults) -> TradingRunReport:
        loaded_positions = self.state_store.load()
        if self.isolate_mode:
            positions = [position for position in loaded_positions if position.mode == config.mode]
            passthrough_positions = [position for position in loaded_positions if position.mode != config.mode]
        else:
            positions = loaded_positions
            passthrough_positions = []
        recent_events = self.state_store.load_events()
        events: list[TradingEvent] = []
        summary, signals = self.scan_result if self.scan_result is not None else self.scanner.scan()
        positions = self._reconcile_pending_entries(positions, recent_events, config, events)
        now = now_app_time()
        filter_counts = {
            "liquidity": 0,
            "score": 0,
            "volume": 0,
            "buy_pressure": 0,
            "cooldown": 0,
            "position_limit": 0,
            "exposure_limit": 0,
        }

        signal_prices = {signal.symbol: signal.ticker.last_price for signal in signals}
        latest_prices = self._latest_prices_for_positions(positions, signal_prices)
        positions = self._evaluate_exits(
            positions,
            config,
            events,
            latest_prices,
            signal_by_symbol={signal.symbol: signal for signal in signals},
            recent_events=recent_events,
        )
        if not config.enabled:
            combined_positions = [*passthrough_positions, *positions]
            self.state_store.save(combined_positions)
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
                open_positions=combined_positions,
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
            combined_positions = [*passthrough_positions, *positions]
            self.state_store.save(combined_positions)
            self.state_store.append_events(events)
            return TradingRunReport(
                enabled=True,
                mode=config.mode,
                scanned_symbols=summary.scanned_symbols,
                returned_signals=summary.returned_signals,
                open_positions=combined_positions,
                events=events,
            )

        open_symbols = {position.symbol for position in positions}
        exposure = sum(self._position_margin_notional(position) for position in positions)
        cooldown_after = now - timedelta(minutes=config.cooldown_minutes)
        recent_symbols = {
            event.symbol
            for event in [*recent_events, *events]
            if event.mode == config.mode
            and event.action in TRADE_EVENT_ACTIONS
            and event.status in FILLED_TRADE_STATUSES | INFLIGHT_TRADE_STATUSES
            and event.symbol != "*"
            and event.created_at > cooldown_after
        }
        entry_config = entry_rule_config_from_runtime(config)
        portfolio_risk_block = self._portfolio_risk_block_reason(config, recent_events)
        if portfolio_risk_block:
            events.append(
                TradingEvent(
                    action="SKIP",
                    symbol="*",
                    mode=config.mode,
                    status="portfolio_risk_blocked",
                    message=portfolio_risk_block,
                    exchange=config.execution_exchange.upper(),
                )
            )

        candidate_signals = [] if portfolio_risk_block else signals
        for signal_index, signal in enumerate(candidate_signals):
            if len(positions) >= config.max_open_positions:
                filter_counts["position_limit"] = len(signals) - signal_index
                break
            indicative_price = self._signal_price(signal)
            indicative_stop, _ = self._structured_exit_prices(signal, indicative_price, config)
            indicative_margin_notional = self._risk_sized_margin_notional(
                config=config,
                entry_price=indicative_price,
                stop_price=indicative_stop,
            )
            if exposure + indicative_margin_notional > config.max_total_quote_exposure:
                filter_counts["exposure_limit"] += 1
                continue
            if signal.symbol in open_symbols:
                continue
            if signal.symbol in recent_symbols:
                filter_counts["cooldown"] += 1
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
            if not bool(getattr(signal, "liquidity_eligible", True)):
                filter_counts["liquidity"] += 1
                continue
            if signal.score < config.score_threshold:
                filter_counts["score"] += 1
                continue
            entry_decision = evaluate_long_entry(
                score=signal.score,
                indicators=signal.indicators,
                config=entry_config,
                symbol=signal.symbol,
                current_price=signal.ticker.last_price,
            )
            if not entry_decision.allowed:
                status = entry_decision.status or "wait_momentum"
                if status == "wait_volume":
                    filter_counts["volume"] += 1
                elif status == "wait_buy_pressure":
                    filter_counts["buy_pressure"] += 1
                events.append(
                    TradingEvent(
                        action="SKIP",
                        symbol=signal.symbol,
                        mode=config.mode,
                        status=status,
                        message=entry_decision.reasons[-1] if entry_decision.reasons else "指标共振尚未满足",
                        score=signal.score,
                        price=signal.ticker.last_price,
                        response={"entry_setup": entry_decision.setup, "confirmations": entry_decision.reasons[-5:]},
                        exchange=config.execution_exchange.upper(),
                    )
                )
                continue
            entry_price = self._latest_price_for_symbol(signal.symbol, fallback=indicative_price)
            stop_price, _ = self._structured_exit_prices(signal, entry_price, config)
            candidate_margin_notional = self._risk_sized_margin_notional(
                config=config,
                entry_price=entry_price,
                stop_price=stop_price,
            )
            if exposure + candidate_margin_notional > config.max_total_quote_exposure:
                filter_counts["exposure_limit"] += 1
                continue
            position, event = self._open_position(signal, config, entry_price=entry_price)
            event.response = {
                **(event.response or {}),
                "entry_setup": entry_decision.setup,
                "confirmations": entry_decision.reasons[-5:],
            }
            events.append(event)
            if event.status in FILLED_TRADE_STATUSES:
                positions.append(position)
                self._notify_trade_event(event=event, position=position)
                open_symbols.add(position.symbol)
                exposure += self._position_margin_notional(position)

        summary_event: TradingEvent | None = None
        if not events:
            summary_event = TradingEvent(
                action="SKIP",
                symbol="*",
                mode=config.mode,
                status=NO_ELIGIBLE_SIGNAL_STATUS,
                message=(
                    f"本轮扫描 {summary.returned_signals} 个候选，未产生订单："
                    f"流动性门槛未通过的 {filter_counts['liquidity']} 个，"
                    f"评分低于 {config.score_threshold:.1f} 的 {filter_counts['score']} 个，"
                    f"量比低于 {config.min_volume_ratio:.2f} 的 {filter_counts['volume']} 个，"
                    f"买压低于 {config.min_buy_pressure:.2f} 的 {filter_counts['buy_pressure']} 个，"
                    f"成交冷却期内的 {filter_counts['cooldown']} 个，"
                    f"持仓上限阻断 {filter_counts['position_limit']} 个，"
                    f"敞口上限阻断 {filter_counts['exposure_limit']} 个。"
                ),
                exchange=config.execution_exchange.upper(),
            )
            events.append(summary_event)

        combined_positions = [*passthrough_positions, *positions]
        self.state_store.save(combined_positions)
        persist_events = events
        if summary_event is not None and self._has_recent_no_eligible_summary(recent_events, config.mode, now):
            persist_events = [event for event in events if event is not summary_event]
        self.state_store.append_events(persist_events)
        return TradingRunReport(
            enabled=True,
            mode=config.mode,
            scanned_symbols=summary.scanned_symbols,
            returned_signals=summary.returned_signals,
            open_positions=combined_positions,
            events=events,
        )

    @staticmethod
    def _has_recent_no_eligible_summary(
        recent_events: list[TradingEvent],
        mode: str,
        now: datetime,
    ) -> bool:
        cutoff = now - timedelta(minutes=NO_ELIGIBLE_SIGNAL_LOG_COOLDOWN_MINUTES)
        return any(
            event.status == NO_ELIGIBLE_SIGNAL_STATUS
            and event.mode == mode
            and event.created_at >= cutoff
            for event in recent_events
        )

    def _reconcile_pending_entries(
        self,
        positions: list[TradingPosition],
        recent_events: list[TradingEvent],
        config: AutoTradeDefaults,
        events: list[TradingEvent],
    ) -> list[TradingPosition]:
        if config.mode != "live":
            return positions
        latest_by_client_id: dict[str, TradingEvent] = {}
        for event in sorted(recent_events, key=lambda item: item.created_at):
            if event.mode == config.mode and event.action == "BUY" and event.client_order_id:
                latest_by_client_id[event.client_order_id] = event
        open_symbols = {position.symbol for position in positions}
        for client_order_id, pending_event in latest_by_client_id.items():
            if pending_event.status not in INFLIGHT_TRADE_STATUSES or pending_event.symbol in open_symbols:
                continue
            response = self._query_order_by_client_id(pending_event.symbol, client_order_id)
            if response is None:
                continue
            response, execution_status = self._settle_entry_response(
                pending_event.symbol,
                client_order_id,
                response,
            )
            if execution_status in INFLIGHT_TRADE_STATUSES:
                continue
            if execution_status not in FILLED_TRADE_STATUSES:
                events.append(
                    TradingEvent(
                        action="BUY",
                        symbol=pending_event.symbol,
                        mode=config.mode,
                        status="reconciled_rejected",
                        message="待确认买入订单经交易所对账后未成交。",
                        price=pending_event.price,
                        quantity=pending_event.quantity,
                        quote_notional=pending_event.quote_notional,
                        response=response,
                        exchange=pending_event.exchange,
                        position_id=pending_event.position_id,
                        client_order_id=client_order_id,
                        exchange_order_id=str(response.get("orderId") or ""),
                    )
                )
                continue
            provisional_payload = (
                pending_event.response.get("provisional_position")
                if isinstance(pending_event.response, dict)
                and isinstance(pending_event.response.get("provisional_position"), dict)
                else None
            )
            if provisional_payload is None:
                continue
            provisional = TradingStateStore._position_from_dict(provisional_payload)
            position = self._position_from_order_response(
                position=provisional,
                response=response,
                fallback_price=float(pending_event.price or provisional.entry_price),
            )
            protection_error = ""
            if config.exchange_protection_enabled and config.execution_exchange.lower() == "binance":
                position, protection_error = self._place_exchange_protection(position, config)
            event = TradingEvent(
                action="BUY",
                symbol=position.symbol,
                mode=config.mode,
                status="reconciled_filled",
                message="待确认买入订单已通过交易所对账恢复为持仓。"
                + (f" 保护单未建立：{protection_error}" if protection_error else ""),
                score=position.score,
                price=position.entry_price,
                quantity=position.quantity,
                quote_notional=position.quote_notional,
                fees_quote=position.entry_fee_quote,
                response={
                    **response,
                    "fees_quote": position.entry_fee_quote,
                    "position_client_order_id": position.position_id,
                    "protection_error": protection_error,
                },
                exchange=position.exchange,
                position_id=position.position_id,
                client_order_id=client_order_id,
                exchange_order_id=position.entry_order_id,
            )
            positions.append(position)
            open_symbols.add(position.symbol)
            events.append(event)
            self._notify_trade_event(event=event, position=position)
        return positions

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
            protection_fill = self._exchange_protection_fill_event(position, price)
            if protection_fill is not None:
                events.append(protection_fill)
                self._notify_trade_event(event=protection_fill, position=position)
                if (
                    protection_fill.status == "partially_filled"
                    and protection_fill.quantity is not None
                    and 0 < protection_fill.quantity < position.quantity
                ):
                    remaining.append(
                        self._remaining_position_after_partial_exit(position, protection_fill.quantity)
                    )
                continue
            position = self._apply_profit_protection(position, price, config)
            protection_error = self._refresh_exchange_protection(position, config)
            if protection_error:
                events.append(
                    TradingEvent(
                        action="ALERT",
                        symbol=position.symbol,
                        mode=position.mode,
                        status="protection_failed",
                        message=f"交易所保护单同步失败：{protection_error}",
                        price=price,
                        quantity=position.quantity,
                        quote_notional=position.quote_notional,
                        exchange=position.exchange,
                        position_id=position.position_id,
                    )
                )
            emergency_event = self._emergency_drawdown_event(position, price, config)
            if emergency_event is not None and self._should_emit_emergency_drawdown_alert(
                position=position,
                event=emergency_event,
                config=config,
                recent_events=[*recent_events, *events],
                signal=signal_by_symbol.get(position.symbol),
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
            if event.status in FILLED_TRADE_STATUSES:
                self._notify_trade_event(event=event, position=position)
                if (
                    event.status == "partially_filled"
                    and event.quantity is not None
                    and 0 < event.quantity < position.quantity
                ):
                    remaining.append(self._remaining_position_after_partial_exit(position, event.quantity))
                continue
            if event.status == EXTERNAL_POSITION_CLOSED_STATUS:
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
            message=f"已达到固定止盈，但评分与趋势结构仍有效；继续持有，移动止损已上移至 {position.stop_price:.8g}。",
            score=score,
            price=price,
            quantity=position.quantity,
            quote_notional=position.quote_notional,
            response={
                "highest_price": position.highest_price or price,
                "trailing_stop_price": position.stop_price,
                "fixed_take_profit_price": position.take_profit_price,
            },
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
        strong_confirmation = (
            score >= config.trend_hold_min_score
            and volume_ratio >= config.trend_hold_min_volume_ratio
            and buy_pressure_ratio >= config.trend_hold_min_buy_pressure
        )
        close_price = self._signal_indicator_float(signal, "close_price", self._signal_price(signal))
        ema_20 = self._signal_indicator_float(signal, "ema_20", 0.0)
        ema_50 = self._signal_indicator_float(signal, "ema_50", 0.0)
        if close_price <= 0 or ema_20 <= 0 or ema_50 <= 0:
            return strong_confirmation

        trend_intact = close_price >= ema_20 >= ema_50
        hold_score_floor = max(config.score_threshold, config.trend_hold_min_score - 5.0)
        return trend_intact and score >= hold_score_floor

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
            response={"drawdown_pct": drawdown_pct, "highest_price": high_price},
            exchange=position.exchange,
        )

    def _should_emit_emergency_drawdown_alert(
        self,
        *,
        position: TradingPosition,
        event: TradingEvent,
        config: AutoTradeDefaults,
        recent_events: list[TradingEvent],
        signal: object | None = None,
    ) -> bool:
        global_cooldown_minutes = max(
            MIN_EMERGENCY_ALERT_COOLDOWN_MINUTES,
            int(config.emergency_alert_global_cooldown_minutes or 0),
        )
        global_cutoff = event.created_at - timedelta(minutes=global_cooldown_minutes)
        if any(item.status == EMERGENCY_DRAWDOWN_STATUS and item.created_at >= global_cutoff for item in recent_events):
            return False

        symbol_cooldown_minutes = max(
            MIN_EMERGENCY_ALERT_COOLDOWN_MINUTES,
            int(config.cooldown_minutes or 0),
            int(config.emergency_alert_symbol_cooldown_minutes or 0),
        )
        symbol_cutoff = event.created_at - timedelta(minutes=symbol_cooldown_minutes)
        if any(
            item.status == EMERGENCY_DRAWDOWN_STATUS
            and item.symbol == event.symbol
            and item.created_at >= symbol_cutoff
            for item in recent_events
        ):
            return False

        return self._passes_low_liquidity_emergency_gate(position=position, event=event, config=config, signal=signal)

    def _passes_low_liquidity_emergency_gate(
        self,
        *,
        position: TradingPosition,
        event: TradingEvent,
        config: AutoTradeDefaults,
        signal: object | None,
    ) -> bool:
        quote_volume = self._signal_quote_volume(signal)
        if quote_volume <= 0 or quote_volume > config.emergency_low_liquidity_quote_volume:
            return True
        drawdown_pct = 0.0
        if isinstance(event.response, dict):
            try:
                drawdown_pct = float(event.response.get("drawdown_pct") or 0.0)
            except (TypeError, ValueError):
                drawdown_pct = 0.0
        score = max(position.score, self._signal_float(signal, "score"))
        required_drawdown = config.emergency_drawdown_pct * config.emergency_low_liquidity_drawdown_multiplier
        return score >= config.emergency_low_liquidity_min_score and drawdown_pct >= required_drawdown

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

    def _volatility_entry_reason(self, signal: object, config: AutoTradeDefaults) -> str:
        if isinstance(signal, dict):
            regime = str(signal.get("volatility_regime") or "normal")
        else:
            regime = str(getattr(getattr(signal, "indicators", None), "volatility_regime", "normal"))
        return volatility_entry_reason(
            regime=regime,
            percentile=self._signal_indicator_float(signal, "volatility_percentile", 50.0),
            ratio=self._signal_indicator_float(signal, "volatility_ratio", 1.0),
            atr_pct=self._signal_indicator_float(signal, "atr_pct", 0.0),
            enabled=config.volatility_filter_enabled,
            block_extreme=config.block_extreme_volatility,
            max_percentile=config.max_entry_volatility_percentile,
            max_ratio=config.max_entry_volatility_ratio,
        )

    def _structure_entry_reason(
        self,
        signal: object,
        config: AutoTradeDefaults,
        *,
        current_price: float | None = None,
    ) -> str:
        return structure_entry_reason_from_config(
            close_price=current_price if current_price and current_price > 0 else self._signal_price(signal),
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
    def _signal_quote_volume(signal: object | None) -> float:
        if signal is None:
            return 0.0
        if isinstance(signal, dict):
            raw_value = signal.get("quote_volume", signal.get("quote_volume_m", 0.0))
            multiplier = 1_000_000.0 if "quote_volume_m" in signal and "quote_volume" not in signal else 1.0
        else:
            ticker = getattr(signal, "ticker", None)
            raw_value = getattr(ticker, "quote_volume", 0.0)
            multiplier = 1.0
        try:
            return float(raw_value or 0.0) * multiplier
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

    def _fresh_prices_for_symbols(self, symbols: set[str] | list[str] | tuple[str, ...]) -> dict[str, float]:
        normalized: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized_symbol = str(symbol).upper().strip()
            if normalized_symbol and normalized_symbol not in seen:
                normalized.append(normalized_symbol)
                seen.add(normalized_symbol)
        if not normalized:
            return {}

        gateway = self.execution_gateway or getattr(self.scanner, "gateway", None)
        prices: dict[str, float] = {}
        ticker_prices = getattr(gateway, "ticker_prices", None)
        if callable(ticker_prices):
            try:
                for symbol, price in (ticker_prices(normalized) or {}).items():
                    normalized_symbol = str(symbol).upper()
                    parsed_price = float(price)
                    if normalized_symbol in seen and parsed_price > 0:
                        prices[normalized_symbol] = parsed_price
            except Exception:  # noqa: BLE001
                prices = {}

        missing_symbols = [symbol for symbol in normalized if symbol not in prices]
        ticker_price = getattr(gateway, "ticker_price", None)
        if missing_symbols and callable(ticker_price):
            for symbol in list(missing_symbols):
                try:
                    parsed_price = float(ticker_price(symbol))
                except Exception:  # noqa: BLE001
                    continue
                if parsed_price > 0:
                    prices[symbol] = parsed_price
            missing_symbols = [symbol for symbol in normalized if symbol not in prices]

        ticker24hr_symbols = getattr(gateway, "ticker24hr_symbols", None)
        if missing_symbols and callable(ticker24hr_symbols):
            try:
                for row in ticker24hr_symbols(missing_symbols):
                    symbol = str(row.get("symbol", "")).upper()
                    if symbol in missing_symbols:
                        parsed_price = float(row["lastPrice"])
                        if parsed_price > 0:
                            prices[symbol] = parsed_price
            except Exception:  # noqa: BLE001
                return prices
        return prices

    def _latest_price_for_symbol(self, symbol: str, *, fallback: float = 0.0) -> float:
        normalized = symbol.upper().strip()
        live_price = self._fresh_prices_for_symbols([normalized]).get(normalized)
        return live_price if live_price and live_price > 0 else fallback

    def _latest_prices_for_positions(
        self,
        positions: list[TradingPosition],
        signal_prices: dict[str, float],
    ) -> dict[str, float]:
        latest_prices = dict(signal_prices)
        position_symbols = {position.symbol.upper() for position in positions}
        latest_prices.update(self._fresh_prices_for_symbols(sorted(position_symbols)))
        return latest_prices

    def _open_position(
        self,
        signal,
        config: AutoTradeDefaults,
        *,
        entry_price: float | None = None,
    ) -> tuple[TradingPosition, TradingEvent]:
        now = now_app_time()
        market_price = entry_price if entry_price and entry_price > 0 else signal.ticker.last_price
        stop_price, take_profit_price = self._structured_exit_prices(signal, market_price, config)
        margin_notional = self._risk_sized_margin_notional(
            config=config,
            entry_price=market_price,
            stop_price=stop_price,
        )
        leverage = config.leverage if config.mode == "paper" else 1.0
        position_notional = margin_notional * leverage
        client_order_id = self._client_order_id("buy", signal.symbol, now)
        price = market_price
        if config.mode == "paper" and config.paper_costs_enabled:
            price = market_price * (1 + config.paper_slippage_bps / 10_000)
            stop_ratio = stop_price / market_price if market_price > 0 else 1.0
            take_profit_ratio = take_profit_price / market_price if market_price > 0 else 1.0
            stop_price = price * stop_ratio
            take_profit_price = price * take_profit_ratio
        quantity = position_notional / price
        entry_fee_quote = (
            position_notional * config.paper_fee_bps / 10_000
            if config.mode == "paper" and config.paper_costs_enabled
            else 0.0
        )
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
            position_id=client_order_id,
            entry_fee_quote=entry_fee_quote,
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
                fees_quote=entry_fee_quote,
                position_id=client_order_id,
                client_order_id=client_order_id,
                response={
                    "execution_price": price,
                    "market_price": market_price,
                    "slippage_bps": config.paper_slippage_bps if config.paper_costs_enabled else 0.0,
                    "fees_quote": entry_fee_quote,
                    "risk_sized_margin_notional": margin_notional,
                },
            )

        try:
            response = self.execution_gateway.order_market_buy(
                symbol=signal.symbol,
                quote_order_qty=margin_notional,
                test=config.order_test_only,
                client_order_id=client_order_id,
            )
        except BinanceOrderStatusUnknown as exc:
            response = self._query_order_by_client_id(signal.symbol, client_order_id)
            if response is None:
                return position, TradingEvent(
                    action="BUY",
                    symbol=signal.symbol,
                    mode=config.mode,
                    status="status_unknown",
                    message=str(exc),
                    score=signal.score,
                    price=market_price,
                    quantity=quantity,
                    quote_notional=margin_notional,
                    exchange=config.execution_exchange.upper(),
                    position_id=client_order_id,
                    client_order_id=client_order_id,
                    response={"provisional_position": TradingStateStore._position_to_dict(position)},
                )
        except Exception as exc:  # noqa: BLE001
            return position, TradingEvent(
                action="BUY",
                symbol=signal.symbol,
                mode=config.mode,
                status="rejected",
                message=str(exc),
                score=signal.score,
                price=market_price,
                quantity=quantity,
                quote_notional=margin_notional,
                exchange=config.execution_exchange.upper(),
                position_id=client_order_id,
                client_order_id=client_order_id,
            )
        response_payload = response if isinstance(response, dict) else {"raw": response}
        if config.order_test_only:
            return position, TradingEvent(
                action="BUY",
                symbol=signal.symbol,
                mode=config.mode,
                status="test_accepted",
                message=f"{config.execution_exchange.upper()} 市价买入测试请求已接受。",
                score=signal.score,
                price=market_price,
                quantity=quantity,
                quote_notional=margin_notional,
                response=response_payload,
                exchange=config.execution_exchange.upper(),
                position_id=client_order_id,
                client_order_id=client_order_id,
                exchange_order_id=str(response_payload.get("orderId") or ""),
            )
        response_payload, execution_status = self._settle_entry_response(
            signal.symbol,
            client_order_id,
            response_payload,
        )
        if execution_status not in {"filled", "partially_filled"}:
            return position, TradingEvent(
                action="BUY",
                symbol=signal.symbol,
                mode=config.mode,
                status=execution_status,
                message=f"{config.execution_exchange.upper()} 买入订单尚未确认成交，已进入对账队列。",
                score=signal.score,
                price=market_price,
                quantity=quantity,
                quote_notional=margin_notional,
                response={
                    **response_payload,
                    "provisional_position": TradingStateStore._position_to_dict(position),
                },
                exchange=config.execution_exchange.upper(),
                position_id=client_order_id,
                client_order_id=client_order_id,
                exchange_order_id=str(response_payload.get("orderId") or ""),
            )
        position = self._position_from_order_response(
            position=position,
            response=response_payload,
            fallback_price=market_price,
        )
        protection_error = ""
        if config.exchange_protection_enabled and config.execution_exchange.lower() == "binance":
            position, protection_error = self._place_exchange_protection(position, config)
        response_payload = {
            **response_payload,
            "fees_quote": position.entry_fee_quote,
            "position_client_order_id": position.position_id,
            "protection_error": protection_error,
        }
        return position, TradingEvent(
            action="BUY",
            symbol=signal.symbol,
            mode=config.mode,
            status=execution_status,
            message=(
                f"{config.execution_exchange.upper()} 市价买入已确认成交。"
                + (f" 交易所保护单未建立：{protection_error}" if protection_error else "")
            ),
            score=signal.score,
            price=price,
            quantity=position.quantity,
            quote_notional=position.quote_notional,
            response=response_payload,
            exchange=config.execution_exchange.upper(),
            fees_quote=position.entry_fee_quote,
            position_id=position.position_id,
            client_order_id=client_order_id,
            exchange_order_id=position.entry_order_id,
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

    def _risk_sized_margin_notional(
        self,
        *,
        config: AutoTradeDefaults,
        entry_price: float,
        stop_price: float,
    ) -> float:
        if not config.risk_sizing_enabled or entry_price <= 0 or stop_price >= entry_price:
            return config.quote_order_qty
        equity = self._account_equity(config)
        stop_distance_ratio = (entry_price - stop_price) / entry_price
        if equity <= 0 or stop_distance_ratio <= 0:
            return config.quote_order_qty
        risk_budget = equity * config.risk_per_trade_pct / 100
        risk_sized_notional = risk_budget / stop_distance_ratio
        return max(0.01, min(config.quote_order_qty, risk_sized_notional))

    def _account_equity(self, config: AutoTradeDefaults) -> float:
        events = self.state_store.load_events()
        realized = sum(
            float(event.realized_pnl or 0.0)
            for event in events
            if event.mode == config.mode
            and event.action == "SELL"
            and event.status in FILLED_TRADE_STATUSES
        )
        if config.mode == "paper":
            return max(0.0, config.paper_account_equity + realized)
        account_status = getattr(self.execution_gateway, "account_status", None)
        if callable(account_status):
            try:
                status = account_status()
                quote_available = float(status.get("quote_available") or 0.0)
                open_exposure = sum(
                    self._position_margin_notional(position)
                    for position in self.state_store.load()
                    if position.mode == "live"
                )
                if quote_available + open_exposure > 0:
                    return quote_available + open_exposure
            except Exception:  # noqa: BLE001
                pass
        return max(config.max_total_quote_exposure, config.quote_order_qty)

    def _portfolio_risk_block_reason(
        self,
        config: AutoTradeDefaults,
        events: list[TradingEvent],
    ) -> str:
        closed = [
            event
            for event in events
            if event.mode == config.mode
            and event.action == "SELL"
            and event.status in FILLED_TRADE_STATUSES
            and event.realized_pnl is not None
        ]
        if not closed:
            return ""
        closed.sort(key=lambda event: event.created_at)
        today = now_app_time().date()
        daily_pnl = sum(float(event.realized_pnl or 0.0) for event in closed if event.created_at.date() == today)
        equity = max(self._account_equity(config), config.quote_order_qty)
        if config.max_daily_loss_pct > 0 and daily_pnl <= -(equity * config.max_daily_loss_pct / 100):
            return (
                f"当日净亏损 {daily_pnl:.4f} 已达到净值风险上限 "
                f"{config.max_daily_loss_pct:.2f}%，本日暂停新增仓位。"
            )
        consecutive_losses = 0
        for event in reversed([event for event in closed if event.created_at.date() == today]):
            if float(event.realized_pnl or 0.0) < 0:
                consecutive_losses += 1
            else:
                break
        if config.max_consecutive_losses > 0 and consecutive_losses >= config.max_consecutive_losses:
            return f"已连续亏损 {consecutive_losses} 笔，达到风控上限，暂停新增仓位。"
        if config.max_account_drawdown_pct > 0:
            starting_equity = config.paper_account_equity if config.mode == "paper" else max(equity, config.max_total_quote_exposure)
            curve = starting_equity
            peak = starting_equity
            max_drawdown_pct = 0.0
            for event in closed:
                curve += float(event.realized_pnl or 0.0)
                peak = max(peak, curve)
                if peak > 0:
                    max_drawdown_pct = max(max_drawdown_pct, (peak - curve) / peak * 100)
            if max_drawdown_pct >= config.max_account_drawdown_pct:
                return (
                    f"账户已实现资金曲线最大回撤 {max_drawdown_pct:.2f}% 达到 "
                    f"{config.max_account_drawdown_pct:.2f}% 上限，暂停新增仓位。"
                )
        return ""

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
            execution_price = price
            exit_fee_quote = 0.0
            if config.paper_costs_enabled:
                execution_price = price * (1 - config.paper_slippage_bps / 10_000)
                exit_fee_quote = position.quantity * execution_price * config.paper_fee_bps / 10_000
            exit_notional, gross_pnl, realized_pnl, realized_pnl_pct = self._calculate_exit_pnl(
                position=position,
                exit_price=execution_price,
                executed_quantity=position.quantity,
                exit_fee_quote=exit_fee_quote,
            )
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="paper_filled",
                message=f"模拟卖出已记录：{exit_reason}。",
                price=execution_price,
                quantity=position.quantity,
                quote_notional=exit_notional,
                gross_pnl=gross_pnl,
                fees_quote=position.entry_fee_quote + exit_fee_quote,
                realized_pnl=realized_pnl,
                realized_pnl_pct=realized_pnl_pct,
                exit_reason=exit_reason,
                exchange=position.exchange,
                position_id=position.position_id or position.client_order_id,
                client_order_id=self._client_order_id("paper-sell", position.symbol, now_app_time()),
                response={
                    "market_price": price,
                    "execution_price": execution_price,
                    "slippage_bps": config.paper_slippage_bps if config.paper_costs_enabled else 0.0,
                    "fees_quote": position.entry_fee_quote + exit_fee_quote,
                    "position_client_order_id": position.position_id or position.client_order_id,
                },
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
        pending_response = self._pending_exit_response(position)
        if position.pending_exit_client_order_id and pending_response is None:
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=config.mode,
                status="status_unknown",
                message="已有卖出订单尚未完成交易所对账，避免重复提交。",
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
                exit_reason=exit_reason,
                exchange=position.exchange,
                position_id=position.position_id,
                client_order_id=position.pending_exit_client_order_id,
                exchange_order_id=position.pending_exit_order_id,
            )
        if pending_response is not None:
            pending_status = self._order_execution_status(pending_response)
            if pending_status in INFLIGHT_TRADE_STATUSES:
                return TradingEvent(
                    action="SELL",
                    symbol=position.symbol,
                    mode=config.mode,
                    status=pending_status,
                    message="已有卖出订单尚未确认，等待交易所对账，不重复提交。",
                    price=price,
                    quantity=position.quantity,
                    quote_notional=position.quantity * price,
                    exit_reason=exit_reason,
                    response={**pending_response, "position_client_order_id": position.position_id},
                    exchange=position.exchange,
                    position_id=position.position_id,
                    client_order_id=position.pending_exit_client_order_id,
                    exchange_order_id=position.pending_exit_order_id,
                )
            if pending_status in FILLED_TRADE_STATUSES:
                return self._live_exit_event_from_response(position, price, exit_reason, pending_response)
            position.pending_exit_order_id = ""
            position.pending_exit_client_order_id = ""
        protection_canceled, protection_error = self._cancel_exchange_protection(position)
        if not protection_canceled:
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=config.mode,
                status="protection_cancel_pending",
                message=f"交易所保护单尚未确认撤销，避免重复卖出：{protection_error}",
                price=price,
                quantity=position.quantity,
                quote_notional=position.quantity * price,
                exit_reason=exit_reason,
                exchange=position.exchange,
                position_id=position.position_id,
            )
        reconciled_quantity = self._reconciled_live_sell_quantity(position, price)
        if isinstance(reconciled_quantity, TradingEvent):
            reconciled_quantity.exit_reason = exit_reason
            return reconciled_quantity
        sell_quantity = reconciled_quantity or self._floor_quantity_for_symbol(position.symbol, position.quantity)
        exit_client_order_id = self._client_order_id("sell", position.symbol, now_app_time())
        try:
            response = self.execution_gateway.order_market_sell(
                symbol=position.symbol,
                quantity=sell_quantity,
                test=config.order_test_only,
                client_order_id=exit_client_order_id,
            )
        except BinanceOrderStatusUnknown as exc:
            response = self._query_order_by_client_id(position.symbol, exit_client_order_id)
            if response is None:
                position.pending_exit_client_order_id = exit_client_order_id
                return TradingEvent(
                    action="SELL",
                    symbol=position.symbol,
                    mode=config.mode,
                    status="status_unknown",
                    message=str(exc),
                    price=price,
                    quantity=sell_quantity,
                    quote_notional=sell_quantity * price,
                    exit_reason=exit_reason,
                    exchange=position.exchange,
                    position_id=position.position_id,
                    client_order_id=exit_client_order_id,
                )
        except Exception as exc:  # noqa: BLE001
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=config.mode,
                status="rejected",
                message=str(exc),
                price=price,
                quantity=sell_quantity,
                quote_notional=sell_quantity * price,
                exit_reason=exit_reason,
                exchange=position.exchange,
                position_id=position.position_id,
                client_order_id=exit_client_order_id,
            )
        response_payload = response if isinstance(response, dict) else {"raw": response}
        if config.order_test_only:
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=config.mode,
                status="test_accepted",
                message=f"{position.exchange.upper()} 市价卖出测试请求已接受：{exit_reason}。",
                price=price,
                quantity=sell_quantity,
                quote_notional=sell_quantity * price,
                exit_reason=exit_reason,
                response=response_payload,
                exchange=position.exchange,
                position_id=position.position_id,
                client_order_id=exit_client_order_id,
                exchange_order_id=str(response_payload.get("orderId") or ""),
            )
        execution_status = self._order_execution_status(response_payload)
        if execution_status in INFLIGHT_TRADE_STATUSES:
            position.pending_exit_order_id = str(response_payload.get("orderId") or "")
            position.pending_exit_client_order_id = exit_client_order_id
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=config.mode,
                status=execution_status,
                message=f"{position.exchange.upper()} 卖出订单尚未确认成交，等待对账。",
                price=price,
                quantity=sell_quantity,
                quote_notional=sell_quantity * price,
                exit_reason=exit_reason,
                response={**response_payload, "position_client_order_id": position.position_id},
                exchange=position.exchange,
                position_id=position.position_id,
                client_order_id=exit_client_order_id,
                exchange_order_id=position.pending_exit_order_id,
            )
        return self._live_exit_event_from_response(
            position,
            price,
            exit_reason,
            response_payload,
            client_order_id=exit_client_order_id,
            status=execution_status,
        )

    def _pending_exit_response(self, position: TradingPosition) -> dict[str, object] | None:
        if not position.pending_exit_client_order_id:
            return None
        return self._query_order_by_client_id(position.symbol, position.pending_exit_client_order_id)

    def _live_exit_event_from_response(
        self,
        position: TradingPosition,
        price: float,
        exit_reason: str,
        response: dict[str, object],
        *,
        client_order_id: str = "",
        status: str = "filled",
    ) -> TradingEvent:
        executed_quantity = float(response.get("executedQty") or position.quantity)
        exit_notional = float(response.get("cummulativeQuoteQty") or executed_quantity * price)
        execution_price = exit_notional / executed_quantity if executed_quantity > 0 else price
        exit_fee_quote, _, unconverted_fees = self._commission_summary(response, position.symbol)
        _, gross_pnl, realized_pnl, realized_pnl_pct = self._calculate_exit_pnl(
            position=position,
            exit_price=execution_price,
            executed_quantity=executed_quantity,
            exit_notional=exit_notional,
            exit_fee_quote=exit_fee_quote,
        )
        response_payload = {
            **response,
            "fees_quote": position.entry_fee_quote + exit_fee_quote,
            "unconverted_fees": unconverted_fees,
            "position_client_order_id": position.position_id,
        }
        return TradingEvent(
            action="SELL",
            symbol=position.symbol,
            mode=position.mode,
            status=status,
            message=f"{position.exchange.upper()} 市价卖出已确认：{exit_reason}。",
            price=execution_price,
            quantity=executed_quantity,
            quote_notional=exit_notional,
            gross_pnl=gross_pnl,
            fees_quote=position.entry_fee_quote + exit_fee_quote,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            exit_reason=exit_reason,
            response=response_payload,
            exchange=position.exchange,
            position_id=position.position_id,
            client_order_id=client_order_id or str(response.get("clientOrderId") or ""),
            exchange_order_id=str(response.get("orderId") or ""),
        )

    def _reconciled_live_sell_quantity(
        self,
        position: TradingPosition,
        price: float,
    ) -> float | TradingEvent | None:
        asset_balance = getattr(self.execution_gateway, "asset_balance", None)
        if not callable(asset_balance):
            return None
        base_asset, step_size, min_quantity, min_notional, _ = self._symbol_trade_rules(position.symbol)
        try:
            balance = asset_balance(base_asset)
            free_balance = max(0.0, float(balance.get("free") or 0.0))
            locked_balance = max(0.0, float(balance.get("locked") or 0.0))
        except Exception:  # noqa: BLE001
            return None

        sell_quantity = self._floor_quantity(min(position.quantity, free_balance), step_size)
        quantity_too_small = sell_quantity <= 0 or (min_quantity > 0 and sell_quantity < min_quantity)
        notional_too_small = min_notional > 0 and sell_quantity * price < min_notional
        if not quantity_too_small and not notional_too_small:
            return sell_quantity

        locked_quantity = self._floor_quantity(min(position.quantity, locked_balance), step_size)
        locked_is_material = locked_quantity > 0 and (
            (min_quantity <= 0 or locked_quantity >= min_quantity)
            and (min_notional <= 0 or locked_quantity * price >= min_notional)
        )
        if locked_is_material:
            return TradingEvent(
                action="SELL",
                symbol=position.symbol,
                mode=position.mode,
                status="balance_locked",
                message=f"{base_asset} 余额当前被其他订单占用，暂不重复提交卖出。",
                price=price,
                quantity=locked_quantity,
                quote_notional=locked_quantity * price,
                exchange=position.exchange,
                response={"free_balance": free_balance, "locked_balance": locked_balance},
            )
        return TradingEvent(
            action="SYNC",
            symbol=position.symbol,
            mode=position.mode,
            status=EXTERNAL_POSITION_CLOSED_STATUS,
            message=(
                f"交易所可用 {base_asset} 余额 {free_balance:.8g} 已低于最小可交易量，"
                "判定仓位已在系统外卖出、划转或转换，本地仓位已完成对账。"
            ),
            price=price,
            quantity=free_balance,
            quote_notional=free_balance * price,
            exchange=position.exchange,
            response={
                "local_quantity": position.quantity,
                "free_balance": free_balance,
                "locked_balance": locked_balance,
                "min_quantity": min_quantity,
                "min_notional": min_notional,
            },
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
        if config.paper_account_equity <= 0:
            raise ValueError("模拟账户初始净值必须大于 0。")
        if config.max_daily_loss_pct < 0 or config.max_account_drawdown_pct < 0:
            raise ValueError("账户亏损和回撤上限不能小于 0。")
        if config.max_consecutive_losses < 0:
            raise ValueError("最大连续亏损笔数不能小于 0。")
        if config.paper_fee_bps < 0 or config.paper_slippage_bps < 0:
            raise ValueError("模拟手续费和滑点不能小于 0。")
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
        if config.emergency_alert_global_cooldown_minutes < 0 or config.emergency_alert_symbol_cooldown_minutes < 0:
            raise ValueError("急跌预警冷却时间不能小于 0。")
        if config.emergency_low_liquidity_quote_volume < 0:
            raise ValueError("低流动性急跌预警成交额阈值不能小于 0。")
        if config.emergency_low_liquidity_drawdown_multiplier < 1:
            raise ValueError("低流动性急跌预警回撤倍数不能小于 1。")
        if config.emergency_low_liquidity_min_score < 0 or config.emergency_low_liquidity_min_score > 100:
            raise ValueError("低流动性急跌预警信号分必须在 0 到 100 之间。")
        if config.profit_protection_enabled and config.profit_protection_lock_pct > config.profit_protection_trigger_pct:
            raise ValueError("浮盈保护锁盈比例不能大于触发比例。")

    @staticmethod
    def _live_confirmed() -> bool:
        return os.getenv("AI_TRADE_LIVE_CONFIRM", "") == LIVE_CONFIRM_VALUE

    @staticmethod
    def _client_order_id(side: str, symbol: str, now: datetime) -> str:
        suffix = int(now.timestamp() * 1000)
        return f"aitrade-{side[:7]}-{symbol.lower()[:10]}-{suffix}"[:36]

    def _query_order_by_client_id(self, symbol: str, client_order_id: str) -> dict[str, object] | None:
        query_order = getattr(self.execution_gateway, "query_order", None)
        if not callable(query_order) or not client_order_id:
            return None
        try:
            response = query_order(symbol=symbol, client_order_id=client_order_id)
        except Exception:  # noqa: BLE001
            return None
        return response if isinstance(response, dict) else None

    def _settle_entry_response(
        self,
        symbol: str,
        client_order_id: str,
        response: dict[str, object],
    ) -> tuple[dict[str, object], str]:
        """Cancel a still-open partial buy before turning its executed quantity into a position."""
        if str(response.get("status") or "").upper() != "PARTIALLY_FILLED":
            return response, self._order_execution_status(response)
        cancel = getattr(self.execution_gateway, "cancel_order", None)
        if not callable(cancel):
            return response, "order_pending"
        try:
            canceled = cancel(
                symbol=symbol,
                order_id=response.get("orderId"),
                client_order_id=None if response.get("orderId") is not None else client_order_id,
            )
        except Exception:  # noqa: BLE001
            return response, "order_pending"
        reconciled = self._query_order_by_client_id(symbol, client_order_id)
        terminal = reconciled if reconciled is not None else canceled
        terminal_payload = terminal if isinstance(terminal, dict) else response
        terminal_status = str(terminal_payload.get("status") or "").upper()
        if terminal_status not in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED", "FILLED"}:
            return terminal_payload, "order_pending"
        return terminal_payload, self._order_execution_status(terminal_payload)

    @staticmethod
    def _order_execution_status(response: dict[str, object]) -> str:
        status = str(response.get("status") or "").upper()
        executed_quantity = float(response.get("executedQty") or 0.0)
        if status == "FILLED":
            return "filled"
        if not status and response.get("orderId") is not None:
            return "filled"
        if executed_quantity > 0:
            return "partially_filled"
        if status in {"REJECTED", "EXPIRED", "EXPIRED_IN_MATCH", "CANCELED"}:
            return "rejected"
        if status in {"NEW", "PENDING_NEW", "PARTIALLY_FILLED"}:
            return "order_pending"
        # FULL market responses always include status. This fallback preserves compatibility with
        # gateways that only return an order id while still refusing an empty response.
        return "order_pending"

    def _place_exchange_protection(
        self,
        position: TradingPosition,
        config: AutoTradeDefaults,
    ) -> tuple[TradingPosition, str]:
        submit = getattr(self.execution_gateway, "order_stop_loss_sell", None)
        if not callable(submit):
            return position, "当前执行网关不支持交易所止损单"
        _, step_size, min_quantity, min_notional, tick_size = self._symbol_trade_rules(position.symbol)
        quantity = self._floor_quantity(position.quantity, step_size)
        stop_price = self._floor_quantity(position.stop_price, tick_size)
        if quantity <= 0 or (min_quantity > 0 and quantity < min_quantity):
            return position, "保护单数量低于交易所最小数量"
        if min_notional > 0 and quantity * stop_price < min_notional:
            return position, "保护单名义金额低于交易所最小金额"
        client_order_id = self._client_order_id("protect", position.symbol, now_app_time())
        try:
            response = submit(
                symbol=position.symbol,
                quantity=quantity,
                stop_price=stop_price,
                test=config.order_test_only,
                client_order_id=client_order_id,
            )
        except BinanceOrderStatusUnknown:
            response = self._query_order_by_client_id(position.symbol, client_order_id)
            if response is None:
                return position, "保护单提交结果未知，查询订单也失败"
        except Exception as exc:  # noqa: BLE001
            return position, str(exc)
        response_payload = response if isinstance(response, dict) else {}
        position.protection_order_id = str(response_payload.get("orderId") or "")
        position.protection_client_order_id = str(response_payload.get("clientOrderId") or client_order_id)
        position.protection_stop_price = stop_price
        position.protection_status = str(response_payload.get("status") or "NEW").upper()
        return position, ""

    def _cancel_exchange_protection(self, position: TradingPosition) -> tuple[bool, str]:
        if not position.protection_order_id and not position.protection_client_order_id:
            return True, ""
        cancel = getattr(self.execution_gateway, "cancel_order", None)
        if not callable(cancel):
            return False, "当前执行网关不支持撤销保护单"
        try:
            cancel(
                symbol=position.symbol,
                order_id=position.protection_order_id or None,
                client_order_id=None if position.protection_order_id else position.protection_client_order_id,
            )
        except BinanceOrderStatusUnknown:
            response = self._query_order_by_client_id(position.symbol, position.protection_client_order_id)
            status = str((response or {}).get("status") or "").upper()
            if status not in {"CANCELED", "EXPIRED", "REJECTED"}:
                return False, f"保护单撤销结果未知，当前状态 {status or 'UNKNOWN'}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        position.protection_order_id = ""
        position.protection_client_order_id = ""
        position.protection_stop_price = None
        position.protection_status = "CANCELED"
        return True, ""

    def _exchange_protection_fill_event(
        self,
        position: TradingPosition,
        price: float,
    ) -> TradingEvent | None:
        if position.mode != "live" or not position.protection_client_order_id:
            return None
        response = self._query_order_by_client_id(position.symbol, position.protection_client_order_id)
        if response is None:
            return None
        status = str(response.get("status") or "").upper()
        position.protection_status = status
        if status not in {"PARTIALLY_FILLED", "FILLED"}:
            return None
        cumulative_quantity = float(response.get("executedQty") or 0.0)
        executed_quantity = max(0.0, cumulative_quantity - position.protection_executed_quantity)
        if executed_quantity <= 0:
            return None
        cumulative_quote = float(response.get("cummulativeQuoteQty") or 0.0)
        execution_quote = (
            cumulative_quote * executed_quantity / cumulative_quantity
            if cumulative_quantity > 0 and cumulative_quote > 0
            else executed_quantity * price
        )
        position.protection_executed_quantity = cumulative_quantity
        response = {
            **response,
            "executedQty": str(executed_quantity),
            "cummulativeQuoteQty": str(execution_quote),
        }
        return self._live_exit_event_from_response(
            position,
            price,
            "exchange_stop_loss",
            response,
            client_order_id=position.protection_client_order_id,
            status="reconciled_filled" if status == "FILLED" else "partially_filled",
        )

    def _refresh_exchange_protection(self, position: TradingPosition, config: AutoTradeDefaults) -> str:
        if (
            position.mode != "live"
            or config.order_test_only
            or not config.exchange_protection_enabled
            or config.execution_exchange.lower() != "binance"
        ):
            return ""
        if position.protection_client_order_id:
            response = self._query_order_by_client_id(position.symbol, position.protection_client_order_id)
            if response is None:
                return "无法查询现有保护单状态"
            status = str(response.get("status") or "").upper()
            position.protection_status = status
            if status == "FILLED":
                return ""
            _, _, _, _, tick_size = self._symbol_trade_rules(position.symbol)
            desired_stop = self._floor_quantity(position.stop_price, tick_size)
            current_stop = position.protection_stop_price or float(response.get("stopPrice") or 0.0)
            if status in {"NEW", "PARTIALLY_FILLED", "PENDING_NEW"} and math.isclose(
                desired_stop,
                current_stop,
                rel_tol=0.0,
                abs_tol=max(float(tick_size), 1e-12),
            ):
                return ""
            if status in {"NEW", "PARTIALLY_FILLED", "PENDING_NEW"}:
                canceled, error = self._cancel_exchange_protection(position)
                if not canceled:
                    return error
            else:
                position.protection_order_id = ""
                position.protection_client_order_id = ""
                position.protection_stop_price = None
        _, error = self._place_exchange_protection(position, config)
        return error

    @staticmethod
    def _remaining_position_after_partial_exit(
        position: TradingPosition,
        executed_quantity: float,
    ) -> TradingPosition:
        original_quantity = position.quantity
        remaining_quantity = max(0.0, original_quantity - executed_quantity)
        remaining_ratio = remaining_quantity / original_quantity if original_quantity > 0 else 0.0
        original_margin = position.margin_notional
        position.quantity = remaining_quantity
        position.quote_notional *= remaining_ratio
        position.margin_notional = original_margin * remaining_ratio if original_margin is not None else position.quote_notional
        position.entry_fee_quote *= remaining_ratio
        position.pending_exit_order_id = ""
        position.pending_exit_client_order_id = ""
        return position

    def _floor_quantity_for_symbol(self, symbol: str, quantity: float) -> float:
        _, step_size, _, _, _ = self._symbol_trade_rules(symbol)
        return self._floor_quantity(quantity, step_size)

    def _symbol_trade_rules(self, symbol: str) -> tuple[str, str, float, float, str]:
        normalized = symbol.upper().strip()
        base_asset = self._base_asset_from_symbol(normalized)
        step_size = "0.00000001"
        min_quantity = 0.0
        min_notional = 0.0
        tick_size = "0.00000001"
        try:
            exchange_info = self.execution_gateway.exchange_info()
            for item in exchange_info.get("symbols", []):
                if item.get("symbol") != normalized:
                    continue
                base_asset = str(item.get("baseAsset") or base_asset).upper()
                for filter_item in item.get("filters", []):
                    if filter_item.get("filterType") == "LOT_SIZE":
                        step_size = str(filter_item.get("stepSize") or step_size)
                        min_quantity = float(filter_item.get("minQty") or 0.0)
                    elif filter_item.get("filterType") in {"MIN_NOTIONAL", "NOTIONAL"}:
                        min_notional = float(filter_item.get("minNotional") or 0.0)
                    elif filter_item.get("filterType") == "PRICE_FILTER":
                        tick_size = str(filter_item.get("tickSize") or tick_size)
                break
        except Exception:  # noqa: BLE001
            pass
        return base_asset, step_size, min_quantity, min_notional, tick_size

    @staticmethod
    def _base_asset_from_symbol(symbol: str) -> str:
        for quote_asset in ("FDUSD", "USDT", "USDC", "BUSD", "BTC", "ETH"):
            if symbol.endswith(quote_asset) and len(symbol) > len(quote_asset):
                return symbol[: -len(quote_asset)]
        return symbol

    @staticmethod
    def _quote_asset_from_symbol(symbol: str) -> str:
        for quote_asset in ("FDUSD", "USDT", "USDC", "BUSD", "BTC", "ETH"):
            if symbol.endswith(quote_asset) and len(symbol) > len(quote_asset):
                return quote_asset
        return ""

    @classmethod
    def _commission_summary(
        cls,
        response: dict[str, object],
        symbol: str,
    ) -> tuple[float, float, list[dict[str, object]]]:
        base_asset = cls._base_asset_from_symbol(symbol)
        quote_asset = cls._quote_asset_from_symbol(symbol)
        base_commission = 0.0
        fee_quote = 0.0
        unconverted: list[dict[str, object]] = []
        fills = response.get("fills") if isinstance(response.get("fills"), list) else []
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            commission = float(fill.get("commission") or 0.0)
            asset = str(fill.get("commissionAsset") or "").upper()
            price = float(fill.get("price") or 0.0)
            if asset == base_asset:
                base_commission += commission
                fee_quote += commission * price
            elif asset == quote_asset:
                fee_quote += commission
            elif commission > 0:
                unconverted.append({"asset": asset, "commission": commission})
        return fee_quote, base_commission, unconverted

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
        exit_fee_quote: float = 0.0,
    ) -> tuple[float, float, float, float]:
        quantity = max(0.0, executed_quantity)
        if exit_notional is None:
            exit_notional = quantity * exit_price
        entry_notional = position.quote_notional
        if position.quantity > 0 and quantity != position.quantity:
            entry_notional = position.quote_notional * (quantity / position.quantity)
        margin_notional = position.margin_notional or entry_notional
        if position.quantity > 0 and quantity != position.quantity:
            margin_notional = margin_notional * (quantity / position.quantity)
        entry_fee_quote = position.entry_fee_quote
        if position.quantity > 0 and quantity != position.quantity:
            entry_fee_quote *= quantity / position.quantity
        gross_pnl = exit_notional - entry_notional
        realized_pnl = gross_pnl - entry_fee_quote - exit_fee_quote
        realized_pnl_pct = (realized_pnl / margin_notional) * 100 if margin_notional else 0.0
        return exit_notional, gross_pnl, realized_pnl, realized_pnl_pct

    def _position_from_order_response(
        self,
        *,
        position: TradingPosition,
        response: dict[str, object],
        fallback_price: float,
    ) -> TradingPosition:
        executed_qty = float(response.get("executedQty") or position.quantity)
        quote_notional = float(response.get("cummulativeQuoteQty") or position.quote_notional)
        entry_fee_quote, base_commission, _ = self._commission_summary(response, position.symbol)
        sellable_quantity = max(0.0, executed_qty - base_commission)
        entry_price = quote_notional / executed_qty if executed_qty > 0 else fallback_price
        return TradingPosition(
            symbol=position.symbol,
            quantity=sellable_quantity,
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
            position_id=position.position_id or position.client_order_id,
            entry_order_id=str(response.get("orderId") or ""),
            entry_fee_quote=entry_fee_quote,
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
