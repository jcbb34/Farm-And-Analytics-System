from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.services.db_concurrency import acquire_transaction_lock
from app.core.farm_time import farm_today

from app.models import (
    AuditLog,
    Crop,
    CropYieldRecord,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    LivestockProcessingRecord,
    LivestockGrowthRecord,
    LivestockPen,
    LivestockProductionRecord,
    LivestockReproductionRecord,
    LivestockSale,
    LivestockSaleItem,
    LivestockSalePayment,
    LivestockTransaction,
    User,
)


MONEY = Decimal("0.01")
QTY = Decimal("0.001")


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _audit(
    db: Session,
    *,
    action: str,
    record_name: str,
    entity_id: str,
    details: str,
    icon: str,
    actor_user_id: int | None,
    actor_name: str,
) -> None:
    common = dict(
        action=action,
        module="Production & Sales",
        record_name=record_name,
        entity_id=entity_id,
        details=details,
        icon=icon,
        actor_user_id=actor_user_id,
        actor_name=actor_name,
    )
    db.add(AuditLog(event_type="audit", **common))
    db.add(AuditLog(event_type="timeline", **common))


def get_livestock(db: Session, livestock_id: int, *, for_update: bool = False) -> Livestock:
    statement = select(Livestock).where(
        Livestock.id == livestock_id,
        Livestock.is_archived == False,
    )
    if for_update:
        if db.bind is not None and db.bind.dialect.name == "mssql":
            statement = statement.with_hint(
                Livestock, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql"
            )
        else:
            statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active livestock record not found.",
        )
    return record


def get_crop(db: Session, crop_id: int) -> Crop:
    record = db.get(Crop, crop_id)
    if record is None or bool(record.is_archived):
        raise HTTPException(status_code=404, detail="Active crop record not found.")
    return record


def _source_details(db: Session, *, livestock_id: int | None = None, crop_id: int | None = None):
    if crop_id:
        crop = db.get(Crop, crop_id)
        return (
            "Crop",
            crop.name if crop else "Unknown crop",
            crop.crop_code if crop else "",
            crop,
        )
    animal = db.get(Livestock, livestock_id) if livestock_id else None
    return (
        "Livestock",
        animal.record_name if animal else "Unknown livestock",
        animal.animal_code if animal else "",
        animal,
    )


def _production_sold_quantity(db: Session, production_record_id: int) -> Decimal:
    item_value = db.scalar(
        select(func.coalesce(func.sum(LivestockSaleItem.quantity), 0))
        .join(LivestockSale, LivestockSale.id == LivestockSaleItem.sale_id)
        .where(
            LivestockSaleItem.production_record_id == production_record_id,
            LivestockSale.is_voided == False,
        )
    )
    legacy_value = db.scalar(
        select(func.coalesce(func.sum(LivestockSale.quantity), 0)).where(
            LivestockSale.production_record_id == production_record_id,
            LivestockSale.is_voided == False,
            ~exists(
                select(LivestockSaleItem.id).where(
                    LivestockSaleItem.sale_id == LivestockSale.id
                )
            ),
        )
    )
    return _decimal(item_value) + _decimal(legacy_value)


def production_sold_map(
    db: Session,
    production_ids: list[int],
    *,
    through_date=None,
) -> dict[int, Decimal]:
    if not production_ids:
        return {}
    item_statement = (
        select(
            LivestockSaleItem.production_record_id,
            func.coalesce(func.sum(LivestockSaleItem.quantity), 0),
        )
        .join(LivestockSale, LivestockSale.id == LivestockSaleItem.sale_id)
        .where(
            LivestockSaleItem.production_record_id.in_(production_ids),
            LivestockSale.is_voided == False,
        )
        .group_by(LivestockSaleItem.production_record_id)
    )
    if through_date is not None:
        item_statement = item_statement.where(LivestockSale.sale_date <= through_date)
    item_rows = db.execute(item_statement).all()
    result = {
        int(record_id): _decimal(quantity)
        for record_id, quantity in item_rows
        if record_id is not None
    }
    legacy_statement = (
        select(
            LivestockSale.production_record_id,
            func.coalesce(func.sum(LivestockSale.quantity), 0),
        )
        .where(
            LivestockSale.production_record_id.in_(production_ids),
            LivestockSale.is_voided == False,
            ~exists(
                select(LivestockSaleItem.id).where(
                    LivestockSaleItem.sale_id == LivestockSale.id
                )
            ),
        )
        .group_by(LivestockSale.production_record_id)
    )
    if through_date is not None:
        legacy_statement = legacy_statement.where(LivestockSale.sale_date <= through_date)
    legacy_rows = db.execute(legacy_statement).all()
    for record_id, quantity in legacy_rows:
        if record_id is not None:
            result[int(record_id)] = result.get(int(record_id), Decimal("0")) + _decimal(quantity)
    return result


def production_available_quantity(db: Session, record: LivestockProductionRecord) -> Decimal:
    if not record.track_sale_inventory:
        return Decimal("0")
    return max(
        Decimal("0"),
        _decimal(record.quantity) - _production_sold_quantity(db, record.id),
    )


def _production_destination(available: Decimal, original: Decimal) -> str:
    if available <= 0:
        return "Sold"
    if available < original:
        return "Partially sold"
    return "Available for sale"


def _production_period(record: LivestockProductionRecord):
    start = record.period_start_date or record.record_date
    end = record.period_end_date or record.record_date
    days = max(1, (end - start).days + 1)
    return start, end, days


def serialize_production(
    db: Session,
    record: LivestockProductionRecord,
    livestock: Livestock | None = None,
    sold_quantity: Decimal | None = None,
) -> dict:
    source_type = str(record.source_type or ("Crop" if record.crop_id else "Livestock")).title()
    crop = db.get(Crop, record.crop_id) if record.crop_id else None
    animal = livestock or (db.get(Livestock, record.livestock_id) if record.livestock_id else None)
    if source_type == "Crop":
        source_name = crop.name if crop else "Unknown crop"
        source_code = crop.crop_code if crop else ""
    else:
        source_name = animal.record_name if animal else "Unknown livestock"
        source_code = animal.animal_code if animal else ""

    sold = sold_quantity if sold_quantity is not None else _production_sold_quantity(db, record.id)
    saleable = _decimal(record.quantity)
    available = max(Decimal("0"), saleable - sold) if record.track_sale_inventory else Decimal("0")
    start, end, days = _production_period(record)
    laying_rate = None
    if "egg" in str(record.output_type or "").lower():
        layers = int(record.source_active_quantity or record.source_female_quantity or 0)
        gross = _decimal(record.gross_quantity if record.gross_quantity is not None else record.quantity)
        if layers > 0 and days > 0:
            laying_rate = round(float(gross) / float(layers * days) * 100, 2)

    return {
        "id": record.id,
        "source_type": source_type,
        "source_name": source_name,
        "source_code": source_code,
        "livestock_id": record.livestock_id,
        "livestock_name": animal.record_name if animal else None,
        "animal_code": animal.animal_code if animal else None,
        "crop_id": record.crop_id,
        "crop_yield_record_id": record.crop_yield_record_id,
        "output_type": record.output_type,
        "record_date": record.record_date,
        "period_start_date": start,
        "period_end_date": end,
        "production_days": days,
        "source_head_quantity": record.source_head_quantity,
        "source_female_quantity": record.source_female_quantity,
        "source_active_quantity": record.source_active_quantity,
        "gross_quantity": float(record.gross_quantity) if record.gross_quantity is not None else float(saleable),
        "loss_quantity": float(record.loss_quantity or 0),
        "farm_use_quantity": float(record.farm_use_quantity or 0),
        "reserved_quantity": float(record.reserved_quantity or 0),
        "laying_rate_percent": laying_rate,
        "quantity": float(saleable),
        "sold_quantity": float(sold),
        "available_quantity": float(available),
        "unit": record.unit,
        "quality_grade": record.quality_grade,
        "destination": record.destination,
        "track_sale_inventory": bool(record.track_sale_inventory),
        "notes": record.notes,
        "created_at": record.created_at,
    }


