from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import has_permission, require_administrator
from app.models import AuditLog, User
from app.routers.auth import get_current_user
from app.schemas.audit import AuditLogCreate, AuditLogResponse


router = APIRouter(
    prefix="/api/v1/audit-logs",
    tags=["Audit Trail"],
)


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    event_type: str | None = Query(default=None, pattern="^(audit|timeline)$"),
    module: str | None = None,
    limit: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_administrator),
):
    statement = select(AuditLog)
    if event_type:
        statement = statement.where(AuditLog.event_type == event_type)
    if module:
        statement = statement.where(AuditLog.module == module)

    statement = statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    return list(db.scalars(statement).all())


@router.post("", response_model=AuditLogResponse, status_code=status.HTTP_201_CREATED)
def create_audit_log(
    payload: AuditLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Client-generated audit/timeline events are accepted only for modules
    # the authenticated user can modify. The actor identity always comes from
    # the authenticated database user, never from the client payload.
    module_permissions = {
        "Crop": {"crops:create", "crops:update", "crops:archive"},
        "Livestock": {"livestock:create", "livestock:update", "livestock:archive"},
        "Inventory": {"inventory:create", "inventory:update", "inventory:adjust", "inventory:archive"},
        "Report": {"reports:create", "reports:update"},
    }
    required_any = module_permissions.get(payload.module.strip())
    if not has_permission(current_user, "*") and (
        not required_any
        or not any(has_permission(current_user, permission) for permission in required_any)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot record audit events for this module.",
        )

    record = AuditLog(
        event_type=payload.event_type,
        action=payload.action.strip(),
        module=payload.module.strip() or "System",
        record_name=(payload.record_name or "").strip() or None,
        entity_id=(payload.entity_id or "").strip() or None,
        details=(payload.details or "").strip() or None,
        icon=(payload.icon or "").strip() or None,
        actor_user_id=current_user.id,
        actor_name=current_user.full_name,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
