"""Editable draft master plan. Physical crop and animal records are never synthesized from estimates."""
import json
import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from app.core.database import get_db
from app.core.dependencies import require_permission, require_administrator
from app.models import (AuditLog, Crop, CropField, CropSection, FarmAreaZone,
                        FarmLandConfiguration, InventoryItem, Livestock, LivestockPen)
from app.services.crop_land import decimal, lock_land
from app.services.record_editing import check_edit_version

router = APIRouter(prefix='/api/v1/farm-plan', tags=['Farm Land & Facilities'],
                   dependencies=[Depends(require_permission('crops:view'))])

class ZoneUpdate(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    expected_version: int = Field(gt=0)
    expected_linked_version: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=100)
    proposed_area_m2: Decimal = Field(gt=0, max_digits=16, decimal_places=4)
    measured_area_m2: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=4)
    # Explicitly present only when facility measurement is being changed; omitting
    # it preserves verified measurements while revising proposed dimensions.

class ZoneBatch(BaseModel):
    updates: list[ZoneUpdate] = Field(min_length=1, max_length=80)

class NewFacility(BaseModel):
    code: str = Field(pattern=r'^[A-Z][A-Z0-9]{1,9}$')
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern=r'^(livestock|storage|office|infrastructure)$')
    proposed_area_m2: Decimal = Field(gt=0, max_digits=16, decimal_places=4)
    target_description: str | None = Field(default=None, max_length=180)


def _audit(db, actor, action, details):
    db.add(AuditLog(event_type='audit', module='System', action=action,
                    record_name='Farm Land & Facilities', entity_id='farm-plan',
                    details=json.dumps(details, default=str), icon='landscape',
                    actor_user_id=actor.id, actor_name=actor.full_name or actor.username))


def _active(db):
    return list(db.scalars(select(FarmAreaZone).where(FarmAreaZone.is_active == True)
                           .order_by(FarmAreaZone.code)).all())


def _ensure_valid(db, zones):
    """Proposed polygons never overlap their parent's planned total.

    Planned sizes do not confirm any surveyed measurement. Confirmed facility
    space also cannot overlap known measured crop fields.
    """
    farm = db.get(FarmLandConfiguration, 1)
    if farm is None:
        raise HTTPException(409, 'Farm land configuration is missing. Apply database migrations.')
    by_code = {z.code: z for z in zones}
    root_area = sum((decimal(z.proposed_area_m2) for z in zones if z.parent_code is None), Decimal(0))
    if root_area > decimal(farm.total_area_m2):
        excess = root_area - decimal(farm.total_area_m2)
        raise HTTPException(409, f'Proposed zones exceed the {farm.total_area_m2} m² farm total by {excess} m². Reduce another area in the same save.')
    for zone in zones:
        # Two physical locations at the same level must not share a display name.
        siblings = [x for x in zones if x.parent_code == zone.parent_code and x.kind == zone.kind]
        if any(x.code != zone.code and x.name.strip().casefold() == zone.name.strip().casefold() for x in siblings):
            raise HTTPException(409, f'{zone.parent_code or "farm"}: duplicate location names are not allowed.')
        if zone.parent_code:
            parent = by_code.get(zone.parent_code)
            if parent is None:
                raise HTTPException(409, f'{zone.code}: parent zone is inactive or missing.')
        children = [x for x in zones if x.parent_code == zone.code]
        if children:
            children_area = sum((decimal(x.proposed_area_m2) for x in children), Decimal(0))
            if children_area > decimal(zone.proposed_area_m2):
                raise HTTPException(409, f'{zone.code}: child zones total {children_area} m², exceeding the parent proposal of {zone.proposed_area_m2} m². Adjust both levels before saving.')
            measured_children = sum((decimal(x.measured_area_m2) for x in children
                                     if x.measured_area_m2 is not None), Decimal(0))
            if zone.measured_area_m2 is not None and measured_children > decimal(zone.measured_area_m2):
                raise HTTPException(409, f'{zone.code}: verified child facilities total {measured_children} m² but the verified parent is {zone.measured_area_m2} m². Correct one or more measurements.')
    measured_fields = decimal(db.scalar(select(func.sum(CropField.area_m2))))
    facility = by_code.get('FAC')
    if facility:
        verified_facility = (decimal(facility.measured_area_m2) if facility.measured_area_m2 is not None
            else sum((decimal(z.measured_area_m2) for z in zones if z.parent_code == 'FAC'
                     and z.measured_area_m2 is not None), Decimal(0)))
        if verified_facility + measured_fields > decimal(farm.total_area_m2):
            raise HTTPException(409, f'Verified facilities ({verified_facility} m²) and measured crop fields ({measured_fields} m²) together exceed the farm total ({farm.total_area_m2} m²). Check the physical measurements.')


