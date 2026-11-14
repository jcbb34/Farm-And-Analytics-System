"""Planting registration extensions; caller owns the encompassing transaction."""
import hashlib
import json
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, desc

from app.core.farm_time import farm_today, farm_now_naive
from app.models import Crop, CropSpacingProfile, CropPositionEvent, CropFootprint, FarmActivity, TaskSubmission
from app.services.crop_land import allocate, lock_land
from app.services.db_concurrency import acquire_transaction_lock


def built_in_profiles():
    return json.loads((Path(__file__).resolve().parents[2] / "reference_data/crop_spacing_profiles.json").read_text(encoding="utf-8"))


def seed_profiles(db):
    """Explicit migration/test setup only; ordinary reads never seed farm records."""
    for raw in built_in_profiles()["profiles"]:
        if db.scalar(select(CropSpacingProfile.id).where(CropSpacingProfile.profile_key == raw["profile_key"], CropSpacingProfile.version == 1)):
            continue
        data = {k: v for k, v in raw.items() if k not in {"harvest_parts", "checked_on", "additional_source_urls"}}
        data["harvest_parts_json"] = json.dumps(raw["harvest_parts"])
        data["source_urls_json"] = json.dumps(raw.get("additional_source_urls", []))
        db.add(CropSpacingProfile(**data))
    db.flush()


def profile_dict(profile):
    data = {col.name: getattr(profile, col.name) for col in profile.__table__.columns}
    data["harvest_parts"] = json.loads(data.pop("harvest_parts_json"))
    data["additional_source_urls"] = json.loads(data.pop("source_urls_json"))
    data["spacing_units"] = "metres"
    return data


def capacity(area_ha, snapshot):
    if not snapshot:
        return None
    if snapshot.get("layout") not in {"square", "rectangular"}:
        raise HTTPException(400, "Capacity currently supports square and rectangular layouts only.")
    unit_area = Decimal(str(snapshot["row_spacing_m"])) * Decimal(str(snapshot["plant_spacing_m"]))
    if unit_area <= 0:
        raise HTTPException(400, "Plant spacing must be positive.")
    return int((Decimal(str(area_ha)) * 10000 / unit_area).to_integral_value(rounding=ROUND_FLOOR))


def spacing_snapshot(db, payload, actor):
    snapshot = None
    # Defense in depth: a valid variety automatically receives its *current*
    # verified default even if the user selected the variety before the UI
    # finished fetching /references or a client omitted the profile ID.
    # Unknown/custom choices never inherit an unrelated crop's spacing.
    profile = None
    if payload.spacing_profile_id:
        profile = db.get(CropSpacingProfile, payload.spacing_profile_id)
    elif payload.crop_reference and payload.variety_reference:
        profile = db.scalar(select(CropSpacingProfile).where(
            CropSpacingProfile.crop_key == payload.crop_reference,
            CropSpacingProfile.variety_key == payload.variety_reference,
            CropSpacingProfile.is_default.is_(True),
        ).order_by(desc(CropSpacingProfile.version), desc(CropSpacingProfile.id)).limit(1))
    if payload.spacing_profile_id or profile:
        if not profile:
            raise HTTPException(404, "Spacing profile not found.")
        if payload.crop_reference != profile.crop_key or payload.variety_reference != profile.variety_key:
            raise HTTPException(400, "The spacing profile does not match the crop and variety.")
        snapshot = profile_dict(profile)
        if profile.profile_key == "saba-under-coconut" and not payload.shared_footprint_crop_id:
            raise HTTPException(400, "The Saba under Coconut profile needs an explicitly shared coconut footprint.")
        if profile.profile_key == "saba-under-coconut":
            parent = db.get(Crop, payload.shared_footprint_crop_id)
            if parent is None or parent.crop_reference != "coconut":
                raise HTTPException(400, "The selected shared planting must be Coconut.")
    if payload.spacing_override:
        from app.core.dependencies import has_permission
        if not has_permission(actor, "crops:full-edit"):
            raise HTTPException(403, "Admin crop permission is required to adjust spacing.")
        adjustment = payload.spacing_override.model_dump(mode="json")
        snapshot = {**(snapshot or {}), **adjustment, "count_unit": (snapshot or {}).get("count_unit", "plant"),
                    "harvest_parts": (snapshot or {}).get("harvest_parts", ["crop output"]),
                    "harvest_behavior": (snapshot or {}).get("harvest_behavior", "custom"),
                    "version": (snapshot or {}).get("version", 1), "adjusted_by_user_id": actor.id}
    return snapshot


