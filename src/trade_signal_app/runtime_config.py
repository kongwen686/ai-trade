from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import base64
import hashlib
import hmac
import json
import os

from .config import AppSettings, DEFAULT_X_TRACKED_ACCOUNTS
from .entry_filters import (
    ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT,
    ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT,
    ANTI_CHASE_DEFAULT_MAX_RSI,
    STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT,
    STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT,
    STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO,
    STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH,
    STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT,
    STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT,
)

RUNTIME_CONFIG_TEMPLATE_VERSION = 1
RUNTIME_CONFIG_ENCRYPTED_KIND = "runtime_config_encrypted"
RUNTIME_CONFIG_ENCRYPTED_VERSION = 1
TRADINGVIEW_BARS_MIN = 100
TRADINGVIEW_BARS_DEFAULT = 10000
TRADINGVIEW_BARS_MAX = 100000
AUTOTRADE_EXIT_PROFILES = {"balanced", "leveraged_conservative", "trend_following"}
SECRET_FIELDS = (
    "binance_api_key",
    "binance_api_secret",
    "okx_api_key",
    "okx_api_secret",
    "okx_api_passphrase",
    "x_bearer_token",
    "onchain_api_key",
    "tradingview_password",
    "llm_api_key",
    "openai_api_key",
    "feishu_webhook_url",
)


def _pbkdf2_key_material(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 200_000, dklen=64)


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    offset = 0
    while offset < len(data):
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        chunk = data[offset : offset + len(block)]
        chunks.append(bytes(left ^ right for left, right in zip(chunk, block)))
        offset += len(block)
        counter += 1
    return b"".join(chunks)


def encrypt_runtime_config_payload(payload: dict[str, object], passphrase: str) -> dict[str, object]:
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(16)
    key_material = _pbkdf2_key_material(passphrase, salt)
    encryption_key = key_material[:32]
    mac_key = key_material[32:]
    ciphertext = _xor_stream(plaintext, encryption_key, nonce)
    mac = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        "kind": RUNTIME_CONFIG_ENCRYPTED_KIND,
        "version": RUNTIME_CONFIG_ENCRYPTED_VERSION,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "mac": base64.b64encode(mac).decode("ascii"),
    }


def decrypt_runtime_config_payload(payload: dict[str, object], passphrase: str) -> dict[str, object]:
    try:
        salt = base64.b64decode(str(payload["salt"]))
        nonce = base64.b64decode(str(payload["nonce"]))
        ciphertext = base64.b64decode(str(payload["ciphertext"]))
        expected_mac = base64.b64decode(str(payload["mac"]))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("加密配置文件格式无效。") from exc

    key_material = _pbkdf2_key_material(passphrase, salt)
    encryption_key = key_material[:32]
    mac_key = key_material[32:]
    actual_mac = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        raise ValueError("运行配置解密失败，请检查 RUNTIME_CONFIG_PASSPHRASE 是否正确。")

    plaintext = _xor_stream(ciphertext, encryption_key, nonce)
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("加密配置解密后不是合法 JSON。") from exc
    if not isinstance(decoded, dict):
        raise ValueError("加密配置解密后根节点必须是 JSON 对象。")
    return decoded


@dataclass
class ScanDefaults:
    quote_asset: str = "USDT"
    interval: str = "4h"
    candidate_pool: int = 18
    min_quote_volume: float = 10_000_000
    min_trade_count: int = 3000


@dataclass
class BacktestDefaults:
    preset: str = "custom"
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
    volatility_filter_enabled: bool = True
    block_extreme_volatility: bool = True
    max_entry_volatility_percentile: float = 92.0
    max_entry_volatility_ratio: float = 2.0


