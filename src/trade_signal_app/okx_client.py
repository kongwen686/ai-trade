from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.client import HTTPException, IncompleteRead
import base64
import hashlib
import hmac
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .ssl_compat import create_default_ssl_context


class OKXAPIError(RuntimeError):
    pass


@dataclass
class TimedValue:
    expires_at: datetime
    value: object


class OKXSpotGateway:
    exchange_name = "OKX"

    def __init__(
        self,
        ttl_seconds: int = 45,
        base_url: str = "https://www.okx.com",
        timeout: int = 20,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, TimedValue] = {}
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._ssl_context = create_default_ssl_context()
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase

    def _cache_get(self, key: str) -> object | None:
        cached = self._cache.get(key)
        if cached and cached.expires_at > datetime.now(timezone.utc):
            return cached.value
        return None

    def _cache_set(self, key: str, value: object) -> object:
        self._cache[key] = TimedValue(
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._ttl_seconds),
            value=value,
        )
        return value

    def has_user_data_auth(self) -> bool:
        return bool(self._api_key and self._api_secret and self._passphrase)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _okx_inst_id(symbol: str) -> str:
        normalized = symbol.upper().strip()
        if "-" in normalized:
            return normalized
        for quote in ("USDT", "USDC", "FDUSD", "BUSD", "BTC", "ETH"):
            if normalized.endswith(quote) and len(normalized) > len(quote):
                return f"{normalized[:-len(quote)]}-{quote}"
        return normalized

    @staticmethod
    def _compact_symbol(inst_id: str) -> str:
        return inst_id.upper().replace("-", "")

    def _headers(self, method: str, request_path: str, body: str) -> dict[str, str]:
        timestamp = self._timestamp()
        pre_hash = f"{timestamp}{method.upper()}{request_path}{body}"
        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode("utf-8"),
                pre_hash.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        return {
            "User-Agent": "trade-signal-app/0.1",
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
        }

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
        *,
        signed: bool = False,
    ) -> object:
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        request_path = f"{path}?{query}" if query else path
        body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")) if payload is not None else ""
        url = f"{self._base_url}{request_path}"
        headers = {"User-Agent": "trade-signal-app/0.1", "Content-Type": "application/json"}
        if signed:
            if not self.has_user_data_auth():
                raise ValueError("OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE 未完整配置，无法访问账户级接口。")
            headers = self._headers(method, request_path, body)
        request = Request(
            url,
            data=body.encode("utf-8") if body else None,
            method=method.upper(),
            headers=headers,
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self._timeout, context=self._ssl_context) as response:
                    data = json.load(response)
                if isinstance(data, dict) and str(data.get("code", "0")) not in {"0", ""}:
                    message = str(data.get("msg") or data.get("code") or "OKX API error")
                    raise OKXAPIError(message)
                return data
            except HTTPError as exc:
                detail = self._extract_http_error_detail(exc)
                last_error = OKXAPIError(f"HTTP {exc.code}" + (f"，{detail}" if detail else ""))
                if signed or attempt >= 2:
                    break
                time.sleep(0.2 * (attempt + 1))
            except (HTTPException, IncompleteRead, TimeoutError, URLError, OSError, json.JSONDecodeError, OKXAPIError) as exc:
                last_error = exc
                if signed or attempt >= 2:
                    break
                time.sleep(0.2 * (attempt + 1))
        raise OKXAPIError(f"OKX API 请求失败：{last_error}") from last_error

    def balance(self, quote_assets: set[str] | None = None) -> dict:
        ccy = ",".join(sorted({asset.upper() for asset in quote_assets or set()}))
        cache_key = f"balance:{ccy}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        params = {"ccy": ccy} if ccy else None
        data = self._request_json("GET", "/api/v5/account/balance", params=params, signed=True)
        return self._cache_set(cache_key, data)  # type: ignore[return-value]

    def account_status(self, quote_assets: set[str] | None = None) -> dict[str, object]:
        quote_assets = {asset.upper() for asset in (quote_assets or {"USDT", "USDC", "FDUSD", "BUSD"})}
        if not self.has_user_data_auth():
            return {
                "exchange": "OKX",
                "configured": False,
                "authenticated": False,
                "can_trade": False,
                "status": "not_configured",
                "message": "OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE 未完整配置。",
                "balances": [],
                "quote_available": 0.0,
            }
        try:
            payload = self.balance(quote_assets)
        except Exception as exc:  # noqa: BLE001
            return {
                "exchange": "OKX",
                "configured": True,
                "authenticated": False,
                "can_trade": False,
                "status": "auth_failed",
                "message": str(exc),
                "balances": [],
                "quote_available": 0.0,
            }
        balances: list[dict[str, object]] = []
        quote_available = 0.0
        for account in payload.get("data", []) if isinstance(payload, dict) else []:
            if not isinstance(account, dict):
                continue
            for item in account.get("details", []):
                if not isinstance(item, dict):
                    continue
                asset = str(item.get("ccy", "")).upper()
                free = float(item.get("availBal") or item.get("availEq") or item.get("cashBal") or 0.0)
                locked = float(item.get("frozenBal") or 0.0)
                if free <= 0 and locked <= 0:
                    continue
                balances.append({"asset": asset, "free": free, "locked": locked})
                if asset in quote_assets:
                    quote_available += free
        return {
            "exchange": "OKX",
            "configured": True,
            "authenticated": True,
            "can_trade": True,
            "status": "ready",
            "message": "OKX 账户已授权，交易权限会在订单预检或下单时校验。",
            "balances": balances,
            "quote_available": quote_available,
        }

    def ticker24hr_symbols(self, symbols: list[str]) -> list[dict]:
        normalized = list(dict.fromkeys(symbol.upper().strip() for symbol in symbols if symbol.strip()))
        if len(normalized) <= 1:
            item = self._ticker24hr_symbol(normalized[0]) if normalized else None
            return [item] if item else []

        rows_by_symbol: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=min(6, len(normalized)), thread_name_prefix="okx-ticker") as executor:
            futures = {executor.submit(self._ticker24hr_symbol, symbol): symbol for symbol in normalized}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    item = future.result()
                except Exception:  # noqa: BLE001
                    continue
                if item:
                    rows_by_symbol[symbol] = item
        return [rows_by_symbol[symbol] for symbol in normalized if symbol in rows_by_symbol]

    def _ticker24hr_symbol(self, symbol: str) -> dict | None:
        inst_id = self._okx_inst_id(symbol)
        cache_key = f"ticker:{inst_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        data = self._request_json("GET", "/api/v5/market/ticker", params={"instId": inst_id})
        if isinstance(data, dict) and isinstance(data.get("data"), list) and data["data"]:
            item = self._ticker_to_binance_shape(data["data"][0])
            self._cache_set(cache_key, item)
            return item
        return None

    def order_market_buy(
        self,
        *,
        symbol: str,
        quote_order_qty: float,
        test: bool = False,
        client_order_id: str | None = None,
    ) -> dict:
        payload = {
            "instId": self._okx_inst_id(symbol),
            "tdMode": "cash",
            "side": "buy",
            "ordType": "market",
            "sz": f"{quote_order_qty:.8f}".rstrip("0").rstrip("."),
            "tgtCcy": "quote_ccy",
            "clOrdId": client_order_id,
        }
        return self._submit_order(payload, test=test)

    def order_market_sell(
        self,
        *,
        symbol: str,
        quantity: float,
        test: bool = False,
        client_order_id: str | None = None,
    ) -> dict:
        payload = {
            "instId": self._okx_inst_id(symbol),
            "tdMode": "cash",
            "side": "sell",
            "ordType": "market",
            "sz": f"{quantity:.8f}".rstrip("0").rstrip("."),
            "tgtCcy": "base_ccy",
            "clOrdId": client_order_id,
        }
        return self._submit_order(payload, test=test)

    def _submit_order(self, payload: dict[str, object], *, test: bool) -> dict:
        clean_payload = {key: value for key, value in payload.items() if value not in {None, ""}}
        path = "/api/v5/trade/order-precheck" if test else "/api/v5/trade/order"
        data = self._request_json("POST", path, payload=clean_payload, signed=True)
        result = dict(data) if isinstance(data, dict) else {"raw": data}
        if isinstance(data, dict) and isinstance(data.get("data"), list) and data["data"]:
            first = data["data"][0]
            if isinstance(first, dict):
                result.update(first)
        return result

    @classmethod
    def _ticker_to_binance_shape(cls, payload: dict[str, object]) -> dict[str, object]:
        last_price = float(payload.get("last") or 0.0)
        open_24h = float(payload.get("open24h") or 0.0)
        change_pct = ((last_price - open_24h) / open_24h * 100) if open_24h > 0 else 0.0
        return {
            "symbol": cls._compact_symbol(str(payload.get("instId", ""))),
            "lastPrice": str(last_price),
            "priceChangePercent": f"{change_pct:.8f}",
            "quoteVolume": str(payload.get("volCcy24h") or payload.get("vol24h") or "0"),
            "volume": str(payload.get("vol24h") or "0"),
            "count": 0,
        }

    @staticmethod
    def _extract_http_error_detail(exc: HTTPError) -> str:
        try:
            payload = exc.read().decode("utf-8", errors="ignore").strip()
        except Exception:  # noqa: BLE001
            payload = ""
        if not payload:
            return str(exc.reason)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        if isinstance(parsed, dict):
            if isinstance(parsed.get("msg"), str) and parsed["msg"].strip():
                return parsed["msg"].strip()
            if isinstance(parsed.get("code"), str) and parsed["code"].strip():
                return parsed["code"].strip()
        return payload
