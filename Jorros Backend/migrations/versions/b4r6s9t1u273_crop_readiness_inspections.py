"""Persist crop variety readiness inspections and observations.

Revision ID: b4r6s9t1u273
Revises: a1f7c2b9d604
"""
from alembic import op
import sqlalchemy as sa

revision = "b4r6s9t1u273"
down_revision = "a1f7c2b9d604"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crop_readiness_inspections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("crop_id", sa.Integer(), sa.ForeignKey("crops.id"), nullable=False),
        sa.Column("inspected_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("inspection_date", sa.Date(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("profile_key", sa.String(length=50), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("criteria_json", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("verdict IN ('ready', 'not_ready')", name="ck_crop_readiness_verdict"),
    )
    op.create_index("ix_crop_readiness_crop_date", "crop_readiness_inspections", ["crop_id", "inspection_date"])


def downgrade():
    op.drop_index("ix_crop_readiness_crop_date", table_name="crop_readiness_inspections")
    op.drop_table("crop_readiness_inspections")
