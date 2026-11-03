"""transactional farm change events and task-list indexes

Revision ID: r8p3e6s1f920
Revises: q9e5n2t8b014
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "r8p3e6s1f920"
down_revision: Union[str, Sequence[str], None] = "q9e5n2t8b014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "farm_change_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("modules_json", sa.Text(), nullable=False),
        sa.Column("target_employee_id", sa.Integer()),
        sa.Column("target_user_id", sa.Integer()),
        sa.Column("record_version", sa.String(60)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_farm_change_events_employee_id", "farm_change_events", ["target_employee_id", "id"])
    op.create_index("ix_farm_change_events_user_id", "farm_change_events", ["target_user_id", "id"])
    op.create_index("ix_farm_activities_page_status", "farm_activities", ["is_archived", "status", "activity_date", "id"])
    op.create_index("ix_farm_activities_employee_page", "farm_activities", ["assigned_employee_id", "is_archived", "status", "activity_date", "id"])


def downgrade():
    op.drop_index("ix_farm_activities_employee_page", table_name="farm_activities")
    op.drop_index("ix_farm_activities_page_status", table_name="farm_activities")
    op.drop_index("ix_farm_change_events_user_id", table_name="farm_change_events")
    op.drop_index("ix_farm_change_events_employee_id", table_name="farm_change_events")
    op.drop_table("farm_change_events")
