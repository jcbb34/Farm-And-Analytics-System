from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.trend_queries import load_trend_aggregates

from app.models import (
    Crop,
    CropYieldRecord,
    Livestock,
    LivestockFeedingRecord,
    LivestockGrowthRecord,
    LivestockProductionRecord,
    LivestockProcessingRecord,
    LivestockReproductionRecord,
    LivestockSale,
    LivestockSalePayment,
    WeatherHistory,
)


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_label(key: str) -> str:
    year, month = (int(part) for part in key.split("-"))
    return date(year, month, 1).strftime("%b %Y")


def _season(month: int) -> str:
    if month in {12, 1, 2}:
        return "Cool Dry"
    if month in {3, 4, 5}:
        return "Hot Dry"
    return "Rainy"


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    # Fewer than three monthly observations can make a correlation look
    # artificially perfect, so keep the factor result as insufficient data.
    if len(pairs) < 3:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    mx = mean(xs)
    my = mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denominator = sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denominator


def _correlation_payload(name: str, value: float | None, caution: str) -> dict[str, Any]:
    if value is None:
        return {
            "factor": name,
            "correlation": None,
            "direction": "Insufficient data",
            "strength": "Insufficient data",
            "note": caution,
        }

    absolute = abs(value)
    if absolute >= 0.7:
        strength = "Strong"
    elif absolute >= 0.4:
        strength = "Moderate"
    elif absolute >= 0.2:
        strength = "Weak"
    else:
        strength = "Very weak"

    if value > 0.05:
        direction = "Positive"
    elif value < -0.05:
        direction = "Negative"
    else:
        direction = "Little/no linear relationship"

    return {
        "factor": name,
        "correlation": round(value, 3),
        "direction": direction,
        "strength": strength,
        "note": caution,
    }


