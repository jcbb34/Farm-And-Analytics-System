from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
    crops = list(db.scalars(select(Crop)).all())
    crop_by_id = {item.id: item for item in crops}

    crop_yields = list(
        db.scalars(
            select(CropYieldRecord)
            .where(
                CropYieldRecord.harvest_date >= start_date,
                CropYieldRecord.harvest_date <= end_date,
            )
            .order_by(CropYieldRecord.harvest_date.asc())
        ).all()
    )

    weather = list(
        db.scalars(
            select(WeatherHistory)
            .where(
                WeatherHistory.recorded_date >= start_date,
                WeatherHistory.recorded_date <= end_date,
            )
            .order_by(WeatherHistory.recorded_date.asc())
        ).all()
    )

    livestock = list(db.scalars(select(Livestock)).all())
    livestock_by_id = {item.id: item for item in livestock}

    growth_records = list(
        db.scalars(
            select(LivestockGrowthRecord)
            .where(
                LivestockGrowthRecord.measurement_date >= start_date,
                LivestockGrowthRecord.measurement_date <= end_date,
            )
            .order_by(LivestockGrowthRecord.measurement_date.asc())
        ).all()
    )

    feeding_records = list(
        db.scalars(
            select(LivestockFeedingRecord)
            .where(
                LivestockFeedingRecord.feeding_date >= start_date,
                LivestockFeedingRecord.feeding_date <= end_date,
            )
            .order_by(LivestockFeedingRecord.feeding_date.asc())
        ).all()
    )

    reproduction_records = list(
        db.scalars(
            select(LivestockReproductionRecord)
            .where(
                LivestockReproductionRecord.event_date >= start_date,
                LivestockReproductionRecord.event_date <= end_date,
            )
            .order_by(LivestockReproductionRecord.event_date.asc())
        ).all()
    )

    production_records = list(
        db.scalars(
            select(LivestockProductionRecord)
            .where(
                LivestockProductionRecord.record_date >= start_date,
                LivestockProductionRecord.record_date <= end_date,
                func.lower(LivestockProductionRecord.source_type) == "livestock",
            )
            .order_by(LivestockProductionRecord.record_date.asc())
        ).all()
    )

    production_records_before_void_filter = len(production_records)

    voided_processing_production_ids = set(
        db.scalars(
            select(LivestockProcessingRecord.production_record_id).where(
                LivestockProcessingRecord.is_voided == True
            )
        ).all()
    )
    if voided_processing_production_ids:
        production_records = [
            record
            for record in production_records
            if record.id not in voided_processing_production_ids
        ]

    sales_records = list(
        db.scalars(
            select(LivestockSale)
            .where(
                LivestockSale.sale_date >= start_date,
                LivestockSale.sale_date <= end_date,
                LivestockSale.is_voided == False,
            )
            .order_by(LivestockSale.sale_date.asc())
        ).all()
    )

    payment_records = list(
        db.scalars(
            select(LivestockSalePayment)
            .join(LivestockSale, LivestockSale.id == LivestockSalePayment.sale_id)
            .where(
                LivestockSalePayment.payment_date >= start_date,
                LivestockSalePayment.payment_date <= end_date,
                LivestockSale.is_voided == False,
            )
            .order_by(LivestockSalePayment.payment_date.asc())
        ).all()
    )

    month_keys: list[str] = []
    cursor = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)
    while cursor <= last:
        month_keys.append(_month_key(cursor))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    monthly_crop_yield = defaultdict(float)
    crop_yield_by_name = defaultdict(float)
    monthly_weather: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"rainfall": [], "temperature": [], "humidity": []}
    )
    monthly_feed = defaultdict(float)
    monthly_growth_gain: dict[str, list[float]] = defaultdict(list)
    monthly_production: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    monthly_sales_value = defaultdict(float)
    monthly_crop_sales_value = defaultdict(float)
    monthly_livestock_sales_value = defaultdict(float)
    monthly_cash_collected = defaultdict(float)
    monthly_reproduction_events = defaultdict(int)
    monthly_offspring = defaultdict(int)
    monthly_alive_offspring = defaultdict(int)
    output_units: dict[str, str] = {}

    for record in crop_yields:
        key = _month_key(record.harvest_date)
        quantity = float(record.quantity_kg or 0)
        monthly_crop_yield[key] += quantity
        crop = crop_by_id.get(record.crop_id)
        crop_yield_by_name[crop.name if crop else "Unknown Crop"] += quantity

    for record in weather:
        key = _month_key(record.recorded_date)
        monthly_weather[key]["rainfall"].append(float(record.rainfall_mm or 0))
        monthly_weather[key]["temperature"].append(float(record.temperature_c or 0))
        monthly_weather[key]["humidity"].append(float(record.humidity_percent or 0))

    for record in feeding_records:
        monthly_feed[_month_key(record.feeding_date)] += float(record.actual_quantity_kg or 0)

    for record in growth_records:
        if record.average_daily_gain_kg is not None:
            monthly_growth_gain[_month_key(record.measurement_date)].append(
                float(record.average_daily_gain_kg)
            )

    for record in production_records:
        key = _month_key(record.record_date)
        output = str(record.output_type or "Other").strip() or "Other"
        unit = str(record.unit or "").strip()
        series_name = f"{output} ({unit})" if unit else output
        monthly_production[key][series_name] += float(record.quantity or 0)
        output_units[series_name] = unit

    for record in reproduction_records:
        key = _month_key(record.event_date)
        monthly_reproduction_events[key] += 1
        monthly_offspring[key] += int(record.offspring_count or 0)
        monthly_alive_offspring[key] += int(record.alive_offspring or 0)

    for record in sales_records:
        key = _month_key(record.sale_date)
        gross = float(record.total_amount or 0)
        monthly_sales_value[key] += gross
        if str(record.source_type or "").strip().lower() == "crop":
            monthly_crop_sales_value[key] += gross
        else:
            monthly_livestock_sales_value[key] += gross

    for payment in payment_records:
        monthly_cash_collected[_month_key(payment.payment_date)] += float(payment.amount or 0)

    monthly = []
    for key in month_keys:
        weather_bucket = monthly_weather[key]
        growth_values = monthly_growth_gain[key]
        year, month = (int(part) for part in key.split("-"))
        monthly.append(
            {
                "month": key,
                "label": _month_label(key),
                "season": _season(month),
                "crop_yield_kg": round(monthly_crop_yield[key], 2),
                "feed_consumption_kg": round(monthly_feed[key], 3),
                "average_daily_gain_kg": (
                    round(mean(growth_values), 4) if growth_values else None
                ),
                "average_rainfall_mm": (
                    round(mean(weather_bucket["rainfall"]), 2)
                    if weather_bucket["rainfall"]
                    else None
                ),
                "average_temperature_c": (
                    round(mean(weather_bucket["temperature"]), 2)
                    if weather_bucket["temperature"]
                    else None
                ),
                "average_humidity_percent": (
                    round(mean(weather_bucket["humidity"]), 1)
                    if weather_bucket["humidity"]
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

    health_distribution = defaultdict(int)
    for record in livestock:
        if record.is_archived:
            continue
        health_distribution[str(record.health_status or "Unknown")] += int(record.quantity or 0)

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

    reproduction_events = len(reproduction_records)
    breeder_females = sum(int(record.breeder_female_quantity or 0) for record in reproduction_records)
    confirmed_pregnant = sum(int(record.confirmed_pregnant_quantity or 0) for record in reproduction_records)
    eggs_set = sum(int(record.eggs_set or 0) for record in reproduction_records)
    fertile_eggs = sum(int(record.fertile_eggs or 0) for record in reproduction_records)
    offspring_recorded = sum(int(record.offspring_count or 0) for record in reproduction_records)
    alive_offspring = sum(int(record.alive_offspring or 0) for record in reproduction_records)
    reproduction_losses = sum(int(record.loss_count or 0) for record in reproduction_records)
    birth_hatch_events = sum(
        1
        for record in reproduction_records
        if str(record.record_type or "").strip().lower()
        in {"birth", "hatch", "farrowing", "kidding", "calving"}
    )
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
            measurement_count = len(ordered) + 1
        else:
            start_weight = float(first.weight_kg or 0)
            growth_start_date = first.measurement_date
            measurement_count = len(ordered)

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
            "crop_yield_records": len(crop_yields),
            "weather_records": len(weather),
            "livestock_growth_records": len(growth_records),
            "feeding_records": len(feeding_records),
            "livestock_production_records": len(production_records),
            "reproduction_records": len(reproduction_records),
            "sales_records": len(sales_records),
            "payment_records": len(payment_records),
            "crop_sales_records": sum(1 for record in sales_records if str(record.source_type or "").strip().lower() == "crop"),
            "livestock_sales_records": sum(1 for record in sales_records if str(record.source_type or "").strip().lower() != "crop"),
            "voided_production_records_excluded": max(
                0, production_records_before_void_filter - len(production_records)
            ),
            "rainfall_yield_pair_months": len(rainfall_pairs),
            "temperature_yield_pair_months": len(temperature_pairs),
            "feed_growth_pair_months": len(feed_growth_pairs),
            "rainfall_yield_months_excluded": max(0, len(monthly) - len(rainfall_pairs)),
            "temperature_yield_months_excluded": max(0, len(monthly) - len(temperature_pairs)),
            "feed_growth_months_excluded": max(0, len(monthly) - len(feed_growth_pairs)),
        },
    }
