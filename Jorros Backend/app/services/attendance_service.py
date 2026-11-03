from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive, farm_today
from app.models import (
    AttendanceSettings,
    Employee,
    FarmActivity,
    StaffAttendance,
    StaffAttendanceAudit,
    StaffShift,
    TaskAssignmentHistory,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.services.task_assignment import record_assignment_change
from app.services.work_schedule_service import (
    current_schedule,
    employee_is_qualified_for_task,
    resolve_employee_availability,
)

SELF_SERVICE = "Employee Self-Service"
MANAGER_ASSISTED = "Manager Assisted"
ATTENDANCE_COVERAGE_SOURCE = "Attendance Coverage"
PRESENT_STATUSES = {"On Time", "Late", "Present", "Checked Out", "Early Departure", "Missing Check Out"}
CONFIRMED_UNAVAILABLE = {"Absent", "Sick"}
TERMINAL_TASK_STATUSES = {"Submitted for Review", "Completed", "Approved", "Resolved", "Cancelled", "Voided"}


class AttendanceError(ValueError):
    pass


_UNCHANGED = object()


def get_or_create_attendance_settings(db: Session) -> AttendanceSettings:
    acquire_transaction_lock(db, "attendance:settings")
    row = db.scalar(select(AttendanceSettings).order_by(AttendanceSettings.id).limit(1))
    if row is None:
        row = AttendanceSettings()
        db.add(row)
        db.flush()
    return row


def _minutes(value: timedelta) -> int:
    return max(0, int(value.total_seconds() // 60))


def _shift_datetime(work_date: date, shift_time: time | None) -> datetime | None:
    return datetime.combine(work_date, shift_time) if shift_time is not None else None


def _attendance_snapshot(record: StaffAttendance | None) -> dict[str, Any]:
    if record is None:
        return {"status": None, "check_in_at": None, "check_out_at": None}
    return {
        "status": record.status,
        "check_in_at": record.check_in_at,
        "check_out_at": record.check_out_at,
    }


def _write_audit(
    db: Session,
    record: StaffAttendance,
    *,
    action: str,
    actor_user_id: int | None,
    actor_name: str,
    source: str,
    reason: str | None,
    before: dict[str, Any],
) -> StaffAttendanceAudit:
    audit = StaffAttendanceAudit(
        attendance_id=record.id,
        employee_id=record.employee_id,
        work_date=record.attendance_date,
        action=action,
        old_status=before.get("status"),
        new_status=record.status,
        old_check_in_at=before.get("check_in_at"),
        new_check_in_at=record.check_in_at,
        old_check_out_at=before.get("check_out_at"),
        new_check_out_at=record.check_out_at,
        source=source,
        reason=(reason or "").strip() or None,
        actor_user_id=actor_user_id,
        actor_name=(actor_name or "System").strip() or "System",
    )
    db.add(audit)
    return audit


def _availability_for_attendance(db: Session, employee_id: int, work_date: date):
    return resolve_employee_availability(db, employee_id, work_date, allow_future_attendance=False)


def _ensure_clock_action_allowed(db: Session, employee_id: int, work_date: date) -> Any:
    availability = _availability_for_attendance(db, employee_id, work_date)
    if availability.leave_id is not None or availability.status == "On Leave":
        raise AttendanceError("Approved leave blocks attendance. Cancel or change the approved leave before recording work.")
    if availability.status in {"Rest Day", "Special Day Off"}:
        raise AttendanceError("Attendance cannot be recorded on a rest day or special day off. Create a Working Day Override first.")
    return availability


def _get_record_for_update(db: Session, employee_id: int, work_date: date) -> StaffAttendance | None:
    acquire_transaction_lock(db, f"attendance:{employee_id}:{work_date.isoformat()}")
    return db.scalar(
        select(StaffAttendance).where(
            StaffAttendance.employee_id == employee_id,
            StaffAttendance.attendance_date == work_date,
        )
    )


def _ensure_record(
    db: Session,
    employee_id: int,
    work_date: date,
    *,
    source: str,
    actor_user_id: int | None,
    availability: Any,
) -> StaffAttendance:
    record = _get_record_for_update(db, employee_id, work_date)
    if record is None:
        record = StaffAttendance(
            employee_id=employee_id,
            attendance_date=work_date,
            status="Not Checked In",
            attendance_source=source,
            recorded_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(record)
        db.flush()
    record.attendance_source = source
    record.updated_by_user_id = actor_user_id
    if record.recorded_by_user_id is None:
        record.recorded_by_user_id = actor_user_id
    record.scheduled_shift_id = availability.schedule_exception_id
    record.scheduled_start_time = availability.start_time
    record.scheduled_end_time = availability.end_time
    return record


def _punctuality_for_check_in(now: datetime, work_date: date, start_time: time | None, settings: AttendanceSettings, exempt_windows=None) -> tuple[str, int | None]:
    start = _shift_datetime(work_date, start_time)
    if start is None:
        return "Present", None
    from app.services.farm_event_service import exempt_minutes
    late_seconds = max(0, (now - start).total_seconds() - exempt_minutes(exempt_windows or [], start, now) * 60)
    if late_seconds <= settings.check_in_grace_minutes * 60:
        return "On Time", 0
    return "Late", int(late_seconds // 60)


def check_in(
    db: Session,
    employee_id: int,
    *,
    actor_user_id: int | None,
    actor_name: str,
    source: str,
    now: datetime | None = None,
    notes: str | None = None,
) -> StaffAttendance:
    now = now or farm_now_naive()
    work_date = now.date()
    availability = _ensure_clock_action_allowed(db, employee_id, work_date)
    settings = get_or_create_attendance_settings(db)
    from app.services.farm_event_service import employee_windows, attendance_start
    windows = employee_windows(db, db.get(Employee, employee_id), work_date)
    existing = _get_record_for_update(db, employee_id, work_date)
    if existing is not None and existing.check_in_at is not None:
        return existing
    if any(window["starts_at"] <= now < window["ends_at"] for window in windows):
        raise AttendanceError("Work is suspended for this period. An Owner/Admin must authorize essential duty before Check In.")
    record = _ensure_record(db, employee_id, work_date, source=source, actor_user_id=actor_user_id, availability=availability)
    before = _attendance_snapshot(record)
    if record.check_in_at is not None:
        return record
    start = attendance_start(work_date, availability.start_time, windows) if availability.start_time else None
    if start is not None and now < start - timedelta(minutes=settings.earliest_check_in_minutes):
        raise AttendanceError(
            f"Check In is not available yet. Earliest allowed check-in is {settings.earliest_check_in_minutes} minutes before the scheduled shift."
        )
    status, minutes_late = _punctuality_for_check_in(now, work_date, availability.start_time, settings, windows)
    record.check_in_at = now
    record.status = status
    record.minutes_late = minutes_late
    record.minutes_early = None
    record.overtime_minutes = None
    record.notes = (notes or record.notes or "").strip() or None
    _write_audit(db, record, action="Check In", actor_user_id=actor_user_id, actor_name=actor_name, source=source, reason=notes, before=before)
    return record


def check_out(
    db: Session,
    employee_id: int,
    *,
    actor_user_id: int | None,
    actor_name: str,
    source: str,
    now: datetime | None = None,
    notes: str | None = None,
) -> StaffAttendance:
    now = now or farm_now_naive()
    work_date = now.date()
    availability = _ensure_clock_action_allowed(db, employee_id, work_date)
    settings = get_or_create_attendance_settings(db)
    record = _get_record_for_update(db, employee_id, work_date)
    if record is None or record.check_in_at is None:
        raise AttendanceError("Check Out requires an existing Check In for today.")
    if record.check_out_at is not None:
        return record
    before = _attendance_snapshot(record)
    end = _shift_datetime(work_date, record.scheduled_end_time or availability.end_time)
    record.check_out_at = now
    record.attendance_source = source
    record.updated_by_user_id = actor_user_id
    record.notes = (notes or record.notes or "").strip() or None
    if end is None:
        record.status = "Checked Out"
        record.minutes_early = None
        record.overtime_minutes = None
    else:
        from app.services.farm_event_service import employee_windows, exempt_minutes
        windows = employee_windows(db, db.get(Employee, employee_id), work_date)
        early_seconds = max(0, (end - now).total_seconds() - exempt_minutes(windows, now, end) * 60)
        if early_seconds > settings.early_departure_grace_minutes * 60:
            record.status = "Early Departure"
            record.minutes_early = int(early_seconds // 60)
            record.overtime_minutes = 0
        else:
            record.status = "Checked Out"
            record.minutes_early = 0
            record.overtime_minutes = _minutes(now - end) if now > end else 0
    _write_audit(db, record, action="Check Out", actor_user_id=actor_user_id, actor_name=actor_name, source=source, reason=notes, before=before)
    return record


def _backup_for_task(db: Session, task: FarmActivity, employee_id: int) -> Employee | None:
    schedule = current_schedule(db, employee_id, task.activity_date)
    backup_id = task.backup_employee_id or (schedule.backup_employee_id if schedule else None)
    if not backup_id or backup_id == employee_id:
        return None
    backup = db.get(Employee, backup_id)
    if backup is None or backup.is_archived or backup.employment_status != "Active":
        return None
    availability = resolve_employee_availability(db, backup.id, task.activity_date, allow_future_attendance=True)
    if not availability.available or not employee_is_qualified_for_task(backup, task):
        return None
    return backup


def apply_confirmed_absence_coverage(
    db: Session,
    employee_id: int,
    work_date: date,
    *,
    status: str,
    actor_user_id: int | None,
    actor_name: str,
) -> dict[str, int]:
    summary = {"checked": 0, "covered": 0, "needs_coverage": 0, "preserved": 0}
    tasks = list(db.scalars(select(FarmActivity).where(
        FarmActivity.assigned_employee_id == employee_id,
        FarmActivity.activity_date == work_date,
        FarmActivity.status == "Pending",
        FarmActivity.is_archived == False,
    ).order_by(FarmActivity.id)).all())
    for task in tasks:
        summary["checked"] += 1
        if task.assignment_source in {"manager_override", "reassignment", "Leave Coverage"}:
            summary["preserved"] += 1
            continue
        old_id = task.assigned_employee_id
        old_source = task.assignment_source
        task.default_employee_id = task.default_employee_id or employee_id
        backup = _backup_for_task(db, task, employee_id)
        if backup is not None:
            task.assigned_employee_id = backup.id
            task.assigned_to = backup.full_name
            task.assignment_source = ATTENDANCE_COVERAGE_SOURCE
            task.needs_reassignment = False
            reason = f"Attendance coverage: {actor_name} confirmed {status} for {work_date.isoformat()}."
            record_assignment_change(
                db, task, old_employee_id=old_id, new_employee_id=backup.id,
                assignment_source=ATTENDANCE_COVERAGE_SOURCE, actor_user_id=actor_user_id,
                actor_name=actor_name, reason=reason, old_assignment_source=old_source,
                new_assignment_source=ATTENDANCE_COVERAGE_SOURCE, is_automatic=True,
                event_key=f"attendance-coverage:{task.id}:{work_date.isoformat()}:{status}:{backup.id}",
                default_employee_id=employee_id, coverage_date=work_date,
            )
            summary["covered"] += 1
        else:
            task.assigned_employee_id = None
            task.assigned_to = "Unassigned"
            task.assignment_source = ATTENDANCE_COVERAGE_SOURCE
            task.needs_reassignment = True
            record_assignment_change(
                db, task, old_employee_id=old_id, new_employee_id=None,
                assignment_source=ATTENDANCE_COVERAGE_SOURCE, actor_user_id=actor_user_id,
                actor_name=actor_name,
                reason=f"Attendance coverage required: {actor_name} confirmed {status}; no configured available backup is available.",
                old_assignment_source=old_source, new_assignment_source=ATTENDANCE_COVERAGE_SOURCE,
                is_automatic=True,
                event_key=f"attendance-needs-coverage:{task.id}:{work_date.isoformat()}:{status}",
                default_employee_id=employee_id, coverage_date=work_date,
            )
            summary["needs_coverage"] += 1
    return summary


def restore_attendance_coverage(
    db: Session,
    employee_id: int,
    work_date: date,
    *,
    actor_user_id: int | None,
    actor_name: str,
) -> dict[str, int]:
    summary = {"checked": 0, "returned": 0, "preserved": 0}
    histories = list(db.scalars(select(TaskAssignmentHistory).where(
        TaskAssignmentHistory.assignment_source == ATTENDANCE_COVERAGE_SOURCE,
        TaskAssignmentHistory.default_employee_id == employee_id,
        TaskAssignmentHistory.coverage_date == work_date,
        TaskAssignmentHistory.is_automatic == True,
    ).order_by(TaskAssignmentHistory.id)).all())
    task_ids = {row.activity_id for row in histories}
    tasks = {row.id: row for row in db.scalars(select(FarmActivity).where(FarmActivity.id.in_(task_ids))).all()} if task_ids else {}
    employee = db.get(Employee, employee_id)
    for task_id in sorted(task_ids):
        task = tasks.get(task_id)
        if task is None:
            continue
        summary["checked"] += 1
        if task.status != "Pending" or task.is_archived or task.assignment_source != ATTENDANCE_COVERAGE_SOURCE:
            summary["preserved"] += 1
            continue
        old_id = task.assigned_employee_id
        old_source = task.assignment_source
        task.assigned_employee_id = employee_id
        task.assigned_to = employee.full_name if employee else "Unassigned"
        task.assignment_source = "automatic_default"
        task.needs_reassignment = False
        record_assignment_change(
            db, task, old_employee_id=old_id, new_employee_id=employee_id,
            assignment_source="automatic_default", actor_user_id=actor_user_id, actor_name=actor_name,
            reason="Attendance correction restored the default employee for eligible pending work.",
            old_assignment_source=old_source, new_assignment_source="automatic_default", is_automatic=True,
            event_key=f"attendance-return:{task.id}:{work_date.isoformat()}:{employee_id}",
            default_employee_id=employee_id, coverage_date=work_date,
        )
        summary["returned"] += 1
    return summary


def set_confirmed_status(
    db: Session,
    employee_id: int,
    work_date: date,
    *,
    status: str,
    actor_user_id: int | None,
    actor_name: str,
    notes: str | None = None,
) -> tuple[StaffAttendance, dict[str, int]]:
    if status not in CONFIRMED_UNAVAILABLE:
        raise AttendanceError("Manager confirmation must be Absent or Sick.")
    if work_date > farm_today():
        raise AttendanceError("Future dates cannot be marked Absent or Sick.")
    availability = _availability_for_attendance(db, employee_id, work_date)
    if availability.leave_id is not None or availability.status in {"Rest Day", "Special Day Off", "Work Suspended", "Authorized Day Off"}:
        raise AttendanceError("Approved leave, rest days, special days off and suspended shifts cannot be marked Absent or Sick.")
    record = _ensure_record(db, employee_id, work_date, source=MANAGER_ASSISTED, actor_user_id=actor_user_id, availability=availability)
    before = _attendance_snapshot(record)
    record.status = status
    record.notes = (notes or "").strip() or None
    record.attendance_source = MANAGER_ASSISTED
    record.updated_by_user_id = actor_user_id
    _write_audit(db, record, action=f"Mark {status}", actor_user_id=actor_user_id, actor_name=actor_name, source=MANAGER_ASSISTED, reason=notes, before=before)
    coverage = apply_confirmed_absence_coverage(db, employee_id, work_date, status=status, actor_user_id=actor_user_id, actor_name=actor_name)
    return record, coverage


def correct_attendance(
    db: Session,
    employee_id: int,
    work_date: date,
    *,
    actor_user_id: int | None,
    actor_name: str,
    reason: str,
    status: str,
    check_in_at: datetime | None | object = _UNCHANGED,
    check_out_at: datetime | None | object = _UNCHANGED,
    notes: str | None = None,
) -> tuple[StaffAttendance, dict[str, int] | None]:
    if not (reason or "").strip():
        raise AttendanceError("Attendance corrections require a reason.")
    if work_date > farm_today():
        raise AttendanceError("Future attendance cannot be corrected into Present, Absent, Sick, or Late states.")
    availability = _availability_for_attendance(db, employee_id, work_date)
    if status in CONFIRMED_UNAVAILABLE and availability.suspension_full_shift:
        raise AttendanceError("An excused suspended shift cannot be corrected to Absent or Sick.")
    record = _ensure_record(db, employee_id, work_date, source=MANAGER_ASSISTED, actor_user_id=actor_user_id, availability=availability)
    before = _attendance_snapshot(record)
    previous_status = record.status
    effective_check_in = record.check_in_at if check_in_at is _UNCHANGED else check_in_at
    effective_check_out = record.check_out_at if check_out_at is _UNCHANGED else check_out_at
    if effective_check_in is not None and effective_check_in.date() != work_date:
        raise AttendanceError("Corrected Check In must belong to the selected work date.")
    if effective_check_out is not None and effective_check_out.date() != work_date:
        raise AttendanceError("Corrected Check Out must belong to the selected work date.")
    if effective_check_out is not None and effective_check_in is None:
        raise AttendanceError("Corrected Check Out requires a Check In timestamp.")
    if effective_check_out is not None and effective_check_in is not None and effective_check_out < effective_check_in:
        raise AttendanceError("Corrected Check Out cannot be before Check In.")
    record.status = status
    record.check_in_at = effective_check_in
    record.check_out_at = effective_check_out
    record.notes = (notes or record.notes or "").strip() or None
    record.correction_reason = reason.strip()
    record.attendance_source = MANAGER_ASSISTED
    record.updated_by_user_id = actor_user_id
    # Recalculate punctuality only when a valid schedule snapshot exists.
    settings = get_or_create_attendance_settings(db)
    if effective_check_in and record.scheduled_start_time:
        _, record.minutes_late = _punctuality_for_check_in(effective_check_in, work_date, record.scheduled_start_time, settings)
    else:
        record.minutes_late = None
    if effective_check_out and record.scheduled_end_time:
        end = _shift_datetime(work_date, record.scheduled_end_time)
        record.minutes_early = _minutes(end - effective_check_out) if effective_check_out < end else 0
        record.overtime_minutes = _minutes(effective_check_out - end) if effective_check_out > end else 0
    else:
        record.minutes_early = None
        record.overtime_minutes = None
    _write_audit(db, record, action="Attendance Correction", actor_user_id=actor_user_id, actor_name=actor_name, source=MANAGER_ASSISTED, reason=reason, before=before)
    coverage = None
    if status in CONFIRMED_UNAVAILABLE:
        coverage = apply_confirmed_absence_coverage(db, employee_id, work_date, status=status, actor_user_id=actor_user_id, actor_name=actor_name)
    elif previous_status in CONFIRMED_UNAVAILABLE and status in PRESENT_STATUSES:
        coverage = restore_attendance_coverage(db, employee_id, work_date, actor_user_id=actor_user_id, actor_name=actor_name)
    return record, coverage


def effective_attendance_status(db: Session, record: StaffAttendance, *, now: datetime | None = None) -> str:
    now = now or farm_now_naive()
    if record.check_in_at is None:
        availability = _availability_for_attendance(db, record.employee_id, record.attendance_date)
        if availability.status in {"Work Suspended", "Authorized Day Off"}:
            return availability.status
    if record.status in CONFIRMED_UNAVAILABLE or record.check_out_at is not None:
        return record.status
    if record.check_in_at is None:
        return record.status
    if record.scheduled_end_time and record.attendance_date < now.date():
        return "Missing Check Out"
    if record.scheduled_end_time and record.attendance_date == now.date():
        settings = get_or_create_attendance_settings(db)
        cutoff = datetime.combine(record.attendance_date, record.scheduled_end_time) + timedelta(minutes=settings.missing_checkout_cutoff_minutes)
        if now > cutoff:
            return "Missing Check Out"
    return record.status


def attendance_response_dict(db: Session, record: StaffAttendance, *, now: datetime | None = None) -> dict[str, Any]:
    employee = db.get(Employee, record.employee_id)
    audits = list(db.scalars(select(StaffAttendanceAudit).where(StaffAttendanceAudit.attendance_id == record.id).order_by(StaffAttendanceAudit.created_at, StaffAttendanceAudit.id)).all())
    worked_minutes = None
    if record.check_in_at and record.check_out_at:
        worked_minutes = max(0, int((record.check_out_at - record.check_in_at).total_seconds() // 60))
    return {
        "id": record.id,
        "employee_id": record.employee_id,
        "employee_name": employee.full_name if employee else None,
        "attendance_date": record.attendance_date,
        "scheduled_shift_id": record.scheduled_shift_id,
        "scheduled_start_time": record.scheduled_start_time,
        "scheduled_end_time": record.scheduled_end_time,
        "check_in_at": record.check_in_at,
        "check_out_at": record.check_out_at,
        "status": effective_attendance_status(db, record, now=now),
        "stored_status": record.status,
        "minutes_late": record.minutes_late,
        "minutes_early": record.minutes_early,
        "overtime_minutes": record.overtime_minutes,
        "worked_minutes": worked_minutes,
        "attendance_source": record.attendance_source,
        "notes": record.notes,
        "correction_reason": record.correction_reason,
        "recorded_by_user_id": record.recorded_by_user_id,
        "updated_by_user_id": record.updated_by_user_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "audit": [
            {
                "id": row.id,
                "action": row.action,
                "old_status": row.old_status,
                "new_status": row.new_status,
                "source": row.source,
                "reason": row.reason,
                "actor_user_id": row.actor_user_id,
                "actor_name": row.actor_name,
                "created_at": row.created_at,
            }
            for row in audits
        ],
    }
