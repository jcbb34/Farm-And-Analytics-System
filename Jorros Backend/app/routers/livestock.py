from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete
import re
from uuid import uuid4
from datetime import date, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.services.monitoring_scheduler import annotate_monitoring
from app.services.resource_monitoring import validate_schedule
from app.core.database import get_db
from app.core.farm_time import farm_now_naive, farm_today
from app.core.dependencies import has_permission, require_permission
from app.models import (
    InventoryItem,
    InventoryStockRecord,
    FarmActivity,
    Employee,
    TaskSubmission,
    Livestock,
    LivestockVaccinationRecord,
    LivestockGrowthRecord,
    LivestockGrowthProfile,
    LivestockGrowthProfileStage,
    LivestockGrowthStageOverrideAudit,
    User,
)
from app.models.livestock import LivestockFeedingRecord, LivestockPen, LivestockTransaction
from app.routers.auth import get_current_user
from app.services.task_engine import evaluate_automatic_tasks
from app.services.task_assignment import recalculate_task_reassignment
from app.services.vaccination_summary import lock_vaccination_parent, update_vaccination_summary
from app.services.db_concurrency import acquire_transaction_lock
from app.services.livestock_audit import livestock_snapshot, record_livestock_change
from app.services.care_task_workflow import (
    generate_care_tasks_for_target,
    reconcile_same_template_future_schedule,
    resolve_future_pending_care_tasks,
    validate_care_template_for_target,
)
from app.services.care_protocol_summary import attach_care_protocol_summaries
from app.services.growth_profile_service import (
    assess_growth_values,
    assess_livestock_growth,
    biological_age_days,
)
from app.services.idempotency import (
    begin_creation_command,
    record_creation_command,
    request_fingerprint,
)
from app.schemas.livestock import (
    ALLOWED_GROWTH_STATUSES,
    ALLOWED_HEALTH_STATUSES,
    ALLOWED_VACCINATION_STATUSES,
    LivestockCreate,
    LivestockDetailsResponse,
    LivestockFeedingCreate,
    LivestockFeedingResponse,
    LivestockGrowthCreate,
    LivestockGrowthResponse,
    GrowthAssessmentPreviewRequest,
    GrowthAssessmentResponse,
    GrowthStageOverrideRequest,
    GrowthStageOverrideAuditResponse,
    GrowthProfileCreate,
    GrowthProfileResponse,
    LivestockResponse,
    LivestockUpdate,
    LivestockVaccinationCreate,
    LivestockVaccinationResponse,
    LivestockVaccinationScheduleResponse,
    PenCreate,
    PenUpdate,
    PenTransferCreate,
    BatchSplitCreate,
)


router = APIRouter(
    prefix="/api/v1/livestock",
    dependencies=[Depends(require_permission("livestock:view"))],
    tags=["Livestock"],
)


# =========================================================
# HELPERS
# =========================================================

def _require_livestock_permission(current_user: User, permission: str, message: str) -> User:
    if not has_permission(current_user, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )
    return current_user


def require_livestock_creator(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_livestock_permission(
        current_user,
        "livestock:create",
        "You do not have permission to create livestock records.",
    )


def require_livestock_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_livestock_permission(
        current_user,
        "livestock:update",
        "You do not have permission to manage livestock records.",
    )


def require_growth_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    if not (has_permission(current_user, "workforce:manage") or has_permission(current_user, "*")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or administrator access is required to override growth stages or manage growth profiles.",
        )
    return current_user


def require_livestock_archiver(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_livestock_permission(
        current_user,
        "livestock:archive",
        "You do not have permission to archive or restore livestock records.",
    )


def get_livestock_or_404(
    livestock_id: int,
    db: Session,
) -> Livestock:
    statement = (
        select(Livestock)
        .where(Livestock.id == livestock_id)
        .options(
            selectinload(Livestock.vaccination_records),
            selectinload(Livestock.feeding_records),
            selectinload(Livestock.growth_records),
        )
    )

    livestock = db.scalar(statement)

    if livestock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Livestock record not found.",
        )

    return livestock


def lock_livestock_or_404(
    livestock_id: int,
    db: Session,
) -> Livestock:
    statement = select(Livestock).where(Livestock.id == livestock_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "mssql":
        statement = statement.with_hint(
            Livestock,
            "WITH (UPDLOCK, ROWLOCK)",
            dialect_name="mssql",
        )
    else:
        statement = statement.with_for_update()
    livestock = db.scalar(statement)
    if livestock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Livestock record not found.",
        )
    return livestock


def ensure_not_archived(livestock: Livestock):
    if livestock.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Archived livestock records cannot be modified. "
                "Restore the record first."
            ),
        )


def normalize_feed_name(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def find_feed_inventory_item(
    db: Session,
    feed_type: str | None,
) -> InventoryItem | None:
    normalized = normalize_feed_name(feed_type)
    if not normalized:
        return None

    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.is_archived == False
        )
    ).all()

    for item in items:
        if normalize_feed_name(item.name) == normalized:
            return item

    return None


def get_feed_item_or_400(
    inventory_item_id: int,
    db: Session,
    *,
    for_update: bool = False,
) -> InventoryItem:
    item = lock_inventory_item(db, inventory_item_id) if for_update else db.get(InventoryItem, inventory_item_id)

    if item is None or item.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected feed inventory item is unavailable.",
        )
    if not is_feed_inventory_item(item):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected Inventory item is not a feed item.",
        )

    unit = (item.unit or "").strip().lower()
    if unit not in {"kg", "kgs", "kilogram", "kilograms"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feed inventory used for feeding must be stored in kilograms (kg).",
        )

    return item


def normalize_category(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())


def is_feed_inventory_item(item: InventoryItem) -> bool:
    category = normalize_category(item.category)
    name = normalize_category(item.name)
    return "feed" in category or "feed" in name


def is_vaccine_inventory_item(item: InventoryItem) -> bool:
    category = normalize_category(item.category)
    name = normalize_category(item.name)
    return any(token in category or token in name for token in ("vaccine", "vaccination"))


