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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ResourceUsage(Base):
    __tablename__ = "resource_usages"
    __table_args__ = (
        Index(
            "ix_resource_usage_submission",
            "task_submission_id",
            unique=True,
            mssql_where=text("task_submission_id IS NOT NULL"),
            sqlite_where=text("task_submission_id IS NOT NULL"),
        ),
        Index(
            "ix_resource_usage_active_task_posting",
            "activity_id",
            unique=True,
            mssql_where=text("activity_id IS NOT NULL AND task_posting_active = 1"),
            sqlite_where=text("activity_id IS NOT NULL AND task_posting_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=False,
        index=True,
    )

    module: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    crop_id: Mapped[int | None] = mapped_column(
        ForeignKey("crops.id"),
        nullable=True,
        index=True,
    )

    livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
    )

    # Optional link back to the single task/submission that caused this usage.
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("farm_activities.id"), nullable=True, index=True
    )
    task_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_submissions.id"), nullable=True
    )
    task_posting_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"), index=True
    )

    usage_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    unit: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    item_code_snapshot: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    item_name_snapshot: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    category_snapshot: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    batch_number_snapshot: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    basis_value: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    basis_unit: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    usage_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_voided: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    void_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    voided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    recorded_by_user_id: Mapped[int | None] = mapped_column(
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

    inventory_item = relationship("InventoryItem", back_populates="resource_usages")
    crop = relationship("Crop", back_populates="resource_usages")
    livestock = relationship("Livestock", back_populates="resource_usages")
