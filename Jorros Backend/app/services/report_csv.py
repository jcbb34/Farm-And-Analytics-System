from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from app.models import FarmReport
from app.services.csv_safety import SafeCsvWriter


def _write_section(
    writer: csv.writer,
    title: str,
    rows: list[dict[str, Any]],
):
    writer.writerow([])
    writer.writerow([title])

    if not rows:
        writer.writerow([
            "No records available"
        ])
        return

    keys = []

    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(
                    key
                )

    writer.writerow(
        keys
    )

    for row in rows:
        writer.writerow(
            [
                row.get(
                    key,
                    ""
                )
                for key in keys
            ]
        )


def build_report_csv(
    report: FarmReport,
) -> str:
    output = StringIO(
        newline=""
    )

    writer = SafeCsvWriter(
        csv.writer(output)
    )

    writer.writerow([
        "Joross Farm",
        "Supporting Report Data",
    ])
    writer.writerow([
        "Report Code",
        report.report_code,
    ])
    writer.writerow([
        "Revision",
        report.revision_number,
    ])
    writer.writerow([
        "Title",
        report.title,
    ])
    writer.writerow([
        "Category",
        report.category,
    ])
    writer.writerow([
        "Report Type",
        report.report_type,
    ])
    writer.writerow([
        "Status",
        report.status,
    ])
    writer.writerow([
        "Start Date",
        report.start_date,
    ])
    writer.writerow([
        "End Date",
        report.end_date,
    ])
    writer.writerow([
        "Prepared By",
        report.prepared_by,
    ])
    writer.writerow([
        "Reviewed By",
        report.reviewed_by_name
        or "",
    ])

    snapshot = report.snapshot

    if snapshot.get("report_kind") == "operational_factual":
        writer.writerow(["Generated Source", "System" if report.is_automatic else "Manual"])
        writer.writerow(["Generated Time", report.created_at])
        writer.writerow(["Report Period", f"{report.start_date} to {report.end_date}"])
        filters = snapshot.get("filters", {})
        if filters:
            writer.writerow([])
            writer.writerow(["Applied Filters"])
            for key, value in filters.items():
                writer.writerow([key, value])
        _write_section(writer, "Report Metrics", [snapshot.get("metrics", {})])
        _write_section(writer, "Report Details", snapshot.get("operational_rows", []))
        for section_name, rows in snapshot.get("sections", {}).items():
            if isinstance(rows, list):
                _write_section(writer, section_name.replace("_", " ").title(), rows)
        _write_section(writer, "Data Quality / Notes", [{"note": value} for value in snapshot.get("data_notes", [])])
        return output.getvalue()

    _write_section(writer, "Executive KPIs", report.executive_kpis)
    _write_section(writer, "Performance and Variance", report.performance_variance)
    _write_section(writer, "Risks and Issues", report.risk_flags)

    if report.category in {"Farm", "Trend & Seasonal"}:
        crop = snapshot.get(
            "crop",
            {},
        )
        livestock = snapshot.get(
            "livestock",
            {},
        )
        inventory = snapshot.get(
            "inventory",
            {},
        )

        _write_section(
            writer,
            "Crop Harvest / Yield Records",
            crop.get("yield_records", []),
        )

        _write_section(
            writer,
            "Crop Production Availability",
            crop.get("production_records", []),
        )

        _write_section(
            writer,
            "Crop Sales Transactions",
            crop.get("sales_records", []),
        )

        _write_section(
            writer,
            "Crop Payment Collections",
            crop.get("payment_records", []),
        )

        _write_section(
            writer,
            "Crop Performance",
            crop.get(
                "crop_performance",
                [],
            ),
        )

        _write_section(
            writer,
            "Crop Growth",
            crop.get(
                "growth_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Pest and Disease",
            crop.get(
                "pest_disease",
                {},
            ).get(
                "records",
                [],
            ),
        )

        _write_section(
            writer,
            "Livestock Records",
            livestock.get(
                "livestock_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Vaccination Records",
            livestock.get(
                "vaccination_records",
                [],
            ),
        )

        _write_section(writer, "Reproduction Records", livestock.get("reproduction_records", []))
        _write_section(writer, "Livestock Growth History", livestock.get("growth_records", []))
        _write_section(writer, "Confirmed Feeding Records", livestock.get("feeding_records", []))
        _write_section(writer, "Production Records", livestock.get("production_records", []))
        _write_section(writer, "Processing Records", livestock.get("processing_records", []))
        _write_section(writer, "Sales Transactions", livestock.get("sales_records", []))
        _write_section(writer, "Payment Collections", livestock.get("payment_records", []))

        _write_section(
            writer,
            "Inventory Records",
            inventory.get(
                "inventory_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Stock Movements",
            inventory.get(
                "stock_movements",
                [],
            ),
        )

        _write_section(
            writer,
            "Farm Resource Usage",
            inventory.get("resource_usage", {}).get("records", []),
        )

        trends = snapshot.get("trend_analysis", {})
        _write_section(writer, "Monthly Production Trends", trends.get("monthly", []))
        _write_section(writer, "Seasonal Pattern Summary", trends.get("seasonal", []))
        _write_section(writer, "Performance Factor Analysis", trends.get("factor_analysis", []))
        _write_section(writer, "Livestock Growth Performance", trends.get("growth_summary", []))

    elif report.category == "Production & Sales":
        crop = snapshot.get("crop", {})
        livestock = snapshot.get("livestock", {})

        _write_section(writer, "Crop Harvest / Yield Records", crop.get("yield_records", []))
        _write_section(writer, "Crop Production Availability", crop.get("production_records", []))
        _write_section(writer, "Crop Sales Transactions", crop.get("sales_records", []))
        _write_section(writer, "Crop Payment Collections", crop.get("payment_records", []))
        _write_section(writer, "Livestock Production Records", livestock.get("production_records", []))
        _write_section(writer, "Processing Records", livestock.get("processing_records", []))
        _write_section(writer, "Livestock Sales Transactions", livestock.get("sales_records", []))
        _write_section(writer, "Payment Collections", livestock.get("payment_records", []))

    elif report.category == "Crop":
        _write_section(
            writer,
            "Crop Harvest / Yield Records",
            snapshot.get("yield_records", []),
        )

        _write_section(
            writer,
            "Crop Production Availability",
            snapshot.get("production_records", []),
        )

        _write_section(
            writer,
            "Crop Sales Transactions",
            snapshot.get("sales_records", []),
        )

        _write_section(
            writer,
            "Crop Payment Collections",
            snapshot.get("payment_records", []),
        )

        _write_section(
            writer,
            "Crop Performance",
            snapshot.get(
                "crop_performance",
                [],
            ),
        )

        _write_section(
            writer,
            "Crop Growth",
            snapshot.get(
                "growth_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Pest and Disease",
            snapshot.get(
                "pest_disease",
                {},
            ).get(
                "records",
                [],
            ),
        )

        _write_section(
            writer,
            "Crop Resource Usage",
            snapshot.get("resource_usage", {}).get("records", []),
        )

    elif report.category == "Livestock":
        _write_section(
            writer,
            "Livestock Records",
            snapshot.get(
                "livestock_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Vaccination Records",
            snapshot.get(
                "vaccination_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Reproduction Records",
            snapshot.get("reproduction_records", []),
        )

        _write_section(
            writer,
            "Livestock Growth History",
            snapshot.get("growth_records", []),
        )

        _write_section(
            writer,
            "Confirmed Feeding Records",
            snapshot.get("feeding_records", []),
        )

        _write_section(
            writer,
            "Production Records",
            snapshot.get("production_records", []),
        )

        _write_section(
            writer,
            "Processing Records",
            snapshot.get("processing_records", []),
        )

        _write_section(
            writer,
            "Sales Transactions",
            snapshot.get("sales_records", []),
        )

        _write_section(
            writer,
            "Payment Collections",
            snapshot.get("payment_records", []),
        )

        _write_section(
            writer,
            "Livestock Resource Usage",
            snapshot.get("resource_usage", {}).get("records", []),
        )

    else:
        _write_section(
            writer,
            "Inventory Records",
            snapshot.get(
                "inventory_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Low Stock Records",
            snapshot.get(
                "low_stock_records",
                [],
            ),
        )

        _write_section(
            writer,
            "Expiring Inventory",
            snapshot.get("expiring_records", []),
        )

        _write_section(
            writer,
            "Resource Usage",
            snapshot.get("resource_usage", {}).get("records", []),
        )

        _write_section(
            writer,
            "Stock Movements",
            snapshot.get(
                "stock_movements",
                [],
            ),
        )

    writer.writerow([])
    writer.writerow([
        "Findings",
    ])

    for finding in report.findings:
        writer.writerow([
            finding
        ])

    writer.writerow([])
    writer.writerow([
        "Recommendations",
    ])

    for recommendation in (
        report.recommendations
    ):
        writer.writerow([
            recommendation
        ])

    writer.writerow([])
    writer.writerow([
        "Data Quality Notices",
    ])

    for notice in (
        report.data_quality
    ):
        writer.writerow([
            notice.get(
                "level",
                ""
            ),
            notice.get(
                "message",
                ""
            ),
        ])

    return output.getvalue()
