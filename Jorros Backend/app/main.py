import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import SessionLocal, check_database_connection, get_db
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.locations import router as locations_router
from app.routers.archives import router as archives_router
from app.routers.void_authorizations import router as void_authorizations_router
from app.routers.roles import router as roles_router
from app.routers.crops import router as crops_router
from app.routers.livestock import router as livestock_router
from app.routers.inventory import router as inventory_router
from app.routers.activities import router as activities_router
from app.routers.alerts import router as alerts_router
from app.routers.weather import router as weather_router
from app.routers.reports import router as reports_router
from app.routers.backups import router as backups_router
from app.routers.backup_recovery import router as backup_recovery_router
from app.services.backup_recovery.worker import RecoveryGateMiddleware, backup_worker_loop
from app.routers.imports import router as imports_router
from app.routers.audit import router as audit_router
from app.routers.resource_usages import router as resource_usages_router
from app.routers.production_sales import router as production_sales_router
from app.routers.analytics import router as analytics_router
from app.routers.workforce import router as workforce_router
from app.routers.events import router as events_router
from app.routers.system import router as system_router
from app.routers.farm_events import router as farm_events_router
from app.routers.farm_locations import router as farm_locations_router
from app.services.report_scheduler import (
    attendance_schema_missing_columns,
    report_scheduler_loop,
)
from app.services.farm_automation_scheduler import (
    farm_automation_scheduler_loop,
    scheduler_health,
)
from app.services.leave_coverage_service import reconcile_expired_leave_coverage


LOGGER = logging.getLogger("joross.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks: list[asyncio.Task] = []

    # Startup recovery is intentionally idempotent. If the previous process
    # stopped while leave coverage was active, eligible future Pending tasks
    # are safely restored before the scheduler begins its recurring cycle.
    from app.core.recovery_runtime import farm_access, RecoveryBusy
    try:
        with farm_access():
            startup_db = SessionLocal()
            try:
                reconcile_expired_leave_coverage(startup_db, actor_name="System Startup Recovery")
                startup_db.commit()
            except Exception as error:
                startup_db.rollback()
                LOGGER.exception("Leave coverage startup recovery failed: %s", error)
            finally:
                startup_db.close()

            # Give operators an immediate, actionable message when a newer source ZIP
            # is running against an older SQL Server schema. This check is read-only; it
            # never stamps or upgrades the database automatically.
            schema_db = SessionLocal()
            try:
                missing_attendance_columns = attendance_schema_missing_columns(schema_db)
                if missing_attendance_columns:
                    LOGGER.warning(
                        "Database migration required before Attendance is fully usable. "
                        "Run `python -m alembic upgrade head` from Jorros Backend. "
                        f"Missing staff_attendance columns: {', '.join(sorted(missing_attendance_columns))}"
                    )
            except Exception as error:
                LOGGER.exception("Database schema readiness check could not run: %s", error)
            finally:
                schema_db.close()

    except RecoveryBusy:
        LOGGER.info("Farm startup checks deferred during backup/recovery maintenance.")

    if settings.backup_worker_enabled:
        background_tasks.append(asyncio.create_task(backup_worker_loop()))

    if settings.report_scheduler_enabled:
        background_tasks.append(asyncio.create_task(report_scheduler_loop()))

    if settings.farm_automation_scheduler_enabled:
        background_tasks.append(asyncio.create_task(farm_automation_scheduler_loop()))

    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()

        for task in background_tasks:
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="JoRoss Farm API",
    description="Backend API for JoRoss Farm Analytics and Production Monitoring System",
    version="1.0.0",
    lifespan=lifespan,
)

for router in [
    auth_router, users_router, roles_router, crops_router, locations_router, archives_router, void_authorizations_router,
    livestock_router, inventory_router, activities_router,
    alerts_router, weather_router, reports_router, backups_router,
    backup_recovery_router, imports_router, audit_router, resource_usages_router, production_sales_router, analytics_router, workforce_router,
    events_router, system_router, farm_events_router, farm_locations_router,
]:
    app.include_router(router)

configured_cors_origins = [
    origin.strip().rstrip("/")
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RecoveryGateMiddleware)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID")
    if not request_id or len(request_id) > 64 or not request_id.isascii() or not request_id.replace("-", "").isalnum():
        request_id = uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
        raise
    duration_ms = round((time.perf_counter() - started) * 1000)
    if duration_ms >= 750 and request.url.path != "/api/v1/events/stream":
        LOGGER.warning("slow_request request_id=%s method=%s path=%s status=%s duration_ms=%s",
                       request_id, request.method, request.url.path, response.status_code, duration_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")

    # Authentication and account-security responses must not be cached by
    # browsers or intermediate proxies.
    if request.url.path.startswith(("/api/v1/auth", "/api/v1/backup-recovery")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

    return response


@app.get("/")
def root():
    return {"message": "JoRoss Farm API is running"}


@app.get("/api/v1/health")
def health_check():
    database_connected = check_database_connection()
    return {
        "status": "ok" if database_connected else "error",
        "api": "connected",
        "database": "connected" if database_connected else "disconnected",
    }


@app.get("/api/v1/health/scheduler")
def scheduler_health_check(db: Session = Depends(get_db)):
    """Expose leader identity and the most recent durable scheduler result."""

    return scheduler_health(db)
