from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.farm_time import farm_today
from app.schemas.monitoring import MonitoringObservation
from app.schemas.personal_details import PersonalDetails, PersonalDetailsPayload, PersonalDetailsCreationPayload


TASK_STATUSES = {
    "Pending", "In Progress", "Submitted for Review", "Returned",
    "Completed", "Cancelled", "Resolved", "Voided",
}
ATTENDANCE_STATUSES = {"Not Checked In", "On Time", "Late", "Present", "Checked Out", "Early Departure", "Missing Check Out", "Absent", "Sick"}
LEAVE_TYPES = {"Sick Leave", "Vacation Leave", "Emergency Leave", "Day Off", "Other"}
LEAVE_STATUSES = {"Pending", "Approved", "Rejected", "Cancelled"}
SHIFT_STATUSES = {"Scheduled", "Confirmed", "Completed", "Cancelled"}
SCHEDULE_EXCEPTION_TYPES = {"Working Day Override", "Rest Day Override", "Special Day Off", "Changed Shift"}


class FarmPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


class EmployeePositionResponse(BaseModel):
    id: int
    name: str
    category: str
    description: str | None = None
    is_primary: bool = False


class WorkScheduleDayInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    state: Literal["Working Day", "Rest Day"]
    start_time: time | None = None
    end_time: time | None = None
    break_start_time: time | None = None
    break_end_time: time | None = None

    @model_validator(mode="after")
    def validate_day(self):
        if self.state == "Rest Day":
            self.start_time = None
            self.end_time = None
            self.break_start_time = None
            self.break_end_time = None
            return self
        if self.start_time is None or self.end_time is None:
            raise ValueError("Working days require a shift start and end time.")
        if self.end_time <= self.start_time:
            raise ValueError("Shift end time must be after the start time.")
        if (self.break_start_time is None) != (self.break_end_time is None):
            raise ValueError("Provide both break start and break end, or leave both blank.")
        if self.break_start_time is not None:
            if self.break_end_time <= self.break_start_time:
                raise ValueError("Break end time must be after break start time.")
            if self.break_start_time < self.start_time or self.break_end_time > self.end_time:
                raise ValueError("Break time must stay within the work shift.")
        return self


class WeeklyScheduleInput(BaseModel):
    effective_from: date
    effective_to: date | None = None
    timezone: str = Field(default="Asia/Manila", max_length=64)
    schedule_type: Literal["Fixed", "Rotating / No Fixed Rest Day"] = "Fixed"
    backup_employee_id: int | None = Field(default=None, gt=0)
    days: list[WorkScheduleDayInput] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Schedule end date cannot be before the effective start date.")
        day_numbers = [item.day_of_week for item in self.days]
        if sorted(day_numbers) != list(range(7)):
            raise ValueError("Weekly schedule must explicitly configure Monday through Sunday exactly once.")
        working = sum(1 for item in self.days if item.state == "Working Day")
        resting = 7 - working
        if working < 1:
            raise ValueError("At least one Working Day is required.")
        if self.schedule_type == "Fixed" and resting < 1:
            raise ValueError("A fixed weekly schedule requires at least one Rest Day.")
        if self.timezone != "Asia/Manila":
            raise ValueError("The farm operational timezone must be Asia/Manila.")
        return self


class WorkScheduleDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    day_of_week: int
    is_working_day: bool
    start_time: time | None = None
    end_time: time | None = None
    break_start_time: time | None = None
    break_end_time: time | None = None


class WeeklyScheduleResponse(BaseModel):
    id: int
    employee_id: int
    effective_from: date
    effective_to: date | None = None
    timezone: str
    schedule_type: str
    backup_employee_id: int | None = None
    backup_employee_name: str | None = None
    status: str
    days: list[WorkScheduleDayResponse] = Field(default_factory=list)


class AvailabilityDayResponse(BaseModel):
    suspensions: list[dict] = Field(default_factory=list)
    attendance_suspended_now: bool = False
    suspension_full_shift: bool = False
    employee_id: int
    work_date: date
    available: bool
    status: str
    reason: str
    schedule_status: str
    schedule_id: int | None = None
    schedule_exception_id: int | None = None
    exception_type: str | None = None
    is_working_day: bool | None = None
    start_time: time | None = None
    end_time: time | None = None
    break_start_time: time | None = None
    break_end_time: time | None = None
    attendance_status: str | None = None
    leave_id: int | None = None


