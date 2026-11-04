"""Admin-only backup APIs. No credentials or filesystem paths in public state."""

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
import shutil
import tempfile
from urllib.parse import parse_qs
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_administrator, has_permission
from app.core.recovery_runtime import HostLock, RecoveryBusy, runtime
from app.core.security import verify_password
from app.models import User
from app.services.recovery_service import RecoveryError
from app.services.backup_recovery.catalog import now
from app.services.backup_recovery.crypto import BackupError
from app.services.backup_recovery.drive import Drive
from app.services.backup_recovery.manager import RecoveryManager
from app.services.backup_recovery.options import (
    BackupOptions,
    BackupRequest,
    Credentials,
    Activation,
)

router = APIRouter(prefix="/api/v1/backup-recovery", tags=["Backup and Recovery"])


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except (BackupError, RecoveryBusy, RecoveryError) as error:
        raise HTTPException(
            409 if isinstance(error, RecoveryBusy) else 400, str(error)
        ) from None
    except Exception:
        raise HTTPException(
            400,
            "The operation could not complete. Check server configuration, permissions and available storage.",
        ) from None


def manager():
    return call(RecoveryManager)


def approve(credentials, user, service):
    with HostLock("reauth-" + str(user.id), timeout=10):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        with service.catalog.connect() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM audit WHERE json_extract(data,'$.actor')=? AND json_extract(data,'$.action')='restore_verification_failed' AND json_extract(data,'$.created_at')>?",
                (str(user.id), cutoff),
            ).fetchone()[0]
        if count >= 5:
            raise HTTPException(
                429, "Too many verification attempts. Try again in 15 minutes."
            )
        valid = False
        try:
            valid = verify_password(credentials.password, user.password_hash)
            if user.two_factor_enabled:
                import pyotp

                valid = (
                    valid
                    and bool(user.two_factor_secret)
                    and pyotp.TOTP(user.two_factor_secret).verify(
                        credentials.otp_code, valid_window=1
                    )
                )
        except Exception:
            valid = False
        if not valid:
            service.catalog.event(user.id, "restore_verification_failed", "Failed")
            raise HTTPException(403, "Administrator verification failed.")
    return {
        "user_id": user.id,
        "auth_version": int(user.auth_version or 0),
        "epoch": runtime()["epoch"],
        "at": now(),
    }


@router.get("/overview")
def overview(user: User = Depends(require_administrator), service=Depends(manager)):
    if not service.catalog.get("metadata", "legacy-loaded"):
        service.import_legacy()
        service.catalog.put("metadata", "legacy-loaded", {"at": now()})
    return call(service.overview)


@router.get("/notices")
def notices(user: User = Depends(require_administrator), service=Depends(manager)):
    value = call(service.overview)
    result = []
    if value["backup_overdue"]:
        result.append(
            {
                "id": "backup-due-" + str(value["last_local"]),
                "message": "A farm recovery backup is due. Open System Settings > System Data > Backup & Recovery.",
            }
        )
    if value["drive"].get("status") == "Needs reconnection":
        result.append(
            {
                "id": "google-reconnect-" + str(value["drive"].get("connected_at")),
                "message": "Google Drive needs reconnection. Local backups remain available.",
            }
        )
    return result


