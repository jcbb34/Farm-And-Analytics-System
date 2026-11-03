"""livestock workflow enhancements

Revision ID: j4a9c7e2d615
Revises: i3f8b2d6a041
Create Date: 2026-08-16 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j4a9c7e2d615"
down_revision: Union[str, Sequence[str], None] = "i3f8b2d6a041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("livestock_growth_records", sa.Column("animals_measured", sa.Integer(), nullable=True))
    op.add_column("livestock_growth_records", sa.Column("total_measured_weight_kg", sa.Numeric(12, 3), nullable=True))
    op.add_column("livestock_growth_records", sa.Column("min_weight_kg", sa.Numeric(10, 2), nullable=True))
    op.add_column("livestock_growth_records", sa.Column("max_weight_kg", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "livestock_growth_records",
        sa.Column("measurement_basis", sa.String(length=30), server_default=sa.text("'Average'"), nullable=False),
    )

    op.add_column("livestock_vaccination_records", sa.Column("inventory_item_id", sa.Integer(), nullable=True))
    op.add_column("livestock_vaccination_records", sa.Column("quantity_used", sa.Numeric(12, 3), nullable=True))
    op.add_column("livestock_vaccination_records", sa.Column("unit", sa.String(length=30), nullable=True))
    op.create_index(
        op.f("ix_livestock_vaccination_records_inventory_item_id"),
        "livestock_vaccination_records",
        ["inventory_item_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_livestock_vaccination_inventory_item_id",
        "livestock_vaccination_records",
        "inventory_items",
        ["inventory_item_id"],
        ["id"],
    )

    op.add_column("livestock_reproduction_records", sa.Column("breeder_male_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock_reproduction_records", sa.Column("breeder_female_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock_reproduction_records", sa.Column("confirmed_pregnant_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock_reproduction_records", sa.Column("eggs_set", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock_reproduction_records", sa.Column("fertile_eggs", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock_reproduction_records", sa.Column("incubation_method", sa.String(length=50), nullable=True))

    op.add_column("livestock_production_records", sa.Column("source_active_quantity", sa.Integer(), nullable=True))
    op.add_column("livestock_production_records", sa.Column("gross_quantity", sa.Numeric(12, 3), nullable=True))
    op.add_column("livestock_production_records", sa.Column("loss_quantity", sa.Numeric(12, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("livestock_production_records", "loss_quantity")
    op.drop_column("livestock_production_records", "gross_quantity")
    op.drop_column("livestock_production_records", "source_active_quantity")

    op.drop_column("livestock_reproduction_records", "incubation_method")
    op.drop_column("livestock_reproduction_records", "fertile_eggs")
    op.drop_column("livestock_reproduction_records", "eggs_set")
    op.drop_column("livestock_reproduction_records", "confirmed_pregnant_quantity")
    op.drop_column("livestock_reproduction_records", "breeder_female_quantity")
    op.drop_column("livestock_reproduction_records", "breeder_male_quantity")

    op.drop_constraint("fk_livestock_vaccination_inventory_item_id", "livestock_vaccination_records", type_="foreignkey")
    op.drop_index(op.f("ix_livestock_vaccination_records_inventory_item_id"), table_name="livestock_vaccination_records")
    op.drop_column("livestock_vaccination_records", "unit")
    op.drop_column("livestock_vaccination_records", "quantity_used")
    op.drop_column("livestock_vaccination_records", "inventory_item_id")

    op.drop_column("livestock_growth_records", "measurement_basis")
    op.drop_column("livestock_growth_records", "max_weight_kg")
    op.drop_column("livestock_growth_records", "min_weight_kg")
    op.drop_column("livestock_growth_records", "total_measured_weight_kg")
    op.drop_column("livestock_growth_records", "animals_measured")
