"""Add indexes for login throttling and account history.

Revision ID: n8c4b1e7d250
Revises: m7f1c2d8a640
"""

from alembic import op
from sqlalchemy import inspect


revision = "n8c4b1e7d250"
down_revision = "m7f1c2d8a640"
branch_labels = None
depends_on = None


INDEX_THROTTLE = "ix_login_history_username_ip_created_at"
INDEX_USER_HISTORY = "ix_login_history_user_created_at"


def _index_names() -> set[str]:
    inspector = inspect(op.get_bind())
    return {
        str(item.get("name"))
        for item in inspector.get_indexes("login_history")
        if item.get("name")
    }


def upgrade() -> None:
    existing = _index_names()

    if INDEX_THROTTLE not in existing:
        op.create_index(
            INDEX_THROTTLE,
            "login_history",
            ["username", "ip_address", "created_at"],
            unique=False,
        )

    if INDEX_USER_HISTORY not in existing:
        op.create_index(
            INDEX_USER_HISTORY,
            "login_history",
            ["user_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    existing = _index_names()

    if INDEX_USER_HISTORY in existing:
        op.drop_index(INDEX_USER_HISTORY, table_name="login_history")

    if INDEX_THROTTLE in existing:
        op.drop_index(INDEX_THROTTLE, table_name="login_history")