def initialize_registration(db, crop, payload, actor):
    crop.registration_kind = payload.registration_kind
    crop.crop_reference, crop.variety_reference = payload.crop_reference, payload.variety_reference
    crop.planting_date_precision = payload.planting_date_precision
    crop.initial_surviving = crop.current_surviving
    if payload.registration_kind == "legacy":
        return
    validate_references(db, crop, actor)
    if payload.registration_kind == "new" and (crop.planting_date is None or crop.quantity_planted is None):
        raise HTTPException(400, "A new planting needs an actual planting date and confirmed planted quantity.")
    if payload.registration_kind == "new" and crop.planting_date and crop.planting_date < farm_today():
        raise HTTPException(400, "A new planting must start today or later. Use Existing for an already growing crop.")
    if payload.registration_kind == "existing" and crop.planting_date is None and payload.planting_date_precision != "unknown":
        raise HTTPException(400, "Mark an unrecorded planting date explicitly as Unknown.")
    if payload.registration_kind == "existing" and crop.planting_date and crop.planting_date > farm_today():
        raise HTTPException(400, "An already growing planting cannot have a future planting date.")
    if payload.planting_date_precision == "unknown" and crop.planting_date is not None:
        raise HTTPException(400, "An unknown planting date must remain empty.")
    if not payload.section_id:
        raise HTTPException(409, "Select a measured field and section, or configure Land Setup first.")
    if any(s.enabled and s.start_date < farm_today() for s in payload.care_schedules):
        raise HTTPException(400, "Choose a current or future care start date when registering this planting.")
    if payload.care_template_id:
        raise HTTPException(400, "Use direct Watering and Growth Observation schedules for this planting.")
    snapshot = spacing_snapshot(db, payload, actor)
    crop.spacing_snapshot_json = json.dumps(snapshot, default=str) if snapshot else None
    crop.estimated_capacity = capacity(crop.area_hectares, snapshot)
    allocate(db, crop, section_id=payload.section_id, shared_crop_id=payload.shared_footprint_crop_id, shared_reason=payload.shared_footprint_reason)
    duplicate_query = select(Crop).where(Crop.section_id == crop.section_id,
        Crop.crop_reference == crop.crop_reference, Crop.variety_reference == crop.variety_reference,
        Crop.area_cleared_at.is_(None), Crop.is_archived == False)
    if not crop.crop_reference or not crop.variety_reference:
        duplicate_query = duplicate_query.where(Crop.name == crop.name, Crop.variety == crop.variety)
    matches = list(db.scalars(duplicate_query).all())
    if matches and not payload.duplicate_acknowledged:
        raise HTTPException(409, {"message": "A similar planting is already saved in this section. Confirm that this is a distinct physical planting.", "possible_duplicates": [{"id": x.id, "code": x.crop_code} for x in matches]})
    crop.care_schedules_json = json.dumps([x.model_dump(mode="json") for x in payload.care_schedules])
    crop.schedule_effective_date = payload.schedule_effective_date or farm_today()
    crop.monitoring_enabled = False  # Direct observation schedule owns new occurrences.
    crop.watering_schedule = None
    crop.care_template_id = None
    crop.status = payload.initial_status if payload.registration_kind == "existing" else "Planted"
    if payload.registration_kind == "existing" and payload.initial_status in {"Ready for Harvest", "Harvesting"}:
        from app.core.dependencies import has_permission
        if not payload.confirm_ready or not has_permission(actor, "crops:update"):
            raise HTTPException(400, "Physically confirm the existing planting's harvest readiness.")
        crop.confirmed_ready_at, crop.confirmed_ready_by_user_id = farm_now_naive(), actor.id
    if crop.planting_date is None or crop.estimated_harvest is None:
        crop.current_growth = None
        crop.growth_stage = crop.observed_growth_stage or "Not estimated"


