from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete
from datetime import date, datetime
import re

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query,
    Response,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.orm import (
    Session,
    object_session,
    selectinload,
)

from app.services.resource_monitoring import validate_schedule, record_crop_observation
from app.core.database import get_db
from app.core.farm_time import farm_today
from app.core.dependencies import has_permission, require_permission
from app.models import (
    AuditLog,
    Crop,
    CropGrowthRecord,
    CropPestDisease,
    CropYieldRecord,
    FarmActivity,
    ResourceUsage,
    TaskSubmission,
    User,
)
from app.routers.auth import get_current_user
from app.services.task_engine import evaluate_automatic_tasks
from app.services.crop_growth import (
    calculate_crop_progress,
    stage_for_progress,
    status_for_progress,
    validate_survival_counts,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.services.crop_audit import crop_snapshot, record_crop_change
from app.services.crop_harvest_service import (
    confirm_crop_ready,
    record_harvest,
    reopen_crop_cycle,
)
from app.services.care_task_workflow import (
    generate_care_tasks_for_target,
    reconcile_same_template_future_schedule,
    resolve_future_pending_care_tasks,
    validate_care_template_for_target,
)
from app.services.care_protocol_summary import attach_care_protocol_summaries
from app.services.idempotency import (
    begin_creation_command,
    record_creation_command,
    request_fingerprint,
)
from app.schemas.crops import (
    CropCreate,
    CropDetailsResponse,
    CropGrowthCreate,
    CropGrowthResponse,
    CropPestDiseaseCreate,
    CropPestDiseaseUpdate,
    CropPestDiseaseResponse,
    CropResponse,
    CropUpdate,
    CropYieldCreate,
    CropYieldResponse,
    CropReopenRequest,
    CropReadyConfirmationRequest,
)


router = APIRouter(
    prefix="/api/v1/crops",
    dependencies=[Depends(require_permission("crops:view"))],
    tags=["Crops"],
)

TERMINAL_CROP_STATUSES = {
    "Harvested",
    "Failed",
}

EDITABLE_STATUS_VALUES = {
    "Automatic",
    "Planted",
    "Growing",
    "Ready for Harvest",
    "Harvesting",
    "Harvested",
    "Failed",
}


# =========================================================
# PERMISSIONS
# =========================================================


def require_crop_creator(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "crops:create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create crop records.",
        )
    return current_user


def require_crop_archiver(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "crops:archive"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to archive or restore crop records.",
        )
    return current_user


def require_crop_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "crops:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage crop records.",
        )
    return current_user


def require_crop_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not (
        has_permission(current_user, "crops:full-edit")
        or has_permission(current_user, "*")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete crop editing requires elevated crop permission.",
        )
    return current_user


def require_system_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a System Administrator can permanently delete archived records.",
        )
    return current_user




