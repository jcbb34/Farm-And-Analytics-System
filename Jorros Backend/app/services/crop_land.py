"""Exact physical area accounting; every footprint consumes its section once."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.crop_planning import FarmLandConfiguration, CropField, CropSection, CropFootprint
from app.models import Crop
from app.services.db_concurrency import acquire_transaction_lock
from app.services.record_editing import check_edit_version

ZERO = Decimal("0")


def decimal(value):
    return Decimal(str(value or 0))


def lock_land(db):
    acquire_transaction_lock(db, "farm:measured-land-allocation")


def configured_farm(db):
    row = db.get(FarmLandConfiguration, 1)
    if row is None:
        raise HTTPException(409, "Farm land configuration needs the database upgrade.")
    return row


def used_area(db, section_id, *, exclude_footprint=None):
    stmt = select(func.coalesce(func.sum(CropFootprint.area_m2), 0)).where(
        CropFootprint.section_id == section_id, CropFootprint.released_at.is_(None))
    if exclude_footprint is not None:
        stmt = stmt.where(CropFootprint.id != exclude_footprint)
    return decimal(db.scalar(stmt))


def section_summary(db, row, *, allocated=None):
    used = used_area(db, row.id) if allocated is None else allocated
    usable = None if row.area_m2 is None else decimal(row.area_m2) - decimal(row.unavailable_area_m2)
    available = None if usable is None else max(ZERO, usable - used)
    status = "Unconfigured" if usable is None else "Full" if available == 0 else "Partly Occupied" if used else "Available"
    return dict(id=row.id, field_id=row.field_id, name=row.name, area_m2=row.area_m2,
                unavailable_area_m2=row.unavailable_area_m2, unavailable_reason=row.unavailable_reason,
                usable_area_m2=usable, allocated_area_m2=used, available_area_m2=available,
                status=status, edit_version=row.edit_version)


def land_overview(db):
    farm = configured_farm(db)
    sections = list(db.scalars(select(CropSection).order_by(CropSection.name)).all())
    fields = list(db.scalars(select(CropField).order_by(CropField.name)).all())
    allocated = dict(db.execute(select(CropFootprint.section_id, func.sum(CropFootprint.area_m2))
        .where(CropFootprint.released_at.is_(None)).group_by(CropFootprint.section_id)).all())
    return dict(total_area_m2=farm.total_area_m2, unavailable_area_m2=farm.unavailable_area_m2,
                unavailable_reason=farm.unavailable_reason, edit_version=farm.edit_version,
                measured_fields_area_m2=sum((decimal(f.area_m2) for f in fields), ZERO),
                legacy_unmapped_count=db.scalar(select(func.count()).select_from(Crop).where(Crop.footprint_id.is_(None))),
                fields=[dict(id=f.id, name=f.name, area_m2=f.area_m2, unavailable_area_m2=f.unavailable_area_m2,
                             unavailable_reason=f.unavailable_reason, edit_version=f.edit_version,
                             sections=[section_summary(db, s, allocated=decimal(allocated.get(s.id))) for s in sections if s.field_id == f.id]) for f in fields])


def save_area(db, payload, *, field_id=None, section_id=None, field_record_id=None, actor=None):
    lock_land(db)
    farm = configured_farm(db)
    if field_record_id is not None:
        row = db.get(CropField, field_record_id)
        if row is None:
            raise HTTPException(404, "Field not found.")
    elif section_id is not None:
        row = db.get(CropSection, section_id)
        if row is None:
            raise HTTPException(404, "Section not found.")
        field_id = row.field_id
    elif field_id is not None:
        if db.get(CropField, field_id) is None:
            raise HTTPException(404, "Field not found.")
        row = CropSection(field_id=field_id)
    else:
        row = CropField()
    if getattr(row, "id", None):
        check_edit_version(row, payload.expected_version)
    row.name = payload.name.strip()
    if not row.name:
        raise HTTPException(400, "Enter a field or section name.")
    model = CropSection if isinstance(row, CropSection) else CropField
    duplicate = select(model.id).where(func.lower(model.name) == row.name.lower(), model.id != (row.id or -1))
    if isinstance(row, CropSection):
        duplicate = duplicate.where(CropSection.field_id == row.field_id)
    if db.scalar(duplicate.limit(1)):
        raise HTTPException(409, "This field/section name is already saved in that location.")
    row.area_m2 = payload.area_m2
    row.unavailable_area_m2 = payload.unavailable_area_m2
    row.unavailable_reason = payload.unavailable_reason
    usable = None if row.area_m2 is None else row.area_m2 - row.unavailable_area_m2
    if isinstance(row, CropSection):
        parent = db.get(CropField, row.field_id)
        if parent.area_m2 is None and row.area_m2 is not None:
            raise HTTPException(409, "Save the measured field size first.")
        siblings = decimal(db.scalar(select(func.sum(CropSection.area_m2)).where(CropSection.field_id == row.field_id, CropSection.id != (row.id or -1))))
        if parent.area_m2 is not None and siblings + decimal(row.area_m2) > parent.area_m2 - parent.unavailable_area_m2:
            raise HTTPException(409, "Sections exceed their field's usable measured area.")
        used = used_area(db, row.id) if row.id else ZERO
    else:
        siblings = decimal(db.scalar(select(func.sum(CropField.area_m2)).where(CropField.id != (row.id or -1))))
        if siblings + decimal(row.area_m2) > farm.total_area_m2 - farm.unavailable_area_m2:
            raise HTTPException(409, "Measured fields exceed the farm's available physical area.")
        used = decimal(db.scalar(select(func.sum(CropSection.area_m2)).where(CropSection.field_id == row.id))) if row.id else ZERO
    if used and (usable is None or usable < used):
        raise HTTPException(409, "The new usable size is below existing sections or planting allocations.")
    db.add(row)
    db.flush()
    return row


def allocate(db, crop, *, section_id, shared_crop_id=None, shared_reason=None):
    lock_land(db)
    section = db.get(CropSection, section_id)
    if section is None:
        raise HTTPException(404, "Select a saved section.")
    field = db.get(CropField, section.field_id)
    if section.area_m2 is None or field.area_m2 is None:
        raise HTTPException(409, "Enter measured field and section sizes in Land Setup before allocating space.")
    area = decimal(crop.area_hectares) * 10000
    old = db.get(CropFootprint, crop.footprint_id) if crop.footprint_id else None
    if crop.area_cleared_at or (old and old.released_at):
        raise HTTPException(409, "This planting's area was cleared. Register a new planting for the next season.")
    if shared_crop_id:
        parent = db.get(Crop, shared_crop_id)
        footprint = db.get(CropFootprint, parent.footprint_id) if parent and parent.footprint_id else None
        if not footprint or footprint.released_at or parent.area_cleared_at or footprint.section_id != section_id:
            raise HTTPException(409, "Choose an occupied planting in the same section to share its footprint.")
        if old and old.id != footprint.id:
            raise HTTPException(409, "This planting already occupies a different measured footprint. Confirm its area cleared and register a new planting before sharing another footprint.")
        if area != footprint.area_m2 or not str(shared_reason or "").strip():
            raise HTTPException(400, "A shared planting must use the same measured footprint and describe the intercropping arrangement.")
        footprint.shared_reason = shared_reason.strip()
    else:
        if old and old.released_at is None:
            members = db.scalar(select(func.count()).select_from(Crop).where(Crop.footprint_id == old.id, Crop.id != crop.id, Crop.area_cleared_at.is_(None)))
            if members and (old.area_m2 != area or old.section_id != section_id):
                raise HTTPException(409, "A shared footprint cannot be resized or moved through one planting.")
        available = decimal(section.area_m2) - decimal(section.unavailable_area_m2) - used_area(db, section_id, exclude_footprint=old.id if old else None)
        if area <= 0 or area > available:
            raise HTTPException(409, f"Only {available / 10000:f} ha of usable section area remains.")
        footprint = old or CropFootprint(section_id=section_id)
        footprint.section_id, footprint.area_m2 = section_id, area
        db.add(footprint)
        db.flush()
    crop.section_id, crop.footprint_id, crop.field = section.id, footprint.id, field.name
    return footprint
