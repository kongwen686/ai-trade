from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import re

from .binance_client import BinanceSpotGateway
from .models import Candlestick, utc_datetime_from_epoch


TRADINGVIEW_INTERVALS = {
    "1m": "in_1_minute",
    "3m": "in_3_minute",
    "5m": "in_5_minute",
    "15m": "in_15_minute",
    "30m": "in_30_minute",
    "45m": "in_45_minute",
    "1h": "in_1_hour",
    "2h": "in_2_hour",
    "3h": "in_3_hour",
    "4h": "in_4_hour",
    "1d": "in_daily",
    "1w": "in_weekly",
    "1M": "in_monthly",
}

TRADINGVIEW_INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "45m": 2700,
    "1h": 3600,
    "2h": 7200,
    "3h": 10800,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1M": 2592000,
}


@dataclass(frozen=True)
class TradingViewFetchResult:
    exchange: str
    symbol: str
    interval: str
    cache_path: Path
    candle_count: int
    source: str


def normalize_tradingview_interval(interval: str) -> str:
    value = interval.strip()
    aliases = {
        "1": "1m",
        "3": "3m",
        "5": "5m",
        "15": "15m",
        "30": "30m",
        "45": "45m",
        "60": "1h",
        "120": "2h",
        "180": "3h",
        "240": "4h",
        "1H": "1h",
        "2H": "2h",
        "3H": "3h",
        "4H": "4h",
        "D": "1d",
        "1D": "1d",
        "W": "1w",
        "1W": "1w",
        "M": "1M",
    }
    normalized = aliases.get(value, value)
    if normalized not in TRADINGVIEW_INTERVALS:
        allowed = ", ".join(TRADINGVIEW_INTERVALS)
        raise ValueError(f"TradingView interval 只能是：{allowed}。")
    return normalized


def tradingview_cache_path(cache_root: Path, exchange: str, symbol: str, interval: str) -> Path:
    normalized_interval = normalize_tradingview_interval(interval)
    safe_exchange = _safe_path_part(exchange.upper())
    safe_symbol = _safe_path_part(symbol.upper())
    return cache_root / safe_exchange / safe_symbol / f"{normalized_interval}.csv"


def load_tradingview_csv(path: str | Path, *, interval: str | None = None) -> list[Candlestick]:
    csv_path = Path(path)
    default_interval = interval or csv_path.stem
    normalized_interval = normalize_tradingview_interval(default_interval)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        candles = [
            _row_to_candlestick(row, normalized_interval)
            for row in reader
            if row and _row_value(row, "open") and _row_value(row, "close")
        ]
    return sorted(candles, key=lambda candle: candle.open_time)


def write_tradingview_csv(path: str | Path, candles: list[Candlestick]) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trade_count",
                "taker_buy_base_volume",
                "taker_buy_quote_volume",
                "close_time",
            ],
        )
        writer.writeheader()
        for candle in candles:
            writer.writerow(
                {
                    "datetime": candle.open_time.isoformat(),
                    "open": f"{candle.open_price:.12g}",
                    "high": f"{candle.high_price:.12g}",
                    "low": f"{candle.low_price:.12g}",
                    "close": f"{candle.close_price:.12g}",
                    "volume": f"{candle.volume:.12g}",
                    "quote_volume": f"{candle.quote_volume:.12g}",
                    "trade_count": candle.trade_count,
                    "taker_buy_base_volume": f"{candle.taker_buy_base_volume:.12g}",
                    "taker_buy_quote_volume": f"{candle.taker_buy_quote_volume:.12g}",
                    "close_time": candle.close_time.isoformat(),
                }
            )


def fetch_tradingview_history(
    *,
    cache_root: Path,
    exchange: str,
    symbol: str,
    interval: str,
    bars: int,
    username: str = "",
    password: str = "",
    cache_enabled: bool = True,
) -> TradingViewFetchResult:
    normalized_interval = normalize_tradingview_interval(interval)
    if bars < 1:
        raise ValueError("TradingView bars 必须大于 0。")

    cache_path = tradingview_cache_path(cache_root, exchange, symbol, normalized_interval)
    try:
        tv_datafeed, tv_interval = _load_tvdatafeed(normalized_interval)
    except ValueError as exc:
        if cache_enabled and cache_path.exists():
            candles = load_tradingview_csv(cache_path, interval=normalized_interval)
            if len(candles) >= bars:
                return TradingViewFetchResult(
                    exchange=exchange.upper(),
                    symbol=symbol.upper(),
                    interval=normalized_interval,
                    cache_path=cache_path,
                    candle_count=len(candles),
                    source="cache",
                )
        if exchange.upper() == "BINANCE":
            try:
                candles = _fetch_binance_public_history(symbol=symbol, interval=normalized_interval, bars=bars)
            except Exception as fallback_exc:  # noqa: BLE001
                raise ValueError(
                    f"{exc} Binance 公共行情兜底也失败：{fallback_exc}"
                ) from fallback_exc
            if not candles:
                raise ValueError(f"{exc} Binance 公共行情兜底未返回 {symbol.upper()} {normalized_interval} 的历史 K 线。") from exc
            if cache_enabled:
                write_tradingview_csv(cache_path, candles)
            return TradingViewFetchResult(
                exchange=exchange.upper(),
                symbol=symbol.upper(),
                interval=normalized_interval,
                cache_path=cache_path,
                candle_count=len(candles),
                source="binance_public_fallback",
            )
        raise

    client = tv_datafeed(username.strip(), password.strip()) if username.strip() and password.strip() else tv_datafeed()
    frame = client.get_hist(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        interval=tv_interval,
        n_bars=bars,
    )
    if frame is None or getattr(frame, "empty", False):
        raise ValueError(f"TradingView 未返回 {exchange.upper()}:{symbol.upper()} {normalized_interval} 的历史 K 线。")

    candles = _dataframe_to_candles(frame, normalized_interval)
    if not candles:
        raise ValueError("TradingView 返回数据为空，无法生成回测缓存。")
    if cache_enabled:
        write_tradingview_csv(cache_path, candles)

    return TradingViewFetchResult(
        exchange=exchange.upper(),
        symbol=symbol.upper(),
        interval=normalized_interval,
        cache_path=cache_path,
        candle_count=len(candles),
        source="tradingview",
    )


