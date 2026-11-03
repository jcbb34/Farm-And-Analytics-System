from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Index,
    func,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.database import Base


# =========================================================
# CROP
# =========================================================

class Crop(Base):
    __tablename__ = "crops"

    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    monitoring_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monitoring_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monitoring_frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_growth_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    survival_count_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    @property
    def estimated_progress(self):
        from app.services.crop_growth import calculate_crop_progress
        return calculate_crop_progress(self.planting_date, self.estimated_harvest)

    @property
    def estimated_growth_stage(self):
        from app.services.crop_growth import stage_for_progress
        return stage_for_progress(self.estimated_progress)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    crop_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    variety: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    field: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    area_hectares: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    current_growth: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    growth_stage: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Seeded",
        server_default=text("'Seeded'"),
        index=True,
    )

    quantity_planted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    current_surviving: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Planted",
        server_default=text("'Planted'"),
        index=True,
    )

    planting_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    estimated_harvest: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    fertilizer_quantity_kg: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    fertilizer_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    pesticide_used: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    watering_schedule: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confirmed_ready_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )

    confirmed_ready_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )

    completed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    assigned_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )

    care_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("care_templates.id"), nullable=True, index=True
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

    growth_records: Mapped[
        list["CropGrowthRecord"]
    ] = relationship(
        back_populates="crop",
        cascade="all, delete-orphan",
    )

    yield_records: Mapped[
        list["CropYieldRecord"]
    ] = relationship(
        back_populates="crop",
        cascade="all, delete-orphan",
    )

    pest_diseases: Mapped[
        list["CropPestDisease"]
    ] = relationship(
        back_populates="crop",
        cascade="all, delete-orphan",
    )

    resource_usages = relationship(
        "ResourceUsage",
        back_populates="crop",
    )

    @property
    def readiness_status(self) -> str | None:
        if self.status == "Ready for Harvest":
            return "Confirmed Ready" if self.confirmed_ready_at else "Estimated Ready"
        if self.status == "Harvesting":
            return "Confirmed Ready" if self.confirmed_ready_at else "Estimated Ready"
        return None

    @property
    def harvest_count(self) -> int:
        return len(self.yield_records or [])

    @property
    def total_harvest_quantity_kg(self) -> float:
        return round(sum(float(item.quantity_kg or 0) for item in (self.yield_records or [])), 3)

    @property
    def previous_partial_harvest_total_kg(self) -> float:
        return round(sum(
            float(item.quantity_kg or 0)
            for item in (self.yield_records or [])
            if str(item.harvest_type or "").strip().lower() == "partial harvest"
        ), 3)

    @property
    def first_harvest_date(self) -> date | None:
        dates = [item.harvest_date for item in (self.yield_records or []) if item.harvest_date]
        return min(dates) if dates else None

    @property
    def final_harvest_date(self) -> date | None:
        dates = [
            item.harvest_date for item in (self.yield_records or [])
            if item.harvest_date and str(item.harvest_type or "").strip().lower() == "final harvest"
        ]
        return max(dates) if dates else None


# =========================================================
# CROP GROWTH HISTORY
# =========================================================

class CropGrowthRecord(Base):
    __tablename__ = "crop_growth_records"
    __table_args__ = (Index("ux_crop_growth_records_submission", "task_submission_id", unique=True, mssql_where=text("task_submission_id IS NOT NULL"), sqlite_where=text("task_submission_id IS NOT NULL")),)

    task_submission_id: Mapped[int | None] = mapped_column(ForeignKey("task_submissions.id"), nullable=True)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("farm_activities.id"), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    observed_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id"),
        nullable=False,
        index=True,
    )

    growth_percentage: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    growth_stage: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    current_surviving: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    update_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    crop: Mapped["Crop"] = relationship(
        back_populates="growth_records"
    )


# =========================================================
# CROP YIELD / HARVEST RECORD
# =========================================================

class CropYieldRecord(Base):
    __tablename__ = "crop_yield_records"
    __table_args__ = (
        Index(
            "ux_crop_yield_related_task_not_null",
            "related_task_id",
            unique=True,
            mssql_where=text("related_task_id IS NOT NULL"),
            sqlite_where=text("related_task_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id"),
        nullable=False,
        index=True,
    )

    harvest_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    quantity_kg: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    farm_use_quantity_kg: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    damaged_quantity_kg: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    reserved_quantity_kg: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    quality: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    harvest_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    yield_per_hectare: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    performed_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )

    related_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("farm_activities.id"), nullable=True, index=True
    )

    manual_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    crop: Mapped["Crop"] = relationship(
        back_populates="yield_records"
    )


# =========================================================
# CROP PEST / DISEASE RECORD
# =========================================================

class CropPestDisease(Base):
    __tablename__ = "crop_pest_diseases"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id"),
        nullable=False,
        index=True,
    )

    date_detected: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    pest_disease_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    severity: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    affected_area: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Active",
        server_default=text("'Active'"),
    )

    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    crop: Mapped["Crop"] = relationship(
        back_populates="pest_diseases"
    )