def lock_inventory_item(db: Session, inventory_item_id: int) -> InventoryItem | None:
    statement = select(InventoryItem).where(InventoryItem.id == inventory_item_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "mssql":
        statement = statement.with_hint(InventoryItem, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    else:
        statement = statement.with_for_update()
    return db.scalar(statement)


def get_pen_occupancy(db: Session, pen_id: int, exclude_livestock_id: int | None = None) -> int:
    statement = select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
        Livestock.pen_id == pen_id,
        Livestock.is_archived == False,
        Livestock.lifecycle_status == "Active",
    )
    if exclude_livestock_id is not None:
        statement = statement.where(Livestock.id != exclude_livestock_id)
    return int(db.scalar(statement) or 0)


def get_pen_or_400(
    db: Session,
    pen_id: int,
    *,
    animal_type: str | None = None,
    quantity: int = 0,
    exclude_livestock_id: int | None = None,
    enforce_capacity: bool = True,
) -> LivestockPen:
    acquire_transaction_lock(db, f"livestock-pen:{pen_id}")
    pen = db.get(LivestockPen, pen_id)
    if pen is None or pen.is_archived or pen.status not in {"Active", "Full"}:
        raise HTTPException(status_code=400, detail="Selected pen is not available.")

    allowed = normalize_category(pen.animal_type)
    requested = normalize_category(animal_type)
    if allowed and allowed not in {"all", "all livestock", "any"} and requested and allowed != requested:
        raise HTTPException(
            status_code=400,
            detail=f"{pen.name} is assigned to {pen.animal_type}, not {animal_type}.",
        )

    occupied = get_pen_occupancy(db, pen.id, exclude_livestock_id)
    if enforce_capacity and pen.capacity is not None and occupied + int(quantity or 0) > int(pen.capacity):
        available = max(0, int(pen.capacity) - occupied)
        raise HTTPException(
            status_code=400,
            detail=f"{pen.name} only has {available} available space(s).",
        )
    return pen


def health_status_from_counts(healthy: int, at_risk: int, sick: int, treatment: int) -> str:
    present = [
        label
        for label, count in (
            ("Healthy", healthy),
            ("At Risk", at_risk),
            ("Sick", sick),
            ("Under Treatment", treatment),
        )
        if int(count or 0) > 0
    ]
    if len(present) == 1:
        return present[0]
    return "Mixed" if present else "Healthy"


def validate_aggregate_counts(livestock: Livestock, changes: dict) -> None:
    quantity = int(changes.get("quantity", livestock.quantity) or 0)
    male = int(changes.get("male_quantity", livestock.male_quantity) or 0)
    female = int(changes.get("female_quantity", livestock.female_quantity) or 0)
    unknown = int(changes.get("unknown_sex_quantity", livestock.unknown_sex_quantity) or 0)
    sex_fields_present = any(key in changes for key in ("male_quantity", "female_quantity", "unknown_sex_quantity", "quantity"))
    if sex_fields_present and male + female + unknown != quantity:
        raise HTTPException(status_code=400, detail="Male + Female + Unknown quantities must equal the livestock quantity.")

    healthy = int(changes.get("healthy_quantity", livestock.healthy_quantity) or 0)
    at_risk = int(changes.get("at_risk_quantity", livestock.at_risk_quantity) or 0)
    sick = int(changes.get("sick_quantity", livestock.sick_quantity) or 0)
    treatment = int(changes.get("under_treatment_quantity", livestock.under_treatment_quantity) or 0)
    health_fields_present = any(
        key in changes
        for key in ("healthy_quantity", "at_risk_quantity", "sick_quantity", "under_treatment_quantity", "quantity")
    )
    if health_fields_present and healthy + at_risk + sick + treatment != quantity:
        raise HTTPException(
            status_code=400,
            detail="Healthy + At Risk + Sick + Under Treatment quantities must equal the livestock quantity.",
        )
    if health_fields_present:
        changes["health_status"] = health_status_from_counts(healthy, at_risk, sick, treatment)

def parse_feedings_per_day(value: str | None) -> int:
    text_value = (value or "").strip().lower()

    for separator in ("×", "x"):
        if separator in text_value:
            left = text_value.split(separator, 1)[0].strip()
            try:
                count = int(left)
                return max(1, min(count, 12))
            except ValueError:
                pass

    if "twice" in text_value:
        return 2
    if "three" in text_value or "thrice" in text_value:
        return 3
    if "four" in text_value:
        return 4

    return 1


def generate_animal_code(db: Session) -> str:
    acquire_transaction_lock(db, "code:livestock")
    existing_codes = db.scalars(
        select(Livestock.animal_code)
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
            highest_number = max(highest_number, number)
        except (TypeError, ValueError):
            continue

    return f"C-{highest_number + 1}"


def validate_status_values(data: dict):
    health_status = data.get("health_status")
    growth_status = data.get("growth_status")
    vaccination_status = data.get("vaccination_status")

    if (
        health_status is not None
        and health_status not in ALLOWED_HEALTH_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid livestock health status.",
        )

    if (
        growth_status is not None
        and growth_status not in ALLOWED_GROWTH_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid livestock growth status.",
        )

    if (
        vaccination_status is not None
        and vaccination_status not in ALLOWED_VACCINATION_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid livestock vaccination status.",
        )


def validate_livestock_dates(
    livestock: Livestock,
    changes: dict,
):
    date_of_birth = changes.get(
        "date_of_birth",
        livestock.date_of_birth,
    )
    date_acquired = changes.get(
        "date_acquired",
        livestock.date_acquired,
    )
    last_checkup = changes.get(
        "last_checkup",
        livestock.last_checkup,
    )
    next_vaccination = changes.get(
        "next_vaccination",
        livestock.next_vaccination,
    )

    if date_of_birth is not None and date_acquired < date_of_birth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date acquired cannot be earlier than date of birth/hatch.",
        )

    if last_checkup and date_of_birth is not None and last_checkup < date_of_birth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Last checkup cannot be earlier than date of birth.",
        )

    if next_vaccination and date_of_birth is not None and next_vaccination < date_of_birth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Next vaccination cannot be earlier than date of birth.",
        )


def validate_age_provenance(livestock: Livestock, changes: dict) -> None:
    dob = changes.get("date_of_birth", livestock.date_of_birth)
    estimated_days = changes.get("estimated_age_days", livestock.estimated_age_days)
    estimated_as_of = changes.get("estimated_age_as_of_date", livestock.estimated_age_as_of_date)
    confidence = changes.get("estimated_age_confidence", livestock.estimated_age_confidence)
    source = changes.get("estimated_age_source", livestock.estimated_age_source)
    if dob is None:
        if estimated_days is None:
            raise HTTPException(status_code=400, detail="Unknown birth/hatch date requires an estimated biological age in days.")
        if estimated_as_of is None:
            raise HTTPException(status_code=400, detail="Estimated age requires an estimation date.")
        if not confidence:
            raise HTTPException(status_code=400, detail="Estimated age requires a confidence level.")
        if not str(source or "").strip():
            raise HTTPException(status_code=400, detail="Estimated age requires a source or basis.")


def medical_history_status(vaccination_history: str | None, treatment_history: str | None) -> str:
    vaccination_known = bool(str(vaccination_history or "").strip())
    treatment_known = bool(str(treatment_history or "").strip())
    if vaccination_known and treatment_known:
        return "Known"
    if vaccination_known or treatment_known:
        return "Partial - Needs Review"
    return "Unknown - Needs Review"


def recalculate_growth_history(
    db: Session,
    livestock: Livestock,
) -> None:
    records = list(
        db.scalars(
            select(LivestockGrowthRecord)
            .where(LivestockGrowthRecord.livestock_id == livestock.id)
            .order_by(
                LivestockGrowthRecord.measurement_date.asc(),
                LivestockGrowthRecord.id.asc(),
            )
        ).all()
    )

    previous = None
    for record in records:
        if previous is None:
            record.previous_weight_kg = None
            record.weight_change_kg = None
            record.days_since_previous = None
            record.average_daily_gain_kg = None
        else:
            days = (record.measurement_date - previous.measurement_date).days
            change = round(
                float(record.weight_kg or 0) - float(previous.weight_kg or 0),
                2,
            )
            record.previous_weight_kg = float(previous.weight_kg or 0)
            record.weight_change_kg = change
            record.days_since_previous = days
            record.average_daily_gain_kg = (
                round(change / days, 4) if days > 0 else None
            )
        previous = record

    if records:
        livestock.weight_kg = float(records[-1].weight_kg or 0)
        livestock.min_weight_kg = records[-1].min_weight_kg
        livestock.max_weight_kg = records[-1].max_weight_kg
        livestock.updated_at = datetime.now()


