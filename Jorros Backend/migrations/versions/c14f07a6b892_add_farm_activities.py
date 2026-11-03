"""add farm activities

Revision ID: c14f07a6b892
Revises: 8b9d3e2f1a77
Create Date: 2026-08-10 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c14f07a6b892"
down_revision: Union[str, Sequence[str], None] = "8b9d3e2f1a77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farm_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("related_to", sa.String(length=150), nullable=False),
        sa.Column("location", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("duration", sa.String(length=50), nullable=True),
        sa.Column("assigned_by", sa.String(length=120), nullable=False),
        sa.Column("assigned_to", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'Pending'"), nullable=False),
        sa.Column("priority", sa.String(length=20), server_default=sa.text("'Medium'"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_farm_activities_activity_code"), "farm_activities", ["activity_code"], unique=True)
    op.create_index(op.f("ix_farm_activities_name"), "farm_activities", ["name"], unique=False)
    op.create_index(op.f("ix_farm_activities_category"), "farm_activities", ["category"], unique=False)
    op.create_index(op.f("ix_farm_activities_related_to"), "farm_activities", ["related_to"], unique=False)
    op.create_index(op.f("ix_farm_activities_location"), "farm_activities", ["location"], unique=False)
    op.create_index(op.f("ix_farm_activities_activity_date"), "farm_activities", ["activity_date"], unique=False)
    op.create_index(op.f("ix_farm_activities_assigned_to"), "farm_activities", ["assigned_to"], unique=False)
    op.create_index(op.f("ix_farm_activities_status"), "farm_activities", ["status"], unique=False)
    op.create_index(op.f("ix_farm_activities_priority"), "farm_activities", ["priority"], unique=False)
    op.create_index(op.f("ix_farm_activities_is_archived"), "farm_activities", ["is_archived"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_farm_activities_is_archived"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_priority"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_status"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_assigned_to"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_activity_date"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_location"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_related_to"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_category"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_name"), table_name="farm_activities")
    op.drop_index(op.f("ix_farm_activities_activity_code"), table_name="farm_activities")
    op.drop_table("farm_activities")