class EmployeeCreate(PersonalDetailsCreationPayload):
    full_name: str = Field(min_length=2, max_length=120)
    contact_number: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=100)  # legacy compatibility
    primary_position_id: int | None = Field(default=None, gt=0)
    position_ids: list[int] = Field(default_factory=list, max_length=5)
    date_hired: date | None = None
    employment_type: str | None = Field(default=None, max_length=30)
    assigned_area: str | None = Field(default=None, max_length=120)
    skills: str | None = None
    employment_status: str = Field(default="Active", max_length=30)
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_relationship: str | None = Field(default=None, max_length=60)
    emergency_contact_number: str | None = Field(default=None, max_length=20)
    login_user_id: int | None = Field(default=None, gt=0)
    create_login_account: bool = False
    login_username: str | None = Field(default=None, min_length=3, max_length=50)
    login_password: str | None = Field(default=None, min_length=8, max_length=128)
    notes: str | None = None
    weekly_schedule: WeeklyScheduleInput

    @model_validator(mode="after")
    def validate_positions(self):
        values = list(dict.fromkeys(self.position_ids))
        if self.primary_position_id and self.primary_position_id not in values:
            values.insert(0, self.primary_position_id)
        if len(values) > 5:
            raise ValueError("An employee can have a maximum of 5 active positions.")
        self.position_ids = values
        if self.create_login_account:
            if self.login_user_id:
                raise ValueError("Choose either an existing login account or create a new employee login, not both.")
            if not (self.login_username or "").strip():
                raise ValueError("A username is required when creating an employee login.")
            if not self.login_password:
                raise ValueError("A password is required when creating an employee login.")
        return self


class EmployeeUpdate(PersonalDetailsPayload):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    contact_number: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=100)
    primary_position_id: int | None = Field(default=None, gt=0)
    position_ids: list[int] | None = Field(default=None, max_length=5)
    date_hired: date | None = None
    employment_type: str | None = Field(default=None, max_length=30)
    assigned_area: str | None = Field(default=None, max_length=120)
    skills: str | None = None
    employment_status: str | None = Field(default=None, max_length=30)
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_relationship: str | None = Field(default=None, max_length=60)
    emergency_contact_number: str | None = Field(default=None, max_length=20)
    login_user_id: int | None = Field(default=None, gt=0)
    create_login_account: bool | None = None
    login_username: str | None = Field(default=None, min_length=3, max_length=50)
    login_password: str | None = Field(default=None, min_length=8, max_length=128)
    notes: str | None = None
    # Structured current farm assignments. These update which active Crop/Livestock
    # records this employee normally cares for; historical tasks are intentionally
    # not rewritten when these lists change.
    crop_assignment_ids: list[int] | None = None
    livestock_assignment_ids: list[int] | None = None
    weekly_schedule: WeeklyScheduleInput | None = None

    @model_validator(mode="after")
    def validate_positions(self):
        if self.position_ids is not None:
            values = list(dict.fromkeys(self.position_ids))
            if self.primary_position_id and self.primary_position_id not in values:
                values.insert(0, self.primary_position_id)
            if len(values) > 5:
                raise ValueError("An employee can have a maximum of 5 active positions.")
            self.position_ids = values
        if self.create_login_account:
            if not (self.login_username or "").strip():
                raise ValueError("A username is required when creating an employee login.")
            if not self.login_password:
                raise ValueError("A password is required when creating an employee login.")
        return self


class EmployeeResponse(BaseModel):
    personal_details: PersonalDetails | None = None
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str
    contact_number: str | None
    email: str | None = None
    address: str | None = None
    position: str | None
    primary_position_id: int | None = None
    positions: list[EmployeePositionResponse] = Field(default_factory=list)
    date_hired: date | None = None
    employment_type: str | None = None
    assigned_area: str | None = None
    skills: str | None = None
    employment_status: str
    emergency_contact_name: str | None = None
    emergency_contact_relationship: str | None = None
    emergency_contact_number: str | None = None
    login_user_id: int | None
    login_username: str | None = None
    login_status: str | None = None
    account_status: str = "No Login Account"
    portal_assignment_ready: bool = False
    account_repair_available: bool = False
    account_issue: str | None = None
    notes: str | None
    is_archived: bool
    archived_at: datetime | None = None
    archived_by_user_id: int | None = None
    archived_by_name: str | None = None
    archive_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    schedule_status: str = "Needs Setup"
    weekly_schedule_summary: str | None = None
    next_rest_day: date | None = None
    weekly_schedule: WeeklyScheduleResponse | None = None




