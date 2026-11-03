"""One authoritative policy for declarations, attendance windows and held work.

All mutators flush only. The API/scheduler owns the surrounding transaction.
Weather may suggest a review; it never approves or ends a declaration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from weakref import WeakKeyDictionary

from fastapi import HTTPException
from sqlalchemy import false, inspect, or_, select, update

from app.core.farm_time import farm_now_naive, farm_timezone
from app.models import (
    AuditLog, Employee, FarmActivity, FarmEvent, FarmEventTask,
    FarmEventAcknowledgement, FarmEventAudit, FarmEventReport, TaskSubmission,
)
from app.services.db_concurrency import acquire_transaction_lock

OPEN_TASKS = {"Pending", "In Progress", "Returned"}
WORK_KINDS = {"Planned No-Work Day", "Emergency Suspension"}
_schema_cache = WeakKeyDictionary()


def schema_ready(db):
    engine = db.get_bind()
    if engine not in _schema_cache:
        # Inspect the session's connection: opening another SQLite connection
        # can roll back a shared in-memory transaction used by tests/recovery.
        ready = inspect(db.connection()).has_table("farm_events")
        if ready:
            _schema_cache[engine] = True
        return ready
    return True


def require_schema(db):
    if not schema_ready(db):
        raise HTTPException(503, "Farm events require the database migration. Run python -m alembic upgrade head from Jorros Backend.")


def json_value(raw, fallback=None):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return [] if fallback is None else fallback


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def iso(value):
    return value.replace(tzinfo=farm_timezone()).isoformat() if value else None


def lifecycle(event, now=None):
    now = now or farm_now_naive()
    if event.status in {"Draft", "Cancelled", "Ended"}:
        return event.status
    if now < event.starts_at:
        return "Scheduled"
    if event.kind == "Emergency Suspension":
        return "Active"  # Expected end is advisory; reopening is an explicit decision.
    return "Active" if now < event.ends_at else "Ended"


def effective_end(event):
    if event.ended_at:
        return min(event.ended_at, event.ends_at) if event.kind != "Emergency Suspension" else event.ended_at
    if event.kind == "Emergency Suspension" and event.status not in {"Draft", "Cancelled", "Ended"}:
        return datetime.max
    return event.ends_at


def declarations(db, *, include_drafts=False):
    if not schema_ready(db):
        return []
    stmt = select(FarmEvent).order_by(FarmEvent.starts_at.desc(), FarmEvent.id.desc())
    if not include_drafts:
        stmt = stmt.where(FarmEvent.approved_at.is_not(None))
    return list(db.scalars(stmt).all())


def affected_employee(event, employee):
    if employee is None:
        return event.scope_type == "All"
    values = json_value(event.scope_json)
    if event.scope_type == "Employees":
        return str(employee.id) in {str(x) for x in values}
    if event.scope_type == "Areas":
        return str(employee.assigned_area or "").strip().casefold() in {str(x).casefold() for x in values}
    return True


def affected_task(event, task, employees):
    if event.scope_type == "All":
        return True
    values = json_value(event.scope_json)
    if event.scope_type == "Areas":
        return str(task.location or "").strip().casefold() in {str(x).casefold() for x in values}
    current_employee = task.assigned_employee_id if task.assigned_employee_id is not None else task.default_employee_id
    return str(current_employee or "") in {str(x) for x in values}


def task_interval(task):
    start = datetime.combine(task.activity_date, task.start_time or time.min)
    end = datetime.combine(task.activity_date, task.end_time) if task.end_time else start + timedelta(minutes=1)
    return start, max(end, start + timedelta(minutes=1))


def overlaps(a, b, c, d):
    return a < d and c < b


def task_matches(event, task, employees, *, draft=False):
    if event.kind not in WORK_KINDS:
        return False
    start, end = task_interval(task)
    stop = datetime.max if draft and event.kind == "Emergency Suspension" else effective_end(event)
    affected = affected_task(event, task, employees)
    now = farm_now_naive()
    performing_now = task.activity_date <= now.date() and start <= now and event.starts_at <= now < stop
    return affected and (overlaps(start, end, event.starts_at, stop) or performing_now)


def is_essential(task):
    text = " ".join(str(x or "") for x in (task.category, task.source_type, task.name)).lower()
    return bool(task.time_sensitive or any(word in text for word in ("feeding", "feed ", "animal care", "livestock health", "vaccin")))


def validate_scope(db, values):
    if values.scope_type == "Employees":
        try:
            ids = {int(x) for x in values.scope_values}
        except ValueError as exc:
            raise HTTPException(422, "Employee scope must contain employee IDs.") from exc
        active = set(db.scalars(select(Employee.id).where(Employee.id.in_(ids), Employee.is_archived == False, Employee.employment_status == "Active")).all())
        if active != ids:
            raise HTTPException(422, "An affected employee is missing, inactive or archived.")


def fields_from(payload):
    return {
        name: getattr(payload, name) for name in (
            "title", "kind", "starts_at", "ends_at", "scope_type", "reason", "instructions", "source_name", "source_reference"
        )
    } | {"scope_json": encode(payload.scope_values)}


def default_checklist():
    return [
        {"id": "before-plan", "phase": "Before", "text": "Review the farm's approved preparation plan and affected work.", "completed": False},
        {"id": "during-notice", "phase": "During", "text": "Publish employee instructions and review essential-care coverage.", "completed": False},
        {"id": "after-inspect", "phase": "After", "text": "Review reported damage and inspect affected areas before reopening.", "completed": False},
        {"id": "after-tasks", "phase": "After", "text": "Review held tasks and record the reopening decision.", "completed": False},
    ]


def audit(db, event, user, action, reason, details=None):
    now = farm_now_naive()
    db.add(FarmEventAudit(event_id=event.id, action=action, reason=reason, actor_user_id=user.id,
                          actor_name=user.full_name, details_json=encode(details or {}), created_at=now))
    db.add(AuditLog(event_type="audit", action=f"Farm declaration: {action}", module="Staff Calendar",
                    record_name=event.title, entity_id=str(event.id), details=encode({"reason": reason, **(details or {})}),
                    actor_user_id=user.id, actor_name=user.full_name, created_at=now))


def create_draft(db, payload, user):
    validate_scope(db, payload)
    key = digest([user.id, payload.request_key])
    fingerprint = digest(payload.model_dump(exclude={"request_key"}))
    acquire_transaction_lock(db, f"farm-event-create:{key}")
    existing = db.scalar(select(FarmEvent).where(FarmEvent.command_key == key))
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(409, "This request key was already used for different event details.")
        return existing
    event = FarmEvent(**fields_from(payload), status="Draft", version=1, notice_version=1,
                      checklist_json=encode(default_checklist()), command_key=key, request_hash=fingerprint,
                      created_by_user_id=user.id, created_at=farm_now_naive(), updated_at=farm_now_naive())
    db.add(event)
    db.flush()
    audit(db, event, user, "Created draft", payload.reason)
    return event


def compare_and_update(db, event, expected_version, changes):
    db.info.pop("farm_event_context", None)
    if event.version != expected_version:
        raise HTTPException(409, "This declaration changed. Reload its latest version before saving.")
    acquire_transaction_lock(db, f"farm-event:{event.id}")
    result = db.execute(update(FarmEvent).where(FarmEvent.id == event.id, FarmEvent.version == expected_version)
                        .values(**changes, version=expected_version + 1, updated_at=farm_now_naive())
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "This declaration changed. Reload its latest version and review your changes.")
    db.refresh(event)


def edit_draft(db, event, payload, user):
    if event.status != "Draft":
        raise HTTPException(409, "Approved declarations are locked. End or cancel with a reason, then create a replacement draft.")
    validate_scope(db, payload)
    compare_and_update(db, event, payload.expected_version, fields_from(payload))
    audit(db, event, user, "Edited draft", payload.reason)
    return event


def preview(db, event):
    employees = list(db.scalars(select(Employee).where(Employee.is_archived == False, Employee.employment_status == "Active")).all())
    by_id = {x.id: x for x in employees}
    affected = [x for x in employees if affected_employee(event, x)]
    candidates = list(db.scalars(select(FarmActivity).where(
        FarmActivity.is_archived == False,
        or_(FarmActivity.activity_date >= event.starts_at.date(), FarmActivity.status.in_(OPEN_TASKS)),
        FarmActivity.status.notin_(["Cancelled", "Voided"]),
    )).all())
    matched = [x for x in candidates if task_matches(event, x, by_id, draft=event.status == "Draft")]
    actionable = [x for x in matched if x.status in OPEN_TASKS]
    conflicts = [x for x in declarations(db) if x.id != event.id and lifecycle(x) in {"Scheduled", "Active"}
                 and overlaps(event.starts_at, effective_end(event), x.starts_at, effective_end(x))
                 and any(affected_employee(x, employee) for employee in affected)]
    token = digest({"event": event.id, "version": event.version,
                    "employees": sorted(x.id for x in affected),
                    "tasks": sorted((x.id, x.status, x.activity_date.isoformat(), str(x.start_time), x.assigned_employee_id) for x in matched)})
    return {
        "preview_token": token, "employee_count": len(affected),
        "employees": [{"id": x.id, "name": x.full_name, "area": x.assigned_area} for x in affected],
        "task_count": len(actionable), "protected_task_count": len(matched) - len(actionable),
        "essential_task_count": sum(is_essential(x) for x in actionable),
        "tasks": [{"id": x.id, "name": x.name, "date": x.activity_date.isoformat(), "status": x.status,
                   "essential": is_essential(x), "employee_id": x.assigned_employee_id} for x in actionable[:50]],
        "overlaps": [{"id": x.id, "title": x.title} for x in conflicts],
        "emergency_requires_reopening": event.kind == "Emergency Suspension",
    }


def reconcile_event_holds(db, *, events=None, tasks=None):
    if not schema_ready(db):
        return 0
    events = events if events is not None else [x for x in declarations(db) if x.kind in WORK_KINDS]
    events = [x for x in events if x.approved_at and x.status != "Draft"]
    if not events:
        return 0
    acquire_transaction_lock(db, "farm-event-holds")
    db.flush()
    candidates = tasks if tasks is not None else list(db.scalars(select(FarmActivity).where(
        FarmActivity.status.in_(OPEN_TASKS), FarmActivity.is_archived == False,
    )).all())
    existing = {(x.event_id, x.activity_id) for x in db.scalars(select(FarmEventTask)).all()}
    count = 0
    for event in events:
        for task in candidates:
            key = (event.id, task.id)
            if key in existing or task.status not in OPEN_TASKS or task.is_archived:
                continue
            if not task_matches(event, task, {}):
                continue
            snapshot = {"date": task.activity_date.isoformat(), "start_time": str(task.start_time),
                        "end_time": str(task.end_time) if task.end_time else None,
                        "employee_id": task.assigned_employee_id, "status": task.status,
                        "assignment_source": task.assignment_source}
            db.add(FarmEventTask(event_id=event.id, activity_id=task.id, original_json=encode(snapshot),
                                  essential_review=is_essential(task), resolution="Held", version=1))
            existing.add(key)
            count += 1
    db.flush()
    if count:
        db.info.pop("farm_event_schedule_locks", None)
    return count


def approve(db, event, decision, user):
    acquire_transaction_lock(db, f"farm-event:{event.id}")
    if event.approved_at:
        if event.version == decision.expected_version + 1 and event.approved_by_user_id == user.id:
            return event
        raise HTTPException(409, "This declaration was already approved. Reload the latest version.")
    if event.status != "Draft":
        raise HTTPException(409, "Only drafts can be approved.")
    impact = preview(db, event)
    if decision.preview_token != impact["preview_token"]:
        raise HTTPException(409, "The impact preview changed. Preview the affected employees and tasks again before approval.")
    compare_and_update(db, event, decision.expected_version, {
        "status": "Scheduled" if farm_now_naive() < event.starts_at else "Active",
        "approved_by_user_id": user.id, "approved_at": farm_now_naive(),
    })
    reconcile_event_holds(db, events=[event])
    audit(db, event, user, "Approved", decision.reason, {
        "employees": impact["employee_count"], "tasks": impact["task_count"], "essential_review": impact["essential_task_count"],
    })
    return event


def finish(db, event, decision, user, *, cancel=False):
    target = "Cancelled" if cancel else "Ended"
    if event.status == target and event.version == decision.expected_version + 1 and event.end_reason == decision.reason:
        return event
    if event.status in {"Cancelled", "Ended"}:
        raise HTTPException(409, "This declaration has already ended or been cancelled.")
    if not cancel and not event.approved_at:
        raise HTTPException(409, "Only an approved declaration can be ended.")
    if event.approved_at:
        reconcile_event_holds(db, events=[event])
    compare_and_update(db, event, decision.expected_version, {
        "status": target, "ended_at": farm_now_naive(), "end_reason": decision.reason,
        "notice_version": event.notice_version + 1,
    })
    # Release prospective work that never overlapped the actual closure.
    # Previously affected unfinished work still needs an explicit task decision.
    released = 0
    for hold in db.scalars(select(FarmEventTask).where(FarmEventTask.event_id == event.id, FarmEventTask.resolution == "Held")).all():
        task = db.get(FarmActivity, hold.activity_id)
        never_effective = event.ended_at <= event.starts_at
        future_unstarted = task and task.status == "Pending" and task_interval(task)[0] >= event.ended_at
        if never_effective or future_unstarted:
            hold.resolution = "Released"
            hold.review_reason = "Declaration ended before this work was affected. " + decision.reason
            hold.reviewed_by_user_id = user.id
            hold.reviewed_at = farm_now_naive()
            hold.version += 1
            released += 1
    db.info.pop("farm_event_schedule_locks", None)
    audit(db, event, user, "Cancelled" if cancel else "Reopened / ended", decision.reason, {"unaffected_future_tasks_released": released})
    return event


def held_task_expression(db, activity_id, assigned_employee_id):
    """Correlated predicate for lightweight summaries, without loading task cards."""
    if not schema_ready(db):
        return false()
    return select(FarmEventTask.id).where(
        FarmEventTask.activity_id == activity_id,
        or_(FarmEventTask.resolution == "Held", (
            (FarmEventTask.resolution == "Essential Duty")
            & (assigned_employee_id.is_(None) | (FarmEventTask.authorized_employee_id != assigned_employee_id))
        )),
    ).exists()


def event_context(db):
    if "farm_event_context" in db.info:
        return db.info["farm_event_context"]
    events = declarations(db)
    essential = set()
    if events:
        essential = set(db.execute(select(FarmEventTask.event_id, FarmEventTask.authorized_employee_id, FarmActivity.activity_date)
                                   .join(FarmActivity, FarmActivity.id == FarmEventTask.activity_id)
                                   .where(FarmEventTask.resolution == "Essential Duty", FarmActivity.status.in_(OPEN_TASKS),
                                          FarmEventTask.authorized_employee_id.is_not(None),
                                          FarmActivity.assigned_employee_id == FarmEventTask.authorized_employee_id)).all())
    from app.models import AttendanceSettings
    attendance_settings = db.scalar(select(AttendanceSettings).order_by(AttendanceSettings.id)) if events else None
    result = {"events": events, "essential": essential, "attendance_settings": attendance_settings}
    db.info["farm_event_context"] = result
    return result


def employee_windows(db, employee, work_date, *, context=None, include_essential=False):
    context = context if context is not None else event_context(db)
    day_start = datetime.combine(work_date, time.min)
    day_end = day_start + timedelta(days=1)
    windows = []
    for event in context["events"]:
        if event.kind not in WORK_KINDS or event.status == "Draft" or not affected_employee(event, employee):
            continue
        end = effective_end(event)
        if event.status == "Cancelled" and event.ended_at and event.ended_at <= event.starts_at:
            continue
        if not overlaps(day_start, day_end, event.starts_at, end):
            continue
        essential = (event.id, employee.id if employee else None, work_date) in context["essential"]
        if essential and not include_essential:
            continue
        windows.append({"event_id": event.id, "title": event.title, "kind": event.kind, "reason": event.reason,
                        "starts_at": max(day_start, event.starts_at), "ends_at": min(day_end, end),
                        "essential_authorized": essential, "status": lifecycle(event)})
    return windows


def merged_windows(windows, start, end):
    values = sorted((max(start, x["starts_at"]), min(end, x["ends_at"])) for x in windows
                    if overlaps(start, end, x["starts_at"], x["ends_at"]))
    merged = []
    for a, b in values:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def exempt_minutes(windows, start, end):
    if not start or not end or end <= start:
        return 0
    return sum((b - a).total_seconds() / 60 for a, b in merged_windows(windows, start, end))


def attendance_start(work_date, start_time, windows):
    start = datetime.combine(work_date, start_time or time.min)
    for a, b in merged_windows(windows, start, datetime.combine(work_date + timedelta(days=1), time.min)):
        if a <= start < b:
            start = b
    return start


def decorate_availability(db, result, employee, *, context=None, now=None):
    now = now or farm_now_naive()
    windows = employee_windows(db, employee, result.work_date, context=context)
    if not windows:
        return result
    start = datetime.combine(result.work_date, result.start_time or time.min)
    end = datetime.combine(result.work_date, result.end_time) if result.end_time else datetime.combine(result.work_date + timedelta(days=1), time.min)
    full = exempt_minutes(windows, start, end) >= (end - start).total_seconds() / 60
    current = any(x["starts_at"] <= now < x["ends_at"] for x in windows)
    label = "Work Suspended" if any(x["kind"] == "Emergency Suspension" for x in windows) else "Authorized Day Off"
    serialized = [{**x, "starts_at": iso(x["starts_at"]), "ends_at": iso(x["ends_at"])} for x in windows]
    changes = {"suspensions": serialized, "attendance_suspended_now": current, "suspension_full_shift": full}
    # Approved leave, archived/inactive employees and normal rest days keep their existing provenance.
    if full and result.leave_id is None and result.status not in {"Rest Day", "Special Day Off", "Schedule Needs Setup"}:
        changes.update(available=False, status=label, reason="; ".join(x["title"] for x in windows),
                       is_working_day=False, attendance_status=None)
    elif result.status == "Possible Absence":
        due = attendance_start(result.work_date, result.start_time, windows)
        settings = context.get("attendance_settings") if context is not None else event_context(db).get("attendance_settings")
        delay = (settings.check_in_grace_minutes + settings.attendance_reminder_minutes) if settings else 20
        if current or now < due + timedelta(minutes=delay):
            changes.update(status="Working Day", reason="Partial-day suspension; attendance is evaluated outside the excused hours.")
    return replace(result, **changes)


def hold_context(db, tasks):
    if not schema_ready(db) or not tasks:
        return {"rows": {}, "events": {}, "submitted": set()}
    ids = sorted({x.id for x in tasks})
    rows = []
    for offset in range(0, len(ids), 500):
        rows.extend(db.scalars(select(FarmEventTask).where(FarmEventTask.activity_id.in_(ids[offset:offset + 500]))).all())
    grouped = {}
    for row in rows:
        grouped.setdefault(row.activity_id, []).append(row)
    return {"rows": grouped, "events": {x.id: x for x in declarations(db)}, "submitted": set()}


def task_hold_info(db, task, *, context=None):
    if task.status not in OPEN_TASKS or task.is_archived:
        return {"work_suspended": False, "suspension_holds": []}
    context = context if context is not None else hold_context(db, [task])
    rows = context["rows"].get(task.id, [])
    holds = []
    for row in rows:
        event = context["events"].get(row.event_id)
        if not event or (row.resolution != "Held" and not (
            row.resolution == "Essential Duty" and row.authorized_employee_id != task.assigned_employee_id
        )):
            continue
        holds.append({"id": row.id, "event_id": event.id, "title": event.title, "reason": event.reason,
                      "state": "Held" if lifecycle(event) in {"Scheduled", "Active"} else "Review Required",
                      "essential_review": row.essential_review})
    # Also protect a just-created occurrence before the next scheduler reconciliation.
    recorded = {x.event_id for x in rows}
    for event in context["events"].values():
        if event.id not in recorded and lifecycle(event) in {"Scheduled", "Active"} and task_matches(event, task, {}):
            holds.append({"id": None, "event_id": event.id, "title": event.title, "reason": event.reason,
                          "state": "Held", "essential_review": is_essential(task)})
    return {"work_suspended": bool(holds), "suspension_holds": holds}


def assert_task_available(db, task):
    info = task_hold_info(db, task)
    if info["work_suspended"]:
        raise HTTPException(409, "This work is held by a farm declaration. Owner/Admin must review its suspension or authorize essential duty before work can be recorded.")


def resolve_task_hold(db, event, hold, task, decision, user):
    acquire_transaction_lock(db, f"workforce-task-lifecycle:{task.id}")
    acquire_transaction_lock(db, f"farm-event-task:{hold.id}")
    if hold.resolution not in {"Held", "Essential Duty"} or hold.version != decision.expected_version:
        raise HTTPException(409, "This held task changed or was already reviewed. Reload the latest record.")
    if task.status not in OPEN_TASKS:
        raise HTTPException(409, "Performed or submitted work is protected and cannot be changed by suspension review.")
    active = lifecycle(event) in {"Scheduled", "Active"}
    action = decision.action
    if action in {"Reschedule", "Reassign", "Cancel"} and db.scalar(select(TaskSubmission.id).where(TaskSubmission.activity_id == task.id)):
        raise HTTPException(409, "This task has performed-work history. Its assignment, date and status cannot be changed here.")
    if action == "Release" and active:
        raise HTTPException(409, "End the declaration before releasing routine held work.")
    if action in {"Reschedule", "Reassign", "Cancel"} and task.status != "Pending":
        raise HTTPException(409, "Only unstarted pending tasks may be rescheduled, reassigned or cancelled here.")
    if action == "Reschedule":
        if task.time_sensitive or hold.essential_review:
            raise HTTPException(409, "Time-sensitive or essential care cannot be moved automatically. Review a same-day essential-duty or other explicit care decision.")
        if not decision.new_date or not decision.start_time or decision.new_date < farm_now_naive().date():
            raise HTTPException(422, "Select today or a future date and a start time.")
        if decision.end_time and decision.end_time <= decision.start_time:
            raise HTTPException(422, "End time must be after start time.")
        task.activity_date = decision.new_date
        task.start_time = decision.start_time
        task.end_time = decision.end_time
    if action in {"Reassign", "Essential Duty"}:
        employee = db.get(Employee, decision.employee_id) if decision.employee_id else None
        if not employee or employee.is_archived or employee.employment_status != "Active":
            raise HTTPException(422, "Select an active employee for this work.")
        from app.services.work_schedule_service import employee_is_qualified_for_task, resolve_employee_availability
        if not employee_is_qualified_for_task(employee, task):
            raise HTTPException(409, "The selected employee does not meet this task's existing qualification rules.")
        availability = resolve_employee_availability(db, employee.id, task.activity_date)
        if availability.leave_id or availability.status in {"Rest Day", "Special Day Off", "Unavailable"}:
            raise HTTPException(409, "The selected employee has a leave, rest-day or confirmed attendance conflict.")
        task.assigned_employee_id = employee.id
        task.assigned_to = employee.full_name
        task.needs_reassignment = False
        if action == "Essential Duty":
            hold.authorized_employee_id = employee.id
    if action == "Cancel":
        task.status = "Cancelled"
    # Re-evaluate all overlapping declarations after a proposed move/reassignment.
    if action in {"Reschedule", "Reassign", "Release"}:
        other_info = task_hold_info(db, task)
        other_events = [x for x in declarations(db) if lifecycle(x) in {"Scheduled", "Active"} and task_matches(x, task, {})]
        if other_events:
            raise HTTPException(409, "The proposed work is still covered by an active declaration. Review the overlapping declarations first.")
    if action in {"Reschedule", "Reassign", "Essential Duty"}:
        from app.services.task_assignment import record_assignment_change
        snapshot = json_value(hold.original_json, {})
        record_assignment_change(db, task, old_employee_id=snapshot.get("employee_id"),
                                 new_employee_id=task.assigned_employee_id, assignment_source="manager_override",
                                 actor_user_id=user.id, actor_name=user.full_name,
                                 reason=f"Farm event #{event.id}: {action}. {decision.reason}",
                                 old_assignment_source=task.assignment_source)
        task.assignment_source = "manager_override"
    result = db.execute(update(FarmEventTask).where(FarmEventTask.id == hold.id, FarmEventTask.version == decision.expected_version,
                                                  FarmEventTask.resolution.in_(["Held", "Essential Duty"]))
                        .values(resolution=action, version=decision.expected_version + 1,
                                review_reason=decision.reason, reviewed_by_user_id=user.id,
                                reviewed_at=farm_now_naive(), authorized_employee_id=hold.authorized_employee_id)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "This held task was changed by another administrator.")
    db.refresh(hold)
    db.info.pop("farm_event_context", None)
    db.info.pop("farm_event_schedule_locks", None)
    audit(db, event, user, f"Task {action}", decision.reason, {"task_id": task.id, "hold_id": hold.id,
                                                            "original": json_value(hold.original_json, {}),
                                                            "current_date": str(task.activity_date)})
    return hold


def task_schedule_locked(db, task_id):
    if not schema_ready(db):
        return False
    if "farm_event_schedule_locks" not in db.info:
        db.info["farm_event_schedule_locks"] = set(db.scalars(select(FarmEventTask.activity_id).where(
            FarmEventTask.resolution.in_(["Held", "Reschedule", "Reassign", "Essential Duty"])
        )).all())
    return task_id in db.info["farm_event_schedule_locks"]
