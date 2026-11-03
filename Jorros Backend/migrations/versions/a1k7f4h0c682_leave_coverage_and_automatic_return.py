"""Complete leave approval, temporary coverage, and automatic return.

Revision ID: a1k7f4h0c682
Revises: z0j6e3g9b571
"""

from alembic import op
import sqlalchemy as sa

revision = "a1k7f4h0c682"
down_revision = "z0j6e3g9b571"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("staff_leave", sa.Column("default_covering_employee_id", sa.Integer(), nullable=True))
    op.add_column("staff_leave", sa.Column("coverage_reason", sa.Text(), nullable=True))
    op.add_column("staff_leave", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_staff_leave_default_covering_employee",
        "staff_leave",
        "employees",
        ["default_covering_employee_id"],
        ["id"],
    )
    op.create_index(
        "ix_staff_leave_default_covering_employee_id",
        "staff_leave",
        ["default_covering_employee_id"],
    )

    op.add_column("task_assignment_history", sa.Column("leave_id", sa.Integer(), nullable=True))
    op.add_column("task_assignment_history", sa.Column("old_assignment_source", sa.String(length=30), nullable=True))
    op.add_column("task_assignment_history", sa.Column("new_assignment_source", sa.String(length=30), nullable=True))
    op.add_column(
        "task_assignment_history",
        sa.Column("is_automatic", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("task_assignment_history", sa.Column("event_key", sa.String(length=160), nullable=True))
    op.create_foreign_key(
        "fk_task_assignment_history_leave",
        "task_assignment_history",
        "staff_leave",
        ["leave_id"],
        ["id"],
    )
    op.create_index("ix_task_assignment_history_leave_id", "task_assignment_history", ["leave_id"])
    op.create_index("ix_task_assignment_history_is_automatic", "task_assignment_history", ["is_automatic"])
    op.create_index(
        "uq_task_assignment_history_event_key_not_null",
        "task_assignment_history",
        ["event_key"],
        unique=True,
        mssql_where=sa.text("event_key IS NOT NULL"),
        sqlite_where=sa.text("event_key IS NOT NULL"),
    )

    op.create_table(
        "task_leave_coverage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("farm_activities.id"), nullable=False),
        sa.Column("leave_id", sa.Integer(), sa.ForeignKey("staff_leave.id"), nullable=False),
        sa.Column("original_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("covering_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("coverage_start_date", sa.Date(), nullable=False),
        sa.Column("coverage_end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("source_module", sa.String(length=40), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=True),
        sa.Column("source_record_id", sa.Integer(), nullable=True),
        sa.Column("source_detail_id", sa.Integer(), nullable=True),
        sa.Column("recurring_series_key", sa.String(length=120), nullable=True),
        sa.Column("returned_at", sa.DateTime(), nullable=True),
        sa.Column("returned_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("return_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("activity_id", "leave_id", name="uq_task_leave_coverage_activity_leave"),
    )
    for name, columns in [
        ("ix_task_leave_coverage_activity_id", ["activity_id"]),
        ("ix_task_leave_coverage_leave_id", ["leave_id"]),
        ("ix_task_leave_coverage_original_employee_id", ["original_employee_id"]),
        ("ix_task_leave_coverage_covering_employee_id", ["covering_employee_id"]),
        ("ix_task_leave_coverage_coverage_start_date", ["coverage_start_date"]),
        ("ix_task_leave_coverage_coverage_end_date", ["coverage_end_date"]),
        ("ix_task_leave_coverage_status", ["status"]),
        ("ix_task_leave_coverage_approved_by_user_id", ["approved_by_user_id"]),
        ("ix_task_leave_coverage_source_module", ["source_module"]),
        ("ix_task_leave_coverage_source_type", ["source_type"]),
        ("ix_task_leave_coverage_source_record_id", ["source_record_id"]),
        ("ix_task_leave_coverage_recurring_series_key", ["recurring_series_key"]),
    ]:
        op.create_index(name, "task_leave_coverage", columns)
    op.create_index(
        "ix_task_leave_coverage_source_match",
        "task_leave_coverage",
        ["leave_id", "recurring_series_key", "source_module", "source_type", "source_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_leave_coverage_source_match", table_name="task_leave_coverage")
    for name in [
        "ix_task_leave_coverage_recurring_series_key",
        "ix_task_leave_coverage_source_record_id",
        "ix_task_leave_coverage_source_type",
        "ix_task_leave_coverage_source_module",
        "ix_task_leave_coverage_approved_by_user_id",
        "ix_task_leave_coverage_status",
        "ix_task_leave_coverage_coverage_end_date",
        "ix_task_leave_coverage_coverage_start_date",
        "ix_task_leave_coverage_covering_employee_id",
        "ix_task_leave_coverage_original_employee_id",
        "ix_task_leave_coverage_leave_id",
        "ix_task_leave_coverage_activity_id",
    ]:
        op.drop_index(name, table_name="task_leave_coverage")
    op.drop_table("task_leave_coverage")

    op.drop_index("uq_task_assignment_history_event_key_not_null", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_is_automatic", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_leave_id", table_name="task_assignment_history")
    op.drop_constraint("fk_task_assignment_history_leave", "task_assignment_history", type_="foreignkey")
    op.drop_column("task_assignment_history", "event_key")
    op.drop_column("task_assignment_history", "is_automatic")
    op.drop_column("task_assignment_history", "new_assignment_source")
    op.drop_column("task_assignment_history", "old_assignment_source")
    op.drop_column("task_assignment_history", "leave_id")

    op.drop_index("ix_staff_leave_default_covering_employee_id", table_name="staff_leave")
    op.drop_constraint("fk_staff_leave_default_covering_employee", "staff_leave", type_="foreignkey")
    op.drop_column("staff_leave", "cancellation_reason")
    op.drop_column("staff_leave", "coverage_reason")
    op.drop_column("staff_leave", "default_covering_employee_id")