class EmployeeSelfProfileResponse(BaseModel):
    """Intentionally small employee-facing profile; excludes private HR fields."""
    id: int
    employee_code: str
    full_name: str
    username: str
    contact_number: str | None = None
    email: str | None = None
    position: str | None = None
    assigned_area: str | None = None
    employment_status: str

class EmployeeWorkAssignmentItem(BaseModel):
    id: int
    record_code: str
    name: str
    category: str
    location: str | None = None
    detail: str | None = None
    assigned_employee_id: int | None = None
    assigned_employee_name: str | None = None
    is_assigned_to_employee: bool = False


class EmployeeWorkAssignmentsResponse(BaseModel):
    employee_id: int
    employee_name: str
    crops: list[EmployeeWorkAssignmentItem] = Field(default_factory=list)
    livestock: list[EmployeeWorkAssignmentItem] = Field(default_factory=list)


class EmployeeStatusUpdate(BaseModel):
    employment_status: str = Field(max_length=30)

    @model_validator(mode="after")
    def validate_status(self):
        allowed = {"Active", "Inactive", "On Leave"}
        if self.employment_status not in allowed:
            raise ValueError("Employment status must be Active, Inactive, or On Leave.")
        return self


class EmployeeArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=80)
    related_to: str = Field(default="General Farm", min_length=1, max_length=150)
    location: str = Field(default="Jorros Farm", min_length=1, max_length=150)
    description: str | None = None
    instructions: str | None = None
    activity_date: date
    start_time: str = "08:00"
    end_time: str | None = None
    employee_id: int | None = Field(default=None, gt=0)
    allow_unavailable_override: bool = False
    priority: str = "Medium"
    requires_review: bool = True
    requires_evidence: bool = False
    planned_quantity: float | None = Field(default=None, ge=0)
    planned_unit: str | None = Field(default=None, max_length=40)
    planned_inventory_item_id: int | None = Field(default=None, gt=0)
    planned_usage_type: str | None = Field(default=None, max_length=40)
    recurring_rule: str | None = Field(default=None, max_length=255)
    backup_employee_id: int | None = Field(default=None, gt=0)
    time_sensitive: bool = False
    controlled_rescheduling: bool = False
    max_delay_minutes: int | None = Field(default=None, ge=0, le=10080)
    source_module: str | None = Field(default=None, max_length=40)
    source_type: str | None = Field(default=None, max_length=80)
    source_record_id: int | None = Field(default=None, gt=0)
    source_path: str | None = Field(default=None, max_length=180)

    @model_validator(mode="after")
    def validate_resource_link(self):
        if self.max_delay_minutes is not None and not self.controlled_rescheduling:
            raise ValueError("Maximum delay requires controlled rescheduling to be enabled.")
        if self.planned_inventory_item_id is not None:
            if self.source_module not in {"Crop", "Livestock"} or self.source_record_id is None:
                raise ValueError("An inventory resource must be linked to a specific Crop or Livestock record.")
            if self.planned_quantity is None or self.planned_quantity <= 0:
                raise ValueError("Enter a planned quantity when linking an inventory resource to a task.")
        return self


class ResourceWorkScheduleCreate(BaseModel):
    module: str = Field(min_length=1, max_length=20)
    target_id: int = Field(gt=0)
    inventory_item_id: int = Field(gt=0)
    usage_type: str = Field(min_length=1, max_length=40)
    planned_quantity: float = Field(gt=0)
    activity_date: date
    start_time: str = Field(default="08:00", max_length=10)
    priority: str = Field(default="Medium", max_length=20)
    instructions: str | None = None
    requires_evidence: bool = False

    @model_validator(mode="after")
    def validate_schedule(self):
        crop_types = {"Fertilizer", "Pesticide", "Herbicide", "Other"}
        livestock_types = {
            "Medicine", "Vitamin / Supplement", "Disinfectant",
            "Treatment Supply", "Sanitation Supply", "Other",
        }
        if self.module not in {"Crop", "Livestock"}:
            raise ValueError("Module must be Crop or Livestock.")
        allowed = crop_types if self.module == "Crop" else livestock_types
        if self.usage_type not in allowed:
            raise ValueError(
                f"{self.usage_type} cannot be scheduled from the {self.module.lower()} resource panel."
            )
        if self.activity_date < farm_today():
            raise ValueError("Scheduled resource work cannot be created in the past.")
        return self


