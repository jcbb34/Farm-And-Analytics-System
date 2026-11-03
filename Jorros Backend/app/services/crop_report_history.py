"""Project crop lifecycle state at the end of a report period.

Reopening changes the live Crop row; it must not rewrite the status of an
earlier harvest in a regenerated or revised report. Reopen audits and recorded
yield rows already have stable dates, so no schema migration is needed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_today
from app.models import AuditLog, Crop, CropYieldRecord
from app.services.crop_growth import calculate_crop_progress, status_for_progress


def _status_before_completion(crop: Crop, end_date: date, harvested_before_end: bool) -> str:
    if harvested_before_end:
        return "Harvesting"
    return status_for_progress(calculate_crop_progress(crop.planting_date, crop.estimated_harvest, today=end_date))


def crop_statuses_at_period_end(db: Session, crops: list[Crop], end_date: date) -> dict[int, str]:
    if not crops:
        return {}
    if end_date >= farm_today():
        return {crop.id: crop.status for crop in crops}

    ids = [crop.id for crop in crops]
    codes = [crop.crop_code for crop in crops]
    recorded_yields = list(db.scalars(
        select(CropYieldRecord).where(
            CropYieldRecord.crop_id.in_(ids),
            CropYieldRecord.harvest_date <= end_date,
        )
    ).all())
    reopens = list(db.scalars(
        select(AuditLog).where(
            AuditLog.event_type == "audit",
            AuditLog.module == "Crop",
            AuditLog.action == "Reopened crop cycle",
            AuditLog.entity_id.in_(codes),
        ).order_by(AuditLog.created_at, AuditLog.id)
    ).all())

    finals_by_crop = defaultdict(list)
    yields_by_crop = defaultdict(list)
    reopens_by_code = defaultdict(list)
    for record in recorded_yields:
        yields_by_crop[record.crop_id].append(record)
        if str(record.harvest_type or "").strip().lower() == "final harvest":
            finals_by_crop[record.crop_id].append(record)
    for event in reopens:
        reopens_by_code[event.entity_id].append(event)

    statuses = {}
    for crop in crops:
        history = reopens_by_code[crop.crop_code]
        prior = [event for event in history if event.created_at and event.created_at.date() <= end_date]
        reopen = prior[-1] if prior else None
        baseline = re.search(r"Previous final yield ID: (\d+)", reopen.details or "") if reopen else None
        # A final yield from a previous opening still belongs to that period.
        # A final entered after reopening closes the new opening only.
        final_in_current_opening = any(
            reopen is None or (
                record.id > int(baseline.group(1)) if baseline
                else record.created_at is not None and record.created_at > reopen.created_at
            )
            for record in finals_by_crop[crop.id]
        )
        if final_in_current_opening:
            statuses[crop.id] = "Harvested"
            continue

        if reopen is not None:
            if crop.completed_at and reopen.created_at <= crop.completed_at and crop.completed_at.date() <= end_date:
                statuses[crop.id] = "Harvested"
                continue
            match = re.search(r"Status: Harvested → (Harvesting|Ready for Harvest)\.", reopen.details or "")
            statuses[crop.id] = match.group(1) if match else "Harvesting"
            continue

        if crop.completed_at and crop.completed_at.date() <= end_date:
            statuses[crop.id] = "Harvested"
            continue

        # For cycles closed manually (without a yield), retain the prior
        # completion date that was written into the later reopen audit.
        next_reopen = next((event for event in history if event.created_at and event.created_at.date() > end_date), None)
        if next_reopen:
            match = re.search(r"Previous completion: (\d{4}-\d{2}-\d{2})", next_reopen.details or "")
            if match and date.fromisoformat(match.group(1)) <= end_date:
                statuses[crop.id] = "Harvested"
                continue

        if crop.status == "Failed" and not next_reopen:
            statuses[crop.id] = "Failed"
        elif crop.status == "Harvested" and crop.completed_at is None and not next_reopen:
            # Older imported crops may lack completed_at, but still represent
            # a finished cycle when their recorded completion predates the period.
            statuses[crop.id] = "Harvested"
        else:
            statuses[crop.id] = _status_before_completion(
                crop, end_date, bool(yields_by_crop[crop.id]),
            )
    return statuses
