from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Iterable

from .runtime_config import CarryPaperDefaults
from .time_utils import APP_TIMEZONE, now_app_time, to_app_time


@dataclass(frozen=True)
class CarryMarketSnapshot:
    symbol: str
    spot_exchange: str
    futures_exchange: str
    spot_price: float
    futures_price: float
    basis_bps: float
    funding_rate_bps: float
    observed_at: datetime


@dataclass(frozen=True)
class CarryPaperPosition:
    position_id: str
    symbol: str
    spot_exchange: str
    futures_exchange: str
    spot_quantity: float
    futures_quantity: float
    notional_per_leg: float
    entry_spot_price: float
    entry_futures_price: float
    entry_basis_bps: float
    entry_funding_rate_bps: float
    opened_at: datetime
    last_mark_at: datetime
    last_spot_price: float
    last_futures_price: float
    last_basis_bps: float
    last_funding_rate_bps: float
    accrued_funding: float = 0.0
    entry_cost: float = 0.0


@dataclass(frozen=True)
class CarryPaperEvent:
    action: str
    symbol: str
    status: str
    message: str
    created_at: datetime
    position_id: str
    spot_price: float
    futures_price: float
    basis_bps: float
    funding_rate_bps: float
    gross_market_pnl: float = 0.0
    funding_pnl: float = 0.0
    costs: float = 0.0
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    exit_reason: str = ""


@dataclass(frozen=True)
class CarryPaperRunReport:
    enabled: bool
    mode: str
    research_only: bool
    generated_at: datetime
    snapshot_count: int
    opened_count: int
    closed_count: int
    positions: list[CarryPaperPosition]
    events: list[CarryPaperEvent]
    metrics: dict[str, float | int]


