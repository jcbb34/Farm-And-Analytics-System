from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FarmReport, User
from app.services.report_builder import (
    build_report_snapshot,
)
from app.services.operational_report_builder import (
    OPERATIONAL_REPORT_TYPES,
    build_operational_report_snapshot,
)
from app.core.farm_time import farm_today, farm_now_naive
from app.services.report_insights import (
    build_comparison,
    build_data_quality_notices,
    build_executive_kpis,
    build_findings,
    build_performance_variance,
    build_recommendations,
    build_risk_flags,
    previous_period,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.schemas.reports import DEFAULT_REPORT_SECTIONS
from app.services.report_pdf import (
    generate_report_pdf,
)


def generate_report_code(
    db: Session,
) -> str:
    acquire_transaction_lock(db, "code:report")
    codes = db.scalars(
        select(
            FarmReport.report_code
        )
    ).all()

    highest = 1000

    for code in codes:
        try:
            number = int(
                "".join(
                    character
                    for character in code
                    if character.isdigit()
                )
            )
            highest = max(
                highest,
                number,
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    return (
        f"RPT-{highest + 1}"
    )


def default_report_summary(
    category,
    report_type,
    start_date,
    end_date,
    snapshot,
):
    metrics = snapshot.get(
        "metrics",
        {},
    )

    if report_type in OPERATIONAL_REPORT_TYPES:
        metric_items = []
        for key, value in list(metrics.items())[:4]:
            label = key.replace("_", " ").title()
            metric_items.append(f"{label}: {value}")
        suffix = "; ".join(metric_items) if metric_items else "No recorded source rows for the selected filters."
        return f"{report_type} for {start_date} to {end_date}. {suffix}"

    if category == "Farm":
        if report_type == "Trend & Seasonal Analysis":
            coverage = snapshot.get("trend_analysis", {}).get("data_coverage", {})
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"{coverage.get('crop_yield_records', 0)} crop-yield record(s), "
                f"{coverage.get('weather_records', 0)} weather observation(s), "
                f"{coverage.get('livestock_growth_records', 0)} livestock growth measurement(s), "
                f"{coverage.get('feeding_records', 0)} feeding record(s), and "
                f"{coverage.get('livestock_production_records', 0)} livestock production record(s) analyzed."
            )

        if report_type == "Farm Performance Report":
            return (
                f"Farm performance for {start_date} to {end_date}: "
                f"{metrics.get('total_harvest_kg', 0)} kg crop harvest, "
                f"{metrics.get('survival_rate_percent', 0)}% crop survival, "
                f"{metrics.get('total_head', 0)} livestock head, "
                f"PHP {float(metrics.get('gross_sales_value', 0) or 0):,.2f} gross sales, "
                f"{metrics.get('collection_rate_percent', 0)}% collection rate, "
                f"and {metrics.get('low_stock_items', 0)} low-stock inventory item(s)."
            )

        return (
            f"{report_type} for {start_date} to {end_date}: "
            f"{metrics.get('crop_records', 0)} crop record(s), "
            f"{metrics.get('total_harvest_kg', 0)} kg recorded harvest, "
            f"{metrics.get('total_head', 0)} livestock head count, "
            f"{metrics.get('inventory_items', 0)} inventory item(s), "
            f"and {metrics.get('low_stock_items', 0)} low-stock item(s)."
        )

    if category == "Crop":
        return (
            f"{report_type} for {start_date} to {end_date}: "
            f"{metrics.get('crop_records', 0)} crop record(s), "
            f"{metrics.get('total_harvest_kg', 0)} kg recorded harvest, "
            f"and {metrics.get('total_area_ha', 0)} ha monitored."
        )

    if category == "Production & Sales":
        gross = float(metrics.get("gross_sales_value", 0) or 0)
        cash = float(metrics.get("cash_collected", 0) or 0)
        outstanding = float(metrics.get("outstanding_balance", 0) or 0)
        if report_type == "Crop Production & Sales":
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"{metrics.get('crop_harvest_kg', 0)} kg harvested, "
                f"{metrics.get('crop_available_kg', 0)} kg available, "
                f"PHP {float(metrics.get('crop_sales_value', 0) or 0):,.2f} crop sales, and "
                f"PHP {outstanding:,.2f} outstanding."
            )
        if report_type == "Livestock Production & Sales":
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"{metrics.get('egg_production_pcs', 0)} pcs eggs produced, "
                f"{metrics.get('meat_output_kg', 0)} kg meat output, "
                f"PHP {float(metrics.get('livestock_sales_value', 0) or 0):,.2f} livestock/product sales, and "
                f"PHP {outstanding:,.2f} outstanding."
            )
        if report_type == "Processing Report":
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"{metrics.get('animals_processed_head', 0)} head processed and "
                f"{metrics.get('meat_output_kg', 0)} kg meat output recorded."
            )
        if report_type == "Receivables Report":
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"PHP {gross:,.2f} gross sales, PHP {cash:,.2f} collected, "
                f"and PHP {outstanding:,.2f} outstanding."
            )
        if report_type == "Sales Summary":
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"PHP {float(metrics.get('crop_sales_value', 0) or 0):,.2f} crop sales, "
                f"PHP {float(metrics.get('livestock_sales_value', 0) or 0):,.2f} livestock sales, "
                f"and PHP {outstanding:,.2f} outstanding."
            )
        return (
            f"{report_type} for {start_date} to {end_date}: "
            f"{metrics.get('crop_harvest_kg', 0)} kg crop harvest, "
            f"{metrics.get('egg_production_pcs', 0)} pcs eggs produced, "
            f"{metrics.get('meat_output_kg', 0)} kg meat output, and "
            f"PHP {gross:,.2f} gross sales."
        )

    if category == "Trend & Seasonal":
        coverage = snapshot.get("trend_analysis", {}).get("data_coverage", {})
        return (
            f"Trend & Seasonal Analysis for {start_date} to {end_date}: "
            f"{coverage.get('crop_yield_records', 0)} crop-yield record(s), "
            f"{coverage.get('weather_records', 0)} weather observation(s), "
            f"{coverage.get('livestock_growth_records', 0)} livestock growth measurement(s), "
            f"{coverage.get('livestock_production_records', 0)} livestock production record(s), and "
            f"{coverage.get('sales_records', 0)} sale record(s) analyzed."
        )

    if category == "Livestock":
        if report_type in {"Production & Sales Summary", "Processing Summary", "Livestock Production"}:
            return (
                f"{report_type} for {start_date} to {end_date}: "
                f"{metrics.get('production_records_in_period', 0)} production record(s), "
                f"{metrics.get('animals_processed_head', 0)} animal(s) processed, "
                f"₱{float(metrics.get('gross_sales_value', 0) or 0):,.2f} gross sales, "
                f"₱{float(metrics.get('cash_collected', 0) or 0):,.2f} collected, and "
                f"₱{float(metrics.get('outstanding_balance', 0) or 0):,.2f} outstanding."
            )

        return (
            f"{report_type} for {start_date} to {end_date}: "
            f"{metrics.get('total_head', 0)} animal(s), "
            f"{metrics.get('growth_measurements_in_period', 0)} growth measurement(s), "
            f"and {metrics.get('vaccinations_in_period', 0)} vaccination record(s)."
        )

    return (
        f"{report_type} for {start_date} to {end_date}: "
        f"{metrics.get('inventory_items', 0)} inventory item(s), "
        f"{metrics.get('low_stock_items', 0)} low-stock item(s), "
        f"and {metrics.get('stock_movements', 0)} stock movement(s)."
    )


