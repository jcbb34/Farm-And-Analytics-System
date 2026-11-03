"""add central task source metadata

Revision ID: a12f7c3d9b45
Revises: f9d2b7c84a10
Create Date: 2026-08-12 14:39:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a12f7c3d9b45"
down_revision: Union[str, Sequence[str], None] = "f9d2b7c84a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "farm_activities",
        sa.Column(
            "is_automatic",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_module",
            sa.String(length=40),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_type",
            sa.String(length=80),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_record_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_detail_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_code",
            sa.String(length=60),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_path",
            sa.String(length=180),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "source_key",
            sa.String(length=220),
            nullable=True,
        ),
    )
    op.add_column(
        "farm_activities",
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_farm_activities_is_automatic",
        "farm_activities",
        ["is_automatic"],
        unique=False,
    )
    op.create_index(
        "ix_farm_activities_source_module",
        "farm_activities",
        ["source_module"],
        unique=False,
    )
    op.create_index(
        "ix_farm_activities_source_type",
        "farm_activities",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        "ix_farm_activities_source_record_id",
        "farm_activities",
        ["source_record_id"],
        unique=False,
    )
    op.create_index(
        "ix_farm_activities_source_key",
        "farm_activities",
        ["source_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_farm_activities_source_key",
        table_name="farm_activities",
    )
    op.drop_index(
        "ix_farm_activities_source_record_id",
        table_name="farm_activities",
    )
    op.drop_index(
        "ix_farm_activities_source_type",
        table_name="farm_activities",
    )
    op.drop_index(
        "ix_farm_activities_source_module",
        table_name="farm_activities",
    )
    op.drop_index(
        "ix_farm_activities_is_automatic",
        table_name="farm_activities",
    )

    op.drop_column(
        "farm_activities",
        "completed_at",
    )
    op.drop_column(
        "farm_activities",
        "source_key",
    )
    op.drop_column(
        "farm_activities",
        "source_path",
    )
    op.drop_column(
        "farm_activities",
        "source_code",
    )
    op.drop_column(
        "farm_activities",
        "source_detail_id",
    )
    op.drop_column(
        "farm_activities",
        "source_record_id",
    )
    op.drop_column(
        "farm_activities",
        "source_type",
    )
    op.drop_column(
        "farm_activities",
        "source_module",
    )
    op.drop_column(
        "farm_activities",
        "is_automatic",
    )
