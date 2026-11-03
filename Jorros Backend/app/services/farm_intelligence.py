from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.farm_time import farm_today
from app.services.report_builder import build_report_snapshot
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


def _subtract_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) - months
    year = total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _risk_summary(risks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"High": 0, "Medium": 0, "Low": 0}
    for risk in risks:
        severity = str(risk.get("severity") or risk.get("level") or "Low").title()
        if severity not in counts:
            severity = "Low"
        counts[severity] += 1

    if counts["High"] > 0:
        status = "Needs Attention"
        status_level = "high"
        message = "One or more high-priority farm risks require review."
    elif counts["Medium"] > 0:
        status = "Monitor Closely"
        status_level = "medium"
        message = "No high-priority risk is active, but some records need management attention."
    else:
        status = "Stable"
        status_level = "low"
        message = "No high- or medium-priority risk was detected from the recorded data."

    return {
        "status": status,
        "status_level": status_level,
        "message": message,
        "high": counts["High"],
        "medium": counts["Medium"],
        "low": counts["Low"],
        "total": sum(counts.values()),
    }


def _coverage_summary(snapshot: dict[str, Any], data_quality: list[dict[str, Any]]) -> dict[str, Any]:
    trend = snapshot.get("trend_analysis", {})
    coverage = trend.get("data_coverage", {})
    checks = [
        {
            "key": "crop_yield_records",
            "label": "Crop yield history",
            "count": int(coverage.get("crop_yield_records") or 0),
            "recommended_minimum": 3,
        },
        {
            "key": "weather_records",
            "label": "Weather history",
            "count": int(coverage.get("weather_records") or 0),
            "recommended_minimum": 3,
        },
        {
            "key": "livestock_growth_records",
            "label": "Livestock growth history",
            "count": int(coverage.get("livestock_growth_records") or 0),
            "recommended_minimum": 3,
        },
        {
            "key": "feeding_records",
            "label": "Feeding history",
            "count": int(coverage.get("feeding_records") or 0),
            "recommended_minimum": 3,
        },
        {
            "key": "livestock_production_records",
            "label": "Production history",
            "count": int(coverage.get("livestock_production_records") or 0),
            "recommended_minimum": 3,
        },
        {
            "key": "sales_records",
            "label": "Crop & livestock sales history",
            "count": int(coverage.get("sales_records") or 0),
            "recommended_minimum": 3,
        },
    ]
    for item in checks:
        item["ready"] = item["count"] >= item["recommended_minimum"]

    return {
        "checks": checks,
        "checks_passed": sum(1 for item in checks if item["ready"]),
        "checks_total": len(checks),
        "quality_notice_count": len(data_quality),
        "raw": coverage,
    }


def _previous_period_has_data(snapshot: dict[str, Any]) -> bool:
    metrics = snapshot.get("metrics", {}) or {}
    # These are true period/event measures.  Static population/inventory snapshots
    # should not make an otherwise empty prior period look comparable.
    evidence_keys = (
        "harvest_records",
        "total_harvest_kg",
        "crop_sales_value",
        "vaccinations_in_period",
        "reproduction_records_in_period",
        "offspring_recorded_in_period",
        "production_records_in_period",
        "growth_measurements_in_period",
        "feeding_records_in_period",
        "actual_feed_kg",
        "processing_records_in_period",
        "animals_processed_head",
        "gross_sales_value",
        "cash_collected",
        "stock_movements",
    )
    for key in evidence_keys:
        try:
            if abs(float(metrics.get(key, 0) or 0)) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _comparison_for_intelligence(
    comparison: dict[str, Any],
    previous_snapshot: dict[str, Any],
) -> dict[str, Any]:
    # If the previous period contains no actual event history, zero is not a
    # meaningful baseline.  Mark rows as unavailable instead of claiming every
    # current metric moved "up" from zero.
    if _previous_period_has_data(previous_snapshot):
        for row in comparison.get("metrics", []):
            row["comparable"] = True
        return comparison

    for row in comparison.get("metrics", []):
        row["comparable"] = False
        row["previous"] = None
        row["difference"] = None
        row["percent_change"] = None
        row["direction"] = "n/a"
        row["assessment"] = "neutral"
        row["note"] = "No comparable history"
    comparison["has_comparable_history"] = False
    return comparison


def _route_for_area(area: str) -> tuple[str, str]:
    normalized = str(area or "").strip().lower()
    if "crop" in normalized:
        return "/crops", "Open Crops"
    if "livestock" in normalized or "health" in normalized:
        return "/livestock", "Open Livestock"
    if "inventory" in normalized or "stock" in normalized:
        return "/inventory", "Open Inventory"
    if "sales" in normalized or "production" in normalized or "receivable" in normalized:
        return "/production-sales", "Open Production & Sales"
    if "alert" in normalized or "task" in normalized:
        return "/alerts", "Open Alerts"
    if "report" in normalized or "quality" in normalized or "analytic" in normalized:
        return "/reports", "Open Reports"
    return "/dashboard", "Open Dashboard"


