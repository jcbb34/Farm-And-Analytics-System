from datetime import date, datetime, time

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    field_validator,
)


ALLOWED_ACTIVITY_STATUSES = {
    "Pending",
    "In Progress",
    "Submitted for Review",
    "Returned",
    "Completed",
    "Cancelled",
    "Resolved",
}

ALLOWED_ACTIVITY_PRIORITIES = {
    "Low",
    "Medium",
    "High",
    "Critical",
}


class FarmActivityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=80)
    related_to: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=150)
    description: str | None = None
    activity_date: date
    start_time: time
    end_time: time | None = None
    duration: str | None = Field(default=None, max_length=50)
    assigned_by: str = Field(min_length=1, max_length=120)
    assigned_to: str = Field(min_length=1, max_length=120)
    assigned_employee_id: int | None = Field(default=None, gt=0)
    instructions: str | None = None
    requires_review: bool = True
    requires_evidence: bool = False
    planned_quantity: float | None = Field(default=None, ge=0)
    planned_unit: str | None = Field(default=None, max_length=40)
    recurring_rule: str | None = Field(default=None, max_length=255)
    planned_inventory_item_id: int | None = Field(default=None, gt=0)
    planned_usage_type: str | None = Field(default=None, max_length=60)
    status: str = Field(default="Pending", max_length=30)
    priority: str = Field(default="Medium", max_length=20)

    # Optional source metadata for manually assigned tasks.
    # Automatic tasks are created by task_engine.py instead.
    source_module: str | None = Field(default=None, max_length=40)
    source_type: str | None = Field(default=None, max_length=80)
    source_record_id: int | None = None
    source_detail_id: int | None = None
    source_code: str | None = Field(default=None, max_length=60)
    source_path: str | None = Field(default=None, max_length=180)

    @field_validator("name", "category", "related_to", "location", "assigned_by", "assigned_to")
    @classmethod
    def nonblank_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A nonblank value is required.")
        return value

    @model_validator(mode="after")
    def validate_values(self):
        if self.status not in ALLOWED_ACTIVITY_STATUSES:
            raise ValueError("Invalid activity status.")

        if self.priority not in ALLOWED_ACTIVITY_PRIORITIES:
            raise ValueError("Invalid activity priority.")

        if (
            self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError(
                "End time must be later than start time."
            )

        return self


class FarmActivityUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
    )
    related_to: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    location: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    description: str | None = None
    activity_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration: str | None = Field(
        default=None,
        max_length=50,
    )
    assigned_by: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )
    assigned_to: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )
    assigned_employee_id: int | None = Field(default=None, gt=0)
    instructions: str | None = None
    requires_review: bool | None = None
    requires_evidence: bool | None = None
    planned_quantity: float | None = Field(default=None, ge=0)
    planned_unit: str | None = Field(default=None, max_length=40)
    recurring_rule: str | None = Field(default=None, max_length=255)
    status: str | None = Field(
        default=None,
        max_length=30,
    )
    priority: str | None = Field(
        default=None,
        max_length=20,
    )


class FarmActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_code: str
    name: str
    category: str
    related_to: str
    location: str
    description: str | None = None
    activity_date: date
    start_time: time
    end_time: time | None = None
    duration: str | None = None
    assigned_by: str
    assigned_to: str
    assigned_employee_id: int | None = None
    assignment_source: str = "manual"
    instructions: str | None = None
    requires_review: bool = True
    requires_evidence: bool = False
    planned_quantity: float | None = None
    planned_unit: str | None = None
    recurring_rule: str | None = None
    problem_report: str | None = None
    needs_reassignment: bool = False
    status: str
    priority: str

    is_automatic: bool = False
    source_module: str | None = None
    source_type: str | None = None
    source_record_id: int | None = None
    source_detail_id: int | None = None
    source_code: str | None = None
    source_path: str | None = None
    source_key: str | None = None
    completed_at: datetime | None = None

    # Backend-authoritative workflow metadata used by Dashboard and other
    # clients. These fields are derived from persisted task relationships and
    # permissions; clients must not infer workflow from activity titles.
    workflow_type: str = "standalone_activity"
    linked_task_id: int | None = None
    available_actions: list[str] = Field(default_factory=list)
    can_complete_directly: bool = False
    requires_employee_submission: bool = False
    requires_manager_review: bool = False

    is_archived: bool
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
