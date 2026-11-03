"""Add task-bound workforce evidence audit records.

Revision ID: u5d1f8a4b026
Revises: t4c0e7f3a915
"""

from alembic import op
import sqlalchemy as sa


revision = "u5d1f8a4b026"
down_revision = "t4c0e7f3a915"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=True),
        sa.Column("uploader_user_id", sa.Integer(), nullable=False),
        sa.Column("original_display_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=60), nullable=False),
        sa.Column("storage_identifier", sa.String(length=120), nullable=False),
        sa.Column("thumbnail_storage_identifier", sa.String(length=140), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Temporary'"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("attached_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["farm_activities.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["task_submissions.id"]),
        sa.ForeignKeyConstraint(["uploader_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("storage_identifier"),
        sa.UniqueConstraint("thumbnail_storage_identifier"),
    )
    for column in ("public_id", "activity_id", "submission_id", "uploader_user_id", "sha256", "status", "expires_at", "created_at"):
        op.create_index(f"ix_task_evidence_{column}", "task_evidence", [column], unique=False)


def downgrade() -> None:
    for column in reversed(("public_id", "activity_id", "submission_id", "uploader_user_id", "sha256", "status", "expires_at", "created_at")):
        op.drop_index(f"ix_task_evidence_{column}", table_name="task_evidence")
    op.drop_table("task_evidence")
