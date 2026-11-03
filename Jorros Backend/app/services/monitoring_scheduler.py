"""Occurrence-based monitoring; entered intervals are operational settings."""
from datetime import timedelta, time
from collections import defaultdict

from sqlalchemy import select, func

from app.models import Crop, CropGrowthRecord, Livestock, LivestockGrowthRecord, FarmActivity
from app.models.alert import AlertSettings
from app.core.farm_time import farm_now_naive


def sync_monitoring_tasks(db, *, today, active_keys, counters):
    from app.services.task_engine import _upsert_automatic_task
    config = db.scalar(select(AlertSettings).order_by(AlertSettings.id).limit(1))
    crop_interval = int(config.crop_growth_check_frequency or 7) if config else 7
    crop_enabled = bool(config.crop_growth_check) if config else True
    desired = set()
    resources = {}
    recorded_dates = {}
    for module, model, history, date_column in [
        ("Crop", Crop, CropGrowthRecord, CropGrowthRecord.update_date),
        ("Livestock", Livestock, LivestockGrowthRecord, LivestockGrowthRecord.measurement_date),
    ]:
        module_rows = list(db.scalars(select(model)).all())
        parent_column = history.crop_id if module == "Crop" else history.livestock_id
        dates_by_id = defaultdict(set)
        if module_rows:
            for resource_id, recorded_date in db.execute(select(parent_column, date_column).where(parent_column.in_([row.id for row in module_rows]))):
                dates_by_id[resource_id].add(recorded_date)
        for resource in module_rows:
            resources[(module, resource.id)] = resource
            active = not resource.is_archived and (
                resource.status not in {"Harvested", "Failed"} if module == "Crop"
                else resource.lifecycle_status == "Active" and resource.quantity > 0)
            if not active or not resource.monitoring_enabled or (module == "Crop" and not crop_enabled):
                continue
            interval = resource.monitoring_frequency_days or (crop_interval if module == "Crop" else None)
            if not interval:
                continue
            base = resource.planting_date if module == "Crop" else resource.date_acquired
            dates = dates_by_id[resource.id]
            recorded_dates[(module, resource.id)] = dates
            anchor = resource.monitoring_start_date or ((max(dates) if dates else base) + timedelta(days=interval))
            end = min(resource.monitoring_end_date or today + timedelta(days=7), today + timedelta(days=7))
            # Keep the currently due occurrence plus the next seven days. Work
            # created by earlier passes remains overdue until a human resolves it.
            offset = max(0, (today - anchor).days // interval)
            due = anchor + timedelta(days=offset * interval)
            while due <= end:
                if due not in dates:
                    source_type = "crop_growth_check" if module == "Crop" else "livestock_growth_check"
                    key = f"{module.lower()}:growth-check:{resource.id}:{due.isoformat()}"
                    label = resource.name if module == "Crop" else resource.record_name
                    location = resource.field if module == "Crop" else resource.pen_location
                    task, result = _upsert_automatic_task(
                        db, source_key=key, source_module=module, source_type=source_type,
                        source_record_id=resource.id, source_detail_id=None,
                        source_code=resource.crop_code if module == "Crop" else resource.animal_code,
                        source_path="/crops" if module == "Crop" else "/livestock",
                        name=f"{'Growth Check' if module == 'Crop' else 'Weight Monitoring'} — {label}",
                        category="Farm Inspection", related_to=f"{label} — {location}", location=location,
                        description="Submit dated monitoring observations and photo evidence in My Tasks. An authorized reviewer must approve them before the linked record changes.",
                        activity_date=due, start_time=time(8), assigned_to="Farm Staff", priority="Medium")
                    if task.status == "Pending":
                        task.requires_review = True
                        task.requires_evidence = True
                    desired.add(key)
                    active_keys.add(key)
                    counters[result] += 1
                due += timedelta(days=interval)
    # Preserve missed, started, returned, submitted, completed, and manually
    # resolved work. Only obsolete future Pending occurrences are reconciled.
    for task in db.scalars(select(FarmActivity).where(
        FarmActivity.source_type.in_(["crop_growth_check", "livestock_growth_check"]),
        FarmActivity.is_automatic == True, FarmActivity.status == "Pending",
        FarmActivity.is_archived == False,
    )).all():
        resource = resources.get((task.source_module, task.source_record_id))
        closed = resource is None or resource.is_archived or (
            resource.status in {"Harvested", "Failed"} if task.source_module == "Crop"
            else resource.lifecycle_status != "Active" or resource.quantity <= 0)
        already_inspected = task.activity_date in recorded_dates.get((task.source_module, task.source_record_id), set())
        if already_inspected or (task.source_key not in desired and (closed or task.activity_date > today)):
            task.status = "Resolved"
            task.problem_report = "Monitoring schedule changed or monitoring stopped."
            task.completed_at = None
            task.updated_at = farm_now_naive()
            counters["completed"] += 1


def annotate_monitoring(db, rows, module):
    """Batch list metadata so table rows do not each query their task history."""
    if not rows:
        return rows
    from app.core.farm_time import farm_today
    today = farm_today()
    ids = [row.id for row in rows]
    history = CropGrowthRecord if module == "Crop" else LivestockGrowthRecord
    parent = history.crop_id if module == "Crop" else history.livestock_id
    date_column = history.update_date if module == "Crop" else history.measurement_date
    last_dates = dict(db.execute(select(parent, func.max(date_column)).where(parent.in_(ids)).group_by(parent)).all())
    tasks = list(db.scalars(select(FarmActivity).where(
        FarmActivity.source_module == module, FarmActivity.source_record_id.in_(ids),
        FarmActivity.source_type == ("crop_growth_check" if module == "Crop" else "livestock_growth_check"),
        FarmActivity.is_archived == False,
        FarmActivity.status.in_(["Pending", "In Progress", "Returned", "Submitted for Review"]),
    )).all())
    config = db.scalar(select(AlertSettings).order_by(AlertSettings.id).limit(1)) if module == "Crop" else None
    for row in rows:
        interval = row.monitoring_frequency_days or ((config.crop_growth_check_frequency if config else 7) if module == "Crop" else None)
        enabled = bool(row.monitoring_enabled and (config is None or config.crop_growth_check))
        active = not row.is_archived and (row.status not in {"Harvested", "Failed"} if module == "Crop" else row.lifecycle_status == "Active" and row.quantity > 0)
        own = [task for task in tasks if task.source_record_id == row.id]
        pending = sum(task.status == "Submitted for Review" for task in own)
        overdue = sum(task.activity_date < today and task.status != "Submitted for Review" for task in own)
        next_date = min((task.activity_date for task in own), default=None)
        state = "Awaiting approval" if pending else "Overdue" if overdue else "Due today" if next_date == today else "Scheduled" if next_date else "Monitoring complete"
        if not enabled: state = "Not scheduled"
        elif not active: state = "Stopped"
        elif not row.assigned_employee_id and not pending: state = "Needs assignment"
        if not next_date and enabled and active and interval:
            base = row.planting_date if module == "Crop" else row.date_acquired
            anchor = row.monitoring_start_date or (last_dates.get(row.id, base) + timedelta(days=interval))
            index = max(0, (today - anchor).days // interval)
            next_date = anchor + timedelta(days=index * interval)
            if next_date < today: next_date += timedelta(days=interval)
            if row.monitoring_end_date and next_date > row.monitoring_end_date: next_date = None
            elif state == "Monitoring complete": state = "Scheduled"
        row.monitoring_summary = {"state": state, "last_date": str(last_dates[row.id]) if row.id in last_dates else None,
                                  "next_date": str(next_date) if next_date else None, "interval_days": interval,
                                  "pending_review_count": pending, "overdue_count": overdue}
    return rows