def record_growth_measurement(
    db: Session,
    livestock: Livestock,
    measurement_date,
    weight_kg: float,
    recorded_by_user_id: int | None,
    notes: str | None = None,
    *,
    animals_measured: int | None = None,
    total_measured_weight_kg: float | None = None,
    min_weight_kg: float | None = None,
    max_weight_kg: float | None = None,
    measurement_basis: str = "Average",
) -> LivestockGrowthRecord:
    if livestock.date_of_birth is not None and measurement_date < livestock.date_of_birth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Growth measurement cannot be earlier than date of birth/hatch.",
        )
    if measurement_date < livestock.date_acquired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Growth measurement cannot be earlier than the date acquired.",
        )
    if measurement_date > farm_today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Growth measurement cannot be in the future.",
        )

    measured = int(animals_measured or (1 if int(livestock.quantity or 1) == 1 else livestock.quantity))
    if measured < 1 or measured > int(livestock.quantity or 1):
        raise HTTPException(
            status_code=400,
            detail=f"Animals measured must be between 1 and {livestock.quantity}.",
        )
    average_weight = float(weight_kg)
    if total_measured_weight_kg is not None:
        total_weight = float(total_measured_weight_kg)
        calculated = total_weight / measured
        if abs(calculated - average_weight) > 0.05:
            raise HTTPException(
                status_code=400,
                detail=f"Average weight should be approximately {calculated:.2f} kg for the entered total measured weight.",
            )
    else:
        total_weight = round(average_weight * measured, 3)

    minimum = float(min_weight_kg) if min_weight_kg is not None else average_weight
    maximum = float(max_weight_kg) if max_weight_kg is not None else average_weight
    if minimum > maximum or average_weight < minimum or average_weight > maximum:
        raise HTTPException(
            status_code=400,
            detail="Minimum weight must be <= average weight <= maximum weight.",
        )

    existing = db.scalar(
        select(LivestockGrowthRecord).where(
            LivestockGrowthRecord.livestock_id == livestock.id,
            LivestockGrowthRecord.measurement_date == measurement_date,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A growth measurement already exists for this date. Historical measurements are immutable; record a new measurement date instead.",
        )

    record = LivestockGrowthRecord(
        livestock_id=livestock.id,
        measurement_date=measurement_date,
    )
    assessment = assess_livestock_growth(
        db, livestock, as_of_date=measurement_date, actual_weight_kg=average_weight
    )
    record.biological_age_days = assessment.get("age_days")
    record.expected_stage = assessment.get("suggested_stage")
    record.expected_min_weight_kg = assessment.get("expected_min_weight_kg")
    record.expected_max_weight_kg = assessment.get("expected_max_weight_kg")
    record.growth_profile_family_code = assessment.get("profile_family_code")
    record.growth_profile_version = assessment.get("profile_version")
    record.growth_profile_status = assessment.get("profile_status")
    record.deviation_status = assessment.get("deviation_status")
    record.deviation_message = assessment.get("deviation_message")
    record.weight_kg = average_weight
    record.animals_measured = measured
    record.total_measured_weight_kg = total_weight
    record.min_weight_kg = minimum
    record.max_weight_kg = maximum
    record.measurement_basis = measurement_basis.strip() or ("Sample" if measured < livestock.quantity else "Full Batch")
    record.notes = notes.strip() if notes else None
    record.recorded_by_user_id = recorded_by_user_id

    db.add(record)

    db.flush()
    recalculate_growth_history(db, livestock)
    return record


# =========================================================
# GET ALL LIVESTOCK
# =========================================================

@router.get(
    "",
    response_model=list[LivestockResponse],
)
def list_livestock(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = select(Livestock).order_by(Livestock.id.desc())

    if not include_archived:
        statement = statement.where(
            Livestock.is_archived == False
        )

    return annotate_monitoring(db, attach_care_protocol_summaries(db, list(db.scalars(statement).all())), "Livestock")


# =========================================================
# LIVESTOCK PEN MANAGEMENT
# =========================================================


def serialize_pen(db: Session, pen: LivestockPen) -> dict:
    occupied = get_pen_occupancy(db, pen.id)
    available = None if pen.capacity is None else max(0, int(pen.capacity) - occupied)
    effective_status = pen.status
    if pen.status == "Active" and pen.capacity is not None and occupied >= int(pen.capacity):
        effective_status = "Full"
    return {
        "id": pen.id,
        "name": pen.name,
        "purpose": pen.purpose,
        "animal_type": pen.animal_type,
        "capacity": pen.capacity,
        "current_occupancy": occupied,
        "available_capacity": available,
        "location_area": pen.location_area,
        "status": effective_status,
        "notes": pen.notes,
        "is_archived": pen.is_archived,
        "created_at": pen.created_at,
        "updated_at": pen.updated_at,
    }


@router.get("/pens")
def list_livestock_pens(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = select(LivestockPen).order_by(LivestockPen.name.asc())
    if not include_archived:
        statement = statement.where(LivestockPen.is_archived == False)
    return [serialize_pen(db, pen) for pen in db.scalars(statement).all()]


@router.post("/pens", status_code=status.HTTP_201_CREATED)
def create_livestock_pen(
    payload: PenCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_livestock_editor),
):
    name = payload.name.strip()
    duplicate = db.scalar(select(LivestockPen).where(func.lower(LivestockPen.name) == name.lower()))
    if duplicate is not None:
        raise HTTPException(status_code=400, detail="A livestock pen with this name already exists.")
    pen = LivestockPen(
        name=name,
        purpose=payload.purpose.strip() or "General",
        animal_type=(payload.animal_type.strip() if payload.animal_type else None),
        capacity=payload.capacity,
        location_area=(payload.location_area.strip() if payload.location_area else None),
        status=payload.status.strip() or "Active",
        notes=(payload.notes.strip() if payload.notes else None),
        is_archived=False,
    )
    db.add(pen)
    db.commit()
    db.refresh(pen)
    return serialize_pen(db, pen)


@router.put("/pens/{pen_id}")
def update_livestock_pen(
    pen_id: int,
    payload: PenUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_livestock_editor),
):
    pen = db.get(LivestockPen, pen_id)
    if pen is None:
        raise HTTPException(status_code=404, detail="Livestock pen not found.")
    occupied = get_pen_occupancy(db, pen.id)
    if payload.capacity is not None and int(payload.capacity) < occupied:
        raise HTTPException(
            status_code=400,
            detail=f"Capacity cannot be lower than the current occupancy of {occupied} animal(s).",
        )
    if payload.status in {"Closed", "Inactive"} and occupied > 0:
        raise HTTPException(status_code=400, detail="Move all active livestock out of this pen before closing it.")
    name = payload.name.strip()
    duplicate = db.scalar(
        select(LivestockPen).where(
            func.lower(LivestockPen.name) == name.lower(),
            LivestockPen.id != pen.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=400, detail="A livestock pen with this name already exists.")
    old_name = pen.name
    pen.name = name
    pen.purpose = payload.purpose.strip() or "General"
    pen.animal_type = payload.animal_type.strip() if payload.animal_type else None
    pen.capacity = payload.capacity
    pen.location_area = payload.location_area.strip() if payload.location_area else None
    pen.status = payload.status.strip() or "Active"
    pen.notes = payload.notes.strip() if payload.notes else None
    pen.updated_at = datetime.now()
    if old_name != pen.name:
        for animal in db.scalars(select(Livestock).where(Livestock.pen_id == pen.id)).all():
            animal.pen_location = pen.name
    db.commit()
    db.refresh(pen)
    return serialize_pen(db, pen)


@router.post("/{livestock_id}/transfer-pen", response_model=LivestockResponse)
def transfer_livestock_pen(
    livestock_id: int,
    payload: PenTransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_editor),
):
    livestock = lock_livestock_or_404(livestock_id, db)
    ensure_not_archived(livestock)
    if payload.event_date < livestock.date_acquired:
        raise HTTPException(status_code=400, detail="Transfer date cannot be earlier than the livestock acquisition date.")
    destination = get_pen_or_400(
        db,
        payload.pen_id,
        animal_type=livestock.animal_type,
        quantity=livestock.quantity,
        exclude_livestock_id=livestock.id,
    )
    if destination.id == livestock.pen_id:
        raise HTTPException(status_code=400, detail="Livestock is already assigned to this pen.")
    old_pen_id = livestock.pen_id
    old_location = livestock.pen_location
    livestock.pen_id = destination.id
    livestock.pen_location = destination.name
    livestock.updated_at = datetime.now()
    db.add(
        LivestockTransaction(
            livestock_id=livestock.id,
            transaction_type="Pen Transfer",
            quantity=livestock.quantity,
            from_livestock_id=livestock.id,
            to_livestock_id=livestock.id,
            from_pen_id=old_pen_id,
            to_pen_id=destination.id,
            event_date=payload.event_date,
            reason=(payload.reason.strip() if payload.reason else f"Transferred from {old_location} to {destination.name}."),
            recorded_by_user_id=current_user.id,
        )
    )
    db.commit()
    db.refresh(livestock)
    return livestock


@router.post("/{livestock_id}/split-batch", response_model=LivestockResponse, status_code=status.HTTP_201_CREATED)
def split_livestock_batch(
    livestock_id: int,
    payload: BatchSplitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_editor),
):
    source = lock_livestock_or_404(livestock_id, db)
    ensure_not_archived(source)
    if payload.quantity >= source.quantity:
        raise HTTPException(status_code=400, detail="Split quantity must be smaller than the source batch quantity.")
    for requested, available, label in (
        (payload.male_quantity, source.male_quantity, "male"),
        (payload.female_quantity, source.female_quantity, "female"),
        (payload.unknown_sex_quantity, source.unknown_sex_quantity, "unknown-sex"),
        (payload.healthy_quantity, source.healthy_quantity, "healthy"),
        (payload.at_risk_quantity, source.at_risk_quantity, "at-risk"),
        (payload.sick_quantity, source.sick_quantity, "sick"),
        (payload.under_treatment_quantity, source.under_treatment_quantity, "under-treatment"),
    ):
        if int(requested) > int(available or 0):
            raise HTTPException(status_code=400, detail=f"Not enough {label} animals are available in this batch.")

    destination = None
    if payload.pen_id is not None:
        same_pen = int(payload.pen_id) == int(source.pen_id or 0)
        destination = get_pen_or_400(
            db,
            payload.pen_id,
            animal_type=source.animal_type,
            quantity=0 if same_pen else payload.quantity,
            enforce_capacity=not same_pen,
        )
    new_pen_id = destination.id if destination else source.pen_id
    new_pen_location = destination.name if destination else source.pen_location

    source.quantity -= payload.quantity
    source.male_quantity -= payload.male_quantity
    source.female_quantity -= payload.female_quantity
    source.unknown_sex_quantity -= payload.unknown_sex_quantity
    source.healthy_quantity -= payload.healthy_quantity
    source.at_risk_quantity -= payload.at_risk_quantity
    source.sick_quantity -= payload.sick_quantity
    source.under_treatment_quantity -= payload.under_treatment_quantity
    source.health_status = health_status_from_counts(
        source.healthy_quantity,
        source.at_risk_quantity,
        source.sick_quantity,
        source.under_treatment_quantity,
    )
    source.updated_at = datetime.now()

    sex = "Mixed"
    if payload.male_quantity == payload.quantity:
        sex = "Male"
    elif payload.female_quantity == payload.quantity:
        sex = "Female"

    split = Livestock(
        animal_code=generate_animal_code(db),
        record_name=(payload.record_name.strip() if payload.record_name else f"{source.record_name} Split"),
        animal_type=source.animal_type,
        breed=source.breed,
        quantity=payload.quantity,
        sex=sex,
        record_type="Batch",
        lifecycle_status="Active",
        pen_id=new_pen_id,
        origin_livestock_id=source.id,
        male_quantity=payload.male_quantity,
        female_quantity=payload.female_quantity,
        unknown_sex_quantity=payload.unknown_sex_quantity,
        date_of_birth=source.date_of_birth,
        weight_kg=source.weight_kg,
        min_weight_kg=source.min_weight_kg,
        max_weight_kg=source.max_weight_kg,
        pen_location=new_pen_location,
        health_status=health_status_from_counts(payload.healthy_quantity, payload.at_risk_quantity, payload.sick_quantity, payload.under_treatment_quantity),
        healthy_quantity=payload.healthy_quantity,
        at_risk_quantity=payload.at_risk_quantity,
        sick_quantity=payload.sick_quantity,
        under_treatment_quantity=payload.under_treatment_quantity,
        growth_status=source.growth_status,
        production_purpose=source.production_purpose,
        last_checkup=source.last_checkup,
        health_notes=source.health_notes,
        vaccination_status=source.vaccination_status,
        next_vaccination=source.next_vaccination,
        feed_times=source.feed_times,
        feed_type=source.feed_type,
        daily_feed_kg=source.daily_feed_kg,
        feeding_notes=source.feeding_notes,
        feed_inventory_item_id=source.feed_inventory_item_id,
        production_output=source.production_output,
        age_is_estimated=source.age_is_estimated,
        estimated_age_days=source.estimated_age_days,
        estimated_age_as_of_date=source.estimated_age_as_of_date,
        estimated_age_confidence=source.estimated_age_confidence,
        estimated_age_source=source.estimated_age_source,
        acquisition_stage=source.acquisition_stage,
        acquisition_vaccination_history=source.acquisition_vaccination_history,
        acquisition_treatment_history=source.acquisition_treatment_history,
        medical_history_status=source.medical_history_status,
        date_acquired=source.date_acquired,
        acquired_from=source.acquired_from,
        is_archived=False,
        created_by_user_id=current_user.id,
    )
    db.add(split)
    db.flush()
    db.add(
        LivestockTransaction(
            livestock_id=split.id,
            transaction_type="Batch Split",
            quantity=payload.quantity,
            from_livestock_id=source.id,
            to_livestock_id=split.id,
            from_pen_id=source.pen_id,
            to_pen_id=new_pen_id,
            event_date=payload.event_date,
            reason=(payload.reason.strip() if payload.reason else "Livestock batch split."),
            recorded_by_user_id=current_user.id,
        )
    )
    db.commit()
    db.refresh(split)
    return split