def _annotate_pending_harvest_workflows(db: Session, crops: list[Crop]) -> list[Crop]:
    from app.services.monitoring_scheduler import annotate_monitoring
    annotate_monitoring(db, crops, "Crop")
    if not crops:
        return crops
    attach_care_protocol_summaries(db, crops)
    crop_ids = [int(crop.id) for crop in crops]
    tasks = list(db.scalars(
        select(FarmActivity).where(
            FarmActivity.is_archived == False,  # noqa: E712
            FarmActivity.source_module == "Crop",
            FarmActivity.source_type == "crop_harvest",
            FarmActivity.source_record_id.in_(crop_ids),
            FarmActivity.status.in_(["Pending", "In Progress", "Submitted for Review", "Returned"]),
        ).order_by(FarmActivity.activity_date, FarmActivity.id)
    ).all())
    task_ids = [task.id for task in tasks]
    latest_by_task: dict[int, TaskSubmission] = {}
    if task_ids:
        submissions = list(db.scalars(
            select(TaskSubmission).where(TaskSubmission.activity_id.in_(task_ids)).order_by(
                TaskSubmission.activity_id, TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc()
            )
        ).all())
        for submission in submissions:
            latest_by_task.setdefault(int(submission.activity_id), submission)

    rank = {"Submitted for Review": 0, "Returned": 1, "In Progress": 2, "Pending": 3}
    chosen: dict[int, FarmActivity] = {}
    for task in sorted(tasks, key=lambda row: (rank.get(row.status, 9), row.activity_date, row.id)):
        chosen.setdefault(int(task.source_record_id), task)

    for crop in crops:
        task = chosen.get(int(crop.id))
        setattr(crop, "pending_harvest_task_id", task.id if task else None)
        setattr(crop, "pending_harvest_task_code", task.activity_code if task else None)
        setattr(crop, "pending_harvest_task_status", task.status if task else None)
        if task is None:
            setattr(crop, "pending_harvest_type", None)
            setattr(crop, "pending_harvest_message", None)
            continue
        submission = latest_by_task.get(int(task.id))
        intent = str(getattr(submission, "harvest_type_intent", None) or "").strip() or None
        setattr(crop, "pending_harvest_type", intent)
        if task.status == "Submitted for Review":
            message = f"Waiting for {intent} Confirmation" if intent else "Waiting for Harvest Type Confirmation"
        elif task.status == "Returned":
            message = f"{intent or 'Harvest'} Returned for Correction"
        elif task.status == "In Progress":
            message = f"{intent or 'Harvest'} Task In Progress"
        else:
            message = f"{intent or 'Harvest'} Task Pending"
        setattr(crop, "pending_harvest_message", message)
    return crops


# =========================================================
# AUTOMATIC PROGRESS
# =========================================================


def _harvest_record_type(record: CropYieldRecord) -> str:
    return str(record.harvest_type or "").strip().lower()


def apply_automatic_progress(
    crop: Crop,
) -> Crop:
    # Growth % is automatic until the first real harvest is recorded.
    # A partial harvest means the crop has reached production and remains
    # active; a final harvest closes the crop cycle.
    if crop.status == "Failed":
        return crop

    harvest_records = list(crop.yield_records or [])

    # The live status belongs to the current opening. An earlier Final
    # Harvest remains in history, but cannot close a cycle reopened later.
    if crop.status in {"Harvesting", "Ready for Harvest"} and harvest_records:
        db = object_session(crop)
        if db is not None:
            last_reopen = db.scalar(
                select(AuditLog).where(
                    AuditLog.event_type == "audit",
                    AuditLog.module == "Crop",
                    AuditLog.entity_id == crop.crop_code,
                    AuditLog.action == "Reopened crop cycle",
                ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1)
            )
            if last_reopen is not None:
                baseline = re.search(
                    r"Previous final yield ID: (\d+)", last_reopen.details or ""
                )
                harvest_records = [
                    record for record in harvest_records
                    if record.id > int(baseline.group(1))
                ] if baseline else [
                    record for record in harvest_records
                    if record.created_at and record.created_at > last_reopen.created_at
                ]

    if (
        crop.status == "Harvested"
        or any(
            _harvest_record_type(record) == "final harvest"
            for record in harvest_records
        )
    ):
        crop.status = "Harvested"
        crop.growth_stage = "Harvested"
        crop.current_growth = 100.0
        return crop

    if any(
        _harvest_record_type(record) == "partial harvest"
        for record in harvest_records
    ):
        crop.status = "Harvesting"
        crop.growth_stage = "Harvesting / Production"
        crop.current_growth = 100.0
        return crop

    if crop.status == "Harvesting":
        crop.growth_stage = "Harvesting / Production"
        crop.current_growth = 100.0
        return crop

    if crop.confirmed_ready_at is not None:
        crop.status = "Ready for Harvest"
        crop.growth_stage = "Harvest Ready"
        crop.current_growth = 100.0
        return crop

    progress = calculate_crop_progress(
        crop.planting_date,
        crop.estimated_harvest,
    )
    crop.current_growth = progress
    crop.growth_stage = crop.observed_growth_stage or stage_for_progress(progress)
    crop.status = ("Planted" if crop.observed_growth_stage == "Seeded" else "Growing") if crop.observed_growth_stage else status_for_progress(progress)
    return crop


