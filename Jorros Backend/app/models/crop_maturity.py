"""Dated crop development events used for variety-specific maturity planning."""
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class CropMaturityEvent(Base):
    __tablename__ = "crop_maturity_events"
    __table_args__ = (Index("ix_crop_maturity_event_crop_kind", "crop_id", "event_kind", "observed_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id"), nullable=False, index=True)
    event_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    observed_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
