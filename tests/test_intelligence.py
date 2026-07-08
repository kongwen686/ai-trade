from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from trade_signal_app.config import AppSettings
from trade_signal_app.intelligence import IntelligenceHub, LlmInsightClient, OpenAIInsightClient
from trade_signal_app.runtime_config import RuntimeConfig


def _signal(
    symbol: str,
    score: float,
    price: float,
    change: float = 2.0,
    rsi: float = 58.0,
    price_vs_ema20: float = 2.0,
    recent_change: float = 1.5,
    volume_ratio: float = 1.8,
) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        score=score,
        grade="A",
        reasons=["趋势结构改善", "量能放大"],
        ticker=SimpleNamespace(last_price=price, quote_volume=200_000_000.0, price_change_percent=change),
        indicators=SimpleNamespace(
            volume_ratio=volume_ratio,
            buy_pressure_ratio=0.61,
            ema_spread_pct=1.2,
            rsi_14=rsi,
            price_vs_ema20_pct=price_vs_ema20,
            recent_change_pct=recent_change,
        ),
    )


class FakeScanner:
    def __init__(self, signals) -> None:
        self.signals = signals

    def scan(self):
        return SimpleNamespace(scanned_symbols=20, returned_signals=len(self.signals)), self.signals


class IntelligenceTests(unittest.TestCase):
    def test_snapshot_builds_local_intelligence_sections(self) -> None:
        config = RuntimeConfig()
        config.onchain_data_preset = "local_csv"
        config.autotrade_defaults.score_threshold = 75.0
        config.x_tracked_accounts = ["@lookonchain", "wu_blockchain"]
        hub = IntelligenceHub(
            scanner=FakeScanner([_signal("BTCUSDT", 82.0, 68000.0)]),
            runtime_config=config,
            settings=AppSettings(),
        )

        snapshot = hub.snapshot()

        self.assertEqual(snapshot.scanned_symbols, 20)
        self.assertGreaterEqual(len(snapshot.intel_items), 1)
        self.assertEqual(snapshot.onchain_events, [])
        self.assertEqual(snapshot.spreads, [])
        self.assertGreaterEqual(len(snapshot.strategy_hits), 1)
        self.assertEqual(snapshot.twitter_accounts[0].username, "lookonchain")
        self.assertEqual(snapshot.llm_insight.provider, "local")
        self.assertIn("BTCUSDT", snapshot.execution_risk.allowed_symbols)

    def test_snapshot_loads_csv_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            intel = root / "intel.csv"
            onchain = root / "onchain.csv"
            spreads = root / "spreads.csv"
            funding = root / "funding.csv"
            intel.write_text("source,symbol,title,category,severity,sentiment,url\nbinance,BTCUSDT,Listing update,news,91,0.8,\n", encoding="utf-8")
            onchain.write_text("chain,symbol,event_type,amount_usd,direction,severity,tx_hash\nbitcoin,BTCUSDT,whale_transfer,9000000,outflow,88,tx\n", encoding="utf-8")
            spreads.write_text("symbol,spot_exchange,futures_exchange,spot_price,futures_price,spread_bps,direction\nBTCUSDT,BINANCE,BINANCE-PERP,100,101,100,basis\n", encoding="utf-8")
            funding.write_text("symbol,futures_exchange,funding_rate,mark_price,index_price,source\nBTCUSDT,BINANCE-PERP,0.0012,101,100,fixture\n", encoding="utf-8")
            settings = AppSettings(exchange_intel_csv=intel, onchain_events_csv=onchain, futures_basis_csv=spreads, futures_funding_csv=funding)
            config = RuntimeConfig()
            config.onchain_data_preset = "local_csv"
            hub = IntelligenceHub(
                scanner=FakeScanner([_signal("BTCUSDT", 82.0, 100.0)]),
                runtime_config=config,
                settings=settings,
            )

            snapshot = hub.snapshot()

        self.assertEqual(snapshot.intel_items[0].title, "Listing update")
        self.assertEqual(snapshot.onchain_events[0].tx_hash, "tx")
        self.assertEqual(snapshot.spreads[0].spread_bps, 100.0)
        self.assertEqual(snapshot.funding_rates[0].funding_rate_bps, 12.0)
        self.assertIn("BTCUSDT", snapshot.execution_risk.blocked_symbols)

    def test_low_float_strategy_hits_use_funding_rate_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            funding = Path(temp_dir) / "funding.csv"
            funding.write_text(
                "\n".join(
                    [
                        "symbol,futures_exchange,funding_rate,mark_price,index_price,source",
                        "EARLYUSDT,BINANCE-PERP,-0.0001,1,1,fixture",
                        "BLOWOFFUSDT,BINANCE-PERP,0.0006,1,1,fixture",
                        "CRASHUSDT,BINANCE-PERP,-0.0004,1,1,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            settings = AppSettings(futures_funding_csv=funding)
            hub = IntelligenceHub(
                scanner=FakeScanner(
                    [
                        _signal("EARLYUSDT", 72.0, 1.0, change=35.0, volume_ratio=3.2),
                        _signal("BLOWOFFUSDT", 78.0, 1.0, change=75.0, rsi=82.0, price_vs_ema20=32.0, volume_ratio=3.8),
                        _signal("CRASHUSDT", 60.0, 1.0, change=-28.0, rsi=31.0, price_vs_ema20=-18.0),
                    ]
                ),
                runtime_config=RuntimeConfig(),
                settings=settings,
            )

            snapshot = hub.snapshot()

        strategies = {hit.strategy for hit in snapshot.strategy_hits}
        self.assertIn("low_float_momentum_long", strategies)
        self.assertIn("blowoff_distribution_short", strategies)
        self.assertIn("capitulation_rebound_long", strategies)
        reasons = " ".join(" ".join(hit.reasons) for hit in snapshot.strategy_hits)
        self.assertIn("资金费率", reasons)

    def test_openai_response_text_extractor(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "综合分析"},
                    ],
                }
            ]
        }

        self.assertEqual(OpenAIInsightClient._extract_output_text(payload), "综合分析")

    def test_openai_compatible_chat_text_extractor(self) -> None:
        payload = {"choices": [{"message": {"content": "兼容模型分析"}}]}

        self.assertEqual(LlmInsightClient._extract_chat_text(payload), "兼容模型分析")

    def test_anthropic_text_extractor(self) -> None:
        payload = {"content": [{"type": "text", "text": "Claude 分析"}]}

        self.assertEqual(LlmInsightClient._extract_anthropic_text(payload), "Claude 分析")


if __name__ == "__main__":
    unittest.main()
