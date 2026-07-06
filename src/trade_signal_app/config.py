from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_X_TRACKED_ACCOUNTS = (
    "lookonchain",
    "WuBlockchain",
    "whale_alert",
    "BTCtreasuries",
    "arkham",
    "glassnode",
    "cryptoquant_com",
    "ki_young_ju",
    "SantimentData",
    "tier10k",
    "WatcherGuru",
    "Grayscale",
    "saylor",
    "Strategy",
    "iShares",
    "vaneck_us",
    "ARKInvest",
    "21shares_us",
    "Bitcoin",
    "ethereum",
    "solana",
    "BNBCHAIN",
    "Ripple",
    "chainlink",
    "SuiNetwork",
    "ton_blockchain",
    "CryptoCred",
    "Pentosh1",
    "DaanCrypto",
    "scottmelker",
    "BobLoukas",
    "CryptoHayes",
    "APompliano",
)


def parse_env_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


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
    exchange_community_urls: list[str] = field(
        default_factory=lambda: parse_env_list(
            os.getenv(
                "EXCHANGE_COMMUNITY_URLS",
                "\n".join(
                    (
                        "https://www.binance.com/en/support/announcement",
                        "https://www.binance.com/en/support/announcement/new-cryptocurrency-listing?c=48",
                        "https://www.okx.com/en-us/help/section/announcements-latest-announcements",
                        "https://www.okx.com/en-us/help/section/new-listings",
                    )
                ),
            )
        )
    )
    x_provider: str = os.getenv("X_PROVIDER", "official_api")
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "")
    x_api_base_url: str = os.getenv("X_API_BASE_URL", "https://api.x.com")
    x_nitter_base_url: str = os.getenv("X_NITTER_BASE_URL", "")
    x_session_command: str = os.getenv("X_SESSION_COMMAND", "")
    x_recent_window_hours: int = int(os.getenv("X_RECENT_WINDOW_HOURS", "24"))
    x_recent_max_results: int = int(os.getenv("X_RECENT_MAX_RESULTS", "25"))
    x_language: str = os.getenv("X_LANGUAGE", "en")
    x_max_workers: int = int(os.getenv("X_MAX_WORKERS", "4"))
    x_tracked_accounts: list[str] = field(
        default_factory=lambda: parse_env_list(
            os.getenv("X_TRACKED_ACCOUNTS", "\n".join(DEFAULT_X_TRACKED_ACCOUNTS))
        )
    )
    reddit_api_base_url: str = os.getenv("REDDIT_API_BASE_URL", "https://www.reddit.com")
    reddit_recent_window_hours: int = int(os.getenv("REDDIT_RECENT_WINDOW_HOURS", "24"))
    reddit_max_results: int = int(os.getenv("REDDIT_MAX_RESULTS", "25"))
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "trade-signal-app/0.2")
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    binance_recv_window_ms: float = float(os.getenv("BINANCE_RECV_WINDOW_MS", "5000"))
    okx_api_key: str = os.getenv("OKX_API_KEY", "")
    okx_api_secret: str = os.getenv("OKX_API_SECRET", "")
    okx_api_passphrase: str = os.getenv("OKX_API_PASSPHRASE", "")
    market_data_preset: str = os.getenv("MARKET_DATA_PRESET", "binance_public")
    onchain_data_preset: str = os.getenv("ONCHAIN_DATA_PRESET", "open_multichain_keyless")
    onchain_api_key: str = os.getenv("ONCHAIN_API_KEY", "")
    onchain_api_base_url: str = os.getenv("ONCHAIN_API_BASE_URL", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    llm_api_key: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.5"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.5")
    feishu_webhook_url: str = os.getenv("FEISHU_WEBHOOK_URL", "")
    exchange_intel_csv: Path = BASE_DIR / os.getenv("EXCHANGE_INTEL_CSV", "data/exchange_intel.csv")
    onchain_events_csv: Path = BASE_DIR / os.getenv("ONCHAIN_EVENTS_CSV", "data/onchain_events.csv")
    futures_basis_csv: Path = BASE_DIR / os.getenv("FUTURES_BASIS_CSV", "data/futures_basis.csv")
    futures_funding_csv: Path = BASE_DIR / os.getenv("FUTURES_FUNDING_CSV", "data/futures_funding.csv")
    runtime_config_passphrase: str = os.getenv("RUNTIME_CONFIG_PASSPHRASE", "")
    server_host: str = os.getenv("HOST", "127.0.0.1")
    server_port: int = int(os.getenv("PORT", "8000"))


SETTINGS = AppSettings()
