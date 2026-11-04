from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive, farm_today
from app.services.db_concurrency import acquire_transaction_lock

from app.models import (
    AuditLog,
    Crop,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    ResourceUsage,
    User,
)
from app.schemas.resource_usage import CROP_USAGE_TYPES, LIVESTOCK_USAGE_TYPES


CATEGORY_ALIASES = {
    "Seed": {"seed", "seeds", "planting material", "planting materials"},
    "Feed": {"livestock feed", "animal feed", "feed", "feeds"},
    "Vaccine": {"vaccine", "vaccines", "medicine", "animal medicine"},
    "Fertilizer": {"fertilizer", "fertilizers"},
    "Pesticide": {"pesticide", "pesticides"},
    "Herbicide": {"herbicide", "herbicides"},
    "Medicine": {"medicine", "medicines", "animal medicine", "livestock medicine"},
    "Vitamin / Supplement": {"vitamin", "vitamins", "supplement", "supplements", "vitamin supplement", "vitamin supplements"},
    "Disinfectant": {"disinfectant", "disinfectants"},
    "Treatment Supply": {"treatment supply", "treatment supplies", "medical supply", "medical supplies"},
    "Sanitation Supply": {"sanitation supply", "sanitation supplies", "sanitation", "cleaning supply", "cleaning supplies"},
}


def _normalized(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


def _clean_notes(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _get_item_locked(
    db: Session,
    item_id: int,
    *,
    allow_archived: bool = False,
) -> InventoryItem:
    db.flush()
    statement = select(InventoryItem).where(InventoryItem.id == item_id)
    # SQL Server does not implement SELECT ... FOR UPDATE the same way as
    # PostgreSQL. UPDLOCK keeps concurrent resource deductions from reading
    # the same available quantity before either transaction commits.
    statement = statement.with_hint(
        InventoryItem,
        "WITH (UPDLOCK, ROWLOCK)",
        dialect_name="mssql",
    )
    try:
        statement = statement.with_for_update()
    except Exception:
        pass
    item = db.scalar(statement.execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found.")
    if item.is_archived and not allow_archived:
        raise HTTPException(status_code=400, detail="Archived inventory items cannot be used.")
    return item


def _get_target(
    db: Session,
    module: str,
    target_id: int,
    *,
    allow_archived: bool = False,
):
    if module == "Crop":
        target = db.get(Crop, target_id)
        if target is None or (target.is_archived and not allow_archived):
            raise HTTPException(status_code=404, detail="Active crop record not found.")
        return target

    if module == "Livestock":
        target = db.get(Livestock, target_id)
        if target is None or (target.is_archived and not allow_archived):
            raise HTTPException(status_code=404, detail="Active livestock record not found.")
        return target

    raise HTTPException(status_code=400, detail="Invalid resource usage module.")


def _target_reference(module: str, target) -> str:
    if module == "Crop":
        return f"{target.name} ({target.crop_code})"
    return f"{target.record_name} ({target.animal_code})"

def _usage_basis(module: str, target) -> tuple[float | None, str | None]:
    if module == "Crop":
        area = float(target.area_hectares or 0)
        return (area if area > 0 else None, "ha" if area > 0 else None)
    head = float(target.quantity or 0)
    return (head if head > 0 else None, "animals" if head > 0 else None)


def _validate_usage_type(module: str, usage_type: str) -> None:
    allowed = CROP_USAGE_TYPES if module == "Crop" else LIVESTOCK_USAGE_TYPES
    if usage_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{usage_type} is not a valid {module.lower()} resource usage type.",
        )


def _validate_category(item: InventoryItem, usage_type: str) -> None:
    if usage_type == "Other":
        return
    aliases = CATEGORY_ALIASES.get(usage_type, set())
    category = _normalized(item.category)
    if category not in aliases:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{item.name} is categorized as {item.category}. "
                f"Select an inventory item categorized for {usage_type}."
            ),
        )


def _validate_expiration(item: InventoryItem, usage_date: date) -> None:
    if item.expiration_date and usage_date > item.expiration_date:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{item.name} expired on {item.expiration_date.isoformat()} "
                "and cannot be recorded as used after its expiration date."
            ),
        )


