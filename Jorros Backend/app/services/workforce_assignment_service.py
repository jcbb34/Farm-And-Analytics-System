from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Employee,
    FarmActivity,
    StaffAttendance,
    StaffLeave,
)


OPEN_ASSIGNMENT_STATUSES = frozenset({"Pending", "In Progress", "Returned"})
UNAVAILABLE_ATTENDANCE_STATUSES = frozenset(
    {"Absent", "Sick Leave", "Approved Leave", "Day Off"}
)


def employee_unavailability_reason(
    db: Session,
    employee_id: int | None,
    work_date: date,
) -> str | None:
    if employee_id is None:
        return "No employee is assigned"
    from app.services.work_schedule_service import resolve_employee_availability
    result = resolve_employee_availability(db, employee_id, work_date, allow_future_attendance=True)
    return None if result.available else result.reason


def assignment_needs_reassignment(
    db: Session,
    employee_id: int | None,
    work_date: date,
) -> bool:
    return employee_unavailability_reason(db, employee_id, work_date) is not None


def refresh_task_reassignment(
    db: Session,
    task: FarmActivity,
) -> bool:
    if task.is_archived or task.status not in OPEN_ASSIGNMENT_STATUSES:
        return bool(task.needs_reassignment)

    task.needs_reassignment = assignment_needs_reassignment(
        db,
        task.assigned_employee_id,
        task.activity_date,
    )
    return bool(task.needs_reassignment)


def recalculate_employee_task_availability(
    db: Session,
    employee_id: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    statement = select(FarmActivity).where(
        FarmActivity.assigned_employee_id == employee_id,
        FarmActivity.status.in_(OPEN_ASSIGNMENT_STATUSES),
        FarmActivity.is_archived == False,
    )
    if start_date is not None:
        statement = statement.where(FarmActivity.activity_date >= start_date)
    if end_date is not None:
        statement = statement.where(FarmActivity.activity_date <= end_date)

    changed = 0
    for task in db.scalars(statement).all():
        previous = bool(task.needs_reassignment)
        refresh_task_reassignment(db, task)
        if previous != bool(task.needs_reassignment):
            changed += 1
    return changed


def record_task_assignment_history(
    db: Session,
    *,
    task: FarmActivity,
    old_employee_id: int | None,
    old_employee_name: str | None,
    new_employee_id: int | None,
    new_employee_name: str | None,
    assignment_source: str,
    reason: str,
    actor_user_id: int | None,
    actor_name: str,
) -> None:
    old_label = old_employee_name or "Unassigned"
    new_label = new_employee_name or "Unassigned"
    action = (
        "Task reassigned"
        if old_employee_id is not None and new_employee_id is not None
        else "Task assigned"
        if new_employee_id is not None
        else "Task unassigned"
    )
    details = (
        f"Previous employee: {old_label} (ID: {old_employee_id or 'none'}). "
        f"New employee: {new_label} (ID: {new_employee_id or 'none'}). "
        f"Assignment source: {assignment_source}. "
        f"Reason: {reason}. "
        f"Task date: {task.activity_date.isoformat()}."
    )
    common = {
        "action": action,
        "module": "Workforce",
        "record_name": f"{task.activity_code} — {task.name}",
        "entity_id": str(task.id),
        "details": details,
        "icon": "assignment_ind",
        "actor_user_id": actor_user_id,
        "actor_name": actor_name,
    }
    db.add(AuditLog(event_type="audit", **common))
    db.add(AuditLog(event_type="timeline", **common))
