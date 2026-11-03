"""Protect manual inventory stock adjustments from duplicate retries.

Revision ID: g7q3l0n6i248
Revises: f6p2k9m5h137
"""

from alembic import op
import sqlalchemy as sa

revision = "g7q3l0n6i248"
down_revision = "f6p2k9m5h137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_stock_records",
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "inventory_stock_records",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_inventory_stock_record_idempotency_key",
        "inventory_stock_records",
        ["idempotency_key"],
        unique=True,
        mssql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_stock_record_idempotency_key",
        table_name="inventory_stock_records",
    )
    op.drop_column("inventory_stock_records", "request_hash")
    op.drop_column("inventory_stock_records", "idempotency_key")
