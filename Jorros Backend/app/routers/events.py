"""Authenticated SSE backed by committed SQL rows across API workers."""
import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.dependencies import has_permission, is_task_only_user
from app.models import Employee, FarmChangeEvent, User
from app.routers.auth import bearer_scheme, get_current_user


LOGGER = logging.getLogger("joross.events")
router = APIRouter(prefix="/api/v1/events", tags=["Farm Changes"])
MODULE_PERMISSIONS = {
    "tasks": ("workforce:manage", "workforce:review"), "my_tasks": "workforce:submit",
    "calendar": ("workforce:attendance", "workforce:manage"),
    "employees": "workforce:manage", "care_templates": "workforce:manage", "crops": "crops:view",
    "livestock": "livestock:view", "inventory": "inventory:view", "production_sales": "production_sales:view",
    "dashboard": "dashboard:view", "intelligence": "intelligence:view", "alerts": "alerts:view",
    "notifications": "notifications:view", "reports": "reports:view", "imports": "imports:preview",
    "weather": "weather:view", "users": "users:view", "settings": "settings:view",
}
PRIVATE_ENTITIES = {"Task", "TaskSubmission", "Assignment", "TaskEvidence", "Employee", "Attendance", "Leave", "Schedule"}


def get_stream_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db, scope="function"),
) -> User:
    """Authenticate with a short-lived session; a live stream must not occupy a pool connection."""
    return get_current_user(credentials=credentials, db=db)


def load_authorized_events(db: Session, user: User, employee_id: int | None, after_id: int):
    """Recheck status, role and token version on each poll; emit only allowed modules."""
    account = db.scalar(select(User).options(joinedload(User.role)).where(User.id == user.id))
    if (not account or account.status != "Active" or not account.role or
            not account.role.is_active or account.auth_version != user.auth_version or
            (account.active_session_expires_at is not None and (
                account.active_session_expires_at <= datetime.now(timezone.utc).replace(tzinfo=None) or
                account.active_session_auth_version != user.auth_version))):
        raise HTTPException(status_code=401, detail="Account session has changed.")
    task_only = is_task_only_user(account)
    if task_only:
        audience = FarmChangeEvent.target_user_id == account.id
        if employee_id is not None:
            audience = or_(audience, FarmChangeEvent.target_employee_id == employee_id)
    else:
        audience = or_(FarmChangeEvent.target_user_id == account.id,
                       FarmChangeEvent.target_user_id.is_(None) & FarmChangeEvent.target_employee_id.is_(None))
    rows = db.scalars(select(FarmChangeEvent).where(FarmChangeEvent.id > after_id, audience)
                      .order_by(FarmChangeEvent.id).limit(100)).all()
    private_identity = task_only or any(has_permission(account, permission) for permission in
                                        ("workforce:manage", "workforce:review", "workforce:attendance"))
    notices = []
    for row in rows:
        modules = json.loads(row.modules_json)
        def allowed(name):
            if name == "archives" and row.entity_type.startswith("Archive:"):
                from app.services.archive_service import REGISTRY
                archive_module = REGISTRY.get(row.entity_type.split(":", 1)[1])
                return bool(archive_module and has_permission(account, archive_module[3]))
            required = MODULE_PERMISSIONS.get(name, "*")
            return any(has_permission(account, permission) for permission in
                       (required if isinstance(required, tuple) else (required,)))

        modules = ([name for name in modules if name == "my_tasks"] if task_only else
                   [name for name in modules if allowed(name)])
        if not modules:
            continue
        private = row.entity_type in PRIVATE_ENTITIES and not private_identity
        notices.append({"id": row.id, "event_type": row.event_type,
                        "entity_type": "FarmChange" if private else row.entity_type,
                        "entity_id": None if private or row.entity_type.startswith("Archive:") else row.entity_id, "modules": modules,
                        "target_employee_id": row.target_employee_id, "target_user_id": row.target_user_id,
                        "record_version": row.record_version,
                        "timestamp": row.created_at.replace(tzinfo=timezone.utc).isoformat()})
    return notices, (rows[-1].id if rows else after_id)


@router.get("/stream")
async def stream_changes(request: Request, since: int | None = Query(default=None, ge=0),
                         last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
                         db: Session = Depends(get_db, scope="function"),
                         user: User = Depends(get_stream_user)):
    engine = db.get_bind()
    employee_id = db.scalar(select(Employee.id).where(Employee.login_user_id == user.id))
    try:
        cursor = int(last_event_id) if last_event_id else since
        if cursor is not None and cursor < 0:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event cursor.")
    latest_id = db.scalar(select(func.max(FarmChangeEvent.id))) or 0
    if cursor is None or cursor > latest_id:
        cursor = latest_id

    def poll(last_id):
        with Session(engine, expire_on_commit=False) as session:
            return load_authorized_events(session, user, employee_id, last_id)

    async def body():
        nonlocal cursor
        yield ": connected\n\n"
        # The client refreshes its visible view at this boundary. A commit
        # between the initial page request and the first stream request is
        # otherwise lost when a new subscription starts at max(id).
        yield f"event: ready\ndata: {json.dumps({'cursor': cursor})}\n\n"
        heartbeat = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            try:
                rows, cursor = await run_in_threadpool(poll, cursor)
            except HTTPException:
                yield "event: reconnect\ndata: {}\n\n"
                break
            except Exception:
                LOGGER.exception("Committed event poll failed")
                break
            for row in rows:
                yield f"id: {row['id']}\nevent: change\ndata: {json.dumps(row, separators=(',', ':'))}\n\n"
            now = asyncio.get_running_loop().time()
            if now - heartbeat >= 15:
                yield ": heartbeat\n\n"
                heartbeat = now
            await asyncio.sleep(2)

    return StreamingResponse(body(), media_type="text/event-stream", headers={
        "Cache-Control": "private, no-cache, no-transform", "X-Accel-Buffering": "no", "Vary": "Authorization",
    })
