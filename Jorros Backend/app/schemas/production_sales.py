from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class ReproductionCreate(BaseModel):
    livestock_id: int = Field(ge=1)
    record_type: str = Field(min_length=1, max_length=40)
    event_date: date
    partner_reference: str | None = Field(default=None, max_length=150)
    breeding_method: str | None = Field(default=None, max_length=50)
    breeder_male_quantity: int = Field(default=0, ge=0)
    breeder_female_quantity: int = Field(default=0, ge=0)
    confirmed_pregnant_quantity: int = Field(default=0, ge=0)
    eggs_set: int = Field(default=0, ge=0)
    fertile_eggs: int = Field(default=0, ge=0)
    incubation_method: str | None = Field(default=None, max_length=50)
    reproductive_status: str | None = Field(default=None, max_length=60)
    expected_date: date | None = None
    actual_date: date | None = None
    offspring_count: int = Field(default=0, ge=0)
    alive_offspring: int = Field(default=0, ge=0)
    male_offspring: int | None = Field(default=None, ge=0)
    female_offspring: int | None = Field(default=None, ge=0)
    loss_count: int = Field(default=0, ge=0)
    source_production_record_id: int | None = Field(default=None, ge=1)
    notes: str | None = None

    create_offspring_record: bool = False
    offspring_record_name: str | None = Field(default=None, max_length=120)
    offspring_average_weight_kg: float | None = Field(default=None, gt=0)
    offspring_pen_id: int | None = Field(default=None, ge=1)
    offspring_pen_location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_values(self):
        if self.expected_date and self.expected_date < self.event_date:
            raise ValueError("Expected date cannot be earlier than the event date.")
        if self.actual_date and self.actual_date < self.event_date:
            raise ValueError("Actual date cannot be earlier than the event date.")
        if self.alive_offspring > self.offspring_count:
            raise ValueError("Alive offspring cannot exceed total offspring.")
        sex_total = int(self.male_offspring or 0) + int(self.female_offspring or 0)
        if sex_total > self.alive_offspring:
            raise ValueError("Male and female offspring cannot exceed alive offspring.")
        if self.loss_count > self.offspring_count:
            raise ValueError("Loss count cannot exceed total offspring / eggs being evaluated.")
        if self.confirmed_pregnant_quantity > self.breeder_female_quantity:
            raise ValueError("Confirmed pregnant females cannot exceed females bred.")
        if self.fertile_eggs > self.eggs_set:
            raise ValueError("Fertile eggs cannot exceed eggs set for incubation.")
        if self.create_offspring_record:
            if self.alive_offspring <= 0:
                raise ValueError("Alive offspring must be greater than zero to create an offspring record.")
            if not self.offspring_average_weight_kg:
                raise ValueError("Average offspring weight is required when creating the offspring livestock record.")
            if self.offspring_pen_id is None:
                raise ValueError("Choose an offspring destination pen before creating the offspring batch.")
        return self


class ReproductionResponse(BaseModel):
    id: int
    livestock_id: int
    livestock_name: str
    animal_code: str
    record_type: str
    event_date: date
    partner_reference: str | None
    breeding_method: str | None
    breeder_male_quantity: int = 0
    breeder_female_quantity: int = 0
    confirmed_pregnant_quantity: int = 0
    eggs_set: int = 0
    fertile_eggs: int = 0
    incubation_method: str | None = None
    reproductive_status: str | None
    expected_date: date | None
    actual_date: date | None
    offspring_count: int
    alive_offspring: int
    male_offspring: int | None
    female_offspring: int | None
    loss_count: int
    source_production_record_id: int | None = None
    notes: str | None
    offspring_livestock_id: int | None = None
    offspring_record_name: str | None = None
    created_at: datetime


class ProductionCreate(BaseModel):
    livestock_id: int = Field(ge=1)
    output_type: str = Field(min_length=1, max_length=60)
    record_date: date
    period_start_date: date | None = None
    period_end_date: date | None = None
    source_active_quantity: int | None = Field(default=None, ge=1)
    gross_quantity: float | None = Field(default=None, ge=0)
    loss_quantity: float | None = Field(default=None, ge=0)
    farm_use_quantity: float = Field(default=0, ge=0)
    reserved_quantity: float = Field(default=0, ge=0)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=30)
    quality_grade: str | None = Field(default=None, max_length=80)
    destination: str | None = Field(default="Available for sale", max_length=80)
    track_sale_inventory: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        start = self.period_start_date or self.record_date
        end = self.period_end_date or self.record_date
        if end < start:
            raise ValueError("Production period end cannot be earlier than the start date.")
        if end > self.record_date:
            raise ValueError("Production period end cannot be later than the record date.")
        gross = self.gross_quantity if self.gross_quantity is not None else self.quantity
        loss = self.loss_quantity or 0
        if loss > gross:
            raise ValueError("Damaged/rejected production cannot exceed gross production.")
        farm_use = self.farm_use_quantity or 0
        reserved = self.reserved_quantity or 0
        allocated = loss + farm_use + reserved
        if allocated > gross:
            raise ValueError("Damaged/rejected, farm use, and reserved quantities cannot exceed gross production.")
        usable = gross - allocated
        if abs(usable - self.quantity) > 0.001:
            raise ValueError("Saleable quantity must equal gross production minus damaged/rejected, farm use, and reserved quantities.")
        return self


