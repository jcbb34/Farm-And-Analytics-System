"""Employee archive metadata and lifecycle support.

Revision ID: q1f7b4c0d582
Revises: p0e6d3a9f471
"""

from alembic import op
import sqlalchemy as sa

revision = "q1f7b4c0d582"
down_revision = "p0e6d3a9f471"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("employees", sa.Column("archived_by_user_id", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_employees_archived_by_user_id_users",
        "employees",
        "users",
        ["archived_by_user_id"],
        ["id"],
    )
    op.create_index("ix_employees_archived_at", "employees", ["archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_employees_archived_at", table_name="employees")
    op.drop_constraint("fk_employees_archived_by_user_id_users", "employees", type_="foreignkey")
    op.drop_column("employees", "archive_reason")
    op.drop_column("employees", "archived_by_user_id")
    op.drop_column("employees", "archived_at")
