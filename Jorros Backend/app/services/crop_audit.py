"""Authoritative crop lifecycle audit entries written with the crop transaction."""
import json

from sqlalchemy import inspect

from app.models import AuditLog


def crop_snapshot(crop):
    return {column.key: getattr(crop, column.key) for column in inspect(type(crop)).column_attrs
            if column.key not in {"created_at", "updated_at"}}


def record_crop_change(db, crop, actor, *, action, before=None):
    after = crop_snapshot(crop)
    changes = {key: {"before": before.get(key) if before else None, "after": value}
               for key, value in after.items() if before is None or before.get(key) != value}
    if not changes:
        return
    common = dict(module="Crop", record_name=crop.name, entity_id=crop.crop_code,
                  details=json.dumps({"changes": changes}, default=str, ensure_ascii=False, sort_keys=True),
                  icon="grass", actor_user_id=actor.id, actor_name=actor.full_name or actor.username)
    db.add(AuditLog(event_type="audit", action=action, **common))
    db.add(AuditLog(event_type="timeline", action=action, **common))
