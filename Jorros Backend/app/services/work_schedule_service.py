from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive, farm_today, farm_timezone_name
from app.models import (
    AttendanceSettings,
    Employee,
    EmployeeWorkSchedule,
    EmployeeWorkScheduleDay,
    FarmActivity,
    StaffAttendance,
    StaffLeave,
    StaffShift,
)
from app.services.task_assignment import assignment_is_protected, record_assignment_change


REST_COVERAGE_SOURCE = "Rest-Day Coverage"
AUTOMATIC_DEFAULT_SOURCE = "automatic_default"
SCHEDULE_EXCEPTION_TYPES = frozenset(
    {"Working Day Override", "Rest Day Override", "Special Day Off", "Changed Shift"}
)
REST_EXCEPTION_TYPES = frozenset({"Rest Day Override", "Special Day Off"})
WORKING_EXCEPTION_TYPES = SCHEDULE_EXCEPTION_TYPES - REST_EXCEPTION_TYPES
ABSENT_ATTENDANCE = frozenset({"Absent", "Sick", "Sick Leave", "Approved Leave", "Day Off"})
GENERAL_QUALIFICATION_TERMS = frozenset({"farm", "farmer", "general", "worker", "caretaker", "assistant", "manager", "supervisor"})
CROP_TERMS = frozenset({"crop", "field", "plant", "agronomy", "horticulture", "irrigation", "harvest", "nursery"})
LIVESTOCK_TERMS = frozenset({"livestock", "animal", "poultry", "goat", "pig", "swine", "duck", "chicken", "feeding", "veterinary"})
DEFAULT_CHECK_IN_GRACE_MINUTES = 5
DEFAULT_ATTENDANCE_REMINDER_MINUTES = 15


@dataclass(frozen=True)
class AvailabilityResult:
    employee_id: int
    work_date: date
    available: bool
    status: str
    reason: str
    schedule_status: str
    schedule_id: int | None = None
    schedule_exception_id: int | None = None
    exception_type: str | None = None
    is_working_day: bool | None = None
    start_time: object | None = None
    end_time: object | None = None
    break_start_time: object | None = None
    break_end_time: object | None = None
    attendance_status: str | None = None
    leave_id: int | None = None
    suspensions: list[dict] = field(default_factory=list)
    attendance_suspended_now: bool = False
    suspension_full_shift: bool = False

    def as_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "work_date": self.work_date,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "schedule_status": self.schedule_status,
            "schedule_id": self.schedule_id,
            "schedule_exception_id": self.schedule_exception_id,
            "exception_type": self.exception_type,
            "is_working_day": self.is_working_day,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "break_start_time": self.break_start_time,
            "break_end_time": self.break_end_time,
            "attendance_status": self.attendance_status,
            "leave_id": self.leave_id,
            "suspensions": self.suspensions,
            "attendance_suspended_now": self.attendance_suspended_now,
            "suspension_full_shift": self.suspension_full_shift,
        }


def _norm_words(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip(" ,.;:/\\()[]{}-").lower() for part in value.split() if part.strip(" ,.;:/\\()[]{}-")}


def employee_is_qualified_for_task(employee: Employee, task: FarmActivity) -> bool:
    words = _norm_words(" ".join(filter(None, [employee.position, employee.skills, employee.assigned_area])))
    if not words or words & GENERAL_QUALIFICATION_TERMS:
        return True
    domain = str(task.source_module or "").strip().lower()
    if domain == "crop" and (words & LIVESTOCK_TERMS) and not (words & CROP_TERMS):
        return False
    if domain == "livestock" and (words & CROP_TERMS) and not (words & LIVESTOCK_TERMS):
        return False
    return True


def current_schedule(db: Session, employee_id: int, work_date: date) -> EmployeeWorkSchedule | None:
    return db.scalar(
        select(EmployeeWorkSchedule)
        .where(
            EmployeeWorkSchedule.employee_id == employee_id,
            EmployeeWorkSchedule.status == "Active",
            EmployeeWorkSchedule.effective_from <= work_date,
            or_(
                EmployeeWorkSchedule.effective_to.is_(None),
                EmployeeWorkSchedule.effective_to >= work_date,
            ),
        )
        .order_by(EmployeeWorkSchedule.effective_from.desc(), EmployeeWorkSchedule.id.desc())
    )


