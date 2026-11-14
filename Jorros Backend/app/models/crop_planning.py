"""Measured land, versioned spacing, and dated planting position history."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FarmLandConfiguration(Base):
    __tablename__ = "farm_land_configuration"
    __table_args__ = (CheckConstraint("id = 1", name="ck_farm_land_singleton"),
                      CheckConstraint("total_area_m2 > 0 AND unavailable_area_m2 >= 0 AND unavailable_area_m2 <= total_area_m2", name="ck_farm_land_area"))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    total_area_m2: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    unavailable_area_m2: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False, default=0, server_default="0")
    unavailable_reason: Mapped[str | None] = mapped_column(String(500))
    edit_version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": edit_version}


class CropField(Base):
    __tablename__ = "crop_fields"
    __table_args__ = (UniqueConstraint("name", name="uq_crop_field_name"),
                      CheckConstraint("area_m2 > 0 AND unavailable_area_m2 >= 0 AND unavailable_area_m2 <= area_m2", name="ck_crop_field_area"))
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    unavailable_area_m2: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False, default=0, server_default="0")
    unavailable_reason: Mapped[str | None] = mapped_column(String(500))
    edit_version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": edit_version}


class CropSection(Base):
    __tablename__ = "crop_sections"
    __table_args__ = (UniqueConstraint("field_id", "name", name="uq_crop_section_name"),
                      CheckConstraint("area_m2 > 0 AND unavailable_area_m2 >= 0 AND unavailable_area_m2 <= area_m2", name="ck_crop_section_area"))
    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("crop_fields.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    unavailable_area_m2: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False, default=0, server_default="0")
    unavailable_reason: Mapped[str | None] = mapped_column(String(500))
    edit_version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": edit_version}


class CropFootprint(Base):
    __tablename__ = "crop_footprints"
    __table_args__ = (CheckConstraint("area_m2 > 0", name="ck_crop_footprint_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("crop_sections.id"), nullable=False, index=True)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    shared_reason: Mapped[str | None] = mapped_column(String(500))
    released_at: Mapped[datetime | None] = mapped_column(DateTime)


class CropSpacingProfile(Base):
    __tablename__ = "crop_spacing_profiles"
    __table_args__ = (UniqueConstraint("profile_key", "version", name="uq_crop_spacing_version"),
                      CheckConstraint("row_spacing_m > 0 AND plant_spacing_m > 0 AND version > 0", name="ck_crop_spacing_positive"))
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    crop_key: Mapped[str] = mapped_column(String(60), nullable=False)
    crop_name: Mapped[str] = mapped_column(String(100), nullable=False)
    variety_key: Mapped[str] = mapped_column(String(80), nullable=False)
    variety_name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    row_spacing_m: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    plant_spacing_m: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    layout: Mapped[str] = mapped_column(String(20), nullable=False, default="rectangular")
    count_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_urls_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default=text("'[]'"))
    evidence_scope: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_parts_json: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_behavior: Mapped[str] = mapped_column(String(40), nullable=False)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CropPositionEvent(Base):
    __tablename__ = "crop_position_events"
    __table_args__ = (UniqueConstraint("event_key", name="uq_crop_position_event_key"),
                      CheckConstraint("quantity > 0", name="ck_crop_position_event_positive"))
    id: Mapped[int] = mapped_column(primary_key=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    event_key: Mapped[str] = mapped_column(String(150), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
