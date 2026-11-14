from datetime import date, time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class DirectCropSchedule(BaseModel):
    activity: Literal["watering", "observation"]
    enabled: bool = True
    start_date: date | None = None
    end_date: date | None = None
    frequency_days: int = Field(default=1, ge=1, le=365)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    employee_id: int | None = Field(default=None, gt=0)
    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=720)

    @model_validator(mode="after")
    def valid_interval(self):
        if not self.enabled:
            return self
        if self.start_date is None or self.start_time is None or self.duration_minutes is None:
            raise ValueError("An enabled activity needs a start date, time and actual duration.")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("Schedule end must follow its start.")
        if any(day not in range(7) for day in self.weekdays):
            raise ValueError("Choose weekdays between Monday (0) and Sunday (6).")
        if self.start_time.hour * 60 + self.start_time.minute + self.start_time.second / 60 + self.start_time.microsecond / 60000000 + self.duration_minutes > 1440:
            raise ValueError("A care activity must finish within its scheduled day.")
        return self


class LandAreaInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    area_m2: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=4)
    unavailable_area_m2: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=4)
    unavailable_reason: str | None = Field(default=None, max_length=500)
    expected_version: int | None = None

    @model_validator(mode="after")
    def area_valid(self):
        if self.area_m2 is not None and self.unavailable_area_m2 > self.area_m2:
            raise ValueError("Unavailable space cannot exceed the measured area.")
        if self.unavailable_area_m2 and not (self.unavailable_reason or "").strip():
            raise ValueError("Describe the buildings, livestock facilities, paths, drainage or other unavailable space.")
        return self


class FarmAreaInput(BaseModel):
    total_area_m2: Decimal = Field(gt=0, max_digits=16, decimal_places=4)
    unavailable_area_m2: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=4)
    unavailable_reason: str | None = Field(default=None, max_length=500)
    expected_version: int | None = None


class PositionEventInput(BaseModel):
    event_type: Literal["mortality", "harvested_out", "removed", "verified_cleared", "blocked", "unblocked", "replacement"]
    event_date: date
    quantity: int = Field(gt=0)
    notes: str = Field(min_length=3, max_length=2000)


class EndPlantingInput(BaseModel):
    expected_version: int
    reason: str = Field(min_length=3, max_length=2000)
    confirm_area_cleared: bool = False


class SpacingAdjustment(BaseModel):
    row_spacing_m: Decimal = Field(gt=0, max_digits=10, decimal_places=4)
    plant_spacing_m: Decimal = Field(gt=0, max_digits=10, decimal_places=4)
    layout: Literal["square", "rectangular"] = "rectangular"
    evidence_scope: str = Field(min_length=5)
    source_url: str = Field(min_length=8, max_length=1000)

    @model_validator(mode="after")
    def valid_layout(self):
        if self.layout == "square" and self.row_spacing_m != self.plant_spacing_m:
            raise ValueError("Square layout needs equal row and plant spacing; choose Rectangular for unequal distances.")
        return self
