from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import FarmReport


BACKEND_ROOT = Path(
    __file__
).resolve().parents[2]

REPORT_DIRECTORY = (
    BACKEND_ROOT
    / "generated_reports"
)

PDF_LAYOUT_VERSION = "V5"

GREEN = colors.HexColor(
    "#166534"
)
DARK_GREEN = colors.HexColor(
    "#14532d"
)
LIGHT_GREEN = colors.HexColor(
    "#dcfce7"
)
LIGHT_GRAY = colors.HexColor(
    "#f3f4f6"
)
BORDER = colors.HexColor(
    "#d1d5db"
)
TEXT_GRAY = colors.HexColor(
    "#4b5563"
)
WARNING_BG = colors.HexColor(
    "#fef3c7"
)
APPROVED_BG = colors.HexColor(
    "#dcfce7"
)
REVIEW_BG = colors.HexColor(
    "#dbeafe"
)
DRAFT_BG = colors.HexColor(
    "#f3f4f6"
)


class NumberedCanvas(
    canvas.Canvas
):
    def __init__(
        self,
        *args,
        **kwargs,
    ):
        canvas.Canvas.__init__(
            self,
            *args,
            **kwargs,
        )
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(
            dict(
                self.__dict__
            )
        )
        self._startPage()

    def save(self):
        page_count = len(
            self._saved_page_states
        )

        for state in (
            self._saved_page_states
        ):
            self.__dict__.update(
                state
            )
            self._draw_footer(
                page_count
            )
            canvas.Canvas.showPage(
                self
            )

        canvas.Canvas.save(
            self
        )

    def _draw_footer(
        self,
        page_count,
    ):
        self.saveState()
        self.setStrokeColor(
            BORDER
        )
        self.line(
            18 * mm,
            13 * mm,
            A4[0] - 18 * mm,
            13 * mm,
        )
        self.setFont(
            "Helvetica",
            8,
        )
        self.setFillColor(
            TEXT_GRAY
        )
        self.drawString(
            18 * mm,
            8 * mm,
            "Joross Farm - Farm Analytics and Production Monitoring System",
        )
        self.drawRightString(
            A4[0] - 18 * mm,
            8 * mm,
            (
                f"Page {self._pageNumber} "
                f"of {page_count}"
            ),
        )
        self.restoreState()


def _safe(
    value: Any,
) -> str:
    if value is None:
        return (
            "Not specified"
        )

    value = str(
        value
    ).strip()

    return (
        value
        or "Not specified"
    )


def _num(
    value: Any,
    digits: int = 2,
) -> str:
    try:
        number = float(
            value or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        return _safe(
            value
        )

    if number.is_integer():
        return (
            f"{int(number):,}"
        )

    return (
        f"{number:,.{digits}f}"
    )




def _as_mapping(value: Any) -> dict[str, Any]:
    """Return a safe mapping for persisted report payload fragments.

    Historical/custom reports and operational reports can persist JSON fragments in
    slightly different shapes. PDF rendering must never crash merely because an
    older row/section was stored as a plain string.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    return {}


def _as_mapping_rows(value: Any) -> list[dict[str, Any]]:
    """Normalize table row payloads without discarding legacy textual entries."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                value = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                value = [value]
        else:
            value = [value]
    elif isinstance(value, dict):
        value = [value]

    if not isinstance(value, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in value:
        mapping = _as_mapping(item)
        if mapping:
            rows.append(mapping)
        elif item not in (None, ""):
            rows.append({"value": item})
    return rows

def _slug(
    value: str,
) -> str:
    return (
        re.sub(
            r"[^A-Za-z0-9_-]+",
            "-",
            value.strip(),
        ).strip(
            "-"
        )
        or "report"
    )


def _display_report_title(
    report: FarmReport,
) -> str:
    title = re.sub(
        r"\s+",
        " ",
        _safe(report.title),
    ).strip()

    title = re.sub(
        r"(?i)\bseasona\s*l\s*analysis\b",
        "Seasonal Analysis",
        title,
    )

    if (
        report.report_type
        == "Trend & Seasonal Analysis"
        and title.lower()
        in {
            "trend & seasonal analysis",
            "trend and seasonal analysis",
        }
    ):
        return "Trend and Seasonal Analysis"

    return title


def resolve_report_pdf_path(
    filename: str | None,
    *,
    require_current: bool = False,
) -> Path | None:
    if not filename:
        return None

    clean_name = str(filename).strip()
    if (
        not clean_name
        or Path(clean_name).name != clean_name
        or not clean_name.lower().endswith(".pdf")
    ):
        return None

    if require_current and f"_PDF-{PDF_LAYOUT_VERSION}_" not in clean_name:
        return None

    root = REPORT_DIRECTORY.resolve()
    candidate = (root / clean_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def is_current_pdf_filename(
    filename: str | None,
) -> bool:
    return resolve_report_pdf_path(
        filename,
        require_current=True,
    ) is not None


DEFAULT_REPORT_SECTIONS = [
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


def _included_sections(report: FarmReport) -> set[str]:
    selected = report.included_sections
    return set(selected or DEFAULT_REPORT_SECTIONS)


def _has_section(report: FarmReport, key: str) -> bool:
    return key in _included_sections(report)


def _styles():
    base = (
        getSampleStyleSheet()
    )

    return {
        "title": ParagraphStyle(
            "Title",
            parent=base[
                "Title"
            ],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=20,
            textColor=DARK_GREEN,
            spaceAfter=2,
            alignment=TA_CENTER,
            keepWithNext=True,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base[
                "Normal"
            ],
            fontSize=9,
            leading=12,
            textColor=TEXT_GRAY,
            alignment=TA_CENTER,
            spaceAfter=0,
            keepWithNext=True,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base[
                "Heading2"
            ],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.white,
            backColor=GREEN,
            borderPadding=5,
            spaceBefore=10,
            spaceAfter=7,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base[
                "BodyText"
            ],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor(
                "#1f2937"
            ),
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base[
                "BodyText"
            ],
            fontSize=7.5,
            leading=10,
            textColor=TEXT_GRAY,
        ),
    }


def _section(
    text,
    styles,
):
    return Paragraph(
        text,
        styles[
            "section"
        ],
    )


def _status_label(
    report: FarmReport,
    styles,
):
    background = {
        "Approved": APPROVED_BG,
        "For Review": REVIEW_BG,
        "Draft": DRAFT_BG,
        "Archived": WARNING_BG,
    }.get(
        report.status,
        LIGHT_GRAY,
    )

    table = Table(
        [[
            f"STATUS: {report.status.upper()}",
            (
                f"SERIES: "
                f"{report.revision_group_code or report.report_code} "
                f"• REVISION {report.revision_number}"
            ),
        ]],
        colWidths=[
            87 * mm,
            87 * mm,
        ],
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, 0),
                background,
            ),
            (
                "BACKGROUND",
                (1, 0),
                (1, 0),
                LIGHT_GRAY,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                DARK_GREEN,
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "LEFT",
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                BORDER,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ])
    )

    return table


def _metadata(
    report: FarmReport,
):
    data = [
        [
            "Report No.",
            report.report_code,
            "Generated",
            report.generated_date.strftime(
                "%B %d, %Y"
            ),
        ],
        [
            "Period",
            (
                f"{report.start_date.strftime('%B %d, %Y')} - "
                f"{report.end_date.strftime('%B %d, %Y')}"
            ),
            "Prepared By",
            report.prepared_by,
        ],
        [
            "Category",
            report.category,
            "Generation",
            (
                f"Automatic - {report.frequency}"
                if report.is_automatic
                else "Custom / On Demand"
            ),
        ],
        [
            "Reviewed By",
            (
                report.reviewed_by_name
                or "Pending"
            ),
            "Approved",
            (
                report.approved_at.strftime(
                    "%B %d, %Y %I:%M %p"
                )
                if report.approved_at
                else "Pending"
            ),
        ],
    ]

    table = Table(
        data,
        colWidths=[
            24 * mm,
            62 * mm,
            25 * mm,
            63 * mm,
        ],
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, -1),
                LIGHT_GRAY,
            ),
            (
                "BACKGROUND",
                (2, 0),
                (2, -1),
                LIGHT_GRAY,
            ),
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTNAME",
                (2, 0),
                (2, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                BORDER,
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ])
    )

    return table


