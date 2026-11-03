from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    field_validator,
)


ALLOWED_STOCK_ADJUSTMENT_TYPES = {
    "Restock",
    "Stock Usage",
    "Damaged",
    "Expired",
    "Lost",
    "Correction",
    "Returned",
    "Set Exact Quantity",
}


class InventoryTextFields(BaseModel):
    @field_validator("name", "category", "unit", "supplier", "location", mode="before", check_fields=False)
    @classmethod
    def normalize_required_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("A nonblank value is required.")
        return value

    @field_validator("batch_number", "description", "notes", mode="before", check_fields=False)
    @classmethod
    def normalize_optional_text(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value


class InventoryCreate(InventoryTextFields):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=80)
    batch_number: str | None = Field(default=None, max_length=80)
    quantity: float = Field(default=0, ge=0)
    unit: str = Field(min_length=1, max_length=40)
    reorder_level: float = Field(default=0, ge=0)
    cost: float = Field(default=0, ge=0)
    price: float = Field(default=0, ge=0)
    is_saleable: bool = False
    supplier: str = Field(min_length=1, max_length=150)
    date_acquired: date
    expiration_date: date | None = None
    location: str = Field(min_length=1, max_length=150)
    description: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_inventory_dates(self):
        if (
            self.expiration_date is not None
            and self.expiration_date < self.date_acquired
        ):
            raise ValueError(
                "Expiration date cannot be earlier than date acquired."
            )

        return self


class InventoryUpdate(InventoryTextFields):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    batch_number: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    reorder_level: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    is_saleable: bool | None = None
    supplier: str | None = Field(default=None, min_length=1, max_length=150)
    date_acquired: date | None = None
    expiration_date: date | None = None
    location: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    notes: str | None = None

    @field_validator(
        "name", "category", "unit", "reorder_level", "cost", "price",
        "supplier", "date_acquired", "location", "is_saleable",
        mode="after",
    )
    @classmethod
    def required_inventory_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value


class InventoryStockAdjustmentCreate(BaseModel):
    adjustment_type: str = Field(min_length=1, max_length=50)
    quantity: float = Field(ge=0)
    adjustment_date: date
    reason: str = Field(min_length=1, max_length=300)
    reference: str | None = Field(default=None, max_length=150)
    supplier: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def validate_adjustment(self):
        if self.adjustment_type not in ALLOWED_STOCK_ADJUSTMENT_TYPES:
            raise ValueError("Invalid stock adjustment type.")

        if (
            self.adjustment_type != "Set Exact Quantity"
            and self.quantity <= 0
        ):
            raise ValueError(
                "Adjustment quantity must be greater than zero."
            )

        return self


class InventoryStockRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inventory_item_id: int
    resource_usage_id: int | None = None
    adjustment_type: str
    quantity: float
    previous_quantity: float
    new_quantity: float
    adjustment_date: date
    reason: str
    reference: str | None = None
    supplier: str | None = None
    recorded_by_user_id: int | None = None
    created_at: datetime


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_code: str
    name: str
    category: str
    batch_number: str | None = None
    quantity: float
    unit: str
    reorder_level: float
    cost: float
    price: float
    is_saleable: bool = False
    supplier: str
    date_acquired: date
    expiration_date: date | None = None
    location: str
    description: str | None = None
    notes: str | None = None
    is_archived: bool
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class InventoryDetailsResponse(InventoryResponse):
    stock_history: list[InventoryStockRecordResponse] = Field(default_factory=list)