def schedule_day(db: Session, schedule_id: int, work_date: date) -> EmployeeWorkScheduleDay | None:
    # Python weekday(): Monday=0 ... Sunday=6, matching stored day_of_week.
    return db.scalar(
        select(EmployeeWorkScheduleDay).where(
            EmployeeWorkScheduleDay.schedule_id == schedule_id,
            EmployeeWorkScheduleDay.day_of_week == work_date.weekday(),
        )
    )


def validate_roster_schedule_choice(
    db: Session, employee_id: int, work_date: date, status: str, exception_type: str | None,
) -> None:
    """A regular roster row alone cannot override the recurring weekly rest day."""
    if status == "Cancelled" or exception_type is not None:
        return
    schedule = current_schedule(db, employee_id, work_date)
    day = schedule_day(db, schedule.id, work_date) if schedule else None
    if day is not None and not day.is_working_day:
        raise ValueError(
            "This date is a weekly rest day. Select Working Day Override to schedule work, "
            "or select Rest Day Override / Special Day Off to keep the employee off."
        )


def _attendance_for_schedule(
    attendance: StaffAttendance | None, exception: StaffShift | None,
) -> StaffAttendance | None:
    # A dated working exception supersedes a legacy, unclocked rest-day marker.
    # Keep the historical row intact until an actual attendance action is taken.
    if (
        attendance is not None
        and attendance.status == "Day Off"
        and attendance.check_in_at is None
        and attendance.check_out_at is None
        and exception is not None
        and exception.exception_type in WORKING_EXCEPTION_TYPES
    ):
        return None
    return attendance


def _active_exception(db: Session, employee_id: int, work_date: date) -> StaffShift | None:
    return db.scalar(
        select(StaffShift).where(
            StaffShift.employee_id == employee_id,
            StaffShift.work_date == work_date,
            StaffShift.status != "Cancelled",
            StaffShift.exception_type.in_(SCHEDULE_EXCEPTION_TYPES),
        )
    )


def _attendance_detection_delays(db: Session) -> tuple[int, int]:
    settings = db.scalar(select(AttendanceSettings).order_by(AttendanceSettings.id).limit(1))
    if settings is None:
        return DEFAULT_CHECK_IN_GRACE_MINUTES, DEFAULT_ATTENDANCE_REMINDER_MINUTES
    return (
        max(0, int(settings.check_in_grace_minutes or 0)),
        max(0, int(settings.attendance_reminder_minutes or 0)),
    )


def _is_possible_absence(
    *,
    work_date: date,
    working: bool | None,
    start_time: time | None,
    attendance: StaffAttendance | None,
    now: datetime,
    check_in_grace_minutes: int,
    attendance_reminder_minutes: int,
) -> bool:
    """Infer a missed check-in without turning it into a confirmed absence."""
    if working is not True or start_time is None or work_date > now.date():
        return False
    if attendance is not None:
        if attendance.check_in_at is not None:
            return False
        if str(attendance.status or "").strip() not in {"", "Not Checked In"}:
            return False
    cutoff = datetime.combine(work_date, start_time) + timedelta(
        minutes=check_in_grace_minutes + attendance_reminder_minutes,
    )
    return now >= cutoff


