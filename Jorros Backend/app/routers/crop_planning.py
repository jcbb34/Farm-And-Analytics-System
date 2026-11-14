"""Measured land setup and planting actions attached to the existing Crops module."""
import json
import hashlib
from datetime import date
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from app.core.database import get_db
from app.core.dependencies import require_permission, require_administrator
from app.models import Crop, CropField, CropSection, CropSpacingProfile, AuditLog
from app.schemas.crop_planning import LandAreaInput, FarmAreaInput, PositionEventInput, EndPlantingInput, DirectCropSchedule, SpacingAdjustment
from app.services import crop_land
from app.services.crop_planting import profile_dict, built_in_profiles, position_summary, record_position_event, end_planting
from app.services.crop_direct_care import preview_schedules
from app.services.record_editing import check_edit_version
from app.services.workforce_intervals import available_slots

router = APIRouter(prefix="/api/v1/crop-planning", tags=["Crop Planning"], dependencies=[Depends(require_permission("crops:view"))])


def _audit(db, actor, action, details):
    db.add(AuditLog(event_type="audit", module="Crop", action=action, record_name="Farm land and crop configuration",
        entity_id="farm-configuration", details=json.dumps(details, default=str), icon="landscape",
        actor_user_id=actor.id, actor_name=actor.full_name or actor.username))


@router.get("/references")
def references(db=Depends(get_db)):
    latest = select(CropSpacingProfile.profile_key, func.max(CropSpacingProfile.version).label("version")).group_by(CropSpacingProfile.profile_key).subquery()
    profiles = db.scalars(select(CropSpacingProfile).join(latest, (CropSpacingProfile.profile_key == latest.c.profile_key) & (CropSpacingProfile.version == latest.c.version))).all()
    legacy = db.execute(select(Crop.name, Crop.variety, Crop.field, Crop.crop_reference, Crop.variety_reference).distinct()).all()
    return {"profiles": [profile_dict(x) for x in profiles], "sources": built_in_profiles()["sources"],
            "legacy_choices": [{"name": r.name, "variety": r.variety, "field": r.field,
                                "crop_reference": r.crop_reference, "variety_reference": r.variety_reference} for r in legacy],
            "unknown_label": "Unknown / Not recorded", "supported_layouts": ["square", "rectangular"]}


