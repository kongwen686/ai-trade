from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import json
import math
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import CommunitySignal

QUOTE_SUFFIXES = (
    "USDT",
    "USDC",
    "FDUSD",
    "BUSD",
    "TUSD",
    "USDP",
    "DAI",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "TRY",
    "BRL",
    "JPY",
    "AUD",
)

DEFAULT_X_NAME_MAP = {
    "BTC": ["bitcoin"],
    "ETH": ["ethereum"],
    "BNB": ["binance coin", "bnb chain"],
    "XRP": ["ripple"],
    "SOL": ["solana"],
    "ADA": ["cardano"],
    "DOGE": ["dogecoin"],
    "TRX": ["tron"],
    "DOT": ["polkadot"],
    "LINK": ["chainlink"],
    "AVAX": ["avalanche"],
    "LTC": ["litecoin"],
    "SUI": ["sui"],
    "TON": ["toncoin", "the open network"],
    "SHIB": ["shiba inu"],
}

POSITIVE_TERMS = {
    "accumulation",
    "adoption",
    "ath",
    "bounce",
    "breakout",
    "bull",
    "bullish",
    "buy",
    "growth",
    "long",
    "momentum",
    "pump",
    "rally",
    "rebound",
    "reversal",
    "strong",
    "surge",
    "uptrend",
}

NEGATIVE_TERMS = {
    "bear",
    "bearish",
    "breakdown",
    "capitulation",
    "crash",
    "downtrend",
    "dump",
    "fear",
    "liquidation",
    "panic",
    "resistance",
    "rug",
    "scam",
    "sell",
    "short",
    "weak",
}


class CommunityScoreProvider:
    def prepare(self, symbols: list[str]) -> None:
        return

    def get(self, symbol: str) -> CommunitySignal | None:
        raise NotImplementedError


@dataclass
class NullCommunityScoreProvider(CommunityScoreProvider):
    def get(self, symbol: str) -> CommunitySignal | None:
        return None


@dataclass
class CsvCommunityScoreProvider(CommunityScoreProvider):
    csv_path: Path
    _cache: dict[str, CommunitySignal] | None = None

    def _load(self) -> dict[str, CommunitySignal]:
        if not self.csv_path.exists():
            return {}

        signals: dict[str, CommunitySignal] = {}
        with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                signals[symbol] = CommunitySignal(
                    score=float(row.get("score", 0) or 0),
                    source=(row.get("source") or "csv").strip() or "csv",
                    mentions=int(row["mentions"]) if row.get("mentions") else None,
                    sentiment=float(row["sentiment"]) if row.get("sentiment") else None,
                    sample_size=int(row["sample_size"]) if row.get("sample_size") else None,
                )
        return signals

    def get(self, symbol: str) -> CommunitySignal | None:
        if self._cache is None:
            self._cache = self._load()
        return self._cache.get(symbol.upper())


@dataclass
class NewsCommunityScoreProvider(CommunityScoreProvider):
    csv_path: Path
    _cache: dict[str, CommunitySignal] | None = None

    def _load(self) -> dict[str, CommunitySignal]:
        if not self.csv_path.exists():
            return {}

        grouped: dict[str, list[dict[str, object]]] = {}
        with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                grouped.setdefault(symbol, []).append(
                    {
                        "headline": (row.get("headline") or "").strip(),
                        "sentiment": float(row.get("sentiment", 0) or 0),
                        "source": (row.get("source") or "news").strip() or "news",
                    }
                )

        signals: dict[str, CommunitySignal] = {}
        for symbol, items in grouped.items():
            sentiments = [float(item["sentiment"]) for item in items]
            sources = dedupe_terms([str(item["source"]) for item in items])
            sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
            mentions = len(items)
            score = XCommunityScoreProvider.compute_score(
                mentions=mentions * 20,
                sentiment=sentiment,
                sample_size=len(items),
            )
            signals[symbol] = CommunitySignal(
                score=round(score, 2),
                source="+".join(sources) if sources else "news",
                mentions=mentions,
                sentiment=round(sentiment, 4),
                sample_size=len(items),
            )
        return signals

    def get(self, symbol: str) -> CommunitySignal | None:
        if self._cache is None:
            self._cache = self._load()
        return self._cache.get(symbol.upper())