def _resolve_employee_availability_base(
    db: Session,
    employee_id: int,
    work_date: date,
    *,
    allow_future_attendance: bool = False,
    now: datetime | None = None,
) -> AvailabilityResult:
    now = now or farm_now_naive()
    employee = db.get(Employee, employee_id)
    if employee is None:
        return AvailabilityResult(employee_id, work_date, False, "Unavailable", "Employee record is missing", "Needs Setup")
    if employee.is_archived:
        return AvailabilityResult(employee_id, work_date, False, "Unavailable", "Employee is archived", "Needs Setup")
    if employee.employment_status != "Active":
        return AvailabilityResult(employee_id, work_date, False, "Unavailable", f"Employee is {employee.employment_status.lower()}", "Needs Setup")

    # Highest priority: approved leave. A working-day override cannot defeat it.
    leave = db.scalar(
        select(StaffLeave).where(
            StaffLeave.employee_id == employee_id,
            StaffLeave.start_date <= work_date,
            StaffLeave.end_date >= work_date,
            StaffLeave.status == "Approved",
        )
    )
    if leave is not None:
        return AvailabilityResult(
            employee_id, work_date, False, "On Leave", f"Approved {leave.leave_type}",
            "Configured" if current_schedule(db, employee_id, work_date) else "Needs Setup",
            leave_id=leave.id,
        )

    schedule = current_schedule(db, employee_id, work_date)
    day = schedule_day(db, schedule.id, work_date) if schedule is not None else None
    exception = _active_exception(db, employee_id, work_date)

    schedule_status = "Configured" if schedule is not None else "Needs Setup"
    working = day.is_working_day if day is not None else None
    start_time = day.start_time if day is not None else None
    end_time = day.end_time if day is not None else None
    break_start = day.break_start_time if day is not None else None
    break_end = day.break_end_time if day is not None else None
    status = "Working Day" if working else "Rest Day" if working is False else "Schedule Needs Setup"
    reason = "Weekly working day" if working else "Scheduled weekly rest day" if working is False else "Weekly schedule setup required"

    # Dated exception has priority over the recurring weekly schedule.
    if exception is not None:
        if exception.exception_type in REST_EXCEPTION_TYPES:
            return AvailabilityResult(
                employee_id, work_date, False,
                "Special Day Off" if exception.exception_type == "Special Day Off" else "Rest Day",
                exception.exception_reason or exception.exception_type,
                schedule_status,
                schedule_id=schedule.id if schedule else None,
                schedule_exception_id=exception.id,
                exception_type=exception.exception_type,
                is_working_day=False,
            )
        # Working Day Override and Changed Shift make this a scheduled working day.
        working = True
        start_time = exception.start_time or start_time
        end_time = exception.end_time or end_time
        status = "Changed Shift" if exception.exception_type == "Changed Shift" else "Working Day"
        reason = exception.exception_reason or exception.exception_type

    if schedule is not None and working is False:
        return AvailabilityResult(
            employee_id, work_date, False, "Rest Day", reason, schedule_status,
            schedule_id=schedule.id,
            is_working_day=False,
            start_time=None,
            end_time=None,
        )

    # Legacy employees with no schedule preserve their prior availability rules.
    # Attendance on future calendar dates is never displayed/interpreted as Present/Absent.
    attendance = None
    if allow_future_attendance or work_date <= now.date():
        attendance = db.scalar(
            select(StaffAttendance).where(
                StaffAttendance.employee_id == employee_id,
                StaffAttendance.attendance_date == work_date,
            )
        )
    attendance = _attendance_for_schedule(attendance, exception)
    if attendance is not None and attendance.status in ABSENT_ATTENDANCE:
        return AvailabilityResult(
            employee_id, work_date, False, "Unavailable", f"Employee unavailable: {attendance.status}", schedule_status,
            schedule_id=schedule.id if schedule else None,
            schedule_exception_id=exception.id if exception else None,
            exception_type=exception.exception_type if exception else None,
            is_working_day=working,
            start_time=start_time,
            end_time=end_time,
            break_start_time=break_start,
            break_end_time=break_end,
            attendance_status=attendance.status,
        )

    check_in_grace, reminder_delay = _attendance_detection_delays(db)
    if _is_possible_absence(
        work_date=work_date,
        working=working,
        start_time=start_time,
        attendance=attendance,
        now=now,
        check_in_grace_minutes=check_in_grace,
        attendance_reminder_minutes=reminder_delay,
    ):
        return AvailabilityResult(
            employee_id, work_date, True,
            "Possible Absence",
            "No check-in was recorded after the scheduled start, grace period, and reminder window. Manager confirmation is required.",
            schedule_status,
            schedule_id=schedule.id if schedule else None,
            schedule_exception_id=exception.id if exception else None,
            exception_type=exception.exception_type if exception else None,
            is_working_day=working,
            start_time=start_time,
            end_time=end_time,
            break_start_time=break_start,
            break_end_time=break_end,
            attendance_status=attendance.status if attendance is not None else None,
        )

    return AvailabilityResult(
        employee_id, work_date, True,
        status if schedule is not None or exception is not None else "Schedule Needs Setup",
        reason if schedule is not None or exception is not None else "Legacy availability preserved until weekly schedule is configured",
        schedule_status,
        schedule_id=schedule.id if schedule else None,
        schedule_exception_id=exception.id if exception else None,
        exception_type=exception.exception_type if exception else None,
        is_working_day=working,
        start_time=start_time,
        end_time=end_time,
        break_start_time=break_start,
        break_end_time=break_end,
        attendance_status=attendance.status if attendance is not None else None,
    )


