"""Read-only list projections: bounded rows and whole-collection aggregates.

Crop progress is computed from lightweight scalar rows, streamed in batches;
growth, pest and harvest histories are never materialized for a list request.
"""
from collections import Counter, defaultdict, deque
from datetime import date, datetime, time, timedelta
from heapq import nsmallest
import re

from sqlalchemy import case, func, or_, select

from app.core.farm_time import farm_today
from app.models import AuditLog, Crop, CropGrowthRecord, CropPestDisease, CropYieldRecord, Livestock, LivestockVaccinationRecord
from app.schemas.crops import CropPestDiseaseResponse, CropYieldResponse
from app.schemas.livestock import LivestockResponse, LivestockVaccinationResponse
from app.services.crop_projection import crop_projection, filtered_crop_query
from app.services.crop_growth import calculate_crop_progress, stage_for_progress, status_for_progress


def _crop_rows(db, statement=None):
    statement = statement if statement is not None else crop_projection()
    for raw in db.execute(statement.execution_options(yield_per=250)).mappings():
        row = dict(raw)
        row.pop("computed_status", None)
        progress = calculate_crop_progress(row["planting_date"], row["estimated_harvest"])
        row["estimated_progress"] = progress
        row["estimated_growth_stage"] = stage_for_progress(progress)
        if row.get("registration_kind", "legacy") != "legacy":
            row["current_growth"] = progress
            row["growth_stage"] = row["observed_growth_stage"] or stage_for_progress(progress)
        elif row["status"] == "Failed":
            pass
        elif row["status"] == "Harvested" or row["has_final"]:
            row.update(status="Harvested", current_growth=100, growth_stage="Harvested")
        elif row["status"] == "Harvesting" or row["has_partial"]:
            row.update(status="Harvesting", current_growth=100, growth_stage="Harvesting / Production")
        elif row["confirmed_ready_at"] is not None:
            row.update(status="Ready for Harvest", current_growth=100, growth_stage="Harvest Ready")
        else:
            observed = row["observed_growth_stage"]
            status = ("Planted" if observed == "Seeded" else "Growing") if observed else status_for_progress(progress)
            row.update(status=status, current_growth=progress, growth_stage=observed or stage_for_progress(progress))
        for key in ("harvest_count", "total_harvest_quantity_kg", "previous_partial_harvest_total_kg"):
            row[key] = row[key] or 0
        yield row