def position_summary(db, crop):
    events = list(db.scalars(select(CropPositionEvent).where(CropPositionEvent.crop_id == crop.id).order_by(CropPositionEvent.event_date, CropPositionEvent.id)).all())
    counts = {}
    for event in events:
        counts[event.event_type] = counts.get(event.event_type, 0) + event.quantity
    baseline_loss = max(0, crop.quantity_planted - crop.initial_surviving) if crop.quantity_planted is not None and crop.initial_surviving is not None else None
    losses = (baseline_loss or 0) + counts.get("mortality", 0)
    departed = losses + counts.get("harvested_out", 0) + counts.get("removed", 0)
    replacements = counts.get("replacement", 0)
    blocked = counts.get("blocked", 0) - counts.get("unblocked", 0)
    potential = max(0, departed - replacements)
    verified = max(0, counts.get("verified_cleared", 0) - replacements)
    return {"mortality": counts.get("mortality", 0), "previous_unclassified_losses": baseline_loss, "harvested_out": counts.get("harvested_out", 0), "removed": counts.get("removed", 0),
            "replacements": replacements, "potential_replacement_positions": potential,
            "verified_cleared_positions": max(0, min(verified, potential - blocked)), "blocked_positions": blocked,
            "count_unit": json.loads(crop.spacing_snapshot_json or "{}").get("count_unit", "plant"),
            "events": [{"id": x.id, "event_type": x.event_type, "event_date": x.event_date, "quantity": x.quantity, "notes": x.notes} for x in events]}


def record_position_event(db, crop, payload, actor, key):
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")
    if not db.is_modified(crop, include_collections=False):
        db.refresh(crop)
    fingerprint = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    if not key or len(key) > 100:
        raise HTTPException(400, "A stable Idempotency-Key is required for position events.")
    event_key = f"{crop.id}:{key}"
    existing = db.scalar(select(CropPositionEvent).where(CropPositionEvent.event_key == event_key))
    if existing:
        if existing.request_hash != fingerprint or existing.actor_user_id != actor.id:
            raise HTTPException(409, "This key was used for a different position event.")
        return {**position_summary(db, crop), "idempotent_replay": True}
    if payload.event_date > farm_today() or (crop.planting_date and payload.event_date < crop.planting_date):
        raise HTTPException(400, "Choose the actual event date between planting (when known) and today.")
    last_date = db.scalar(select(CropPositionEvent.event_date).where(CropPositionEvent.crop_id == crop.id)
                          .order_by(CropPositionEvent.event_date.desc()).limit(1))
    if last_date and payload.event_date < last_date:
        raise HTTPException(409, "This date precedes later recorded position changes. Review that history before entering a backdated replacement or loss.")
    if crop.area_cleared_at:
        raise HTTPException(409, "This planting was cleared. Register a new planting for the next season.")
    state = position_summary(db, crop)
    kind, count = payload.event_type, payload.quantity
    if kind in {"mortality", "harvested_out", "removed"}:
        if crop.current_surviving is None or count > crop.current_surviving:
            raise HTTPException(400, "Record a known surviving count before removing these plants.")
        crop.current_surviving -= count
    elif kind == "verified_cleared":
        if count > state["potential_replacement_positions"] - state["verified_cleared_positions"] - state["blocked_positions"]:
            raise HTTPException(400, "Verify only existing vacant positions that have been checked and cleared.")
    elif kind == "replacement":
        if count > state["verified_cleared_positions"]:
            raise HTTPException(400, "Check and confirm cleared replacement positions first.")
        if crop.current_surviving is None:
            raise HTTPException(400, "Record the current surviving count before adding replacements.")
        crop.current_surviving += count
    elif kind == "blocked" and count > state["potential_replacement_positions"] - state["blocked_positions"]:
        raise HTTPException(400, "Blocked positions cannot exceed vacant positions.")
    elif kind == "unblocked" and count > state["blocked_positions"]:
        raise HTTPException(400, "Unblocked positions exceed the recorded blocked positions.")
    db.add(CropPositionEvent(crop_id=crop.id, event_type=kind, event_date=payload.event_date,
        quantity=count, notes=payload.notes, event_key=event_key, request_hash=fingerprint, actor_user_id=actor.id))
    db.flush()
    return position_summary(db, crop)