def _resolve_availability_range_base(
    db: Session,
    employee_ids: Iterable[int],
    date_from: date,
    date_to: date,
    *,
    now: datetime | None = None,
) -> list[AvailabilityResult]:
    """Resolve a calendar range while preloading the relevant rows to avoid cell-by-cell DB queries."""
    ids = sorted({int(value) for value in employee_ids if value})
    if not ids or date_to < date_from:
        return []

    now = now or farm_now_naive()
    employees = {row.id: row for row in db.scalars(select(Employee).where(Employee.id.in_(ids))).all()}
    schedules = list(db.scalars(
        select(EmployeeWorkSchedule).where(
            EmployeeWorkSchedule.employee_id.in_(ids),
            EmployeeWorkSchedule.status == "Active",
            EmployeeWorkSchedule.effective_from <= date_to,
            or_(EmployeeWorkSchedule.effective_to.is_(None), EmployeeWorkSchedule.effective_to >= date_from),
        ).order_by(EmployeeWorkSchedule.employee_id, EmployeeWorkSchedule.effective_from.desc(), EmployeeWorkSchedule.id.desc())
    ).all())
    schedule_ids = [row.id for row in schedules]
    days = list(db.scalars(select(EmployeeWorkScheduleDay).where(EmployeeWorkScheduleDay.schedule_id.in_(schedule_ids))).all()) if schedule_ids else []
    exceptions = list(db.scalars(select(StaffShift).where(
        StaffShift.employee_id.in_(ids), StaffShift.work_date >= date_from, StaffShift.work_date <= date_to,
        StaffShift.status != "Cancelled", StaffShift.exception_type.in_(SCHEDULE_EXCEPTION_TYPES),
    )).all())
    leaves = list(db.scalars(select(StaffLeave).where(
        StaffLeave.employee_id.in_(ids), StaffLeave.start_date <= date_to, StaffLeave.end_date >= date_from,
        StaffLeave.status == "Approved",
    )).all())
    today = now.date()
    attendance_to = min(date_to, today)
    attendance = list(db.scalars(select(StaffAttendance).where(
        StaffAttendance.employee_id.in_(ids), StaffAttendance.attendance_date >= date_from,
        StaffAttendance.attendance_date <= attendance_to,
    )).all()) if attendance_to >= date_from else []

    days_by_schedule = {(row.schedule_id, row.day_of_week): row for row in days}
    exception_by_key = {(row.employee_id, row.work_date): row for row in exceptions}
    attendance_by_key = {(row.employee_id, row.attendance_date): row for row in attendance}
    leaves_by_employee: dict[int, list[StaffLeave]] = {}
    for row in leaves:
        leaves_by_employee.setdefault(row.employee_id, []).append(row)
    schedules_by_employee: dict[int, list[EmployeeWorkSchedule]] = {}
    for row in schedules:
        schedules_by_employee.setdefault(row.employee_id, []).append(row)
    check_in_grace, reminder_delay = _attendance_detection_delays(db)

    results: list[AvailabilityResult] = []
    current = date_from
    while current <= date_to:
        for employee_id in ids:
            employee = employees.get(employee_id)
            if employee is None or employee.is_archived or employee.employment_status != "Active":
                reason = "Employee record is missing" if employee is None else "Employee is archived" if employee.is_archived else f"Employee is {employee.employment_status.lower()}"
                results.append(AvailabilityResult(employee_id, current, False, "Unavailable", reason, "Needs Setup"))
                continue
            active_schedule = next((row for row in schedules_by_employee.get(employee_id, []) if row.effective_from <= current and (row.effective_to is None or row.effective_to >= current)), None)
            leave = next((row for row in leaves_by_employee.get(employee_id, []) if row.start_date <= current <= row.end_date), None)
            if leave is not None:
                results.append(AvailabilityResult(employee_id, current, False, "On Leave", f"Approved {leave.leave_type}", "Configured" if active_schedule else "Needs Setup", schedule_id=active_schedule.id if active_schedule else None, leave_id=leave.id))
                continue
            day = days_by_schedule.get((active_schedule.id, current.weekday())) if active_schedule else None
            exception = exception_by_key.get((employee_id, current))
            schedule_status = "Configured" if active_schedule else "Needs Setup"
            working = day.is_working_day if day else None
            start = day.start_time if day else None
            end = day.end_time if day else None
            break_start = day.break_start_time if day else None
            break_end = day.break_end_time if day else None
            status = "Working Day" if working else "Rest Day" if working is False else "Schedule Needs Setup"
            reason = "Weekly working day" if working else "Scheduled weekly rest day" if working is False else "Weekly schedule setup required"
            if exception:
                if exception.exception_type in REST_EXCEPTION_TYPES:
                    results.append(AvailabilityResult(employee_id, current, False, "Special Day Off" if exception.exception_type == "Special Day Off" else "Rest Day", exception.exception_reason or exception.exception_type, schedule_status, schedule_id=active_schedule.id if active_schedule else None, schedule_exception_id=exception.id, exception_type=exception.exception_type, is_working_day=False))
                    continue
                working = True
                start = exception.start_time or start
                end = exception.end_time or end
                status = "Changed Shift" if exception.exception_type == "Changed Shift" else "Working Day"
                reason = exception.exception_reason or exception.exception_type
            if active_schedule and working is False:
                results.append(AvailabilityResult(employee_id, current, False, "Rest Day", reason, schedule_status, schedule_id=active_schedule.id, is_working_day=False))
                continue
            att = _attendance_for_schedule(attendance_by_key.get((employee_id, current)), exception)
            if att and att.status in ABSENT_ATTENDANCE:
                results.append(AvailabilityResult(employee_id, current, False, "Unavailable", f"Employee unavailable: {att.status}", schedule_status, schedule_id=active_schedule.id if active_schedule else None, schedule_exception_id=exception.id if exception else None, exception_type=exception.exception_type if exception else None, is_working_day=working, start_time=start, end_time=end, break_start_time=break_start, break_end_time=break_end, attendance_status=att.status))
                continue
            if _is_possible_absence(
                work_date=current,
                working=working,
                start_time=start,
                attendance=att,
                now=now,
                check_in_grace_minutes=check_in_grace,
                attendance_reminder_minutes=reminder_delay,
            ):
                results.append(AvailabilityResult(
                    employee_id, current, True, "Possible Absence",
                    "No check-in was recorded after the scheduled start, grace period, and reminder window. Manager confirmation is required.",
                    schedule_status,
                    schedule_id=active_schedule.id if active_schedule else None,
                    schedule_exception_id=exception.id if exception else None,
                    exception_type=exception.exception_type if exception else None,
                    is_working_day=working,
                    start_time=start,
                    end_time=end,
                    break_start_time=break_start,
                    break_end_time=break_end,
                    attendance_status=att.status if att else None,
                ))
                continue
            results.append(AvailabilityResult(employee_id, current, True, status, reason if active_schedule or exception else "Legacy availability preserved until weekly schedule is configured", schedule_status, schedule_id=active_schedule.id if active_schedule else None, schedule_exception_id=exception.id if exception else None, exception_type=exception.exception_type if exception else None, is_working_day=working, start_time=start, end_time=end, break_start_time=break_start, break_end_time=break_end, attendance_status=att.status if att else None))
        current += timedelta(days=1)
    return results