def _crop_scan_summary(db, *, offset=0, limit=0, search="", crop_type="All", status_filter="Active Crops", field="All", planting_date=None):
    names, current_names, fields, status_counts, months = set(), set(), set(), Counter(), defaultdict(lambda: {"cropCount": 0, "area": 0})
    totals = {"total": 0, "active": 0, "harvested": 0, "alerts": 0, "ready": 0, "area": 0.0}
    growth_sum = growth_count = survival_sum = survival_count = 0
    counted_footprints = set()
    matches = 0
    needle = str(search or "").strip().casefold()
    rank = {"Ready for Harvest": 0, "Harvesting": 1, "Growing": 2, "Planted": 3}

    def matching_rows():
        nonlocal matches, growth_sum, growth_count, survival_sum, survival_count
        for row in _crop_rows(db):
            names.add(row["name"]); fields.add(row["field"])
            active = not row["is_archived"]
            if active:
                current_names.add(row["name"])
                totals["total"] += 1
                totals["active"] += row["status"] not in {"Harvested", "Failed"}
                totals["harvested"] += row["status"] == "Harvested"
                totals["alerts"] += bool(row["has_pest_alert"])
                totals["ready"] += row["status"] == "Ready for Harvest"
                footprint_key = row.get("footprint_id") or f"legacy:{row['id']}"
                if footprint_key not in counted_footprints:
                    totals["area"] += float(row["area_hectares"] or 0)
                    counted_footprints.add(footprint_key)
                status_counts[row["status"]] += 1
                if row["current_growth"] is not None:
                    growth_sum += float(row["current_growth"])
                    growth_count += 1
                if row["quantity_planted"]:
                    survival_sum += float(row["current_surviving"] or 0) / row["quantity_planted"] * 100
                    survival_count += 1
                if row["status"] not in {"Harvested", "Failed"} and row["estimated_harvest"] is not None:
                    month = row["estimated_harvest"].strftime("%Y-%m")
                    months[month]["cropCount"] += 1
                    months[month]["area"] += float(row["area_hectares"] or 0)
            if status_filter == "All": status_match = True
            elif status_filter == "Archived": status_match = not active
            elif status_filter == "Active Crops": status_match = active and row["status"] not in {"Harvested", "Failed"}
            elif status_filter == "Fully Harvested/Completed": status_match = active and row["status"] == "Harvested"
            else: status_match = active and row["status"] == status_filter
            if not status_match or (crop_type != "All" and row["name"] != crop_type) or (field != "All" and row["field"] != field): continue
            if planting_date and row["planting_date"] != planting_date: continue
            if needle and not any(needle in str(row[key] or "").casefold() for key in ("name", "variety", "field", "crop_code")): continue
            matches += 1
            yield row

    # Only the requested prefix is retained; histories never enter this list.
    if limit:
        retained = nsmallest(offset + limit, matching_rows(), key=lambda row: (
            rank.get(row["status"], 4), row["estimated_harvest"] if row["status"] == "Ready for Harvest" and row["estimated_harvest"] else date.max,
            row["name"].casefold(), row["id"]))
    else:
        deque(matching_rows(), maxlen=0)  # Aggregate without retaining rows.
        retained = []
    items = retained[offset:offset + limit] if limit else []
    if limit == 0: retained.clear()
    _attach_crop_page(db, items)
    yield_groups = db.execute(select(Crop.name, func.sum(CropYieldRecord.quantity_kg), func.count(CropYieldRecord.id))
        .join(CropYieldRecord, CropYieldRecord.crop_id == Crop.id).where(Crop.is_archived == False)
        .group_by(Crop.name).order_by(func.sum(CropYieldRecord.quantity_kg).desc(), Crop.name)).all()
    total_yield = sum(float(quantity or 0) for _, quantity, _ in yield_groups)
    overview = {**totals, "status_counts": dict(status_counts), "names": sorted(names), "current_names": sorted(current_names), "fields": sorted(fields),
        "analytics": {
            "monthlyPrediction": [{"monthKey": key, **value} for key, value in sorted(months.items())],
            "yieldByCrop": [{"cropName": name, "quantityKg": float(quantity or 0), "records": count} for name, quantity, count in yield_groups],
            "productivityStats": {"totalYield": total_yield, "totalArea": totals["area"],
                "averageGrowth": growth_sum / growth_count if growth_count else None if totals["total"] else 0,
                "averageSurvival": survival_sum / survival_count if survival_count else None,
                "topYieldCrop": yield_groups[0][0] if yield_groups else "No data",
                "yieldPerHectare": total_yield / totals["area"] if totals["area"] else 0},
        }}
    return {"items": items, "total": matches, "offset": offset, "limit": limit, "overview": overview}


def _attach_crop_page(db, items):
    from app.routers.crops import _annotate_pending_harvest_workflows
    parents = list(db.scalars(select(Crop).where(Crop.id.in_([row["id"] for row in items]))).all()) if items else []
    annotated = {row.id: row for row in _annotate_pending_harvest_workflows(db, parents)}
    pest_ids = [row["active_pest_id"] for row in items if row["active_pest_id"]]
    pests = {row.id: CropPestDiseaseResponse.model_validate(row).model_dump(mode="json")
             for row in db.scalars(select(CropPestDisease).where(CropPestDisease.id.in_(pest_ids))).all()} if pest_ids else {}
    for row in items:
        parent = annotated[row["id"]]
        for name in ("monitoring_summary", "care_protocol_name", "care_protocol_version", "care_protocol_status",
                     "pending_harvest_task_id", "pending_harvest_task_code", "pending_harvest_task_status",
                     "pending_harvest_type", "pending_harvest_message"):
            row[name] = getattr(parent, name, None)
        # One real unresolved issue for the badge; full history loads on open.
        pest = pests.get(row.pop("active_pest_id"))
        row["pest_diseases"] = [pest] if pest else []
        row.pop("has_pest_alert", None)
        row.pop("has_final", None); row.pop("has_partial", None)
    return items


