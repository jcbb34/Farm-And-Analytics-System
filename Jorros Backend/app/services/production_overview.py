"""Whole-farm production totals without materializing invoices or stock lots."""
from sqlalchemy import Float, case, cast, func, select, union_all

from app.models import LivestockProductionRecord as Production, LivestockSale as Sale, LivestockSaleItem as Item


def _source(column, crop_id):
    return func.lower(func.coalesce(func.nullif(column, ""), case((crop_id.is_not(None), "Crop"), else_="Livestock")))


def source_sales_totals(db):
    # Legacy invoices with no lines remain a single synthetic line. A real line
    # set always takes precedence, including mixed invoices and zero-value lines.
    lines = select(Item.sale_id.label("sale_id"), func.lower(Item.source_type).label("source"),
                   func.sum(Item.line_total).label("amount")).group_by(Item.sale_id, func.lower(Item.source_type)).subquery()
    modern = select(Sale.id.label("sale_id"), lines.c.source, lines.c.amount).join(lines, lines.c.sale_id == Sale.id).where(Sale.is_voided == False)
    legacy = select(Sale.id.label("sale_id"), _source(Sale.source_type, Sale.crop_id).label("source"), Sale.total_amount.label("amount"))\
        .where(Sale.is_voided == False, ~select(Item.id).where(Item.sale_id == Sale.id).exists())
    sources = union_all(modern, legacy).subquery()
    ratio = case((Sale.total_amount > 0, cast(sources.c.amount, Float) / func.nullif(cast(Sale.total_amount, Float), 0)), else_=0.0)
    statement = select(sources.c.source, func.sum(sources.c.amount),
        func.sum(func.coalesce(Sale.amount_paid, 0) * ratio), func.sum(func.coalesce(Sale.balance_due, 0) * ratio))\
        .join(Sale, Sale.id == sources.c.sale_id).where(sources.c.source.in_(["crop", "livestock"]), sources.c.amount > 0).group_by(sources.c.source)
    result = {"crop": (0.0, 0.0, 0.0), "livestock": (0.0, 0.0, 0.0)}
    result.update((kind, (float(gross or 0), float(paid or 0), float(balance or 0))) for kind, gross, paid, balance in db.execute(statement))
    return result


def production_stock_totals(db):
    sold_lines = select(Item.production_record_id.label("production_id"), func.sum(Item.quantity).label("sold"))\
        .join(Sale, Sale.id == Item.sale_id).where(Sale.is_voided == False, Item.production_record_id.is_not(None)).group_by(Item.production_record_id).subquery()
    sold_legacy = select(Sale.production_record_id.label("production_id"), func.sum(Sale.quantity).label("sold"))\
        .where(Sale.is_voided == False, Sale.production_record_id.is_not(None),
            ~select(Item.id).where(Item.sale_id == Sale.id).exists()).group_by(Sale.production_record_id).subquery()
    remaining = Production.quantity - func.coalesce(sold_lines.c.sold, 0) - func.coalesce(sold_legacy.c.sold, 0)
    source = _source(Production.source_type, Production.crop_id)
    unit = func.lower(func.ltrim(func.rtrim(Production.unit)))
    output = func.lower(func.coalesce(Production.output_type, ""))
    crop, animal = source == "crop", source != "crop"
    statement = select(
        func.sum(case((animal & output.like("%egg%"), remaining), else_=0)).label("eggs_available"),
        func.sum(case((animal & output.like("%meat%") & (unit == "kg"), remaining), else_=0)).label("meat_available_kg"),
        func.sum(case((animal & output.like("%milk%") & unit.in_(["l", "liter", "liters", "litre", "litres"]), remaining), else_=0)).label("milk_available_l"),
        func.sum(case((crop & (unit == "kg"), remaining), else_=0)).label("crop_available_kg"),
        func.sum(case((crop, 1), else_=0)).label("crop_product_lots"),
        func.sum(case((animal, 1), else_=0)).label("livestock_product_lots"))\
        .select_from(Production).outerjoin(sold_lines, sold_lines.c.production_id == Production.id)\
        .outerjoin(sold_legacy, sold_legacy.c.production_id == Production.id)\
        .where(Production.track_sale_inventory == True, remaining > 0)
    row = db.execute(statement).mappings().one()
    return {key: int(value or 0) if key.endswith("_lots") else float(value or 0) for key, value in row.items()}
