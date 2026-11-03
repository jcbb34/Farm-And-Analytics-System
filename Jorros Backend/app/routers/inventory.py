from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import case, extract, func, or_, select
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.core.database import get_db
from app.core.dependencies import has_permission, require_permission
from app.models import (
    AuditLog,
    InventoryItem,
    InventoryStockRecord,
    ResourceUsage,
    User,
)
from app.routers.auth import get_current_user
from app.services.task_engine import evaluate_automatic_tasks
from app.services.db_concurrency import acquire_transaction_lock
from app.services.idempotency import (
    begin_creation_command, normalize_idempotency_key, record_creation_command,
    request_fingerprint,
)
from app.services.inventory_audit import inventory_snapshot, record_inventory_change
from app.schemas.inventory import (
    ALLOWED_STOCK_ADJUSTMENT_TYPES,
    InventoryCreate,
    InventoryDetailsResponse,
    InventoryResponse,
    InventoryStockAdjustmentCreate,
    InventoryStockRecordResponse,
    InventoryUpdate,
)


router = APIRouter(
    prefix="/api/v1/inventory",
    dependencies=[Depends(require_permission("inventory:view"))],
    tags=["Inventory"],
)

# =========================================================
# HELPERS
# =========================================================

def require_inventory_creator(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "inventory:create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create inventory records.",
        )
    return current_user


def require_inventory_archiver(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "inventory:archive"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to archive or restore inventory records.",
        )
    return current_user


def require_inventory_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "inventory:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage inventory records.",
        )
    return current_user


def require_inventory_adjuster(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "inventory:adjust"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to adjust inventory stock.",
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



def get_inventory_or_404(
    inventory_id: int,
    db: Session,
) -> InventoryItem:
    statement = (
        select(InventoryItem)
        .where(InventoryItem.id == inventory_id)
        .options(
            selectinload(InventoryItem.stock_history)
        )
    )

    item = db.scalar(statement)

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found.",
        )

    return item



def lock_inventory_or_404(
    inventory_id: int,
    db: Session,
) -> InventoryItem:
    statement = select(InventoryItem).where(InventoryItem.id == inventory_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "mssql":
        statement = statement.with_hint(
            InventoryItem,
            "WITH (UPDLOCK, ROWLOCK)",
            dialect_name="mssql",
        )
    else:
        statement = statement.with_for_update()

    item = db.scalar(statement)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found.",
        )
    return item


def ensure_inventory_not_archived(item: InventoryItem):
    if item.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Archived inventory records cannot be modified. "
                "Restore the record first."
            ),
        )


def generate_item_code(db: Session) -> str:
    acquire_transaction_lock(db, "code:inventory")
    existing_codes = db.scalars(
        select(InventoryItem.item_code)
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

    return f"INV-{highest_number + 1}"


def validate_inventory_dates(
    item: InventoryItem,
    changes: dict,
):
    date_acquired = changes.get(
        "date_acquired",
        item.date_acquired,
    )
    expiration_date = changes.get(
        "expiration_date",
        item.expiration_date,
    )

    if (
        expiration_date is not None
        and expiration_date < date_acquired
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Expiration date cannot be earlier than date acquired."
            ),
        )


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


# =========================================================
# GET ALL INVENTORY
# =========================================================

