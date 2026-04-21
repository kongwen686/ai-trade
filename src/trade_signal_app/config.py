from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppSettings:
    quote_asset: str = os.getenv("QUOTE_ASSET", "USDT")
    interval: str = os.getenv("SIGNAL_INTERVAL", "4h")
    kline_limit: int = int(os.getenv("KLINE_LIMIT", "240"))
    candidate_pool: int = int(os.getenv("CANDIDATE_POOL", "18"))
    min_quote_volume: float = float(os.getenv("MIN_QUOTE_VOLUME", "10000000"))
    min_trade_count: int = int(os.getenv("MIN_TRADE_COUNT", "3000"))
    scan_ttl_seconds: int = int(os.getenv("SCAN_TTL_SECONDS", "45"))
    max_workers: int = int(os.getenv("MAX_WORKERS", "6"))
    community_provider: str = os.getenv("COMMUNITY_PROVIDER", "auto")
    community_csv: Path = BASE_DIR / os.getenv("COMMUNITY_CSV", "data/community_scores.csv")
    community_news_csv: Path = BASE_DIR / os.getenv("COMMUNITY_NEWS_CSV", "data/news_sentiment.csv")
    community_telegram_csv: Path = BASE_DIR / os.getenv("COMMUNITY_TELEGRAM_CSV", "data/telegram_sentiment.csv")
    community_aliases_csv: Path = BASE_DIR / os.getenv("COMMUNITY_ALIASES_CSV", "data/social_aliases.csv")
    community_ttl_seconds: int = int(os.getenv("COMMUNITY_TTL_SECONDS", "900"))
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "")
    x_api_base_url: str = os.getenv("X_API_BASE_URL", "https://api.x.com")
    x_recent_window_hours: int = int(os.getenv("X_RECENT_WINDOW_HOURS", "24"))
    x_recent_max_results: int = int(os.getenv("X_RECENT_MAX_RESULTS", "25"))
    x_language: str = os.getenv("X_LANGUAGE", "en")
    x_max_workers: int = int(os.getenv("X_MAX_WORKERS", "4"))
    reddit_api_base_url: str = os.getenv("REDDIT_API_BASE_URL", "https://www.reddit.com")
    reddit_recent_window_hours: int = int(os.getenv("REDDIT_RECENT_WINDOW_HOURS", "24"))
    reddit_max_results: int = int(os.getenv("REDDIT_MAX_RESULTS", "25"))
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "trade-signal-app/0.2")
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    binance_recv_window_ms: float = float(os.getenv("BINANCE_RECV_WINDOW_MS", "5000"))
    runtime_config_passphrase: str = os.getenv("RUNTIME_CONFIG_PASSPHRASE", "")
    server_host: str = os.getenv("HOST", "127.0.0.1")
    server_port: int = int(os.getenv("PORT", "8000"))


SETTINGS = AppSettings()
