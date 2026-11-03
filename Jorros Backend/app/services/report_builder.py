from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Crop,
    CropPestDisease,
    CropYieldRecord,
    InventoryItem,
    InventoryStockRecord,
    ResourceUsage,
    Livestock,
    LivestockVaccinationRecord,
    LivestockReproductionRecord,
    LivestockProductionRecord,
    LivestockGrowthRecord,
    LivestockFeedingRecord,
    LivestockProcessingRecord,
    LivestockSale,
    LivestockSaleItem,
    LivestockSalePayment,
)

from app.services.trend_analytics import build_trend_analysis
from app.services.production_sales_service import production_sold_map
from app.services.crop_report_history import crop_statuses_at_period_end

from app.services.crop_growth import (
    calculate_crop_progress,
    status_for_progress,
)


def _rounded(value: float, digits: int = 2) -> float:
    return round(float(value or 0), digits)


def _available_production_quantity(quantity: Any, sold_quantity: Any) -> float:
    """Return an API-safe float even when SQL aggregates return Decimal."""
    return max(
        0.0,
        float(quantity or 0) - float(sold_quantity or 0),
    )


def _sale_source_clause(source: str):
    normalized = source.strip().lower()
    return or_(
        func.lower(LivestockSale.source_type) == normalized,
        select(LivestockSaleItem.id).where(
            LivestockSaleItem.sale_id == LivestockSale.id,
            func.lower(LivestockSaleItem.source_type) == normalized,
        ).exists(),
    )


def _sale_items_by_sale(db: Session, sales: list[LivestockSale]):
    sale_ids = [sale.id for sale in sales]
    grouped = defaultdict(list)
    if sale_ids:
        for item in db.scalars(
            select(LivestockSaleItem).where(LivestockSaleItem.sale_id.in_(sale_ids))
        ).all():
            grouped[item.sale_id].append(item)
    return grouped


def _sale_source_total(sale: LivestockSale, items_by_sale, source: str) -> float:
    items = items_by_sale.get(sale.id, [])
    if items:
        return sum(
            float(item.line_total or 0)
            for item in items
            if str(item.source_type or "").strip().lower() == source.lower()
        )
    return float(sale.total_amount or 0) if str(sale.source_type or "").strip().lower() == source.lower() else 0.0


def _sale_source_ratio(sale: LivestockSale, items_by_sale, source: str) -> float:
    total = float(sale.total_amount or 0)
    return _sale_source_total(sale, items_by_sale, source) / total if total > 0 else 0.0


def _month_label(value: date) -> str:
    return value.strftime("%Y-%m")


def _counter_rows(counter: Counter) -> list[dict[str, Any]]:
    return [
        {
            "label": str(label),
            "value": int(value),
        }
        for label, value in sorted(
            counter.items(),
            key=lambda item: str(item[0]),
        )
    ]


def _resource_usage_snapshot(
    db: Session,
    *,
    module: str | None,
    target_ids: list[int] | None,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    statement = select(ResourceUsage).where(
        ResourceUsage.is_voided == False,
        ResourceUsage.usage_date >= start_date,
        ResourceUsage.usage_date <= end_date,
    )
    if module:
        statement = statement.where(ResourceUsage.module == module)
    if target_ids is not None:
        if not target_ids:
            usages = []
        elif module == "Crop":
            usages = list(db.scalars(statement.where(ResourceUsage.crop_id.in_(target_ids))).all())
        elif module == "Livestock":
            usages = list(db.scalars(statement.where(ResourceUsage.livestock_id.in_(target_ids))).all())
        else:
            usages = list(db.scalars(statement).all())
    else:
        usages = list(db.scalars(statement).all())

    item_ids = {u.inventory_item_id for u in usages}
    items = {
        item.id: item
        for item in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids))).all()
    } if item_ids else {}

    crop_ids = {u.crop_id for u in usages if u.crop_id is not None}
    livestock_ids = {u.livestock_id for u in usages if u.livestock_id is not None}
    crops = {
        record.id: record
        for record in db.scalars(select(Crop).where(Crop.id.in_(crop_ids))).all()
    } if crop_ids else {}
    livestock = {
        record.id: record
        for record in db.scalars(select(Livestock).where(Livestock.id.in_(livestock_ids))).all()
    } if livestock_ids else {}

    totals = defaultdict(float)
    rows = []
    for usage in usages:
        item = items.get(usage.inventory_item_id)
        totals[(usage.usage_type, usage.unit)] += float(usage.quantity or 0)
        target = crops.get(usage.crop_id) if usage.module == "Crop" else livestock.get(usage.livestock_id)
        if usage.module == "Crop" and target is not None:
            target_name = f"{target.name} ({target.crop_code})"
        elif usage.module == "Livestock" and target is not None:
            target_name = f"{target.record_name} ({target.animal_code})"
        else:
            target_name = "Unknown Record"

        rows.append({
            "usage_id": usage.id,
            "module": usage.module,
            "target_id": usage.crop_id if usage.module == "Crop" else usage.livestock_id,
            "target_name": target_name,
            "usage_type": usage.usage_type,
            "item_code": usage.item_code_snapshot or (item.item_code if item else None),
            "item": usage.item_name_snapshot or (item.name if item else "Unknown Item"),
            "category": usage.category_snapshot or (item.category if item else None),
            "batch_number": usage.batch_number_snapshot,
            "quantity": _rounded(usage.quantity),
            "unit": usage.unit,
            "basis_value": _rounded(usage.basis_value) if usage.basis_value is not None else None,
            "basis_unit": usage.basis_unit,
            "usage_rate": (
                _rounded(float(usage.quantity or 0) / float(usage.basis_value))
                if usage.basis_value is not None and float(usage.basis_value) > 0
                else None
            ),
            "usage_rate_unit": (
                f"{usage.unit}/ha" if usage.basis_unit == "ha"
                else f"{usage.unit}/animal" if usage.basis_unit == "animals"
                else None
            ),
            "usage_date": usage.usage_date.isoformat(),
            "notes": usage.notes,
        })

    return {
        "records": rows,
        "totals": [
            {"usage_type": usage_type, "unit": unit, "quantity": _rounded(quantity)}
            for (usage_type, unit), quantity in sorted(totals.items())
        ],
        "record_count": len(rows),
    }


