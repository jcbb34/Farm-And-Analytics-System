"""add farm reports

Revision ID: a84d9f2c6e11
Revises: f7b3c41d9e20
Create Date: 2026-08-11 12:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a84d9f2c6e11"
down_revision: Union[str, Sequence[str], None] = "f7b3c41d9e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farm_reports",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "report_code",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.String(length=40),
            nullable=False,
        ),
        sa.Column(
            "report_type",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "start_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "end_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "generated_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "prepared_by",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "snapshot_json",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "generated_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("GETDATE()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("GETDATE()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_code"),
    )

    for column in (
        "report_code",
        "title",
        "category",
        "report_type",
        "start_date",
        "end_date",
        "generated_date",
        "status",
    ):
        op.create_index(
            op.f(f"ix_farm_reports_{column}"),
            "farm_reports",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "status",
        "generated_date",
        "end_date",
        "start_date",
        "report_type",
        "category",
        "title",
        "report_code",
    ):
        op.drop_index(
            op.f(f"ix_farm_reports_{column}"),
            table_name="farm_reports",
        )

    op.drop_table("farm_reports")
