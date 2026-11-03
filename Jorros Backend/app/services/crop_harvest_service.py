from __future__ import annotations

from datetime import date, datetime
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive, farm_today
from app.models import (
    AuditLog,
    Crop,
    CropYieldRecord,
    Employee,
    FarmActivity,
    FarmAlert,
    TaskSubmission,
    User,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.services.production_sales_service import create_crop_production_from_yield


OPEN_CROP_STATUSES = {"Planted", "Growing", "Ready for Harvest", "Harvesting"}
FINAL_STATUS = "Harvested"
PROTECTED_TASK_STATUSES = {
    "In Progress",
    "Submitted for Review",
    "Completed",
    "Approved",
    "Voided",
    "Cancelled",
    "Resolved",
}


def _audit(
    db: Session, *, crop: Crop, action: str, details: str, actor: User,
    occurred_at: datetime | None = None,
) -> None:
    common = dict(
        action=action,
        module="Crop",
        record_name=f"{crop.name} — {crop.field}",
        entity_id=crop.crop_code,
        details=details,
        icon="agriculture",
        actor_user_id=actor.id,
        actor_name=actor.full_name or actor.username,
    )
    if occurred_at is not None:
        common["created_at"] = occurred_at
    db.add(AuditLog(event_type="audit", **common))
    db.add(AuditLog(event_type="timeline", **common))


def crop_harvest_totals(db: Session, crop_id: int) -> dict[str, float | int | date | None]:
    rows = list(
        db.scalars(
            select(CropYieldRecord)
            .where(CropYieldRecord.crop_id == int(crop_id))
            .order_by(CropYieldRecord.harvest_date, CropYieldRecord.id)
        ).all()
    )
    partial = [r for r in rows if str(r.harvest_type or "").strip().lower() == "partial harvest"]
    finals = [r for r in rows if str(r.harvest_type or "").strip().lower() == "final harvest"]
    return {
        "harvest_count": len(rows),
        "partial_total_kg": round(sum(float(r.quantity_kg or 0) for r in partial), 3),
        "total_kg": round(sum(float(r.quantity_kg or 0) for r in rows), 3),
        "first_harvest_date": rows[0].harvest_date if rows else None,
        "final_harvest_date": finals[-1].harvest_date if finals else None,
    }


def final_harvest_blockers(
    db: Session,
    *,
    crop_id: int,
    harvest_date: date,
    related_task_id: int | None = None,
) -> list[FarmActivity]:
    stmt = select(FarmActivity).where(
        FarmActivity.is_archived == False,  # noqa: E712
        FarmActivity.source_module == "Crop",
        FarmActivity.source_record_id == int(crop_id),
        FarmActivity.activity_date == harvest_date,
        FarmActivity.status.in_(["Pending", "In Progress", "Submitted for Review", "Returned"]),
    )
    if related_task_id is not None:
        stmt = stmt.where(FarmActivity.id != int(related_task_id))
    return list(db.scalars(stmt.order_by(FarmActivity.id)).all())


def harvest_approval_blocker(
    db: Session,
    *,
    crop: Crop,
    harvest_date: date,
    related_task_id: int | None = None,
) -> str | None:
    """Explain recorded harvest conflicts without accepting duplicate yields."""
    if crop.is_archived:
        return "Restore this archived crop before reviewing its harvest task."
    if crop.status == "Failed":
        return "This crop cycle is marked Failed. Correct its status in Crops before reviewing the harvest."

    final = db.scalar(
        select(CropYieldRecord).where(
            CropYieldRecord.crop_id == crop.id,
            CropYieldRecord.harvest_type.ilike("Final Harvest"),
        ).order_by(CropYieldRecord.id.desc()).limit(1)
    )
    last_reopen = db.scalar(
        select(AuditLog).where(
            AuditLog.event_type == "audit",
            AuditLog.module == "Crop",
            AuditLog.entity_id == crop.crop_code,
            AuditLog.action == "Reopened crop cycle",
        ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1)
    ) if crop.status in OPEN_CROP_STATUSES else None
    reopen_at = last_reopen.created_at if last_reopen else None

    if reopen_at is not None and harvest_date < reopen_at.date():
        return "This harvest predates the latest crop reopening. Review the original yield history instead of adding it to the reopened cycle."

    baseline = re.search(r"Previous final yield ID: (\d+)", last_reopen.details or "") if last_reopen else None
    previous_cycle_final = bool(
        final is not None and reopen_at is not None and (
            final.id <= int(baseline.group(1)) if baseline
            else final.created_at is not None and final.created_at <= reopen_at
        )
    )
    if final is not None and final.related_task_id != related_task_id and not previous_cycle_final:
        return (
            f"This crop already has a Final Harvest of {float(final.quantity_kg):g} kg "
            f"on {final.harvest_date.isoformat()}. Approving another harvest would count it twice. "
            "Compare the yield records in Crops; void a duplicate submission or correct the crop history first."
        )

    if crop.status == FINAL_STATUS:
        newer = db.scalar(
            select(CropYieldRecord).where(
                CropYieldRecord.crop_id == crop.id,
                CropYieldRecord.harvest_date > harvest_date,
            ).order_by(CropYieldRecord.harvest_date, CropYieldRecord.id).limit(1)
        )
        if newer is not None:
            return (
                f"This crop is Fully Harvested and has a recorded harvest on {newer.harvest_date.isoformat()}, "
                f"after this task's {harvest_date.isoformat()} date. Review the crop's yield history "
                "before approving or voiding this submission."
            )
    return None


def _void_future_pending_crop_tasks(
    db: Session,
    *,
    crop_id: int,
    harvest_date: date,
    related_task_id: int | None,
) -> int:
    stmt = select(FarmActivity).where(
        FarmActivity.is_archived == False,  # noqa: E712
        FarmActivity.source_module == "Crop",
        FarmActivity.source_record_id == int(crop_id),
        FarmActivity.status == "Pending",
        FarmActivity.activity_date > harvest_date,
    )
    if related_task_id is not None:
        stmt = stmt.where(FarmActivity.id != int(related_task_id))
    rows = list(db.scalars(stmt).all())
    now = farm_now_naive()
    for task in rows:
        task.status = "Voided"
        task.problem_report = "Crop cycle fully harvested."
        task.completed_at = None
        task.updated_at = now
    return len(rows)


def _resolve_readiness_alerts(db: Session, crop_id: int) -> int:
    rows = list(
        db.scalars(
            select(FarmAlert).where(
                FarmAlert.is_automatic == True,  # noqa: E712
                FarmAlert.source_type == "crop_harvest",
                FarmAlert.source_id == int(crop_id),
                FarmAlert.status == "Active",
            )
        ).all()
    )
    now = farm_now_naive()
    for row in rows:
        row.status = "Resolved"
        row.updated_at = now
    return len(rows)


def confirm_crop_ready(db: Session, *, crop: Crop, actor: User) -> Crop:
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")
    if crop.is_archived:
        raise HTTPException(status_code=400, detail="Archived crop records cannot be marked ready for harvest.")
    if crop.status in {"Harvested", "Failed"}:
        raise HTTPException(status_code=400, detail="A completed or failed crop cycle cannot be marked ready for harvest.")
    crop.status = "Ready for Harvest" if crop.status != "Harvesting" else "Harvesting"
    crop.growth_stage = "Harvest Ready" if crop.status == "Ready for Harvest" else "Harvesting / Production"
    crop.current_growth = 100.0
    crop.confirmed_ready_at = farm_now_naive()
    crop.confirmed_ready_by_user_id = actor.id
    _audit(
        db,
        crop=crop,
        action="Confirmed crop ready for harvest",
        details="Physical harvest readiness was confirmed by an authorized user.",
        actor=actor,
    )
    return crop


def record_harvest(
    db: Session,
    *,
    crop: Crop,
    harvest_date: date,
    quantity_kg: float,
    harvest_type: str,
    actor: User,
    performed_by_employee_id: int | None,
    related_task_id: int | None = None,
    manual_reason: str | None = None,
    quality: str | None = None,
    farm_use_quantity_kg: float = 0,
    damaged_quantity_kg: float = 0,
    reserved_quantity_kg: float = 0,
    notes: str | None = None,
    evidence_url: str | None = None,
    final_harvest_confirmed: bool = False,
    allow_completed_crop_for_linked_review: bool = False,
) -> CropYieldRecord:
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")

    if related_task_id is not None:
        existing = db.scalar(
            select(CropYieldRecord).where(CropYieldRecord.related_task_id == int(related_task_id))
        )
        if existing is not None:
            return existing

    if crop.is_archived:
        raise HTTPException(status_code=400, detail="Archived crop records cannot receive a harvest.")
    if crop.status == "Failed":
        raise HTTPException(status_code=400, detail="A failed crop cycle cannot receive a harvest record.")
    if harvest_date < crop.planting_date:
        raise HTTPException(status_code=400, detail="Harvest date cannot be earlier than the planting date.")
    if harvest_date > farm_today():
        raise HTTPException(status_code=400, detail="Harvest date cannot be in the future.")
    if float(quantity_kg or 0) <= 0:
        raise HTTPException(status_code=400, detail="Harvest quantity must be greater than zero.")

    normalized_type = " ".join(str(harvest_type or "").strip().lower().split())
    if normalized_type not in {"partial harvest", "final harvest"}:
        raise HTTPException(status_code=400, detail="Harvest type must be Partial Harvest or Final Harvest.")
    if normalized_type == "final harvest" and not final_harvest_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Final Harvest requires explicit confirmation because it closes the crop cycle and stops future care tasks.",
        )

    linked_review = bool(
        allow_completed_crop_for_linked_review
        and related_task_id is not None
        and normalized_type == "final harvest"
        and db.scalar(select(FarmActivity.id).where(
            FarmActivity.id == related_task_id,
            FarmActivity.source_module == "Crop",
            FarmActivity.source_type == "crop_harvest",
            FarmActivity.source_record_id == crop.id,
            FarmActivity.status == "Submitted for Review",
        )) is not None
    )
    if crop.status == FINAL_STATUS and not linked_review:
        raise HTTPException(
            status_code=409 if allow_completed_crop_for_linked_review else 400,
            detail="This crop is already Fully Harvested. Reopen the crop in Crops before recording another harvest, or review its existing yield records and void a duplicate submission.",
        )
    conflict = harvest_approval_blocker(db, crop=crop, harvest_date=harvest_date, related_task_id=related_task_id)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    if crop.status not in OPEN_CROP_STATUSES and crop.status != FINAL_STATUS:
        raise HTTPException(status_code=400, detail="This crop cycle is not open for harvest recording.")

    if related_task_id is None:
        active_task = db.scalar(
            select(FarmActivity).where(
                FarmActivity.is_archived == False,  # noqa: E712
                FarmActivity.source_module == "Crop",
                FarmActivity.source_type == "crop_harvest",
                FarmActivity.source_record_id == int(crop.id),
                FarmActivity.activity_date == harvest_date,
                FarmActivity.status.in_(["Pending", "In Progress", "Submitted for Review", "Returned"]),
            ).order_by(FarmActivity.id)
        )
        if active_task is not None:
            latest_submission = db.scalar(
                select(TaskSubmission).where(TaskSubmission.activity_id == active_task.id).order_by(
                    TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc()
                )
            )
            intent = str(getattr(latest_submission, "harvest_type_intent", None) or "").strip() or None
            if active_task.status == "Submitted for Review":
                state = f"Waiting for {intent} Confirmation" if intent else "Waiting for Harvest Type Confirmation"
            elif active_task.status == "Returned":
                state = f"{intent or 'Harvest'} Returned for Correction"
            else:
                state = f"{intent or 'Harvest'} Task {active_task.status}"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This harvest is already controlled by Task Management ({active_task.activity_code}: {state}). "
                    "Open the linked task instead of recording a second harvest in Crops."
                ),
            )
        if performed_by_employee_id is None:
            raise HTTPException(status_code=400, detail="Select the employee who performed this manual/assisted harvest.")
        if not str(manual_reason or "").strip():
            raise HTTPException(status_code=400, detail="Enter a reason for recording a harvest without an existing task.")

    performer = None
    if performed_by_employee_id is not None:
        performer = db.get(Employee, int(performed_by_employee_id))
        if performer is None or performer.is_archived:
            raise HTTPException(status_code=400, detail="The employee who performed this harvest is unavailable.")

    allocated = float(farm_use_quantity_kg or 0) + float(damaged_quantity_kg or 0) + float(reserved_quantity_kg or 0)
    if min(float(farm_use_quantity_kg or 0), float(damaged_quantity_kg or 0), float(reserved_quantity_kg or 0)) < 0:
        raise HTTPException(status_code=400, detail="Harvest allocation quantities cannot be negative.")
    if allocated > float(quantity_kg):
        raise HTTPException(status_code=400, detail="Farm use, damaged/spoiled, and reserved quantities cannot exceed the harvested quantity.")

    if normalized_type == "final harvest":
        blockers = final_harvest_blockers(
            db,
            crop_id=crop.id,
            harvest_date=harvest_date,
            related_task_id=related_task_id,
        )
        if blockers:
            labels = ", ".join(f"{row.activity_code} ({row.status})" for row in blockers[:5])
            raise HTTPException(
                status_code=409,
                detail=f"Resolve same-day crop task(s) before Final Harvest: {labels}.",
            )

    area = float(crop.area_hectares or 0)
    now = farm_now_naive()
    row = CropYieldRecord(
        crop_id=crop.id,
        harvest_date=harvest_date,
        quantity_kg=float(quantity_kg),
        farm_use_quantity_kg=float(farm_use_quantity_kg or 0),
        damaged_quantity_kg=float(damaged_quantity_kg or 0),
        reserved_quantity_kg=float(reserved_quantity_kg or 0),
        quality=(str(quality).strip() if quality else None),
        harvest_type="Final Harvest" if normalized_type == "final harvest" else "Partial Harvest",
        yield_per_hectare=(float(quantity_kg) / area if area > 0 else None),
        notes=(str(notes).strip() if notes else None),
        performed_by_employee_id=(performer.id if performer else None),
        related_task_id=related_task_id,
        manual_reason=(str(manual_reason).strip() if manual_reason else None),
        evidence_url=(str(evidence_url).strip() if evidence_url else None),
        recorded_by_user_id=actor.id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    create_crop_production_from_yield(db, row, crop, actor)

    if normalized_type == "final harvest":
        crop.status = FINAL_STATUS
        crop.growth_stage = "Harvested"
        crop.current_growth = 100.0
        crop.completed_at = now
        crop.completed_by_user_id = actor.id
        voided = _void_future_pending_crop_tasks(
            db,
            crop_id=crop.id,
            harvest_date=harvest_date,
            related_task_id=related_task_id,
        )
        resolved_alerts = _resolve_readiness_alerts(db, crop.id)
        _audit(
            db,
            crop=crop,
            action="Recorded Final Harvest",
            details=(
                f"Final Harvest {float(quantity_kg):g} kg; crop cycle closed. "
                f"Voided {voided} eligible future task(s); resolved {resolved_alerts} readiness alert(s)."
            ),
            actor=actor,
        )
    else:
        crop.status = "Harvesting"
        crop.growth_stage = "Harvesting / Production"
        crop.current_growth = 100.0
        _audit(
            db,
            crop=crop,
            action="Recorded Partial Harvest",
            details=f"Partial Harvest {float(quantity_kg):g} kg; crop cycle remains active for additional harvests.",
            actor=actor,
        )
    crop.updated_at = now
    return row


def reopen_crop_cycle(
    db: Session,
    *,
    crop: Crop,
    actor: User,
    reason: str,
    new_status: str,
) -> Crop:
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")
    if crop.is_archived:
        raise HTTPException(status_code=400, detail="Restore the archived crop before reopening its crop cycle.")
    if crop.status != FINAL_STATUS:
        raise HTTPException(status_code=400, detail="Only a Fully Harvested/Completed crop can be reopened.")
    cleaned_reason = str(reason or "").strip()
    if len(cleaned_reason) < 3:
        raise HTTPException(status_code=400, detail="A reopen reason is required.")
    if new_status not in {"Harvesting", "Ready for Harvest"}:
        raise HTTPException(status_code=400, detail="Reopened crop status must be Harvesting or Ready for Harvest.")

    previous = crop.status
    previous_completed_at = crop.completed_at
    previous_final = db.scalar(
        select(CropYieldRecord.id).where(
            CropYieldRecord.crop_id == crop.id,
            CropYieldRecord.harvest_type.ilike("Final Harvest"),
        ).order_by(CropYieldRecord.id.desc()).limit(1)
    )
    now = farm_now_naive()
    crop.status = new_status
    crop.growth_stage = "Harvesting / Production" if new_status == "Harvesting" else "Harvest Ready"
    crop.current_growth = 100.0
    crop.completed_at = None
    crop.completed_by_user_id = None
    if new_status == "Ready for Harvest":
        crop.confirmed_ready_at = now
        crop.confirmed_ready_by_user_id = actor.id
    crop.updated_at = now
    _audit(
        db,
        crop=crop,
        action="Reopened crop cycle",
        details=(
            f"Reason: {cleaned_reason}. Status: {previous} → {new_status}. "
            f"Previous completion: {previous_completed_at.isoformat() if previous_completed_at else 'Not Recorded'}. "
            f"Previous final yield ID: {previous_final or 0}. "
            "Existing harvest and production history was preserved."
        ),
        actor=actor,
        occurred_at=now,
    )
    return crop