def _metric_label(
    value: str,
) -> str:
    mapping = {
        "crop_records":
            "Crop Records",
        "total_area_ha":
            "Total Area (ha)",
        "harvest_records":
            "Harvest Records",
        "total_harvest_kg":
            "Recorded Harvest (kg)",
        "average_yield_kg_per_ha":
            "Average Yield (kg/ha)",
        "pest_disease_records":
            "Pest/Disease Cases",
        "livestock_records":
            "Livestock Records",
        "total_head":
            "Total Head Count",
        "average_record_weight_kg":
            "Average Weight (kg)",
        "average_weight_kg":
            "Average Weight (kg)",
        "daily_feed_kg":
            "Daily Feed (kg)",
        "growth_measurements_in_period":
            "Growth Measurements",
        "average_daily_gain_kg":
            "Avg. Daily Gain (kg/day)",
        "planned_feed_kg":
            "Planned Feed (kg)",
        "actual_feed_kg":
            "Actual Feed (kg)",
        "feed_variance_kg":
            "Feed Variance (kg)",
        "feed_variance_percent":
            "Feed Variance (%)",
        "feed_adherence_percent":
            "Feed Adherence (%)",
        "feeding_records_in_period":
            "Feeding Records",
        "production_records_in_period":
            "Production Records",
        "collection_rate_percent":
            "Collection Rate (%)",
        "cash_collected_value":
            "Cash Collected",
        "average_laying_rate_percent":
            "Avg. Laying Rate (%)",
        "dressing_yield_percent":
            "Dressing Yield (%)",
        "quantity_planted":
            "Quantity Planted",
        "current_surviving":
            "Current Surviving",
        "survival_rate_percent":
            "Survival Rate (%)",
        "plant_loss_count":
            "Plant Loss",
        "potential_margin_value":
            "Potential Margin",
        "reorder_shortfall_quantity":
            "Reorder Shortfall",
        "vaccinations_in_period":
            "Vaccinations",
        "inventory_items":
            "Inventory Items",
        "low_stock_items":
            "Low Stock Items",
        "stock_movements":
            "Stock Movements",
        "restock_quantity":
            "Restocked Quantity",
        "usage_quantity":
            "Used/Damaged/Expired",
        "cost_value":
            "Inventory Cost Value",
        "retail_value":
            "Inventory Retail Value",
        "inventory_cost_value":
            "Inventory Cost Value",
        "inventory_retail_value":
            "Inventory Retail Value",
        "processing_records_in_period":
            "Processing Records",
        "animals_processed_head":
            "Animals Processed",
        "processing_live_weight_kg":
            "Processed Live Weight (kg)",
        "meat_output_kg":
            "Meat Output (kg)",
        "average_dressing_yield_percent":
            "Avg. Dressing Yield (%)",
        "egg_production_pcs":
            "Egg Production (pcs)",
        "average_laying_rate_percent":
            "Avg. Laying Rate (%)",
        "eggs_available_pcs":
            "Eggs Available (pcs)",
        "meat_available_kg":
            "Meat Available (kg)",
        "gross_sales_value":
            "Gross Sales Value",
        "cash_collected":
            "Cash Collected",
        "outstanding_balance":
            "Outstanding Balance",
        "egg_sold_pcs":
            "Eggs Sold (pcs)",
        "meat_sold_kg":
            "Meat Sold (kg)",
        "egg_sell_through_percent":
            "Egg Sell-through (%)",
        "meat_sell_through_percent":
            "Meat Sell-through (%)",
        "collected_against_period_sales":
            "Collected Against Period Sales",
    }

    return mapping.get(
        value,
        value.replace(
            "_",
            " ",
        ).title(),
    )


def _metric_table(
    metrics: dict[str, Any],
):
    cells = []

    for (
        key,
        value,
    ) in metrics.items():
        if not isinstance(
            value,
            (int, float),
        ) or isinstance(
            value,
            bool,
        ):
            continue

        monetary_keys = {
            "gross_sales_value",
            "sales_revenue",
            "cash_collected",
            "cash_collected_value",
            "outstanding_balance",
            "potential_margin_value",
            "cost_value",
            "retail_value",
            "inventory_cost_value",
            "inventory_retail_value",
        }
        display_value = (
            f"P {_num(value)}"
            if key in monetary_keys
            else _num(value)
        )
        cells.append(
            (
                _metric_label(key),
                display_value,
            )
        )

    if not cells:
        return None

    rows = []

    for index in range(
        0,
        len(
            cells
        ),
        2,
    ):
        left = cells[
            index
        ]
        right = (
            cells[
                index + 1
            ]
            if index + 1
            < len(
                cells
            )
            else (
                "",
                "",
            )
        )

        metric_cell_style = ParagraphStyle(
            "MetricCell",
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9.2,
            textColor=colors.HexColor("#111827"),
            spaceBefore=0,
            spaceAfter=0,
        )
        value_cell_style = ParagraphStyle(
            "MetricValueCell",
            fontName="Helvetica",
            fontSize=7.8,
            leading=9.2,
            textColor=colors.HexColor("#111827"),
            spaceBefore=0,
            spaceAfter=0,
        )

        rows.append([
            Paragraph(_safe(left[0]), metric_cell_style),
            Paragraph(_safe(left[1]), value_cell_style),
            Paragraph(_safe(right[0]), metric_cell_style) if right[0] else "",
            Paragraph(_safe(right[1]), value_cell_style) if right[1] else "",
        ])

    table = Table(
        rows,
        colWidths=[
            42 * mm,
            43 * mm,
            42 * mm,
            43 * mm,
        ],
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, -1),
                LIGHT_GREEN,
            ),
            (
                "BACKGROUND",
                (2, 0),
                (2, -1),
                LIGHT_GREEN,
            ),
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTNAME",
                (2, 0),
                (2, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                BORDER,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ])
    )

    return table


def _table(
    headers,
    rows,
    widths=None,
):
    header_style = ParagraphStyle(
        "TableHeaderCell",
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.2,
        textColor=colors.white,
        spaceBefore=0,
        spaceAfter=0,
    )
    body_style = ParagraphStyle(
        "TableBodyCell",
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.2,
        textColor=colors.HexColor("#111827"),
        spaceBefore=0,
        spaceAfter=0,
    )
    clean_headers = [
        Paragraph(_safe(value), header_style)
        for value in headers
    ]
    clean_rows = [
        [Paragraph(_safe(value), body_style) for value in row]
        for row in rows
    ]

    table = Table(
        [
            clean_headers,
            *clean_rows,
        ],
        colWidths=widths,
        repeatRows=1,
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                GREEN,
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                7,
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                BORDER,
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    colors.HexColor(
                        "#f9fafb"
                    ),
                ],
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
        ])
    )

    return table


def _bar_chart(
    rows,
    title,
    styles,
):
    rows = list(
        rows or []
    )[:8]

    values = []
    labels = []

    for row in rows:
        try:
            values.append(
                float(
                    row.get(
                        "value",
                        0,
                    )
                )
            )
            labels.append(
                str(
                    row.get(
                        "label",
                        "",
                    )
                )[:13]
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    if not values:
        return []

    drawing = Drawing(
        170 * mm,
        58 * mm,
    )

    chart = (
        VerticalBarChart()
    )
    chart.x = 18 * mm
    chart.y = 13 * mm
    chart.height = 35 * mm
    chart.width = 140 * mm
    chart.data = [
        values
    ]
    chart.categoryAxis.categoryNames = (
        labels
    )
    chart.categoryAxis.labels.fontSize = (
        6.5
    )
    chart.valueAxis.labels.fontSize = (
        6.5
    )
    chart.valueAxis.valueMin = 0
    chart.bars[
        0
    ].fillColor = GREEN
    chart.bars[
        0
    ].strokeColor = DARK_GREEN
    drawing.add(
        chart
    )

    return [
        Paragraph(
            f"<b>{title}</b>",
            styles[
                "body"
            ],
        ),
        drawing,
        Spacer(
            1,
            2 * mm,
        ),
    ]


def _comparison_section(
    report: FarmReport,
    styles,
    number: str,
):
    comparison = (
        report.comparison
    )

    rows = _as_mapping_rows(comparison.get(
        "metrics",
        [],
    ))

    if not rows:
        return []

    previous = _as_mapping(comparison.get(
        "previous_period",
        {},
    ))

    story = [
        _section(
            f"{number}. Previous Period Comparison",
            styles,
        ),
        Paragraph(
            (
                "Previous equivalent period: "
                f"{_safe(previous.get('start_date'))} "
                f"to {_safe(previous.get('end_date'))}"
            ),
            styles[
                "body"
            ],
        ),
    ]

    important = [
        row
        for row in rows
        if row.get(
            "metric"
        )
        in {
            "total_harvest_kg",
            "average_yield_kg_per_ha",
            "pest_disease_records",
            "total_head",
            "vaccinations_in_period",
            "growth_measurements_in_period",
            "actual_feed_kg",
            "production_records_in_period",
            "gross_sales_value",
            "cash_collected",
            "outstanding_balance",
            "inventory_items",
            "low_stock_items",
            "stock_movements",
            "usage_quantity",
        }
    ]

    if not important:
        important = rows[
            :8
        ]

    story.append(
        _table(
            [
                "Metric",
                "Current",
                "Previous",
                "Difference",
                "% Change",
                "Trend",
            ],
            [
                [
                    _metric_label(
                        row.get(
                            "metric",
                            "",
                        )
                    ),
                    _num(
                        row.get(
                            "current",
                            0,
                        )
                    ),
                    _num(
                        row.get(
                            "previous",
                            0,
                        )
                    ),
                    (
                        f"{row.get('difference', 0):+,.2f}"
                    ),
                    (
                        "N/A"
                        if row.get(
                            "percent_change"
                        )
                        is None
                        else (
                            f"{row.get('percent_change'):+.1f}%"
                        )
                    ),
                    str(
                        row.get(
                            "direction",
                            "same",
                        )
                    ).title(),
                ]
                for row
                in important
            ],
            [
                48 * mm,
                25 * mm,
                25 * mm,
                28 * mm,
                25 * mm,
                23 * mm,
            ],
        )
    )

    return story


def _executive_kpi_section(
    report: FarmReport,
    styles,
    number: str,
):
    rows = _as_mapping_rows(report.executive_kpis)
    if not rows:
        return []

    table_rows = []
    for index in range(0, len(rows), 2):
        pair = rows[index:index + 2]
        row = []
        for item in pair:
            value = _num(item.get("value"), 3)
            unit = _safe(item.get("unit")) if item.get("unit") else ""
            if unit == "PHP":
                display = f"PHP {value}"
            else:
                display = f"{value} {unit}".strip()
            row.append(
                Paragraph(
                    f"<b>{_safe(item.get('label'))}</b><br/><font size='11'>{display}</font>",
                    styles["body"],
                )
            )
        while len(row) < 2:
            row.append("")
        table_rows.append(row)

    table = Table(table_rows, colWidths=[87 * mm, 87 * mm])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])
    )
    return [
        _section(f"{number}. Executive KPI Overview", styles),
        table,
    ]


