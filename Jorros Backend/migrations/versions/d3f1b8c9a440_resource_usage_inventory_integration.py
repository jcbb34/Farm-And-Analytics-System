"""resource usage inventory integration

Revision ID: d3f1b8c9a440
Revises: b91f4a7e2c10
Create Date: 2026-08-12 23:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f1b8c9a440"
down_revision: Union[str, Sequence[str], None] = "b91f4a7e2c10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("batch_number", sa.String(length=80), nullable=True),
    )
    op.create_index(
        op.f("ix_inventory_items_batch_number"),
        "inventory_items",
        ["batch_number"],
        unique=False,
    )

    op.create_table(
        "resource_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=True),
        sa.Column("livestock_id", sa.Integer(), nullable=True),
        sa.Column("usage_type", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("item_code_snapshot", sa.String(length=30), nullable=True),
        sa.Column("item_name_snapshot", sa.String(length=150), nullable=True),
        sa.Column("category_snapshot", sa.String(length=80), nullable=True),
        sa.Column("batch_number_snapshot", sa.String(length=80), nullable=True),
        sa.Column("basis_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("basis_unit", sa.String(length=30), nullable=True),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("voided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"]),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["voided_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resource_usages_inventory_item_id"), "resource_usages", ["inventory_item_id"], unique=False)
    op.create_index(op.f("ix_resource_usages_module"), "resource_usages", ["module"], unique=False)
    op.create_index(op.f("ix_resource_usages_crop_id"), "resource_usages", ["crop_id"], unique=False)
    op.create_index(op.f("ix_resource_usages_livestock_id"), "resource_usages", ["livestock_id"], unique=False)
    op.create_index(op.f("ix_resource_usages_usage_type"), "resource_usages", ["usage_type"], unique=False)
    op.create_index(op.f("ix_resource_usages_usage_date"), "resource_usages", ["usage_date"], unique=False)
    op.create_index(op.f("ix_resource_usages_is_voided"), "resource_usages", ["is_voided"], unique=False)

    op.add_column(
        "inventory_stock_records",
        sa.Column("resource_usage_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_stock_records_resource_usage",
        "inventory_stock_records",
        "resource_usages",
        ["resource_usage_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_inventory_stock_records_resource_usage_id"),
        "inventory_stock_records",
        ["resource_usage_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_stock_records_resource_usage_id"), table_name="inventory_stock_records")
    op.drop_constraint("fk_inventory_stock_records_resource_usage", "inventory_stock_records", type_="foreignkey")
    op.drop_column("inventory_stock_records", "resource_usage_id")

    op.drop_index(op.f("ix_resource_usages_is_voided"), table_name="resource_usages")
    op.drop_index(op.f("ix_resource_usages_usage_date"), table_name="resource_usages")
    op.drop_index(op.f("ix_resource_usages_usage_type"), table_name="resource_usages")
    op.drop_index(op.f("ix_resource_usages_livestock_id"), table_name="resource_usages")
    op.drop_index(op.f("ix_resource_usages_crop_id"), table_name="resource_usages")
    op.drop_index(op.f("ix_resource_usages_module"), table_name="resource_usages")
    op.drop_index(op.f("ix_resource_usages_inventory_item_id"), table_name="resource_usages")
    op.drop_table("resource_usages")

    op.drop_index(op.f("ix_inventory_items_batch_number"), table_name="inventory_items")
    op.drop_column("inventory_items", "batch_number")
