"""Coalesce changes by entity family and audience in the business transaction."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, event, inspect, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.models.change_event import FarmChangeEvent


MODULES = {
    "farm_events": ("FarmDeclaration", ("calendar", "my_tasks", "tasks", "dashboard", "alerts")),
    "farm_event_tasks": ("SuspensionReview", ("calendar", "my_tasks", "tasks", "dashboard")),
    "farm_event_acknowledgements": ("DeclarationAcknowledgement", ("calendar", "my_tasks")),
    "farm_event_audits": ("DeclarationAudit", ("calendar",)),
    "farm_event_reports": ("DeclarationReport", ("calendar", "my_tasks")),
    "audit_logs": ("Archive", ("archives", "settings")),
    "farm_activities": ("Task", ("tasks", "my_tasks", "dashboard", "intelligence", "alerts")),
    "task_submissions": ("TaskSubmission", ("tasks", "my_tasks", "inventory", "livestock", "crops", "dashboard")),
    "task_assignment_history": ("Assignment", ("tasks", "my_tasks", "calendar")),
    "task_leave_coverage": ("Assignment", ("tasks", "my_tasks", "calendar")),
    "task_evidence": ("TaskEvidence", ("tasks", "my_tasks")),
    "employees": ("Employee", ("employees", "tasks", "calendar", "reports")),
    "employee_work_schedules": ("Schedule", ("employees", "calendar", "tasks", "my_tasks")),
    "staff_attendance": ("Attendance", ("calendar", "reports", "tasks", "my_tasks")),
    "staff_leave": ("Leave", ("calendar", "tasks", "my_tasks", "reports")),
    "staff_shifts": ("Schedule", ("calendar", "tasks", "my_tasks")),
    "care_templates": ("CareTemplate", ("care_templates", "tasks")),
    "care_template_steps": ("CareTemplate", ("care_templates", "tasks")),
    "crops": ("Crop", ("crops", "production_sales", "dashboard", "intelligence", "reports", "alerts")),
    "crop_growth_records": ("CropGrowth", ("crops", "dashboard", "intelligence")),
    "crop_pest_diseases": ("CropHealth", ("crops", "dashboard", "intelligence", "alerts")),
    "crop_yield_records": ("CropYield", ("crops", "production_sales", "dashboard", "intelligence", "reports")),
    "livestock": ("Livestock", ("livestock", "dashboard", "intelligence", "reports", "alerts")),
    "livestock_feeding_records": ("Feeding", ("livestock", "inventory", "dashboard", "intelligence")),
    "livestock_growth_records": ("LivestockGrowth", ("livestock", "dashboard", "intelligence")),
    "livestock_vaccination_records": ("Vaccination", ("livestock", "inventory", "dashboard", "intelligence")),
    "livestock_production_records": ("Production", ("production_sales", "livestock", "dashboard", "intelligence", "reports")),
    "livestock_sales": ("Sale", ("production_sales", "dashboard", "intelligence", "reports")),
    "livestock_processing_records": ("Production", ("production_sales", "livestock", "dashboard", "reports")),
    "resource_usages": ("InventoryMovement", ("inventory", "tasks", "dashboard", "intelligence")),
    "inventory_items": ("Inventory", ("inventory", "dashboard", "intelligence", "alerts")),
    "inventory_stock_records": ("InventoryMovement", ("inventory", "dashboard", "intelligence")),
    "farm_alerts": ("Alert", ("alerts", "notifications", "dashboard")),
    "farm_reports": ("Report", ("reports",)),
    "data_import_batches": ("Import", ("imports", "crops", "livestock", "inventory", "dashboard", "reports")),
    "weather_history": ("Weather", ("weather", "dashboard", "intelligence", "alerts")),
    "users": ("User", ("users", "settings")),
    "roles": ("Role", ("users", "settings")),
}
PRIVATE = {"farm_activities", "task_submissions", "task_assignment_history", "task_leave_coverage",
           "task_evidence", "employees", "employee_work_schedules", "staff_attendance", "staff_leave", "staff_shifts"}


def _employee_ids(item):
    table = item.__table__.name
    if table == "employees":
        return [item.id]
    if table == "task_assignment_history":
        return [value for value in (item.old_employee_id, item.new_employee_id) if value]
    if table == "farm_activities":
        history = inspect(item).attrs.assigned_employee_id.history
        return [value for value in (*history.deleted, item.assigned_employee_id) if value]
    employee_id = getattr(item, "employee_id", None)
    return [employee_id] if employee_id else []


def _after_flush(session: Session, flush_context):
    notices = session.info.setdefault("farm_change_rows", {})
    changed = [(item, "created") for item in session.new]
    changed += [(item, "updated") for item in session.dirty if session.is_modified(item, include_collections=False)]
    changed += [(item, "deleted") for item in session.deleted]
    for item, action in changed:
        table = getattr(getattr(item, "__table__", None), "name", None)
        if table == "audit_logs" and item.event_type != "archive":
            continue
        if table not in MODULES or isinstance(item, FarmChangeEvent):
            continue
        family, modules = MODULES[table]
        if table == "audit_logs":
            family, modules = f"Archive:{item.module}", ("archives",)
        audiences = [(None, None)]
        if table in PRIVATE:
            audiences.extend((int(value), None) for value in set(_employee_ids(item)))
        if table == "users":
            audiences.append((None, int(item.id)))
        for employee_id, user_id in audiences:
            key = (family, employee_id, user_id)
            existing = notices.get(key)
            if existing:
                if existing.entity_id != item.id or existing.event_type != f"{family.lower()}.{action}":
                    if existing.id is not None:
                        session.connection().execute(update(FarmChangeEvent).where(FarmChangeEvent.id == existing.id)
                                                     .values(entity_id=None, event_type=f"{family.lower()}.batch"))
                        set_committed_value(existing, "entity_id", None)
                        set_committed_value(existing, "event_type", f"{family.lower()}.batch")
                    else:
                        existing.entity_id = None
                        existing.event_type = f"{family.lower()}.batch"
                continue
            notice = FarmChangeEvent(event_type=f"{family.lower()}.{action}", entity_type=family,
                                     entity_id=item.id, modules_json=json.dumps(modules),
                                     target_employee_id=employee_id, target_user_id=user_id)
            notices[key] = notice
            session.add(notice)


def _clear(session: Session):
    session.info.pop("farm_change_rows", None)
    session.info.pop("farm_event_context", None)
    session.info.pop("farm_event_schedule_locks", None)


def install_change_events():
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
        event.listen(Session, "after_commit", _clear)
        event.listen(Session, "after_rollback", _clear)


def prune_change_events(db: Session, *, retention_days: int = 14, batch_size: int = 500) -> int:
    """Prune a bounded batch; reconnecting clients refresh at the ready boundary."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days)
    ids = db.scalars(select(FarmChangeEvent.id).where(FarmChangeEvent.created_at < cutoff)
                     .order_by(FarmChangeEvent.created_at, FarmChangeEvent.id).limit(batch_size)).all()
    if ids:
        db.execute(delete(FarmChangeEvent).where(FarmChangeEvent.id.in_(ids)))
        db.commit()
    return len(ids)
