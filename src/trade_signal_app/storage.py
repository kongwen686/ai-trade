from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from .time_utils import now_app_time

SCHEMA_VERSION = 1


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, default: object) -> object:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LocalDataStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trading_events (
                  event_uid TEXT PRIMARY KEY,
                  action TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  status TEXT NOT NULL,
                  message TEXT NOT NULL,
                  score REAL,
                  price REAL,
                  quantity REAL,
                  quote_notional REAL,
                  realized_pnl REAL,
                  realized_pnl_pct REAL,
                  exit_reason TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  response_json TEXT,
                  exchange TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  inserted_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trading_events_created_at
                  ON trading_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_trading_events_symbol_status
                  ON trading_events(symbol, status);
                CREATE INDEX IF NOT EXISTS idx_trading_events_exchange
                  ON trading_events(exchange);

                CREATE TABLE IF NOT EXISTS trading_positions (
                  position_uid TEXT PRIMARY KEY,
                  symbol TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  exchange TEXT NOT NULL,
                  client_order_id TEXT NOT NULL DEFAULT '',
                  quantity REAL NOT NULL,
                  entry_price REAL NOT NULL,
                  quote_notional REAL NOT NULL,
                  score REAL NOT NULL,
                  grade TEXT NOT NULL,
                  opened_at TEXT NOT NULL,
                  stop_price REAL NOT NULL,
                  take_profit_price REAL NOT NULL,
                  highest_price REAL,
                  leverage REAL NOT NULL DEFAULT 1,
                  margin_notional REAL,
                  payload_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trading_positions_symbol
                  ON trading_positions(symbol);

                CREATE TABLE IF NOT EXISTS backtest_runs (
                  run_uid TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  preset TEXT NOT NULL,
                  symbols TEXT NOT NULL,
                  intervals TEXT NOT NULL,
                  series_count INTEGER NOT NULL DEFAULT 0,
                  portfolio_count INTEGER NOT NULL DEFAULT 0,
                  rebalance_count INTEGER NOT NULL DEFAULT 0,
                  total_trades INTEGER NOT NULL DEFAULT 0,
                  best_final_equity REAL NOT NULL DEFAULT 0,
                  params_json TEXT NOT NULL,
                  summary_json TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  error TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_backtest_runs_last_seen_at
                  ON backtest_runs(last_seen_at);

                CREATE TABLE IF NOT EXISTS metric_snapshots (
                  snapshot_uid TEXT PRIMARY KEY,
                  scope TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  metrics_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_metric_snapshots_scope_created
                  ON metric_snapshots(scope, created_at);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    def upsert_trading_events(self, payloads: list[dict[str, object]]) -> None:
        if not payloads:
            return
        self.initialize()
        inserted_at = now_app_time().isoformat()
        rows = []
        for payload in payloads:
            response = payload.get("response") if isinstance(payload.get("response"), dict) else None
            identity = {
                "action": payload.get("action"),
                "symbol": payload.get("symbol"),
                "mode": payload.get("mode"),
                "status": payload.get("status"),
                "created_at": payload.get("created_at"),
                "price": payload.get("price"),
                "quantity": payload.get("quantity"),
                "realized_pnl": payload.get("realized_pnl"),
                "message": payload.get("message"),
                "exchange": payload.get("exchange"),
            }
            rows.append(
                (
                    _hash_payload(identity),
                    str(payload.get("action") or ""),
                    str(payload.get("symbol") or ""),
                    str(payload.get("mode") or "paper"),
                    str(payload.get("status") or ""),
                    str(payload.get("message") or ""),
                    _float_or_none(payload.get("score")),
                    _float_or_none(payload.get("price")),
                    _float_or_none(payload.get("quantity")),
                    _float_or_none(payload.get("quote_notional")),
                    _float_or_none(payload.get("realized_pnl")),
                    _float_or_none(payload.get("realized_pnl_pct")),
                    str(payload.get("exit_reason") or ""),
                    str(payload.get("created_at") or now_app_time().isoformat()),
                    _json_dumps(response) if response is not None else None,
                    str(payload.get("exchange") or "BINANCE").upper(),
                    _json_dumps(payload),
                    inserted_at,
                )
            )
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO trading_events (
                  event_uid, action, symbol, mode, status, message, score, price, quantity,
                  quote_notional, realized_pnl, realized_pnl_pct, exit_reason, created_at,
                  response_json, exchange, payload_json, inserted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def load_trading_event_payloads(self) -> list[dict[str, object]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM trading_events ORDER BY created_at, rowid"
            ).fetchall()
        payloads = []
        for row in rows:
            payload = _json_loads(str(row["payload_json"]), {})
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def replace_trading_positions(self, payloads: list[dict[str, object]]) -> None:
        self.initialize()
        updated_at = now_app_time().isoformat()
        rows = []
        for payload in payloads:
            identity = (
                str(payload.get("client_order_id") or "").strip()
                or f"{payload.get('exchange') or 'BINANCE'}:{payload.get('mode') or 'paper'}:{payload.get('symbol')}:{payload.get('opened_at')}"
            )
            rows.append(
                (
                    _hash_payload(identity),
                    str(payload.get("symbol") or ""),
                    str(payload.get("mode") or "paper"),
                    str(payload.get("exchange") or "BINANCE").upper(),
                    str(payload.get("client_order_id") or ""),
                    float(payload.get("quantity") or 0.0),
                    float(payload.get("entry_price") or 0.0),
                    float(payload.get("quote_notional") or 0.0),
                    float(payload.get("score") or 0.0),
                    str(payload.get("grade") or ""),
                    str(payload.get("opened_at") or ""),
                    float(payload.get("stop_price") or 0.0),
                    float(payload.get("take_profit_price") or 0.0),
                    _float_or_none(payload.get("highest_price")),
                    max(1.0, float(payload.get("leverage") or 1.0)),
                    _float_or_none(payload.get("margin_notional")),
                    _json_dumps(payload),
                    updated_at,
                )
            )
        with self._connect() as connection:
            connection.execute("DELETE FROM trading_positions")
            connection.executemany(
                """
                INSERT INTO trading_positions (
                  position_uid, symbol, mode, exchange, client_order_id, quantity,
                  entry_price, quote_notional, score, grade, opened_at, stop_price,
                  take_profit_price, highest_price, leverage, margin_notional,
                  payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def load_trading_position_payloads(self) -> list[dict[str, object]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM trading_positions ORDER BY opened_at, rowid"
            ).fetchall()
        payloads = []
        for row in rows:
            payload = _json_loads(str(row["payload_json"]), {})
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def record_metric_snapshot(self, scope: str, metrics: dict[str, object]) -> None:
        self.initialize()
        created_at = now_app_time().isoformat()
        payload = {"scope": scope, "created_at": created_at, "metrics": metrics}
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metric_snapshots(snapshot_uid, scope, created_at, metrics_json)
                VALUES (?, ?, ?, ?)
                """,
                (_hash_payload(payload), scope, created_at, _json_dumps(metrics)),
            )

    def record_backtest_run(self, *, params: dict[str, object], payload: dict[str, object], error: str | None = None) -> str:
        self.initialize()
        series_reports = payload.get("series_reports") if isinstance(payload.get("series_reports"), list) else []
        portfolio_reports = payload.get("portfolio_reports") if isinstance(payload.get("portfolio_reports"), list) else []
        rebalance_reports = payload.get("rebalance_reports") if isinstance(payload.get("rebalance_reports"), list) else []
        symbols = sorted({str(report.get("symbol") or "").upper() for report in series_reports if isinstance(report, dict) and report.get("symbol")})
        intervals = sorted({str(report.get("interval") or "") for report in series_reports if isinstance(report, dict) and report.get("interval")})
        total_trades = sum(int(float(report.get("signal_count") or 0)) for report in series_reports if isinstance(report, dict))
        equities = [
            float(report.get("final_equity") or 0.0)
            for report in [*series_reports, *portfolio_reports]
            if isinstance(report, dict)
        ]
        summary = {
            "series_count": len(series_reports),
            "portfolio_count": len(portfolio_reports),
            "rebalance_count": len(rebalance_reports),
            "symbols": symbols,
            "intervals": intervals,
            "total_trades": total_trades,
            "best_final_equity": max(equities, default=0.0),
            "error": error or "",
        }
        run_uid = _hash_payload({"params": params, "summary": summary})
        seen_at = now_app_time().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO backtest_runs (
                  run_uid, created_at, last_seen_at, preset, symbols, intervals,
                  series_count, portfolio_count, rebalance_count, total_trades,
                  best_final_equity, params_json, summary_json, payload_json, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_uid) DO UPDATE SET
                  last_seen_at = excluded.last_seen_at,
                  payload_json = excluded.payload_json,
                  summary_json = excluded.summary_json,
                  error = excluded.error
                """,
                (
                    run_uid,
                    seen_at,
                    seen_at,
                    str(params.get("preset") or ""),
                    ",".join(symbols),
                    ",".join(intervals),
                    len(series_reports),
                    len(portfolio_reports),
                    len(rebalance_reports),
                    total_trades,
                    max(equities, default=0.0),
                    _json_dumps(params),
                    _json_dumps(summary),
                    _json_dumps(payload),
                    error or "",
                ),
            )
        return run_uid

    def status(self) -> dict[str, object]:
        self.initialize()
        with self._connect() as connection:
            counts = {
                "trading_events": connection.execute("SELECT COUNT(*) FROM trading_events").fetchone()[0],
                "trading_positions": connection.execute("SELECT COUNT(*) FROM trading_positions").fetchone()[0],
                "backtest_runs": connection.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0],
                "metric_snapshots": connection.execute("SELECT COUNT(*) FROM metric_snapshots").fetchone()[0],
            }
            schema_version = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "schema_version": int(schema_version[0]) if schema_version else SCHEMA_VERSION,
            **counts,
        }