def _performance_variance_section(
    report: FarmReport,
    styles,
    number: str,
):
    rows = _as_mapping_rows(report.performance_variance)
    if not rows:
        return []
    return [
        _section(f"{number}. Performance and Variance", styles),
        Paragraph(
            "Variance is calculated only where the system has a recorded plan, biological capacity, schedule, or other defensible reference value. No unrecorded crop-yield target is invented.",
            styles["body"],
        ),
        _table(
            ["Metric", "Actual", "Reference", "Variance", "% Variance"],
            [
                [
                    _safe(row.get("metric")),
                    (
                        f"PHP {_num(row.get('actual'))}"
                        if row.get("unit") == "PHP"
                        else f"{_num(row.get('actual'), 3)} {_safe(row.get('unit')) if row.get('unit') else ''}".strip()
                    ),
                    (
                        f"{_safe(row.get('reference_label'))}: PHP {_num(row.get('reference'))}"
                        if row.get("unit") == "PHP"
                        else f"{_safe(row.get('reference_label'))}: {_num(row.get('reference'), 3)} {_safe(row.get('unit')) if row.get('unit') else ''}".strip()
                    ),
                    f"{float(row.get('variance') or 0):+,.3f}",
                    (
                        "N/A"
                        if row.get("variance_percent") is None
                        else f"{float(row.get('variance_percent')):+.1f}%"
                    ),
                ]
                for row in rows
            ],
            [50 * mm, 28 * mm, 52 * mm, 24 * mm, 24 * mm],
        ),
    ]


def _findings_section(report, styles, number):
    story = [_section(f"{number}. Key Findings", styles)]
    for finding in report.findings or ["No major finding was generated."]:
        story.append(Paragraph(f"• {_safe(finding)}", styles["body"]))
    return story


def _risk_section(report, styles, number):
    risks = _as_mapping_rows(report.risk_flags)
    story = [_section(f"{number}. Risks and Issues", styles)]
    if not risks:
        return story + [Paragraph("No operational risk flag was generated.", styles["body"])]
    story.append(
        _table(
            ["Level", "Area", "Issue", "Recommended Response"],
            [
                [
                    row.get("level"),
                    row.get("area"),
                    row.get("issue"),
                    row.get("action"),
                ]
                for row in risks
            ],
            [20 * mm, 28 * mm, 63 * mm, 67 * mm],
        )
    )
    return story


def _recommendations_section(report, styles, number):
    story = [_section(f"{number}. Recommended Actions", styles)]
    for recommendation in report.recommendations or [
        "Continue routine monitoring and timely record entry."
    ]:
        story.append(Paragraph(f"• {_safe(recommendation)}", styles["body"]))
    return story


def _append_resource_usage_table(
    story,
    snapshot,
    styles,
    title="Resource Usage",
):
    rows = _as_mapping_rows(_as_mapping(snapshot.get("resource_usage", {})).get("records", []))
    if not rows:
        return

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>{title}</b>", styles["body"]))
    story.append(
        _table(
            ["Record", "Item", "Type", "Qty", "Unit", "Date"],
            [
                [
                    row.get("target_name") or row.get("module"),
                    row.get("item"),
                    row.get("usage_type"),
                    _num(row.get("quantity")),
                    row.get("unit"),
                    row.get("usage_date"),
                ]
                for row in rows[:80]
            ],
            [40 * mm, 43 * mm, 30 * mm, 20 * mm, 20 * mm, 28 * mm],
        )
    )


def _crop_main(
    report,
    snapshot,
    styles,
    number,
):
    story = [
        _section(
            f"{number}. Crop Report Details",
            styles,
        )
    ]

    report_type = (
        report.report_type
    )

    metrics = snapshot.get(
        "metrics",
        {},
    )

    metric_table = (
        _metric_table(
            metrics
        )
    )

    if metric_table:
        story.extend([
            metric_table,
            Spacer(
                1,
                4 * mm,
            ),
        ])

    if report_type in {
        "Crop Production",
        "Harvest Summary",
        "Yield Performance",
    }:
        story.extend(
            _bar_chart(
                snapshot.get(
                    "monthly_harvest",
                    [],
                ),
                "Recorded Harvest by Month",
                styles,
            )
        )

        rows = snapshot.get(
            "crop_performance",
            [],
        )

        if rows:
            story.append(
                Paragraph(
                    "<b>Crop Performance</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Crop",
                        "Field",
                        "Area (ha)",
                        "Harvest (kg)",
                        "Yield (kg/ha)",
                    ],
                    [
                        [
                            row.get(
                                "crop"
                            ),
                            row.get(
                                "field"
                            ),
                            _num(
                                row.get(
                                    "area_ha"
                                )
                            ),
                            _num(
                                row.get(
                                    "harvest_kg"
                                )
                            ),
                            _num(
                                row.get(
                                    "yield_kg_per_ha"
                                )
                            ),
                        ]
                        for row
                        in rows[
                            :50
                        ]
                    ],
                    [
                        42 * mm,
                        34 * mm,
                        28 * mm,
                        32 * mm,
                        38 * mm,
                    ],
                )
            )

    if report_type in {
        "Crop Production",
        "Harvest Summary",
        "Yield Performance",
    }:
        production_rows = snapshot.get("production_records", [])
        if production_rows:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("<b>Harvest Allocation and Available Output</b>", styles["body"]))
            story.append(
                _table(
                    ["Crop", "Date", "Harvest", "Farm Use", "Damaged", "Reserved", "Sold", "Available"],
                    [[
                        row.get("crop"),
                        row.get("record_date"),
                        f"{_num(row.get('gross_quantity'))} kg",
                        f"{_num(row.get('farm_use_quantity'))} kg",
                        f"{_num(row.get('loss_quantity'))} kg",
                        f"{_num(row.get('reserved_quantity'))} kg",
                        f"{_num(row.get('sold_quantity'))} kg",
                        f"{_num(row.get('available_quantity'))} kg",
                    ] for row in production_rows[:50]],
                    [28 * mm, 22 * mm, 23 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 24 * mm],
                )
            )

        sales_rows = snapshot.get("sales_records", [])
        if sales_rows:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("<b>Crop Sales</b>", styles["body"]))
            story.append(
                _table(
                    ["Sale", "Crop", "Date", "Qty", "Unit", "Gross", "Paid", "Balance"],
                    [[
                        row.get("sale_code"),
                        row.get("crop"),
                        row.get("sale_date"),
                        _num(row.get("quantity")),
                        row.get("unit"),
                        f"PHP {_num(row.get('total_amount'))}",
                        f"PHP {_num(row.get('amount_paid'))}",
                        f"PHP {_num(row.get('balance_due'))}",
                    ] for row in sales_rows[:50]],
                    [22 * mm, 26 * mm, 22 * mm, 16 * mm, 14 * mm, 23 * mm, 23 * mm, 23 * mm],
                )
            )

    if report_type in {
        "Crop Production",
        "Crop Growth",
    }:
        rows = snapshot.get(
            "growth_records",
            [],
        )

        if rows:
            story.append(
                Paragraph(
                    "<b>Growth Monitoring</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Crop",
                        "Field",
                        "Growth %",
                        "Status",
                        "Planting Date",
                        "Est. Harvest",
                    ],
                    [
                        [
                            row.get(
                                "crop"
                            ),
                            row.get(
                                "field"
                            ),
                            _num(
                                row.get(
                                    "growth_percent"
                                )
                            ),
                            row.get(
                                "status"
                            ),
                            row.get(
                                "planting_date"
                            ),
                            row.get(
                                "estimated_harvest"
                            ),
                        ]
                        for row
                        in rows[
                            :50
                        ]
                    ],
                    [
                        32 * mm,
                        28 * mm,
                        23 * mm,
                        28 * mm,
                        31 * mm,
                        34 * mm,
                    ],
                )
            )

    if report_type in {
        "Crop Production",
        "Pest and Disease",
    }:
        rows = snapshot.get(
            "pest_disease",
            {},
        ).get(
            "records",
            [],
        )

        if rows:
            story.append(
                Paragraph(
                    "<b>Pest / Disease Records</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Crop",
                        "Date",
                        "Type",
                        "Severity",
                        "Affected Area",
                        "Status",
                    ],
                    [
                        [
                            row.get(
                                "crop"
                            ),
                            row.get(
                                "date_detected"
                            ),
                            row.get(
                                "type"
                            ),
                            row.get(
                                "severity"
                            ),
                            row.get(
                                "affected_area"
                            ),
                            row.get(
                                "status"
                            ),
                        ]
                        for row
                        in rows[
                            :50
                        ]
                    ],
                    [
                        30 * mm,
                        28 * mm,
                        34 * mm,
                        25 * mm,
                        32 * mm,
                        27 * mm,
                    ],
                )
            )

    if report_type == "Resource Usage":
        _append_resource_usage_table(
            story, snapshot, styles, "Crop Resource Usage"
        )

    return story


