"""Full duration checks shared by crop planning and workforce assignments."""
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.models import FarmActivity
from app.services.db_concurrency import acquire_transaction_lock
from app.services.work_schedule_service import resolve_employee_availability


def minutes(value):
    return value.hour * 60 + value.minute + value.second / 60 + value.microsecond / 60000000


def interval_conflict(db, employee_id, work_date, start, duration, *, exclude_ids=(), strict=True, proposed=()):
    if employee_id is None:
        return "Choose an employee for this enabled activity."
    acquire_transaction_lock(db, f"farm:employee-interval:{employee_id}:{work_date.isoformat()}")
    availability = resolve_employee_availability(db, employee_id, work_date, allow_future_attendance=True)
    if not availability.available:
        return availability.reason
    if availability.start_time is None or availability.end_time is None:
        return "Configure this employee's recorded working hours before scheduling care." if strict else None
    first, last = minutes(start), minutes(start) + duration
    if first < minutes(availability.start_time) or last > minutes(availability.end_time):
        return "The entire activity must fit within the employee's recorded working hours."
    if availability.break_start_time and availability.break_end_time:
        if first < minutes(availability.break_end_time) and last > minutes(availability.break_start_time):
            return "The activity overlaps the employee's recorded break."
    if availability.suspension_full_shift:
        return "A farm event makes this employee unavailable for the shift."
    begin_at = datetime.combine(work_date, start)
    end_at = begin_at + timedelta(minutes=duration)
    for suspension in availability.suspensions:
        first_at = datetime.fromisoformat(suspension["starts_at"]).replace(tzinfo=None)
        last_at = datetime.fromisoformat(suspension["ends_at"]).replace(tzinfo=None)
        if begin_at < last_at and end_at > first_at:
            return "The activity overlaps a recorded farm work suspension: " + suspension.get("title", "Farm event")
    tasks = list(db.scalars(select(FarmActivity).where(FarmActivity.assigned_employee_id == employee_id,
        FarmActivity.activity_date == work_date, FarmActivity.is_archived == False,
        FarmActivity.status.not_in(["Voided", "Cancelled", "Resolved"]), FarmActivity.id.not_in(list(exclude_ids)))).all())
    for task in tasks:
        if task.start_time is None:
            return f"{task.activity_code} has no recorded time; resolve its timing before scheduling competing work."
        begin = minutes(task.start_time)
        if task.end_time is None:
            if first < minutes(availability.end_time) and last > begin:
                return f"Conflicts with {task.activity_code}; its full duration has not been recorded."
            continue
        end = minutes(task.end_time)
        if first < end and last > begin:
            return f"Conflicts with {task.activity_code} ({task.name})."
    for item in proposed:
        if item["employee_id"] == employee_id and item["date"] == work_date and first < item["end"] and last > item["start"]:
            return "Two proposed activities overlap for the same employee."
    return None


def available_slots(db, employee_id, work_date, duration, *, exclude_ids=()):
    availability = resolve_employee_availability(db, employee_id, work_date, allow_future_attendance=True)
    if not availability.available or not availability.start_time or not availability.end_time:
        return {"slots": [], "reason": availability.reason if not availability.available else "Configure recorded working hours first."}
    current = datetime.combine(work_date, availability.start_time)
    stop = datetime.combine(work_date, availability.end_time)
    slots = []
    while current + timedelta(minutes=duration) <= stop:
        if not interval_conflict(db, employee_id, work_date, current.time(), duration, exclude_ids=exclude_ids):
            slots.append({"start_time": current.time().isoformat(timespec="seconds"), "end_time": (current + timedelta(minutes=duration)).time().isoformat(timespec="seconds")})
        current += timedelta(minutes=15)  # Display grid only; a typed time is validated without rounding.
    return {"slots": slots, "reason": None if slots else "No full-duration slots fit the recorded schedule and competing work."}


def validate_task_interval(db, task):
    if task.assigned_employee_id is None or not task.start_time or not task.end_time:
        return
    duration = minutes(task.end_time) - minutes(task.start_time)
    if duration <= 0:
        raise HTTPException(400, "The task's end time must follow its start time.")
    conflict = interval_conflict(db, task.assigned_employee_id, task.activity_date, task.start_time,
                                 duration, exclude_ids=[task.id] if task.id else [], strict=False)
    if conflict:
        raise HTTPException(409, conflict)
