"""Authorized, paged creation choices with independent selected-record lookup."""

from sqlalchemy import func, or_, select
from app.core.farm_time import farm_today
from app.models import Crop, InventoryItem, Livestock

CROP_CATEGORIES = [
    "Fertilizer",
    "Fertilizers",
    "Pesticide",
    "Pesticides",
    "Herbicide",
    "Herbicides",
    "Fungicide",
    "Fungicides",
    "Farm Supplies",
]
ANIMAL_CATEGORIES = [
    "Livestock Feed",
    "Animal Feed",
    "Feed",
    "Feeds",
    "Medicine",
    "Medicines",
    "Animal Medicine",
    "Livestock Medicine",
    "Vaccine",
    "Vaccines",
    "Vitamin",
    "Vitamins",
    "Supplement",
    "Supplements",
    "Disinfectant",
    "Disinfectants",
    "Cleaning Supplies",
    "Treatment Supply",
    "Treatment Supplies",
]


def supply_predicate(db, module, kind):
    category = func.lower(func.ltrim(func.rtrim(InventoryItem.category)))
    exact = (
        InventoryItem.category.collate("Latin1_General_100_BIN2")
        if db.get_bind().dialect.name == "mssql"
        else InventoryItem.category
    )
    if module == "Crop":
        compatible = ~category.contains("seed")
        if kind in {"fertilizer", "herbicide", "fungicide"}:
            return compatible & category.contains(
                "fertiliz" if kind == "fertilizer" else kind
            )
        if kind == "pesticide":
            return compatible & or_(
                category.contains("pesticide"), category.contains("insecticide")
            )
        return compatible & exact.in_(CROP_CATEGORIES)
    if module == "Livestock":
        compatible = category.not_in(
            [
                "seed",
                "seeds",
                "fertilizer",
                "fertilizers",
                "pesticide",
                "pesticides",
                "herbicide",
                "herbicides",
                "fungicide",
                "fungicides",
            ]
        )
        groups = {
            "feed": ["livestock feed", "animal feed", "feed", "feeds"],
            "medicine": [
                "medicine",
                "medicines",
                "animal medicine",
                "livestock medicine",
                "treatment supply",
                "treatment supplies",
            ],
            "supplement": ["vitamin", "vitamins", "supplement", "supplements"],
            "disinfectant": ["disinfectant", "disinfectants", "cleaning supplies"],
        }
        if kind in groups:
            return compatible & category.in_(groups[kind])
        if kind == "vaccine":
            return compatible & or_(
                category.in_(["vaccine", "vaccines"]),
                func.lower(InventoryItem.name).contains("vaccine"),
            )
        return compatible & exact.in_(ANIMAL_CATEGORIES)
    return None


def resource_choice_page(
    db,
    *,
    domain,
    search="",
    offset=0,
    limit=25,
    selected_id=None,
    work_module=None,
    work_kind="all",
    inventory_use=None,
):
    if domain == "Crop":
        model = Crop
        stmt = select(
            Crop.id, Crop.name, Crop.crop_code.label("code"), Crop.field
        ).where(Crop.is_archived == False)
        columns = [Crop.name, Crop.crop_code, Crop.field, Crop.variety]
        ordering = [Crop.name, Crop.id]
    elif domain == "Livestock":
        model = Livestock
        stmt = select(
            Livestock.id,
            Livestock.record_name.label("name"),
            Livestock.animal_code.label("code"),
            Livestock.pen_location.label("location"),
            Livestock.feed_times,
            Livestock.feed_inventory_item_id,
        ).where(Livestock.is_archived == False)
        columns = [
            Livestock.record_name,
            Livestock.animal_code,
            Livestock.pen_location,
            Livestock.breed,
            Livestock.animal_type,
        ]
        ordering = [Livestock.record_name, Livestock.id]
    else:
        model = InventoryItem
        stmt = select(
            InventoryItem.id,
            InventoryItem.name,
            InventoryItem.item_code.label("code"),
            InventoryItem.category,
            InventoryItem.unit,
            InventoryItem.quantity,
            InventoryItem.location,
            InventoryItem.reorder_level,
            InventoryItem.expiration_date,
            InventoryItem.batch_number,
        ).where(InventoryItem.is_archived == False)
        columns = [
            InventoryItem.name,
            InventoryItem.item_code,
            InventoryItem.category,
            InventoryItem.location,
        ]
        ordering = [InventoryItem.name, InventoryItem.id]
        if inventory_use:
            category = func.lower(func.ltrim(func.rtrim(InventoryItem.category)))
            if inventory_use == "livestock_feeding":
                compatible = or_(category.contains("feed"), func.lower(InventoryItem.name).contains("feed"))
                compatible &= func.lower(func.ltrim(func.rtrim(InventoryItem.unit))).in_(["kg", "kilogram", "kilograms"])
            elif inventory_use == "livestock_vaccination":
                compatible = category.in_(["vaccine", "vaccines", "vaccination"])
            else:
                raise ValueError("Unknown inventory selection use.")
            compatible &= (InventoryItem.quantity > 0) & or_(
                InventoryItem.expiration_date.is_(None), InventoryItem.expiration_date >= farm_today(),
            )
        else:
            compatible = supply_predicate(db, work_module, work_kind)
        if compatible is not None:
            stmt = stmt.where(compatible)
    selected_stmt = stmt.where(model.id == selected_id) if selected_id else None
    if search.strip():
        needle = (
            "%"
            + search.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            + "%"
        )
        stmt = stmt.where(
            or_(*(column.ilike(needle, escape="\\") for column in columns))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    def payload(row):
        value = dict(row)
        if domain == "Crop":
            value.update(cropCode=value["code"], location=value["field"])
        elif domain == "Livestock":
            from app.services.task_engine import _feeding_occurrences

            slots = [
                slot for _, slot, _ in _feeding_occurrences(value.pop("feed_times"))
            ]
            value.update(
                recordName=value["name"],
                animalId=value["code"],
                penLocation=value["location"],
                feedingSlots=slots,
                feeding_slots=slots,
            )
        else:
            value.update(
                itemCode=value["code"],
                quantity=float(value["quantity"] or 0),
                reorder_level=float(value["reorder_level"] or 0),
                expirationDate=value["expiration_date"],
                batchNumber=value["batch_number"],
            )
        return value

    items = [
        payload(row)
        for row in db.execute(
            stmt.order_by(*ordering).offset(offset).limit(limit)
        ).mappings()
    ]
    selected = (
        db.execute(selected_stmt).mappings().first()
        if selected_stmt is not None
        else None
    )
    return {
        "items": items,
        "selected": payload(selected) if selected else None,
        "total": total,
        "offset": offset,
        "limit": limit,
    }