# =========================================================
# HELPERS
# =========================================================


def get_crop_or_404(
    crop_id: int,
    db: Session,
) -> Crop:
    statement = (
        select(Crop)
        .where(Crop.id == crop_id)
        .options(
            selectinload(
                Crop.growth_records
            ),
            selectinload(
                Crop.yield_records
            ),
            selectinload(
                Crop.pest_diseases
            ),
        )
    )

    crop = db.scalar(statement)

    if crop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crop record not found.",
        )

    return apply_automatic_progress(
        crop
    )



def validate_edit_status(
    crop_status: str,
):
    if crop_status not in EDITABLE_STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid crop status. Use Automatic, "
                "Harvested, or Failed."
            ),
        )



def generate_crop_code(
    db: Session,
) -> str:
    acquire_transaction_lock(db, "code:crop")
    existing_codes = db.scalars(
        select(Crop.crop_code)
    ).all()

    highest_number = 1000

    for code in existing_codes:
        try:
            number = int(
                "".join(
                    character
                    for character in code
                    if character.isdigit()
                )
            )

            highest_number = max(
                highest_number,
                number,
            )
        except (TypeError, ValueError):
            continue

    return f"CRP-{highest_number + 1}"



def ensure_crop_not_archived(
    crop: Crop,
):
    if crop.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Archived crop records cannot be "
                "modified. Restore the crop first."
            ),
        )


# =========================================================
# GET ALL CROPS
# =========================================================