class TaskAssignmentUpdate(BaseModel):
    employee_id: int | None = Field(default=None, gt=0)
    allow_unavailable_override: bool = False
    activity_date: date | None = None
    priority: str | None = Field(default=None, max_length=20)
    instructions: str | None = None
    requires_review: bool | None = None
    requires_evidence: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


class TaskStartRequest(BaseModel):
    notes: str | None = None


class TaskSubmitRequest(BaseModel):
    monitoring: MonitoringObservation | None = None

    actual_quantity: float | None = Field(default=None, ge=0)
    actual_quantity_confirmed: bool = False
    inventory_item_id: int | None = Field(default=None, gt=0)
    actual_unit: str | None = Field(default=None, max_length=40)
    harvest_type_intent: Literal["Partial Harvest", "Final Harvest"] | None = None
    # evidence_ids is the authoritative new workflow. evidence_url remains as a
    # compatibility field for the managed URL returned by the upload endpoint;
    # arbitrary external URLs are rejected by the backend.
    evidence_ids: list[str] = Field(default_factory=list, max_length=4)
    evidence_url: str | None = Field(default=None, max_length=500)
    worker_notes: str | None = None
    problem_report: str | None = None
    performed_by_employee_id: int | None = Field(default=None, gt=0)
    assisted_reason: str | None = Field(default=None, max_length=200)
    approve_now: bool = False
    correction_only: bool = False
    allow_negative_inventory: bool = False
    inventory_override_reason: str | None = Field(default=None, max_length=500)


class TaskReviewRequest(BaseModel):
    confirmed_growth_stage: str | None = Field(default=None, max_length=40)
    confirm_harvest_ready: bool = False

    decision: str
    feedback: str | None = None
    harvest_type: Literal["Partial Harvest", "Final Harvest"] | None = None
    final_harvest_confirmed: bool = False

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision not in {"Approve", "Return", "Reject", "Void"}:
            raise ValueError("Decision must be Approve, Return, Reject, or Void.")
        if self.decision in {"Return", "Reject", "Void"} and not str(self.feedback or "").strip():
            raise ValueError("Feedback is required when returning or voiding a task.")
        return self


class TaskVoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_void_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class TaskEvidenceUploadResponse(BaseModel):
    evidence_id: str
    evidence_url: str
    thumbnail_url: str
    file_name: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    expires_at: datetime


class TaskSubmissionResponse(BaseModel):
    monitoring: MonitoringObservation | None = None

    model_config = ConfigDict(from_attributes=True)
    id: int
    activity_id: int
    employee_id: int
    employee_name: str | None = None
    recorded_by_user_id: int | None
    recorded_by_name: str | None = None
    reviewed_by_name: str | None = None
    is_assisted: bool = False
    attempt_number: int
    actual_quantity: float | None
    actual_unit: str | None
    harvest_type_intent: str | None = None
    harvest_type_confirmed: str | None = None
    evidence_url: str | None
    worker_notes: str | None
    problem_report: str | None
    inventory_override_used: bool = False
    inventory_override_reason: str | None = None
    review_status: str
    review_feedback: str | None
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    submitted_at: datetime


class MyTasksSummaryResponse(BaseModel):
    held: int = 0
    total: int = 0
    today: int = 0
    missed: int = 0
    in_progress: int = 0
    returned: int = 0
    for_review: int = 0
    upcoming: int = 0