@router.put("/settings")
def save_settings(
    value: BackupOptions,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return call(service.save_options, value.model_dump(), user.username)


@router.post("/readiness")
def readiness(user: User = Depends(require_administrator), service=Depends(manager)):
    return {**call(service.readiness), "estimated_bytes": call(service.estimate)}


@router.post("/backups", status_code=202)
def create(
    value: BackupRequest,
    user: User = Depends(require_administrator),
    service=Depends(manager),
    idempotency_key: str | None = Header(default=None, max_length=100),
):
    return service.public_job(
        call(service.queue_backup, value.model_dump(), user.username, idempotency_key)
    )


class Keep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep: bool


@router.patch("/backups/{identifier}/keep")
def keep(
    identifier: str,
    value: Keep,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return call(service.protect, identifier, value.keep, user.username)


class Confirmation(BaseModel):
    confirmation: str


@router.post("/backups/{identifier}/delete", status_code=202)
def delete(
    identifier: str,
    value: Confirmation,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    if value.confirmation != "DELETE":
        raise HTTPException(400, "Enter DELETE to confirm.")
    return service.public_job(
        service.catalog.enqueue(
            "delete", {"backup_id": identifier}, user.username, "delete:" + identifier
        )
    )


@router.post("/backups/{identifier}/upload", status_code=202)
def upload(
    identifier: str,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return service.public_job(
        service.catalog.enqueue("upload", {"backup_id": identifier}, user.username)
    )


@router.get("/backups/{identifier}/download/{kind}")
def download(
    identifier: str,
    kind: str,
    decrypt: bool = False,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    value = service.catalog.get("backup", identifier)
    if (
        not value
        or value["status"] not in ("Completed", "Partial")
        or kind not in value["artifacts"]
    ):
        raise HTTPException(404, "Backup file unavailable.")
    temporary = tempfile.TemporaryDirectory(dir=service.root / "tmp")
    try:
        artifact = value["artifacts"][kind]
        name = artifact["name"] + (
            ".enc" if artifact.get("encrypted") and not decrypt else ""
        )
        path = Path(temporary.name) / name
        if decrypt:
            call(service.plaintext, artifact, path)
        else:
            shutil.copyfile(call(service.artifact_path, artifact), path)
        service.catalog.event(
            user.username,
            "backup_download_started",
            backup_id=identifier,
            artifact=kind,
            decrypted=decrypt,
        )
        return FileResponse(
            path,
            filename=name,
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store"},
            background=BackgroundTask(temporary.cleanup),
        )
    except Exception:
        temporary.cleanup()
        raise


@router.post("/recovery-key")
def key(
    value: Credentials,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    approve(value, user, service)
    service.catalog.put(
        "key-export", service.keys.id, {"at": now(), "actor": user.username}
    )
    service.catalog.event(user.username, "recovery_key_download_started")
    return Response(
        service.keys.path.read_bytes(),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="Joross_recovery.key"',
        },
    )


def google(service, fn, *args):
    drive = Drive(service.catalog, service.keys)
    try:
        return call(getattr(drive, fn), *args)
    finally:
        drive.close()


@router.post("/drive/connect")
def connect(user: User = Depends(require_administrator), service=Depends(manager)):
    return {
        "authorization_url": google(
            service, "start", user.id, int(user.auth_version or 0)
        )
    }


@router.get("/drive/callback")
def callback(request: Request, db: Session = Depends(get_db), service=Depends(manager)):
    query = parse_qs(
        request.scope.get(
            "joross_oauth_query", request.scope.get("query_string", b"")
        ).decode("utf8", errors="ignore")
    )

    def authorized(identifier, version):
        user = db.get(User, identifier)
        if (
            not user
            or user.status != "Active"
            or int(user.auth_version or 0) != version
            or not user.role
            or not user.role.is_active
            or not has_permission(user, "*")
        ):
            raise BackupError(
                "The account starting Google OAuth is no longer authorized."
            )

    try:
        if query.get("error") or not query.get("state") or not query.get("code"):
            raise BackupError("Google connection incomplete.")
        google(service, "finish", query["state"][0], query["code"][0], authorized)
        target = settings.backup_frontend_return_url
    except Exception:
        target = (
            settings.backup_frontend_return_url
            + ("&" if "?" in settings.backup_frontend_return_url else "?")
            + "drive_connection=failed"
        )
    return RedirectResponse(target, status_code=303)


@router.post("/drive/disconnect")
def disconnect(user: User = Depends(require_administrator), service=Depends(manager)):
    google(service, "disconnect", user.username)
    return {"status": "Disconnected"}


@router.get("/drive/storage")
def storage(user: User = Depends(require_administrator), service=Depends(manager)):
    return {"quota": google(service, "quota"), "folders": google(service, "folders")}


class Folder(BaseModel):
    name: str = Field(default="Joross Farm Backups", min_length=1, max_length=100)
    folder_id: str | None = None


@router.put("/drive/folder")
def folder(
    value: Folder, user: User = Depends(require_administrator), service=Depends(manager)
):
    result = (
        google(service, "select_folder", value.folder_id)
        if value.folder_id
        else google(service, "create_folder", value.name)
    )
    service.catalog.event(user.username, "backup_folder_changed")
    return result


@router.get("/drive/backups")
def cloud(user: User = Depends(require_administrator), service=Depends(manager)):
    return google(service, "remote_sets")


class Selection(BaseModel):
    format: str = Field(pattern="^(zip|bak)$")


@router.post("/backups/{identifier}/prepare")
def prepare(
    identifier: str,
    value: Selection,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return call(service.candidate_from_set, identifier, value.format)


class CloudSelection(Selection):
    backup_id: str = Field(max_length=100)
    recovery_key: str = Field(default="", max_length=512)


@router.post("/drive/prepare", status_code=202)
def prepare_cloud(
    value: CloudSelection,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return service.public_job(
        service.catalog.enqueue(
            "cloud_import",
            {
                "backup_id": value.backup_id,
                "format": value.format,
                "key": (
                    service.keys.seal(value.recovery_key)
                    if value.recovery_key
                    else None
                ),
            },
            user.username,
        )
    )


@router.post("/candidates/import")
async def imported(
    primary: UploadFile = File(...),
    companion: UploadFile | None = File(default=None),
    recovery_key: str = Form(default="", max_length=512),
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    try:
        with tempfile.TemporaryDirectory(dir=service.root / "tmp") as temporary:
            paths = []
            total = 0
            for index, file in enumerate(
                [primary] + ([companion] if companion else [])
            ):
                path = Path(temporary) / str(index)
                with path.open("wb") as output:
                    while block := await file.read(1024 * 1024):
                        total += len(block)
                        if total > settings.backup_max_upload_bytes:
                            raise HTTPException(
                                413, "Uploaded backup exceeds the supported size."
                            )
                        output.write(block)
                paths.append(path)
            result = await asyncio.to_thread(
                partial(
                    call,
                    service.import_candidate,
                    paths[0],
                    paths[1] if len(paths) > 1 else None,
                    key=recovery_key.encode() if recovery_key else None,
                )
            )
            service.catalog.event(
                user.username, "backup_import_validated", candidate_id=result["id"]
            )
            return result
    finally:
        await primary.close()
        if companion:
            await companion.close()


@router.post("/candidates/{identifier}/test", status_code=202)
def test(
    identifier: str,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    value = service.catalog.get("candidate", identifier)
    if not value or value["status"] != "Validated":
        raise HTTPException(409, "Choose a validated, unused staged copy.")
    return service.public_job(
        service.catalog.enqueue(
            "test", {"candidate_id": identifier}, user.username, "test:" + identifier
        )
    )


@router.post("/candidates/{identifier}/activate", status_code=202)
def activate(
    identifier: str,
    value: Activation,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    candidate = service.catalog.get("candidate", identifier)
    if not settings.backup_activation_enabled:
        raise HTTPException(
            409, "Activation is disabled until host recovery testing is completed."
        )
    if value.confirmation != "RESTORE":
        raise HTTPException(400, "Enter RESTORE to confirm.")
    if (
        not candidate
        or candidate["status"] != "Ready"
        or not candidate.get("restore_tested")
    ):
        raise HTTPException(409, "A successful staged restore is required.")
    return service.public_job(
        service.catalog.enqueue(
            "activate",
            {"candidate_id": identifier, "approval": approve(value, user, service)},
            user.username,
            "activate:" + identifier,
        )
    )


@router.post("/candidates/{identifier}/discard", status_code=202)
def discard(
    identifier: str,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return service.public_job(
        service.catalog.enqueue(
            "discard",
            {"candidate_id": identifier},
            user.username,
            "discard:" + identifier,
        )
    )


@router.post("/rollbacks/{identifier}/prepare", status_code=202)
def rollback(
    identifier: str,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    return service.public_job(
        service.catalog.enqueue("rollback", {"rollback_id": identifier}, user.username)
    )


@router.post("/jobs/{identifier}/retry", status_code=202)
def retry(
    identifier: str,
    user: User = Depends(require_administrator),
    service=Depends(manager),
):
    value = service.catalog.job(identifier)
    if (
        not value
        or value["status"] not in ("Failed", "Incomplete", "Partial")
        or value["kind"] in ("activate", "test")
    ):
        raise HTTPException(
            409,
            "This job needs a fresh recovery selection or approval, or is already running.",
        )
    if value["kind"] == "backup":
        return service.public_job(
            service.catalog.enqueue("backup", value["payload"], user.username)
        )
    return service.public_job(
        service.catalog.update_job(
            identifier, status="Queued", attempts=0, next_attempt=None, error=None
        )
    )
