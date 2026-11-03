"""add inventory tables

Revision ID: 8b9d3e2f1a77
Revises: 4c6e1d91f204
Create Date: 2026-08-10 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b9d3e2f1a77"
down_revision: Union[str, Sequence[str], None] = "4c6e1d91f204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("reorder_level", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("supplier", sa.String(length=150), nullable=False),
        sa.Column("date_acquired", sa.Date(), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_inventory_items_item_code"), "inventory_items", ["item_code"], unique=True)
    op.create_index(op.f("ix_inventory_items_name"), "inventory_items", ["name"], unique=False)
    op.create_index(op.f("ix_inventory_items_category"), "inventory_items", ["category"], unique=False)
    op.create_index(op.f("ix_inventory_items_supplier"), "inventory_items", ["supplier"], unique=False)
    op.create_index(op.f("ix_inventory_items_location"), "inventory_items", ["location"], unique=False)
    op.create_index(op.f("ix_inventory_items_is_archived"), "inventory_items", ["is_archived"], unique=False)

    op.create_table(
        "inventory_stock_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("adjustment_type", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("previous_quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("new_quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("adjustment_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("reference", sa.String(length=150), nullable=True),
        sa.Column("supplier", sa.String(length=150), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_inventory_stock_records_inventory_item_id"), "inventory_stock_records", ["inventory_item_id"], unique=False)
    op.create_index(op.f("ix_inventory_stock_records_adjustment_type"), "inventory_stock_records", ["adjustment_type"], unique=False)
    op.create_index(op.f("ix_inventory_stock_records_adjustment_date"), "inventory_stock_records", ["adjustment_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_stock_records_adjustment_date"), table_name="inventory_stock_records")
    op.drop_index(op.f("ix_inventory_stock_records_adjustment_type"), table_name="inventory_stock_records")
    op.drop_index(op.f("ix_inventory_stock_records_inventory_item_id"), table_name="inventory_stock_records")
    op.drop_table("inventory_stock_records")

    op.drop_index(op.f("ix_inventory_items_is_archived"), table_name="inventory_items")
    op.drop_index(op.f("ix_inventory_items_location"), table_name="inventory_items")
    op.drop_index(op.f("ix_inventory_items_supplier"), table_name="inventory_items")
    op.drop_index(op.f("ix_inventory_items_category"), table_name="inventory_items")
    op.drop_index(op.f("ix_inventory_items_name"), table_name="inventory_items")
    op.drop_index(op.f("ix_inventory_items_item_code"), table_name="inventory_items")
    op.drop_table("inventory_items")