def _load_tvdatafeed(interval: str):
    try:
        from tvDatafeed import Interval, TvDatafeed  # type: ignore
    except Exception as exc:  # noqa: BLE001
        try:
            from tvdatafeed import Interval, TvDatafeed  # type: ignore
        except Exception as fallback_exc:  # noqa: BLE001
            raise ValueError(
                "TradingView 非官方拉取依赖未安装。请安装 tvDatafeed/tvdatafeed 兼容包，或先把 CSV 放入本地缓存目录。"
            ) from fallback_exc
        else:
            _ = exc
    attribute = TRADINGVIEW_INTERVALS[interval]
    tv_interval = getattr(Interval, attribute, None)
    if tv_interval is None:
        raise ValueError(f"当前 tvDatafeed 版本不支持 TradingView interval：{interval}。")
    return TvDatafeed, tv_interval


def _fetch_binance_public_history(*, symbol: str, interval: str, bars: int) -> list[Candlestick]:
    gateway = BinanceSpotGateway()
    remaining = bars
    end_time_ms: int | None = None
    candles_by_open_time: dict[datetime, Candlestick] = {}
    while remaining > 0:
        batch_limit = min(remaining, 1000)
        params: dict[str, object] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": batch_limit,
        }
        if end_time_ms is not None:
            params["endTime"] = end_time_ms
        data = gateway._get_json("/api/v3/klines", params)
        if not isinstance(data, list) or not data:
            break
        batch = [_binance_row_to_candlestick(row) for row in data if isinstance(row, list)]
        if not batch:
            break
        for candle in batch:
            candles_by_open_time[candle.open_time] = candle
        remaining -= len(batch)
        earliest = min(batch, key=lambda candle: candle.open_time)
        end_time_ms = int(earliest.open_time.timestamp() * 1000) - 1
        if len(batch) < batch_limit:
            break
    return sorted(candles_by_open_time.values(), key=lambda candle: candle.open_time)[-bars:]


def _binance_row_to_candlestick(row: list[object]) -> Candlestick:
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


def _dataframe_to_candles(frame: object, interval: str) -> list[Candlestick]:
    candles: list[Candlestick] = []
    for index, row in frame.iterrows():  # type: ignore[attr-defined]
        opened_at = _parse_datetime(index)
        open_price = float(row["open"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        close_price = float(row["close"])
        volume = float(row.get("volume", 0.0) or 0.0)
        quote_volume = float(row.get("quote_volume", close_price * volume) or 0.0)
        close_time = opened_at + timedelta(seconds=TRADINGVIEW_INTERVAL_SECONDS[interval]) - timedelta(milliseconds=1)
        candles.append(
            Candlestick(
                open_time=opened_at,
                close_time=close_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                quote_volume=quote_volume,
                trade_count=int(row.get("trade_count", 0) or 0),
                taker_buy_base_volume=float(row.get("taker_buy_base_volume", volume * 0.5) or 0.0),
                taker_buy_quote_volume=float(row.get("taker_buy_quote_volume", quote_volume * 0.5) or 0.0),
            )
        )
    return sorted(candles, key=lambda candle: candle.open_time)


def _row_to_candlestick(row: dict[str, str], interval: str) -> Candlestick:
    opened_at = _parse_datetime(_row_value(row, "datetime") or _row_value(row, "time") or _row_value(row, "timestamp"))
    close_at_value = _row_value(row, "close_time")
    close_time = (
        _parse_datetime(close_at_value)
        if close_at_value
        else opened_at + timedelta(seconds=TRADINGVIEW_INTERVAL_SECONDS[interval]) - timedelta(milliseconds=1)
    )
    close_price = float(_row_value(row, "close") or 0.0)
    volume = float(_row_value(row, "volume") or 0.0)
    quote_volume = float(_row_value(row, "quote_volume") or close_price * volume)
    return Candlestick(
        open_time=opened_at,
        close_time=close_time,
        open_price=float(_row_value(row, "open") or 0.0),
        high_price=float(_row_value(row, "high") or 0.0),
        low_price=float(_row_value(row, "low") or 0.0),
        close_price=close_price,
        volume=volume,
        quote_volume=quote_volume,
        trade_count=int(float(_row_value(row, "trade_count") or 0.0)),
        taker_buy_base_volume=float(_row_value(row, "taker_buy_base_volume") or volume * 0.5),
        taker_buy_quote_volume=float(_row_value(row, "taker_buy_quote_volume") or quote_volume * 0.5),
    )


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        opened_at = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("TradingView CSV 缺少 datetime/time/timestamp 字段。")
        if re.fullmatch(r"\d+(\.\d+)?", text):
            opened_at = utc_datetime_from_epoch(int(float(text)))
        else:
            opened_at = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    return opened_at.astimezone(timezone.utc)


def _row_value(row: dict[str, str], key: str) -> str:
    for candidate in (key, key.lower(), key.upper(), key.title()):
        value = row.get(candidate)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _safe_path_part(value: str) -> str:
    sanitized = re.sub(r"[^A-Z0-9_.-]+", "_", value.upper()).strip("._")
    return sanitized or "UNKNOWN"
