from datetime import date, datetime
from typing import Literal

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

    area_hectares: float = Field(
        gt=0,
    )

    quantity_planted: int = Field(default=0, ge=0)
    current_surviving: int | None = Field(default=None, ge=0)

    planting_date: date
    estimated_harvest: date

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
        if self.estimated_harvest < self.planting_date:
            raise ValueError(
                "Estimated harvest date cannot "
                "be earlier than planting date."
            )

        return self


class CropUpdate(BaseModel):
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

    area_hectares: float | None = Field(
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

    @field_validator("monitoring_enabled")
    @classmethod
    def monitoring_flag_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Monitoring enabled cannot be null.")
        return value

    @field_validator(
        "name", "variety", "field", "area_hectares", "quantity_planted",
        "current_surviving", "status", "planting_date", "estimated_harvest",
        "fertilizer_quantity_kg",
        mode="after",
    )
    @classmethod
    def required_crop_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value


class CropResponse(BaseModel):
    monitoring_summary: dict | None = None
    monitoring_enabled: bool = False
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)
    estimated_progress: float = 0
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
    current_growth: float
    growth_stage: str
    quantity_planted: int
    current_surviving: int
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

    planting_date: date
    estimated_harvest: date

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
    growth_percentage: float
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
