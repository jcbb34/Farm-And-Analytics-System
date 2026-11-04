from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete
from datetime import date, datetime
import re

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Header,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.farm_time import farm_now_naive, farm_today
from app.core.dependencies import has_permission, require_permission
from app.models import (
    FarmActivity,
    Crop,
    Employee,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    LivestockFeedingRecord,
    ResourceUsage,
    TaskSubmission,
    User,
)
from app.routers.auth import get_current_user
from app.services.code_counter_service import next_record_code
from app.services.idempotency import begin_creation_command, record_creation_command, request_fingerprint
from app.services.task_assignment import record_assignment_change, recalculate_task_reassignment
from app.services.task_engine import evaluate_automatic_tasks
from app.services.event_planning import event_domain, is_equipment_category
from app.schemas.activity import (
    ALLOWED_ACTIVITY_PRIORITIES,
    ALLOWED_ACTIVITY_STATUSES,
    FarmActivityCreate,
    FarmActivityResponse,
    FarmActivityUpdate,
)


router = APIRouter(
    prefix="/api/v1/activities",
    dependencies=[Depends(require_permission("activities:view"))],
    tags=["Farm Activities"],
)

def require_activity_creator(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "activities:create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create farm activities.",
        )
    return current_user


def require_activity_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "activities:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage farm activities.",
        )
    return current_user



def get_activity_or_404(
    activity_id: int,
    db: Session,
    *,
    lock: bool = False,
) -> FarmActivity:
    statement = select(FarmActivity).where(FarmActivity.id == activity_id)
    if lock:
        # Use the same row lock as workforce submission/review mutations.
        statement = statement.with_hint(FarmActivity, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql").with_for_update()
    activity = db.scalar(statement)

    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Farm activity record not found.",
        )

    return activity


def ensure_activity_not_archived(activity: FarmActivity):
    if activity.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Archived farm activities cannot be modified. "
                "Restore the activity first."
            ),
        )


def generate_activity_code(db: Session) -> str:
    return next_record_code(
        db,
        namespace="activity",
        prefix="ACT",
        seed_model=FarmActivity,
        code_column=FarmActivity.activity_code,
    )


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def validate_status_priority(
    activity_status: str | None,
    priority: str | None,
):
    if (
        activity_status is not None
        and activity_status not in ALLOWED_ACTIVITY_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid activity status.",
        )

    if (
        priority is not None
        and priority not in ALLOWED_ACTIVITY_PRIORITIES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid activity priority.",
        )


def validate_times(
    activity: FarmActivity | None,
    changes: dict,
):
    start_time = changes.get(
        "start_time",
        activity.start_time if activity else None,
    )
    end_time = changes.get(
        "end_time",
        activity.end_time if activity else None,
    )

    if (
        start_time is not None
        and end_time is not None
        and end_time < start_time
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time cannot be earlier than start time.",
        )


TASK_WORKFLOW_STATUSES = {
    "Pending",
    "In Progress",
    "Submitted for Review",
    "Returned",
    "Completed",
    "Approved",
}


def _activity_workflow_type(activity: FarmActivity) -> str:
    """Classify from persisted relationships, never display text."""
    has_care_source = bool(
        activity.source_module in {"Crop", "Livestock"}
        and (
            activity.is_automatic
            or activity.source_record_id is not None
            or activity.source_type
        )
    )
    if has_care_source and (
        activity.assigned_employee_id is not None
        or activity.requires_review
    ):
        return "care_task"
    if activity.assigned_employee_id is not None or activity.requires_review:
        return "workforce_task"
    if activity.is_automatic or has_care_source:
        return "system_informational"
    return "standalone_activity"


def _can_complete_activity_directly(activity: FarmActivity) -> bool:
    # Keep this exactly aligned with update_activity's protected workflow:
    # automatic, employee-assigned, and review-required work must flow through
    # My Tasks / Task Management review instead of a raw activity PUT.
    return bool(
        not activity.is_automatic
        and activity.assigned_employee_id is None
        and not activity.requires_review
        and not activity.is_archived
    )