# =========================================================
# VACCINATION SCHEDULE (WORKFORCE-LINKED)
# =========================================================

def _is_vaccination_activity(task: FarmActivity) -> bool:
    text_value = " ".join([
        str(task.name or ""), str(task.category or ""), str(task.source_type or "")
    ]).lower()
    return (
        task.source_type == "livestock_vaccination"
        or "vaccin" in text_value
        or "booster" in text_value
    )


@router.get(
    "/{livestock_id}/vaccination-schedule",
    response_model=list[LivestockVaccinationScheduleResponse],
)
def get_livestock_vaccination_schedule(
    livestock_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    livestock = db.get(Livestock, livestock_id)
    if livestock is None:
        raise HTTPException(status_code=404, detail="Livestock record not found.")

    task_rows = list(db.scalars(
        select(FarmActivity).where(
            FarmActivity.source_module == "Livestock",
            FarmActivity.source_record_id == livestock_id,
            FarmActivity.is_archived == False,
        ).order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
    ).all())
    task_rows = [row for row in task_rows if _is_vaccination_activity(row)]

    task_ids = [row.id for row in task_rows]
    latest_submission: dict[int, TaskSubmission] = {}
    if task_ids:
        submissions = list(db.scalars(
            select(TaskSubmission)
            .where(TaskSubmission.activity_id.in_(task_ids))
            .order_by(TaskSubmission.activity_id, TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc())
        ).all())
        for row in submissions:
            latest_submission.setdefault(row.activity_id, row)

    employee_ids = {
        int(row.assigned_employee_id) for row in task_rows if row.assigned_employee_id
    }
    employee_ids.update(
        int(row.employee_id) for row in latest_submission.values() if row.employee_id
    )
    if livestock.assigned_employee_id:
        employee_ids.add(int(livestock.assigned_employee_id))
    employees = {
        row.id: row
        for row in db.scalars(select(Employee).where(Employee.id.in_(employee_ids))).all()
    } if employee_ids else {}

    inventory_ids = {
        int(row.planned_inventory_item_id) for row in task_rows if row.planned_inventory_item_id
    }
    inventory = {
        row.id: row
        for row in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(inventory_ids))).all()
    } if inventory_ids else {}

    result: list[LivestockVaccinationScheduleResponse] = []
    scheduled_dates: set[date] = set()
    for task in task_rows:
        scheduled_dates.add(task.activity_date)
        submission = latest_submission.get(task.id)
        assigned_employee = employees.get(task.assigned_employee_id) if task.assigned_employee_id else None
        performer = employees.get(submission.employee_id) if submission else None
        item = inventory.get(task.planned_inventory_item_id) if task.planned_inventory_item_id else None
        result.append(LivestockVaccinationScheduleResponse(
            task_id=task.id,
            activity_code=task.activity_code,
            title=task.name,
            scheduled_date=task.activity_date,
            status=task.status,
            assigned_employee_id=task.assigned_employee_id,
            assigned_employee_name=assigned_employee.full_name if assigned_employee else None,
            inventory_item_id=item.id if item else None,
            inventory_item_name=item.name if item else None,
            planned_quantity=float(task.planned_quantity) if task.planned_quantity is not None else None,
            planned_unit=item.unit if item else task.planned_unit,
            actual_quantity=float(submission.actual_quantity) if submission and submission.actual_quantity is not None else None,
            actual_unit=submission.actual_unit if submission else None,
            performed_by=performer.full_name if performer else None,
            completed_at=task.completed_at,
            source="Task Management",
        ))

    # Keep the livestock's own scheduled date visible even before Task Management
    # generates the reminder (automatic tasks are only created close to due date).
    if livestock.next_vaccination and livestock.next_vaccination not in scheduled_dates:
        assigned_employee = employees.get(livestock.assigned_employee_id) if livestock.assigned_employee_id else None
        derived_status = livestock.vaccination_status or "Scheduled"
        if derived_status == "Up to Date":
            derived_status = "Scheduled"
        result.append(LivestockVaccinationScheduleResponse(
            title=f"Vaccination schedule — {livestock.record_name}",
            scheduled_date=livestock.next_vaccination,
            status=derived_status,
            assigned_employee_id=livestock.assigned_employee_id,
            assigned_employee_name=assigned_employee.full_name if assigned_employee else None,
            source="Livestock Schedule",
        ))

    result.sort(key=lambda row: (row.scheduled_date, row.task_id or 0))
    return result


# =========================================================
# VERSIONED GROWTH PROFILES + BACKEND ASSESSMENT
# =========================================================

def _profile_response(profile: LivestockGrowthProfile) -> GrowthProfileResponse:
    return GrowthProfileResponse.model_validate(profile)


