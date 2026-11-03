from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import has_permission, require_permission
from app.models import DataImportBatch, User
from app.routers.auth import get_current_user
from app.schemas.imports import (
    ImportBatchSummary,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportReviewRequest,
    ImportRollbackRequest,
    ImportRollbackResponse,
)
from app.services.import_service import (
    MAX_IMPORT_BYTES,
    batch_summary,
    build_error_csv,
    commit_batch,
    create_preview,
    field_catalog,
    get_batch_or_none,
    is_admin,
    list_history,
    preview_response,
    revalidate_preview,
    rollback_batch,
)


router = APIRouter(
    prefix="/api/v1/imports",
    dependencies=[Depends(require_permission("imports:preview"))],
    tags=["Smart Data Import"],
)

def require_import_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "imports:commit"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to preview or import farm data.",
        )
    return current_user



def require_import_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a System Administrator can perform this import action.",
        )
    return current_user



def _get_batch_or_404(db: Session, batch_id: int) -> DataImportBatch:
    batch = get_batch_or_none(db, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import batch not found.",
        )
    return batch


@router.get("/field-catalog")
def get_field_catalog(
    _: User = Depends(get_current_user),
):
    return field_catalog()


@router.post(
    "/preview",
    response_model=ImportPreviewResponse,
)
async def preview_import_file(
    file: UploadFile = File(...),
    force: bool = Form(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_import_editor),
):
    if force and not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a System Administrator can force-preview a previously imported file.",
        )

    # Read at most one byte beyond the allowed size so an oversized upload
    # cannot be loaded completely into process memory before validation.
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The selected import file is larger than the 15 MB import limit.",
        )

    try:
        return create_preview(
            db,
            filename=file.filename or "import_file",
            content=content,
            current_user=current_user,
            force=force,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/history",
    response_model=list[ImportBatchSummary],
)
def import_history(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return list_history(db, limit)


@router.get(
    "/{batch_id}",
    response_model=ImportPreviewResponse,
)
def get_import_batch_preview(
    batch_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    batch = _get_batch_or_404(db, batch_id)
    return preview_response(db, batch)


@router.post(
    "/{batch_id}/review",
    response_model=ImportPreviewResponse,
)
def review_import_mapping(
    batch_id: int,
    payload: ImportReviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_import_editor),
):
    batch = _get_batch_or_404(db, batch_id)
    try:
        return revalidate_preview(
            db,
            batch,
            [item.model_dump() for item in payload.sheets],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{batch_id}/commit",
    response_model=ImportCommitResponse,
)
def commit_import(
    batch_id: int,
    payload: ImportCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_import_editor),
):
    batch = _get_batch_or_404(db, batch_id)
    try:
        return commit_batch(
            db,
            batch,
            current_user=current_user,
            row_actions=payload.row_actions,
            force_exact_duplicate=payload.force_exact_duplicate,
        )
    except PermissionError as exc:
        detail = str(exc)
        code = status.HTTP_409_CONFLICT if "already imported" in detail.lower() else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=code, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/{batch_id}/errors.csv")
def download_import_errors(
    batch_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    batch = _get_batch_or_404(db, batch_id)
    content = build_error_csv(batch)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{batch.batch_code}_import-errors.csv"'
        },
    )


@router.post(
    "/{batch_id}/rollback",
    response_model=ImportRollbackResponse,
)
def rollback_import(
    batch_id: int,
    payload: ImportRollbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_import_admin),
):
    batch = _get_batch_or_404(db, batch_id)
    try:
        return rollback_batch(
            db,
            batch,
            current_user=current_user,
            force=payload.force,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