def _livestock_main(
    report,
    snapshot,
    styles,
    number,
):
    story = [
        _section(
            f"{number}. Livestock Report Details",
            styles,
        )
    ]

    metrics = snapshot.get(
        "metrics",
        {},
    )

    metric_table = (
        _metric_table(
            metrics
        )
    )

    if metric_table:
        story.extend([
            metric_table,
            Spacer(
                1,
                4 * mm,
            ),
        ])

    report_type = (
        report.report_type
    )

    if report_type in {
        "Livestock Production",
        "Production & Sales Summary",
        "Processing Summary",
        "Growth Summary",
        "Health Summary",
        "Feeding Consumption",
    }:
        rows = snapshot.get(
            "livestock_records",
            [],
        )

        if rows:
            story.append(
                _table(
                    [
                        "Record",
                        "Type",
                        "Qty",
                        "Weight",
                        "Health",
                        "Growth",
                        "Feed/day",
                    ],
                    [
                        [
                            row.get(
                                "record_name"
                            ),
                            row.get(
                                "animal_type"
                            ),
                            row.get(
                                "quantity"
                            ),
                            (
                                f"{_num(row.get('weight_kg'))} kg"
                            ),
                            row.get(
                                "health_status"
                            ),
                            row.get(
                                "growth_status"
                            ),
                            (
                                f"{_num(row.get('daily_feed_kg'))} kg"
                            ),
                        ]
                        for row
                        in rows[
                            :60
                        ]
                    ],
                    [
                        34 * mm,
                        24 * mm,
                        15 * mm,
                        24 * mm,
                        25 * mm,
                        25 * mm,
                        28 * mm,
                    ],
                )
            )

    if report_type in {
        "Livestock Production",
        "Production & Sales Summary",
        "Vaccination Summary",
    }:
        rows = snapshot.get(
            "vaccination_records",
            [],
        )

        if rows:
            story.append(
                Spacer(
                    1,
                    4 * mm,
                )
            )
            story.append(
                Paragraph(
                    "<b>Vaccination Records</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Livestock",
                        "Vaccine",
                        "Date",
                        "Next Due",
                        "Status",
                        "Administered By",
                    ],
                    [
                        [
                            row.get(
                                "livestock"
                            ),
                            row.get(
                                "vaccine"
                            ),
                            row.get(
                                "date_administered"
                            ),
                            row.get(
                                "next_due"
                            ),
                            row.get(
                                "status"
                            ),
                            row.get(
                                "administered_by"
                            ),
                        ]
                        for row
                        in rows[
                            :60
                        ]
                    ],
                    [
                        34 * mm,
                        34 * mm,
                        27 * mm,
                        27 * mm,
                        24 * mm,
                        30 * mm,
                    ],
                )
            )

    if report_type in {
        "Livestock Production",
        "Production & Sales Summary",
        "Processing Summary",
    }:
        reproduction_rows = snapshot.get("reproduction_records", [])
        if reproduction_rows and report_type != "Processing Summary":
            story.extend([Spacer(1, 4 * mm), Paragraph("<b>Reproduction Records</b>", styles["body"])])
            story.append(_table(
                ["Livestock", "Event", "Date", "Status", "Expected", "Actual", "Alive"],
                [[
                    row.get("livestock"), row.get("record_type"), row.get("event_date"),
                    row.get("reproductive_status"), row.get("expected_date"),
                    row.get("actual_date"), row.get("alive_offspring"),
                ] for row in reproduction_rows[:50]],
                [32 * mm, 26 * mm, 24 * mm, 28 * mm, 24 * mm, 24 * mm, 18 * mm],
            ))

        production_rows = snapshot.get("production_records", [])
        if production_rows and report_type != "Processing Summary":
            story.extend([Spacer(1, 4 * mm), Paragraph("<b>Production Records</b>", styles["body"])])
            story.append(_table(
                ["Livestock", "Output", "Period", "Qty", "Rate", "Available", "Destination"],
                [[
                    row.get("livestock"),
                    row.get("output_type"),
                    f"{row.get('period_start_date') or row.get('record_date')} to {row.get('period_end_date') or row.get('record_date')}",
                    f"{_num(row.get('quantity'))} {row.get('unit') or ''}",
                    (f"{_num(row.get('laying_rate_percent'))}%" if row.get("laying_rate_percent") is not None else "-"),
                    f"{_num(row.get('available_quantity'))} {row.get('unit') or ''}",
                    row.get("destination"),
                ] for row in production_rows[:60]],
                [31 * mm, 24 * mm, 40 * mm, 24 * mm, 20 * mm, 25 * mm, 32 * mm],
            ))

        processing_rows = snapshot.get("processing_records", [])
        if processing_rows:
            story.extend([Spacer(1, 4 * mm), Paragraph("<b>Livestock Processing / Meat Output</b>", styles["body"])])
            story.append(_table(
                ["Livestock", "Date", "Head", "Live Wt.", "Meat", "Yield", "Grade"],
                [[
                    row.get("livestock"), row.get("processing_date"), row.get("animals_processed"),
                    f"{_num(row.get('live_weight_kg'))} kg",
                    f"{_num(row.get('meat_output_kg'))} kg",
                    f"{_num(row.get('dressing_yield_percent'))}%",
                    row.get("quality_grade"),
                ] for row in processing_rows[:60]],
                [34 * mm, 25 * mm, 18 * mm, 25 * mm, 24 * mm, 22 * mm, 28 * mm],
            ))

        sales_rows = snapshot.get("sales_records", [])
        if sales_rows and report_type != "Processing Summary":
            story.extend([Spacer(1, 4 * mm), Paragraph("<b>Sales & Payment Transactions</b>", styles["body"])])
            story.append(_table(
                ["Sale", "Date", "Product", "Gross", "Paid", "Balance", "Status"],
                [[
                    row.get("sale_code"), row.get("sale_date"), row.get("product_type"),
                    f"P {_num(row.get('total_amount'))}",
                    f"P {_num(row.get('amount_paid'))}",
                    f"P {_num(row.get('balance_due'))}",
                    row.get("payment_status"),
                ] for row in sales_rows[:60]],
                [28 * mm, 24 * mm, 32 * mm, 28 * mm, 28 * mm, 28 * mm, 25 * mm],
            ))

        payment_rows = snapshot.get("payment_records", [])
        if payment_rows and report_type != "Processing Summary":
            story.extend([Spacer(1, 4 * mm), Paragraph("<b>Payment Collection History</b>", styles["body"])])
            story.append(_table(
                ["Sale", "Payment Date", "Amount", "Method", "Notes"],
                [[
                    row.get("sale_code"), row.get("payment_date"),
                    f"P {_num(row.get('amount'))}", row.get("payment_method"), row.get("notes"),
                ] for row in payment_rows[:80]],
                [31 * mm, 28 * mm, 28 * mm, 28 * mm, 72 * mm],
            ))

    if report_type == "Growth Summary":
        growth_rows = snapshot.get("growth_records", [])
        if growth_rows:
            story.extend([
                Spacer(1, 4 * mm),
                Paragraph("<b>Growth / Weight Measurements</b>", styles["body"]),
            ])
            story.append(_table(
                ["Livestock", "Date", "Weight", "Change", "Days", "Daily Gain"],
                [[
                    row.get("livestock"),
                    row.get("measurement_date"),
                    f"{_num(row.get('weight_kg'))} kg",
                    (
                        f"{_num(row.get('weight_change_kg'))} kg"
                        if row.get("weight_change_kg") is not None
                        else "Baseline"
                    ),
                    row.get("days_since_previous") or "-",
                    (
                        f"{_num(row.get('average_daily_gain_kg'), 4)} kg/day"
                        if row.get("average_daily_gain_kg") is not None
                        else "-"
                    ),
                ] for row in growth_rows[:80]],
                [38 * mm, 26 * mm, 26 * mm, 26 * mm, 16 * mm, 38 * mm],
            ))

    if report_type in {"Livestock Production", "Feeding Consumption"}:
        feeding_rows = snapshot.get("feeding_records", [])
        if feeding_rows:
            story.extend([
                Spacer(1, 4 * mm),
                Paragraph("<b>Confirmed Feeding Records</b>", styles["body"]),
            ])
            story.append(_table(
                ["Livestock", "Date", "Feed", "Planned", "Actual", "Variance"],
                [[
                    row.get("livestock"),
                    row.get("feeding_date"),
                    row.get("feed_type"),
                    f"{_num(row.get('planned_quantity_kg'), 3)} kg",
                    f"{_num(row.get('actual_quantity_kg'), 3)} kg",
                    f"{float(row.get('variance_kg') or 0):+,.3f} kg",
                ] for row in feeding_rows[:80]],
                [36 * mm, 25 * mm, 46 * mm, 24 * mm, 24 * mm, 24 * mm],
            ))

    if report_type in {"Resource Usage", "Feeding Consumption"}:
        _append_resource_usage_table(
            story, snapshot, styles, "Livestock Resource Usage"
        )

    return story