def end_planting(db, crop, actor, *, reason, cleared):
    lock_land(db)
    acquire_transaction_lock(db, f"crop-harvest:{crop.id}")
    crop.ended_at = crop.ended_at or farm_now_naive()
    crop.status = "Harvested"
    if cleared:
        if crop.current_surviving and crop.area_cleared_at is None:
            from app.schemas.crop_planning import PositionEventInput
            record_position_event(db, crop, PositionEventInput(event_type="removed", event_date=farm_today(),
                quantity=crop.current_surviving, notes=reason), actor, "area-clearing")
        crop.area_cleared_at, crop.area_cleared_by_user_id = farm_now_naive(), actor.id
        crop.current_surviving = 0
        if crop.footprint_id:
            db.flush()
            others = db.scalar(select(Crop.id).where(Crop.footprint_id == crop.footprint_id, Crop.area_cleared_at.is_(None)).limit(1))
            if others is None:
                db.get(CropFootprint, crop.footprint_id).released_at = farm_now_naive()
    protected = select(TaskSubmission.activity_id).distinct()
    for task in db.scalars(select(FarmActivity).where(FarmActivity.source_module == "Crop", FarmActivity.source_record_id == crop.id,
            FarmActivity.status == "Pending", FarmActivity.activity_date > farm_today(), FarmActivity.id.not_in(protected))).all():
        task.status, task.problem_report = "Resolved", "Planting ended: " + reason
    from app.services.crop_audit import record_crop_change
    record_crop_change(db, crop, actor, action="Confirmed planting area cleared" if cleared else "Ended planting", before={"reason": reason})


PLANNING_INPUTS = {"registration_kind", "crop_reference", "variety_reference", "section_id", "spacing_profile_id",
    "spacing_override", "shared_footprint_crop_id", "shared_footprint_reason", "duplicate_acknowledged",
    "planting_date_precision", "initial_status", "confirm_ready", "care_schedules", "schedule_effective_date"}


def established_count(db, crop):
    if crop.quantity_planted is None:
        return None
    return crop.quantity_planted + position_summary(db, crop)["replacements"]


