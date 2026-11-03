from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LivestockSale(Base):
    __tablename__ = "livestock_sales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sale_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    sale_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Livestock", server_default=text("'Livestock'"), index=True
    )
    livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"), nullable=True, index=True
    )
    crop_id: Mapped[int | None] = mapped_column(
        ForeignKey("crops.id"), nullable=True, index=True
    )
    production_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock_production_records.id"), nullable=True, index=True
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default=text("0")
    )
    balance_due: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default=text("0")
    )
    buyer_name: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    payment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Paid", server_default=text("'Paid'"), index=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    male_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    female_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    unknown_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    healthy_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_voided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"), index=True
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    items: Mapped[list["LivestockSaleItem"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="LivestockSaleItem.line_number",
    )


class LivestockSaleItem(Base):
    """A stock-affecting line on a farm sale invoice.

    LivestockSale remains the invoice/payment header so existing integrations keep
    working. New transactions use these rows to support mixed crop, livestock,
    meat, egg, and inventory-product invoices without losing source traceability.
    """

    __tablename__ = "livestock_sale_items"
    __table_args__ = (
        UniqueConstraint("sale_id", "line_number", name="uq_sale_item_line"),
        Index("ix_sale_items_sale_source", "sale_id", "source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("livestock_sales.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    production_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock_production_records.id"), nullable=True, index=True
    )
    livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"), nullable=True, index=True
    )
    crop_id: Mapped[int | None] = mapped_column(
        ForeignKey("crops.id"), nullable=True, index=True
    )
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=True, index=True
    )
    inventory_stock_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_stock_records.id"), nullable=True, index=True
    )

    source_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    source_code_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_type: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    male_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    female_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    unknown_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    healthy_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    sale: Mapped[LivestockSale] = relationship(back_populates="items")


class LivestockSalePayment(Base):
    __tablename__ = "livestock_sale_payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("livestock_sales.id"), nullable=False, index=True
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )


class LivestockProcessingRecord(Base):
    __tablename__ = "livestock_processing_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    livestock_id: Mapped[int] = mapped_column(
        ForeignKey("livestock.id"), nullable=False, index=True
    )
    production_record_id: Mapped[int] = mapped_column(
        ForeignKey("livestock_production_records.id"), nullable=False, unique=True, index=True
    )
    processing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    animals_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    male_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    female_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    unknown_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    healthy_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    live_weight_kg: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    meat_output_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    quality_grade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_voided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"), index=True
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
