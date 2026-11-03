"""aggregate livestock composition and pen purposes

Revision ID: f5c8a3e1b720
Revises: e4b7c2d9a610
Create Date: 2026-08-14 22:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5c8a3e1b720"
down_revision: Union[str, Sequence[str], None] = "e4b7c2d9a610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "livestock_pens",
        sa.Column("purpose", sa.String(length=60), server_default=sa.text("'General'"), nullable=False),
    )
    op.create_index(op.f("ix_livestock_pens_purpose"), "livestock_pens", ["purpose"], unique=False)

    op.add_column("livestock", sa.Column("male_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("female_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("unknown_sex_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("min_weight_kg", sa.Numeric(10, 2), nullable=True))
    op.add_column("livestock", sa.Column("max_weight_kg", sa.Numeric(10, 2), nullable=True))
    op.add_column("livestock", sa.Column("healthy_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("at_risk_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("sick_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("under_treatment_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column(
        "livestock",
        sa.Column("production_purpose", sa.String(length=80), server_default=sa.text("'General'"), nullable=False),
    )
    op.create_index(op.f("ix_livestock_production_purpose"), "livestock", ["production_purpose"], unique=False)

    op.execute("UPDATE dbo.livestock SET record_type = 'Batch'")
    op.execute(
        """
        UPDATE dbo.livestock
        SET male_quantity = CASE WHEN LOWER(LTRIM(RTRIM(sex))) = 'male' THEN quantity ELSE 0 END,
            female_quantity = CASE WHEN LOWER(LTRIM(RTRIM(sex))) = 'female' THEN quantity ELSE 0 END,
            unknown_sex_quantity = CASE
                WHEN LOWER(LTRIM(RTRIM(sex))) IN ('male', 'female') THEN 0
                ELSE quantity
            END,
            min_weight_kg = weight_kg,
            max_weight_kg = weight_kg,
            healthy_quantity = CASE WHEN health_status = 'Healthy' THEN quantity ELSE 0 END,
            at_risk_quantity = CASE WHEN health_status = 'At Risk' THEN quantity ELSE 0 END,
            sick_quantity = CASE WHEN health_status = 'Sick' THEN quantity ELSE 0 END,
            under_treatment_quantity = CASE WHEN health_status = 'Under Treatment' THEN quantity ELSE 0 END
        """
    )
    op.execute(
        """
        UPDATE dbo.livestock
        SET healthy_quantity = quantity,
            health_status = 'Healthy'
        WHERE healthy_quantity + at_risk_quantity + sick_quantity + under_treatment_quantity = 0
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_livestock_production_purpose"), table_name="livestock")
    op.drop_column("livestock", "production_purpose")
    op.drop_column("livestock", "under_treatment_quantity")
    op.drop_column("livestock", "sick_quantity")
    op.drop_column("livestock", "at_risk_quantity")
    op.drop_column("livestock", "healthy_quantity")
    op.drop_column("livestock", "max_weight_kg")
    op.drop_column("livestock", "min_weight_kg")
    op.drop_column("livestock", "unknown_sex_quantity")
    op.drop_column("livestock", "female_quantity")
    op.drop_column("livestock", "male_quantity")

    op.drop_index(op.f("ix_livestock_pens_purpose"), table_name="livestock_pens")
    op.drop_column("livestock_pens", "purpose")
