"""Store crop flowering/shooting observations for maturity estimates.

Revision ID: c5v7w0x2y384
Revises: b4r6s9t1u273
"""
from alembic import op
import sqlalchemy as sa

revision = "c5v7w0x2y384"
down_revision = "b4r6s9t1u273"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "crop_maturity_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("crop_id", sa.Integer(), sa.ForeignKey("crops.id"), nullable=False),
        sa.Column("event_kind", sa.String(30), nullable=False),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_crop_maturity_event_crop_id", "crop_maturity_events", ["crop_id"])
    op.create_index("ix_crop_maturity_event_crop_kind", "crop_maturity_events", ["crop_id", "event_kind", "observed_date"])

def downgrade():
    op.drop_index("ix_crop_maturity_event_crop_kind", table_name="crop_maturity_events")
    op.drop_index("ix_crop_maturity_event_crop_id", table_name="crop_maturity_events")
    op.drop_table("crop_maturity_events")