@dataclass
class TelegramCommunityScoreProvider(CommunityScoreProvider):
    csv_path: Path
    _cache: dict[str, CommunitySignal] | None = None

    def _load(self) -> dict[str, CommunitySignal]:
        if not self.csv_path.exists():
            return {}

        grouped: dict[str, list[dict[str, object]]] = {}
        with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                grouped.setdefault(symbol, []).append(
                    {
                        "channel": (row.get("channel") or "telegram").strip() or "telegram",
                        "sentiment": float(row.get("sentiment", 0) or 0),
                        "message": (row.get("message") or "").strip(),
                    }
                )

        signals: dict[str, CommunitySignal] = {}
        for symbol, items in grouped.items():
            sentiments = [float(item["sentiment"]) for item in items]
            channels = dedupe_terms([str(item["channel"]) for item in items])
            sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
            mentions = len(items)
            score = XCommunityScoreProvider.compute_score(
                mentions=mentions * 18,
                sentiment=sentiment,
                sample_size=len(items),
            )
            signals[symbol] = CommunitySignal(
                score=round(score, 2),
                source="+".join(channels) if channels else "telegram",
                mentions=mentions,
                sentiment=round(sentiment, 4),
                sample_size=len(items),
            )
        return signals

    def get(self, symbol: str) -> CommunitySignal | None:
        if self._cache is None:
            self._cache = self._load()
        return self._cache.get(symbol.upper())


@dataclass
class RedditCommunityScoreProvider(CommunityScoreProvider):
    alias_registry: AliasRegistry
    base_url: str
    ttl_seconds: int
    recent_window_hours: int
    max_results: int
    user_agent: str
    timeout: int = 20
    fetcher: Callable[[str, dict[str, str] | None, int], object] | None = None
    _cache: dict[str, CachedSignal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fetcher is None:
            self.fetcher = http_get_json

    def prepare(self, symbols: list[str]) -> None:
        for symbol in [item.upper() for item in symbols if not self._is_cached(item)]:
            try:
                signal = self._fetch_symbol(symbol)
            except Exception:  # noqa: BLE001
                signal = None
            self._cache[symbol] = CachedSignal(
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds),
                signal=signal,
            )

    def get(self, symbol: str) -> CommunitySignal | None:
        cached = self._cache.get(symbol.upper())
        if cached and cached.expires_at > datetime.now(timezone.utc):
            return cached.signal
        try:
            signal = self._fetch_symbol(symbol.upper())
        except Exception:  # noqa: BLE001
            signal = None
        self._cache[symbol.upper()] = CachedSignal(
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds),
            signal=signal,
        )
        return signal

    def _is_cached(self, symbol: str) -> bool:
        cached = self._cache.get(symbol.upper())
        return bool(cached and cached.expires_at > datetime.now(timezone.utc))

    def build_query(self, symbol: str) -> str:
        symbol = symbol.upper()
        alias_query = self.alias_registry.get_query(symbol)
        if alias_query:
            return alias_query.replace("lang:en", "").replace("-is:retweet", "").strip()

        base_asset = derive_base_asset(symbol)
        names = DEFAULT_X_NAME_MAP.get(base_asset, [])
        terms = [base_asset, f"${base_asset}"]
        terms.extend(names)
        return " OR ".join(format_reddit_term(term) for term in dedupe_terms(terms))

    def _fetch_symbol(self, symbol: str) -> CommunitySignal | None:
        params = {
            "q": self.build_query(symbol),
            "sort": "new",
            "t": "day",
            "limit": str(max(5, min(self.max_results, 100))),
            "restrict_sr": "0",
            "raw_json": "1",
        }
        url = f"{self.base_url.rstrip('/')}/search.json?{urlencode(params)}"
        assert self.fetcher is not None
        payload = self.fetcher(url, {"User-Agent": self.user_agent}, self.timeout)
        posts = self._parse_posts(payload)
        if not posts:
            return None
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.recent_window_hours)
        fresh_posts = [post for post in posts if post["created_at"] >= cutoff]
        if not fresh_posts:
            return None
        texts = [post["text"] for post in fresh_posts if post["text"]]
        sentiment = XCommunityScoreProvider.score_sentiment(texts)
        score = XCommunityScoreProvider.compute_score(
            mentions=len(fresh_posts) * 15,
            sentiment=sentiment,
            sample_size=len(fresh_posts),
        )
        return CommunitySignal(
            score=round(score, 2),
            source="reddit",
            mentions=len(fresh_posts),
            sentiment=round(sentiment, 4),
            sample_size=len(fresh_posts),
        )

    @staticmethod
    def _parse_posts(payload: object) -> list[dict[str, object]]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        children = data.get("children")
        if not isinstance(children, list):
            return []
        posts: list[dict[str, object]] = []
        for child in children:
            if not isinstance(child, dict):
                continue
            child_data = child.get("data")
            if not isinstance(child_data, dict):
                continue
            created_utc = child_data.get("created_utc")
            if created_utc is None:
                continue
            title = str(child_data.get("title", "")).strip()
            body = str(child_data.get("selftext", "")).strip()
            text = " ".join(item for item in [title, body] if item)
            posts.append(
                {
                    "created_at": datetime.fromtimestamp(float(created_utc), tz=timezone.utc),
                    "text": text,
                }
            )
        return posts


