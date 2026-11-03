from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
import json
import logging
import re
import traceback

from sqlalchemy import inspect, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive
from app.models import FarmReport, ReportAutomationSettings
from app.services.db_concurrency import (
    SMART_IMPORT_AUTOMATION_GUARD,
    acquire_transaction_lock,
    try_acquire_transaction_lock,
)
from app.services.operational_report_builder import build_operational_report_snapshot
from app.services.report_generation_service import create_report_record



ATTENDANCE_REPORT_TYPES = {
    "Daily Attendance Report",
    "Weekly Attendance Summary",
}

REQUIRED_ATTENDANCE_COLUMNS = {
    "scheduled_shift_id",
    "scheduled_start_time",
    "scheduled_end_time",
    "check_in_at",
    "check_out_at",
    "minutes_late",
    "minutes_early",
    "overtime_minutes",
    "attendance_source",
    "correction_reason",
    "updated_by_user_id",
}

_schema_warning_emitted = False
LOGGER = logging.getLogger("joross.scheduler.reports")


def _log(level: int, event: str, **fields) -> None:
    LOGGER.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


def _log_failure(event: str, error: Exception, **fields) -> None:
    # SQLAlchemy's DBAPIError string includes every bound value in an IN list.
    # Log the driver error and traceback without dumping thousands of task IDs.
    cause = error.orig if isinstance(error, DBAPIError) else error
    _log(
        logging.ERROR, event, **fields,
        error_type=type(error).__name__,
        error=str(cause)[:500],
        traceback="".join(traceback.format_tb(error.__traceback__, limit=12)),
    )


def attendance_schema_missing_columns(db: Session) -> set[str]:
    """Return attendance columns missing from the live database.

    This is a readiness check only. It never creates/alters tables and therefore
    cannot replace the required Alembic upgrade.
    """
    try:
        columns = {
            str(column.get("name") or "").lower()
            for column in inspect(db.get_bind()).get_columns("staff_attendance")
        }
    except Exception:
        # If the DBAPI/inspector is unavailable, keep normal behavior. The actual
        # query will surface the connection problem instead of falsely claiming a
        # migration mismatch.
        return set()
    return REQUIRED_ATTENDANCE_COLUMNS - columns


def _warn_attendance_schema_once(missing: set[str]) -> None:
    global _schema_warning_emitted
    if not missing or _schema_warning_emitted:
        return
    _schema_warning_emitted = True
    _log(
        logging.WARNING,
        "report_scheduler_schema_incomplete",
        missing_columns=sorted(missing),
        action="Run python -m alembic upgrade head from Jorros Backend.",
    )

LIMITS = {"Daily": 31, "Weekly": 12, "Monthly": 24, "Seasonal": 8, "Yearly": 5}

AUTOMATIC_REPORT_PLAN = {
    "Daily": [
        ("Workforce", "Daily Attendance Report"),
        ("Tasks", "Task Completion and Employee Performance"),
        ("Inventory", "Inventory Movement and Resource Usage"),
    ],
    "Weekly": [
        ("Workforce", "Weekly Attendance Summary"),
        ("Tasks", "Task Completion and Employee Performance"),
        ("Tasks", "Task Coverage and Reassignment"),
    ],
    "Monthly": [
        ("Inventory", "Inventory Movement and Resource Usage"),
        ("Livestock", "Livestock Feeding, Growth, and Health"),
        ("Production & Sales", "Production and Sales Summary"),
    ],
    "Seasonal": [
        ("Crop", "Crop Yield and Input Usage"),
        ("Care Compliance", "Care Protocol Compliance"),
    ],
}


def get_or_create_automation_settings(db: Session) -> ReportAutomationSettings:
    acquire_transaction_lock(db, "automation:report-settings")
    settings = db.scalar(select(ReportAutomationSettings).order_by(ReportAutomationSettings.id.asc()).limit(1))
    if settings is None:
        settings = ReportAutomationSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _parse_time(value: str) -> time:
    hour, minute = [int(part) for part in value.split(":", 1)]
    return time(hour, minute)


