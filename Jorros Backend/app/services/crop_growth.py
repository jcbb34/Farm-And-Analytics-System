from datetime import date

from app.core.farm_time import farm_today


# These percentages are used as the automatic stage thresholds shown in the UI.
# Growth percentage itself comes from planting date -> estimated harvest date.
GROWTH_STAGE_PROGRESS = {
    "Seeded": 0.0,
    "Germination": 15.0,
    "Seedling": 30.0,
    "Vegetative": 50.0,
    "Flowering": 65.0,
    "Fruiting": 80.0,
    "Maturity": 90.0,
    "Harvest Ready": 100.0,
    "Harvesting / Production": 100.0,
    "Harvested": 100.0,
}

GROWTH_STAGES = tuple(GROWTH_STAGE_PROGRESS.keys())


def calculate_crop_progress(
    planting_date: date,
    estimated_harvest: date,
    today: date | None = None,
) -> float:
    """Return automatic crop progress based only on the crop schedule."""
    current_date = today or farm_today()

    if current_date <= planting_date:
        return 0.0

    if current_date >= estimated_harvest:
        return 100.0

    total_days = (estimated_harvest - planting_date).days
    if total_days <= 0:
        return 100.0

    elapsed_days = (current_date - planting_date).days
    progress = (elapsed_days / total_days) * 100
    return round(max(0.0, min(100.0, progress)), 1)


def stage_for_progress(progress: float) -> str:
    """Derive a readable biological stage from automatic progress."""
    value = max(0.0, min(100.0, float(progress or 0)))

    if value >= 100:
        return "Harvest Ready"
    if value >= 90:
        return "Maturity"
    if value >= 80:
        return "Fruiting"
    if value >= 65:
        return "Flowering"
    if value >= 50:
        return "Vegetative"
    if value >= 30:
        return "Seedling"
    if value >= 15:
        return "Germination"
    return "Seeded"


def status_for_progress(progress: float) -> str:
    value = float(progress or 0)
    if value <= 0:
        return "Planted"
    if value < 90:
        return "Growing"
    return "Ready for Harvest"


def growth_stage_progress(stage: str | None) -> float:
    """Compatibility helper for old growth-record data."""
    return GROWTH_STAGE_PROGRESS.get(str(stage or "Seeded").strip(), 0.0)


def status_for_growth_stage(stage: str | None) -> str:
    """Compatibility helper for historical data/imports."""
    normalized = str(stage or "Seeded").strip()
    if normalized == "Harvested":
        return "Harvested"
    if normalized == "Harvesting / Production":
        return "Harvesting"
    return status_for_progress(growth_stage_progress(normalized))


def validate_survival_counts(quantity_planted: int, current_surviving: int) -> None:
    if quantity_planted < 0 or current_surviving < 0:
        raise ValueError("Plant quantities cannot be negative.")
    if quantity_planted and current_surviving > quantity_planted:
        raise ValueError("Current surviving plants cannot exceed quantity planted.")


def survival_rate(quantity_planted: int, current_surviving: int) -> float | None:
    if quantity_planted <= 0:
        return None
    return round((current_surviving / quantity_planted) * 100, 1)
