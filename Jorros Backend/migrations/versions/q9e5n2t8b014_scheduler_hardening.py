"""scheduler leadership, due-query indexes, and safe code counters

Revision ID: q9e5n2t8b014
Revises: p8d4m1s7a903
Create Date: 2026-09-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q9e5n2t8b014"
down_revision: Union[str, Sequence[str], None] = "p8d4m1s7a903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "code_counters",
        sa.Column("namespace", sa.String(length=40), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("namespace"),
    )
    op.create_table(
        "scheduler_status",
        sa.Column("scheduler_name", sa.String(length=60), nullable=False),
        sa.Column("leader_instance_id", sa.String(length=160), nullable=True),
        sa.Column("last_run_id", sa.String(length=36), nullable=True),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("generated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scheduler_name"),
    )

    op.create_index(
        "ix_farm_activities_scheduler_due",
        "farm_activities",
        ["is_automatic", "is_archived", "status", "source_type", "activity_date"],
        unique=False,
    )
    op.create_index(
        "ix_farm_alerts_scheduler_active",
        "farm_alerts",
        ["is_automatic", "status", "source_type"],
        unique=False,
    )
    op.create_index(
        "ix_crops_scheduler_harvest_due",
        "crops",
        ["is_archived", "status", "estimated_harvest"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_scheduler_vaccination_due",
        "livestock",
        ["is_archived", "next_vaccination"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_stock_records_threshold_crossing",
        "inventory_stock_records",
        ["inventory_item_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_items_scheduler_low_stock",
        "inventory_items",
        ["is_archived", "quantity", "reorder_level"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_reproduction_scheduler_due",
        "livestock_reproduction_records",
        ["actual_date", "expected_date", "livestock_id"],
        unique=False,
    )
    op.create_index(
        "ix_crop_growth_records_latest",
        "crop_growth_records",
        ["crop_id", "update_date", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crop_growth_records_latest",
        table_name="crop_growth_records",
    )
    op.drop_index(
        "ix_livestock_reproduction_scheduler_due",
        table_name="livestock_reproduction_records",
    )
    op.drop_index(
        "ix_inventory_stock_records_threshold_crossing",
        table_name="inventory_stock_records",
    )
    op.drop_index(
        "ix_inventory_items_scheduler_low_stock",
        table_name="inventory_items",
    )
    op.drop_index(
        "ix_livestock_scheduler_vaccination_due",
        table_name="livestock",
    )
    op.drop_index("ix_crops_scheduler_harvest_due", table_name="crops")
    op.drop_index("ix_farm_alerts_scheduler_active", table_name="farm_alerts")
    op.drop_index("ix_farm_activities_scheduler_due", table_name="farm_activities")
    op.drop_table("scheduler_status")
    op.drop_table("code_counters")
