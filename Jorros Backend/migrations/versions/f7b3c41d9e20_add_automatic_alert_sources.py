"""add automatic alert source metadata

Revision ID: f7b3c41d9e20
Revises: e2f4a91b7c33
Create Date: 2026-08-10 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7b3c41d9e20"
down_revision: Union[str, Sequence[str], None] = "e2f4a91b7c33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "farm_alerts",
        sa.Column(
            "is_automatic",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "farm_alerts",
        sa.Column("source_type", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "farm_alerts",
        sa.Column("source_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        op.f("ix_farm_alerts_is_automatic"),
        "farm_alerts",
        ["is_automatic"],
        unique=False,
    )
    op.create_index(
        op.f("ix_farm_alerts_source_type"),
        "farm_alerts",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_farm_alerts_source_id"),
        "farm_alerts",
        ["source_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_farm_alerts_source_id"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_source_type"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_is_automatic"), table_name="farm_alerts")

    op.drop_column("farm_alerts", "source_id")
    op.drop_column("farm_alerts", "source_type")
    op.drop_column("farm_alerts", "is_automatic")