class TaskResponse(BaseModel):
    work_suspended: bool = False
    suspension_holds: list[dict] = Field(default_factory=list)
    monitoring_context: dict | None = None

    id: int
    activity_code: str
    name: str
    category: str
    related_to: str
    location: str
    description: str | None
    instructions: str | None
    activity_date: date
    start_time: str
    end_time: str | None
    assigned_by: str
    assigned_to: str
    assigned_employee_id: int | None
    assignment_source: str = "manual"
    employee_name: str | None = None
    employee_status: str | None = None
    employee_is_archived: bool = False
    is_archived: bool = False
    previous_employee_name: str | None = None
    reassignment_reason: str | None = None
    leave_coverage_id: int | None = None
    related_leave_id: int | None = None
    original_employee_id: int | None = None
    original_employee_name: str | None = None
    covering_employee_id: int | None = None
    covering_employee_name: str | None = None
    coverage_start_date: date | None = None
    coverage_end_date: date | None = None
    coverage_reason: str | None = None
    coverage_status: str | None = None
    coverage_indicator: str | None = None
    status: str
    priority: str
    completed_at: datetime | None = None
    requires_review: bool
    requires_evidence: bool
    planned_quantity: float | None
    planned_unit: str | None
    planned_inventory_item_id: int | None = None
    planned_inventory_item_code: str | None = None
    planned_inventory_item_name: str | None = None
    planned_inventory_category: str | None = None
    planned_inventory_available_quantity: float | None = None
    planned_inventory_unit: str | None = None
    planned_usage_type: str | None = None
    resource_required: bool = False
    resource_linked: bool = False
    recurring_rule: str | None
    default_employee_id: int | None = None
    backup_employee_id: int | None = None
    time_sensitive: bool = False
    controlled_rescheduling: bool = False
    max_delay_minutes: int | None = None
    problem_report: str | None
    needs_reassignment: bool
    source_module: str | None
    source_type: str | None
    source_record_id: int | None
    source_protocol_family_code: str | None = None
    source_protocol_version: int | None = None
    source_path: str | None
    is_automatic: bool
    has_performed_work_record: bool = False
    can_void: bool = False
    void_block_reason: str | None = None
    record_origin: str | None = None
    latest_submission: TaskSubmissionResponse | None = None


class TaskPageResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    offset: int
    limit: int


class TaskReviewMovementResponse(BaseModel):
    id: int
    movement_type: str
    quantity: float
    previous_quantity: float
    new_quantity: float
    movement_date: date
    reference: str | None = None
    recorded_by_name: str | None = None
    created_at: datetime


class TaskReviewResourceResponse(BaseModel):
    tracked: bool = False
    inventory_item_id: int | None = None
    inventory_item_code: str | None = None
    inventory_item_name: str | None = None
    inventory_category: str | None = None
    planned_quantity: float | None = None
    planned_unit: str | None = None
    actual_quantity: float | None = None
    actual_unit: str | None = None
    quantity_difference: float | None = None
    deduction_status: str = "Not Required"
    resource_usage_id: int | None = None
    movement_reference: str | None = None
    movements: list[TaskReviewMovementResponse] = Field(default_factory=list)


class TaskReviewReportResponse(BaseModel):
    task: TaskResponse
    current_submission: TaskSubmissionResponse
    previous_submissions: list[TaskSubmissionResponse] = Field(default_factory=list)
    resource_usage: TaskReviewResourceResponse
    crop_status: str | None = None
    harvest_approval_blocker: str | None = None


class TaskAssignmentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activity_id: int
    old_employee_id: int | None
    new_employee_id: int | None
    old_employee_name: str | None = None
    new_employee_name: str | None = None
    assignment_source: str
    leave_id: int | None = None
    old_assignment_source: str | None = None
    new_assignment_source: str | None = None
    is_automatic: bool = False
    default_employee_id: int | None = None
    schedule_id: int | None = None
    schedule_exception_id: int | None = None
    coverage_date: date | None = None
    actor_user_id: int | None
    actor_name: str
    reason: str
    changed_at: datetime


class AttendanceUpsert(BaseModel):
    """Legacy compatibility payload. Manager workflow should prefer explicit attendance actions."""
    employee_id: int = Field(gt=0)
    attendance_date: date
    status: str
    notes: str | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status not in ATTENDANCE_STATUSES:
            raise ValueError("Invalid attendance status.")
        return self


class AttendanceActionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class AttendanceStatusRequest(BaseModel):
    status: Literal["Absent", "Sick"]
    notes: str | None = Field(default=None, max_length=1000)


class AttendanceCorrectionRequest(BaseModel):
    status: str
    correction_reason: str = Field(min_length=3, max_length=1000)
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_correction(self):
        if self.status not in ATTENDANCE_STATUSES:
            raise ValueError("Invalid attendance status.")
        if "check_in_at" in self.model_fields_set and self.check_in_at is None and self.check_out_at:
            raise ValueError("Corrected Check Out requires a Check In timestamp.")
        return self


class AttendanceSettingsUpdate(BaseModel):
    check_in_grace_minutes: int = Field(default=5, ge=0, le=120)
    earliest_check_in_minutes: int = Field(default=120, ge=0, le=720)
    early_departure_grace_minutes: int = Field(default=5, ge=0, le=120)
    missing_checkout_cutoff_minutes: int = Field(default=120, ge=0, le=1440)
    attendance_reminder_minutes: int = Field(default=15, ge=0, le=240)


