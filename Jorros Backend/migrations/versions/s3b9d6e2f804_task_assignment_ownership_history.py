"""Preserve task assignment ownership and reassignment history.

Revision ID: s3b9d6e2f804
Revises: r2a8c5d1e693
"""

from alembic import op
import sqlalchemy as sa


revision = "s3b9d6e2f804"
down_revision = "r2a8c5d1e693"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "farm_activities",
        sa.Column(
            "assignment_source",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )
    op.create_index(
        "ix_farm_activities_assignment_source",
        "farm_activities",
        ["assignment_source"],
        unique=False,
    )
    op.execute(
        "UPDATE farm_activities "
        "SET assignment_source = 'legacy_preserved' "
        "WHERE is_automatic = 1"
    )

    op.create_table(
        "task_assignment_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("old_employee_id", sa.Integer(), nullable=True),
        sa.Column("new_employee_id", sa.Integer(), nullable=True),
        sa.Column("assignment_source", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["farm_activities.id"]),
        sa.ForeignKeyConstraint(["old_employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["new_employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_assignment_history_activity_id",
        "task_assignment_history",
        ["activity_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_assignment_history_old_employee_id",
        "task_assignment_history",
        ["old_employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_assignment_history_new_employee_id",
        "task_assignment_history",
        ["new_employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_assignment_history_assignment_source",
        "task_assignment_history",
        ["assignment_source"],
        unique=False,
    )
    op.create_index(
        "ix_task_assignment_history_actor_user_id",
        "task_assignment_history",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_assignment_history_changed_at",
        "task_assignment_history",
        ["changed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_task_assignment_history_changed_at", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_actor_user_id", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_assignment_source", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_new_employee_id", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_old_employee_id", table_name="task_assignment_history")
    op.drop_index("ix_task_assignment_history_activity_id", table_name="task_assignment_history")
    op.drop_table("task_assignment_history")
    op.drop_index("ix_farm_activities_assignment_source", table_name="farm_activities")
    op.drop_column("farm_activities", "assignment_source")
