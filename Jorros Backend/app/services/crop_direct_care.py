"""Bounded recurring work using the existing FarmActivity/submission/review flow."""
import json
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.core.farm_time import farm_today, farm_now_naive
from app.models import Crop, Employee, FarmActivity, TaskSubmission
from app.schemas.crop_planning import DirectCropSchedule
from app.services.workforce_intervals import interval_conflict, minutes
from app.services.db_concurrency import acquire_transaction_lock

HORIZON_DAYS = 28


def protected_task(task, submission_ids, effective_date):
    now = farm_now_naive()
    return (task.status != "Pending" or task.id in submission_ids or task.activity_date < effective_date
            or task.assignment_source not in {"automatic_default", "System", None}
            or (task.activity_date == now.date() and task.start_time is not None and task.start_time < now.time()))


def occurrences(schedule, today):
    start = max(schedule.start_date, today)
    stop = min(schedule.end_date or today + timedelta(days=HORIZON_DAYS - 1), today + timedelta(days=HORIZON_DAYS - 1))
    day = start
    while day <= stop:
        if (schedule.weekdays and day.weekday() in schedule.weekdays) or (not schedule.weekdays and (day - schedule.start_date).days % schedule.frequency_days == 0):
            yield day
        day += timedelta(days=1)


def preview_schedules(db, schedules, *, default_employee_id=None, crop_id=None, effective_date=None):
    today = max(farm_today(), effective_date or farm_today())
    if len({s.activity for s in schedules}) != len(schedules):
        raise HTTPException(400, "Keep one Watering and one Growth Observation schedule per planting.")
    lock_keys = {(s.employee_id or default_employee_id, day) for s in schedules if s.enabled
                 for day in occurrences(s, today) if s.employee_id or default_employee_id}
    for employee_id, day in sorted(lock_keys):
        acquire_transaction_lock(db, f"farm:employee-interval:{employee_id}:{day.isoformat()}")
    protected_ids = select(TaskSubmission.activity_id).distinct()
    saved = list(db.scalars(select(FarmActivity).where(FarmActivity.source_module == "Crop", FarmActivity.source_record_id == crop_id)).all()) if crop_id else []
    submissions = set(db.scalars(select(TaskSubmission.activity_id).where(TaskSubmission.activity_id.in_([x.id for x in saved]))).all()) if saved else set()
    protected_by_key = {x.source_key: x for x in saved if x.source_key and protected_task(x, submissions, today)}
    editable = [x.id for x in saved if x.source_type in {"crop_watering", "crop_growth_check"}
                and not protected_task(x, submissions, today)]
    proposed, rows = [], []
    for schedule in schedules:
        if not schedule.enabled:
            continue
        employee_id = schedule.employee_id or default_employee_id
        for day in occurrences(schedule, today):
            key = f"crop:direct:{crop_id}:{schedule.activity}:{day.isoformat()}"
            preserved = protected_by_key.get(key)
            if preserved:
                rows.append(dict(activity=schedule.activity, date=day, employee_id=preserved.assigned_employee_id,
                    start_time=preserved.start_time, end_time=preserved.end_time or preserved.start_time,
                    duration_minutes=schedule.duration_minutes, conflict=None, preserved=True))
                continue
            conflict = interval_conflict(db, employee_id, day, schedule.start_time, schedule.duration_minutes,
                exclude_ids=editable, proposed=proposed)
            end = (datetime.combine(day, schedule.start_time) + timedelta(minutes=schedule.duration_minutes)).time()
            rows.append(dict(activity=schedule.activity, date=day, employee_id=employee_id, start_time=schedule.start_time,
                end_time=end, duration_minutes=schedule.duration_minutes, conflict=conflict))
            proposed.append(dict(employee_id=employee_id, date=day, start=minutes(schedule.start_time), end=minutes(end)))
    return {"horizon_days": HORIZON_DAYS, "checked_from": today, "checked_through": today + timedelta(days=HORIZON_DAYS - 1),
            "occurrences": sorted(rows, key=lambda row: (row["date"], row["start_time"])),
            "conflicts": sum(bool(x["conflict"]) for x in rows),
            "note": "Later occurrences are revalidated as the 28-day scheduling window rolls forward."}


