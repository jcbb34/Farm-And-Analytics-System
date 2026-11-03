from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FarmActivity(Base):
    __tablename__ = "farm_activities"
    __table_args__ = (
        Index("ix_farm_activities_page_status", "is_archived", "status", "activity_date", "id"),
        Index("ix_farm_activities_employee_page", "assigned_employee_id", "is_archived", "status", "activity_date", "id"),
        Index(
            "uq_farm_activities_source_key_not_null",
            "source_key",
            unique=True,
            mssql_where=text("source_key IS NOT NULL"),
            sqlite_where=text("source_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    activity_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    related_to: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    location: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    activity_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    end_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    duration: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    assigned_by: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    assigned_to: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
    )

    # New workforce assignment. assigned_to remains as a historical/display snapshot.
    assigned_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True,
        index=True,
    )

    # Tracks who currently owns the assignment decision. The scheduler only
    # supplies automatic_default on initial creation; later manager decisions
    # are preserved as manager_override/reassignment.
    assignment_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
        server_default=text("'manual'"),
        index=True,
    )

    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    requires_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1"), index=True
    )

    requires_evidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    planned_quantity: Mapped[float | None] = mapped_column(nullable=True)
    planned_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    planned_inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=True, index=True
    )
    planned_usage_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    recurring_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recurring_series_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    # Persist the assignment/timing policy on each occurrence. The current
    # assignee may change because of leave/rest-day coverage, while the default
    # employee remains stable for safe future reconciliation.
    default_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    backup_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    time_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    controlled_rescheduling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    max_delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    problem_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_reassignment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Pending",
        server_default=text("'Pending'"),
        index=True,
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Medium",
        server_default=text("'Medium'"),
        index=True,
    )

    # -----------------------------------------------------
    # CENTRAL TASK SOURCE METADATA
    # -----------------------------------------------------

    is_automatic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    source_module: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        index=True,
    )

    source_type: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )

    source_record_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    source_detail_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_code: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
    )

    source_protocol_family_code: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        index=True,
    )

    source_protocol_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_path: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    source_key: Mapped[str | None] = mapped_column(
        String(220),
        nullable=True,
        index=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
