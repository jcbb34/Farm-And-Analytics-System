from app.core.farm_time import farm_now_naive, farm_today
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


CROP_USAGE_TYPES = {"Seed", "Fertilizer", "Pesticide", "Herbicide", "Other"}
LIVESTOCK_USAGE_TYPES = {"Feed", "Vaccine", "Medicine", "Vitamin / Supplement", "Disinfectant", "Treatment Supply", "Sanitation Supply", "Other"}
RESOURCE_MODULES = {"Crop", "Livestock"}


class ResourceUsageCreate(BaseModel):
    module: str = Field(min_length=1, max_length=20)
    target_id: int = Field(gt=0)
    inventory_item_id: int = Field(gt=0)
    usage_type: str = Field(min_length=1, max_length=40)
    quantity: float = Field(gt=0)
    usage_date: date
    notes: str | None = None

    @model_validator(mode="after")
    def validate_usage_type(self):
        if self.module not in RESOURCE_MODULES:
            raise ValueError("Invalid resource usage module.")

        allowed = CROP_USAGE_TYPES if self.module == "Crop" else LIVESTOCK_USAGE_TYPES
        if self.usage_type not in allowed:
            raise ValueError(
                f"Invalid {self.module.lower()} resource usage type."
            )
        if self.usage_date > farm_today():
            raise ValueError("Resource usage date cannot be in the future.")
        return self


class ResourceUsageUpdate(BaseModel):
    inventory_item_id: int | None = Field(default=None, gt=0)
    usage_type: str | None = Field(default=None, min_length=1, max_length=40)
    quantity: float | None = Field(default=None, gt=0)
    usage_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_usage_date(self):
        if self.usage_date is not None and self.usage_date > farm_today():
            raise ValueError("Resource usage date cannot be in the future.")
        return self


class ResourceUsageResponse(BaseModel):
    id: int
    activity_id: int | None = None
    task_submission_id: int | None = None
    module: str
    target_id: int
    target_name: str
    inventory_item_id: int
    inventory_item_code: str
    inventory_item_name: str
    inventory_category: str
    batch_number: str | None
    basis_value: float | None = None
    basis_unit: str | None = None
    usage_type: str
    quantity: float
    unit: str
    usage_date: date
    notes: str | None
    is_voided: bool
    void_reason: str | None
    available_quantity: float
    efficiency_value: float | None = None
    efficiency_label: str | None = None
    recorded_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class ResourceUsageSummaryRow(BaseModel):
    module: str
    usage_type: str
    unit: str
    quantity: float


class ResourceUsageTopItem(BaseModel):
    inventory_item_id: int
    item_name: str
    unit: str
    quantity: float


class ResourceUsageSummaryResponse(BaseModel):
    start_date: date
    end_date: date
    total_records: int
    totals: list[ResourceUsageSummaryRow]
    top_items: list[ResourceUsageTopItem]
    low_stock_items: int
    expiring_items: int
