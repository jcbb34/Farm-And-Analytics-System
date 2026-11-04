import asyncio
import logging
from app.core.config import settings
from app.core.recovery_runtime import HostLock, RecoveryBusy, runtime
from .manager import RecoveryManager


async def backup_worker_loop():
    await asyncio.sleep(2)
    while True:
        try:
            await asyncio.to_thread(lambda: RecoveryManager().tick())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logging.getLogger("joross.backup-worker").error(
                "Backup worker needs attention: %s", type(error).__name__
            )
        await asyncio.sleep(settings.backup_worker_interval_seconds)


class RecoveryGateMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        path = scope.get("path", "")
        if path == "/api/v1/backup-recovery/drive/callback":
            scope["joross_oauth_query"] = scope.get("query_string", b"")
            scope["query_string"] = b""
        if (
            path == "/api/v1/backup-recovery/candidates/import"
            and scope.get("method") == "POST"
        ):
            from fastapi import HTTPException

            maximum = settings.backup_max_upload_bytes + 2 * 1024 * 1024
            headers = dict(scope.get("headers", []))
            try:
                if int(headers.get(b"content-length", b"0")) > maximum:
                    return await JSONResponse(
                        {"detail": "Recovery upload exceeds the supported size."},
                        status_code=413,
                    )(scope, receive, send)
            except ValueError:
                return await JSONResponse(
                    {"detail": "Invalid upload length."}, status_code=400
                )(scope, receive, send)

            def authorize():
                from app.core.database import get_db
                from app.core.dependencies import has_permission
                from app.routers.auth import get_current_user
                from fastapi.security import HTTPAuthorizationCredentials

                parts = (
                    headers.get(b"authorization", b"")
                    .decode("ascii", errors="ignore")
                    .split(" ", 1)
                )
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    raise HTTPException(401, "Authentication required.")
                factory = getattr(scope.get("app"), "dependency_overrides", {}).get(
                    get_db, get_db
                )
                generator = factory()
                try:
                    user = get_current_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer", credentials=parts[1]
                        ),
                        next(generator),
                    )
                    if not has_permission(user, "*"):
                        raise HTTPException(403, "Administrator access is required.")
                finally:
                    generator.close()

            try:
                await asyncio.to_thread(authorize)
            except HTTPException as error:
                return await JSONResponse(
                    {"detail": error.detail}, status_code=error.status_code
                )(scope, receive, send)
            except Exception:
                return await JSONResponse(
                    {"detail": "Account authorization is temporarily unavailable."},
                    status_code=503,
                )(scope, receive, send)
            total = 0
            original = receive

            async def limited_receive():
                nonlocal total
                message = await original()
                total += len(message.get("body", b""))
                if total > maximum:
                    raise HTTPException(
                        413, "Recovery upload exceeds the supported size."
                    )
                return message

            return await self.app(scope, limited_receive, send)
        if (
            not path.startswith("/api/")
            or path.startswith(("/api/v1/backup-recovery", "/api/v1/health"))
            or path == "/api/v1/events/stream"
        ):
            return await self.app(scope, receive, send)
        lock = None
        try:
            if runtime().get("maintenance"):
                raise RecoveryBusy()
            lock = HostLock("farm-access", shared=True).acquire()
            if runtime().get("maintenance"):
                raise RecoveryBusy()
        except RecoveryBusy:
            if lock:
                lock.release()
            return await JSONResponse(
                {
                    "detail": "Backup or recovery maintenance is in progress. Try again shortly."
                },
                status_code=503,
                headers={"Retry-After": "3", "Cache-Control": "no-store"},
            )(scope, receive, send)
        try:
            return await self.app(scope, receive, send)
        finally:
            lock.release()
