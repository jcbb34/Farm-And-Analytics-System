"""Recorded physical harvest readiness inspection, separate from date-based estimates."""
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CropReadinessInspection(Base):
    __tablename__ = "crop_readiness_inspections"
    __table_args__ = (
        Index("ix_crop_readiness_crop_date", "crop_id", "inspection_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id"), nullable=False)
    inspected_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    criteria_json: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
