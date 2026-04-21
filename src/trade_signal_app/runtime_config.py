from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

from .config import AppSettings


@dataclass
class ScanDefaults:
    quote_asset: str = "USDT"
    interval: str = "4h"
    candidate_pool: int = 18
    min_quote_volume: float = 10_000_000
    min_trade_count: int = 3000


@dataclass
class BacktestDefaults:
    archives: str = ""
    lookback_bars: int = 240
    score_threshold: float = 70.0
    holding_periods: str = "3,6,12"
    portfolio_top_n: int = 0
    cooldown_bars: int = 0
    stop_loss_pct: float = 4.0
    take_profit_pct: float = 9.0
    max_holding_bars: int = 12
    fee_bps: float = 10.0
    fee_model: str = "flat"
    fee_source: str = "manual"
    maker_fee_bps: float = 10.0
    taker_fee_bps: float = 10.0
    entry_fee_role: str = "taker"
    exit_fee_role: str = "taker"
    fee_discount_pct: float = 0.0
    no_binance_discount: bool = False
    slippage_bps: float = 5.0
    slippage_model: str = "fixed"
    min_slippage_bps: float = 2.0
    max_slippage_bps: float = 25.0
    slippage_window_bars: int = 20
    capital_fraction_pct: float = 100.0
    max_portfolio_exposure_pct: float = 100.0
    max_concurrent_positions: int = 0
    min_volume_ratio: float = 1.10
    min_buy_pressure: float = 0.52
    min_rsi: float = 45.0
    max_rsi: float = 72.0
    no_kdj_confirmation: bool = False


@dataclass
class RuntimeConfig:
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_recv_window_ms: float = 5000.0
    community_provider: str = "auto"
    x_bearer_token: str = ""
    x_api_base_url: str = "https://api.x.com"
    x_recent_window_hours: int = 24
    x_recent_max_results: int = 25
    x_language: str = "en"
    x_account_mode: str = "off"
    x_account_weight_pct: float = 35.0
    x_tracked_accounts: list[str] = field(default_factory=list)
    scan_defaults: ScanDefaults = field(default_factory=ScanDefaults)
    backtest_defaults: BacktestDefaults = field(default_factory=BacktestDefaults)

    @classmethod
    def default_from_settings(cls, settings: AppSettings) -> "RuntimeConfig":
        return cls(
            binance_api_key=settings.binance_api_key,
            binance_api_secret=settings.binance_api_secret,
            binance_recv_window_ms=settings.binance_recv_window_ms,
            community_provider=settings.community_provider,
            x_bearer_token=settings.x_bearer_token,
            x_api_base_url=settings.x_api_base_url,
            x_recent_window_hours=settings.x_recent_window_hours,
            x_recent_max_results=settings.x_recent_max_results,
            x_language=settings.x_language,
            scan_defaults=ScanDefaults(
                quote_asset=settings.quote_asset,
                interval=settings.interval,
                candidate_pool=settings.candidate_pool,
                min_quote_volume=settings.min_quote_volume,
                min_trade_count=settings.min_trade_count,
            ),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, object], settings: AppSettings) -> "RuntimeConfig":
        defaults = cls.default_from_settings(settings)
        scan_payload = payload.get("scan_defaults")
        backtest_payload = payload.get("backtest_defaults")
        return cls(
            binance_api_key=str(payload.get("binance_api_key", defaults.binance_api_key)),
            binance_api_secret=str(payload.get("binance_api_secret", defaults.binance_api_secret)),
            binance_recv_window_ms=float(payload.get("binance_recv_window_ms", defaults.binance_recv_window_ms)),
            community_provider=str(payload.get("community_provider", defaults.community_provider)),
            x_bearer_token=str(payload.get("x_bearer_token", defaults.x_bearer_token)),
            x_api_base_url=str(payload.get("x_api_base_url", defaults.x_api_base_url)),
            x_recent_window_hours=int(payload.get("x_recent_window_hours", defaults.x_recent_window_hours)),
            x_recent_max_results=int(payload.get("x_recent_max_results", defaults.x_recent_max_results)),
            x_language=str(payload.get("x_language", defaults.x_language)),
            x_account_mode=str(payload.get("x_account_mode", defaults.x_account_mode)),
            x_account_weight_pct=float(payload.get("x_account_weight_pct", defaults.x_account_weight_pct)),
            x_tracked_accounts=[
                str(item).strip()
                for item in payload.get("x_tracked_accounts", defaults.x_tracked_accounts)
                if str(item).strip()
            ]
            if isinstance(payload.get("x_tracked_accounts", defaults.x_tracked_accounts), list)
            else defaults.x_tracked_accounts,
            scan_defaults=ScanDefaults(
                **{
                    **asdict(defaults.scan_defaults),
                    **(scan_payload if isinstance(scan_payload, dict) else {}),
                }
            ),
            backtest_defaults=BacktestDefaults(
                **{
                    **asdict(defaults.backtest_defaults),
                    **(backtest_payload if isinstance(backtest_payload, dict) else {}),
                }
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RuntimeConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, settings: AppSettings) -> RuntimeConfig:
        if not self.path.exists():
            return RuntimeConfig.default_from_settings(settings)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return RuntimeConfig.default_from_settings(settings)
        return RuntimeConfig.from_dict(payload, settings)

    def save(self, config: RuntimeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
