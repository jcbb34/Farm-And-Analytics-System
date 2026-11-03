from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.farm_time import farm_today
from app.models import (
    Livestock,
    LivestockGrowthProfile,
    LivestockGrowthProfileStage,
)


def _normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def biological_age_days_from_values(
    *,
    date_of_birth: date | None,
    estimated_age_days: int | None,
    estimated_age_as_of_date: date | None,
    as_of_date: date | None = None,
) -> int | None:
    """Return biological age without inventing a stored birth date.

    Exact DOB is preferred. If DOB is unknown, the explicit estimated age is
    advanced from the date on which that estimate was made.
    """
    target_date = as_of_date or farm_today()
    if date_of_birth is not None:
        return max(0, (target_date - date_of_birth).days)
    if estimated_age_days is None or estimated_age_as_of_date is None:
        return None
    return max(0, int(estimated_age_days) + (target_date - estimated_age_as_of_date).days)


def biological_age_days(livestock: Livestock, as_of_date: date | None = None) -> int | None:
    return biological_age_days_from_values(
        date_of_birth=livestock.date_of_birth,
        estimated_age_days=livestock.estimated_age_days,
        estimated_age_as_of_date=livestock.estimated_age_as_of_date,
        as_of_date=as_of_date,
    )


def estimated_biological_birth_anchor(livestock: Livestock) -> date | None:
    """Return a scheduling anchor only; never writes an estimated DOB to livestock."""
    if livestock.date_of_birth is not None:
        return livestock.date_of_birth
    if livestock.estimated_age_days is None or livestock.estimated_age_as_of_date is None:
        return None
    return livestock.estimated_age_as_of_date - timedelta(days=int(livestock.estimated_age_days))


def _profile_matches(profile: LivestockGrowthProfile, *, species: str, breed: str | None, production_purpose: str | None, sex: str | None, as_of_date: date) -> bool:
    if not profile.is_active or profile.status not in {"Published", "Draft"}:
        return False
    if profile.effective_from and as_of_date < profile.effective_from:
        return False
    if profile.effective_to and as_of_date > profile.effective_to:
        return False
    if _normalize(profile.species) != _normalize(species):
        return False
    for expected, actual in (
        (profile.breed_strain, breed),
        (profile.production_purpose, production_purpose),
        (profile.sex, sex),
    ):
        if expected and _normalize(expected) != _normalize(actual):
            return False
    return True


def find_best_growth_profile(
    db: Session,
    *,
    species: str,
    breed: str | None = None,
    production_purpose: str | None = None,
    sex: str | None = None,
    as_of_date: date | None = None,
) -> LivestockGrowthProfile | None:
    today = as_of_date or farm_today()
    profiles = list(
        db.scalars(
            select(LivestockGrowthProfile)
            .where(func.lower(LivestockGrowthProfile.species) == _normalize(species))
            .options(selectinload(LivestockGrowthProfile.stages))
        ).all()
    )
    matches = [
        profile for profile in profiles
        if _profile_matches(
            profile,
            species=species,
            breed=breed,
            production_purpose=production_purpose,
            sex=sex,
            as_of_date=today,
        )
    ]
    if not matches:
        return None

    def rank(profile: LivestockGrowthProfile) -> tuple[int, int, int, int]:
        specificity = (
            (4 if profile.breed_strain else 0)
            + (2 if profile.production_purpose else 0)
            + (1 if profile.sex else 0)
        )
        status_rank = 2 if profile.status == "Published" else 1
        return (specificity, status_rank, int(profile.version or 0), int(profile.id or 0))

    return max(matches, key=rank)


def stage_for_age(profile: LivestockGrowthProfile | None, age_days: int | None) -> LivestockGrowthProfileStage | None:
    if profile is None or age_days is None:
        return None
    ordered = sorted(profile.stages or [], key=lambda row: (row.sequence_number, row.id or 0))
    for stage in ordered:
        if age_days < int(stage.age_start_days or 0):
            continue
        if stage.age_end_days is not None and age_days > int(stage.age_end_days):
            continue
        return stage
    return None


