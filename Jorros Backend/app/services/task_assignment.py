from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import FarmActivity
from app.models.workforce import (
    Employee,
    StaffAttendance,
    StaffLeave,
    TaskAssignmentHistory,
)


OPEN_ASSIGNMENT_STATUSES = frozenset({"Pending", "In Progress", "Returned"})
PROTECTED_ASSIGNMENT_STATUSES = frozenset(
    {
        "Submitted for Review",
        "Completed",
        "Cancelled",
        "Resolved",
        # Defensive compatibility with any legacy/future workflow labels.
        "Approved",
        "Voided",
    }
)
UNAVAILABLE_ATTENDANCE_STATUSES = frozenset(
    {"Absent", "Sick", "Sick Leave", "Approved Leave", "Day Off"}
)
ASSIGNMENT_SOURCES = frozenset(
    {"manual", "automatic_default", "manager_override", "reassignment", "Leave Coverage", "Rest-Day Coverage", "Attendance Coverage"}
)


def assignment_is_protected(task: FarmActivity) -> bool:
    """Return True when assignment history must be treated as immutable."""
    return bool(task.is_archived or task.status in PROTECTED_ASSIGNMENT_STATUSES)


def employee_unavailability_reason(
    db: Session,
    employee_id: int | None,
    activity_date: date,
) -> str | None:
    if not employee_id:
        return "No active employee is assigned"
    # Import lazily to avoid a circular dependency: the schedule service also
    # reuses record_assignment_change from this module.
    from app.services.work_schedule_service import resolve_employee_availability
    result = resolve_employee_availability(
        db, employee_id, activity_date,
        # Assignment validation retains legacy semantics for explicitly stored
        # future absence rows; calendar display suppresses future attendance.
        allow_future_attendance=True,
    )
    return None if result.available else result.reason


def recalculate_task_reassignment(db: Session, task: FarmActivity) -> bool:
    """Recalculate only actionable work; historical/archived tasks are untouched."""
    if task.is_archived or task.status not in OPEN_ASSIGNMENT_STATUSES:
        return bool(task.needs_reassignment)

    reason = employee_unavailability_reason(
        db,
        task.assigned_employee_id,
        task.activity_date,
    )
    # Unassigned automatic work needs manager attention. A deliberately
    # unassigned manual task keeps its existing workflow semantics.
    task.needs_reassignment = bool(
        reason is not None
        and (task.assigned_employee_id is not None or task.is_automatic)
    )
    return bool(task.needs_reassignment)


def recalculate_employee_tasks(
    db: Session,
    employee_id: int,
    start_date: date,
    end_date: date,
) -> int:
    tasks = list(
        db.scalars(
            select(FarmActivity).where(
                FarmActivity.assigned_employee_id == employee_id,
                FarmActivity.activity_date >= start_date,
                FarmActivity.activity_date <= end_date,
                FarmActivity.status.in_(OPEN_ASSIGNMENT_STATUSES),
                FarmActivity.is_archived == False,
            )
        ).all()
    )
    for task in tasks:
        recalculate_task_reassignment(db, task)
    return len(tasks)


def record_assignment_change(
    db: Session,
    task: FarmActivity,
    *,
    old_employee_id: int | None,
    new_employee_id: int | None,
    assignment_source: str,
    actor_user_id: int | None,
    actor_name: str,
    reason: str,
    leave_id: int | None = None,
    old_assignment_source: str | None = None,
    new_assignment_source: str | None = None,
    is_automatic: bool = False,
    event_key: str | None = None,
    default_employee_id: int | None = None,
    schedule_id: int | None = None,
    schedule_exception_id: int | None = None,
    coverage_date: date | None = None,
) -> TaskAssignmentHistory | None:
    if old_employee_id == new_employee_id and (old_assignment_source or assignment_source) == (new_assignment_source or assignment_source):
        return None
    if assignment_source not in ASSIGNMENT_SOURCES:
        raise ValueError(f"Unsupported assignment source: {assignment_source}")

    if event_key:
        existing = db.scalar(
            select(TaskAssignmentHistory).where(TaskAssignmentHistory.event_key == event_key)
        )
        if existing is not None:
            return existing

    history = TaskAssignmentHistory(
        activity_id=task.id,
        old_employee_id=old_employee_id,
        new_employee_id=new_employee_id,
        assignment_source=assignment_source,
        leave_id=leave_id,
        old_assignment_source=old_assignment_source,
        new_assignment_source=new_assignment_source or assignment_source,
        is_automatic=bool(is_automatic),
        event_key=event_key,
        default_employee_id=default_employee_id,
        schedule_id=schedule_id,
        schedule_exception_id=schedule_exception_id,
        coverage_date=coverage_date,
        actor_user_id=actor_user_id,
        actor_name=(actor_name or "System").strip() or "System",
        reason=(reason or "Assignment changed").strip(),
    )
    db.add(history)
    return history