def _current_employee_id(db: Session, current_user: User) -> int | None:
    if not has_permission(current_user, "workforce:submit"):
        return None
    return db.scalar(
        select(Employee.id).where(
            Employee.login_user_id == current_user.id,
            Employee.is_archived == False,
            Employee.employment_status == "Active",
        )
    )


def _activity_workflow_metadata(
    activity: FarmActivity,
    current_user: User,
    *,
    current_employee_id: int | None = None,
) -> dict:
    workflow_type = _activity_workflow_type(activity)
    is_task_workflow = workflow_type in {"workforce_task", "care_task"}
    can_complete_directly = _can_complete_activity_directly(activity)
    can_manage = bool(
        has_permission(current_user, "workforce:manage")
        or has_permission(current_user, "workforce:review")
        or has_permission(current_user, "*")
    )
    is_assigned_employee = bool(
        current_employee_id is not None
        and activity.assigned_employee_id == current_employee_id
    )
    actions: list[str] = []

    if is_task_workflow:
        if can_manage:
            if activity.needs_reassignment:
                actions.append("resolve_assignment")
            elif activity.status == "Submitted for Review":
                actions.append("review_submission")
            elif activity.status == "Returned":
                actions.append("view_returned_task")
            elif activity.status in {"Completed", "Approved"}:
                actions.append("view_report")
            elif activity.status in {"Pending", "In Progress"}:
                actions.append("open_task")
                # Assisted recording remains inside Task Management; this flag
                # lets clients offer a secondary route without inventing a
                # direct-complete workaround.
                actions.append("assisted_submission")
            else:
                actions.append("open_task")
        elif is_assigned_employee:
            if activity.status == "Returned":
                actions.append("correct_submission")
            elif activity.status == "Submitted for Review":
                actions.append("view_submission")
            elif activity.status in {"Completed", "Approved"}:
                actions.append("view_history")
            elif activity.status in {"Pending", "In Progress"}:
                actions.append("open_my_tasks")
    elif workflow_type == "standalone_activity":
        if can_complete_directly and activity.status == "Pending":
            actions.append("start_directly")
        elif can_complete_directly and activity.status == "In Progress":
            actions.append("complete_directly")
    elif workflow_type == "system_informational" and activity.source_path:
        actions.append("open_source")

    return {
        "workflow_type": workflow_type,
        "linked_task_id": activity.id if is_task_workflow else None,
        "available_actions": actions,
        "can_complete_directly": can_complete_directly,
        "requires_employee_submission": bool(
            is_task_workflow
            and activity.assigned_employee_id is not None
        ),
        "requires_manager_review": bool(
            is_task_workflow and activity.requires_review
        ),
    }


def _activity_response(
    activity: FarmActivity,
    current_user: User,
    *,
    current_employee_id: int | None = None,
) -> FarmActivityResponse:
    response = FarmActivityResponse.model_validate(activity)
    return response.model_copy(
        update=_activity_workflow_metadata(
            activity,
            current_user,
            current_employee_id=current_employee_id,
        )
    )