@router.get(
    "",
    response_model=list[InventoryResponse],
)
def list_inventory(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = select(InventoryItem).order_by(
        InventoryItem.id.desc()
    )

    if not include_archived:
        statement = statement.where(
            InventoryItem.is_archived == False
        )

    return list(db.scalars(statement).all())


# =========================================================
# PAGED INVENTORY AND SQL-BACKED SUMMARY
# =========================================================

@router.get("/page")
def inventory_page(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    category: str | None = None, supplier: str | None = None,
    stock_status: str | None = None, date_acquired: date | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    stmt = select(InventoryItem).where(InventoryItem.is_archived == False)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        stmt = stmt.where(or_(InventoryItem.item_code.ilike(needle), InventoryItem.name.ilike(needle),
                              InventoryItem.category.ilike(needle), InventoryItem.supplier.ilike(needle),
                              InventoryItem.location.ilike(needle)))
    if category and category != "All":
        stmt = stmt.where(InventoryItem.category == category)
    if supplier and supplier != "All":
        stmt = stmt.where(InventoryItem.supplier == supplier)
    if date_acquired:
        stmt = stmt.where(InventoryItem.date_acquired == date_acquired)
    if stock_status == "Out of Stock":
        stmt = stmt.where(InventoryItem.quantity <= 0)
    elif stock_status == "Low Stock":
        stmt = stmt.where(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.reorder_level)
    elif stock_status == "In Stock":
        stmt = stmt.where(InventoryItem.quantity > 0, InventoryItem.quantity > InventoryItem.reorder_level)
    elif stock_status not in (None, "All"):
        raise HTTPException(status_code=422, detail="Invalid stock status.")
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(InventoryItem.id.desc()).offset(offset).limit(limit)).all())
    return {"items": [InventoryResponse.model_validate(item).model_dump(mode="json") for item in items],
            "total": total, "offset": offset, "limit": limit}


