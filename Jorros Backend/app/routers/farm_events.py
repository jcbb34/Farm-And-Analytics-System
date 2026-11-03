from datetime import date, datetime, time, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import has_permission
from app.core.farm_time import farm_now_naive
from app.models import (Employee, FarmActivity, FarmEvent, FarmEventTask,
                        FarmEventAcknowledgement, FarmEventAudit, FarmEventReport, User)
from app.routers.auth import get_current_user
from app.schemas.farm_event import (FarmEventCreate, FarmEventUpdate, EventDecision, ChecklistDecision,
                                    EventAcknowledgement, EventReportInput, EventTaskDecision)
from app.services import farm_event_service as service
from app.services.db_concurrency import acquire_transaction_lock
from app.services.void_authorization import owner_or_admin

router = APIRouter(prefix="/api/v1/farm-events", tags=["Farm events and suspensions"])


def can_view_all(user):
    return any(has_permission(user, p) for p in ("workforce:manage", "workforce:attendance"))


def require_editor(user):
    if not has_permission(user, "workforce:manage"):
        raise HTTPException(403, "Workforce management permission is required to prepare a declaration.")


def require_approver(user):
    if not owner_or_admin(user):
        raise HTTPException(403, "Only an active Owner/Admin can approve, reopen or review suspended work.")


def own_employee(db, user):
    return db.scalar(select(Employee).where(Employee.login_user_id == user.id, Employee.is_archived == False))


def record_or_404(db, event_id, user):
    service.require_schema(db)
    event = db.get(FarmEvent, event_id)
    if event is None:
        raise HTTPException(404, "Farm declaration not found.")
    if not can_view_all(user):
        employee = own_employee(db, user)
        if not has_permission(user, "workforce:submit") or not employee or not event.approved_at or not service.affected_employee(event, employee):
            raise HTTPException(404, "Farm declaration not found.")
    return event


def serialize(db, event, user, *, details=False, employee=None):
    manager = can_view_all(user)
    employee = employee if employee is not None else own_employee(db, user)
    acknowledgements = list(db.scalars(select(FarmEventAcknowledgement).where(FarmEventAcknowledgement.event_id == event.id)).all())
    own_ack = next((x for x in acknowledgements if employee and x.employee_id == employee.id and x.notice_version == event.notice_version), None)
    result = {
        "id": event.id, "title": event.title, "kind": event.kind, "status": service.lifecycle(event),
        "starts_at": service.iso(event.starts_at), "ends_at": service.iso(event.ends_at),
        "scope_type": event.scope_type, "scope_values": service.json_value(event.scope_json) if manager else [],
        "reason": event.reason, "instructions": event.instructions or "", "source_name": event.source_name or "",
        "source_reference": event.source_reference or "", "version": event.version, "notice_version": event.notice_version,
        "approved_at": service.iso(event.approved_at), "ended_at": service.iso(event.ended_at), "end_reason": event.end_reason,
        "requires_reopening": event.kind == "Emergency Suspension" and event.status not in {"Draft", "Cancelled", "Ended"},
        "acknowledged": bool(own_ack), "acknowledged_at": service.iso(own_ack.acknowledged_at) if own_ack else None,
        "can_acknowledge": bool(employee and event.approved_at and service.affected_employee(event, employee)),
        "can_edit": has_permission(user, "workforce:manage") and event.status == "Draft",
        "can_approve": owner_or_admin(user), "can_manage": has_permission(user, "workforce:manage"),
        "checklist": service.json_value(event.checklist_json) if manager else [],
    }
    if details:
        reports = list(db.scalars(select(FarmEventReport).where(FarmEventReport.event_id == event.id).order_by(FarmEventReport.id.desc())).all())
        result["reports"] = [{"id": x.id, "area": x.area, "description": x.description,
                              "created_at": service.iso(x.created_at)} for x in reports if manager or (employee and x.employee_id == employee.id)]
        if manager:
            result["audit"] = [{"id": x.id, "action": x.action, "reason": x.reason, "actor_name": x.actor_name,
                                "created_at": service.iso(x.created_at), "details": service.json_value(x.details_json, {})}
                               for x in db.scalars(select(FarmEventAudit).where(FarmEventAudit.event_id == event.id)
                                                   .order_by(FarmEventAudit.id.desc()).limit(100)).all()]
            names = {x.id: x.full_name for x in db.scalars(select(Employee)).all()}
            result["acknowledgements"] = [{"employee_name": names.get(x.employee_id, "Employee"),
                                           "notice_version": x.notice_version, "acknowledged_at": service.iso(x.acknowledged_at)}
                                          for x in acknowledgements]
            result["impact"] = service.preview(db, event)
    return result


