"""add system backups

Revision ID: b5e1d8a3c742
Revises: a84d9f2c6e11
Create Date: 2026-08-11 14:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5e1d8a3c742"
down_revision: Union[str, Sequence[str], None] = "a84d9f2c6e11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_backups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("backup_code", sa.String(length=40), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=600), nullable=False),
        sa.Column(
            "format_version",
            sa.String(length=20),
            server_default=sa.text("'1.0'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'Creating'"),
            nullable=False,
        ),
        sa.Column(
            "file_size_bytes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "table_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("GETDATE()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("backup_code"),
    )

    for column in (
        "backup_code",
        "status",
        "created_by_user_id",
        "created_at",
        "completed_at",
    ):
        op.create_index(
            op.f(f"ix_system_backups_{column}"),
            "system_backups",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "completed_at",
        "created_at",
        "created_by_user_id",
        "status",
        "backup_code",
    ):
        op.drop_index(
            op.f(f"ix_system_backups_{column}"),
            table_name="system_backups",
        )

    op.drop_table("system_backups")