def _previous_month(anchor: date):
    first = anchor.replace(day=1)
    end = first - timedelta(days=1)
    return end.replace(day=1), end


def _latest_daily(now: datetime, scheduled_time: str, force: bool):
    scheduled_today = datetime.combine(now.date(), _parse_time(scheduled_time))
    target = now.date() - timedelta(days=1 if force or now >= scheduled_today else 2)
    return target, target


def _latest_weekly(now: datetime, scheduled_weekday: int, scheduled_time: str, force: bool):
    # Reporting period is always Monday-Sunday. The configurable weekday/time controls
    # when generation occurs; it never changes the reporting week definition.
    days_since_monday = now.date().weekday()
    this_monday = now.date() - timedelta(days=days_since_monday)
    scheduled_date = this_monday + timedelta(days=(scheduled_weekday % 7))
    scheduled = datetime.combine(scheduled_date, _parse_time(scheduled_time))
    if force or now >= scheduled:
        end = this_monday - timedelta(days=1)
    else:
        end = this_monday - timedelta(days=8)
    return end - timedelta(days=6), end


def _latest_monthly(now: datetime, monthly_day: int, scheduled_time: str, force: bool):
    t = _parse_time(scheduled_time)
    scheduled = datetime(now.year, now.month, min(monthly_day, 28), t.hour, t.minute)
    anchor = now.date()
    if not force and now < scheduled:
        anchor = anchor.replace(day=1) - timedelta(days=1)
    return _previous_month(anchor)


def _quarter_bounds(year: int, quarter: int):
    first_month = (quarter - 1) * 3 + 1
    start = date(year, first_month, 1)
    if quarter == 4:
        next_start = date(year + 1, 1, 1)
    else:
        next_start = date(year, first_month + 3, 1)
    return start, next_start - timedelta(days=1)


def _latest_seasonal(now: datetime, force: bool):
    current_quarter = ((now.month - 1) // 3) + 1
    year = now.year
    quarter = current_quarter - 1
    if quarter == 0:
        quarter = 4
        year -= 1
    return _quarter_bounds(year, quarter)


def _next_period(frequency: str, previous_end: date):
    start = previous_end + timedelta(days=1)
    if frequency == "Daily":
        return start, start
    if frequency == "Weekly":
        return start, start + timedelta(days=6)
    if frequency == "Monthly":
        first = start.replace(day=1)
        next_month = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)
        return first, next_month - timedelta(days=1)
    if frequency == "Seasonal":
        q = ((start.month - 1) // 3) + 1
        return _quarter_bounds(start.year, q)
    return date(start.year, 1, 1), date(start.year, 12, 31)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:42]


def _period_key(frequency: str, report_type: str, start: date, end: date):
    return f"{frequency.lower()}:{_slug(report_type)}:{start.isoformat()}:{end.isoformat()}"


def _title(frequency: str, report_type: str, start: date, end: date):
    if frequency == "Daily": period = start.strftime("%B %d, %Y")
    elif frequency == "Weekly": period = f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
    elif frequency == "Monthly": period = start.strftime("%B %Y")
    elif frequency == "Seasonal": period = f"{start.strftime('%b %Y')} - {end.strftime('%b %Y')}"
    else: period = str(start.year)
    return f"{report_type} - {period}"


def _latest_report(db: Session, frequency: str, report_type: str | None = None):
    stmt = select(FarmReport).where(FarmReport.is_automatic == True, FarmReport.frequency == frequency)  # noqa: E712
    if report_type:
        stmt = stmt.where(FarmReport.report_type == report_type)
    return db.scalar(stmt.order_by(FarmReport.end_date.desc(), FarmReport.revision_number.desc(), FarmReport.id.desc()).limit(1))


def _candidate_periods(db: Session, frequency: str, report_type: str, latest_due: tuple[date, date]):
    latest = _latest_report(db, frequency, report_type)
    if latest is None:
        return [latest_due]
    periods = []
    start, end = _next_period(frequency, latest.end_date)
    while end <= latest_due[1] and len(periods) < LIMITS[frequency]:
        periods.append((start, end))
        start, end = _next_period(frequency, end)
    # Always include the latest due period so a finalized snapshot can be revised
    # after source records are corrected, even when no period is missing.
    if not periods and latest.end_date == latest_due[1]:
        periods.append(latest_due)
    return periods