def _replace_profile_stages(db: Session, profile: LivestockGrowthProfile, stages) -> None:
    # Keep the ORM relationship synchronized with the rows being written.
    # SessionLocal uses expire_on_commit=False, so inserting only by profile_id
    # would otherwise leave a previously loaded profile.stages collection stale.
    profile.stages.clear()
    for stage in stages:
        profile.stages.append(
            LivestockGrowthProfileStage(
                sequence_number=stage.sequence_number,
                stage_name=stage.stage_name,
                age_start_days=stage.age_start_days,
                age_end_days=stage.age_end_days,
                expected_min_weight_kg=stage.expected_min_weight_kg,
                expected_max_weight_kg=stage.expected_max_weight_kg,
                notes=stage.notes.strip() if stage.notes else None,
            )
        )
    db.flush()


def _apply_profile_payload(profile: LivestockGrowthProfile, payload: GrowthProfileCreate) -> None:
    profile.name = payload.name.strip()
    profile.species = payload.species.strip()
    profile.breed_strain = payload.breed_strain.strip() if payload.breed_strain else None
    profile.production_purpose = payload.production_purpose.strip() if payload.production_purpose else None
    profile.sex = payload.sex.strip() if payload.sex else None
    profile.source_title = payload.source_title.strip() if payload.source_title else None
    profile.source_url = payload.source_url.strip() if payload.source_url else None
    profile.source_notes = payload.source_notes.strip() if payload.source_notes else None
    profile.last_reviewed_date = payload.last_reviewed_date
    profile.approval_status = payload.approval_status.strip()
    profile.effective_from = payload.effective_from
    profile.effective_to = payload.effective_to
    profile.updated_at = datetime.now()


@router.post(
    "/growth-assessment/preview",
    response_model=GrowthAssessmentResponse,
)
def preview_growth_assessment(
    payload: GrowthAssessmentPreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = assess_growth_values(
        db,
        species=payload.animal_type,
        breed=payload.breed,
        production_purpose=payload.production_purpose,
        sex=payload.sex,
        date_of_birth=payload.date_of_birth,
        estimated_age_days=payload.estimated_age_days,
        estimated_age_as_of_date=payload.estimated_age_as_of_date,
        actual_weight_kg=payload.weight_kg,
        as_of_date=payload.as_of_date,
    )
    return GrowthAssessmentResponse(**result)


@router.get(
    "/growth-profiles",
    response_model=list[GrowthProfileResponse],
)
def list_growth_profiles(
    include_all_versions: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = list(
        db.scalars(
            select(LivestockGrowthProfile)
            .options(selectinload(LivestockGrowthProfile.stages))
            .order_by(
                LivestockGrowthProfile.species,
                LivestockGrowthProfile.breed_strain,
                LivestockGrowthProfile.profile_family_code,
                LivestockGrowthProfile.version.desc(),
            )
        ).all()
    )
    if not include_all_versions:
        latest: dict[str, LivestockGrowthProfile] = {}
        for row in rows:
            if row.status in {"Published", "Draft"} and row.is_active:
                latest.setdefault(row.profile_family_code, row)
        rows = list(latest.values())
    return [_profile_response(row) for row in rows]


@router.post(
    "/growth-profiles",
    response_model=GrowthProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_growth_profile(
    payload: GrowthProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_growth_manager),
):
    profile = LivestockGrowthProfile(
        profile_family_code=f"GROW-{uuid4().hex[:12].upper()}",
        version=1,
        status="Draft",
        is_active=True,
        created_by_user_id=current_user.id,
    )
    _apply_profile_payload(profile, payload)
    db.add(profile)
    db.flush()
    _replace_profile_stages(db, profile, payload.stages)
    db.commit()
    db.refresh(profile)
    profile = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile.id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    return _profile_response(profile)


@router.put(
    "/growth-profiles/{profile_id}",
    response_model=GrowthProfileResponse,
)
def update_growth_profile(
    profile_id: int,
    payload: GrowthProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_growth_manager),
):
    profile = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile_id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Growth profile not found.")
    if profile.status != "Draft":
        raise HTTPException(status_code=409, detail="Published/superseded growth profiles are immutable. Create a new version instead.")
    _apply_profile_payload(profile, payload)
    _replace_profile_stages(db, profile, payload.stages)
    db.commit()
    profile = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile_id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    return _profile_response(profile)


@router.post(
    "/growth-profiles/{profile_id}/new-version",
    response_model=GrowthProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_growth_profile_version(
    profile_id: int,
    payload: GrowthProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_growth_manager),
):
    source = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile_id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Growth profile not found.")
    acquire_transaction_lock(db, f"growth-profile-version:{source.profile_family_code}")
    max_version = db.scalar(
        select(func.max(LivestockGrowthProfile.version)).where(
            LivestockGrowthProfile.profile_family_code == source.profile_family_code
        )
    ) or 0
    profile = LivestockGrowthProfile(
        profile_family_code=source.profile_family_code,
        version=int(max_version) + 1,
        status="Draft",
        is_active=True,
        created_by_user_id=current_user.id,
    )
    _apply_profile_payload(profile, payload)
    db.add(profile)
    db.flush()
    _replace_profile_stages(db, profile, payload.stages)
    db.commit()
    profile = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile.id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    return _profile_response(profile)


@router.post(
    "/growth-profiles/{profile_id}/publish",
    response_model=GrowthProfileResponse,
)
def publish_growth_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_growth_manager),
):
    profile = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile_id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Growth profile not found.")
    if profile.status != "Draft":
        raise HTTPException(status_code=409, detail="Only Draft growth profiles can be published.")
    if not profile.source_title or not profile.source_url or not profile.last_reviewed_date:
        raise HTTPException(status_code=400, detail="Publishing requires source title, source URL, and last-reviewed date.")
    if "needs" in str(profile.approval_status or "").lower() or "draft" in str(profile.approval_status or "").lower():
        raise HTTPException(status_code=400, detail="Expert approval is required before publishing a growth profile.")
    acquire_transaction_lock(db, f"growth-profile-publish:{profile.profile_family_code}")
    previous = list(
        db.scalars(
            select(LivestockGrowthProfile).where(
                LivestockGrowthProfile.profile_family_code == profile.profile_family_code,
                LivestockGrowthProfile.status == "Published",
                LivestockGrowthProfile.id != profile.id,
            )
        ).all()
    )
    for row in previous:
        row.status = "Superseded"
        row.is_active = False
    profile.status = "Published"
    profile.is_active = True
    profile.published_by_user_id = current_user.id
    profile.published_at = datetime.now()
    db.commit()
    return _profile_response(profile)


