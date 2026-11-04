from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


ALLOWED_HEALTH_STATUSES = {
    "Healthy",
    "Mixed",
    "Under Treatment",
    "At Risk",
    "Sick",
}

ALLOWED_GROWTH_STATUSES = {
    "Newborn",
    "Brooding",
    "Young",
    "Growing",
    "Pre-Laying",
    "Laying",
    "Finisher",
    "Mature",
    "Breeding",
    "Pregnant",
    "Nursing",
    "Weaned",
    "Lactating",
    "Production",
    "Ready for Market",
}

ALLOWED_VACCINATION_STATUSES = {
    "Not Vaccinated",
    "Scheduled",
    "Due",
    "Due Soon",
    "Up to Date",
}


def _health_status_from_counts(healthy: int, at_risk: int, sick: int, treatment: int) -> str:
    non_zero = [
        ("Healthy", healthy),
        ("At Risk", at_risk),
        ("Sick", sick),
        ("Under Treatment", treatment),
    ]
    present = [label for label, count in non_zero if count > 0]
    if len(present) == 1:
        return present[0]
    return "Mixed" if present else "Healthy"


class LivestockCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    monitoring_enabled: bool = False
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)

    record_name: str = Field(min_length=2, max_length=120)
    animal_type: str = Field(min_length=2, max_length=50)
    breed: str = Field(min_length=1, max_length=100)
    quantity: int = Field(default=1, ge=1)
    sex: str = Field(default="Mixed", max_length=20)

    record_type: str = Field(default="Batch", max_length=20)
    lifecycle_status: str = Field(default="Active", max_length=30)
    pen_id: int | None = Field(default=None, ge=1)
    male_quantity: int = Field(default=0, ge=0)
    female_quantity: int = Field(default=0, ge=0)
    unknown_sex_quantity: int = Field(default=0, ge=0)

    date_of_birth: date | None = None
    weight_kg: float = Field(gt=0)
    min_weight_kg: float | None = Field(default=None, gt=0)
    max_weight_kg: float | None = Field(default=None, gt=0)
    pen_location: str = Field(min_length=1, max_length=120)

    health_status: str = Field(default="Healthy", max_length=40)
    healthy_quantity: int = Field(default=0, ge=0)
    at_risk_quantity: int = Field(default=0, ge=0)
    sick_quantity: int = Field(default=0, ge=0)
    under_treatment_quantity: int = Field(default=0, ge=0)
    growth_status: str = Field(default="Growing", max_length=40)
    production_purpose: str = Field(default="General", max_length=80)
    last_checkup: date | None = None
    health_notes: str | None = None

    vaccination_status: str = Field(default="Not Vaccinated", max_length=40)
    next_vaccination: date | None = None

    feed_times: str | None = Field(default=None, max_length=150)
    feed_type: str | None = Field(default=None, max_length=150)
    daily_feed_kg: float = Field(default=0, ge=0)
    feeding_notes: str | None = None
    feed_inventory_item_id: int | None = Field(default=None, ge=1)

    production_output: str | None = None

    age_is_estimated: bool = False
    estimated_age_days: int | None = Field(default=None, ge=0)
    estimated_age_as_of_date: date | None = None
    estimated_age_confidence: Literal["Low", "Medium", "High"] | None = None
    estimated_age_source: str | None = Field(default=None, max_length=255)
    acquisition_stage: str | None = Field(default=None, max_length=40)
    acquisition_vaccination_history: str | None = None
    acquisition_treatment_history: str | None = None
    feeding_plan_name: str | None = Field(default=None, max_length=150)
    assigned_employee_id: int | None = Field(default=None, ge=1)
    care_template_id: int | None = Field(default=None, ge=1)

    date_acquired: date
    acquired_from: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def validate_values(self):
        if self.date_of_birth is None:
            if self.estimated_age_days is None:
                raise ValueError("Provide a date of birth/hatch or an estimated biological age in days.")
            if self.estimated_age_as_of_date is None:
                raise ValueError("Estimated age requires an estimation date.")
            if not self.estimated_age_confidence:
                raise ValueError("Estimated age requires a confidence level.")
            if not (self.estimated_age_source or "").strip():
                raise ValueError("Estimated age requires a source or basis.")
            self.age_is_estimated = True
        else:
            self.age_is_estimated = False

        if self.date_of_birth is not None and self.date_acquired < self.date_of_birth:
            raise ValueError("Date acquired cannot be earlier than date of birth/hatch.")
        if self.last_checkup is not None and self.date_of_birth is not None and self.last_checkup < self.date_of_birth:
            raise ValueError("Last checkup cannot be earlier than date of birth/hatch.")
        if self.next_vaccination is not None and self.date_of_birth is not None and self.next_vaccination < self.date_of_birth:
            raise ValueError("Next vaccination cannot be earlier than date of birth/hatch.")
        if self.health_status not in ALLOWED_HEALTH_STATUSES:
            raise ValueError("Invalid livestock health status.")
        if self.growth_status not in ALLOWED_GROWTH_STATUSES:
            raise ValueError("Invalid livestock growth status.")
        if self.vaccination_status not in ALLOWED_VACCINATION_STATUSES:
            raise ValueError("Invalid livestock vaccination status.")
        if self.record_type not in {"Batch", "Individual"}:
            raise ValueError("Record type must be Batch or Individual.")
        if self.record_type == "Individual" and self.quantity != 1:
            raise ValueError("Individual livestock records must contain exactly one animal.")

        sex_total = self.male_quantity + self.female_quantity + self.unknown_sex_quantity
        if sex_total == 0:
            if self.sex.strip().lower() == "male":
                self.male_quantity = self.quantity
            elif self.sex.strip().lower() == "female":
                self.female_quantity = self.quantity
            else:
                self.unknown_sex_quantity = self.quantity
        elif sex_total != self.quantity:
            raise ValueError("Male + Female + Unknown quantities must equal the livestock quantity.")

        health_total = (
            self.healthy_quantity
            + self.at_risk_quantity
            + self.sick_quantity
            + self.under_treatment_quantity
        )
        if health_total == 0:
            if self.health_status == "At Risk":
                self.at_risk_quantity = self.quantity
            elif self.health_status == "Sick":
                self.sick_quantity = self.quantity
            elif self.health_status == "Under Treatment":
                self.under_treatment_quantity = self.quantity
            else:
                self.healthy_quantity = self.quantity
        elif health_total != self.quantity:
            raise ValueError("Healthy + At Risk + Sick + Under Treatment quantities must equal the livestock quantity.")
        self.health_status = _health_status_from_counts(
            self.healthy_quantity,
            self.at_risk_quantity,
            self.sick_quantity,
            self.under_treatment_quantity,
        )

        if self.min_weight_kg is not None and self.max_weight_kg is not None:
            if self.min_weight_kg > self.max_weight_kg:
                raise ValueError("Minimum weight cannot exceed maximum weight.")
        return self


class LivestockUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    monitoring_enabled: bool | None = None
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)

    record_name: str | None = Field(default=None, min_length=2, max_length=120)
    animal_type: str | None = Field(default=None, min_length=2, max_length=50)
    breed: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: int | None = Field(default=None, ge=1)
    sex: str | None = Field(default=None, max_length=20)

    record_type: str | None = Field(default=None, max_length=20)
    lifecycle_status: str | None = Field(default=None, max_length=30)
    pen_id: int | None = Field(default=None, ge=1)
    male_quantity: int | None = Field(default=None, ge=0)
    female_quantity: int | None = Field(default=None, ge=0)
    unknown_sex_quantity: int | None = Field(default=None, ge=0)

    date_of_birth: date | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    min_weight_kg: float | None = Field(default=None, gt=0)
    max_weight_kg: float | None = Field(default=None, gt=0)
    pen_location: str | None = Field(default=None, min_length=1, max_length=120)

    health_status: str | None = Field(default=None, max_length=40)
    healthy_quantity: int | None = Field(default=None, ge=0)
    at_risk_quantity: int | None = Field(default=None, ge=0)
    sick_quantity: int | None = Field(default=None, ge=0)
    under_treatment_quantity: int | None = Field(default=None, ge=0)
    growth_status: str | None = Field(default=None, max_length=40)
    production_purpose: str | None = Field(default=None, max_length=80)
    last_checkup: date | None = None
    health_notes: str | None = None

    vaccination_status: str | None = Field(default=None, max_length=40)
    next_vaccination: date | None = None

    feed_times: str | None = Field(default=None, max_length=150)
    feed_type: str | None = Field(default=None, max_length=150)
    daily_feed_kg: float | None = Field(default=None, ge=0)
    feeding_notes: str | None = None
    feed_inventory_item_id: int | None = Field(default=None, ge=1)

    production_output: str | None = None

    age_is_estimated: bool | None = None
    estimated_age_days: int | None = Field(default=None, ge=0)
    estimated_age_as_of_date: date | None = None
    estimated_age_confidence: Literal["Low", "Medium", "High"] | None = None
    estimated_age_source: str | None = Field(default=None, max_length=255)
    acquisition_stage: str | None = Field(default=None, max_length=40)
    acquisition_vaccination_history: str | None = None
    acquisition_treatment_history: str | None = None
    feeding_plan_name: str | None = Field(default=None, max_length=150)
    assigned_employee_id: int | None = Field(default=None, ge=1)
    care_template_id: int | None = Field(default=None, ge=1)
    future_care_task_action: Literal["keep", "resolve"] | None = None

    date_acquired: date | None = None
    acquired_from: str | None = Field(default=None, max_length=150)

    @field_validator("monitoring_enabled")
    @classmethod
    def monitoring_flag_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Monitoring enabled cannot be null.")
        return value

    @field_validator(
        "record_name", "animal_type", "breed", "quantity", "sex",
        "record_type", "lifecycle_status", "male_quantity", "female_quantity",
        "unknown_sex_quantity", "weight_kg", "pen_location",
        "health_status", "healthy_quantity", "at_risk_quantity", "sick_quantity",
        "under_treatment_quantity", "growth_status", "production_purpose",
        "vaccination_status", "daily_feed_kg", "date_acquired",
        mode="after",
    )
    @classmethod
    def required_livestock_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value


