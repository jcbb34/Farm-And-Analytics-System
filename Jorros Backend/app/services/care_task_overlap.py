"""Keep protocol steps from duplicating work owned by an operational schedule."""

from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Crop, CropGrowthRecord, FarmActivity, Livestock


NATIVE_CARE_TYPES = frozenset({
    "crop_watering", "crop_harvest", "crop_growth_check", "crop_pest_followup",
    "livestock_feeding", "livestock_vaccination", "livestock_health_check",
})


def native_family_for_step(module: str, category: str | None, title: str | None) -> str | None:
    """Recognize only a step with the same *action* as a native task.

    A general inspection, pesticide application, supplement, or weighing is
    not interchangeable with a growth/health/pest follow-up reminder.
    """
    category = " ".join(str(category or "").lower().split())
    title = " ".join(str(title or "").lower().split())
    if module == "Crop":
        if category in {"watering", "irrigation", "crop watering"} or re.match(r"^(water|irrigate)\b", title):
            return "crop_watering"
        if category in {"harvest", "harvesting"} or re.match(r"^harvest\b", title):
            return "crop_harvest"
        if title.startswith("growth check"):
            return "crop_growth_check"
        if title.startswith(("pest follow-up", "pest/disease follow-up")):
            return "crop_pest_followup"
    if module == "Livestock":
        if category in {"feeding", "livestock feeding"} or re.match(r"^(feed|feeding)\b", title):
            return "livestock_feeding"
        if category in {"vaccine", "vaccination"} or re.match(r"^vaccinat", title):
            return "livestock_vaccination"
        if title.startswith("health check"):
            return "livestock_health_check"
    return None


def native_covered_occurrences(
    db: Session,
    *,
    module: str,
    target: Crop | Livestock,
    occurrences: list[tuple[object, date, int]],
) -> set[tuple[str, date]]:
    """Look up existing native work once, then account for its future schedule."""
    families = {
        family for step, _, _ in occurrences
        if (family := native_family_for_step(module, step.category, step.title))
    }
    if not families or not occurrences:
        return set()

    dates = [task_date for _, task_date, _ in occurrences]
    rows = db.execute(
        select(FarmActivity.source_type, FarmActivity.activity_date).where(
            FarmActivity.is_automatic == True,
            FarmActivity.source_module == module,
            FarmActivity.source_record_id == target.id,
            FarmActivity.source_type.in_(families),
            FarmActivity.activity_date.between(min(dates), max(dates)),
            FarmActivity.is_archived == False,
            FarmActivity.status.notin_(["Resolved", "Voided", "Cancelled"]),
        )
    ).all()
    covered = {(family, activity_date) for family, activity_date in rows}

    scheduled_dates = {task_date for _, task_date, _ in occurrences}
    if module == "Livestock":
        if "livestock_feeding" in families and str(target.feed_times or "").strip():
            covered.update(("livestock_feeding", day) for day in scheduled_dates if day >= target.date_acquired)
        if "livestock_vaccination" in families and target.next_vaccination in scheduled_dates:
            covered.add(("livestock_vaccination", target.next_vaccination))
        if "livestock_health_check" in families:
            due = (target.last_checkup or target.date_acquired) + timedelta(days=14)
            if due in scheduled_dates:
                covered.add(("livestock_health_check", due))
            if str(target.health_status or "").strip().lower() not in {"", "healthy", "good"}:
                from app.core.farm_time import farm_today

                if farm_today() in scheduled_dates:
                    covered.add(("livestock_health_check", farm_today()))
    elif module == "Crop" and target.status not in {"Harvested", "Failed"}:
        if "crop_watering" in families:
            # Reuse the canonical schedule parser; this avoids assuming every
            # crop is watered daily or treating rain-fed crops as scheduled.
            from app.services.task_engine import _watering_occurrences

            covered.update(
                ("crop_watering", day)
                for day in scheduled_dates
                if any(occurrence_date == day for occurrence_date, _, _ in _watering_occurrences(target, day))
            )
        if "crop_harvest" in families and target.estimated_harvest in scheduled_dates and target.status != "Harvesting":
            covered.add(("crop_harvest", target.estimated_harvest))
        if "crop_growth_check" in families and target.status != "Harvesting":
            dates = db.scalars(select(FarmActivity.activity_date).where(
                FarmActivity.source_module == "Crop", FarmActivity.source_record_id == target.id,
                FarmActivity.source_type == "crop_growth_check", FarmActivity.is_automatic == True,
                FarmActivity.activity_date.in_(scheduled_dates), FarmActivity.status != "Resolved",
            )).all()
            covered.update(("crop_growth_check", day) for day in dates)
    return covered


def resolve_pending_protocol_overlaps(db: Session, *, today: date) -> int:
    """Resolve only Pending duplicates once the native scheduler creates work.

    The bounded, indexed due-date queries leave existing employee submissions,
    started tasks, and completed history untouched.
    """
    end_date = today + timedelta(days=7)
    beginning = today - timedelta(days=7)
    native_rows = db.execute(
        select(FarmActivity.source_module, FarmActivity.source_record_id,
               FarmActivity.source_type, FarmActivity.activity_date).where(
            FarmActivity.is_automatic == True,
            FarmActivity.is_archived == False,
            FarmActivity.source_type.in_(NATIVE_CARE_TYPES),
            FarmActivity.activity_date.between(beginning, end_date),
            FarmActivity.status.notin_(["Resolved", "Voided", "Cancelled"]),
        )
    ).all()
    if not native_rows:
        return 0
    native = set(native_rows)
    pending = db.scalars(select(FarmActivity).where(
        FarmActivity.is_automatic == True,
        FarmActivity.is_archived == False,
        FarmActivity.source_type == "care_template_step",
        FarmActivity.status == "Pending",
        FarmActivity.activity_date.between(beginning, end_date),
    )).all()
    count = 0
    for task in pending:
        family = native_family_for_step(task.source_module, task.category, task.name)
        if family and (task.source_module, task.source_record_id, family, task.activity_date) in native:
            task.status = "Resolved"
            task.completed_at = None
            count += 1
    return count
