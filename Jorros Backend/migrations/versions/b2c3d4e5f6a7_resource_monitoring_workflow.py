"""Resource monitoring schedules and approved observation provenance.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    for table, enabled in [("crops", "1"), ("livestock", "0")]:
        op.add_column(table, sa.Column("monitoring_enabled", sa.Boolean(), nullable=False, server_default=sa.text(enabled)))
        op.add_column(table, sa.Column("monitoring_start_date", sa.Date(), nullable=True))
        op.add_column(table, sa.Column("monitoring_end_date", sa.Date(), nullable=True))
        op.add_column(table, sa.Column("monitoring_frequency_days", sa.Integer(), nullable=True))
    op.add_column("crops", sa.Column("observed_growth_stage", sa.String(40), nullable=True))
    op.add_column("crops", sa.Column("last_observation_date", sa.Date(), nullable=True))
    op.add_column("crops", sa.Column("survival_count_date", sa.Date(), nullable=True))
    op.execute("UPDATE crops SET survival_count_date = CASE WHEN (SELECT MAX(update_date) FROM crop_growth_records WHERE crop_growth_records.crop_id = crops.id) > CAST(crops.updated_at AS DATE) THEN (SELECT MAX(update_date) FROM crop_growth_records WHERE crop_growth_records.crop_id = crops.id) ELSE CAST(crops.updated_at AS DATE) END")
    op.add_column("task_submissions", sa.Column("monitoring_data_json", sa.Text(), nullable=True))
    for table in ["crop_growth_records", "livestock_growth_records"]:
        for name, target in [("task_submission_id", "task_submissions"), ("related_task_id", "farm_activities"), ("approved_by_user_id", "users")]:
            op.add_column(table, sa.Column(name, sa.Integer(), nullable=True))
            op.create_foreign_key(f"fk_{table}_{name}", table, target, [name], ["id"])
        op.create_index(f"ux_{table}_submission", table, ["task_submission_id"], unique=True,
                        mssql_where=sa.text("task_submission_id IS NOT NULL"), sqlite_where=sa.text("task_submission_id IS NOT NULL"))
    op.add_column("crop_growth_records", sa.Column("observed_stage", sa.String(40), nullable=True))


def downgrade():
    op.drop_column("crop_growth_records", "observed_stage")
    for table in ["crop_growth_records", "livestock_growth_records"]:
        op.drop_index(f"ux_{table}_submission", table_name=table)
        for name in ["approved_by_user_id", "related_task_id", "task_submission_id"]:
            op.drop_constraint(f"fk_{table}_{name}", table, type_="foreignkey")
            op.drop_column(table, name, mssql_drop_default=True)
    op.drop_column("task_submissions", "monitoring_data_json")
    op.drop_column("crops", "survival_count_date")
    op.drop_column("crops", "last_observation_date")
    op.drop_column("crops", "observed_growth_stage")
    for table in ["livestock", "crops"]:
        for name in ["monitoring_frequency_days", "monitoring_end_date", "monitoring_start_date", "monitoring_enabled"]:
            op.drop_column(table, name, mssql_drop_default=True)
