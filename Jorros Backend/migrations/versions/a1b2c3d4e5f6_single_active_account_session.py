"""Track one active account session across API workers.

Revision ID: a1b2c3d4e5f6
Revises: s9a4f7t2g031
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "s9a4f7t2g031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("active_session_auth_version", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("active_session_expires_at", sa.DateTime(), nullable=True))
    # Previously issued tokens have no database claim; require a fresh sign-in.
    op.execute(sa.text("UPDATE users SET auth_version = auth_version + 1"))


def downgrade():
    op.drop_column("users", "active_session_expires_at")
    op.drop_column("users", "active_session_auth_version")
    # Keep tokens revoked by the upgrade revoked after a rollback.
