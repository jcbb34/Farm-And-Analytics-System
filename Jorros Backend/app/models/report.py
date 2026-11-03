import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _json_dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


class FarmReport(Base):
    __tablename__ = "farm_reports"
    __table_args__ = (
        Index(
            "uq_farm_reports_automation_period_key_not_null",
            "automation_period_key",
            unique=True,
            mssql_where=text("automation_period_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    report_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    report_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    generated_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        server_default=func.cast(
            func.getdate(),
            Date,
        ),
        index=True,
    )

    prepared_by: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Draft -> For Review -> Approved -> Archived
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Draft",
        index=True,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    snapshot_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    comparison_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    findings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default=text("'[]'"),
    )

    recommendations_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default=text("'[]'"),
    )

    data_quality_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default=text("'[]'"),
    )

    generated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    reviewed_by_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    archived_from_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    revision_group_code: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    revision_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    revision_of_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("farm_reports.id"),
        nullable=True,
    )

    is_automatic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    frequency: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    automation_period_key: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    pdf_filename: Mapped[str | None] = mapped_column(
        String(255),
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

    @property
    def snapshot(self) -> dict[str, Any]:
        return _json_dict(
            self.snapshot_json
        )

    @property
    def comparison(self) -> dict[str, Any]:
        return _json_dict(
            self.comparison_json
        )

    @property
    def findings(self) -> list[Any]:
        return _json_list(
            self.findings_json
        )

    @property
    def recommendations(self) -> list[Any]:
        return _json_list(
            self.recommendations_json
        )

    @property
    def data_quality(self) -> list[Any]:
        return _json_list(
            self.data_quality_json
        )

    @property
    def included_sections(self) -> list[str]:
        options = self.snapshot.get("report_options", {})
        sections = options.get("included_sections", [])
        return sections if isinstance(sections, list) else []

    @property
    def executive_kpis(self) -> list[Any]:
        value = self.snapshot.get("executive_kpis", [])
        return value if isinstance(value, list) else []

    @property
    def performance_variance(self) -> list[Any]:
        value = self.snapshot.get("performance_variance", [])
        return value if isinstance(value, list) else []

    @property
    def risk_flags(self) -> list[Any]:
        value = self.snapshot.get("risk_flags", [])
        return value if isinstance(value, list) else []

    @property
    def is_locked(self) -> bool:
        return self.status in {
            "For Review",
            "Approved",
            "Final",
            "Revised",
            "Archived",
        }


class ReportAutomationSettings(Base):
    __tablename__ = "report_automation_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    daily_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    daily_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="00:05",
        server_default="00:05",
    )

    weekly_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    weekly_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    weekly_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="00:10",
        server_default="00:10",
    )

    monthly_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    monthly_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    monthly_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="00:15",
        server_default="00:15",
    )

    yearly_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    yearly_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    yearly_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    yearly_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="00:20",
        server_default="00:20",
    )

    prepared_by: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        default="System Generated",
        server_default="System Generated",
    )

    auto_generate_pdf: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    last_scheduler_run_at: Mapped[datetime | None] = mapped_column(
        DateTime,
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
