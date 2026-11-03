"""Add farm-local roster and leave decision audit fields.

Revision ID: x8h4c1e7f359
Revises: w7f3b0d6e248
"""

from alembic import op
import sqlalchemy as sa

revision = "x8h4c1e7f359"
down_revision = "w7f3b0d6e248"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("staff_leave", sa.Column("requested_by_user_id", sa.Integer(), nullable=True))
    op.add_column("staff_leave", sa.Column("decided_by_user_id", sa.Integer(), nullable=True))
    op.add_column("staff_leave", sa.Column("decided_at", sa.DateTime(), nullable=True))
    op.add_column("staff_leave", sa.Column("decision_notes", sa.Text(), nullable=True))
    op.add_column("staff_leave", sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True))
    op.add_column("staff_leave", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_staff_leave_requested_by_user", "staff_leave", "users", ["requested_by_user_id"], ["id"])
    op.create_foreign_key("fk_staff_leave_decided_by_user", "staff_leave", "users", ["decided_by_user_id"], ["id"])
    op.create_foreign_key("fk_staff_leave_cancelled_by_user", "staff_leave", "users", ["cancelled_by_user_id"], ["id"])
    op.create_index("ix_staff_leave_requested_by_user_id", "staff_leave", ["requested_by_user_id"])
    op.create_index("ix_staff_leave_decided_by_user_id", "staff_leave", ["decided_by_user_id"])
    op.create_index("ix_staff_leave_cancelled_by_user_id", "staff_leave", ["cancelled_by_user_id"])

    # Existing approved leave was management-recorded before explicit request /
    # decision audit fields existed. Preserve it and identify the recorder as the
    # best available legacy request/decision actor without rewriting leave dates.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE staff_leave SET requested_by_user_id = recorded_by_user_id "
        "WHERE requested_by_user_id IS NULL AND recorded_by_user_id IS NOT NULL"
    ))
    bind.execute(sa.text(
        "UPDATE staff_leave SET decided_by_user_id = recorded_by_user_id, decided_at = created_at "
        "WHERE status = 'Approved' AND decided_by_user_id IS NULL AND recorded_by_user_id IS NOT NULL"
    ))

    op.create_table(
        "staff_shifts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("assigned_area", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'Scheduled'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_staff_shift_employee_date"),
    )
    op.create_index("ix_staff_shifts_employee_id", "staff_shifts", ["employee_id"])
    op.create_index("ix_staff_shifts_work_date", "staff_shifts", ["work_date"])
    op.create_index("ix_staff_shifts_status", "staff_shifts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_staff_shifts_status", table_name="staff_shifts")
    op.drop_index("ix_staff_shifts_work_date", table_name="staff_shifts")
    op.drop_index("ix_staff_shifts_employee_id", table_name="staff_shifts")
    op.drop_table("staff_shifts")

    op.drop_index("ix_staff_leave_cancelled_by_user_id", table_name="staff_leave")
    op.drop_index("ix_staff_leave_decided_by_user_id", table_name="staff_leave")
    op.drop_index("ix_staff_leave_requested_by_user_id", table_name="staff_leave")
    op.drop_constraint("fk_staff_leave_cancelled_by_user", "staff_leave", type_="foreignkey")
    op.drop_constraint("fk_staff_leave_decided_by_user", "staff_leave", type_="foreignkey")
    op.drop_constraint("fk_staff_leave_requested_by_user", "staff_leave", type_="foreignkey")
    op.drop_column("staff_leave", "cancelled_at")
    op.drop_column("staff_leave", "cancelled_by_user_id")
    op.drop_column("staff_leave", "decision_notes")
    op.drop_column("staff_leave", "decided_at")
    op.drop_column("staff_leave", "decided_by_user_id")
    op.drop_column("staff_leave", "requested_by_user_id")
