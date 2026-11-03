"""Inventory metadata history committed atomically with the record."""
import json

from sqlalchemy import inspect

from app.models import AuditLog


def inventory_snapshot(item):
    return {
        column.key: getattr(item, column.key)
        for column in inspect(type(item)).column_attrs
        if column.key not in {"created_at", "updated_at"}
    }


def record_inventory_change(db, item, actor, *, action, before=None):
    after = inventory_snapshot(item)
    changes = {
        key: {"before": before.get(key) if before else None, "after": value}
        for key, value in after.items()
        if before is None or before.get(key) != value
    }
    if not changes:
        return
    common = dict(
        module="Inventory", record_name=item.name, entity_id=item.item_code,
        details=json.dumps({"changes": changes}, default=str, ensure_ascii=False, sort_keys=True),
        icon="inventory_2", actor_user_id=actor.id,
        actor_name=actor.full_name or actor.username,
    )
    db.add(AuditLog(event_type="audit", action=action, **common))
    db.add(AuditLog(event_type="timeline", action=action, **common))
