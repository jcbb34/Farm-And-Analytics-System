from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


DEFAULT_FARM_TIMEZONE = "Asia/Manila"


def farm_timezone_name() -> str:
    return str(getattr(settings, "farm_timezone", DEFAULT_FARM_TIMEZONE) or DEFAULT_FARM_TIMEZONE).strip() or DEFAULT_FARM_TIMEZONE


def farm_timezone() -> tzinfo:
    name = farm_timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        # Windows installations may not provide the IANA timezone database
        # unless the optional ``tzdata`` package is installed. Asia/Manila has
        # used UTC+08:00 continuously since 1978 and currently observes no DST,
        # so keep the capstone's default Philippine deployment operational with
        # a fixed-offset fallback while still requiring valid IANA data for any
        # other configured timezone. ``tzdata`` remains a declared dependency.
        if name == DEFAULT_FARM_TIMEZONE:
            return timezone(timedelta(hours=8), name)
        raise RuntimeError(f"Invalid FARM_TIMEZONE configuration: {name}") from exc


def farm_now(instant: datetime | None = None) -> datetime:
    """Return an aware datetime in the configured farm timezone.

    Tests may pass an explicit aware instant. A naive explicit instant is treated
    as UTC so midnight-boundary tests are deterministic rather than dependent on
    the machine timezone.
    """
    if instant is None:
        instant = datetime.now(timezone.utc)
    elif instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(farm_timezone())


def farm_today(instant: datetime | None = None) -> date:
    return farm_now(instant).date()


def farm_now_naive(instant: datetime | None = None) -> datetime:
    """Farm-local wall-clock timestamp for existing naive DateTime columns."""
    return farm_now(instant).replace(tzinfo=None)
