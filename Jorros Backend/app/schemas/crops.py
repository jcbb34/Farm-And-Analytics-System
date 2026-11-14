from datetime import date, datetime
from typing import Literal
from decimal import Decimal
from app.schemas.crop_planning import DirectCropSchedule, SpacingAdjustment

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =========================================================
# CROP
# =========================================================

class CropCreate(BaseModel):
    registration_kind: Literal["legacy", "new", "existing"] = "legacy"
    crop_reference: str | None = Field(default=None, max_length=60)
    variety_reference: str | None = Field(default=None, max_length=80)
    section_id: int | None = Field(default=None, gt=0)
    spacing_profile_id: int | None = Field(default=None, gt=0)
    spacing_override: SpacingAdjustment | None = None
    shared_footprint_crop_id: int | None = Field(default=None, gt=0)
    shared_footprint_reason: str | None = Field(default=None, max_length=500)
    duplicate_acknowledged: bool = False
    planting_date_precision: Literal["known", "estimated", "unknown"] = "known"
    initial_status: Literal["Growing", "Ready for Harvest", "Harvesting"] = "Growing"
    confirm_ready: bool = False
    care_schedules: list[DirectCropSchedule] = Field(default_factory=list, max_length=2)
    schedule_effective_date: date | None = None

    model_config = ConfigDict(str_strip_whitespace=True)
    monitoring_enabled: bool = True
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)

    name: str = Field(
        min_length=2,
        max_length=100,
    )

    variety: str = Field(
        min_length=1,
        max_length=100,
    )

    field: str = Field(
        min_length=1,
        max_length=100,
    )

    area_hectares: Decimal = Field(
        gt=0,
    )

    quantity_planted: int | None = Field(default=None, ge=0)
    current_surviving: int | None = Field(default=None, ge=0)

    planting_date: date | None = None
    estimated_harvest: date | None = None

    fertilizer_quantity_kg: float = Field(
        default=0,
        ge=0,
    )

    fertilizer_date: date | None = None

    pesticide_used: str | None = Field(
        default=None,
        max_length=150,
    )

    watering_schedule: str | None = Field(
        default=None,
        max_length=255,
    )

    notes: str | None = None
    assigned_employee_id: int | None = Field(default=None, gt=0)
    care_template_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.estimated_harvest and self.planting_date and self.estimated_harvest < self.planting_date:
            raise ValueError(
                "Estimated harvest date cannot "
                "be earlier than planting date."
            )

        return self


class CropUpdate(BaseModel):
    registration_kind: Literal["legacy", "new", "existing"] = "legacy"
    crop_reference: str | None = Field(default=None, max_length=60)
    variety_reference: str | None = Field(default=None, max_length=80)
    section_id: int | None = Field(default=None, gt=0)
    spacing_profile_id: int | None = Field(default=None, gt=0)
    spacing_override: SpacingAdjustment | None = None
    shared_footprint_crop_id: int | None = Field(default=None, gt=0)
    shared_footprint_reason: str | None = Field(default=None, max_length=500)
    duplicate_acknowledged: bool = False
    planting_date_precision: Literal["known", "estimated", "unknown"] = "known"
    initial_status: Literal["Growing", "Ready for Harvest", "Harvesting"] = "Growing"
    confirm_ready: bool = False
    care_schedules: list[DirectCropSchedule] = Field(default_factory=list, max_length=2)
    schedule_effective_date: date | None = None

    expected_version: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(str_strip_whitespace=True)
    monitoring_enabled: bool | None = None
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    variety: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    field: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    area_hectares: Decimal | None = Field(
        default=None,
        gt=0,
    )

    quantity_planted: int | None = Field(default=None, ge=0)
    current_surviving: int | None = Field(default=None, ge=0)

    # Status remains available for terminal states such as Harvested and Failed.
    status: str | None = Field(
        default=None,
        max_length=30,
    )

    planting_date: date | None = None
    estimated_harvest: date | None = None

    fertilizer_quantity_kg: float | None = Field(
        default=None,
        ge=0,
    )

    fertilizer_date: date | None = None

    pesticide_used: str | None = Field(
        default=None,
        max_length=150,
    )

    watering_schedule: str | None = Field(
        default=None,
        max_length=255,
    )

    notes: str | None = None
    assigned_employee_id: int | None = Field(default=None, gt=0)
    care_template_id: int | None = Field(default=None, gt=0)
    future_care_task_action: Literal["keep", "resolve"] | None = None

    @model_validator(mode="after")
    def explicitly_unknown_dates(self):
        if "planting_date" in self.model_fields_set and self.planting_date is None:
            if self.registration_kind != "existing" or self.planting_date_precision != "unknown":
                raise ValueError("Clearing a planting date requires an existing planting with explicitly unknown date precision.")
        if "estimated_harvest" in self.model_fields_set and self.estimated_harvest is None and self.registration_kind != "existing":
            raise ValueError("An optional next harvest date applies to an existing planting.")
        return self

    @field_validator("monitoring_enabled")
    @classmethod
    def monitoring_flag_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Monitoring enabled cannot be null.")
        return value

    @field_validator(
        "name", "variety", "field", "area_hectares",
        "status",
        "fertilizer_quantity_kg",
        mode="after",
    )
    @classmethod
    def required_crop_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value


