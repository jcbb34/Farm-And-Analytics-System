import calendar
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["both", "zip", "bak"] = "both"
    destination: Literal["local", "local_drive"] = "local"
    encrypted: bool = True


class BackupOptions(BackupRequest):
    schedule_enabled: bool = False
    frequency: Literal["daily", "weekly", "monthly", "custom"] = "weekly"
    hour: int = Field(default=18, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: int = Field(default=6, ge=0, le=6)
    month_day: int = Field(default=1, ge=1, le=31)
    interval_days: int = Field(default=7, ge=1, le=365)
    timezone: str = "Asia/Manila"
    reminder_enabled: bool = True
    reminder_days: int = Field(default=7, ge=1, le=365)
    retention_enabled: bool = False
    retain_count: int = Field(default=10, ge=2, le=365)
    recovery_key_acknowledged: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError("Choose a valid time zone.") from None
        return value

    @model_validator(mode="after")
    def key_saved(self):
        if (
            self.schedule_enabled
            and self.encrypted
            and not self.recovery_key_acknowledged
        ):
            raise ValueError(
                "Save the recovery key before scheduling encrypted backups."
            )
        return self


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=128)
    otp_code: str = Field(default="", max_length=6)


class Activation(Credentials):
    confirmation: str


def next_run(options, after=None):
    local = (after or datetime.now(timezone.utc)).astimezone(ZoneInfo(options.timezone))
    value = local.replace(
        hour=options.hour, minute=options.minute, second=0, microsecond=0
    )
    if options.frequency == "monthly":
        value = value.replace(
            day=min(options.month_day, calendar.monthrange(value.year, value.month)[1])
        )
        if value <= local:
            year, month = (
                (value.year + 1, 1)
                if value.month == 12
                else (value.year, value.month + 1)
            )
            value = value.replace(day=1, year=year, month=month).replace(
                day=min(options.month_day, calendar.monthrange(year, month)[1])
            )
    elif options.frequency == "weekly":
        value += timedelta(days=(options.weekday - value.weekday()) % 7)
        if value <= local:
            value += timedelta(days=7)
    elif value <= local:
        value += timedelta(
            days=options.interval_days if options.frequency == "custom" else 1
        )
    return value.astimezone(timezone.utc).isoformat()
