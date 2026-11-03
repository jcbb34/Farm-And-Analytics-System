"""Link workforce tasks to planned inventory resources.

Revision ID: r2a8c5d1e693
Revises: q1f7b4c0d582
"""

from alembic import op
import sqlalchemy as sa

revision = "r2a8c5d1e693"
down_revision = "q1f7b4c0d582"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("farm_activities", sa.Column("planned_inventory_item_id", sa.Integer(), nullable=True))
    op.add_column("farm_activities", sa.Column("planned_usage_type", sa.String(length=40), nullable=True))
    op.create_foreign_key(
        "fk_farm_activities_planned_inventory_item_id_inventory_items",
        "farm_activities",
        "inventory_items",
        ["planned_inventory_item_id"],
        ["id"],
    )
    op.create_index(
        "ix_farm_activities_planned_inventory_item_id",
        "farm_activities",
        ["planned_inventory_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_farm_activities_planned_inventory_item_id", table_name="farm_activities")
    op.drop_constraint(
        "fk_farm_activities_planned_inventory_item_id_inventory_items",
        "farm_activities",
        type_="foreignkey",
    )
    op.drop_column("farm_activities", "planned_usage_type")
    op.drop_column("farm_activities", "planned_inventory_item_id")
