from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Candlestick, MarketTicker, utc_datetime_from_epoch


@dataclass
class TimedValue:
    expires_at: datetime
    value: object


class BinanceSpotGateway:
    # Keep the same method surface as the official connector:
    # exchange_info / ticker24hr / klines
    def __init__(
        self,
        ttl_seconds: int = 45,
        base_url: str = "https://api.binance.com",
        timeout: int = 20,
        api_key: str = "",
        api_secret: str = "",
        recv_window_ms: float = 5000,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, TimedValue] = {}
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._api_key = api_key
        self._api_secret = api_secret
        self._recv_window_ms = recv_window_ms

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
        return bool(self._api_key and self._api_secret)

    @staticmethod
    def _format_recv_window(recv_window_ms: float) -> str:
        return f"{recv_window_ms:.3f}".rstrip("0").rstrip(".")

    def _get_json(self, path: str, params: dict[str, object] | None = None) -> object:
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{query}"
        request = Request(url, headers={"User-Agent": "trade-signal-app/0.1"})
        with urlopen(request, timeout=self._timeout) as response:
            return json.load(response)

    def _signed_request_json(
        self,
        method: str,
        path: str,
        params: dict[str, object] | None = None,
    ) -> object:
        if not self.has_user_data_auth():
            raise ValueError("BINANCE_API_KEY / BINANCE_API_SECRET 未配置，无法访问账户级 SIGNED 接口。")

        signed_params = {key: value for key, value in (params or {}).items() if value is not None}
        signed_params["recvWindow"] = self._format_recv_window(self._recv_window_ms)
        signed_params["timestamp"] = int(time.time() * 1000)
        query = urlencode(signed_params, doseq=True)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        body = f"{query}&signature={signature}".encode("utf-8")
        url = f"{self._base_url}{path}"
        data = body if method.upper() in {"POST", "PUT", "DELETE"} else None
        if data is None:
            url = f"{url}?{body.decode('utf-8')}"
        request = Request(
            url,
            data=data,
            method=method.upper(),
            headers={
                "User-Agent": "trade-signal-app/0.1",
                "X-MBX-APIKEY": self._api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = self._extract_http_error_detail(exc)
            message = f"Binance SIGNED 接口请求失败：HTTP {exc.code}"
            if detail:
                message = f"{message}，{detail}"
            raise ValueError(message) from exc
        except URLError as exc:
            raise ValueError(f"Binance SIGNED 接口请求失败：{exc.reason}") from exc

    def _signed_get_json(self, path: str, params: dict[str, object] | None = None) -> object:
        return self._signed_request_json("GET", path, params)

    def _signed_post_json(self, path: str, params: dict[str, object] | None = None) -> object:
        return self._signed_request_json("POST", path, params)

    def exchange_info(self) -> dict:
        cache_key = "exchange_info"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        data = self._get_json("/api/v3/exchangeInfo")
        return self._cache_set(cache_key, data)  # type: ignore[return-value]

    def ticker24hr(self) -> list[dict]:
        cache_key = "ticker24hr"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        data = self._get_json("/api/v3/ticker/24hr")
        return self._cache_set(cache_key, data)  # type: ignore[return-value]

    def account(self, omit_zero_balances: bool = True) -> dict:
        cache_key = f"account:{int(omit_zero_balances)}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        data = self._signed_get_json(
            "/api/v3/account",
            {"omitZeroBalances": str(omit_zero_balances).lower()},
        )
        return self._cache_set(cache_key, data)  # type: ignore[return-value]

    def account_commission(self, symbol: str) -> dict:
        cache_key = f"account_commission:{symbol.upper()}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        data = self._signed_get_json(
            "/api/v3/account/commission",
            {"symbol": symbol.upper()},
        )
        return self._cache_set(cache_key, data)  # type: ignore[return-value]

    def order_market_buy(
        self,
        *,
        symbol: str,
        quote_order_qty: float,
        test: bool = False,
        client_order_id: str | None = None,
    ) -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": f"{quote_order_qty:.8f}".rstrip("0").rstrip("."),
            "newOrderRespType": "FULL",
            "newClientOrderId": client_order_id,
        }
        path = "/api/v3/order/test" if test else "/api/v3/order"
        return self._signed_post_json(path, params)  # type: ignore[return-value]

    def order_market_sell(
        self,
        *,
        symbol: str,
        quantity: float,
        test: bool = False,
        client_order_id: str | None = None,
    ) -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": "SELL",
            "type": "MARKET",
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
            "newOrderRespType": "FULL",
            "newClientOrderId": client_order_id,
        }
        path = "/api/v3/order/test" if test else "/api/v3/order"
        return self._signed_post_json(path, params)  # type: ignore[return-value]

    def klines(self, symbol: str, interval: str, limit: int) -> list[Candlestick]:
        data = self._get_json(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [self._parse_kline(row) for row in data]

    def map_klines(
        self,
        symbols: list[str],
        interval: str,
        limit: int,
        max_workers: int,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> dict[str, list[Candlestick]]:
        results: dict[str, list[Candlestick]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self.klines, symbol, interval, limit): symbol for symbol in symbols
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    results[symbol] = future.result()
                except Exception as exc:  # noqa: BLE001
                    if on_error:
                        on_error(symbol, exc)
        return results

    @staticmethod
    def _parse_kline(row: list) -> Candlestick:
        return Candlestick(
            open_time=utc_datetime_from_epoch(int(row[0])),
            open_price=float(row[1]),
            high_price=float(row[2]),
            low_price=float(row[3]),
            close_price=float(row[4]),
            volume=float(row[5]),
            close_time=utc_datetime_from_epoch(int(row[6])),
            quote_volume=float(row[7]),
            trade_count=int(row[8]),
            taker_buy_base_volume=float(row[9]),
            taker_buy_quote_volume=float(row[10]),
        )

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
            if isinstance(parsed.get("error"), str) and parsed["error"].strip():
                return parsed["error"].strip()
        return payload


def parse_ticker(payload: dict) -> MarketTicker:
    return MarketTicker(
        symbol=payload["symbol"],
        last_price=float(payload["lastPrice"]),
        price_change_percent=float(payload["priceChangePercent"]),
        quote_volume=float(payload["quoteVolume"]),
        volume=float(payload["volume"]),
        trade_count=int(payload["count"]),
    )