def _inventory_main(
    report,
    snapshot,
    styles,
    number,
):
    story = [
        _section(
            f"{number}. Inventory Report Details",
            styles,
        )
    ]

    metric_table = (
        _metric_table(
            snapshot.get(
                "metrics",
                {},
            )
        )
    )

    if metric_table:
        story.extend([
            metric_table,
            Spacer(
                1,
                4 * mm,
            ),
        ])

    report_type = (
        report.report_type
    )

    if report_type in {
        "Inventory Summary",
        "Low Stock",
    }:
        rows = snapshot.get(
            "low_stock_records",
            [],
        )

        if rows:
            story.append(
                Paragraph(
                    "<b>Low Stock Items</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Item Code",
                        "Item",
                        "Quantity",
                        "Unit",
                        "Reorder Level",
                    ],
                    [
                        [
                            row.get(
                                "item_code"
                            ),
                            row.get(
                                "name"
                            ),
                            _num(
                                row.get(
                                    "quantity"
                                )
                            ),
                            row.get(
                                "unit"
                            ),
                            _num(
                                row.get(
                                    "reorder_level"
                                )
                            ),
                        ]
                        for row
                        in rows[
                            :60
                        ]
                    ],
                    [
                        34 * mm,
                        55 * mm,
                        27 * mm,
                        25 * mm,
                        35 * mm,
                    ],
                )
            )

    if report_type in {
        "Inventory Summary",
        "Stock Movement",
        "Consumption Summary",
    }:
        rows = snapshot.get(
            "stock_movements",
            [],
        )

        if rows:
            story.append(
                Spacer(
                    1,
                    4 * mm,
                )
            )
            story.append(
                Paragraph(
                    "<b>Stock Movements</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Item",
                        "Type",
                        "Quantity",
                        "Previous",
                        "New",
                        "Date",
                    ],
                    [
                        [
                            row.get(
                                "item"
                            ),
                            row.get(
                                "adjustment_type"
                            ),
                            _num(
                                row.get(
                                    "quantity"
                                )
                            ),
                            _num(
                                row.get(
                                    "previous_quantity"
                                )
                            ),
                            _num(
                                row.get(
                                    "new_quantity"
                                )
                            ),
                            row.get(
                                "adjustment_date"
                            ),
                        ]
                        for row
                        in rows[
                            :80
                        ]
                    ],
                    [
                        42 * mm,
                        32 * mm,
                        25 * mm,
                        25 * mm,
                        25 * mm,
                        27 * mm,
                    ],
                )
            )

    if report_type in {
        "Inventory Summary",
        "Inventory Valuation",
    }:
        rows = snapshot.get(
            "inventory_records",
            [],
        )

        if rows:
            story.append(
                Spacer(
                    1,
                    4 * mm,
                )
            )
            story.append(
                Paragraph(
                    "<b>Inventory Valuation Detail</b>",
                    styles[
                        "body"
                    ],
                )
            )
            story.append(
                _table(
                    [
                        "Item",
                        "Category",
                        "Qty",
                        "Unit",
                        "Cost",
                        "Price",
                    ],
                    [
                        [
                            row.get(
                                "name"
                            ),
                            row.get(
                                "category"
                            ),
                            _num(
                                row.get(
                                    "quantity"
                                )
                            ),
                            row.get(
                                "unit"
                            ),
                            _num(
                                row.get(
                                    "cost"
                                )
                            ),
                            _num(
                                row.get(
                                    "price"
                                )
                            ),
                        ]
                        for row
                        in rows[
                            :70
                        ]
                    ],
                    [
                        45 * mm,
                        34 * mm,
                        20 * mm,
                        20 * mm,
                        28 * mm,
                        28 * mm,
                    ],
                )
            )

    if report_type in {"Inventory Summary", "Expiring Items"}:
        rows = snapshot.get("expiring_records", [])
        if rows:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("<b>Expiring Inventory Items</b>", styles["body"]))
            story.append(
                _table(
                    ["Item Code", "Item", "Batch/Lot", "Qty", "Unit", "Expiration"],
                    [
                        [
                            row.get("item_code"),
                            row.get("name"),
                            row.get("batch_number") or "—",
                            _num(row.get("quantity")),
                            row.get("unit"),
                            row.get("expiration_date"),
                        ]
                        for row in rows[:60]
                    ],
                    [30 * mm, 43 * mm, 32 * mm, 20 * mm, 20 * mm, 32 * mm],
                )
            )

    if report_type in {"Inventory Summary", "Consumption Summary", "Resource Usage"}:
        _append_resource_usage_table(
            story, snapshot, styles, "Inventory-Linked Resource Usage"
        )

    return story



