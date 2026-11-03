from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any


NEGATIVE_WHEN_HIGHER = {
    "low_stock_items",
    "pest_disease_records",
    "outstanding_balance",
}


PERIOD_EVENT_METRICS = {
    "harvest_records",
    "total_harvest_kg",
    "crop_harvest_records",
    "crop_harvest_kg",
    "crop_sales_records",
    "crop_sales_value",
    "livestock_production_records",
    "livestock_sales_records",
    "livestock_sales_value",
    "average_yield_kg_per_ha",
    "pest_disease_records",
    "vaccinations_in_period",
    "reproduction_records_in_period",
    "offspring_recorded_in_period",
    "production_records_in_period",
    "growth_measurements_in_period",
    "average_daily_gain_kg",
    "feeding_records_in_period",
    "planned_feed_kg",
    "actual_feed_kg",
    "feed_variance_percent",
    "feed_adherence_percent",
    "processing_records_in_period",
    "animals_processed_head",
    "meat_output_kg",
    "egg_production_pcs",
    "average_laying_rate_percent",
    "average_dressing_yield_percent",
    "egg_sell_through_percent",
    "meat_sell_through_percent",
    "sales_records_in_period",
    "gross_sales_value",
    "cash_collected",
    "collected_against_period_sales",
    "collection_rate_percent",
    "outstanding_balance",
    "stock_movements",
    "restock_quantity",
    "usage_quantity",
}


def _numeric_metrics(
    snapshot: dict[str, Any],
) -> dict[str, float]:
    metrics = snapshot.get(
        "metrics",
        {},
    )

    result = {}

    for key, value in metrics.items():
        if isinstance(
            value,
            bool,
        ):
            continue

        if isinstance(
            value,
            (int, float),
        ):
            result[
                key
            ] = float(
                value
            )

    return result


def previous_period(
    start_date: date,
    end_date: date,
    frequency: str | None = None,
) -> tuple[
    date,
    date,
]:
    if frequency == "Daily":
        target = (
            start_date
            - timedelta(
                days=1
            )
        )
        return (
            target,
            target,
        )

    if frequency == "Weekly":
        previous_end = (
            start_date
            - timedelta(
                days=1
            )
        )
        return (
            previous_end
            - timedelta(
                days=6
            ),
            previous_end,
        )

    if frequency == "Monthly":
        first_current = (
            start_date.replace(
                day=1
            )
        )
        previous_end = (
            first_current
            - timedelta(
                days=1
            )
        )
        return (
            previous_end.replace(
                day=1
            ),
            previous_end,
        )

    if frequency == "Yearly":
        year = (
            start_date.year
            - 1
        )
        return (
            date(
                year,
                1,
                1,
            ),
            date(
                year,
                12,
                31,
            ),
        )

    day_count = (
        end_date
        - start_date
    ).days + 1

    previous_end = (
        start_date
        - timedelta(
            days=1
        )
    )

    previous_start = (
        previous_end
        - timedelta(
            days=day_count - 1
        )
    )

    return (
        previous_start,
        previous_end,
    )


def build_comparison(
    current_snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any],
    previous_start: date,
    previous_end: date,
    *,
    previous_snapshot_is_saved: bool = False,
) -> dict[str, Any]:
    current = _numeric_metrics(
        current_snapshot
    )
    previous = _numeric_metrics(
        previous_snapshot
    )

    rows = []

    comparable_keys = (
        (
            set(
                current
            )
            | set(
                previous
            )
        )
        if previous_snapshot_is_saved
        else (
            (
                set(
                    current
                )
                | set(
                    previous
                )
            )
            & PERIOD_EVENT_METRICS
        )
    )

    for key in sorted(
        comparable_keys
    ):
        current_value = float(
            current.get(
                key,
                0,
            )
        )
        previous_value = float(
            previous.get(
                key,
                0,
            )
        )

        difference = (
            current_value
            - previous_value
        )

        percent_change = None

        if previous_value != 0:
            percent_change = (
                difference
                / abs(
                    previous_value
                )
                * 100
            )

        if difference > 0:
            direction = "up"
        elif difference < 0:
            direction = "down"
        else:
            direction = "same"

        if key in NEGATIVE_WHEN_HIGHER:
            if difference > 0:
                assessment = "negative"
            elif difference < 0:
                assessment = "positive"
            else:
                assessment = "neutral"
        else:
            if difference > 0:
                assessment = "positive"
            elif difference < 0:
                assessment = "negative"
            else:
                assessment = "neutral"

        rows.append(
            {
                "metric": key,
                "current": round(
                    current_value,
                    2,
                ),
                "previous": round(
                    previous_value,
                    2,
                ),
                "difference": round(
                    difference,
                    2,
                ),
                "percent_change": (
                    round(
                        percent_change,
                        2,
                    )
                    if percent_change
                    is not None
                    else None
                ),
                "direction": direction,
                "assessment": assessment,
            }
        )

    return {
        "previous_period": {
            "start_date": previous_start.isoformat(),
            "end_date": previous_end.isoformat(),
        },
        "source": (
            "saved_report_snapshot"
            if previous_snapshot_is_saved
            else "period_event_reconstruction"
        ),
        "metrics": rows,
    }