def _float_value(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: object, default: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            parsed = default or now_app_time()
    else:
        parsed = default or now_app_time()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return to_app_time(parsed)


def build_carry_market_snapshots(
    spreads: Iterable[dict[str, object]],
    funding_rates: Iterable[dict[str, object]],
    *,
    observed_at: datetime | None = None,
) -> list[CarryMarketSnapshot]:
    timestamp = _parse_datetime(observed_at or now_app_time())
    funding_by_symbol = {
        str(row.get("symbol") or "").strip().upper(): row
        for row in funding_rates
        if str(row.get("symbol") or "").strip()
    }
    snapshots: list[CarryMarketSnapshot] = []
    for spread in spreads:
        symbol = str(spread.get("symbol") or "").strip().upper()
        funding = funding_by_symbol.get(symbol)
        if not symbol or funding is None:
            continue
        spot_price = _float_value(spread.get("spot_price"))
        futures_price = _float_value(spread.get("futures_price"), _float_value(funding.get("mark_price")))
        if spot_price <= 0 or futures_price <= 0:
            continue
        basis_bps = _float_value(
            spread.get("spread_bps"),
            ((futures_price - spot_price) / spot_price) * 10_000,
        )
        snapshots.append(
            CarryMarketSnapshot(
                symbol=symbol,
                spot_exchange=str(spread.get("spot_exchange") or "BINANCE").upper(),
                futures_exchange=str(
                    spread.get("futures_exchange")
                    or funding.get("futures_exchange")
                    or "BINANCE-PERP"
                ).upper(),
                spot_price=spot_price,
                futures_price=futures_price,
                basis_bps=basis_bps,
                funding_rate_bps=_float_value(funding.get("funding_rate_bps")),
                observed_at=timestamp,
            )
        )
    return sorted(
        snapshots,
        key=lambda item: (item.basis_bps, item.funding_rate_bps),
        reverse=True,
    )


def carry_position_from_payload(payload: dict[str, object]) -> CarryPaperPosition:
    opened_at = _parse_datetime(payload.get("opened_at"))
    return CarryPaperPosition(
        position_id=str(payload.get("position_id") or ""),
        symbol=str(payload.get("symbol") or "").upper(),
        spot_exchange=str(payload.get("spot_exchange") or "BINANCE").upper(),
        futures_exchange=str(payload.get("futures_exchange") or "BINANCE-PERP").upper(),
        spot_quantity=_float_value(payload.get("spot_quantity")),
        futures_quantity=_float_value(payload.get("futures_quantity")),
        notional_per_leg=_float_value(payload.get("notional_per_leg")),
        entry_spot_price=_float_value(payload.get("entry_spot_price")),
        entry_futures_price=_float_value(payload.get("entry_futures_price")),
        entry_basis_bps=_float_value(payload.get("entry_basis_bps")),
        entry_funding_rate_bps=_float_value(payload.get("entry_funding_rate_bps")),
        opened_at=opened_at,
        last_mark_at=_parse_datetime(payload.get("last_mark_at"), opened_at),
        last_spot_price=_float_value(payload.get("last_spot_price")),
        last_futures_price=_float_value(payload.get("last_futures_price")),
        last_basis_bps=_float_value(payload.get("last_basis_bps")),
        last_funding_rate_bps=_float_value(payload.get("last_funding_rate_bps")),
        accrued_funding=_float_value(payload.get("accrued_funding")),
        entry_cost=_float_value(payload.get("entry_cost")),
    )


def _execution_cost(notional: float, config: CarryPaperDefaults) -> float:
    return max(0.0, notional) * (config.fee_bps_per_leg + config.slippage_bps_per_leg) / 10_000


def _mark_position(
    position: CarryPaperPosition,
    snapshot: CarryMarketSnapshot,
    config: CarryPaperDefaults,
) -> tuple[CarryPaperPosition, dict[str, float]]:
    elapsed_hours = max(0.0, (snapshot.observed_at - position.last_mark_at).total_seconds() / 3600)
    futures_notional = position.futures_quantity * snapshot.futures_price
    funding_increment = futures_notional * (snapshot.funding_rate_bps / 10_000) * (elapsed_hours / 8)
    accrued_funding = position.accrued_funding + funding_increment
    spot_pnl = position.spot_quantity * (snapshot.spot_price - position.entry_spot_price)
    futures_pnl = position.futures_quantity * (position.entry_futures_price - snapshot.futures_price)
    gross_market_pnl = spot_pnl + futures_pnl
    exit_notional = position.spot_quantity * snapshot.spot_price + futures_notional
    exit_cost = _execution_cost(exit_notional, config)
    net_pnl = gross_market_pnl + accrued_funding - position.entry_cost - exit_cost
    marked = replace(
        position,
        last_mark_at=snapshot.observed_at,
        last_spot_price=snapshot.spot_price,
        last_futures_price=snapshot.futures_price,
        last_basis_bps=snapshot.basis_bps,
        last_funding_rate_bps=snapshot.funding_rate_bps,
        accrued_funding=accrued_funding,
    )
    return marked, {
        "spot_pnl": spot_pnl,
        "futures_pnl": futures_pnl,
        "gross_market_pnl": gross_market_pnl,
        "funding_pnl": accrued_funding,
        "entry_cost": position.entry_cost,
        "exit_cost": exit_cost,
        "costs": position.entry_cost + exit_cost,
        "net_pnl": net_pnl,
    }


def _exit_reason(
    position: CarryPaperPosition,
    snapshot: CarryMarketSnapshot,
    config: CarryPaperDefaults,
) -> str:
    held_hours = max(0.0, (snapshot.observed_at - position.opened_at).total_seconds() / 3600)
    if snapshot.basis_bps >= position.entry_basis_bps + config.stop_basis_bps:
        return "basis_stop"
    if held_hours >= config.max_holding_hours:
        return "max_holding"
    if snapshot.funding_rate_bps <= config.exit_funding_bps:
        return "funding_reversal"
    if snapshot.basis_bps <= config.exit_basis_bps:
        return "basis_converged"
    return ""


def _open_position(
    snapshot: CarryMarketSnapshot,
    config: CarryPaperDefaults,
) -> tuple[CarryPaperPosition, CarryPaperEvent]:
    timestamp = snapshot.observed_at
    identifier = f"carry-paper-{snapshot.symbol.lower()}-{int(timestamp.timestamp() * 1000)}"
    spot_quantity = config.notional_per_leg / snapshot.spot_price
    futures_quantity = config.notional_per_leg / snapshot.futures_price
    entry_cost = _execution_cost(config.notional_per_leg * 2, config)
    position = CarryPaperPosition(
        position_id=identifier,
        symbol=snapshot.symbol,
        spot_exchange=snapshot.spot_exchange,
        futures_exchange=snapshot.futures_exchange,
        spot_quantity=spot_quantity,
        futures_quantity=futures_quantity,
        notional_per_leg=config.notional_per_leg,
        entry_spot_price=snapshot.spot_price,
        entry_futures_price=snapshot.futures_price,
        entry_basis_bps=snapshot.basis_bps,
        entry_funding_rate_bps=snapshot.funding_rate_bps,
        opened_at=timestamp,
        last_mark_at=timestamp,
        last_spot_price=snapshot.spot_price,
        last_futures_price=snapshot.futures_price,
        last_basis_bps=snapshot.basis_bps,
        last_funding_rate_bps=snapshot.funding_rate_bps,
        entry_cost=entry_cost,
    )
    event = CarryPaperEvent(
        action="OPEN",
        symbol=snapshot.symbol,
        status="paper_opened",
        message="Opened paper cash-and-carry: long spot and short perpetual.",
        created_at=timestamp,
        position_id=identifier,
        spot_price=snapshot.spot_price,
        futures_price=snapshot.futures_price,
        basis_bps=snapshot.basis_bps,
        funding_rate_bps=snapshot.funding_rate_bps,
        costs=entry_cost,
    )
    return position, event


def _close_event(
    position: CarryPaperPosition,
    snapshot: CarryMarketSnapshot,
    mark: dict[str, float],
    reason: str,
) -> CarryPaperEvent:
    gross_capital = position.notional_per_leg * 2
    realized_pnl = mark["net_pnl"]
    return CarryPaperEvent(
        action="CLOSE",
        symbol=position.symbol,
        status="paper_closed",
        message=f"Closed paper cash-and-carry: {reason}.",
        created_at=snapshot.observed_at,
        position_id=position.position_id,
        spot_price=snapshot.spot_price,
        futures_price=snapshot.futures_price,
        basis_bps=snapshot.basis_bps,
        funding_rate_bps=snapshot.funding_rate_bps,
        gross_market_pnl=mark["gross_market_pnl"],
        funding_pnl=mark["funding_pnl"],
        costs=mark["costs"],
        realized_pnl=realized_pnl,
        realized_pnl_pct=(realized_pnl / gross_capital) * 100 if gross_capital else 0.0,
        exit_reason=reason,
    )


def carry_position_mark_payload(
    position: CarryPaperPosition,
    config: CarryPaperDefaults,
) -> dict[str, object]:
    snapshot = CarryMarketSnapshot(
        symbol=position.symbol,
        spot_exchange=position.spot_exchange,
        futures_exchange=position.futures_exchange,
        spot_price=position.last_spot_price,
        futures_price=position.last_futures_price,
        basis_bps=position.last_basis_bps,
        funding_rate_bps=position.last_funding_rate_bps,
        observed_at=position.last_mark_at,
    )
    _, mark = _mark_position(position, snapshot, config)
    gross_capital = position.notional_per_leg * 2
    return {
        **asdict(position),
        **mark,
        "net_pnl_pct": (mark["net_pnl"] / gross_capital) * 100 if gross_capital else 0.0,
        "held_hours": max(0.0, (position.last_mark_at - position.opened_at).total_seconds() / 3600),
    }


def run_carry_paper_cycle(
    *,
    snapshots: list[CarryMarketSnapshot],
    positions: list[CarryPaperPosition],
    config: CarryPaperDefaults,
) -> CarryPaperRunReport:
    snapshot_by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    remaining: list[CarryPaperPosition] = []
    events: list[CarryPaperEvent] = []
    closed_symbols: set[str] = set()

    for position in positions:
        snapshot = snapshot_by_symbol.get(position.symbol)
        if snapshot is None:
            remaining.append(position)
            continue
        marked, mark = _mark_position(position, snapshot, config)
        reason = _exit_reason(marked, snapshot, config)
        if reason:
            events.append(_close_event(marked, snapshot, mark, reason))
            closed_symbols.add(position.symbol)
            continue
        remaining.append(marked)

    open_symbols = {position.symbol for position in remaining}
    if config.enabled:
        for snapshot in snapshots:
            if len(remaining) >= config.max_positions:
                break
            if snapshot.symbol in open_symbols:
                continue
            if snapshot.symbol in closed_symbols:
                continue
            if snapshot.basis_bps < config.min_basis_bps:
                continue
            if snapshot.funding_rate_bps < config.min_funding_bps:
                continue
            position, event = _open_position(snapshot, config)
            remaining.append(position)
            events.append(event)
            open_symbols.add(snapshot.symbol)

    closed_events = [event for event in events if event.action == "CLOSE"]
    opened_events = [event for event in events if event.action == "OPEN"]
    unrealized_pnl = sum(
        float(carry_position_mark_payload(position, config)["net_pnl"])
        for position in remaining
    )
    return CarryPaperRunReport(
        enabled=config.enabled,
        mode="paper",
        research_only=True,
        generated_at=max((snapshot.observed_at for snapshot in snapshots), default=now_app_time()),
        snapshot_count=len(snapshots),
        opened_count=len(opened_events),
        closed_count=len(closed_events),
        positions=remaining,
        events=events,
        metrics={
            "open_positions": len(remaining),
            "gross_exposure": sum(position.notional_per_leg * 2 for position in remaining),
            "unrealized_pnl": round(unrealized_pnl, 8),
            "cycle_realized_pnl": round(sum(event.realized_pnl for event in closed_events), 8),
            "cycle_funding_pnl": round(sum(event.funding_pnl for event in closed_events), 8),
            "cycle_costs": round(sum(event.costs for event in events), 8),
        },
    )


__all__ = [
    "CarryMarketSnapshot",
    "CarryPaperEvent",
    "CarryPaperPosition",
    "CarryPaperRunReport",
    "build_carry_market_snapshots",
    "carry_position_from_payload",
    "carry_position_mark_payload",
    "run_carry_paper_cycle",
]
