from __future__ import annotations

from datetime import date, datetime
import re

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive, farm_today
from app.models import (
    Crop,
    Employee,
    FarmActivity,
    FarmAlert,
    Livestock,
    StaffAttendance,
    StaffLeave,
    StaffShift,
    TaskAssignmentHistory,
    TaskLeaveCoverage,
    TaskSubmission,
)
from app.services.task_assignment import (
    employee_unavailability_reason,
    recalculate_task_reassignment,
    record_assignment_change,
)


COVERAGE_ASSIGNMENT_SOURCE = "Leave Coverage"
COVERAGE_ACTIVE_STATUSES = frozenset({"Active", "Needs Reassignment", "Urgent Review"})
PROTECTED_LEAVE_TASK_STATUSES = frozenset(
    {"Submitted for Review", "Completed", "Approved", "Voided", "Cancelled", "Resolved"}
)
GENERAL_QUALIFICATION_TERMS = frozenset(
    {"farmer", "farm", "worker", "general", "caretaker", "technician", "manager"}
)
CROP_TERMS = frozenset(
    {"crop", "field", "plant", "corn", "tomato", "okra", "vegetable", "fertilizer", "pesticide", "harvest"}
)
LIVESTOCK_TERMS = frozenset(
    {"livestock", "animal", "poultry", "chicken", "duck", "goat", "pig", "swine", "feed", "vaccine", "vaccination"}
)


def _norm_words(value: str | None) -> set[str]:
    return {
        word
        for word in re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split()
        if len(word) >= 3
    }


def _employee_label(employee: Employee | None) -> str:
    return employee.full_name if employee is not None else "Unassigned"


def _source_default_employee_id(db: Session, task: FarmActivity) -> int | None:
    if task.source_module == "Crop" and task.source_record_id:
        source = db.get(Crop, task.source_record_id)
        return getattr(source, "assigned_employee_id", None) if source is not None else None
    if task.source_module == "Livestock" and task.source_record_id:
        source = db.get(Livestock, task.source_record_id)
        return getattr(source, "assigned_employee_id", None) if source is not None else None
    return None


def _task_has_submission(db: Session, task_id: int) -> bool:
    return db.scalar(
        select(TaskSubmission.id).where(TaskSubmission.activity_id == task_id).limit(1)
    ) is not None


def _existing_coverage(db: Session, task_id: int, leave_id: int) -> TaskLeaveCoverage | None:
    return db.scalar(
        select(TaskLeaveCoverage).where(
            TaskLeaveCoverage.activity_id == task_id,
            TaskLeaveCoverage.leave_id == leave_id,
        )
    )


def _upsert_manager_alert(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    alert_type: str,
    subject: str,
    description: str,
    priority: str = "High",
) -> None:
    alert = db.scalar(
        select(FarmAlert).where(
            FarmAlert.is_automatic == True,
            FarmAlert.source_type == source_type,
            FarmAlert.source_id == source_id,
            FarmAlert.alert_type == alert_type,
        )
    )
    if alert is None:
        db.add(
            FarmAlert(
                alert_name=alert_type,
                category="Task",
                subject=subject[:180],
                alert_type=alert_type[:100],
                condition="Review",
                threshold="Manager action required",
                unit=None,
                priority=priority,
                status="Active",
                is_automatic=True,
                source_type=source_type[:60],
                source_id=source_id,
                description=description,
                last_triggered=farm_now_naive(),
                created_by_user_id=None,
            )
        )
    else:
        alert.subject = subject[:180]
        alert.description = description
        alert.priority = priority
        alert.status = "Active"
        alert.last_triggered = farm_now_naive()


def affected_tasks_for_leave(db: Session, leave: StaffLeave) -> list[FarmActivity]:
    return list(
        db.scalars(
            select(FarmActivity)
            .where(
                FarmActivity.assigned_employee_id == leave.employee_id,
                FarmActivity.activity_date >= leave.start_date,
                FarmActivity.activity_date <= leave.end_date,
                FarmActivity.is_archived == False,
            )
            .order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
        ).all()
    )