@router.post(
    "/growth-profiles/{profile_id}/deactivate",
    response_model=GrowthProfileResponse,
)
def deactivate_growth_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_growth_manager),
):
    profile = db.scalar(
        select(LivestockGrowthProfile)
        .where(LivestockGrowthProfile.id == profile_id)
        .options(selectinload(LivestockGrowthProfile.stages))
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Growth profile not found.")
    profile.status = "Inactive"
    profile.is_active = False
    profile.updated_at = datetime.now()
    db.commit()
    return _profile_response(profile)


# =========================================================
# GET ONE LIVESTOCK RECORD
# =========================================================

@router.get(
    "/{livestock_id}",
    response_model=LivestockDetailsResponse,
)
def get_livestock(
    livestock_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return annotate_monitoring(db, attach_care_protocol_summaries(db, [get_livestock_or_404(livestock_id, db)]), "Livestock")[0]


@router.get(
    "/{livestock_id}/growth-assessment",
    response_model=GrowthAssessmentResponse,
)
def get_growth_assessment(
    livestock_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    livestock = get_livestock_or_404(livestock_id, db)
    result = assess_livestock_growth(db, livestock)
    result["current_stage"] = livestock.growth_status
    return GrowthAssessmentResponse(**result)


@router.get(
    "/{livestock_id}/growth-stage-overrides",
    response_model=list[GrowthStageOverrideAuditResponse],
)
def list_growth_stage_overrides(
    livestock_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_livestock_or_404(livestock_id, db)
    return list(
        db.scalars(
            select(LivestockGrowthStageOverrideAudit)
            .where(LivestockGrowthStageOverrideAudit.livestock_id == livestock_id)
            .order_by(LivestockGrowthStageOverrideAudit.created_at.desc(), LivestockGrowthStageOverrideAudit.id.desc())
        ).all()
    )


@router.post(
    "/{livestock_id}/growth-stage-override",
    response_model=GrowthAssessmentResponse,
)
def override_growth_stage(
    livestock_id: int,
    payload: GrowthStageOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_growth_manager),
):
    livestock = lock_livestock_or_404(livestock_id, db)
    ensure_not_archived(livestock)
    assessment = assess_livestock_growth(db, livestock)
    previous_stage = livestock.growth_status
    livestock.growth_status = payload.stage
    livestock.updated_at = datetime.now()
    db.add(
        LivestockGrowthStageOverrideAudit(
            livestock_id=livestock.id,
            previous_stage=previous_stage,
            suggested_stage=assessment.get("suggested_stage"),
            override_stage=payload.stage,
            reason=payload.reason.strip(),
            overridden_by_user_id=current_user.id,
        )
    )
    db.commit()
    result = assess_livestock_growth(db, livestock)
    result["current_stage"] = livestock.growth_status
    return GrowthAssessmentResponse(**result)


# =========================================================
# CREATE LIVESTOCK
# =========================================================

@router.post(
    "",
    response_model=LivestockResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_livestock(
    payload: LivestockCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_creator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_hash = request_fingerprint(payload)
    try:
        existing_command = begin_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="livestock_create",
            request_hash=request_hash,
            user_id=current_user.id,
        )
        if existing_command is not None:
            existing_livestock = db.get(Livestock, existing_command.target_id)
            if existing_livestock is None:
                raise HTTPException(
                    status_code=409,
                    detail="The original idempotent livestock result is no longer available.",
                )
            return existing_livestock

        data = payload.model_dump()
        validate_status_values(data)

        if payload.feed_inventory_item_id is not None:
            feed_item = get_feed_item_or_400(payload.feed_inventory_item_id, db)
            feed_inventory_item_id = feed_item.id
            feed_type = feed_item.name
        else:
            feed_inventory_item_id = None
            feed_type = None
            if float(payload.daily_feed_kg or 0) > 0 or (payload.feed_times or "").strip():
                raise HTTPException(
                    status_code=400,
                    detail="Select an exact Feed item from Inventory before saving a feeding schedule.",
                )

        if payload.pen_id is not None:
            pen = get_pen_or_400(
                db,
                payload.pen_id,
                animal_type=payload.animal_type,
                quantity=payload.quantity,
            )
        else:
            pen = db.scalar(
                select(LivestockPen).where(
                    func.lower(LivestockPen.name) == payload.pen_location.strip().lower(),
                    LivestockPen.is_archived == False,
                )
            )
            if pen is None:
                raise HTTPException(
                    status_code=400,
                    detail="Choose an existing livestock pen. Create new pens from Manage Pens first.",
                )
            pen = get_pen_or_400(
                db,
                pen.id,
                animal_type=payload.animal_type,
                quantity=payload.quantity,
            )

        livestock = Livestock(
            monitoring_enabled=payload.monitoring_enabled,
            monitoring_start_date=payload.monitoring_start_date,
            monitoring_end_date=payload.monitoring_end_date,
            monitoring_frequency_days=payload.monitoring_frequency_days,
            animal_code=generate_animal_code(db),
            record_name=payload.record_name.strip(),
            animal_type=payload.animal_type.strip(),
            breed=payload.breed.strip(),
            quantity=payload.quantity,
            sex=payload.sex.strip(),
            record_type=payload.record_type,
            lifecycle_status=payload.lifecycle_status,
            pen_id=pen.id,
            male_quantity=payload.male_quantity,
            female_quantity=payload.female_quantity,
            unknown_sex_quantity=payload.unknown_sex_quantity,
            date_of_birth=payload.date_of_birth,
            weight_kg=payload.weight_kg,
            min_weight_kg=payload.min_weight_kg or payload.weight_kg,
            max_weight_kg=payload.max_weight_kg or payload.weight_kg,
            pen_location=pen.name,
            health_status=payload.health_status,
            healthy_quantity=payload.healthy_quantity,
            at_risk_quantity=payload.at_risk_quantity,
            sick_quantity=payload.sick_quantity,
            under_treatment_quantity=payload.under_treatment_quantity,
            growth_status=payload.growth_status,
            production_purpose=payload.production_purpose,
            last_checkup=payload.last_checkup,
            health_notes=payload.health_notes.strip() if payload.health_notes else None,
            vaccination_status=payload.vaccination_status,
            next_vaccination=payload.next_vaccination,
            feed_times=payload.feed_times.strip() if payload.feed_times else None,
            feed_type=feed_type,
            daily_feed_kg=payload.daily_feed_kg,
            feeding_notes=payload.feeding_notes.strip() if payload.feeding_notes else None,
            feed_inventory_item_id=feed_inventory_item_id,
            production_output=payload.production_output.strip() if payload.production_output else None,
            age_is_estimated=payload.age_is_estimated,
            estimated_age_days=payload.estimated_age_days,
            estimated_age_as_of_date=payload.estimated_age_as_of_date,
            estimated_age_confidence=payload.estimated_age_confidence,
            estimated_age_source=payload.estimated_age_source.strip() if payload.estimated_age_source else None,
            acquisition_stage=payload.acquisition_stage or payload.growth_status,
            acquisition_vaccination_history=payload.acquisition_vaccination_history.strip() if payload.acquisition_vaccination_history else None,
            acquisition_treatment_history=payload.acquisition_treatment_history.strip() if payload.acquisition_treatment_history else None,
            medical_history_status=medical_history_status(payload.acquisition_vaccination_history, payload.acquisition_treatment_history),
            feeding_plan_name=payload.feeding_plan_name.strip() if payload.feeding_plan_name else None,
            assigned_employee_id=payload.assigned_employee_id,
            care_template_id=payload.care_template_id,
            date_acquired=payload.date_acquired,
            acquired_from=payload.acquired_from.strip() if payload.acquired_from else None,
            is_archived=False,
            created_by_user_id=current_user.id,
        )

        template = None
        if payload.care_template_id is not None:
            template = validate_care_template_for_target(
                db,
                template_id=payload.care_template_id,
                module="Livestock",
                target=livestock,
            )

        validate_schedule(livestock, "Livestock")
        db.add(livestock)
        db.flush()

        record_growth_measurement(
            db,
            livestock,
            farm_today(),
            float(payload.weight_kg),
            current_user.id,
            "Initial average weight recorded when the livestock record was created.",
            animals_measured=payload.quantity,
            total_measured_weight_kg=float(payload.weight_kg) * int(payload.quantity),
            min_weight_kg=float(payload.min_weight_kg or payload.weight_kg),
            max_weight_kg=float(payload.max_weight_kg or payload.weight_kg),
            measurement_basis="Full Batch" if payload.quantity > 1 else "Individual",
        )

        if template is not None:
            generate_care_tasks_for_target(
                db,
                module="Livestock",
                target=livestock,
                template=template,
                current_user=current_user,
                base_date=livestock.date_acquired,
            )

        record_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="livestock_create",
            request_hash=request_hash,
            target_id=livestock.id,
            user_id=current_user.id,
        )
        db.flush()
        evaluate_automatic_tasks(db, commit=False)
        annotate_monitoring(db, [livestock], "Livestock")
        record_livestock_change(db, livestock, current_user, action="Created livestock record")
        db.commit()
        db.refresh(livestock)
        return livestock
    except Exception:
        db.rollback()
        raise


# =========================================================
# UPDATE LIVESTOCK
# =========================================================

@router.put(
    "/{livestock_id}",
    response_model=LivestockResponse,
)
def update_livestock(
    livestock_id: int,
    payload: LivestockUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_editor),
):
    try:
        return _update_livestock(livestock_id, payload, db, current_user)
    except Exception:
        db.rollback()
        raise


def _update_livestock(livestock_id, payload, db, current_user):
    livestock = lock_livestock_or_404(livestock_id, db)
    ensure_not_archived(livestock)
    before = livestock_snapshot(livestock)

    changes = payload.model_dump(exclude_unset=True)
    future_care_task_action = changes.pop("future_care_task_action", None)
    old_care_template_id = livestock.care_template_id
    old_date_acquired = livestock.date_acquired
    if (
        "care_template_id" in changes
        and changes.get("care_template_id") is None
        and old_care_template_id is not None
        and future_care_task_action not in {"keep", "resolve"}
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Removing a livestock care protocol requires future_care_task_action "
                "to be 'keep' or 'resolve'."
            ),
        )
    old_weight = float(livestock.weight_kg or 0)
    if "growth_status" in changes and changes.get("growth_status") != livestock.growth_status:
        raise HTTPException(
            status_code=400,
            detail="Growth stage changes require the manager stage-override action with a reason so the change is audited.",
        )
    validate_status_values(changes)
    validate_livestock_dates(livestock, changes)
    validate_age_provenance(livestock, changes)
    validate_aggregate_counts(livestock, changes)

    if "feed_inventory_item_id" in changes:
        item_id = changes.get("feed_inventory_item_id")
        if item_id is None:
            changes["feed_type"] = None
            if float(changes.get("daily_feed_kg", livestock.daily_feed_kg) or 0) > 0:
                raise HTTPException(status_code=400, detail="A feeding schedule with a daily ration requires a linked Feed Inventory item.")
        else:
            feed_item = get_feed_item_or_400(item_id, db)
            changes["feed_type"] = feed_item.name
    elif "feed_type" in changes:
        # Feed names are system-controlled from the linked Inventory item.
        changes.pop("feed_type", None)

    target_quantity = int(changes.get("quantity", livestock.quantity) or 0)
    target_animal_type = str(changes.get("animal_type", livestock.animal_type) or "")
    if "pen_id" in changes and changes.get("pen_id") is not None:
        pen = get_pen_or_400(
            db,
            int(changes["pen_id"]),
            animal_type=target_animal_type,
            quantity=target_quantity,
            exclude_livestock_id=livestock.id,
        )
        changes["pen_location"] = pen.name
    elif "pen_location" in changes:
        pen_name = str(changes.get("pen_location") or "").strip()
        pen = db.scalar(
            select(LivestockPen).where(
                func.lower(LivestockPen.name) == pen_name.lower(),
                LivestockPen.is_archived == False,
            )
        )
        if pen is None:
            raise HTTPException(status_code=400, detail="Choose an existing livestock pen from Manage Pens.")
        get_pen_or_400(
            db,
            pen.id,
            animal_type=target_animal_type,
            quantity=target_quantity,
            exclude_livestock_id=livestock.id,
        )
        changes["pen_id"] = pen.id
        changes["pen_location"] = pen.name
    elif "quantity" in changes and livestock.pen_id:
        get_pen_or_400(
            db,
            livestock.pen_id,
            animal_type=target_animal_type,
            quantity=target_quantity,
            exclude_livestock_id=livestock.id,
        )

    text_fields = {
        "record_name",
        "animal_type",
        "breed",
        "sex",
        "pen_location",
        "health_notes",
        "feed_times",
        "feed_type",
        "feeding_notes",
        "production_output",
        "production_purpose",
        "acquired_from",
        "feeding_plan_name",
        "estimated_age_confidence",
        "estimated_age_source",
        "acquisition_stage",
        "acquisition_vaccination_history",
        "acquisition_treatment_history",
    }
    for field_name, value in changes.items():
        if field_name in text_fields and isinstance(value, str):
            value = value.strip()
        setattr(livestock, field_name, value)

    if livestock.date_of_birth is not None:
        livestock.age_is_estimated = False
    else:
        livestock.age_is_estimated = True

    if any(key in changes for key in ("acquisition_vaccination_history", "acquisition_treatment_history")):
        livestock.medical_history_status = medical_history_status(
            livestock.acquisition_vaccination_history,
            livestock.acquisition_treatment_history,
        )

    if any(key in changes for key in ("healthy_quantity", "at_risk_quantity", "sick_quantity", "under_treatment_quantity")):
        livestock.health_status = health_status_from_counts(
            livestock.healthy_quantity,
            livestock.at_risk_quantity,
            livestock.sick_quantity,
            livestock.under_treatment_quantity,
        )

    validate_schedule(livestock, "Livestock")
    livestock.updated_at = datetime.now()

    if "weight_kg" in changes and float(changes["weight_kg"]) != old_weight:
        record_growth_measurement(
            db,
            livestock,
            farm_today(),
            float(changes["weight_kg"]),
            current_user.id,
            "Average weight updated from livestock record.",
            animals_measured=int(livestock.quantity or 1),
            total_measured_weight_kg=float(changes["weight_kg"]) * int(livestock.quantity or 1),
            min_weight_kg=float(livestock.min_weight_kg or changes["weight_kg"]),
            max_weight_kg=float(livestock.max_weight_kg or changes["weight_kg"]),
            measurement_basis="Full Batch" if int(livestock.quantity or 1) > 1 else "Individual",
        )

    care_assignment_changed = "care_template_id" in changes
    schedule_anchor_changed = "date_acquired" in changes
    target_type_changed = "animal_type" in changes
    new_care_template_id = livestock.care_template_id

    try:
        if new_care_template_id is not None:
            template = validate_care_template_for_target(
                db,
                template_id=new_care_template_id,
                module="Livestock",
                target=livestock,
            )
        else:
            template = None

        if care_assignment_changed and old_care_template_id != new_care_template_id:
            if old_care_template_id is not None:
                if new_care_template_id is not None or future_care_task_action == "resolve":
                    resolve_future_pending_care_tasks(
                        db,
                        module="Livestock",
                        target_id=livestock.id,
                        template_id=old_care_template_id,
                    )
            if template is not None:
                generate_care_tasks_for_target(
                    db,
                    module="Livestock",
                    target=livestock,
                    template=template,
                    current_user=current_user,
                    base_date=livestock.date_acquired,
                    future_only=True,
                )
        elif template is not None and (schedule_anchor_changed or target_type_changed):
            reconcile_same_template_future_schedule(
                db,
                module="Livestock",
                target=livestock,
                template=template,
                current_user=current_user,
                base_date=livestock.date_acquired,
            )

        db.flush()
        evaluate_automatic_tasks(db, commit=False)
        annotate_monitoring(db, [livestock], "Livestock")
        record_livestock_change(db, livestock, current_user, action="Updated livestock record", before=before)
        db.commit()
        db.refresh(livestock)
        return livestock
    except Exception:
        db.rollback()
        raise


# =========================================================
# GROWTH / WEIGHT HISTORY
# =========================================================

@router.get(
    "/{livestock_id}/growth-records",
    response_model=list[LivestockGrowthResponse],
)
def list_growth_records(
    livestock_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user),
    date_from: date | None = None, date_to: date | None = None,
):
    get_livestock_or_404(livestock_id, db)
    if date_from and date_to and date_to < date_from:
        raise HTTPException(400, "History end date cannot precede start date.")
    query = select(LivestockGrowthRecord).where(LivestockGrowthRecord.livestock_id == livestock_id)
    if date_from: query = query.where(LivestockGrowthRecord.measurement_date >= date_from)
    if date_to: query = query.where(LivestockGrowthRecord.measurement_date <= date_to)
    return list(db.scalars(query.order_by(LivestockGrowthRecord.measurement_date.desc(), LivestockGrowthRecord.id.desc())).all())


