"""Attendance sessions, punctuality settings, and audit history.

Revision ID: c3m9h6j2e804
Revises: b2l8g5i1d793
"""

from alembic import op
import sqlalchemy as sa

revision = "c3m9h6j2e804"
down_revision = "b2l8g5i1d793"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in [
        ("scheduled_shift_id", sa.Column("scheduled_shift_id", sa.Integer(), nullable=True)),
        ("scheduled_start_time", sa.Column("scheduled_start_time", sa.Time(), nullable=True)),
        ("scheduled_end_time", sa.Column("scheduled_end_time", sa.Time(), nullable=True)),
        ("check_in_at", sa.Column("check_in_at", sa.DateTime(), nullable=True)),
        ("check_out_at", sa.Column("check_out_at", sa.DateTime(), nullable=True)),
        ("minutes_late", sa.Column("minutes_late", sa.Integer(), nullable=True)),
        ("minutes_early", sa.Column("minutes_early", sa.Integer(), nullable=True)),
        ("overtime_minutes", sa.Column("overtime_minutes", sa.Integer(), nullable=True)),
        ("attendance_source", sa.Column("attendance_source", sa.String(length=30), nullable=False, server_default=sa.text("'Manager Assisted'"))),
        ("correction_reason", sa.Column("correction_reason", sa.Text(), nullable=True)),
        ("updated_by_user_id", sa.Column("updated_by_user_id", sa.Integer(), nullable=True)),
    ]:
        op.add_column("staff_attendance", column)
    op.create_foreign_key("fk_staff_attendance_shift", "staff_attendance", "staff_shifts", ["scheduled_shift_id"], ["id"])
    op.create_foreign_key("fk_staff_attendance_updated_by", "staff_attendance", "users", ["updated_by_user_id"], ["id"])
    for name, columns in [
        ("ix_staff_attendance_scheduled_shift_id", ["scheduled_shift_id"]),
        ("ix_staff_attendance_check_in_at", ["check_in_at"]),
        ("ix_staff_attendance_check_out_at", ["check_out_at"]),
        ("ix_staff_attendance_attendance_source", ["attendance_source"]),
        ("ix_staff_attendance_recorded_by_user_id", ["recorded_by_user_id"]),
        ("ix_staff_attendance_updated_by_user_id", ["updated_by_user_id"]),
    ]:
        op.create_index(name, "staff_attendance", columns)

    op.create_table(
        "staff_attendance_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("attendance_id", sa.Integer(), sa.ForeignKey("staff_attendance.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("old_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=True),
        sa.Column("old_check_in_at", sa.DateTime(), nullable=True),
        sa.Column("new_check_in_at", sa.DateTime(), nullable=True),
        sa.Column("old_check_out_at", sa.DateTime(), nullable=True),
        sa.Column("new_check_out_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for name, columns in [
        ("ix_staff_attendance_audit_attendance_id", ["attendance_id"]),
        ("ix_staff_attendance_audit_employee_id", ["employee_id"]),
        ("ix_staff_attendance_audit_work_date", ["work_date"]),
        ("ix_staff_attendance_audit_action", ["action"]),
        ("ix_staff_attendance_audit_actor_user_id", ["actor_user_id"]),
        ("ix_staff_attendance_audit_created_at", ["created_at"]),
    ]:
        op.create_index(name, "staff_attendance_audit", columns)

    op.create_table(
        "attendance_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("check_in_grace_minutes", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("earliest_check_in_minutes", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("early_departure_grace_minutes", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("missing_checkout_cutoff_minutes", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("attendance_reminder_minutes", sa.Integer(), nullable=False, server_default=sa.text("15")),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("attendance_settings")
    for name in [
        "ix_staff_attendance_audit_created_at", "ix_staff_attendance_audit_actor_user_id",
        "ix_staff_attendance_audit_action", "ix_staff_attendance_audit_work_date",
        "ix_staff_attendance_audit_employee_id", "ix_staff_attendance_audit_attendance_id",
    ]:
        op.drop_index(name, table_name="staff_attendance_audit")
    op.drop_table("staff_attendance_audit")

    for name in [
        "ix_staff_attendance_updated_by_user_id", "ix_staff_attendance_recorded_by_user_id",
        "ix_staff_attendance_attendance_source", "ix_staff_attendance_check_out_at",
        "ix_staff_attendance_check_in_at", "ix_staff_attendance_scheduled_shift_id",
    ]:
        op.drop_index(name, table_name="staff_attendance")
    op.drop_constraint("fk_staff_attendance_updated_by", "staff_attendance", type_="foreignkey")
    op.drop_constraint("fk_staff_attendance_shift", "staff_attendance", type_="foreignkey")
    for name in [
        "updated_by_user_id", "correction_reason", "attendance_source", "overtime_minutes",
        "minutes_early", "minutes_late", "check_out_at", "check_in_at",
        "scheduled_end_time", "scheduled_start_time", "scheduled_shift_id",
    ]:
        op.drop_column("staff_attendance", name)