def _report_status(report_type: str, snapshot: dict, *, revision: bool = False) -> str:
    if revision:
        return "Revised"
    if report_type == "Daily Attendance Report":
        metrics = snapshot.get("metrics", {})
        if int(metrics.get("possible_absences", 0) or 0) > 0 or int(metrics.get("missing_checkouts", 0) or 0) > 0:
            return "Needs Review"
    return "Final"


def _latest_period_version(db: Session, category: str, report_type: str, start: date, end: date):
    return db.scalar(
        select(FarmReport).where(
            FarmReport.category == category,
            FarmReport.report_type == report_type,
            FarmReport.start_date == start,
            FarmReport.end_date == end,
            FarmReport.is_automatic == True,  # noqa: E712
        ).order_by(FarmReport.revision_number.desc(), FarmReport.id.desc()).limit(1)
    )


def _generate_or_revise(
    db: Session,
    *,
    settings: ReportAutomationSettings,
    frequency: str,
    category: str,
    report_type: str,
    start: date,
    end: date,
):
    key = _period_key(frequency, report_type, start, end)
    current_snapshot = build_operational_report_snapshot(db, report_type, start, end, {})
    latest = _latest_period_version(db, category, report_type, start, end)

    if latest is not None:
        old_fingerprint = latest.snapshot.get("source_fingerprint")
        if old_fingerprint == current_snapshot.get("source_fingerprint"):
            return None
        # Never rewrite a historical System report. Create a new audited version.
        next_revision = int(latest.revision_number or 1) + 1
        revision_key = f"{key}:revision:{next_revision}"
        if db.scalar(select(FarmReport.id).where(FarmReport.automation_period_key == revision_key)) is not None:
            return None
        return create_report_record(
            db,
            title=_title(frequency, report_type, start, end),
            category=category,
            report_type=report_type,
            start_date=start,
            end_date=end,
            prepared_by=settings.prepared_by,
            status=_report_status(report_type, current_snapshot, revision=True),
            is_automatic=True,
            frequency=frequency,
            automation_period_key=revision_key,
            generate_pdf=settings.auto_generate_pdf,
            revision_group_code=latest.revision_group_code or latest.report_code,
            revision_number=next_revision,
            revision_of_report_id=latest.id,
        )

    if db.scalar(select(FarmReport.id).where(FarmReport.automation_period_key == key)) is not None:
        return None
    return create_report_record(
        db,
        title=_title(frequency, report_type, start, end),
        category=category,
        report_type=report_type,
        start_date=start,
        end_date=end,
        prepared_by=settings.prepared_by,
        status=_report_status(report_type, current_snapshot),
        is_automatic=True,
        frequency=frequency,
        automation_period_key=key,
        generate_pdf=settings.auto_generate_pdf,
    )


def run_due_report_automation(db: Session, *, force: bool = False):
    acquire_transaction_lock(db, "automation:reports")
    settings = get_or_create_automation_settings(db)
    missing_attendance_columns = attendance_schema_missing_columns(db)
    _warn_attendance_schema_once(missing_attendance_columns)
    now = farm_now_naive()
    schedules: list[tuple[str, tuple[date, date]]] = []
    if settings.daily_enabled:
        schedules.append(("Daily", _latest_daily(now, settings.daily_time, force)))
    if settings.weekly_enabled:
        schedules.append(("Weekly", _latest_weekly(now, settings.weekly_day, settings.weekly_time, force)))
    if settings.monthly_enabled:
        schedules.append(("Monthly", _latest_monthly(now, settings.monthly_day, settings.monthly_time, force)))
    if settings.yearly_enabled:
        schedules.append(("Seasonal", _latest_seasonal(now, force)))

    generated = []
    for frequency, latest_due in schedules:
        for category, report_type in AUTOMATIC_REPORT_PLAN[frequency]:
            if missing_attendance_columns and report_type in ATTENDANCE_REPORT_TYPES:
                # Keep the rest of the report scheduler healthy while the local
                # database is awaiting its Alembic upgrade. Attendance APIs/reports
                # will become available immediately after the schema is upgraded.
                continue
            for start, end in _candidate_periods(db, frequency, report_type, latest_due):
                try:
                    report = _generate_or_revise(
                        db, settings=settings, frequency=frequency, category=category,
                        report_type=report_type, start=start, end=end,
                    )
                    if report is not None:
                        generated.append(report)
                except Exception as error:
                    db.rollback()
                    _log_failure(
                        "automatic_report_failed", error,
                        frequency=frequency,
                        report_type=report_type,
                    )

    settings.last_scheduler_run_at = farm_now_naive()
    db.commit()
    return generated


