"""Employee weekly schedules, dated exceptions, and recurring-task coverage policy.

Revision ID: b2l8g5i1d793
Revises: a1k7f4h0c682
"""

from alembic import op
import sqlalchemy as sa

revision = "b2l8g5i1d793"
down_revision = "a1k7f4h0c682"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_work_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default=sa.text("'Asia/Manila'")),
        sa.Column("schedule_type", sa.String(length=30), nullable=False, server_default=sa.text("'Fixed'")),
        sa.Column("backup_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_employee_work_schedule_effective_range"),
    )
    for name, columns in [
        ("ix_employee_work_schedules_employee_id", ["employee_id"]),
        ("ix_employee_work_schedules_effective_from", ["effective_from"]),
        ("ix_employee_work_schedules_effective_to", ["effective_to"]),
        ("ix_employee_work_schedules_backup_employee_id", ["backup_employee_id"]),
        ("ix_employee_work_schedules_status", ["status"]),
    ]:
        op.create_index(name, "employee_work_schedules", columns)

    op.create_table(
        "employee_work_schedule_days",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("employee_work_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("is_working_day", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("break_start_time", sa.Time(), nullable=True),
        sa.Column("break_end_time", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("schedule_id", "day_of_week", name="uq_employee_work_schedule_day"),
        sa.CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_employee_work_schedule_day_of_week"),
    )
    op.create_index("ix_employee_work_schedule_days_schedule_id", "employee_work_schedule_days", ["schedule_id"])

    op.add_column("staff_shifts", sa.Column("exception_type", sa.String(length=40), nullable=True))
    op.add_column("staff_shifts", sa.Column("exception_reason", sa.Text(), nullable=True))
    op.create_index("ix_staff_shifts_exception_type", "staff_shifts", ["exception_type"])

    for name, column in [
        ("default_employee_id", sa.Column("default_employee_id", sa.Integer(), nullable=True)),
        ("backup_employee_id", sa.Column("backup_employee_id", sa.Integer(), nullable=True)),
        ("time_sensitive", sa.Column("time_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("0"))),
        ("controlled_rescheduling", sa.Column("controlled_rescheduling", sa.Boolean(), nullable=False, server_default=sa.text("0"))),
        ("max_delay_minutes", sa.Column("max_delay_minutes", sa.Integer(), nullable=True)),
    ]:
        op.add_column("farm_activities", column)
    op.create_foreign_key("fk_farm_activities_default_employee", "farm_activities", "employees", ["default_employee_id"], ["id"] )
    op.create_foreign_key("fk_farm_activities_backup_employee", "farm_activities", "employees", ["backup_employee_id"], ["id"] )
    op.create_index("ix_farm_activities_default_employee_id", "farm_activities", ["default_employee_id"])
    op.create_index("ix_farm_activities_backup_employee_id", "farm_activities", ["backup_employee_id"])

    op.add_column("task_assignment_history", sa.Column("default_employee_id", sa.Integer(), nullable=True))
    op.add_column("task_assignment_history", sa.Column("schedule_id", sa.Integer(), nullable=True))
    op.add_column("task_assignment_history", sa.Column("schedule_exception_id", sa.Integer(), nullable=True))
    op.add_column("task_assignment_history", sa.Column("coverage_date", sa.Date(), nullable=True))
    op.create_foreign_key("fk_task_assignment_history_default_employee", "task_assignment_history", "employees", ["default_employee_id"], ["id"] )
    op.create_foreign_key("fk_task_assignment_history_schedule", "task_assignment_history", "employee_work_schedules", ["schedule_id"], ["id"] )
    op.create_foreign_key("fk_task_assignment_history_schedule_exception", "task_assignment_history", "staff_shifts", ["schedule_exception_id"], ["id"] )
    op.create_index("ix_task_assignment_history_default_employee_id", "task_assignment_history", ["default_employee_id"])
    op.create_index("ix_task_assignment_history_schedule_id", "task_assignment_history", ["schedule_id"])
    op.create_index("ix_task_assignment_history_schedule_exception_id", "task_assignment_history", ["schedule_exception_id"])
    op.create_index("ix_task_assignment_history_coverage_date", "task_assignment_history", ["coverage_date"])


def downgrade() -> None:
    for name in ["ix_task_assignment_history_coverage_date", "ix_task_assignment_history_schedule_exception_id", "ix_task_assignment_history_schedule_id", "ix_task_assignment_history_default_employee_id"]:
        op.drop_index(name, table_name="task_assignment_history")
    op.drop_constraint("fk_task_assignment_history_schedule_exception", "task_assignment_history", type_="foreignkey")
    op.drop_constraint("fk_task_assignment_history_schedule", "task_assignment_history", type_="foreignkey")
    op.drop_constraint("fk_task_assignment_history_default_employee", "task_assignment_history", type_="foreignkey")
    for name in ["coverage_date", "schedule_exception_id", "schedule_id", "default_employee_id"]:
        op.drop_column("task_assignment_history", name)

    op.drop_index("ix_farm_activities_backup_employee_id", table_name="farm_activities")
    op.drop_index("ix_farm_activities_default_employee_id", table_name="farm_activities")
    op.drop_constraint("fk_farm_activities_backup_employee", "farm_activities", type_="foreignkey")
    op.drop_constraint("fk_farm_activities_default_employee", "farm_activities", type_="foreignkey")
    for name in ["max_delay_minutes", "controlled_rescheduling", "time_sensitive", "backup_employee_id", "default_employee_id"]:
        op.drop_column("farm_activities", name)

    op.drop_index("ix_staff_shifts_exception_type", table_name="staff_shifts")
    op.drop_column("staff_shifts", "exception_reason")
    op.drop_column("staff_shifts", "exception_type")

    op.drop_index("ix_employee_work_schedule_days_schedule_id", table_name="employee_work_schedule_days")
    op.drop_table("employee_work_schedule_days")
    for name in ["ix_employee_work_schedules_status", "ix_employee_work_schedules_backup_employee_id", "ix_employee_work_schedules_effective_to", "ix_employee_work_schedules_effective_from", "ix_employee_work_schedules_employee_id"]:
        op.drop_index(name, table_name="employee_work_schedules")
    op.drop_table("employee_work_schedules")