@router.get("/custom-reference")
def custom_reference(name: str = Query(min_length=1, max_length=100), actor=Depends(require_permission("crops:full-edit"))):
    normalized = name.strip().lower()
    if not normalized:
        raise HTTPException(400, "Enter a crop or variety name.")
    return {"reference": "custom:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:40]}


@router.get("/land")
def land(db=Depends(get_db)):
    return crop_land.land_overview(db)


@router.put("/land")
def save_farm(payload: FarmAreaInput, db=Depends(get_db), actor=Depends(require_administrator)):
    try:
        crop_land.lock_land(db)
        row = crop_land.configured_farm(db)
        check_edit_version(row, payload.expected_version)
        measured = crop_land.decimal(db.scalar(select(func.sum(CropField.area_m2))))
        if payload.unavailable_area_m2 > payload.total_area_m2 or measured > payload.total_area_m2 - payload.unavailable_area_m2:
            raise HTTPException(409, "The farm size cannot be smaller than its unavailable space and measured fields.")
        if payload.unavailable_area_m2 and not (payload.unavailable_reason or "").strip():
            raise HTTPException(400, "Describe excluded livestock facilities, buildings, paths or drainage.")
        for key in ("total_area_m2", "unavailable_area_m2", "unavailable_reason"):
            setattr(row, key, getattr(payload, key))
        _audit(db, actor, "Updated farm measured area", payload.model_dump())
        db.commit()
        return crop_land.land_overview(db)
    except Exception:
        db.rollback()
        raise


def _save(db, actor, payload, **target):
    try:
        row = crop_land.save_area(db, payload, actor=actor, **target)
        _audit(db, actor, "Saved field/section measured area", {"id": row.id, "type": type(row).__name__, **payload.model_dump()})
        db.commit()
        return crop_land.land_overview(db)
    except Exception:
        db.rollback()
        raise


@router.post("/fields")
def add_field(payload: LandAreaInput, db=Depends(get_db), actor=Depends(require_administrator)):
    return _save(db, actor, payload)


@router.put("/fields/{field_id}")
def update_field(field_id: int, payload: LandAreaInput, db=Depends(get_db), actor=Depends(require_administrator)):
    return _save(db, actor, payload, field_record_id=field_id)


@router.post("/fields/{field_id}/sections")
def add_section(field_id: int, payload: LandAreaInput, db=Depends(get_db), actor=Depends(require_administrator)):
    return _save(db, actor, payload, field_id=field_id)


@router.put("/sections/{section_id}")
def update_section(section_id: int, payload: LandAreaInput, db=Depends(get_db), actor=Depends(require_administrator)):
    return _save(db, actor, payload, section_id=section_id)


class PreviewInput(BaseModel):
    care_schedules: list[DirectCropSchedule] = Field(default_factory=list, max_length=2)
    assigned_employee_id: int | None = None
    crop_id: int | None = None
    effective_date: date | None = None


@router.post("/schedule-preview")
def schedule_preview(payload: PreviewInput, db=Depends(get_db), actor=Depends(require_permission("crops:create"))):
    return preview_schedules(db, payload.care_schedules, default_employee_id=payload.assigned_employee_id,
                             crop_id=payload.crop_id, effective_date=payload.effective_date)


@router.get("/available-slots")
def slots(employee_id: int, work_date: date, duration_minutes: int = Query(gt=0, le=720), db=Depends(get_db)):
    return available_slots(db, employee_id, work_date, duration_minutes)


@router.get("/plantings")
def planting_choices(section_id: int, db=Depends(get_db)):
    rows = db.scalars(select(Crop).where(Crop.section_id == section_id, Crop.area_cleared_at.is_(None), Crop.is_archived == False)).all()
    return [{"id": x.id, "code": x.crop_code, "name": x.name, "variety": x.variety, "area_hectares": x.area_hectares,
             "crop_reference": x.crop_reference, "variety_reference": x.variety_reference, "footprint_id": x.footprint_id} for x in rows]


def _crop(db, crop_id):
    row = db.get(Crop, crop_id)
    if row is None:
        raise HTTPException(404, "Planting not found.")
    return row


@router.get("/plantings/{crop_id}/positions")
def positions(crop_id: int, db=Depends(get_db)):
    return position_summary(db, _crop(db, crop_id))


@router.post("/plantings/{crop_id}/positions")
def position_event(crop_id: int, payload: PositionEventInput, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), db=Depends(get_db), actor=Depends(require_permission("crops:update"))):
    try:
        crop = _crop(db, crop_id)
        result = record_position_event(db, crop, payload, actor, idempotency_key)
        if not result.get("idempotent_replay"):
            _audit(db, actor, "Recorded planting position event", {"crop_id": crop.id, **payload.model_dump()})
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/plantings/{crop_id}/end")
def end(crop_id: int, payload: EndPlantingInput, db=Depends(get_db), actor=Depends(require_permission("crops:full-edit"))):
    try:
        crop = _crop(db, crop_id)
        check_edit_version(crop, payload.expected_version)
        end_planting(db, crop, actor, reason=payload.reason, cleared=payload.confirm_area_cleared)
        db.commit()
        return {"id": crop.id, "status": crop.status, "area_cleared_at": crop.area_cleared_at, "edit_version": crop.edit_version}
    except Exception:
        db.rollback()
        raise


@router.post("/profiles/{profile_id}/versions")
def adjust_profile(profile_id: int, payload: SpacingAdjustment, db=Depends(get_db), actor=Depends(require_administrator)):
    try:
        crop_land.lock_land(db)
        old = db.get(CropSpacingProfile, profile_id)
        if not old:
            raise HTTPException(404, "Profile not found.")
        data = {c.name: getattr(old, c.name) for c in old.__table__.columns if c.name not in {"id", "version", "created_by_user_id"}}
        data.update(payload.model_dump())
        data["version"] = db.scalar(select(func.max(CropSpacingProfile.version)).where(CropSpacingProfile.profile_key == old.profile_key)) + 1
        row = CropSpacingProfile(**data, created_by_user_id=actor.id)
        db.add(row)
        _audit(db, actor, "Versioned crop spacing default", data)
        db.commit()
        return profile_dict(row)
    except Exception:
        db.rollback()
        raise
