"""Portable SQL projection of crop lifecycle state for filtering and paging."""
from datetime import date

from sqlalchemy import Float, Integer, and_, case, cast, func, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app.core.farm_time import farm_today
from app.models import AuditLog, Crop, CropPestDisease, CropYieldRecord, CropSection


class DayDifference(FunctionElement):
    type = Integer()
    inherit_cache = True


@compiles(DayDifference, "mssql")
def _day_difference_mssql(element, compiler, **kwargs):
    start, end = list(element.clauses)
    return f"DATEDIFF(day, {compiler.process(start, **kwargs)}, {compiler.process(end, **kwargs)})"


@compiles(DayDifference)
def _day_difference_sqlite(element, compiler, **kwargs):
    start, end = list(element.clauses)
    return f"CAST(julianday({compiler.process(end, **kwargs)}) - julianday({compiler.process(start, **kwargs)}) AS INTEGER)"


class ReopenYieldBoundary(FunctionElement):
    type = Integer()
    inherit_cache = True


@compiles(ReopenYieldBoundary, "mssql")
def _boundary_mssql(element, compiler, **kwargs):
    details = f"CAST({compiler.process(list(element.clauses)[0], **kwargs)} AS NVARCHAR(MAX))"
    marker = "N'Previous final yield ID: '"
    tail = f"SUBSTRING({details}, CHARINDEX({marker}, {details}) + LEN({marker} + N'x') - 1, 40)"
    digits = f"LEFT({tail}, PATINDEX(N'%[^0-9]%', {tail} + N'x') - 1)"
    return f"CASE WHEN CHARINDEX({marker}, {details}) > 0 THEN TRY_CONVERT(int, NULLIF({digits}, N'')) END"


@compiles(ReopenYieldBoundary)
def _boundary_sqlite(element, compiler, **kwargs):
    details = compiler.process(list(element.clauses)[0], **kwargs)
    marker = "'Previous final yield ID: '"
    tail = f"substr({details}, instr({details}, {marker}) + length({marker}))"
    return f"CASE WHEN instr({details}, {marker}) > 0 AND substr({tail}, 1, 1) GLOB '[0-9]' THEN CAST({tail} AS INTEGER) END"


def crop_projection(today=None):
    today = today or farm_today()
    harvest_type = func.lower(CropYieldRecord.harvest_type)
    history = select(CropYieldRecord.crop_id.label("crop_id"), func.count().label("harvest_count"),
        func.sum(CropYieldRecord.quantity_kg).label("total_harvest_quantity_kg"),
        func.sum(case((harvest_type == "partial harvest", CropYieldRecord.quantity_kg), else_=0)).label("previous_partial_harvest_total_kg"),
        func.min(CropYieldRecord.harvest_date).label("first_harvest_date"),
        func.max(case((harvest_type == "final harvest", CropYieldRecord.harvest_date))).label("final_harvest_date"),
        *(func.max(case((harvest_type == kind + " harvest", column))).label(kind + suffix)
          for kind in ("final", "partial") for suffix, column in (("_id", CropYieldRecord.id), ("_at", CropYieldRecord.created_at))))\
        .group_by(CropYieldRecord.crop_id).subquery()
    ranked = select(AuditLog.entity_id.label("code"), AuditLog.created_at.label("at"),
        ReopenYieldBoundary(AuditLog.details).label("boundary"),
        func.row_number().over(partition_by=AuditLog.entity_id, order_by=(AuditLog.created_at.desc(), AuditLog.id.desc())).label("rank"))\
        .where(AuditLog.event_type == "audit", AuditLog.module == "Crop", AuditLog.action == "Reopened crop cycle").subquery()
    reopened = select(ranked.c.code, ranked.c.at, ranked.c.boundary).where(ranked.c.rank == 1).subquery()

    def current_harvest(kind):
        identifier, recorded_at = history.c[kind + "_id"], history.c[kind + "_at"]
        return and_(identifier.is_not(None), or_(reopened.c.at.is_(None),
            and_(reopened.c.boundary.is_not(None), identifier > reopened.c.boundary),
            and_(reopened.c.boundary.is_(None), recorded_at > reopened.c.at)))

    final, partial = current_harvest("final"), current_harvest("partial")
    progress = case((or_(Crop.planting_date.is_(None), Crop.estimated_harvest.is_(None)), None), (Crop.planting_date >= today, 0.0), (Crop.estimated_harvest <= today, 100.0),
        else_=func.round(cast(DayDifference(Crop.planting_date, today), Float) /
            func.nullif(cast(DayDifference(Crop.planting_date, Crop.estimated_harvest), Float), 0) * 100.0, 1))
    effective_status = case((Crop.registration_kind != "legacy", Crop.status), (Crop.status == "Failed", "Failed"),
        (or_(Crop.status == "Harvested", final), "Harvested"),
        (or_(Crop.status == "Harvesting", partial), "Harvesting"),
        (Crop.confirmed_ready_at.is_not(None), "Ready for Harvest"),
        (Crop.observed_growth_stage == "Seeded", "Planted"),
        (and_(Crop.observed_growth_stage.is_not(None), Crop.observed_growth_stage != ""), "Growing"),
        (progress <= 0, "Planted"), (progress < 90, "Growing"), else_="Ready for Harvest")
    pest_exists = select(CropPestDisease.id).where(CropPestDisease.crop_id == Crop.id, CropPestDisease.status != "Resolved").exists()
    pest_id = select(CropPestDisease.id).where(CropPestDisease.crop_id == Crop.id, CropPestDisease.status != "Resolved")\
        .order_by(CropPestDisease.date_detected.desc(), CropPestDisease.id.desc()).limit(1).scalar_subquery()
    return select(*Crop.__table__.columns, CropSection.name.label("section_name"),
        *(history.c[name] for name in ("harvest_count", "total_harvest_quantity_kg", "previous_partial_harvest_total_kg", "first_harvest_date", "final_harvest_date")),
        case((final, 1), else_=0).label("has_final"), case((partial, 1), else_=0).label("has_partial"),
        case((pest_exists, 1), else_=0).label("has_pest_alert"), pest_id.label("active_pest_id"),
        effective_status.label("computed_status"))\
        .outerjoin(CropSection, CropSection.id == Crop.section_id)\
        .outerjoin(history, history.c.crop_id == Crop.id).outerjoin(reopened, reopened.c.code == Crop.crop_code)


def filtered_crop_query(*, search="", crop_type="All", status_filter="Active Crops", field="All", planting_date=None):
    projection = crop_projection().subquery()
    statement = select(projection)
    active = projection.c.is_archived == False
    status = projection.c.computed_status
    if status_filter == "Archived": statement = statement.where(~active)
    elif status_filter == "Active Crops": statement = statement.where(active, status.not_in(["Harvested", "Failed"]))
    elif status_filter != "All": statement = statement.where(active, status == ("Harvested" if status_filter == "Fully Harvested/Completed" else status_filter))
    if crop_type != "All": statement = statement.where(projection.c.name == crop_type)
    if field != "All": statement = statement.where(projection.c.field == field)
    if planting_date: statement = statement.where(projection.c.planting_date == planting_date)
    if search.strip():
        needle = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        statement = statement.where(or_(*(projection.c[name].ilike(needle, escape="\\") for name in ("name", "variety", "field", "crop_code"))))
    priority = case((status == "Ready for Harvest", 0), (status == "Harvesting", 1), (status == "Growing", 2), (status == "Planted", 3), else_=4)
    ordering = (priority, case((status == "Ready for Harvest", projection.c.estimated_harvest), else_=date.max), func.lower(projection.c.name), projection.c.id)
    return statement, ordering