def resolve_employee_availability(db, employee_id, work_date, *, allow_future_attendance=False, now=None):
    from app.services.farm_event_service import decorate_availability, event_context
    result = _resolve_employee_availability_base(db, employee_id, work_date, allow_future_attendance=allow_future_attendance, now=now)
    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_archived or employee.employment_status != "Active":
        return result
    return decorate_availability(db, result, employee, context=event_context(db), now=now)


def resolve_availability_range(db, employee_ids, date_from, date_to, *, now=None):
    from app.services.farm_event_service import decorate_availability, event_context
    results = _resolve_availability_range_base(db, employee_ids, date_from, date_to, now=now)
    context = event_context(db)
    if not context["events"]:
        return results
    employees = {x.id: x for x in db.scalars(select(Employee)).all()}
    return [decorate_availability(db, result, employees.get(result.employee_id), context=context, now=now)
            if result.employee_id in employees and employees[result.employee_id].employment_status == "Active"
            and not employees[result.employee_id].is_archived else result for result in results]


def schedule_response(db: Session, schedule: EmployeeWorkSchedule | None) -> dict | None:
    if schedule is None:
        return None
    days = list(db.scalars(select(EmployeeWorkScheduleDay).where(EmployeeWorkScheduleDay.schedule_id == schedule.id).order_by(EmployeeWorkScheduleDay.day_of_week)).all())
    backup = db.get(Employee, schedule.backup_employee_id) if schedule.backup_employee_id else None
    return {
        "id": schedule.id,
        "employee_id": schedule.employee_id,
        "effective_from": schedule.effective_from,
        "effective_to": schedule.effective_to,
        "timezone": schedule.timezone,
        "schedule_type": schedule.schedule_type,
        "backup_employee_id": schedule.backup_employee_id,
        "backup_employee_name": backup.full_name if backup else None,
        "status": schedule.status,
        "days": days,
    }


