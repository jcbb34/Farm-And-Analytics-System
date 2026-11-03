from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FarmAlert(Base):
    __tablename__ = "farm_alerts"
    __table_args__ = (
        Index("ix_farm_alerts_active_page", "status", "id"),
        Index("ix_farm_alerts_history_page", "status", "updated_at", "id"),
        # The bell requests the newest 30 triggered alerts on every refresh.
        Index("ix_farm_alerts_triggered_preview", "last_triggered", "id",
              mssql_where=text("last_triggered IS NOT NULL"),
              sqlite_where=text("last_triggered IS NOT NULL")),
        Index(
            "uq_farm_alerts_automatic_source",
            "source_type",
            "source_id",
            "alert_type",
            unique=True,
            mssql_where=text(
                "is_automatic = 1 AND source_type IS NOT NULL AND source_id IS NOT NULL"
            ),
            sqlite_where=text(
                "is_automatic = 1 AND source_type IS NOT NULL AND source_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    alert_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    subject: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        index=True,
    )

    alert_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    condition: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    threshold: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Medium",
        server_default=text("'Medium'"),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Active",
        server_default=text("'Active'"),
        index=True,
    )

    is_automatic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    source_type: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        index=True,
    )

    source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    last_triggered: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AlertSettings(Base):
    __tablename__ = "alert_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    crop_planting_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    crop_growth_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    crop_harvest_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    crop_pest_disease_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    crop_harvest_advance_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )
    crop_growth_check_frequency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )
    crop_soil_moisture_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=30, server_default=text("30")
    )

    livestock_feeding_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    livestock_vaccination_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    livestock_health_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    livestock_production_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    livestock_vaccination_advance_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )
    livestock_health_check_frequency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14, server_default=text("14")
    )
    livestock_feeding_reminder_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="06:00", server_default=text("'06:00'")
    )

    weather_heavy_rain_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    weather_high_temperature_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    weather_strong_wind_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    weather_thunderstorm_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    weather_rainfall_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=80, server_default=text("80")
    )
    weather_temperature_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=32, server_default=text("32")
    )
    weather_wind_speed_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=40, server_default=text("40")
    )

    system_backup_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    system_low_inventory_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    system_low_storage_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    system_failed_login_alert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    system_backup_frequency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )
    system_storage_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=10, server_default=text("10")
    )
    system_failed_login_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default=text("5")
    )

    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
