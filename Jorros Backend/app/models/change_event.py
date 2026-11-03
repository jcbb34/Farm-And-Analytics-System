"""Durable, committed change hints used by the authenticated farm event stream."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FarmChangeEvent(Base):
    __tablename__ = "farm_change_events"
    __table_args__ = (
        Index("ix_farm_change_events_employee_id", "target_employee_id", "id"),
        Index("ix_farm_change_events_user_id", "target_user_id", "id"),
        Index("ix_farm_change_events_created_at", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    modules_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Historical audiences remain valid if an archived account is later purged.
    target_employee_id: Mapped[int | None] = mapped_column(Integer)
    target_user_id: Mapped[int | None] = mapped_column(Integer)
    record_version: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
