from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import shutil
import subprocess
from threading import Event, RLock, Thread
from typing import Callable

from .binance_client import parse_ticker
from .time_utils import now_app_time


DEFAULT_FALLBACK_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
AGENT_REACH_HEALTH_TTL = timedelta(hours=6)


@dataclass(frozen=True)
class AgentReachHealth:
    installed: bool
    executable: str
    checked_at: str
    channels: dict[str, dict[str, object]]
    error: str = ""


def resolve_agent_reach_executable(configured: str = "") -> str:
    candidates = [
        str(Path(configured.strip()).expanduser()) if configured.strip() else "",
        shutil.which("agent-reach") or "",
        str(Path.home() / ".local" / "bin" / "agent-reach"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return ""


def probe_agent_reach(configured: str = "", *, timeout: int = 40) -> AgentReachHealth:
    executable = resolve_agent_reach_executable(configured)
    checked_at = now_app_time().isoformat()
    if not executable:
        return AgentReachHealth(False, "", checked_at, {}, "Agent-Reach CLI 未安装或不可执行。")
    try:
        completed = subprocess.run(
            [executable, "doctor", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(5, timeout),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return AgentReachHealth(True, executable, checked_at, {}, f"Agent-Reach doctor 失败：{exc}")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return AgentReachHealth(True, executable, checked_at, {}, detail or f"doctor exit {completed.returncode}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return AgentReachHealth(True, executable, checked_at, {}, f"doctor 输出不是合法 JSON：{exc}")
    channels = {
        name: value
        for name, value in payload.items()
        if name in {"twitter", "reddit", "rss", "web", "exa_search"} and isinstance(value, dict)
    }
    return AgentReachHealth(True, executable, checked_at, channels)


class CommunityIntelligenceScheduler:
    def __init__(
        self,
        *,
        snapshot: Callable[[], tuple[object, object]],
        cache_path: Path,
        health_probe: Callable[[str], AgentReachHealth] = probe_agent_reach,
    ) -> None:
        self._snapshot = snapshot
        self._cache_path = cache_path
        self._health_probe = health_probe
        self._lock = RLock()
        self._run_lock = RLock()
        self._stop_event: Event | None = None
        self._thread: Thread | None = None
        self._health: AgentReachHealth | None = None
        self._health_checked_at: datetime | None = None
        self._state: dict[str, object] = {
            "running": False,
            "enabled": False,
            "interval_seconds": 900,
            "last_run_at": None,
            "next_run_at": None,
            "last_error": "",
            "symbol_count": 0,
            "signal_count": 0,
            "raw_signal_count": 0,
            "bullish_candidates": [],
            "bearish_candidates": [],
            "agent_reach": {},
        }

    def start(self) -> dict[str, object]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            stop_event = Event()
            self._stop_event = stop_event
            self._thread = Thread(target=self._worker, args=(stop_event,), name="community-intelligence", daemon=True)
            self._state["running"] = True
            self._state["next_run_at"] = (now_app_time() + timedelta(seconds=10)).isoformat()
            self._thread.start()
            return self.status()

    def stop(self) -> dict[str, object]:
        with self._lock:
            stop_event = self._stop_event
            thread = self._thread
            if stop_event is not None:
                stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        with self._lock:
            self._state.update({"running": False, "next_run_at": None})
            return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            return json.loads(json.dumps(self._state, ensure_ascii=False))

    def run_once(self) -> dict[str, object]:
        with self._run_lock:
            runtime_config, scanner = self._snapshot()
            rules = runtime_config.intelligence_defaults
            interval = max(60, int(rules.community_scan_interval_seconds))
            attempted_at = now_app_time()
            with self._lock:
                self._state.update(
                    {
                        "enabled": bool(rules.community_scan_enabled),
                        "interval_seconds": interval,
                        "last_run_at": attempted_at.isoformat(),
                    }
                )
            if not rules.community_scan_enabled:
                return self._finish(attempted_at, interval, [], [], [], "")

            try:
                symbols = self._candidate_symbols(
                    scanner,
                    quote_asset=runtime_config.scan_defaults.quote_asset,
                    limit=rules.community_max_symbols,
                )
                provider = scanner.community_provider
                provider.prepare(symbols)
                signals = []
                for symbol in symbols:
                    signal = provider.get(symbol)
                    if signal is not None:
                        signals.append((symbol, signal))

                valid = [
                    (symbol, signal)
                    for symbol, signal in signals
                    if (signal.mentions or 0) >= rules.community_min_mentions
                    and (signal.confidence is None or signal.confidence >= rules.community_min_confidence)
                ]
                bullish = [
                    self._signal_payload(symbol, signal)
                    for symbol, signal in valid
                    if signal.score >= rules.community_bullish_threshold and (signal.sentiment or 0.0) >= 0.05
                ]
                bearish = [
                    self._signal_payload(symbol, signal)
                    for symbol, signal in valid
                    if (signal.risk_score or 0.0) >= rules.community_bearish_threshold
                    or (signal.sentiment or 0.0) <= -0.45
                ]
                bullish.sort(key=lambda item: float(item["score"]), reverse=True)
                bearish.sort(key=lambda item: float(item["risk_score"]), reverse=True)
                health = self._agent_reach_health(rules.agent_reach_executable) if rules.agent_reach_enabled else None
                return self._finish(
                    attempted_at,
                    interval,
                    symbols,
                    bullish[:10],
                    bearish[:10],
                    "",
                    signal_count=len(valid),
                    raw_signal_count=len(signals),
                    health=health,
                )
            except Exception as exc:  # noqa: BLE001
                return self._finish(attempted_at, interval, [], [], [], str(exc))

    def _worker(self, stop_event: Event) -> None:
        if stop_event.wait(10):
            return
        while not stop_event.is_set():
            result = self.run_once()
            interval = max(60, int(result.get("interval_seconds") or 900))
            if stop_event.wait(interval):
                break
        with self._lock:
            if self._stop_event is stop_event:
                self._state.update({"running": False, "next_run_at": None})

    def _agent_reach_health(self, configured: str) -> AgentReachHealth:
        now = now_app_time()
        if self._health is None or self._health_checked_at is None or now - self._health_checked_at >= AGENT_REACH_HEALTH_TTL:
            self._health = self._health_probe(configured)
            self._health_checked_at = now
        return self._health

    @staticmethod
    def _candidate_symbols(scanner: object, *, quote_asset: str, limit: int) -> list[str]:
        try:
            rows = scanner.gateway.ticker24hr()
            tickers = []
            for row in rows:
                try:
                    tickers.append(parse_ticker(row))
                except (KeyError, TypeError, ValueError):
                    continue
            ranked = sorted(
                [ticker for ticker in tickers if ticker.symbol.endswith(quote_asset.upper())],
                key=lambda ticker: ticker.quote_volume,
                reverse=True,
            )
            symbols = [ticker.symbol for ticker in ranked[: max(5, min(int(limit), 100))]]
            if symbols:
                return symbols
        except Exception:  # noqa: BLE001
            pass
        return list(DEFAULT_FALLBACK_SYMBOLS)[: max(1, int(limit))]

    @staticmethod
    def _signal_payload(symbol: str, signal: object) -> dict[str, object]:
        return {
            "symbol": symbol,
            "score": round(float(signal.score), 2),
            "risk_score": round(float(signal.risk_score or 0.0), 2),
            "sentiment": round(float(signal.sentiment or 0.0), 4),
            "confidence": None if signal.confidence is None else round(float(signal.confidence), 4),
            "confidence_pct": None if signal.confidence is None else round(float(signal.confidence) * 100, 1),
            "mentions": signal.mentions,
            "source": signal.source,
            "summary": signal.summary,
        }

    def _finish(
        self,
        attempted_at: datetime,
        interval: int,
        symbols: list[str],
        bullish: list[dict[str, object]],
        bearish: list[dict[str, object]],
        error: str,
        *,
        signal_count: int = 0,
        raw_signal_count: int = 0,
        health: AgentReachHealth | None = None,
    ) -> dict[str, object]:
        with self._lock:
            self._state.update(
                {
                    "last_error": error,
                    "symbol_count": len(symbols),
                    "signal_count": signal_count,
                    "raw_signal_count": raw_signal_count,
                    "bullish_candidates": bullish,
                    "bearish_candidates": bearish,
                    "next_run_at": (attempted_at + timedelta(seconds=interval)).isoformat(),
                    "agent_reach": asdict(health) if health is not None else self._state.get("agent_reach", {}),
                }
            )
            payload = self.status()
        self._persist(payload)
        return payload

    def _persist(self, payload: dict[str, object]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self._cache_path)
        except OSError:
            return


__all__ = [
    "AgentReachHealth",
    "CommunityIntelligenceScheduler",
    "probe_agent_reach",
    "resolve_agent_reach_executable",
]
