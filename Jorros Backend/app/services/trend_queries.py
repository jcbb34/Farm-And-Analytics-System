"""Bounded monthly trend projections, preserving the analysis response shape."""
from collections import defaultdict
from types import SimpleNamespace

from sqlalchemy import Float, case, cast, extract, func, select

from app.models import (
    Crop, CropYieldRecord, Livestock, LivestockFeedingRecord, LivestockGrowthRecord,
    LivestockProductionRecord, LivestockProcessingRecord, LivestockReproductionRecord,
    LivestockSale, LivestockSalePayment, WeatherHistory,
)


def _exact(db, column):
    # Python's grouping keeps differently cased names separate. Preserve that
    # behavior when the farm database uses a case-insensitive SQL collation.
    return column.collate("Latin1_General_100_BIN2") if db.get_bind().dialect.name == "mssql" else column


def load_trend_aggregates(db, start, end):
    counts = defaultdict(int)
    crop_yield, crop_names, feed, growth = defaultdict(float), defaultdict(float), defaultdict(float), {}
    weather, production = {}, defaultdict(lambda: defaultdict(float))
    sales, crop_sales, animal_sales, cash = (defaultdict(float) for _ in range(4))
    reproduction, offspring, alive = (defaultdict(int) for _ in range(3))
    reproduction_totals = defaultdict(int)

    def months(column):
        return extract("year", column), extract("month", column)

    def grouped(column, *values):
        year, month = months(column)
        return select(year, month, *values).where(column >= start, column <= end).group_by(year, month)

    def key(year, month):
        return f"{int(year):04d}-{int(month):02d}"

    name = _exact(db, Crop.name)
    statement = grouped(CropYieldRecord.harvest_date, name, func.sum(CropYieldRecord.quantity_kg), func.count())\
        .outerjoin(Crop, Crop.id == CropYieldRecord.crop_id).group_by(name)\
        .order_by(func.min(CropYieldRecord.harvest_date), func.min(CropYieldRecord.id))
    for year, month, crop_name, quantity, count in db.execute(statement):
        crop_yield[key(year, month)] += float(quantity or 0)
        crop_names[crop_name or "Unknown Crop"] += float(quantity or 0)
        counts["crop_yield_records"] += count

    statement = grouped(WeatherHistory.recorded_date,
        *(func.avg(cast(func.coalesce(column, 0), Float)) for column in
            (WeatherHistory.rainfall_mm, WeatherHistory.temperature_c, WeatherHistory.humidity_percent)), func.count())
    for year, month, rain, temperature, humidity, count in db.execute(statement):
        weather[key(year, month)] = {"rainfall": rain, "temperature": temperature, "humidity": humidity}
        counts["weather_records"] += count

    for year, month, quantity, count in db.execute(grouped(LivestockFeedingRecord.feeding_date,
            func.sum(LivestockFeedingRecord.actual_quantity_kg), func.count())):
        feed[key(year, month)] = float(quantity or 0)
        counts["feeding_records"] += count

    for year, month, gain, count in db.execute(grouped(LivestockGrowthRecord.measurement_date,
            func.avg(cast(LivestockGrowthRecord.average_daily_gain_kg, Float)), func.count())):
        growth[key(year, month)] = gain
        counts["livestock_growth_records"] += count

    # Only the first/last measurements are needed for each growth summary.
    model = LivestockGrowthRecord
    window = dict(partition_by=model.livestock_id)
    ranked = select(*model.__table__.columns,
        func.row_number().over(**window, order_by=(model.measurement_date, model.id)).label("first_rank"),
        func.row_number().over(**window, order_by=(model.measurement_date.desc(), model.id.desc())).label("last_rank"),
        func.count().over(**window).label("measurement_count"))\
        .where(model.measurement_date >= start, model.measurement_date <= end).subquery()
    samples, animals = [], {}
    statement = select(ranked, Livestock.record_name.label("animal_name"), Livestock.animal_type.label("animal_type"))\
        .outerjoin(Livestock, Livestock.id == ranked.c.livestock_id)\
        .where((ranked.c.first_rank == 1) | (ranked.c.last_rank == 1))\
        .order_by(ranked.c.measurement_date, ranked.c.id)
    for row in db.execute(statement).mappings():
        values = dict(row)
        name, kind = values.pop("animal_name"), values.pop("animal_type")
        samples.append(SimpleNamespace(**values))
        if name is not None:
            animals[row["livestock_id"]] = SimpleNamespace(record_name=name, animal_type=kind)

    model = LivestockProductionRecord
    voided_ids = select(LivestockProcessingRecord.production_record_id.label("production_id")).where(
        LivestockProcessingRecord.is_voided == True, LivestockProcessingRecord.production_record_id.is_not(None)).distinct().subquery()
    voided = voided_ids.c.production_id.is_not(None)
    output, unit = _exact(db, model.output_type), _exact(db, model.unit)
    statement = grouped(model.record_date, output, unit, func.count(),
        func.sum(case((voided, 0), else_=1)), func.sum(case((voided, 0), else_=model.quantity)))\
        .outerjoin(voided_ids, voided_ids.c.production_id == model.id)\
        .where(func.lower(model.source_type) == "livestock").group_by(output, unit)
    for year, month, output, unit, before_count, valid_count, quantity in db.execute(statement):
        counts["voided_production_records_excluded"] += before_count - valid_count
        counts["livestock_production_records"] += valid_count
        if not valid_count:
            continue
        output, unit = str(output or "Other").strip() or "Other", str(unit or "").strip()
        series = f"{output} ({unit})" if unit else output
        production[key(year, month)][series] += float(quantity or 0)

    model = LivestockReproductionRecord
    fields = ("breeder_female_quantity", "confirmed_pregnant_quantity", "eggs_set", "fertile_eggs", "offspring_count", "alive_offspring", "loss_count")
    record_type = func.lower(func.ltrim(func.rtrim(model.record_type)))
    statement = grouped(model.event_date, func.count(),
        *(func.sum(getattr(model, field)) for field in fields),
        func.sum(case((record_type.in_(["birth", "hatch", "farrowing", "kidding", "calving"]), 1), else_=0)))
    for year, month, count, *values in db.execute(statement):
        month_key = key(year, month)
        reproduction[month_key] = count
        counts["reproduction_records"] += count
        for field, value in zip(fields, values):
            reproduction_totals[field] += int(value or 0)
        reproduction_totals["birth_hatch_events"] += int(values[-1] or 0)
        offspring[month_key] = int(values[fields.index("offspring_count")] or 0)
        alive[month_key] = int(values[fields.index("alive_offspring")] or 0)

    is_crop = func.lower(func.ltrim(func.rtrim(func.coalesce(LivestockSale.source_type, "")))) == "crop"
    statement = grouped(LivestockSale.sale_date, func.sum(LivestockSale.total_amount),
        func.sum(case((is_crop, LivestockSale.total_amount), else_=0)),
        func.sum(case((is_crop, 0), else_=LivestockSale.total_amount)), func.count(),
        func.sum(case((is_crop, 1), else_=0))).where(LivestockSale.is_voided == False)
    for year, month, total, crop_total, animal_total, count, crop_count in db.execute(statement):
        month_key = key(year, month)
        sales[month_key], crop_sales[month_key], animal_sales[month_key] = float(total or 0), float(crop_total or 0), float(animal_total or 0)
        counts["sales_records"] += count
        counts["crop_sales_records"] += int(crop_count or 0)
        counts["livestock_sales_records"] += count - int(crop_count or 0)

    statement = grouped(LivestockSalePayment.payment_date, func.sum(LivestockSalePayment.amount), func.count())\
        .join(LivestockSale, LivestockSale.id == LivestockSalePayment.sale_id).where(LivestockSale.is_voided == False)
    for year, month, amount, count in db.execute(statement):
        cash[key(year, month)] = float(amount or 0)
        counts["payment_records"] += count

    health_key = _exact(db, Livestock.health_status)
    health = defaultdict(int)
    for name, quantity in db.execute(select(health_key, func.sum(Livestock.quantity))
            .where(Livestock.is_archived == False).group_by(health_key)):
        health[str(name or "Unknown")] += int(quantity or 0)
    return {"counts": counts, "crop_yield": crop_yield, "crop_names": crop_names, "feed": feed, "growth": growth,
        "weather": weather, "production": production, "sales": sales, "crop_sales": crop_sales, "animal_sales": animal_sales,
        "cash": cash, "reproduction": reproduction, "offspring": offspring, "alive": alive,
        "reproduction_totals": reproduction_totals, "growth_records": samples, "animals": animals,
        "health": dict(health)}
