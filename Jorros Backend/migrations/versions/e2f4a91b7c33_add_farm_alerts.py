"""add farm alerts and alert settings

Revision ID: e2f4a91b7c33
Revises: c14f07a6b892
Create Date: 2026-08-10 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f4a91b7c33"
down_revision: Union[str, Sequence[str], None] = "c14f07a6b892"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farm_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column("alert_type", sa.String(length=100), nullable=False),
        sa.Column("condition", sa.String(length=30), nullable=False),
        sa.Column("threshold", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.String(length=20), server_default=sa.text("'Medium'"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Active'"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_triggered", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_farm_alerts_alert_name"), "farm_alerts", ["alert_name"], unique=False)
    op.create_index(op.f("ix_farm_alerts_category"), "farm_alerts", ["category"], unique=False)
    op.create_index(op.f("ix_farm_alerts_subject"), "farm_alerts", ["subject"], unique=False)
    op.create_index(op.f("ix_farm_alerts_alert_type"), "farm_alerts", ["alert_type"], unique=False)
    op.create_index(op.f("ix_farm_alerts_priority"), "farm_alerts", ["priority"], unique=False)
    op.create_index(op.f("ix_farm_alerts_status"), "farm_alerts", ["status"], unique=False)

    op.create_table(
        "alert_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_planting_reminder", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("crop_growth_check", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("crop_harvest_reminder", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("crop_pest_disease_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("crop_harvest_advance_days", sa.Integer(), server_default=sa.text("7"), nullable=False),
        sa.Column("crop_growth_check_frequency", sa.Integer(), server_default=sa.text("7"), nullable=False),
        sa.Column("crop_soil_moisture_threshold", sa.Float(), server_default=sa.text("30"), nullable=False),
        sa.Column("livestock_feeding_reminder", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("livestock_vaccination_reminder", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("livestock_health_check", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("livestock_production_check", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("livestock_vaccination_advance_days", sa.Integer(), server_default=sa.text("7"), nullable=False),
        sa.Column("livestock_health_check_frequency", sa.Integer(), server_default=sa.text("14"), nullable=False),
        sa.Column("livestock_feeding_reminder_time", sa.String(length=5), server_default=sa.text("'06:00'"), nullable=False),
        sa.Column("weather_heavy_rain_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("weather_high_temperature_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("weather_strong_wind_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("weather_thunderstorm_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("weather_rainfall_threshold", sa.Float(), server_default=sa.text("80"), nullable=False),
        sa.Column("weather_temperature_threshold", sa.Float(), server_default=sa.text("32"), nullable=False),
        sa.Column("weather_wind_speed_threshold", sa.Float(), server_default=sa.text("40"), nullable=False),
        sa.Column("system_backup_reminder", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("system_low_inventory_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("system_low_storage_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("system_failed_login_alert", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("system_backup_frequency", sa.Integer(), server_default=sa.text("7"), nullable=False),
        sa.Column("system_storage_threshold", sa.Float(), server_default=sa.text("10"), nullable=False),
        sa.Column("system_failed_login_limit", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("alert_settings")
    op.drop_index(op.f("ix_farm_alerts_status"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_priority"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_alert_type"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_subject"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_category"), table_name="farm_alerts")
    op.drop_index(op.f("ix_farm_alerts_alert_name"), table_name="farm_alerts")
    op.drop_table("farm_alerts")