def employee_schedule_metadata(db: Session, employee_id: int, *, reference_date: date | None = None) -> dict:
    reference_date = reference_date or farm_today()
    schedule = current_schedule(db, employee_id, reference_date)
    if schedule is None:
        # A future schedule still counts as configured, but should not rewrite current/past availability.
        schedule = db.scalar(select(EmployeeWorkSchedule).where(EmployeeWorkSchedule.employee_id == employee_id, EmployeeWorkSchedule.status == "Active").order_by(EmployeeWorkSchedule.effective_from.desc(), EmployeeWorkSchedule.id.desc()))
        if schedule is None:
            return {"schedule_status": "Needs Setup", "weekly_schedule_summary": None, "next_rest_day": None, "weekly_schedule": None}
    rows = list(db.scalars(select(EmployeeWorkScheduleDay).where(EmployeeWorkScheduleDay.schedule_id == schedule.id).order_by(EmployeeWorkScheduleDay.day_of_week)).all())
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if schedule.schedule_type == "Rotating / No Fixed Rest Day":
        summary = "Rotating / No Fixed Rest Day"
        next_rest = None
    else:
        work_labels = [labels[row.day_of_week] for row in rows if row.is_working_day]
        rest_labels = [labels[row.day_of_week] for row in rows if not row.is_working_day]
        summary = f"Working: {', '.join(work_labels) or 'None'} · Rest: {', '.join(rest_labels) or 'None'}"
        rest_days = {row.day_of_week for row in rows if not row.is_working_day}
        next_rest = None
        for offset in range(0, 15):
            candidate = reference_date + timedelta(days=offset)
            if candidate >= schedule.effective_from and (schedule.effective_to is None or candidate <= schedule.effective_to) and candidate.weekday() in rest_days:
                next_rest = candidate
                break
    return {"schedule_status": "Configured", "weekly_schedule_summary": summary, "next_rest_day": next_rest, "weekly_schedule": schedule_response(db, schedule)}


