"""Make task submissions idempotent and task inventory postings unique.

Revision ID: v6e2a9c5d137
Revises: u5d1f8a4b026
"""

from alembic import op
import sqlalchemy as sa

revision = "v6e2a9c5d137"
down_revision = "u5d1f8a4b026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_submissions", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.add_column("task_submissions", sa.Column("request_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "task_submissions",
        sa.Column("inventory_override_used", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("task_submissions", sa.Column("inventory_override_reason", sa.Text(), nullable=True))
    op.create_index(
        "ix_task_submission_idempotency_key",
        "task_submissions",
        ["idempotency_key"],
        unique=True,
        mssql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column(
        "resource_usages",
        sa.Column("task_posting_active", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index(
        "ix_resource_usages_task_posting_active",
        "resource_usages",
        ["task_posting_active"],
        unique=False,
    )

    # Preserve all legacy usage rows. For a task that somehow already has more
    # than one non-voided usage row, only the newest row becomes the canonical
    # active posting; older rows remain historical and are not deleted/reversed.
    op.execute(
        sa.text(
            "UPDATE resource_usages SET task_posting_active = 1 "
            "WHERE id IN ("
            "SELECT MAX(id) FROM resource_usages "
            "WHERE activity_id IS NOT NULL AND is_voided = 0 "
            "GROUP BY activity_id"
            ")"
        )
    )
    op.create_index(
        "ix_resource_usage_active_task_posting",
        "resource_usages",
        ["activity_id"],
        unique=True,
        mssql_where=sa.text("activity_id IS NOT NULL AND task_posting_active = 1"),
        sqlite_where=sa.text("activity_id IS NOT NULL AND task_posting_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("ix_resource_usage_active_task_posting", table_name="resource_usages")
    op.drop_index("ix_resource_usages_task_posting_active", table_name="resource_usages")
    op.drop_column("resource_usages", "task_posting_active")
    op.drop_index("ix_task_submission_idempotency_key", table_name="task_submissions")
    op.drop_column("task_submissions", "inventory_override_reason")
    op.drop_column("task_submissions", "inventory_override_used")
    op.drop_column("task_submissions", "request_hash")
    op.drop_column("task_submissions", "idempotency_key")
