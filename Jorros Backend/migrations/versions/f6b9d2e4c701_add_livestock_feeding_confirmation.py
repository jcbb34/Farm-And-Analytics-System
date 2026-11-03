"""add livestock feeding confirmation

Revision ID: f6b9d2e4c701
Revises: f5c8a3e1b720
Create Date: 2026-08-15 12:26:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6b9d2e4c701"
down_revision: Union[str, Sequence[str], None] = "f5c8a3e1b720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep livestock feed values such as 0.185 kg without rounding to 0.19.
    op.alter_column(
        "livestock",
        "daily_feed_kg",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Numeric(10, 3),
        existing_nullable=False,
    )

    # Inventory feed usage can also require thousandths of a kilogram.
    op.alter_column(
        "inventory_items",
        "quantity",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(12, 3),
        existing_nullable=False,
    )
    op.alter_column(
        "inventory_items",
        "reorder_level",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(12, 3),
        existing_nullable=False,
    )

    for column in ("quantity", "previous_quantity", "new_quantity"):
        op.alter_column(
            "inventory_stock_records",
            column,
            existing_type=sa.Numeric(12, 2),
            type_=sa.Numeric(12, 3),
            existing_nullable=False,
        )

    op.add_column(
        "livestock",
        sa.Column("feed_inventory_item_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_livestock_feed_inventory_item_id"),
        "livestock",
        ["feed_inventory_item_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_livestock_feed_inventory_item_id_inventory_items",
        "livestock",
        "inventory_items",
        ["feed_inventory_item_id"],
        ["id"],
    )

    op.create_table(
        "livestock_feeding_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("feeding_date", sa.Date(), nullable=False),
        sa.Column("feeding_slot", sa.String(length=40), nullable=False),
        sa.Column("scheduled_times", sa.String(length=150), nullable=True),
        sa.Column("feed_type", sa.String(length=150), nullable=False),
        sa.Column("planned_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("actual_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(),
            server_default=sa.text("GETDATE()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "livestock_id",
            "feeding_date",
            "feeding_slot",
            name="uq_livestock_feeding_date_slot",
        ),
    )

    for column in (
        "livestock_id",
        "inventory_item_id",
        "feeding_date",
        "confirmed_at",
    ):
        op.create_index(
            op.f(f"ix_livestock_feeding_records_{column}"),
            "livestock_feeding_records",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "confirmed_at",
        "feeding_date",
        "inventory_item_id",
        "livestock_id",
    ):
        op.drop_index(
            op.f(f"ix_livestock_feeding_records_{column}"),
            table_name="livestock_feeding_records",
        )

    op.drop_table("livestock_feeding_records")

    op.drop_constraint(
        "fk_livestock_feed_inventory_item_id_inventory_items",
        "livestock",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_livestock_feed_inventory_item_id"),
        table_name="livestock",
    )
    op.drop_column("livestock", "feed_inventory_item_id")

    for column in ("quantity", "previous_quantity", "new_quantity"):
        op.alter_column(
            "inventory_stock_records",
            column,
            existing_type=sa.Numeric(12, 3),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )

    op.alter_column(
        "inventory_items",
        "reorder_level",
        existing_type=sa.Numeric(12, 3),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )
    op.alter_column(
        "inventory_items",
        "quantity",
        existing_type=sa.Numeric(12, 3),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )
    op.alter_column(
        "livestock",
        "daily_feed_kg",
        existing_type=sa.Numeric(10, 3),
        type_=sa.Numeric(10, 2),
        existing_nullable=False,
    )
