from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import (
    MetaData,
    Table,
    case,
    func,
    inspect,
    select,
)
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse

from app.core.database import get_db
from app.core.recovery_runtime import HostLock, RecoveryBusy
from app.core.dependencies import has_permission
from app.models import (
    SystemBackup,
    User,
)
from app.routers.auth import get_current_user
from app.schemas.backups import BackupResponse
from app.services.backup_service import (
    BackupServiceError,
    create_database_backup,
    get_backup_content,
    get_recovery_package,
    recovery_package_available,
)


router = APIRouter(
    prefix="/api/v1/backups",
    tags=["Backups"],
)


IMPORT_BATCH_TABLE = "data_import_batches"
IMPORT_ROW_TABLE = "data_import_rows"


def require_backup_administrator(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "System Administrator permission is required to access "
                "database backups and import history."
            ),
        )

    return current_user


def get_backup_or_404(
    backup_id: int,
    db: Session,
) -> SystemBackup:
    record = db.get(
        SystemBackup,
        backup_id,
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup record not found.",
        )

    return record


def _first_value(
    record: dict[str, Any],
    *names: str,
    default: Any = None,
) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and value != "":
            return value
    return default


def _as_number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return str(value)


def _json_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_value(value)
        for key, value in record.items()
    }


def _get_import_tables(db: Session) -> tuple[Table, Table | None]:
    bind = db.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table(IMPORT_BATCH_TABLE):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Smart Import history is not available because the "
                "data_import_batches table does not exist."
            ),
        )

    metadata = MetaData()
    batch_table = Table(
        IMPORT_BATCH_TABLE,
        metadata,
        autoload_with=bind,
    )

    row_table = None
    if inspector.has_table(IMPORT_ROW_TABLE):
        row_table = Table(
            IMPORT_ROW_TABLE,
            metadata,
            autoload_with=bind,
        )

    return batch_table, row_table


def _find_batch_fk_column(row_table: Table | None):
    if row_table is None:
        return None

    for foreign_key in row_table.foreign_keys:
        try:
            if foreign_key.column.table.name == IMPORT_BATCH_TABLE:
                return foreign_key.parent
        except Exception:
            continue

    for name in (
        "batch_id",
        "import_batch_id",
        "data_import_batch_id",
    ):
        if name in row_table.c:
            return row_table.c[name]

    return None


def _row_status_column(row_table: Table | None):
    if row_table is None:
        return None

    for name in (
        "status",
        "row_status",
        "result",
        "action",
    ):
        if name in row_table.c:
            return row_table.c[name]

    return None


def _summarize_rows(
    db: Session,
    row_table: Table | None,
    batch_fk,
    batch_id: int,
) -> dict[str, int]:
    if row_table is None or batch_fk is None:
        return {
            "total": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
        }

    total = db.scalar(
        select(func.count())
        .select_from(row_table)
        .where(batch_fk == batch_id)
    ) or 0

    summary = {
        "total": int(total),
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }

    status_column = _row_status_column(row_table)
    if status_column is None:
        return summary

    grouped = db.execute(
        select(
            status_column,
            func.count(),
        )
        .where(batch_fk == batch_id)
        .group_by(status_column)
    ).all()

    for raw_status, count in grouped:
        normalized = str(raw_status or "").strip().lower()
        count = int(count or 0)

        if normalized in {
            "success",
            "successful",
            "valid",
            "committed",
            "imported",
            "inserted",
            "updated",
            "created",
        }:
            summary["success"] += count
        elif normalized in {
            "skip",
            "skipped",
            "duplicate",
            "ignored",
        }:
            summary["skipped"] += count
        elif normalized in {
            "failed",
            "failure",
            "invalid",
            "error",
            "rejected",
        }:
            summary["failed"] += count

    return summary


