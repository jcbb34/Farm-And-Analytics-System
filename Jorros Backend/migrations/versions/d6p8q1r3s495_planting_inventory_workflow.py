"""Link counted planting materials to crop registrations and task confirmations.

Revision ID: d6p8q1r3s495
Revises: c5v7w0x2y384
"""
from alembic import op
import sqlalchemy as sa

revision = "d6p8q1r3s495"
down_revision = "c5v7w0x2y384"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inventory_items", sa.Column("planting_crop_reference", sa.String(60), nullable=True))
    op.add_column("inventory_items", sa.Column("planting_variety_reference", sa.String(80), nullable=True))
    op.add_column("inventory_items", sa.Column("planting_material_kind", sa.String(40), nullable=True))
    op.add_column("inventory_items", sa.Column("planting_units_per_position", sa.Integer(), nullable=True))
    op.create_index("ix_inventory_items_planting_crop_reference", "inventory_items", ["planting_crop_reference"])
    op.add_column("crops", sa.Column("planting_inventory_item_id", sa.Integer(), nullable=True))
    op.add_column("crops", sa.Column("planting_material_required", sa.Integer(), nullable=True))
    op.add_column("crops", sa.Column("planting_confirmed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_crops_planting_inventory_item_id", "crops", ["planting_inventory_item_id"])
    op.create_foreign_key("fk_crops_planting_inventory_item", "crops", "inventory_items", ["planting_inventory_item_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_crops_planting_inventory_item", "crops", type_="foreignkey")
    op.drop_index("ix_crops_planting_inventory_item_id", table_name="crops")
    op.drop_column("crops", "planting_confirmed_at")
    op.drop_column("crops", "planting_material_required")
    op.drop_column("crops", "planting_inventory_item_id")
    op.drop_index("ix_inventory_items_planting_crop_reference", table_name="inventory_items")
    op.drop_column("inventory_items", "planting_units_per_position")
    op.drop_column("inventory_items", "planting_material_kind")
    op.drop_column("inventory_items", "planting_variety_reference")
    op.drop_column("inventory_items", "planting_crop_reference")