def crop_summary(db):
    # Exact Python rounding remains in the independent whole-farm summary.
    # Filtering/searching and loading later pages do not repeat this scan.
    return _crop_scan_summary(db, limit=0)["overview"]


def crop_listing(db, *, offset=0, limit=50, search="", crop_type="All", status_filter="Active Crops", field="All", planting_date=None, include_overview=True):
    if not limit:
        return _crop_scan_summary(db, limit=0)
    statement, ordering = filtered_crop_query(search=search, crop_type=crop_type, status_filter=status_filter, field=field, planting_date=planting_date)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(_crop_rows(db, statement.order_by(*ordering).offset(offset).limit(limit)))
    _attach_crop_page(db, items)
    return {"items": items, "total": total, "offset": offset, "limit": limit,
        "overview": crop_summary(db) if include_overview else None}


def crop_chart(db, start_date, end_date):
    stmt = select(CropGrowthRecord, Crop.name, Crop.crop_code).join(Crop, Crop.id == CropGrowthRecord.crop_id)\
        .where(Crop.is_archived == False, CropGrowthRecord.update_date >= start_date, CropGrowthRecord.update_date <= end_date)\
        .order_by(CropGrowthRecord.update_date.desc(), CropGrowthRecord.id.desc()).limit(12)
    charts = []
    for record, name, code in db.execute(stmt):
        charts.append({"id": record.crop_id, "name": name, "crop_code": code,
            "growth_records": [{"id": record.id, "growth_percentage": record.growth_percentage, "update_date": record.update_date}]})
    return charts


def crop_dashboard(db, start_date, end_date):
    overview = crop_listing(db, limit=0)["overview"]
    charts = crop_chart(db, start_date, end_date)
    # Recommendation history is represented by one aggregate per crop name,
    # instead of downloading every crop's individual harvest history.
    performance = dict(db.execute(select(Crop.name, func.avg(CropYieldRecord.yield_per_hectare))
        .join(CropYieldRecord, CropYieldRecord.crop_id == Crop.id).where(Crop.is_archived == False, CropYieldRecord.yield_per_hectare > 0)
        .group_by(Crop.name)).all())
    context = [{"name": name, "yieldRecords": [{"yieldPerHectare": float(performance[name])}] if name in performance else []} for name in overview["current_names"]]
    return {**overview, "chart_records": charts, "recommendation_crops": context}


def crop_yields(db, offset=0, limit=25):
    stmt = select(CropYieldRecord, Crop.name, Crop.field, Crop.area_hectares).join(Crop, Crop.id == CropYieldRecord.crop_id).where(Crop.is_archived == False)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    records = db.execute(stmt.order_by(CropYieldRecord.harvest_date.desc(), CropYieldRecord.id.desc()).offset(offset).limit(limit))
    return {"items": [{**CropYieldResponse.model_validate(record).model_dump(mode="json"), "crop_name": name,
                       "field": field, "area": float(area)} for record, name, field, area in records],
            "total": total, "offset": offset, "limit": limit}


def livestock_overview(db):
    total = healthy = risk = due = births = 0
    types, pens, health = set(), set(), Counter()
    population, ages, feed = Counter(), Counter(), Counter()
    monthly_budget = 0.0
    rates = {"Pig": 30, "Chicken": 32, "Goat": 20, "Cattle": 18, "Duck": 28}
    today = farm_today()
    columns = (Livestock.animal_type, Livestock.pen_location, Livestock.quantity, Livestock.health_status,
        Livestock.healthy_quantity, Livestock.at_risk_quantity, Livestock.sick_quantity, Livestock.under_treatment_quantity,
        Livestock.vaccination_status, Livestock.date_of_birth, Livestock.daily_feed_kg)
    records = 0
    for kind, pen, quantity, status, h, a, s, t, vaccination, born, daily_feed in db.execute(select(*columns)
            .where(Livestock.is_archived == False).execution_options(yield_per=250)):
        records += 1; total += quantity; types.add(kind); pens.add(pen)
        counts = {"Healthy": int(h or 0), "At Risk": int(a or 0), "Sick": int(s or 0), "Under Treatment": int(t or 0)}
        if not sum(counts.values()) and status in counts: counts[status] = quantity
        health.update(counts)
        healthy += counts["Healthy"]
        risk += counts["At Risk"] + counts["Sick"] + counts["Under Treatment"]
        due += quantity if vaccination in {"Due", "Due Soon"} else 0
        births += quantity if born and 0 <= (today - born).days <= 90 else 0
        population[kind] += quantity
        months = (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day) if born else None
        group = "Unknown" if months is None else "Newborn" if months <= 3 else "Young" if months <= 12 else "Growing" if months <= 24 else "Mature"
        ages[group] += quantity
        planned_feed = float(daily_feed or 0) * quantity
        feed[kind] += planned_feed
        monthly_budget += planned_feed * 30 * rates.get(kind, 25)
    return {"records": records, "total": total, "healthy": healthy, "risk": risk, "vaccination_due": due,
        "births": births, "types": sorted(types), "pens": sorted(pens), "health_counts": dict(health),
        "analytics": {"population": dict(population), "age_groups": dict(ages), "planned_feed": dict(feed),
                      "estimated_monthly_budget": monthly_budget}}