def _normalize_import_batch(
    record: dict[str, Any],
    row_summary: dict[str, int] | None = None,
) -> dict[str, Any]:
    row_summary = row_summary or {
        "total": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }

    total_rows = _as_number(
        _first_value(
            record,
            "total_rows",
            "row_count",
            "total_count",
            default=0,
        )
    ) or row_summary["total"]

    success_rows = _as_number(
        _first_value(
            record,
            "successful_rows",
            "success_rows",
            "imported_rows",
            "committed_rows",
            "success_count",
            default=0,
        )
    ) or row_summary["success"]

    skipped_rows = _as_number(
        _first_value(
            record,
            "skipped_rows",
            "duplicate_rows",
            "skipped_count",
            default=0,
        )
    ) or row_summary["skipped"]

    failed_rows = _as_number(
        _first_value(
            record,
            "failed_rows",
            "invalid_rows",
            "error_rows",
            "failure_count",
            "error_count",
            default=0,
        )
    ) or row_summary["failed"]

    return {
        "id": _as_number(record.get("id")),
        "fileName": _first_value(
            record,
            "original_filename",
            "file_name",
            "filename",
            "source_filename",
            default="",
        ),
        "module": _first_value(
            record,
            "module",
            "module_name",
            "import_type",
            "target_module",
            "entity_type",
            default="General",
        ),
        "status": _first_value(
            record,
            "status",
            "import_status",
            "state",
            default="Unknown",
        ),
        "totalRows": total_rows,
        "successRows": success_rows,
        "skippedRows": skipped_rows,
        "failedRows": failed_rows,
        "checksum": _first_value(
            record,
            "checksum_sha256",
            "checksum",
            "file_hash",
            "content_hash",
            default=None,
        ),
        "createdByUserId": _first_value(
            record,
            "created_by_user_id",
            "imported_by_user_id",
            default=None,
        ),
        "createdAt": _json_value(
            _first_value(
                record,
                "created_at",
                "uploaded_at",
                "imported_at",
                "started_at",
                default=None,
            )
        ),
        "completedAt": _json_value(
            _first_value(
                record,
                "completed_at",
                "committed_at",
                "finished_at",
                "updated_at",
                default=None,
            )
        ),
    }


def _normalize_import_row(
    record: dict[str, Any],
    fallback_number: int,
) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "rowNumber": _first_value(
            record,
            "row_number",
            "source_row_number",
            "excel_row",
            "row_index",
            default=fallback_number,
        ),
        "status": _first_value(
            record,
            "status",
            "row_status",
            "result",
            "action",
            default="Unknown",
        ),
        "targetType": _first_value(
            record,
            "target_type",
            "module",
            "entity_type",
            default="",
        ),
        "recordName": _first_value(
            record,
            "record_name",
            "entity_name",
            "target_name",
            "item_name",
            "crop_name",
            default="",
        ),
        "message": _first_value(
            record,
            "message",
            "error_message",
            "validation_message",
            "reason",
            "notes",
            default="",
        ),
    }


@router.get(
    "",
    response_model=list[BackupResponse],
)
def list_backups(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_backup_administrator),
):
    return [_backup_response(record) for record in list(
        db.scalars(
            select(SystemBackup)
            .order_by(SystemBackup.id.desc())
            .limit(limit)
        ).all()
    )]


def _backup_response(record):
    response = BackupResponse.model_validate(record).model_dump()
    response["recovery_available"] = recovery_package_available(record)
    if response["recovery_available"]:
        from pathlib import Path
        response["recovery_file_size_bytes"] = Path(record.storage_path).with_suffix(".recovery.zip").stat().st_size
    return response


@router.post(
    "",
    response_model=BackupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_backup_administrator),
):
    try:
        with HostLock("backup-worker"):
            return _backup_response(create_database_backup(
                db,
                created_by_user_id=current_user.id,
            ))
    except RecoveryBusy as error:
        raise HTTPException(409, str(error)) from None
    except BackupServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error


@router.get("/import-history")
def list_import_history(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_backup_administrator),
):
    batch_table, row_table = _get_import_tables(db)
    batch_fk = _find_batch_fk_column(row_table)

    if "id" in batch_table.c:
        order_column = batch_table.c.id
    elif "created_at" in batch_table.c:
        order_column = batch_table.c.created_at
    else:
        order_column = list(batch_table.c)[0]

    records = db.execute(
        select(batch_table)
        .order_by(order_column.desc())
        .limit(limit)
    ).mappings().all()

    normalized = []
    for raw_record in records:
        record = dict(raw_record)
        batch_id = _as_number(record.get("id"))
        summary = _summarize_rows(
            db,
            row_table,
            batch_fk,
            batch_id,
        ) if batch_id else None
        normalized.append(
            _normalize_import_batch(record, summary)
        )

    return normalized