def _production_sales_main(
    report,
    snapshot,
    styles,
    number,
):
    story = [
        _section(
            f"{number}. Production & Sales Details",
            styles,
        )
    ]

    metric_table = _metric_table(snapshot.get("metrics", {}))
    if metric_table:
        story.extend([metric_table, Spacer(1, 4 * mm)])

    report_type = str(report.report_type or "")
    crop = snapshot.get("crop", {})
    livestock = snapshot.get("livestock", {})

    if report_type in {"Production Summary", "Crop Production & Sales"}:
        rows = crop.get("production_records", [])
        if rows:
            story.append(Paragraph("<b>Crop Harvest Output and Availability</b>", styles["body"]))
            story.append(
                _table(
                    ["Crop", "Date", "Harvest", "Farm Use", "Loss", "Reserved", "Sold", "Available"],
                    [[
                        row.get("crop"),
                        row.get("record_date"),
                        _num(row.get("gross_quantity")),
                        _num(row.get("farm_use_quantity")),
                        _num(row.get("loss_quantity")),
                        _num(row.get("reserved_quantity")),
                        _num(row.get("sold_quantity")),
                        _num(row.get("available_quantity")),
                    ] for row in rows[:60]],
                    [28 * mm, 22 * mm, 22 * mm, 22 * mm, 20 * mm, 22 * mm, 20 * mm, 24 * mm],
                )
            )
            story.append(Spacer(1, 4 * mm))

    if report_type in {"Production Summary", "Livestock Production & Sales"}:
        rows = livestock.get("production_records", [])
        if rows:
            story.append(Paragraph("<b>Livestock Production Output</b>", styles["body"]))
            story.append(
                _table(
                    ["Livestock", "Output", "Date", "Qty", "Unit", "Available", "Destination"],
                    [[
                        row.get("livestock"),
                        row.get("output_type"),
                        row.get("record_date"),
                        _num(row.get("quantity")),
                        row.get("unit"),
                        _num(row.get("available_quantity")),
                        row.get("destination"),
                    ] for row in rows[:60]],
                    [38 * mm, 27 * mm, 24 * mm, 20 * mm, 16 * mm, 24 * mm, 31 * mm],
                )
            )
            story.append(Spacer(1, 4 * mm))

    if report_type in {"Production Summary", "Livestock Production & Sales", "Processing Report"}:
        rows = livestock.get("processing_records", [])
        if rows:
            story.append(Paragraph("<b>Processing / Meat Output</b>", styles["body"]))
            story.append(
                _table(
                    ["Livestock", "Date", "Head", "Live kg", "Meat kg", "Yield %", "Grade"],
                    [[
                        row.get("livestock"),
                        row.get("processing_date"),
                        row.get("animals_processed"),
                        _num(row.get("live_weight_kg")),
                        _num(row.get("meat_output_kg")),
                        _num(row.get("dressing_yield_percent")),
                        row.get("quality_grade"),
                    ] for row in rows[:60]],
                    [39 * mm, 24 * mm, 18 * mm, 23 * mm, 23 * mm, 23 * mm, 23 * mm],
                )
            )
            story.append(Spacer(1, 4 * mm))

    if report_type in {"Production Summary", "Sales Summary", "Crop Production & Sales", "Receivables Report"}:
        rows = crop.get("sales_records", [])
        if rows:
            story.append(Paragraph("<b>Crop Sales</b>", styles["body"]))
            story.append(
                _table(
                    ["Sale", "Crop", "Date", "Qty", "Unit", "Gross", "Paid", "Balance"],
                    [[
                        row.get("sale_code"), row.get("crop"), row.get("sale_date"),
                        _num(row.get("quantity")), row.get("unit"),
                        f"PHP {_num(row.get('total_amount'))}",
                        f"PHP {_num(row.get('amount_paid'))}",
                        f"PHP {_num(row.get('balance_due'))}",
                    ] for row in rows[:60]],
                    [22 * mm, 26 * mm, 22 * mm, 16 * mm, 14 * mm, 23 * mm, 23 * mm, 23 * mm],
                )
            )
            story.append(Spacer(1, 4 * mm))

        payment_rows = crop.get("payment_records", [])
        if payment_rows and report_type in {"Sales Summary", "Crop Production & Sales", "Receivables Report"}:
            story.append(Paragraph("<b>Crop Payment Collections</b>", styles["body"]))
            story.append(
                _table(
                    ["Sale", "Date", "Amount", "Method", "Notes"],
                    [[
                        row.get("sale_code"), row.get("payment_date"),
                        f"PHP {_num(row.get('amount'))}", row.get("payment_method"), row.get("notes"),
                    ] for row in payment_rows[:60]],
                    [27 * mm, 27 * mm, 30 * mm, 35 * mm, 55 * mm],
                )
            )
            story.append(Spacer(1, 4 * mm))

    if report_type in {"Production Summary", "Sales Summary", "Livestock Production & Sales", "Receivables Report"}:
        rows = livestock.get("sales_records", [])
        if rows:
            story.append(Paragraph("<b>Livestock / Product Sales</b>", styles["body"]))
            story.append(
                _table(
                    ["Sale", "Product", "Date", "Qty", "Unit", "Gross", "Paid", "Balance"],
                    [[
                        row.get("sale_code"), row.get("product_type"), row.get("sale_date"),
                        _num(row.get("quantity")), row.get("unit"),
                        f"PHP {_num(row.get('total_amount'))}",
                        f"PHP {_num(row.get('amount_paid'))}",
                        f"PHP {_num(row.get('balance_due'))}",
                    ] for row in rows[:60]],
                    [22 * mm, 29 * mm, 22 * mm, 16 * mm, 14 * mm, 23 * mm, 23 * mm, 23 * mm],
                )
            )

    return story


def _farm_main(
    report,
    snapshot,
    styles,
    number,
):
    overview_title = (
        "Production & Sales Overview"
        if report.category == "Production & Sales"
        else "Trend & Seasonal Overview"
        if report.category == "Trend & Seasonal"
        else "Farm Production Overview"
    )
    story = [
        _section(
            f"{number}. {overview_title}",
            styles,
        )
    ]

    table = _metric_table(
        snapshot.get(
            "metrics",
            {},
        )
    )

    if table:
        story.extend([
            table,
            Spacer(
                1,
                4 * mm,
            ),
        ])

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

    crop_table = _metric_table(
        crop.get(
            "metrics",
            {},
        )
    )
    if crop_table:
        story.append(
            Paragraph(
                "<b>Crop Overview</b>",
                styles[
                    "body"
                ],
            )
        )
        story.append(
            crop_table
        )

    livestock_table = (
        _metric_table(
            livestock.get(
                "metrics",
                {},
            )
        )
    )
    if livestock_table:
        story.append(
            Spacer(
                1,
                4 * mm,
            )
        )
        story.append(
            Paragraph(
                "<b>Livestock Overview</b>",
                styles[
                    "body"
                ],
            )
        )
        story.append(
            livestock_table
        )

    inventory_table = (
        _metric_table(
            inventory.get(
                "metrics",
                {},
            )
        )
    )
    if inventory_table:
        story.append(
            Spacer(
                1,
                4 * mm,
            )
        )
        story.append(
            Paragraph(
                "<b>Inventory Overview</b>",
                styles[
                    "body"
                ],
            )
        )
        story.append(
            inventory_table
        )

    if report.report_type in {"Trend & Seasonal Analysis", "Farm Performance Report"}:
        trends = snapshot.get("trend_analysis", {})
        seasonal_rows = trends.get("seasonal", [])
        factor_rows = trends.get("factor_analysis", [])
        growth_rows = trends.get("growth_summary", [])

        if seasonal_rows:
            story.extend([
                Spacer(1, 5 * mm),
                Paragraph("<b>Seasonal Pattern Summary</b>", styles["body"]),
                _table(
                    ["Season", "Months", "Crop Yield", "Feed Used", "Avg. Daily Gain"],
                    [[
                        row.get("season"),
                        row.get("months_in_period"),
                        f"{_num(row.get('crop_yield_kg'))} kg",
                        f"{_num(row.get('feed_consumption_kg'))} kg",
                        (
                            f"{_num(row.get('average_daily_gain_kg'), 4)} kg/day"
                            if row.get("average_daily_gain_kg") is not None
                            else "-"
                        ),
                    ] for row in seasonal_rows],
                    [34 * mm, 22 * mm, 34 * mm, 34 * mm, 48 * mm],
                ),
            ])

        if factor_rows:
            story.extend([
                Spacer(1, 5 * mm),
                Paragraph("<b>Factors Associated With Performance</b>", styles["body"]),
                Paragraph(
                    "These are descriptive correlations from recorded farm data and do not prove causation.",
                    styles["body"],
                ),
                _table(
                    ["Factor", "Correlation", "Direction", "Strength"],
                    [[
                        row.get("factor"),
                        (
                            _num(row.get("correlation"), 3)
                            if row.get("correlation") is not None
                            else "Insufficient data"
                        ),
                        row.get("direction"),
                        row.get("strength"),
                    ] for row in factor_rows],
                    [68 * mm, 30 * mm, 40 * mm, 30 * mm],
                ),
            ])

        if growth_rows:
            story.extend([
                Spacer(1, 5 * mm),
                Paragraph("<b>Livestock Growth Performance</b>", styles["body"]),
                _table(
                    ["Livestock", "Type", "Measurements", "Start", "Latest", "Daily Gain"],
                    [[
                        row.get("record_name"),
                        row.get("animal_type"),
                        row.get("measurements"),
                        f"{_num(row.get('start_weight_kg'))} kg",
                        f"{_num(row.get('latest_weight_kg'))} kg",
                        (
                            f"{_num(row.get('average_daily_gain_kg'), 4)} kg/day"
                            if row.get("average_daily_gain_kg") is not None
                            else "-"
                        ),
                    ] for row in growth_rows[: (12 if report.report_type == "Farm Performance Report" else 60)]],
                    [38 * mm, 24 * mm, 20 * mm, 26 * mm, 26 * mm, 42 * mm],
                ),
            ])

        monthly_rows = trends.get("monthly", [])
        if monthly_rows and report.report_type == "Trend & Seasonal Analysis":
            story.extend([
                Spacer(1, 5 * mm),
                Paragraph("<b>Monthly Sales Trend</b>", styles["body"]),
                _table(
                    ["Month", "Crop Sales", "Livestock Sales", "Gross Sales", "Cash Collected"],
                    [[
                        row.get("label"),
                        f"PHP {_num(row.get('crop_sales_value'))}",
                        f"PHP {_num(row.get('livestock_sales_value'))}",
                        f"PHP {_num(row.get('gross_sales_value'))}",
                        f"PHP {_num(row.get('cash_collected'))}",
                    ] for row in monthly_rows],
                    [30 * mm, 35 * mm, 38 * mm, 35 * mm, 35 * mm],
                ),
            ])

    return story


def _findings_recommendations(
    report,
    styles,
    number,
):
    story = [
        _section(
            f"{number}. Findings and Recommendations",
            styles,
        )
    ]

    story.append(
        Paragraph(
            "<b>Key Findings</b>",
            styles[
                "body"
            ],
        )
    )

    for finding in (
        report.findings
        or [
            "No major finding was generated."
        ]
    ):
        story.append(
            Paragraph(
                f"• {_safe(finding)}",
                styles[
                    "body"
                ],
            )
        )

    story.append(
        Spacer(
            1,
            2 * mm,
        )
    )

    story.append(
        Paragraph(
            "<b>Recommended Actions</b>",
            styles[
                "body"
            ],
        )
    )

    for recommendation in (
        report.recommendations
        or []
    ):
        story.append(
            Paragraph(
                f"• {_safe(recommendation)}",
                styles[
                    "body"
                ],
            )
        )

    return story


