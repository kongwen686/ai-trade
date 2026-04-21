from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from trade_signal_app.community import (
    AliasRegistry,
    CompositeCommunityScoreProvider,
    CommunitySignal,
    CsvCommunityScoreProvider,
    NullCommunityScoreProvider,
    sanitize_account_names,
    XCommunityScoreProvider,
    build_community_provider,
    derive_base_asset,
)


class CommunityTests(unittest.TestCase):
    def test_derive_base_asset(self) -> None:
        self.assertEqual(derive_base_asset("BTCUSDT"), "BTC")
        self.assertEqual(derive_base_asset("ETHBTC"), "ETH")
        self.assertEqual(derive_base_asset("SUIFDUSD"), "SUI")

    def test_x_query_builder_uses_default_map(self) -> None:
        provider = XCommunityScoreProvider(
            bearer_token="token",
            alias_registry=AliasRegistry(alias_csv_path=Path("/tmp/does-not-exist.csv")),
            base_url="https://api.x.com",
            ttl_seconds=60,
            recent_window_hours=24,
            max_results=10,
            language="en",
            max_workers=1,
        )
        query = provider.build_query("BTCUSDT")
        self.assertIn("$BTC", query)
        self.assertIn("bitcoin", query.lower())
        self.assertIn("lang:en", query)
        self.assertIn("-is:retweet", query)

    def test_x_query_builder_uses_alias_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            alias_path = Path(temp_dir) / "social_aliases.csv"
            alias_path.write_text("symbol,query\nLINKUSDT,(\"chainlink\" OR \"$LINK\") lang:en -is:retweet\n", encoding="utf-8")
            provider = XCommunityScoreProvider(
                bearer_token="token",
                alias_registry=AliasRegistry(alias_csv_path=alias_path),
                base_url="https://api.x.com",
                ttl_seconds=60,
                recent_window_hours=24,
                max_results=10,
                language="en",
                max_workers=1,
            )
            self.assertEqual(provider.build_query("LINKUSDT"), "(\"chainlink\" OR \"$LINK\") lang:en -is:retweet")

    def test_x_account_query_builder_adds_from_filters(self) -> None:
        provider = XCommunityScoreProvider(
            bearer_token="token",
            alias_registry=AliasRegistry(alias_csv_path=Path("/tmp/does-not-exist.csv")),
            base_url="https://api.x.com",
            ttl_seconds=60,
            recent_window_hours=24,
            max_results=10,
            language="en",
            max_workers=1,
            tracked_accounts=["@lookonchain", "wu_blockchain"],
        )
        query = provider.build_account_query("BTCUSDT")
        self.assertIn("from:lookonchain", query)
        self.assertIn("from:wu_blockchain", query)
        self.assertIn("$BTC", query)

    def test_sentiment_scoring_direction(self) -> None:
        positive = XCommunityScoreProvider.score_sentiment(
            [
                "bullish breakout and strong momentum",
                "buy setup with rally and rebound",
            ]
        )
        negative = XCommunityScoreProvider.score_sentiment(
            [
                "bearish breakdown and weak momentum",
                "fear, panic and sell pressure",
            ]
        )
        self.assertGreater(positive, 0)
        self.assertLess(negative, 0)

    def test_prepare_fetches_x_signal(self) -> None:
        def fake_fetcher(url: str, headers: dict[str, str] | None, timeout: int) -> object:
            self.assertIsNotNone(headers)
            if "counts/recent" in url:
                return {"meta": {"total_tweet_count": 240}}
            if "search/recent" in url:
                return {
                    "data": [
                        {"text": "bullish breakout for bitcoin"},
                        {"text": "strong rally and buy momentum"},
                        {"text": "bitcoin adoption growth"},
                    ]
                }
            raise AssertionError(f"unexpected url: {url}")

        provider = XCommunityScoreProvider(
            bearer_token="token",
            alias_registry=AliasRegistry(alias_csv_path=Path("/tmp/does-not-exist.csv")),
            base_url="https://api.x.com",
            ttl_seconds=60,
            recent_window_hours=24,
            max_results=10,
            language="en",
            max_workers=1,
            fetcher=fake_fetcher,
        )
        provider.prepare(["BTCUSDT"])
        signal = provider.get("BTCUSDT")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.source, "x")
        self.assertEqual(signal.mentions, 240)
        self.assertGreater(signal.score, 50)
        self.assertGreater(signal.sentiment or 0, 0)

    def test_prepare_fetches_blended_account_signal(self) -> None:
        def fake_fetcher(url: str, headers: dict[str, str] | None, timeout: int) -> object:
            if "counts/recent" in url and "from%3Alookonchain" in url:
                return {"meta": {"total_tweet_count": 40}}
            if "counts/recent" in url:
                return {"meta": {"total_tweet_count": 200}}
            if "search/recent" in url and "from%3Alookonchain" in url:
                return {"data": [{"text": "bullish breakout from tracked account"}]}
            if "search/recent" in url:
                return {"data": [{"text": "bearish setup"}, {"text": "weak momentum"}]}
            raise AssertionError(f"unexpected url: {url}")

        provider = XCommunityScoreProvider(
            bearer_token="token",
            alias_registry=AliasRegistry(alias_csv_path=Path("/tmp/does-not-exist.csv")),
            base_url="https://api.x.com",
            ttl_seconds=60,
            recent_window_hours=24,
            max_results=10,
            language="en",
            max_workers=1,
            tracked_accounts=["lookonchain"],
            account_mode="blend",
            account_weight_pct=50.0,
            fetcher=fake_fetcher,
        )
        provider.prepare(["BTCUSDT"])
        signal = provider.get("BTCUSDT")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.source, "x+x_accounts")
        self.assertEqual(signal.mentions, 240)
        self.assertGreater(signal.score, 0)

    def test_sanitize_account_names_deduplicates_and_strips(self) -> None:
        self.assertEqual(
            sanitize_account_names(["@lookonchain", " lookonchain ", "@Wu_Blockchain"]),
            ["lookonchain", "Wu_Blockchain"],
        )

    def test_composite_provider_averages_scores(self) -> None:
        class StaticProvider(NullCommunityScoreProvider):
            def __init__(self, signal: CommunitySignal) -> None:
                self.signal = signal

            def get(self, symbol: str) -> CommunitySignal | None:
                return self.signal

        provider = CompositeCommunityScoreProvider(
            providers=[
                StaticProvider(CommunitySignal(score=80, source="x", mentions=100, sentiment=0.4, sample_size=20)),
                StaticProvider(CommunitySignal(score=60, source="csv", mentions=20, sentiment=0.2, sample_size=5)),
            ]
        )
        signal = provider.get("BTCUSDT")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.score, 70)
        self.assertEqual(signal.source, "x+csv")
        self.assertEqual(signal.mentions, 120)

    def test_build_provider_auto_without_credentials_returns_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = build_community_provider(
                provider_mode="auto",
                csv_path=Path(temp_dir) / "missing.csv",
                alias_csv_path=Path(temp_dir) / "aliases.csv",
                x_bearer_token="",
                x_api_base_url="https://api.x.com",
                community_ttl_seconds=60,
                x_recent_window_hours=24,
                x_recent_max_results=10,
                x_language="en",
                x_max_workers=1,
            )
            self.assertIsInstance(provider, NullCommunityScoreProvider)

    def test_build_provider_with_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "community_scores.csv"
            csv_path.write_text("symbol,score,mentions,sentiment,source\nBTCUSDT,82,1240,0.78,csv\n", encoding="utf-8")
            provider = build_community_provider(
                provider_mode="csv",
                csv_path=csv_path,
                alias_csv_path=Path(temp_dir) / "aliases.csv",
                x_bearer_token="",
                x_api_base_url="https://api.x.com",
                community_ttl_seconds=60,
                x_recent_window_hours=24,
                x_recent_max_results=10,
                x_language="en",
                x_max_workers=1,
            )
            self.assertIsInstance(provider, CsvCommunityScoreProvider)


if __name__ == "__main__":
    unittest.main()
