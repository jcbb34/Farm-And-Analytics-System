from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MonitoringObservation(BaseModel):
    resource_type: Literal["Crop", "Livestock"]
    observation_date: date
    observed_stage: str | None = Field(default=None, max_length=40)
    current_surviving: int | None = Field(default=None, ge=0)
    animals_measured: int | None = Field(default=None, ge=1)
    average_weight_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    total_measured_weight_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    min_weight_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    max_weight_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_observation(self):
        if self.resource_type == "Crop":
            from app.services.crop_growth import GROWTH_STAGES
            if self.observed_stage not in GROWTH_STAGES[:-2] or self.current_surviving is None:
                raise ValueError("Enter a crop observation stage and surviving plant count.")
        else:
            if self.animals_measured is None or self.average_weight_kg is None:
                raise ValueError("Enter the number of animals measured and average weight.")
            if self.animals_measured > 1 and (self.min_weight_kg is None or self.max_weight_kg is None):
                raise ValueError("Record minimum and maximum measured weights when measuring more than one animal.")
            low = self.min_weight_kg or self.average_weight_kg
            high = self.max_weight_kg or self.average_weight_kg
            if not low <= self.average_weight_kg <= high:
                raise ValueError("Minimum weight must be <= average weight <= maximum weight.")
            if self.total_measured_weight_kg is not None:
                if abs(self.total_measured_weight_kg / self.animals_measured - self.average_weight_kg) > 0.05:
                    raise ValueError("Average weight must match the total measured weight divided by animals measured.")
        return self
