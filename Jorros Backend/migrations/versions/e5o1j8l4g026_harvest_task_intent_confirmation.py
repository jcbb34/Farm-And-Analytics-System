"""Persist crop harvest task intent and manager-confirmed harvest type.

Revision ID: e5o1j8l4g026
Revises: d4n0i7k3f915
"""

from alembic import op
import sqlalchemy as sa

revision = "e5o1j8l4g026"
down_revision = "d4n0i7k3f915"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_submissions", sa.Column("harvest_type_intent", sa.String(length=30), nullable=True))
    op.add_column("task_submissions", sa.Column("harvest_type_confirmed", sa.String(length=30), nullable=True))
    op.create_index("ix_task_submissions_harvest_type_intent", "task_submissions", ["harvest_type_intent"])
    op.create_index("ix_task_submissions_harvest_type_confirmed", "task_submissions", ["harvest_type_confirmed"])


def downgrade() -> None:
    op.drop_index("ix_task_submissions_harvest_type_confirmed", table_name="task_submissions")
    op.drop_index("ix_task_submissions_harvest_type_intent", table_name="task_submissions")
    op.drop_column("task_submissions", "harvest_type_confirmed")
    op.drop_column("task_submissions", "harvest_type_intent")