def _analytics_payload(
    db: Session,
    *,
    category: str,
    report_type: str,
    start_date: date,
    end_date: date,
    frequency: str | None,
    included_sections: list[str] | None = None,
    filters: dict[str, object] | None = None,
):
    is_operational = report_type in OPERATIONAL_REPORT_TYPES
    snapshot = (
        build_operational_report_snapshot(
            db, report_type, start_date, end_date, filters or {}
        )
        if is_operational
        else build_report_snapshot(
            db, category, report_type, start_date, end_date
        )
    )

    if is_operational:
        selected_sections = list(
            included_sections
            or snapshot.get("report_options", {}).get("included_sections")
            or DEFAULT_REPORT_SECTIONS
        )
        # Reports are factual historical outputs. Operational report types intentionally
        # do not create recommendations or predictive findings.
        snapshot["report_options"] = {
            "included_sections": selected_sections,
            "filters": dict(filters or {}),
        }
        snapshot["executive_kpis"] = [
            {"label": key.replace("_", " ").title(), "value": value}
            for key, value in snapshot.get("metrics", {}).items()
        ][:8]
        snapshot["performance_variance"] = []
        snapshot["risk_flags"] = []
        return {
            "snapshot": snapshot,
            "comparison": {},
            "data_quality": list(snapshot.get("data_notes", [])),
            "findings": [],
            "recommendations": [],
        }

    (
        previous_start,
        previous_end,
    ) = previous_period(
        start_date,
        end_date,
        frequency,
    )

    previous_report = db.scalar(
        select(
            FarmReport
        )
        .where(
            FarmReport.category
            == category,
            FarmReport.report_type
            == report_type,
            FarmReport.start_date
            == previous_start,
            FarmReport.end_date
            == previous_end,
            FarmReport.status
            != "Archived",
        )
        .order_by(
            FarmReport.revision_number.desc(),
            FarmReport.id.desc(),
        )
        .limit(
            1
        )
    )

    previous_snapshot_is_saved = (
        previous_report
        is not None
    )

    previous_snapshot = (
        previous_report.snapshot
        if previous_report
        else build_report_snapshot(
            db,
            category,
            report_type,
            previous_start,
            previous_end,
        )
    )

    comparison = build_comparison(
        snapshot,
        previous_snapshot,
        previous_start,
        previous_end,
        previous_snapshot_is_saved=(
            previous_snapshot_is_saved
        ),
    )

    analysis_category = "Farm" if category == "Trend & Seasonal" else category

    data_quality = (
        build_data_quality_notices(
            analysis_category,
            snapshot,
        )
    )

    findings = build_findings(
        analysis_category,
        snapshot,
        comparison,
    )

    recommendations = (
        build_recommendations(
            analysis_category,
            snapshot,
            comparison,
            data_quality,
        )
    )

    selected_sections = list(
        included_sections
        or snapshot.get("report_options", {}).get("included_sections")
        or DEFAULT_REPORT_SECTIONS
    )
    snapshot["report_options"] = {
        "included_sections": selected_sections,
    }
    snapshot["executive_kpis"] = build_executive_kpis(
        analysis_category, snapshot
    )
    snapshot["performance_variance"] = build_performance_variance(
        analysis_category, snapshot
    )
    snapshot["risk_flags"] = build_risk_flags(
        analysis_category,
        snapshot,
        comparison,
        data_quality,
    )

    return {
        "snapshot": snapshot,
        "comparison": comparison,
        "data_quality": data_quality,
        "findings": findings,
        "recommendations": recommendations,
    }


