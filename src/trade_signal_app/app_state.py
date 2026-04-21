from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import RLock

from .binance_client import BinanceSpotGateway
from .community import build_community_provider
from .config import AppSettings
from .runtime_config import RuntimeConfig, RuntimeConfigStore
from .service import SignalScanner


class AppState:
    def __init__(self, settings: AppSettings, runtime_config_path: Path) -> None:
        self._settings = settings
        self._store = RuntimeConfigStore(runtime_config_path, passphrase=settings.runtime_config_passphrase)
        self._lock = RLock()
        self._runtime_config = self._store.load(settings)
        self._scanner = self._build_scanner(self._runtime_config)

    def snapshot(self) -> tuple[RuntimeConfig, SignalScanner]:
        with self._lock:
            return deepcopy(self._runtime_config), self._scanner

    def update_config(self, config: RuntimeConfig) -> None:
        with self._lock:
            self._runtime_config = config
            self._store.save(config)
            self._scanner = self._build_scanner(config)

    def storage_mode_label(self) -> str:
        return self._store.storage_mode_label()

    def _build_scanner(self, config: RuntimeConfig) -> SignalScanner:
        effective_settings = replace(
            self._settings,
            quote_asset=config.scan_defaults.quote_asset,
            interval=config.scan_defaults.interval,
            candidate_pool=config.scan_defaults.candidate_pool,
            min_quote_volume=config.scan_defaults.min_quote_volume,
            min_trade_count=config.scan_defaults.min_trade_count,
            community_provider=config.community_provider,
            x_bearer_token=config.x_bearer_token,
            x_api_base_url=config.x_api_base_url,
            x_recent_window_hours=config.x_recent_window_hours,
            x_recent_max_results=config.x_recent_max_results,
            x_language=config.x_language,
            reddit_api_base_url=config.reddit_api_base_url,
            reddit_recent_window_hours=config.reddit_recent_window_hours,
            reddit_max_results=config.reddit_max_results,
            reddit_user_agent=config.reddit_user_agent,
            binance_api_key=config.binance_api_key,
            binance_api_secret=config.binance_api_secret,
            binance_recv_window_ms=config.binance_recv_window_ms,
        )
        gateway = BinanceSpotGateway(
            ttl_seconds=effective_settings.scan_ttl_seconds,
            api_key=effective_settings.binance_api_key,
            api_secret=effective_settings.binance_api_secret,
            recv_window_ms=effective_settings.binance_recv_window_ms,
        )
        community_provider = build_community_provider(
            provider_mode=effective_settings.community_provider,
            csv_path=effective_settings.community_csv,
            news_csv_path=effective_settings.community_news_csv,
            telegram_csv_path=effective_settings.community_telegram_csv,
            alias_csv_path=effective_settings.community_aliases_csv,
            x_bearer_token=effective_settings.x_bearer_token,
            x_api_base_url=effective_settings.x_api_base_url,
            community_ttl_seconds=effective_settings.community_ttl_seconds,
            x_recent_window_hours=effective_settings.x_recent_window_hours,
            x_recent_max_results=effective_settings.x_recent_max_results,
            x_language=effective_settings.x_language,
            x_max_workers=effective_settings.x_max_workers,
            reddit_api_base_url=effective_settings.reddit_api_base_url,
            reddit_recent_window_hours=effective_settings.reddit_recent_window_hours,
            reddit_max_results=effective_settings.reddit_max_results,
            reddit_user_agent=effective_settings.reddit_user_agent,
            x_tracked_accounts=config.x_tracked_accounts,
            x_account_mode=config.x_account_mode,
            x_account_weight_pct=config.x_account_weight_pct,
        )
        return SignalScanner(
            gateway=gateway,
            community_provider=community_provider,
            settings=effective_settings,
        )