@router.get(
    "",
    response_model=list[FarmActivityResponse],
)
def list_activities(
    include_archived: bool = Query(default=False),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = select(FarmActivity).order_by(
        FarmActivity.activity_date.desc(),
        FarmActivity.start_time.desc(),
        FarmActivity.id.desc(),
    )

    if not has_permission(current_user, "workforce:manage") and not has_permission(current_user, "activities:update"):
        employee = db.scalar(select(Employee).where(Employee.login_user_id == current_user.id, Employee.is_archived == False))
        if employee is None:
            return []
        statement = statement.where(FarmActivity.assigned_employee_id == employee.id)

    if not include_archived:
        statement = statement.where(
            FarmActivity.is_archived == False
        )

    if date_from is not None:
        statement = statement.where(
            FarmActivity.activity_date >= date_from
        )

    if date_to is not None:
        statement = statement.where(
            FarmActivity.activity_date <= date_to
        )

    rows = list(db.scalars(statement).all())
    employee_id = _current_employee_id(db, current_user)
    return [
        _activity_response(row, current_user, current_employee_id=employee_id)
        for row in rows
    ]


@router.post(
    "/evaluate",
)
def evaluate_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return evaluate_automatic_tasks(db, skip_if_busy=True)


@router.get("/event-resources")
def event_resources(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    domains = {
        module
        for module, permission in (
            ("Crop", "crops:view"),
            ("Livestock", "livestock:view"),
            ("Inventory", "inventory:view"),
        )
        if has_permission(current_user, permission)
        or has_permission(current_user, "workforce:manage")
    }
    if not domains:
        raise HTTPException(
            403,
            "Crop, livestock, inventory or workforce viewing permission is required to prepare event records.",
        )
    crops = (
        db.execute(
            select(Crop.id, Crop.name, Crop.field)
            .where(Crop.is_archived == False)
            .order_by(Crop.name, Crop.id)
        ).all()
        if "Crop" in domains
        else []
    )
    animals = (
        db.execute(
            select(
                Livestock.id,
                Livestock.record_name,
                Livestock.animal_code,
                Livestock.pen_location,
                Livestock.feed_times,
                Livestock.feed_inventory_item_id,
            )
            .where(Livestock.is_archived == False)
            .order_by(Livestock.record_name, Livestock.id)
        ).all()
        if "Livestock" in domains
        else []
    )
    items = (
        db.execute(
            select(
                InventoryItem.id,
                InventoryItem.name,
                InventoryItem.category,
                InventoryItem.unit,
                InventoryItem.quantity,
                InventoryItem.location,
                InventoryItem.reorder_level,
                InventoryItem.expiration_date,
            )
            .where(InventoryItem.is_archived == False)
            .order_by(InventoryItem.name, InventoryItem.id)
        ).all()
        if "Inventory" in domains
        else []
    )
    from app.services.task_engine import _feeding_occurrences

    return {
        "crops": [{"id": x.id, "name": x.name, "field": x.field} for x in crops],
        "livestock": [
            {
                "id": x.id,
                "name": x.record_name,
                "code": x.animal_code,
                "location": x.pen_location,
                "feeding_slots": [slot for _, slot, _ in _feeding_occurrences(x.feed_times)],
                "feed_inventory_item_id": x.feed_inventory_item_id,
            }
            for x in animals
        ],
        "inventory": [
            {
                "id": x.id,
                "name": x.name,
                "category": x.category,
                "unit": x.unit,
                "quantity": float(x.quantity or 0),
                "location": x.location,
                "reorder_level": float(x.reorder_level or 0),
                "expiration_date": x.expiration_date,
            }
            for x in items
        ],
    }


@router.get(
    "/{activity_id}",
    response_model=FarmActivityResponse,
)
def get_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = get_activity_or_404(activity_id, db)
    current_employee_id = _current_employee_id(db, current_user)

    # Keep the detail endpoint aligned with the employee-scoped list endpoint.
    # A task-only user must not reveal another employee's activity by changing
    # the activity id in the URL. Managers/editors retain their existing view.
    if (
        not has_permission(current_user, "workforce:manage")
        and not has_permission(current_user, "activities:update")
        and activity.assigned_employee_id != current_employee_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Farm activity record not found.",
        )

    return _activity_response(
        activity,
        current_user,
        current_employee_id=current_employee_id,
    )


@router.post(
    "",
    response_model=FarmActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    payload: FarmActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_activity_creator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not isinstance(idempotency_key, (str, type(None))):
        idempotency_key = None
    fingerprint = request_fingerprint(payload)
    try:
        existing = begin_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="activity_create",
            request_hash=fingerprint,
            user_id=current_user.id,
        )
        if existing:
            activity = db.get(FarmActivity, existing.target_id)
            if activity is None:
                raise HTTPException(
                    409,
                    "The original event is no longer available; no duplicate was created.",
                )
            return _activity_response(
                activity,
                current_user,
                current_employee_id=_current_employee_id(db, current_user),
            )
        from app.services.manual_activity_service import create_manual_activity

        activity = create_manual_activity(
            db, payload, current_user,
            assignment_reason="Employee assigned from Add Farm Event.",
        )
        record_creation_command(
            db,
            idempotency_key=idempotency_key,
            command_type="activity_create",
            request_hash=fingerprint,
            target_id=activity.id,
            user_id=current_user.id,
        )
        db.commit()
        db.refresh(activity)
        return _activity_response(
            activity,
            current_user,
            current_employee_id=_current_employee_id(db, current_user),
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            "The event changed during saving. Retry the same request; no partial event was saved.",
        ) from exc
    except Exception:
        db.rollback()
        raise


def _named_feeding_slots(value: str | None) -> list[str]:
    text_value = (value or "").strip().lower()
    slot_terms = [
        (("morning",), "Morning"),
        (("midday", "noon"), "Midday"),
        (("afternoon",), "Afternoon"),
        (("evening", "night"), "Evening"),
    ]

    slots: list[str] = []
    for terms, label in slot_terms:
        if any(
            re.search(rf"\b{re.escape(term)}\b", text_value)
            for term in terms
        ):
            slots.append(label)

    return slots


def _parse_feedings_per_day(value: str | None) -> int:
    text_value = (value or "").strip().lower()

    for separator in ("×", "x"):
        if separator in text_value:
            left = text_value.split(separator, 1)[0].strip()
            try:
                return max(1, min(int(left), 12))
            except ValueError:
                pass

    if "twice" in text_value:
        return 2
    if "three" in text_value or "thrice" in text_value:
        return 3
    if "four" in text_value:
        return 4

    named_slots = _named_feeding_slots(value)
    if named_slots:
        return max(1, min(len(named_slots), 12))

    return 1


def _feeding_slots(
    count: int,
    value: str | None = None,
) -> list[str]:
    named_slots = _named_feeding_slots(value)
    if len(named_slots) == count:
        return named_slots

    if count == 1:
        return ["Daily Feeding"]
    if count == 2:
        return ["Morning", "Afternoon"]
    if count == 3:
        return ["Morning", "Midday", "Evening"]

    return [
        f"Feeding {index + 1}"
        for index in range(count)
    ]


def _feeding_slot_for_activity(
    activity: FarmActivity,
    slots: list[str],
    completed_slots: set[str],
) -> str | None:
    detail_id = activity.source_detail_id
    if detail_id is not None:
        try:
            index = int(detail_id) - 1
        except (TypeError, ValueError):
            index = -1

        if 0 <= index < len(slots):
            return slots[index]

    activity_text = " ".join(
        [
            str(activity.name or ""),
            str(activity.description or ""),
            str(activity.source_key or ""),
        ]
    ).lower()

    for slot in slots:
        if slot.lower() in activity_text:
            return slot

    for slot in slots:
        if slot.lower() not in completed_slots:
            return slot

    return None


def _get_linked_livestock(
    activity: FarmActivity,
    db: Session,
) -> Livestock:
    if activity.source_record_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This livestock activity is not linked to a livestock record. "
                "Open Livestock Management and complete the work there."
            ),
        )

    livestock = db.scalar(
        select(Livestock).where(
            Livestock.id == activity.source_record_id
        )
    )

    if livestock is None or livestock.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The livestock record linked to this activity is unavailable."
            ),
        )

    return livestock