class LivestockVaccinationCreate(BaseModel):
    vaccine: str = Field(min_length=1, max_length=150)
    date_administered: date
    next_due: date | None = None
    status: str = Field(default="Up to Date", max_length=40)
    administered_by: str | None = Field(default=None, max_length=150)
    inventory_item_id: int | None = Field(default=None, ge=1)
    quantity_used: float | None = Field(default=None, gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_vaccination(self):
        if self.next_due is not None and self.next_due < self.date_administered:
            raise ValueError("Next vaccination date cannot be earlier than administration date.")
        if self.status not in ALLOWED_VACCINATION_STATUSES:
            raise ValueError("Invalid vaccination status.")
        if (self.inventory_item_id is None) != (self.quantity_used is None):
            raise ValueError("Select a vaccine Inventory item and enter the quantity used together.")
        return self


class LivestockVaccinationResponse(BaseModel):
    id: int
    livestock_id: int
    vaccine: str
    date_administered: date
    next_due: date | None
    status: str
    administered_by: str | None
    inventory_item_id: int | None = None
    quantity_used: float | None = None
    unit: str | None = None
    notes: str | None
    recorded_by_user_id: int | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LivestockVaccinationScheduleResponse(BaseModel):
    task_id: int | None = None
    activity_code: str | None = None
    title: str
    scheduled_date: date
    status: str
    assigned_employee_id: int | None = None
    assigned_employee_name: str | None = None
    inventory_item_id: int | None = None
    inventory_item_name: str | None = None
    planned_quantity: float | None = None
    planned_unit: str | None = None
    actual_quantity: float | None = None
    actual_unit: str | None = None
    performed_by: str | None = None
    completed_at: datetime | None = None
    source: str = "Task Management"



class LivestockFeedingCreate(BaseModel):
    inventory_item_id: int = Field(ge=1)
    feeding_date: date
    feeding_slot: str = Field(min_length=1, max_length=40)
    actual_quantity_kg: float | None = Field(default=None, gt=0)
    notes: str | None = None
    evidence_url: str | None = Field(default=None, max_length=500)
    performed_by_employee_id: int | None = Field(default=None, gt=0)


class LivestockFeedingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    livestock_id: int
    inventory_item_id: int
    feeding_date: date
    feeding_slot: str
    scheduled_times: str | None = None
    feed_type: str
    planned_quantity_kg: float
    actual_quantity_kg: float
    notes: str | None = None
    recorded_by_user_id: int | None = None
    confirmed_at: datetime


class LivestockGrowthCreate(BaseModel):
    measurement_date: date
    weight_kg: float = Field(gt=0)
    animals_measured: int | None = Field(default=None, ge=1)
    total_measured_weight_kg: float | None = Field(default=None, gt=0)
    min_weight_kg: float | None = Field(default=None, gt=0)
    max_weight_kg: float | None = Field(default=None, gt=0)
    measurement_basis: str = Field(default="Average", max_length=30)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_growth(self):
        if self.min_weight_kg is not None and self.max_weight_kg is not None and self.min_weight_kg > self.max_weight_kg:
            raise ValueError("Minimum weight cannot exceed maximum weight.")
        if self.min_weight_kg is not None and self.weight_kg < self.min_weight_kg:
            raise ValueError("Average weight cannot be lower than the minimum weight.")
        if self.max_weight_kg is not None and self.weight_kg > self.max_weight_kg:
            raise ValueError("Average weight cannot exceed the maximum weight.")
        return self


class LivestockGrowthResponse(BaseModel):
    task_submission_id: int | None = None
    related_task_id: int | None = None
    approved_by_user_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
    id: int
    livestock_id: int
    measurement_date: date
    weight_kg: float
    animals_measured: int | None = None
    total_measured_weight_kg: float | None = None
    min_weight_kg: float | None = None
    max_weight_kg: float | None = None
    measurement_basis: str = "Average"
    previous_weight_kg: float | None = None
    weight_change_kg: float | None = None
    days_since_previous: int | None = None
    average_daily_gain_kg: float | None = None
    biological_age_days: int | None = None
    expected_stage: str | None = None
    expected_min_weight_kg: float | None = None
    expected_max_weight_kg: float | None = None
    growth_profile_family_code: str | None = None
    growth_profile_version: int | None = None
    growth_profile_status: str | None = None
    deviation_status: str | None = None
    deviation_message: str | None = None
    notes: str | None = None
    recorded_by_user_id: int | None = None
    created_at: datetime


class LivestockResponse(BaseModel):
    @computed_field
    @property
    def feeding_slots(self) -> list[str]:
        from app.services.task_engine import _feeding_occurrences
        return [slot for _, slot, _ in _feeding_occurrences(self.feed_times)]

    monitoring_summary: dict | None = None
    monitoring_enabled: bool = False
    monitoring_start_date: date | None = None
    monitoring_end_date: date | None = None
    monitoring_frequency_days: int | None = Field(default=None, ge=1, le=365)

    id: int
    animal_code: str
    record_name: str
    animal_type: str
    breed: str
    quantity: int
    sex: str

    record_type: str
    lifecycle_status: str
    pen_id: int | None = None
    origin_livestock_id: int | None = None
    male_quantity: int
    female_quantity: int
    unknown_sex_quantity: int

    date_of_birth: date | None
    weight_kg: float
    min_weight_kg: float | None = None
    max_weight_kg: float | None = None
    pen_location: str

    health_status: str
    healthy_quantity: int
    at_risk_quantity: int
    sick_quantity: int
    under_treatment_quantity: int
    growth_status: str
    production_purpose: str
    last_checkup: date | None
    health_notes: str | None

    vaccination_status: str
    next_vaccination: date | None

    feed_times: str | None
    feed_type: str | None
    daily_feed_kg: float
    feeding_notes: str | None
    feed_inventory_item_id: int | None = None

    production_output: str | None
    age_is_estimated: bool = False
    estimated_age_days: int | None = None
    estimated_age_as_of_date: date | None = None
    estimated_age_confidence: str | None = None
    estimated_age_source: str | None = None
    acquisition_stage: str | None = None
    acquisition_vaccination_history: str | None = None
    acquisition_treatment_history: str | None = None
    medical_history_status: str = "Unknown - Needs Review"
    feeding_plan_name: str | None = None
    assigned_employee_id: int | None = None
    care_template_id: int | None = None
    care_protocol_name: str | None = None
    care_protocol_version: int | None = None
    care_protocol_status: str | None = None
    date_acquired: date
    acquired_from: str | None

    is_archived: bool
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LivestockDetailsResponse(LivestockResponse):
    vaccination_records: list[LivestockVaccinationResponse] = Field(default_factory=list)
    feeding_records: list[LivestockFeedingResponse] = Field(default_factory=list)
    growth_records: list[LivestockGrowthResponse] = Field(default_factory=list)


class GrowthAssessmentPreviewRequest(BaseModel):
    animal_type: str = Field(min_length=2, max_length=50)
    breed: str | None = Field(default=None, max_length=100)
    production_purpose: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    estimated_age_days: int | None = Field(default=None, ge=0)
    estimated_age_as_of_date: date | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    as_of_date: date | None = None

    @model_validator(mode="after")
    def validate_age_input(self):
        if self.date_of_birth is None and self.estimated_age_days is not None and self.estimated_age_as_of_date is None:
            raise ValueError("Estimated age requires an estimation date.")
        return self


class GrowthAssessmentResponse(BaseModel):
    as_of_date: date
    age_days: int | None = None
    age_source: str
    current_stage: str | None = None
    suggested_stage: str | None = None
    suggestion_reason: str
    expected_min_weight_kg: float | None = None
    expected_max_weight_kg: float | None = None
    deviation_status: str | None = None
    deviation_message: str | None = None
    profile_id: int | None = None
    profile_family_code: str | None = None
    profile_version: int | None = None
    profile_name: str | None = None
    profile_status: str | None = None
    approval_status: str | None = None
    source_title: str | None = None
    source_url: str | None = None


class GrowthStageOverrideRequest(BaseModel):
    stage: str = Field(min_length=2, max_length=40)
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str):
        if value not in ALLOWED_GROWTH_STATUSES:
            raise ValueError("Invalid livestock growth stage.")
        return value


class GrowthStageOverrideAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    livestock_id: int
    previous_stage: str
    suggested_stage: str | None = None
    override_stage: str
    reason: str
    overridden_by_user_id: int | None = None
    created_at: datetime


class GrowthProfileStageInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sequence_number: int = Field(ge=1)
    stage_name: str = Field(min_length=2, max_length=40)
    age_start_days: int = Field(ge=0)
    age_end_days: int | None = Field(default=None, ge=0)
    expected_min_weight_kg: float | None = Field(default=None, ge=0)
    expected_max_weight_kg: float | None = Field(default=None, ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_stage_window(self):
        if self.age_end_days is not None and self.age_end_days < self.age_start_days:
            raise ValueError("Stage age end cannot be earlier than age start.")
        if self.expected_min_weight_kg is not None and self.expected_max_weight_kg is not None and self.expected_max_weight_kg < self.expected_min_weight_kg:
            raise ValueError("Expected maximum weight cannot be below expected minimum weight.")
        return self


class GrowthProfileCreate(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    species: str = Field(min_length=2, max_length=50)
    breed_strain: str | None = Field(default=None, max_length=100)
    production_purpose: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=20)
    source_title: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=500)
    source_notes: str | None = None
    last_reviewed_date: date | None = None
    approval_status: str = Field(default="Draft - Needs Veterinarian/Agriculturist Approval", max_length=100)
    effective_from: date | None = None
    effective_to: date | None = None
    stages: list[GrowthProfileStageInput] = Field(min_length=1)


class GrowthProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profile_family_code: str
    version: int
    name: str
    species: str
    breed_strain: str | None = None
    production_purpose: str | None = None
    sex: str | None = None
    status: str
    approval_status: str
    effective_from: date | None = None
    effective_to: date | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_notes: str | None = None
    last_reviewed_date: date | None = None
    is_active: bool
    stages: list[GrowthProfileStageInput] = Field(default_factory=list)


class PenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    purpose: str = Field(default="General", max_length=60)
    animal_type: str | None = Field(default=None, max_length=50)
    capacity: int | None = Field(default=None, ge=1)
    location_area: str | None = Field(default=None, max_length=150)
    status: str = Field(default="Active", max_length=30)
    notes: str | None = None


class PenUpdate(PenCreate):
    pass


class PenTransferCreate(BaseModel):
    pen_id: int = Field(ge=1)
    event_date: date
    reason: str | None = None


class BatchSplitCreate(BaseModel):
    quantity: int = Field(ge=1)
    record_name: str | None = Field(default=None, max_length=120)
    pen_id: int | None = Field(default=None, ge=1)
    event_date: date
    reason: str | None = None
    male_quantity: int = Field(default=0, ge=0)
    female_quantity: int = Field(default=0, ge=0)
    unknown_sex_quantity: int = Field(default=0, ge=0)
    healthy_quantity: int = Field(default=0, ge=0)
    at_risk_quantity: int = Field(default=0, ge=0)
    sick_quantity: int = Field(default=0, ge=0)
    under_treatment_quantity: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_split(self):
        if self.male_quantity + self.female_quantity + self.unknown_sex_quantity != self.quantity:
            raise ValueError("Split Male + Female + Unknown quantities must equal the split quantity.")
        if self.healthy_quantity + self.at_risk_quantity + self.sick_quantity + self.under_treatment_quantity != self.quantity:
            raise ValueError("Split health quantities must equal the split quantity.")
        return self