@router.get(
    "",
    response_model=list[CropResponse],
)
def list_crops(
    include_archived: bool = Query(
        default=False
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = (
        select(Crop)
        .options(
            selectinload(Crop.yield_records)
        )
        .order_by(Crop.id.desc())
    )

    if not include_archived:
        statement = statement.where(
            Crop.is_archived == False
        )

    crops = list(
        db.scalars(statement).all()
    )

    crops = [apply_automatic_progress(crop) for crop in crops]
    return _annotate_pending_harvest_workflows(db, crops)


# =========================================================
# GET ALL CROPS WITH DETAIL HISTORY
# =========================================================

@router.get(
    "/details",
    response_model=list[CropDetailsResponse],
)
def list_crop_details(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = (
        select(Crop)
        .options(
            selectinload(Crop.growth_records),
            selectinload(Crop.yield_records),
            selectinload(Crop.pest_diseases),
        )
        .order_by(Crop.id.desc())
    )

    if not include_archived:
        statement = statement.where(
            Crop.is_archived == False
        )

    crops = [apply_automatic_progress(crop) for crop in db.scalars(statement).all()]
    return _annotate_pending_harvest_workflows(db, crops)


# =========================================================
# GET ONE CROP
# =========================================================

@router.get(
    "/{crop_id}",
    response_model=CropDetailsResponse,
)
def get_crop(
    crop_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    crop = get_crop_or_404(crop_id, db)
    apply_automatic_progress(crop)
    return _annotate_pending_harvest_workflows(db, [crop])[0]


# =========================================================
# CREATE CROP
# =========================================================

@router.post(
    "",
    response_model=CropResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_crop(
    payload: CropCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_crop_creator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_hash = request_fingerprint(payload)
    try:
        existing_command = begin_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="crop_create",
            request_hash=request_hash,
            user_id=current_user.id,
        )
        if existing_command is not None:
            existing_crop = db.get(Crop, existing_command.target_id)
            if existing_crop is None:
                raise HTTPException(
                    status_code=409,
                    detail="The original idempotent crop result is no longer available.",
                )
            return apply_automatic_progress(existing_crop)

        current_surviving = (
            payload.current_surviving
            if payload.current_surviving is not None
            else payload.quantity_planted
        )
        try:
            validate_survival_counts(payload.quantity_planted, current_surviving)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        automatic_progress = calculate_crop_progress(
            payload.planting_date,
            payload.estimated_harvest,
        )

        crop = Crop(
            crop_code=generate_crop_code(db),
            name=payload.name.strip(),
            variety=payload.variety.strip(),
            field=payload.field.strip(),
            area_hectares=payload.area_hectares,
            current_growth=automatic_progress,
            growth_stage=stage_for_progress(automatic_progress),
            quantity_planted=payload.quantity_planted,
            current_surviving=current_surviving,
            status=status_for_progress(automatic_progress),
            planting_date=payload.planting_date,
            estimated_harvest=payload.estimated_harvest,
            fertilizer_quantity_kg=payload.fertilizer_quantity_kg,
            fertilizer_date=payload.fertilizer_date,
            pesticide_used=payload.pesticide_used.strip() if payload.pesticide_used else None,
            watering_schedule=payload.watering_schedule.strip() if payload.watering_schedule else None,
            notes=payload.notes.strip() if payload.notes else None,
            survival_count_date=farm_today(),
            monitoring_enabled=payload.monitoring_enabled,
            monitoring_start_date=payload.monitoring_start_date,
            monitoring_end_date=payload.monitoring_end_date,
            monitoring_frequency_days=payload.monitoring_frequency_days,
            assigned_employee_id=payload.assigned_employee_id,
            care_template_id=payload.care_template_id,
            created_by_user_id=current_user.id,
            is_archived=False,
        )
        validate_schedule(crop, "Crop")
        apply_automatic_progress(crop)

        template = None
        if payload.care_template_id is not None:
            template = validate_care_template_for_target(
                db,
                template_id=payload.care_template_id,
                module="Crop",
                target=crop,
            )

        db.add(crop)
        db.flush()

        if template is not None:
            generate_care_tasks_for_target(
                db,
                module="Crop",
                target=crop,
                template=template,
                current_user=current_user,
                base_date=crop.planting_date,
            )

        record_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="crop_create",
            request_hash=request_hash,
            target_id=crop.id,
            user_id=current_user.id,
        )
        record_crop_change(db, crop, current_user, action="Created crop record")
        evaluate_automatic_tasks(db, commit=False)
        db.commit()
        db.refresh(crop)
        return apply_automatic_progress(crop)
    except Exception:
        db.rollback()
        raise


# =========================================================
# FULL EDIT CROP - ADMIN ONLY
# =========================================================

@router.put(
    "/{crop_id}",
    response_model=CropResponse,
)
def update_crop(
    crop_id: int,
    payload: CropUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_crop_admin
    ),
):
    acquire_transaction_lock(db, f"crop-harvest:{crop_id}")
    crop = get_crop_or_404(
        crop_id,
        db,
    )

    ensure_crop_not_archived(crop)

    before = crop_snapshot(crop)
    changes = payload.model_dump(
        exclude_unset=True
    )
    future_care_task_action = changes.pop("future_care_task_action", None)
    old_care_template_id = crop.care_template_id
    old_planting_date = crop.planting_date

    if (
        "care_template_id" in changes
        and changes.get("care_template_id") is None
        and old_care_template_id is not None
        and future_care_task_action not in {"keep", "resolve"}
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Removing a crop care protocol requires future_care_task_action "
                "to be 'keep' or 'resolve'."
            ),
        )

    requested_status = changes.pop(
        "status",
        None,
    )

    # Growth stage is system-controlled. Ignore legacy clients that still send it.
    changes.pop("growth_stage", None)

    if requested_status is not None:
        validate_edit_status(
            requested_status
        )

    proposed_planting_date = (
        changes.get(
            "planting_date",
            crop.planting_date,
        )
    )

    proposed_harvest_date = (
        changes.get(
            "estimated_harvest",
            crop.estimated_harvest,
        )
    )

    if (
        proposed_harvest_date
        < proposed_planting_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Estimated harvest date cannot be "
                "earlier than planting date."
            ),
        )

    proposed_quantity = int(changes.get("quantity_planted", crop.quantity_planted))
    proposed_surviving = int(changes.get("current_surviving", crop.current_surviving))
    try:
        validate_survival_counts(proposed_quantity, proposed_surviving)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if "current_surviving" in changes and int(changes["current_surviving"]) != int(crop.current_surviving):
        crop.survival_count_date = farm_today()
    text_fields = {
        "name",
        "variety",
        "field",
        "pesticide_used",
        "watering_schedule",
        "notes",
    }

    for field_name, value in changes.items():
        if (
            field_name in text_fields
            and isinstance(value, str)
        ):
            value = value.strip()

        setattr(
            crop,
            field_name,
            value,
        )

    if requested_status in TERMINAL_CROP_STATUSES:
        crop.status = requested_status

        if requested_status == "Harvested":
            crop.growth_stage = "Harvested"
            crop.current_growth = 100.0
    else:
        # Active records always return to automatic date-based tracking.
        crop.status = "Planted"
        apply_automatic_progress(crop)

    validate_schedule(crop, "Crop")
    crop.updated_at = datetime.now()

    care_assignment_changed = "care_template_id" in changes
    schedule_anchor_changed = "planting_date" in changes
    target_type_changed = "name" in changes
    new_care_template_id = crop.care_template_id

    try:
        if new_care_template_id is not None:
            template = validate_care_template_for_target(
                db,
                template_id=new_care_template_id,
                module="Crop",
                target=crop,
            )
        else:
            template = None

        if care_assignment_changed and old_care_template_id != new_care_template_id:
            if old_care_template_id is not None:
                if new_care_template_id is not None or future_care_task_action == "resolve":
                    resolve_future_pending_care_tasks(
                        db,
                        module="Crop",
                        target_id=crop.id,
                        template_id=old_care_template_id,
                    )
            if template is not None:
                generate_care_tasks_for_target(
                    db,
                    module="Crop",
                    target=crop,
                    template=template,
                    current_user=_,
                    base_date=crop.planting_date,
                    future_only=True,
                )
        elif template is not None and (schedule_anchor_changed or target_type_changed):
            reconcile_same_template_future_schedule(
                db,
                module="Crop",
                target=crop,
                template=template,
                current_user=_,
                base_date=crop.planting_date,
            )

        evaluate_automatic_tasks(db, commit=False)
        record_crop_change(db, crop, _, action="Edited crop information", before=before)
        db.commit()
        db.refresh(crop)
        return apply_automatic_progress(crop)
    except Exception:
        db.rollback()
        raise


# =========================================================
# ARCHIVE CROP
# =========================================================

@router.post(
    "/{crop_id}/archive",
    response_model=CropResponse,
)
def archive_crop(
    crop_id: int,
    payload: ArchiveRequest,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_crop_archiver
    ),
):
    record = change_archive_state(db, "Crop", crop_id, _, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return apply_automatic_progress(record)


# =========================================================
# RESTORE CROP
# =========================================================

@router.post(
    "/{crop_id}/restore",
    response_model=CropResponse,
)
def restore_crop(
    crop_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_crop_archiver
    ),
):
    record = change_archive_state(db, "Crop", crop_id, _, archive=False)
    db.commit()
    db.refresh(record)
    return apply_automatic_progress(record)


