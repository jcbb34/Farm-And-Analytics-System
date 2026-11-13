"""Version counters for stale Crop, Livestock and Inventory edit forms."""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("crops", "livestock", "inventory_items"):
        op.add_column(table, sa.Column("edit_version", sa.Integer(), nullable=False, server_default=sa.text("1")))


def downgrade():
    for table in ("inventory_items", "livestock", "crops"):
        op.drop_column(table, "edit_version", mssql_drop_default=True)