def create_report_record(
    db: Session,
    *,
    title: str,
    category: str,
    report_type: str,
    start_date: date,
    end_date: date,
    prepared_by: str,
    status: str = "Draft",
    summary: str | None = None,
    generated_by_user_id: int | None = None,
    is_automatic: bool = False,
    frequency: str | None = None,
    automation_period_key: str | None = None,
    generate_pdf: bool = True,
    revision_group_code: str | None = None,
    revision_number: int = 1,
    revision_of_report_id: int | None = None,
    included_sections: list[str] | None = None,
    filters: dict[str, object] | None = None,
) -> FarmReport:
    analytics = _analytics_payload(
        db,
        category=category,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
        included_sections=included_sections,
        filters=filters,
    )

    report_code = generate_report_code(
        db
    )

    report = FarmReport(
        report_code=report_code,
        title=title.strip(),
        category=category,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        generated_date=farm_today(),
        prepared_by=prepared_by.strip(),
        status=status,
        summary=(
            summary.strip()
            if summary
            else default_report_summary(
                category,
                report_type,
                start_date,
                end_date,
                analytics[
                    "snapshot"
                ],
            )
        ),
        snapshot_json=json.dumps(
            analytics[
                "snapshot"
            ],
            ensure_ascii=False,
        ),
        comparison_json=json.dumps(
            analytics[
                "comparison"
            ],
            ensure_ascii=False,
        ),
        findings_json=json.dumps(
            analytics[
                "findings"
            ],
            ensure_ascii=False,
        ),
        recommendations_json=json.dumps(
            analytics[
                "recommendations"
            ],
            ensure_ascii=False,
        ),
        data_quality_json=json.dumps(
            analytics[
                "data_quality"
            ],
            ensure_ascii=False,
        ),
        generated_by_user_id=generated_by_user_id,
        submitted_at=(
            farm_now_naive()
            if status
            == "For Review"
            else None
        ),
        is_automatic=is_automatic,
        frequency=frequency,
        automation_period_key=automation_period_key,
        revision_group_code=(
            revision_group_code
            or report_code
        ),
        revision_number=revision_number,
        revision_of_report_id=revision_of_report_id,
    )

    db.add(
        report
    )
    db.commit()
    db.refresh(
        report
    )

    if generate_pdf:
        try:
            pdf_path = (
                generate_report_pdf(
                    report
                )
            )

            report.pdf_filename = (
                pdf_path.name
            )

            db.commit()
            db.refresh(
                report
            )
        except Exception as error:
            print(
                "Report PDF generation failed:",
                error,
            )

    return report



