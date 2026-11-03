from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_today
from app.models import (
    Crop,
    CropYieldRecord,
    DataImportBatch,
    DataImportRow,
    InventoryItem,
    Livestock,
    LivestockPen,
    LivestockTransaction,
    LivestockGrowthRecord,
    LivestockFeedingRecord,
    LivestockProductionRecord,
    LivestockReproductionRecord,
    LivestockProcessingRecord,
    LivestockSale,
    LivestockVaccinationRecord,
    ResourceUsage,
    User,
)

from app.services.crop_growth import (
    calculate_crop_progress,
    stage_for_progress,
    status_for_progress,
)
from app.services.db_concurrency import (
    SMART_IMPORT_AUTOMATION_GUARD,
    acquire_transaction_lock,
)
from app.services.csv_safety import SafeCsvWriter
from app.schemas.livestock import (
    ALLOWED_GROWTH_STATUSES as LIVESTOCK_GROWTH_STATUSES,
    ALLOWED_HEALTH_STATUSES as LIVESTOCK_HEALTH_STATUSES,
    ALLOWED_VACCINATION_STATUSES as LIVESTOCK_VACCINATION_STATUSES,
)
from app.schemas.production_sales import ProcessingCreate, ProductionCreate, SaleCreate
from app.services.production_sales_service import (
    create_crop_production_from_yield,
    create_processing,
    create_production,
    create_sale,
)
from app.services.task_engine import evaluate_automatic_tasks
from app.services.alert_engine import evaluate_livestock_alerts_only



BACKEND_ROOT = Path(__file__).resolve().parents[2]
IMPORT_DIRECTORY = BACKEND_ROOT / "import_uploads"
MAX_IMPORT_BYTES = 15 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_ARCHIVE_ENTRIES = 5000
MAX_IMPORT_ROWS = 50000
LARGE_IMPORT_THRESHOLD = 100
SUPPORTED_EXTENSIONS = {".xlsx", ".csv", ".json"}
SUPPORTED_TARGETS = {
    "Livestock Pen",
    "Crop",
    "Livestock",
    "Livestock Growth",
    "Livestock Feeding",
    "Resource Usage",
    "Inventory",
    "Crop Yield",
    "Vaccination",
    "Livestock Reproduction",
    "Livestock Production",
    "Livestock Processing",
    "Sales",
}
UNSUPPORTED_TARGETS = {"Report"}


@dataclass(frozen=True)
class FieldSpec:
    label: str
    aliases: tuple[str, ...]
    required: bool = False
    kind: str = "text"


