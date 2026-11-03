"""multi-item farm sales and saleable inventory products

Revision ID: p8d4m1s7a903
Revises: g7q3l0n6i248
Create Date: 2026-09-15 03:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p8d4m1s7a903"
down_revision: Union[str, Sequence[str], None] = "g7q3l0n6i248"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column(
            "is_saleable",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_inventory_items_is_saleable",
        "inventory_items",
        ["is_saleable"],
        unique=False,
    )

    op.create_table(
        "livestock_sale_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("production_record_id", sa.Integer(), nullable=True),
        sa.Column("livestock_id", sa.Integer(), nullable=True),
        sa.Column("crop_id", sa.Integer(), nullable=True),
        sa.Column("inventory_item_id", sa.Integer(), nullable=True),
        sa.Column("inventory_stock_record_id", sa.Integer(), nullable=True),
        sa.Column("source_name_snapshot", sa.String(length=150), nullable=False),
        sa.Column("source_code_snapshot", sa.String(length=50), nullable=True),
        sa.Column("product_type", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("male_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("female_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unknown_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("healthy_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["livestock_sales.id"]),
        sa.ForeignKeyConstraint(
            ["production_record_id"], ["livestock_production_records.id"]
        ),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"]),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(
            ["inventory_stock_record_id"], ["inventory_stock_records.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_id", "line_number", name="uq_sale_item_line"),
    )
    for name, columns in (
        ("ix_livestock_sale_items_sale_id", ["sale_id"]),
        ("ix_livestock_sale_items_item_kind", ["item_kind"]),
        ("ix_livestock_sale_items_source_type", ["source_type"]),
        ("ix_livestock_sale_items_production_record_id", ["production_record_id"]),
        ("ix_livestock_sale_items_livestock_id", ["livestock_id"]),
        ("ix_livestock_sale_items_crop_id", ["crop_id"]),
        ("ix_livestock_sale_items_inventory_item_id", ["inventory_item_id"]),
        ("ix_livestock_sale_items_inventory_stock_record_id", ["inventory_stock_record_id"]),
        ("ix_sale_items_sale_source", ["sale_id", "source_type"]),
    ):
        op.create_index(name, "livestock_sale_items", columns, unique=False)

    # Every historical single-item sale becomes a one-line invoice. The old
    # header columns remain populated for compatibility with imports and older
    # reports, while all new stock calculations use the line ledger.
    op.execute(
        """
        INSERT INTO livestock_sale_items (
            sale_id, line_number, item_kind, source_type,
            production_record_id, livestock_id, crop_id,
            inventory_item_id, inventory_stock_record_id,
            source_name_snapshot, source_code_snapshot, product_type,
            quantity, unit, unit_price, line_total,
            male_quantity, female_quantity, unknown_quantity, healthy_quantity,
            created_at
        )
        SELECT
            s.id, 1,
            CASE WHEN LOWER(LTRIM(RTRIM(s.sale_type))) = 'live animal'
                 THEN 'Live Animal' ELSE 'Production' END,
            COALESCE(NULLIF(LTRIM(RTRIM(s.source_type)), ''), 'Livestock'),
            s.production_record_id, s.livestock_id, s.crop_id,
            NULL, NULL,
            COALESCE(c.name, l.record_name, s.product_type, 'Historical sale'),
            COALESCE(c.crop_code, l.animal_code, s.sale_code),
            s.product_type, s.quantity, s.unit, s.unit_price, s.total_amount,
            s.male_quantity, s.female_quantity, s.unknown_quantity,
            s.healthy_quantity, s.created_at
        FROM livestock_sales s
        LEFT JOIN crops c ON c.id = s.crop_id
        LEFT JOIN livestock l ON l.id = s.livestock_id
        WHERE NOT EXISTS (
            SELECT 1 FROM livestock_sale_items i WHERE i.sale_id = s.id
        )
        """
    )


def downgrade() -> None:
    op.drop_table("livestock_sale_items")
    op.drop_index("ix_inventory_items_is_saleable", table_name="inventory_items")
    op.drop_column("inventory_items", "is_saleable")
