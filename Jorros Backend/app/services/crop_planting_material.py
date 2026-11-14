"""New planting material requirements and reservations.

One inventory unit per planting position unless an authorized, explicitly
configured seed/lot conversion says otherwise. No guesses from free text names.
"""
from datetime import time
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from app.models import Crop, CropSection, FarmActivity, InventoryItem
from app.models.workforce import Employee
from app.services.db_concurrency import acquire_transaction_lock
from app.services.crop_planting_material_catalog import material_method

CATEGORIES = {"seeds", "seed", "seedlings", "seedling", "planting material", "planting materials", "cuttings", "suckers", "corms"}
COUNT_UNITS = {"pieces", "piece", "pcs", "pc", "units", "unit", "seeds", "seedlings", "plants", "cuttings", "suckers", "corms", "setts"}
MATERIAL_KINDS = {"seed", "seedling", "sucker", "cutting", "corm", "sett", "plantlet"}
OPEN_STATES = {"Pending", "In Progress", "Returned", "Submitted for Review"}


def validate_material_tag(item, *, require_for_planting_category=False):
    tagged = [item.planting_crop_reference, item.planting_variety_reference,
              item.planting_material_kind, item.planting_units_per_position]
    if not any(v is not None for v in tagged):
        if require_for_planting_category and str(item.category).strip().lower() in CATEGORIES:
            raise HTTPException(422, "Choose a built-in crop and exact variety for this seed or planting material.")
        return
    if not all(v is not None for v in tagged):
        raise HTTPException(422, "Planting material requires a crop, exact variety, material type and units per position.")
    if str(item.category).strip().lower() not in CATEGORIES:
        raise HTTPException(422, "Tagged planting material must use a Seeds, Seedlings or Planting Material inventory category.")
    if str(item.unit).strip().lower() not in COUNT_UNITS:
        raise HTTPException(422, "Planting material must be counted in individual units. Use a separate item or a verified conversion for kilograms, grams, bags or packs.")
    if str(item.planting_material_kind).strip().lower() not in MATERIAL_KINDS:
        raise HTTPException(422, "Choose a valid planting material type (seed, seedling, sucker, cutting, corm, sett or plantlet).")
    method = material_method(item.planting_crop_reference, item.planting_variety_reference, item.planting_material_kind)
    if method is None:
        raise HTTPException(422, "The selected planting material type is not supported for this crop and variety. Choose a compatible built-in reference.")
    if str(item.category).strip().lower() != method["category"].lower():
        raise HTTPException(422, f"{item.planting_material_kind.title()} for this crop must use the {method['category']} inventory category.")
    if item.planting_units_per_position < 1 or item.planting_units_per_position > 100:
        raise HTTPException(422, "Units per planting position must be from 1 to 100.")


def compatible(item, crop_key, variety_key, planting_date=None):
    if item is None or item.is_archived:
        return False
    try:
        validate_material_tag(item)
    except HTTPException:
        return False
    return bool(item.planting_crop_reference and item.planting_variety_reference and
                item.planting_crop_reference == crop_key and item.planting_variety_reference == variety_key and
                (item.expiration_date is None or planting_date is None or item.expiration_date >= planting_date))


def reserved_quantity(db, inventory_item_id, *, omit_task_id=None):
    """Reserve all not-yet-posted planting assignments; do not double count other task types."""
    rows = db.scalars(select(FarmActivity).where(
        FarmActivity.planned_inventory_item_id == inventory_item_id,
        FarmActivity.source_type == "crop_planting",
        FarmActivity.is_archived == False,
        FarmActivity.status.in_(OPEN_STATES),
    )).all()
    return sum(Decimal(str(x.planned_quantity or 0)) for x in rows if x.id != omit_task_id)