def _data_quality(
    report,
    styles,
    number,
):
    story = [
        _section(
            f"{number}. Data Quality and Interpretation Notes",
            styles,
        )
    ]

    for notice in (
        report.data_quality
        or []
    ):
        # Legacy analytical reports store structured notices, while the factual
        # Attendance operational reports intentionally store
        # plain explanatory strings. PDF generation must support both persisted
        # shapes so an existing report can always be previewed/downloaded.
        if isinstance(notice, dict):
            level = _safe(
                notice.get(
                    "level"
                )
            )
            message = _safe(
                notice.get(
                    "message"
                )
            )
        else:
            level = "Note"
            message = _safe(notice)

        story.append(
            Paragraph(
                (
                    f"<b>{level}:</b> "
                    f"{message}"
                ),
                styles[
                    "body"
                ],
            )
        )

    return story


def _appendix(
    report,
    styles,
):
    snapshot = report.snapshot

    if report.category in {"Farm", "Trend & Seasonal"}:
        categories = [
            ("Crop", snapshot.get("crop", {})),
            ("Livestock", snapshot.get("livestock", {})),
            ("Inventory", snapshot.get("inventory", {})),
        ]
    elif report.category == "Production & Sales":
        categories = [
            ("Crop", snapshot.get("crop", {})),
            ("Livestock", snapshot.get("livestock", {})),
        ]
    else:
        categories = [(report.category, snapshot)]

    table_specs = []

    def queue_table(title, headers, rows, keys, widths=None):
        safe_rows = _as_mapping_rows(rows)
        if safe_rows:
            table_specs.append((title, headers, safe_rows, keys, widths))

    for category, data in categories:
        if report.category == "Production & Sales" and category == "Crop":
            queue_table(
                "Crop Harvest / Yield Records",
                ["Code", "Crop", "Harvest Date", "Harvest (kg)", "Yield (kg/ha)", "Quality"],
                data.get("yield_records", []),
                ["crop_code", "crop", "harvest_date", "quantity_kg", "yield_kg_per_ha", "quality"],
                [23 * mm, 34 * mm, 28 * mm, 27 * mm, 31 * mm, 28 * mm],
            )
            queue_table(
                "Crop Production Availability",
                ["Crop", "Date", "Harvest", "Farm Use", "Loss", "Reserved", "Sold", "Available"],
                data.get("production_records", []),
                ["crop", "record_date", "gross_quantity", "farm_use_quantity", "loss_quantity", "reserved_quantity", "sold_quantity", "available_quantity"],
                [28 * mm, 22 * mm, 22 * mm, 22 * mm, 20 * mm, 22 * mm, 20 * mm, 24 * mm],
            )
            queue_table(
                "Crop Sales Records",
                ["Sale", "Crop", "Date", "Qty", "Unit", "Gross", "Paid", "Balance"],
                data.get("sales_records", []),
                ["sale_code", "crop", "sale_date", "quantity", "unit", "total_amount", "amount_paid", "balance_due"],
                [23 * mm, 28 * mm, 23 * mm, 18 * mm, 16 * mm, 23 * mm, 23 * mm, 23 * mm],
            )
            queue_table(
                "Crop Payment Collections",
                ["Sale", "Date", "Amount", "Method", "Notes"],
                data.get("payment_records", []),
                ["sale_code", "payment_date", "amount", "payment_method", "notes"],
            )

        elif report.category == "Production & Sales" and category == "Livestock":
            queue_table(
                "Livestock Production Records",
                ["Livestock", "Output", "Date", "Qty", "Unit", "Available"],
                data.get("production_records", []),
                ["livestock", "output_type", "record_date", "quantity", "unit", "available_quantity"],
                [44 * mm, 31 * mm, 27 * mm, 24 * mm, 18 * mm, 28 * mm],
            )
            queue_table(
                "Processing Records",
                ["Livestock", "Date", "Head", "Live kg", "Meat kg", "Yield %"],
                data.get("processing_records", []),
                ["livestock", "processing_date", "animals_processed", "live_weight_kg", "meat_output_kg", "dressing_yield_percent"],
                [47 * mm, 28 * mm, 20 * mm, 25 * mm, 25 * mm, 25 * mm],
            )
            queue_table(
                "Livestock Sales Records",
                ["Sale", "Product", "Date", "Qty", "Gross", "Paid", "Balance"],
                data.get("sales_records", []),
                ["sale_code", "product_type", "sale_date", "quantity", "total_amount", "amount_paid", "balance_due"],
                [26 * mm, 32 * mm, 25 * mm, 20 * mm, 25 * mm, 25 * mm, 25 * mm],
            )
            queue_table(
                "Payment Collections",
                ["Sale", "Date", "Amount", "Method", "Notes"],
                data.get("payment_records", []),
                ["sale_code", "payment_date", "amount", "payment_method", "notes"],
            )

        elif category == "Crop":
            queue_table(
                "Crop Harvest / Yield Records",
                ["Code", "Crop", "Harvest Date", "Harvest (kg)", "Yield (kg/ha)", "Quality"],
                data.get("yield_records", []),
                ["crop_code", "crop", "harvest_date", "quantity_kg", "yield_kg_per_ha", "quality"],
                [23 * mm, 34 * mm, 28 * mm, 27 * mm, 31 * mm, 28 * mm],
            )
            queue_table(
                "Crop Production Availability",
                ["Crop", "Date", "Harvest", "Farm Use", "Loss", "Reserved", "Sold", "Available"],
                data.get("production_records", []),
                ["crop", "record_date", "gross_quantity", "farm_use_quantity", "loss_quantity", "reserved_quantity", "sold_quantity", "available_quantity"],
                [28 * mm, 22 * mm, 22 * mm, 22 * mm, 20 * mm, 22 * mm, 20 * mm, 24 * mm],
            )
            queue_table(
                "Crop Sales Records",
                ["Sale", "Crop", "Date", "Qty", "Unit", "Gross", "Paid", "Balance"],
                data.get("sales_records", []),
                ["sale_code", "crop", "sale_date", "quantity", "unit", "total_amount", "amount_paid", "balance_due"],
                [23 * mm, 28 * mm, 23 * mm, 18 * mm, 16 * mm, 23 * mm, 23 * mm, 23 * mm],
            )
            queue_table(
                "Crop Growth Records",
                ["Code", "Crop", "Field", "Growth %", "Status"],
                data.get("growth_records", []),
                ["crop_code", "crop", "field", "growth_percent", "status"],
            )
            queue_table(
                "Pest / Disease Records",
                ["Crop", "Date", "Type", "Severity", "Status"],
                data.get("pest_disease", {}).get("records", []),
                ["crop", "date_detected", "type", "severity", "status"],
            )
            queue_table(
                "Crop Resource Usage",
                ["Crop", "Type", "Item", "Qty", "Unit", "Date"],
                data.get("resource_usage", {}).get("records", []),
                ["target_name", "usage_type", "item", "quantity", "unit", "usage_date"],
                [38 * mm, 28 * mm, 42 * mm, 20 * mm, 18 * mm, 28 * mm],
            )

        elif category == "Livestock":
            queue_table(
                "Livestock Records",
                ["Code", "Record", "Type", "Qty", "Health Mix", "Growth"],
                data.get("livestock_records", []),
                ["animal_code", "record_name", "animal_type", "quantity", "health_summary", "growth_status"],
            )
            queue_table(
                "Livestock Growth Measurements",
                ["Livestock", "Date", "Measured", "Avg kg", "Min kg", "Max kg", "Daily Gain"],
                data.get("growth_records", []),
                ["livestock", "measurement_date", "animals_measured", "weight_kg", "min_weight_kg", "max_weight_kg", "average_daily_gain_kg"],
                [39 * mm, 25 * mm, 20 * mm, 22 * mm, 20 * mm, 20 * mm, 28 * mm],
            )
            queue_table(
                "Confirmed Feeding Records",
                ["Livestock", "Date", "Feed", "Planned", "Actual", "Variance %"],
                data.get("feeding_records", []),
                ["livestock", "feeding_date", "feed_type", "planned_quantity_kg", "actual_quantity_kg", "variance_percent"],
                [43 * mm, 27 * mm, 37 * mm, 23 * mm, 23 * mm, 24 * mm],
            )
            queue_table(
                "Production Records",
                ["Livestock", "Output", "Date", "Qty", "Unit", "Available"],
                data.get("production_records", []),
                ["livestock", "output_type", "record_date", "quantity", "unit", "available_quantity"],
                [44 * mm, 31 * mm, 27 * mm, 24 * mm, 18 * mm, 28 * mm],
            )
            queue_table(
                "Processing Records",
                ["Livestock", "Date", "Head", "Live kg", "Meat kg", "Yield %"],
                data.get("processing_records", []),
                ["livestock", "processing_date", "animals_processed", "live_weight_kg", "meat_output_kg", "dressing_yield_percent"],
                [47 * mm, 28 * mm, 20 * mm, 25 * mm, 25 * mm, 25 * mm],
            )
            queue_table(
                "Sales Records",
                ["Sale", "Product", "Date", "Qty", "Gross", "Paid", "Balance"],
                data.get("sales_records", []),
                ["sale_code", "product_type", "sale_date", "quantity", "total_amount", "amount_paid", "balance_due"],
                [26 * mm, 32 * mm, 25 * mm, 20 * mm, 25 * mm, 25 * mm, 25 * mm],
            )
            queue_table(
                "Vaccination Records",
                ["Livestock", "Vaccine", "Date", "Next Due", "Status"],
                data.get("vaccination_records", []),
                ["livestock", "vaccine", "date_administered", "next_due", "status"],
            )
            queue_table(
                "Reproduction Records",
                ["Livestock", "Type", "Date", "Status", "Offspring", "Alive"],
                data.get("reproduction_records", []),
                ["livestock", "record_type", "event_date", "reproductive_status", "offspring_count", "alive_offspring"],
            )
            queue_table(
                "Livestock Resource Usage",
                ["Livestock", "Type", "Item", "Qty", "Unit", "Date"],
                data.get("resource_usage", {}).get("records", []),
                ["target_name", "usage_type", "item", "quantity", "unit", "usage_date"],
                [38 * mm, 28 * mm, 42 * mm, 20 * mm, 18 * mm, 28 * mm],
            )

        elif category == "Inventory":
            queue_table(
                "Inventory Records",
                ["Code", "Item", "Category", "Qty", "Unit", "Reorder"],
                data.get("inventory_records", []),
                ["item_code", "name", "category", "quantity", "unit", "reorder_level"],
            )
            queue_table(
                "Stock Movement Records",
                ["Item", "Type", "Qty", "Previous", "New", "Date"],
                data.get("stock_movements", []),
                ["item", "adjustment_type", "quantity", "previous_quantity", "new_quantity", "adjustment_date"],
            )

    if not table_specs:
        return []

    story = [
        PageBreak(),
        _section("Appendix - Supporting Records", styles),
        Paragraph(
            "The appendix contains detailed source records captured in the report snapshot. "
            "These records support the figures shown in the main report.",
            styles["body"],
        ),
        Spacer(1, 3 * mm),
    ]

    for title, headers, rows, keys, widths in table_specs:
        story.append(Paragraph(f"<b>{title}</b>", styles["body"]))
        story.append(
            _table(
                headers,
                [[row.get(key) for key in keys] for row in rows[:150]],
                widths,
            )
        )
        story.append(Spacer(1, 4 * mm))

    return story


