from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import (
    date,
    datetime,
    time,
)
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    MetaData,
    Table,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.models import SystemBackup
from app.services.recovery_service import RecoveryError, write_recovery_package, inspect_recovery_package


BACKUP_FORMAT_VERSION = "1.0"
BACKUP_FOLDER = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "backups"
)

# Backup history is metadata about backups themselves. Excluding it prevents
# recursive backup files while the rest of the application database is saved.
EXCLUDED_TABLES = {
    "system_backups",
}


class BackupServiceError(RuntimeError):
    pass


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, datetime):
        return {
            "__type__": "datetime",
            "value": value.isoformat(),
        }

    if isinstance(value, date):
        return {
            "__type__": "date",
            "value": value.isoformat(),
        }

    if isinstance(value, time):
        return {
            "__type__": "time",
            "value": value.isoformat(),
        }

    if isinstance(value, Decimal):
        return {
            "__type__": "decimal",
            "value": str(value),
        }

    if isinstance(
        value,
        (bytes, bytearray, memoryview),
    ):
        raw = bytes(value)
        return {
            "__type__": "bytes",
            "value": base64.b64encode(raw).decode("ascii"),
        }

    if isinstance(value, (str, int, float, bool)):
        return value

    return {
        "__type__": "string",
        "value": str(value),
    }


def _backup_code() -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(4).upper()
    return f"BKP-{timestamp}-{suffix}"


def _get_alembic_revision(connection) -> str | None:
    try:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except Exception:
        return None


def _snapshot_database(on_snapshot=None) -> tuple[dict[str, Any], int, int]:
    metadata = MetaData()
    tables_payload: dict[str, Any] = {}
    total_rows = 0

    # Hold one consistent database view while its referenced photos are copied.
    snapshot_engine = engine.execution_options(isolation_level="SERIALIZABLE")
    with snapshot_engine.begin() as connection:
        inspector = inspect(connection)
        table_names = sorted(
            table_name
            for table_name in inspector.get_table_names()
            if table_name not in EXCLUDED_TABLES
        )

        for table_name in table_names:
            table = Table(
                table_name,
                metadata,
                autoload_with=connection,
            )

            rows = connection.execute(
                select(table)
            ).mappings().all()

            serialized_rows = [
                {
                    str(key): _serialize_value(value)
                    for key, value in row.items()
                }
                for row in rows
            ]

            tables_payload[table_name] = {
                "columns": [
                    column.name
                    for column in table.columns
                ],
                "row_count": len(serialized_rows),
                "rows": serialized_rows,
            }

            total_rows += len(serialized_rows)

        payload = {
            "backup_type": "Joross Farm Database Logical Backup",
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": datetime.now().isoformat(),
            "database": {
                "name": settings.db_name,
                "server": settings.db_server,
                "alembic_revision": _get_alembic_revision(connection),
            },
            "table_count": len(tables_payload),
            "row_count": total_rows,
            "tables": tables_payload,
        }

        if engine.dialect.name == "sqlite" and engine.url.database not in (None, ":memory:"):
            payload["database"]["sqlite_source_path"] = str(Path(engine.url.database).resolve())
        if on_snapshot:
            on_snapshot(payload)
    return payload, len(tables_payload), total_rows


def create_database_backup(
    db: Session,
    *,
    created_by_user_id: int | None,
) -> SystemBackup:
    BACKUP_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    code = _backup_code()
    filename = f"{code}.json"
    final_path = BACKUP_FOLDER / filename
    temporary_path = BACKUP_FOLDER / f".{filename}.tmp"
    recovery_path = final_path.with_suffix(".recovery.zip")
    temporary_recovery = recovery_path.with_suffix(".zip.tmp")

    record = SystemBackup(
        backup_code=code,
        filename=filename,
        storage_path=str(final_path),
        format_version=BACKUP_FORMAT_VERSION,
        status="Creating",
        created_by_user_id=created_by_user_id,
        notes=(
            "Server-side logical snapshot of the Joross Farm SQL Server "
            "application tables."
        ),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        def save_snapshot(payload):
            write_recovery_package(payload, temporary_path, temporary_recovery)
            temporary_path.replace(final_path)
            temporary_recovery.replace(recovery_path)

        payload, table_count, row_count = _snapshot_database(on_snapshot=save_snapshot)

        raw = final_path.read_bytes()

        record.status = "Completed"
        record.file_size_bytes = len(raw)
        record.table_count = table_count
        record.row_count = row_count
        record.checksum_sha256 = hashlib.sha256(raw).hexdigest()
        record.completed_at = datetime.now()
        record.notes = (
            f"Completed logical database snapshot containing "
            f"{table_count} table(s), {row_count} row(s), and {len(payload['recovery']['evidence_files'])} evidence file(s)."
        )

        db.commit()
        db.refresh(record)
        return record

    except Exception as error:
        # A failed commit leaves a SQLAlchemy session unusable until rollback.
        # Roll back first, then remove both temporary and final files so a
        # failed metadata commit cannot leave an orphaned backup on disk.
        db.rollback()

        for candidate in (temporary_path, final_path, temporary_recovery, recovery_path):
            try:
                if candidate.exists():
                    candidate.unlink()
            except OSError:
                pass

        message = str(error) if isinstance(error, RecoveryError) else 'Backup could not be completed. Check database access and evidence storage.'
        try:
            failed_record = db.get(SystemBackup, record.id)
            if failed_record is not None:
                failed_record.status = "Failed"
                failed_record.notes = f"Backup failed: {message[:800]}"
                failed_record.completed_at = datetime.now()
                db.commit()
        except Exception:
            db.rollback()

        raise BackupServiceError(
            f"Database backup failed: {message}"
        ) from error


def get_backup_content(record: SystemBackup) -> dict[str, Any]:
    if record.status != "Completed":
        raise BackupServiceError(
            "Only completed backups can be downloaded."
        )

    backup_folder = BACKUP_FOLDER.resolve()
    file_path = Path(record.storage_path).resolve()

    try:
        file_path.relative_to(backup_folder)
    except ValueError as error:
        raise BackupServiceError(
            "The stored backup path is invalid."
        ) from error

    if not file_path.exists():
        raise BackupServiceError(
            "The backup file no longer exists on the server."
        )

    try:
        raw = file_path.read_bytes()
        if record.checksum_sha256:
            actual_checksum = hashlib.sha256(raw).hexdigest()
            if not secrets.compare_digest(actual_checksum, record.checksum_sha256):
                raise BackupServiceError(
                    "The backup file failed its integrity check and will not be served."
                )
        content = json.loads(raw.decode("utf-8"))
    except BackupServiceError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupServiceError(
            "The backup file could not be read."
        ) from error

    if not isinstance(content, dict):
        raise BackupServiceError(
            "The backup file has an invalid format."
        )

    return content


def recovery_package_available(record: SystemBackup) -> bool:
    path = Path(record.storage_path).resolve().with_suffix(".recovery.zip")
    return record.status == "Completed" and path.is_relative_to(BACKUP_FOLDER.resolve()) and path.is_file()


def get_recovery_package(record: SystemBackup) -> Path:
    get_backup_content(record)  # Preserve authorization-independent path/checksum checks.
    if not recovery_package_available(record):
        raise BackupServiceError("This backup has no recovery package. Create a new backup to include task photos.")
    path = Path(record.storage_path).resolve().with_suffix(".recovery.zip")
    try:
        inspect_recovery_package(path, expected_database_sha256=record.checksum_sha256)
    except ValueError as error:
        raise BackupServiceError(str(error)) from error
    return path