def livestock_records(db, kind, offset=0, limit=25):
    if kind == "vaccinations":
        stmt = select(LivestockVaccinationRecord, Livestock.record_name, Livestock.animal_code).join(
            Livestock, Livestock.id == LivestockVaccinationRecord.livestock_id).where(Livestock.is_archived == False)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(LivestockVaccinationRecord.date_administered.desc(), LivestockVaccinationRecord.id.desc()).offset(offset).limit(limit))
        items = [{**LivestockVaccinationResponse.model_validate(row).model_dump(mode="json"), "record_name": name,
                  "animal_code": code} for row, name, code in rows]
    else:
        stmt = select(Livestock).where(Livestock.is_archived == False)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(Livestock.animal_code, Livestock.id).offset(offset).limit(limit)).all()
        items = [{"id": row.id, "livestock_id": row.id, "record_name": row.record_name, "animal_code": row.animal_code,
                  "feed_times": row.feed_times, "feed_type": row.feed_type, "daily_feed_kg": float(row.daily_feed_kg),
                  "quantity": row.quantity, "feeding_notes": row.feeding_notes} for row in rows]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def livestock_listing(db, *, offset=0, limit=50, search="", animal_type="All", health_status="All", pen="All"):
    stmt = select(Livestock).where(Livestock.is_archived == False)
    if search and search.strip():
        needle = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(*(column.ilike(needle, escape="\\") for column in (
            Livestock.animal_code, Livestock.record_name, Livestock.animal_type, Livestock.breed, Livestock.pen_location))))
    if animal_type != "All": stmt = stmt.where(Livestock.animal_type == animal_type)
    if pen != "All": stmt = stmt.where(Livestock.pen_location == pen)
    if health_status != "All":
        column = {"Healthy": Livestock.healthy_quantity, "At Risk": Livestock.at_risk_quantity,
            "Sick": Livestock.sick_quantity, "Under Treatment": Livestock.under_treatment_quantity}.get(health_status)
        stmt = stmt.where(or_(Livestock.health_status == health_status, column > 0)) if column is not None else stmt.where(Livestock.health_status == health_status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    parents = list(db.scalars(stmt.order_by(Livestock.id.desc()).offset(offset).limit(limit)).all())
    from app.services.monitoring_scheduler import annotate_monitoring
    from app.services.care_protocol_summary import attach_care_protocol_summaries
    parents = annotate_monitoring(db, attach_care_protocol_summaries(db, parents), "Livestock")
    return {"items": [LivestockResponse.model_validate(row).model_dump(mode="json") for row in parents],
        "total": total, "offset": offset, "limit": limit, "overview": livestock_overview(db)}


def livestock_chart(db, start_date, end_date):
    timestamp = func.coalesce(Livestock.updated_at, Livestock.created_at)
    stmt = select(Livestock).where(Livestock.is_archived == False,
        timestamp >= datetime.combine(start_date, time.min), timestamp < datetime.combine(end_date + timedelta(days=1), time.min))
    rows = db.scalars(stmt.order_by(timestamp.desc(), Livestock.id.desc()).limit(12)).all()
    return [LivestockResponse.model_validate(row).model_dump(mode="json") for row in rows]


def livestock_dashboard(db, start_date, end_date):
    return {**livestock_overview(db), "chart_records": livestock_chart(db, start_date, end_date)}