class ProductionResponse(BaseModel):
    id: int
    source_type: str = "Livestock"
    source_name: str
    source_code: str
    livestock_id: int | None = None
    livestock_name: str | None = None
    animal_code: str | None = None
    crop_id: int | None = None
    crop_yield_record_id: int | None = None
    output_type: str
    record_date: date
    period_start_date: date | None
    period_end_date: date | None
    production_days: int
    source_head_quantity: int | None
    source_female_quantity: int | None
    source_active_quantity: int | None = None
    gross_quantity: float | None = None
    loss_quantity: float | None = None
    farm_use_quantity: float = 0
    reserved_quantity: float = 0
    laying_rate_percent: float | None
    quantity: float
    sold_quantity: float
    available_quantity: float
    unit: str
    quality_grade: str | None
    destination: str | None
    track_sale_inventory: bool
    notes: str | None
    created_at: datetime


class ProcessingCreate(BaseModel):
    livestock_id: int = Field(ge=1)
    processing_date: date
    animals_processed: int = Field(ge=1)
    male_quantity: int = Field(default=0, ge=0)
    female_quantity: int = Field(default=0, ge=0)
    unknown_quantity: int = Field(default=0, ge=0)
    live_weight_kg: float | None = Field(default=None, gt=0)
    meat_output_kg: float = Field(gt=0)
    quality_grade: str | None = Field(default=None, max_length=80)
    destination: str | None = Field(default="Available for sale", max_length=80)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_processing(self):
        sex_total = self.male_quantity + self.female_quantity + self.unknown_quantity
        if sex_total not in {0, self.animals_processed}:
            raise ValueError("Male + Female + Unknown must equal the number of animals processed.")
        if self.live_weight_kg is not None and self.meat_output_kg > self.live_weight_kg:
            raise ValueError("Meat output cannot exceed total live weight.")
        return self


class ProcessingResponse(BaseModel):
    id: int
    livestock_id: int
    livestock_name: str
    animal_code: str
    production_record_id: int
    processing_date: date
    animals_processed: int
    male_quantity: int
    female_quantity: int
    unknown_quantity: int
    healthy_quantity: int
    live_weight_kg: float | None
    meat_output_kg: float
    yield_percent: float | None
    quality_grade: str | None
    destination: str | None
    notes: str | None
    is_voided: bool
    void_reason: str | None
    voided_at: datetime | None
    created_at: datetime


class ProcessingVoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SaleItemCreate(BaseModel):
    item_kind: str = Field(min_length=1, max_length=30)
    production_record_id: int | None = Field(default=None, ge=1)
    livestock_id: int | None = Field(default=None, ge=1)
    inventory_item_id: int | None = Field(default=None, ge=1)
    quantity: float = Field(gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    unit_price: float = Field(ge=0)
    male_quantity: int = Field(default=0, ge=0)
    female_quantity: int = Field(default=0, ge=0)
    unknown_quantity: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_source(self):
        kind = self.item_kind.strip().lower()
        expected = {
            "production": self.production_record_id,
            "live animal": self.livestock_id,
            "inventory": self.inventory_item_id,
        }
        if kind not in expected:
            raise ValueError("Item type must be Production, Live Animal, or Inventory.")
        if expected[kind] is None:
            raise ValueError(f"A source record is required for {self.item_kind.strip()}.")
        selected = sum(value is not None for value in expected.values())
        if selected != 1:
            raise ValueError("Each sale item must reference exactly one stock source.")
        if kind != "live animal" and (
            self.male_quantity or self.female_quantity or self.unknown_quantity
        ):
            raise ValueError("Sex quantities only apply to live-animal sale items.")
        if kind == "live animal":
            if abs(self.quantity - round(self.quantity)) > 0.000001:
                raise ValueError("Live-animal sale quantity must be a whole number.")
            sex_total = self.male_quantity + self.female_quantity + self.unknown_quantity
            if sex_total not in {0, int(round(self.quantity))}:
                raise ValueError("Sex breakdown must total the live animals on this line.")
        return self


class SaleCreate(BaseModel):
    # Legacy single-line fields remain accepted so imports and older clients do
    # not break. New clients send one or more `items` instead.
    sale_type: str = Field(default="Multi-item", min_length=1, max_length=30)
    livestock_id: int | None = Field(default=None, ge=1)
    crop_id: int | None = Field(default=None, ge=1)
    production_record_id: int | None = Field(default=None, ge=1)
    sale_date: date
    product_type: str | None = Field(default=None, min_length=1, max_length=80)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    unit_price: float | None = Field(default=None, ge=0)
    items: list[SaleItemCreate] = Field(default_factory=list, max_length=30)
    buyer_name: str | None = Field(default=None, max_length=150)
    payment_status: str = Field(default="Paid", max_length=30)
    amount_paid: float | None = Field(default=None, ge=0)
    payment_method: str | None = Field(default=None, max_length=50)
    male_quantity: int = Field(default=0, ge=0)
    female_quantity: int = Field(default=0, ge=0)
    unknown_quantity: int = Field(default=0, ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_sale(self):
        payment_status = self.payment_status.strip().lower()
        if payment_status not in {"paid", "partial", "unpaid"}:
            raise ValueError("Payment Status must be Paid, Partial, or Unpaid.")

        if self.items:
            sources: set[tuple[str, int]] = set()
            for item in self.items:
                kind = item.item_kind.strip().lower()
                source_id = (
                    item.production_record_id
                    if kind == "production"
                    else item.livestock_id
                    if kind == "live animal"
                    else item.inventory_item_id
                )
                key = (kind, int(source_id or 0))
                if key in sources:
                    raise ValueError("The same stock source cannot appear more than once on an invoice.")
                sources.add(key)
            return self

        sale_type = self.sale_type.strip().lower()
        if sale_type not in {"product", "live animal"}:
            raise ValueError("Legacy sale type must be Product or Live Animal.")
        if sale_type == "product" and self.production_record_id is None:
            raise ValueError("A production record is required for a product sale.")
        if sale_type == "live animal":
            if self.livestock_id is None:
                raise ValueError("A livestock record is required for a live-animal sale.")
            if self.quantity is None or abs(self.quantity - round(self.quantity)) > 0.000001:
                raise ValueError("Live-animal sale quantity must be a whole number of animals.")
            if self.male_quantity + self.female_quantity + self.unknown_quantity not in {0, int(round(self.quantity))}:
                raise ValueError("Sex breakdown must total the number of live animals being sold.")
        if self.product_type is None or self.quantity is None or self.unit is None or self.unit_price is None:
            raise ValueError("Product, quantity, unit, and unit price are required for a legacy sale.")
        return self


class SaleItemResponse(BaseModel):
    id: int | None = None
    line_number: int
    item_kind: str
    source_type: str
    production_record_id: int | None = None
    livestock_id: int | None = None
    crop_id: int | None = None
    inventory_item_id: int | None = None
    source_name: str
    source_code: str | None = None
    product_type: str
    quantity: float
    unit: str
    unit_price: float
    line_total: float
    male_quantity: int = 0
    female_quantity: int = 0
    unknown_quantity: int = 0
    healthy_quantity: int = 0


class SaleResponse(BaseModel):
    id: int
    sale_code: str
    sale_type: str
    source_type: str = "Livestock"
    source_name: str
    source_code: str
    livestock_id: int | None = None
    livestock_name: str | None = None
    animal_code: str | None = None
    crop_id: int | None = None
    production_record_id: int | None
    sale_date: date
    product_type: str
    quantity: float
    unit: str
    unit_price: float
    total_amount: float
    amount_paid: float
    balance_due: float
    buyer_name: str | None
    payment_status: str
    payment_method: str | None
    male_quantity: int
    female_quantity: int
    unknown_quantity: int
    healthy_quantity: int
    notes: str | None
    is_voided: bool
    void_reason: str | None
    voided_at: datetime | None
    recorded_by_name: str | None = None
    item_count: int = 1
    source_types: list[str] = Field(default_factory=list)
    items: list[SaleItemResponse] = Field(default_factory=list)
    created_at: datetime


class SalePaymentCreate(BaseModel):
    payment_date: date
    amount: float = Field(gt=0)
    payment_method: str | None = Field(default=None, max_length=50)
    notes: str | None = None


class SalePaymentResponse(BaseModel):
    id: int
    sale_id: int
    payment_date: date
    amount: float
    payment_method: str | None
    notes: str | None
    recorded_by_name: str | None = None
    created_at: datetime


class SalePaymentResult(BaseModel):
    sale: SaleResponse
    payment: SalePaymentResponse


class SaleVoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class OverviewResponse(BaseModel):
    active_livestock: int
    harvest_ready_crops: int = 0
    breeding_records: int
    production_records: int
    processing_records: int
    sales_records: int
    total_revenue: float
    cash_collected: float
    outstanding_balance: float
    livestock_revenue: float = 0
    livestock_cash_collected: float = 0
    livestock_outstanding_balance: float = 0
    crop_revenue: float = 0
    crop_cash_collected: float = 0
    crop_outstanding_balance: float = 0
    eggs_available: float
    meat_available_kg: float
    milk_available_l: float = 0
    crop_available_kg: float = 0
    crop_product_lots: int = 0
    livestock_product_lots: int = 0
    recent_production: list[ProductionResponse]
    recent_sales: list[SaleResponse]
