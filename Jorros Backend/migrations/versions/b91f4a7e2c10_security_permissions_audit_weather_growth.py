"""security permissions audit weather and crop growth

Revision ID: b91f4a7e2c10
Revises: a12f7c3d9b45
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b91f4a7e2c10"
down_revision: Union[str, Sequence[str], None] = "a12f7c3d9b45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roles", sa.Column("permissions_json", sa.Text(), nullable=True))

    op.add_column("users", sa.Column("two_factor_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "two_factor_enabled",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=180), nullable=False),
        sa.Column("module", sa.String(length=60), nullable=False),
        sa.Column("record_name", sa.String(length=180), nullable=True),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("GETDATE()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_module", "audit_logs", ["module"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "weather_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recorded_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(length=150), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("humidity_percent", sa.Integer(), nullable=False),
        sa.Column("rainfall_mm", sa.Float(), nullable=False),
        sa.Column("wind_speed_kph", sa.Float(), nullable=False),
        sa.Column("condition", sa.String(length=80), nullable=False),
        sa.Column("weather_code", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("GETDATE()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("GETDATE()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recorded_date", name="uq_weather_history_recorded_date"),
    )
    op.create_index("ix_weather_history_recorded_date", "weather_history", ["recorded_date"])

    op.add_column(
        "crops",
        sa.Column("growth_stage", sa.String(length=40), server_default=sa.text("'Seeded'"), nullable=False),
    )
    op.add_column(
        "crops",
        sa.Column("quantity_planted", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "crops",
        sa.Column("current_surviving", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index("ix_crops_growth_stage", "crops", ["growth_stage"])

    # Preserve each existing crop's approximate visual progress as a stage.
    op.execute(
        """
        UPDATE crops
        SET growth_stage = CASE
            WHEN status = 'Harvested' THEN 'Harvested'
            WHEN current_growth >= 100 THEN 'Harvest Ready'
            WHEN current_growth >= 90 THEN 'Maturity'
            WHEN current_growth >= 80 THEN 'Fruiting'
            WHEN current_growth >= 65 THEN 'Flowering'
            WHEN current_growth >= 50 THEN 'Vegetative'
            WHEN current_growth >= 30 THEN 'Seedling'
            WHEN current_growth >= 15 THEN 'Germination'
            ELSE 'Seeded'
        END
        """
    )

    op.add_column("crop_growth_records", sa.Column("growth_stage", sa.String(length=40), nullable=True))
    op.add_column("crop_growth_records", sa.Column("current_surviving", sa.Integer(), nullable=True))

    # Make automatic report generation idempotent across multiple server workers.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, automation_period_key,
                   ROW_NUMBER() OVER (
                       PARTITION BY automation_period_key
                       ORDER BY id
                   ) AS row_num
            FROM farm_reports
            WHERE automation_period_key IS NOT NULL
        )
        UPDATE farm_reports
        SET automation_period_key = CONCAT(
            farm_reports.automation_period_key,
            '-DUP-',
            farm_reports.id
        )
        FROM farm_reports
        INNER JOIN ranked ON ranked.id = farm_reports.id
        WHERE ranked.row_num > 1
        """
    )
    op.drop_index("ix_farm_reports_automation_period_key", table_name="farm_reports")
    op.create_index(
        "uq_farm_reports_automation_period_key_not_null",
        "farm_reports",
        ["automation_period_key"],
        unique=True,
        mssql_where=sa.text("automation_period_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_farm_reports_automation_period_key_not_null", table_name="farm_reports")
    op.create_index("ix_farm_reports_automation_period_key", "farm_reports", ["automation_period_key"], unique=False)

    op.drop_column("crop_growth_records", "current_surviving")
    op.drop_column("crop_growth_records", "growth_stage")

    op.drop_index("ix_crops_growth_stage", table_name="crops")
    op.drop_column("crops", "current_surviving")
    op.drop_column("crops", "quantity_planted")
    op.drop_column("crops", "growth_stage")

    op.drop_index("ix_weather_history_recorded_date", table_name="weather_history")
    op.drop_table("weather_history")

    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_module", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_column("users", "two_factor_enabled")
    op.drop_column("users", "two_factor_secret")
    op.drop_column("roles", "permissions_json")