@router.get("/summary")
def inventory_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Exact overview and bounded monitoring panels, independent of the visible page."""
    table = InventoryItem
    active = table.is_archived == False
    attention = or_(table.quantity <= 0, table.quantity <= table.reorder_level)
    total, in_stock, low, empty, value, supplier_count = db.execute(select(
        func.count(table.id),
        func.sum(case(((table.quantity > 0) & (table.quantity > table.reorder_level), 1), else_=0)),
        func.sum(case(((table.quantity > 0) & (table.quantity <= table.reorder_level), 1), else_=0)),
        func.sum(case((table.quantity <= 0, 1), else_=0)),
        func.sum(table.quantity * table.cost),
        func.count(func.distinct(table.supplier)),
    ).where(active)).one()
    category_rows = db.execute(select(table.category, func.sum(table.quantity * table.cost))
                               .where(active).group_by(table.category).order_by(table.category)).all()
    supplier_rows = db.execute(select(
        table.supplier, func.count(table.id), func.sum(table.quantity),
        func.sum(table.quantity * table.cost),
        func.sum(case((attention, 1), else_=0)), func.max(table.date_acquired),
    ).where(active).group_by(table.supplier).order_by(table.supplier)).all()
    low_items = db.scalars(select(table).where(active, attention)
                           .order_by(table.quantity, table.id).limit(25)).all()
    expiry_items = db.scalars(select(table).where(active, table.expiration_date.is_not(None))
                              .order_by(table.expiration_date, table.id).limit(25)).all()
    return {
        "total": total, "in_stock": in_stock or 0, "low_stock": low or 0,
        "out_of_stock": empty or 0, "total_value": float(value or 0),
        "supplier_count": supplier_count,
        "categories": sorted([row[0] for row in category_rows if row[0]]),
        "suppliers": sorted([row[0] for row in supplier_rows if row[0]]),
        "category_values": [{"category": category, "value": float(amount or 0)}
                            for category, amount in sorted(category_rows, key=lambda row: row[1] or 0, reverse=True)],
        "supplier_performance": [{"supplier": name, "itemCount": count,
                                  "totalQuantity": float(quantity or 0), "inventoryValue": float(amount or 0),
                                  "attentionItems": count_attention or 0,
                                  "latestDelivery": acquired.isoformat() if acquired else ""}
                                 for name, count, quantity, amount, count_attention, acquired in
                                 sorted(supplier_rows, key=lambda row: row[3] or 0, reverse=True)[:25]],
        "low_stock_items": [InventoryResponse.model_validate(item).model_dump(mode="json") for item in low_items],
        "expiration_items": [InventoryResponse.model_validate(item).model_dump(mode="json") for item in expiry_items],
        "expiration_count": db.scalar(select(func.count(table.id)).where(
            active, table.expiration_date.is_not(None))) or 0,
    }


# =========================================================
# SIX-MONTH STOCK MOVEMENT SUMMARY
# =========================================================

@router.get("/movements/summary")
def inventory_movement_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Six-month movement chart without shipping every stock-history row."""
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    first_month = today.year * 12 + today.month - 6
    month_start = datetime((first_month // 12), (first_month % 12) + 1, 1).date()
    delta = case(
        (InventoryStockRecord.adjustment_type == "Set Exact Quantity",
         InventoryStockRecord.new_quantity - InventoryStockRecord.previous_quantity),
        (InventoryStockRecord.adjustment_type == "Restock", InventoryStockRecord.quantity),
        else_=-InventoryStockRecord.quantity,
    )
    year = extract("year", InventoryStockRecord.adjustment_date)
    month = extract("month", InventoryStockRecord.adjustment_date)
    rows = db.execute(select(
        year, month,
        func.sum(case((delta >= 0, delta), else_=0)),
        func.sum(case((delta < 0, -delta), else_=0)),
    ).join(InventoryItem, InventoryStockRecord.inventory_item_id == InventoryItem.id)
        .where(InventoryItem.is_archived == False,
               InventoryStockRecord.adjustment_date >= month_start,
               InventoryStockRecord.adjustment_date <= today)
        .group_by(year, month)).all()
    return [{"month": f"{int(year_value):04d}-{int(month_value):02d}",
             "incoming": float(incoming or 0), "outgoing": float(outgoing or 0)}
            for year_value, month_value, incoming, outgoing in rows]


# =========================================================
# GET ALL INVENTORY WITH STOCK HISTORY
# =========================================================

@router.get(
    "/details",
    response_model=list[InventoryDetailsResponse],
)
def list_inventory_details(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = (
        select(InventoryItem)
        .options(
            selectinload(InventoryItem.stock_history)
        )
        .order_by(InventoryItem.id.desc())
    )

    if not include_archived:
        statement = statement.where(
            InventoryItem.is_archived == False
        )

    return list(db.scalars(statement).all())


# =========================================================
# GET ONE INVENTORY ITEM
# =========================================================

@router.get(
    "/{inventory_id}",
    response_model=InventoryDetailsResponse,
)
def get_inventory_item(
    inventory_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return get_inventory_or_404(inventory_id, db)


# =========================================================
# CREATE INVENTORY ITEM
# =========================================================

@router.post(
    "",
    response_model=InventoryDetailsResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item(
    payload: InventoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_inventory_creator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not isinstance(idempotency_key, (str, type(None))):
        idempotency_key = None
    fingerprint = request_fingerprint(payload)
    try:
        existing = begin_creation_command(
            db, idempotency_key=idempotency_key, command_type="inventory_create",
            request_hash=fingerprint, user_id=current_user.id,
        )
        if existing:
            item = db.get(InventoryItem, existing.target_id)
            if item is None:
                raise HTTPException(409, "The original inventory record is no longer available; no duplicate was created.")
            return get_inventory_or_404(item.id, db)
        return _create_inventory_item(db, payload, current_user, idempotency_key, fingerprint)
    except Exception:
        db.rollback()
        raise


def _create_inventory_item(db, payload, current_user, idempotency_key, fingerprint):
    item = InventoryItem(
        item_code=generate_item_code(db),
        name=payload.name.strip(),
        category=payload.category.strip(),
        batch_number=clean_optional_text(payload.batch_number),
        quantity=payload.quantity,
        unit=payload.unit.strip(),
        reorder_level=payload.reorder_level,
        cost=payload.cost,
        price=payload.price,
        is_saleable=payload.is_saleable,
        supplier=payload.supplier.strip(),
        date_acquired=payload.date_acquired,
        expiration_date=payload.expiration_date,
        location=payload.location.strip(),
        description=clean_optional_text(payload.description),
        notes=clean_optional_text(payload.notes),
        is_archived=False,
        created_by_user_id=current_user.id,
    )

    db.add(item)
    db.flush()

    if payload.quantity > 0:
        initial_record = InventoryStockRecord(
            inventory_item_id=item.id,
            adjustment_type="Restock",
            quantity=payload.quantity,
            previous_quantity=0,
            new_quantity=payload.quantity,
            adjustment_date=payload.date_acquired,
            reason="Initial inventory quantity.",
            reference="Initial record",
            supplier=payload.supplier.strip(),
            recorded_by_user_id=current_user.id,
        )
        db.add(initial_record)

    record_inventory_change(db, item, current_user, action="Created inventory record")
    record_creation_command(
        db, idempotency_key=idempotency_key, command_type="inventory_create",
        request_hash=fingerprint, target_id=item.id, user_id=current_user.id,
    )
    db.commit()

    return get_inventory_or_404(item.id, db)


# =========================================================
# UPDATE INVENTORY ITEM
# =========================================================

@router.put(
    "/{inventory_id}",
    response_model=InventoryDetailsResponse,
)
def update_inventory_item(
    inventory_id: int,
    payload: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_inventory_editor),
):
    try:
        return _update_inventory_item(inventory_id, payload, db, current_user)
    except Exception:
        db.rollback()
        raise


def _update_inventory_item(inventory_id, payload, db, current_user):
    item = get_inventory_or_404(inventory_id, db)
    ensure_inventory_not_archived(item)

    changes = payload.model_dump(exclude_unset=True)
    validate_inventory_dates(item, changes)

    if (
        "unit" in changes
        and changes["unit"] != item.unit
        and item.stock_history
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unit cannot be changed after stock movement history exists. "
                "Create a separate inventory item for a different unit."
            ),
        )

    before = inventory_snapshot(item)
    text_fields = {
        "name",
        "category",
        "batch_number",
        "unit",
        "supplier",
        "location",
        "description",
        "notes",
    }

    for field_name, value in changes.items():
        if field_name in text_fields and isinstance(value, str):
            if field_name in {"description", "notes", "batch_number"}:
                value = clean_optional_text(value)
            else:
                value = value.strip()

        setattr(item, field_name, value)

    item.updated_at = datetime.now()

    record_inventory_change(db, item, current_user, action="Updated inventory record", before=before)
    db.flush()
    evaluate_automatic_tasks(
        db,
        commit=False,
    )
    db.commit()

    return get_inventory_or_404(item.id, db)


# =========================================================
# ARCHIVE INVENTORY ITEM
# =========================================================

@router.post(
    "/{inventory_id}/archive",
    response_model=InventoryResponse,
)
def archive_inventory_item(
    inventory_id: int,
    payload: ArchiveRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_inventory_archiver),
):
    record = change_archive_state(db, "Inventory", inventory_id, _, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# RESTORE INVENTORY ITEM
# =========================================================

@router.post(
    "/{inventory_id}/restore",
    response_model=InventoryResponse,
)
def restore_inventory_item(
    inventory_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_inventory_archiver),
):
    record = change_archive_state(db, "Inventory", inventory_id, _, archive=False)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# PERMANENTLY DELETE ARCHIVED INVENTORY ITEM
# =========================================================

@router.delete(
    "/{inventory_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
)
def permanently_delete_inventory_item(
    inventory_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_system_admin),
):
    permanent_delete(db, "Inventory", inventory_id, _)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================
# STOCK ADJUSTMENT
# =========================================================

def _run_stock_adjustment_task_sync() -> None:
    """Refresh automatic tasks after the response using a fresh DB session."""
    # Import lazily so route/unit-test imports do not require a configured
    # SQL Server engine merely to define the endpoint.
    from app.core.database import SessionLocal

    background_db = SessionLocal()
    try:
        evaluate_automatic_tasks(background_db)
    except Exception as error:
        background_db.rollback()
        print("Post-adjustment task synchronization failed:")
        print(error)
    finally:
        background_db.close()


@router.post(
    "/{inventory_id}/stock-adjustments",
    response_model=InventoryStockRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_stock_adjustment(
    inventory_id: int,
    payload: InventoryStockAdjustmentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_inventory_adjuster),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    normalized_key = normalize_idempotency_key(idempotency_key)
    payload_hash = request_fingerprint(payload)

    # A double-click, browser retry, or slow-network retry must resolve to the
    # original stock movement instead of creating a second movement.
    if normalized_key is not None:
        acquire_transaction_lock(db, f"inventory-stock-adjust:{normalized_key}")
        existing = db.scalar(
            select(InventoryStockRecord).where(
                InventoryStockRecord.idempotency_key == normalized_key
            )
        )
        if existing is not None:
            if (
                existing.inventory_item_id != inventory_id
                or existing.recorded_by_user_id != current_user.id
                or existing.request_hash != payload_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This Idempotency-Key was already used for a different "
                        "stock adjustment request."
                    ),
                )
            return existing

    item = lock_inventory_or_404(inventory_id, db)
    ensure_inventory_not_archived(item)

    if payload.adjustment_type not in ALLOWED_STOCK_ADJUSTMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stock adjustment type.",
        )

    previous_quantity = float(item.quantity)
    adjustment_quantity = float(payload.quantity)

    if (
        payload.adjustment_type == "Stock Usage"
        and item.expiration_date is not None
        and payload.adjustment_date > item.expiration_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Expired inventory cannot be recorded as Stock Usage. "
                "Use the Expired adjustment type instead."
            ),
        )

    if payload.adjustment_type in {"Restock", "Returned"}:
        new_quantity = previous_quantity + adjustment_quantity
    elif payload.adjustment_type == "Set Exact Quantity":
        new_quantity = adjustment_quantity
    else:
        if adjustment_quantity > previous_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "The quantity to remove is greater than the available stock."
                ),
            )
        new_quantity = previous_quantity - adjustment_quantity

    record = InventoryStockRecord(
        inventory_item_id=item.id,
        adjustment_type=payload.adjustment_type,
        quantity=adjustment_quantity,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        adjustment_date=payload.adjustment_date,
        reason=payload.reason.strip(),
        reference=clean_optional_text(payload.reference),
        supplier=clean_optional_text(payload.supplier),
        recorded_by_user_id=current_user.id,
        idempotency_key=normalized_key,
        request_hash=payload_hash if normalized_key is not None else None,
    )

    item.quantity = new_quantity

    if (
        payload.adjustment_type == "Restock"
        and payload.supplier
        and payload.supplier.strip()
    ):
        item.supplier = payload.supplier.strip()

    item.updated_at = datetime.now()

    db.add(record)

    movement_sign = "+" if payload.adjustment_type in {"Restock", "Returned"} else "-"
    if payload.adjustment_type == "Set Exact Quantity":
        movement_text = f"Set stock from {previous_quantity:g} to {new_quantity:g} {item.unit}."
    else:
        movement_text = (
            f"{payload.adjustment_type}: {movement_sign}{adjustment_quantity:g} {item.unit}. "
            f"Stock changed from {previous_quantity:g} to {new_quantity:g} {item.unit}."
        )

    audit_common = {
        "action": "Adjusted inventory stock",
        "module": "Inventory",
        "record_name": item.name,
        "entity_id": item.item_code,
        "details": f"{movement_text} Reason: {payload.reason.strip()}",
        "icon": "inventory_2",
        "actor_user_id": current_user.id,
        "actor_name": current_user.full_name,
    }
    db.add(AuditLog(event_type="audit", **audit_common))
    db.add(AuditLog(event_type="timeline", **audit_common))

    db.flush()
    db.commit()
    db.refresh(record)

    # Farm-wide task synchronization can take several seconds and may wait on
    # the automation lock. Run it after the HTTP response instead of holding
    # the stock-save request open. The 60-second scheduler remains a fallback.
    background_tasks.add_task(_run_stock_adjustment_task_sync)

    return record
