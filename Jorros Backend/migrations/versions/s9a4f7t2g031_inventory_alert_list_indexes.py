"""support bounded inventory and alert lists

Revision ID: s9a4f7t2g031
Revises: r8p3e6s1f920
"""
from typing import Sequence, Union

from alembic import op

revision: str = "s9a4f7t2g031"
down_revision: Union[str, Sequence[str], None] = "r8p3e6s1f920"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_farm_change_events_created_at", "farm_change_events", ["created_at", "id"])
    op.create_index("ix_inventory_items_active_page", "inventory_items", ["is_archived", "id"])
    op.create_index("ix_farm_alerts_active_page", "farm_alerts", ["status", "id"])
    op.create_index("ix_farm_alerts_history_page", "farm_alerts", ["status", "updated_at", "id"])


def downgrade():
    op.drop_index("ix_farm_alerts_history_page", table_name="farm_alerts")
    op.drop_index("ix_farm_alerts_active_page", table_name="farm_alerts")
    op.drop_index("ix_inventory_items_active_page", table_name="inventory_items")
    op.drop_index("ix_farm_change_events_created_at", table_name="farm_change_events")