@dataclass
class AliasRegistry:
    alias_csv_path: Path
    _cache: dict[str, str] | None = None

    def get_query(self, symbol: str) -> str | None:
        if self._cache is None:
            self._cache = self._load()
        return self._cache.get(symbol.upper())

    def _load(self) -> dict[str, str]:
        if not self.alias_csv_path.exists():
            return {}

        aliases: dict[str, str] = {}
        with self.alias_csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("symbol") or "").strip().upper()
                query = (row.get("query") or "").strip()
                if symbol and query:
                    aliases[symbol] = query
        return aliases


@dataclass
class CachedSignal:
    expires_at: datetime
    signal: CommunitySignal | None


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> object:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


@dataclass
class XCommunityScoreProvider(CommunityScoreProvider):
    bearer_token: str
    alias_registry: AliasRegistry
    base_url: str
    ttl_seconds: int
    recent_window_hours: int
    max_results: int
    language: str
    max_workers: int
    tracked_accounts: list[str] = field(default_factory=list)
    account_mode: str = "off"
    account_weight_pct: float = 35.0
    timeout: int = 20
    fetcher: Callable[[str, dict[str, str] | None, int], object] = http_get_json
    _cache: dict[str, CachedSignal] = field(default_factory=dict)

    def prepare(self, symbols: list[str]) -> None:
        targets = [symbol.upper() for symbol in symbols if not self._is_cached(symbol)]
        if not targets:
            return

        with ThreadPoolExecutor(max_workers=max(self.max_workers, 1)) as executor:
            future_map = {executor.submit(self._fetch_symbol, symbol): symbol for symbol in targets}
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    signal = future.result()
                except Exception:  # noqa: BLE001
                    signal = None
                self._cache[symbol] = CachedSignal(
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds),
                    signal=signal,
                )

    def get(self, symbol: str) -> CommunitySignal | None:
        cached = self._cache.get(symbol.upper())
        if cached and cached.expires_at > datetime.now(timezone.utc):
            return cached.signal
        try:
            signal = self._fetch_symbol(symbol.upper())
        except Exception:  # noqa: BLE001
            signal = None
        self._cache[symbol.upper()] = CachedSignal(
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds),
            signal=signal,
        )
        return signal

    def _is_cached(self, symbol: str) -> bool:
        cached = self._cache.get(symbol.upper())
        return bool(cached and cached.expires_at > datetime.now(timezone.utc))

    def _fetch_symbol(self, symbol: str) -> CommunitySignal | None:
        headers = {"Authorization": f"Bearer {self.bearer_token}", "User-Agent": "trade-signal-app/0.2"}
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=self.recent_window_hours)
        time_params = {
            "start_time": start_time.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "end_time": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        general_query = self.build_query(symbol)
        general_mentions, general_texts = self._fetch_sample(general_query, headers, time_params)

        tracked_accounts = sanitize_account_names(self.tracked_accounts)
        if not tracked_accounts or self.account_mode == "off":
            return self._signal_from_sample(
                mentions=general_mentions,
                texts=general_texts,
                source="x",
            )

        account_query = self.build_account_query(symbol, tracked_accounts)
        account_mentions, account_texts = self._fetch_sample(account_query, headers, time_params)
        if self.account_mode == "only":
            return self._signal_from_sample(
                mentions=account_mentions,
                texts=account_texts,
                source="x_accounts",
            )

        general_signal = self._signal_from_sample(
            mentions=general_mentions,
            texts=general_texts,
            source="x",
        )
        account_signal = self._signal_from_sample(
            mentions=account_mentions,
            texts=account_texts,
            source="x_accounts",
        )
        if general_signal is None:
            return account_signal
        if account_signal is None:
            return general_signal

        account_weight = max(0.0, min(self.account_weight_pct, 100.0)) / 100
        blended_score = (general_signal.score * (1 - account_weight)) + (account_signal.score * account_weight)
        blended_mentions = (general_signal.mentions or 0) + (account_signal.mentions or 0)
        blended_samples = (general_signal.sample_size or 0) + (account_signal.sample_size or 0)
        blended_sentiment = (
            ((general_signal.sentiment or 0.0) * (1 - account_weight))
            + ((account_signal.sentiment or 0.0) * account_weight)
        )
        return CommunitySignal(
            score=round(blended_score, 2),
            source="x+x_accounts",
            mentions=blended_mentions,
            sentiment=round(blended_sentiment, 4),
            sample_size=blended_samples,
        )

    def build_query(self, symbol: str) -> str:
        symbol = symbol.upper()
        alias_query = self.alias_registry.get_query(symbol)
        if alias_query:
            return alias_query

        base_asset = derive_base_asset(symbol)
        names = DEFAULT_X_NAME_MAP.get(base_asset, [])
        terms = [f"${base_asset}", f"#{base_asset}", base_asset]
        terms.extend(names)
        term_clause = " OR ".join(format_x_term(term) for term in dedupe_terms(terms))
        query = f"({term_clause}) -is:retweet"
        if self.language:
            query = f"{query} lang:{self.language}"
        return query

    def build_account_query(self, symbol: str, tracked_accounts: list[str] | None = None) -> str:
        tracked_accounts = sanitize_account_names(tracked_accounts or self.tracked_accounts)
        if not tracked_accounts:
            return self.build_query(symbol)
        account_clause = " OR ".join(f"from:{account}" for account in tracked_accounts)
        return f"{self.build_query(symbol)} ({account_clause})"

    def _get_json(self, path: str, params: dict[str, str], headers: dict[str, str]) -> object:
        query = urlencode(params)
        url = f"{self.base_url.rstrip('/')}{path}?{query}"
        return self.fetcher(url, headers, self.timeout)

    def _fetch_sample(
        self,
        query: str,
        headers: dict[str, str],
        time_params: dict[str, str],
    ) -> tuple[int, list[str]]:
        counts_payload = self._get_json(
            "/2/tweets/counts/recent",
            {
                "query": query,
                "granularity": "hour",
                **time_params,
            },
            headers,
        )
        mentions = self._parse_counts(counts_payload)

        search_payload = self._get_json(
            "/2/tweets/search/recent",
            {
                "query": query,
                "max_results": str(max(10, min(self.max_results, 100))),
                "tweet.fields": "created_at",
                **time_params,
            },
            headers,
        )
        texts = self._parse_texts(search_payload)
        return mentions, texts

    def _signal_from_sample(self, *, mentions: int, texts: list[str], source: str) -> CommunitySignal | None:
        if mentions <= 0 and not texts:
            return None
        sentiment = self.score_sentiment(texts)
        score = self.compute_score(mentions=mentions, sentiment=sentiment, sample_size=len(texts))
        return CommunitySignal(
            score=round(score, 2),
            source=source,
            mentions=mentions,
            sentiment=round(sentiment, 4),
            sample_size=len(texts),
        )

    @staticmethod
    def _parse_counts(payload: object) -> int:
        if not isinstance(payload, dict):
            return 0
        meta = payload.get("meta")
        if isinstance(meta, dict) and "total_tweet_count" in meta:
            return int(meta["total_tweet_count"])
        total = 0
        for row in payload.get("data", []) if isinstance(payload.get("data"), list) else []:
            if isinstance(row, dict):
                total += int(row.get("tweet_count", 0))
        return total

    @staticmethod
    def _parse_texts(payload: object) -> list[str]:
        if not isinstance(payload, dict):
            return []
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        texts: list[str] = []
        for row in rows:
            if isinstance(row, dict) and row.get("text"):
                texts.append(str(row["text"]))
        return texts

    @staticmethod
    def score_sentiment(texts: list[str]) -> float:
        if not texts:
            return 0.0

        total = 0.0
        for text in texts:
            tokens = normalize_tokens(text)
            if not tokens:
                continue
            positive = sum(1 for token in tokens if token in POSITIVE_TERMS)
            negative = sum(1 for token in tokens if token in NEGATIVE_TERMS)
            if positive == 0 and negative == 0:
                continue
            total += (positive - negative) / max(positive + negative, 1)
        return max(-1.0, min(1.0, total / max(len(texts), 1)))

    @staticmethod
    def compute_score(mentions: int, sentiment: float, sample_size: int) -> float:
        mention_score = max(0.0, min(100.0, (math.log10(max(mentions, 1)) / math.log10(5000)) * 100))
        sentiment_score = max(0.0, min(100.0, ((sentiment + 1) / 2) * 100))
        sample_bonus = max(0.0, min(8.0, sample_size * 0.25))
        return min(100.0, (mention_score * 0.62) + (sentiment_score * 0.38) + sample_bonus)


@dataclass
class CompositeCommunityScoreProvider(CommunityScoreProvider):
    providers: list[CommunityScoreProvider]

    def prepare(self, symbols: list[str]) -> None:
        for provider in self.providers:
            provider.prepare(symbols)

    def get(self, symbol: str) -> CommunitySignal | None:
        signals = [signal for signal in (provider.get(symbol) for provider in self.providers) if signal is not None]
        if not signals:
            return None
        if len(signals) == 1:
            return signals[0]

        score = sum(signal.score for signal in signals) / len(signals)
        mention_values = [signal.mentions for signal in signals if signal.mentions is not None]
        sentiment_values = [signal.sentiment for signal in signals if signal.sentiment is not None]
        sample_values = [signal.sample_size for signal in signals if signal.sample_size is not None]
        return CommunitySignal(
            score=round(score, 2),
            source="+".join(signal.source for signal in signals),
            mentions=sum(mention_values) if mention_values else None,
            sentiment=(sum(sentiment_values) / len(sentiment_values)) if sentiment_values else None,
            sample_size=sum(sample_values) if sample_values else None,
        )


def dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        key = term.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(term)
    return result


def normalize_tokens(text: str) -> list[str]:
    cleaned = []
    current = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        else:
            if current:
                cleaned.append("".join(current))
                current = []
    if current:
        cleaned.append("".join(current))
    return cleaned


def format_x_term(term: str) -> str:
    if " " in term:
        return f'"{term}"'
    return term


def format_reddit_term(term: str) -> str:
    if " " in term:
        return f'"{term}"'
    return term


def sanitize_account_names(accounts: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in accounts:
        account = raw.strip().lstrip("@")
        if not account:
            continue
        normalized = account.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(account)
    return result


def derive_base_asset(symbol: str) -> str:
    for suffix in sorted(QUOTE_SUFFIXES, key=len, reverse=True):
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[: -len(suffix)]
    return symbol


def parse_provider_mode(value: str) -> list[str]:
    normalized = (value or "auto").strip().lower()
    if normalized == "auto":
        return ["x", "csv", "news"]
    return [item.strip().lower() for item in normalized.split(",") if item.strip()]


def build_community_provider(
    *,
    provider_mode: str,
    csv_path: Path,
    news_csv_path: Path,
    telegram_csv_path: Path,
    alias_csv_path: Path,
    x_bearer_token: str,
    x_api_base_url: str,
    community_ttl_seconds: int,
    x_recent_window_hours: int,
    x_recent_max_results: int,
    x_language: str,
    x_max_workers: int,
    reddit_api_base_url: str,
    reddit_recent_window_hours: int,
    reddit_max_results: int,
    reddit_user_agent: str,
    x_tracked_accounts: list[str] | None = None,
    x_account_mode: str = "off",
    x_account_weight_pct: float = 35.0,
) -> CommunityScoreProvider:
    providers: list[CommunityScoreProvider] = []
    requested = parse_provider_mode(provider_mode)

    if "x" in requested and x_bearer_token:
        providers.append(
            XCommunityScoreProvider(
                bearer_token=x_bearer_token,
                alias_registry=AliasRegistry(alias_csv_path=alias_csv_path),
                base_url=x_api_base_url,
                ttl_seconds=community_ttl_seconds,
                recent_window_hours=x_recent_window_hours,
                max_results=x_recent_max_results,
                language=x_language,
                max_workers=x_max_workers,
                tracked_accounts=sanitize_account_names(x_tracked_accounts or []),
                account_mode=x_account_mode,
                account_weight_pct=x_account_weight_pct,
            )
        )

    if "csv" in requested and csv_path.exists():
        providers.append(CsvCommunityScoreProvider(csv_path=csv_path))

    if "news" in requested and news_csv_path.exists():
        providers.append(NewsCommunityScoreProvider(csv_path=news_csv_path))

    if "telegram" in requested and telegram_csv_path.exists():
        providers.append(TelegramCommunityScoreProvider(csv_path=telegram_csv_path))

    if "reddit" in requested:
        providers.append(
            RedditCommunityScoreProvider(
                alias_registry=AliasRegistry(alias_csv_path=alias_csv_path),
                base_url=reddit_api_base_url,
                ttl_seconds=community_ttl_seconds,
                recent_window_hours=reddit_recent_window_hours,
                max_results=reddit_max_results,
                user_agent=reddit_user_agent,
            )
        )

    if not providers:
        return NullCommunityScoreProvider()
    if len(providers) == 1:
        return providers[0]
    return CompositeCommunityScoreProvider(providers=providers)
