from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WeatherHistory(Base):
    __tablename__ = "weather_history"
    __table_args__ = (
        UniqueConstraint("recorded_date", name="uq_weather_history_recorded_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    wind_speed_kph: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    condition: Mapped[str] = mapped_column(String(80), nullable=False)
    weather_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="OpenWeather")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
