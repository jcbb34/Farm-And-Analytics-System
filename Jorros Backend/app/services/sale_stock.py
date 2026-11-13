"""Searchable, paged invoice choices; mutations still verify and lock live stock."""
from sqlalchemy import case, func, or_, select

from app.models import Crop, InventoryItem, Livestock, LivestockProductionRecord as Production, LivestockSale as Sale, LivestockSaleItem as Item


def production_availability():
    lines = select(Item.production_record_id.label("production_id"), func.sum(Item.quantity).label("sold"))\
        .join(Sale, Sale.id == Item.sale_id).where(Sale.is_voided == False, Item.production_record_id.is_not(None)).group_by(Item.production_record_id).subquery()
    legacy = select(Sale.production_record_id.label("production_id"), func.sum(Sale.quantity).label("sold"))\
        .where(Sale.is_voided == False, Sale.production_record_id.is_not(None),
            ~select(Item.id).where(Item.sale_id == Sale.id).exists()).group_by(Sale.production_record_id).subquery()
    sold = func.coalesce(lines.c.sold, 0) + func.coalesce(legacy.c.sold, 0)
    return select(Production.id.label("production_id"), sold.label("sold_quantity"), (Production.quantity - sold).label("available_quantity"))\
        .outerjoin(lines, lines.c.production_id == Production.id).outerjoin(legacy, legacy.c.production_id == Production.id).subquery()


def _matching(search, *columns):
    needle = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(*(column.ilike(needle, escape="\\") for column in columns))


def stock_page(db, *, kind="Production", search="", source_type=None, offset=0, limit=25):
    if kind == "Production":
        available = production_availability()
        source = func.lower(func.coalesce(func.nullif(Production.source_type, ""), case((Production.crop_id.is_not(None), "Crop"), else_="Livestock")))
        name = case((source == "crop", func.coalesce(Crop.name, "Unknown crop")), else_=func.coalesce(Livestock.record_name, "Unknown livestock"))
        code = case((source == "crop", func.coalesce(Crop.crop_code, "")), else_=func.coalesce(Livestock.animal_code, ""))
        statement = select(Production.id, Production.source_type, name.label("name"), code.label("code"),
            Production.output_type.label("product_type"), available.c.available_quantity, Production.unit)\
            .join(available, available.c.production_id == Production.id).outerjoin(Crop, Crop.id == Production.crop_id)\
            .outerjoin(Livestock, Livestock.id == Production.livestock_id)\
            .where(Production.track_sale_inventory == True, available.c.available_quantity > 0)
        if str(source_type or "").lower() in {"crop", "livestock"}: statement = statement.where(source == source_type.lower())
        if search.strip(): statement = statement.where(_matching(search, name, code, Production.output_type))
        ordering = (Production.record_date.desc(), Production.id.desc())
    elif kind == "Live Animal":
        statement = select(Livestock.id, Livestock.record_name.label("name"), Livestock.animal_code.label("code"),
            Livestock.animal_type.label("product_type"), Livestock.quantity.label("available_quantity"))\
            .where(Livestock.is_archived == False, Livestock.lifecycle_status == "Active", Livestock.quantity > 0)
        if search.strip(): statement = statement.where(_matching(search, Livestock.record_name, Livestock.animal_code, Livestock.animal_type, Livestock.breed))
        ordering = (Livestock.record_name, Livestock.id)
    else:
        statement = select(InventoryItem.id, InventoryItem.name, InventoryItem.item_code.label("code"),
            InventoryItem.category.label("product_type"), InventoryItem.quantity.label("available_quantity"),
            InventoryItem.unit, InventoryItem.price.label("suggested_price"))\
            .where(InventoryItem.is_archived == False, InventoryItem.is_saleable == True, InventoryItem.quantity > 0)
        if search.strip(): statement = statement.where(_matching(search, InventoryItem.name, InventoryItem.item_code, InventoryItem.category))
        ordering = (InventoryItem.name, InventoryItem.id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = []
    for row in db.execute(statement.order_by(*ordering).offset(offset).limit(limit)).mappings():
        item = dict(row)
        item.update(kind=kind, available_quantity=float(item["available_quantity"]),
                    unit="head" if kind == "Live Animal" else item["unit"])
        if "suggested_price" in item: item["suggested_price"] = float(item["suggested_price"] or 0)
        items.append(item)
    return {"items": items, "total": total, "offset": offset, "limit": limit}