def replace_employee_schedule(db: Session, *, employee: Employee, payload, actor_user_id: int | None) -> EmployeeWorkSchedule:
    if payload.backup_employee_id == employee.id:
        raise ValueError("An employee cannot be their own backup employee.")
    if payload.backup_employee_id:
        backup = db.get(Employee, payload.backup_employee_id)
        if backup is None or backup.is_archived or backup.employment_status != "Active":
            raise ValueError("Configured backup employee must be an active employee.")

    same_start = db.scalar(select(EmployeeWorkSchedule).where(
        EmployeeWorkSchedule.employee_id == employee.id,
        EmployeeWorkSchedule.status == "Active",
        EmployeeWorkSchedule.effective_from == payload.effective_from,
    ).order_by(EmployeeWorkSchedule.id.desc()))
    if same_start is not None:
        schedule = same_start
        schedule.effective_to = payload.effective_to
        schedule.timezone = payload.timezone
        schedule.schedule_type = payload.schedule_type
        schedule.backup_employee_id = payload.backup_employee_id
        schedule.updated_by_user_id = actor_user_id
        old_days = list(db.scalars(select(EmployeeWorkScheduleDay).where(EmployeeWorkScheduleDay.schedule_id == schedule.id)).all())
        by_dow = {row.day_of_week: row for row in old_days}
        for item in payload.days:
            row = by_dow.get(item.day_of_week)
            if row is None:
                row = EmployeeWorkScheduleDay(schedule_id=schedule.id, day_of_week=item.day_of_week, is_working_day=True)
                db.add(row)
            row.is_working_day = item.state == "Working Day"
            row.start_time = item.start_time if row.is_working_day else None
            row.end_time = item.end_time if row.is_working_day else None
            row.break_start_time = item.break_start_time if row.is_working_day else None
            row.break_end_time = item.break_end_time if row.is_working_day else None
        db.flush()
        return schedule

    # Close only schedules that would overlap the new effective period. This preserves historical rows.
    overlapping = list(db.scalars(select(EmployeeWorkSchedule).where(
        EmployeeWorkSchedule.employee_id == employee.id,
        EmployeeWorkSchedule.status == "Active",
        EmployeeWorkSchedule.effective_from < payload.effective_from,
        or_(EmployeeWorkSchedule.effective_to.is_(None), EmployeeWorkSchedule.effective_to >= payload.effective_from),
    )).all())
    for row in overlapping:
        row.effective_to = payload.effective_from - timedelta(days=1)
        row.updated_by_user_id = actor_user_id

    schedule = EmployeeWorkSchedule(
        employee_id=employee.id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        timezone=payload.timezone,
        schedule_type=payload.schedule_type,
        backup_employee_id=payload.backup_employee_id,
        status="Active",
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(schedule)
    db.flush()
    for item in payload.days:
        working = item.state == "Working Day"
        db.add(EmployeeWorkScheduleDay(
            schedule_id=schedule.id,
            day_of_week=item.day_of_week,
            is_working_day=working,
            start_time=item.start_time if working else None,
            end_time=item.end_time if working else None,
            break_start_time=item.break_start_time if working else None,
            break_end_time=item.break_end_time if working else None,
        ))
    db.flush()
    return schedule


def _rest_or_special_unavailability(result: AvailabilityResult) -> bool:
    return result.status in {"Rest Day", "Special Day Off"}


def apply_schedule_aware_assignment(
    db: Session,
    task: FarmActivity,
    *,
    default_employee_id: int | None = None,
    actor_user_id: int | None = None,
    actor_name: str = "System",
) -> str:
    """Apply rest-day coverage to one task occurrence without committing.

    Leave Coverage, manager overrides, manual reassignments and protected workflow states
    are deliberately preserved. The function is idempotent through occurrence identity +
    assignment-history event_key.
    """
    if assignment_is_protected(task):
        return "protected"
    if task.status != "Pending" or task.is_archived:
        return "protected"
    if task.assignment_source in {"manager_override", "reassignment", "Leave Coverage"}:
        return "preserved"

    default_id = default_employee_id or task.default_employee_id or task.assigned_employee_id
    if not default_id:
        if task.is_automatic:
            task.needs_reassignment = True
        return "no-default"
    task.default_employee_id = default_id

    default_result = resolve_employee_availability(db, default_id, task.activity_date)
    if default_result.status in {"Work Suspended", "Authorized Day Off"}:
        return "held"
    # Approved leave is owned by the existing Leave Coverage workflow, not Rest-Day Coverage.
    if default_result.leave_id is not None:
        task.needs_reassignment = True
        return "leave"

    if default_result.available:
        # Only automatically return work that is still owned by the rest-day coverage mechanism.
        if task.assignment_source == REST_COVERAGE_SOURCE or task.assigned_employee_id in {None, default_id}:
            old_id = task.assigned_employee_id
            old_source = task.assignment_source
            default_employee = db.get(Employee, default_id)
            task.assigned_employee_id = default_id
            task.assigned_to = default_employee.full_name if default_employee else "Unassigned"
            task.assignment_source = AUTOMATIC_DEFAULT_SOURCE
            task.needs_reassignment = False
            if old_id != default_id or old_source != AUTOMATIC_DEFAULT_SOURCE:
                record_assignment_change(
                    db, task,
                    old_employee_id=old_id,
                    new_employee_id=default_id,
                    assignment_source=AUTOMATIC_DEFAULT_SOURCE,
                    actor_user_id=actor_user_id,
                    actor_name=actor_name,
                    reason="Default employee is available again after schedule reconciliation.",
                    old_assignment_source=old_source,
                    new_assignment_source=AUTOMATIC_DEFAULT_SOURCE,
                    is_automatic=True,
                    event_key=f"schedule-return:{task.id}:{task.activity_date.isoformat()}:{default_id}",
                    default_employee_id=default_id,
                    schedule_id=default_result.schedule_id,
                    schedule_exception_id=default_result.schedule_exception_id,
                    coverage_date=task.activity_date,
                )
            return "default"
        return "preserved"

    if not _rest_or_special_unavailability(default_result):
        task.needs_reassignment = True
        return "unavailable"

    schedule = current_schedule(db, default_id, task.activity_date)
    backup_id = task.backup_employee_id or (schedule.backup_employee_id if schedule else None)
    backup = db.get(Employee, backup_id) if backup_id else None
    backup_result = resolve_employee_availability(db, backup_id, task.activity_date) if backup_id else None
    valid_backup = bool(
        backup is not None
        and backup.id != default_id
        and not backup.is_archived
        and backup.employment_status == "Active"
        and backup_result is not None
        and backup_result.available
        and employee_is_qualified_for_task(backup, task)
    )

    old_id = task.assigned_employee_id
    old_source = task.assignment_source
    if valid_backup:
        task.assigned_employee_id = backup.id
        task.assigned_to = backup.full_name
        task.assignment_source = REST_COVERAGE_SOURCE
        task.needs_reassignment = False
        reason = f"Covered Task — {db.get(Employee, default_id).full_name if db.get(Employee, default_id) else 'Default employee'} is on a scheduled rest day."
        if old_id != backup.id or old_source != REST_COVERAGE_SOURCE:
            record_assignment_change(
                db, task,
                old_employee_id=old_id,
                new_employee_id=backup.id,
                assignment_source=REST_COVERAGE_SOURCE,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                reason=reason,
                old_assignment_source=old_source,
                new_assignment_source=REST_COVERAGE_SOURCE,
                is_automatic=True,
                event_key=f"rest-coverage:{task.id}:{task.activity_date.isoformat()}:{backup.id}:{default_result.schedule_id or 0}:{default_result.schedule_exception_id or 0}",
                default_employee_id=default_id,
                schedule_id=default_result.schedule_id,
                schedule_exception_id=default_result.schedule_exception_id,
                coverage_date=task.activity_date,
            )
        return "covered"

    task.assigned_employee_id = None
    task.assigned_to = "Unassigned"
    task.assignment_source = REST_COVERAGE_SOURCE
    task.needs_reassignment = True
    if old_id is not None or old_source != REST_COVERAGE_SOURCE:
        record_assignment_change(
            db, task,
            old_employee_id=old_id,
            new_employee_id=None,
            assignment_source=REST_COVERAGE_SOURCE,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            reason="Default employee is on a scheduled rest day and no configured available/qualified backup employee is available. Needs Coverage.",
            old_assignment_source=old_source,
            new_assignment_source=REST_COVERAGE_SOURCE,
            is_automatic=True,
            event_key=f"rest-needs-coverage:{task.id}:{task.activity_date.isoformat()}:{default_result.schedule_id or 0}:{default_result.schedule_exception_id or 0}",
            default_employee_id=default_id,
            schedule_id=default_result.schedule_id,
            schedule_exception_id=default_result.schedule_exception_id,
            coverage_date=task.activity_date,
        )
    return "needs-coverage"


def reconcile_employee_future_tasks(
    db: Session,
    employee_id: int,
    *,
    from_date: date | None = None,
    actor_user_id: int | None = None,
    actor_name: str = "System",
) -> dict[str, int]:
    start = max(from_date or farm_today(), farm_today())
    tasks = list(db.scalars(select(FarmActivity).where(
        FarmActivity.is_archived == False,
        FarmActivity.is_automatic == True,
        FarmActivity.status == "Pending",
        FarmActivity.activity_date >= start,
        FarmActivity.default_employee_id == employee_id,
        FarmActivity.assignment_source.in_([AUTOMATIC_DEFAULT_SOURCE, REST_COVERAGE_SOURCE]),
    ).order_by(FarmActivity.activity_date, FarmActivity.id)).all())
    summary = {"checked": 0, "default": 0, "covered": 0, "needs_coverage": 0, "preserved": 0}
    for task in tasks:
        summary["checked"] += 1
        outcome = apply_schedule_aware_assignment(db, task, default_employee_id=employee_id, actor_user_id=actor_user_id, actor_name=actor_name)
        if outcome == "default":
            summary["default"] += 1
        elif outcome == "covered":
            summary["covered"] += 1
        elif outcome == "needs-coverage":
            summary["needs_coverage"] += 1
        else:
            summary["preserved"] += 1
    return summary
