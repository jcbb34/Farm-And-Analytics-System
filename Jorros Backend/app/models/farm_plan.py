"""Editable, non-surveyed master plan zones; physical crop allocations remain elsewhere."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class FarmAreaZone(Base):
    __tablename__ = 'farm_area_zones'
    __table_args__ = (
        CheckConstraint('proposed_area_m2 > 0', name='ck_zone_positive_proposal'),
        CheckConstraint('measured_area_m2 IS NULL OR measured_area_m2 > 0', name='ck_zone_positive_measurement'),
    )
    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    parent_code: Mapped[str | None] = mapped_column(ForeignKey('farm_area_zones.code'), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    proposed_area_m2: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    measured_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    target_description: Mapped[str | None] = mapped_column(String(180), nullable=True)
    expected_quantity: Mapped[int | None] = mapped_column(Integer)
    crop_field_id: Mapped[int | None] = mapped_column(ForeignKey('crop_fields.id'), nullable=True)
    crop_section_id: Mapped[int | None] = mapped_column(ForeignKey('crop_sections.id'), nullable=True)
    livestock_pen_id: Mapped[int | None] = mapped_column(ForeignKey('livestock_pens.id'), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text('1'))
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text('1'))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    __mapper_args__ = {'version_id_col': edit_version}
