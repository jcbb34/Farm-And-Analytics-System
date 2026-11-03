"""Index triggered alerts for the notification bell.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_farm_alerts_triggered_preview", "farm_alerts", ["last_triggered", "id"],
        mssql_where=sa.text("last_triggered IS NOT NULL"),
        sqlite_where=sa.text("last_triggered IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_farm_alerts_triggered_preview", table_name="farm_alerts")