TARGET_FIELDS: dict[str, dict[str, FieldSpec]] = {
    "Livestock Pen": {
        "name": FieldSpec(
            "Pen Name",
            ("name", "pen_name", "pen name", "livestock_pen", "livestock pen"),
            True,
        ),
        "purpose": FieldSpec(
            "Purpose",
            ("purpose", "pen_purpose", "pen purpose", "use", "pen use"),
        ),
        "animal_type": FieldSpec(
            "Animal Type",
            ("animal_type", "animal type", "species", "livestock_type", "livestock type"),
        ),
        "capacity": FieldSpec(
            "Capacity",
            ("capacity", "pen_capacity", "pen capacity", "max_capacity", "maximum capacity"),
            False,
            "int_positive",
        ),
        "location_area": FieldSpec(
            "Location Area",
            ("location_area", "location area", "area", "housing_area", "housing area", "location"),
        ),
        "status": FieldSpec(
            "Status",
            ("status", "pen_status", "pen status"),
        ),
        "notes": FieldSpec(
            "Notes",
            ("notes", "remarks", "comment", "comments"),
        ),
    },
    "Crop": {
        "crop_code": FieldSpec(
            "Crop Code / ID",
            ("crop_code", "crop_id", "crop id", "code", "id"),
        ),
        "name": FieldSpec(
            "Crop Name",
            ("crop", "crop_name", "crop name", "name"),
            True,
        ),
        "variety": FieldSpec("Variety", ("variety", "crop_variety"), True),
        "field": FieldSpec(
            "Field / Location",
            ("field", "field_location", "field location", "plot", "location"),
            True,
        ),
        "area_hectares": FieldSpec(
            "Area (ha)",
            ("area", "area_hectares", "area hectares", "area_ha", "hectares", "ha"),
            True,
            "float_positive",
        ),
        "planting_date": FieldSpec(
            "Planting Date",
            ("planting_date", "planting date", "date_planted", "date planted", "planted_date"),
            True,
            "date",
        ),
        "estimated_harvest": FieldSpec(
            "Estimated Harvest",
            ("estimated_harvest", "estimated harvest", "estimated_harvest_date", "est harvest", "harvest_estimate"),
            True,
            "date",
        ),
        "quantity_planted": FieldSpec(
            "Quantity Planted",
            ("quantity_planted", "quantity planted", "plants planted", "seedlings planted", "initial plant count", "plant count"),
            False,
            "int_nonnegative",
        ),
        "current_surviving": FieldSpec(
            "Current Surviving",
            ("current_surviving", "current surviving", "surviving plants", "survival count", "current plant count", "plants surviving"),
            False,
            "int_nonnegative",
        ),
        "fertilizer_quantity_kg": FieldSpec(
            "Fertilizer Quantity (kg)",
            ("fertilizer_quantity_kg", "fertilizer kg", "fertilizer_quantity", "fertilizer amount", "fertilizer used kg"),
            False,
            "float_nonnegative",
        ),
        "fertilizer_date": FieldSpec(
            "Fertilizer Date",
            ("fertilizer_date", "fertilizer date", "date_fertilized", "fertilizer application date"),
            False,
            "date",
        ),
        "pesticide_used": FieldSpec(
            "Pesticide Used",
            ("pesticide_used", "pesticide used", "pesticide", "pesticide_name"),
        ),
        "watering_schedule": FieldSpec(
            "Watering Schedule",
            ("watering_schedule", "watering schedule", "irrigation_schedule", "irrigation schedule"),
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comment", "comments")),
    },
    "Livestock": {
        "animal_code": FieldSpec(
            "Animal ID / Code",
            ("animal_code", "animal id", "animal_id", "livestock_id", "livestock id", "code", "id"),
        ),
        "record_type": FieldSpec(
            "Record Type",
            ("record_type", "record type", "tracking_type", "tracking type", "individual_or_batch", "individual or batch"),
        ),
        "record_name": FieldSpec(
            "Record Name",
            ("record_name", "record name", "livestock_name", "livestock name", "batch_name", "batch name", "name"),
            True,
        ),
        "animal_type": FieldSpec(
            "Animal Type",
            ("animal_type", "animal type", "type", "livestock_type", "species"),
            True,
        ),
        "breed": FieldSpec("Breed", ("breed", "animal_breed"), True),
        "quantity": FieldSpec(
            "Count / Quantity",
            ("quantity", "count", "animal_count", "number of animals", "no of animals", "population", "head"),
            True,
            "int_positive",
        ),
        "sex": FieldSpec("Sex", ("sex", "gender")),
        "male_quantity": FieldSpec("Male Quantity", ("male_quantity", "male quantity", "male count", "males"), False, "int_nonnegative"),
        "female_quantity": FieldSpec("Female Quantity", ("female_quantity", "female quantity", "female count", "females"), False, "int_nonnegative"),
        "unknown_sex_quantity": FieldSpec("Unknown Sex Quantity", ("unknown_sex_quantity", "unknown sex quantity", "unsexed", "unknown sex"), False, "int_nonnegative"),
        "date_of_birth": FieldSpec(
            "Date of Birth",
            ("date_of_birth", "date of birth", "birth_date", "birth date", "dob", "hatch_date"),
            True,
            "date",
        ),
        "weight_kg": FieldSpec(
            "Average Weight (kg)",
            ("weight_kg", "weight kg", "weight", "average weight", "avg weight", "body_weight", "body weight"),
            True,
            "float_positive",
        ),
        "min_weight_kg": FieldSpec("Minimum Weight (kg)", ("min_weight_kg", "minimum weight", "min weight"), False, "float_positive"),
        "max_weight_kg": FieldSpec("Maximum Weight (kg)", ("max_weight_kg", "maximum weight", "max weight"), False, "float_positive"),
        "pen_location": FieldSpec(
            "Current Pen",
            (
                "current_pen",
                "current pen",
                "pen_location",
                "pen location",
                "pen",
                "housing",
                "location",
            ),
            True,
        ),
        "health_status": FieldSpec(
            "Health Status",
            ("health_status", "health status", "health", "condition"),
        ),
        "healthy_quantity": FieldSpec("Healthy Quantity", ("healthy_quantity", "healthy quantity", "healthy count"), False, "int_nonnegative"),
        "at_risk_quantity": FieldSpec("At Risk Quantity", ("at_risk_quantity", "at risk quantity", "at risk count"), False, "int_nonnegative"),
        "sick_quantity": FieldSpec("Sick Quantity", ("sick_quantity", "sick quantity", "sick count"), False, "int_nonnegative"),
        "under_treatment_quantity": FieldSpec("Under Treatment Quantity", ("under_treatment_quantity", "under treatment quantity", "treatment count"), False, "int_nonnegative"),
        "growth_status": FieldSpec(
            "Growth Status",
            ("growth_status", "growth status", "growth_stage", "growth stage", "stage"),
        ),
        "production_purpose": FieldSpec(
            "Production Purpose",
            ("production_purpose", "production purpose", "purpose", "production use"),
        ),
        "last_checkup": FieldSpec(
            "Last Checkup",
            ("last_checkup", "last checkup", "checkup_date", "health_check_date"),
            False,
            "date",
        ),
        "health_notes": FieldSpec("Health Notes", ("health_notes", "health notes", "medical_notes")),
        "vaccination_status": FieldSpec(
            "Vaccination Status",
            ("vaccination_status", "vaccination status", "vaccine_status"),
        ),
        "next_vaccination": FieldSpec(
            "Next Vaccination",
            ("next_vaccination", "next vaccination", "next_vaccine_date"),
            False,
            "date",
        ),
        "feed_times": FieldSpec(
            "Feeding Times",
            ("feed_times", "feeding_times", "feeding times", "feeding_schedule", "feeding schedule"),
        ),
        "feed_type": FieldSpec("Feed Type", ("feed_type", "feed type", "feed", "feed_name")),
        "daily_feed_kg": FieldSpec(
            "Daily Feed (kg)",
            ("daily_feed_kg", "daily feed kg", "daily_feed", "feed_kg_per_day", "feed per day"),
            False,
            "float_nonnegative",
        ),
        "feeding_notes": FieldSpec("Feeding Notes", ("feeding_notes", "feeding notes", "feed_notes")),
        "date_acquired": FieldSpec(
            "Date Acquired",
            ("date_acquired", "date acquired", "acquired_date", "arrival_date", "date arrived"),
            True,
            "date",
        ),
        "acquired_from": FieldSpec(
            "Acquired From",
            ("acquired_from", "acquired from", "source", "supplier", "origin"),
        ),
    },
    "Livestock Growth": {
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name"),
        ),
        "measurement_date": FieldSpec(
            "Measurement Date",
            ("measurement_date", "measurement date", "weight_date", "weight date", "date"),
            True,
            "date",
        ),
        "weight_kg": FieldSpec(
            "Average Weight (kg)",
            ("weight_kg", "weight kg", "average weight", "average weight kg", "weight"),
            True,
            "float_positive",
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Livestock Feeding": {
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name"),
        ),
        "inventory_item_code": FieldSpec(
            "Inventory Item Code",
            ("inventory_item_code", "inventory item code", "item_code", "feed_item_code"),
        ),
        "inventory_item_name": FieldSpec(
            "Inventory Feed Item",
            ("inventory_item_name", "inventory feed item", "feed_inventory_item", "feed inventory item", "inventory item"),
        ),
        "feeding_date": FieldSpec(
            "Feeding Date",
            ("feeding_date", "feeding date", "feed_date", "date"),
            True,
            "date",
        ),
        "feeding_slot": FieldSpec(
            "Feeding Slot",
            ("feeding_slot", "feeding slot", "feeding_period", "period", "slot"),
            True,
        ),
        "scheduled_times": FieldSpec(
            "Scheduled Times",
            ("scheduled_times", "scheduled times", "feeding_times", "feeding times", "feeding_schedule"),
        ),
        "feed_type": FieldSpec(
            "Feed Type",
            ("feed_type", "feed type", "feed", "feed_name"),
            True,
        ),
        "planned_quantity_kg": FieldSpec(
            "Planned Quantity (kg)",
            ("planned_quantity_kg", "planned quantity kg", "planned feed kg", "planned quantity"),
            False,
            "float_positive",
        ),
        "actual_quantity_kg": FieldSpec(
            "Actual Quantity (kg)",
            ("actual_quantity_kg", "actual quantity kg", "actual feed kg", "feed consumed kg", "quantity kg"),
            True,
            "float_positive",
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Inventory": {
        "item_code": FieldSpec(
            "Item Code / ID",
            ("item_code", "item code", "item_id", "inventory_id", "inventory id", "code", "id"),
        ),
        "name": FieldSpec(
            "Item Name",
            ("name", "item_name", "item name", "inventory_item", "product"),
            True,
        ),
        "category": FieldSpec("Category", ("category", "item_category"), True),
        "batch_number": FieldSpec(
            "Batch / Lot Number",
            ("batch_number", "batch number", "batch", "lot_number", "lot number", "lot"),
        ),
        "quantity": FieldSpec(
            "Quantity",
            ("quantity", "stock", "stock_quantity", "qty", "on_hand", "on hand"),
            True,
            "float_nonnegative",
        ),
        "unit": FieldSpec("Unit", ("unit", "uom", "unit_of_measure"), True),
        "reorder_level": FieldSpec(
            "Reorder Level",
            ("reorder_level", "reorder level", "minimum_stock", "minimum stock", "min_stock"),
            True,
            "float_nonnegative",
        ),
        "cost": FieldSpec("Cost", ("cost", "unit_cost", "purchase_cost"), True, "float_nonnegative"),
        "price": FieldSpec("Price", ("price", "selling_price", "unit_price"), True, "float_nonnegative"),
        "supplier": FieldSpec("Supplier", ("supplier", "vendor", "source"), True),
        "date_acquired": FieldSpec(
            "Date Acquired",
            ("date_acquired", "date acquired", "acquired_date", "purchase_date", "arrival_date"),
            True,
            "date",
        ),
        "expiration_date": FieldSpec(
            "Expiration Date",
            ("expiration_date", "expiration date", "expiry_date", "expiry", "expires"),
            False,
            "date",
        ),
        "location": FieldSpec(
            "Storage Location",
            ("location", "storage_location", "storage location", "warehouse", "stock_location"),
            True,
        ),
        "description": FieldSpec("Description", ("description", "details")),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Crop Yield": {
        "crop_code": FieldSpec(
            "Crop Code",
            ("crop_code", "crop code", "crop_id", "crop id"),
        ),
        "crop_name": FieldSpec(
            "Crop Name",
            ("crop_name", "crop name", "crop", "name"),
        ),
        "field": FieldSpec("Field", ("field", "field_location", "location")),
        "harvest_date": FieldSpec(
            "Harvest Date",
            ("harvest_date", "harvest date", "date_harvested"),
            True,
            "date",
        ),
        "quantity_kg": FieldSpec(
            "Harvest Quantity (kg)",
            ("quantity_kg", "quantity kg", "harvest_quantity", "harvest quantity", "yield", "yield_kg", "harvest_kg"),
            True,
            "float_positive",
        ),
        "quality": FieldSpec("Quality", ("quality", "grade")),
        "harvest_type": FieldSpec("Harvest Type", ("harvest_type", "harvest type", "type")),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Vaccination": {
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name"),
        ),
        "vaccine": FieldSpec("Vaccine", ("vaccine", "vaccine_name", "vaccination"), True),
        "date_administered": FieldSpec(
            "Date Administered",
            ("date_administered", "date administered", "vaccination_date", "vaccine_date", "date"),
            True,
            "date",
        ),
        "next_due": FieldSpec(
            "Next Due",
            ("next_due", "next due", "next_vaccination", "next vaccination"),
            False,
            "date",
        ),
        "status": FieldSpec("Status", ("status", "vaccination_status", "vaccine_status")),
        "administered_by": FieldSpec(
            "Administered By",
            ("administered_by", "administered by", "veterinarian", "vet"),
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Livestock Reproduction": {
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name"),
        ),
        "record_type": FieldSpec(
            "Record Type",
            ("record_type", "record type", "event_type", "event type", "reproduction_type"),
            True,
        ),
        "event_date": FieldSpec(
            "Event Date",
            ("event_date", "event date", "reproduction_date", "breeding_date", "date"),
            True,
            "date",
        ),
        "partner_reference": FieldSpec(
            "Partner / Parent Reference",
            ("partner_reference", "partner reference", "partner", "sire", "dam", "parent_reference"),
        ),
        "breeding_method": FieldSpec(
            "Breeding Method",
            ("breeding_method", "breeding method", "method"),
        ),
        "reproductive_status": FieldSpec(
            "Reproductive Status",
            ("reproductive_status", "reproductive status", "pregnancy_status", "status"),
        ),
        "expected_date": FieldSpec(
            "Expected Birth / Hatch Date",
            ("expected_date", "expected date", "expected_birth", "expected_hatch", "due_date"),
            False,
            "date",
        ),
        "actual_date": FieldSpec(
            "Actual Birth / Hatch Date",
            ("actual_date", "actual date", "actual_birth", "actual_hatch", "birth_date", "hatch_date"),
            False,
            "date",
        ),
        "offspring_count": FieldSpec(
            "Offspring / Hatched",
            ("offspring_count", "offspring", "total_offspring", "hatched", "chicks_hatched"),
            False,
            "int_nonnegative",
        ),
        "alive_offspring": FieldSpec(
            "Alive Offspring",
            ("alive_offspring", "alive offspring", "alive", "live_offspring"),
            False,
            "int_nonnegative",
        ),
        "male_offspring": FieldSpec(
            "Male Offspring",
            ("male_offspring", "male offspring", "male", "males"),
            False,
            "int_nonnegative_optional",
        ),
        "female_offspring": FieldSpec(
            "Female Offspring",
            ("female_offspring", "female offspring", "female", "females"),
            False,
            "int_nonnegative_optional",
        ),
        "loss_count": FieldSpec(
            "Loss / Stillborn / Unhatched",
            ("loss_count", "loss", "losses", "stillborn", "unhatched", "mortality"),
            False,
            "int_nonnegative",
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Livestock Production": {
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name"),
        ),
        "output_type": FieldSpec(
            "Output Type",
            ("output_type", "output type", "production_type", "production type", "product", "type"),
            True,
        ),
        "record_date": FieldSpec(
            "Record Date",
            ("record_date", "record date", "production_date", "output_date", "date"),
            True,
            "date",
        ),
        "period_start_date": FieldSpec(
            "Period Start",
            ("period_start_date", "period start", "production period start", "start date"),
            False,
            "date",
        ),
        "period_end_date": FieldSpec(
            "Period End",
            ("period_end_date", "period end", "production period end", "end date"),
            False,
            "date",
        ),
        "quantity": FieldSpec(
            "Quantity",
            ("quantity", "output_quantity", "production_quantity", "amount"),
            True,
            "float_positive",
        ),
        "unit": FieldSpec("Unit", ("unit", "uom", "unit_of_measure"), True),
        "quality_grade": FieldSpec(
            "Quality / Grade",
            ("quality_grade", "quality grade", "quality", "grade"),
        ),
        "destination_use": FieldSpec(
            "Destination / Use",
            ("destination_use", "destination use", "destination", "use", "purpose"),
        ),
        "track_sale_inventory": FieldSpec(
            "Track as Sale Inventory",
            ("track_sale_inventory", "track sale inventory", "available_for_sale", "available for sale", "sellable", "sale inventory"),
            False,
            "boolean",
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Livestock Processing": {
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name", "livestock"),
        ),
        "processing_date": FieldSpec(
            "Processing Date",
            ("processing_date", "processing date", "slaughter_date", "slaughter date", "date processed", "date"),
            True,
            "date",
        ),
        "animals_processed": FieldSpec(
            "Animals Processed",
            ("animals_processed", "animals processed", "head processed", "quantity processed", "processed head"),
            True,
            "int_positive",
        ),
        "male_quantity": FieldSpec(
            "Male Processed",
            ("male_quantity", "male processed", "males processed"),
            False,
            "int_nonnegative",
        ),
        "female_quantity": FieldSpec(
            "Female Processed",
            ("female_quantity", "female processed", "females processed"),
            False,
            "int_nonnegative",
        ),
        "unknown_quantity": FieldSpec(
            "Unknown Sex Processed",
            ("unknown_quantity", "unknown sex processed", "unknown processed"),
            False,
            "int_nonnegative",
        ),
        "live_weight_kg": FieldSpec(
            "Total Live Weight (kg)",
            ("live_weight_kg", "total live weight kg", "live weight", "live weight kg"),
            False,
            "float_positive",
        ),
        "meat_output_kg": FieldSpec(
            "Meat Output (kg)",
            ("meat_output_kg", "meat output kg", "meat output", "processed meat kg", "carcass weight kg"),
            True,
            "float_positive",
        ),
        "quality_grade": FieldSpec(
            "Quality / Grade",
            ("quality_grade", "quality grade", "quality", "grade"),
        ),
        "destination_use": FieldSpec(
            "Destination / Use",
            ("destination_use", "destination use", "destination", "use", "purpose"),
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Sales": {
        "sale_code": FieldSpec(
            "Sale Code",
            ("sale_code", "sale code", "transaction_code", "transaction code", "sales_id", "sale id"),
        ),
        "sale_type": FieldSpec(
            "Sale Type",
            ("sale_type", "sale type", "transaction_type", "transaction type"),
            True,
        ),
        "animal_code": FieldSpec(
            "Animal Code",
            ("animal_code", "animal code", "animal_id", "animal id", "livestock_id", "livestock id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock_name", "animal_name", "livestock"),
        ),
        "production_record_id": FieldSpec(
            "Production Record ID",
            ("production_record_id", "production record id", "production_id", "production id"),
            False,
            "int_positive",
        ),
        "production_date": FieldSpec(
            "Production Date",
            ("production_date", "production date", "output_date", "output date"),
            False,
            "date",
        ),
        "production_output_type": FieldSpec(
            "Production Output Type",
            ("production_output_type", "production output type", "output_type", "output type", "production type"),
        ),
        "sale_date": FieldSpec(
            "Sale Date",
            ("sale_date", "sale date", "transaction_date", "transaction date", "date sold", "date"),
            True,
            "date",
        ),
        "product_type": FieldSpec(
            "Product / Sale Item",
            ("product_type", "product type", "product", "sale_item", "sale item", "item"),
        ),
        "quantity": FieldSpec(
            "Quantity Sold",
            ("quantity", "quantity_sold", "quantity sold", "sold_quantity", "sold quantity", "qty"),
            True,
            "float_positive",
        ),
        "unit": FieldSpec("Unit", ("unit", "uom", "unit_of_measure"), True),
        "unit_price": FieldSpec(
            "Unit Price",
            ("unit_price", "unit price", "price", "selling_price", "selling price"),
            True,
            "float_nonnegative",
        ),
        "buyer_name": FieldSpec(
            "Buyer / Customer",
            ("buyer_name", "buyer name", "buyer", "customer", "customer_name", "customer name"),
        ),
        "payment_status": FieldSpec(
            "Payment Status",
            ("payment_status", "payment status", "status"),
        ),
        "payment_method": FieldSpec(
            "Payment Method",
            ("payment_method", "payment method", "method"),
        ),
        "amount_paid": FieldSpec(
            "Amount Paid",
            ("amount_paid", "amount paid", "paid amount", "payment amount", "cash received"),
            False,
            "float_nonnegative",
        ),
        "male_quantity": FieldSpec(
            "Male Quantity Sold",
            ("male_quantity", "male quantity", "male sold", "males sold"),
            False,
            "int_nonnegative",
        ),
        "female_quantity": FieldSpec(
            "Female Quantity Sold",
            ("female_quantity", "female quantity", "female sold", "females sold"),
            False,
            "int_nonnegative",
        ),
        "unknown_quantity": FieldSpec(
            "Unknown Sex Quantity Sold",
            ("unknown_quantity", "unknown quantity", "unknown sold", "unknown sex sold"),
            False,
            "int_nonnegative",
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Resource Usage": {
        "module": FieldSpec(
            "Module",
            ("module", "resource module", "target module"),
            True,
        ),
        "crop_code": FieldSpec(
            "Crop Code / ID",
            ("crop_code", "crop code", "crop id", "crop_id"),
        ),
        "crop_name": FieldSpec(
            "Crop Name",
            ("crop_name", "crop name", "crop"),
        ),
        "field": FieldSpec(
            "Field / Location",
            ("field", "field location", "location", "plot"),
        ),
        "animal_code": FieldSpec(
            "Animal ID / Code",
            ("animal_code", "animal code", "animal id", "livestock id", "livestock_id"),
        ),
        "record_name": FieldSpec(
            "Livestock Record Name",
            ("record_name", "record name", "livestock name", "batch name", "animal name"),
        ),
        "inventory_item_code": FieldSpec(
            "Inventory Item Code",
            ("inventory_item_code", "inventory item code", "item code", "inventory code"),
        ),
        "inventory_item_name": FieldSpec(
            "Inventory Item Name",
            ("inventory_item_name", "inventory item name", "item name", "resource item", "resource name"),
        ),
        "usage_type": FieldSpec(
            "Usage Type",
            ("usage_type", "usage type", "resource type", "type"),
            True,
        ),
        "quantity": FieldSpec(
            "Quantity Used",
            ("quantity", "quantity used", "usage quantity", "amount used"),
            True,
            "float_positive",
        ),
        "usage_date": FieldSpec(
            "Usage Date",
            ("usage_date", "usage date", "date used", "application date", "date"),
            True,
            "date",
        ),
        "notes": FieldSpec("Notes", ("notes", "remarks", "comments")),
    },
    "Report": {
        "report_code": FieldSpec("Report Code", ("report_code", "report code", "report_id")),
        "title": FieldSpec("Title", ("title", "report_title", "report title"), True),
        "report_type": FieldSpec("Report Type", ("report_type", "report type"), True),
        "start_date": FieldSpec("Start Date", ("start_date", "start date"), False, "date"),
        "end_date": FieldSpec("End Date", ("end_date", "end date"), False, "date"),
        "prepared_by": FieldSpec("Prepared By", ("prepared_by", "prepared by", "author")),
        "summary": FieldSpec("Summary", ("summary", "executive_summary", "remarks")),
    },
}


SHEET_HINTS = {
    "Livestock Pen": ("livestock pens", "livestock pen", "pens", "pen management", "housing pens"),
    "Crop": ("crop", "planting"),
    "Livestock": ("livestock", "animal", "herd", "flock"),
    "Livestock Growth": ("livestock growth", "growth history", "weight history", "weight measurement"),
    "Livestock Feeding": ("livestock feeding", "feeding history", "feed consumption", "feeding record"),
    "Resource Usage": ("resource usage", "resource utilization", "fertilizer usage", "pesticide usage", "input usage"),
    "Inventory": ("inventory", "stock", "supplies"),
    "Crop Yield": ("yield", "harvest"),
    "Vaccination": ("vaccination", "vaccine", "immunization"),
    "Livestock Reproduction": ("reproduction", "breeding", "birth", "hatch", "pregnancy"),
    "Livestock Production": ("production", "output", "egg", "milk"),
    "Livestock Processing": ("processing", "processed", "slaughter", "slaughtered", "meat output", "carcass"),
    "Sales": ("sale", "sales", "sold", "buyer", "customer", "revenue", "payment"),
    "Report": ("report", "summary"),
}

# Workbook tabs with these names are usually helpers, not farm records.
UTILITY_SHEET_HINTS = (
    "instruction", "instructions", "guide", "read me", "readme",
    "dashboard", "chart", "charts", "summary", "cover", "template",
)



MASTER_TARGETS = {"Livestock Pen"}
BASE_TARGETS = {"Crop", "Livestock", "Inventory"}
ROOT_TARGETS = MASTER_TARGETS | BASE_TARGETS
CHILD_TARGETS = {
    "Crop Yield",
    "Livestock Growth",
    "Livestock Feeding",
    "Resource Usage",
    "Vaccination",
    "Livestock Reproduction",
    "Livestock Production",
    "Livestock Processing",
    "Sales",
}


MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "Livestock Pen": (
        "name", "purpose", "animal_type", "capacity", "location_area",
        "status", "notes", "is_archived",
    ),
    "Crop": (
        "crop_code", "name", "variety", "field", "area_hectares",
        "planting_date", "estimated_harvest", "quantity_planted", "current_surviving",
        "fertilizer_quantity_kg",
        "fertilizer_date", "pesticide_used", "watering_schedule", "notes",
    ),
    "Livestock": (
        "animal_code", "record_type", "record_name", "animal_type", "breed", "quantity", "sex",
        "male_quantity", "female_quantity", "unknown_sex_quantity",
        "date_of_birth", "weight_kg", "min_weight_kg", "max_weight_kg", "pen_location",
        "health_status", "healthy_quantity", "at_risk_quantity", "sick_quantity", "under_treatment_quantity",
        "growth_status", "production_purpose",
        "last_checkup", "health_notes", "vaccination_status", "next_vaccination",
        "feed_times", "feed_type", "daily_feed_kg", "feeding_notes",
        "date_acquired", "acquired_from",
    ),
    "Livestock Growth": (
        "livestock_id", "measurement_date", "weight_kg", "previous_weight_kg",
        "weight_change_kg", "days_since_previous", "average_daily_gain_kg",
        "notes", "recorded_by_user_id",
    ),
    "Livestock Feeding": (
        "livestock_id", "inventory_item_id", "feeding_date", "feeding_slot",
        "scheduled_times", "feed_type", "planned_quantity_kg",
        "actual_quantity_kg", "notes", "recorded_by_user_id",
    ),
    "Resource Usage": (
        "inventory_item_id", "module", "crop_id", "livestock_id", "usage_type",
        "quantity", "unit", "item_code_snapshot", "item_name_snapshot",
        "category_snapshot", "batch_number_snapshot", "basis_value", "basis_unit",
        "usage_date", "notes", "is_voided", "recorded_by_user_id",
    ),
    "Inventory": (
        "item_code", "name", "category", "batch_number", "quantity", "unit", "reorder_level",
        "cost", "price", "supplier", "date_acquired", "expiration_date",
        "location", "description", "notes",
    ),
    "Crop Yield": (
        "crop_id", "harvest_date", "quantity_kg", "quality", "harvest_type", "notes",
    ),
    "Vaccination": (
        "livestock_id", "vaccine", "date_administered", "next_due", "status",
        "administered_by", "notes",
    ),
    "Livestock Reproduction": (
        "livestock_id", "record_type", "event_date", "partner_reference",
        "breeding_method", "reproductive_status", "expected_date", "actual_date",
        "offspring_count", "alive_offspring", "male_offspring", "female_offspring",
        "loss_count", "notes",
    ),
    "Livestock Production": (
        "livestock_id", "output_type", "record_date", "period_start_date", "period_end_date",
        "source_head_quantity", "source_female_quantity", "quantity", "unit",
        "quality_grade", "destination", "track_sale_inventory", "notes",
    ),
    "Livestock Processing": (
        "livestock_id", "production_record_id", "processing_date", "animals_processed",
        "male_quantity", "female_quantity", "unknown_quantity", "healthy_quantity",
        "live_weight_kg", "meat_output_kg", "quality_grade", "destination", "notes", "is_voided",
    ),
    "Sales": (
        "sale_code", "sale_type", "livestock_id", "production_record_id", "sale_date",
        "product_type", "quantity", "unit", "unit_price", "total_amount", "buyer_name",
        "payment_status", "payment_method", "amount_paid", "balance_due",
        "male_quantity", "female_quantity", "unknown_quantity", "healthy_quantity", "notes", "is_voided",
    ),
}


TARGET_MODELS = {
    "Livestock Pen": LivestockPen,
    "Crop": Crop,
    "Livestock": Livestock,
    "Livestock Growth": LivestockGrowthRecord,
    "Livestock Feeding": LivestockFeedingRecord,
    "Resource Usage": ResourceUsage,
    "Inventory": InventoryItem,
    "Crop Yield": CropYieldRecord,
    "Vaccination": LivestockVaccinationRecord,
    "Livestock Reproduction": LivestockReproductionRecord,
    "Livestock Production": LivestockProductionRecord,
    "Livestock Processing": LivestockProcessingRecord,
    "Sales": LivestockSale,
}


ALLOWED_PEN_PURPOSES = {
    "General",
    "Brooder / Nursery",
    "Nursing / Farrowing",
    "Weaner",
    "Growing",
    "Breeding",
    "Pregnancy / Maternity",
    "Layer / Egg Production",
    "Meat / Finisher",
    "Market Ready",
    "Isolation / Sick",
    "Observation",
    "Quarantine",
    "Recovery",
}
ALLOWED_PEN_STATUSES = {"Active", "Maintenance", "Inactive", "Closed"}
ALLOWED_PEN_ANIMAL_TYPES = {"Pig", "Goat", "Chicken", "Duck", "Cattle", "All Livestock"}

ALLOWED_HEALTH_STATUSES = set(LIVESTOCK_HEALTH_STATUSES)
ALLOWED_GROWTH_STATUSES = set(LIVESTOCK_GROWTH_STATUSES)
ALLOWED_VACCINATION_STATUSES = set(LIVESTOCK_VACCINATION_STATUSES)
ALLOWED_LIVESTOCK_RECORD_TYPES = {"Batch"}
ALLOWED_REPRO_TYPES = {"Breeding", "Pregnancy Check", "Birth", "Egg Setting", "Hatch"}
ALLOWED_PRODUCTION_TYPES = {"Eggs", "Milk", "Manure", "Offspring", "Other"}
ALLOWED_SALE_TYPES = {"Product", "Live Animal"}
ALLOWED_PAYMENT_STATUSES = {"Paid", "Partial", "Unpaid"}
ALLOWED_RESOURCE_MODULES = {"Crop", "Livestock"}
ALLOWED_CROP_USAGE_TYPES = {"Fertilizer", "Pesticide", "Herbicide", "Other"}
ALLOWED_LIVESTOCK_USAGE_TYPES = {"Feed", "Medicine", "Vitamin", "Vaccine", "Other"}


def _json_load(value: str | None, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def normalize_header(value: Any) -> str:
    text_value = _clean_text(value).lower()
    text_value = text_value.replace("&", " and ")
    text_value = re.sub(r"[^a-z0-9]+", "_", text_value)
    return text_value.strip("_")


def _normalize_compare(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean_text(value).lower()).strip()


def field_catalog() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for target, fields in TARGET_FIELDS.items():
        result[target] = {
            "supported": target in SUPPORTED_TARGETS,
            "fields": [
                {
                    "key": key,
                    "label": spec.label,
                    "required": spec.required,
                    "kind": spec.kind,
                }
                for key, spec in fields.items()
            ],
        }
    return result


def _field_aliases(target: str, key: str) -> set[str]:
    spec = TARGET_FIELDS[target][key]
    aliases = {normalize_header(alias) for alias in spec.aliases}
    aliases.add(normalize_header(key))
    aliases.add(normalize_header(spec.label))
    return aliases


def suggest_mapping(target: str, columns: Iterable[str]) -> dict[str, str | None]:
    columns = [str(column) for column in columns]
    normalized_to_column: dict[str, str] = {}
    for column in columns:
        normalized = normalize_header(column)
        if normalized and normalized not in normalized_to_column:
            normalized_to_column[normalized] = column

    mapping: dict[str, str | None] = {}
    used_columns: set[str] = set()

    for field_key in TARGET_FIELDS[target]:
        selected = None
        for alias in _field_aliases(target, field_key):
            candidate = normalized_to_column.get(alias)
            if candidate and candidate not in used_columns:
                selected = candidate
                used_columns.add(candidate)
                break
        mapping[field_key] = selected

    return mapping


def detect_target(sheet_name: str, columns: list[str]) -> tuple[str, int, dict[str, str | None]]:
    normalized_sheet = normalize_header(sheet_name)
    scores: list[tuple[int, str, dict[str, str | None]]] = []

    for target, fields in TARGET_FIELDS.items():
        mapping = suggest_mapping(target, columns)
        required = [key for key, spec in fields.items() if spec.required]
        optional = [key for key, spec in fields.items() if not spec.required]
        required_matches = sum(1 for key in required if mapping.get(key))
        optional_matches = sum(1 for key in optional if mapping.get(key))

        if required:
            required_score = (required_matches / len(required)) * 70
        else:
            required_score = 0

        signature_score = min(optional_matches + required_matches, 6) / 6 * 25
        hint_score = 0
        for hint in SHEET_HINTS.get(target, ()):
            normalized_hint = normalize_header(hint)
            if normalized_sheet == normalized_hint:
                hint_score = 25
                break
            if normalized_hint and normalized_hint in normalized_sheet:
                hint_score = 18
                break

        # Child datasets often have only a few strong required columns. Give a small
        # bonus when the distinguishing parent/date fields are present.
        if target in CHILD_TARGETS:
            has_parent = bool(mapping.get("animal_code") or mapping.get("record_name") or mapping.get("crop_code") or mapping.get("crop_name"))
            if has_parent:
                hint_score += 8

        score = int(round(min(100, required_score + signature_score + hint_score)))
        scores.append((score, target, mapping))

    scores.sort(key=lambda item: item[0], reverse=True)
    best_score, best_target, best_mapping = scores[0]
    return best_target, best_score, best_mapping


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel serial date fallback for values read outside openpyxl date formatting.
        if 1 <= float(value) <= 100000:
            try:
                return date(1899, 12, 30) + timedelta(days=int(float(value)))
            except (OverflowError, ValueError):
                pass

    text_value = _clean_text(value)
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%b %d %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(text_value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text_value = _clean_text(value).replace(",", "")
    text_value = re.sub(r"[^0-9.+-]", "", text_value)
    if not text_value or text_value in {"+", "-", "."}:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    number = _parse_float(value)
    if number is None or not float(number).is_integer():
        return None
    return int(number)


def _typed_mapped(target: str, mapped: dict[str, Any]) -> dict[str, Any]:
    restored = dict(mapped)
    for field_key, spec in TARGET_FIELDS.get(target, {}).items():
        if spec.kind == "date" and isinstance(restored.get(field_key), str):
            restored[field_key] = _parse_date(restored[field_key])
        elif spec.kind == "boolean" and isinstance(restored.get(field_key), str):
            restored[field_key] = restored[field_key].strip().lower() in {"1", "true", "yes", "y", "on"}
    return restored


def _convert_value(value: Any, kind: str) -> tuple[Any, str | None]:
    if kind == "text":
        return _optional_text(value), None
    if kind == "date":
        if value is None or _clean_text(value) == "":
            return None, None
        parsed = _parse_date(value)
        return (parsed, None) if parsed else (None, "Invalid date value.")
    if kind.startswith("float"):
        if value is None or _clean_text(value) == "":
            return None, None
        parsed = _parse_float(value)
        if parsed is None:
            return None, "Must contain a valid number."
        if kind == "float_positive" and parsed <= 0:
            return None, "Must be greater than zero."
        if kind == "float_nonnegative" and parsed < 0:
            return None, "Cannot be negative."
        return parsed, None
    if kind == "boolean":
        if value is None or _clean_text(value) == "":
            return None, None
        if isinstance(value, bool):
            return value, None
        text_value = _clean_text(value).strip().lower()
        if text_value in {"1", "true", "yes", "y", "on", "available", "sellable"}:
            return True, None
        if text_value in {"0", "false", "no", "n", "off", "historical", "monitoring"}:
            return False, None
        return None, "Use Yes/No, True/False, or 1/0."
    if kind.startswith("int"):
        if value is None or _clean_text(value) == "":
            return None, None
        parsed = _parse_int(value)
        if parsed is None:
            return None, "Must contain a whole number."
        if kind == "int_positive" and parsed <= 0:
            return None, "Must be at least 1."
        if kind in {"int_nonnegative", "int_nonnegative_optional"} and parsed < 0:
            return None, "Cannot be negative."
        return parsed, None
    return value, None


def map_and_validate_row(
    target: str,
    source: dict[str, Any],
    mapping: dict[str, str | None],
) -> tuple[dict[str, Any], list[str], list[str]]:
    mapped: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for field_key, spec in TARGET_FIELDS[target].items():
        source_column = mapping.get(field_key)
        raw_value = source.get(source_column) if source_column else None
        converted, conversion_error = _convert_value(raw_value, spec.kind)

        if conversion_error:
            errors.append(f"{spec.label}: {conversion_error}")
        if spec.required and (converted is None or converted == ""):
            errors.append(f"{spec.label} is required.")
        mapped[field_key] = converted

    if target == "Livestock Pen":
        mapped["name"] = (_optional_text(mapped.get("name")) or "").strip()
        mapped["purpose"] = (_optional_text(mapped.get("purpose")) or "General").strip()
        mapped["animal_type"] = _optional_text(mapped.get("animal_type"))
        mapped["location_area"] = _optional_text(mapped.get("location_area"))
        mapped["status"] = (_optional_text(mapped.get("status")) or "Active").strip()
        mapped["notes"] = _optional_text(mapped.get("notes"))

        if mapped["purpose"] not in ALLOWED_PEN_PURPOSES:
            errors.append("Purpose is not one of the supported Livestock Pen purposes.")
        if mapped["status"] not in ALLOWED_PEN_STATUSES:
            errors.append("Status is not one of the supported Livestock Pen statuses.")
        if mapped.get("animal_type") and mapped["animal_type"] not in ALLOWED_PEN_ANIMAL_TYPES:
            errors.append("Animal Type is not supported for Livestock Pens.")

    elif target == "Crop":
        if mapped.get("estimated_harvest") and mapped.get("planting_date"):
            if mapped["estimated_harvest"] < mapped["planting_date"]:
                errors.append("Estimated Harvest cannot be earlier than Planting Date.")
        if mapped.get("fertilizer_date") and mapped.get("planting_date"):
            if mapped["fertilizer_date"] < mapped["planting_date"]:
                warnings.append("Fertilizer Date is earlier than Planting Date. Review this row.")

        planted = int(mapped.get("quantity_planted") or 0)
        surviving = mapped.get("current_surviving")
        # Match the normal Crop Create behavior: if the user supplies a planted
        # quantity but leaves Current Surviving blank, the baseline assumes all
        # planted units are currently surviving. Zero remains valid for legacy
        # records that do not track plant counts.
        if surviving is None:
            surviving = planted
        surviving = int(surviving or 0)
        mapped["quantity_planted"] = planted
        mapped["current_surviving"] = surviving
        if planted and surviving > planted:
            errors.append("Current Surviving cannot exceed Quantity Planted.")

    elif target == "Livestock":
        # Smart Import uses the same aggregate-only livestock model as the UI.
        # A batch may contain one animal, so no separate individual record type is needed.
        mapped["record_type"] = "Batch"
        quantity = int(mapped.get("quantity") or 0)

        sex_text = (_optional_text(mapped.get("sex")) or "Mixed").strip()
        sex_key = sex_text.lower()
        sex_fields = ("male_quantity", "female_quantity", "unknown_sex_quantity")
        has_sex_breakdown = any(mapped.get(field) is not None for field in sex_fields)
        if not has_sex_breakdown:
            mapped["male_quantity"] = quantity if sex_key == "male" else 0
            mapped["female_quantity"] = quantity if sex_key == "female" else 0
            mapped["unknown_sex_quantity"] = quantity if sex_key not in {"male", "female"} else 0
        else:
            for field in sex_fields:
                mapped[field] = int(mapped.get(field) or 0)

        sex_total = sum(int(mapped.get(field) or 0) for field in sex_fields)
        if sex_total != quantity:
            errors.append(
                f"Sex breakdown must equal Count / Quantity ({quantity}); current total is {sex_total}."
            )
        if mapped.get("male_quantity") == quantity and quantity > 0:
            mapped["sex"] = "Male"
        elif mapped.get("female_quantity") == quantity and quantity > 0:
            mapped["sex"] = "Female"
        else:
            mapped["sex"] = "Mixed"

        health_text = (_optional_text(mapped.get("health_status")) or "Healthy").strip()
        health_fields = (
            "healthy_quantity",
            "at_risk_quantity",
            "sick_quantity",
            "under_treatment_quantity",
        )
        has_health_breakdown = any(mapped.get(field) is not None for field in health_fields)
        if not has_health_breakdown:
            if health_text == "Mixed":
                errors.append(
                    "Mixed Health Status requires Healthy, At Risk, Sick, and/or Under Treatment quantities."
                )
                mapped["healthy_quantity"] = 0
                mapped["at_risk_quantity"] = 0
                mapped["sick_quantity"] = 0
                mapped["under_treatment_quantity"] = 0
            else:
                mapped["healthy_quantity"] = quantity if health_text == "Healthy" else 0
                mapped["at_risk_quantity"] = quantity if health_text == "At Risk" else 0
                mapped["sick_quantity"] = quantity if health_text == "Sick" else 0
                mapped["under_treatment_quantity"] = quantity if health_text == "Under Treatment" else 0
        else:
            for field in health_fields:
                mapped[field] = int(mapped.get(field) or 0)

        health_total = sum(int(mapped.get(field) or 0) for field in health_fields)
        if health_total != quantity:
            errors.append(
                f"Health breakdown must equal Count / Quantity ({quantity}); current total is {health_total}."
            )

        if mapped.get("healthy_quantity") == quantity and quantity > 0:
            mapped["health_status"] = "Healthy"
        elif mapped.get("at_risk_quantity") == quantity and quantity > 0:
            mapped["health_status"] = "At Risk"
        elif mapped.get("sick_quantity") == quantity and quantity > 0:
            mapped["health_status"] = "Sick"
        elif mapped.get("under_treatment_quantity") == quantity and quantity > 0:
            mapped["health_status"] = "Under Treatment"
        else:
            mapped["health_status"] = "Mixed"

        mapped["growth_status"] = mapped.get("growth_status") or "Growing"
        mapped["production_purpose"] = _optional_text(mapped.get("production_purpose")) or "General"
        mapped["vaccination_status"] = mapped.get("vaccination_status") or "Not Vaccinated"
        mapped["daily_feed_kg"] = mapped.get("daily_feed_kg") or 0

        average_weight = mapped.get("weight_kg")
        mapped["min_weight_kg"] = mapped.get("min_weight_kg") or average_weight
        mapped["max_weight_kg"] = mapped.get("max_weight_kg") or average_weight
        if (
            mapped.get("min_weight_kg") is not None
            and average_weight is not None
            and mapped.get("max_weight_kg") is not None
            and not (mapped["min_weight_kg"] <= average_weight <= mapped["max_weight_kg"])
        ):
            errors.append("Weight values must follow Minimum Weight <= Average Weight <= Maximum Weight.")

        if health_text not in ALLOWED_HEALTH_STATUSES:
            errors.append("Health Status is not one of the supported values.")
        if mapped["growth_status"] not in ALLOWED_GROWTH_STATUSES:
            errors.append("Growth Status is not one of the supported values.")
        if mapped["vaccination_status"] not in ALLOWED_VACCINATION_STATUSES:
            errors.append("Vaccination Status is not one of the supported values.")
        if mapped.get("date_acquired") and mapped.get("date_of_birth"):
            if mapped["date_acquired"] < mapped["date_of_birth"]:
                errors.append("Date Acquired cannot be earlier than Date of Birth.")
        for date_field, label in (("last_checkup", "Last Checkup"), ("next_vaccination", "Next Vaccination")):
            if mapped.get(date_field) and mapped.get("date_of_birth") and mapped[date_field] < mapped["date_of_birth"]:
                errors.append(f"{label} cannot be earlier than Date of Birth.")

    elif target == "Resource Usage":
        module = (_optional_text(mapped.get("module")) or "").title()
        mapped["module"] = module
        if module not in ALLOWED_RESOURCE_MODULES:
            errors.append("Module must be Crop or Livestock.")
        elif module == "Crop":
            if not mapped.get("crop_code") and not mapped.get("crop_name"):
                errors.append("Crop Code or Crop Name is required for crop resource usage.")
            allowed_usage = ALLOWED_CROP_USAGE_TYPES
        else:
            if not mapped.get("animal_code") and not mapped.get("record_name"):
                errors.append("Animal Code or Livestock Record Name is required for livestock resource usage.")
            allowed_usage = ALLOWED_LIVESTOCK_USAGE_TYPES

        if not mapped.get("inventory_item_code") and not mapped.get("inventory_item_name"):
            errors.append("Inventory Item Code or Inventory Item Name is required for resource usage.")
        usage_type = (_optional_text(mapped.get("usage_type")) or "").title()
        mapped["usage_type"] = usage_type
        if module in ALLOWED_RESOURCE_MODULES and usage_type not in allowed_usage:
            errors.append(f"{usage_type or 'Usage Type'} is not valid for {module.lower()} resource usage.")
        if mapped.get("usage_date") and mapped["usage_date"] > farm_today():
            errors.append("Usage Date cannot be in the future.")
        warnings.append(
            "Historical Resource Usage imported by Smart Import does not deduct Inventory again; "
            "the Inventory sheet should contain the current on-hand balance."
        )

    elif target == "Inventory":
        if mapped.get("expiration_date") and mapped.get("date_acquired"):
            if mapped["expiration_date"] < mapped["date_acquired"]:
                errors.append("Expiration Date cannot be earlier than Date Acquired.")

    elif target == "Crop Yield":
        if not mapped.get("crop_code") and not mapped.get("crop_name"):
            errors.append("Crop Code or Crop Name is required to link the yield record.")

    elif target in {"Livestock Growth", "Livestock Feeding", "Vaccination", "Livestock Reproduction", "Livestock Production", "Livestock Processing", "Sales"}:
        if not mapped.get("animal_code") and not mapped.get("record_name"):
            errors.append("Animal Code or Livestock Record Name is required to link this record.")

        if target == "Livestock Growth":
            # Historical weights are linked to a livestock batch. The actual
            # previous/change/day/ADG values are recalculated by the backend.
            pass

        elif target == "Livestock Feeding":
            if not mapped.get("inventory_item_code") and not mapped.get("inventory_item_name"):
                errors.append("Inventory Item Code or Inventory Feed Item is required to link feed consumption.")
            if mapped.get("planned_quantity_kg") is None:
                mapped["planned_quantity_kg"] = mapped.get("actual_quantity_kg")

        elif target == "Vaccination":
            mapped["status"] = mapped.get("status") or "Up to Date"
            if mapped["status"] not in ALLOWED_VACCINATION_STATUSES:
                errors.append("Vaccination Status is not one of the supported values.")
            if mapped.get("next_due") and mapped.get("date_administered") and mapped["next_due"] < mapped["date_administered"]:
                errors.append("Next Due cannot be earlier than Date Administered.")

        elif target == "Livestock Reproduction":
            mapped["offspring_count"] = mapped.get("offspring_count") or 0
            mapped["alive_offspring"] = mapped.get("alive_offspring") or 0
            mapped["loss_count"] = mapped.get("loss_count") or 0
            if mapped.get("record_type") not in ALLOWED_REPRO_TYPES:
                errors.append("Record Type is not supported for livestock reproduction.")
            if mapped["alive_offspring"] > mapped["offspring_count"]:
                errors.append("Alive Offspring cannot exceed total Offspring / Hatched.")
            if mapped["loss_count"] > mapped["offspring_count"]:
                errors.append("Loss Count cannot exceed total Offspring / Hatched.")
            male = mapped.get("male_offspring") or 0
            female = mapped.get("female_offspring") or 0
            if male + female > mapped["alive_offspring"] and mapped["alive_offspring"] > 0:
                errors.append("Male + Female Offspring cannot exceed Alive Offspring.")
            if mapped.get("expected_date") and mapped.get("event_date") and mapped["expected_date"] < mapped["event_date"]:
                warnings.append("Expected Date is earlier than Event Date. Review this row.")

        elif target == "Livestock Production":
            output_type = str(mapped.get("output_type") or "").strip()
            if output_type not in ALLOWED_PRODUCTION_TYPES:
                if "meat" in output_type.lower():
                    errors.append(
                        "Meat output must be imported through Livestock Processing so the source livestock quantity is reduced."
                    )
                else:
                    errors.append("Output Type is not supported for livestock production.")
            if mapped.get("period_start_date") is None:
                mapped["period_start_date"] = mapped.get("record_date")
            if mapped.get("period_end_date") is None:
                mapped["period_end_date"] = mapped.get("record_date")
            if (
                mapped.get("period_start_date")
                and mapped.get("period_end_date")
                and mapped["period_end_date"] < mapped["period_start_date"]
            ):
                errors.append("Period End cannot be earlier than Period Start.")
            if (
                mapped.get("record_date")
                and mapped.get("period_end_date")
                and mapped["record_date"] < mapped["period_end_date"]
            ):
                errors.append("Record Date cannot be earlier than Period End.")
            if mapped.get("track_sale_inventory") is None:
                mapped["track_sale_inventory"] = False

        elif target == "Livestock Processing":
            mapped["male_quantity"] = int(mapped.get("male_quantity") or 0)
            mapped["female_quantity"] = int(mapped.get("female_quantity") or 0)
            mapped["unknown_quantity"] = int(mapped.get("unknown_quantity") or 0)
            sex_total = mapped["male_quantity"] + mapped["female_quantity"] + mapped["unknown_quantity"]
            if mapped.get("animals_processed") is None and sex_total > 0:
                mapped["animals_processed"] = sex_total
                errors = [error for error in errors if not error.startswith("Animals Processed")]
                warnings.append(
                    "Animals Processed was derived from Male + Female + Unknown Processed."
                )
            processed = int(mapped.get("animals_processed") or 0)
            if sex_total not in {0, processed}:
                errors.append(
                    "Male + Female + Unknown Processed must equal Animals Processed, or all three may be left at zero."
                )
            if (
                mapped.get("live_weight_kg") is not None
                and mapped.get("meat_output_kg") is not None
                and mapped["meat_output_kg"] > mapped["live_weight_kg"]
            ):
                errors.append("Meat Output cannot exceed Total Live Weight.")

    elif target == "Sales":
        if not mapped.get("animal_code") and not mapped.get("record_name"):
            errors.append("Animal Code or Livestock Record Name is required to link this sale.")
        sale_type = str(mapped.get("sale_type") or "").strip().title()
        mapped["sale_type"] = sale_type
        if sale_type not in ALLOWED_SALE_TYPES:
            errors.append("Sale Type must be Product or Live Animal.")
        mapped["payment_status"] = str(mapped.get("payment_status") or "Paid").strip().title()
        if mapped["payment_status"] not in ALLOWED_PAYMENT_STATUSES:
            errors.append("Payment Status must be Paid, Partial, or Unpaid.")
        if mapped["payment_status"] == "Partial" and mapped.get("amount_paid") is None:
            errors.append("Amount Paid is required when Payment Status is Partial.")
        if mapped["payment_status"] == "Unpaid" and float(mapped.get("amount_paid") or 0) > 0:
            errors.append("Amount Paid must be 0 for an Unpaid sale.")
        mapped["male_quantity"] = int(mapped.get("male_quantity") or 0)
        mapped["female_quantity"] = int(mapped.get("female_quantity") or 0)
        mapped["unknown_quantity"] = int(mapped.get("unknown_quantity") or 0)
        if sale_type == "Product":
            if not mapped.get("production_record_id") and not (mapped.get("production_date") and mapped.get("production_output_type")):
                errors.append("Product sales require Production Record ID, or both Production Date and Production Output Type.")
        elif sale_type == "Live Animal":
            if not mapped.get("product_type"):
                errors.append("Product / Sale Item is required for a Live Animal sale.")
            quantity = mapped.get("quantity") or 0
            if float(quantity).is_integer() is False:
                errors.append("Live-animal sale quantity must be a whole number.")
            sex_total = mapped["male_quantity"] + mapped["female_quantity"] + mapped["unknown_quantity"]
            if sex_total not in {0, int(quantity) if float(quantity).is_integer() else -1}:
                errors.append("Male + Female + Unknown quantities must total the live animals sold, or all be left at zero.")

    elif target == "Report":
        errors.append(
            "Report-shaped data was detected. Reports are not imported as operational farm records; use the Reports module to generate official system reports."
        )

    # Deduplicate repeated errors caused by both conversion and required checks.
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    return mapped, errors, warnings


def _rows_from_matrix(matrix: list[list[Any]]) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    if not matrix:
        return [], []

    # Prefer the early row that looks most like farm-data headers. This
    # handles workbooks that place a title, farm name, or report heading above
    # the real columns on each worksheet.
    known_headers: set[str] = set()
    for target, fields in TARGET_FIELDS.items():
        for field_key in fields:
            known_headers.update(_field_aliases(target, field_key))

    candidates = []
    for index, row in enumerate(matrix[:30]):
        normalized_cells = [normalize_header(cell) for cell in row if _clean_text(cell)]
        non_empty = len(normalized_cells)
        if not non_empty:
            continue
        recognized = sum(1 for cell in normalized_cells if cell in known_headers)
        # Recognized headers matter more than a decorative row with many cells.
        candidates.append((recognized, non_empty, -index, index))

    if not candidates:
        return [], []

    header_index = max(candidates)[3]

    raw_headers = matrix[header_index]
    headers: list[str] = []
    seen: Counter[str] = Counter()
    for index, header in enumerate(raw_headers, start=1):
        label = _clean_text(header) or f"Column {index}"
        seen[label] += 1
        if seen[label] > 1:
            label = f"{label} ({seen[label]})"
        headers.append(label)

    rows: list[tuple[int, dict[str, Any]]] = []
    for matrix_index, row in enumerate(matrix[header_index + 1 :], start=header_index + 2):
        values = list(row) + [None] * max(0, len(headers) - len(row))
        record = {headers[index]: values[index] if index < len(values) else None for index in range(len(headers))}
        if not any(_clean_text(value) for value in record.values()):
            continue
        rows.append((matrix_index, record))
    return headers, rows


def _validate_xlsx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_XLSX_ARCHIVE_ENTRIES:
                raise ValueError(
                    "The XLSX file contains too many internal archive entries."
                )
            uncompressed_size = sum(max(int(item.file_size or 0), 0) for item in entries)
            if uncompressed_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise ValueError(
                    "The XLSX file expands beyond the 100 MB safety limit."
                )
    except zipfile.BadZipFile as exc:
        raise ValueError("The XLSX file is damaged or is not a valid Excel workbook.") from exc


def _validate_import_row_count(sheets: list[dict[str, Any]]) -> None:
    total_rows = sum(len(sheet.get("rows") or []) for sheet in sheets)
    if total_rows > MAX_IMPORT_ROWS:
        raise ValueError(
            f"The import contains {total_rows:,} rows; the maximum supported import is "
            f"{MAX_IMPORT_ROWS:,} rows."
        )


def _resolve_stored_import_path(batch: DataImportBatch) -> Path:
    root = IMPORT_DIRECTORY.resolve()
    path = Path(batch.stored_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("The stored import file path is invalid.") from exc
    return path


def parse_import_bytes(filename: str, content: bytes) -> list[dict[str, Any]]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only .xlsx, .csv, and .json files are supported for Smart Import.")

    sheets: list[dict[str, Any]] = []

    if extension == ".xlsx":
        _validate_xlsx_archive(content)
        workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        for worksheet in workbook.worksheets:
            matrix = [list(row) for row in worksheet.iter_rows(values_only=True)]
            columns, rows = _rows_from_matrix(matrix)
            if columns and rows:
                sheets.append({"name": worksheet.title, "columns": columns, "rows": rows})
        workbook.close()

    elif extension == ".csv":
        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252"):
            try:
                decoded = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("The CSV text encoding could not be read.")
        # Excel/Windows CSV exports may use comma, semicolon, tab, or pipe.
        sample = decoded[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            reader = csv.reader(io.StringIO(decoded), dialect)
        except csv.Error:
            reader = csv.reader(io.StringIO(decoded))
        matrix = [row for row in reader]
        columns, rows = _rows_from_matrix(matrix)
        if columns and rows:
            sheets.append({"name": "CSV Data", "columns": columns, "rows": rows})

    else:
        try:
            payload = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("The JSON file is not valid JSON data.") from exc

        def object_rows(name: str, value: Any):
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                columns: list[str] = []
                for item in value:
                    for key in item.keys():
                        if str(key) not in columns:
                            columns.append(str(key))
                rows = [(index + 2, {column: item.get(column) for column in columns}) for index, item in enumerate(value)]
                sheets.append({"name": name, "columns": columns, "rows": rows})

        if isinstance(payload, list):
            object_rows("JSON Data", payload)
        elif isinstance(payload, dict):
            added = False
            for key, value in payload.items():
                if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                    object_rows(str(key), value)
                    added = True
            if not added:
                if isinstance(payload.get("data"), list):
                    object_rows("JSON Data", payload["data"])
                elif payload:
                    object_rows("JSON Data", [payload])

    if not sheets:
        raise ValueError("No structured rows were found in the selected file.")
    _validate_import_row_count(sheets)
    return sheets


def generate_batch_code(db: Session) -> str:
    acquire_transaction_lock(db, "code:import-batch")
    today = farm_today().strftime("%Y%m%d")
    prefix = f"IMP-{today}-"
    existing = db.scalars(
        select(DataImportBatch.batch_code).where(DataImportBatch.batch_code.like(f"{prefix}%"))
    ).all()
    highest = 0
    for code in existing:
        try:
            highest = max(highest, int(str(code).rsplit("-", 1)[1]))
        except (IndexError, TypeError, ValueError):
            continue
    return f"{prefix}{highest + 1:04d}"


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_import_file(filename: str, content: bytes, file_hash: str) -> tuple[str, str]:
    IMPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name) or "import_file"
    stored_filename = f"{file_hash[:12]}_{uuid.uuid4().hex[:8]}_{safe_name}"
    path = IMPORT_DIRECTORY / stored_filename
    path.write_bytes(content)
    return stored_filename, str(path)


def _existing_code_set(db: Session, model, column) -> set[str]:
    return {str(value) for value in db.scalars(select(column)).all() if value}


def _reserve_code(existing: set[str], prefix: str) -> str:
    highest = 1000
    pattern = re.compile(r"(\d+)$")
    for code in existing:
        match = pattern.search(str(code))
        if match:
            try:
                highest = max(highest, int(match.group(1)))
            except ValueError:
                pass
    while True:
        highest += 1
        candidate = f"{prefix}-{highest}"
        if candidate not in existing:
            existing.add(candidate)
            return candidate


def _livestock_code_prefix(
    animal_type: str,
    record_type: str,
    breed: str = "",
) -> str:
    combined = f"{animal_type or ''} {breed or ''}".strip().lower()
    normalized = (animal_type or "").strip().lower()
    if "goat" in combined or normalized in {"buck", "doe", "buckling", "doeling"}:
        species = "GOAT"
    elif "duck" in combined or "itik" in combined or normalized == "drake":
        species = "DUCK"
    elif "pig" in combined or "swine" in combined or normalized in {"boar", "sow", "gilt"}:
        species = "PIG"
    elif "chicken" in combined or normalized in {"hen", "rooster", "chick", "pullet"}:
        species = "CHKN"
    elif "cattle" in combined or "cow" in combined or normalized in {"bull", "heifer", "calf"}:
        species = "CATL"
    else:
        species = "ANML"
    return f"{species}-B" if record_type == "Batch" else species


def _reserve_livestock_code(
    existing: set[str],
    animal_type: str,
    record_type: str,
    breed: str = "",
) -> str:
    prefix = _livestock_code_prefix(animal_type, record_type, breed)
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$", re.IGNORECASE)
    for code in existing:
        match = pattern.match(str(code))
        if match:
            highest = max(highest, int(match.group(1)))
    while True:
        highest += 1
        candidate = f"{prefix}-{highest:04d}"
        if candidate not in existing:
            existing.add(candidate)
            return candidate


def _normalize_livestock_category(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())


def _get_import_pen_or_raise(
    db: Session,
    pen_location: str,
    animal_type: str | None,
    quantity: int,
    *,
    exclude_livestock_id: int | None = None,
) -> LivestockPen:
    name = str(pen_location or "").strip()
    if not name:
        raise ValueError("Livestock Pen / Current Pen is required.")

    pen = db.scalar(
        select(LivestockPen).where(
            func.lower(LivestockPen.name) == name.lower(),
            LivestockPen.is_archived == False,
        )
    )
    if pen is None:
        raise ValueError(
            f'Pen "{name}" does not exist. Add it to a Livestock Pens sheet in the same workbook or create it first in Livestock > Manage Pens.'
        )

    acquire_transaction_lock(db, f"livestock-pen:{pen.id}")
    db.refresh(pen)
    if pen.is_archived or pen.status not in {"Active", "Full"}:
        raise ValueError(f'Pen "{pen.name}" is not available for livestock assignment.')

    allowed = _normalize_livestock_category(pen.animal_type)
    requested = _normalize_livestock_category(animal_type)
    if allowed and allowed not in {"all", "all livestock", "any"} and requested and allowed != requested:
        raise ValueError(
            f'{pen.name} is assigned to {pen.animal_type}, not {animal_type}.'
        )

    occupancy_query = select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
        Livestock.pen_id == pen.id,
        Livestock.is_archived == False,
        Livestock.lifecycle_status == "Active",
    )
    if exclude_livestock_id is not None:
        occupancy_query = occupancy_query.where(Livestock.id != exclude_livestock_id)
    occupied = int(db.scalar(occupancy_query) or 0)

    if pen.capacity is not None and occupied + int(quantity or 0) > int(pen.capacity):
        available = max(0, int(pen.capacity) - occupied)
        raise ValueError(f"{pen.name} only has {available} available space(s).")

    return pen


def _crop_progress(planting: date, estimated_harvest: date) -> tuple[float, str]:
    progress = calculate_crop_progress(planting, estimated_harvest)
    return progress, status_for_progress(progress)


def _find_base_duplicate(db: Session, target: str, mapped: dict[str, Any]):
    if target == "Livestock Pen":
        name = _optional_text(mapped.get("name"))
        if name:
            match = db.scalar(
                select(LivestockPen).where(func.lower(LivestockPen.name) == name.lower())
            )
            if match:
                return match, "Name Match"

    elif target == "Crop":
        code = _optional_text(mapped.get("crop_code"))
        if code:
            match = db.scalar(select(Crop).where(func.lower(Crop.crop_code) == code.lower()))
            if match:
                return match, "Code Match"
        if mapped.get("name") and mapped.get("variety") and mapped.get("field") and mapped.get("planting_date"):
            match = db.scalar(
                select(Crop).where(
                    func.lower(Crop.name) == str(mapped["name"]).lower(),
                    func.lower(Crop.variety) == str(mapped["variety"]).lower(),
                    func.lower(Crop.field) == str(mapped["field"]).lower(),
                    Crop.planting_date == mapped["planting_date"],
                )
            )
            if match:
                return match, "Likely Existing Record"

    elif target == "Livestock":
        code = _optional_text(mapped.get("animal_code"))
        if code:
            match = db.scalar(select(Livestock).where(func.lower(Livestock.animal_code) == code.lower()))
            if match:
                return match, "Code Match"

        record_type = "Batch"

        if (
            mapped.get("record_name")
            and mapped.get("animal_type")
            and mapped.get("breed")
            and mapped.get("date_of_birth")
            and mapped.get("pen_location")
        ):
            match = db.scalar(
                select(Livestock).where(
                    Livestock.record_type == "Batch",
                    func.lower(Livestock.record_name) == str(mapped["record_name"]).lower(),
                    func.lower(Livestock.animal_type) == str(mapped["animal_type"]).lower(),
                    func.lower(Livestock.breed) == str(mapped["breed"]).lower(),
                    Livestock.date_of_birth == mapped["date_of_birth"],
                    func.lower(Livestock.pen_location) == str(mapped["pen_location"]).lower(),
                )
            )
            if match:
                return match, "Likely Existing Batch"

    elif target == "Inventory":
        code = _optional_text(mapped.get("item_code"))
        if code:
            match = db.scalar(select(InventoryItem).where(func.lower(InventoryItem.item_code) == code.lower()))
            if match:
                return match, "Code Match"
        if mapped.get("name") and mapped.get("category") and mapped.get("supplier"):
            match = db.scalar(
                select(InventoryItem).where(
                    func.lower(InventoryItem.name) == str(mapped["name"]).lower(),
                    func.lower(InventoryItem.category) == str(mapped["category"]).lower(),
                    func.lower(InventoryItem.supplier) == str(mapped["supplier"]).lower(),
                )
            )
            if match:
                return match, "Likely Existing Record"
    return None, "New"


def _unique_crop_by_name(db: Session, name: str, field: str | None = None):
    statement = select(Crop).where(func.lower(Crop.name) == name.lower())
    if field:
        statement = statement.where(func.lower(Crop.field) == field.lower())
    matches = list(db.scalars(statement).all())
    return matches[0] if len(matches) == 1 else None


def _unique_livestock_by_name(db: Session, name: str):
    matches = list(
        db.scalars(select(Livestock).where(func.lower(Livestock.record_name) == name.lower())).all()
    )
    return matches[0] if len(matches) == 1 else None


def _resolve_crop_parent(db: Session, mapped: dict[str, Any], pending_by_code: dict[str, dict[str, Any]], pending_by_name: dict[str, list[dict[str, Any]]]):
    code = _optional_text(mapped.get("crop_code"))
    if code:
        db_parent = db.scalar(select(Crop).where(func.lower(Crop.crop_code) == code.lower()))
        if db_parent:
            return db_parent.id, db_parent.crop_code, None
        pending = pending_by_code.get(code.lower())
        if pending:
            return None, pending["code"], "Parent crop will be created by this import batch."
        return None, code, "Crop Code was not found in the database or this import batch."

    name = _optional_text(mapped.get("crop_name"))
    field = _optional_text(mapped.get("field"))
    if not name:
        return None, None, "Crop Code or Crop Name is required."
    db_parent = _unique_crop_by_name(db, name, field)
    if db_parent:
        return db_parent.id, db_parent.crop_code, None
    pending_candidates = pending_by_name.get(name.lower(), [])
    if field:
        pending_candidates = [item for item in pending_candidates if _normalize_compare(item.get("field")) == _normalize_compare(field)]
    if len(pending_candidates) == 1:
        return None, pending_candidates[0]["code"], "Parent crop will be created by this import batch."
    if len(pending_candidates) > 1:
        return None, None, "Crop Name matches more than one pending crop; provide a Crop Code or Field."
    return None, None, "Crop Name could not be matched to one existing or pending crop."


def _resolve_livestock_parent(db: Session, mapped: dict[str, Any], pending_by_code: dict[str, dict[str, Any]], pending_by_name: dict[str, list[dict[str, Any]]]):
    code = _optional_text(mapped.get("animal_code"))
    if code:
        db_parent = db.scalar(select(Livestock).where(func.lower(Livestock.animal_code) == code.lower()))
        if db_parent:
            return db_parent.id, db_parent.animal_code, None
        pending = pending_by_code.get(code.lower())
        if pending:
            return None, pending["code"], "Parent livestock record will be created by this import batch."
        return None, code, "Animal Code was not found in the database or this import batch."

    name = _optional_text(mapped.get("record_name"))
    if not name:
        return None, None, "Animal Code or Livestock Record Name is required."
    db_parent = _unique_livestock_by_name(db, name)
    if db_parent:
        return db_parent.id, db_parent.animal_code, None
    pending_candidates = pending_by_name.get(name.lower(), [])
    if len(pending_candidates) == 1:
        return None, pending_candidates[0]["code"], "Parent livestock record will be created by this import batch."
    if len(pending_candidates) > 1:
        return None, None, "Livestock Record Name matches more than one pending record; provide an Animal Code."
    return None, None, "Livestock Record Name could not be matched to one existing or pending livestock record."


def _find_child_duplicate(db: Session, target: str, mapped: dict[str, Any], parent_id: int | None):
    if parent_id is None:
        return None, "New"
    if target == "Crop Yield":
        match = db.scalar(
            select(CropYieldRecord).where(
                CropYieldRecord.crop_id == parent_id,
                CropYieldRecord.harvest_date == mapped.get("harvest_date"),
                CropYieldRecord.quantity_kg == mapped.get("quantity_kg"),
            )
        )
    elif target == "Livestock Growth":
        match = db.scalar(
            select(LivestockGrowthRecord).where(
                LivestockGrowthRecord.livestock_id == parent_id,
                LivestockGrowthRecord.measurement_date == mapped.get("measurement_date"),
            )
        )
    elif target == "Livestock Feeding":
        match = db.scalar(
            select(LivestockFeedingRecord).where(
                LivestockFeedingRecord.livestock_id == parent_id,
                LivestockFeedingRecord.feeding_date == mapped.get("feeding_date"),
                func.lower(LivestockFeedingRecord.feeding_slot) == str(mapped.get("feeding_slot") or "").lower(),
            )
        )
    elif target == "Resource Usage":
        item = _resolve_resource_inventory_item(db, mapped, required=False)
        if item is None:
            return None, "New"
        module = mapped.get("module")
        parent_filter = (
            ResourceUsage.crop_id == parent_id if module == "Crop" else ResourceUsage.livestock_id == parent_id
        )
        match = db.scalar(
            select(ResourceUsage).where(
                parent_filter,
                ResourceUsage.inventory_item_id == item.id,
                func.lower(ResourceUsage.usage_type) == str(mapped.get("usage_type") or "").lower(),
                ResourceUsage.usage_date == mapped.get("usage_date"),
                ResourceUsage.quantity == mapped.get("quantity"),
                ResourceUsage.is_voided == False,
            )
        )
    elif target == "Vaccination":
        match = db.scalar(
            select(LivestockVaccinationRecord).where(
                LivestockVaccinationRecord.livestock_id == parent_id,
                func.lower(LivestockVaccinationRecord.vaccine) == str(mapped.get("vaccine") or "").lower(),
                LivestockVaccinationRecord.date_administered == mapped.get("date_administered"),
            )
        )
    elif target == "Livestock Reproduction":
        match = db.scalar(
            select(LivestockReproductionRecord).where(
                LivestockReproductionRecord.livestock_id == parent_id,
                func.lower(LivestockReproductionRecord.record_type) == str(mapped.get("record_type") or "").lower(),
                LivestockReproductionRecord.event_date == mapped.get("event_date"),
            )
        )
    elif target == "Livestock Production":
        match = db.scalar(
            select(LivestockProductionRecord).where(
                LivestockProductionRecord.livestock_id == parent_id,
                func.lower(LivestockProductionRecord.output_type) == str(mapped.get("output_type") or "").lower(),
                LivestockProductionRecord.record_date == mapped.get("record_date"),
                LivestockProductionRecord.quantity == mapped.get("quantity"),
                func.lower(LivestockProductionRecord.unit) == str(mapped.get("unit") or "").lower(),
            )
        )
    elif target == "Livestock Processing":
        match = db.scalar(
            select(LivestockProcessingRecord).where(
                LivestockProcessingRecord.livestock_id == parent_id,
                LivestockProcessingRecord.processing_date == mapped.get("processing_date"),
                LivestockProcessingRecord.animals_processed == mapped.get("animals_processed"),
                LivestockProcessingRecord.meat_output_kg == mapped.get("meat_output_kg"),
                LivestockProcessingRecord.is_voided == False,
            )
        )
    elif target == "Sales":
        sale_code = _optional_text(mapped.get("sale_code"))
        if sale_code:
            match = db.scalar(select(LivestockSale).where(func.lower(LivestockSale.sale_code) == sale_code.lower()))
        else:
            match = db.scalar(
                select(LivestockSale).where(
                    LivestockSale.livestock_id == parent_id,
                    LivestockSale.sale_date == mapped.get("sale_date"),
                    func.lower(LivestockSale.sale_type) == str(mapped.get("sale_type") or "").lower(),
                    func.lower(LivestockSale.product_type) == str(mapped.get("product_type") or "").lower(),
                    LivestockSale.quantity == mapped.get("quantity"),
                    LivestockSale.unit_price == mapped.get("unit_price"),
                    LivestockSale.is_voided == False,
                )
            )
    else:
        match = None
    return (match, "Likely Existing Record") if match else (None, "New")


def _serialize_model(record: Any, target: str) -> dict[str, Any]:
    if record is None:
        return {}
    result: dict[str, Any] = {}
    for field in MODEL_FIELDS[target]:
        if hasattr(record, field):
            result[field] = getattr(record, field)
    return json.loads(_json_dump(result))


def _batch_user_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.full_name if user else None


def batch_summary(db: Session, batch: DataImportBatch) -> dict[str, Any]:
    has_imported_sales = any(
        row.target_type == "Sales" and row.status in {"Imported", "Updated"}
        for row in batch.rows
    )
    return {
        "id": batch.id,
        "batch_code": batch.batch_code,
        "original_filename": batch.original_filename,
        "file_hash_sha256": batch.file_hash_sha256,
        "file_size_bytes": batch.file_size_bytes,
        "file_type": batch.file_type,
        "status": batch.status,
        "sheet_count": batch.sheet_count,
        "total_rows": batch.total_rows,
        "valid_rows": batch.valid_rows,
        "invalid_rows": batch.invalid_rows,
        "duplicate_rows": batch.duplicate_rows,
        "imported_rows": batch.imported_rows,
        "updated_rows": batch.updated_rows,
        "skipped_rows": batch.skipped_rows,
        "error_rows": batch.error_rows,
        "imported_by_user_id": batch.imported_by_user_id,
        "imported_by_name": _batch_user_name(db, batch.imported_by_user_id),
        "created_at": batch.created_at,
        "completed_at": batch.completed_at,
        "rolled_back_at": batch.rolled_back_at,
        "notes": batch.notes,
        "can_rollback": (
            batch.status == "Completed"
            and (batch.imported_rows > 0 or batch.updated_rows > 0)
            and not has_imported_sales
        ),
    }


def row_response(row: DataImportRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "sheet_name": row.sheet_name,
        "row_number": row.row_number,
        "detected_type": row.detected_type,
        "target_type": row.target_type,
        "confidence": row.confidence,
        "source": _json_load(row.source_json, {}),
        "mapping": _json_load(row.mapping_json, {}),
        "mapped": _json_load(row.mapped_json, {}),
        "validation_errors": _json_load(row.validation_errors_json, []),
        "warnings": _json_load(row.warnings_json, []),
        "duplicate_status": row.duplicate_status,
        "existing_record_id": row.existing_record_id,
        "generated_code": row.generated_code,
        "requested_action": row.requested_action,
        "result_record_id": row.result_record_id,
        "status": row.status,
        "error_message": row.error_message,
    }


def _sheet_response(batch_rows: list[DataImportRow], metadata: dict[str, Any]) -> dict[str, Any]:
    name = metadata["sheet_name"]
    rows = [row for row in batch_rows if row.sheet_name == name]
    target = metadata["target_type"]
    return {
        **metadata,
        "supported": target in SUPPORTED_TARGETS,
        "row_count": len(rows),
        "valid_rows": sum(1 for row in rows if row.status == "Ready"),
        "invalid_rows": sum(1 for row in rows if row.status in {"Invalid", "Unsupported"}),
        "duplicate_rows": sum(1 for row in rows if row.duplicate_status != "New"),
        "generated_code_rows": sum(1 for row in rows if row.generated_code),
        "rows": [row_response(row) for row in rows[:200]],
    }


def _refresh_batch_counts(batch: DataImportBatch):
    rows = list(batch.rows)
    batch.total_rows = len(rows)
    batch.valid_rows = sum(1 for row in rows if row.status == "Ready")
    batch.invalid_rows = sum(1 for row in rows if row.status in {"Invalid", "Unsupported"})
    batch.duplicate_rows = sum(1 for row in rows if row.duplicate_status != "New")


def _admin_requirement(batch: DataImportBatch) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if batch.total_rows > LARGE_IMPORT_THRESHOLD:
        reasons.append(f"This import contains more than {LARGE_IMPORT_THRESHOLD} rows and requires administrator approval.")
    return bool(reasons), reasons


def _review_metadata_from_rows(batch: DataImportBatch) -> list[dict[str, Any]]:
    detected_types = _json_load(batch.detected_types_json, [])
    if isinstance(detected_types, list):
        return detected_types
    return []


def preview_response(db: Session, batch: DataImportBatch) -> dict[str, Any]:
    metadata = _review_metadata_from_rows(batch)
    rows = list(batch.rows)
    requires_admin, reasons = _admin_requirement(batch)
    return {
        "already_imported": False,
        "exact_duplicate_batch": None,
        "batch": batch_summary(db, batch),
        "sheets": [_sheet_response(rows, item) for item in metadata],
        "field_catalog": field_catalog(),
        "requires_admin": requires_admin,
        "admin_reasons": reasons,
        "message": "Review the detected data types, column mapping, generated codes, validation results, and duplicates before importing.",
    }


def exact_duplicate_response(db: Session, existing: DataImportBatch) -> dict[str, Any]:
    return {
        "already_imported": True,
        "exact_duplicate_batch": batch_summary(db, existing),
        "batch": None,
        "sheets": [],
        "field_catalog": field_catalog(),
        "requires_admin": True,
        "admin_reasons": ["The exact file contents were already imported. Force re-import is administrator-only."],
        "message": "This exact file has already been imported. Renaming the file does not bypass duplicate detection because the system checks its SHA-256 content fingerprint.",
    }


def _is_utility_sheet(sheet_name: str) -> bool:
    normalized = normalize_header(sheet_name).replace("_", " ")
    return any(hint in normalized for hint in UTILITY_SHEET_HINTS)


def _build_rows(
    db: Session,
    batch: DataImportBatch,
    parsed_sheets: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None = None,
):
    overrides = overrides or {}

    # Clear the previous preview rows when revalidating mappings.
    batch.rows.clear()
    db.flush()

    crop_codes = _existing_code_set(db, Crop, Crop.crop_code)
    livestock_codes = _existing_code_set(db, Livestock, Livestock.animal_code)
    inventory_codes = _existing_code_set(db, InventoryItem, InventoryItem.item_code)

    metadata: list[dict[str, Any]] = []
    base_pending_rows: list[DataImportRow] = []

    for sheet in parsed_sheets:
        sheet_name = sheet["name"]
        columns = sheet["columns"]
        detected_type, confidence, detected_mapping = detect_target(sheet_name, columns)
        override = overrides.get(sheet_name, {})
        default_include = not _is_utility_sheet(sheet_name)
        include = bool(override.get("include", default_include))
        target_type = str(override.get("target_type") or detected_type)
        if target_type not in TARGET_FIELDS:
            target_type = detected_type
        mapping = dict(detected_mapping)
        if override.get("column_mapping"):
            mapping.update({key: value for key, value in override["column_mapping"].items() if key in TARGET_FIELDS[target_type]})
        if target_type != detected_type and not override.get("column_mapping"):
            mapping = suggest_mapping(target_type, columns)

        fields = TARGET_FIELDS[target_type]
        required_fields = [key for key, spec in fields.items() if spec.required]
        optional_fields = [key for key, spec in fields.items() if not spec.required]

        metadata.append({
            "sheet_name": sheet_name,
            "target_type": target_type,
            "detected_type": detected_type,
            "confidence": confidence,
            "source_columns": columns,
            "column_mapping": mapping,
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "included": include,
        })

        # Utility/instruction sheets are represented in the preview metadata but
        # do not become import rows unless the user explicitly includes them.
        if not include and _is_utility_sheet(sheet_name) and sheet_name not in overrides:
            continue

        for row_number, source in sheet["rows"]:
            mapped, errors, warnings = map_and_validate_row(target_type, source, mapping)
            generated_code = None

            if not include:
                errors.append("This sheet is excluded from the import.")

            if target_type == "Crop":
                supplied = _optional_text(mapped.get("crop_code"))
                if not supplied or not re.fullmatch(r"CRP-\d+", supplied, flags=re.IGNORECASE):
                    generated_code = _reserve_code(crop_codes, "CRP")
                    mapped["crop_code"] = generated_code
                    warnings.append(
                        f"{'Missing' if not supplied else 'Invalid'} Crop Code: {generated_code} will be generated."
                    )
            elif target_type == "Livestock":
                supplied = _optional_text(mapped.get("animal_code"))
                record_type = "Batch"
                mapped["record_type"] = record_type
                if not supplied:
                    generated_code = _reserve_livestock_code(
                        livestock_codes,
                        str(mapped.get("animal_type") or "Animal"),
                        record_type,
                        str(mapped.get("breed") or ""),
                    )
                    mapped["animal_code"] = generated_code
                    warnings.append(
                        f"Missing Animal Code: {generated_code} will be generated."
                    )
            elif target_type == "Inventory":
                supplied = _optional_text(mapped.get("item_code"))
                if not supplied or not re.fullmatch(r"INV-\d+", supplied, flags=re.IGNORECASE):
                    generated_code = _reserve_code(inventory_codes, "INV")
                    mapped["item_code"] = generated_code
                    warnings.append(
                        f"{'Missing' if not supplied else 'Invalid'} Item Code: {generated_code} will be generated."
                    )

            status_value = "Ready"
            if target_type in UNSUPPORTED_TARGETS:
                status_value = "Unsupported"
            elif errors:
                status_value = "Invalid"

            row = DataImportRow(
                import_batch_id=batch.id,
                sheet_name=sheet_name,
                row_number=row_number,
                detected_type=detected_type,
                target_type=target_type,
                confidence=confidence,
                source_json=_json_dump(source),
                mapping_json=_json_dump(mapping),
                mapped_json=_json_dump(mapped),
                validation_errors_json=_json_dump(errors),
                warnings_json=_json_dump(warnings),
                duplicate_status="New",
                existing_record_id=None,
                generated_code=generated_code,
                requested_action="skip",
                status=status_value,
            )
            batch.rows.append(row)
            if target_type in ROOT_TARGETS:
                base_pending_rows.append(row)

    db.flush()

    # Base-record duplicate detection happens first so child sheets can also
    # resolve parents that will be created in this same import batch.
    pending_crop_by_code: dict[str, dict[str, Any]] = {}
    pending_crop_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pending_livestock_by_code: dict[str, dict[str, Any]] = {}
    pending_livestock_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in base_pending_rows:
        if row.status != "Ready":
            continue
        mapped = _typed_mapped(row.target_type, _json_load(row.mapped_json, {}))
        existing, duplicate_status = _find_base_duplicate(db, row.target_type, mapped)
        if existing:
            row.existing_record_id = existing.id
            row.duplicate_status = duplicate_status
            warnings = _json_load(row.warnings_json, [])
            warnings.append(f"Potential duplicate detected: existing {row.target_type} record ID {existing.id}.")
            row.warnings_json = _json_dump(list(dict.fromkeys(warnings)))
        else:
            if row.target_type == "Crop":
                entry = {"code": mapped.get("crop_code"), "name": mapped.get("name"), "field": mapped.get("field"), "row_id": row.id}
                if entry["code"]:
                    pending_crop_by_code[str(entry["code"]).lower()] = entry
                if entry["name"]:
                    pending_crop_by_name[str(entry["name"]).lower()].append(entry)
            elif row.target_type == "Livestock":
                entry = {"code": mapped.get("animal_code"), "name": mapped.get("record_name"), "row_id": row.id}
                if entry["code"]:
                    pending_livestock_by_code[str(entry["code"]).lower()] = entry
                if entry["name"]:
                    pending_livestock_by_name[str(entry["name"]).lower()].append(entry)

    for row in batch.rows:
        if row.status != "Ready" or row.target_type not in CHILD_TARGETS:
            continue
        mapped = _typed_mapped(row.target_type, _json_load(row.mapped_json, {}))
        errors = _json_load(row.validation_errors_json, [])
        warnings = _json_load(row.warnings_json, [])

        if row.target_type == "Crop Yield":
            parent_id, parent_code, parent_note = _resolve_crop_parent(
                db, mapped, pending_crop_by_code, pending_crop_by_name
            )
            if parent_code:
                mapped["crop_code"] = parent_code
            if parent_note and "will be created" not in parent_note:
                errors.append(parent_note)
            elif parent_note:
                warnings.append(parent_note)
            existing, duplicate_status = _find_child_duplicate(db, row.target_type, mapped, parent_id)
        elif row.target_type == "Resource Usage":
            if mapped.get("module") == "Crop":
                parent_id, parent_code, parent_note = _resolve_crop_parent(
                    db, mapped, pending_crop_by_code, pending_crop_by_name
                )
                if parent_code:
                    mapped["crop_code"] = parent_code
            else:
                parent_id, parent_code, parent_note = _resolve_livestock_parent(
                    db, mapped, pending_livestock_by_code, pending_livestock_by_name
                )
                if parent_code:
                    mapped["animal_code"] = parent_code
            if parent_note and "will be created" not in parent_note:
                errors.append(parent_note)
            elif parent_note:
                warnings.append(parent_note)
            existing, duplicate_status = _find_child_duplicate(db, row.target_type, mapped, parent_id)
        else:
            parent_id, parent_code, parent_note = _resolve_livestock_parent(
                db, mapped, pending_livestock_by_code, pending_livestock_by_name
            )
            if parent_code:
                mapped["animal_code"] = parent_code
            if parent_note and "will be created" not in parent_note:
                errors.append(parent_note)
            elif parent_note:
                warnings.append(parent_note)
            existing, duplicate_status = _find_child_duplicate(db, row.target_type, mapped, parent_id)

        if existing:
            row.existing_record_id = existing.id
            row.duplicate_status = duplicate_status
            warnings.append(f"Potential duplicate detected: existing {row.target_type} record ID {existing.id}.")
        row.mapped_json = _json_dump(mapped)
        row.validation_errors_json = _json_dump(list(dict.fromkeys(errors)))
        row.warnings_json = _json_dump(list(dict.fromkeys(warnings)))
        if errors:
            row.status = "Invalid"

    batch.detected_types_json = _json_dump(metadata)
    batch.sheet_count = len(metadata)
    _refresh_batch_counts(batch)
    db.flush()


def create_preview(
    db: Session,
    *,
    filename: str,
    content: bytes,
    current_user: User,
    force: bool = False,
) -> dict[str, Any]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only .xlsx, .csv, and .json files are supported.")
    if not content:
        raise ValueError("The selected import file is empty.")
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("The selected import file is larger than the 15 MB import limit.")

    file_hash = hash_bytes(content)
    existing = db.scalar(
        select(DataImportBatch)
        .where(
            DataImportBatch.file_hash_sha256 == file_hash,
            DataImportBatch.status == "Completed",
        )
        .order_by(DataImportBatch.id.desc())
        .limit(1)
    )
    if existing is not None and not force:
        return exact_duplicate_response(db, existing)

    parsed = parse_import_bytes(filename, content)
    stored_filename, stored_path = save_import_file(filename, content, file_hash)

    batch = DataImportBatch(
        batch_code=generate_batch_code(db),
        original_filename=Path(filename).name,
        stored_filename=stored_filename,
        stored_path=stored_path,
        file_hash_sha256=file_hash,
        file_size_bytes=len(content),
        file_type=extension.lstrip("."),
        status="Previewed",
        sheet_count=len(parsed),
        detected_types_json="[]",
        imported_by_user_id=current_user.id,
        notes=(
            "Forced preview of a previously imported file fingerprint."
            if existing is not None and force
            else None
        ),
    )
    db.add(batch)
    db.flush()
    _build_rows(db, batch, parsed)
    db.commit()
    db.refresh(batch)
    return preview_response(db, batch)


def get_batch_or_none(db: Session, batch_id: int) -> DataImportBatch | None:
    return db.get(DataImportBatch, batch_id)


def revalidate_preview(
    db: Session,
    batch: DataImportBatch,
    sheet_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    if batch.status not in {"Previewed", "Reviewed"}:
        raise ValueError("Only a pending import preview can be revalidated.")
    path = _resolve_stored_import_path(batch)
    if not path.exists():
        raise ValueError("The stored import file is no longer available on the server.")
    parsed = parse_import_bytes(batch.original_filename, path.read_bytes())
    overrides = {item["sheet_name"]: item for item in sheet_reviews}
    _build_rows(db, batch, parsed, overrides)
    batch.status = "Reviewed"
    db.commit()
    db.refresh(batch)
    return preview_response(db, batch)


def is_admin(user: User) -> bool:
    return "*" in set(getattr(user, "permissions", []) or [])


def _ensure_code_available(db: Session, target: str, mapped: dict[str, Any], existing_ids_to_ignore: set[int] | None = None):
    existing_ids_to_ignore = existing_ids_to_ignore or set()
    if target == "Crop":
        code_field, model, column, prefix = "crop_code", Crop, Crop.crop_code, "CRP"
        lock_resource = "code:crop"
    elif target == "Livestock":
        code_field, model, column, prefix = "animal_code", Livestock, Livestock.animal_code, "C"
        lock_resource = "code:livestock"
    else:
        code_field, model, column, prefix = "item_code", InventoryItem, InventoryItem.item_code, "INV"
        lock_resource = "code:inventory"

    # Keep Smart Import code reservation serialized with normal create routes.
    acquire_transaction_lock(db, lock_resource)

    code = _optional_text(mapped.get(code_field))
    if code:
        match = db.scalar(select(model).where(func.lower(column) == code.lower()))
        if not match or match.id in existing_ids_to_ignore:
            return code

    existing = _existing_code_set(db, model, column)
    if target == "Livestock":
        record_type = "Batch"
        return _reserve_livestock_code(
            existing,
            str(mapped.get("animal_type") or "Animal"),
            record_type,
            str(mapped.get("breed") or ""),
        )
    return _reserve_code(existing, prefix)


def _resolve_parent_at_commit(db: Session, target: str, mapped: dict[str, Any]):
    if target in {"Crop Yield", "Resource Usage"} and (target == "Crop Yield" or mapped.get("module") == "Crop"):
        code = _optional_text(mapped.get("crop_code"))
        parent = db.scalar(select(Crop).where(func.lower(Crop.crop_code) == code.lower())) if code else None
        if not parent and mapped.get("crop_name"):
            parent = _unique_crop_by_name(db, str(mapped["crop_name"]), _optional_text(mapped.get("field")))
        if not parent:
            raise ValueError("The parent crop could not be resolved during import commit.")
        return parent

    code = _optional_text(mapped.get("animal_code"))
    parent = db.scalar(select(Livestock).where(func.lower(Livestock.animal_code) == code.lower())) if code else None
    if not parent and mapped.get("record_name"):
        parent = _unique_livestock_by_name(db, str(mapped["record_name"]))
    if not parent:
        raise ValueError("The parent livestock record could not be resolved during import commit.")
    return parent


def _resolve_sale_production_record(
    db: Session,
    mapped: dict[str, Any],
    livestock_id: int,
) -> LivestockProductionRecord:
    production_id = mapped.get("production_record_id")
    if production_id:
        record = db.get(LivestockProductionRecord, int(production_id))
        if record is None:
            raise ValueError("Production Record ID was not found.")
        if record.livestock_id != livestock_id:
            raise ValueError("The Production Record ID does not belong to the selected livestock record.")
        return record

    production_date = mapped.get("production_date")
    output_type = _optional_text(mapped.get("production_output_type"))
    if not production_date or not output_type:
        raise ValueError(
            "Product sales require Production Record ID, or both Production Date and Production Output Type."
        )

    # Meat inventory is created by Livestock Processing. If the processing row
    # is a duplicate, Smart Import correctly skips the processing transaction so
    # the livestock quantity is not reduced twice. In that case, resolve the sale
    # through the existing processing record and its linked production inventory.
    meat_output_types = {
        "meat",
        "pork",
        "broiler meat",
        "chicken meat",
        "duck meat",
        "goat meat",
    }
    if output_type.strip().lower() in meat_output_types:
        processing_matches = list(
            db.scalars(
                select(LivestockProcessingRecord)
                .where(
                    LivestockProcessingRecord.livestock_id == livestock_id,
                    LivestockProcessingRecord.processing_date == production_date,
                    LivestockProcessingRecord.is_voided == False,
                )
                .order_by(LivestockProcessingRecord.id.desc())
            ).all()
        )

        if len(processing_matches) > 1:
            raise ValueError(
                "More than one livestock processing record matches this meat sale. "
                "Provide Production Record ID to identify the source exactly."
            )

        if len(processing_matches) == 1:
            processing = processing_matches[0]
            linked = db.get(
                LivestockProductionRecord,
                int(processing.production_record_id),
            ) if processing.production_record_id else None

            if linked is not None:
                if linked.livestock_id != livestock_id:
                    raise ValueError(
                        "The production record linked to the processing transaction belongs to a different livestock record."
                    )

                # Processing output is sale inventory by design. Repair older
                # records that may predate that flag without recreating processing
                # or changing the animal population again.
                if not linked.track_sale_inventory:
                    linked.track_sale_inventory = True
                if not _optional_text(linked.output_type):
                    linked.output_type = "Meat"
                db.flush()
                return linked

            # Defensive repair for legacy/orphan processing history. Recreate only
            # the missing production inventory; do NOT process animals again.
            repaired = LivestockProductionRecord(
                livestock_id=processing.livestock_id,
                output_type="Meat",
                record_date=processing.processing_date,
                period_start_date=processing.processing_date,
                period_end_date=processing.processing_date,
                source_head_quantity=processing.animals_processed,
                source_female_quantity=None,
                quantity=processing.meat_output_kg,
                unit="kg",
                quality_grade=processing.quality_grade,
                destination=processing.destination or "Available for sale",
                track_sale_inventory=True,
                notes=(
                    (processing.notes or "")
                    + " Smart Import restored the missing meat production link from the existing processing record."
                ).strip(),
                recorded_by_user_id=processing.recorded_by_user_id,
            )
            db.add(repaired)
            db.flush()
            processing.production_record_id = repaired.id
            db.flush()
            return repaired

    statement = select(LivestockProductionRecord).where(
        LivestockProductionRecord.livestock_id == livestock_id,
        LivestockProductionRecord.record_date == production_date,
        func.lower(LivestockProductionRecord.output_type) == output_type.lower(),
    )
    unit = _optional_text(mapped.get("unit"))
    if unit:
        statement = statement.where(
            func.lower(LivestockProductionRecord.unit) == unit.lower()
        )
    matches = list(db.scalars(statement.order_by(LivestockProductionRecord.id.desc())).all())
    if not matches:
        raise ValueError(
            "No matching livestock production record was found for this product sale."
        )
    if len(matches) > 1:
        raise ValueError(
            "More than one production record matches this sale. Provide Production Record ID to identify the source exactly."
        )
    return matches[0]


def _recalculate_import_growth_history(db: Session, livestock: Livestock) -> None:
    records = list(
        db.scalars(
            select(LivestockGrowthRecord)
            .where(LivestockGrowthRecord.livestock_id == livestock.id)
            .order_by(LivestockGrowthRecord.measurement_date.asc(), LivestockGrowthRecord.id.asc())
        ).all()
    )
    previous = None
    for record in records:
        if previous is None:
            record.previous_weight_kg = None
            record.weight_change_kg = None
            record.days_since_previous = None
            record.average_daily_gain_kg = None
        else:
            days = (record.measurement_date - previous.measurement_date).days
            change = round(float(record.weight_kg or 0) - float(previous.weight_kg or 0), 2)
            record.previous_weight_kg = float(previous.weight_kg or 0)
            record.weight_change_kg = change
            record.days_since_previous = days
            record.average_daily_gain_kg = round(change / days, 4) if days > 0 else None
        previous = record
    if records:
        livestock.weight_kg = float(records[-1].weight_kg or 0)
        livestock.updated_at = datetime.now()


def _resolve_resource_inventory_item(
    db: Session,
    mapped: dict[str, Any],
    *,
    required: bool = True,
) -> InventoryItem | None:
    code = _optional_text(mapped.get("inventory_item_code"))
    name = _optional_text(mapped.get("inventory_item_name"))
    item = None
    if code:
        item = db.scalar(select(InventoryItem).where(func.lower(InventoryItem.item_code) == code.lower()))
    if item is None and name:
        item = db.scalar(select(InventoryItem).where(func.lower(InventoryItem.name) == name.lower()))
    if item is None and required:
        raise ValueError("The inventory item for resource usage could not be resolved during import commit.")
    return item


def _resolve_feed_inventory_item(
    db: Session,
    mapped: dict[str, Any],
    *,
    required: bool = True,
) -> InventoryItem | None:
    code = _optional_text(mapped.get("inventory_item_code"))
    item = db.scalar(
        select(InventoryItem).where(func.lower(InventoryItem.item_code) == code.lower())
    ) if code else None
    name = _optional_text(mapped.get("inventory_item_name")) or _optional_text(mapped.get("feed_type"))
    if item is None and name:
        item = db.scalar(select(InventoryItem).where(func.lower(InventoryItem.name) == name.lower()))
    if item is None:
        if required:
            raise ValueError(
                "The exact Feed Inventory item could not be resolved. Add/map Inventory Item Code or Inventory Feed Item before importing the feeding schedule."
            )
        return None
    if item.is_archived:
        raise ValueError(f'The feed inventory item "{item.name}" is archived.')

    category = _normalize_livestock_category(item.category)
    item_name = _normalize_livestock_category(item.name)
    if "feed" not in category and "feed" not in item_name:
        raise ValueError(f'Inventory item "{item.name}" is not classified as feed.')

    unit = str(item.unit or "").strip().lower()
    if unit not in {"kg", "kgs", "kilogram", "kilograms"}:
        raise ValueError(
            f'Feed inventory item "{item.name}" must use kilograms (kg), not {item.unit or "an unspecified unit"}.'
        )
    return item


def _create_record(db: Session, target: str, mapped: dict[str, Any], current_user: User):
    if mapped.get("is_archived"):
        raise ValueError("Create the record first, then use the Archive action with a reason.")
    if target == "Livestock Pen":
        name = str(mapped["name"]).strip()
        acquire_transaction_lock(db, f"livestock-pen-name:{name.lower()}")
        duplicate = db.scalar(
            select(LivestockPen).where(func.lower(LivestockPen.name) == name.lower())
        )
        if duplicate is not None:
            raise ValueError(f'Livestock Pen "{name}" already exists. Choose Update or Skip instead of Keep as New.')
        record = LivestockPen(
            name=name,
            purpose=_optional_text(mapped.get("purpose")) or "General",
            animal_type=_optional_text(mapped.get("animal_type")),
            capacity=mapped.get("capacity"),
            location_area=_optional_text(mapped.get("location_area")),
            status=_optional_text(mapped.get("status")) or "Active",
            notes=_optional_text(mapped.get("notes")),
            is_archived=False,
        )
    elif target == "Crop":
        progress, status_value = _crop_progress(mapped["planting_date"], mapped["estimated_harvest"])
        record = Crop(
            crop_code=mapped["crop_code"],
            name=str(mapped["name"]).strip(),
            variety=str(mapped["variety"]).strip(),
            field=str(mapped["field"]).strip(),
            area_hectares=mapped["area_hectares"],
            current_growth=progress,
            growth_stage=stage_for_progress(progress),
            quantity_planted=int(mapped.get("quantity_planted") or 0),
            current_surviving=int(mapped.get("current_surviving") or mapped.get("quantity_planted") or 0),
            status=status_value,
            planting_date=mapped["planting_date"],
            estimated_harvest=mapped["estimated_harvest"],
            fertilizer_quantity_kg=mapped.get("fertilizer_quantity_kg") or 0,
            fertilizer_date=mapped.get("fertilizer_date"),
            pesticide_used=_optional_text(mapped.get("pesticide_used")),
            watering_schedule=_optional_text(mapped.get("watering_schedule")),
            notes=_optional_text(mapped.get("notes")),
            is_archived=False,
            created_by_user_id=current_user.id,
        )
    elif target == "Livestock":
        record_type = "Batch"
        pen = _get_import_pen_or_raise(
            db,
            str(mapped["pen_location"]),
            str(mapped["animal_type"]),
            int(mapped["quantity"]),
        )
        has_feeding_schedule = bool(
            float(mapped.get("daily_feed_kg") or 0) > 0
            or _optional_text(mapped.get("feed_times"))
            or _optional_text(mapped.get("feed_type"))
            or _optional_text(mapped.get("inventory_item_code"))
            or _optional_text(mapped.get("inventory_item_name"))
        )
        feed_item = _resolve_feed_inventory_item(
            db, mapped, required=has_feeding_schedule
        ) if has_feeding_schedule else None
        record = Livestock(
            animal_code=mapped["animal_code"],
            record_type=record_type,
            lifecycle_status="Active",
            record_name=str(mapped["record_name"]).strip(),
            animal_type=str(mapped["animal_type"]).strip(),
            breed=str(mapped["breed"]).strip(),
            quantity=int(mapped["quantity"]),
            male_quantity=int(mapped.get("male_quantity") or 0),
            female_quantity=int(mapped.get("female_quantity") or 0),
            unknown_sex_quantity=int(mapped.get("unknown_sex_quantity") or 0),
            sex=_optional_text(mapped.get("sex")) or "Mixed",
            date_of_birth=mapped["date_of_birth"],
            weight_kg=mapped["weight_kg"],
            min_weight_kg=mapped.get("min_weight_kg") or mapped["weight_kg"],
            max_weight_kg=mapped.get("max_weight_kg") or mapped["weight_kg"],
            pen_location=pen.name,
            pen_id=pen.id,
            health_status=_optional_text(mapped.get("health_status")) or "Healthy",
            healthy_quantity=int(mapped.get("healthy_quantity") or 0),
            at_risk_quantity=int(mapped.get("at_risk_quantity") or 0),
            sick_quantity=int(mapped.get("sick_quantity") or 0),
            under_treatment_quantity=int(mapped.get("under_treatment_quantity") or 0),
            growth_status=_optional_text(mapped.get("growth_status")) or "Growing",
            production_purpose=_optional_text(mapped.get("production_purpose")) or "General",
            last_checkup=mapped.get("last_checkup"),
            health_notes=_optional_text(mapped.get("health_notes")),
            vaccination_status=_optional_text(mapped.get("vaccination_status")) or "Not Vaccinated",
            next_vaccination=mapped.get("next_vaccination"),
            feed_times=_optional_text(mapped.get("feed_times")),
            feed_type=feed_item.name if feed_item is not None else None,
            daily_feed_kg=mapped.get("daily_feed_kg") or 0,
            feeding_notes=_optional_text(mapped.get("feeding_notes")),
            feed_inventory_item_id=feed_item.id if feed_item is not None else None,
            production_output=None,
            date_acquired=mapped["date_acquired"],
            acquired_from=_optional_text(mapped.get("acquired_from")),
            is_archived=False,
            created_by_user_id=current_user.id,
        )
    elif target == "Resource Usage":
        parent = _resolve_parent_at_commit(db, target, mapped)
        item = _resolve_resource_inventory_item(db, mapped)
        module = str(mapped["module"])
        usage_date = mapped["usage_date"]
        if module == "Crop" and usage_date < parent.planting_date:
            raise ValueError("Resource Usage Date cannot be earlier than the crop Planting Date.")
        if module == "Livestock" and parent.date_acquired and usage_date < parent.date_acquired:
            raise ValueError("Resource Usage Date cannot be earlier than the livestock Date Acquired.")
        basis_value = float(parent.area_hectares or 0) if module == "Crop" else float(parent.quantity or 0)
        basis_unit = "ha" if module == "Crop" else "animals"
        record = ResourceUsage(
            inventory_item_id=item.id,
            module=module,
            crop_id=parent.id if module == "Crop" else None,
            livestock_id=parent.id if module == "Livestock" else None,
            usage_type=str(mapped["usage_type"]),
            quantity=mapped["quantity"],
            unit=item.unit,
            item_code_snapshot=item.item_code,
            item_name_snapshot=item.name,
            category_snapshot=item.category,
            batch_number_snapshot=item.batch_number,
            basis_value=basis_value if basis_value > 0 else None,
            basis_unit=basis_unit if basis_value > 0 else None,
            usage_date=usage_date,
            notes=_optional_text(mapped.get("notes")),
            is_voided=False,
            recorded_by_user_id=current_user.id,
        )
        # This is historical import data. Do not deduct the current inventory
        # balance again; the imported Inventory row is the source of truth for
        # current on-hand stock.
        db.add(record)
        db.flush()
        return record
    elif target == "Inventory":
        record = InventoryItem(
            item_code=mapped["item_code"],
            name=str(mapped["name"]).strip(),
            category=str(mapped["category"]).strip(),
            batch_number=_optional_text(mapped.get("batch_number")),
            quantity=mapped["quantity"],
            unit=str(mapped["unit"]).strip(),
            reorder_level=mapped["reorder_level"],
            cost=mapped["cost"],
            price=mapped["price"],
            supplier=str(mapped["supplier"]).strip(),
            date_acquired=mapped["date_acquired"],
            expiration_date=mapped.get("expiration_date"),
            location=str(mapped["location"]).strip(),
            description=_optional_text(mapped.get("description")),
            notes=_optional_text(mapped.get("notes")),
            is_archived=False,
            created_by_user_id=current_user.id,
        )
    elif target == "Crop Yield":
        parent = _resolve_parent_at_commit(db, target, mapped)
        area = float(parent.area_hectares or 0)
        quantity = float(mapped["quantity_kg"])
        record = CropYieldRecord(
            crop_id=parent.id,
            harvest_date=mapped["harvest_date"],
            quantity_kg=quantity,
            quality=_optional_text(mapped.get("quality")),
            harvest_type=_optional_text(mapped.get("harvest_type")),
            yield_per_hectare=(quantity / area if area > 0 else None),
            notes=_optional_text(mapped.get("notes")),
            recorded_by_user_id=current_user.id,
        )
    elif target == "Livestock Growth":
        parent = _resolve_parent_at_commit(db, target, mapped)
        if parent.date_of_birth is not None and mapped["measurement_date"] < parent.date_of_birth:
            raise ValueError("Growth measurement cannot be earlier than Date of Birth.")
        if mapped["measurement_date"] < parent.date_acquired:
            raise ValueError("Growth measurement cannot be earlier than Date Acquired.")
        if mapped["measurement_date"] > farm_today():
            raise ValueError("Growth measurement cannot be in the future.")
        record = LivestockGrowthRecord(
            livestock_id=parent.id,
            measurement_date=mapped["measurement_date"],
            weight_kg=mapped["weight_kg"],
            notes=_optional_text(mapped.get("notes")),
            recorded_by_user_id=current_user.id,
        )
        db.add(record)
        db.flush()
        _recalculate_import_growth_history(db, parent)
        return record
    elif target == "Livestock Feeding":
        parent = _resolve_parent_at_commit(db, target, mapped)
        if mapped["feeding_date"] < parent.date_acquired:
            raise ValueError("Feeding Date cannot be earlier than Date Acquired.")
        if mapped["feeding_date"] > farm_today():
            raise ValueError("Feeding Date cannot be in the future.")
        item = _resolve_feed_inventory_item(db, mapped)
        actual = float(mapped["actual_quantity_kg"] or 0)
        planned = float(mapped.get("planned_quantity_kg") or actual)
        record = LivestockFeedingRecord(
            livestock_id=parent.id,
            inventory_item_id=item.id,
            feeding_date=mapped["feeding_date"],
            feeding_slot=str(mapped["feeding_slot"]).strip(),
            scheduled_times=_optional_text(mapped.get("scheduled_times")) or _optional_text(parent.feed_times),
            feed_type=_optional_text(mapped.get("feed_type")) or item.name,
            planned_quantity_kg=planned,
            actual_quantity_kg=actual,
            notes=_optional_text(mapped.get("notes")),
            recorded_by_user_id=current_user.id,
        )
        db.add(record)
        db.flush()
        return record
    elif target == "Vaccination":
        parent = _resolve_parent_at_commit(db, target, mapped)
        record = LivestockVaccinationRecord(
            livestock_id=parent.id,
            vaccine=str(mapped["vaccine"]).strip(),
            date_administered=mapped["date_administered"],
            next_due=mapped.get("next_due"),
            status=_optional_text(mapped.get("status")) or "Up to Date",
            administered_by=_optional_text(mapped.get("administered_by")),
            notes=_optional_text(mapped.get("notes")),
            recorded_by_user_id=current_user.id,
        )
    elif target == "Livestock Reproduction":
        parent = _resolve_parent_at_commit(db, target, mapped)
        record = LivestockReproductionRecord(
            livestock_id=parent.id,
            record_type=str(mapped["record_type"]).strip(),
            event_date=mapped["event_date"],
            partner_reference=_optional_text(mapped.get("partner_reference")),
            breeding_method=_optional_text(mapped.get("breeding_method")),
            reproductive_status=_optional_text(mapped.get("reproductive_status")),
            expected_date=mapped.get("expected_date"),
            actual_date=mapped.get("actual_date"),
            offspring_count=int(mapped.get("offspring_count") or 0),
            alive_offspring=int(mapped.get("alive_offspring") or 0),
            male_offspring=mapped.get("male_offspring"),
            female_offspring=mapped.get("female_offspring"),
            loss_count=int(mapped.get("loss_count") or 0),
            notes=_optional_text(mapped.get("notes")),
            recorded_by_user_id=current_user.id,
        )
    elif target == "Livestock Production":
        parent = _resolve_parent_at_commit(db, target, mapped)
        payload = ProductionCreate(
            livestock_id=parent.id,
            output_type=str(mapped["output_type"]).strip(),
            record_date=mapped["record_date"],
            period_start_date=mapped.get("period_start_date"),
            period_end_date=mapped.get("period_end_date"),
            quantity=mapped["quantity"],
            unit=str(mapped["unit"]).strip(),
            quality_grade=_optional_text(mapped.get("quality_grade")),
            destination=_optional_text(mapped.get("destination_use")),
            track_sale_inventory=bool(mapped.get("track_sale_inventory")),
            notes=_optional_text(mapped.get("notes")),
        )
        result = create_production(db, payload, current_user)
        record = db.get(LivestockProductionRecord, int(result["id"]))
        if record is None:
            raise ValueError("The production record could not be loaded after creation.")
        return record
    elif target == "Livestock Processing":
        parent = _resolve_parent_at_commit(db, target, mapped)
        payload = ProcessingCreate(
            livestock_id=parent.id,
            processing_date=mapped["processing_date"],
            animals_processed=int(mapped["animals_processed"]),
            male_quantity=int(mapped.get("male_quantity") or 0),
            female_quantity=int(mapped.get("female_quantity") or 0),
            unknown_quantity=int(mapped.get("unknown_quantity") or 0),
            live_weight_kg=mapped.get("live_weight_kg"),
            meat_output_kg=mapped["meat_output_kg"],
            quality_grade=_optional_text(mapped.get("quality_grade")),
            destination=_optional_text(mapped.get("destination_use")),
            notes=_optional_text(mapped.get("notes")),
        )
        result = create_processing(db, payload, current_user)
        record = db.get(LivestockProcessingRecord, int(result["id"]))
        if record is None:
            raise ValueError("The processing record could not be loaded after creation.")
        return record
    elif target == "Sales":
        parent = _resolve_parent_at_commit(db, target, mapped)
        sale_type = str(mapped.get("sale_type") or "").strip().title()
        production = None
        product_type = _optional_text(mapped.get("product_type"))
        production_record_id = None
        if sale_type == "Product":
            production = _resolve_sale_production_record(db, mapped, parent.id)
            production_record_id = production.id
            product_type = product_type or production.output_type

        requested_sale_code = _optional_text(mapped.get("sale_code"))
        if requested_sale_code:
            existing_code = db.scalar(
                select(LivestockSale.id).where(
                    func.lower(LivestockSale.sale_code) == requested_sale_code.lower()
                )
            )
            if existing_code:
                raise ValueError(f"Sale Code {requested_sale_code} already exists.")

        payload = SaleCreate(
            sale_type=sale_type,
            livestock_id=parent.id,
            production_record_id=production_record_id,
            sale_date=mapped["sale_date"],
            product_type=product_type or parent.record_name,
            quantity=mapped["quantity"],
            unit=str(mapped["unit"]).strip(),
            unit_price=mapped["unit_price"],
            buyer_name=_optional_text(mapped.get("buyer_name")),
            payment_status=_optional_text(mapped.get("payment_status")) or "Paid",
            payment_method=_optional_text(mapped.get("payment_method")),
            amount_paid=mapped.get("amount_paid"),
            male_quantity=int(mapped.get("male_quantity") or 0),
            female_quantity=int(mapped.get("female_quantity") or 0),
            unknown_quantity=int(mapped.get("unknown_quantity") or 0),
            notes=_optional_text(mapped.get("notes")),
        )
        result = create_sale(db, payload, current_user)
        record = db.get(LivestockSale, int(result["id"]))
        if record is None:
            raise ValueError("The sale transaction could not be loaded after creation.")
        if requested_sale_code and requested_sale_code.lower() != record.sale_code.lower():
            record.sale_code = requested_sale_code
            db.flush()
        return record
    else:
        raise ValueError(f"Unsupported import target: {target}")

    db.add(record)
    db.flush()
    if target == "Crop Yield":
        crop = db.get(Crop, record.crop_id)
        if crop is None:
            raise ValueError("The crop linked to this yield record no longer exists.")
        create_crop_production_from_yield(
            db,
            record,
            crop,
            current_user,
        )
    if target == "Livestock":
        db.add(
            LivestockTransaction(
                livestock_id=record.id,
                transaction_type="Imported",
                quantity=record.quantity,
                to_livestock_id=record.id,
                to_pen_id=record.pen_id,
                event_date=record.date_acquired,
                reason="Created by Smart Import.",
                recorded_by_user_id=current_user.id,
            )
        )
        db.flush()
    return record


def _update_record(
    db: Session,
    record: Any,
    target: str,
    mapped: dict[str, Any],
    mapping: dict[str, str | None],
):
    if getattr(record, "is_archived", False):
        raise ValueError("Archived records are read-only. Restore the record before importing changes.")
    if mapped.get("is_archived"):
        raise ValueError("Use the Archive action and provide an archive reason.")
    if target == "Livestock Pen":
        # Pen name is the stable import identity. Rename pens from Manage Pens so
        # linked livestock display names are updated deliberately.
        fields = [field for field in MODEL_FIELDS[target] if field not in {"name", "is_archived"}]
    elif target == "Crop":
        fields = [field for field in MODEL_FIELDS[target] if field != "crop_code"]
    elif target == "Livestock":
        fields = [
            field for field in MODEL_FIELDS[target]
            if field not in {"animal_code", "pen_location", "feed_type"}
        ]
    elif target == "Inventory":
        fields = [field for field in MODEL_FIELDS[target] if field != "item_code"]
    else:
        fields = [field for field in MODEL_FIELDS[target] if not field.endswith("_id")]

    for field in fields:
        # Update only columns that the user actually mapped from the source file.
        # This prevents an omitted optional column from overwriting an existing
        # database value with a default or blank value.
        source_field = field
        if target == "Livestock Production" and field == "destination":
            source_field = "destination_use"
        if not mapping.get(source_field):
            continue
        if source_field in mapped:
            setattr(record, field, mapped[source_field])

    if target == "Livestock Pen":
        occupied = int(
            db.scalar(
                select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
                    Livestock.pen_id == record.id,
                    Livestock.is_archived == False,
                    Livestock.lifecycle_status == "Active",
                )
            )
            or 0
        )
        if record.capacity is not None and int(record.capacity) < occupied:
            raise ValueError(
                f"Capacity cannot be lower than the current occupancy of {occupied} animal(s)."
            )
        if record.status in {"Closed", "Inactive"} and occupied > 0:
            raise ValueError("Move all active livestock out of this pen before closing or deactivating it.")
        allowed_type = _normalize_livestock_category(record.animal_type)
        if occupied > 0 and allowed_type and allowed_type not in {"all", "all livestock", "any"}:
            mismatched = db.scalar(
                select(Livestock.id).where(
                    Livestock.pen_id == record.id,
                    Livestock.is_archived == False,
                    Livestock.lifecycle_status == "Active",
                    func.lower(Livestock.animal_type) != str(record.animal_type).lower(),
                ).limit(1)
            )
            if mismatched:
                raise ValueError(
                    "Animal Type cannot be changed because active livestock in this pen use a different type."
                )
        record.is_archived = False

    if target == "Livestock Growth":
        livestock = db.get(Livestock, record.livestock_id)
        if livestock is not None:
            db.flush()
            _recalculate_import_growth_history(db, livestock)

    if target == "Livestock":
        # Keep aggregate composition internally consistent when Smart Import updates
        # an existing batch. Quantity changes also carry the validated breakdown.
        sex_breakdown_mapped = any(
            mapping.get(field) for field in ("male_quantity", "female_quantity", "unknown_sex_quantity")
        )
        health_breakdown_mapped = any(
            mapping.get(field)
            for field in ("healthy_quantity", "at_risk_quantity", "sick_quantity", "under_treatment_quantity")
        )
        if mapping.get("quantity") or mapping.get("sex") or sex_breakdown_mapped:
            record.sex = mapped["sex"]
            record.male_quantity = int(mapped.get("male_quantity") or 0)
            record.female_quantity = int(mapped.get("female_quantity") or 0)
            record.unknown_sex_quantity = int(mapped.get("unknown_sex_quantity") or 0)
        if mapping.get("quantity") or mapping.get("health_status") or health_breakdown_mapped:
            record.health_status = mapped["health_status"]
            record.healthy_quantity = int(mapped.get("healthy_quantity") or 0)
            record.at_risk_quantity = int(mapped.get("at_risk_quantity") or 0)
            record.sick_quantity = int(mapped.get("sick_quantity") or 0)
            record.under_treatment_quantity = int(mapped.get("under_treatment_quantity") or 0)
        if mapping.get("weight_kg"):
            if not mapping.get("min_weight_kg"):
                record.min_weight_kg = mapped.get("min_weight_kg") or mapped.get("weight_kg")
            if not mapping.get("max_weight_kg"):
                record.max_weight_kg = mapped.get("max_weight_kg") or mapped.get("weight_kg")

        # Pen changes and quantity changes must obey the same capacity/type rules
        # used by manual livestock entry.
        new_quantity = int(mapped.get("quantity") or record.quantity) if mapping.get("quantity") else int(record.quantity)
        new_animal_type = str(mapped.get("animal_type") or record.animal_type) if mapping.get("animal_type") else str(record.animal_type)
        if mapping.get("pen_location"):
            pen = _get_import_pen_or_raise(
                db,
                str(mapped.get("pen_location") or ""),
                new_animal_type,
                new_quantity,
                exclude_livestock_id=record.id,
            )
            record.pen_id = pen.id
            record.pen_location = pen.name
        elif mapping.get("quantity") or mapping.get("animal_type"):
            pen = _get_import_pen_or_raise(
                db,
                str(record.pen_location),
                new_animal_type,
                new_quantity,
                exclude_livestock_id=record.id,
            )
            record.pen_id = pen.id
            record.pen_location = pen.name

        feed_mapping_present = any(
            mapping.get(field)
            for field in ("inventory_item_code", "inventory_item_name", "feed_type")
        )
        schedule_mapping_present = any(
            mapping.get(field) for field in ("daily_feed_kg", "feed_times")
        )
        if feed_mapping_present:
            feed_item = _resolve_feed_inventory_item(db, mapped, required=True)
            record.feed_inventory_item_id = feed_item.id
            record.feed_type = feed_item.name
        elif schedule_mapping_present:
            scheduled_amount = float(mapped.get("daily_feed_kg") or record.daily_feed_kg or 0)
            scheduled_times = _optional_text(mapped.get("feed_times")) if mapping.get("feed_times") else _optional_text(record.feed_times)
            if (scheduled_amount > 0 or scheduled_times) and record.feed_inventory_item_id is None:
                raise ValueError(
                    "This livestock feeding schedule needs an exact Feed Inventory item. Map Inventory Item Code / Inventory Feed Item."
                )

    if (
        target == "Crop"
        and mapping.get("planting_date")
        and mapping.get("estimated_harvest")
        and mapped.get("planting_date")
        and mapped.get("estimated_harvest")
    ):
        progress, status_value = _crop_progress(
            mapped["planting_date"],
            mapped["estimated_harvest"],
        )
        record.current_growth = progress
        if getattr(record, "status", None) not in {"Harvested", "Failed"}:
            record.growth_stage = stage_for_progress(progress)
            record.status = status_value


def _get_record_by_id(db: Session, target: str, record_id: int):
    model = TARGET_MODELS[target]
    return db.get(model, record_id)


def _commit_sort_key(row: DataImportRow) -> tuple[int, int]:
    # Dependencies are explicit so sheet order does not control correctness.
    if row.target_type == "Livestock Pen":
        return (0, row.id)
    if row.target_type in {"Crop", "Inventory"}:
        return (1, row.id)
    if row.target_type == "Livestock":
        return (2, row.id)
    if row.target_type == "Livestock Processing":
        return (4, row.id)
    if row.target_type == "Sales":
        return (5, row.id)
    return (3, row.id)


def commit_batch(
    db: Session,
    batch: DataImportBatch,
    *,
    current_user: User,
    row_actions: dict[int, str],
    force_exact_duplicate: bool = False,
) -> dict[str, Any]:
    if batch.status not in {"Previewed", "Reviewed"}:
        raise ValueError("This import batch is no longer pending.")

    admin = is_admin(current_user)
    other_completed = db.scalar(
        select(DataImportBatch)
        .where(
            DataImportBatch.file_hash_sha256 == batch.file_hash_sha256,
            DataImportBatch.status == "Completed",
            DataImportBatch.id != batch.id,
        )
        .order_by(DataImportBatch.id.desc())
        .limit(1)
    )
    forced_preview = bool(
        batch.notes
        and batch.notes.startswith("Forced preview of a previously imported file fingerprint.")
    )
    duplicate_force_allowed = force_exact_duplicate or forced_preview
    if other_completed and not duplicate_force_allowed:
        raise PermissionError(
            f"This exact file was already imported as {other_completed.batch_code}."
        )
    if other_completed and duplicate_force_allowed and not admin:
        raise PermissionError("Only an administrator can force re-import an exact duplicate file.")

    if batch.total_rows > LARGE_IMPORT_THRESHOLD and not admin:
        raise PermissionError(
            f"Imports larger than {LARGE_IMPORT_THRESHOLD} rows require a System Administrator."
        )

    # A large Smart Import writes across crops, inventory, livestock, histories,
    # sales, activities, and alerts in one transaction. Hold a transaction-level
    # application lock so the background automation scheduler skips its cycle
    # instead of scanning the same tables and deadlocking with this commit.
    acquire_transaction_lock(
        db,
        SMART_IMPORT_AUTOMATION_GUARD,
        timeout_ms=120000,
    )

    rows = list(batch.rows)
    auto_new_row_ids: set[int] = set()
    for row in rows:
        explicit_action = row_actions.get(row.id)

        # New validated rows should be imported automatically. Duplicate
        # rows stay on the safer default action of skip unless reviewed.
        if explicit_action is None and row.duplicate_status == "New":
            action = "new"
            auto_new_row_ids.add(row.id)
        else:
            action = explicit_action or row.requested_action or "skip"

        if action not in {"skip", "update", "new"}:
            action = "skip"
        if row.target_type == "Resource Usage" and action == "update":
            raise ValueError(
                "Resource Usage is historical utilization data and cannot be updated in place by Smart Import. "
                "Skip the duplicate or import a corrected row as new, then manage the old usage record from Resource Usage if needed."
            )
        if row.target_type in {"Livestock Production", "Livestock Processing", "Sales"} and action == "update":
            raise ValueError(
                f"{row.target_type} records are transactional history and cannot be updated in place by Smart Import. "
                "Skip the duplicate or import a new record; use the Production & Sales correction/void workflow when applicable."
            )
        row.requested_action = action
        if row.duplicate_status != "New" and action in {"update", "new"} and not admin:
            raise PermissionError("Updating existing records or keeping duplicates as new requires a System Administrator.")

    imported = updated = skipped = errors = 0
    batch.status = "Importing"
    db.flush()

    # Master data and dependencies first, independent of workbook tab order.
    ordered_rows = sorted(rows, key=_commit_sort_key)

    try:
        for row in ordered_rows:
            if row.status not in {"Ready"}:
                row.status = "Skipped"
                skipped += 1
                continue

            mapped = _typed_mapped(row.target_type, _json_load(row.mapped_json, {}))
            mapping = _json_load(row.mapping_json, {})
            action = row.requested_action

            # Re-check duplicate against live database state immediately before write.
            if row.target_type in ROOT_TARGETS:
                existing, duplicate_status = _find_base_duplicate(db, row.target_type, mapped)
            else:
                try:
                    parent = _resolve_parent_at_commit(db, row.target_type, mapped)
                    if getattr(parent, "is_archived", False):
                        raise ValueError("The linked source is archived. Restore it before importing new history.")
                    existing, duplicate_status = _find_child_duplicate(db, row.target_type, mapped, parent.id)
                except ValueError as exc:
                    row.status = "Error"
                    row.error_message = str(exc)
                    errors += 1
                    continue

            if existing:
                row.existing_record_id = existing.id
                row.duplicate_status = duplicate_status

                # A row that was new during preview may become a duplicate
                # before commit (or duplicate another row in the same file).
                # Skip it safely unless the user explicitly chose an action.
                if row.id in auto_new_row_ids:
                    row.status = "Skipped"
                    row.result_record_id = existing.id
                    skipped += 1
                    continue

                if action == "skip":
                    row.status = "Skipped"
                    row.result_record_id = existing.id
                    skipped += 1
                    continue
                if row.target_type == "Livestock Pen" and action == "new":
                    row.status = "Error"
                    row.error_message = (
                        "Livestock Pen names must be unique. Rename the pen in the workbook, "
                        "or choose Update/Skip for the existing pen."
                    )
                    errors += 1
                    continue
                if action == "update":
                    try:
                        with db.begin_nested():
                            row.before_json = _json_dump(_serialize_model(existing, row.target_type))
                            _update_record(db, existing, row.target_type, mapped, mapping)
                            db.flush()
                            if row.target_type == "Crop Yield":
                                crop = db.get(Crop, existing.crop_id)
                                if crop is None:
                                    raise ValueError("The crop linked to this yield record no longer exists.")
                                create_crop_production_from_yield(
                                    db,
                                    existing,
                                    crop,
                                    current_user,
                                )
                            row.after_json = _json_dump(_serialize_model(existing, row.target_type))
                            row.result_record_id = existing.id
                            row.status = "Updated"
                    except Exception as exc:
                        row.status = "Error"
                        row.error_message = str(exc)
                        errors += 1
                        continue
                    updated += 1
                    continue
                # action == new. Base codes must be regenerated when there is a collision.
                # Sales corrections are append-only: a duplicate kept as new receives
                # a fresh transaction code instead of reusing the source code.
                if row.target_type == "Sales":
                    mapped["sale_code"] = None
                    row.generated_code = "Auto-generated sale code"
                    row.mapped_json = _json_dump(mapped)
                if row.target_type in BASE_TARGETS:
                    new_code = _ensure_code_available(db, row.target_type, mapped)
                    if row.target_type == "Crop":
                        mapped["crop_code"] = new_code
                    elif row.target_type == "Livestock":
                        mapped["animal_code"] = new_code
                    else:
                        mapped["item_code"] = new_code
                    row.generated_code = new_code
                    row.mapped_json = _json_dump(mapped)

            # For brand-new base records, confirm provided/generated code is still unique.
            if row.target_type in BASE_TARGETS and not existing:
                if row.target_type == "Crop":
                    code_key = "crop_code"
                elif row.target_type == "Livestock":
                    code_key = "animal_code"
                else:
                    code_key = "item_code"
                safe_code = _ensure_code_available(db, row.target_type, mapped)
                if safe_code != mapped.get(code_key):
                    mapped[code_key] = safe_code
                    row.generated_code = safe_code
                    row.mapped_json = _json_dump(mapped)

            try:
                with db.begin_nested():
                    record = _create_record(db, row.target_type, mapped, current_user)
                    db.flush()
                    row.result_record_id = record.id
                    row.after_json = _json_dump(_serialize_model(record, row.target_type))
                    row.status = "Imported"
                imported += 1
            except Exception as exc:
                row.status = "Error"
                row.error_message = str(exc)
                errors += 1

        batch.imported_rows = imported
        batch.updated_rows = updated
        batch.skipped_rows = skipped
        batch.error_rows = errors
        batch.status = "Completed"
        batch.completed_at = datetime.now()
        batch.notes = (
            f"Import completed with {imported} new, {updated} updated, "
            f"{skipped} skipped, and {errors} error row(s)."
        )

        successful_rows = [
            row for row in rows if row.status in {"Imported", "Updated"}
        ]
        if any(
            row.target_type in {"Livestock Reproduction", "Livestock Production", "Livestock Processing", "Sales"}
            for row in successful_rows
        ):
            evaluate_automatic_tasks(db, commit=False)
        if any(
            row.target_type == "Livestock Processing"
            or (
                row.target_type == "Sales"
                and str(_json_load(row.mapped_json, {}).get("sale_type") or "").strip().lower() == "live animal"
            )
            for row in successful_rows
        ):
            evaluate_livestock_alerts_only(db, commit=False)

        db.commit()
        db.refresh(batch)
    except Exception:
        db.rollback()
        raise

    return {
        "batch": batch_summary(db, batch),
        "message": batch.notes or "Import completed.",
    }


def list_history(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    batches = list(
        db.scalars(
            select(DataImportBatch)
            .where(DataImportBatch.status.in_(["Completed", "Rolled Back", "Failed", "Previewed", "Reviewed"]))
            .order_by(DataImportBatch.id.desc())
            .limit(max(1, min(limit, 100)))
        ).all()
    )
    return [batch_summary(db, batch) for batch in batches]


def build_error_csv(batch: DataImportBatch) -> str:
    output = io.StringIO(newline="")
    writer = SafeCsvWriter(csv.writer(output))
    writer.writerow([
        "Batch Code", "Sheet", "Row", "Detected Type", "Target Type",
        "Status", "Duplicate Status", "Generated Code", "Errors / Reason", "Source Data",
    ])
    for row in batch.rows:
        validation_errors = _json_load(row.validation_errors_json, [])
        if row.status not in {"Invalid", "Unsupported", "Error"} and not validation_errors:
            continue
        reason_parts = list(validation_errors)
        if row.error_message:
            reason_parts.append(row.error_message)
        writer.writerow([
            batch.batch_code,
            row.sheet_name,
            row.row_number,
            row.detected_type,
            row.target_type,
            row.status,
            row.duplicate_status,
            row.generated_code or "",
            " | ".join(reason_parts),
            _json_dump(_json_load(row.source_json, {})),
        ])
    return output.getvalue()


def _restore_model_fields(record: Any, target: str, snapshot: dict[str, Any]):
    date_fields = {
        "Crop": {"planting_date", "estimated_harvest", "fertilizer_date"},
        "Livestock": {"date_of_birth", "last_checkup", "next_vaccination", "date_acquired"},
        "Livestock Growth": {"measurement_date"},
        "Livestock Feeding": {"feeding_date"},
        "Resource Usage": {"usage_date"},
        "Inventory": {"date_acquired", "expiration_date"},
        "Crop Yield": {"harvest_date"},
        "Vaccination": {"date_administered", "next_due"},
        "Livestock Reproduction": {"event_date", "expected_date", "actual_date"},
        "Livestock Production": {"record_date", "period_start_date", "period_end_date"},
        "Livestock Processing": {"processing_date"},
        "Sales": {"sale_date"},
    }.get(target, set())
    for field in MODEL_FIELDS[target]:
        if field not in snapshot or not hasattr(record, field):
            continue
        value = snapshot[field]
        if field in date_fields and isinstance(value, str) and value:
            value = _parse_date(value)
        setattr(record, field, value)


def _current_snapshot_matches(record: Any, target: str, expected: dict[str, Any]) -> bool:
    current = _serialize_model(record, target)
    # JSON round-trip normalizes Decimal/date types. Compare only keys captured in expected.
    for key, expected_value in expected.items():
        if key in current and current[key] != expected_value:
            return False
    return True


def _external_dependencies_exist(db: Session, target: str, record_id: int, imported_record_ids: dict[str, set[int]]) -> str | None:
    if target == "Livestock Pen":
        livestock_ids = set(
            db.scalars(select(Livestock.id).where(Livestock.pen_id == record_id)).all()
        )
        if livestock_ids - imported_record_ids.get("Livestock", set()):
            return "This imported pen now contains livestock records that were not created by the same import batch."

    elif target == "Crop":
        # Only yield records are imported by Smart Import. Growth/pest records are
        # operational records created elsewhere and must prevent destructive rollback.
        from app.models import CropGrowthRecord, CropPestDisease
        growth = db.scalar(select(CropGrowthRecord.id).where(CropGrowthRecord.crop_id == record_id).limit(1))
        pest = db.scalar(select(CropPestDisease.id).where(CropPestDisease.crop_id == record_id).limit(1))
        if growth or pest:
            return "This imported crop now has growth or pest/disease records that were created outside the import batch."
        yield_ids = set(db.scalars(select(CropYieldRecord.id).where(CropYieldRecord.crop_id == record_id)).all())
        usage_ids = set(db.scalars(select(ResourceUsage.id).where(ResourceUsage.crop_id == record_id)).all())
        if yield_ids - imported_record_ids.get("Crop Yield", set()):
            return "This imported crop now has additional yield records created after the import."
        if usage_ids - imported_record_ids.get("Resource Usage", set()):
            return "This imported crop now has resource-usage records created after the import."

    elif target == "Livestock":
        growth_ids = set(db.scalars(select(LivestockGrowthRecord.id).where(LivestockGrowthRecord.livestock_id == record_id)).all())
        feeding_ids = set(db.scalars(select(LivestockFeedingRecord.id).where(LivestockFeedingRecord.livestock_id == record_id)).all())
        vacc_ids = set(db.scalars(select(LivestockVaccinationRecord.id).where(LivestockVaccinationRecord.livestock_id == record_id)).all())
        repro_ids = set(db.scalars(select(LivestockReproductionRecord.id).where(LivestockReproductionRecord.livestock_id == record_id)).all())
        prod_ids = set(db.scalars(select(LivestockProductionRecord.id).where(LivestockProductionRecord.livestock_id == record_id)).all())
        processing_ids = set(db.scalars(select(LivestockProcessingRecord.id).where(LivestockProcessingRecord.livestock_id == record_id)).all())
        usage_ids = set(db.scalars(select(ResourceUsage.id).where(ResourceUsage.livestock_id == record_id)).all())
        if growth_ids - imported_record_ids.get("Livestock Growth", set()):
            return "This imported livestock record now has additional growth measurements created after the import."
        if feeding_ids - imported_record_ids.get("Livestock Feeding", set()):
            return "This imported livestock record now has additional feeding records created after the import."
        if vacc_ids - imported_record_ids.get("Vaccination", set()):
            return "This imported livestock record now has additional vaccination records created after the import."
        if repro_ids - imported_record_ids.get("Livestock Reproduction", set()):
            return "This imported livestock record now has additional reproduction records created after the import."
        if prod_ids - imported_record_ids.get("Livestock Production", set()):
            return "This imported livestock record now has additional production records created after the import."
        if processing_ids - imported_record_ids.get("Livestock Processing", set()):
            return "This imported livestock record now has additional processing records created after the import."
        if usage_ids - imported_record_ids.get("Resource Usage", set()):
            return "This imported livestock record now has resource-usage records created after the import."

        movement_id = db.scalar(
            select(LivestockTransaction.id).where(
                or_(
                    LivestockTransaction.livestock_id == record_id,
                    LivestockTransaction.from_livestock_id == record_id,
                    LivestockTransaction.to_livestock_id == record_id,
                ),
                LivestockTransaction.transaction_type != "Imported",
            ).limit(1)
        )
        if movement_id:
            return "This imported livestock record now has movement or population history created after the import."

    elif target == "Inventory":
        from app.models import InventoryStockRecord
        stock_id = db.scalar(select(InventoryStockRecord.id).where(InventoryStockRecord.inventory_item_id == record_id).limit(1))
        usage_ids = set(db.scalars(select(ResourceUsage.id).where(ResourceUsage.inventory_item_id == record_id)).all())
        if stock_id:
            return "This imported inventory item now has stock-history records. Rollback would risk removing later inventory activity."
        if usage_ids - imported_record_ids.get("Resource Usage", set()):
            return "This imported inventory item now has resource-usage history created after the import."
    return None


def rollback_batch(
    db: Session,
    batch: DataImportBatch,
    *,
    current_user: User,
    force: bool = False,
) -> dict[str, Any]:
    if not is_admin(current_user):
        raise PermissionError("Only a System Administrator can rollback an import batch.")
    if batch.status != "Completed":
        raise ValueError("Only a completed import batch can be rolled back.")

    if any(
        row.target_type in {"Sales", "Livestock Processing"}
        and row.status in {"Imported", "Updated"}
        for row in batch.rows
    ):
        raise ValueError(
            "Import batches containing Sales or Livestock Processing records are not rolled back destructively. "
            "Use Void Sale or Void Processing from Production & Sales so livestock and product quantities are restored safely."
        )

    rows = [row for row in batch.rows if row.status in {"Imported", "Updated"}]
    imported_record_ids: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row.status == "Imported" and row.result_record_id:
            imported_record_ids[row.target_type].add(row.result_record_id)

    # Safety checks before modifying anything.
    for row in rows:
        if not row.result_record_id:
            continue
        record = _get_record_by_id(db, row.target_type, row.result_record_id)
        if record is None:
            if row.status == "Imported":
                continue
            raise ValueError(f"Updated {row.target_type} record {row.result_record_id} no longer exists.")
        if row.status == "Updated" and not force:
            after = _json_load(row.after_json, {})
            if after and not _current_snapshot_matches(record, row.target_type, after):
                raise PermissionError(
                    f"Cannot safely rollback {row.target_type} record {row.result_record_id} because it changed after this import."
                )
        if row.status == "Imported" and row.target_type in ROOT_TARGETS:
            dependency_error = _external_dependencies_exist(
                db, row.target_type, row.result_record_id, imported_record_ids
            )
            if dependency_error:
                raise PermissionError(dependency_error)

    # Child records must be removed/restored before parents.
    # Track growth parents so deleting/restoring imported measurements also
    # restores the derived growth chain and the livestock batch's latest weight.
    growth_parent_ids: set[int] = set()
    for row in rows:
        if row.target_type != "Livestock Growth" or not row.result_record_id:
            continue
        growth_record = _get_record_by_id(db, row.target_type, row.result_record_id)
        if growth_record is not None and getattr(growth_record, "livestock_id", None):
            growth_parent_ids.add(int(growth_record.livestock_id))

    def _rollback_sort_key(row: DataImportRow) -> tuple[int, int]:
        if row.target_type in CHILD_TARGETS:
            return (0, -row.id)
        if row.target_type == "Livestock":
            return (1, -row.id)
        if row.target_type == "Livestock Pen":
            return (2, -row.id)
        return (1, -row.id)

    ordered = sorted(rows, key=_rollback_sort_key)
    for row in ordered:
        if not row.result_record_id:
            continue
        record = _get_record_by_id(db, row.target_type, row.result_record_id)
        if row.status == "Imported":
            if record is not None:
                if row.target_type == "Livestock":
                    db.execute(
                        delete(LivestockTransaction).where(
                            or_(
                                LivestockTransaction.livestock_id == record.id,
                                LivestockTransaction.from_livestock_id == record.id,
                                LivestockTransaction.to_livestock_id == record.id,
                            ),
                            LivestockTransaction.transaction_type == "Imported",
                        )
                    )
                db.delete(record)
        else:
            if record is None:
                raise ValueError(f"Updated {row.target_type} record {row.result_record_id} no longer exists.")
            before = _json_load(row.before_json, {})
            _restore_model_fields(record, row.target_type, before)
        row.status = "Rolled Back"

    if growth_parent_ids:
        db.flush()
        for livestock_id in sorted(growth_parent_ids):
            livestock = db.get(Livestock, livestock_id)
            if livestock is not None:
                _recalculate_import_growth_history(db, livestock)

    batch.status = "Rolled Back"
    batch.rolled_back_at = datetime.now()
    batch.rollback_by_user_id = current_user.id
    batch.notes = f"Import batch rolled back by {current_user.full_name}."
    db.commit()
    db.refresh(batch)
    return {
        "batch": batch_summary(db, batch),
        "message": f"{batch.batch_code} was rolled back successfully.",
    }
