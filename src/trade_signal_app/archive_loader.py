from __future__ import annotations

from pathlib import Path
import csv
import io
import zipfile

from .models import Candlestick, utc_datetime_from_epoch


def load_public_data_klines(path: str | Path) -> list[Candlestick]:
    archive_path = Path(path)
    with zipfile.ZipFile(archive_path) as archive:
        csv_name = next(name for name in archive.namelist() if name.endswith(".csv"))
        with archive.open(csv_name, "r") as handle:
            payload = io.TextIOWrapper(handle, encoding="utf-8")
            reader = csv.reader(payload)
            candles = [parse_public_data_kline_row(row) for row in reader if row]
    return candles


def parse_public_data_kline_row(row: list[str]) -> Candlestick:
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
