"""Crop partial/final harvest lifecycle and task linkage.

Revision ID: d4n0i7k3f915
Revises: c3m9h6j2e804
"""

from alembic import op
import sqlalchemy as sa

revision = "d4n0i7k3f915"
down_revision = "c3m9h6j2e804"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crops", sa.Column("confirmed_ready_at", sa.DateTime(), nullable=True))
    op.add_column("crops", sa.Column("confirmed_ready_by_user_id", sa.Integer(), nullable=True))
    op.add_column("crops", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.add_column("crops", sa.Column("completed_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_crops_confirmed_ready_by", "crops", "users", ["confirmed_ready_by_user_id"], ["id"])
    op.create_foreign_key("fk_crops_completed_by", "crops", "users", ["completed_by_user_id"], ["id"])
    op.create_index("ix_crops_confirmed_ready_at", "crops", ["confirmed_ready_at"])
    op.create_index("ix_crops_confirmed_ready_by_user_id", "crops", ["confirmed_ready_by_user_id"])
    op.create_index("ix_crops_completed_at", "crops", ["completed_at"])
    op.create_index("ix_crops_completed_by_user_id", "crops", ["completed_by_user_id"])

    op.add_column("crop_yield_records", sa.Column("performed_by_employee_id", sa.Integer(), nullable=True))
    op.add_column("crop_yield_records", sa.Column("related_task_id", sa.Integer(), nullable=True))
    op.add_column("crop_yield_records", sa.Column("manual_reason", sa.Text(), nullable=True))
    op.add_column("crop_yield_records", sa.Column("evidence_url", sa.String(length=500), nullable=True))
    op.create_foreign_key("fk_crop_yield_performed_by", "crop_yield_records", "employees", ["performed_by_employee_id"], ["id"])
    op.create_foreign_key("fk_crop_yield_related_task", "crop_yield_records", "farm_activities", ["related_task_id"], ["id"])
    op.create_index("ix_crop_yield_records_performed_by_employee_id", "crop_yield_records", ["performed_by_employee_id"])
    op.create_index("ix_crop_yield_records_related_task_id", "crop_yield_records", ["related_task_id"])
    op.create_index(
        "ux_crop_yield_related_task_not_null",
        "crop_yield_records",
        ["related_task_id"],
        unique=True,
        mssql_where=sa.text("related_task_id IS NOT NULL"),
        sqlite_where=sa.text("related_task_id IS NOT NULL"),
    )

    # Preserve existing historical meaning. Existing Harvested rows are completed
    # crop cycles, but no readiness confirmation is fabricated during migration.
    op.execute(
        "UPDATE crops SET completed_at = updated_at "
        "WHERE status = 'Harvested' AND completed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ux_crop_yield_related_task_not_null", table_name="crop_yield_records")
    op.drop_index("ix_crop_yield_records_related_task_id", table_name="crop_yield_records")
    op.drop_index("ix_crop_yield_records_performed_by_employee_id", table_name="crop_yield_records")
    op.drop_constraint("fk_crop_yield_related_task", "crop_yield_records", type_="foreignkey")
    op.drop_constraint("fk_crop_yield_performed_by", "crop_yield_records", type_="foreignkey")
    op.drop_column("crop_yield_records", "evidence_url")
    op.drop_column("crop_yield_records", "manual_reason")
    op.drop_column("crop_yield_records", "related_task_id")
    op.drop_column("crop_yield_records", "performed_by_employee_id")

    op.drop_index("ix_crops_completed_by_user_id", table_name="crops")
    op.drop_index("ix_crops_completed_at", table_name="crops")
    op.drop_index("ix_crops_confirmed_ready_by_user_id", table_name="crops")
    op.drop_index("ix_crops_confirmed_ready_at", table_name="crops")
    op.drop_constraint("fk_crops_completed_by", "crops", type_="foreignkey")
    op.drop_constraint("fk_crops_confirmed_ready_by", "crops", type_="foreignkey")
    op.drop_column("crops", "completed_by_user_id")
    op.drop_column("crops", "completed_at")
    op.drop_column("crops", "confirmed_ready_by_user_id")
    op.drop_column("crops", "confirmed_ready_at")