def build_trend_analysis(db: Session, start_date: date, end_date: date) -> dict[str, Any]:
    aggregates = load_trend_aggregates(db, start_date, end_date)
    counts = aggregates["counts"]
    growth_records, livestock_by_id = aggregates["growth_records"], aggregates["animals"]

    month_keys: list[str] = []
    cursor = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)
    while cursor <= last:
        month_keys.append(_month_key(cursor))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    monthly_crop_yield = aggregates["crop_yield"]
    crop_yield_by_name = aggregates["crop_names"]
    monthly_weather = aggregates["weather"]
    monthly_feed = aggregates["feed"]
    monthly_growth_gain = aggregates["growth"]
    monthly_production = aggregates["production"]
    monthly_sales_value, monthly_crop_sales_value, monthly_livestock_sales_value = aggregates["sales"], aggregates["crop_sales"], aggregates["animal_sales"]
    monthly_cash_collected = aggregates["cash"]
    monthly_reproduction_events, monthly_offspring, monthly_alive_offspring = aggregates["reproduction"], aggregates["offspring"], aggregates["alive"]

    monthly = []
    for key in month_keys:
        weather_bucket = monthly_weather.get(key, {})
        growth_value = monthly_growth_gain.get(key)
        year, month = (int(part) for part in key.split("-"))
        monthly.append(
            {
                "month": key,
                "label": _month_label(key),
                "season": _season(month),
                "crop_yield_kg": round(monthly_crop_yield[key], 2),
                "feed_consumption_kg": round(monthly_feed[key], 3),
                "average_daily_gain_kg": (
                    round(float(growth_value), 4) if growth_value is not None else None
                ),
                "average_rainfall_mm": (
                    round(float(weather_bucket["rainfall"]), 2)
                    if weather_bucket.get("rainfall") is not None
                    else None
                ),
                "average_temperature_c": (
                    round(float(weather_bucket["temperature"]), 2)
                    if weather_bucket.get("temperature") is not None
                    else None
                ),
                "average_humidity_percent": (
                    round(float(weather_bucket["humidity"]), 1)
                    if weather_bucket.get("humidity") is not None
                    else None
                ),
                "production": dict(monthly_production[key]),
                "gross_sales_value": round(monthly_sales_value[key], 2),
                "crop_sales_value": round(monthly_crop_sales_value[key], 2),
                "livestock_sales_value": round(monthly_livestock_sales_value[key], 2),
                "cash_collected": round(monthly_cash_collected[key], 2),
                "reproduction_events": int(monthly_reproduction_events[key]),
                "offspring_recorded": int(monthly_offspring[key]),
                "alive_offspring": int(monthly_alive_offspring[key]),
            }
        )

    seasons = defaultdict(
        lambda: {
            "months": 0,
            "crop_yield_kg": 0.0,
            "feed_consumption_kg": 0.0,
            "growth_values": [],
            "production": defaultdict(float),
            "gross_sales_value": 0.0,
            "crop_sales_value": 0.0,
            "livestock_sales_value": 0.0,
            "cash_collected": 0.0,
        }
    )
    for row in monthly:
        bucket = seasons[row["season"]]
        bucket["months"] += 1
        bucket["crop_yield_kg"] += row["crop_yield_kg"]
        bucket["feed_consumption_kg"] += row["feed_consumption_kg"]
        if row["average_daily_gain_kg"] is not None:
            bucket["growth_values"].append(row["average_daily_gain_kg"])
        for output, quantity in row["production"].items():
            bucket["production"][output] += quantity
        bucket["gross_sales_value"] += float(row.get("gross_sales_value") or 0)
        bucket["crop_sales_value"] += float(row.get("crop_sales_value") or 0)
        bucket["livestock_sales_value"] += float(row.get("livestock_sales_value") or 0)
        bucket["cash_collected"] += float(row.get("cash_collected") or 0)

    seasonal = []
    for season_name in ("Cool Dry", "Hot Dry", "Rainy"):
        bucket = seasons[season_name]
        seasonal.append(
            {
                "season": season_name,
                "months_in_period": bucket["months"],
                "crop_yield_kg": round(bucket["crop_yield_kg"], 2),
                "feed_consumption_kg": round(bucket["feed_consumption_kg"], 3),
                "average_daily_gain_kg": (
                    round(mean(bucket["growth_values"]), 4)
                    if bucket["growth_values"]
                    else None
                ),
                "production": dict(bucket["production"]),
                "gross_sales_value": round(bucket["gross_sales_value"], 2),
                "crop_sales_value": round(bucket["crop_sales_value"], 2),
                "livestock_sales_value": round(bucket["livestock_sales_value"], 2),
                "cash_collected": round(bucket["cash_collected"], 2),
            }
        )

    rainfall_pairs = [
        (row["average_rainfall_mm"], row["crop_yield_kg"])
        for row in monthly
        if row["average_rainfall_mm"] is not None and row["crop_yield_kg"] > 0
    ]
    temperature_pairs = [
        (row["average_temperature_c"], row["crop_yield_kg"])
        for row in monthly
        if row["average_temperature_c"] is not None and row["crop_yield_kg"] > 0
    ]
    feed_growth_pairs = [
        (row["feed_consumption_kg"], row["average_daily_gain_kg"])
        for row in monthly
        if row["feed_consumption_kg"] > 0 and row["average_daily_gain_kg"] is not None
    ]

    factor_analysis = [
        _correlation_payload(
            "Recorded rainfall vs crop yield",
            _pearson(rainfall_pairs),
            "Correlation is descriptive only and does not prove that rainfall caused the yield change.",
        ),
        _correlation_payload(
            "Temperature vs crop yield",
            _pearson(temperature_pairs),
            "Correlation is descriptive only and should be interpreted with crop variety, field, pests, and management records.",
        ),
        _correlation_payload(
            "Feed consumption vs livestock daily gain",
            _pearson(feed_growth_pairs),
            "This compares monthly feed use with recorded weight-gain measurements; it does not by itself establish feed efficiency.",
        ),
    ]

    health_distribution = aggregates["health"]

    top_crops = sorted(
        (
            {"crop": crop_name, "yield_kg": round(quantity, 2)}
            for crop_name, quantity in crop_yield_by_name.items()
        ),
        key=lambda item: item["yield_kg"],
        reverse=True,
    )[:8]

    production_series = sorted(
        {
            output
            for row in monthly
            for output in row["production"].keys()
        }
    )

    totals = aggregates["reproduction_totals"]
    reproduction_events = counts["reproduction_records"]
    breeder_females, confirmed_pregnant = totals["breeder_female_quantity"], totals["confirmed_pregnant_quantity"]
    eggs_set, fertile_eggs = totals["eggs_set"], totals["fertile_eggs"]
    offspring_recorded, alive_offspring = totals["offspring_count"], totals["alive_offspring"]
    reproduction_losses, birth_hatch_events = totals["loss_count"], totals["birth_hatch_events"]
    reproduction_summary = {
        "events": reproduction_events,
        "birth_hatch_events": birth_hatch_events,
        "breeder_females": breeder_females,
        "confirmed_pregnant": confirmed_pregnant,
        "eggs_set": eggs_set,
        "fertile_eggs": fertile_eggs,
        "fertility_percent": round(fertile_eggs / eggs_set * 100, 1) if eggs_set > 0 else None,
        "offspring_recorded": offspring_recorded,
        "alive_offspring": alive_offspring,
        "losses": reproduction_losses,
        "offspring_survival_percent": round(alive_offspring / offspring_recorded * 100, 1) if offspring_recorded > 0 else None,
    }

    growth_by_livestock: dict[int, list[LivestockGrowthRecord]] = defaultdict(list)
    for record in growth_records:
        growth_by_livestock[record.livestock_id].append(record)

    growth_summary = []
    for livestock_id, records in growth_by_livestock.items():
        ordered = sorted(records, key=lambda item: (item.measurement_date, item.id))
        first = ordered[0]
        last_record = ordered[-1]
        animal = livestock_by_id.get(livestock_id)

        if first.previous_weight_kg is not None and first.days_since_previous:
            start_weight = float(first.previous_weight_kg)
            growth_start_date = date.fromordinal(
                first.measurement_date.toordinal() - int(first.days_since_previous)
            )
            measurement_count = int(first.measurement_count) + 1
        else:
            start_weight = float(first.weight_kg or 0)
            growth_start_date = first.measurement_date
            measurement_count = int(first.measurement_count)

        latest_weight = float(last_record.weight_kg or 0)
        total_change = latest_weight - start_weight
        total_days = (last_record.measurement_date - growth_start_date).days
        avg_daily = total_change / total_days if total_days > 0 else None
        growth_summary.append(
            {
                "livestock_id": livestock_id,
                "record_name": animal.record_name if animal else "Unknown Livestock",
                "animal_type": animal.animal_type if animal else "Unknown",
                "measurements": measurement_count,
                "start_weight_kg": round(start_weight, 2),
                "latest_weight_kg": round(latest_weight, 2),
                "total_change_kg": round(total_change, 2),
                "average_daily_gain_kg": round(avg_daily, 4) if avg_daily is not None else None,
                "animals_measured": int(last_record.animals_measured or 0) if last_record.animals_measured is not None else None,
                "measurement_basis": str(last_record.measurement_basis or "Average"),
                "min_weight_kg": round(float(last_record.min_weight_kg), 2) if last_record.min_weight_kg is not None else None,
                "max_weight_kg": round(float(last_record.max_weight_kg), 2) if last_record.max_weight_kg is not None else None,
                "start_date": growth_start_date.isoformat(),
                "latest_date": last_record.measurement_date.isoformat(),
            }
        )
    growth_summary.sort(key=lambda item: (item["average_daily_gain_kg"] is None, -(item["average_daily_gain_kg"] or 0)))

    return {
        "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "monthly": monthly,
        "seasonal": seasonal,
        "factor_analysis": factor_analysis,
        "top_crops": top_crops,
        "production_series": production_series,
        "reproduction_summary": reproduction_summary,
        "growth_summary": growth_summary,
        "health_distribution": [
            {"label": label, "value": value}
            for label, value in sorted(health_distribution.items())
        ],
        "data_coverage": {
            "months_in_period": len(monthly),
            "crop_yield_records": counts["crop_yield_records"],
            "weather_records": counts["weather_records"],
            "livestock_growth_records": counts["livestock_growth_records"],
            "feeding_records": counts["feeding_records"],
            "livestock_production_records": counts["livestock_production_records"],
            "reproduction_records": counts["reproduction_records"],
            "sales_records": counts["sales_records"],
            "payment_records": counts["payment_records"],
            "crop_sales_records": counts["crop_sales_records"],
            "livestock_sales_records": counts["livestock_sales_records"],
            "voided_production_records_excluded": counts["voided_production_records_excluded"],
            "rainfall_yield_pair_months": len(rainfall_pairs),
            "temperature_yield_pair_months": len(temperature_pairs),
            "feed_growth_pair_months": len(feed_growth_pairs),
            "rainfall_yield_months_excluded": max(0, len(monthly) - len(rainfall_pairs)),
            "temperature_yield_months_excluded": max(0, len(monthly) - len(temperature_pairs)),
            "feed_growth_months_excluded": max(0, len(monthly) - len(feed_growth_pairs)),
        },
    }
