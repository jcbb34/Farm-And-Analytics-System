"""Durable jobs, verified staging and deliberately confirmed database cutovers."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.recovery_runtime import (
    HostLock,
    RecoveryBusy,
    control_root,
    farm_access,
    runtime,
    write_runtime,
)
from app.services.backup_service import _snapshot_database
from app.services.evidence_storage import get_evidence_storage
from app.services.recovery_service import (
    inspect_recovery_package,
    write_recovery_package,
    restore_recovery_package,
    _safe_file,
)
from .catalog import Catalog, now
from .crypto import BackupError, Keyring, sha256_file, encrypted_file
from .drive import Drive, DriveError, API, file_id
from .native import SqlServer
from .options import BackupOptions, BackupRequest, next_run
from .packages import (
    current_revision,
    signatures,
    metadata,
    native_assets,
    inspect_assets,
    write_kit,
)


class RecoveryManager:
    def __init__(self, source_engine=None):
        if source_engine is None:
            from app.core.database import engine

            source_engine = engine
        self.engine = source_engine
        self.catalog = Catalog()
        self.root = self.catalog.root
        self.keys = Keyring(self.root / "secrets")
        self.native = SqlServer(source_engine)
        for name in ("sets", "incoming", "staging", "tmp"):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)

    def options(self):
        return BackupOptions.model_validate(self.catalog.get("settings", "backup", {}))

    def save_options(self, value, actor):
        value = BackupOptions.model_validate(value)
        if (
            value.schedule_enabled
            and value.format != "zip"
            and self.engine.dialect.name != "mssql"
        ):
            raise BackupError(
                "Scheduled BAK creation requires SQL Server. Choose ZIP on this installation."
            )
        if value.recovery_key_acknowledged and not self.catalog.get(
            "key-export", self.keys.id
        ):
            raise BackupError(
                "Download and save the recovery key before acknowledging it."
            )
        drive = Drive(self.catalog, self.keys)
        try:
            if (
                value.schedule_enabled
                and value.destination == "local_drive"
                and drive.connection().get("status") != "Connected"
            ):
                raise BackupError(
                    "Connect Google Drive before scheduling cloud backups."
                )
        finally:
            drive.close()
        self.catalog.put("settings", "backup", value.model_dump())
        self.catalog.put(
            "schedule",
            "next",
            {"at": next_run(value) if value.schedule_enabled else None},
        )
        self.catalog.event(actor, "backup_settings_changed")
        return value.model_dump()

    @staticmethod
    def public_job(value):
        return {key: val for key, val in value.items() if key not in ("payload",)}

    @staticmethod
    def public_candidate(value):
        return {
            key: value.get(key)
            for key in (
                "id",
                "backup_id",
                "format",
                "created_at",
                "source_date",
                "status",
                "file_validated",
                "restore_tested",
                "tested_at",
                "expires_at",
                "row_count",
                "table_count",
                "photo_count",
                "error",
                "rollback",
            )
        }

    @staticmethod
    def public_set(value):
        result = {
            key: value.get(key)
            for key in (
                "id",
                "created_at",
                "actor",
                "status",
                "format",
                "destination",
                "encrypted",
                "file_validated",
                "tested_formats",
                "restore_tested_at",
                "cloud_status",
                "uploaded_at",
                "protected",
                "row_count",
                "table_count",
                "photo_count",
                "error",
                "legacy",
            )
        }
        result["artifacts"] = {
            kind: {
                key: artifact.get(key)
                for key in ("name", "size", "encrypted", "checksum", "cloud_status")
            }
            for kind, artifact in value.get("artifacts", {}).items()
        }
        return result

    def sql_directory(self):
        path = (
            Path(settings.backup_sql_directory)
            if settings.backup_sql_directory
            else self.root / "sql-transfer"
        )
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    def readiness(self):
        value = {
            "available": False,
            "restore_available": False,
            "activation_enabled": settings.backup_activation_enabled,
            "reason": "Native BAK requires SQL Server and a shared backup folder.",
        }
        try:
            if self.engine.dialect.name == "mssql":
                value.update(self.native.probe())
                self.sql_directory()
                value["reason"] = (
                    "SQL backup permissions are available. Creating a BAK verifies folder access."
                )
        except Exception:
            value.update(
                available=False,
                reason="SQL Server readiness failed. Check connection, permissions and backup folder.",
            )
        self.catalog.put("readiness", "sql", value)
        return value

    def overview(self):
        values = self.catalog.list("backup")
        complete = sorted(
            [
                v
                for v in values
                if v["status"] == "Completed" and v.get("file_validated")
            ],
            key=lambda v: v["created_at"],
            reverse=True,
        )
        cloud = sorted(
            [v for v in complete if v.get("cloud_status") == "Completed"],
            key=lambda v: v.get("uploaded_at", ""),
            reverse=True,
        )
        tested = sorted(
            [v for v in values if v.get("restore_tested_at")],
            key=lambda v: v["restore_tested_at"],
            reverse=True,
        )
        drive = Drive(self.catalog, self.keys)
        try:
            connection = drive.connection()
        finally:
            drive.close()
        options = self.options()
        last = complete[0]["created_at"] if complete else None
        return {
            "options": options.model_dump(),
            "sets": [self.public_set(v) for v in values],
            "jobs": [self.public_job(v) for v in self.catalog.jobs()[:100]],
            "drills": [
                self.public_candidate(v) for v in self.catalog.list("candidate")
            ],
            "rollbacks": [
                {key: v.get(key) for key in ("id", "created_at", "status")}
                for v in self.catalog.list("rollback")
            ],
            "audit": self.catalog.events(),
            "drive": connection,
            "recovery_key_exported": bool(self.catalog.get("key-export", self.keys.id)),
            "storage": {"free_bytes": shutil.disk_usage(self.root).free},
            "readiness": self.catalog.get(
                "readiness",
                "sql",
                {
                    "available": False,
                    "activation_enabled": settings.backup_activation_enabled,
                },
            ),
            "last_local": last,
            "last_cloud": cloud[0]["uploaded_at"] if cloud else None,
            "last_test": tested[0]["restore_tested_at"] if tested else None,
            "next_backup": self.catalog.get("schedule", "next", {}).get("at"),
            "backup_overdue": options.reminder_enabled
            and (
                not last
                or datetime.fromisoformat(last) + timedelta(days=options.reminder_days)
                < datetime.now(timezone.utc)
            ),
            "maintenance": runtime().get("maintenance"),
        }

    def queue_backup(self, value, actor, key=None):
        value = BackupRequest.model_validate(value)
        if value.format != "zip" and self.engine.dialect.name != "mssql":
            raise BackupError(
                "ZIP works here. Native BAK requires your SQL Server installation."
            )
        if (
            value.destination == "local_drive"
            and value.encrypted
            and not self.options().recovery_key_acknowledged
        ):
            raise BackupError(
                "Save and acknowledge the recovery key before uploading encrypted backups."
            )
        return self.catalog.enqueue(
            "backup", value.model_dump(), actor, "backup:" + key if key else None
        )

    def estimate(self):
        size = 0
        if self.engine.dialect.name == "mssql":
            with self.engine.connect() as c:
                size = int(
                    c.scalar(
                        text(
                            "SELECT COALESCE(SUM(CAST(size AS bigint)),0)*8192 FROM sys.database_files"
                        )
                    )
                    or 0
                )
        elif (
            self.engine.url.database not in (None, ":memory:")
            and Path(self.engine.url.database).is_file()
        ):
            size = Path(self.engine.url.database).stat().st_size
        return max(
            size
            + sum(
                p.stat().st_size
                for p in get_evidence_storage().root.iterdir()
                if p.is_file() and not p.is_symlink()
            ),
            16 * 1024 * 1024,
        )

    def artifact_path(self, value):
        if value.get("legacy_path"):
            from app.services.backup_service import BACKUP_FOLDER

            path = Path(value["legacy_path"]).resolve()
            allowed = BACKUP_FOLDER.resolve()
        else:
            path = (self.root / value["path"]).resolve()
            allowed = self.root.resolve()
        if (
            not path.is_relative_to(allowed)
            or not path.is_file()
            or path.is_symlink()
            or sha256_file(path) != value["checksum"]
        ):
            raise BackupError("The backup is missing or failed its integrity check.")
        return path

    def plaintext(self, value, path):
        source = self.artifact_path(value)
        if value.get("encrypted"):
            self.keys.decrypt(source, path)
        else:
            shutil.copyfile(source, path)
        return Path(path)

    def store(self, path, folder, encrypted):
        path = Path(path)
        destination = folder / (path.name + (".enc" if encrypted else ""))
        if encrypted:
            self.keys.encrypt(path, destination)
        else:
            shutil.copyfile(path, destination)
        return {
            "path": str(destination.relative_to(self.root)),
            "name": path.name,
            "encrypted": encrypted,
            "size": destination.stat().st_size,
            "checksum": sha256_file(destination),
            "cloud_status": "Not uploaded",
        }

    def capture(
        self,
        value,
        actor,
        stage=lambda message: None,
        *,
        already_locked=False,
        protect=False
    ):
        options = BackupRequest.model_validate(value)
        estimate = self.estimate()
        if shutil.disk_usage(self.root).free < estimate * 3 + 64 * 1024 * 1024:
            raise BackupError("Not enough local storage to create this recovery set.")
        if (
            options.format != "zip"
            and shutil.disk_usage(self.sql_directory()).free
            < estimate + 64 * 1024 * 1024
        ):
            raise BackupError("Not enough space in the SQL backup folder.")
        identifier = uuid4().hex
        folder = self.root / "sets" / identifier
        folder.mkdir(mode=0o700)
        record = {
            "id": identifier,
            "created_at": now(),
            "actor": str(actor),
            "format": options.format,
            "destination": options.destination,
            "encrypted": options.encrypted,
            "protected": protect,
            "status": "Creating",
            "file_validated": False,
            "artifacts": {},
            "cloud_status": (
                "Queued" if options.destination == "local_drive" else "Not uploaded"
            ),
        }
        self.catalog.put("backup", identifier, record)
        native_path = None
        try:
            with tempfile.TemporaryDirectory(dir=self.root / "tmp") as temporary:
                temp = Path(temporary)
                record["temporary_directory"] = str(temp)
                self.catalog.put("backup", identifier, record)
                native_error = None

                def snapshot(payload):
                    nonlocal native_error, native_path
                    payload["created_at"] = now()
                    record["created_at"] = payload["created_at"]
                    stage("Creating ZIP and checking evidence photos")
                    write_recovery_package(
                        payload,
                        temp / "database.json",
                        temp / (identifier + ".recovery.zip"),
                    )
                    if options.format != "zip":
                        try:
                            stage("Creating native SQL Server BAK")
                            info = self.native.probe()
                            native_path = self.sql_directory() / (
                                "Joross_" + identifier + ".bak"
                            )
                            self.native.backup(native_path)
                            native_assets(
                                temp / (identifier + ".recovery.zip"),
                                native_path,
                                temp / (identifier + ".photos.zip"),
                                identifier,
                                info,
                            )
                            shutil.copyfile(native_path, temp / (identifier + ".bak"))
                        except Exception as error:
                            native_error = (
                                str(error)
                                if isinstance(error, BackupError)
                                else "Native BAK failed. Check SQL Server permissions and shared folder access."
                            )

                if already_locked:
                    payload, count, rows = _snapshot_database(
                        on_snapshot=snapshot, source_engine=self.engine
                    )
                else:
                    write_runtime(
                        maintenance={
                            "operation": "backup",
                            "message": "Capturing consistent farm records and photos",
                        }
                    )
                    try:
                        with farm_access(exclusive=True, timeout=60):
                            payload, count, rows = _snapshot_database(
                                on_snapshot=snapshot, source_engine=self.engine
                            )
                    finally:
                        write_runtime(maintenance=None)
                if options.format in ("zip", "both") or native_error:
                    record["artifacts"]["zip"] = self.store(
                        temp / (identifier + ".recovery.zip"), folder, options.encrypted
                    )
                if options.format != "zip" and not native_error:
                    for kind, suffix in [("bak", ".bak"), ("assets", ".photos.zip")]:
                        record["artifacts"][kind] = self.store(
                            temp / (identifier + suffix), folder, options.encrypted
                        )
                stage("Saving matching application recovery kit")
                write_kit(temp / (identifier + ".kit.zip"), identifier)
                record["artifacts"]["kit"] = self.store(
                    temp / (identifier + ".kit.zip"), folder, False
                )
                record.update(
                    status="Partial" if native_error else "Completed",
                    file_validated=True,
                    error=native_error,
                    row_count=rows,
                    table_count=count,
                    photo_count=len(payload["recovery"]["evidence_files"]),
                )
                self.catalog.put("backup", identifier, record)
        except Exception as error:
            record.update(
                status="Failed",
                error=(
                    str(error)
                    if isinstance(error, BackupError)
                    else "Backup failed. Check storage, database access and evidence files."
                ),
            )
            self.catalog.put("backup", identifier, record)
            raise
        finally:
            if native_path:
                native_path.unlink(missing_ok=True)
        self.catalog.event(
            actor, "backup_created", record["status"], backup_id=identifier
        )
        if options.destination == "local_drive":
            self.catalog.enqueue(
                "upload", {"backup_id": identifier}, actor, "upload:" + identifier
            )
        return record

    def import_legacy(self):
        from app.models import SystemBackup
        from app.services.backup_service import BACKUP_FOLDER

        try:
            with Session(self.engine) as db:
                for value in db.scalars(select(SystemBackup)).all():
                    identifier = "legacy-" + str(value.id)
                    if (
                        self.catalog.get("backup", identifier)
                        or value.status != "Completed"
                    ):
                        continue
                    original = Path(value.storage_path).resolve()
                    if not original.is_relative_to(BACKUP_FOLDER.resolve()):
                        continue
                    path = original.with_suffix(".recovery.zip")
                    validated = False
                    photos = None
                    try:
                        payload = inspect_recovery_package(path)
                        validated = True
                        photos = len(payload["recovery"]["evidence_files"])
                    except Exception:
                        path = original
                    if not path.is_file() or path.is_symlink():
                        continue
                    kind = "zip" if validated else "json"
                    self.catalog.put(
                        "backup",
                        identifier,
                        {
                            "id": identifier,
                            "created_at": value.created_at.replace(
                                tzinfo=timezone.utc
                            ).isoformat(),
                            "actor": "Existing backup",
                            "status": "Completed",
                            "format": kind,
                            "encrypted": False,
                            "protected": True,
                            "legacy": True,
                            "file_validated": validated,
                            "photo_count": photos,
                            "artifacts": {
                                kind: {
                                    "legacy_path": str(path),
                                    "name": path.name,
                                    "size": path.stat().st_size,
                                    "checksum": sha256_file(path),
                                    "encrypted": False,
                                }
                            },
                        },
                    )
        except Exception:
            return  # Legacy files are read-only; a missing farm DB must not block server recovery.

    def upload_set(self, identifier, stage):
        value = self.catalog.get("backup", identifier)
        if not value or value["status"] not in ("Completed", "Partial"):
            raise BackupError("Choose an available recovery set.")
        drive = Drive(self.catalog, self.keys)
        try:
            stage("Checking Google Drive connection and free space")
            quota = drive.quota()
            needed = sum(
                v["size"]
                for v in value["artifacts"].values()
                if v.get("cloud_status") != "Completed"
            )
            if (
                quota.get("limit")
                and int(quota["limit"]) - int(quota.get("usage", 0)) < needed
            ):
                raise DriveError(
                    "Google Drive does not have enough free storage. Free Google account storage before retrying this cloud copy."
                )
            if not drive.connection().get("folder_id"):
                stage("Preparing Google Drive backup folder")
                drive.create_folder("Joross Farm Backups")
            for kind, artifact in value["artifacts"].items():
                if artifact.get("cloud_status") == "Completed":
                    continue
                stage("Uploading " + kind.upper())

                def persist(transfer):
                    artifact.update(
                        transfer=dict(transfer),
                        cloud_status=transfer.get("status", "Uploading"),
                    )
                    value["cloud_status"] = "Uploading"
                    self.catalog.put("backup", identifier, value)

                drive.upload(
                    self.artifact_path(artifact),
                    {
                        "backup_id": identifier,
                        "artifact": kind,
                        "sha256": artifact["checksum"],
                    },
                    artifact.get("transfer", {}),
                    persist,
                )
            value.update(cloud_status="Completed", uploaded_at=now())
            self.catalog.put("backup", identifier, value)
            self.catalog.event("System", "backup_uploaded", backup_id=identifier)
        except Exception:
            value["cloud_status"] = "Needs attention"
            self.catalog.put("backup", identifier, value)
            raise
        finally:
            drive.close()
        return {"backup_id": identifier}

    def protect(self, identifier, keep, actor):
        with HostLock("backup-worker", timeout=1):
            value = self.catalog.get("backup", identifier)
            if not value or value["status"] == "Deleted":
                raise BackupError("Backup not found.")
            value["protected"] = keep
            self.catalog.put("backup", identifier, value)
            self.catalog.event(
                actor, "backup_protection_changed", backup_id=identifier, keep=keep
            )
        return self.public_set(value)

    def delete_set(self, identifier, actor, automatic=False):
        value = self.catalog.get("backup", identifier)
        if not value:
            raise BackupError("Backup not found.")
        complete = sorted(
            [
                v
                for v in self.catalog.list("backup")
                if v["status"] == "Completed" and v.get("file_validated")
            ],
            key=lambda v: v["created_at"],
            reverse=True,
        )
        tested = sorted(
            [v for v in complete if v.get("restore_tested_at")],
            key=lambda v: v["restore_tested_at"],
            reverse=True,
        )
        if (
            value.get("protected")
            or value.get("legacy")
            or (complete and complete[0]["id"] == identifier)
            or (tested and tested[0]["id"] == identifier)
        ):
            raise BackupError(
                "Keep the newest verified and newest restore-tested backups. Unmark protected backups before deleting."
            )
        drive = Drive(self.catalog, self.keys)
        try:
            for artifact in value["artifacts"].values():
                remote = artifact.get("transfer", {})
                if remote.get("id") and not remote.get("deleted"):
                    if remote.get("subject") != drive.connection().get("subject"):
                        raise BackupError(
                            "Reconnect the Google account owning this backup."
                        )
                    response = drive.client.delete(
                        API + "/files/" + file_id(remote["id"]),
                        headers={"Authorization": "Bearer " + drive.token()},
                    )
                    if response.status_code not in (204, 404):
                        raise BackupError(
                            "Cloud deletion failed. The local backup was retained."
                        )
                    remote["deleted"] = True
                    self.catalog.put("backup", identifier, value)
            for artifact in value["artifacts"].values():
                path = (self.root / artifact["path"]).resolve()
                if not path.is_relative_to((self.root / "sets").resolve()):
                    raise BackupError("Invalid backup deletion path.")
                path.unlink(missing_ok=True)
            value["status"] = "Deleted"
            self.catalog.put("backup", identifier, value)
            self.catalog.event(
                actor, "backup_deleted", backup_id=identifier, automatic=automatic
            )
        finally:
            drive.close()

    def retain(self):
        options = self.options()
        if not options.retention_enabled:
            return
        complete = sorted(
            [
                v
                for v in self.catalog.list("backup")
                if v["status"] == "Completed" and v.get("file_validated")
            ],
            key=lambda v: v["created_at"],
            reverse=True,
        )
        if not complete or (
            complete[0].get("destination") == "local_drive"
            and complete[0].get("cloud_status") != "Completed"
        ):
            return
        for value in complete[options.retain_count :]:
            if value.get("protected") or value.get("legacy"):
                continue
            try:
                self.delete_set(value["id"], "System", automatic=True)
            except BackupError:
                self.catalog.event(
                    "System",
                    "retention_skipped",
                    "Needs attention",
                    backup_id=value["id"],
                )

    def import_candidate(self, primary, companion=None, *, key=None, backup_id=None):
        if (
            len(
                [
                    v
                    for v in self.catalog.list("candidate")
                    if v["status"] not in ("Activated", "Discarded")
                ]
            )
            >= 20
        ):
            raise BackupError(
                "Discard unused staged copies before importing another backup."
            )
        identifier = uuid4().hex
        folder = self.root / "incoming" / identifier
        folder.mkdir(mode=0o700)
        try:
            with tempfile.TemporaryDirectory(dir=self.root / "tmp") as temporary:
                temp = Path(temporary)
                first = temp / (identifier + (".bak" if companion else ".recovery.zip"))
                if encrypted_file(primary):
                    self.keys.decrypt(primary, first, key)
                else:
                    shutil.copyfile(primary, first)
                if companion:
                    second = temp / (identifier + ".photos.zip")
                    if encrypted_file(companion):
                        self.keys.decrypt(companion, second, key)
                    else:
                        shutil.copyfile(companion, second)
                    meta = inspect_assets(second, first)
                    kind = "bak"
                    if self.engine.dialect.name != "mssql":
                        raise BackupError("A BAK restore test requires SQL Server.")
                    shared = self.sql_directory() / (
                        "JorossValidate_" + identifier + ".bak"
                    )
                    try:
                        shutil.copyfile(first, shared)
                        self.native.verify(shared)
                    finally:
                        shared.unlink(missing_ok=True)
                else:
                    meta = metadata(inspect_recovery_package(first))
                    kind = "zip"
                if meta["revision"] != current_revision():
                    raise BackupError(
                        "Install the matching application version before restoring this backup."
                    )
                artifacts = {kind: self.store(first, folder, True)}
                if companion:
                    artifacts["assets"] = self.store(second, folder, True)
                value = {
                    "id": identifier,
                    "backup_id": backup_id,
                    "format": kind,
                    "created_at": now(),
                    "source_date": meta["created_at"],
                    "status": "Validated",
                    "file_validated": True,
                    "restore_tested": False,
                    "meta": meta,
                    "artifacts": artifacts,
                    "row_count": sum(
                        v["rows"] for v in meta["table_signatures"].values()
                    ),
                    "table_count": len(meta["table_signatures"]),
                    "photo_count": len(meta["evidence_files"]),
                }
                self.catalog.put("candidate", identifier, value)
                return self.public_candidate(value)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def candidate_from_set(self, identifier, kind):
        value = self.catalog.get("backup", identifier)
        if (
            not value
            or kind not in ("zip", "bak")
            or kind not in value["artifacts"]
            or value["status"] not in ("Completed", "Partial")
        ):
            raise BackupError("The selected backup format is unavailable.")
        with tempfile.TemporaryDirectory(dir=self.root / "tmp") as temporary:
            primary = self.plaintext(
                value["artifacts"][kind], Path(temporary) / "backup"
            )
            companion = None
            if kind == "bak":
                if "assets" not in value["artifacts"]:
                    raise BackupError("This BAK needs its matching photo package.")
                companion = self.plaintext(
                    value["artifacts"]["assets"], Path(temporary) / "photos.zip"
                )
            return self.import_candidate(primary, companion, backup_id=identifier)

    def candidate_from_drive(self, identifier, kind, key=None):
        drive = Drive(self.catalog, self.keys)
        try:
            selected = next(
                (v for v in drive.remote_sets() if v["id"] == identifier), None
            )
            if (
                not selected
                or kind not in ("zip", "bak")
                or kind not in selected["artifacts"]
            ):
                raise BackupError("Cloud backup format not found.")
            with tempfile.TemporaryDirectory(dir=self.root / "tmp") as temporary:
                primary = Path(temporary) / "backup"
                drive.download(
                    selected["artifacts"][kind],
                    primary,
                    settings.backup_max_upload_bytes,
                )
                companion = None
                if kind == "bak":
                    if "assets" not in selected["artifacts"]:
                        raise BackupError(
                            "The cloud BAK needs its matching photo package."
                        )
                    companion = Path(temporary) / "photos"
                    drive.download(
                        selected["artifacts"]["assets"],
                        companion,
                        settings.backup_max_upload_bytes,
                    )
                return self.import_candidate(primary, companion, key=key)
        finally:
            drive.close()

    def verify_target(self, target, evidence, expected):
        payload, _, _ = _snapshot_database(source_engine=target)
        if signatures(payload) != expected["table_signatures"]:
            raise BackupError(
                "Restored record checksums and counts do not match this backup."
            )
        for item in expected["evidence_files"]:
            path = Path(evidence) / _safe_file(item["name"])
            if (
                not path.is_file()
                or path.is_symlink()
                or path.stat().st_size != item["size"]
                or sha256_file(path) != item["sha256"]
            ):
                raise BackupError(
                    "A restored evidence photo or thumbnail is missing or changed."
                )
        with target.connect() as connection:
            if target.dialect.name == "sqlite":
                if (
                    connection.scalar(text("PRAGMA integrity_check")) != "ok"
                    or connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                ):
                    raise BackupError(
                        "Restored records failed integrity or relationship checks."
                    )
            elif connection.scalar(
                text(
                    "SELECT (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1)+(SELECT COUNT(*) FROM sys.check_constraints WHERE is_disabled=1 OR is_not_trusted=1)"
                )
            ):
                raise BackupError(
                    "Restored database has disabled or untrusted constraints."
                )
            from app.models import Crop, Livestock, User

            for table in (Crop.__table__, Livestock.__table__, User.__table__):
                connection.execute(select(table).limit(1)).first()
        with Session(target) as db:
            if not any(
                v.status == "Active"
                and v.role
                and v.role.is_active
                and "*" in v.permissions
                for v in db.scalars(select(User)).all()
            ):
                raise BackupError(
                    "The restored database has no active administrator account."
                )
        return payload

    def target_for(self, value):
        if self.engine.dialect.name == "mssql":
            return self.native.target_engine(value["target"])
        path = Path(value["target_file"]).resolve()
        if not value.get("rollback") and not path.is_relative_to(
            (self.root / "staging").resolve()
        ):
            raise BackupError("Invalid staged database path.")
        return create_engine("sqlite+pysqlite:///" + str(path), poolclass=NullPool)

    def test_candidate(self, identifier, stage):
        value = self.catalog.get("candidate", identifier)
        if not value or value["status"] != "Validated" or value.get("target"):
            raise BackupError("Choose a validated, unused staged copy.")
        folder = self.root / "staging" / identifier
        folder.mkdir(exist_ok=True)
        evidence = folder / "evidence"
        name = "JorossRecovery_" + uuid4().hex
        value.update(status="Testing", target=name, evidence=str(evidence))
        self.catalog.put("candidate", identifier, value)
        target = None
        try:
            with tempfile.TemporaryDirectory(dir=self.root / "tmp") as temporary:
                primary = self.plaintext(
                    value["artifacts"][value["format"]], Path(temporary) / "backup"
                )
                stage("Restoring a separate database and photo folder")
                if self.engine.dialect.name == "mssql":
                    target = self.native.target_engine(name)
                    if value["format"] == "zip":
                        self.native.create_empty(name)
                        restore_recovery_package(
                            primary, target, evidence, apply=True, initialize=True
                        )
                    else:
                        shared = self.sql_directory() / (name + ".bak")
                        try:
                            shutil.copyfile(primary, shared)
                            self.native.restore(
                                shared, name, value["meta"]["sql_version"]
                            )
                        finally:
                            shared.unlink(missing_ok=True)
                        companion = self.plaintext(
                            value["artifacts"]["assets"], Path(temporary) / "photos.zip"
                        )
                        inspect_assets(companion, primary, evidence)
                    self.native.check(name)
                else:
                    value["target_file"] = str(folder / (name + ".sqlite3"))
                    self.catalog.put("candidate", identifier, value)
                    target = self.target_for(value)
                    restore_recovery_package(
                        primary, target, evidence, apply=True, initialize=True
                    )
                stage(
                    "Checking every record, relationship, photo and administrator account"
                )
                self.verify_target(target, evidence, value["meta"])
                value.update(
                    status="Ready",
                    restore_tested=True,
                    tested_at=now(),
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(hours=24)
                    ).isoformat(),
                    error=None,
                )
                self.catalog.put("candidate", identifier, value)
                if value.get("backup_id"):
                    backup = self.catalog.get("backup", value["backup_id"])
                    backup.update(
                        restore_tested_at=value["tested_at"],
                        tested_formats=sorted(
                            set(backup.get("tested_formats", []) + [value["format"]])
                        ),
                    )
                    self.catalog.put("backup", backup["id"], backup)
                self.catalog.event(
                    "System",
                    "restore_test_passed",
                    candidate_id=identifier,
                    format=value["format"],
                )
                return self.public_candidate(value)
        except Exception as error:
            value.update(
                status="Test failed",
                restore_tested=False,
                error=(
                    str(error)
                    if isinstance(error, BackupError)
                    else "The staged restore failed. Live farm data was not replaced. Discard the staged copy before retrying."
                ),
            )
            self.catalog.put("candidate", identifier, value)
            raise
        finally:
            if target is not None:
                target.dispose()

    def check_actor(self, approval):
        if (
            not approval
            or approval.get("epoch") != runtime()["epoch"]
            or datetime.fromisoformat(approval["at"]) + timedelta(minutes=5)
            < datetime.now(timezone.utc)
        ):
            raise BackupError(
                "Restore approval expired. Verify your administrator credentials again."
            )
        from app.models import User

        with Session(self.engine) as db:
            value = db.get(User, approval["user_id"])
            if (
                not value
                or value.status != "Active"
                or int(value.auth_version or 0) != approval["auth_version"]
                or not value.role
                or not value.role.is_active
                or "*" not in value.permissions
            ):
                raise BackupError(
                    "The approving administrator is no longer authorized."
                )

    def safety_meta(self, identifier):
        value = self.catalog.get("backup", identifier)
        if not value or "zip" not in value["artifacts"]:
            raise BackupError("The activation safety backup is unavailable.")
        with tempfile.TemporaryDirectory(dir=self.root / "tmp") as temporary:
            return metadata(
                inspect_recovery_package(
                    self.plaintext(
                        value["artifacts"]["zip"], Path(temporary) / "safety.zip"
                    )
                )
            )

    def activate(
        self,
        identifier,
        stage,
        actor,
        *,
        approval=None,
        offline=False,
        skip_current_backup=False
    ):
        if not settings.backup_activation_enabled:
            raise BackupError(
                "Activation is disabled until this installation completes its recovery drill."
            )
        value = self.catalog.get("candidate", identifier)
        if not value or value["status"] != "Ready" or not value.get("restore_tested"):
            raise BackupError(
                "A successful staged restore is required before activation."
            )
        if datetime.fromisoformat(value["expires_at"]) <= datetime.now(timezone.utc):
            raise BackupError(
                "This staged restore test expired. Prepare and test a fresh copy."
            )
        if runtime().get("activation"):
            raise BackupError(
                "Repair the interrupted activation before starting another restore."
            )
        target = self.target_for(value)
        live = get_evidence_storage().root.resolve()
        staged = live.parent / (".joross-activate-" + uuid4().hex)
        previous = live.parent / (".joross-previous-" + uuid4().hex)
        previous_name = "JorossPrevious_" + uuid4().hex
        source_file = None
        old_file = None
        try:
            self.verify_target(target, value["evidence"], value["meta"])
            staged.mkdir(mode=0o700)
            for item in value["meta"]["evidence_files"]:
                shutil.copyfile(
                    Path(value["evidence"]) / item["name"], staged / item["name"]
                )
                if sha256_file(staged / item["name"]) != item["sha256"]:
                    raise BackupError("A staged photo changed before activation.")
            if self.engine.dialect.name == "sqlite":
                if self.engine.url.database in (None, ":memory:"):
                    raise BackupError("Activation requires a persistent database.")
                source_file = Path(self.engine.url.database).resolve()
                old_file = source_file.with_name(
                    source_file.name + ".previous-" + uuid4().hex
                )
            journal = {
                "candidate_id": identifier,
                "phase": "prepared",
                "source_database": self.native.database,
                "previous_database": previous_name,
                "source_file": str(source_file) if source_file else None,
                "previous_file": str(old_file) if old_file else None,
                "live_photos": str(live),
                "previous_photos": str(previous),
                "staged_photos": str(staged),
            }
            write_runtime(
                maintenance={
                    "operation": "activation",
                    "message": "Activating a verified recovery copy",
                }
            )
            try:
                with farm_access(exclusive=True, timeout=90):
                    if not offline:
                        self.check_actor(approval)
                    healthy = True
                    try:
                        with self.engine.connect() as connection:
                            connection.execute(text("SELECT 1"))
                    except Exception:
                        healthy = False
                    if healthy and skip_current_backup:
                        raise BackupError(
                            "A working database must have a safety backup."
                        )
                    if not healthy and not (offline and skip_current_backup):
                        raise BackupError(
                            "Use the protected local recovery tool when the working database is unavailable."
                        )
                    source_exists = (
                        self.native.exists(self.native.database)
                        if self.engine.dialect.name == "mssql"
                        else source_file.exists()
                    )
                    if healthy:
                        stage("Backing up the current farm before activation")
                        safety = self.capture(
                            {
                                "format": (
                                    "both"
                                    if self.engine.dialect.name == "mssql"
                                    else "zip"
                                ),
                                "encrypted": True,
                            },
                            actor,
                            stage,
                            already_locked=True,
                            protect=True,
                        )
                        if safety["status"] != "Completed":
                            raise BackupError(
                                "The safety backup failed. No live data was replaced."
                            )
                        journal["safety_backup_id"] = safety["id"]
                    from app.models import User

                    with target.begin() as connection:
                        connection.execute(
                            update(User).values(
                                auth_version=User.auth_version + 1,
                                active_session_auth_version=None,
                                active_session_expires_at=None,
                            )
                        )
                    expected = {
                        "table_signatures": signatures(
                            _snapshot_database(source_engine=target)[0]
                        ),
                        "evidence_files": value["meta"]["evidence_files"],
                    }
                    target.dispose()
                    self.engine.dispose()
                    write_runtime(activation=journal)
                    stage("Switching the verified database and photos")
                    try:
                        if self.engine.dialect.name == "mssql":
                            if source_exists:
                                self.native.rename(self.native.database, previous_name)
                            self.native.rename(value["target"], self.native.database)
                        else:
                            if source_exists:
                                os.replace(source_file, old_file)
                            os.replace(value["target_file"], source_file)
                        journal["phase"] = "database_switched"
                        write_runtime(activation=journal)
                        os.replace(live, previous)
                        os.replace(staged, live)
                        journal["phase"] = "photos_switched"
                        write_runtime(activation=journal)
                        self.engine.dispose()
                        self.verify_target(self.engine, live, expected)
                    except Exception:
                        if previous.exists():
                            if live.exists():
                                os.replace(
                                    live,
                                    self.root
                                    / "staging"
                                    / ("failed-photos-" + uuid4().hex),
                                )
                            os.replace(previous, live)
                        if self.engine.dialect.name == "mssql":
                            if self.native.exists(previous_name):
                                if self.native.exists(self.native.database):
                                    failed = (
                                        value["target"]
                                        if not self.native.exists(value["target"])
                                        else "JorossRecovery_failed_" + uuid4().hex
                                    )
                                    self.native.rename(self.native.database, failed)
                                    value["target"] = failed
                                self.native.rename(previous_name, self.native.database)
                        elif old_file and old_file.exists():
                            if source_file.exists():
                                os.replace(source_file, value["target_file"])
                            os.replace(old_file, source_file)
                        self.engine.dispose()
                        if not journal.get("safety_backup_id"):
                            raise BackupError(
                                "Automatic rollback could not be verified. Keep maintenance active and inspect the server recovery journal."
                            ) from None
                        self.verify_target(
                            self.engine,
                            live,
                            self.safety_meta(journal["safety_backup_id"]),
                        )
                        value.update(
                            status="Test failed",
                            restore_tested=False,
                            error="Activation failed; previous database and photos were reinstated. Prepare a fresh staged copy.",
                        )
                        self.catalog.put("candidate", identifier, value)
                        self.catalog.event(
                            actor,
                            "activation_reverted",
                            "Failed",
                            candidate_id=identifier,
                        )
                        write_runtime(
                            activation=None, maintenance=None, epoch=uuid4().hex
                        )
                        raise BackupError(
                            "Activation failed. The previous database and photos were reinstated."
                        ) from None
                    if source_exists:
                        rollback_id = uuid4().hex
                        self.catalog.put(
                            "rollback",
                            rollback_id,
                            {
                                "id": rollback_id,
                                "created_at": now(),
                                "status": "Available",
                                "target": previous_name,
                                "target_file": str(old_file) if old_file else None,
                                "evidence": str(previous),
                            },
                        )
                    if value.get("rollback_id"):
                        rotation = self.catalog.get("rollback", value["rollback_id"])
                        rotation["status"] = "Consumed"
                        self.catalog.put("rollback", rotation["id"], rotation)
                    value.update(status="Activated", activated_at=now())
                    self.catalog.put("candidate", identifier, value)
                    self.catalog.event(
                        actor, "restore_activated", candidate_id=identifier
                    )
                    write_runtime(activation=None, maintenance=None, epoch=uuid4().hex)
                    return {
                        "candidate_id": identifier,
                        "status": "Activated",
                        "sign_in_required": True,
                    }
            finally:
                if not runtime().get("activation"):
                    write_runtime(maintenance=None)
        finally:
            target.dispose()
            if staged.exists() and not runtime().get("activation"):
                shutil.rmtree(staged)

    def prepare_rollback(self, identifier):
        rotation = self.catalog.get("rollback", identifier)
        if not rotation or rotation["status"] != "Available":
            raise BackupError("The previous copy is unavailable.")
        value = {
            **rotation,
            "id": uuid4().hex,
            "rollback": True,
            "rollback_id": identifier,
            "format": "rollback",
        }
        target = self.target_for(value)
        try:
            payload, _, _ = _snapshot_database(source_engine=target)
            files = {}
            for row in payload["tables"].get("task_evidence", {}).get("rows", []):
                if str(row.get("status", "")).lower() == "deleted":
                    continue
                for column in ("storage_identifier", "thumbnail_storage_identifier"):
                    name = _safe_file(row.get(column))
                    path = Path(value["evidence"]) / name
                    if not path.is_file() or path.is_symlink():
                        raise BackupError("A retained photo is unavailable.")
                    digest = sha256_file(path)
                    if column == "storage_identifier" and digest != row.get("sha256"):
                        raise BackupError("A retained photo is damaged.")
                    files[name] = {
                        "name": name,
                        "size": path.stat().st_size,
                        "sha256": digest,
                    }
            meta = {
                "revision": payload["database"]["alembic_revision"],
                "table_signatures": signatures(payload),
                "evidence_files": list(files.values()),
            }
            if meta["revision"] != current_revision():
                raise BackupError(
                    "Use the application version matching the previous database."
                )
            self.verify_target(target, value["evidence"], meta)
            value.update(
                status="Ready",
                file_validated=True,
                restore_tested=True,
                tested_at=now(),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(hours=24)
                ).isoformat(),
                meta=meta,
                row_count=sum(v["rows"] for v in meta["table_signatures"].values()),
                table_count=len(meta["table_signatures"]),
                photo_count=len(files),
            )
            self.catalog.put("candidate", value["id"], value)
            return self.public_candidate(value)
        finally:
            target.dispose()

    def discard(self, identifier):
        value = self.catalog.get("candidate", identifier)
        if (
            not value
            or value["status"] == "Activated"
            or value.get("rollback")
            or runtime().get("activation")
        ):
            raise BackupError("Only unused staged copies may be discarded here.")
        if value.get("target") and self.engine.dialect.name == "mssql":
            self.native.drop_recovery(value["target"])
        for folder in (
            self.root / "incoming" / identifier,
            self.root / "staging" / identifier,
        ):
            if folder.exists():
                shutil.rmtree(folder)
        value.update(status="Discarded", restore_tested=False)
        self.catalog.put("candidate", identifier, value)
        return {"candidate_id": identifier, "status": "Discarded"}

    def schedule(self):
        options = self.options()
        scheduled = self.catalog.get("schedule", "next", {}).get("at")
        if not options.schedule_enabled:
            return
        if scheduled and datetime.fromisoformat(scheduled) <= datetime.now(
            timezone.utc
        ):
            self.catalog.enqueue(
                "backup",
                {
                    key: options.model_dump()[key]
                    for key in ("format", "destination", "encrypted")
                },
                "System schedule",
                "schedule:" + scheduled,
            )
        if not scheduled or datetime.fromisoformat(scheduled) <= datetime.now(
            timezone.utc
        ):
            self.catalog.put("schedule", "next", {"at": next_run(options)})

    def tick(self):
        try:
            lock = HostLock("backup-worker").acquire()
        except RecoveryBusy:
            return
        try:
            if runtime().get("activation"):
                return
            self.catalog.put("worker", "heartbeat", {"at": now()})
            for value in self.catalog.jobs():
                if value["status"] == "Running":
                    self.catalog.update_job(
                        value["id"],
                        status="Queued" if value["kind"] == "upload" else "Incomplete",
                        error="The server stopped during this job. Completed files were retained.",
                    )
                    if value["kind"] == "test":
                        candidate = self.catalog.get(
                            "candidate", value["payload"]["candidate_id"]
                        )
                        if candidate and candidate["status"] == "Testing":
                            candidate.update(
                                status="Test failed",
                                restore_tested=False,
                                error="The server stopped during this test. Discard the isolated copy and prepare a fresh test.",
                            )
                            self.catalog.put("candidate", candidate["id"], candidate)
            for value in self.catalog.list("backup"):
                if value["status"] == "Creating":
                    value.update(
                        status="Incomplete",
                        error="Capture was interrupted. Final files were retained for review.",
                    )
                    self.catalog.put("backup", value["id"], value)
                    temp = Path(value.get("temporary_directory", "")).resolve()
                    if temp.is_relative_to((self.root / "tmp").resolve()):
                        shutil.rmtree(temp, ignore_errors=True)
                    (self.sql_directory() / ("Joross_" + value["id"] + ".bak")).unlink(
                        missing_ok=True
                    )
            if runtime().get("maintenance"):
                write_runtime(maintenance=None)
            self.schedule()
            pending = [
                v
                for v in self.catalog.jobs()
                if v["status"] in ("Queued", "Retrying")
                and (
                    not v.get("next_attempt")
                    or datetime.fromisoformat(v["next_attempt"])
                    <= datetime.now(timezone.utc)
                )
            ]
            if not pending:
                return
            job = min(pending, key=lambda v: v["created_at"])
            attempts = job["attempts"] + 1
            self.catalog.update_job(
                job["id"], status="Running", attempts=attempts, error=None
            )

            def stage(message):
                self.catalog.update_job(job["id"], stage=message)

            try:
                payload = job["payload"]
                kind = job["kind"]
                if kind == "backup":
                    record = self.capture(payload, job["actor"], stage)
                    result = {"backup_id": record["id"]}
                    if record["status"] == "Partial":
                        self.catalog.update_job(
                            job["id"],
                            status="Partial",
                            result=result,
                            error=record["error"],
                        )
                        return
                elif kind == "upload":
                    result = self.upload_set(payload["backup_id"], stage)
                elif kind == "test":
                    result = self.test_candidate(payload["candidate_id"], stage)
                elif kind == "activate":
                    result = self.activate(
                        payload["candidate_id"],
                        stage,
                        job["actor"],
                        approval=payload["approval"],
                    )
                elif kind == "rollback":
                    result = self.prepare_rollback(payload["rollback_id"])
                elif kind == "discard":
                    result = self.discard(payload["candidate_id"])
                elif kind == "delete":
                    self.delete_set(payload["backup_id"], job["actor"])
                    result = {"backup_id": payload["backup_id"]}
                elif kind == "cloud_import":
                    result = self.candidate_from_drive(
                        payload["backup_id"],
                        payload["format"],
                        (
                            self.keys.unseal(payload["key"])
                            if payload.get("key")
                            else None
                        ),
                    )
                else:
                    raise BackupError("Unsupported recovery job.")
                self.catalog.update_job(
                    job["id"],
                    status="Completed",
                    stage="Completed",
                    result=result,
                    next_attempt=None,
                )
                try:
                    self.retain()
                except Exception:
                    self.catalog.event("System", "retention_failed", "Needs attention")
            except Exception as error:
                retry = (
                    job["kind"] == "upload"
                    and attempts < 5
                    and getattr(error, "retryable", True)
                )
                message = (
                    str(error)
                    if isinstance(error, (BackupError, RecoveryBusy))
                    else "The operation failed. Review storage, database permissions and the isolated recovery copy."
                )
                self.catalog.update_job(
                    job["id"],
                    status="Retrying" if retry else "Failed",
                    error=message,
                    next_attempt=(
                        (
                            datetime.now(timezone.utc)
                            + timedelta(seconds=min(3600, 30 * 2**attempts))
                        ).isoformat()
                        if retry
                        else None
                    ),
                )
                self.catalog.event(
                    job["actor"], job["kind"] + "_failed", "Failed", job_id=job["id"]
                )
        finally:
            lock.release()