def calendar_events(db, date_from, date_to, user, *, employee_id=None):
    if not service.schema_ready(db):
        return []
    if not can_view_all(user) and not has_permission(user, "workforce:submit"):
        raise HTTPException(403, "Workforce access is required.")
    employee = db.get(Employee, employee_id) if employee_id and can_view_all(user) else own_employee(db, user)
    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to + timedelta(days=1), time.min)
    values = []
    for event in service.declarations(db, include_drafts=can_view_all(user)):
        if not service.overlaps(start, end, event.starts_at, service.effective_end(event)):
            continue
        if employee is not None and not service.affected_employee(event, employee):
            continue
        if not can_view_all(user) and (employee is None or not event.approved_at):
            continue
        values.append(serialize(db, event, user, employee=employee))
    return values


def mutate(db, callback):
    try:
        result = callback()
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "A concurrent request changed this declaration. Reload and retry; no duplicate was saved.") from exc
    except Exception:
        db.rollback()
        raise


@router.get("")
def list_events(date_from: date, date_to: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.require_schema(db)
    if date_to < date_from or (date_to - date_from).days > 366:
        raise HTTPException(422, "Choose a date range of at most 367 days.")
    return calendar_events(db, date_from, date_to, user)


@router.post("", status_code=201)
def create_event(payload: FarmEventCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(user)
    service.require_schema(db)
    return mutate(db, lambda: serialize(db, service.create_draft(db, payload, user), user, details=True))


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return serialize(db, record_or_404(db, event_id, user), user, details=True)


@router.put("/{event_id}")
def update_event(event_id: int, payload: FarmEventUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(user)
    event = record_or_404(db, event_id, user)
    return mutate(db, lambda: serialize(db, service.edit_draft(db, event, payload, user), user, details=True))


@router.get("/{event_id}/preview")
def preview_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(user)
    return service.preview(db, record_or_404(db, event_id, user))


@router.post("/{event_id}/approve")
def approve_event(event_id: int, payload: EventDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_approver(user)
    event = record_or_404(db, event_id, user)
    return mutate(db, lambda: serialize(db, service.approve(db, event, payload, user), user, details=True))


@router.post("/{event_id}/end")
def end_event(event_id: int, payload: EventDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_approver(user)
    event = record_or_404(db, event_id, user)
    return mutate(db, lambda: serialize(db, service.finish(db, event, payload, user), user, details=True))


@router.post("/{event_id}/cancel")
def cancel_event(event_id: int, payload: EventDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = record_or_404(db, event_id, user)
    require_editor(user) if event.status == "Draft" else require_approver(user)
    return mutate(db, lambda: serialize(db, service.finish(db, event, payload, user, cancel=True), user, details=True))


@router.post("/{event_id}/checklist")
def update_checklist(event_id: int, payload: ChecklistDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(user)
    event = record_or_404(db, event_id, user)
    def operation():
        items = service.json_value(event.checklist_json)
        item = next((x for x in items if x["id"] == payload.item_id), None)
        if item is None:
            raise HTTPException(404, "Checklist item not found.")
        item.update(completed=payload.completed, actor_name=user.full_name, updated_at=service.iso(farm_now_naive()))
        service.compare_and_update(db, event, payload.expected_version, {"checklist_json": service.encode(items)})
        service.audit(db, event, user, "Checklist updated", item["text"], {"completed": payload.completed})
        return serialize(db, event, user, details=True)
    return mutate(db, operation)


@router.post("/{event_id}/acknowledge")
def acknowledge_event(event_id: int, payload: EventAcknowledgement, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = record_or_404(db, event_id, user)
    employee = own_employee(db, user)
    if not employee or not event.approved_at or not service.affected_employee(event, employee):
        raise HTTPException(403, "Only an affected employee can acknowledge this notice for their own account.")
    def operation():
        acquire_transaction_lock(db, f"farm-event-ack:{event.id}:{employee.id}")
        if payload.notice_version != event.notice_version:
            raise HTTPException(409, "The notice changed. Read its latest instructions before acknowledging.")
        existing = db.scalar(select(FarmEventAcknowledgement).where(
            FarmEventAcknowledgement.event_id == event.id, FarmEventAcknowledgement.employee_id == employee.id,
            FarmEventAcknowledgement.notice_version == payload.notice_version))
        if not existing:
            db.add(FarmEventAcknowledgement(event_id=event.id, employee_id=employee.id, user_id=user.id,
                                            notice_version=payload.notice_version, acknowledged_at=farm_now_naive()))
            db.flush()
        return serialize(db, event, user)
    return mutate(db, operation)


@router.post("/{event_id}/reports", status_code=201)
def report_event(event_id: int, payload: EventReportInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = record_or_404(db, event_id, user)
    employee = own_employee(db, user)
    def operation():
        if not payload.area.strip() or len(payload.description.strip()) < 3:
            raise HTTPException(422, "Enter an area and a description.")
        db.add(FarmEventReport(event_id=event.id, employee_id=employee.id if employee else None,
                               actor_user_id=user.id, area=payload.area.strip(), description=payload.description.strip(),
                               created_at=farm_now_naive()))
        service.audit(db, event, user, "Observation reported", payload.description.strip(), {"area": payload.area.strip()})
        db.flush()
        return serialize(db, event, user, details=True)
    return mutate(db, operation)


@router.get("/{event_id}/tasks")
def event_tasks(event_id: int, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not can_view_all(user):
        raise HTTPException(403, "Workforce-wide access is required to review affected work.")
    event = record_or_404(db, event_id, user)
    stmt = select(FarmEventTask, FarmActivity).join(FarmActivity, FarmActivity.id == FarmEventTask.activity_id).where(FarmEventTask.event_id == event.id)
    total = db.scalar(select(func.count()).select_from(FarmEventTask).where(FarmEventTask.event_id == event.id)) or 0
    rows = db.execute(stmt.order_by(FarmEventTask.id).offset(offset).limit(limit)).all()
    return {"items": [{"id": hold.id, "activity_id": task.id, "name": task.name, "code": task.activity_code,
                        "date": task.activity_date.isoformat(), "start_time": str(task.start_time), "status": task.status,
                        "assigned_to": task.assigned_to, "resolution": hold.resolution, "version": hold.version,
                        "essential_review": hold.essential_review, "time_sensitive": task.time_sensitive,
                        "original": service.json_value(hold.original_json, {}), "review_reason": hold.review_reason,
                        "can_review": owner_or_admin(user) and hold.resolution in {"Held", "Essential Duty"} and task.status in service.OPEN_TASKS}
                       for hold, task in rows], "total": total, "offset": offset, "limit": limit}


@router.post("/{event_id}/tasks/{hold_id}/review")
def review_event_task(event_id: int, hold_id: int, payload: EventTaskDecision,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_approver(user)
    event = record_or_404(db, event_id, user)
    hold = db.get(FarmEventTask, hold_id)
    if not hold or hold.event_id != event.id:
        raise HTTPException(404, "Held task not found.")
    task = db.get(FarmActivity, hold.activity_id)
    def operation():
        service.resolve_task_hold(db, event, hold, task, payload, user)
        db.flush()
        return {"id": hold.id, "resolution": hold.resolution, "version": hold.version}
    return mutate(db, operation)