def apply_planning_update(db, crop, payload, actor, *, before):
    supplied = payload.model_fields_set
    if not supplied.intersection(PLANNING_INPUTS) and crop.registration_kind == "legacy":
        return
    for key in ("registration_kind", "crop_reference", "variety_reference", "planting_date_precision"):
        if key in supplied:
            setattr(crop, key, getattr(payload, key))
    if crop.registration_kind != "legacy":
        validate_references(db, crop, actor)
    if "section_id" in supplied and payload.section_id:
        allocate(db, crop, section_id=payload.section_id, shared_crop_id=payload.shared_footprint_crop_id,
                 shared_reason=payload.shared_footprint_reason)
    elif crop.footprint_id and "area_hectares" in supplied:
        allocate(db, crop, section_id=crop.section_id)
    if payload.spacing_profile_id or payload.spacing_override:
        snapshot = spacing_snapshot(db, payload, actor)
        crop.spacing_snapshot_json = json.dumps(snapshot, default=str)
    elif any(before.get(key) != getattr(crop, key) for key in ("crop_reference", "variety_reference")):
        # On a new variety, refresh the saved snapshot from that variety's
        # default; never silently keep a previous variety's spacing.
        snapshot = spacing_snapshot(db, payload, actor)
        crop.spacing_snapshot_json = json.dumps(snapshot, default=str) if snapshot else None
        if snapshot is None:
            crop.estimated_capacity = None
    if crop.spacing_snapshot_json:
        crop.estimated_capacity = capacity(crop.area_hectares, json.loads(crop.spacing_snapshot_json))
    if "initial_status" in supplied and payload.initial_status != crop.status:
        if crop.ended_at or (crop.registration_kind != "legacy" and before.get("status") == "Harvested"):
            raise HTTPException(409, "Register a new planting for the next season instead of reopening an ended planting.")
        if payload.initial_status in {"Ready for Harvest", "Harvesting"}:
            if not payload.confirm_ready:
                raise HTTPException(400, "Physically confirm readiness before changing this status.")
            crop.confirmed_ready_at, crop.confirmed_ready_by_user_id = farm_now_naive(), actor.id
        crop.status = payload.initial_status
    if crop.planting_date_precision == "unknown" and crop.planting_date is not None:
        raise HTTPException(400, "An unknown planting date must remain empty.")
    if crop.registration_kind == "new" and crop.planting_date and crop.planting_date < farm_today():
        # Preserve previously recorded dates on edit, but never allow a new backdated planting.
        original_date = before.get("planting_date")
        if original_date != crop.planting_date:
            raise HTTPException(400, "A new planting cannot be moved to a past date.")
    if "care_schedules" in supplied:
        original_schedules = {row.get("activity"): row.get("start_date") for row in json.loads(crop.care_schedules_json or "[]")}
        for schedule in payload.care_schedules:
            if (schedule.enabled and schedule.start_date < farm_today()
                    and str(schedule.start_date) != str(original_schedules.get(schedule.activity))):
                raise HTTPException(400, "A new Watering or Growth Observation start date cannot be in the past.")
        crop.care_schedules_json = json.dumps([x.model_dump(mode="json") for x in payload.care_schedules])
        crop.schedule_effective_date = payload.schedule_effective_date or farm_today()
        crop.care_template_id, crop.watering_schedule, crop.monitoring_enabled = None, None, False
    if "quantity_planted" in supplied and crop.quantity_planted != before.get("quantity_planted"):
        if db.scalar(select(CropPositionEvent.id).where(CropPositionEvent.crop_id == crop.id).limit(1)):
            raise HTTPException(409, "Position history already exists. Record a dated replacement or loss instead of changing the original establishment count.")
        crop.initial_surviving = crop.current_surviving
    elif "current_surviving" in supplied and before.get("current_surviving") != crop.current_surviving:
        new_count, old_count = crop.current_surviving, before.get("current_surviving")
        if old_count is not None and new_count is not None:
            if new_count > old_count:
                raise HTTPException(409, "Record dated replacements in Planting Positions before increasing surviving counts.")
            crop.current_surviving = old_count
            from app.schemas.crop_planning import PositionEventInput
            record_position_event(db, crop, PositionEventInput(event_type="mortality", event_date=farm_today(),
                quantity=old_count - new_count, notes="Authorized surviving-count correction"), actor, f"count-edit:{crop.edit_version}")
        elif new_count is not None:
            crop.initial_surviving = new_count
    if crop.care_schedules_json is not None:
        db.flush()
        from app.services.crop_direct_care import sync_direct_care
        sync_direct_care(db, crop, strict=True)


def validate_references(db, crop, actor):
    from app.core.dependencies import has_permission
    known = db.scalar(select(CropSpacingProfile).where(CropSpacingProfile.crop_key == crop.crop_reference).limit(1))
    variety = db.scalar(select(CropSpacingProfile).where(CropSpacingProfile.crop_key == crop.crop_reference,
                        CropSpacingProfile.variety_key == crop.variety_reference).limit(1))
    if known and known.crop_name != crop.name:
        raise HTTPException(400, "The selected crop reference does not match its saved name.")
    if variety and variety.variety_name != crop.variety:
        raise HTTPException(400, "The selected variety reference does not match its crop or saved name.")
    crop_unknown = crop.crop_reference == "unknown" and crop.name == "Unknown / Not recorded"
    variety_unknown = crop.variety_reference == "unknown" and crop.variety == "Unknown / Not recorded"
    legacy_choice = db.scalar(select(Crop.id).where(Crop.name == crop.name, Crop.variety == crop.variety).limit(1))
    if not ((known or crop_unknown) and (variety or variety_unknown)) and not legacy_choice and not has_permission(actor, "crops:full-edit"):
        raise HTTPException(403, "An administrator must authorize a new custom crop or variety. Existing saved choices remain available.")
