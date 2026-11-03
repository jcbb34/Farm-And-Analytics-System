"""professional pdf and automatic report schedules

Revision ID: c6f2a94e8d31
Revises: b5e1d8a3c742
Create Date: 2026-08-11 19:05:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c6f2a94e8d31"
down_revision: Union[str, Sequence[str], None] = "b5e1d8a3c742"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("farm_reports", sa.Column("is_automatic", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.add_column("farm_reports", sa.Column("frequency", sa.String(length=20), nullable=True))
    op.add_column("farm_reports", sa.Column("automation_period_key", sa.String(length=80), nullable=True))
    op.add_column("farm_reports", sa.Column("pdf_filename", sa.String(length=255), nullable=True))

    op.create_index(op.f("ix_farm_reports_is_automatic"), "farm_reports", ["is_automatic"], unique=False)
    op.create_index(op.f("ix_farm_reports_frequency"), "farm_reports", ["frequency"], unique=False)
    op.create_index(op.f("ix_farm_reports_automation_period_key"), "farm_reports", ["automation_period_key"], unique=False)

    op.create_table(
        "report_automation_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("daily_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("daily_time", sa.String(length=5), server_default="00:05", nullable=False),
        sa.Column("weekly_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("weekly_day", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("weekly_time", sa.String(length=5), server_default="00:10", nullable=False),
        sa.Column("monthly_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("monthly_day", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("monthly_time", sa.String(length=5), server_default="00:15", nullable=False),
        sa.Column("yearly_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("yearly_month", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("yearly_day", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("yearly_time", sa.String(length=5), server_default="00:20", nullable=False),
        sa.Column("prepared_by", sa.String(length=150), server_default="System Generated", nullable=False),
        sa.Column("auto_generate_pdf", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_scheduler_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("GETDATE()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("GETDATE()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("report_automation_settings")
    op.drop_index(op.f("ix_farm_reports_automation_period_key"), table_name="farm_reports")
    op.drop_index(op.f("ix_farm_reports_frequency"), table_name="farm_reports")
    op.drop_index(op.f("ix_farm_reports_is_automatic"), table_name="farm_reports")
    op.drop_column("farm_reports", "pdf_filename")
    op.drop_column("farm_reports", "automation_period_key")
    op.drop_column("farm_reports", "frequency")
    op.drop_column("farm_reports", "is_automatic")