def _get_linked_feed_item(
    livestock: Livestock,
    db: Session,
) -> InventoryItem:
    expected_feed = (livestock.feed_type or "Required livestock feed").strip()

    if livestock.feed_inventory_item_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Feeding cannot be completed because no feed inventory item is linked "
                f"to {livestock.record_name}. Required feed: {expected_feed}. "
                "Link the correct feed item in Livestock Management first."
            ),
        )

    item = db.scalar(
        select(InventoryItem).where(
            InventoryItem.id == livestock.feed_inventory_item_id,
            InventoryItem.is_archived == False,
        )
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Feeding cannot be completed because the linked feed inventory item "
                "is missing or archived. Restore or link the correct feed item first."
            ),
        )

    if (item.unit or "").strip().lower() not in {
        "kg",
        "kgs",
        "kilogram",
        "kilograms",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Feeding cannot use {item.name} because its inventory unit is "
                f"{item.unit or 'not set'}. Feed inventory used by livestock must "
                "be recorded in kilograms (kg)."
            ),
        )

    return item


def _sync_livestock_feeding_completion(
    activity: FarmActivity,
    livestock: Livestock,
    db: Session,
    current_user: User,
) -> None:
    if not has_permission(current_user, "livestock:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You need livestock update permission to confirm this feeding task."
            ),
        )

    if not has_permission(current_user, "inventory:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You need inventory update permission because confirmed feeding deducts feed stock."
            ),
        )

    if activity.activity_date > farm_today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A future feeding task cannot be marked completed yet.",
        )

    feedings_per_day = _parse_feedings_per_day(
        livestock.feed_times
    )
    slots = _feeding_slots(feedings_per_day, livestock.feed_times)

    batch_daily_quantity = (
        float(livestock.daily_feed_kg or 0)
        * int(livestock.quantity or 1)
    )
    planned_per_feeding = round(
        batch_daily_quantity / feedings_per_day,
        3,
    )

    if planned_per_feeding <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This livestock batch has no valid daily feed amount. "
                "Update its feeding schedule before completing this task."
            ),
        )

    existing_records = db.scalars(
        select(LivestockFeedingRecord).where(
            LivestockFeedingRecord.livestock_id == livestock.id,
            LivestockFeedingRecord.feeding_date == activity.activity_date,
        )
    ).all()
    completed_slots = {
        str(record.feeding_slot or "").strip().lower()
        for record in existing_records
    }

    target_slot = _feeding_slot_for_activity(
        activity,
        slots,
        completed_slots,
    )

    if target_slot is None:
        return

    if target_slot.lower() in completed_slots:
        return

    item = _get_linked_feed_item(livestock, db)
    available = round(float(item.quantity or 0), 3)

    if planned_per_feeding > available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Not enough {item.name} in inventory to complete the "
                f"{target_slot} feeding. Required: "
                f"{planned_per_feeding:.3f} kg; available: "
                f"{available:.3f} kg."
            ),
        )

    feed_type = (livestock.feed_type or item.name).strip()
    previous_quantity = round(float(item.quantity or 0), 3)
    new_quantity = round(
        previous_quantity - planned_per_feeding,
        3,
    )

    feeding_record = LivestockFeedingRecord(
        livestock_id=livestock.id,
        inventory_item_id=item.id,
        feeding_date=activity.activity_date,
        feeding_slot=target_slot,
        scheduled_times=livestock.feed_times,
        feed_type=feed_type,
        planned_quantity_kg=planned_per_feeding,
        actual_quantity_kg=planned_per_feeding,
        notes=(
            f"{target_slot} feeding confirmed from Farm Activity "
            f"{activity.activity_code}."
        ),
        recorded_by_user_id=current_user.id,
    )

    stock_record = InventoryStockRecord(
        inventory_item_id=item.id,
        adjustment_type="Stock Usage",
        quantity=planned_per_feeding,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        adjustment_date=activity.activity_date,
        reason=f"Livestock feeding - {livestock.record_name}",
        reference=(
            f"{livestock.animal_code} / {target_slot} feeding / "
            f"{activity.activity_code}"
        ),
        supplier=None,
        recorded_by_user_id=current_user.id,
    )

    item.quantity = new_quantity
    item.updated_at = datetime.now()
    db.add(feeding_record)
    db.add(stock_record)

    livestock.feed_inventory_item_id = item.id
    if not livestock.feed_type:
        livestock.feed_type = item.name
    livestock.updated_at = datetime.now()


