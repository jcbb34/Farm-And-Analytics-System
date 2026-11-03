"""add livestock reproduction and production output records

Revision ID: e8c4f1a62b91
Revises: d7a1c5b9e402
Create Date: 2026-08-12 12:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8c4f1a62b91"
down_revision: Union[str, Sequence[str], None] = "d7a1c5b9e402"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "livestock_reproduction_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("partner_reference", sa.String(length=150), nullable=True),
        sa.Column("breeding_method", sa.String(length=50), nullable=True),
        sa.Column("reproductive_status", sa.String(length=60), nullable=True),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column(
            "offspring_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "alive_offspring",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("male_offspring", sa.Integer(), nullable=True),
        sa.Column("female_offspring", sa.Integer(), nullable=True),
        sa.Column(
            "loss_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["livestock_id"],
            ["livestock.id"],
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_livestock_reproduction_records_livestock_id"),
        "livestock_reproduction_records",
        ["livestock_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_livestock_reproduction_records_record_type"),
        "livestock_reproduction_records",
        ["record_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_livestock_reproduction_records_event_date"),
        "livestock_reproduction_records",
        ["event_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_livestock_reproduction_records_reproductive_status"),
        "livestock_reproduction_records",
        ["reproductive_status"],
        unique=False,
    )

    op.create_table(
        "livestock_production_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("output_type", sa.String(length=60), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("quality_grade", sa.String(length=80), nullable=True),
        sa.Column("destination", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["livestock_id"],
            ["livestock.id"],
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_livestock_production_records_livestock_id"),
        "livestock_production_records",
        ["livestock_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_livestock_production_records_output_type"),
        "livestock_production_records",
        ["output_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_livestock_production_records_record_date"),
        "livestock_production_records",
        ["record_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_livestock_production_records_record_date"),
        table_name="livestock_production_records",
    )
    op.drop_index(
        op.f("ix_livestock_production_records_output_type"),
        table_name="livestock_production_records",
    )
    op.drop_index(
        op.f("ix_livestock_production_records_livestock_id"),
        table_name="livestock_production_records",
    )
    op.drop_table("livestock_production_records")

    op.drop_index(
        op.f("ix_livestock_reproduction_records_reproductive_status"),
        table_name="livestock_reproduction_records",
    )
    op.drop_index(
        op.f("ix_livestock_reproduction_records_event_date"),
        table_name="livestock_reproduction_records",
    )
    op.drop_index(
        op.f("ix_livestock_reproduction_records_record_type"),
        table_name="livestock_reproduction_records",
    )
    op.drop_index(
        op.f("ix_livestock_reproduction_records_livestock_id"),
        table_name="livestock_reproduction_records",
    )
    op.drop_table("livestock_reproduction_records")
