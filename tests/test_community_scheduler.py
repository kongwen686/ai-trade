from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from trade_signal_app.community_scheduler import AgentReachHealth, CommunityIntelligenceScheduler
from trade_signal_app.models import CommunitySignal


class FakeProvider:
    def __init__(self) -> None:
        self.prepared: list[str] = []

    def prepare(self, symbols: list[str]) -> None:
        self.prepared = list(symbols)

    def get(self, symbol: str) -> CommunitySignal | None:
        if symbol != "BTCUSDT":
            return None
        return CommunitySignal(
            score=82,
            source="agent_reach_rss",
            mentions=5,
            sentiment=0.5,
            confidence=0.9,
            risk_score=10,
            summary="BTC 社区情绪偏多。",
        )


class CommunitySchedulerTests(unittest.TestCase):
    def test_run_once_prewarms_without_invoking_trading(self) -> None:
        provider = FakeProvider()
        scanner = SimpleNamespace(
            gateway=SimpleNamespace(ticker24hr=lambda: (_ for _ in ()).throw(RuntimeError("offline"))),
            community_provider=provider,
        )
        rules = SimpleNamespace(
            community_scan_enabled=True,
            community_scan_interval_seconds=900,
            community_max_symbols=40,
            community_min_mentions=3,
            community_min_confidence=0.55,
            community_bullish_threshold=70,
            community_bearish_threshold=70,
            agent_reach_enabled=True,
            agent_reach_executable="",
        )
        config = SimpleNamespace(
            intelligence_defaults=rules,
            scan_defaults=SimpleNamespace(quote_asset="USDT"),
        )
        health = AgentReachHealth(
            installed=True,
            executable="/tmp/agent-reach",
            checked_at="2026-07-25T08:00:00+08:00",
            channels={"rss": {"status": "ok", "active_backend": "feedparser"}},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            scheduler = CommunityIntelligenceScheduler(
                snapshot=lambda: (config, scanner),
                cache_path=Path(temp_dir) / "community.json",
                health_probe=lambda _configured: health,
            )

            status = scheduler.run_once()

            self.assertIn("BTCUSDT", provider.prepared)
            self.assertEqual(status["signal_count"], 1)
            self.assertEqual(status["bullish_candidates"][0]["symbol"], "BTCUSDT")
            self.assertEqual(status["bearish_candidates"], [])
            self.assertEqual(status["agent_reach"]["channels"]["rss"]["status"], "ok")
            self.assertTrue((Path(temp_dir) / "community.json").exists())


if __name__ == "__main__":
    unittest.main()