def _next_daily_run(now: datetime, value: str):
    target = datetime.combine(now.date(), _parse_time(value))
    if target <= now: target += timedelta(days=1)
    return target


def _next_weekly_run(now: datetime, weekday: int, value: str):
    days_ahead = (weekday - now.weekday()) % 7
    target = datetime.combine(now.date() + timedelta(days=days_ahead), _parse_time(value))
    if target <= now: target += timedelta(days=7)
    return target


def _next_monthly_run(now: datetime, day: int, value: str):
    t = _parse_time(value)
    target = datetime(now.year, now.month, min(day, 28), t.hour, t.minute)
    if target > now: return target
    if now.month == 12: return datetime(now.year + 1, 1, min(day, 28), t.hour, t.minute)
    return datetime(now.year, now.month + 1, min(day, 28), t.hour, t.minute)


def _next_seasonal_run(now: datetime, value: str):
    t = _parse_time(value)
    quarter = ((now.month - 1) // 3) + 1
    next_month = quarter * 3 + 1
    year = now.year
    if next_month > 12:
        next_month = 1; year += 1
    return datetime(year, next_month, 1, t.hour, t.minute)


def get_automation_status(db: Session):
    settings = get_or_create_automation_settings(db)
    now = farm_now_naive()
    config = {
        "Daily": {"enabled": settings.daily_enabled, "next": _next_daily_run(now, settings.daily_time)},
        "Weekly": {"enabled": settings.weekly_enabled, "next": _next_weekly_run(now, settings.weekly_day, settings.weekly_time)},
        "Monthly": {"enabled": settings.monthly_enabled, "next": _next_monthly_run(now, settings.monthly_day, settings.monthly_time)},
        "Seasonal": {"enabled": settings.yearly_enabled, "next": _next_seasonal_run(now, settings.yearly_time)},
    }
    items = []
    for frequency, values in config.items():
        latest = _latest_report(db, frequency)
        items.append({
            "frequency": frequency,
            "enabled": bool(values["enabled"]),
            "last_report_code": latest.report_code if latest else None,
            "last_period_start": latest.start_date if latest else None,
            "last_period_end": latest.end_date if latest else None,
            "last_status": latest.status if latest else None,
            "next_run_at": values["next"] if values["enabled"] else None,
        })
    return items


def _run_report_scheduler_once():
    # Import lazily so report-period helpers and tests do not require the live DBAPI/engine.
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        if not try_acquire_transaction_lock(db, SMART_IMPORT_AUTOMATION_GUARD, timeout_ms=100):
            db.rollback()
            return []
        generated = run_due_report_automation(db)
        # A later report failure may roll back and expire earlier ORM objects.
        # Capture their codes while the session is still open.
        return [report.report_code for report in generated]


async def report_scheduler_loop():
    await asyncio.sleep(5)
    while True:
        try:
            generated = await asyncio.to_thread(_run_report_scheduler_once)
            if generated:
                _log(
                    logging.INFO,
                    "automatic_reports_generated",
                    report_codes=generated,
                    generated_count=len(generated),
                )
        except Exception as error:
            _log_failure("report_scheduler_failed", error)
        await asyncio.sleep(60)