@router.post(
    "/{livestock_id}/growth-records",
    response_model=LivestockGrowthResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_growth_record(
    livestock_id: int,
    payload: LivestockGrowthCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_editor),
):
    livestock = get_livestock_or_404(livestock_id, db)
    ensure_not_archived(livestock)
    acquire_transaction_lock(db, f"livestock-monitoring:{livestock.id}")
    livestock = lock_livestock_or_404(livestock_id, db)
    db.refresh(livestock)

    record = record_growth_measurement(
        db,
        livestock,
        payload.measurement_date,
        payload.weight_kg,
        current_user.id,
        payload.notes,
        animals_measured=payload.animals_measured,
        total_measured_weight_kg=payload.total_measured_weight_kg,
        min_weight_kg=payload.min_weight_kg,
        max_weight_kg=payload.max_weight_kg,
        measurement_basis=payload.measurement_basis,
    )
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# CONFIRM FEEDING
# =========================================================

@router.post(
    "/{livestock_id}/feeding-records",
    response_model=LivestockFeedingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_feeding_record(
    livestock_id: int,
    payload: LivestockFeedingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_editor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    livestock = get_livestock_or_404(livestock_id, db)
    ensure_not_archived(livestock)

    if livestock.feed_inventory_item_id is None:
        raise HTTPException(
            status_code=400,
            detail="This livestock record has no Feed Inventory item linked. Update Feeding Information first.",
        )
    if int(payload.inventory_item_id) != int(livestock.feed_inventory_item_id):
        raise HTTPException(
            status_code=400,
            detail="Feeding must use the exact Feed Inventory item linked to this livestock record.",
        )
    if payload.actual_quantity_kg is None or float(payload.actual_quantity_kg) <= 0:
        raise HTTPException(status_code=400, detail="Enter the actual feed quantity used.")

    # Keep the Livestock page and My Tasks on one submission path. Serialize
    # this logical feeding confirmation before generating/looking up its task,
    # then let submit_task perform the task/inventory transaction.
    slot_key = re.sub(
        r"[^a-z0-9]+", "-", payload.feeding_slot.strip().lower()
    ).strip("-")
    source_key = (
        f"livestock:feeding:{livestock.id}:"
        f"{payload.feeding_date.isoformat()}:{slot_key}"
    )
    acquire_transaction_lock(db, f"livestock-feeding-confirmation:{source_key}")
    evaluate_automatic_tasks(db, commit=False)
    task = db.scalar(
        select(FarmActivity).where(
            FarmActivity.source_type == "livestock_feeding",
            FarmActivity.source_record_id == livestock.id,
            FarmActivity.source_key == source_key,
            FarmActivity.is_archived == False,
        )
    )

    if task is None:
        # Historical/manual confirmations still become a real task rather than
        # bypassing the workforce/resource-usage ledger.
        from app.routers.activities import generate_activity_code

        employee = db.get(Employee, livestock.assigned_employee_id) if livestock.assigned_employee_id else None
        if employee is None or employee.is_archived:
            raise HTTPException(
                status_code=400,
                detail="Assign an active employee to this livestock record before confirming feeding.",
            )
        task = FarmActivity(
            activity_code=generate_activity_code(db),
            name=f"{payload.feeding_slot.strip()} Feeding - {livestock.record_name}",
            category="Livestock Feeding",
            related_to=livestock.record_name,
            location=livestock.pen_location,
            description="Feeding confirmation submitted from the Livestock page.",
            instructions="Record the actual feed used, then submit the work for review.",
            activity_date=payload.feeding_date,
            start_time=farm_now_naive().time().replace(second=0, microsecond=0),
            assigned_by=current_user.full_name,
            assigned_to=employee.full_name,
            assigned_employee_id=employee.id,
            status="Pending",
            priority="Medium",
            requires_review=True,
            planned_quantity=None,
            planned_unit="kg",
            is_automatic=False,
            source_module="Livestock",
            source_type="livestock_feeding",
            source_record_id=livestock.id,
            source_code=livestock.animal_code,
            source_path="/livestock",
            source_key=source_key,
            created_by_user_id=current_user.id,
        )
        db.add(task)
        db.flush()
        recalculate_task_reassignment(db, task)

    if not task.assigned_employee_id:
        raise HTTPException(
            status_code=400,
            detail="Assign an employee to this feeding task before submitting it.",
        )

    from app.routers.workforce import submit_task
    from app.schemas.workforce import TaskSubmitRequest

    submit_task(
        task.id,
        TaskSubmitRequest(
            actual_quantity=float(payload.actual_quantity_kg),
            actual_quantity_confirmed=True,
            actual_unit="kg",
            evidence_url=payload.evidence_url,
            worker_notes=payload.notes,
            performed_by_employee_id=payload.performed_by_employee_id or task.assigned_employee_id,
            assisted_reason="Authorized livestock feeding confirmation recorded from the Livestock page.",
        ),
        db=db,
        current_user=current_user,
        idempotency_key=idempotency_key,
    )

    feeding_record = db.scalar(
        select(LivestockFeedingRecord).where(
            LivestockFeedingRecord.livestock_id == livestock.id,
            LivestockFeedingRecord.feeding_date == payload.feeding_date,
            func.lower(LivestockFeedingRecord.feeding_slot) == payload.feeding_slot.strip().lower(),
        )
    )
    if feeding_record is None:
        raise HTTPException(status_code=500, detail="Feeding submission was saved but its feeding record could not be loaded.")
    db.refresh(feeding_record)
    return feeding_record


# =========================================================
# ARCHIVE LIVESTOCK
# =========================================================

@router.post(
    "/{livestock_id}/archive",
    response_model=LivestockResponse,
)
def archive_livestock(
    livestock_id: int,
    payload: ArchiveRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_livestock_archiver),
):
    record = change_archive_state(db, "Livestock", livestock_id, _, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# RESTORE LIVESTOCK
# =========================================================

@router.post(
    "/{livestock_id}/restore",
    response_model=LivestockResponse,
)
def restore_livestock(
    livestock_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_livestock_archiver),
):
    record = change_archive_state(db, "Livestock", livestock_id, _, archive=False)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# ADD VACCINATION RECORD
# =========================================================

@router.post(
    "/{livestock_id}/vaccination-records",
    response_model=LivestockVaccinationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_vaccination_record(
    livestock_id: int,
    payload: LivestockVaccinationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_livestock_editor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    fingerprint = request_fingerprint(payload)
    command_type = f"livestock-vaccination:{livestock_id}"
    existing = begin_creation_command(db, idempotency_key=idempotency_key, command_type=command_type,
                                      request_hash=fingerprint, user_id=current_user.id)
    if existing is not None:
        record = db.get(LivestockVaccinationRecord, existing.target_id)
        if record is None or record.livestock_id != livestock_id:
            raise HTTPException(409, "The saved vaccination retry target no longer exists.")
        return record
    livestock = get_livestock_or_404(livestock_id, db)
    ensure_not_archived(livestock)

    if livestock.date_of_birth is not None and payload.date_administered < livestock.date_of_birth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vaccination date cannot be earlier than the livestock date of birth.",
        )
    if payload.date_administered > farm_today():
        raise HTTPException(status_code=400, detail="Vaccination date cannot be in the future.")
    if payload.inventory_item_id is None or payload.quantity_used is None:
        raise HTTPException(
            status_code=400,
            detail="Select the exact Vaccine Inventory item and enter the quantity used.",
        )

    item = lock_inventory_item(db, payload.inventory_item_id)
    if item is None or item.is_archived:
        raise HTTPException(status_code=400, detail="Selected vaccine Inventory item is unavailable.")
    if not is_vaccine_inventory_item(item):
        raise HTTPException(status_code=400, detail="Selected Inventory item is not categorized as a vaccine.")
    previous_quantity = float(item.quantity or 0)
    quantity_used = round(float(payload.quantity_used), 3)
    if quantity_used <= 0:
        raise HTTPException(status_code=400, detail="Vaccine quantity used must be greater than zero.")
    if quantity_used > previous_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough {item.name} in Inventory. Available: {previous_quantity:g} {item.unit}.",
        )
    if item.expiration_date and item.expiration_date < payload.date_administered:
        raise HTTPException(status_code=400, detail=f"{item.name} is expired and cannot be administered.")

    livestock = lock_vaccination_parent(db, livestock_id)
    ensure_not_archived(livestock)
    new_quantity = round(previous_quantity - quantity_used, 3)
    item.quantity = new_quantity
    record = LivestockVaccinationRecord(
        livestock_id=livestock.id,
        vaccine=item.name,
        date_administered=payload.date_administered,
        next_due=payload.next_due,
        status=payload.status,
        administered_by=(payload.administered_by.strip() if payload.administered_by else None),
        inventory_item_id=item.id,
        quantity_used=quantity_used,
        unit=item.unit,
        notes=(payload.notes.strip() if payload.notes else None),
        recorded_by_user_id=current_user.id,
    )
    stock_record = InventoryStockRecord(
        inventory_item_id=item.id,
        adjustment_type="Stock Usage",
        quantity=quantity_used,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        adjustment_date=payload.date_administered,
        reason=f"Livestock vaccination - {livestock.record_name}",
        reference=f"{livestock.animal_code} / Vaccination",
        supplier=None,
        recorded_by_user_id=current_user.id,
    )

    livestock.updated_at = datetime.now()

    db.add(record)
    db.add(stock_record)
    db.flush()
    update_vaccination_summary(db, livestock, record, status=payload.status, next_due=payload.next_due)
    record_creation_command(db, idempotency_key=idempotency_key, command_type=command_type,
                            request_hash=fingerprint, target_id=record.id, user_id=current_user.id)
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{livestock_id}/permanent", status_code=204)
def permanently_delete_livestock(livestock_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    from fastapi import Response
    permanent_delete(db, "Livestock", livestock_id, actor)
    db.commit()
    return Response(status_code=204)