def serialize_reproduction(
    db: Session,
    record: LivestockReproductionRecord,
    livestock: Livestock | None = None,
) -> dict:
    animal = livestock or db.get(Livestock, record.livestock_id)
    offspring = (
        db.get(Livestock, record.offspring_livestock_id)
        if record.offspring_livestock_id
        else None
    )
    return {
        "id": record.id,
        "livestock_id": record.livestock_id,
        "livestock_name": animal.record_name if animal else "Unknown livestock",
        "animal_code": animal.animal_code if animal else "",
        "record_type": record.record_type,
        "event_date": record.event_date,
        "partner_reference": record.partner_reference,
        "breeding_method": record.breeding_method,
        "breeder_male_quantity": record.breeder_male_quantity,
        "breeder_female_quantity": record.breeder_female_quantity,
        "confirmed_pregnant_quantity": record.confirmed_pregnant_quantity,
        "eggs_set": record.eggs_set,
        "fertile_eggs": record.fertile_eggs,
        "incubation_method": record.incubation_method,
        "reproductive_status": record.reproductive_status,
        "expected_date": record.expected_date,
        "actual_date": record.actual_date,
        "offspring_count": record.offspring_count,
        "alive_offspring": record.alive_offspring,
        "male_offspring": record.male_offspring,
        "female_offspring": record.female_offspring,
        "loss_count": record.loss_count,
        "source_production_record_id": record.source_production_record_id,
        "notes": record.notes,
        "offspring_livestock_id": record.offspring_livestock_id,
        "offspring_record_name": offspring.record_name if offspring else None,
        "created_at": record.created_at,
    }


def serialize_sale_item(record: LivestockSaleItem) -> dict:
    return {
        "id": record.id,
        "line_number": record.line_number,
        "item_kind": record.item_kind,
        "source_type": record.source_type,
        "production_record_id": record.production_record_id,
        "livestock_id": record.livestock_id,
        "crop_id": record.crop_id,
        "inventory_item_id": record.inventory_item_id,
        "source_name": record.source_name_snapshot,
        "source_code": record.source_code_snapshot,
        "product_type": record.product_type,
        "quantity": float(record.quantity),
        "unit": record.unit,
        "unit_price": float(record.unit_price),
        "line_total": float(record.line_total),
        "male_quantity": int(record.male_quantity or 0),
        "female_quantity": int(record.female_quantity or 0),
        "unknown_quantity": int(record.unknown_quantity or 0),
        "healthy_quantity": int(record.healthy_quantity or 0),
    }


def serialize_sale(db: Session, sale: LivestockSale, livestock: Livestock | None = None) -> dict:
    source_type = str(sale.source_type or ("Crop" if sale.crop_id else "Livestock")).title()
    crop = db.get(Crop, sale.crop_id) if sale.crop_id else None
    animal = livestock or (db.get(Livestock, sale.livestock_id) if sale.livestock_id else None)
    item_records = list(
        db.scalars(
            select(LivestockSaleItem)
            .where(LivestockSaleItem.sale_id == sale.id)
            .order_by(LivestockSaleItem.line_number.asc())
        ).all()
    )
    items = [serialize_sale_item(item) for item in item_records]
    if not items:
        legacy_name = crop.name if source_type == "Crop" and crop else (animal.record_name if animal else "Unknown source")
        legacy_code = crop.crop_code if source_type == "Crop" and crop else (animal.animal_code if animal else sale.sale_code)
        items = [{
            "id": None,
            "line_number": 1,
            "item_kind": "Live Animal" if str(sale.sale_type).lower() == "live animal" else "Production",
            "source_type": source_type,
            "production_record_id": sale.production_record_id,
            "livestock_id": sale.livestock_id,
            "crop_id": sale.crop_id,
            "inventory_item_id": None,
            "source_name": legacy_name,
            "source_code": legacy_code,
            "product_type": sale.product_type,
            "quantity": float(sale.quantity),
            "unit": sale.unit,
            "unit_price": float(sale.unit_price),
            "line_total": float(sale.total_amount),
            "male_quantity": int(sale.male_quantity or 0),
            "female_quantity": int(sale.female_quantity or 0),
            "unknown_quantity": int(sale.unknown_quantity or 0),
            "healthy_quantity": int(sale.healthy_quantity or 0),
        }]
    source_types = list(dict.fromkeys(item["source_type"] for item in items))
    if len(items) > 1:
        source_name = "Multiple farm products"
        source_code = sale.sale_code
    else:
        source_name = items[0]["source_name"]
        source_code = items[0]["source_code"] or ""
    user = db.get(User, sale.recorded_by_user_id) if sale.recorded_by_user_id else None
    return {
        "id": sale.id,
        "sale_code": sale.sale_code,
        "sale_type": sale.sale_type,
        "source_type": source_type,
        "source_name": source_name,
        "source_code": source_code,
        "livestock_id": sale.livestock_id,
        "livestock_name": animal.record_name if animal else None,
        "animal_code": animal.animal_code if animal else None,
        "crop_id": sale.crop_id,
        "production_record_id": sale.production_record_id,
        "sale_date": sale.sale_date,
        "product_type": sale.product_type,
        "quantity": float(sale.quantity),
        "unit": sale.unit,
        "unit_price": float(sale.unit_price),
        "total_amount": float(sale.total_amount),
        "amount_paid": float(sale.amount_paid or 0),
        "balance_due": float(sale.balance_due or 0),
        "buyer_name": sale.buyer_name,
        "payment_status": sale.payment_status,
        "payment_method": sale.payment_method,
        "male_quantity": sale.male_quantity,
        "female_quantity": sale.female_quantity,
        "unknown_quantity": sale.unknown_quantity,
        "healthy_quantity": sale.healthy_quantity,
        "notes": sale.notes,
        "is_voided": sale.is_voided,
        "void_reason": sale.void_reason,
        "voided_at": sale.voided_at,
        "recorded_by_name": (user.full_name or user.username) if user else None,
        "item_count": len(items),
        "source_types": source_types,
        "items": items,
        "created_at": sale.created_at,
    }


def serialize_processing(
    db: Session,
    record: LivestockProcessingRecord,
    livestock: Livestock | None = None,
) -> dict:
    animal = livestock or db.get(Livestock, record.livestock_id)
    live_weight = float(record.live_weight_kg) if record.live_weight_kg is not None else None
    meat_output = float(record.meat_output_kg or 0)
    yield_percent = (
        round(meat_output / live_weight * 100, 2)
        if live_weight and live_weight > 0
        else None
    )
    return {
        "id": record.id,
        "livestock_id": record.livestock_id,
        "livestock_name": animal.record_name if animal else "Unknown livestock",
        "animal_code": animal.animal_code if animal else "",
        "production_record_id": record.production_record_id,
        "processing_date": record.processing_date,
        "animals_processed": record.animals_processed,
        "male_quantity": record.male_quantity,
        "female_quantity": record.female_quantity,
        "unknown_quantity": record.unknown_quantity,
        "healthy_quantity": record.healthy_quantity,
        "live_weight_kg": live_weight,
        "meat_output_kg": meat_output,
        "yield_percent": yield_percent,
        "quality_grade": record.quality_grade,
        "destination": record.destination,
        "notes": record.notes,
        "is_voided": record.is_voided,
        "void_reason": record.void_reason,
        "voided_at": record.voided_at,
        "created_at": record.created_at,
    }


def serialize_payment(record: LivestockSalePayment, db: Session | None = None) -> dict:
    user = db.get(User, record.recorded_by_user_id) if db is not None and record.recorded_by_user_id else None
    return {
        "id": record.id,
        "sale_id": record.sale_id,
        "payment_date": record.payment_date,
        "amount": float(record.amount),
        "payment_method": record.payment_method,
        "notes": record.notes,
        "recorded_by_name": (user.full_name or user.username) if user else None,
        "created_at": record.created_at,
    }


def _next_animal_code(db: Session) -> str:
    acquire_transaction_lock(db, "code:livestock")
    codes = db.scalars(select(Livestock.animal_code)).all()
    highest = 1000
    for code in codes:
        match = re.search(r"(\d+)$", str(code or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"C-{highest + 1}"


def _new_sale_code() -> str:
    return f"SALE-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def _tracked_sex_total(livestock: Livestock) -> int:
    return (
        int(livestock.male_quantity or 0)
        + int(livestock.female_quantity or 0)
        + int(livestock.unknown_sex_quantity or 0)
    )


def _tracked_health_total(livestock: Livestock) -> int:
    return (
        int(livestock.healthy_quantity or 0)
        + int(livestock.at_risk_quantity or 0)
        + int(livestock.sick_quantity or 0)
        + int(livestock.under_treatment_quantity or 0)
    )


def _source_female_quantity(livestock: Livestock) -> int:
    if _tracked_sex_total(livestock) == int(livestock.quantity or 0):
        return int(livestock.female_quantity or 0)
    if str(livestock.sex or "").strip().lower() == "female":
        return int(livestock.quantity or 0)
    return 0


def _species_group(livestock: Livestock) -> str:
    animal_type = str(livestock.animal_type or "").strip().lower()
    if animal_type in {"chicken", "duck", "bird", "poultry"}:
        return "bird"
    if animal_type == "pig":
        return "pig"
    if animal_type in {"goat", "cattle", "cow"}:
        return "ruminant"
    return "other"


def is_meat_production_livestock(livestock: Livestock) -> bool:
    purpose = str(livestock.production_purpose or "").strip().lower()
    return purpose in {"meat", "meat production"}


def _pen_occupancy(db: Session, pen_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
                Livestock.pen_id == pen_id,
                Livestock.is_archived == False,
                Livestock.lifecycle_status == "Active",
            )
        )
        or 0
    )