def _deviation(actual_weight_kg: float | None, stage: LivestockGrowthProfileStage | None) -> tuple[str | None, str | None]:
    if actual_weight_kg is None or stage is None:
        return None, None
    low = float(stage.expected_min_weight_kg) if stage.expected_min_weight_kg is not None else None
    high = float(stage.expected_max_weight_kg) if stage.expected_max_weight_kg is not None else None
    actual = float(actual_weight_kg)
    if low is None and high is None:
        return "No verified weight range", "The matched stage has no verified expected weight range. Continue recording actual measurements."
    if low is not None and actual < low:
        meaningful = actual < (low * 0.90)
        label = "Meaningfully below expected" if meaningful else "Below expected"
        return label, (
            f"Actual weight {actual:.2f} kg is below the profile range"
            f"{f' {low:.2f}–{high:.2f} kg' if high is not None else f' starting at {low:.2f} kg'}. "
            "Review the measurement and husbandry context; this flag is not a disease diagnosis."
        )
    if high is not None and actual > high:
        meaningful = actual > (high * 1.10)
        label = "Meaningfully above expected" if meaningful else "Above expected"
        return label, (
            f"Actual weight {actual:.2f} kg is above the profile range"
            f"{f' {low:.2f}–{high:.2f} kg' if low is not None else f' ending at {high:.2f} kg'}. "
            "Review the measurement and husbandry context; this flag is not a disease diagnosis."
        )
    return "Within expected range", "Actual weight is within the matched profile range."


def assess_growth_values(
    db: Session,
    *,
    species: str,
    breed: str | None,
    production_purpose: str | None,
    sex: str | None,
    date_of_birth: date | None,
    estimated_age_days: int | None,
    estimated_age_as_of_date: date | None,
    actual_weight_kg: float | None,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    target_date = as_of_date or farm_today()
    age_days = biological_age_days_from_values(
        date_of_birth=date_of_birth,
        estimated_age_days=estimated_age_days,
        estimated_age_as_of_date=estimated_age_as_of_date,
        as_of_date=target_date,
    )
    profile = find_best_growth_profile(
        db,
        species=species,
        breed=breed,
        production_purpose=production_purpose,
        sex=sex,
        as_of_date=target_date,
    )
    stage = stage_for_age(profile, age_days)
    deviation_status, deviation_message = _deviation(actual_weight_kg, stage)

    if age_days is None:
        why = "Biological age cannot be calculated until an exact birth/hatch date or a dated age estimate is recorded."
    elif profile is None:
        why = f"Biological age is {age_days} day(s), but no matching growth profile exists for the recorded species/breed/purpose/sex."
    elif stage is None:
        why = f"Biological age is {age_days} day(s); the matched profile has no stage covering this age."
    else:
        qualifier_bits = [profile.species]
        if profile.breed_strain:
            qualifier_bits.append(profile.breed_strain)
        if profile.production_purpose:
            qualifier_bits.append(profile.production_purpose)
        if profile.sex:
            qualifier_bits.append(profile.sex)
        why = (
            f"Suggested from biological age {age_days} day(s) using {' / '.join(qualifier_bits)} "
            f"growth profile v{profile.version} ({profile.status}). Stage window: "
            f"{stage.age_start_days}–{stage.age_end_days if stage.age_end_days is not None else 'open-ended'} days."
        )

    return {
        "as_of_date": target_date,
        "age_days": age_days,
        "age_source": "Exact birth/hatch date" if date_of_birth is not None else ("Dated age estimate" if age_days is not None else "Unknown"),
        "suggested_stage": stage.stage_name if stage else None,
        "suggestion_reason": why,
        "expected_min_weight_kg": float(stage.expected_min_weight_kg) if stage and stage.expected_min_weight_kg is not None else None,
        "expected_max_weight_kg": float(stage.expected_max_weight_kg) if stage and stage.expected_max_weight_kg is not None else None,
        "deviation_status": deviation_status,
        "deviation_message": deviation_message,
        "profile_id": profile.id if profile else None,
        "profile_family_code": profile.profile_family_code if profile else None,
        "profile_version": profile.version if profile else None,
        "profile_name": profile.name if profile else None,
        "profile_status": profile.status if profile else None,
        "approval_status": profile.approval_status if profile else None,
        "source_title": profile.source_title if profile else None,
        "source_url": profile.source_url if profile else None,
    }


def assess_livestock_growth(db: Session, livestock: Livestock, *, as_of_date: date | None = None, actual_weight_kg: float | None = None) -> dict[str, Any]:
    return assess_growth_values(
        db,
        species=livestock.animal_type,
        breed=livestock.breed,
        production_purpose=livestock.production_purpose,
        sex=livestock.sex,
        date_of_birth=livestock.date_of_birth,
        estimated_age_days=livestock.estimated_age_days,
        estimated_age_as_of_date=livestock.estimated_age_as_of_date,
        actual_weight_kg=float(livestock.weight_kg) if actual_weight_kg is None and livestock.weight_kg is not None else actual_weight_kg,
        as_of_date=as_of_date,
    )
