"""livestock growth history and trend analytics

Revision ID: i3f8b2d6a041
Revises: h2e7a1c4d930
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i3f8b2d6a041"
down_revision: Union[str, Sequence[str], None] = "h2e7a1c4d930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "livestock_growth_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("measurement_date", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(10, 2), nullable=False),
        sa.Column("previous_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("weight_change_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("days_since_previous", sa.Integer(), nullable=True),
        sa.Column("average_daily_gain_kg", sa.Numeric(10, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "livestock_id",
            "measurement_date",
            name="uq_livestock_growth_measurement_date",
        ),
    )
    op.create_index(
        "ix_livestock_growth_records_livestock_id",
        "livestock_growth_records",
        ["livestock_id"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_growth_records_measurement_date",
        "livestock_growth_records",
        ["measurement_date"],
        unique=False,
    )

    # Preserve each active batch's current weight as its historical baseline.
    op.execute(
        """
        INSERT INTO livestock_growth_records (
            livestock_id, measurement_date, weight_kg, notes, recorded_by_user_id
        )
        SELECT
            id,
            CAST(GETDATE() AS date),
            weight_kg,
            'Baseline created from existing current livestock weight',
            created_by_user_id
        FROM livestock
        WHERE weight_kg IS NOT NULL AND weight_kg > 0
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_livestock_growth_records_measurement_date",
        table_name="livestock_growth_records",
    )
    op.drop_index(
        "ix_livestock_growth_records_livestock_id",
        table_name="livestock_growth_records",
    )
    op.drop_table("livestock_growth_records")
