from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import base64
import hashlib
import hmac
import json
import os

from .config import AppSettings

RUNTIME_CONFIG_TEMPLATE_VERSION = 1
RUNTIME_CONFIG_ENCRYPTED_KIND = "runtime_config_encrypted"
RUNTIME_CONFIG_ENCRYPTED_VERSION = 1
SECRET_FIELDS = ("binance_api_key", "binance_api_secret", "x_bearer_token")


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
    reddit_api_base_url: str = "https://www.reddit.com"
    reddit_recent_window_hours: int = 24
    reddit_max_results: int = 25
    reddit_user_agent: str = "trade-signal-app/0.2"
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
            reddit_api_base_url=settings.reddit_api_base_url,
            reddit_recent_window_hours=settings.reddit_recent_window_hours,
            reddit_max_results=settings.reddit_max_results,
            reddit_user_agent=settings.reddit_user_agent,
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
            reddit_api_base_url=str(payload.get("reddit_api_base_url", defaults.reddit_api_base_url)),
            reddit_recent_window_hours=int(payload.get("reddit_recent_window_hours", defaults.reddit_recent_window_hours)),
            reddit_max_results=int(payload.get("reddit_max_results", defaults.reddit_max_results)),
            reddit_user_agent=str(payload.get("reddit_user_agent", defaults.reddit_user_agent)),
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

    def to_template_payload(self, *, include_secrets: bool = False) -> dict[str, object]:
        payload = self.to_dict()
        if not include_secrets:
            for field_name in SECRET_FIELDS:
                payload[field_name] = ""
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
