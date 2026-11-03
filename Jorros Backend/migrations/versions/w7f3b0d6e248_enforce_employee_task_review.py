"""Enforce manager review for employee-performed task submissions.

Revision ID: w7f3b0d6e248
Revises: v6e2a9c5d137
"""

from alembic import op
import sqlalchemy as sa

revision = "w7f3b0d6e248"
down_revision = "v6e2a9c5d137"
branch_labels = None
depends_on = None


_TERMINAL_STATUSES_SQL = "'Completed','Approved','Voided','Cancelled','Resolved'"
_DEFAULT_CONSTRAINT_NAME = "DF_farm_activities_requires_review"


def _set_requires_review_default(bind, value: bool) -> None:
    """Replace the server default without creating duplicate MSSQL defaults.

    SQL Server implements a column DEFAULT as a separate constraint.  Alembic's
    generic ``alter_column(..., server_default=...)`` emits ``ADD DEFAULT`` and
    fails when the column already has the auto-named constraint created by the
    original employee-workflow migration.  Discover and drop that constraint
    first, then add one deterministic constraint.
    """
    default_sql = "1" if value else "0"

    if bind.dialect.name == "mssql":
        bind.execute(
            sa.text(
                f"""
DECLARE @constraint_name sysname;
DECLARE @schema_name sysname;

SELECT TOP (1)
    @constraint_name = dc.name,
    @schema_name = s.name
FROM sys.default_constraints AS dc
INNER JOIN sys.columns AS c
    ON c.default_object_id = dc.object_id
INNER JOIN sys.tables AS t
    ON t.object_id = c.object_id
INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
WHERE t.name = N'farm_activities'
  AND c.name = N'requires_review';

DECLARE @sql nvarchar(max);

IF @constraint_name IS NOT NULL
BEGIN
    SET @sql =
        N'ALTER TABLE ' + QUOTENAME(@schema_name) + N'.[farm_activities] ' +
        N'DROP CONSTRAINT ' + QUOTENAME(@constraint_name) + N';';
    EXEC sys.sp_executesql @sql;
END;

IF @schema_name IS NULL
BEGIN
    SELECT TOP (1) @schema_name = s.name
    FROM sys.tables AS t
    INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
    WHERE t.name = N'farm_activities';
END;

IF @schema_name IS NULL
    THROW 50001, 'farm_activities table was not found while updating requires_review default.', 1;

SET @sql =
    N'ALTER TABLE ' + QUOTENAME(@schema_name) + N'.[farm_activities] ' +
    N'ADD CONSTRAINT [{_DEFAULT_CONSTRAINT_NAME}] DEFAULT ({default_sql}) FOR [requires_review];';
EXEC sys.sp_executesql @sql;
"""
            )
        )
        return

    # Other supported test/development databases can use Alembic's generic
    # server-default alteration.
    op.alter_column(
        "farm_activities",
        "requires_review",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text(default_sql),
    )


def _repair_open_employee_tasks(bind) -> None:
    bind.execute(
        sa.text(
            "UPDATE farm_activities "
            "SET requires_review = 1 "
            "WHERE assigned_employee_id IS NOT NULL "
            "AND is_archived = 0 "
            f"AND status NOT IN ({_TERMINAL_STATUSES_SQL})"
        )
    )


def _repair_submitted_task_status(bind) -> None:
    bind.execute(
        sa.text(
            "UPDATE farm_activities "
            "SET status = 'Submitted for Review', requires_review = 1, completed_at = NULL "
            "WHERE is_archived = 0 "
            f"AND status NOT IN ({_TERMINAL_STATUSES_SQL}) "
            "AND EXISTS ("
            "  SELECT 1 FROM task_submissions s "
            "  WHERE s.activity_id = farm_activities.id "
            "    AND s.review_status = 'Submitted' "
            "    AND NOT EXISTS ("
            "      SELECT 1 FROM task_submissions newer "
            "      WHERE newer.activity_id = s.activity_id "
            "        AND (newer.attempt_number > s.attempt_number "
            "          OR (newer.attempt_number = s.attempt_number AND newer.id > s.id))"
            "    )"
            ")"
        )
    )


def upgrade() -> None:
    # New farm activities default to review-required. Code paths that create
    # non-work reminders (for example Inventory restock reminders) explicitly
    # opt out and use the Resolve workflow instead.
    bind = op.get_bind()
    _set_requires_review_default(bind, True)

    # Repair open employee assignments and stale Submitted task state without
    # touching terminal/archived history.
    _repair_open_employee_tasks(bind)
    _repair_submitted_task_status(bind)



def downgrade() -> None:
    # Data is intentionally not mass-reverted: changing reviewed workflow state
    # during downgrade would rewrite task history. Only restore the old default.
    bind = op.get_bind()
    _set_requires_review_default(bind, False)