def _sync_livestock_health_completion(
    activity: FarmActivity,
    livestock: Livestock,
    current_user: User,
) -> None:
    if not has_permission(current_user, "livestock:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You need livestock update permission to complete this health check."
            ),
        )

    if activity.activity_date > farm_today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A future livestock health check cannot be marked completed yet.",
        )

    completed_on = farm_today()
    note = (
        f"Health check completed from Farm Activity "
        f"{activity.activity_code} on {completed_on.isoformat()}."
    )

    current_notes = (livestock.health_notes or "").strip()
    if note not in current_notes:
        livestock.health_notes = (
            f"{current_notes}\n{note}".strip()
            if current_notes
            else note
        )

    livestock.last_checkup = completed_on
    livestock.updated_at = datetime.now()


def _sync_activity_source_completion(
    activity: FarmActivity,
    db: Session,
    current_user: User,
) -> None:
    if not activity.is_automatic:
        return

    source_type = (activity.source_type or "").strip()

    if source_type == "livestock_feeding":
        livestock = _get_linked_livestock(activity, db)
        _sync_livestock_feeding_completion(
            activity,
            livestock,
            db,
            current_user,
        )
        return

    if source_type == "livestock_health_check":
        livestock = _get_linked_livestock(activity, db)
        _sync_livestock_health_completion(
            activity,
            livestock,
            current_user,
        )
        return

    if source_type == "crop_watering":
        if activity.activity_date > farm_today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A future crop watering occurrence cannot be completed yet.",
            )
        # The completed FarmActivity itself is the operational watering record.
        # Water consumption is intentionally not tracked as inventory.
        return

    detailed_source_types = {
        "livestock_vaccination",
        "livestock_reproduction",
        "crop_harvest",
        "crop_growth_check",
        "crop_pest_followup",
        "inventory_restock",
    }

    if source_type in detailed_source_types:
        destination = activity.source_path or "the related management page"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This automatic task needs operational details that cannot be "
                "safely inferred from a checkbox. Complete the record in "
                f"{destination}; the activity will then synchronize automatically."
            ),
        )


