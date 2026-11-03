from datetime import date, datetime
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


REPORT_TYPES = {
    "Workforce": {
        "Daily Attendance Report",
        "Weekly Attendance Summary",
    },
    "Tasks": {
        "Task Completion and Employee Performance",
        "Task Coverage and Reassignment",
    },
    "Care Compliance": {
        "Care Protocol Compliance",
    },
    "Audit": {
        "Generated Report History and Audit Trail",
    },
    "Farm": {
        "Farm Summary",
        "Farm Performance Report",
        "Trend & Seasonal Analysis",
    },
    "Crop": {
        "Crop Yield and Input Usage",
        "Crop Production",
        "Harvest Summary",
        "Yield Performance",
        "Crop Growth",
        "Pest and Disease",
        "Resource Usage",
    },
    "Livestock": {
        "Livestock Feeding, Growth, and Health",
        "Livestock Production",
        "Growth Summary",
        "Health Summary",
        "Vaccination Summary",
        "Feeding Consumption",
        "Resource Usage",
    },
    "Production & Sales": {
        "Production and Sales Summary",
        "Production Summary",
        "Sales Summary",
        "Crop Production & Sales",
        "Livestock Production & Sales",
        "Processing Report",
        "Receivables Report",
    },
    "Trend & Seasonal": {
        "Trend & Seasonal Analysis",
    },
    "Inventory": {
        "Inventory Movement and Resource Usage",
        "Inventory Summary",
        "Stock Movement",
        "Low Stock",
        "Expiring Items",
        "Consumption Summary",
        "Resource Usage",
        "Inventory Valuation",
    },
}


REPORT_SECTION_ORDER = [
    "executive_summary",
    "kpi_overview",
    "period_comparison",
    "performance_variance",
    "detailed_analysis",
    "findings",
    "risks",
    "recommendations",
    "data_quality",
    "appendix",
]

DEFAULT_REPORT_SECTIONS = list(REPORT_SECTION_ORDER)

REPORT_STATUSES = {
    "Draft",
    "For Review",
    "Approved",
    "Archived",
    "In Progress",
    "Needs Review",
    "Final",
    "Revised",
    "Failed",
}

CREATION_STATUSES = {
    "Draft",
    "For Review",
}


class ReportCreate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=180,
    )
    category: str = Field(
        min_length=1,
        max_length=40,
    )
    report_type: str = Field(
        min_length=1,
        max_length=80,
    )
    start_date: date
    end_date: date
    prepared_by: str = Field(
        min_length=1,
        max_length=150,
    )
    status: str = "Draft"
    summary: str | None = None
    included_sections: list[str] = Field(
        default_factory=lambda: list(DEFAULT_REPORT_SECTIONS)
    )
    filters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_report(self):
        if self.category not in REPORT_TYPES:
            raise ValueError(
                "Invalid report category."
            )

        if (
            self.report_type
            not in REPORT_TYPES[
                self.category
            ]
        ):
            raise ValueError(
                "The selected report type does not belong to the category."
            )

        if self.end_date < self.start_date:
            raise ValueError(
                "End date cannot be earlier than start date."
            )

        if self.status not in CREATION_STATUSES:
            raise ValueError(
                "New custom reports must be Draft or For Review."
            )

        invalid_sections = [
            section
            for section in self.included_sections
            if section not in REPORT_SECTION_ORDER
        ]
        if invalid_sections:
            raise ValueError(
                "Invalid report section selection: "
                + ", ".join(invalid_sections)
            )

        selected = set(self.included_sections)
        self.included_sections = [
            section
            for section in REPORT_SECTION_ORDER
            if section in selected
        ]
        if not self.included_sections:
            raise ValueError(
                "Select at least one report section."
            )

        allowed_filters = {
            "employee_id", "crop_id", "field", "livestock_id", "pen_id",
            "inventory_item_id", "status", "source",
        }
        unknown = sorted(set(self.filters) - allowed_filters)
        if unknown:
            raise ValueError("Unsupported report filter(s): " + ", ".join(unknown))
        self.filters = {
            key: value for key, value in self.filters.items()
            if value not in (None, "")
        }

        return self


class ReportUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=180,
    )
    prepared_by: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    summary: str | None = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    report_code: str
    title: str
    category: str
    report_type: str
    start_date: date
    end_date: date
    generated_date: date
    prepared_by: str
    status: str
    summary: str

    snapshot: dict[str, Any]
    comparison: dict[str, Any]
    findings: list[Any]
    recommendations: list[Any]
    data_quality: list[Any]
    included_sections: list[str] = Field(default_factory=list)
    executive_kpis: list[Any] = Field(default_factory=list)
    performance_variance: list[Any] = Field(default_factory=list)
    risk_flags: list[Any] = Field(default_factory=list)

    generated_by_user_id: int | None = None

    submitted_at: datetime | None = None
    reviewed_by_user_id: int | None = None
    reviewed_by_name: str | None = None
    approved_at: datetime | None = None

    revision_group_code: str | None = None
    revision_number: int = 1
    revision_of_report_id: int | None = None

    is_automatic: bool = False
    frequency: str | None = None
    automation_period_key: str | None = None
    pdf_filename: str | None = None
    is_locked: bool = False

    created_at: datetime
    updated_at: datetime


class ReportAutomationSettingsUpdate(BaseModel):
    daily_enabled: bool = True
    daily_time: str = "00:05"

    weekly_enabled: bool = True
    weekly_day: int = Field(
        default=0,
        ge=0,
        le=6,
    )
    weekly_time: str = "00:10"

    monthly_enabled: bool = True
    monthly_day: int = Field(
        default=1,
        ge=1,
        le=28,
    )
    monthly_time: str = "00:15"

    yearly_enabled: bool = True
    yearly_month: int = Field(
        default=1,
        ge=1,
        le=12,
    )
    yearly_day: int = Field(
        default=1,
        ge=1,
        le=28,
    )
    yearly_time: str = "00:20"

    prepared_by: str = Field(
        default="System Generated",
        min_length=1,
        max_length=150,
    )

    auto_generate_pdf: bool = True

    @field_validator(
        "daily_time",
        "weekly_time",
        "monthly_time",
        "yearly_time",
    )
    @classmethod
    def validate_time(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not re.fullmatch(
            r"([01]\d|2[0-3]):[0-5]\d",
            normalized,
        ):
            raise ValueError(
                "Time must use 24-hour HH:MM format."
            )

        return normalized


class ReportAutomationSettingsResponse(
    ReportAutomationSettingsUpdate
):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    last_scheduler_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReportAutomationRunResponse(BaseModel):
    generated_count: int
    generated_reports: list[
        ReportResponse
    ]
    message: str


class ReportAutomationStatusItem(BaseModel):
    frequency: str
    enabled: bool
    last_report_code: str | None = None
    last_period_start: date | None = None
    last_period_end: date | None = None
    last_status: str | None = None
    next_run_at: datetime | None = None


class ReportAutomationStatusResponse(BaseModel):
    items: list[
        ReportAutomationStatusItem
    ]


class ReportVersionHistoryResponse(BaseModel):
    series_code: str
    versions: list[
        ReportResponse
    ]
