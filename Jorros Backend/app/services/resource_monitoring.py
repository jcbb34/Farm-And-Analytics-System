"""Validated observations posted only by the existing authorized review flow.

Functions flush into the caller's transaction; they never commit independently.
"""
from fastapi import HTTPException
from sqlalchemy import select

from app.core.farm_time import farm_today, farm_now_naive
from app.models import Crop, CropGrowthRecord, Livestock, LivestockGrowthRecord, User
from app.schemas.monitoring import MonitoringObservation
from app.services.crop_growth import calculate_crop_progress, stage_for_progress, status_for_progress, validate_survival_counts, GROWTH_STAGES
from app.services.db_concurrency import acquire_transaction_lock

MONITORING_TYPES = {"crop_growth_check": "Crop", "livestock_growth_check": "Livestock"}


def monitoring_context(db, task):
    module = MONITORING_TYPES.get(task.source_type)
    if not module or module != task.source_module:
        return None
    resource = db.get(Crop if module == "Crop" else Livestock, task.source_record_id)
    if resource is None:
        return None
    from app.schemas.livestock import ALLOWED_GROWTH_STATUSES
    return {
        "resource_type": module,
        "quantity": resource.quantity_planted if module == "Crop" else resource.quantity,
        "earliest_date": str(max(task.activity_date, resource.planting_date if module == "Crop" else resource.date_acquired)),
        "latest_date": str(min(farm_today(), resource.monitoring_end_date or farm_today())),
        "stage_choices": list(GROWTH_STAGES[:-2]) if module == "Crop" else sorted(ALLOWED_GROWTH_STATUSES),
        "current_stage": resource.observed_growth_stage if module == "Crop" else resource.growth_status,
    }


def validate_schedule(resource, module):
    base = resource.planting_date if module == "Crop" else resource.date_acquired
    start, end = resource.monitoring_start_date, resource.monitoring_end_date
    if start and start < base:
        raise HTTPException(400, "Monitoring cannot start before planting/acquisition.")
    if end and end < (start or base):
        raise HTTPException(400, "Monitoring end date cannot precede its start.")
    if resource.monitoring_enabled and module == "Livestock":
        if not start or not resource.monitoring_frequency_days:
            raise HTTPException(400, "Choose a monitoring start date and frequency for livestock.")


def validate_task_observation(db, task, value, *, reviewing=False):
    module = MONITORING_TYPES.get(task.source_type)
    if not module:
        if value is not None:
            raise HTTPException(400, "Observations can only be submitted for resource monitoring tasks.")
        return None
    if value is None:
        raise HTTPException(400, "Enter the structured monitoring observation before submitting this task.")
    observation = value if isinstance(value, MonitoringObservation) else MonitoringObservation.model_validate(value)
    if observation.resource_type != module or task.source_module != module:
        raise HTTPException(400, "The observation does not match the task's linked resource.")
    resource = db.get(Crop if module == "Crop" else Livestock, task.source_record_id)
    if resource is None or resource.is_archived:
        raise HTTPException(400, "The linked monitoring record is unavailable or archived.")
    base = resource.planting_date if module == "Crop" else resource.date_acquired
    if not base <= observation.observation_date <= farm_today():
        raise HTTPException(400, "Observation date must be between planting/acquisition and today in farm time.")
    if observation.observation_date < task.activity_date:
        raise HTTPException(400, "An observation cannot precede this monitoring task's scheduled date.")
    if not reviewing and resource.monitoring_end_date and observation.observation_date > resource.monitoring_end_date:
        raise HTTPException(400, "Observation date is outside the configured monitoring period.")
    if module == "Crop":
        try:
            validate_survival_counts(resource.quantity_planted, observation.current_surviving)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    else:
        if observation.animals_measured > resource.quantity:
            raise HTTPException(400, "Animals measured cannot exceed the livestock group's current quantity.")
        from app.schemas.livestock import ALLOWED_GROWTH_STATUSES
        if observation.observed_stage and observation.observed_stage not in ALLOWED_GROWTH_STATUSES:
            raise HTTPException(400, "Invalid proposed livestock stage.")
    return observation