def _serialize(db, zone):
    linked = None
    occupied = None
    physical_name = None
    if zone.kind == 'field' and zone.crop_field_id:
        linked = db.get(CropField, zone.crop_field_id)
    elif zone.kind == 'section' and zone.crop_section_id:
        linked = db.get(CropSection, zone.crop_section_id)
        occupied = int(db.scalar(select(func.coalesce(func.sum(Crop.current_surviving), 0)).where(
            Crop.section_id == zone.crop_section_id, Crop.is_archived == False, Crop.area_cleared_at.is_(None))) or 0)
    elif zone.kind == 'livestock' and zone.livestock_pen_id:
        pen = db.get(LivestockPen, zone.livestock_pen_id)
        if pen:
            physical_name = pen.name
            occupied = int(db.scalar(select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
                Livestock.pen_id == pen.id, Livestock.is_archived == False,
                Livestock.lifecycle_status == 'Active')) or 0)
    elif zone.kind == 'storage':
        occupied = int(db.scalar(select(func.count(InventoryItem.id)).where(
            InventoryItem.location == zone.name, InventoryItem.is_archived == False)) or 0)
    return dict(code=zone.code, parent_code=zone.parent_code, kind=zone.kind,
                name=(linked.name if linked else physical_name) or zone.name,
                proposed_area_m2=zone.proposed_area_m2,
                measured_area_m2=(linked.area_m2 if linked else zone.measured_area_m2),
                unavailable_area_m2=(linked.unavailable_area_m2 if linked else None),
                target_description=zone.target_description, expected_quantity=zone.expected_quantity,
                current_quantity=occupied, is_active=zone.is_active, edit_version=zone.edit_version,
                crop_field_id=zone.crop_field_id, crop_section_id=zone.crop_section_id,
                livestock_pen_id=zone.livestock_pen_id,
                linked_edit_version=(linked.edit_version if linked else None))


def _overview(db):
    farm = db.get(FarmLandConfiguration, 1)
    if not farm:
        raise HTTPException(409, 'Farm configuration missing; run the database migration first.')
    zones = _active(db)
    if not zones:
        raise HTTPException(409, 'Master plan is missing. Run python -m alembic upgrade head.')
    field_ids = {z.crop_field_id for z in zones if z.crop_field_id}
    extra_fields = db.scalars(select(CropField).where(CropField.id.not_in(field_ids)).order_by(CropField.name)).all()
    return dict(total_area_m2=farm.total_area_m2,
                proposed_crop_m2=sum((decimal(z.proposed_area_m2) for z in zones if z.kind == 'field'), Decimal(0)),
                proposed_facility_m2=sum((decimal(z.proposed_area_m2) for z in zones if z.kind == 'facility'), Decimal(0)),
                measured_crop_m2=decimal(db.scalar(select(func.sum(CropField.area_m2)))),
                verified_facility_m2=(next((z.measured_area_m2 for z in zones if z.code == 'FAC'), None)),
                zones=[_serialize(db, z) for z in zones],
                additional_fields=[dict(id=x.id, name=x.name, measured_area_m2=x.area_m2) for x in extra_fields],
                is_surveyed=False,
                note='Proposed area sizes are editable estimates. Livestock targets do not create animal records; actual counts come from Livestock Management.')


@router.get('')
def get_plan(db=Depends(get_db)):
    return _overview(db)


def _check_changes(db, updates):
    if len({u.code for u in updates}) != len(updates):
        raise HTTPException(400, 'Each zone may be updated only once per request.')
    for update in updates:
        zone = db.get(FarmAreaZone, update.code)
        if not zone or not zone.is_active:
            raise HTTPException(404, f'Zone {update.code} was not found.')
        check_edit_version(zone, update.expected_version)
        new_name = update.name.strip()
        if not new_name:
            raise HTTPException(400, 'Enter a zone name.')
        if zone.kind in ('field', 'section') and 'measured_area_m2' in update.model_fields_set:
            raise HTTPException(400, 'Verify crop field and section sizes in measured Crop Land Setup, not the draft plan.')
        if zone.kind == 'storage' and new_name != zone.name:
            in_use = db.scalar(select(func.count(InventoryItem.id)).where(
                InventoryItem.location == zone.name, InventoryItem.is_archived == False))
            if in_use:
                raise HTTPException(409, f'{zone.name} has inventory records. Transfer stock using Inventory before renaming the location.')
        if zone.kind == 'livestock' and zone.livestock_pen_id:
            pen = db.get(LivestockPen, zone.livestock_pen_id)
            if pen and new_name != pen.name and db.scalar(select(func.count(Livestock.id)).where(
                Livestock.pen_id == pen.id, Livestock.is_archived == False)):
                raise HTTPException(409, 'Transfer existing livestock through Livestock Management before renaming its pen.')
        zone.name = new_name
        zone.proposed_area_m2 = update.proposed_area_m2
        if zone.kind not in ('field', 'section') and 'measured_area_m2' in update.model_fields_set:
            zone.measured_area_m2 = update.measured_area_m2
        if zone.kind == 'field' and zone.crop_field_id:
            field = db.get(CropField, zone.crop_field_id)
            if field is not None:
                check_edit_version(field, update.expected_linked_version)
            if field:
                field.name = new_name
        elif zone.kind == 'section' and zone.crop_section_id:
            section = db.get(CropSection, zone.crop_section_id)
            if section is not None:
                check_edit_version(section, update.expected_linked_version)
            if section:
                section.name = new_name
        elif zone.kind == 'livestock' and zone.livestock_pen_id:
            pen = db.get(LivestockPen, zone.livestock_pen_id)
            if pen:
                pen.name = new_name