def _build_crop_snapshot(
    db: Session,
    report_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    crops = list(
        db.scalars(
            select(Crop)
            .where(Crop.planting_date <= end_date)
            .order_by(Crop.name.asc())
        ).all()
    )
    # Archived records still belong to periods before they were archived.
    crops = [
        crop for crop in crops
        if not crop.is_archived or not crop.updated_at or crop.updated_at.date() >= start_date
    ]

    crop_ids = [crop.id for crop in crops]
    period_status = crop_statuses_at_period_end(db, crops, end_date)

    yield_records = []
    pest_records = []

    if crop_ids:
        yield_records = list(
            db.scalars(
                select(CropYieldRecord)
                .where(
                    CropYieldRecord.crop_id.in_(crop_ids),
                    CropYieldRecord.harvest_date >= start_date,
                    CropYieldRecord.harvest_date <= end_date,
                )
                .order_by(CropYieldRecord.harvest_date.asc())
            ).all()
        )

        pest_records = list(
            db.scalars(
                select(CropPestDisease)
                .where(
                    CropPestDisease.crop_id.in_(crop_ids),
                    CropPestDisease.date_detected >= start_date,
                    CropPestDisease.date_detected <= end_date,
                )
                .order_by(CropPestDisease.date_detected.asc())
            ).all()
        )

    resource_usage = _resource_usage_snapshot(
        db,
        module="Crop",
        target_ids=crop_ids,
        start_date=start_date,
        end_date=end_date,
    )

    crop_by_id = {crop.id: crop for crop in crops}

    total_area = sum(
        float(crop.area_hectares or 0)
        for crop in crops
    )
    total_harvest_kg = sum(
        float(record.quantity_kg or 0)
        for record in yield_records
    )
    average_yield = (
        total_harvest_kg / total_area
        if total_area > 0
        else 0
    )

    total_planted = sum(
        int(crop.quantity_planted or 0)
        for crop in crops
    )
    total_surviving = sum(
        int(crop.current_surviving or 0)
        for crop in crops
    )
    plant_loss_count = max(0, total_planted - total_surviving)
    survival_rate_percent = (
        total_surviving / total_planted * 100
        if total_planted > 0
        else 0
    )

    harvest_schedule_variances = []
    for record in yield_records:
        crop = crop_by_id.get(record.crop_id)
        if crop is not None and crop.estimated_harvest is not None:
            harvest_schedule_variances.append(
                (record.harvest_date - crop.estimated_harvest).days
            )
    average_harvest_schedule_variance_days = (
        sum(harvest_schedule_variances) / len(harvest_schedule_variances)
        if harvest_schedule_variances
        else 0
    )

    status_counts = Counter(
        period_status[crop.id]
        for crop in crops
    )

    monthly_harvest = defaultdict(float)
    for record in yield_records:
        monthly_harvest[_month_label(record.harvest_date)] += float(
            record.quantity_kg or 0
        )

    yield_by_crop = defaultdict(float)
    for record in yield_records:
        yield_by_crop[record.crop_id] += float(
            record.quantity_kg or 0
        )

    crop_performance = []
    for crop_id, quantity_kg in yield_by_crop.items():
        crop = crop_by_id.get(crop_id)
        if crop is None:
            continue

        area = float(crop.area_hectares or 0)
        crop_performance.append(
            {
                "crop_id": crop.id,
                "crop_code": crop.crop_code,
                "crop": crop.name,
                "field": crop.field,
                "area_ha": _rounded(area),
                "quantity_planted": int(crop.quantity_planted or 0),
                "current_surviving": int(crop.current_surviving or 0),
                "survival_rate_percent": _rounded(
                    (int(crop.current_surviving or 0) / int(crop.quantity_planted or 0) * 100)
                    if int(crop.quantity_planted or 0) > 0
                    else 0
                ),
                "harvest_kg": _rounded(quantity_kg),
                "yield_kg_per_ha": _rounded(
                    quantity_kg / area
                    if area > 0
                    else 0
                ),
            }
        )

    crop_performance.sort(
        key=lambda item: item["harvest_kg"],
        reverse=True,
    )

    pest_types = Counter(
        record.pest_disease_type
        for record in pest_records
    )
    pest_severity = Counter(
        record.severity or "Not specified"
        for record in pest_records
    )

    growth_rows = []
    for crop in crops:
        historical_status = period_status[crop.id]
        if historical_status == "Harvested":
            progress = 100.0
            crop_status = "Harvested"
        elif historical_status == "Harvesting":
            progress = 100.0
            crop_status = "Harvesting"
        elif historical_status == "Failed":
            progress = float(crop.current_growth or 0)
            crop_status = "Failed"
        else:
            progress = calculate_crop_progress(
                crop.planting_date,
                crop.estimated_harvest,
                today=end_date,
            )
            crop_status = historical_status

        growth_rows.append(
            {
                "crop_id": crop.id,
                "crop_code": crop.crop_code,
                "crop": crop.name,
                "field": crop.field,
                "growth_percent": _rounded(progress),
                "status": crop_status,
                "planting_date": crop.planting_date.isoformat(),
                "estimated_harvest": crop.estimated_harvest.isoformat(),
            }
        )

    crop_sales = list(
        db.scalars(
            select(LivestockSale).where(
                LivestockSale.sale_date >= start_date,
                LivestockSale.sale_date <= end_date,
                LivestockSale.is_voided == False,
                _sale_source_clause("crop"),
            ).order_by(LivestockSale.sale_date.asc())
        ).all()
    )
    crop_items_by_sale = _sale_items_by_sale(db, crop_sales)
    crop_gross_sales = sum(_sale_source_total(record, crop_items_by_sale, "crop") for record in crop_sales)

    # Cash collected follows actual payment dates, while receivables for sales
    # created in this period are reconstructed as of the report period end.
    crop_payment_records = list(
        db.scalars(
            select(LivestockSalePayment)
            .join(LivestockSale, LivestockSale.id == LivestockSalePayment.sale_id)
            .where(
                LivestockSalePayment.payment_date >= start_date,
                LivestockSalePayment.payment_date <= end_date,
                LivestockSale.is_voided == False,
                _sale_source_clause("crop"),
            )
            .order_by(
                LivestockSalePayment.payment_date.asc(),
                LivestockSalePayment.id.asc(),
            )
        ).all()
    )
    crop_sales_by_id = {record.id: record for record in crop_sales}
    crop_cash_collected = sum(
        float(record.amount or 0)
        * _sale_source_ratio(crop_sales_by_id[record.sale_id], crop_items_by_sale, "crop")
        for record in crop_payment_records
        if record.sale_id in crop_sales_by_id
    )

    crop_sale_ids = [record.id for record in crop_sales]
    crop_payments_to_end_by_sale = defaultdict(float)
    if crop_sale_ids:
        crop_payments_to_end = list(
            db.scalars(
                select(LivestockSalePayment)
                .join(LivestockSale, LivestockSale.id == LivestockSalePayment.sale_id)
                .where(
                    LivestockSalePayment.sale_id.in_(crop_sale_ids),
                    LivestockSalePayment.payment_date <= end_date,
                    LivestockSale.is_voided == False,
                    _sale_source_clause("crop"),
                )
            ).all()
        )
        for payment in crop_payments_to_end:
            sale = crop_sales_by_id.get(payment.sale_id)
            if sale is not None:
                crop_payments_to_end_by_sale[payment.sale_id] += float(payment.amount or 0) * _sale_source_ratio(sale, crop_items_by_sale, "crop")

    def crop_sale_payment_as_of_end(record: LivestockSale) -> tuple[float, float, str]:
        gross = _sale_source_total(record, crop_items_by_sale, "crop")
        paid = min(gross, crop_payments_to_end_by_sale.get(record.id, 0.0))
        balance = max(0.0, gross - paid)
        if paid <= 0:
            status_text = "Unpaid"
        elif balance <= 0:
            status_text = "Paid"
        else:
            status_text = "Partial"
        return paid, balance, status_text

    crop_collected_against_period_sales = sum(
        crop_sale_payment_as_of_end(record)[0] for record in crop_sales
    )
    crop_outstanding = sum(
        crop_sale_payment_as_of_end(record)[1] for record in crop_sales
    )
    crop_collection_rate_percent = (
        crop_collected_against_period_sales / crop_gross_sales * 100
        if crop_gross_sales > 0 else 0
    )

    crop_production_records = list(
        db.scalars(
            select(LivestockProductionRecord).where(
                LivestockProductionRecord.record_date >= start_date,
                LivestockProductionRecord.record_date <= end_date,
                func.lower(LivestockProductionRecord.source_type) == "crop",
            )
        ).all()
    )
    crop_production_ids = [record.id for record in crop_production_records]
    crop_sold_by_production = production_sold_map(db, crop_production_ids, through_date=end_date)
    crop_available_kg = sum(
        _available_production_quantity(
            record.quantity,
            crop_sold_by_production.get(record.id),
        )
        for record in crop_production_records
        if record.track_sale_inventory and str(record.unit or "").strip().lower() == "kg"
    )
    active_crops = [crop for crop in crops if period_status[crop.id] not in {"Harvested", "Failed"}]
    completed_crops = [crop for crop in crops if period_status[crop.id] == "Harvested"]

    return {
        "report_type": report_type,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "metrics": {
            "crop_records": len(crops),
            "active_crop_records": len(active_crops),
            "completed_crop_records": len(completed_crops),
            "total_area_ha": _rounded(total_area),
            "harvest_records": len(yield_records),
            "total_harvest_kg": _rounded(total_harvest_kg),
            "average_yield_kg_per_ha": _rounded(average_yield),
            "pest_disease_records": len(pest_records),
            "resource_usage_records": resource_usage["record_count"],
            "quantity_planted": total_planted,
            "current_surviving": total_surviving,
            "plant_loss_count": plant_loss_count,
            "survival_rate_percent": _rounded(survival_rate_percent),
            "average_harvest_schedule_variance_days": _rounded(
                average_harvest_schedule_variance_days
            ),
            "crop_sales_records": len(crop_sales),
            "crop_gross_sales_value": _rounded(crop_gross_sales),
            "crop_cash_collected": _rounded(crop_cash_collected),
            "crop_collected_against_period_sales": _rounded(crop_collected_against_period_sales),
            "crop_collection_rate_percent": _rounded(crop_collection_rate_percent),
            "crop_outstanding_balance": _rounded(crop_outstanding),
            "crop_available_kg": _rounded(crop_available_kg, 3),
        },
        "status_distribution": _counter_rows(status_counts),
        "monthly_harvest": [
            {
                "label": month,
                "value": _rounded(value),
            }
            for month, value in sorted(monthly_harvest.items())
        ],
        "crop_performance": crop_performance,
        "yield_records": [
            {
                "crop": crop_by_id.get(record.crop_id).name
                if crop_by_id.get(record.crop_id)
                else "Unknown Crop",
                "crop_code": crop_by_id.get(record.crop_id).crop_code
                if crop_by_id.get(record.crop_id)
                else None,
                "harvest_date": record.harvest_date.isoformat(),
                "quantity_kg": _rounded(record.quantity_kg),
                "farm_use_quantity_kg": _rounded(getattr(record, "farm_use_quantity_kg", 0) or 0, 3),
                "damaged_quantity_kg": _rounded(getattr(record, "damaged_quantity_kg", 0) or 0, 3),
                "reserved_quantity_kg": _rounded(getattr(record, "reserved_quantity_kg", 0) or 0, 3),
                "sellable_quantity_kg": _rounded(
                    max(
                        0.0,
                        float(record.quantity_kg or 0)
                        - float(getattr(record, "farm_use_quantity_kg", 0) or 0)
                        - float(getattr(record, "damaged_quantity_kg", 0) or 0)
                        - float(getattr(record, "reserved_quantity_kg", 0) or 0),
                    ),
                    3,
                ),
                "yield_kg_per_ha": _rounded(record.yield_per_hectare)
                if record.yield_per_hectare is not None
                else None,
                "quality": record.quality,
                "harvest_type": record.harvest_type,
            }
            for record in yield_records
        ],
        "production_records": [
            {
                "production_id": record.id,
                "crop": crop_by_id.get(record.crop_id).name if crop_by_id.get(record.crop_id) else record.output_type,
                "crop_code": crop_by_id.get(record.crop_id).crop_code if crop_by_id.get(record.crop_id) else None,
                "record_date": record.record_date.isoformat(),
                "gross_quantity": _rounded(getattr(record, "gross_quantity", 0) or 0, 3),
                "farm_use_quantity": _rounded(getattr(record, "farm_use_quantity", 0) or 0, 3),
                "loss_quantity": _rounded(getattr(record, "loss_quantity", 0) or 0, 3),
                "reserved_quantity": _rounded(getattr(record, "reserved_quantity", 0) or 0, 3),
                "sellable_quantity": _rounded(record.quantity, 3),
                "sold_quantity": _rounded(crop_sold_by_production.get(record.id, 0.0), 3),
                "available_quantity": _rounded(
                    _available_production_quantity(
                        record.quantity,
                        crop_sold_by_production.get(record.id),
                    ),
                    3,
                ),
                "unit": record.unit,
                "quality_grade": record.quality_grade,
                "destination": record.destination,
            }
            for record in crop_production_records
        ],
        "sales_records": [
            {
                "sale_code": record.sale_code,
                "crop": crop_by_id.get(record.crop_id).name if crop_by_id.get(record.crop_id) else record.product_type,
                "sale_date": record.sale_date.isoformat(),
                "quantity": _rounded(record.quantity, 3),
                "unit": record.unit,
                "unit_price": _rounded(record.unit_price),
                "total_amount": _rounded(record.total_amount),
                "amount_paid": _rounded(crop_sale_payment_as_of_end(record)[0]),
                "balance_due": _rounded(crop_sale_payment_as_of_end(record)[1]),
                "payment_status": crop_sale_payment_as_of_end(record)[2],
                "buyer_name": record.buyer_name,
            }
            for record in crop_sales
        ],
        "payment_records": [
            {
                "sale_code": next((sale.sale_code for sale in crop_sales if sale.id == record.sale_id), f"Sale #{record.sale_id}"),
                "payment_date": record.payment_date.isoformat(),
                "amount": _rounded(record.amount),
                "payment_method": record.payment_method,
                "notes": record.notes,
            }
            for record in crop_payment_records
        ],
        "growth_records": growth_rows,
        "resource_usage": resource_usage,
        "pest_disease": {
            "types": _counter_rows(pest_types),
            "severity": _counter_rows(pest_severity),
            "records": [
                {
                    "crop": crop_by_id.get(record.crop_id).name
                    if crop_by_id.get(record.crop_id)
                    else "Unknown Crop",
                    "date_detected": record.date_detected.isoformat(),
                    "type": record.pest_disease_type,
                    "severity": record.severity,
                    "affected_area": record.affected_area,
                    "status": record.status,
                }
                for record in pest_records
            ],
        },
    }


def _build_livestock_snapshot(
    db: Session,
    report_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    # Current population metrics use only active records. Period events are queried
    # independently so processed/sold-out batches remain visible in historical reports.
    livestock = list(
        db.scalars(
            select(Livestock)
            .where(Livestock.is_archived == False)
            .order_by(Livestock.record_name.asc())
        ).all()
    )
    active_ids = [record.id for record in livestock]

    vaccinations = list(
        db.scalars(
            select(LivestockVaccinationRecord)
            .where(
                LivestockVaccinationRecord.date_administered >= start_date,
                LivestockVaccinationRecord.date_administered <= end_date,
            )
            .order_by(LivestockVaccinationRecord.date_administered.asc())
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
    growth_records = list(
        db.scalars(
            select(LivestockGrowthRecord)
            .where(
                LivestockGrowthRecord.measurement_date >= start_date,
                LivestockGrowthRecord.measurement_date <= end_date,
            )
            .order_by(
                LivestockGrowthRecord.measurement_date.asc(),
                LivestockGrowthRecord.id.asc(),
            )
        ).all()
    )
    feeding_records = list(
        db.scalars(
            select(LivestockFeedingRecord)
            .where(
                LivestockFeedingRecord.feeding_date >= start_date,
                LivestockFeedingRecord.feeding_date <= end_date,
            )
            .order_by(
                LivestockFeedingRecord.feeding_date.asc(),
                LivestockFeedingRecord.id.asc(),
            )
        ).all()
    )
    voided_processing_production_ids = set(
        db.scalars(
            select(LivestockProcessingRecord.production_record_id).where(
                LivestockProcessingRecord.is_voided == True
            )
        ).all()
    )
    if voided_processing_production_ids:
        production_records = [
            record for record in production_records
            if record.id not in voided_processing_production_ids
        ]
    processing_records = list(
        db.scalars(
            select(LivestockProcessingRecord)
            .where(
                LivestockProcessingRecord.processing_date >= start_date,
                LivestockProcessingRecord.processing_date <= end_date,
                LivestockProcessingRecord.is_voided == False,
            )
            .order_by(LivestockProcessingRecord.processing_date.asc())
        ).all()
    )
    sales_records = list(
        db.scalars(
            select(LivestockSale)
            .where(
                LivestockSale.sale_date >= start_date,
                LivestockSale.sale_date <= end_date,
                LivestockSale.is_voided == False,
                _sale_source_clause("livestock"),
            )
            .order_by(LivestockSale.sale_date.asc())
        ).all()
    )
    livestock_items_by_sale = _sale_items_by_sale(db, sales_records)
    payment_records = list(
        db.scalars(
            select(LivestockSalePayment)
            .join(LivestockSale, LivestockSale.id == LivestockSalePayment.sale_id)
            .where(
                LivestockSalePayment.payment_date >= start_date,
                LivestockSalePayment.payment_date <= end_date,
                LivestockSale.is_voided == False,
                _sale_source_clause("livestock"),
            )
            .order_by(
                LivestockSalePayment.payment_date.asc(),
                LivestockSalePayment.id.asc(),
            )
        ).all()
    )
    payment_sale_ids = {record.sale_id for record in payment_records}
    payment_sale_codes = dict(
        db.execute(
            select(LivestockSale.id, LivestockSale.sale_code).where(
                LivestockSale.id.in_(payment_sale_ids)
            )
        ).all()
    ) if payment_sale_ids else {}

    event_ids = {
        record.livestock_id
        for collection in (
            vaccinations,
            reproduction_records,
            production_records,
            growth_records,
            feeding_records,
            processing_records,
            sales_records,
        )
        for record in collection
        if getattr(record, "livestock_id", None) is not None
    }
    all_livestock_ids = set(active_ids) | event_ids
    livestock_by_id = {
        record.id: record
        for record in db.scalars(
            select(Livestock).where(Livestock.id.in_(all_livestock_ids))
        ).all()
    } if all_livestock_ids else {}

    resource_usage = _resource_usage_snapshot(
        db,
        module="Livestock",
        target_ids=None,
        start_date=start_date,
        end_date=end_date,
    )

    total_head = sum(int(record.quantity or 0) for record in livestock)
    health_counts = Counter()
    growth_counts = Counter()
    type_counts = Counter()
    under_treatment_head = 0
    for record in livestock:
        quantity = int(record.quantity or 0)
        healthy = int(getattr(record, "healthy_quantity", 0) or 0)
        sick = int(getattr(record, "sick_quantity", 0) or 0)
        at_risk = int(getattr(record, "at_risk_quantity", 0) or 0)
        tracked_health = healthy + sick + at_risk
        if tracked_health > 0:
            health_counts["Healthy"] += healthy
            health_counts["Sick"] += sick
            health_counts["At Risk"] += at_risk
            if tracked_health < quantity:
                health_counts["Unspecified"] += quantity - tracked_health
        else:
            health_counts[record.health_status or "Unknown"] += quantity
        under_treatment_head += int(getattr(record, "under_treatment_quantity", 0) or 0)
        growth_counts[record.growth_status] += quantity
        type_counts[record.animal_type] += quantity

    # daily_feed_kg is a per-head requirement.
    total_daily_feed = sum(
        float(record.daily_feed_kg or 0) * int(record.quantity or 0)
        for record in livestock
    )
    average_weight = (
        sum(float(record.weight_kg or 0) for record in livestock) / len(livestock)
        if livestock else 0
    )

    offspring_recorded = sum(
        int(record.offspring_count or 0)
        for record in reproduction_records
        if record.record_type in {"Birth", "Hatch"}
    )
    alive_offspring_recorded = sum(
        int(record.alive_offspring or 0)
        for record in reproduction_records
        if record.record_type in {"Birth", "Hatch"}
    )

    gross_sales = sum(_sale_source_total(record, livestock_items_by_sale, "livestock") for record in sales_records)

    # Cash collection is based on actual payment dates, not the cumulative amount
    # stored on sales. This keeps period reports accurate when a balance is paid later.
    livestock_sales_by_id = {record.id: record for record in sales_records}
    cash_collected = sum(
        float(record.amount or 0)
        * _sale_source_ratio(livestock_sales_by_id[record.sale_id], livestock_items_by_sale, "livestock")
        for record in payment_records
        if record.sale_id in livestock_sales_by_id
    )

    sales_ids = [record.id for record in sales_records]
    payments_to_end_by_sale = defaultdict(float)
    if sales_ids:
        through_end_payments = list(
            db.scalars(
                select(LivestockSalePayment)
                .join(LivestockSale, LivestockSale.id == LivestockSalePayment.sale_id)
                .where(
                    LivestockSalePayment.sale_id.in_(sales_ids),
                    LivestockSalePayment.payment_date <= end_date,
                    LivestockSale.is_voided == False,
                    _sale_source_clause("livestock"),
                )
            ).all()
        )
        for payment in through_end_payments:
            sale = livestock_sales_by_id.get(payment.sale_id)
            if sale is not None:
                payments_to_end_by_sale[payment.sale_id] += float(payment.amount or 0) * _sale_source_ratio(sale, livestock_items_by_sale, "livestock")

    def sale_payment_as_of_end(record: LivestockSale) -> tuple[float, float, str]:
        gross = _sale_source_total(record, livestock_items_by_sale, "livestock")
        paid = min(gross, payments_to_end_by_sale.get(record.id, 0.0))
        balance = max(0.0, gross - paid)
        if paid <= 0:
            status_text = "Unpaid"
        elif balance <= 0:
            status_text = "Paid"
        else:
            status_text = "Partial"
        return paid, balance, status_text

    outstanding_balance = sum(
        sale_payment_as_of_end(record)[1]
        for record in sales_records
    )
    livestock_lines = [item for sale in sales_records for item in livestock_items_by_sale.get(sale.id, []) if str(item.source_type or "").lower() == "livestock"]
    product_sales_quantity = sum(float(item.quantity or 0) for item in livestock_lines if item.item_kind == "Production")
    live_animal_sales = sum(int(float(item.quantity or 0)) for item in livestock_lines if item.item_kind == "Live Animal")
    if not livestock_lines:
        product_sales_quantity = sum(float(record.quantity or 0) for record in sales_records if record.sale_type == "Product")
        live_animal_sales = sum(int(float(record.quantity or 0)) for record in sales_records if record.sale_type == "Live Animal")
    payment_counts = Counter(
        sale_payment_as_of_end(record)[2]
        for record in sales_records
    )

    animals_processed = sum(int(record.animals_processed or 0) for record in processing_records)
    processing_live_weight = sum(float(record.live_weight_kg or 0) for record in processing_records)
    meat_output_kg = sum(float(record.meat_output_kg or 0) for record in processing_records)
    dressing_yield = (
        meat_output_kg / processing_live_weight * 100
        if processing_live_weight > 0 else 0
    )

    production_totals = defaultdict(float)
    egg_production_pcs = 0.0
    egg_capacity = 0.0
    for record in production_records:
        key = (record.output_type, record.unit)
        production_totals[key] += float(record.quantity or 0)
        if str(record.output_type or "").strip().lower() == "eggs":
            egg_production_pcs += float(record.quantity or 0)
            female_count = int(record.source_female_quantity or 0)
            period_start = record.period_start_date or record.record_date
            period_end = record.period_end_date or record.record_date
            production_days = max(1, (period_end - period_start).days + 1)
            egg_capacity += female_count * production_days

    laying_rate_percent = (
        egg_production_pcs / egg_capacity * 100
        if egg_capacity > 0 else 0
    )

    planned_feed_kg = sum(
        float(record.planned_quantity_kg or 0)
        for record in feeding_records
    )
    actual_feed_kg = sum(
        float(record.actual_quantity_kg or 0)
        for record in feeding_records
    )
    feed_variance_kg = actual_feed_kg - planned_feed_kg
    feed_variance_percent = (
        feed_variance_kg / planned_feed_kg * 100
        if planned_feed_kg > 0
        else 0
    )
    feed_adherence_percent = (
        actual_feed_kg / planned_feed_kg * 100
        if planned_feed_kg > 0
        else 0
    )

    # Classify product sales from their authoritative production record so labels
    # such as "Pork" still count as Meat and "Chicken Eggs" still count as Eggs.
    sale_production_ids = {
        item.production_record_id
        for item in livestock_lines
        if item.item_kind == "Production" and item.production_record_id is not None
    }
    sale_production_by_id = {
        record.id: record
        for record in db.scalars(
            select(LivestockProductionRecord).where(
                LivestockProductionRecord.id.in_(sale_production_ids)
            )
        ).all()
    } if sale_production_ids else {}

    def sale_output_type(record) -> str:
        production = sale_production_by_id.get(record.production_record_id)
        if production is not None:
            return str(production.output_type or "").strip().lower()
        return str(record.product_type or "").strip().lower()

    egg_sold_pcs = sum(
        float(record.quantity or 0)
        for record in livestock_lines
        if record.item_kind == "Production"
        and "egg" in sale_output_type(record)
        and str(record.unit or "").strip().lower() in {"pcs", "pc", "piece", "pieces", "eggs"}
    )
    meat_sold_kg = sum(
        float(record.quantity or 0)
        for record in livestock_lines
        if record.item_kind == "Production"
        and "meat" in sale_output_type(record)
        and str(record.unit or "").strip().lower() == "kg"
    )

    # Current sellable balance for production records created in the report period.
    period_production_ids = [r.id for r in production_records if r.track_sale_inventory]
    sold_by_production = production_sold_map(db, period_production_ids, through_date=end_date)

    eggs_available_pcs = 0.0
    meat_available_kg = 0.0
    egg_sale_inventory_pcs = 0.0
    meat_sale_inventory_kg = 0.0
    for record in production_records:
        if not record.track_sale_inventory:
            continue
        quantity = float(record.quantity or 0)
        available = _available_production_quantity(
            quantity,
            sold_by_production.get(record.id),
        )
        output = str(record.output_type or "").lower()
        unit = str(record.unit or "").lower()
        if "egg" in output and unit in {"pcs", "pc", "piece", "pieces", "eggs"}:
            egg_sale_inventory_pcs += quantity
            eggs_available_pcs += available
        if "meat" in output and unit == "kg":
            meat_sale_inventory_kg += quantity
            meat_available_kg += available

    egg_production_sold_pcs = max(0.0, egg_sale_inventory_pcs - eggs_available_pcs)
    meat_production_sold_kg = max(0.0, meat_sale_inventory_kg - meat_available_kg)
    egg_sell_through_percent = (
        egg_production_sold_pcs / egg_sale_inventory_pcs * 100
        if egg_sale_inventory_pcs > 0
        else 0
    )
    meat_sell_through_percent = (
        meat_production_sold_kg / meat_sale_inventory_kg * 100
        if meat_sale_inventory_kg > 0
        else 0
    )

    def animal_name(livestock_id: int) -> str:
        animal = livestock_by_id.get(livestock_id)
        return animal.record_name if animal else "Unknown Livestock"

    collected_against_period_sales = max(0.0, gross_sales - outstanding_balance)
    collection_rate_percent = (
        collected_against_period_sales / gross_sales * 100
        if gross_sales > 0
        else 0
    )
    production_payload = []
    for record in production_records:
        period_start = record.period_start_date or record.record_date
        period_end = record.period_end_date or record.record_date
        days = max(1, (period_end - period_start).days + 1)
        female_count = int(record.source_female_quantity or 0)
        capacity = female_count * days
        laying_rate = (
            float(record.quantity or 0) / capacity * 100
            if str(record.output_type or "").lower() == "eggs" and capacity > 0
            else None
        )
        production_payload.append({
            "livestock": animal_name(record.livestock_id),
            "output_type": record.output_type,
            "record_date": record.record_date.isoformat(),
            "period_start_date": period_start.isoformat(),
            "period_end_date": period_end.isoformat(),
            "production_days": days,
            "source_head_quantity": int(record.source_head_quantity or 0),
            "source_female_quantity": record.source_female_quantity,
            "quantity": _rounded(record.quantity, 3),
            "unit": record.unit,
            "laying_rate_percent": _rounded(laying_rate) if laying_rate is not None else None,
            "quality_grade": record.quality_grade,
            "destination": record.destination,
            "track_sale_inventory": bool(record.track_sale_inventory),
            "available_quantity": _rounded(
                _available_production_quantity(
                    record.quantity,
                    sold_by_production.get(record.id),
                ),
                3,
            ) if record.track_sale_inventory else 0,
            "notes": record.notes,
        })

    return {
        "report_type": report_type,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "metrics": {
            "livestock_records": len(livestock),
            "total_head": total_head,
            "healthy_head": int(health_counts.get("Healthy", 0) or 0),
            "sick_head": int(health_counts.get("Sick", 0) or 0),
            "at_risk_head": int(health_counts.get("At Risk", 0) or 0),
            "under_treatment_head": under_treatment_head,
            "average_record_weight_kg": _rounded(average_weight),
            "daily_feed_kg": _rounded(total_daily_feed),
            "vaccinations_in_period": len(vaccinations),
            "reproduction_records_in_period": len(reproduction_records),
            "offspring_recorded_in_period": offspring_recorded,
            "alive_offspring_recorded_in_period": alive_offspring_recorded,
            "production_records_in_period": len(production_records),
            "growth_measurements_in_period": len(growth_records),
            "average_daily_gain_kg": _rounded(
                sum(float(record.average_daily_gain_kg or 0) for record in growth_records if record.average_daily_gain_kg is not None)
                / max(1, sum(1 for record in growth_records if record.average_daily_gain_kg is not None)),
                4,
            ),
            "processing_records_in_period": len(processing_records),
            "animals_processed_head": animals_processed,
            "processing_live_weight_kg": _rounded(processing_live_weight, 3),
            "meat_output_kg": _rounded(meat_output_kg, 3),
            "average_dressing_yield_percent": _rounded(dressing_yield),
            "egg_production_pcs": _rounded(egg_production_pcs, 0),
            "average_laying_rate_percent": _rounded(laying_rate_percent),
            "egg_capacity_pcs": _rounded(egg_capacity, 0),
            "laying_capacity_variance_pcs": _rounded(egg_production_pcs - egg_capacity, 0),
            "eggs_available_pcs": _rounded(eggs_available_pcs, 0),
            "meat_available_kg": _rounded(meat_available_kg, 3),
            "egg_production_sold_pcs": _rounded(egg_production_sold_pcs, 0),
            "meat_production_sold_kg": _rounded(meat_production_sold_kg, 3),
            "feeding_records_in_period": len(feeding_records),
            "planned_feed_kg": _rounded(planned_feed_kg, 3),
            "actual_feed_kg": _rounded(actual_feed_kg, 3),
            "feed_variance_kg": _rounded(feed_variance_kg, 3),
            "feed_variance_percent": _rounded(feed_variance_percent),
            "feed_adherence_percent": _rounded(feed_adherence_percent),
            "sales_records_in_period": len(sales_records),
            "payment_records_in_period": len(payment_records),
            "gross_sales_value": _rounded(gross_sales),
            "sales_revenue": _rounded(gross_sales),  # compatibility with existing UI/reports
            "cash_collected": _rounded(cash_collected),
            "collected_against_period_sales": _rounded(collected_against_period_sales),
            "collection_rate_percent": _rounded(collection_rate_percent),
            "outstanding_balance": _rounded(outstanding_balance),
            "product_sales_quantity": _rounded(product_sales_quantity),
            "egg_sell_through_percent": _rounded(egg_sell_through_percent),
            "meat_sell_through_percent": _rounded(meat_sell_through_percent),
            "egg_sold_pcs": _rounded(egg_sold_pcs, 0),
            "meat_sold_kg": _rounded(meat_sold_kg, 3),
            "live_animal_sales_head": live_animal_sales,
            "resource_usage_records": resource_usage["record_count"],
        },
        "type_distribution": _counter_rows(type_counts),
        "health_distribution": _counter_rows(health_counts),
        "growth_distribution": _counter_rows(growth_counts),
        "payment_status_distribution": _counter_rows(payment_counts),
        "livestock_records": [
            {
                "livestock_id": record.id,
                "animal_code": record.animal_code,
                "record_name": record.record_name,
                "animal_type": record.animal_type,
                "breed": record.breed,
                "quantity": int(record.quantity or 0),
                "weight_kg": _rounded(record.weight_kg),
                "health_status": record.health_status,
                "healthy_quantity": int(getattr(record, "healthy_quantity", 0) or 0),
                "sick_quantity": int(getattr(record, "sick_quantity", 0) or 0),
                "at_risk_quantity": int(getattr(record, "at_risk_quantity", 0) or 0),
                "under_treatment_quantity": int(getattr(record, "under_treatment_quantity", 0) or 0),
                "health_summary": (
                    f"{int(getattr(record, 'healthy_quantity', 0) or 0)} healthy / "
                    f"{int(getattr(record, 'sick_quantity', 0) or 0)} sick / "
                    f"{int(getattr(record, 'at_risk_quantity', 0) or 0)} at risk"
                    if (
                        int(getattr(record, "healthy_quantity", 0) or 0)
                        + int(getattr(record, "sick_quantity", 0) or 0)
                        + int(getattr(record, "at_risk_quantity", 0) or 0)
                    ) > 0
                    else record.health_status
                ),
                "growth_status": record.growth_status,
                "vaccination_status": record.vaccination_status,
                "next_vaccination": record.next_vaccination.isoformat() if record.next_vaccination else None,
                "daily_feed_kg": _rounded(float(record.daily_feed_kg or 0) * int(record.quantity or 0)),
                "production_output": record.production_output,
            }
            for record in livestock
        ],
        "resource_usage": resource_usage,
        "vaccination_records": [
            {
                "livestock": animal_name(record.livestock_id),
                "vaccine": record.vaccine,
                "date_administered": record.date_administered.isoformat(),
                "next_due": record.next_due.isoformat() if record.next_due else None,
                "status": record.status,
                "administered_by": record.administered_by,
            }
            for record in vaccinations
        ],
        "reproduction_records": [
            {
                "livestock": animal_name(record.livestock_id),
                "record_type": record.record_type,
                "event_date": record.event_date.isoformat(),
                "partner_reference": record.partner_reference,
                "breeding_method": record.breeding_method,
                "breeder_male_quantity": int(getattr(record, "breeder_male_quantity", 0) or 0),
                "breeder_female_quantity": int(getattr(record, "breeder_female_quantity", 0) or 0),
                "confirmed_pregnant_quantity": int(getattr(record, "confirmed_pregnant_quantity", 0) or 0),
                "eggs_set": int(getattr(record, "eggs_set", 0) or 0),
                "fertile_eggs": int(getattr(record, "fertile_eggs", 0) or 0),
                "incubation_method": getattr(record, "incubation_method", None),
                "reproductive_status": record.reproductive_status,
                "expected_date": record.expected_date.isoformat() if record.expected_date else None,
                "actual_date": record.actual_date.isoformat() if record.actual_date else None,
                "offspring_count": int(record.offspring_count or 0),
                "alive_offspring": int(record.alive_offspring or 0),
                "male_offspring": record.male_offspring,
                "female_offspring": record.female_offspring,
                "loss_count": int(record.loss_count or 0),
                "notes": record.notes,
            }
            for record in reproduction_records
        ],
        "growth_records": [
            {
                "livestock": animal_name(record.livestock_id),
                "measurement_date": record.measurement_date.isoformat(),
                "weight_kg": _rounded(record.weight_kg),
                "animals_measured": getattr(record, "animals_measured", None),
                "total_measured_weight_kg": (
                    _rounded(getattr(record, "total_measured_weight_kg", None), 3)
                    if getattr(record, "total_measured_weight_kg", None) is not None
                    else None
                ),
                "min_weight_kg": (
                    _rounded(getattr(record, "min_weight_kg", None))
                    if getattr(record, "min_weight_kg", None) is not None
                    else None
                ),
                "max_weight_kg": (
                    _rounded(getattr(record, "max_weight_kg", None))
                    if getattr(record, "max_weight_kg", None) is not None
                    else None
                ),
                "measurement_basis": getattr(record, "measurement_basis", None),
                "previous_weight_kg": (
                    _rounded(record.previous_weight_kg)
                    if record.previous_weight_kg is not None
                    else None
                ),
                "weight_change_kg": (
                    _rounded(record.weight_change_kg)
                    if record.weight_change_kg is not None
                    else None
                ),
                "days_since_previous": record.days_since_previous,
                "average_daily_gain_kg": (
                    _rounded(record.average_daily_gain_kg, 4)
                    if record.average_daily_gain_kg is not None
                    else None
                ),
                "notes": record.notes,
            }
            for record in growth_records
        ],
        "feeding_records": [
            {
                "livestock": animal_name(record.livestock_id),
                "feeding_date": record.feeding_date.isoformat(),
                "feeding_slot": record.feeding_slot,
                "feed_type": record.feed_type,
                "planned_quantity_kg": _rounded(record.planned_quantity_kg, 3),
                "actual_quantity_kg": _rounded(record.actual_quantity_kg, 3),
                "variance_kg": _rounded(
                    float(record.actual_quantity_kg or 0)
                    - float(record.planned_quantity_kg or 0),
                    3,
                ),
                "variance_percent": _rounded(
                    (
                        (float(record.actual_quantity_kg or 0) - float(record.planned_quantity_kg or 0))
                        / float(record.planned_quantity_kg or 0)
                        * 100
                    )
                    if float(record.planned_quantity_kg or 0) > 0
                    else 0
                ),
                "notes": record.notes,
            }
            for record in feeding_records
        ],
        "production_records": production_payload,
        "processing_records": [
            {
                "livestock": animal_name(record.livestock_id),
                "processing_date": record.processing_date.isoformat(),
                "animals_processed": int(record.animals_processed or 0),
                "male_quantity": int(record.male_quantity or 0),
                "female_quantity": int(record.female_quantity or 0),
                "unknown_quantity": int(record.unknown_quantity or 0),
                "live_weight_kg": _rounded(record.live_weight_kg, 3),
                "meat_output_kg": _rounded(record.meat_output_kg, 3),
                "dressing_yield_percent": _rounded(
                    float(record.meat_output_kg or 0) / float(record.live_weight_kg or 0) * 100
                    if float(record.live_weight_kg or 0) > 0 else 0
                ),
                "quality_grade": record.quality_grade,
                "destination": record.destination,
                "notes": record.notes,
            }
            for record in processing_records
        ],
        "sales_records": [
            {
                "sale_code": record.sale_code,
                "livestock": animal_name(record.livestock_id),
                "sale_type": record.sale_type,
                "sale_date": record.sale_date.isoformat(),
                "product_type": record.product_type,
                "quantity": _rounded(record.quantity, 3),
                "unit": record.unit,
                "unit_price": _rounded(record.unit_price),
                "total_amount": _rounded(record.total_amount),
                "amount_paid": _rounded(sale_payment_as_of_end(record)[0]),
                "balance_due": _rounded(sale_payment_as_of_end(record)[1]),
                "buyer_name": record.buyer_name,
                "payment_status": sale_payment_as_of_end(record)[2],
                "payment_method": record.payment_method,
            }
            for record in sales_records
        ],
        "payment_records": [
            {
                "sale_code": payment_sale_codes.get(record.sale_id) or f"Sale #{record.sale_id}",
                "payment_date": record.payment_date.isoformat(),
                "amount": _rounded(record.amount),
                "payment_method": record.payment_method,
                "notes": record.notes,
            }
            for record in payment_records
        ],
        "production_totals": [
            {
                "output_type": output_type,
                "unit": unit,
                "quantity": _rounded(quantity, 3),
            }
            for (output_type, unit), quantity in sorted(
                production_totals.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
            )
        ],
    }


def _build_production_sales_snapshot(
    db: Session,
    report_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Build a farm-output snapshot without mixing incompatible product units.

    Crop harvest/yield records remain the source of crop output. Livestock
    production and processing remain the source of eggs, milk, meat, and live
    animal sales. Sales are combined only for financial metrics.
    """
    crop_snapshot = _build_crop_snapshot(
        db,
        "Crop Production",
        start_date,
        end_date,
    )
    livestock_snapshot = _build_livestock_snapshot(
        db,
        "Livestock Production",
        start_date,
        end_date,
    )

    include_crop = report_type not in {
        "Livestock Production & Sales",
        "Processing Report",
    }
    include_livestock = report_type != "Crop Production & Sales"

    crop = crop_snapshot if include_crop else {}
    livestock = livestock_snapshot if include_livestock else {}
    crop_metrics = crop.get("metrics", {})
    livestock_metrics = livestock.get("metrics", {})

    crop_gross = float(crop_metrics.get("crop_gross_sales_value", 0) or 0)
    livestock_gross = float(livestock_metrics.get("gross_sales_value", 0) or 0)
    crop_cash = float(crop_metrics.get("crop_cash_collected", 0) or 0)
    livestock_cash = float(livestock_metrics.get("cash_collected", 0) or 0)
    crop_period_collected = float(crop_metrics.get("crop_collected_against_period_sales", 0) or 0)
    livestock_period_collected = float(livestock_metrics.get("collected_against_period_sales", 0) or 0)
    crop_outstanding = float(crop_metrics.get("crop_outstanding_balance", 0) or 0)
    livestock_outstanding = float(livestock_metrics.get("outstanding_balance", 0) or 0)
    gross_sales = crop_gross + livestock_gross
    cash_collected = crop_cash + livestock_cash
    outstanding = crop_outstanding + livestock_outstanding

    metrics = {
        "crop_harvest_records": int(crop_metrics.get("harvest_records", 0) or 0),
        "crop_harvest_kg": _rounded(crop_metrics.get("total_harvest_kg", 0) or 0, 3),
        "crop_available_kg": _rounded(crop_metrics.get("crop_available_kg", 0) or 0, 3),
        "crop_sales_records": int(crop_metrics.get("crop_sales_records", 0) or 0),
        "crop_sales_value": _rounded(crop_gross),
        "livestock_production_records": int(livestock_metrics.get("production_records_in_period", 0) or 0),
        "processing_records": int(livestock_metrics.get("processing_records_in_period", 0) or 0),
        "animals_processed_head": int(livestock_metrics.get("animals_processed_head", 0) or 0),
        "egg_production_pcs": _rounded(livestock_metrics.get("egg_production_pcs", 0) or 0, 0),
        "eggs_available_pcs": _rounded(livestock_metrics.get("eggs_available_pcs", 0) or 0, 0),
        "meat_output_kg": _rounded(livestock_metrics.get("meat_output_kg", 0) or 0, 3),
        "meat_available_kg": _rounded(livestock_metrics.get("meat_available_kg", 0) or 0, 3),
        "livestock_sales_records": int(livestock_metrics.get("sales_records_in_period", 0) or 0),
        "livestock_sales_value": _rounded(livestock_gross),
        "live_animal_sales_head": int(livestock_metrics.get("live_animal_sales_head", 0) or 0),
        "gross_sales_value": _rounded(gross_sales),
        "cash_collected": _rounded(cash_collected),
        "collected_against_period_sales": _rounded(crop_period_collected + livestock_period_collected),
        "outstanding_balance": _rounded(outstanding),
        "collection_rate_percent": _rounded((crop_period_collected + livestock_period_collected) / gross_sales * 100 if gross_sales > 0 else 0),
        "sales_records_in_period": int(crop_metrics.get("crop_sales_records", 0) or 0)
        + int(livestock_metrics.get("sales_records_in_period", 0) or 0),
    }

    if not include_crop:
        for key in [
            "crop_harvest_records",
            "crop_harvest_kg",
            "crop_available_kg",
            "crop_sales_records",
            "crop_sales_value",
        ]:
            metrics.pop(key, None)

    if not include_livestock:
        for key in [
            "livestock_production_records",
            "processing_records",
            "animals_processed_head",
            "egg_production_pcs",
            "eggs_available_pcs",
            "meat_output_kg",
            "meat_available_kg",
            "livestock_sales_records",
            "livestock_sales_value",
            "live_animal_sales_head",
        ]:
            metrics.pop(key, None)

    if report_type in {"Sales Summary", "Receivables Report"}:
        for key in [
            "crop_harvest_records", "crop_harvest_kg",
            "livestock_production_records", "processing_records",
            "animals_processed_head", "egg_production_pcs",
            "meat_output_kg",
        ]:
            metrics.pop(key, None)

    if report_type == "Processing Report":
        for key in ["egg_production_pcs", "eggs_available_pcs"]:
            metrics.pop(key, None)

    return {
        "report_type": report_type,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "metrics": metrics,
        "scope": {
            "crop": include_crop,
            "livestock": include_livestock,
        },
        "crop": crop,
        "livestock": livestock,
        "crop_harvest_records": crop.get("yield_records", []),
        "crop_production_records": crop.get("production_records", []),
        "crop_sales_records": crop.get("sales_records", []),
        "livestock_production_records": livestock.get("production_records", []),
        "processing_records": livestock.get("processing_records", []),
        "livestock_sales_records": livestock.get("sales_records", []),
        "payment_records": livestock.get("payment_records", []),
    }

def _build_inventory_snapshot(
    db: Session,
    report_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    inventory = list(
        db.scalars(
            select(InventoryItem)
            .where(InventoryItem.is_archived == False)
            .order_by(InventoryItem.name.asc())
        ).all()
    )

    item_ids = [
        item.id
        for item in inventory
    ]

    movements = []
    if item_ids:
        movements = list(
            db.scalars(
                select(InventoryStockRecord)
                .where(
                    InventoryStockRecord.inventory_item_id.in_(item_ids),
                    InventoryStockRecord.adjustment_date >= start_date,
                    InventoryStockRecord.adjustment_date <= end_date,
                )
                .order_by(InventoryStockRecord.adjustment_date.asc())
            ).all()
        )

    item_by_id = {
        item.id: item
        for item in inventory
    }

    resource_usage = _resource_usage_snapshot(
        db,
        module=None,
        target_ids=None,
        start_date=start_date,
        end_date=end_date,
    )

    low_stock = [
        item
        for item in inventory
        if float(item.quantity or 0)
        <= float(item.reorder_level or 0)
    ]

    expiry_limit = date.today() + timedelta(days=30)
    expiring_stock = [
        item
        for item in inventory
        if float(item.quantity or 0) > 0
        and item.expiration_date is not None
        and item.expiration_date <= expiry_limit
    ]

    total_cost_value = sum(
        float(item.quantity or 0)
        * float(item.cost or 0)
        for item in inventory
    )
    total_retail_value = sum(
        float(item.quantity or 0)
        * float(item.price or 0)
        for item in inventory
    )
    total_reorder_requirement = sum(
        max(0.0, float(item.reorder_level or 0) - float(item.quantity or 0))
        for item in low_stock
    )
    potential_margin_value = max(0.0, total_retail_value - total_cost_value)

    category_counts = Counter(
        item.category
        for item in inventory
    )
    movement_counts = Counter(
        record.adjustment_type
        for record in movements
    )

    usage_quantity = sum(
        float(record.quantity or 0)
        for record in movements
        if record.adjustment_type
        in {
            "Stock Usage",
            "Damaged",
            "Expired",
        }
    )

    restock_quantity = sum(
        float(record.quantity or 0)
        for record in movements
        if record.adjustment_type in {"Restock", "Returned"}
    )

    return {
        "report_type": report_type,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "metrics": {
            "inventory_items": len(inventory),
            "low_stock_items": len(low_stock),
            "expiring_items": len(expiring_stock),
            "stock_movements": len(movements),
            "restock_quantity": _rounded(restock_quantity),
            "usage_quantity": _rounded(usage_quantity),
            "cost_value": _rounded(total_cost_value),
            "retail_value": _rounded(total_retail_value),
            "potential_margin_value": _rounded(potential_margin_value),
            "reorder_shortfall_quantity": _rounded(total_reorder_requirement),
            "resource_usage_records": resource_usage["record_count"],
        },
        "category_distribution": _counter_rows(category_counts),
        "movement_distribution": _counter_rows(movement_counts),
        "inventory_records": [
            {
                "inventory_id": item.id,
                "item_code": item.item_code,
                "name": item.name,
                "category": item.category,
                "batch_number": item.batch_number,
                "quantity": _rounded(item.quantity),
                "unit": item.unit,
                "reorder_level": _rounded(item.reorder_level),
                "cost": _rounded(item.cost),
                "price": _rounded(item.price),
                "supplier": item.supplier,
                "location": item.location,
                "expiration_date": item.expiration_date.isoformat() if item.expiration_date else None,
                "is_low_stock": (
                    float(item.quantity or 0)
                    <= float(item.reorder_level or 0)
                ),
            }
            for item in inventory
        ],
        "low_stock_records": [
            {
                "item_code": item.item_code,
                "name": item.name,
                "quantity": _rounded(item.quantity),
                "unit": item.unit,
                "reorder_level": _rounded(item.reorder_level),
            }
            for item in low_stock
        ],
        "expiring_records": [
            {
                "item_code": item.item_code,
                "name": item.name,
                "batch_number": item.batch_number,
                "quantity": _rounded(item.quantity),
                "unit": item.unit,
                "expiration_date": item.expiration_date.isoformat() if item.expiration_date else None,
            }
            for item in expiring_stock
        ],
        "resource_usage": resource_usage,
        "stock_movements": [
            {
                "item": (
                    item_by_id.get(record.inventory_item_id).name
                    if item_by_id.get(record.inventory_item_id)
                    else "Unknown Item"
                ),
                "adjustment_type": record.adjustment_type,
                "quantity": _rounded(record.quantity),
                "previous_quantity": _rounded(record.previous_quantity),
                "new_quantity": _rounded(record.new_quantity),
                "adjustment_date": record.adjustment_date.isoformat(),
                "reason": record.reason,
            }
            for record in movements
        ],
    }


def _build_farm_snapshot(
    db: Session,
    report_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Build one farm-wide snapshot from the three operational modules.

    Farm Summary is an aggregate report.  Keep each module snapshot intact so
    the PDF/CSV appendices can render the detailed Crop, Livestock and
    Inventory sections, while exposing a small farm-level metrics dictionary
    for the executive summary and period comparison.
    """
    crop = _build_crop_snapshot(
        db,
        "Crop Production",
        start_date,
        end_date,
    )
    livestock = _build_livestock_snapshot(
        db,
        "Livestock Production",
        start_date,
        end_date,
    )
    inventory = _build_inventory_snapshot(
        db,
        "Inventory Summary",
        start_date,
        end_date,
    )

    crop_metrics = crop.get("metrics", {})
    livestock_metrics = livestock.get("metrics", {})
    inventory_metrics = inventory.get("metrics", {})

    return {
        "report_type": report_type,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "metrics": {
            "crop_records": crop_metrics.get("crop_records", 0),
            "total_area_ha": crop_metrics.get("total_area_ha", 0),
            "harvest_records": crop_metrics.get("harvest_records", 0),
            "total_harvest_kg": crop_metrics.get("total_harvest_kg", 0),
            "average_yield_kg_per_ha": crop_metrics.get("average_yield_kg_per_ha", 0),
            "quantity_planted": crop_metrics.get("quantity_planted", 0),
            "current_surviving": crop_metrics.get("current_surviving", 0),
            "survival_rate_percent": crop_metrics.get("survival_rate_percent", 0),
            "pest_disease_records": crop_metrics.get("pest_disease_records", 0),
            "livestock_records": livestock_metrics.get("livestock_records", 0),
            "total_head": livestock_metrics.get("total_head", 0),
            "healthy_head": livestock_metrics.get("healthy_head", 0),
            "sick_head": livestock_metrics.get("sick_head", 0),
            "at_risk_head": livestock_metrics.get("at_risk_head", 0),
            "under_treatment_head": livestock_metrics.get("under_treatment_head", 0),
            "vaccinations_in_period": livestock_metrics.get("vaccinations_in_period", 0),
            "reproduction_records_in_period": livestock_metrics.get("reproduction_records_in_period", 0),
            "offspring_recorded_in_period": livestock_metrics.get("offspring_recorded_in_period", 0),
            "alive_offspring_recorded_in_period": livestock_metrics.get("alive_offspring_recorded_in_period", 0),
            "production_records_in_period": livestock_metrics.get("production_records_in_period", 0),
            "growth_measurements_in_period": livestock_metrics.get("growth_measurements_in_period", 0),
            "average_daily_gain_kg": livestock_metrics.get("average_daily_gain_kg", 0),
            "feeding_records_in_period": livestock_metrics.get("feeding_records_in_period", 0),
            "planned_feed_kg": livestock_metrics.get("planned_feed_kg", 0),
            "actual_feed_kg": livestock_metrics.get("actual_feed_kg", 0),
            "feed_variance_percent": livestock_metrics.get("feed_variance_percent", 0),
            "feed_adherence_percent": livestock_metrics.get("feed_adherence_percent", 0),
            "processing_records_in_period": livestock_metrics.get("processing_records_in_period", 0),
            "animals_processed_head": livestock_metrics.get("animals_processed_head", 0),
            "meat_output_kg": livestock_metrics.get("meat_output_kg", 0),
            "egg_production_pcs": livestock_metrics.get("egg_production_pcs", 0),
            "egg_sell_through_percent": livestock_metrics.get("egg_sell_through_percent", 0),
            "meat_sell_through_percent": livestock_metrics.get("meat_sell_through_percent", 0),
            "gross_sales_value": _rounded(float(livestock_metrics.get("gross_sales_value", 0) or 0) + float(crop_metrics.get("crop_gross_sales_value", 0) or 0)),
            "cash_collected": _rounded(float(livestock_metrics.get("cash_collected", 0) or 0) + float(crop_metrics.get("crop_cash_collected", 0) or 0)),
            "collected_against_period_sales": _rounded(float(livestock_metrics.get("collected_against_period_sales", 0) or 0) + float(crop_metrics.get("crop_collected_against_period_sales", 0) or 0)),
            "collection_rate_percent": _rounded(
                (
                    float(livestock_metrics.get("collected_against_period_sales", 0) or 0)
                    + float(crop_metrics.get("crop_collected_against_period_sales", 0) or 0)
                )
                / max(
                    1.0,
                    float(livestock_metrics.get("gross_sales_value", 0) or 0)
                    + float(crop_metrics.get("crop_gross_sales_value", 0) or 0),
                )
                * 100
            ),
            "outstanding_balance": _rounded(float(livestock_metrics.get("outstanding_balance", 0) or 0) + float(crop_metrics.get("crop_outstanding_balance", 0) or 0)),
            "crop_sales_value": crop_metrics.get("crop_gross_sales_value", 0),
            "livestock_sales_value": livestock_metrics.get("gross_sales_value", 0),
            "crop_available_kg": crop_metrics.get("crop_available_kg", 0),
            "average_laying_rate_percent": livestock_metrics.get("average_laying_rate_percent", 0),
            "average_dressing_yield_percent": livestock_metrics.get("average_dressing_yield_percent", 0),
            "inventory_items": inventory_metrics.get("inventory_items", 0),
            "low_stock_items": inventory_metrics.get("low_stock_items", 0),
            "expiring_items": inventory_metrics.get("expiring_items", 0),
            "stock_movements": inventory_metrics.get("stock_movements", 0),
            "restock_quantity": inventory_metrics.get("restock_quantity", 0),
            "usage_quantity": inventory_metrics.get("usage_quantity", 0),
            "cost_value": inventory_metrics.get("cost_value", 0),
            "retail_value": inventory_metrics.get("retail_value", 0),
            "potential_margin_value": inventory_metrics.get("potential_margin_value", 0),
            "reorder_shortfall_quantity": inventory_metrics.get("reorder_shortfall_quantity", 0),
            "resource_usage_records": (
                int(crop_metrics.get("resource_usage_records", 0) or 0)
                + int(livestock_metrics.get("resource_usage_records", 0) or 0)
            ),
        },
        "trend_analysis": build_trend_analysis(db, start_date, end_date),
        "crop": crop,
        "livestock": livestock,
        "inventory": inventory,
    }


def build_report_snapshot(
    db: Session,
    category: str,
    report_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    if category == "Farm":
        return _build_farm_snapshot(
            db,
            report_type,
            start_date,
            end_date,
        )

    if category == "Crop":
        return _build_crop_snapshot(
            db,
            report_type,
            start_date,
            end_date,
        )

    if category == "Livestock":
        return _build_livestock_snapshot(
            db,
            report_type,
            start_date,
            end_date,
        )

    if category == "Production & Sales":
        return _build_production_sales_snapshot(
            db,
            report_type,
            start_date,
            end_date,
        )

    if category == "Trend & Seasonal":
        return _build_farm_snapshot(
            db,
            report_type,
            start_date,
            end_date,
        )

    if category == "Inventory":
        return _build_inventory_snapshot(
            db,
            report_type,
            start_date,
            end_date,
        )

    raise ValueError("Unsupported report category.")