def record_crop_observation(db, crop, *, observation_date, surviving, observed_stage=None,
                            notes=None, recorder_id=None, reviewer_id=None, submission_id=None, task_id=None,
                            confirm_ready=False, feedback=None):
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")
    db.refresh(crop)
    if submission_id:
        posted = db.scalar(select(CropGrowthRecord).where(CropGrowthRecord.task_submission_id == submission_id))
        if posted:
            return posted
    if db.scalar(select(CropGrowthRecord.id).where(CropGrowthRecord.crop_id == crop.id, CropGrowthRecord.update_date == observation_date)):
        raise HTTPException(409, "This crop already has an inspection on that date. Review its existing history.")
    if not crop.planting_date <= observation_date <= farm_today():
        raise HTTPException(400, "Inspection date must be between planting and today.")
    if observed_stage and observed_stage not in GROWTH_STAGES[:-2]:
        raise HTTPException(400, "Invalid observed crop stage.")
    try:
        validate_survival_counts(crop.quantity_planted, surviving)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    latest = db.scalar(select(CropGrowthRecord).where(CropGrowthRecord.crop_id == crop.id)
                       .order_by(CropGrowthRecord.update_date.desc(), CropGrowthRecord.id.desc()).limit(1))
    is_latest = latest is None or observation_date >= latest.update_date
    active = crop.status not in {"Harvested", "Failed"}
    if confirm_ready and observed_stage != "Harvest Ready":
        raise HTTPException(400, "Harvest readiness confirmation requires the Harvest Ready observed stage.")
    if observed_stage == "Harvest Ready" and not confirm_ready:
        raise HTTPException(400, "Explicitly confirm physical harvest readiness before approving this stage.")
    if is_latest and active and crop.confirmed_ready_at and observed_stage and observed_stage != "Harvest Ready" and not str(feedback or notes or "").strip():
        raise HTTPException(400, "Enter a reason for changing a previously confirmed harvest-ready stage.")
    progress = calculate_crop_progress(crop.planting_date, crop.estimated_harvest, today=observation_date)
    record = CropGrowthRecord(crop_id=crop.id, update_date=observation_date,
                              growth_percentage=progress, growth_stage=stage_for_progress(progress),
                              observed_stage=observed_stage, current_surviving=surviving,
                              status=("Ready for Harvest" if confirm_ready else "Planted" if observed_stage == "Seeded" else "Growing") if observed_stage else status_for_progress(progress), notes=notes,
                              recorded_by_user_id=recorder_id, approved_by_user_id=reviewer_id,
                              task_submission_id=submission_id, related_task_id=task_id)
    db.add(record)
    count_date = crop.survival_count_date or (latest.update_date if latest else None)
    if active and (count_date is None or observation_date >= count_date):
        crop.current_surviving = surviving
        crop.survival_count_date = observation_date
    if is_latest and active:
        crop.last_observation_date = observation_date
        if observed_stage:
            crop.observed_growth_stage = observed_stage
            if crop.status != "Harvesting":
                if confirm_ready:
                    from app.services.crop_harvest_service import confirm_crop_ready
                    actor = db.get(User, reviewer_id)
                    confirm_crop_ready(db, crop=crop, actor=actor)
                else:
                    crop.confirmed_ready_at = None
                    crop.confirmed_ready_by_user_id = None
                    crop.growth_stage = observed_stage
                    crop.status = "Planted" if observed_stage == "Seeded" else "Growing"
                    crop.current_growth = calculate_crop_progress(crop.planting_date, crop.estimated_harvest)
        crop.updated_at = farm_now_naive()
    db.flush()
    return record


def post_approved_observation(db, task, submission, review, reviewer):
    if not MONITORING_TYPES.get(task.source_type):
        return
    observation = validate_task_observation(db, task, submission.monitoring, reviewing=True)
    if observation.resource_type == "Crop":
        if review.confirmed_growth_stage and review.confirmed_growth_stage != observation.observed_stage and not str(review.feedback or "").strip():
            raise HTTPException(400, "Explain why the confirmed crop stage differs from the employee observation.")
        crop = db.get(Crop, task.source_record_id)
        stage = review.confirmed_growth_stage or observation.observed_stage
        return record_crop_observation(db, crop, observation_date=observation.observation_date,
                                      surviving=observation.current_surviving, observed_stage=stage,
                                      notes=submission.worker_notes, recorder_id=submission.recorded_by_user_id,
                                      reviewer_id=reviewer.id, submission_id=submission.id, task_id=task.id,
                                      confirm_ready=review.confirm_harvest_ready, feedback=review.feedback)
    from app.routers.livestock import record_growth_measurement, lock_livestock_or_404
    from app.models.livestock import LivestockGrowthStageOverrideAudit
    from app.schemas.livestock import ALLOWED_GROWTH_STATUSES
    from app.core.dependencies import has_permission
    animal = db.get(Livestock, task.source_record_id)
    acquire_transaction_lock(db, f"livestock-monitoring:{animal.id}")
    animal = lock_livestock_or_404(animal.id, db)
    db.refresh(animal)
    posted = db.scalar(select(LivestockGrowthRecord).where(LivestockGrowthRecord.task_submission_id == submission.id))
    if posted:
        return posted
    stage = review.confirmed_growth_stage
    if stage and (stage not in ALLOWED_GROWTH_STATUSES or not str(review.feedback or "").strip()):
        raise HTTPException(400, "A valid confirmed stage and reviewer reason are required for a livestock stage override.")
    if stage and not (has_permission(reviewer, "workforce:manage") or has_permission(reviewer, "*")):
        raise HTTPException(403, "Workforce management permission is required to confirm a growth-stage override.")
    latest = db.scalar(select(LivestockGrowthRecord).where(LivestockGrowthRecord.livestock_id == animal.id)
                       .order_by(LivestockGrowthRecord.measurement_date.desc()).limit(1))
    if stage and latest and observation.observation_date < latest.measurement_date:
        raise HTTPException(400, "A backdated measurement cannot override the current livestock stage.")
    record = record_growth_measurement(db, animal, observation.observation_date, observation.average_weight_kg,
                                      submission.recorded_by_user_id, submission.worker_notes,
                                      animals_measured=observation.animals_measured,
                                      total_measured_weight_kg=observation.total_measured_weight_kg,
                                      min_weight_kg=observation.min_weight_kg, max_weight_kg=observation.max_weight_kg,
                                      measurement_basis="Sample" if observation.animals_measured < animal.quantity else "Full Batch" if animal.quantity > 1 else "Individual")
    record.task_submission_id, record.related_task_id, record.approved_by_user_id = submission.id, task.id, reviewer.id
    if stage and stage != animal.growth_status:
        db.add(LivestockGrowthStageOverrideAudit(livestock_id=animal.id, previous_stage=animal.growth_status,
                                                suggested_stage=record.expected_stage, override_stage=stage,
                                                reason=review.feedback.strip(), overridden_by_user_id=reviewer.id))
        animal.growth_status = stage
    db.flush()
    return record
