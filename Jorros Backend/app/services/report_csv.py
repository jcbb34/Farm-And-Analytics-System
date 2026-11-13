from __future__ import annotations
import csv
from io import StringIO
from typing import Any
from app.models import FarmReport
from app.services.csv_safety import SafeCsvWriter


def _section_rows(title: str, rows: list[dict[str, Any]]):
    yield []
    yield [title]
    if not rows:
        yield ["No records available"]
        return
    keys = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    yield keys
    for row in rows:
        yield [row.get(key, "") for key in keys]


def _report_rows(report: FarmReport):
    yield ["Joross Farm", "Supporting Report Data"]
    yield ["Report Code", report.report_code]
    yield ["Revision", report.revision_number]
    yield ["Title", report.title]
    yield ["Category", report.category]
    yield ["Report Type", report.report_type]
    yield ["Status", report.status]
    yield ["Start Date", report.start_date]
    yield ["End Date", report.end_date]
    yield ["Prepared By", report.prepared_by]
    yield ["Reviewed By", report.reviewed_by_name or ""]
    snapshot = report.snapshot
    if snapshot.get("report_kind") == "operational_factual":
        yield ["Generated Source", "System" if report.is_automatic else "Manual"]
        yield ["Generated Time", report.created_at]
        yield ["Report Period", f"{report.start_date} to {report.end_date}"]
        filters = snapshot.get("filters", {})
        if filters:
            yield []
            yield ["Applied Filters"]
            for key, value in filters.items():
                yield [key, value]
        yield from _section_rows("Report Metrics", [snapshot.get("metrics", {})])
        yield from _section_rows("Report Details", snapshot.get("operational_rows", []))
        for section_name, rows in snapshot.get("sections", {}).items():
            if isinstance(rows, list):
                yield from _section_rows(section_name.replace("_", " ").title(), rows)
        yield from _section_rows(
            "Data Quality / Notes",
            [{"note": value} for value in snapshot.get("data_notes", [])],
        )
        return
    yield from _section_rows("Executive KPIs", report.executive_kpis)
    yield from _section_rows("Performance and Variance", report.performance_variance)
    yield from _section_rows("Risks and Issues", report.risk_flags)
    if report.category in {"Farm", "Trend & Seasonal"}:
        crop = snapshot.get("crop", {})
        livestock = snapshot.get("livestock", {})
        inventory = snapshot.get("inventory", {})
        yield from _section_rows(
            "Crop Harvest / Yield Records", crop.get("yield_records", [])
        )
        yield from _section_rows(
            "Crop Production Availability", crop.get("production_records", [])
        )
        yield from _section_rows(
            "Crop Sales Transactions", crop.get("sales_records", [])
        )
        yield from _section_rows(
            "Crop Payment Collections", crop.get("payment_records", [])
        )
        yield from _section_rows("Crop Performance", crop.get("crop_performance", []))
        yield from _section_rows("Crop Growth", crop.get("growth_records", []))
        yield from _section_rows(
            "Pest and Disease", crop.get("pest_disease", {}).get("records", [])
        )
        yield from _section_rows(
            "Livestock Records", livestock.get("livestock_records", [])
        )
        yield from _section_rows(
            "Vaccination Records", livestock.get("vaccination_records", [])
        )
        yield from _section_rows(
            "Reproduction Records", livestock.get("reproduction_records", [])
        )
        yield from _section_rows(
            "Livestock Growth History", livestock.get("growth_records", [])
        )
        yield from _section_rows(
            "Confirmed Feeding Records", livestock.get("feeding_records", [])
        )
        yield from _section_rows(
            "Production Records", livestock.get("production_records", [])
        )
        yield from _section_rows(
            "Processing Records", livestock.get("processing_records", [])
        )
        yield from _section_rows(
            "Sales Transactions", livestock.get("sales_records", [])
        )
        yield from _section_rows(
            "Payment Collections", livestock.get("payment_records", [])
        )
        yield from _section_rows(
            "Inventory Records", inventory.get("inventory_records", [])
        )
        yield from _section_rows(
            "Stock Movements", inventory.get("stock_movements", [])
        )
        yield from _section_rows(
            "Farm Resource Usage",
            inventory.get("resource_usage", {}).get("records", []),
        )
        trends = snapshot.get("trend_analysis", {})
        yield from _section_rows("Monthly Production Trends", trends.get("monthly", []))
        yield from _section_rows("Seasonal Pattern Summary", trends.get("seasonal", []))
        yield from _section_rows(
            "Performance Factor Analysis", trends.get("factor_analysis", [])
        )
        yield from _section_rows(
            "Livestock Growth Performance", trends.get("growth_summary", [])
        )
    elif report.category == "Production & Sales":
        crop = snapshot.get("crop", {})
        livestock = snapshot.get("livestock", {})
        yield from _section_rows(
            "Crop Harvest / Yield Records", crop.get("yield_records", [])
        )
        yield from _section_rows(
            "Crop Production Availability", crop.get("production_records", [])
        )
        yield from _section_rows(
            "Crop Sales Transactions", crop.get("sales_records", [])
        )
        yield from _section_rows(
            "Crop Payment Collections", crop.get("payment_records", [])
        )
        yield from _section_rows(
            "Livestock Production Records", livestock.get("production_records", [])
        )
        yield from _section_rows(
            "Processing Records", livestock.get("processing_records", [])
        )
        yield from _section_rows(
            "Livestock Sales Transactions", livestock.get("sales_records", [])
        )
        yield from _section_rows(
            "Payment Collections", livestock.get("payment_records", [])
        )
    elif report.category == "Crop":
        yield from _section_rows(
            "Crop Harvest / Yield Records", snapshot.get("yield_records", [])
        )
        yield from _section_rows(
            "Crop Production Availability", snapshot.get("production_records", [])
        )
        yield from _section_rows(
            "Crop Sales Transactions", snapshot.get("sales_records", [])
        )
        yield from _section_rows(
            "Crop Payment Collections", snapshot.get("payment_records", [])
        )
        yield from _section_rows(
            "Crop Performance", snapshot.get("crop_performance", [])
        )
        yield from _section_rows("Crop Growth", snapshot.get("growth_records", []))
        yield from _section_rows(
            "Pest and Disease", snapshot.get("pest_disease", {}).get("records", [])
        )
        yield from _section_rows(
            "Crop Resource Usage", snapshot.get("resource_usage", {}).get("records", [])
        )
    elif report.category == "Livestock":
        yield from _section_rows(
            "Livestock Records", snapshot.get("livestock_records", [])
        )
        yield from _section_rows(
            "Vaccination Records", snapshot.get("vaccination_records", [])
        )
        yield from _section_rows(
            "Reproduction Records", snapshot.get("reproduction_records", [])
        )
        yield from _section_rows(
            "Livestock Growth History", snapshot.get("growth_records", [])
        )
        yield from _section_rows(
            "Confirmed Feeding Records", snapshot.get("feeding_records", [])
        )
        yield from _section_rows(
            "Production Records", snapshot.get("production_records", [])
        )
        yield from _section_rows(
            "Processing Records", snapshot.get("processing_records", [])
        )
        yield from _section_rows(
            "Sales Transactions", snapshot.get("sales_records", [])
        )
        yield from _section_rows(
            "Payment Collections", snapshot.get("payment_records", [])
        )
        yield from _section_rows(
            "Livestock Resource Usage",
            snapshot.get("resource_usage", {}).get("records", []),
        )
    else:
        yield from _section_rows(
            "Inventory Records", snapshot.get("inventory_records", [])
        )
        yield from _section_rows(
            "Low Stock Records", snapshot.get("low_stock_records", [])
        )
        yield from _section_rows(
            "Expiring Inventory", snapshot.get("expiring_records", [])
        )
        yield from _section_rows(
            "Resource Usage", snapshot.get("resource_usage", {}).get("records", [])
        )
        yield from _section_rows("Stock Movements", snapshot.get("stock_movements", []))
    yield []
    yield ["Findings"]
    for finding in report.findings:
        yield [finding]
    yield []
    yield ["Recommendations"]
    for recommendation in report.recommendations:
        yield [recommendation]
    yield []
    yield ["Data Quality Notices"]
    for notice in report.data_quality:
        yield [notice.get("level", ""), notice.get("message", "")]
    return


def iter_report_csv(report: FarmReport, chunk_size: int = 65536):
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    output = StringIO(newline="")
    writer = SafeCsvWriter(csv.writer(output))
    for row in _report_rows(report):
        writer.writerow(row)
        if output.tell() >= chunk_size:
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    if output.tell():
        yield output.getvalue()


def build_report_csv(report: FarmReport) -> str:
    return "".join(iter_report_csv(report))