def _ensure_stock(item: InventoryItem, quantity: float, *, allow_negative: bool = False) -> None:
    available = float(item.quantity or 0)
    if not allow_negative and quantity > available + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock. Only {available:g} {item.unit} of "
                f"{item.name} is available."
            ),
        )


def _add_stock_record(
    db: Session,
    *,
    item: InventoryItem,
    usage: ResourceUsage | None,
    adjustment_type: str,
    movement_quantity: float,
    previous_quantity: float,
    new_quantity: float,
    movement_date: date,
    reason: str,
    reference: str,
    current_user: User,
) -> InventoryStockRecord:
    record = InventoryStockRecord(
        inventory_item_id=item.id,
        resource_usage_id=usage.id if usage is not None and usage.id else None,
        adjustment_type=adjustment_type,
        quantity=abs(float(movement_quantity)),
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        adjustment_date=movement_date,
        reason=reason,
        reference=reference,
        supplier=item.supplier,
        recorded_by_user_id=current_user.id,
    )
    db.add(record)
    return record


def _add_audit(
    db: Session,
    *,
    action: str,
    module: str,
    target,
    usage: ResourceUsage,
    details: str,
    current_user: User,
) -> None:
    record_name = _target_reference(module, target)
    common = {
        "action": action,
        "module": module,
        "record_name": record_name,
        "entity_id": str(target.id),
        "details": details,
        "icon": "inventory_2",
        "actor_user_id": current_user.id,
        "actor_name": current_user.full_name,
    }
    db.add(AuditLog(event_type="audit", **common))
    db.add(AuditLog(event_type="timeline", **common))


