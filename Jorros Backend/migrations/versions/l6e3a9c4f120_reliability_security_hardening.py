"""reliability and security hardening

Revision ID: l6e3a9c4f120
Revises: k5d2f8a7c930
Create Date: 2026-08-16 20:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "l6e3a9c4f120"
down_revision: Union[str, Sequence[str], None] = "k5d2f8a7c930"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    """Return current column names so a retry after an interrupted migration is safe."""
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    """Return current index names so migration retries do not recreate/drop missing indexes."""
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    # Session revision: changing a password or logging out increments this value,
    # which invalidates access tokens issued with an older revision.
    if "auth_version" not in _column_names("users"):
        op.add_column(
            "users",
            sa.Column(
                "auth_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    # Preserve one canonical automatic task per source key before enforcing the
    # unique index. Any historical duplicates keep their content with a distinct
    # legacy key rather than being deleted.
    #
    # IMPORTANT: use exec_driver_sql() instead of op.execute(). SQLAlchemy's text
    # parser treats ':legacy' inside the SQL string literal ':legacy-dup:' as a
    # bind parameter. Sending the statement directly to the DBAPI preserves it as
    # ordinary SQL text. LEFT(..., 180) also keeps the rewritten value safely
    # inside the source_key VARCHAR(220) column.
    bind.exec_driver_sql(
        """
        ;WITH ranked AS (
            SELECT id, source_key,
                   ROW_NUMBER() OVER (PARTITION BY source_key ORDER BY id DESC) AS row_num
            FROM farm_activities
            WHERE source_key IS NOT NULL
        )
        UPDATE farm_activities
        SET source_key = CONCAT(
            LEFT(farm_activities.source_key, 180),
            ':legacy-dup:',
            farm_activities.id
        )
        FROM farm_activities
        INNER JOIN ranked ON ranked.id = farm_activities.id
        WHERE ranked.row_num > 1
        """
    )

    activity_indexes = _index_names("farm_activities")
    if "ix_farm_activities_source_key" in activity_indexes:
        op.drop_index("ix_farm_activities_source_key", table_name="farm_activities")

    activity_indexes = _index_names("farm_activities")
    if "uq_farm_activities_source_key_not_null" not in activity_indexes:
        op.create_index(
            "uq_farm_activities_source_key_not_null",
            "farm_activities",
            ["source_key"],
            unique=True,
            mssql_where=sa.text("source_key IS NOT NULL"),
        )

    # Resolve any pre-existing automatic alert duplicates without deleting audit
    # history, then prevent future worker races from creating another copy.
    bind.exec_driver_sql(
        """
        ;WITH ranked AS (
            SELECT id, source_type, source_id, alert_type,
                   ROW_NUMBER() OVER (
                       PARTITION BY source_type, source_id, alert_type
                       ORDER BY id DESC
                   ) AS row_num
            FROM farm_alerts
            WHERE is_automatic = 1
              AND source_type IS NOT NULL
              AND source_id IS NOT NULL
        )
        UPDATE farm_alerts
        SET source_id = -farm_alerts.id,
            status = 'Resolved'
        FROM farm_alerts
        INNER JOIN ranked ON ranked.id = farm_alerts.id
        WHERE ranked.row_num > 1
        """
    )

    alert_indexes = _index_names("farm_alerts")
    if "uq_farm_alerts_automatic_source" not in alert_indexes:
        op.create_index(
            "uq_farm_alerts_automatic_source",
            "farm_alerts",
            ["source_type", "source_id", "alert_type"],
            unique=True,
            mssql_where=sa.text(
                "is_automatic = 1 AND source_type IS NOT NULL AND source_id IS NOT NULL"
            ),
        )


def downgrade() -> None:
    alert_indexes = _index_names("farm_alerts")
    if "uq_farm_alerts_automatic_source" in alert_indexes:
        op.drop_index("uq_farm_alerts_automatic_source", table_name="farm_alerts")

    activity_indexes = _index_names("farm_activities")
    if "uq_farm_activities_source_key_not_null" in activity_indexes:
        op.drop_index(
            "uq_farm_activities_source_key_not_null",
            table_name="farm_activities",
        )

    activity_indexes = _index_names("farm_activities")
    if "ix_farm_activities_source_key" not in activity_indexes:
        op.create_index(
            "ix_farm_activities_source_key",
            "farm_activities",
            ["source_key"],
            unique=False,
        )

    if "auth_version" in _column_names("users"):
        op.drop_column("users", "auth_version", mssql_drop_default=True)
