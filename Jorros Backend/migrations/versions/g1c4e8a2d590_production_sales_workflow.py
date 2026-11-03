"""production sales workflow

Revision ID: g1c4e8a2d590
Revises: f6b9d2e4c701
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g1c4e8a2d590"
down_revision: Union[str, Sequence[str], None] = "f6b9d2e4c701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "livestock_production_records",
        sa.Column("track_sale_inventory", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index(
        "ix_livestock_production_records_track_sale_inventory",
        "livestock_production_records",
        ["track_sale_inventory"],
        unique=False,
    )

    op.add_column(
        "livestock_reproduction_records",
        sa.Column("offspring_livestock_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_livestock_reproduction_records_offspring_livestock_id",
        "livestock_reproduction_records",
        ["offspring_livestock_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_livestock_reproduction_offspring_livestock",
        "livestock_reproduction_records",
        "livestock",
        ["offspring_livestock_id"],
        ["id"],
    )

    op.create_table(
        "livestock_sales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_code", sa.String(length=30), nullable=False),
        sa.Column("sale_type", sa.String(length=30), nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("production_record_id", sa.Integer(), nullable=True),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("product_type", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("buyer_name", sa.String(length=150), nullable=True),
        sa.Column("payment_status", sa.String(length=30), server_default=sa.text("'Paid'"), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=True),
        sa.Column("male_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("female_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unknown_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("healthy_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["production_record_id"], ["livestock_production_records.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_code"),
    )
    op.create_index("ix_livestock_sales_sale_type", "livestock_sales", ["sale_type"], unique=False)
    op.create_index("ix_livestock_sales_livestock_id", "livestock_sales", ["livestock_id"], unique=False)
    op.create_index("ix_livestock_sales_production_record_id", "livestock_sales", ["production_record_id"], unique=False)
    op.create_index("ix_livestock_sales_sale_date", "livestock_sales", ["sale_date"], unique=False)
    op.create_index("ix_livestock_sales_product_type", "livestock_sales", ["product_type"], unique=False)
    op.create_index("ix_livestock_sales_buyer_name", "livestock_sales", ["buyer_name"], unique=False)
    op.create_index("ix_livestock_sales_payment_status", "livestock_sales", ["payment_status"], unique=False)
    op.create_index("ix_livestock_sales_is_voided", "livestock_sales", ["is_voided"], unique=False)
    op.create_index("ix_livestock_sales_created_at", "livestock_sales", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("livestock_sales")
    op.drop_constraint(
        "fk_livestock_reproduction_offspring_livestock",
        "livestock_reproduction_records",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_livestock_reproduction_records_offspring_livestock_id",
        table_name="livestock_reproduction_records",
    )
    op.drop_column("livestock_reproduction_records", "offspring_livestock_id")
    op.drop_index(
        "ix_livestock_production_records_track_sale_inventory",
        table_name="livestock_production_records",
    )
    op.drop_column("livestock_production_records", "track_sale_inventory")
