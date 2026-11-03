from datetime import datetime, date, time
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator
from app.core.farm_time import farm_timezone

KINDS = Literal["Farm Event", "Planned No-Work Day", "Emergency Suspension"]


class FarmEventInput(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    kind: KINDS
    starts_at: datetime
    ends_at: datetime
    scope_type: Literal["All", "Employees", "Areas"] = "All"
    scope_values: list[str] = Field(default_factory=list, max_length=300)
    reason: str = Field(min_length=3, max_length=3000)
    instructions: str = Field(default="", max_length=5000)
    source_name: str = Field(default="", max_length=150)
    source_reference: str = Field(default="", max_length=600)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def local_clock(cls, value):
        return value.astimezone(farm_timezone()).replace(tzinfo=None) if value.tzinfo else value

    @field_validator("title", "reason")
    @classmethod
    def required_text(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Enter at least three non-space characters.")
        return value

    @model_validator(mode="after")
    def validate_event(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("End must be after start.")
        if (self.ends_at - self.starts_at).days > 366:
            raise ValueError("A declaration may span at most 366 days.")
        self.scope_values = sorted({str(x).strip() for x in self.scope_values if str(x).strip()})
        if self.scope_type != "All" and not self.scope_values:
            raise ValueError("Select at least one affected employee or area.")
        if self.scope_type == "All":
            self.scope_values = []
        if any(len(x) > 150 for x in self.scope_values):
            raise ValueError("Scope entries must be at most 150 characters.")
        return self


class FarmEventCreate(FarmEventInput):
    request_key: str = Field(min_length=16, max_length=100)


class FarmEventUpdate(FarmEventInput):
    expected_version: int = Field(ge=1)


class EventDecision(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=3000)
    preview_token: str | None = None

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("A reason is required.")
        return value.strip()


class ChecklistDecision(BaseModel):
    expected_version: int = Field(ge=1)
    item_id: str = Field(max_length=60)
    completed: bool


class EventAcknowledgement(BaseModel):
    notice_version: int = Field(ge=1)


class EventReportInput(BaseModel):
    area: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=3, max_length=5000)


class EventTaskDecision(BaseModel):
    expected_version: int = Field(ge=1)
    action: Literal["Release", "Reschedule", "Reassign", "Cancel", "Essential Duty"]
    reason: str = Field(min_length=3, max_length=3000)
    employee_id: int | None = Field(default=None, gt=0)
    new_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("A reason is required.")
        return value.strip()
