from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.farm_time import farm_today
from app.core.dependencies import has_permission
from app.models import ResourceUsage, User
from app.routers.auth import get_current_user
from app.schemas.resource_usage import (
    ResourceUsageCreate,
    ResourceUsageResponse,
    ResourceUsageSummaryResponse,
    ResourceUsageUpdate,
)
from app.services.void_authorization import require_void_administrator
from app.services.task_engine import evaluate_automatic_tasks
from app.services.csv_safety import SafeCsvWriter
from app.services.idempotency import begin_creation_command, record_creation_command, request_fingerprint
from app.services.resource_usage_service import (
    build_summary,
    create_usage,
    serialize_usage,
    update_usage,
    void_usage,
)


router = APIRouter(prefix="/api/v1/resource-usages", tags=["Resource Usage"])


def _allowed_view_modules(user: User) -> set[str]:
    if has_permission(user, "*"):
        return {"Crop", "Livestock"}

    modules: set[str] = set()
    if has_permission(user, "crops:view"):
        modules.add("Crop")
    if has_permission(user, "livestock:view"):
        modules.add("Livestock")
    if not modules:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Crop or livestock view permission is required to view resource usage.",
        )
    return modules


def _require_module_permission(user: User, module: str) -> None:
    permission = "crops:update" if module == "Crop" else "livestock:update"
    if not has_permission(user, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {permission}.",
        )


def _get_usage_or_404(db: Session, usage_id: int) -> ResourceUsage:
    usage = db.get(ResourceUsage, usage_id)
    if usage is None:
        raise HTTPException(status_code=404, detail="Resource usage record not found.")
    return usage


@router.get("", response_model=list[ResourceUsageResponse])
def list_resource_usages(
    module: str | None = Query(default=None),
    target_id: int | None = Query(default=None, gt=0),
    inventory_item_id: int | None = Query(default=None, gt=0),
    include_voided: bool = Query(default=False),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_modules = _allowed_view_modules(current_user)
    statement = select(ResourceUsage).where(
        ResourceUsage.module.in_(sorted(allowed_modules))
    ).order_by(
        ResourceUsage.usage_date.desc(), ResourceUsage.id.desc()
    )

    if module:
        if module not in {"Crop", "Livestock"}:
            raise HTTPException(status_code=400, detail="Invalid resource usage module.")
        if module not in allowed_modules:
            raise HTTPException(status_code=403, detail=f"You do not have permission to view {module.lower()} resource usage.")
        statement = statement.where(ResourceUsage.module == module)
        if target_id:
            if module == "Crop":
                statement = statement.where(ResourceUsage.crop_id == target_id)
            elif module == "Livestock":
                statement = statement.where(ResourceUsage.livestock_id == target_id)
    if inventory_item_id:
        statement = statement.where(ResourceUsage.inventory_item_id == inventory_item_id)
    if not include_voided:
        statement = statement.where(ResourceUsage.is_voided == False)
    if start_date:
        statement = statement.where(ResourceUsage.usage_date >= start_date)
    if end_date:
        statement = statement.where(ResourceUsage.usage_date <= end_date)

    return [serialize_usage(db, usage) for usage in db.scalars(statement).all()]


@router.post("", response_model=ResourceUsageResponse, status_code=status.HTTP_201_CREATED)
def add_resource_usage(
    payload: ResourceUsageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _require_module_permission(current_user, payload.module)
    try:
        fingerprint = request_fingerprint(payload)
        existing = begin_creation_command(db, idempotency_key=idempotency_key, command_type="manual-resource-usage",
                                          request_hash=fingerprint, user_id=current_user.id)
        if existing is not None:
            return serialize_usage(db, _get_usage_or_404(db, existing.target_id))
        usage = create_usage(
            db,
            module=payload.module,
            target_id=payload.target_id,
            inventory_item_id=payload.inventory_item_id,
            usage_type=payload.usage_type,
            quantity=float(payload.quantity),
            usage_date=payload.usage_date,
            notes=payload.notes,
            current_user=current_user,
        )
        db.flush()
        record_creation_command(db, idempotency_key=idempotency_key, command_type="manual-resource-usage",
                                request_hash=fingerprint, target_id=usage.id, user_id=current_user.id)
        evaluate_automatic_tasks(db, commit=False)
        db.commit()
        db.refresh(usage)
        return serialize_usage(db, usage)
    except Exception:
        db.rollback()
        raise


@router.get("/analytics/summary", response_model=ResourceUsageSummaryResponse)
def get_resource_usage_summary(
    days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    end_date = farm_today()
    start_date = end_date - timedelta(days=days - 1)
    return build_summary(
        db,
        start_date,
        end_date,
        allowed_modules=_allowed_view_modules(current_user),
    )


@router.get("/export/csv")
def export_resource_usage_csv(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    end = end_date or farm_today()
    start = start_date or (end - timedelta(days=29))
    allowed_modules = _allowed_view_modules(current_user)
    statement = (
        select(ResourceUsage)
        .where(
            ResourceUsage.is_voided == False,
            ResourceUsage.module.in_(sorted(allowed_modules)),
            ResourceUsage.usage_date >= start,
            ResourceUsage.usage_date <= end,
        )
        .order_by(ResourceUsage.usage_date.asc(), ResourceUsage.id.asc())
    )
    rows = [serialize_usage(db, usage) for usage in db.scalars(statement).all()]

    stream = io.StringIO()
    writer = SafeCsvWriter(csv.writer(stream))
    writer.writerow([
        "Date", "Module", "Record", "Usage Type", "Item Code", "Item",
        "Batch/Lot", "Quantity", "Unit", "Usage per Area/Animal", "Notes"
    ])
    for row in rows:
        efficiency = ""
        if row.get("efficiency_value") is not None:
            efficiency = f"{row['efficiency_value']} {row.get('efficiency_label') or ''}".strip()
        writer.writerow([
            row["usage_date"].isoformat(), row["module"], row["target_name"],
            row["usage_type"], row["inventory_item_code"], row["inventory_item_name"],
            row.get("batch_number") or "", row["quantity"], row["unit"],
            efficiency, row.get("notes") or ""
        ])

    filename = f"joross-resource-usage-{start.isoformat()}-to-{end.isoformat()}.csv"
    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.put("/{usage_id}", response_model=ResourceUsageResponse)
def edit_resource_usage(
    usage_id: int,
    payload: ResourceUsageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    usage = _get_usage_or_404(db, usage_id)
    _require_module_permission(current_user, usage.module)
    try:
        updated = update_usage(
            db,
            usage=usage,
            changes=payload.model_dump(exclude_unset=True),
            current_user=current_user,
        )
        db.flush()
        evaluate_automatic_tasks(db, commit=False)
        db.commit()
        db.refresh(updated)
        return serialize_usage(db, updated)
    except Exception:
        db.rollback()
        raise


@router.delete("/{usage_id}", response_model=ResourceUsageResponse)
def delete_resource_usage(
    usage_id: int,
    reason: str = Query(min_length=2, max_length=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_void_administrator(current_user)
    usage = _get_usage_or_404(db, usage_id)
    if usage.activity_id:
        raise HTTPException(409, "Task-linked usage must be reversed through its approved task.")
    _require_module_permission(current_user, usage.module)
    try:
        voided = void_usage(
            db,
            usage=usage,
            reason=reason,
            current_user=current_user,
        )
        db.flush()
        evaluate_automatic_tasks(db, commit=False)
        db.commit()
        db.refresh(voided)
        return serialize_usage(db, voided)
    except Exception:
        db.rollback()
        raise