@router.get("/import-history/{batch_id}")
def get_import_history_details(
    batch_id: int,
    result_filter: str = Query(default="all"),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_backup_administrator),
):
    batch_table, row_table = _get_import_tables(db)

    if "id" not in batch_table.c:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Smart Import batches do not expose an id column.",
        )

    normalized_filter = str(result_filter or "all").strip().lower()
    if normalized_filter not in {"all", "failed", "skipped", "imported"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="result_filter must be one of: all, failed, skipped, imported.",
        )

    raw_batch = db.execute(
        select(batch_table)
        .where(batch_table.c.id == batch_id)
    ).mappings().first()

    if raw_batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Smart Import batch not found.",
        )

    batch_fk = _find_batch_fk_column(row_table)
    summary = _summarize_rows(
        db,
        row_table,
        batch_fk,
        batch_id,
    )

    rows: list[dict[str, Any]] = []
    total_row_count = summary["total"]
    filtered_row_count = total_row_count
    rows_truncated = False

    if row_table is not None and batch_fk is not None:
        success_statuses = (
            "success", "successful", "valid", "committed", "imported",
            "inserted", "updated", "created",
        )
        skipped_statuses = ("skip", "skipped", "duplicate", "ignored")
        failed_statuses = (
            "failed", "failure", "invalid", "error", "rejected",
        )

        statement = select(row_table).where(batch_fk == batch_id)
        status_column = _row_status_column(row_table)
        status_value = func.lower(status_column) if status_column is not None else None

        selected_statuses = None
        if normalized_filter == "failed":
            selected_statuses = failed_statuses
        elif normalized_filter == "skipped":
            selected_statuses = skipped_statuses
        elif normalized_filter == "imported":
            selected_statuses = success_statuses

        if selected_statuses is not None and status_value is not None:
            statement = statement.where(status_value.in_(selected_statuses))
            filtered_row_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(row_table)
                    .where(
                        batch_fk == batch_id,
                        status_value.in_(selected_statuses),
                    )
                )
                or 0
            )
        elif selected_statuses is not None:
            filtered_row_count = 0
            statement = statement.where(False)

        # In the All view, surface actionable rows first so failed/skipped
        # records can never be buried behind hundreds of successful rows.
        if status_value is not None:
            statement = statement.order_by(
                case(
                    (status_value.in_(failed_statuses), 0),
                    (status_value.in_(skipped_statuses), 1),
                    (status_value.in_(success_statuses), 2),
                    else_=3,
                ).asc()
            )
        if "id" in row_table.c:
            statement = statement.order_by(row_table.c.id.asc())

        raw_rows = db.execute(
            statement.offset(offset).limit(limit + 1)
        ).mappings().all()

        rows_truncated = len(raw_rows) > limit or (offset + min(len(raw_rows), limit)) < filtered_row_count
        visible_rows = raw_rows[:limit]

        rows = [
            _normalize_import_row(
                dict(record),
                offset + index + 1,
            )
            for index, record in enumerate(visible_rows)
        ]

    return {
        "batch": _normalize_import_batch(
            dict(raw_batch),
            summary,
        ),
        "rows": rows,
        "rowCount": total_row_count,
        "filteredRowCount": filtered_row_count,
        "resultFilter": normalized_filter,
        "rowsTruncated": rows_truncated,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{backup_id}/recovery-package")
def download_recovery_package(backup_id: int, db: Session = Depends(get_db),
                              _: User = Depends(require_backup_administrator)):
    record = get_backup_or_404(backup_id, db)
    try:
        path = get_recovery_package(record)
        return FileResponse(path, media_type="application/zip", filename=f"{record.backup_code}.recovery.zip",
                            headers={"Cache-Control": "private, no-store"})
    except BackupServiceError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/{backup_id}/content")
def download_backup_content(
    backup_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_backup_administrator),
):
    record = get_backup_or_404(
        backup_id,
        db,
    )

    try:
        return get_backup_content(record)
    except BackupServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