@dataclass
class AutoTradeDefaults:
    enabled: bool = False
    mode: str = "paper"
    paper_enabled: bool = False
    live_enabled: bool = False
    execution_exchange: str = "binance"
    quote_order_qty: float = 25.0
    leverage: float = 1.0
    risk_per_trade_pct: float = 4.0
    exit_profile: str = "balanced"
    max_open_positions: int = 3
    max_total_quote_exposure: float = 100.0
    score_threshold: float = 75.0
    min_volume_ratio: float = 1.10
    min_buy_pressure: float = 0.52
    anti_chase_enabled: bool = True
    max_entry_rsi: float = ANTI_CHASE_DEFAULT_MAX_RSI
    max_entry_price_vs_ema20_pct: float = ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT
    max_entry_recent_change_pct: float = ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT
    structure_filter_enabled: bool = True
    max_entry_support_distance_pct: float = STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT
    min_entry_support_strength: float = STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH
    min_entry_risk_reward_ratio: float = STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO
    min_entry_resistance_distance_pct: float = STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT
    volatility_filter_enabled: bool = True
    block_extreme_volatility: bool = True
    max_entry_volatility_percentile: float = 92.0
    max_entry_volatility_ratio: float = 2.0
    support_stop_buffer_pct: float = STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT
    resistance_take_profit_buffer_pct: float = STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT
    stop_loss_pct: float = 4.0
    take_profit_pct: float = 9.0
    profit_protection_enabled: bool = True
    profit_protection_trigger_pct: float = 3.0
    profit_protection_lock_pct: float = 0.5
    trailing_stop_pct: float = 2.0
    trend_hold_enabled: bool = True
    trend_hold_min_score: float = 82.0
    trend_hold_min_volume_ratio: float = 1.25
    trend_hold_min_buy_pressure: float = 0.56
    emergency_drawdown_pct: float = 2.5
    emergency_alert_global_cooldown_minutes: int = 60
    emergency_alert_symbol_cooldown_minutes: int = 720
    emergency_low_liquidity_quote_volume: float = 10_000_000
    emergency_low_liquidity_drawdown_multiplier: float = 2.0
    emergency_low_liquidity_min_score: float = 85.0
    cooldown_minutes: int = 240
    order_test_only: bool = True


@dataclass
class CarryPaperDefaults:
    enabled: bool = False
    notional_per_leg: float = 100.0
    min_basis_bps: float = 25.0
    min_funding_bps: float = 1.0
    exit_basis_bps: float = 5.0
    exit_funding_bps: float = 0.0
    stop_basis_bps: float = 35.0
    max_holding_hours: int = 168
    max_positions: int = 3
    fee_bps_per_leg: float = 10.0
    slippage_bps_per_leg: float = 2.0


def _payload_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no"}
    return bool(value)


def _autotrade_defaults_from_payload(defaults: "RuntimeConfig", payload: object) -> AutoTradeDefaults:
    raw_payload = payload if isinstance(payload, dict) else {}
    raw = {
        **asdict(defaults.autotrade_defaults),
        **raw_payload,
    }
    mode = str(raw.get("mode") or "paper").strip() or "paper"
    enabled = _payload_bool(raw.get("enabled", False))

    if "paper_enabled" in raw_payload:
        paper_enabled = _payload_bool(raw.get("paper_enabled"))
    else:
        paper_enabled = enabled and mode == "paper"
    if "live_enabled" in raw_payload:
        live_enabled = _payload_bool(raw.get("live_enabled"))
    else:
        live_enabled = enabled and mode == "live"

    raw["mode"] = mode
    raw["enabled"] = enabled or paper_enabled or live_enabled
    raw["paper_enabled"] = paper_enabled
    raw["live_enabled"] = live_enabled
    return AutoTradeDefaults(**raw)


@dataclass
class IntelligenceDefaults:
    enabled: bool = True
    llm_enabled: bool = False
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-5.5"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    min_intel_severity: float = 60.0
    min_spread_bps: float = 12.0
    whale_transfer_threshold_usd: float = 5_000_000.0


