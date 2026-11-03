"""add livestock tables

Revision ID: 4c6e1d91f204
Revises: 173b27386732
Create Date: 2026-08-10 09:34:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c6e1d91f204"
down_revision: Union[str, Sequence[str], None] = "173b27386732"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "livestock",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("animal_code", sa.String(length=30), nullable=False),
        sa.Column("record_name", sa.String(length=120), nullable=False),
        sa.Column("animal_type", sa.String(length=50), nullable=False),
        sa.Column("breed", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("sex", sa.String(length=20), server_default=sa.text("'Mixed'"), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("pen_location", sa.String(length=120), nullable=False),
        sa.Column("health_status", sa.String(length=40), server_default=sa.text("'Healthy'"), nullable=False),
        sa.Column("growth_status", sa.String(length=40), server_default=sa.text("'Growing'"), nullable=False),
        sa.Column("last_checkup", sa.Date(), nullable=True),
        sa.Column("health_notes", sa.Text(), nullable=True),
        sa.Column("vaccination_status", sa.String(length=40), server_default=sa.text("'Not Vaccinated'"), nullable=False),
        sa.Column("next_vaccination", sa.Date(), nullable=True),
        sa.Column("feed_times", sa.String(length=150), nullable=True),
        sa.Column("feed_type", sa.String(length=150), nullable=True),
        sa.Column("daily_feed_kg", sa.Numeric(precision=10, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("feeding_notes", sa.Text(), nullable=True),
        sa.Column("production_output", sa.Text(), nullable=True),
        sa.Column("date_acquired", sa.Date(), nullable=False),
        sa.Column("acquired_from", sa.String(length=150), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_livestock_animal_code"), "livestock", ["animal_code"], unique=True)
    op.create_index(op.f("ix_livestock_record_name"), "livestock", ["record_name"], unique=False)
    op.create_index(op.f("ix_livestock_animal_type"), "livestock", ["animal_type"], unique=False)
    op.create_index(op.f("ix_livestock_pen_location"), "livestock", ["pen_location"], unique=False)
    op.create_index(op.f("ix_livestock_health_status"), "livestock", ["health_status"], unique=False)
    op.create_index(op.f("ix_livestock_growth_status"), "livestock", ["growth_status"], unique=False)
    op.create_index(op.f("ix_livestock_vaccination_status"), "livestock", ["vaccination_status"], unique=False)
    op.create_index(op.f("ix_livestock_is_archived"), "livestock", ["is_archived"], unique=False)

    op.create_table(
        "livestock_vaccination_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("vaccine", sa.String(length=150), nullable=False),
        sa.Column("date_administered", sa.Date(), nullable=False),
        sa.Column("next_due", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default=sa.text("'Up to Date'"), nullable=False),
        sa.Column("administered_by", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_livestock_vaccination_records_livestock_id"),
        "livestock_vaccination_records",
        ["livestock_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_livestock_vaccination_records_livestock_id"),
        table_name="livestock_vaccination_records",
    )
    op.drop_table("livestock_vaccination_records")

    op.drop_index(op.f("ix_livestock_is_archived"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_vaccination_status"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_growth_status"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_health_status"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_pen_location"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_animal_type"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_record_name"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_animal_code"), table_name="livestock")
    op.drop_table("livestock")
