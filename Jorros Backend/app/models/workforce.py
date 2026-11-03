from datetime import date, datetime, time
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.personal_details import PersonalDetailsMixin


class Employee(PersonalDetailsMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        Index(
            "ix_employees_login_user",
            "login_user_id",
            unique=True,
            mssql_where=text("login_user_id IS NOT NULL"),
            sqlite_where=text("login_user_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_hired: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    assigned_area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_contact_relationship: Mapped[str | None] = mapped_column(String(60), nullable=True)
    emergency_contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Active", server_default=text("'Active'"), index=True
    )
    login_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"), index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    archived_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EmployeeWorkSchedule(Base):
    __tablename__ = "employee_work_schedules"
    __table_args__ = (
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_employee_work_schedule_effective_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Manila", server_default=text("'Asia/Manila'"))
    schedule_type: Mapped[str] = mapped_column(String(30), nullable=False, default="Fixed", server_default=text("'Fixed'"))
    backup_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active", server_default=text("'Active'"), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class EmployeeWorkScheduleDay(Base):
    __tablename__ = "employee_work_schedule_days"
    __table_args__ = (
        UniqueConstraint("schedule_id", "day_of_week", name="uq_employee_work_schedule_day"),
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_employee_work_schedule_day_of_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("employee_work_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class FarmPosition(Base):
    __tablename__ = "farm_positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class EmployeePosition(Base):
    __tablename__ = "employee_positions"
    __table_args__ = (
        UniqueConstraint("employee_id", "position_id", name="uq_employee_position"),
        Index(
            "ix_employee_positions_one_primary",
            "employee_id",
            unique=True,
            mssql_where=text("is_primary = 1"),
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("farm_positions.id"), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    position: Mapped["FarmPosition"] = relationship("FarmPosition", lazy="joined")




class TaskAssignmentHistory(Base):
    __tablename__ = "task_assignment_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("farm_activities.id"), nullable=False, index=True
    )
    old_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    new_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    assignment_source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    leave_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_leave.id"), nullable=True, index=True
    )
    old_assignment_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_assignment_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_automatic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"), index=True
    )
    event_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("employee_work_schedules.id"), nullable=True, index=True)
    schedule_exception_id: Mapped[int | None] = mapped_column(ForeignKey("staff_shifts.id"), nullable=True, index=True)
    coverage_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )


class TaskSubmission(Base):
    __tablename__ = "task_submissions"
    __table_args__ = (
        UniqueConstraint("activity_id", "attempt_number", name="uq_task_submission_attempt"),
        Index(
            "ix_task_submission_idempotency_key",
            "idempotency_key",
            unique=True,
            mssql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    monitoring_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def monitoring(self):
        import json
        return json.loads(self.monitoring_data_json) if self.monitoring_data_json else None

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("farm_activities.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_quantity: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    actual_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    harvest_type_intent: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    harvest_type_confirmed: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worker_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    inventory_override_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    inventory_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Submitted", server_default=text("'Submitted'"), index=True
    )
    review_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskEvidence(Base):
    __tablename__ = "task_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("farm_activities.id"), nullable=False, index=True)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("task_submissions.id"), nullable=True, index=True)
    uploader_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    original_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    storage_identifier: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    thumbnail_storage_identifier: Mapped[str] = mapped_column(String(140), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Temporary", server_default=text("'Temporary'"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    attached_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class StaffAttendance(Base):
    __tablename__ = "staff_attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_employee_attendance_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scheduled_shift_id: Mapped[int | None] = mapped_column(ForeignKey("staff_shifts.id"), nullable=True, index=True)
    scheduled_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    scheduled_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    minutes_late: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_early: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attendance_source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Manager Assisted", server_default=text("'Manager Assisted'"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class StaffAttendanceAudit(Base):
    __tablename__ = "staff_attendance_audit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    attendance_id: Mapped[int] = mapped_column(ForeignKey("staff_attendance.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    old_check_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    new_check_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    old_check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    new_check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class AttendanceSettings(Base):
    __tablename__ = "attendance_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    check_in_grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default=text("5"))
    earliest_check_in_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120, server_default=text("120"))
    early_departure_grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default=text("5"))
    missing_checkout_cutoff_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120, server_default=text("120"))
    attendance_reminder_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15, server_default=text("15"))
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class StaffLeave(Base):
    __tablename__ = "staff_leave"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    leave_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Approved", server_default=text("'Approved'"), index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_covering_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    coverage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskLeaveCoverage(Base):
    """Structured, occurrence-level temporary assignment created by approved leave."""

    __tablename__ = "task_leave_coverage"
    __table_args__ = (
        UniqueConstraint("activity_id", "leave_id", name="uq_task_leave_coverage_activity_leave"),
        Index("ix_task_leave_coverage_source_match", "leave_id", "recurring_series_key", "source_module", "source_type", "source_record_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("farm_activities.id"), nullable=False, index=True)
    leave_id: Mapped[int] = mapped_column(ForeignKey("staff_leave.id"), nullable=False, index=True)
    original_employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    covering_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    coverage_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    coverage_end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Active", server_default=text("'Active'"), index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    source_module: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_detail_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurring_series_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class StaffShift(Base):
    __tablename__ = "staff_shifts"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_staff_shift_employee_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    assigned_area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Scheduled", server_default=text("'Scheduled'"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CareTemplate(Base):
    __tablename__ = "care_templates"
    __table_args__ = (
        UniqueConstraint("protocol_family_code", "version", name="uq_care_template_family_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    protocol_family_code: Mapped[str] = mapped_column(String(40), nullable=False, default=lambda: f"LEGACY-{uuid4().hex[:12]}", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # Crop / Livestock
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    target_breed: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    target_variety: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    production_purpose: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    growth_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Published", server_default=text("'Published'"), index=True)
    approval_status: Mapped[str] = mapped_column(String(80), nullable=False, default="Legacy - Review Recommended", server_default=text("'Legacy - Review Recommended'"), index=True)
    source_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reviewed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supersedes_template_id: Mapped[int | None] = mapped_column(ForeignKey("care_templates.id"), nullable=True, index=True)
    copied_from_template_id: Mapped[int | None] = mapped_column(ForeignKey("care_templates.id"), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1"), index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CareTemplateStep(Base):
    __tablename__ = "care_template_steps"
    __table_args__ = (
        UniqueConstraint("template_id", "sequence_number", name="uq_care_template_step_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("care_templates.id"), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    timing_anchor: Mapped[str] = mapped_column(String(40), nullable=False, default="base_date", server_default=text("'base_date'"), index=True)
    age_start_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_end_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_step_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    dose_basis: Mapped[str | None] = mapped_column(String(60), nullable=True)
    resource_product_name: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    resource_category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    withdrawal_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preharvest_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Medium", server_default=text("'Medium'")
    )
    requires_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    requires_evidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    planned_quantity: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    planned_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
