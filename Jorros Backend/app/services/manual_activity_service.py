"""Shared, transaction-scoped creation rules for calendar and workforce assignments.

The caller owns commit/rollback and the idempotent creation command. No historical
work is reclassified: operational metadata is assigned only to new work.
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import has_permission
from app.core.farm_time import farm_now_naive
from app.models import Crop, FarmActivity, InventoryItem, Livestock, User
from app.schemas.activity import FarmActivityCreate
from app.services.code_counter_service import next_record_code
from app.services.db_concurrency import acquire_transaction_lock
from app.services.event_planning import event_domain, is_equipment_category
from app.services.task_assignment import (
    record_assignment_change,
    recalculate_task_reassignment,
)


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def validate_planned_resource(item: InventoryItem | None, work_date: date) -> None:
    if item is None or item.is_archived:
        raise HTTPException(
            422, "The selected inventory resource is missing or archived."
        )
    if item.expiration_date and work_date > item.expiration_date:
        raise HTTPException(
            422, f"{item.name} expires before this work date. Select valid stock."
        )


def create_manual_activity(
    db: Session,
    payload: FarmActivityCreate,
    current_user: User,
    *,
    allow_unavailable_override=False,
    backup_employee_id=None,
    time_sensitive=False,
    controlled_rescheduling=False,
    max_delay_minutes=None,
    assignment_reason="Initial employee assignment.",
) -> FarmActivity:
    if payload.recurring_rule and payload.recurring_rule.strip():
        raise HTTPException(
            422,
            "Repeating manual tasks are not supported. Create dated assignments, or configure repeating care in Crops or Livestock.",
        )
    if payload.source_type not in {
        None,
        "manual",
        "manual_work",
        "crop_harvest",
        "livestock_feeding",
        "inventory_restock_plan",
        "equipment_maintenance_plan",
    }:
        raise HTTPException(
            422, "Use the crop or livestock scheduling screen for this task type."
        )
    if backup_employee_id:
        from app.routers.workforce_handlers import (
            _assignable_employee_or_404,
            _require_portal_assignment_account,
        )

        backup = _assignable_employee_or_404(db, backup_employee_id)
        _require_portal_assignment_account(db, backup)
        if backup.id == payload.assigned_employee_id:
            raise HTTPException(
                422, "Backup employee must be different from the assigned employee."
            )
    employee = None
    if payload.assigned_employee_id is not None:
        if not has_permission(current_user, "workforce:manage"):
            raise HTTPException(
                403,
                "Workforce management permission is required to assign employee work.",
            )
        if payload.status != "Pending":
            raise HTTPException(
                422,
                "Assigned work must start as Pending and use employee submission and manager approval.",
            )
        from app.routers.workforce_handlers import (
            _assignable_employee_or_404,
            _require_portal_assignment_account,
            _require_assignment_availability,
        )

        employee = _assignable_employee_or_404(db, payload.assigned_employee_id)
        _require_portal_assignment_account(db, employee)
        _require_assignment_availability(
            db,
            employee,
            payload.activity_date,
            allow_override=allow_unavailable_override,
        )
    elif payload.status in {"Submitted for Review", "Returned"}:
        raise HTTPException(
            422, "New events cannot start with a submission or correction status."
        )
    if payload.source_module not in {None, "Crop", "Livestock", "Inventory"}:
        raise HTTPException(422, "Invalid related farm record type.")
    if bool(payload.source_module) != bool(payload.source_record_id):
        raise HTTPException(
            422,
            "Select a specific related farm record, or leave the record type empty.",
        )
    domain = event_domain(payload.category)
    expected_module = "Inventory" if domain == "Equipment" else domain
    if (
        payload.source_record_id
        and domain != "General"
        and payload.source_module != expected_module
    ):
        raise HTTPException(
            422, "The related record must match the selected event type."
        )
    if domain == "Inventory" and not (
        payload.source_module == "Inventory" and payload.source_record_id
    ):
        raise HTTPException(
            422,
            "Select the inventory item to restock before scheduling this event.",
        )
    target = None
    if (
        payload.source_module in {"Crop", "Livestock", "Inventory"}
        and payload.source_record_id
    ):
        target = db.get(
            {"Crop": Crop, "Livestock": Livestock, "Inventory": InventoryItem}[
                payload.source_module
            ],
            payload.source_record_id,
        )
        if target is None or target.is_archived:
            raise HTTPException(
                422, "The selected related record is missing or archived."
            )
    if (
        target is not None
        and payload.source_module == "Crop"
        and target.status in {"Harvested", "Failed"}
    ):
        raise HTTPException(
            422, "Work cannot be scheduled for a harvested or failed crop cycle."
        )
    if (
        target is not None
        and payload.source_module == "Livestock"
        and int(target.quantity or 0) <= 0
    ):
        raise HTTPException(
            422, "Work requires an active livestock record with animals."
        )
    if employee is not None and domain in {"Crop", "Livestock"} and target is None:
        raise HTTPException(
            422,
            "Select the related crop or livestock record before assigning this work.",
        )
    planning_inventory = payload.source_module == "Inventory" and target is not None
    record_location = (
        getattr(
            target,
            {
                "Crop": "field",
                "Livestock": "pen_location",
                "Inventory": "location",
            }.get(payload.source_module, "location"),
            None,
        )
        if target is not None
        else None
    )
    if target is not None and not str(record_location or "").strip():
        raise HTTPException(
            422,
            "The related record has no field, pen or warehouse. Set its location in the management page before scheduling the event.",
        )
    if planning_inventory and domain not in {"Inventory", "Equipment"}:
        raise HTTPException(
            422,
            "Inventory records can be linked to restocking or equipment maintenance events.",
        )
    if (
        planning_inventory
        and domain == "Equipment"
        and not is_equipment_category(target.category)
    ):
        raise HTTPException(
            422, "Select an equipment or tool record for equipment maintenance."
        )
    if planning_inventory and payload.planned_inventory_item_id:
        raise HTTPException(
            422,
            "A restocking or equipment plan cannot deduct a consumption resource.",
        )
    event_location = record_location if target is not None else payload.location
    event_source_type = (
        (
            "inventory_restock_plan"
            if domain == "Inventory"
            else "equipment_maintenance_plan"
        )
        if planning_inventory
        else (
            "manual_work"
            if payload.source_type == "manual"
            else payload.source_type or ("manual_work" if target else None)
        )
    )
    resource = None
    usage = payload.planned_usage_type
    if payload.planned_inventory_item_id:
        if employee is None or target is None:
            raise HTTPException(
                422,
                "Stock-linked work requires an employee and a crop/livestock record.",
            )
        resource = db.get(InventoryItem, payload.planned_inventory_item_id)
        if resource is None or resource.is_archived:
            raise HTTPException(
                422, "The selected inventory resource is missing or archived."
            )
        from app.routers.workforce_handlers import (
            _validate_task_resource_choice,
            _infer_usage_type,
        )

        _validate_task_resource_choice(
            module=payload.source_module,
            item=resource,
            task_text=f"{payload.name} {payload.category}",
        )
        if not payload.planned_quantity:
            raise HTTPException(
                422,
                "Enter a positive planned quantity for the linked inventory resource.",
            )
        if payload.planned_quantity > float(resource.quantity or 0):
            raise HTTPException(
                422,
                f"Insufficient stock for assignment. Planned {payload.planned_quantity:g} {resource.unit}, but only {float(resource.quantity or 0):g} {resource.unit} of {resource.name} is available.",
            )
        validate_planned_resource(resource, payload.activity_date)
        inferred_usage = _infer_usage_type(payload.source_module, resource)
        if usage and usage != inferred_usage:
            raise HTTPException(
                422,
                "The resource usage type must match the selected inventory category.",
            )
        usage = inferred_usage
    # Generator and manual creation take automation before the activity-code lock.
    acquire_transaction_lock(db, "automation:tasks", timeout_ms=1500)
    activity = FarmActivity(
        activity_code=next_record_code(
            db,
            namespace="activity",
            prefix="ACT",
            seed_model=FarmActivity,
            code_column=FarmActivity.activity_code,
        ),
        name=payload.name,
        category=payload.category,
        related_to=(
            (
                target.name
                if payload.source_module in {"Crop", "Inventory"}
                else target.record_name
            )
            + (f" — {record_location}" if not planning_inventory else "")
        )[:150]
        if target
        else payload.related_to,
        location=event_location,
        description=clean_optional_text(payload.description),
        activity_date=payload.activity_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration=clean_optional_text(payload.duration),
        assigned_by=current_user.full_name,
        assigned_to=employee.full_name if employee else payload.assigned_to,
        assigned_employee_id=employee.id if employee else None,
        default_employee_id=employee.id if employee else None,
        assignment_source="manual",
        backup_employee_id=backup_employee_id,
        time_sensitive=time_sensitive,
        controlled_rescheduling=controlled_rescheduling,
        max_delay_minutes=max_delay_minutes,
        instructions=clean_optional_text(payload.instructions),
        requires_review=True if employee else payload.requires_review,
        requires_evidence=payload.requires_evidence,
        planned_quantity=payload.planned_quantity,
        planned_unit=(
            resource.unit if resource else clean_optional_text(payload.planned_unit)
        ),
        planned_inventory_item_id=resource.id if resource else None,
        planned_usage_type=usage,
        recurring_rule=clean_optional_text(payload.recurring_rule),
        status=payload.status,
        priority=payload.priority,
        is_automatic=False,
        source_module=payload.source_module,
        source_type=event_source_type,
        source_record_id=payload.source_record_id,
        source_detail_id=payload.source_detail_id,
        source_code=payload.source_code,
        source_path={
            "Crop": "/crops",
            "Livestock": "/livestock",
            "Inventory": "/inventory",
        }.get(payload.source_module),
        source_key=None,
        completed_at=farm_now_naive() if payload.status == "Completed" else None,
        is_archived=False,
        created_by_user_id=current_user.id,
    )
    prepare_operational_occurrence(db, activity, target, payload.feeding_slot)
    if employee:
        from app.routers.workforce_handlers import _task_resource_profile

        profile = _task_resource_profile(db, activity)
        if profile["linked"]:
            validate_planned_resource(profile["item"], activity.activity_date)
            if profile["planned_quantity"] and profile["planned_quantity"] > float(
                profile["item"].quantity or 0
            ):
                raise HTTPException(
                    422, "Insufficient stock for the planned assignment."
                )
        if profile["required"] and not profile["linked"]:
            raise HTTPException(
                422,
                "This work uses inventory. Link its crop/livestock and inventory resource before saving. Seed use is recorded through Crops.",
            )
    db.add(activity)
    db.flush()
    if employee:
        record_assignment_change(
            db,
            activity,
            old_employee_id=None,
            new_employee_id=employee.id,
            assignment_source="manual",
            actor_user_id=current_user.id,
            actor_name=current_user.full_name,
            reason=assignment_reason,
        )
        recalculate_task_reassignment(db, activity)
    from app.services.farm_event_service import reconcile_event_holds

    reconcile_event_holds(db, tasks=[activity])
    return activity


def prepare_operational_occurrence(
    db: Session, task: FarmActivity, target, feeding_slot: str | None = None
) -> None:
    """Give planned operations the same identity used by their native module."""
    category = str(task.category or "").strip().casefold()
    feeding = task.source_module == "Livestock" and (
        category in {"livestock feeding", "feeding"}
        or task.source_type == "livestock_feeding"
        or task.planned_usage_type == "Feed"
    )
    harvest = task.source_module == "Crop" and (
        category in {"harvesting", "crop harvesting", "crop harvest"}
        or task.source_type == "crop_harvest"
    )
    if (task.source_type == "livestock_feeding" and not feeding) or (
        task.source_type == "crop_harvest" and not harvest
    ):
        raise HTTPException(
            422, "The operational work type must match its related farm record."
        )
    if not (feeding or harvest):
        return
    if target is None:
        if task.assigned_employee_id is None and task.source_type not in {
            "crop_harvest",
            "livestock_feeding",
        }:
            return  # An unlinked, unassigned calendar reminder has no performed work.
        raise HTTPException(
            422, "Select the related farm record before assigning this operation."
        )
    if task.status != "Pending":
        raise HTTPException(
            422,
            "Operational work must start as Pending and use employee submission and review.",
        )
    if feeding:
        from app.services.task_engine import _feeding_occurrences, _feeding_source_key

        occurrences = _feeding_occurrences(target.feed_times)
        slot = str(feeding_slot or "").strip()
        if not slot and len(occurrences) == 1:
            slot = occurrences[0][1]
        occurrence = next(
            (row for row in occurrences if row[1].casefold() == slot.casefold()), None
        )
        if occurrence is None:
            raise HTTPException(
                422, "Select a feeding slot from the livestock's feeding schedule."
            )
        if (
            target.feed_inventory_item_id
            and task.planned_inventory_item_id
            and task.planned_inventory_item_id != target.feed_inventory_item_id
        ):
            raise HTTPException(
                422,
                "Feeding must use the Feed Inventory item linked to this livestock record.",
            )
        item_id = task.planned_inventory_item_id or target.feed_inventory_item_id
        if not item_id:
            raise HTTPException(
                422, "Select a feed inventory item before assigning feeding."
            )
        item = db.get(InventoryItem, item_id)
        validate_planned_resource(item, task.activity_date)
        from app.routers.workforce_handlers import (
            _same_unit,
            _validate_task_resource_choice,
        )

        _validate_task_resource_choice(
            module="Livestock", item=item, task_text="Livestock Feeding"
        )
        if not _same_unit(item.unit, "kg"):
            raise HTTPException(422, "Livestock feeding inventory must use kg.")
        task.source_type = "livestock_feeding"
        task.source_detail_id = occurrence[0]
        task.source_key = _feeding_source_key(
            target.id, task.activity_date, occurrence[1]
        )
        task.name = f"{occurrence[1]} Feeding - {target.record_name}"[:150]
        task.category = "Livestock Feeding"
        task.planned_inventory_item_id = item.id
        task.planned_unit = item.unit
        task.planned_usage_type = "Feed"
        task.source_code = target.animal_code
    else:
        if task.planned_inventory_item_id:
            raise HTTPException(
                422,
                "Harvest tasks record actual yield in kg. Schedule any supply usage separately.",
            )
        task.source_type = "crop_harvest"
        task.source_key = f"crop:harvest:{target.id}:{task.activity_date.isoformat()}"
        task.source_code = target.crop_code
        task.category = "Harvesting"
        task.planned_unit = "kg"
    # The caller holds the generator lock before allocating an activity code.
    existing = db.scalar(
        select(FarmActivity).where(FarmActivity.source_key == task.source_key)
    )
    if existing is not None:
        raise HTTPException(
            409,
            f"This occurrence already exists as {existing.activity_code}. Open that task in Task Management; a duplicate was not created.",
            headers={"X-Existing-Task-Id": str(existing.id)},
        )
    task.requires_review = True


def assert_operational_workflow(task: FarmActivity) -> None:
    """Old generic operations require a deliberate reschedule, never silent reposting."""
    if (
        task.source_type not in {None, "manual", "manual_work"}
        or task.status == "Completed"
    ):
        return
    category = str(task.category or "").strip().casefold()
    if (
        category
        in {
            "livestock feeding",
            "feeding",
            "harvesting",
            "crop harvesting",
            "crop harvest",
        }
        or task.planned_usage_type == "Feed"
    ):
        raise HTTPException(
            409,
            "This older calendar reminder is not linked to an operational feeding or harvest occurrence. Schedule the work from its farm record or create a linked feeding/harvest assignment. No stock or yield was posted.",
        )