# =========================================================
# PERMANENTLY DELETE ARCHIVED CROP
# =========================================================

@router.delete(
    "/{crop_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
)
def permanently_delete_crop(
    crop_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_system_admin),
):
    permanent_delete(db, "Crop", crop_id, _)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================
# GROWTH / SURVIVAL OBSERVATION
# =========================================================

@router.get("/{crop_id}/growth-records", response_model=list[CropGrowthResponse])
def list_growth_records(crop_id: int, date_from: date | None = None, date_to: date | None = None,
                        db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    get_crop_or_404(crop_id, db)
    if date_from and date_to and date_to < date_from:
        raise HTTPException(400, "History end date cannot precede start date.")
    query = select(CropGrowthRecord).where(CropGrowthRecord.crop_id == crop_id)
    if date_from: query = query.where(CropGrowthRecord.update_date >= date_from)
    if date_to: query = query.where(CropGrowthRecord.update_date <= date_to)
    return list(db.scalars(query.order_by(CropGrowthRecord.update_date.desc(), CropGrowthRecord.id.desc())).all())


@router.post(
    "/{crop_id}/growth-records",
    response_model=CropGrowthResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_growth_record(
    crop_id: int,
    payload: CropGrowthCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_crop_editor),
):
    """Record a real crop growth/survival inspection.

    Growth percentage and stage remain schedule-driven. The operational
    observation updates surviving plants and supplies the evidence that
    resolves the related automatic Growth Check activity.
    """
    acquire_transaction_lock(db, f"crop-harvest:{crop_id}")
    crop = get_crop_or_404(crop_id, db)
    ensure_crop_not_archived(crop)

    if crop.status in TERMINAL_CROP_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Growth checks cannot be added to a {crop.status.lower()} crop cycle.",
        )

    if payload.update_date < crop.planting_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Growth check date cannot be earlier than the planting date.",
        )

    if payload.update_date > farm_today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Growth check date cannot be in the future.",
        )

    duplicate = db.scalar(
        select(CropGrowthRecord).where(
            CropGrowthRecord.crop_id == crop.id,
            CropGrowthRecord.update_date == payload.update_date,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A growth check has already been recorded for this crop on that date.",
        )

    if payload.update_date < farm_today() and payload.current_surviving is None:
        raise HTTPException(400, "Enter the surviving count actually observed on the backdated inspection date.")
    current_surviving = (
        payload.current_surviving
        if payload.current_surviving is not None
        else int(crop.current_surviving)
    )

    try:
        validate_survival_counts(
            int(crop.quantity_planted),
            current_surviving,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    record = record_crop_observation(db, crop, observation_date=payload.update_date,
                                     surviving=current_surviving, observed_stage=payload.observed_stage,
                                     notes=(payload.notes or "").strip() or None,
                                     recorder_id=current_user.id, reviewer_id=current_user.id,
                                     confirm_ready=payload.observed_stage == "Harvest Ready")
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# ADD YIELD / HARVEST RECORD
# =========================================================

@router.post(
    "/{crop_id}/yield-records",
    response_model=CropYieldResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_yield_record(
    crop_id: int,
    payload: CropYieldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_crop_editor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    crop = get_crop_or_404(crop_id, db)
    ensure_crop_not_archived(crop)
    request_hash = request_fingerprint(payload)
    try:
        existing_command = begin_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="crop_harvest_create",
            request_hash=request_hash,
            user_id=current_user.id,
        )
        if existing_command is not None:
            existing = db.get(CropYieldRecord, existing_command.target_id)
            if existing is None:
                raise HTTPException(status_code=409, detail="The original idempotent harvest result is no longer available.")
            return existing

        harvest = record_harvest(
            db,
            crop=crop,
            harvest_date=payload.harvest_date,
            quantity_kg=payload.quantity_kg,
            harvest_type=payload.harvest_type or "",
            actor=current_user,
            performed_by_employee_id=payload.performed_by_employee_id,
            related_task_id=None,
            manual_reason=payload.manual_reason,
            quality=payload.quality,
            farm_use_quantity_kg=payload.farm_use_quantity_kg,
            damaged_quantity_kg=payload.damaged_quantity_kg,
            reserved_quantity_kg=payload.reserved_quantity_kg,
            notes=payload.notes,
            evidence_url=payload.evidence_url,
            final_harvest_confirmed=payload.final_harvest_confirmed,
        )
        record_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="crop_harvest_create",
            request_hash=request_hash,
            target_id=harvest.id,
            user_id=current_user.id,
        )
        evaluate_automatic_tasks(db, commit=False)
        db.commit()
        db.refresh(harvest)
        return harvest
    except Exception:
        db.rollback()
        raise


@router.post("/{crop_id}/confirm-ready", response_model=CropResponse)
def confirm_ready_for_harvest(
    crop_id: int,
    payload: CropReadyConfirmationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_crop_editor),
):
    crop = get_crop_or_404(crop_id, db)
    try:
        confirm_crop_ready(db, crop=crop, actor=current_user)
        db.commit()
        db.refresh(crop)
        return apply_automatic_progress(crop)
    except Exception:
        db.rollback()
        raise


@router.post("/{crop_id}/reopen", response_model=CropResponse)
def reopen_completed_crop(
    crop_id: int,
    payload: CropReopenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_crop_admin),
):
    crop = get_crop_or_404(crop_id, db)
    try:
        reopen_crop_cycle(
            db,
            crop=crop,
            actor=current_user,
            reason=payload.reason,
            new_status=payload.new_status,
        )
        db.commit()
        db.refresh(crop)
        return apply_automatic_progress(crop)
    except Exception:
        db.rollback()
        raise