def leave_overlap_context(db: Session, leave: StaffLeave) -> dict:
    attendance = list(
        db.scalars(
            select(StaffAttendance)
            .where(
                StaffAttendance.employee_id == leave.employee_id,
                StaffAttendance.attendance_date >= leave.start_date,
                StaffAttendance.attendance_date <= leave.end_date,
            )
            .order_by(StaffAttendance.attendance_date)
        ).all()
    )
    shifts = list(
        db.scalars(
            select(StaffShift)
            .where(
                StaffShift.employee_id == leave.employee_id,
                StaffShift.work_date >= leave.start_date,
                StaffShift.work_date <= leave.end_date,
                StaffShift.status != "Cancelled",
            )
            .order_by(StaffShift.work_date, StaffShift.start_time)
        ).all()
    )
    other_leave = list(
        db.scalars(
            select(StaffLeave)
            .where(
                StaffLeave.employee_id == leave.employee_id,
                StaffLeave.id != leave.id,
                StaffLeave.start_date <= leave.end_date,
                StaffLeave.end_date >= leave.start_date,
                StaffLeave.status.in_(["Pending", "Approved"]),
            )
            .order_by(StaffLeave.start_date)
        ).all()
    )
    return {"attendance": attendance, "shifts": shifts, "leave": other_leave}


