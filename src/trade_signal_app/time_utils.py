from __future__ import annotations

from datetime import datetime, timedelta, timezone

APP_TIMEZONE = timezone(timedelta(hours=8), "UTC+08:00")


def now_app_time() -> datetime:
    return datetime.now(APP_TIMEZONE)


def to_app_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def format_app_datetime(value: datetime, *, include_timezone: bool = False) -> str:
    formatted = to_app_time(value).strftime("%Y-%m-%d %H:%M:%S")
    return f"{formatted} UTC+8" if include_timezone else formatted