def sync_direct_care(db, crop, *, strict=False):
    from app.services.task_engine import _generate_activity_code
    acquire_transaction_lock(db, "automation:tasks")
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")
    schedules = [DirectCropSchedule.model_validate(x) for x in json.loads(crop.care_schedules_json or "[]")]
    active = not crop.is_archived and not crop.ended_at and crop.status not in {"Harvested", "Failed"}
    preview = preview_schedules(db, schedules if active else [], default_employee_id=crop.assigned_employee_id,
        crop_id=crop.id, effective_date=crop.schedule_effective_date)
    if strict and preview["conflicts"]:
        raise HTTPException(409, {"message": "Resolve schedule conflicts before saving; no selected times were moved.", "preview": jsonable_encoder(preview)})
    effective = max(farm_today(), crop.schedule_effective_date or farm_today())
    existing = list(db.scalars(select(FarmActivity).where(FarmActivity.source_module == "Crop", FarmActivity.source_record_id == crop.id)).all())
    by_key = {row.source_key: row for row in existing if row.source_key}
    history = set(db.scalars(select(TaskSubmission.activity_id).where(TaskSubmission.activity_id.in_([x.id for x in existing]))).all()) if existing else set()
    desired = set()
    for item in preview["occurrences"]:
        kind = "crop_watering" if item["activity"] == "watering" else "crop_growth_check"
        key = f"crop:direct:{crop.id}:{item['activity']}:{item['date'].isoformat()}"
        desired.add(key)
        task = by_key.get(key)
        if task is None:
            # A compatible, untouched legacy occurrence is converted in place.
            task = next((x for x in existing if x.is_automatic and not protected_task(x, history, effective) and x.activity_date == item["date"] and x.source_type == kind
                         and not str(x.source_key or "").startswith("crop:direct:")), None)
        if task is not None and protected_task(task, history, effective):
            continue
        if task is None:
            task = FarmActivity(activity_code=_generate_activity_code(db), source_module="Crop", source_type=kind,
                source_record_id=crop.id, source_detail_id=None, source_code=crop.crop_code, source_path="/crops",
                status="Pending", is_archived=False, is_automatic=True, priority="Medium", created_by_user_id=crop.created_by_user_id,
                assignment_source="automatic_default", assigned_by="Crop Direct Schedule")
            db.add(task)
        task.source_key = key
        task.name = f"{'Water' if item['activity'] == 'watering' else 'Growth Observation'} {crop.name}"
        task.category = "Crop Watering" if item["activity"] == "watering" else "Farm Inspection"
        task.location, task.related_to = crop.field, f"{crop.crop_code} — {crop.name}"
        task.description = "Use My Tasks to submit actual work and evidence for authorized review."
        task.activity_date, task.start_time, task.end_time = item["date"], item["start_time"], item["end_time"]
        task.duration = f"{item['duration_minutes']} minutes"
        employee = db.get(Employee, item["employee_id"]) if item["employee_id"] else None
        task.default_employee_id = item["employee_id"]
        task.assigned_employee_id = None if item["conflict"] else item["employee_id"]
        task.assigned_to = employee.full_name if employee and not item["conflict"] else "Needs assignment"
        task.requires_review = task.requires_evidence = True
        task.needs_reassignment, task.problem_report = bool(item["conflict"]), item["conflict"]
        db.flush()
    for task in existing:
        if protected_task(task, history, effective):
            continue
        if task.source_type in {"crop_watering", "crop_growth_check"} and task.source_key not in desired:
            task.status, task.problem_report = "Resolved", "Direct crop schedule changed; preserved in history."
        elif task.source_type == "care_template_step":
            task.needs_reassignment = True
            task.problem_report = "Legacy crop protocol work retained; review this unmapped activity before assignment."
    db.flush()
    return preview