def coverage_candidate_check(
    db: Session,
    employee: Employee,
    task: FarmActivity,
    *,
    leave_employee_id: int,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if employee.id == leave_employee_id:
        blockers.append("Employee taking leave cannot cover their own task.")
    if employee.is_archived:
        blockers.append("Employee is archived.")
    if employee.employment_status != "Active":
        blockers.append(f"Employee is {employee.employment_status.lower()}.")

    unavailable = employee_unavailability_reason(db, employee.id, task.activity_date)
    if unavailable:
        blockers.append(unavailable)

    task_domain = str(task.source_module or "").strip().lower()
    employee_words = _norm_words(" ".join(filter(None, [employee.position, employee.skills, employee.assigned_area])))
    if employee_words and not (employee_words & GENERAL_QUALIFICATION_TERMS):
        if task_domain == "crop" and (employee_words & LIVESTOCK_TERMS) and not (employee_words & CROP_TERMS):
            blockers.append("Employee qualifications appear livestock-specific for this crop task.")
        if task_domain == "livestock" and (employee_words & CROP_TERMS) and not (employee_words & LIVESTOCK_TERMS):
            blockers.append("Employee qualifications appear crop-specific for this livestock task.")

    if employee.assigned_area and task.location:
        area_words = _norm_words(employee.assigned_area)
        location_words = _norm_words(task.location)
        if area_words and location_words and not (area_words & location_words):
            warnings.append(
                f"Assigned area '{employee.assigned_area}' does not clearly match task location '{task.location}'."
            )

    if not employee.position and not employee.skills:
        warnings.append("No position/skills are recorded, so qualification must be confirmed by the reviewer.")

    return blockers, warnings


def covering_employee_candidates(
    db: Session,
    *,
    leave: StaffLeave,
    tasks: list[FarmActivity] | None = None,
) -> list[dict]:
    tasks = tasks if tasks is not None else affected_tasks_for_leave(db, leave)
    employees = list(
        db.scalars(
            select(Employee)
            .where(
                Employee.is_archived == False,
                Employee.employment_status == "Active",
                Employee.id != leave.employee_id,
            )
            .order_by(Employee.full_name)
        ).all()
    )
    result: list[dict] = []
    for employee in employees:
        warnings: list[str] = []
        blockers: list[str] = []
        per_task: dict[str, dict] = {}
        for task in tasks:
            task_blockers, task_warnings = coverage_candidate_check(
                db, employee, task, leave_employee_id=leave.employee_id
            )
            per_task[str(task.id)] = {
                "available": not task_blockers,
                "blockers": task_blockers,
                "warnings": task_warnings,
            }
            blockers.extend(f"{task.activity_date}: {message}" for message in task_blockers)
            warnings.extend(f"{task.activity_date}: {message}" for message in task_warnings)
        result.append(
            {
                "employee": employee,
                "available_for_all": not blockers,
                "blockers": list(dict.fromkeys(blockers)),
                "warnings": list(dict.fromkeys(warnings)),
                "task_availability": per_task,
            }
        )
    return result


def _coverage_reason(leave: StaffLeave) -> str:
    parts = [f"{leave.leave_type} coverage"]
    if leave.reason:
        parts.append(leave.reason.strip())
    if leave.coverage_reason:
        parts.append(leave.coverage_reason.strip())
    return " — ".join(part for part in parts if part)


def _create_or_update_coverage_record(
    db: Session,
    *,
    task: FarmActivity,
    leave: StaffLeave,
    original_employee_id: int,
    covering_employee_id: int | None,
    actor_user_id: int | None,
    status: str,
) -> TaskLeaveCoverage:
    coverage = _existing_coverage(db, task.id, leave.id)
    if coverage is None:
        coverage = TaskLeaveCoverage(
            activity_id=task.id,
            leave_id=leave.id,
            original_employee_id=original_employee_id,
            covering_employee_id=covering_employee_id,
            coverage_start_date=leave.start_date,
            coverage_end_date=leave.end_date,
            status=status,
            reason=_coverage_reason(leave),
            approved_by_user_id=actor_user_id,
            approved_at=leave.decided_at or farm_now_naive(),
            source_module=task.source_module,
            source_type=task.source_type,
            source_record_id=task.source_record_id,
            source_detail_id=task.source_detail_id,
            recurring_series_key=task.recurring_series_key,
        )
        db.add(coverage)
        db.flush()
    else:
        coverage.covering_employee_id = covering_employee_id
        coverage.status = status
        coverage.coverage_start_date = leave.start_date
        coverage.coverage_end_date = leave.end_date
        coverage.reason = _coverage_reason(leave)
        coverage.source_module = task.source_module
        coverage.source_type = task.source_type
        coverage.source_record_id = task.source_record_id
        coverage.source_detail_id = task.source_detail_id
        coverage.recurring_series_key = task.recurring_series_key
    return coverage


def _assign_coverage_occurrence(
    db: Session,
    *,
    task: FarmActivity,
    leave: StaffLeave,
    original_employee_id: int,
    covering_employee_id: int | None,
    actor_user_id: int | None,
    actor_name: str,
    automatic: bool,
) -> TaskLeaveCoverage:
    old_employee_id = task.assigned_employee_id
    old_source = task.assignment_source

    covering = db.get(Employee, covering_employee_id) if covering_employee_id else None
    if covering is not None:
        blockers, _warnings = coverage_candidate_check(
            db, covering, task, leave_employee_id=leave.employee_id
        )
        if blockers:
            raise ValueError("; ".join(blockers))
        task.assigned_employee_id = covering.id
        task.assigned_to = covering.full_name
        task.assigned_by = actor_name or "System"
        task.assignment_source = COVERAGE_ASSIGNMENT_SOURCE
        task.needs_reassignment = False
        coverage_status = "Active"
    else:
        task.assigned_employee_id = None
        task.assigned_to = "Unassigned"
        task.assigned_by = actor_name or "System"
        task.assignment_source = COVERAGE_ASSIGNMENT_SOURCE
        task.needs_reassignment = True
        coverage_status = "Needs Reassignment"
        _upsert_manager_alert(
            db,
            source_type="leave_coverage_reassignment",
            source_id=task.id,
            alert_type="Leave Coverage Needs Reassignment",
            subject=f"{task.name} needs leave coverage",
            description=(
                f"{task.activity_code} on {task.activity_date.isoformat()} was unassigned because "
                f"{_employee_label(db.get(Employee, original_employee_id))} is on approved leave."
            ),
        )

    coverage = _create_or_update_coverage_record(
        db,
        task=task,
        leave=leave,
        original_employee_id=original_employee_id,
        covering_employee_id=covering_employee_id,
        actor_user_id=actor_user_id,
        status=coverage_status,
    )
    record_assignment_change(
        db,
        task,
        old_employee_id=old_employee_id,
        new_employee_id=task.assigned_employee_id,
        assignment_source=COVERAGE_ASSIGNMENT_SOURCE,
        actor_user_id=actor_user_id,
        actor_name=actor_name or "System",
        reason=coverage.reason,
        leave_id=leave.id,
        old_assignment_source=old_source,
        new_assignment_source=COVERAGE_ASSIGNMENT_SOURCE,
        is_automatic=automatic,
        event_key=f"leave-coverage:{leave.id}:{task.id}",
    )
    return coverage


def approve_leave_with_coverage(
    db: Session,
    *,
    leave: StaffLeave,
    actor_user_id: int | None,
    actor_name: str,
    default_covering_employee_id: int | None,
    task_covering_employee_ids: dict[int, int | None] | None = None,
) -> dict[str, int]:
    """Apply an approved leave plan to current task occurrences.

    Only Pending, unstarted occurrences are transferred/unassigned. In Progress
    work remains assigned and is flagged for urgent review. Historical/reviewed
    statuses are preserved without assignment changes.
    """
    task_covering_employee_ids = task_covering_employee_ids or {}
    leave.default_covering_employee_id = default_covering_employee_id

    tasks = affected_tasks_for_leave(db, leave)
    summary = {
        "affected": len(tasks),
        "covered": 0,
        "needs_reassignment": 0,
        "urgent_review": 0,
        "protected": 0,
    }
    for task in tasks:
        if task.status in PROTECTED_LEAVE_TASK_STATUSES or task.is_archived:
            summary["protected"] += 1
            continue
        if task.status == "In Progress":
            task.needs_reassignment = True
            _create_or_update_coverage_record(
                db,
                task=task,
                leave=leave,
                original_employee_id=leave.employee_id,
                covering_employee_id=None,
                actor_user_id=actor_user_id,
                status="Urgent Review",
            )
            _upsert_manager_alert(
                db,
                source_type="leave_coverage_in_progress",
                source_id=task.id,
                alert_type="In Progress Leave Conflict",
                subject=f"Review in-progress task {task.activity_code}",
                description=(
                    f"{task.name} is already In Progress while {_employee_label(db.get(Employee, leave.employee_id))} "
                    "has approved leave. It was not transferred automatically."
                ),
            )
            summary["urgent_review"] += 1
            continue
        if task.status != "Pending" or _task_has_submission(db, task.id):
            summary["protected"] += 1
            continue

        cover_id = (
            task_covering_employee_ids[task.id]
            if task.id in task_covering_employee_ids
            else default_covering_employee_id
        )
        try:
            coverage = _assign_coverage_occurrence(
                db,
                task=task,
                leave=leave,
                original_employee_id=leave.employee_id,
                covering_employee_id=cover_id,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                automatic=False,
            )
        except ValueError as exc:
            raise ValueError(f"Task {task.activity_code}: {exc}") from exc
        if coverage.covering_employee_id:
            summary["covered"] += 1
        else:
            summary["needs_reassignment"] += 1
    return summary


def _matching_cover_from_prior_occurrence(
    db: Session,
    *,
    leave: StaffLeave,
    task: FarmActivity,
) -> int | None:
    stmt = select(TaskLeaveCoverage).where(
        TaskLeaveCoverage.leave_id == leave.id,
        TaskLeaveCoverage.covering_employee_id.is_not(None),
    )
    match = None
    if task.recurring_series_key:
        match = db.scalar(
            stmt.where(TaskLeaveCoverage.recurring_series_key == task.recurring_series_key)
            .order_by(TaskLeaveCoverage.id.desc())
        )
    if match is None and task.source_module and task.source_type and task.source_record_id:
        source_stmt = stmt.where(
            TaskLeaveCoverage.source_module == task.source_module,
            TaskLeaveCoverage.source_type == task.source_type,
            TaskLeaveCoverage.source_record_id == task.source_record_id,
        )
        if task.source_detail_id is None:
            source_stmt = source_stmt.where(TaskLeaveCoverage.source_detail_id.is_(None))
        else:
            source_stmt = source_stmt.where(TaskLeaveCoverage.source_detail_id == task.source_detail_id)
        match = db.scalar(source_stmt.order_by(TaskLeaveCoverage.id.desc()))
    return match.covering_employee_id if match is not None else None


def apply_leave_coverage_to_task(
    db: Session,
    task: FarmActivity,
    *,
    default_employee_id: int | None = None,
) -> TaskLeaveCoverage | None:
    """Apply structured coverage to a newly generated occurrence, idempotently."""
    if task.is_archived or task.status != "Pending":
        return None
    if task.assignment_source in {"manager_override", "reassignment"}:
        return None
    if _task_has_submission(db, task.id):
        return None

    original_employee_id = default_employee_id or _source_default_employee_id(db, task) or task.assigned_employee_id
    if not original_employee_id:
        return None
    leave = db.scalar(
        select(StaffLeave)
        .where(
            StaffLeave.employee_id == original_employee_id,
            StaffLeave.status == "Approved",
            StaffLeave.start_date <= task.activity_date,
            StaffLeave.end_date >= task.activity_date,
        )
        .order_by(StaffLeave.start_date.desc(), StaffLeave.id.desc())
    )
    if leave is None:
        return None
    existing = _existing_coverage(db, task.id, leave.id)
    if existing is not None:
        return existing

    cover_id = leave.default_covering_employee_id
    if cover_id is None:
        cover_id = _matching_cover_from_prior_occurrence(db, leave=leave, task=task)

    if cover_id is not None:
        employee = db.get(Employee, cover_id)
        if employee is None:
            cover_id = None
        else:
            blockers, _warnings = coverage_candidate_check(
                db, employee, task, leave_employee_id=leave.employee_id
            )
            if blockers:
                cover_id = None

    return _assign_coverage_occurrence(
        db,
        task=task,
        leave=leave,
        original_employee_id=original_employee_id,
        covering_employee_id=cover_id,
        actor_user_id=leave.decided_by_user_id,
        actor_name="System",
        automatic=True,
    )


def mark_leave_coverage_manager_override(
    db: Session,
    *,
    task: FarmActivity,
    actor_user_id: int | None,
) -> None:
    coverage = db.scalar(
        select(TaskLeaveCoverage)
        .where(
            TaskLeaveCoverage.activity_id == task.id,
            TaskLeaveCoverage.status.in_(list(COVERAGE_ACTIVE_STATUSES)),
        )
        .order_by(TaskLeaveCoverage.id.desc())
    )
    if coverage is not None:
        coverage.status = "Manager Override"
        coverage.returned_by_user_id = actor_user_id
        coverage.returned_at = farm_now_naive()
        coverage.return_reason = "Later manager assignment override preserved."


def _has_later_manager_override(db: Session, coverage: TaskLeaveCoverage) -> bool:
    return db.scalar(
        select(TaskAssignmentHistory.id).where(
            TaskAssignmentHistory.activity_id == coverage.activity_id,
            TaskAssignmentHistory.changed_at > coverage.approved_at,
            or_(
                TaskAssignmentHistory.assignment_source.in_(["manager_override", "reassignment"]),
                TaskAssignmentHistory.new_assignment_source.in_(["manager_override", "reassignment"]),
            ),
        ).limit(1)
    ) is not None


def reconcile_expired_leave_coverage(
    db: Session,
    *,
    leave_id: int | None = None,
    actor_user_id: int | None = None,
    actor_name: str = "System",
    as_of_date: date | None = None,
) -> dict[str, int]:
    """Return only future Pending/unstarted coverage work when coverage ended.

    A normal ended leave preserves overdue/unfinished tasks whose activity date
    was inside the leave period. Early cancellation makes dates after the
    cancellation date eligible for restoration.
    """
    today = as_of_date or farm_today()
    stmt = select(TaskLeaveCoverage).where(
        TaskLeaveCoverage.status.in_(["Active", "Needs Reassignment"])
    )
    if leave_id is not None:
        stmt = stmt.where(TaskLeaveCoverage.leave_id == leave_id)

    summary = {"checked": 0, "returned": 0, "preserved": 0}
    for coverage in db.scalars(stmt.order_by(TaskLeaveCoverage.id)).all():
        summary["checked"] += 1
        leave = db.get(StaffLeave, coverage.leave_id)
        task = db.get(FarmActivity, coverage.activity_id)
        if leave is None or task is None:
            summary["preserved"] += 1
            continue

        early_cancel_date = leave.cancelled_at.date() if leave.status == "Cancelled" and leave.cancelled_at else None
        effective_end = min(leave.end_date, early_cancel_date) if early_cancel_date else leave.end_date
        leave_has_ended = leave.status == "Cancelled" or today > leave.end_date
        if not leave_has_ended or task.activity_date <= effective_end:
            summary["preserved"] += 1
            continue

        if (
            task.is_archived
            or task.status != "Pending"
            or task.assignment_source != COVERAGE_ASSIGNMENT_SOURCE
            or _task_has_submission(db, task.id)
            or _has_later_manager_override(db, coverage)
        ):
            summary["preserved"] += 1
            continue

        original = db.get(Employee, coverage.original_employee_id)
        if original is None or original.is_archived or original.employment_status != "Active":
            summary["preserved"] += 1
            continue

        source_default = _source_default_employee_id(db, task)
        if source_default is not None and source_default != coverage.original_employee_id:
            summary["preserved"] += 1
            continue

        if employee_unavailability_reason(db, original.id, task.activity_date):
            summary["preserved"] += 1
            continue

        old_employee_id = task.assigned_employee_id
        old_source = task.assignment_source
        new_source = "automatic_default" if task.is_automatic else "manual"
        task.assigned_employee_id = original.id
        task.assigned_to = original.full_name
        task.assigned_by = actor_name or "System"
        task.assignment_source = new_source
        task.needs_reassignment = False
        recalculate_task_reassignment(db, task)

        reason = "Automatic Return After Leave — temporary leave coverage ended"
        record_assignment_change(
            db,
            task,
            old_employee_id=old_employee_id,
            new_employee_id=original.id,
            assignment_source=new_source,
            actor_user_id=actor_user_id,
            actor_name=actor_name or "System",
            reason=reason,
            leave_id=leave.id,
            old_assignment_source=old_source,
            new_assignment_source=new_source,
            is_automatic=True,
            event_key=f"leave-return:{coverage.id}",
        )
        coverage.status = "Returned"
        coverage.returned_at = farm_now_naive()
        coverage.returned_by_user_id = actor_user_id
        coverage.return_reason = reason
        _upsert_manager_alert(
            db,
            source_type="leave_coverage_return",
            source_id=coverage.id,
            alert_type="Leave Coverage Returned",
            subject=f"{task.activity_code} returned to {original.full_name}",
            description=reason,
            priority="Medium",
        )
        summary["returned"] += 1
    return summary


def coverage_for_task(db: Session, task_id: int) -> TaskLeaveCoverage | None:
    return db.scalar(
        select(TaskLeaveCoverage)
        .where(TaskLeaveCoverage.activity_id == task_id)
        .order_by(TaskLeaveCoverage.id.desc())
    )


def coverage_display(db: Session, task: FarmActivity, *, today: date | None = None) -> dict | None:
    coverage = coverage_for_task(db, task.id)
    if coverage is None:
        return None
    leave = db.get(StaffLeave, coverage.leave_id)
    original = db.get(Employee, coverage.original_employee_id)
    covering = db.get(Employee, coverage.covering_employee_id) if coverage.covering_employee_id else None
    today = today or farm_today()
    indicator = None
    if coverage.status in COVERAGE_ACTIVE_STATUSES:
        if today > coverage.coverage_end_date:
            indicator = "Coverage Ended"
        elif (coverage.coverage_end_date - today).days <= 1:
            indicator = "Coverage Ending"
    return {
        "coverage_id": coverage.id,
        "leave_id": coverage.leave_id,
        "status": coverage.status,
        "original_employee_id": coverage.original_employee_id,
        "original_employee_name": original.full_name if original else None,
        "covering_employee_id": coverage.covering_employee_id,
        "covering_employee_name": covering.full_name if covering else None,
        "coverage_start_date": coverage.coverage_start_date,
        "coverage_end_date": coverage.coverage_end_date,
        "coverage_reason": coverage.reason,
        "indicator": indicator,
        "leave_type": leave.leave_type if leave else None,
        "leave_status": leave.status if leave else None,
        "approved_at": coverage.approved_at,
        "returned_at": coverage.returned_at,
        "return_reason": coverage.return_reason,
    }