@router.put('')
def update_plan(payload: ZoneBatch, db=Depends(get_db), actor=Depends(require_administrator)):
    try:
        lock_land(db)
        _check_changes(db, payload.updates)
        db.flush()
        _ensure_valid(db, _active(db))
        _audit(db, actor, 'Updated editable farm master plan', [u.model_dump(mode='json') for u in payload.updates])
        db.commit()
        return _overview(db)
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(409, 'One or more farm areas changed in another session. Reload the plan and review your edits before saving.') from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'The area update conflicts with an existing field, section, livestock pen, or database reference. Check for duplicate names and active linked records.') from exc
    except Exception:
        db.rollback()
        raise


@router.post('/facilities')
def add_facility(payload: NewFacility, db=Depends(get_db), actor=Depends(require_administrator)):
    try:
        lock_land(db)
        if db.get(FarmAreaZone, payload.code):
            raise HTTPException(409, 'A location with that stable code already exists.')
        shared = db.get(FarmAreaZone, 'R1')
        if not shared or not shared.is_active or shared.proposed_area_m2 <= payload.proposed_area_m2:
            raise HTTPException(409, 'No draft facility space is available. Reduce another facility allocation first.')
        # New facilities draw from shared-infrastructure draft space; no measured area is transferred.
        shared.proposed_area_m2 -= payload.proposed_area_m2
        zone = FarmAreaZone(code=payload.code, parent_code='FAC', kind=payload.kind,
                            name=payload.name.strip(), proposed_area_m2=payload.proposed_area_m2,
                            target_description=payload.target_description)
        if payload.kind == 'livestock':
            pen = db.scalar(select(LivestockPen).where(LivestockPen.name == zone.name))
            if pen is None:
                pen = LivestockPen(name=zone.name, capacity=None, location_area='Joross Farm · '+payload.code,
                                   status='Active', purpose='General')
                db.add(pen)
                db.flush()
            zone.livestock_pen_id = pen.id
        db.add(zone)
        db.flush()
        _ensure_valid(db, _active(db))
        _audit(db, actor, 'Created draft facility zone', payload.model_dump(mode='json'))
        db.commit()
        return _overview(db)
    except Exception:
        db.rollback()
        raise


@router.post('/facilities/{code}/archive')
def archive_facility(code: str, expected_version: int, db=Depends(get_db), actor=Depends(require_administrator)):
    try:
        lock_land(db)
        zone = db.get(FarmAreaZone, code)
        if not zone or not zone.is_active or zone.kind not in ('livestock', 'storage', 'office', 'infrastructure') or code == 'R1':
            raise HTTPException(404, 'Editable facility not found.')
        check_edit_version(zone, expected_version)
        if zone.measured_area_m2 is not None:
            raise HTTPException(409, 'Clear verified measurements before archiving this area.')
        if zone.kind == 'storage' and db.scalar(select(func.count(InventoryItem.id)).where(
            InventoryItem.location == zone.name, InventoryItem.is_archived == False)):
            raise HTTPException(409, 'Move its inventory before archiving.')
        if zone.kind == 'livestock' and zone.livestock_pen_id:
            if db.scalar(select(func.count(Livestock.id)).where(
                Livestock.pen_id == zone.livestock_pen_id, Livestock.is_archived == False)):
                raise HTTPException(409, 'Transfer animals before archiving this area.')
            pen = db.get(LivestockPen, zone.livestock_pen_id)
            if pen:
                pen.is_archived = True
        shared = db.get(FarmAreaZone, 'R1')
        if shared and shared.is_active:
            shared.proposed_area_m2 += zone.proposed_area_m2
        zone.is_active = False
        db.flush()
        _ensure_valid(db, _active(db))
        _audit(db, actor, 'Archived unused facility zone', {'code': code, 'name': zone.name})
        db.commit()
        return _overview(db)
    except Exception:
        db.rollback()
        raise
