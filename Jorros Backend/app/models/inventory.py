from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.database import Base


# =========================================================
# INVENTORY ITEM
# =========================================================

class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        Index("ix_inventory_items_active_page", "is_archived", "id"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    item_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    # Added by the resource-usage integration. This keeps the Inventory
    # model aligned with reports, Smart Import, and usage snapshots.
    batch_number: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    # Step 98 feeding confirmation uses thousandths of a kilogram.
    quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    unit: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    reorder_level: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    cost: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    price: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    is_saleable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    supplier: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    date_acquired: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    expiration_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    location: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    stock_history: Mapped[list["InventoryStockRecord"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by=(
            "InventoryStockRecord.adjustment_date.desc(), "
            "InventoryStockRecord.id.desc()"
        ),
    )

    # Required by ResourceUsage.inventory_item back_populates.
    # Resource-usage records are historical records, so they are not
    # delete-orphaned when an inventory record changes state.
    resource_usages = relationship(
        "ResourceUsage",
        back_populates="inventory_item",
    )


# =========================================================
# INVENTORY STOCK HISTORY
# =========================================================

class InventoryStockRecord(Base):
    __tablename__ = "inventory_stock_records"
    __table_args__ = (
        Index(
            "ix_inventory_stock_record_idempotency_key",
            "idempotency_key",
            unique=True,
            mssql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=False,
        index=True,
    )

    # Added by the resource-usage integration so stock movements can be
    # traced to the exact crop/livestock resource-usage record.
    resource_usage_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_usages.id"),
        nullable=True,
        index=True,
    )

    adjustment_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    previous_quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    new_quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    adjustment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    reference: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    supplier: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    # Manual stock changes are protected against duplicate browser retries.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    request_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    item: Mapped["InventoryItem"] = relationship(
        back_populates="stock_history"
    )
