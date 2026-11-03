"""Authoritative livestock metadata history in the record transaction."""
import json

from sqlalchemy import inspect

from app.models import AuditLog


def livestock_snapshot(record):
    return {column.key: getattr(record, column.key)
            for column in inspect(type(record)).column_attrs
            if column.key not in {"created_at", "updated_at"}}


def record_livestock_change(db, record, actor, *, action, before=None):
    after = livestock_snapshot(record)
    changes = {key: {"before": before.get(key) if before else None, "after": value}
               for key, value in after.items() if before is None or before.get(key) != value}
    if not changes:
        return
    common = dict(module="Livestock", record_name=record.record_name, entity_id=record.animal_code,
                  details=json.dumps({"changes": changes}, default=str, ensure_ascii=False, sort_keys=True),
                  icon="pets", actor_user_id=actor.id, actor_name=actor.full_name or actor.username)
    db.add(AuditLog(event_type="audit", action=action, **common))
    db.add(AuditLog(event_type="timeline", action=action, **common))