def _require_breeding_pen(db: Session, livestock: Livestock) -> LivestockPen:
    if livestock.pen_id is None:
        raise HTTPException(status_code=400, detail="Breeding requires the livestock batch to be assigned to a Breeding pen.")
    pen = db.get(LivestockPen, livestock.pen_id)
    if pen is None or "breeding" not in str(pen.purpose or "").strip().lower():
        raise HTTPException(
            status_code=400,
            detail="Breeding can only be recorded while the livestock batch is inside a Breeding pen.",
        )
    return pen


def _offspring_pen(db: Session, pen_id: int, animal_type: str, quantity: int) -> LivestockPen:
    pen = db.get(LivestockPen, pen_id)
    if pen is None or pen.is_archived or pen.status not in {"Active", "Full"}:
        raise HTTPException(status_code=400, detail="Selected offspring destination pen is unavailable.")
    allowed = str(pen.animal_type or "").strip().lower()
    requested = str(animal_type or "").strip().lower()
    if allowed and allowed not in {"all", "all livestock", "any"} and allowed != requested:
        raise HTTPException(status_code=400, detail=f"{pen.name} is not configured for {animal_type}.")

    purpose = str(pen.purpose or "").strip().lower()
    if requested in {"chicken", "duck", "bird", "poultry"}:
        allowed_purpose = any(token in purpose for token in ("brooder", "nursery"))
        expected = "Brooder / Nursery"
    elif requested == "pig":
        allowed_purpose = any(token in purpose for token in ("nursing", "farrowing", "nursery"))
        expected = "Nursing / Farrowing"
    elif requested in {"goat", "cattle", "cow"}:
        allowed_purpose = any(token in purpose for token in ("nursing", "nursery", "maternity"))
        expected = "Nursing / Nursery / Maternity"
    else:
        allowed_purpose = True
        expected = "an offspring-appropriate"

    if not allowed_purpose:
        raise HTTPException(
            status_code=400,
            detail=f"New {animal_type} offspring must first be assigned to a {expected} pen.",
        )

    occupied = _pen_occupancy(db, pen.id)
    if pen.capacity is not None and occupied + int(quantity) > int(pen.capacity):
        raise HTTPException(
            status_code=400,
            detail=f"{pen.name} only has {max(0, int(pen.capacity) - occupied)} available space(s).",
        )
    return pen


def _automatic_expected_date(livestock: Livestock, record_type: str, event_date):
    from datetime import timedelta

    group = _species_group(livestock)
    normalized = str(record_type or "").strip().lower()
    if normalized in {"breeding", "mating"}:
        days = {"pig": 114, "ruminant": 150}.get(group)
        if str(livestock.animal_type or "").strip().lower() in {"cattle", "cow"}:
            days = 283
        return event_date + timedelta(days=days) if days else None
    if normalized in {"egg setting", "incubation"} and group == "bird":
        days = 28 if str(livestock.animal_type or "").strip().lower() == "duck" else 21
        return event_date + timedelta(days=days)
    return None


def _normalize_payment(total: Decimal, requested_status: str, amount_paid) -> tuple[Decimal, Decimal, str]:
    requested = str(requested_status or "Paid").strip().lower()
    if amount_paid is None:
        if requested == "paid":
            paid = total
        elif requested == "unpaid":
            paid = Decimal("0")
        else:
            raise HTTPException(
                status_code=400,
                detail="Amount Paid is required when Payment Status is Partial.",
            )
    else:
        paid = _decimal(amount_paid).quantize(MONEY, rounding=ROUND_HALF_UP)

    if paid < 0 or paid > total:
        raise HTTPException(
            status_code=400,
            detail=f"Amount Paid must be between ₱0.00 and ₱{float(total):,.2f}.",
        )

    balance = (total - paid).quantize(MONEY, rounding=ROUND_HALF_UP)
    if paid <= 0:
        status_text = "Unpaid"
    elif balance <= 0:
        status_text = "Paid"
    else:
        status_text = "Partial"
    return paid, balance, status_text


