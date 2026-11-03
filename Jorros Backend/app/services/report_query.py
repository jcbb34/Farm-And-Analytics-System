from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import FarmReport


def build_report_filter_statement(
    *,
    include_archived: bool = False,
    search: str | None = None,
    category: str | None = None,
    report_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    tab: str | None = None,
):
    """Apply the same filters to report pages and their matching total."""
    statement = select(FarmReport)
    if not include_archived:
        statement = statement.where(FarmReport.status != "Archived")
    if tab == "Farm Performance":
        statement = statement.where(
            FarmReport.category == "Farm",
            FarmReport.report_type.in_(("Farm Performance Report", "Farm Summary")),
        )
    elif tab == "Workforce Reports":
        statement = statement.where(FarmReport.category == "Workforce")
    elif tab == "Task Reports":
        statement = statement.where(FarmReport.category == "Tasks")
    elif tab == "Care Compliance":
        statement = statement.where(FarmReport.category == "Care Compliance")
    elif tab == "Crop Reports":
        statement = statement.where(FarmReport.category == "Crop")
    elif tab == "Livestock Reports":
        statement = statement.where(FarmReport.category == "Livestock")
    elif tab == "Production & Sales":
        statement = statement.where(or_(
            FarmReport.category == "Production & Sales",
            (FarmReport.category == "Livestock") & FarmReport.report_type.in_(
                ("Production & Sales Summary", "Processing Summary")
            ),
        ))
    elif tab == "Trend & Seasonal Analysis":
        statement = statement.where(or_(
            FarmReport.category == "Trend & Seasonal",
            (FarmReport.category == "Farm") & (FarmReport.report_type == "Trend & Seasonal Analysis"),
        ))
    elif tab == "Inventory Reports":
        statement = statement.where(FarmReport.category == "Inventory")
    elif tab == "Audit Trail":
        statement = statement.where(FarmReport.category == "Audit")
    if category:
        statement = statement.where(FarmReport.category == category)
    if report_status:
        statement = statement.where(FarmReport.status == report_status)
    if start_date:
        statement = statement.where(FarmReport.start_date >= start_date)
    if end_date:
        statement = statement.where(FarmReport.end_date <= end_date)
    if source:
        normalized_source = source.strip().lower()
        if normalized_source == "system":
            statement = statement.where(FarmReport.is_automatic == True)  # noqa: E712
        elif normalized_source == "manual":
            statement = statement.where(FarmReport.is_automatic == False)  # noqa: E712
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(or_(
            FarmReport.report_code.ilike(term),
            FarmReport.title.ilike(term),
            FarmReport.report_type.ilike(term),
            FarmReport.prepared_by.ilike(term),
            FarmReport.frequency.ilike(term),
            FarmReport.revision_group_code.ilike(term),
        ))
    return statement


def build_report_list_statement(*, offset: int = 0, limit: int = 100, **filters):
    """Preserve the list API while applying filters before pagination."""
    statement = build_report_filter_statement(**filters)
    return statement.order_by(FarmReport.id.desc()).offset(offset).limit(limit)


def report_list_summary(db: Session, **filters) -> dict[str, int]:
    matching_ids = build_report_filter_statement(**filters).with_only_columns(FarmReport.id).subquery()
    matching_total = db.scalar(select(func.count()).select_from(matching_ids)) or 0
    total, approved, for_review, automatic = db.execute(
        select(
            func.count(FarmReport.id),
            func.coalesce(func.sum(case((FarmReport.status.in_(("Approved", "Final", "Revised")), 1), else_=0)), 0),
            func.coalesce(func.sum(case((FarmReport.status.in_(("For Review", "Needs Review")), 1), else_=0)), 0),
            func.coalesce(func.sum(case((FarmReport.is_automatic == True, 1), else_=0)), 0),  # noqa: E712
        ).where(FarmReport.status != "Archived")
    ).one()
    return {
        "matching_total": int(matching_total),
        "total": int(total),
        "approved": int(approved),
        "for_review": int(for_review),
        "automatic": int(automatic),
        "custom": int(total - automatic),
    }