# =========================================================
# ADD PEST / DISEASE RECORD
# =========================================================

@router.post(
    "/{crop_id}/pest-diseases",
    response_model=CropPestDiseaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pest_disease_record(
    crop_id: int,
    payload: CropPestDiseaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_crop_editor
    ),
):
    crop = get_crop_or_404(
        crop_id,
        db,
    )

    ensure_crop_not_archived(crop)

    if crop.status in TERMINAL_CROP_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pest or disease records cannot be added to a {crop.status.lower()} crop cycle.",
        )

    if payload.date_detected < crop.planting_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Detection date cannot be earlier than the crop planting date.",
        )

    if payload.date_detected > farm_today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Detection date cannot be in the future.",
        )

    record = CropPestDisease(
        crop_id=crop.id,
        date_detected=payload.date_detected,
        pest_disease_type=(
            payload.pest_disease_type.strip()
        ),
        severity=(
            payload.severity.strip()
            if payload.severity
            else None
        ),
        affected_area=(
            payload.affected_area.strip()
            if payload.affected_area
            else None
        ),
        notes=(
            payload.notes.strip()
            if payload.notes
            else None
        ),
        status="Active",
        recorded_by_user_id=current_user.id,
    )

    apply_automatic_progress(crop)
    crop.updated_at = datetime.now()

    db.add(record)
    db.flush()
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    db.refresh(record)

    return record