def create_reproduction(db: Session, payload, current_user) -> dict:
    livestock = get_livestock(db, payload.livestock_id)
    if livestock.date_of_birth is not None and payload.event_date < livestock.date_of_birth:
        raise HTTPException(status_code=400, detail="Reproduction event date cannot be earlier than the livestock date of birth.")
    if payload.event_date > farm_today():
        raise HTTPException(status_code=400, detail="Reproduction event date cannot be in the future.")

    normalized_type = payload.record_type.strip().lower()
    group = _species_group(livestock)
    males_available = int(livestock.male_quantity or 0)
    females_available = _source_female_quantity(livestock)
    breeder_males = int(payload.breeder_male_quantity or 0)
    breeder_females = int(payload.breeder_female_quantity or 0)

    if normalized_type in {"breeding", "mating"}:
        _require_breeding_pen(db, livestock)
        if males_available <= 0 or females_available <= 0:
            raise HTTPException(status_code=400, detail="Breeding requires at least one eligible male and one eligible female in the batch.")
        if breeder_males < 1 or breeder_females < 1:
            raise HTTPException(status_code=400, detail="Enter the number of breeder males and females used.")
        if breeder_males > males_available or breeder_females > females_available:
            raise HTTPException(status_code=400, detail="Breeder counts exceed the male/female animals available in this batch.")

    if normalized_type == "pregnancy check":
        if group == "bird":
            raise HTTPException(status_code=400, detail="Bird reproduction uses egg setting and hatching, not pregnancy checks.")
        if int(payload.confirmed_pregnant_quantity or 0) > females_available:
            raise HTTPException(status_code=400, detail="Confirmed pregnant animals cannot exceed the females available in the batch.")

    if normalized_type == "birth" and group == "bird":
        raise HTTPException(status_code=400, detail="Bird offspring must be recorded with a Hatch event.")

    if normalized_type in {"egg setting", "incubation"}:
        if group != "bird":
            raise HTTPException(status_code=400, detail="Egg setting is only available for chicken, duck, or other poultry records.")
        _require_breeding_pen(db, livestock)
        if males_available <= 0 or females_available <= 0:
            raise HTTPException(status_code=400, detail="A breeder flock needs at least one male and one female before eggs can be set for hatching.")
        if int(payload.eggs_set or 0) <= 0:
            raise HTTPException(status_code=400, detail="Enter the number of eggs set for incubation.")

    if normalized_type == "hatch":
        if group != "bird":
            raise HTTPException(status_code=400, detail="Hatch records are only available for poultry.")
        if int(payload.fertile_eggs or 0) and int(payload.alive_offspring or 0) > int(payload.fertile_eggs or 0):
            raise HTTPException(status_code=400, detail="Hatched alive cannot exceed fertile eggs.")

    source_production = None
    if normalized_type in {"egg setting", "incubation"}:
        if payload.source_production_record_id is None:
            raise HTTPException(status_code=400, detail="Choose the egg production stock being reserved for incubation.")
        production_statement = select(LivestockProductionRecord).where(
            LivestockProductionRecord.id == payload.source_production_record_id
        )
        if db.bind is not None and db.bind.dialect.name == "mssql":
            production_statement = production_statement.with_hint(
                LivestockProductionRecord, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql"
            )
        else:
            production_statement = production_statement.with_for_update()
        source_production = db.scalar(production_statement)
        if (
            source_production is None
            or source_production.livestock_id != livestock.id
            or "egg" not in str(source_production.output_type or "").lower()
            or not source_production.track_sale_inventory
        ):
            raise HTTPException(status_code=400, detail="Select available egg production from this breeder flock.")
        eggs = Decimal(int(payload.eggs_set or 0))
        available = production_available_quantity(db, source_production)
        if eggs > available:
            raise HTTPException(status_code=400, detail=f"Only {float(available):g} eggs remain available to reserve for incubation.")
        source_production.quantity = (_decimal(source_production.quantity) - eggs).quantize(QTY)
        source_production.reserved_quantity = (_decimal(source_production.reserved_quantity) + eggs).quantize(QTY)
        source_production.destination = _production_destination(
            production_available_quantity(db, source_production), _decimal(source_production.quantity)
        )

    expected_date = payload.expected_date or _automatic_expected_date(livestock, payload.record_type, payload.event_date)

    if normalized_type in {"birth", "hatch"}:
        pending = db.scalar(
            select(LivestockReproductionRecord)
            .where(
                LivestockReproductionRecord.livestock_id == livestock.id,
                LivestockReproductionRecord.expected_date.is_not(None),
                LivestockReproductionRecord.actual_date.is_(None),
            )
            .order_by(LivestockReproductionRecord.expected_date.desc(), LivestockReproductionRecord.id.desc())
            .limit(1)
        )
        if pending is not None:
            pending.actual_date = payload.actual_date or payload.event_date
            pending.reproductive_status = _clean(payload.reproductive_status) or ("Hatched" if normalized_type == "hatch" else "Completed")

    record = LivestockReproductionRecord(
        livestock_id=livestock.id,
        record_type=payload.record_type.strip(),
        event_date=payload.event_date,
        partner_reference=_clean(payload.partner_reference),
        breeding_method=_clean(payload.breeding_method),
        breeder_male_quantity=breeder_males,
        breeder_female_quantity=breeder_females,
        confirmed_pregnant_quantity=int(payload.confirmed_pregnant_quantity or 0),
        eggs_set=int(payload.eggs_set or 0),
        fertile_eggs=int(payload.fertile_eggs or 0),
        incubation_method=_clean(payload.incubation_method),
        reproductive_status=_clean(payload.reproductive_status),
        expected_date=expected_date,
        actual_date=payload.actual_date,
        offspring_count=payload.offspring_count,
        alive_offspring=payload.alive_offspring,
        male_offspring=payload.male_offspring,
        female_offspring=payload.female_offspring,
        loss_count=payload.loss_count,
        source_production_record_id=payload.source_production_record_id,
        notes=_clean(payload.notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(record)
    db.flush()

    if payload.create_offspring_record:
        if normalized_type not in {"birth", "hatch"}:
            raise HTTPException(status_code=400, detail="An offspring batch can only be created from a Birth or Hatch record.")
        alive = int(payload.alive_offspring)
        male = int(payload.male_offspring or 0)
        female = int(payload.female_offspring or 0)
        unknown = max(0, alive - male - female)
        birth_date = payload.actual_date or payload.event_date
        destination = _offspring_pen(db, int(payload.offspring_pen_id), livestock.animal_type, alive)
        offspring_growth = "Brooding" if group == "bird" else "Newborn"
        offspring = Livestock(
            animal_code=_next_animal_code(db),
            record_name=_clean(payload.offspring_record_name) or f"{livestock.record_name} Offspring {birth_date.isoformat()}",
            animal_type=livestock.animal_type,
            breed=livestock.breed,
            quantity=alive,
            sex="Mixed" if alive > 1 else ("Male" if male == 1 else "Female" if female == 1 else "Unknown"),
            record_type="Batch" if alive > 1 else "Individual",
            lifecycle_status="Active",
            pen_id=destination.id,
            origin_livestock_id=livestock.id,
            male_quantity=male,
            female_quantity=female,
            unknown_sex_quantity=unknown,
            date_of_birth=birth_date,
            weight_kg=payload.offspring_average_weight_kg,
            min_weight_kg=payload.offspring_average_weight_kg,
            max_weight_kg=payload.offspring_average_weight_kg,
            pen_location=destination.name,
            health_status="Healthy",
            healthy_quantity=alive,
            at_risk_quantity=0,
            sick_quantity=0,
            under_treatment_quantity=0,
            growth_status=offspring_growth,
            production_purpose="Growing",
            vaccination_status="Not Vaccinated",
            feed_times=None,
            feed_type=None,
            daily_feed_kg=0,
            feeding_notes=None,
            feed_inventory_item_id=None,
            production_output="Growth",
            date_acquired=birth_date,
            acquired_from="Born on farm",
            is_archived=False,
            created_by_user_id=current_user.id,
        )
        db.add(offspring)
        db.flush()
        db.add(
            LivestockGrowthRecord(
                livestock_id=offspring.id,
                measurement_date=birth_date,
                weight_kg=payload.offspring_average_weight_kg,
                animals_measured=alive,
                total_measured_weight_kg=float(payload.offspring_average_weight_kg) * alive,
                min_weight_kg=payload.offspring_average_weight_kg,
                max_weight_kg=payload.offspring_average_weight_kg,
                measurement_basis="Full Batch" if alive > 1 else "Individual",
                notes="Initial offspring weight recorded from reproduction event.",
                recorded_by_user_id=current_user.id,
            )
        )
        record.offspring_livestock_id = offspring.id
        db.add(
            LivestockTransaction(
                livestock_id=offspring.id,
                transaction_type="Birth/Hatch",
                quantity=alive,
                from_livestock_id=livestock.id,
                to_livestock_id=offspring.id,
                from_pen_id=livestock.pen_id,
                to_pen_id=destination.id,
                event_date=birth_date,
                reason=f"Created from reproduction record #{record.id} and assigned to {destination.name}.",
                recorded_by_user_id=current_user.id,
            )
        )

    _audit(
        db,
        action=f"Recorded livestock {record.record_type.lower()}",
        record_name=livestock.record_name,
        entity_id=livestock.animal_code,
        details=f"{record.record_type} recorded on {record.event_date.isoformat()}.",
        icon="family_restroom",
        actor_user_id=current_user.id,
        actor_name=current_user.full_name or current_user.username,
    )
    db.flush()
    db.refresh(record)
    return serialize_reproduction(db, record, livestock)


def create_production(db: Session, payload, current_user) -> dict:
    livestock = get_livestock(db, payload.livestock_id)
    if livestock.date_of_birth is not None and payload.record_date < livestock.date_of_birth:
        raise HTTPException(status_code=400, detail="Production date cannot be earlier than the livestock date of birth.")
    if payload.record_date > farm_today():
        raise HTTPException(status_code=400, detail="Production date cannot be in the future.")

    output_type = payload.output_type.strip()
    output_lower = output_type.lower()
    if "meat" in output_lower:
        raise HTTPException(status_code=400, detail="Meat output must be recorded through Record Processing so livestock population and sale stock stay synchronized.")

    start = payload.period_start_date or payload.record_date
    end = payload.period_end_date or payload.record_date
    if livestock.date_of_birth is not None and start < livestock.date_of_birth:
        raise HTTPException(status_code=400, detail="Production period cannot begin before the livestock date of birth.")
    days = max(1, (end - start).days + 1)
    saleable_quantity = _decimal(payload.quantity).quantize(QTY)
    gross_quantity = _decimal(payload.gross_quantity if payload.gross_quantity is not None else payload.quantity).quantize(QTY)
    loss_quantity = _decimal(payload.loss_quantity or 0).quantize(QTY)
    farm_use_quantity = _decimal(payload.farm_use_quantity or 0).quantize(QTY)
    reserved_quantity = _decimal(payload.reserved_quantity or 0).quantize(QTY)
    if gross_quantity - loss_quantity - farm_use_quantity - reserved_quantity != saleable_quantity:
        raise HTTPException(status_code=400, detail="Saleable quantity must equal gross production minus damaged/rejected, farm-use, and reserved quantities.")

    group = _species_group(livestock)
    female_count = _source_female_quantity(livestock)
    active_count = int(payload.source_active_quantity or female_count or livestock.quantity or 0)
    if active_count <= 0 or active_count > int(livestock.quantity or 0):
        raise HTTPException(status_code=400, detail="Active producing animals must be within the current livestock quantity.")

    if "egg" in output_lower:
        if group != "bird":
            raise HTTPException(status_code=400, detail="Egg production can only be recorded for poultry livestock.")
        purpose_text = f"{livestock.production_purpose or ''} {livestock.growth_status or ''}".lower()
        if not any(token in purpose_text for token in ("egg", "laying", "layer", "breeding", "breeder")):
            raise HTTPException(
                status_code=400,
                detail="Egg production is only available for poultry currently marked for egg/layer or breeding production.",
            )
        if str(payload.unit or "").strip().lower() not in {"pcs", "pc", "piece", "pieces", "eggs"}:
            raise HTTPException(status_code=400, detail="Egg production must use pcs as the unit.")
        if female_count <= 0:
            raise HTTPException(status_code=400, detail="This livestock record has no female birds available for egg production.")
        if active_count > female_count:
            raise HTTPException(status_code=400, detail=f"Active laying females cannot exceed the {female_count} female bird(s) in the batch.")
        maximum = Decimal(active_count * days)
        if gross_quantity > maximum:
            raise HTTPException(status_code=400, detail=f"Egg quantity is not possible for this period. {active_count} laying female(s) × {days} day(s) allows at most {int(maximum)} eggs.")

    if "milk" in output_lower:
        if group != "ruminant":
            raise HTTPException(status_code=400, detail="Milk production is only available for goat/cattle livestock.")
        purpose_text = f"{livestock.production_purpose or ''} {livestock.growth_status or ''}".lower()
        if not any(token in purpose_text for token in ("milk", "dairy", "lactat")):
            raise HTTPException(status_code=400, detail="Milk production is only available for livestock currently marked for milk/dairy production or lactation.")
        if str(payload.unit or "").strip().lower() not in {"l", "liter", "liters", "litre", "litres"}:
            raise HTTPException(status_code=400, detail="Milk production must use L as the unit.")
        if female_count <= 0 or active_count > female_count:
            raise HTTPException(status_code=400, detail=f"Animals milked cannot exceed the {female_count} eligible female animal(s) in the batch.")

    record = LivestockProductionRecord(
        source_type="Livestock",
        livestock_id=livestock.id,
        crop_id=None,
        crop_yield_record_id=None,
        output_type=output_type,
        record_date=payload.record_date,
        period_start_date=start,
        period_end_date=end,
        source_head_quantity=int(livestock.quantity or 0),
        source_female_quantity=female_count if ("egg" in output_lower or "milk" in output_lower) else None,
        source_active_quantity=active_count,
        gross_quantity=gross_quantity,
        loss_quantity=loss_quantity,
        farm_use_quantity=farm_use_quantity,
        reserved_quantity=reserved_quantity,
        quantity=saleable_quantity,
        unit=payload.unit.strip(),
        quality_grade=_clean(payload.quality_grade),
        destination=_clean(payload.destination) or ("Available for sale" if payload.track_sale_inventory else "Farm use / monitoring"),
        track_sale_inventory=bool(payload.track_sale_inventory and saleable_quantity > 0),
        notes=_clean(payload.notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(record)
    db.flush()

    detail = f"{float(gross_quantity):g} {record.unit} gross {record.output_type}; {float(saleable_quantity):g} {record.unit} available for sale."
    _audit(db, action="Recorded livestock production", record_name=livestock.record_name, entity_id=livestock.animal_code, details=detail, icon="egg_alt" if "egg" in output_lower else "water_drop", actor_user_id=current_user.id, actor_name=current_user.full_name or current_user.username)
    db.flush()
    db.refresh(record)
    return serialize_production(db, record, livestock)


def create_crop_production_from_yield(db: Session, yield_record: CropYieldRecord, crop: Crop, current_user) -> dict:
    existing = db.scalar(select(LivestockProductionRecord).where(LivestockProductionRecord.crop_yield_record_id == yield_record.id))
    gross = _decimal(yield_record.quantity_kg).quantize(QTY)
    loss = _decimal(yield_record.damaged_quantity_kg or 0).quantize(QTY)
    farm_use = _decimal(yield_record.farm_use_quantity_kg or 0).quantize(QTY)
    reserved = _decimal(yield_record.reserved_quantity_kg or 0).quantize(QTY)
    saleable = (gross - loss - farm_use - reserved).quantize(QTY)
    if saleable < 0:
        raise HTTPException(status_code=400, detail="Crop harvest allocations cannot exceed the harvested quantity.")
    if existing is not None:
        sold = _production_sold_quantity(db, existing.id)
        if saleable < sold:
            raise HTTPException(
                status_code=400,
                detail="Crop harvest allocations cannot reduce available production below the quantity already sold.",
            )
        existing.source_type = "Crop"
        existing.livestock_id = None
        existing.crop_id = crop.id
        existing.output_type = crop.name
        existing.record_date = yield_record.harvest_date
        existing.period_start_date = yield_record.harvest_date
        existing.period_end_date = yield_record.harvest_date
        existing.gross_quantity = gross
        existing.loss_quantity = loss
        existing.farm_use_quantity = farm_use
        existing.reserved_quantity = reserved
        existing.quantity = saleable
        existing.unit = "kg"
        existing.quality_grade = _clean(yield_record.quality)
        existing.destination = _production_destination(saleable - sold, saleable)
        existing.track_sale_inventory = saleable > 0
        existing.notes = _clean(yield_record.notes)
        db.flush()
        db.refresh(existing)
        return serialize_production(db, existing, sold_quantity=sold)
    record = LivestockProductionRecord(
        source_type="Crop",
        livestock_id=None,
        crop_id=crop.id,
        crop_yield_record_id=yield_record.id,
        output_type=crop.name,
        record_date=yield_record.harvest_date,
        period_start_date=yield_record.harvest_date,
        period_end_date=yield_record.harvest_date,
        source_head_quantity=None,
        source_female_quantity=None,
        source_active_quantity=None,
        gross_quantity=gross,
        loss_quantity=loss,
        farm_use_quantity=farm_use,
        reserved_quantity=reserved,
        quantity=saleable,
        unit="kg",
        quality_grade=_clean(yield_record.quality),
        destination="Available for sale" if saleable > 0 else "Fully allocated / unavailable",
        track_sale_inventory=saleable > 0,
        notes=_clean(yield_record.notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(record)
    db.flush()
    _audit(db, action="Recorded crop harvest output", record_name=f"{crop.name} — {crop.field}", entity_id=crop.crop_code, details=f"{float(gross):g} kg harvested; {float(saleable):g} kg available for sale.", icon="agriculture", actor_user_id=current_user.id, actor_name=current_user.full_name or current_user.username)
    db.refresh(record)
    return serialize_production(db, record)


def create_processing(db: Session, payload, current_user) -> dict:
    livestock = get_livestock(db, payload.livestock_id, for_update=True)
    if not is_meat_production_livestock(livestock):
        raise HTTPException(
            status_code=400,
            detail=(
                "Only livestock with Production Purpose set to Meat or Meat Production "
                "can be processed into meat. Update the livestock purpose first; breeding, "
                "egg, milk, dual-purpose, and general records are protected."
            ),
        )
    if payload.processing_date < livestock.date_acquired:
        raise HTTPException(
            status_code=400,
            detail="Processing date cannot be earlier than the livestock acquisition date.",
        )

    whole_quantity = int(payload.animals_processed)
    if whole_quantity > int(livestock.quantity or 0):
        raise HTTPException(
            status_code=400,
            detail=f"Only {livestock.quantity} animal(s) are available in this livestock record.",
        )

    male = int(payload.male_quantity or 0)
    female = int(payload.female_quantity or 0)
    unknown = int(payload.unknown_quantity or 0)
    tracked_sex_total = _tracked_sex_total(livestock)
    if tracked_sex_total == int(livestock.quantity or 0):
        if male + female + unknown != whole_quantity:
            raise HTTPException(
                status_code=400,
                detail="Enter the sex breakdown for all animals being processed.",
            )
        if (
            male > int(livestock.male_quantity or 0)
            or female > int(livestock.female_quantity or 0)
            or unknown > int(livestock.unknown_sex_quantity or 0)
        ):
            raise HTTPException(
                status_code=400,
                detail="The processing sex breakdown exceeds the livestock quantities on hand.",
            )
    else:
        male = female = unknown = 0

    tracked_health_total = _tracked_health_total(livestock)
    healthy_processed = 0
    if tracked_health_total == int(livestock.quantity or 0):
        if int(livestock.healthy_quantity or 0) < whole_quantity:
            raise HTTPException(
                status_code=400,
                detail="Processing is limited to healthy animals. Update the livestock health allocation first.",
            )
        healthy_processed = whole_quantity

    live_weight = (
        _decimal(payload.live_weight_kg).quantize(QTY)
        if payload.live_weight_kg is not None
        else None
    )
    meat_output = _decimal(payload.meat_output_kg).quantize(QTY)
    if live_weight is not None and meat_output > live_weight:
        raise HTTPException(status_code=400, detail="Meat output cannot exceed total live weight.")

    livestock.quantity -= whole_quantity
    if tracked_sex_total > 0:
        livestock.male_quantity -= male
        livestock.female_quantity -= female
        livestock.unknown_sex_quantity -= unknown
    if tracked_health_total > 0:
        livestock.healthy_quantity -= healthy_processed
    if livestock.quantity == 0:
        livestock.lifecycle_status = "Processed"
        livestock.is_archived = True

    production = LivestockProductionRecord(
        source_type="Livestock",
        livestock_id=livestock.id,
        crop_id=None,
        crop_yield_record_id=None,
        output_type="Meat",
        record_date=payload.processing_date,
        period_start_date=payload.processing_date,
        period_end_date=payload.processing_date,
        source_head_quantity=whole_quantity,
        source_female_quantity=None,
        gross_quantity=meat_output,
        loss_quantity=0,
        farm_use_quantity=0,
        reserved_quantity=0,
        quantity=meat_output,
        unit="kg",
        quality_grade=_clean(payload.quality_grade),
        destination=_clean(payload.destination) or "Available for sale",
        track_sale_inventory=True,
        notes=_clean(payload.notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(production)
    db.flush()

    processing = LivestockProcessingRecord(
        livestock_id=livestock.id,
        production_record_id=production.id,
        processing_date=payload.processing_date,
        animals_processed=whole_quantity,
        male_quantity=male,
        female_quantity=female,
        unknown_quantity=unknown,
        healthy_quantity=healthy_processed,
        live_weight_kg=live_weight,
        meat_output_kg=meat_output,
        quality_grade=_clean(payload.quality_grade),
        destination=_clean(payload.destination) or "Available for sale",
        notes=_clean(payload.notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(processing)
    db.flush()

    yield_text = ""
    if live_weight and live_weight > 0:
        yield_text = f" Dressing yield: {float(meat_output / live_weight * 100):.1f}%."

    db.add(
        LivestockTransaction(
            livestock_id=livestock.id,
            transaction_type="Processing",
            quantity=whole_quantity,
            from_livestock_id=livestock.id,
            to_livestock_id=None,
            from_pen_id=livestock.pen_id,
            to_pen_id=None,
            event_date=payload.processing_date,
            reason=(
                f"Processed {whole_quantity} head into {float(meat_output):g} kg meat."
                + yield_text
            ),
            recorded_by_user_id=current_user.id,
        )
    )
    _audit(
        db,
        action="Recorded livestock processing",
        record_name=livestock.record_name,
        entity_id=livestock.animal_code,
        details=(
            f"{whole_quantity} head processed into {float(meat_output):g} kg of meat."
            + yield_text
        ),
        icon="set_meal",
        actor_user_id=current_user.id,
        actor_name=current_user.full_name or current_user.username,
    )
    db.flush()
    db.refresh(processing)
    return serialize_processing(db, processing, livestock)


def void_processing(db: Session, processing_id: int, reason: str, current_user) -> dict:
    statement = select(LivestockProcessingRecord).where(
        LivestockProcessingRecord.id == processing_id
    )
    if db.bind is not None and db.bind.dialect.name == "mssql":
        statement = statement.with_hint(
            LivestockProcessingRecord, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql"
        )
    else:
        statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        raise HTTPException(status_code=404, detail="Processing record not found.")
    if record.is_voided:
        raise HTTPException(status_code=400, detail="This processing record is already voided.")

    sold = _production_sold_quantity(db, record.production_record_id)
    if sold > 0:
        raise HTTPException(
            status_code=400,
            detail="Void the sales linked to this meat production first, then void the processing record.",
        )

    livestock_statement = select(Livestock).where(Livestock.id == record.livestock_id)
    if db.bind is not None and db.bind.dialect.name == "mssql":
        livestock_statement = livestock_statement.with_hint(
            Livestock, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql"
        )
    else:
        livestock_statement = livestock_statement.with_for_update()
    livestock = db.scalar(livestock_statement)
    if livestock is None:
        raise HTTPException(status_code=404, detail="Related livestock record not found.")

    restored = int(record.animals_processed or 0)
    livestock.quantity += restored
    livestock.male_quantity += int(record.male_quantity or 0)
    livestock.female_quantity += int(record.female_quantity or 0)
    livestock.unknown_sex_quantity += int(record.unknown_quantity or 0)
    livestock.healthy_quantity += int(record.healthy_quantity or 0)
    if livestock.lifecycle_status == "Processed":
        livestock.lifecycle_status = "Active"
    livestock.is_archived = False

    production = db.get(LivestockProductionRecord, record.production_record_id)
    if production is not None:
        production.track_sale_inventory = False
        production.destination = "Voided processing"

    record.is_voided = True
    record.void_reason = reason.strip()
    record.voided_at = datetime.now()

    db.add(
        LivestockTransaction(
            livestock_id=livestock.id,
            transaction_type="Processing Void",
            quantity=restored,
            from_livestock_id=None,
            to_livestock_id=livestock.id,
            from_pen_id=None,
            to_pen_id=livestock.pen_id,
            event_date=farm_today(),
            reason=f"Voided processing record #{record.id}: {reason.strip()}",
            recorded_by_user_id=current_user.id,
        )
    )
    _audit(
        db,
        action="Voided livestock processing",
        record_name=livestock.record_name,
        entity_id=livestock.animal_code,
        details=reason.strip(),
        icon="undo",
        actor_user_id=current_user.id,
        actor_name=current_user.full_name or current_user.username,
    )
    db.flush()
    db.refresh(record)
    return serialize_processing(db, record, livestock)


def _lock_record(db: Session, model, record_id: int):
    statement = select(model).where(model.id == record_id)
    if db.bind is not None and db.bind.dialect.name == "mssql":
        statement = statement.with_hint(model, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    else:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _sale_request_items(payload) -> list[dict]:
    if getattr(payload, "items", None):
        return [
            {
                "line_number": index,
                "item_kind": item.item_kind.strip().title(),
                "production_record_id": item.production_record_id,
                "livestock_id": item.livestock_id,
                "inventory_item_id": item.inventory_item_id,
                "quantity": _decimal(item.quantity).quantize(QTY),
                "unit": _clean(item.unit),
                "unit_price": _decimal(item.unit_price).quantize(MONEY),
                "male_quantity": int(item.male_quantity or 0),
                "female_quantity": int(item.female_quantity or 0),
                "unknown_quantity": int(item.unknown_quantity or 0),
            }
            for index, item in enumerate(payload.items, start=1)
        ]
    kind = "Live Animal" if payload.sale_type.strip().lower() == "live animal" else "Production"
    return [{
        "line_number": 1,
        "item_kind": kind,
        "production_record_id": payload.production_record_id,
        "livestock_id": payload.livestock_id,
        "inventory_item_id": None,
        "quantity": _decimal(payload.quantity).quantize(QTY),
        "unit": _clean(payload.unit),
        "unit_price": _decimal(payload.unit_price).quantize(MONEY),
        "male_quantity": int(payload.male_quantity or 0),
        "female_quantity": int(payload.female_quantity or 0),
        "unknown_quantity": int(payload.unknown_quantity or 0),
    }]


def create_sale(db: Session, payload, current_user) -> dict:
    requested = _sale_request_items(payload)
    prepared: list[dict] = []

    # Lock source rows in a stable order, validate every line, and only then
    # mutate stock. A validation error therefore cannot leave half an invoice.
    source_key = {
        "Production": "production_record_id",
        "Live Animal": "livestock_id",
        "Inventory": "inventory_item_id",
    }
    for item in sorted(
        requested,
        key=lambda value: (
            value["item_kind"],
            int(value.get(source_key[value["item_kind"]]) or 0),
        ),
    ):
        quantity = item["quantity"]
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="Every sale quantity must be greater than zero.")
        if item["unit_price"] < 0:
            raise HTTPException(status_code=400, detail="Unit price cannot be negative.")

        if item["item_kind"] == "Production":
            production = _lock_record(db, LivestockProductionRecord, int(item["production_record_id"]))
            if production is None:
                raise HTTPException(status_code=400, detail="A selected production/harvest lot no longer exists.")
            if not production.track_sale_inventory:
                raise HTTPException(status_code=400, detail="A selected production lot is not available as sale stock.")
            if payload.sale_date < production.record_date:
                raise HTTPException(status_code=400, detail="Sale date cannot be earlier than a production/harvest date.")
            unit = str(production.unit or "").strip()
            if item["unit"] and item["unit"].lower() != unit.lower():
                raise HTTPException(status_code=400, detail=f"Sale unit must match the production unit ({unit}).")
            available = production_available_quantity(db, production)
            if quantity > available:
                raise HTTPException(status_code=400, detail=f"Only {float(available):g} {unit} remain for {production.output_type}.")
            crop = db.get(Crop, production.crop_id) if production.crop_id else None
            animal = db.get(Livestock, production.livestock_id) if production.livestock_id else None
            source_type = str(production.source_type or ("Crop" if crop else "Livestock")).title()
            source_name = crop.name if crop else (animal.record_name if animal else production.output_type)
            source_code = crop.crop_code if crop else (animal.animal_code if animal else None)
            prepared.append({
                **item,
                "record": production,
                "source_type": source_type,
                "source_name": source_name,
                "source_code": source_code,
                "product_type": production.output_type,
                "unit": unit,
                "livestock_id": production.livestock_id,
                "crop_id": production.crop_id,
                "healthy_quantity": 0,
            })
            continue

        if item["item_kind"] == "Inventory":
            inventory = _lock_record(db, InventoryItem, int(item["inventory_item_id"]))
            if inventory is None or inventory.is_archived:
                raise HTTPException(status_code=400, detail="A selected inventory product is unavailable.")
            if not inventory.is_saleable:
                raise HTTPException(status_code=400, detail=f"{inventory.name} is not marked as saleable.")
            if payload.sale_date < inventory.date_acquired:
                raise HTTPException(status_code=400, detail="Sale date cannot be earlier than inventory acquisition.")
            if inventory.expiration_date and payload.sale_date > inventory.expiration_date:
                raise HTTPException(status_code=400, detail=f"{inventory.name} expired on {inventory.expiration_date} and cannot be sold.")
            unit = str(inventory.unit or "").strip()
            if item["unit"] and item["unit"].lower() != unit.lower():
                raise HTTPException(status_code=400, detail=f"Sale unit must match the inventory unit ({unit}).")
            if quantity > _decimal(inventory.quantity):
                raise HTTPException(status_code=400, detail=f"Only {float(inventory.quantity):g} {unit} remain for {inventory.name}.")
            prepared.append({
                **item,
                "record": inventory,
                "source_type": "Inventory",
                "source_name": inventory.name,
                "source_code": inventory.item_code,
                "product_type": inventory.name,
                "unit": unit,
                "livestock_id": None,
                "crop_id": None,
                "healthy_quantity": 0,
            })
            continue

        livestock = _lock_record(db, Livestock, int(item["livestock_id"]))
        if livestock is None or livestock.is_archived or livestock.lifecycle_status != "Active":
            raise HTTPException(status_code=400, detail="A selected livestock batch is no longer active.")
        if payload.sale_date < livestock.date_acquired:
            raise HTTPException(status_code=400, detail="Sale date cannot be earlier than livestock acquisition.")
        whole_quantity = int(quantity)
        if quantity != Decimal(whole_quantity) or whole_quantity <= 0:
            raise HTTPException(status_code=400, detail="Live-animal quantities must be whole numbers.")
        if whole_quantity > int(livestock.quantity or 0):
            raise HTTPException(status_code=400, detail=f"Only {livestock.quantity} animal(s) remain in {livestock.record_name}.")
        male = item["male_quantity"]
        female = item["female_quantity"]
        unknown = item["unknown_quantity"]
        tracked_sex_total = _tracked_sex_total(livestock)
        if tracked_sex_total == int(livestock.quantity or 0):
            if male + female + unknown != whole_quantity:
                raise HTTPException(status_code=400, detail=f"Enter the complete sex breakdown for {livestock.record_name}.")
            if male > livestock.male_quantity or female > livestock.female_quantity or unknown > livestock.unknown_sex_quantity:
                raise HTTPException(status_code=400, detail=f"The sex breakdown exceeds stock for {livestock.record_name}.")
        else:
            male = female = unknown = 0
        tracked_health_total = _tracked_health_total(livestock)
        if tracked_health_total == int(livestock.quantity or 0) and int(livestock.healthy_quantity or 0) < whole_quantity:
            raise HTTPException(status_code=400, detail=f"Only healthy animals from {livestock.record_name} can be sold.")
        healthy = whole_quantity if tracked_health_total == int(livestock.quantity or 0) else 0
        prepared.append({
            **item,
            "record": livestock,
            "source_type": "Livestock",
            "source_name": livestock.record_name,
            "source_code": livestock.animal_code,
            "product_type": f"{livestock.animal_type} — Live Animal",
            "unit": "head",
            "livestock_id": livestock.id,
            "crop_id": None,
            "male_quantity": male,
            "female_quantity": female,
            "unknown_quantity": unknown,
            "healthy_quantity": healthy,
            "tracked_sex": tracked_sex_total > 0,
            "tracked_health": tracked_health_total > 0,
        })

    prepared.sort(key=lambda value: value["line_number"])
    total = sum(
        (item["quantity"] * item["unit_price"]).quantize(MONEY, rounding=ROUND_HALF_UP)
        for item in prepared
    ).quantize(MONEY, rounding=ROUND_HALF_UP)
    amount_paid, balance_due, payment_status = _normalize_payment(
        total, payload.payment_status, payload.amount_paid
    )

    first = prepared[0]
    single = len(prepared) == 1
    header_source = first["source_type"] if single else (
        first["source_type"]
        if len({item["source_type"] for item in prepared}) == 1
        else "Mixed"
    )
    header_type = (
        "Live Animal" if first["item_kind"] == "Live Animal"
        else "Inventory Product" if first["item_kind"] == "Inventory"
        else "Product"
    ) if single else "Multi-item"
    sale = LivestockSale(
        sale_code=_new_sale_code(),
        sale_type=header_type,
        source_type=header_source,
        livestock_id=first["livestock_id"] if single else None,
        crop_id=first["crop_id"] if single else None,
        production_record_id=first.get("production_record_id") if single else None,
        sale_date=payload.sale_date,
        product_type=first["product_type"] if single else f"{len(prepared)} farm products",
        quantity=first["quantity"] if single else Decimal(len(prepared)),
        unit=first["unit"] if single else "line items",
        unit_price=first["unit_price"] if single else Decimal("0"),
        total_amount=total,
        amount_paid=amount_paid,
        balance_due=balance_due,
        buyer_name=_clean(payload.buyer_name),
        payment_status=payment_status,
        payment_method=_clean(payload.payment_method),
        male_quantity=first["male_quantity"] if single else 0,
        female_quantity=first["female_quantity"] if single else 0,
        unknown_quantity=first["unknown_quantity"] if single else 0,
        healthy_quantity=first["healthy_quantity"] if single else 0,
        notes=_clean(payload.notes),
        recorded_by_user_id=current_user.id,
    )
    db.add(sale)
    db.flush()

    production_records: dict[int, LivestockProductionRecord] = {}
    for item in prepared:
        record = item["record"]
        stock_record = None
        if item["item_kind"] == "Live Animal":
            whole_quantity = int(item["quantity"])
            record.quantity -= whole_quantity
            if item.get("tracked_sex"):
                record.male_quantity -= item["male_quantity"]
                record.female_quantity -= item["female_quantity"]
                record.unknown_sex_quantity -= item["unknown_quantity"]
            if item.get("tracked_health"):
                record.healthy_quantity -= item["healthy_quantity"]
            if record.quantity == 0:
                record.lifecycle_status = "Sold"
                record.is_archived = True
            db.add(LivestockTransaction(
                livestock_id=record.id,
                transaction_type="Sale",
                quantity=whole_quantity,
                from_livestock_id=record.id,
                to_livestock_id=None,
                from_pen_id=record.pen_id,
                to_pen_id=None,
                event_date=payload.sale_date,
                reason=f"Sold on invoice {sale.sale_code} to {_clean(payload.buyer_name) or 'buyer not specified'}.",
                recorded_by_user_id=current_user.id,
            ))
        elif item["item_kind"] == "Inventory":
            previous = _decimal(record.quantity).quantize(QTY)
            updated = (previous - item["quantity"]).quantize(QTY)
            record.quantity = updated
            stock_record = InventoryStockRecord(
                inventory_item_id=record.id,
                adjustment_type="Sale",
                quantity=item["quantity"],
                previous_quantity=previous,
                new_quantity=updated,
                adjustment_date=payload.sale_date,
                reason=f"Sold on invoice {sale.sale_code}.",
                reference=sale.sale_code,
                recorded_by_user_id=current_user.id,
            )
            db.add(stock_record)
            db.flush()
        else:
            production_records[record.id] = record

        line_total = (item["quantity"] * item["unit_price"]).quantize(MONEY, rounding=ROUND_HALF_UP)
        db.add(LivestockSaleItem(
            sale_id=sale.id,
            line_number=item["line_number"],
            item_kind=item["item_kind"],
            source_type=item["source_type"],
            production_record_id=item.get("production_record_id"),
            livestock_id=item["livestock_id"],
            crop_id=item["crop_id"],
            inventory_item_id=item.get("inventory_item_id"),
            inventory_stock_record_id=stock_record.id if stock_record else None,
            source_name_snapshot=item["source_name"],
            source_code_snapshot=item["source_code"],
            product_type=item["product_type"],
            quantity=item["quantity"],
            unit=item["unit"],
            unit_price=item["unit_price"],
            line_total=line_total,
            male_quantity=item["male_quantity"],
            female_quantity=item["female_quantity"],
            unknown_quantity=item["unknown_quantity"],
            healthy_quantity=item["healthy_quantity"],
        ))

    db.flush()
    for production in production_records.values():
        remaining = production_available_quantity(db, production)
        production.destination = _production_destination(remaining, _decimal(production.quantity))

    if amount_paid > 0:
        db.add(LivestockSalePayment(
            sale_id=sale.id,
            payment_date=payload.sale_date,
            amount=amount_paid,
            payment_method=_clean(payload.payment_method),
            notes="Initial payment recorded with sale.",
            recorded_by_user_id=current_user.id,
        ))
    _audit(
        db,
        action="Recorded farm sale",
        record_name=_clean(payload.buyer_name) or "Walk-in customer",
        entity_id=sale.sale_code,
        details=(
            f"{len(prepared)} item(s) sold for ₱{float(total):,.2f}. "
            f"Paid ₱{float(amount_paid):,.2f}; balance ₱{float(balance_due):,.2f}."
        ),
        icon="payments",
        actor_user_id=current_user.id,
        actor_name=current_user.full_name or current_user.username,
    )
    db.flush()
    db.refresh(sale)
    return serialize_sale(db, sale)


def add_sale_payment(db: Session, sale_id: int, payload, current_user) -> dict:
    statement = select(LivestockSale).where(LivestockSale.id == sale_id)
    if db.bind is not None and db.bind.dialect.name == "mssql":
        statement = statement.with_hint(LivestockSale, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    else:
        statement = statement.with_for_update()
    sale = db.scalar(statement)
    if sale is None: raise HTTPException(status_code=404, detail="Sale record not found.")
    if sale.is_voided: raise HTTPException(status_code=400, detail="Payments cannot be added to a voided sale.")
    if payload.payment_date < sale.sale_date: raise HTTPException(status_code=400, detail="Payment date cannot be earlier than the sale date.")
    amount = _decimal(payload.amount).quantize(MONEY, rounding=ROUND_HALF_UP)
    balance = _decimal(sale.balance_due).quantize(MONEY)
    if amount <= 0: raise HTTPException(status_code=400, detail="Payment amount must be greater than zero.")
    if amount > balance: raise HTTPException(status_code=400, detail=f"Payment exceeds the remaining balance of ₱{float(balance):,.2f}.")
    payment = LivestockSalePayment(sale_id=sale.id, payment_date=payload.payment_date, amount=amount, payment_method=_clean(payload.payment_method), notes=_clean(payload.notes), recorded_by_user_id=current_user.id)
    db.add(payment)
    paid = (_decimal(sale.amount_paid) + amount).quantize(MONEY, rounding=ROUND_HALF_UP)
    total = _decimal(sale.total_amount).quantize(MONEY)
    sale.amount_paid = paid; sale.balance_due = max(Decimal("0"), total - paid).quantize(MONEY)
    sale.payment_status = "Paid" if sale.balance_due <= 0 else "Partial"
    if payload.payment_method: sale.payment_method = payload.payment_method.strip()
    source_type, source_name, _, source = _source_details(db, livestock_id=sale.livestock_id, crop_id=sale.crop_id)
    if sale.source_type == "Mixed":
        source_name = sale.sale_code
    _audit(db, action="Recorded sale payment", record_name=source_name, entity_id=sale.sale_code, details=f"Payment of ₱{float(amount):,.2f} recorded. Remaining balance: ₱{float(sale.balance_due):,.2f}.", icon="account_balance_wallet", actor_user_id=current_user.id, actor_name=current_user.full_name or current_user.username)
    db.flush(); db.refresh(payment); db.refresh(sale)
    return {"sale": serialize_sale(db, sale, source if isinstance(source, Livestock) else None), "payment": serialize_payment(payment, db)}


def void_sale(db: Session, sale_id: int, reason: str, current_user) -> dict:
    sale_statement = select(LivestockSale).where(LivestockSale.id == sale_id)
    if db.bind is not None and db.bind.dialect.name == "mssql":
        sale_statement = sale_statement.with_hint(LivestockSale, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    else:
        sale_statement = sale_statement.with_for_update()
    sale = db.scalar(sale_statement)
    if sale is None: raise HTTPException(status_code=404, detail="Sale record not found.")
    if sale.is_voided: raise HTTPException(status_code=400, detail="This sale has already been voided.")
    line_items = list(
        db.scalars(
            select(LivestockSaleItem)
            .where(LivestockSaleItem.sale_id == sale.id)
            .order_by(LivestockSaleItem.item_kind.asc(), LivestockSaleItem.id.asc())
        ).all()
    )
    production_records: dict[int, LivestockProductionRecord] = {}
    restored_names: list[str] = []

    if line_items:
        for item in line_items:
            restored_names.append(item.source_name_snapshot)
            if item.item_kind == "Live Animal" and item.livestock_id:
                livestock = _lock_record(db, Livestock, item.livestock_id)
                if livestock is None:
                    raise HTTPException(status_code=404, detail=f"Cannot restore missing livestock source for line {item.line_number}.")
                restored = int(_decimal(item.quantity))
                livestock.quantity += restored
                livestock.male_quantity += int(item.male_quantity or 0)
                livestock.female_quantity += int(item.female_quantity or 0)
                livestock.unknown_sex_quantity += int(item.unknown_quantity or 0)
                livestock.healthy_quantity += int(item.healthy_quantity or 0)
                if livestock.lifecycle_status == "Sold":
                    livestock.lifecycle_status = "Active"
                livestock.is_archived = False
                db.add(LivestockTransaction(
                    livestock_id=livestock.id,
                    transaction_type="Sale Void",
                    quantity=restored,
                    from_livestock_id=None,
                    to_livestock_id=livestock.id,
                    from_pen_id=None,
                    to_pen_id=livestock.pen_id,
                    event_date=farm_today(),
                    reason=f"Voided invoice {sale.sale_code}: {reason.strip()}",
                    recorded_by_user_id=current_user.id,
                ))
            elif item.item_kind == "Inventory" and item.inventory_item_id:
                inventory = _lock_record(db, InventoryItem, item.inventory_item_id)
                if inventory is None:
                    raise HTTPException(status_code=404, detail=f"Cannot restore missing inventory source for line {item.line_number}.")
                previous = _decimal(inventory.quantity).quantize(QTY)
                restored = _decimal(item.quantity).quantize(QTY)
                updated = (previous + restored).quantize(QTY)
                inventory.quantity = updated
                db.add(InventoryStockRecord(
                    inventory_item_id=inventory.id,
                    adjustment_type="Returned",
                    quantity=restored,
                    previous_quantity=previous,
                    new_quantity=updated,
                    adjustment_date=farm_today(),
                    reason=f"Stock restored from voided invoice {sale.sale_code}.",
                    reference=sale.sale_code,
                    recorded_by_user_id=current_user.id,
                ))
            elif item.production_record_id:
                production = _lock_record(db, LivestockProductionRecord, item.production_record_id)
                if production is not None:
                    production_records[production.id] = production
    else:
        # Compatibility for a pre-migration row created by an older client.
        if sale.sale_type == "Live Animal" and sale.livestock_id:
            livestock = _lock_record(db, Livestock, sale.livestock_id)
            if livestock is None:
                raise HTTPException(status_code=404, detail="Related livestock record not found.")
            restored = int(_decimal(sale.quantity))
            livestock.quantity += restored
            livestock.male_quantity += int(sale.male_quantity or 0)
            livestock.female_quantity += int(sale.female_quantity or 0)
            livestock.unknown_sex_quantity += int(sale.unknown_quantity or 0)
            livestock.healthy_quantity += int(sale.healthy_quantity or 0)
            if livestock.lifecycle_status == "Sold":
                livestock.lifecycle_status = "Active"
            livestock.is_archived = False
        if sale.production_record_id:
            production = _lock_record(db, LivestockProductionRecord, sale.production_record_id)
            if production is not None:
                production_records[production.id] = production

    sale.is_voided = True
    sale.void_reason = reason.strip()
    sale.voided_at = datetime.now()
    db.flush()
    for production in production_records.values():
        remaining = production_available_quantity(db, production)
        production.destination = _production_destination(remaining, _decimal(production.quantity))
    source_name = ", ".join(dict.fromkeys(restored_names)) or sale.source_type
    _audit(db, action="Voided sale", record_name=source_name, entity_id=sale.sale_code, details=reason.strip(), icon="undo", actor_user_id=current_user.id, actor_name=current_user.full_name or current_user.username)
    db.flush(); db.refresh(sale)
    return serialize_sale(db, sale)