def stock_options(db, crop_key, variety_key, *, planting_date=None, planned_count=None):
    if not crop_key or not variety_key:
        return []
    rows = db.scalars(select(InventoryItem).where(
        InventoryItem.planting_crop_reference == crop_key,
        InventoryItem.planting_variety_reference == variety_key,
        InventoryItem.is_archived == False,
    ).order_by(InventoryItem.name, InventoryItem.id)).all()
    result = []
    for item in rows:
        if not compatible(item, crop_key, variety_key, planting_date):
            continue
        reserved = reserved_quantity(db, item.id)
        on_hand = Decimal(str(item.quantity or 0))
        available = max(Decimal(0), on_hand - reserved)
        needed = (int(planned_count) * item.planting_units_per_position) if planned_count is not None else None
        result.append({"id": item.id, "code": item.item_code, "name": item.name,
                       "category": item.category, "material_kind": item.planting_material_kind,
                       "unit": item.unit, "units_per_position": item.planting_units_per_position,
                       "on_hand": float(on_hand), "reserved": float(reserved),
                       "available": float(available), "required": needed,
                       "sufficient": (available >= needed if needed is not None else None)})
    return result


def lock_validate_planting_material(db, payload, crop):
    if not payload.planting_inventory_item_id:
        raise HTTPException(422, "Choose the exact matching seed, seedling or planting material in Inventory before saving a new crop.")
    if crop.quantity_planted is None or crop.quantity_planted <= 0:
        raise HTTPException(422, "Enter the number of planting positions to fill before reserving materials.")
    acquire_transaction_lock(db, f"inventory-task-reservation:{payload.planting_inventory_item_id}")
    statement = select(InventoryItem).where(InventoryItem.id == payload.planting_inventory_item_id)
    statement = statement.with_hint(InventoryItem, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    item = db.scalar(statement.with_for_update())
    if not compatible(item, crop.crop_reference, crop.variety_reference, crop.planting_date):
        raise HTTPException(422, "This stock item is not tagged for the selected crop and variety, is archived, or expires before the planting date.")
    needed = int(crop.quantity_planted) * int(item.planting_units_per_position)
    available = Decimal(str(item.quantity or 0)) - reserved_quantity(db, item.id)
    if available < needed:
        raise HTTPException(409, f"Insufficient {item.name} for {crop.name} {crop.variety}: need {needed} {item.unit} for {crop.quantity_planted} planting positions, only {max(available, Decimal(0)):g} unreserved {item.unit} available. Restock or lower the planned quantity.")
    return item, needed


def create_planting_task(db, crop, payload, item, needed):
    """Create task and stock reservation in the caller's crop-registration transaction."""
    if not crop.assigned_employee_id:
        raise HTTPException(422, "Assign an active employee to perform the planting task.")
    employee = db.get(Employee, crop.assigned_employee_id)
    if employee is None or employee.is_archived or employee.employment_status != "Active":
        raise HTTPException(422, "The planting employee must be active and available in Workforce Management.")
    from app.services.task_engine import _upsert_automatic_task
    section = db.get(CropSection, crop.section_id) if crop.section_id else None
    place = f"{crop.field} / {section.name}" if section else crop.field
    when = payload.planting_start_time or time(8, 0)
    task, _ = _upsert_automatic_task(
        db, source_key=f"crop:planting:{crop.id}", source_module="Crop", source_type="crop_planting",
        source_record_id=crop.id, source_detail_id=None, source_code=crop.crop_code, source_path="/crops",
        name=f"Plant {crop.name} {crop.variety} — {section.name if section else crop.field}"[:150],
        category="Planting", related_to=f"{crop.name} {crop.variety} ({crop.crop_code})"[:150],
        location=place[:150],
        description=(f"Plant {crop.quantity_planted} positions using {needed} {item.unit} of {item.name} "
                     f"({item.item_code}); {item.planting_units_per_position} {item.unit} per position. "
                     "Record actual material usage in My Tasks. Stock is deducted only after approval."),
        activity_date=crop.planting_date, start_time=when, assigned_to=employee.full_name, priority="Medium",
    )
    task.planned_inventory_item_id = item.id
    task.planned_quantity = needed
    task.planned_unit = item.unit
    task.planned_usage_type = "Seed" if item.category.strip().lower() in {"seeds", "seed"} else "Planting Material"
    task.requires_review = True
    task.requires_evidence = False
    crop.planting_inventory_item_id = item.id
    crop.planting_material_required = needed
    crop.status = "Planting Scheduled"
    crop.growth_stage = "Not started"
    crop.current_growth = None
    db.flush()
    return task
