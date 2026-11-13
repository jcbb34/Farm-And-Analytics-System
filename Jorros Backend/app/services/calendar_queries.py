"""Calendar summaries and small detail pages share the caller's visible query."""
from sqlalchemy import case, func, or_, select

from app.models import FarmActivity


def _within(statement, start, end):
    return statement.where(FarmActivity.activity_date >= start, FarmActivity.activity_date <= end)


def calendar_event(row):
    return {"id": row["id"], "name": row["name"], "category": row["category"],
        "activity_date": row["activity_date"], "start_time": row["start_time"], "end_time": row["end_time"],
        "location": row["location"], "description": row.get("description", ""),
        "status": row["status"], "priority": row["priority"]}


def calendar_summary(db, visible, start, end):
    base = _within(visible, start, end)
    grouped = db.execute(base.with_only_columns(FarmActivity.activity_date, func.count().label("total"),
        func.sum(case((FarmActivity.category == "Harvesting", 1), else_=0)).label("harvests"),
        func.sum(case((or_(FarmActivity.category.like("%Livestock%"), FarmActivity.category == "Vaccination"), 1), else_=0)).label("livestock"),
        func.sum(case((FarmActivity.status == "Completed", 1), else_=0)).label("completed"))
        .group_by(FarmActivity.activity_date).order_by(FarmActivity.activity_date)).mappings().all()
    columns = [getattr(FarmActivity, name) for name in ("id", "name", "category", "activity_date", "start_time", "end_time", "location", "status", "priority")]
    ranked = base.with_only_columns(*columns, func.row_number().over(partition_by=FarmActivity.activity_date,
        order_by=(FarmActivity.start_time, FarmActivity.id)).label("position")).subquery()
    previews = db.execute(select(ranked).where(ranked.c.position <= 4)
        .order_by(ranked.c.activity_date, ranked.c.start_time, ranked.c.id)).mappings()
    by_date = {}
    for row in previews: by_date.setdefault(row["activity_date"], []).append(calendar_event(row))
    days = [{"date": row["activity_date"], "total": row["total"], "items": by_date.get(row["activity_date"], [])} for row in grouped]
    totals = {name: sum(int(row[name] or 0) for row in grouped) for name in ("total", "harvests", "livestock", "completed")}
    return {"days": days, "summary": totals, "date_from": start, "date_to": end}


def calendar_events(db, visible, start, end, offset=0, limit=25):
    base = _within(visible, start, end)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    columns = [getattr(FarmActivity, name) for name in ("id", "name", "category", "activity_date", "start_time", "end_time", "location", "description", "status", "priority")]
    records = db.execute(base.with_only_columns(*columns).order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
        .offset(offset).limit(limit)).mappings()
    return {"items": [calendar_event(row) for row in records], "total": total, "offset": offset, "limit": limit}