class CropResponse(BaseModel):
    registration_kind: str = "legacy"
    crop_reference: str | None = None
    variety_reference: str | None = None
    section_id: int | None = None
    footprint_id: int | None = None
    estimated_capacity: int | None = None
    spacing_snapshot_json: str | None = None
    care_schedules_json: str | None = None
    planting_date_precision: str = "known"
    position_summary: dict | None = None
    ended_at: datetime | None = None
    area_cleared_at: datetime | None = None
    edit_version: int = Field(default=1, ge=1)

    monitoring_summary: dict | None = None
    monitoring_enabled: bool = False
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)
    estimated_progress: float | None = None
    estimated_growth_stage: str | None = None
    observed_growth_stage: str | None = None
    last_observation_date: date | None = None
    survival_count_date: date | None = None

    id: int
    crop_code: str
    name: str
    variety: str
    field: str

    area_hectares: float
    current_growth: float | None
    growth_stage: str
    quantity_planted: int | None
    current_surviving: int | None
    status: str
    readiness_status: str | None = None
    confirmed_ready_at: datetime | None = None
    confirmed_ready_by_user_id: int | None = None
    completed_at: datetime | None = None
    completed_by_user_id: int | None = None
    harvest_count: int = 0
    total_harvest_quantity_kg: float = 0
    previous_partial_harvest_total_kg: float = 0
    first_harvest_date: date | None = None
    final_harvest_date: date | None = None
    pending_harvest_task_id: int | None = None
    pending_harvest_task_code: str | None = None
    pending_harvest_task_status: str | None = None
    pending_harvest_type: str | None = None
    pending_harvest_message: str | None = None

    planting_date: date | None = None
    estimated_harvest: date | None = None

    fertilizer_quantity_kg: float
    fertilizer_date: date | None

    pesticide_used: str | None
    watering_schedule: str | None
    notes: str | None
    assigned_employee_id: int | None = None
    care_template_id: int | None = None
    care_protocol_name: str | None = None
    care_protocol_version: int | None = None
    care_protocol_status: str | None = None

    is_archived: bool
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# =========================================================
# SURVIVAL OBSERVATION (LEGACY/COMPATIBILITY ENDPOINT)
# =========================================================
# Growth percentage and stage are automatic from planting/harvest dates.

class CropGrowthCreate(BaseModel):
    observed_stage: str | None = Field(default=None, max_length=40)

    current_surviving: int | None = Field(default=None, ge=0)
    update_date: date
    notes: str | None = None


class CropGrowthResponse(BaseModel):
    task_submission_id: int | None = None
    related_task_id: int | None = None
    approved_by_user_id: int | None = None
    observed_stage: str | None = None

    id: int
    crop_id: int
    growth_percentage: float | None
    growth_stage: str | None
    current_surviving: int | None
    status: str
    update_date: date
    notes: str | None
    recorded_by_user_id: int | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# =========================================================
# YIELD / HARVEST RECORD
# =========================================================

class CropYieldCreate(BaseModel):
    harvested_part: str | None = Field(default=None, max_length=40)
    plants_harvested_out: int = Field(default=0, ge=0)
    harvest_date: date

    quantity_kg: float = Field(
        gt=0,
    )

    farm_use_quantity_kg: float = Field(default=0, ge=0)
    damaged_quantity_kg: float = Field(default=0, ge=0)
    reserved_quantity_kg: float = Field(default=0, ge=0)

    quality: str | None = Field(
        default=None,
        max_length=50,
    )

    harvest_type: str | None = Field(
        default=None,
        max_length=50,
    )

    notes: str | None = None
    performed_by_employee_id: int | None = Field(default=None, gt=0)
    manual_reason: str | None = Field(default=None, max_length=500)
    evidence_url: str | None = Field(default=None, max_length=500)
    final_harvest_confirmed: bool = False


class CropYieldResponse(BaseModel):
    harvested_part: str | None = None
    plants_harvested_out: int = 0
    id: int
    crop_id: int
    harvest_date: date
    quantity_kg: float
    farm_use_quantity_kg: float = 0
    damaged_quantity_kg: float = 0
    reserved_quantity_kg: float = 0
    quality: str | None
    harvest_type: str | None
    yield_per_hectare: float | None
    notes: str | None
    performed_by_employee_id: int | None = None
    related_task_id: int | None = None
    manual_reason: str | None = None
    evidence_url: str | None = None
    recorded_by_user_id: int | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# =========================================================
# PEST / DISEASE
# =========================================================

class CropPestDiseaseCreate(BaseModel):
    date_detected: date

    pest_disease_type: str = Field(
        min_length=2,
        max_length=120,
    )

    severity: str | None = Field(
        default=None,
        max_length=50,
    )

    affected_area: str | None = Field(
        default=None,
        max_length=100,
    )

    notes: str | None = None


class CropPestDiseaseUpdate(BaseModel):
    severity: str | None = Field(
        default=None,
        max_length=50,
    )

    affected_area: str | None = Field(
        default=None,
        max_length=100,
    )

    notes: str | None = None

    status: str | None = Field(
        default=None,
        max_length=20,
    )


class CropPestDiseaseResponse(BaseModel):
    id: int
    crop_id: int
    date_detected: date
    pest_disease_type: str
    severity: str | None
    affected_area: str | None
    notes: str | None
    status: str
    recorded_by_user_id: int | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class CropReopenRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    new_status: Literal["Harvesting", "Ready for Harvest"] = "Harvesting"


class CropReadyConfirmationRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)


# =========================================================
# FULL CROP DETAILS
# =========================================================

class CropDetailsResponse(CropResponse):
    growth_records: list[CropGrowthResponse] = Field(default_factory=list)
    yield_records: list[CropYieldResponse] = Field(default_factory=list)
    pest_diseases: list[CropPestDiseaseResponse] = Field(default_factory=list)