def _management_actions(
    risks: list[dict[str, Any]],
    recommendations: list[Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for risk in risks:
        text = str(risk.get("action") or risk.get("recommendation") or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        href, label = _route_for_area(str(risk.get("area") or risk.get("category") or ""))
        actions.append({
            "text": text,
            "area": risk.get("area") or risk.get("category") or "Farm",
            "severity": risk.get("severity") or risk.get("level") or "Low",
            "href": href,
            "link_label": label,
        })

    for item in recommendations:
        text = str(item if isinstance(item, str) else item.get("recommendation") or item.get("text") or item.get("message") or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        lowered = text.lower()
        if any(word in lowered for word in ("crop", "harvest", "plant")):
            area = "Crop"
        elif any(word in lowered for word in ("livestock", "animal", "vaccin", "health", "feed")):
            area = "Livestock"
        elif any(word in lowered for word in ("stock", "inventory", "expiry", "expired")):
            area = "Inventory"
        elif any(word in lowered for word in ("sale", "receivable", "payment", "production")):
            area = "Production & Sales"
        else:
            area = "Reports"
        href, label = _route_for_area(area)
        actions.append({
            "text": text,
            "area": area,
            "severity": "Info",
            "href": href,
            "link_label": label,
        })

    return actions[:10]


def _sales_signals(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = snapshot.get("metrics", {}) or {}

    def number(key: str) -> float:
        try:
            return float(metrics.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    return [
        {"label": "Crop Sales", "value": number("crop_sales_value"), "unit": "PHP"},
        {"label": "Livestock Sales", "value": number("livestock_sales_value"), "unit": "PHP"},
        {"label": "Gross Sales", "value": number("gross_sales_value"), "unit": "PHP"},
        {"label": "Cash Collected", "value": number("cash_collected"), "unit": "PHP"},
        {"label": "Receivables", "value": number("outstanding_balance"), "unit": "PHP"},
        {"label": "Collection Rate", "value": number("collection_rate_percent"), "unit": "%"},
        {"label": "Egg Sell-through", "value": number("egg_sell_through_percent"), "unit": "%"},
        {"label": "Meat Sell-through", "value": number("meat_sell_through_percent"), "unit": "%"},
    ]


def _reproduction_signals(snapshot: dict[str, Any]) -> dict[str, Any]:
    metrics = snapshot.get("metrics", {}) or {}

    def integer(key: str) -> int:
        try:
            return int(float(metrics.get(key, 0) or 0))
        except (TypeError, ValueError):
            return 0

    events = integer("reproduction_records_in_period")
    offspring = integer("offspring_recorded_in_period")
    alive = integer("alive_offspring_recorded_in_period")
    survival = (alive / offspring * 100) if offspring > 0 else None
    return {
        "events": events,
        "offspring_recorded": offspring,
        "alive_offspring": alive,
        "offspring_survival_percent": round(survival, 1) if survival is not None else None,
        "has_data": events > 0 or offspring > 0,
    }


def build_farm_intelligence_overview(
    db: Session,
    *,
    months: int = 12,
) -> dict[str, Any]:
    end_date = farm_today()
    start_date = _subtract_months(end_date, max(0, months - 1))

    snapshot = build_report_snapshot(
        db,
        "Farm",
        "Farm Performance Report",
        start_date,
        end_date,
    )

    previous_start, previous_end = previous_period(start_date, end_date)
    previous_snapshot = build_report_snapshot(
        db,
        "Farm",
        "Farm Performance Report",
        previous_start,
        previous_end,
    )

    comparison = build_comparison(
        snapshot,
        previous_snapshot,
        previous_start,
        previous_end,
        previous_snapshot_is_saved=False,
    )
    comparison = _comparison_for_intelligence(comparison, previous_snapshot)
    data_quality = build_data_quality_notices("Farm", snapshot)
    findings = build_findings("Farm", snapshot, comparison)
    recommendations = build_recommendations(
        "Farm",
        snapshot,
        comparison,
        data_quality,
    )
    executive_kpis = build_executive_kpis("Farm", snapshot)
    performance_variance = build_performance_variance("Farm", snapshot)
    risk_flags = build_risk_flags(
        "Farm",
        snapshot,
        comparison,
        data_quality,
    )

    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "months": months,
        },
        "previous_period": {
            "start_date": previous_start.isoformat(),
            "end_date": previous_end.isoformat(),
        },
        "metrics": snapshot.get("metrics", {}),
        "executive_kpis": executive_kpis,
        "sales_signals": _sales_signals(snapshot),
        "reproduction_signals": _reproduction_signals(snapshot),
        "comparison": comparison,
        "performance_variance": performance_variance,
        "risk_flags": risk_flags,
        "risk_summary": _risk_summary(risk_flags),
        "findings": findings,
        "recommendations": recommendations,
        "management_actions": _management_actions(risk_flags, recommendations),
        "data_quality": data_quality,
        "data_readiness": _coverage_summary(snapshot, data_quality),
        "trend_analysis": snapshot.get("trend_analysis", {}),
    }