def create_usage(
    db: Session,
    *,
    module: str,
    target_id: int,
    inventory_item_id: int,
    usage_type: str,
    quantity: float,
    usage_date: date,
    notes: str | None,
    current_user: User,
    movement_type: str | None = None,
    allow_negative: bool = False,
    movement_reason: str | None = None,
) -> ResourceUsage:
    _validate_usage_type(module, usage_type)
    target = _get_target(db, module, target_id)
    if module == "Crop" and target.status in {"Harvested", "Failed"}:
        raise HTTPException(
            status_code=400,
            detail=f"Resource usage cannot be added to a {target.status.lower()} crop cycle.",
        )
    if module == "Crop" and usage_date < target.planting_date:
        raise HTTPException(
            status_code=400,
            detail="Crop resource usage date cannot be earlier than the planting date.",
        )
    item = _get_item_locked(db, inventory_item_id)
    _validate_category(item, usage_type)
    _validate_expiration(item, usage_date)
    _ensure_stock(item, quantity, allow_negative=allow_negative)

    previous = float(item.quantity or 0)
    new_quantity = previous - float(quantity)
    basis_value, basis_unit = _usage_basis(module, target)

    usage = ResourceUsage(
        inventory_item_id=item.id,
        module=module,
        crop_id=target.id if module == "Crop" else None,
        livestock_id=target.id if module == "Livestock" else None,
        usage_type=usage_type,
        quantity=quantity,
        unit=item.unit,
        item_code_snapshot=item.item_code,
        item_name_snapshot=item.name,
        category_snapshot=item.category,
        batch_number_snapshot=item.batch_number,
        basis_value=basis_value,
        basis_unit=basis_unit,
        usage_date=usage_date,
        notes=_clean_notes(notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(usage)
    db.flush()

    item.quantity = new_quantity
    item.updated_at = datetime.now()

    _add_stock_record(
        db,
        item=item,
        usage=usage,
        adjustment_type=movement_type or f"{module} Use",
        movement_quantity=quantity,
        previous_quantity=previous,
        new_quantity=new_quantity,
        movement_date=usage_date,
        reason=movement_reason or f"{usage_type} used for {_target_reference(module, target)}.",
        reference=_target_reference(module, target),
        current_user=current_user,
    )

    _add_audit(
        db,
        action=f"Recorded {usage_type.lower()} usage",
        module=module,
        target=target,
        usage=usage,
        details=(
            f"Used {float(quantity):g} {item.unit} of {item.name}. "
            f"Inventory changed from {previous:g} to {new_quantity:g} {item.unit}."
        ),
        current_user=current_user,
    )

    return usage


def _lock_usage(db: Session, usage: ResourceUsage) -> ResourceUsage:
    acquire_transaction_lock(db, f"resource-usage:{usage.id}")
    db.flush()
    statement = select(ResourceUsage).where(ResourceUsage.id == usage.id)
    if db.get_bind().dialect.name == "mssql":
        statement = statement.with_hint(ResourceUsage, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    else:
        statement = statement.with_for_update()
    row = db.scalar(statement.execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Resource usage record not found.")
    return row


def update_usage(
    db: Session,
    *,
    usage: ResourceUsage,
    changes: dict,
    current_user: User,
    movement_type: str | None = None,
    allow_negative: bool = False,
    movement_reason: str | None = None,
    allow_task_correction: bool = False,
) -> ResourceUsage:
    usage = _lock_usage(db, usage)
    if (usage.activity_id or usage.task_submission_id) and not allow_task_correction:
        raise HTTPException(409, "Task-linked usage must be corrected through its approved task in Task Management.")
    if usage.is_voided:
        raise HTTPException(status_code=400, detail="Voided resource usage cannot be edited.")

    target_id = usage.crop_id if usage.module == "Crop" else usage.livestock_id
    target = _get_target(
        db, usage.module, int(target_id or 0), allow_archived=True
    )

    old_quantity = float(usage.quantity or 0)
    new_item_id = int(changes.get("inventory_item_id") or usage.inventory_item_id)
    # Lock both stock rows in a consistent order for item-to-item corrections.
    items = {item_id: _get_item_locked(db, item_id, allow_archived=item_id == usage.inventory_item_id)
             for item_id in sorted({usage.inventory_item_id, new_item_id})}
    old_item = items[usage.inventory_item_id]
    new_usage_type = changes.get("usage_type") or usage.usage_type
    new_quantity_used = float(changes.get("quantity") or old_quantity)
    new_usage_date = changes.get("usage_date") or usage.usage_date
    new_notes = changes.get("notes", usage.notes)

    _validate_usage_type(usage.module, new_usage_type)

    if usage.module == "Crop" and new_usage_date < target.planting_date:
        raise HTTPException(
            status_code=400,
            detail="Crop resource usage date cannot be earlier than the planting date.",
        )

    if new_item_id == old_item.id:
        new_item = old_item
    else:
        new_item = items[new_item_id]

    _validate_category(new_item, new_usage_type)
    _validate_expiration(new_item, new_usage_date)

    reference = _target_reference(usage.module, target)

    if new_item.id == old_item.id:
        delta = new_quantity_used - old_quantity
        previous_stock = float(old_item.quantity or 0)

        if delta > 0:
            if old_item.is_archived:
                raise HTTPException(
                    status_code=400,
                    detail="Archived inventory items cannot have their usage increased.",
                )
            _ensure_stock(old_item, delta, allow_negative=allow_negative)
            resulting_stock = previous_stock - delta
            movement_label = movement_type or "Usage Correction"
            reason = movement_reason or (
                f"{new_usage_type} usage for {reference} increased from "
                f"{old_quantity:g} to {new_quantity_used:g} {old_item.unit}."
            )
        elif delta < 0:
            resulting_stock = previous_stock + abs(delta)
            movement_label = movement_type or "Usage Correction"
            reason = movement_reason or (
                f"{new_usage_type} usage for {reference} decreased from "
                f"{old_quantity:g} to {new_quantity_used:g} {old_item.unit}; "
                f"{abs(delta):g} {old_item.unit} returned to inventory."
            )
        else:
            resulting_stock = previous_stock
            movement_label = None
            reason = ""

        if movement_label:
            old_item.quantity = resulting_stock
            old_item.updated_at = datetime.now()
            _add_stock_record(
                db,
                item=old_item,
                usage=usage,
                adjustment_type=movement_label,
                movement_quantity=abs(delta),
                previous_quantity=previous_stock,
                new_quantity=resulting_stock,
                movement_date=new_usage_date,
                reason=reason,
                reference=reference,
                current_user=current_user,
            )
    else:
        # Return the old usage to the old item, then deduct the new usage from the replacement item.
        old_previous = float(old_item.quantity or 0)
        old_new = old_previous + old_quantity
        old_item.quantity = old_new
        old_item.updated_at = datetime.now()
        _add_stock_record(
            db,
            item=old_item,
            usage=usage,
            adjustment_type=movement_type or "Usage Restored",
            movement_quantity=old_quantity,
            previous_quantity=old_previous,
            new_quantity=old_new,
            movement_date=new_usage_date,
            reason=f"Usage item changed for {reference}; previous stock was restored.",
            reference=reference,
            current_user=current_user,
        )

        _ensure_stock(new_item, new_quantity_used, allow_negative=allow_negative)
        new_previous = float(new_item.quantity or 0)
        new_stock = new_previous - new_quantity_used
        new_item.quantity = new_stock
        new_item.updated_at = datetime.now()
        _add_stock_record(
            db,
            item=new_item,
            usage=usage,
            adjustment_type=movement_type or f"{usage.module} Use",
            movement_quantity=new_quantity_used,
            previous_quantity=new_previous,
            new_quantity=new_stock,
            movement_date=new_usage_date,
            reason=f"Replacement {new_usage_type} item used for {reference}.",
            reference=reference,
            current_user=current_user,
        )

    old_description = f"{old_quantity:g} {old_item.unit} of {old_item.name}"
    new_description = f"{new_quantity_used:g} {new_item.unit} of {new_item.name}"

    usage.inventory_item_id = new_item.id
    usage.usage_type = new_usage_type
    usage.quantity = new_quantity_used
    usage.unit = new_item.unit
    if new_item.id != old_item.id:
        usage.item_code_snapshot = new_item.item_code
        usage.item_name_snapshot = new_item.name
        usage.category_snapshot = new_item.category
        usage.batch_number_snapshot = new_item.batch_number
    usage.usage_date = new_usage_date
    usage.notes = _clean_notes(new_notes)
    usage.updated_at = datetime.now()

    _add_audit(
        db,
        action="Corrected resource usage",
        module=usage.module,
        target=target,
        usage=usage,
        details=f"Changed resource usage from {old_description} to {new_description}.",
        current_user=current_user,
    )
    return usage


def void_usage(
    db: Session,
    *,
    usage: ResourceUsage,
    reason: str,
    current_user: User,
    movement_type: str | None = None,
) -> ResourceUsage:
    if len(str(reason or "").strip()) < 2:
        raise HTTPException(400, "Enter a reason of at least two non-space characters.")
    usage = _lock_usage(db, usage)
    if usage.is_voided:
        raise HTTPException(status_code=400, detail="Resource usage is already voided.")

    target_id = usage.crop_id if usage.module == "Crop" else usage.livestock_id
    target = _get_target(
        db, usage.module, int(target_id or 0), allow_archived=True
    )
    item = _get_item_locked(
        db, usage.inventory_item_id, allow_archived=True
    )

    previous = float(item.quantity or 0)
    restored = float(usage.quantity or 0)
    new_quantity = previous + restored

    item.quantity = new_quantity
    item.updated_at = datetime.now()

    usage.is_voided = True
    usage.void_reason = reason.strip()
    usage.voided_at = datetime.now()
    usage.voided_by_user_id = current_user.id
    usage.updated_at = datetime.now()

    reference = _target_reference(usage.module, target)
    _add_stock_record(
        db,
        item=item,
        usage=usage,
        adjustment_type=movement_type or "Usage Restored",
        movement_quantity=restored,
        previous_quantity=previous,
        new_quantity=new_quantity,
        movement_date=farm_today(),
        reason=f"Voided {usage.usage_type} usage for {reference}: {reason.strip()}",
        reference=reference,
        current_user=current_user,
    )

    _add_audit(
        db,
        action="Voided resource usage",
        module=usage.module,
        target=target,
        usage=usage,
        details=(
            f"Restored {restored:g} {item.unit} of {item.name} to inventory. "
            f"Reason: {reason.strip()}"
        ),
        current_user=current_user,
    )
    return usage


def serialize_usage(db: Session, usage: ResourceUsage) -> dict:
    item = db.get(InventoryItem, usage.inventory_item_id)
    target = db.get(Crop, usage.crop_id) if usage.module == "Crop" else db.get(Livestock, usage.livestock_id)

    target_id = usage.crop_id if usage.module == "Crop" else usage.livestock_id
    target_name = "Unknown record"
    efficiency_value = None
    efficiency_label = None

    if usage.module == "Crop" and target is not None:
        target_name = f"{target.name} ({target.crop_code})"
    elif usage.module == "Livestock" and target is not None:
        target_name = f"{target.record_name} ({target.animal_code})"

    basis = float(usage.basis_value or 0)
    if basis > 0:
        efficiency_value = round(float(usage.quantity or 0) / basis, 2)
        efficiency_label = (
            f"{usage.unit}/ha"
            if usage.basis_unit == "ha"
            else f"{usage.unit}/animal"
        )

    return {
        "id": usage.id,
        "module": usage.module,
        "activity_id": usage.activity_id,
        "task_submission_id": usage.task_submission_id,
        "target_id": int(target_id or 0),
        "target_name": target_name,
        "inventory_item_id": usage.inventory_item_id,
        "inventory_item_code": usage.item_code_snapshot or (item.item_code if item else ""),
        "inventory_item_name": usage.item_name_snapshot or (item.name if item else "Unknown Item"),
        "inventory_category": usage.category_snapshot or (item.category if item else ""),
        "batch_number": usage.batch_number_snapshot,
        "basis_value": float(usage.basis_value) if usage.basis_value is not None else None,
        "basis_unit": usage.basis_unit,
        "usage_type": usage.usage_type,
        "quantity": float(usage.quantity or 0),
        "unit": usage.unit,
        "usage_date": usage.usage_date,
        "notes": usage.notes,
        "is_voided": bool(usage.is_voided),
        "void_reason": usage.void_reason,
        "available_quantity": float(item.quantity or 0) if item else 0,
        "efficiency_value": efficiency_value,
        "efficiency_label": efficiency_label,
        "recorded_by_user_id": usage.recorded_by_user_id,
        "created_at": usage.created_at,
        "updated_at": usage.updated_at,
    }


def build_summary(
    db: Session,
    start_date: date,
    end_date: date,
    *,
    allowed_modules: set[str] | None = None,
) -> dict:
    statement = select(ResourceUsage).where(
        ResourceUsage.is_voided == False,
        ResourceUsage.usage_date >= start_date,
        ResourceUsage.usage_date <= end_date,
    )
    if allowed_modules is not None:
        statement = statement.where(ResourceUsage.module.in_(sorted(allowed_modules)))

    usages = list(db.scalars(statement).all())

    totals = defaultdict(float)
    item_totals = defaultdict(float)
    for usage in usages:
        totals[(usage.module, usage.usage_type, usage.unit)] += float(usage.quantity or 0)
        item_totals[(usage.inventory_item_id, usage.unit)] += float(usage.quantity or 0)

    items = {
        item.id: item
        for item in db.scalars(
            select(InventoryItem).where(InventoryItem.is_archived == False)
        ).all()
    }
    today = farm_today()
    expiring_limit = today + timedelta(days=30)
    low_stock_items = sum(
        1
        for item in items.values()
        if float(item.quantity or 0) <= float(item.reorder_level or 0)
    )
    expiring_items = sum(
        1
        for item in items.values()
        if float(item.quantity or 0) > 0
        and item.expiration_date is not None
        and today <= item.expiration_date <= expiring_limit
    )

    top_items = sorted(item_totals.items(), key=lambda kv: kv[1], reverse=True)[:8]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_records": len(usages),
        "totals": [
            {
                "module": module,
                "usage_type": usage_type,
                "unit": unit,
                "quantity": round(quantity, 2),
            }
            for (module, usage_type, unit), quantity in sorted(totals.items())
        ],
        "top_items": [
            {
                "inventory_item_id": item_id,
                "item_name": items.get(item_id).name if items.get(item_id) else "Unknown Item",
                "unit": unit,
                "quantity": round(quantity, 2),
            }
            for (item_id, unit), quantity in top_items
        ],
        "low_stock_items": low_stock_items,
        "expiring_items": expiring_items,
    }