def _metric(
    snapshot: dict[str, Any],
    key: str,
    default: float = 0.0,
) -> float:
    metrics = snapshot.get("metrics", {}) or {}

    try:
        fallback = float(default or 0)
    except (TypeError, ValueError):
        fallback = 0.0

    if key in metrics:
        value = metrics.get(key, 0)
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return fallback

    def raw(name: str) -> float:
        try:
            return float(metrics.get(name, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    if key == "collected_against_period_sales":
        return max(0.0, raw("gross_sales_value") - raw("outstanding_balance"))

    if key == "collection_rate_percent":
        gross = raw("gross_sales_value")
        return (max(0.0, gross - raw("outstanding_balance")) / gross * 100) if gross > 0 else 0.0

    if key == "feed_variance_kg":
        return raw("actual_feed_kg") - raw("planned_feed_kg")

    if key == "feed_variance_percent":
        planned = raw("planned_feed_kg")
        return ((raw("actual_feed_kg") - planned) / planned * 100) if planned > 0 else 0.0

    if key == "feed_adherence_percent":
        planned = raw("planned_feed_kg")
        return (raw("actual_feed_kg") / planned * 100) if planned > 0 else 0.0

    if key == "egg_sell_through_percent":
        produced = raw("egg_production_pcs")
        available = raw("eggs_available_pcs")
        return (max(0.0, produced - available) / produced * 100) if produced > 0 else 0.0

    if key == "meat_sell_through_percent":
        produced = raw("meat_output_kg")
        available = raw("meat_available_kg")
        return (max(0.0, produced - available) / produced * 100) if produced > 0 else 0.0

    if key == "potential_margin_value":
        return raw("retail_value") - raw("cost_value")

    return fallback


def build_data_quality_notices(
    category: str,
    snapshot: dict[str, Any],
) -> list[
    dict[str, str]
]:
    notices: list[
        dict[str, str]
    ] = []

    def add(
        level: str,
        message: str,
    ):
        notices.append(
            {
                "level": level,
                "message": message,
            }
        )

    if category == "Production & Sales":
        metrics = snapshot.get("metrics", {})
        report_type = str(snapshot.get("report_type") or "")
        if report_type in {"Production Summary", "Crop Production & Sales"} and int(metrics.get("crop_harvest_records", 0) or 0) == 0:
            add(
                "Info",
                "No crop harvest records were entered for the selected period.",
            )
        if report_type in {"Production Summary", "Livestock Production & Sales", "Processing Report"} and int(metrics.get("livestock_production_records", 0) or 0) == 0 and int(metrics.get("processing_records", 0) or 0) == 0:
            add(
                "Info",
                "No livestock production or processing output records were entered for the selected period.",
            )
        if report_type in {"Sales Summary", "Crop Production & Sales", "Livestock Production & Sales", "Receivables Report"} and int(metrics.get("sales_records_in_period", 0) or 0) == 0:
            add(
                "Info",
                "No product or live-animal sales were recorded for the selected period.",
            )
        if float(metrics.get("outstanding_balance", 0) or 0) > 0:
            add(
                "Info",
                "Receivables are calculated from recorded paid amounts and balances as of the report snapshot.",
            )

    if category in {
        "Farm",
        "Crop",
    }:
        crop = (
            snapshot.get(
                "crop",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        crop_records = _metric(
            crop,
            "active_crop_records",
            _metric(crop, "crop_records"),
        )

        harvest_records = _metric(
            crop,
            "harvest_records",
        )

        pest_records = _metric(
            crop,
            "pest_disease_records",
        )

        if crop_records == 0:
            add(
                "Warning",
                "No active crop records were available when this report was generated.",
            )
        elif harvest_records == 0:
            add(
                "Info",
                "No harvest records were entered for this reporting period. This does not necessarily mean that no harvest occurred.",
            )

        if (
            crop_records > 0
            and pest_records == 0
        ):
            add(
                "Info",
                "No pest or disease records were entered for this period. This should be interpreted as no recorded incident, not guaranteed absence of pests or disease.",
            )

    if category in {
        "Farm",
        "Livestock",
    }:
        livestock = (
            snapshot.get(
                "livestock",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        livestock_records = _metric(
            livestock,
            "livestock_records",
        )
        vaccinations = _metric(
            livestock,
            "vaccinations_in_period",
        )

        if livestock_records == 0:
            add(
                "Warning",
                "No active livestock records were available when this report was generated.",
            )
        elif vaccinations == 0:
            add(
                "Info",
                "No vaccination entries were recorded for this reporting period. This is a record-availability notice, not confirmation that no vaccinations occurred.",
            )

        growth_measurements = _metric(livestock, "growth_measurements_in_period")
        feeding_records = _metric(livestock, "feeding_records_in_period")
        production_records = _metric(livestock, "production_records_in_period")
        if livestock_records > 0 and growth_measurements == 0:
            add(
                "Info",
                "No livestock weight measurements were recorded in the selected period, so growth-rate conclusions are limited.",
            )
        if livestock_records > 0 and feeding_records == 0:
            add(
                "Info",
                "No confirmed feeding records were available for the selected period; feed variance and adherence cannot be evaluated from confirmations.",
            )
        if livestock_records > 0 and production_records == 0:
            add(
                "Info",
                "No livestock production output records were entered for the selected period.",
            )

    if category in {
        "Farm",
        "Inventory",
    }:
        inventory = (
            snapshot.get(
                "inventory",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        items = _metric(
            inventory,
            "inventory_items",
        )
        movements = _metric(
            inventory,
            "stock_movements",
        )

        if items == 0:
            add(
                "Warning",
                "No active inventory items were available when this report was generated.",
            )
        elif movements == 0:
            add(
                "Info",
                "No stock movement entries were recorded for this reporting period.",
            )

    if category == "Farm":
        coverage = snapshot.get("trend_analysis", {}).get("data_coverage", {})
        months_in_period = int(coverage.get("months_in_period") or 0)
        crop_yield_records = int(coverage.get("crop_yield_records") or 0)
        weather_records = int(coverage.get("weather_records") or 0)
        growth_records = int(coverage.get("livestock_growth_records") or 0)
        feeding_records = int(coverage.get("feeding_records") or 0)
        production_records = int(coverage.get("livestock_production_records") or 0)
        sales_records = int(coverage.get("sales_records") or 0)
        excluded_production = int(coverage.get("voided_production_records_excluded") or 0)
        rainfall_pairs = int(coverage.get("rainfall_yield_pair_months") or 0)
        feed_growth_pairs = int(coverage.get("feed_growth_pair_months") or 0)

        add(
            "Info",
            f"Trend data coverage for {months_in_period} month(s): {crop_yield_records} crop-yield record(s), "
            f"{weather_records} weather record(s), {growth_records} livestock growth record(s), "
            f"{feeding_records} feeding record(s), {production_records} livestock production record(s), "
            f"and {sales_records} crop/livestock sale record(s).",
        )
        if excluded_production > 0:
            add(
                "Info",
                f"{excluded_production} production record(s) linked to voided processing were excluded from trend calculations.",
            )
        if months_in_period > 0:
            add(
                "Info",
                f"Correlation coverage: rainfall-vs-yield used {rainfall_pairs}/{months_in_period} monthly point(s); "
                f"feed-vs-growth used {feed_growth_pairs}/{months_in_period} monthly point(s).",
            )
        if weather_records < 3:
            add(
                "Warning",
                f"Only {weather_records} weather-history record(s) support the selected trend period; weather correlations should be treated as preliminary.",
            )
        if growth_records < 2:
            add(
                "Info",
                f"Only {growth_records} livestock growth measurement(s) support growth-trend analysis in the selected period.",
            )
        if feeding_records == 0:
            add(
                "Info",
                "No confirmed feeding records support feed-to-growth trend analysis in the selected period.",
            )
        if production_records == 0:
            add(
                "Info",
                "No livestock production records support monthly production trend analysis in the selected period.",
            )

    if not notices:
        add(
            "Good",
            "No major record-availability issue was detected in the data used for this report.",
        )

    return notices


def _comparison_row(
    comparison: dict[str, Any],
    metric: str,
) -> dict[str, Any] | None:
    for row in comparison.get(
        "metrics",
        [],
    ):
        if (
            row.get(
                "metric"
            )
            == metric
        ):
            return row

    return None


def build_findings(
    category: str,
    snapshot: dict[str, Any],
    comparison: dict[str, Any],
) -> list[str]:
    findings: list[str] = []

    if category == "Production & Sales":
        metrics = snapshot.get("metrics", {})
        report_type = str(snapshot.get("report_type") or "")
        crop_harvest = float(metrics.get("crop_harvest_kg", 0) or 0)
        eggs = float(metrics.get("egg_production_pcs", 0) or 0)
        meat = float(metrics.get("meat_output_kg", 0) or 0)
        gross = float(metrics.get("gross_sales_value", 0) or 0)
        cash = float(metrics.get("cash_collected", 0) or 0)
        collected_against_sales = float(metrics.get("collected_against_period_sales", 0) or 0)
        outstanding = float(metrics.get("outstanding_balance", 0) or 0)
        rate = float(metrics.get("collection_rate_percent", 0) or 0)

        if report_type in {"Production Summary", "Crop Production & Sales"}:
            findings.append(f"Recorded crop harvest output in the selected period was {crop_harvest:,.2f} kg.")
            if "crop_available_kg" in metrics:
                findings.append(f"Available crop output at snapshot time was {float(metrics.get('crop_available_kg', 0) or 0):,.2f} kg.")

        if report_type in {"Production Summary", "Livestock Production & Sales"}:
            if eggs > 0 or "egg_production_pcs" in metrics:
                findings.append(f"Recorded egg production was {eggs:,.0f} pcs, with {float(metrics.get('eggs_available_pcs', 0) or 0):,.0f} pcs available at snapshot time.")
            if meat > 0 or "meat_output_kg" in metrics:
                findings.append(f"Recorded meat output was {meat:,.2f} kg, with {float(metrics.get('meat_available_kg', 0) or 0):,.2f} kg available at snapshot time.")

        if report_type == "Processing Report":
            findings.append(
                f"{int(metrics.get('animals_processed_head', 0) or 0)} animal(s) were processed, producing {meat:,.2f} kg of meat."
            )

        if report_type in {"Sales Summary", "Crop Production & Sales", "Livestock Production & Sales", "Receivables Report", "Production Summary"}:
            findings.append(f"Gross sales were PHP {gross:,.2f}; PHP {collected_against_sales:,.2f} had been collected against those period sales by report end ({rate:.1f}% collection rate).")
            if abs(cash - collected_against_sales) > 0.005:
                findings.append(f"Actual cash received during the selected period was PHP {cash:,.2f}, including any payments on earlier sales.")
            if outstanding > 0:
                findings.append(f"Outstanding receivables at snapshot time were PHP {outstanding:,.2f}.")
            comparison_row = _comparison_row(comparison, "gross_sales_value")
            if comparison_row and comparison_row.get("percent_change") is not None:
                pct = float(comparison_row.get("percent_change") or 0)
                findings.append(
                    "Gross sales " + (f"increased by {abs(pct):.1f}%" if pct > 0 else f"decreased by {abs(pct):.1f}%" if pct < 0 else "were unchanged") + " versus the previous equivalent period."
                )
        return findings[:8]

    if category in {
        "Farm",
        "Crop",
    }:
        crop = (
            snapshot.get(
                "crop",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        harvest = _metric(
            crop,
            "total_harvest_kg",
        )

        findings.append(
            f"Recorded crop harvest for the selected period was {harvest:,.2f} kg."
        )

        planted = _metric(crop, "quantity_planted")
        if planted > 0:
            survival = _metric(crop, "survival_rate_percent")
            surviving = int(_metric(crop, "current_surviving"))
            findings.append(
                f"Crop survival is {survival:.1f}% ({surviving} surviving out of {int(planted)} planted)."
            )

        pest_count = int(
            _metric(
                crop,
                "pest_disease_records",
            )
        )

        if pest_count > 0:
            findings.append(
                f"{pest_count} pest or disease record(s) were documented during the period."
            )

        crop_sales = _metric(crop, "crop_gross_sales_value")
        if crop_sales > 0:
            crop_cash = _metric(crop, "crop_cash_collected")
            crop_outstanding = _metric(crop, "crop_outstanding_balance")
            findings.append(
                f"Crop sales totaled PHP {crop_sales:,.2f}; PHP {crop_cash:,.2f} cash was received during the selected period and PHP {crop_outstanding:,.2f} remained outstanding on crop sales created in the period."
            )

        harvest_compare = _comparison_row(
            comparison,
            "total_harvest_kg",
        )

        if (
            harvest_compare
            and harvest_compare.get(
                "percent_change"
            )
            is not None
        ):
            percent = float(
                harvest_compare[
                    "percent_change"
                ]
            )

            findings.append(
                "Recorded harvest "
                + (
                    f"increased by {abs(percent):.1f}%"
                    if percent > 0
                    else (
                        f"decreased by {abs(percent):.1f}%"
                        if percent < 0
                        else "was unchanged"
                    )
                )
                + " compared with the previous equivalent period."
            )

    if category in {
        "Farm",
        "Livestock",
    }:
        livestock = (
            snapshot.get(
                "livestock",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        findings.append(
            f"Livestock monitoring covered {int(_metric(livestock, 'total_head'))} animal(s)."
        )

        vaccinations = int(
            _metric(
                livestock,
                "vaccinations_in_period",
            )
        )

        if vaccinations > 0:
            findings.append(
                f"{vaccinations} vaccination record(s) were documented during the reporting period."
            )

        growth_measurements = int(
            _metric(livestock, "growth_measurements_in_period")
        )
        if growth_measurements > 0:
            average_gain = _metric(livestock, "average_daily_gain_kg")
            findings.append(
                f"{growth_measurements} livestock weight measurement(s) supported growth-rate analysis; "
                f"the mean recorded daily gain was {average_gain:,.4f} kg/day."
            )

        planned_feed = _metric(livestock, "planned_feed_kg")
        if planned_feed > 0:
            actual_feed = _metric(livestock, "actual_feed_kg")
            feed_variance = _metric(livestock, "feed_variance_percent")
            findings.append(
                f"Confirmed feed use was {actual_feed:,.3f} kg against {planned_feed:,.3f} kg planned "
                f"({feed_variance:+.1f}% variance)."
            )

        sales_snapshot = snapshot if category == "Farm" else livestock
        gross_sales = _metric(sales_snapshot, "gross_sales_value")
        if gross_sales > 0:
            collection_rate = _metric(sales_snapshot, "collection_rate_percent")
            outstanding = _metric(sales_snapshot, "outstanding_balance")
            findings.append(
                f"Gross period sales were PHP {gross_sales:,.2f}; {collection_rate:.1f}% was collected against those sales by period end, "
                f"leaving PHP {outstanding:,.2f} outstanding."
            )

        egg_capacity = _metric(livestock, "egg_capacity_pcs")
        if egg_capacity > 0:
            findings.append(
                f"Recorded egg laying rate was {_metric(livestock, 'average_laying_rate_percent'):.1f}% of the female-day biological capacity represented in production records."
            )

        if _metric(livestock, "processing_live_weight_kg") > 0:
            findings.append(
                f"Average dressing yield from recorded processing was {_metric(livestock, 'average_dressing_yield_percent'):.1f}%."
            )

    if category == "Farm":
        trends = snapshot.get("trend_analysis", {})
        seasonal_rows = [
            row for row in trends.get("seasonal", [])
            if float(row.get("crop_yield_kg") or 0) > 0
        ]
        if seasonal_rows:
            best = max(
                seasonal_rows,
                key=lambda row: float(row.get("crop_yield_kg") or 0),
            )
            findings.append(
                f"Within the selected period, the {best.get('season')} season had the highest recorded crop yield "
                f"at {float(best.get('crop_yield_kg') or 0):,.2f} kg."
            )

        valid_factors = [
            row for row in trends.get("factor_analysis", [])
            if row.get("correlation") is not None
        ]
        if valid_factors:
            strongest = max(
                valid_factors,
                key=lambda row: abs(float(row.get("correlation") or 0)),
            )
            findings.append(
                f"The strongest recorded linear association was {strongest.get('factor')} "
                f"(r={float(strongest.get('correlation')):.3f}); this is descriptive and does not prove causation."
            )

    if category in {
        "Farm",
        "Inventory",
    }:
        inventory = (
            snapshot.get(
                "inventory",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        low_stock = int(
            _metric(
                inventory,
                "low_stock_items",
            )
        )

        findings.append(
            f"{low_stock} inventory item(s) were at or below their reorder level at report generation."
        )

        cost_value = _metric(inventory, "cost_value")
        retail_value = _metric(inventory, "retail_value")
        if cost_value > 0 or retail_value > 0:
            findings.append(
                f"Current inventory is valued at PHP {cost_value:,.2f} cost and PHP {retail_value:,.2f} potential retail value."
            )

        low_compare = _comparison_row(
            comparison,
            "low_stock_items",
        )

        if (
            low_compare
            and low_compare.get(
                "difference"
            )
        ):
            difference = float(
                low_compare[
                    "difference"
                ]
            )

            findings.append(
                "Low-stock items "
                + (
                    f"increased by {int(abs(difference))}"
                    if difference > 0
                    else f"decreased by {int(abs(difference))}"
                )
                + " compared with the previous equivalent period."
            )

    return findings[:8]


def build_recommendations(
    category: str,
    snapshot: dict[str, Any],
    comparison: dict[str, Any],
    data_quality: list[
        dict[str, str]
    ],
) -> list[str]:
    recommendations: list[str] = []

    if category == "Production & Sales":
        metrics = snapshot.get("metrics", {})
        report_type = str(snapshot.get("report_type") or "")
        if report_type in {"Sales Summary", "Crop Production & Sales", "Livestock Production & Sales", "Receivables Report", "Production Summary"} and float(metrics.get("outstanding_balance", 0) or 0) > 0:
            recommendations.append("Follow up partial or unpaid crop and livestock sales and record collection payments promptly.")
        if report_type in {"Production Summary", "Crop Production & Sales"} and float(metrics.get("crop_available_kg", 0) or 0) > 0:
            recommendations.append("Review available harvested crop quantities, storage condition, pricing, and planned sales before quality declines.")
        if report_type in {"Production Summary", "Livestock Production & Sales"} and float(metrics.get("eggs_available_pcs", 0) or 0) > 0:
            recommendations.append("Review available egg stock and sales timing while keeping hatching-reserved eggs excluded from sellable quantity.")
        if report_type in {"Production Summary", "Livestock Production & Sales", "Processing Report"} and float(metrics.get("meat_available_kg", 0) or 0) > 0:
            recommendations.append("Review remaining meat stock, storage, demand, and sales timing to reduce spoilage risk.")
        gross_compare = _comparison_row(comparison, "gross_sales_value")
        if report_type != "Processing Report" and gross_compare and gross_compare.get("percent_change") is not None and float(gross_compare.get("percent_change") or 0) <= -10:
            recommendations.append("Review the decline in gross sales by product source, available output, pricing, and recorded customer demand.")
        if any(item.get("level") == "Warning" for item in data_quality):
            recommendations.append("Complete missing production or sales records before using this report for final management decisions.")
        if not recommendations:
            recommendations.append("Continue recording production, processing, sales, and collections from the same source records to preserve traceability.")
        return recommendations[:8]

    if category in {
        "Farm",
        "Inventory",
    }:
        inventory = (
            snapshot.get(
                "inventory",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        if _metric(
            inventory,
            "low_stock_items",
        ) > 0:
            recommendations.append(
                "Review low-stock inventory items and schedule replenishment based on reorder levels and upcoming farm activities."
            )

    if category in {
        "Farm",
        "Crop",
    }:
        crop = (
            snapshot.get(
                "crop",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        if _metric(
            crop,
            "pest_disease_records",
        ) > 0:
            recommendations.append(
                "Review the recorded pest and disease cases, verify treatment or control actions, and continue follow-up monitoring."
            )

        if _metric(crop, "quantity_planted") > 0 and _metric(crop, "survival_rate_percent") < 85:
            recommendations.append(
                "Review crop establishment losses and field conditions; document causes of low survival and replant where operationally appropriate."
            )

        if _metric(crop, "crop_outstanding_balance") > 0:
            recommendations.append(
                "Follow up outstanding crop-sale balances and record collection payments promptly."
            )

        harvest_compare = _comparison_row(
            comparison,
            "total_harvest_kg",
        )

        if (
            harvest_compare
            and harvest_compare.get(
                "percent_change"
            )
            is not None
            and float(
                harvest_compare[
                    "percent_change"
                ]
            )
            <= -10
        ):
            recommendations.append(
                "Investigate the decline in recorded harvest by reviewing crop area, crop condition, pest incidents, weather conditions, and harvest completeness."
            )

    if category in {
        "Farm",
        "Livestock",
    }:
        livestock = (
            snapshot.get(
                "livestock",
                {},
            )
            if category
            == "Farm"
            else snapshot
        )

        # Batch health is count-aware.  Under-treatment is a condition on an
        # affected animal, not an extra head-count bucket, and unspecified
        # health should not be treated as sick.
        unhealthy = int(
            _metric(livestock, "sick_head")
            + _metric(livestock, "at_risk_head")
        )

        if unhealthy > 0:
            recommendations.append(
                f"Review the health records of {unhealthy} sick or at-risk livestock head and their treatment/follow-up status."
            )

        if _metric(livestock, "growth_measurements_in_period") < 2:
            recommendations.append(
                "Record periodic livestock weights as child growth measurements so growth rate can be evaluated without duplicating the main livestock batch record."
            )

        if _metric(livestock, "planned_feed_kg") > 0 and abs(_metric(livestock, "feed_variance_percent")) > 10:
            recommendations.append(
                "Review the feed plan against confirmed consumption, animal requirements, and possible feed wastage because actual use differs from plan by more than 10%."
            )

        sales_snapshot = snapshot if category == "Farm" else livestock
        if _metric(sales_snapshot, "outstanding_balance") > 0:
            recommendations.append(
                "Follow up outstanding crop/livestock sale balances and record payments promptly so collection performance remains accurate."
                if category == "Farm"
                else "Follow up outstanding livestock/product sale balances and record payments promptly so collection performance remains accurate."
            )

    if category == "Farm":
        trends = snapshot.get("trend_analysis", {})
        coverage = trends.get("data_coverage", {})
        if int(coverage.get("weather_records") or 0) < 3:
            recommendations.append(
                "Continue recording weather observations so seasonal and weather-to-yield comparisons become more reliable over time."
            )

    if any(
        item.get(
            "level"
        )
        == "Warning"
        for item in data_quality
    ):
        recommendations.append(
            "Complete missing production records before using this report for final operational or management decisions."
        )

    if not recommendations:
        recommendations.append(
            "Continue routine monitoring and maintain complete, timely crop, livestock, and inventory records for the next reporting period."
        )

    return recommendations[:8]


def _variance_row(
    metric: str,
    actual: float,
    reference: float,
    *,
    unit: str = "",
    reference_label: str = "Expected / Reference",
    lower_is_better: bool = False,
) -> dict[str, Any]:
    actual_value = float(actual or 0)
    reference_value = float(reference or 0)
    variance = actual_value - reference_value
    variance_percent = (
        variance / abs(reference_value) * 100
        if reference_value != 0
        else None
    )

    if variance == 0:
        assessment = "on_target"
    elif lower_is_better:
        assessment = "positive" if variance < 0 else "negative"
    else:
        assessment = "positive" if variance > 0 else "negative"

    return {
        "metric": metric,
        "actual": round(actual_value, 3),
        "reference": round(reference_value, 3),
        "reference_label": reference_label,
        "variance": round(variance, 3),
        "variance_percent": (
            round(variance_percent, 2)
            if variance_percent is not None
            else None
        ),
        "unit": unit,
        "assessment": assessment,
    }


def build_performance_variance(
    category: str,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if category == "Production & Sales":
        report_type = str(snapshot.get("report_type") or "")
        gross_sales = _metric(snapshot, "gross_sales_value")
        collected_against_sales = _metric(snapshot, "collected_against_period_sales")
        if report_type != "Processing Report" and gross_sales > 0:
            rows.append(
                _variance_row(
                    "Collections against gross sales",
                    collected_against_sales,
                    gross_sales,
                    unit="PHP",
                    reference_label="Gross sales",
                )
            )
        return rows

    crop = snapshot.get("crop", {}) if category == "Farm" else snapshot
    livestock = snapshot.get("livestock", {}) if category == "Farm" else snapshot

    if category in {"Farm", "Crop"}:
        planted = _metric(crop, "quantity_planted")
        surviving = _metric(crop, "current_surviving")
        if planted > 0:
            rows.append(
                _variance_row(
                    "Crop survival vs planted baseline",
                    surviving,
                    planted,
                    unit="plants",
                    reference_label="Quantity planted",
                )
            )

        harvest_schedule_variance = _metric(
            crop,
            "average_harvest_schedule_variance_days",
        )
        if _metric(crop, "harvest_records") > 0:
            rows.append(
                _variance_row(
                    "Average harvest schedule variance",
                    harvest_schedule_variance,
                    0,
                    unit="days",
                    reference_label="Estimated harvest date",
                    lower_is_better=True,
                )
            )

    if category in {"Farm", "Livestock"}:
        planned_feed = _metric(livestock, "planned_feed_kg")
        actual_feed = _metric(livestock, "actual_feed_kg")
        if planned_feed > 0:
            rows.append(
                _variance_row(
                    "Feed consumption",
                    actual_feed,
                    planned_feed,
                    unit="kg",
                    reference_label="Planned feed",
                    lower_is_better=True,
                )
            )

        egg_capacity = _metric(livestock, "egg_capacity_pcs")
        egg_production = _metric(livestock, "egg_production_pcs")
        if egg_capacity > 0:
            rows.append(
                _variance_row(
                    "Egg production vs biological capacity",
                    egg_production,
                    egg_capacity,
                    unit="pcs",
                    reference_label="Female-days maximum",
                )
            )

        sales_snapshot = snapshot if category == "Farm" else livestock
        gross_sales = _metric(sales_snapshot, "gross_sales_value")
        period_collected = _metric(
            sales_snapshot,
            "collected_against_period_sales",
        )
        if gross_sales > 0:
            rows.append(
                _variance_row(
                    "Collections against period sales",
                    period_collected,
                    gross_sales,
                    unit="PHP",
                    reference_label="Gross period sales",
                )
            )

    return rows


def build_executive_kpis(
    category: str,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    def item(label: str, value: float, unit: str = "") -> dict[str, Any]:
        return {
            "label": label,
            "value": round(float(value or 0), 3),
            "unit": unit,
        }

    if category == "Production & Sales":
        report_type = str(snapshot.get("report_type") or "")
        if report_type == "Crop Production & Sales":
            return [
                item("Crop Harvest", _metric(snapshot, "crop_harvest_kg"), "kg"),
                item("Crop Available", _metric(snapshot, "crop_available_kg"), "kg"),
                item("Crop Sales", _metric(snapshot, "crop_sales_value"), "PHP"),
                item("Cash Collected", _metric(snapshot, "cash_collected"), "PHP"),
                item("Receivables", _metric(snapshot, "outstanding_balance"), "PHP"),
                item("Collection Rate", _metric(snapshot, "collection_rate_percent"), "%"),
            ]
        if report_type == "Livestock Production & Sales":
            return [
                item("Egg Production", _metric(snapshot, "egg_production_pcs"), "pcs"),
                item("Eggs Available", _metric(snapshot, "eggs_available_pcs"), "pcs"),
                item("Meat Output", _metric(snapshot, "meat_output_kg"), "kg"),
                item("Meat Available", _metric(snapshot, "meat_available_kg"), "kg"),
                item("Livestock Sales", _metric(snapshot, "livestock_sales_value"), "PHP"),
                item("Receivables", _metric(snapshot, "outstanding_balance"), "PHP"),
            ]
        if report_type == "Processing Report":
            return [
                item("Processed", _metric(snapshot, "animals_processed_head"), "head"),
                item("Meat Output", _metric(snapshot, "meat_output_kg"), "kg"),
                item("Meat Available", _metric(snapshot, "meat_available_kg"), "kg"),
                item("Gross Sales", _metric(snapshot, "gross_sales_value"), "PHP"),
            ]
        if report_type == "Receivables Report":
            return [
                item("Sales Records", _metric(snapshot, "sales_records_in_period")),
                item("Gross Sales", _metric(snapshot, "gross_sales_value"), "PHP"),
                item("Cash Collected", _metric(snapshot, "cash_collected"), "PHP"),
                item("Receivables", _metric(snapshot, "outstanding_balance"), "PHP"),
                item("Collection Rate", _metric(snapshot, "collection_rate_percent"), "%"),
            ]
        if report_type == "Sales Summary":
            return [
                item("Crop Sales", _metric(snapshot, "crop_sales_value"), "PHP"),
                item("Livestock Sales", _metric(snapshot, "livestock_sales_value"), "PHP"),
                item("Gross Sales", _metric(snapshot, "gross_sales_value"), "PHP"),
                item("Cash Collected", _metric(snapshot, "cash_collected"), "PHP"),
                item("Receivables", _metric(snapshot, "outstanding_balance"), "PHP"),
                item("Collection Rate", _metric(snapshot, "collection_rate_percent"), "%"),
            ]
        return [
            item("Crop Harvest", _metric(snapshot, "crop_harvest_kg"), "kg"),
            item("Egg Production", _metric(snapshot, "egg_production_pcs"), "pcs"),
            item("Meat Output", _metric(snapshot, "meat_output_kg"), "kg"),
            item("Gross Sales", _metric(snapshot, "gross_sales_value"), "PHP"),
            item("Cash Collected", _metric(snapshot, "cash_collected"), "PHP"),
            item("Receivables", _metric(snapshot, "outstanding_balance"), "PHP"),
        ]

    if category == "Crop":
        return [
            item("Harvest", _metric(snapshot, "total_harvest_kg"), "kg"),
            item("Available Crop Output", _metric(snapshot, "crop_available_kg"), "kg"),
            item("Crop Sales", _metric(snapshot, "crop_gross_sales_value"), "PHP"),
            item("Crop Receivables", _metric(snapshot, "crop_outstanding_balance"), "PHP"),
            item("Yield", _metric(snapshot, "average_yield_kg_per_ha"), "kg/ha"),
            item("Survival Rate", _metric(snapshot, "survival_rate_percent"), "%"),
            item("Area Monitored", _metric(snapshot, "total_area_ha"), "ha"),
            item("Pest/Disease Records", _metric(snapshot, "pest_disease_records")),
        ]

    if category == "Livestock":
        return [
            item("Livestock Head", _metric(snapshot, "total_head"), "head"),
            item("Sick / At Risk", _metric(snapshot, "sick_head") + _metric(snapshot, "at_risk_head"), "head"),
            item("Under Treatment", _metric(snapshot, "under_treatment_head"), "head"),
            item("Avg. Daily Gain", _metric(snapshot, "average_daily_gain_kg"), "kg/day"),
            item("Feed Adherence", _metric(snapshot, "feed_adherence_percent"), "%"),
            item("Laying Rate", _metric(snapshot, "average_laying_rate_percent"), "%"),
            item("Gross Sales", _metric(snapshot, "gross_sales_value"), "PHP"),
            item("Collection Rate", _metric(snapshot, "collection_rate_percent"), "%"),
            item("Egg Sell-through", _metric(snapshot, "egg_sell_through_percent"), "%"),
            item("Meat Sell-through", _metric(snapshot, "meat_sell_through_percent"), "%"),
        ]

    if category == "Inventory":
        return [
            item("Inventory Items", _metric(snapshot, "inventory_items")),
            item("Low Stock", _metric(snapshot, "low_stock_items")),
            item("Expiring", _metric(snapshot, "expiring_items")),
            item("Cost Value", _metric(snapshot, "cost_value"), "PHP"),
            item("Retail Value", _metric(snapshot, "retail_value"), "PHP"),
            item("Potential Margin", _metric(snapshot, "potential_margin_value"), "PHP"),
        ]

    crop = snapshot.get("crop", {})
    livestock = snapshot.get("livestock", {})
    inventory = snapshot.get("inventory", {})
    return [
        item("Crop Harvest", _metric(crop, "total_harvest_kg"), "kg"),
        item("Crop Survival", _metric(crop, "survival_rate_percent"), "%"),
        item("Livestock Head", _metric(livestock, "total_head"), "head"),
        item("Avg. Daily Gain", _metric(livestock, "average_daily_gain_kg"), "kg/day"),
        item("Gross Sales", _metric(snapshot, "gross_sales_value"), "PHP"),
        item("Collection Rate", _metric(snapshot, "collection_rate_percent"), "%"),
        item("Low Stock Items", _metric(inventory, "low_stock_items")),
        item("Inventory Value", _metric(inventory, "cost_value"), "PHP"),
    ]


def build_risk_flags(
    category: str,
    snapshot: dict[str, Any],
    comparison: dict[str, Any],
    data_quality: list[dict[str, str]],
) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []

    def add(level: str, area: str, issue: str, action: str) -> None:
        risks.append(
            {
                "level": level,
                "area": area,
                "issue": issue,
                "action": action,
            }
        )

    if category == "Production & Sales":
        report_type = str(snapshot.get("report_type") or "")
        outstanding = _metric(snapshot, "outstanding_balance")
        if report_type != "Processing Report" and outstanding > 0:
            add(
                "Medium",
                "Sales",
                f"Outstanding receivables total PHP {outstanding:,.2f}.",
                "Follow up partial or unpaid sales and record collection payments.",
            )
        if report_type in {"Production Summary", "Livestock Production & Sales", "Processing Report"} and _metric(snapshot, "meat_available_kg") > 0:
            add(
                "Low",
                "Production & Sales",
                f"{_metric(snapshot, 'meat_available_kg'):,.2f} kg meat remains available for sale.",
                "Review storage condition and sales timing.",
            )
        if any(item.get("level") == "Warning" for item in data_quality):
            add(
                "Medium",
                "Data Quality",
                "One or more data-availability warnings affect this report.",
                "Complete missing production or sales records before final decisions.",
            )
        if not risks:
            add(
                "Low",
                "Production & Sales",
                "No material production or sales risk flag was detected from the recorded data.",
                "Continue routine production, sales, and collection monitoring.",
            )
        return risks[:10]

    crop = snapshot.get("crop", {}) if category == "Farm" else snapshot
    livestock = snapshot.get("livestock", {}) if category == "Farm" else snapshot
    inventory = snapshot.get("inventory", {}) if category == "Farm" else snapshot

    if category in {"Farm", "Crop"}:
        survival = _metric(crop, "survival_rate_percent")
        planted = _metric(crop, "quantity_planted")
        if planted > 0 and survival < 85:
            add(
                "High" if survival < 70 else "Medium",
                "Crop",
                f"Recorded crop survival is {survival:.1f}%.",
                "Review establishment losses, field conditions, and replanting needs.",
            )

        pest_count = int(_metric(crop, "pest_disease_records"))
        if pest_count > 0:
            add(
                "Medium",
                "Crop",
                f"{pest_count} pest or disease incident(s) were recorded.",
                "Confirm treatment, affected-area follow-up, and resolution status.",
            )

        crop_receivable = _metric(crop, "crop_outstanding_balance")
        if crop_receivable > 0:
            add(
                "Medium",
                "Crop Sales",
                f"Outstanding crop-sale receivables total PHP {crop_receivable:,.2f}.",
                "Follow up partial or unpaid crop sales and record collection payments.",
            )

        harvest_compare = _comparison_row(comparison, "total_harvest_kg")
        if harvest_compare and harvest_compare.get("percent_change") is not None:
            pct = float(harvest_compare.get("percent_change") or 0)
            if pct <= -10:
                add(
                    "Medium",
                    "Crop",
                    f"Recorded harvest decreased by {abs(pct):.1f}% from the previous equivalent period.",
                    "Review area, crop condition, seasonal conditions, and harvest completeness.",
                )

    if category in {"Farm", "Livestock"}:
        unhealthy = int(
            _metric(livestock, "sick_head")
            + _metric(livestock, "at_risk_head")
        )
        if unhealthy > 0:
            add(
                "High" if unhealthy >= 5 else "Medium",
                "Livestock",
                f"{unhealthy} livestock head are recorded as sick or at risk.",
                "Review health notes, treatment status, and follow-up checks.",
            )

        feed_variance = _metric(livestock, "feed_variance_percent")
        planned_feed = _metric(livestock, "planned_feed_kg")
        if planned_feed > 0 and abs(feed_variance) > 10:
            direction = "above" if feed_variance > 0 else "below"
            add(
                "Medium",
                "Feeding",
                f"Actual feed use is {abs(feed_variance):.1f}% {direction} plan.",
                "Review feeding confirmation, ration assumptions, wastage, and animal requirements.",
            )

        sales_snapshot = snapshot if category == "Farm" else livestock
        outstanding = _metric(sales_snapshot, "outstanding_balance")
        if outstanding > 0:
            add(
                "Medium",
                "Sales",
                f"Outstanding receivables total PHP {outstanding:,.2f}.",
                "Follow up partial or unpaid sales and record collection payments.",
            )

        if _metric(livestock, "egg_production_pcs") > 0:
            egg_sell_through = _metric(livestock, "egg_sell_through_percent")
            if egg_sell_through < 50 and _metric(livestock, "eggs_available_pcs") > 0:
                add(
                    "Medium",
                    "Production & Sales",
                    f"Egg sell-through for production created in the period is {egg_sell_through:.1f}%.",
                    "Review available egg inventory, demand, pricing, and sales timing.",
                )

        if _metric(livestock, "meat_output_kg") > 0:
            meat_sell_through = _metric(livestock, "meat_sell_through_percent")
            if meat_sell_through < 50 and _metric(livestock, "meat_available_kg") > 0:
                add(
                    "Medium",
                    "Production & Sales",
                    f"Meat sell-through for production created in the period is {meat_sell_through:.1f}%.",
                    "Review remaining meat inventory, storage, demand, and sales timing.",
                )

    if category in {"Farm", "Inventory"}:
        low_stock = int(_metric(inventory, "low_stock_items"))
        if low_stock > 0:
            add(
                "High" if low_stock >= 5 else "Medium",
                "Inventory",
                f"{low_stock} item(s) are at or below reorder level.",
                "Prioritize replenishment based on upcoming farm activities.",
            )
        expiring = int(_metric(inventory, "expiring_items"))
        if expiring > 0:
            add(
                "Medium",
                "Inventory",
                f"{expiring} stocked item(s) are expired or within the 30-day expiry window.",
                "Review FEFO usage, disposal, or replacement actions.",
            )

    if category == "Farm":
        coverage = snapshot.get("trend_analysis", {}).get("data_coverage", {})
        weather_count = int(coverage.get("weather_records") or 0)
        if weather_count < 3:
            add(
                "Low",
                "Analytics",
                "Weather-history coverage is limited for seasonal factor analysis.",
                "Continue collecting weather observations before relying on weather correlations.",
            )

    if any(item.get("level") == "Warning" for item in data_quality):
        add(
            "Medium",
            "Data Quality",
            "One or more important data-availability warnings affect this report.",
            "Complete the missing records before using the report for final management decisions.",
        )

    if not risks:
        add(
            "Low",
            "Farm",
            "No material operational risk flag was detected from the recorded data and configured thresholds.",
            "Continue routine monitoring and timely record entry.",
        )

    return risks[:10]