def refresh_report_analysis(
    db: Session,
    report: FarmReport,
) -> FarmReport:
    if report.report_type in OPERATIONAL_REPORT_TYPES:
        filters = report.snapshot.get("filters") or report.snapshot.get("report_options", {}).get("filters") or {}
        analytics = _analytics_payload(
            db, category=report.category, report_type=report.report_type,
            start_date=report.start_date, end_date=report.end_date,
            frequency=report.frequency, included_sections=report.included_sections,
            filters=filters,
        )
        report.snapshot_json = json.dumps(analytics["snapshot"], ensure_ascii=False)
        report.comparison_json = "{}"
        report.data_quality_json = json.dumps(analytics["data_quality"], ensure_ascii=False)
        report.findings_json = "[]"
        report.recommendations_json = "[]"
        report.updated_at = farm_now_naive()
        db.commit()
        db.refresh(report)
        return report
    (
        previous_start,
        previous_end,
    ) = previous_period(
        report.start_date,
        report.end_date,
        report.frequency,
    )

    previous_report = db.scalar(
        select(
            FarmReport
        )
        .where(
            FarmReport.category
            == report.category,
            FarmReport.report_type
            == report.report_type,
            FarmReport.start_date
            == previous_start,
            FarmReport.end_date
            == previous_end,
            FarmReport.id
            != report.id,
            FarmReport.status
            != "Archived",
        )
        .order_by(
            FarmReport.revision_number.desc(),
            FarmReport.id.desc(),
        )
        .limit(
            1
        )
    )

    previous_snapshot_is_saved = (
        previous_report
        is not None
    )

    previous_snapshot = (
        previous_report.snapshot
        if previous_report
        else build_report_snapshot(
            db,
            report.category,
            report.report_type,
            previous_start,
            previous_end,
        )
    )

    comparison = build_comparison(
        report.snapshot,
        previous_snapshot,
        previous_start,
        previous_end,
        previous_snapshot_is_saved=(
            previous_snapshot_is_saved
        ),
    )

    analysis_category = "Farm" if report.category == "Trend & Seasonal" else report.category

    data_quality = (
        build_data_quality_notices(
            analysis_category,
            report.snapshot,
        )
    )

    findings = build_findings(
        analysis_category,
        report.snapshot,
        comparison,
    )

    recommendations = (
        build_recommendations(
            analysis_category,
            report.snapshot,
            comparison,
            data_quality,
        )
    )

    snapshot = dict(report.snapshot)
    selected_sections = list(
        snapshot.get("report_options", {}).get("included_sections")
        or DEFAULT_REPORT_SECTIONS
    )
    snapshot["report_options"] = {
        "included_sections": selected_sections,
    }
    snapshot["executive_kpis"] = build_executive_kpis(
        analysis_category, snapshot
    )
    snapshot["performance_variance"] = build_performance_variance(
        analysis_category, snapshot
    )
    snapshot["risk_flags"] = build_risk_flags(
        analysis_category,
        snapshot,
        comparison,
        data_quality,
    )
    report.snapshot_json = json.dumps(
        snapshot, ensure_ascii=False
    )

    report.comparison_json = json.dumps(
        comparison,
        ensure_ascii=False,
    )
    report.data_quality_json = json.dumps(
        data_quality,
        ensure_ascii=False,
    )
    report.findings_json = json.dumps(
        findings,
        ensure_ascii=False,
    )
    report.recommendations_json = json.dumps(
        recommendations,
        ensure_ascii=False,
    )
    report.updated_at = datetime.now()

    db.commit()
    db.refresh(
        report
    )

    return report

def create_revision(
    db: Session,
    source: FarmReport,
    generated_by_user_id: int | None,
) -> FarmReport:
    series_code = (
        source.revision_group_code
        or source.report_code
    )

    highest_revision = db.scalar(
        select(
            FarmReport.revision_number
        )
        .where(
            FarmReport.revision_group_code
            == series_code
        )
        .order_by(
            FarmReport.revision_number.desc()
        )
        .limit(
            1
        )
    ) or 1

    next_revision = (
        int(
            highest_revision
        )
        + 1
    )

    prepared_by = source.prepared_by
    if generated_by_user_id:
        author = db.get(
            User,
            generated_by_user_id,
        )
        if author is not None:
            prepared_by = (
                author.full_name
                or author.username
                or prepared_by
            )

    return create_report_record(
        db,
        title=source.title,
        category=source.category,
        report_type=source.report_type,
        start_date=source.start_date,
        end_date=source.end_date,
        prepared_by=prepared_by,
        status=("Revised" if source.report_type in OPERATIONAL_REPORT_TYPES else "Draft"),
        summary=source.summary,
        generated_by_user_id=generated_by_user_id,
        is_automatic=False,
        frequency=None,
        automation_period_key=None,
        generate_pdf=True,
        revision_group_code=series_code,
        revision_number=next_revision,
        revision_of_report_id=source.id,
        included_sections=(
            source.included_sections
            or list(DEFAULT_REPORT_SECTIONS)
        ),
        filters=(source.snapshot.get("filters") or source.snapshot.get("report_options", {}).get("filters") or {}),
    )
