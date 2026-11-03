"""Durable farm declarations; operational history is never deleted on reopening."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UnicodeText, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class FarmEvent(Base):
    __tablename__ = "farm_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="Draft", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="All")
    scope_json: Mapped[str] = mapped_column(UnicodeText, default="[]")
    reason: Mapped[str] = mapped_column(UnicodeText)
    instructions: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(600), nullable=True)
    checklist_json: Mapped[str] = mapped_column(UnicodeText, default="[]")
    version: Mapped[int] = mapped_column(Integer, default=1)
    notice_version: Mapped[int] = mapped_column(Integer, default=1)
    command_key: Mapped[str] = mapped_column(String(64), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FarmEventTask(Base):
    __tablename__ = "farm_event_tasks"
    __table_args__ = (UniqueConstraint("event_id", "activity_id", name="uq_farm_event_task"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("farm_events.id"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("farm_activities.id"), index=True)
    original_json: Mapped[str] = mapped_column(UnicodeText)
    resolution: Mapped[str] = mapped_column(String(30), default="Held", index=True)
    essential_review: Mapped[bool] = mapped_column(default=False)
    authorized_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FarmEventAcknowledgement(Base):
    __tablename__ = "farm_event_acknowledgements"
    __table_args__ = (UniqueConstraint("event_id", "employee_id", "notice_version", name="uq_farm_event_acknowledgement"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("farm_events.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    notice_version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime)


class FarmEventAudit(Base):
    __tablename__ = "farm_event_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("farm_events.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    reason: Mapped[str] = mapped_column(UnicodeText)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(150))
    details_json: Mapped[str] = mapped_column(UnicodeText, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class FarmEventReport(Base):
    __tablename__ = "farm_event_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("farm_events.id"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    area: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(UnicodeText)
    created_at: Mapped[datetime] = mapped_column(DateTime)