@router.put(
    "/{activity_id}",
    response_model=FarmActivityResponse,
)
def update_activity(
    activity_id: int,
    payload: FarmActivityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_activity_editor),
):
    activity = get_activity_or_404(activity_id, db, lock=True)

    if activity.is_archived:
        if activity.is_automatic:
            evaluate_automatic_tasks(
                db,
                commit=False,
            )
            db.commit()
            db.refresh(activity)
            return _activity_response(
                activity,
                current_user,
                current_employee_id=_current_employee_id(db, current_user),
            )

        ensure_activity_not_archived(activity)

    changes = payload.model_dump(exclude_unset=True)
    # Validate every supplied value before touching the ORM object; rejected
    # requests must never leave a partial edit pending in the caller's session.
    required_fields = {"name", "category", "related_to", "location", "assigned_by", "assigned_to",
                       "activity_date", "start_time", "status", "priority", "requires_review", "requires_evidence"}
    for field_name, value in changes.items():
        if field_name in required_fields and (value is None or isinstance(value, str) and not value.strip()):
            raise HTTPException(400, f"{field_name.replace('_', ' ').title()} is required.")
        if isinstance(value, str):
            changes[field_name] = value.strip() or None
    previous_status = activity.status
    if (
        "assigned_employee_id" in changes
        and changes["assigned_employee_id"] != activity.assigned_employee_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Change employee assignments through Task Management so account checks, availability and assignment history are preserved.",
        )
    from app.services.farm_event_service import assert_task_available
    if changes.get("status") in {"In Progress", "Completed", "Resolved", "Cancelled"} or any(
        key in changes for key in ("activity_date", "start_time", "end_time", "assigned_employee_id")
    ):
        assert_task_available(db, activity)

    if (
        activity.is_automatic
        and previous_status == "Completed"
        and changes.get("status") in {"Pending", "In Progress"}
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Completed automatic activities cannot be reopened because the "
                "linked farm record may already have been updated."
            ),
        )

    validate_status_priority(
        changes.get("status"),
        changes.get("priority"),
    )
    validate_times(activity, changes)

    # Reject protected task completion before mutating the ORM object. Older
    # code applied payload fields first and only then raised 400, leaving a
    # dirty in-memory status that could be flushed by later work in the same
    # session even though the request was rejected.
    approved_submission = None
    if changes.get("status") == "Completed":
        if activity.is_automatic or activity.assigned_employee_id is not None or activity.requires_review:
            approved_submission = db.scalar(
                select(TaskSubmission.id).where(
                    TaskSubmission.activity_id == activity.id,
                    TaskSubmission.review_status == "Approved",
                )
            )
            if not approved_submission:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "This employee/workforce task cannot be marked Completed directly. "
                        "Have the employee submit it from My Tasks, or use Assisted Submission "
                        "from Task Management so performed by, recorded by, actual usage, and review history are preserved."
                    ),
                )

    effective_changes = {key: value for key, value in changes.items() if getattr(activity, key) != value}
    has_submission = db.scalar(select(TaskSubmission.id).where(TaskSubmission.activity_id == activity.id).limit(1)) is not None
    has_posting = db.scalar(select(ResourceUsage.id).where(ResourceUsage.activity_id == activity.id).limit(1)) is not None
    protected_task = bool(activity.is_automatic or activity.assigned_employee_id is not None or activity.requires_review or has_submission or has_posting)
    if protected_task and effective_changes:
        if has_submission or has_posting or previous_status in {"Completed", "Approved", "Voided", "Cancelled", "Resolved", "Submitted for Review"}:
            raise HTTPException(400, "Submitted or completed tasks cannot be edited through calendar activities. Use Task Management review, correction, or Owner/Admin void so work history and stock postings stay consistent.")
        if "status" in effective_changes:
            raise HTTPException(400, "Change workforce task status through My Tasks or Task Management so submission and review history are preserved.")
        if any(key in effective_changes for key in {"assigned_by", "assigned_to", "requires_evidence"}) or changes.get("requires_review") is False:
            raise HTTPException(400, "Change task assignment and evidence requirements through Task Management.")
    if not protected_task and effective_changes.get("status") in {"Submitted for Review", "Returned"}:
        raise HTTPException(400, "Submission and review statuses require the workforce task workflow.")
    if not effective_changes:
        return _activity_response(activity, current_user, current_employee_id=_current_employee_id(db, current_user))

    required_text_fields = {
        "name",
        "category",
        "related_to",
        "location",
        "assigned_by",
        "assigned_to",
    }
    optional_text_fields = {
        "description",
        "duration",
    }

    for field_name, value in changes.items():
        if field_name in required_text_fields:
            value = value.strip()

            if not value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name.replace('_', ' ').title()} is required.",
                )

        if field_name in optional_text_fields:
            value = clean_optional_text(value)

        setattr(activity, field_name, value)

    # Any open task assigned to an employee must remain review-required.
    # This keeps stored metadata aligned with the authoritative workforce
    # submission rule even if an older/manual client tries to clear the flag.
    if (
        activity.assigned_employee_id is not None
        and not activity.is_archived
        and activity.status not in {
            "Completed",
            "Approved",
            "Voided",
            "Cancelled",
            "Resolved",
        }
    ):
        activity.requires_review = True

    if "status" in changes:
        if changes["status"] == "Completed":
            if previous_status != "Completed":
                _sync_activity_source_completion(
                    activity,
                    db,
                    current_user,
                )
            activity.completed_at = datetime.now()

            if (
                activity.is_automatic
                and activity.source_type == "livestock_feeding"
            ):
                evaluate_automatic_tasks(
                    db,
                    commit=False,
                )
        elif changes["status"] in {
            "Pending",
            "In Progress",
        }:
            activity.completed_at = None

    activity.updated_at = datetime.now()

    db.commit()
    db.refresh(activity)

    return _activity_response(
        activity,
        current_user,
        current_employee_id=_current_employee_id(db, current_user),
    )


@router.post(
    "/{activity_id}/archive",
    response_model=FarmActivityResponse,
)
def archive_activity(
    activity_id: int,
    payload: ArchiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_activity_editor),
):
    record = change_archive_state(db, "Task", activity_id, current_user, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return _activity_response(record, current_user, current_employee_id=_current_employee_id(db, current_user))


@router.post(
    "/{activity_id}/restore",
    response_model=FarmActivityResponse,
)
def restore_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_activity_editor),
):
    record = change_archive_state(db, "Task", activity_id, current_user, archive=False)
    db.commit()
    db.refresh(record)
    return _activity_response(record, current_user, current_employee_id=_current_employee_id(db, current_user))
