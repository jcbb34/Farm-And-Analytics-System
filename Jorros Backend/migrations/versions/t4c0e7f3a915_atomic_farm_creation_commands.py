"""Add durable idempotency records for atomic farm creation commands.

Revision ID: t4c0e7f3a915
Revises: s3b9d6e2f804
"""

from alembic import op
import sqlalchemy as sa


revision = "t4c0e7f3a915"
down_revision = "s3b9d6e2f804"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "farm_creation_commands",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("command_type", sa.String(length=30), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_farm_creation_commands_idempotency_key",
        "farm_creation_commands",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_farm_creation_commands_command_type",
        "farm_creation_commands",
        ["command_type"],
        unique=False,
    )
    op.create_index(
        "ix_farm_creation_commands_target_id",
        "farm_creation_commands",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        "ix_farm_creation_commands_created_by_user_id",
        "farm_creation_commands",
        ["created_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_farm_creation_commands_created_by_user_id", table_name="farm_creation_commands")
    op.drop_index("ix_farm_creation_commands_target_id", table_name="farm_creation_commands")
    op.drop_index("ix_farm_creation_commands_command_type", table_name="farm_creation_commands")
    op.drop_index("ix_farm_creation_commands_idempotency_key", table_name="farm_creation_commands")
    op.drop_table("farm_creation_commands")