@router.put(
    "/{crop_id}/pest-diseases/{pest_id}",
    response_model=CropPestDiseaseResponse,
)
def update_pest_disease_record(
    crop_id: int,
    pest_id: int,
    payload: CropPestDiseaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_crop_editor),
):
    crop = get_crop_or_404(crop_id, db)
    ensure_crop_not_archived(crop)

    record = db.scalar(
        select(CropPestDisease).where(
            CropPestDisease.id == pest_id,
            CropPestDisease.crop_id == crop.id,
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pest or disease record not found for this crop.",
        )

    changes = payload.model_dump(exclude_unset=True)

    if "severity" in changes:
        record.severity = (changes["severity"] or "").strip() or None
    if "affected_area" in changes:
        record.affected_area = (changes["affected_area"] or "").strip() or None
    if "notes" in changes:
        record.notes = (changes["notes"] or "").strip() or None

    if "status" in changes:
        next_status = str(changes["status"] or "").strip()
        allowed_statuses = {"Active", "Under Treatment", "Resolved"}
        if next_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pest/disease status must be Active, Under Treatment, or Resolved.",
            )
        record.status = next_status
        record.resolved_at = datetime.now() if next_status == "Resolved" else None

    crop.updated_at = datetime.now()
    db.flush()
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    db.refresh(record)
    return record