@dataclass
class RuntimeConfig:
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_recv_window_ms: float = 5000.0
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_api_passphrase: str = ""
    market_data_preset: str = "binance_public"
    tradingview_username: str = ""
    tradingview_password: str = ""
    tradingview_exchange: str = "BINANCE"
    tradingview_symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    tradingview_interval: str = "4h"
    tradingview_bars: int = TRADINGVIEW_BARS_DEFAULT
    tradingview_cache_enabled: bool = True
    onchain_data_preset: str = "open_multichain_keyless"
    onchain_api_key: str = ""
    onchain_api_base_url: str = ""
    community_provider: str = "auto"
    x_provider: str = "official_api"
    x_bearer_token: str = ""
    x_api_base_url: str = "https://api.x.com"
    x_nitter_base_url: str = ""
    x_session_command: str = ""
    x_recent_window_hours: int = 24
    x_recent_max_results: int = 25
    x_language: str = "en"
    x_account_mode: str = "off"
    x_account_weight_pct: float = 35.0
    x_tracked_accounts: list[str] = field(default_factory=lambda: list(DEFAULT_X_TRACKED_ACCOUNTS))
    reddit_api_base_url: str = "https://www.reddit.com"
    reddit_recent_window_hours: int = 24
    reddit_max_results: int = 25
    reddit_user_agent: str = "trade-signal-app/0.2"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-5.5"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    feishu_webhook_url: str = ""
    scan_defaults: ScanDefaults = field(default_factory=ScanDefaults)
    backtest_defaults: BacktestDefaults = field(default_factory=BacktestDefaults)
    autotrade_defaults: AutoTradeDefaults = field(default_factory=AutoTradeDefaults)
    carry_paper_defaults: CarryPaperDefaults = field(default_factory=CarryPaperDefaults)
    intelligence_defaults: IntelligenceDefaults = field(default_factory=IntelligenceDefaults)

    @classmethod
    def default_from_settings(cls, settings: AppSettings) -> "RuntimeConfig":
        return cls(
            binance_api_key=settings.binance_api_key,
            binance_api_secret=settings.binance_api_secret,
            binance_recv_window_ms=settings.binance_recv_window_ms,
            okx_api_key=settings.okx_api_key,
            okx_api_secret=settings.okx_api_secret,
            okx_api_passphrase=settings.okx_api_passphrase,
            market_data_preset=settings.market_data_preset,
            onchain_data_preset=settings.onchain_data_preset,
            onchain_api_key=settings.onchain_api_key,
            onchain_api_base_url=settings.onchain_api_base_url,
            community_provider=settings.community_provider,
            x_provider=settings.x_provider,
            x_bearer_token=settings.x_bearer_token,
            x_api_base_url=settings.x_api_base_url,
            x_nitter_base_url=settings.x_nitter_base_url,
            x_session_command=settings.x_session_command,
            x_recent_window_hours=settings.x_recent_window_hours,
            x_recent_max_results=settings.x_recent_max_results,
            x_language=settings.x_language,
            x_tracked_accounts=list(settings.x_tracked_accounts),
            reddit_api_base_url=settings.reddit_api_base_url,
            reddit_recent_window_hours=settings.reddit_recent_window_hours,
            reddit_max_results=settings.reddit_max_results,
            reddit_user_agent=settings.reddit_user_agent,
            llm_provider=settings.llm_provider,
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
            llm_model=settings.llm_model,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            feishu_webhook_url=settings.feishu_webhook_url,
            intelligence_defaults=IntelligenceDefaults(
                llm_provider=settings.llm_provider,
                llm_api_key=settings.llm_api_key,
                llm_base_url=settings.llm_base_url,
                llm_model=settings.llm_model,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
            ),
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
        autotrade_payload = payload.get("autotrade_defaults")
        carry_paper_payload = payload.get("carry_paper_defaults")
        intelligence_payload = payload.get("intelligence_defaults")
        intelligence_dict = intelligence_payload if isinstance(intelligence_payload, dict) else {}
        llm_provider = str(payload.get("llm_provider", intelligence_dict.get("llm_provider", defaults.llm_provider)))
        llm_api_key = str(payload.get("llm_api_key", payload.get("openai_api_key", intelligence_dict.get("llm_api_key", defaults.llm_api_key))))
        llm_base_url = str(payload.get("llm_base_url", intelligence_dict.get("llm_base_url", defaults.llm_base_url)))
        llm_model = str(payload.get("llm_model", payload.get("openai_model", intelligence_dict.get("llm_model", defaults.llm_model))))
        tradingview_symbols_raw = payload.get("tradingview_symbols", defaults.tradingview_symbols)
        if isinstance(tradingview_symbols_raw, list):
            tradingview_symbols = [str(item).strip().upper() for item in tradingview_symbols_raw if str(item).strip()]
        elif isinstance(tradingview_symbols_raw, str):
            tradingview_symbols = [
                item.strip().upper()
                for item in tradingview_symbols_raw.replace(",", "\n").splitlines()
                if item.strip()
            ]
        else:
            tradingview_symbols = defaults.tradingview_symbols
        return cls(
            binance_api_key=str(payload.get("binance_api_key", defaults.binance_api_key)),
            binance_api_secret=str(payload.get("binance_api_secret", defaults.binance_api_secret)),
            binance_recv_window_ms=float(payload.get("binance_recv_window_ms", defaults.binance_recv_window_ms)),
            okx_api_key=str(payload.get("okx_api_key", defaults.okx_api_key)),
            okx_api_secret=str(payload.get("okx_api_secret", defaults.okx_api_secret)),
            okx_api_passphrase=str(payload.get("okx_api_passphrase", defaults.okx_api_passphrase)),
            market_data_preset=str(payload.get("market_data_preset", defaults.market_data_preset)),
            tradingview_username=str(payload.get("tradingview_username", defaults.tradingview_username)),
            tradingview_password=str(payload.get("tradingview_password", defaults.tradingview_password)),
            tradingview_exchange=str(payload.get("tradingview_exchange", defaults.tradingview_exchange)),
            tradingview_symbols=tradingview_symbols,
            tradingview_interval=str(payload.get("tradingview_interval", defaults.tradingview_interval)),
            tradingview_bars=int(payload.get("tradingview_bars", defaults.tradingview_bars)),
            tradingview_cache_enabled=bool(payload.get("tradingview_cache_enabled", defaults.tradingview_cache_enabled)),
            onchain_data_preset=str(payload.get("onchain_data_preset", defaults.onchain_data_preset)),
            onchain_api_key=str(payload.get("onchain_api_key", defaults.onchain_api_key)),
            onchain_api_base_url=str(payload.get("onchain_api_base_url", defaults.onchain_api_base_url)),
            community_provider=str(payload.get("community_provider", defaults.community_provider)),
            x_provider=str(payload.get("x_provider", defaults.x_provider)),
            x_bearer_token=str(payload.get("x_bearer_token", defaults.x_bearer_token)),
            x_api_base_url=str(payload.get("x_api_base_url", defaults.x_api_base_url)),
            x_nitter_base_url=str(payload.get("x_nitter_base_url", defaults.x_nitter_base_url)),
            x_session_command=str(payload.get("x_session_command", defaults.x_session_command)),
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
            reddit_api_base_url=str(payload.get("reddit_api_base_url", defaults.reddit_api_base_url)),
            reddit_recent_window_hours=int(payload.get("reddit_recent_window_hours", defaults.reddit_recent_window_hours)),
            reddit_max_results=int(payload.get("reddit_max_results", defaults.reddit_max_results)),
            reddit_user_agent=str(payload.get("reddit_user_agent", defaults.reddit_user_agent)),
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            openai_api_key=str(payload.get("openai_api_key", defaults.openai_api_key)),
            openai_model=str(payload.get("openai_model", defaults.openai_model)),
            feishu_webhook_url=str(payload.get("feishu_webhook_url", defaults.feishu_webhook_url)),
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
            autotrade_defaults=_autotrade_defaults_from_payload(defaults, autotrade_payload),
            carry_paper_defaults=CarryPaperDefaults(
                **{
                    **asdict(defaults.carry_paper_defaults),
                    **(carry_paper_payload if isinstance(carry_paper_payload, dict) else {}),
                }
            ),
            intelligence_defaults=IntelligenceDefaults(
                **{
                    **asdict(defaults.intelligence_defaults),
                    **intelligence_dict,
                    "llm_provider": llm_provider,
                    "llm_api_key": llm_api_key,
                    "llm_base_url": llm_base_url,
                    "llm_model": llm_model,
                    "openai_api_key": str(payload.get("openai_api_key", defaults.openai_api_key)),
                    "openai_model": str(payload.get("openai_model", defaults.openai_model)),
                }
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_template_payload(self, *, include_secrets: bool = False) -> dict[str, object]:
        payload = self.to_dict()
        if not include_secrets:
            for field_name in SECRET_FIELDS:
                payload[field_name] = ""
            intelligence_payload = payload.get("intelligence_defaults")
            if isinstance(intelligence_payload, dict):
                intelligence_payload["llm_api_key"] = ""
                intelligence_payload["openai_api_key"] = ""
        return {
            "kind": "runtime_config_template",
            "version": RUNTIME_CONFIG_TEMPLATE_VERSION,
            "include_secrets": include_secrets,
            "config": payload,
        }

    @classmethod
    def from_template_payload(
        cls,
        payload: dict[str, object],
        settings: AppSettings,
        *,
        current_config: "RuntimeConfig | None" = None,
    ) -> "RuntimeConfig":
        raw_config = payload.get("config", payload)
        if not isinstance(raw_config, dict):
            raise ValueError("配置模板缺少 config 对象。")

        merged_payload = dict(raw_config)
        if current_config is not None:
            for field_name in SECRET_FIELDS:
                incoming = merged_payload.get(field_name)
                if incoming is None or str(incoming).strip() == "":
                    merged_payload[field_name] = getattr(current_config, field_name)
        return cls.from_dict(merged_payload, settings)


class RuntimeConfigStore:
    def __init__(self, path: Path, passphrase: str = "") -> None:
        self.path = path
        self.passphrase = passphrase

    def storage_mode_label(self) -> str:
        return "Encrypted" if self.passphrase else "Local"

    def load(self, settings: AppSettings) -> RuntimeConfig:
        if not self.path.exists():
            return RuntimeConfig.default_from_settings(settings)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return RuntimeConfig.default_from_settings(settings)
        if payload.get("kind") == RUNTIME_CONFIG_ENCRYPTED_KIND:
            if not self.passphrase:
                raise ValueError("运行配置文件已加密，请先设置环境变量 RUNTIME_CONFIG_PASSPHRASE。")
            payload = decrypt_runtime_config_payload(payload, self.passphrase)
        return RuntimeConfig.from_dict(payload, settings)

    def save(self, config: RuntimeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object]
        if self.passphrase:
            payload = encrypt_runtime_config_payload(config.to_dict(), self.passphrase)
        else:
            payload = config.to_dict()
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