class AttendanceSettingsResponse(AttendanceSettingsUpdate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class AttendanceAuditResponse(BaseModel):
    id: int
    action: str
    old_status: str | None = None
    new_status: str | None = None
    source: str
    reason: str | None = None
    actor_user_id: int | None = None
    actor_name: str
    created_at: datetime


class AttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: str | None = None
    attendance_date: date
    scheduled_shift_id: int | None = None
    scheduled_start_time: time | None = None
    scheduled_end_time: time | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: str
    stored_status: str | None = None
    minutes_late: int | None = None
    minutes_early: int | None = None
    overtime_minutes: int | None = None
    worked_minutes: int | None = None
    attendance_source: str = "Manager Assisted"
    notes: str | None = None
    correction_reason: str | None = None
    recorded_by_user_id: int | None = None
    updated_by_user_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    audit: list[AttendanceAuditResponse] = Field(default_factory=list)


class AttendanceBulkResponse(BaseModel):
    work_date: date
    scheduled_count: int
    recorded_count: int
    preserved_count: int
    skipped_count: int
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    records: list[AttendanceResponse] = Field(default_factory=list)


class LeaveCreate(BaseModel):
    employee_id: int = Field(gt=0)
    leave_type: str
    start_date: date
    end_date: date
    reason: str | None = None
    status: Literal["Pending", "Approved"] = "Approved"

    @model_validator(mode="after")
    def validate_leave(self):
        if self.leave_type not in LEAVE_TYPES:
            raise ValueError("Invalid leave type.")
        if self.end_date < self.start_date:
            raise ValueError("Leave end date cannot be before start date.")
        return self


class LeaveRequestCreate(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_leave(self):
        if self.leave_type not in LEAVE_TYPES:
            raise ValueError("Invalid leave type.")
        if self.end_date < self.start_date:
            raise ValueError("Leave end date cannot be before start date.")
        today = farm_today()
        if self.start_date <= today or self.end_date <= today:
            raise ValueError("Leave start and end dates must be after today in the farm timezone.")
        self.reason = (self.reason or "").strip() or None
        if self.leave_type == "Other" and not self.reason:
            raise ValueError("A reason is required when the leave type is Other.")
        return self


class LeaveCoverageTaskSelection(BaseModel):
    task_id: int = Field(gt=0)
    covering_employee_id: int | None = Field(default=None, gt=0)


class LeaveDecisionRequest(BaseModel):
    decision: Literal["Approved", "Rejected"]
    notes: str | None = Field(default=None, max_length=1000)
    default_covering_employee_id: int | None = Field(default=None, gt=0)
    task_coverages: list[LeaveCoverageTaskSelection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_coverage_only_for_approval(self):
        if self.decision != "Approved" and (
            self.default_covering_employee_id is not None or self.task_coverages
        ):
            raise ValueError("Coverage selections are only allowed when approving leave.")
        ids = [row.task_id for row in self.task_coverages]
        if len(ids) != len(set(ids)):
            raise ValueError("A task can only appear once in the coverage plan.")
        return self


class LeaveCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: str | None = None
    leave_type: str
    start_date: date
    end_date: date
    request_date: datetime | None = None
    status: str
    reason: str | None
    recorded_by_user_id: int | None
    requested_by_user_id: int | None = None
    requested_by_name: str | None = None
    decided_by_user_id: int | None = None
    reviewed_by_name: str | None = None
    decided_at: datetime | None = None
    decision_notes: str | None = None
    default_covering_employee_id: int | None = None
    default_covering_employee_name: str | None = None
    coverage_reason: str | None = None
    affected_task_count: int = 0
    cancelled_by_user_id: int | None = None
    cancelled_by_name: str | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None


class LeaveCandidateTaskAvailability(BaseModel):
    available: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LeaveCoveringCandidateResponse(BaseModel):
    employee_id: int
    employee_name: str
    position: str | None = None
    assigned_area: str | None = None
    skills: str | None = None
    available_for_all: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    task_availability: dict[str, LeaveCandidateTaskAvailability] = Field(default_factory=dict)


class LeaveReviewResponse(BaseModel):
    leave: LeaveResponse
    employee_availability: str
    attendance: list[AttendanceResponse] = Field(default_factory=list)
    shifts: list[dict] = Field(default_factory=list)
    overlapping_leave: list[LeaveResponse] = Field(default_factory=list)
    affected_tasks: list[TaskResponse] = Field(default_factory=list)
    covering_candidates: list[LeaveCoveringCandidateResponse] = Field(default_factory=list)
    assignment_summary: dict[str, int] = Field(default_factory=dict)


class LeaveRecalculationResponse(BaseModel):
    checked: int = 0
    returned: int = 0
    preserved: int = 0


class ShiftCreate(BaseModel):
    employee_id: int = Field(gt=0)
    work_date: date
    start_time: time | None = None
    end_time: time | None = None
    assigned_area: str | None = Field(default=None, max_length=120)
    status: str = "Scheduled"
    notes: str | None = Field(default=None, max_length=1000)
    exception_type: str | None = None
    exception_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_shift(self):
        if self.status not in SHIFT_STATUSES:
            raise ValueError("Invalid shift status.")
        if self.exception_type is not None and self.exception_type not in SCHEDULE_EXCEPTION_TYPES:
            raise ValueError("Invalid schedule exception type.")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("Shift end time must be after the start time.")
        return self


class ShiftUpdate(BaseModel):
    work_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    assigned_area: str | None = Field(default=None, max_length=120)
    status: str | None = None
    notes: str | None = Field(default=None, max_length=1000)
    exception_type: str | None = None
    exception_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_shift(self):
        if self.status is not None and self.status not in SHIFT_STATUSES:
            raise ValueError("Invalid shift status.")
        if self.exception_type is not None and self.exception_type not in SCHEDULE_EXCEPTION_TYPES:
            raise ValueError("Invalid schedule exception type.")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("Shift end time must be after the start time.")
        return self


class ShiftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    work_date: date
    start_time: time | None = None
    end_time: time | None = None
    assigned_area: str | None = None
    status: str
    notes: str | None = None
    exception_type: str | None = None
    exception_reason: str | None = None
    created_by_user_id: int | None = None
    updated_by_user_id: int | None = None


class CalendarConfigResponse(BaseModel):
    timezone: str
    today: date


CARE_PROTOCOL_STATUSES = {"Draft", "Published", "Superseded", "Inactive"}
CARE_PROTOCOL_APPROVAL_STATUSES = {
    "Draft - Needs Veterinarian/Agriculturist Approval",
    "Approved",
    "Rejected",
    "Legacy - Review Recommended",
}
CARE_TIMING_ANCHORS = {"base_date", "planting_date", "birth_date", "acquisition_date", "age_window", "stage", "previous_step"}
CARE_DOSE_BASES = {"per_head", "per_kg_body_weight", "per_batch", "per_plant", "per_hectare"}


class CareTemplateStepInput(BaseModel):
    sequence_number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=80)
    offset_days: int = Field(default=0, ge=0)
    timing_anchor: str = "base_date"
    age_start_days: int | None = Field(default=None, ge=0)
    age_end_days: int | None = Field(default=None, ge=0)
    previous_step_sequence: int | None = Field(default=None, gt=0)
    recurrence_interval_days: int | None = Field(default=None, gt=0)
    recurrence_occurrences: int = Field(default=1, ge=1, le=366)
    instructions: str | None = None
    priority: str = "Medium"
    requires_review: bool = True
    requires_evidence: bool = False
    planned_quantity: float | None = Field(default=None, gt=0)
    planned_unit: str | None = Field(default=None, max_length=40)
    dose_basis: str | None = Field(default=None, max_length=60)
    resource_product_name: str | None = Field(default=None, max_length=150)
    resource_category: str | None = Field(default=None, max_length=80)
    inventory_item_id: int | None = Field(default=None, gt=0)  # legacy compatibility only
    safety_notes: str | None = None
    withdrawal_interval_days: int | None = Field(default=None, ge=0)
    preharvest_interval_days: int | None = Field(default=None, ge=0)
    source_citation: str | None = None

    @model_validator(mode="after")
    def validate_protocol_step(self):
        if self.timing_anchor not in CARE_TIMING_ANCHORS:
            raise ValueError("Unsupported care-protocol timing anchor.")
        if self.age_start_days is not None and self.age_end_days is not None and self.age_end_days < self.age_start_days:
            raise ValueError("Age-window end must be on or after its start.")
        if self.timing_anchor == "age_window" and self.age_start_days is None:
            raise ValueError("Age-window timing requires age_start_days.")
        if self.timing_anchor == "previous_step" and self.previous_step_sequence is None:
            raise ValueError("Previous-step timing requires previous_step_sequence.")
        if self.recurrence_occurrences > 1 and not self.recurrence_interval_days:
            raise ValueError("Recurring steps require recurrence_interval_days.")
        if self.dose_basis and self.dose_basis not in CARE_DOSE_BASES:
            raise ValueError("Unsupported planned-dose basis.")
        if (self.resource_product_name or self.resource_category or self.inventory_item_id) and self.planned_quantity is None:
            raise ValueError("A resource-linked care step must have a planned quantity.")
        return self


class CareTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    module: str
    target_type: str | None = Field(default=None, max_length=100)
    target_breed: str | None = Field(default=None, max_length=100)
    target_variety: str | None = Field(default=None, max_length=100)
    production_purpose: str | None = Field(default=None, max_length=100)
    growth_stage: str | None = Field(default=None, max_length=100)
    description: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    approval_status: str = "Draft - Needs Veterinarian/Agriculturist Approval"
    source_title: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=500)
    citations: list[str] = Field(default_factory=list)
    last_reviewed_date: date | None = None
    steps: list[CareTemplateStepInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_protocol(self):
        if self.module not in {"Crop", "Livestock"}:
            raise ValueError("Care protocol module must be Crop or Livestock.")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Protocol effective_to must be on or after effective_from.")
        if self.approval_status not in CARE_PROTOCOL_APPROVAL_STATUSES:
            raise ValueError("Unsupported protocol approval status.")
        return self


class CareTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    target_type: str | None = Field(default=None, max_length=100)
    target_breed: str | None = Field(default=None, max_length=100)
    target_variety: str | None = Field(default=None, max_length=100)
    production_purpose: str | None = Field(default=None, max_length=100)
    growth_stage: str | None = Field(default=None, max_length=100)
    description: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    approval_status: str | None = None
    source_title: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=500)
    citations: list[str] | None = None
    last_reviewed_date: date | None = None
    is_active: bool | None = None
    steps: list[CareTemplateStepInput] | None = None
    future_task_action: Literal["keep", "resolve"] | None = None


class CareTemplateStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sequence_number: int
    title: str
    category: str
    offset_days: int
    timing_anchor: str
    age_start_days: int | None = None
    age_end_days: int | None = None
    previous_step_sequence: int | None = None
    recurrence_interval_days: int | None = None
    recurrence_occurrences: int
    instructions: str | None
    priority: str
    requires_review: bool
    requires_evidence: bool
    planned_quantity: float | None
    planned_unit: str | None
    dose_basis: str | None = None
    resource_product_name: str | None = None
    resource_category: str | None = None
    inventory_item_id: int | None
    safety_notes: str | None = None
    withdrawal_interval_days: int | None = None
    preharvest_interval_days: int | None = None
    source_citation: str | None = None


class CareTemplateResponse(BaseModel):
    id: int
    template_code: str
    protocol_family_code: str
    version: int
    name: str
    module: str
    target_type: str | None
    target_breed: str | None = None
    target_variety: str | None = None
    production_purpose: str | None = None
    growth_stage: str | None = None
    description: str | None
    effective_from: date | None = None
    effective_to: date | None = None
    status: str
    approval_status: str
    source_title: str | None = None
    source_url: str | None = None
    citations: list[str] = Field(default_factory=list)
    last_reviewed_date: date | None = None
    supersedes_template_id: int | None = None
    copied_from_template_id: int | None = None
    published_at: datetime | None = None
    is_active: bool
    steps: list[CareTemplateStepResponse]


class CareProtocolPublishRequest(BaseModel):
    future_task_action: Literal["keep", "resolve"] = "keep"
    apply_to_assigned_targets: bool = False


class CareProtocolCopyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)


class CareProtocolImportRequest(BaseModel):
    protocols: list[CareTemplateCreate]


class GenerateCareTasksRequest(BaseModel):
    module: str
    target_id: int = Field(gt=0)
    template_id: int = Field(gt=0)
    base_date: date | None = None
    employee_id: int | None = Field(default=None, gt=0)
    backup_employee_id: int | None = Field(default=None, gt=0)
    time_sensitive: bool = False
    controlled_rescheduling: bool = False
    max_delay_minutes: int | None = Field(default=None, ge=0, le=10080)

    @model_validator(mode="after")
    def validate_timing_policy(self):
        if self.max_delay_minutes is not None and not self.controlled_rescheduling:
            raise ValueError("Maximum delay requires controlled rescheduling to be enabled.")
        return self