def _operational_main(report, snapshot, styles, section_number):
    story = [_section(f"{section_number}. Detailed Factual Records", styles)]
    metrics = snapshot.get("metrics", {})
    if metrics:
        metric_rows = [[key.replace("_", " ").title(), value] for key, value in metrics.items()]
        story.extend([_table(["Metric", "Recorded Value"], metric_rows, widths=[75 * mm, 95 * mm]), Spacer(1, 4 * mm)])

    rows = _as_mapping_rows(snapshot.get("operational_rows", []))
    if not rows:
        story.append(Paragraph("No Data for the selected report period and filters.", styles["body"]))
        return story

    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    # Attendance status and check-out are essential facts, but appeared after
    # the first six keys and were silently dropped from previous PDF layouts.
    if report.report_type == "Daily Attendance Report" and "attendance_status" in keys:
        keys = [key for key in (
            "employee", "work_date", "scheduled_shift", "check_in", "check_out", "attendance_status",
        ) if key in keys]
    else:
        # Keep the printed table readable. Full detail remains in the CSV export.
        keys = keys[:6]
    headers = [key.replace("_", " ").title() for key in keys]
    widths = [170 * mm / max(1, len(keys))] * len(keys)
    table_rows = [[row.get(key, "Not Recorded") for key in keys] for row in rows[:120]]
    story.append(_table(headers, table_rows, widths=widths))
    if len(rows) > 120:
        story.extend([Spacer(1, 2 * mm), Paragraph(
            f"The PDF displays the first 120 of {len(rows)} detail rows. Use the authorized CSV export for the complete factual dataset.",
            styles["small"],
        )])
    return story

def generate_report_pdf(
    report: FarmReport,
) -> Path:
    REPORT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    display_title = _display_report_title(
        report
    )

    filename = (
        f"{_slug(report.report_code)}_"
        f"REV-{report.revision_number}_"
        f"PDF-{PDF_LAYOUT_VERSION}_"
        f"{_slug(display_title)}.pdf"
    )

    output_path = (
        REPORT_DIRECTORY
        / filename
    )

    styles = _styles()

    document = (
        SimpleDocTemplate(
            str(
                output_path
            ),
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=20 * mm,
            title=display_title,
            author="Joross Farm",
            subject=(
                "Farm Analytics and Production Monitoring Report"
            ),
        )
    )

    story = [
        Paragraph(
            "JOROSS FARM",
            styles["title"],
        ),
        Paragraph(
            "Farm Analytics and Production Monitoring System",
            styles["subtitle"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            display_title,
            ParagraphStyle(
                "ReportTitle",
                parent=styles["title"],
                fontSize=14,
                leading=18,
                textColor=colors.HexColor("#111827"),
                alignment=TA_CENTER,
                spaceBefore=0,
                spaceAfter=0,
                keepWithNext=True,
            ),
        ),
        Spacer(1, 3 * mm),
        _status_label(report, styles),
        Spacer(1, 3 * mm),
        _metadata(report),
        Spacer(1, 5 * mm),
    ]

    section_number = 1

    if _has_section(report, "executive_summary"):
        story.extend([
            _section(f"{section_number}. Executive Summary", styles),
            Paragraph(_safe(report.summary), styles["body"]),
        ])
        section_number += 1

    if _has_section(report, "kpi_overview"):
        section = _executive_kpi_section(report, styles, str(section_number))
        if section:
            story.extend(section)
            section_number += 1

    if _has_section(report, "period_comparison"):
        section = _comparison_section(report, styles, str(section_number))
        if section:
            story.extend(section)
            section_number += 1

    if _has_section(report, "performance_variance"):
        section = _performance_variance_section(report, styles, str(section_number))
        if section:
            story.extend(section)
            section_number += 1

    if _has_section(report, "detailed_analysis"):
        if report.snapshot.get("report_kind") == "operational_factual":
            story.extend(_operational_main(report, report.snapshot, styles, str(section_number)))
        elif report.category in {"Farm", "Trend & Seasonal"}:
            story.extend(_farm_main(report, report.snapshot, styles, str(section_number)))
        elif report.category == "Production & Sales":
            story.extend(_production_sales_main(report, report.snapshot, styles, str(section_number)))
        elif report.category == "Crop":
            story.extend(_crop_main(report, report.snapshot, styles, str(section_number)))
        elif report.category == "Livestock":
            story.extend(_livestock_main(report, report.snapshot, styles, str(section_number)))
        else:
            story.extend(_inventory_main(report, report.snapshot, styles, str(section_number)))
        section_number += 1

    if _has_section(report, "findings"):
        story.extend(_findings_section(report, styles, str(section_number)))
        section_number += 1

    if _has_section(report, "risks"):
        story.extend(_risk_section(report, styles, str(section_number)))
        section_number += 1

    if _has_section(report, "recommendations"):
        story.extend(_recommendations_section(report, styles, str(section_number)))
        section_number += 1

    if _has_section(report, "data_quality"):
        story.extend(_data_quality(report, styles, str(section_number)))
        section_number += 1

    if _has_section(report, "appendix"):
        story.extend(_appendix(report, styles))

    story.append(
        Spacer(
            1,
            8 * mm,
        )
    )

    signature_table = Table(
        [
            [
                "Prepared by",
                "Reviewed / Approved by",
            ],
            [
                Paragraph(
                    (
                        "<br/><br/>"
                        "______________________________"
                        f"<br/>{_safe(report.prepared_by)}"
                    ),
                    styles[
                        "body"
                    ],
                ),
                Paragraph(
                    (
                        "<br/><br/>"
                        "______________________________"
                        f"<br/>{_safe(report.reviewed_by_name or 'Pending Approval')}"
                    ),
                    styles[
                        "body"
                    ],
                ),
            ],
        ],
        colWidths=[
            87 * mm,
            87 * mm,
        ],
    )

    signature_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                GREEN,
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, 0),
                8,
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                BORDER,
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
        ])
    )

    story.append(
        signature_table
    )

    document.build(
        story,
        canvasmaker=NumberedCanvas,
    )

    return output_path
