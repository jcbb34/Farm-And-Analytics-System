from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
# LIVESTOCK PEN
# =========================================================

class LivestockPen(Base):
    __tablename__ = "livestock_pens"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
        index=True,
    )
    animal_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    capacity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    location_area: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Active",
        server_default=text("'Active'"),
        index=True,
    )
    purpose: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="General",
        server_default=text("'General'"),
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
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


# =========================================================
# LIVESTOCK
# =========================================================

class Livestock(Base):
    __tablename__ = "livestock"

    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    monitoring_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monitoring_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monitoring_frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    animal_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )
    record_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
    )
    animal_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    breed: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    sex: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Mixed",
        server_default=text("'Mixed'"),
    )

    # Hybrid/aggregate livestock fields added by the newer livestock migrations.
    record_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Batch",
        server_default=text("'Batch'"),
        index=True,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Active",
        server_default=text("'Active'"),
        index=True,
    )
    pen_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock_pens.id"),
        nullable=True,
        index=True,
    )
    origin_livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
    )

    male_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    female_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    unknown_sex_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    date_of_birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    weight_kg: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    min_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    max_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    pen_location: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
    )

    health_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Healthy",
        server_default=text("'Healthy'"),
        index=True,
    )
    healthy_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    at_risk_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    sick_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    under_treatment_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    growth_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Growing",
        server_default=text("'Growing'"),
        index=True,
    )
    production_purpose: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="General",
        server_default=text("'General'"),
        index=True,
    )
    last_checkup: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    health_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    vaccination_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Not Vaccinated",
        server_default=text("'Not Vaccinated'"),
        index=True,
    )
    next_vaccination: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    feed_times: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    feed_type: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    daily_feed_kg: Mapped[float] = mapped_column(
        Numeric(10, 3),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    feeding_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Links this livestock batch to the actual feed item in Inventory.
    feed_inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=True,
        index=True,
    )

    production_output: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Workforce/care-plan metadata. Purchased adults can enter at their current age/stage.
    age_is_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    estimated_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_age_as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_age_confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    estimated_age_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acquisition_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    acquisition_vaccination_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    acquisition_treatment_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_history_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Unknown - Needs Review",
        server_default=text("'Unknown - Needs Review'"), index=True
    )
    feeding_plan_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    assigned_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    care_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("care_templates.id"), nullable=True, index=True
    )

    date_acquired: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    acquired_from: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
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

    vaccination_records: Mapped[list["LivestockVaccinationRecord"]] = relationship(
        back_populates="livestock",
        cascade="all, delete-orphan",
        order_by="LivestockVaccinationRecord.date_administered.desc()",
    )
    feeding_records: Mapped[list["LivestockFeedingRecord"]] = relationship(
        back_populates="livestock",
        cascade="all, delete-orphan",
        order_by=(
            "LivestockFeedingRecord.confirmed_at.desc(), "
            "LivestockFeedingRecord.id.desc()"
        ),
    )

    growth_records: Mapped[list["LivestockGrowthRecord"]] = relationship(
        back_populates="livestock",
        cascade="all, delete-orphan",
        order_by=(
            "LivestockGrowthRecord.measurement_date.desc(), "
            "LivestockGrowthRecord.id.desc()"
        ),
    )

    # Required by ResourceUsage.livestock back_populates. Resource usage is
    # historical/auditable data, so it is intentionally not delete-orphaned.
    resource_usages = relationship(
        "ResourceUsage",
        back_populates="livestock",
    )


# =========================================================
# LIVESTOCK GROWTH / WEIGHT HISTORY
# =========================================================

class LivestockGrowthRecord(Base):
    __tablename__ = "livestock_growth_records"
    __table_args__ = (
        Index("ux_livestock_growth_records_submission", "task_submission_id", unique=True, mssql_where=text("task_submission_id IS NOT NULL"), sqlite_where=text("task_submission_id IS NOT NULL")),
        UniqueConstraint(
            "livestock_id",
            "measurement_date",
            name="uq_livestock_growth_measurement_date",
        ),
    )

    task_submission_id: Mapped[int | None] = mapped_column(ForeignKey("task_submissions.id"), nullable=True)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("farm_activities.id"), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    livestock_id: Mapped[int] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=False,
        index=True,
    )
    measurement_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    weight_kg: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    animals_measured: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    total_measured_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )
    min_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    max_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    measurement_basis: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Average",
        server_default=text("'Average'"),
    )
    previous_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    weight_change_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    days_since_previous: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    average_daily_gain_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )
    biological_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expected_min_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    expected_max_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    growth_profile_family_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    growth_profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    growth_profile_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    deviation_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    deviation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    livestock: Mapped["Livestock"] = relationship(
        back_populates="growth_records"
    )


# =========================================================
# VERSIONED LIVESTOCK GROWTH PROFILES
# =========================================================

class LivestockGrowthProfile(Base):
    __tablename__ = "livestock_growth_profiles"
    __table_args__ = (
        UniqueConstraint(
            "profile_family_code",
            "version",
            name="uq_livestock_growth_profile_family_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_family_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    species: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    breed_strain: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    production_purpose: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft", server_default=text("'Draft'"), index=True)
    approval_status: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Draft - Needs Veterinarian/Agriculturist Approval",
        server_default=text("'Draft - Needs Veterinarian/Agriculturist Approval'")
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reviewed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    stages: Mapped[list["LivestockGrowthProfileStage"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="LivestockGrowthProfileStage.sequence_number.asc()",
    )


class LivestockGrowthProfileStage(Base):
    __tablename__ = "livestock_growth_profile_stages"
    __table_args__ = (
        UniqueConstraint("profile_id", "sequence_number", name="uq_livestock_growth_profile_stage_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("livestock_growth_profiles.id"), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_name: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    age_start_days: Mapped[int] = mapped_column(Integer, nullable=False)
    age_end_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_min_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    expected_max_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped["LivestockGrowthProfile"] = relationship(back_populates="stages")


class LivestockGrowthStageOverrideAudit(Base):
    __tablename__ = "livestock_growth_stage_override_audits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    livestock_id: Mapped[int] = mapped_column(ForeignKey("livestock.id"), nullable=False, index=True)
    previous_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    suggested_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    override_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    overridden_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


# =========================================================
# LIVESTOCK TRANSACTION HISTORY
# =========================================================

class LivestockTransaction(Base):
    __tablename__ = "livestock_transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
    )
    transaction_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    from_livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
    )
    to_livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
    )
    from_pen_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock_pens.id"),
        nullable=True,
    )
    to_pen_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock_pens.id"),
        nullable=True,
    )
    event_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(
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


# =========================================================
# LIVESTOCK VACCINATION HISTORY
# =========================================================

class LivestockVaccinationRecord(Base):
    __tablename__ = "livestock_vaccination_records"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    livestock_id: Mapped[int] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=False,
        index=True,
    )
    vaccine: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    date_administered: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    next_due: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Up to Date",
        server_default=text("'Up to Date'"),
    )
    administered_by: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=True,
        index=True,
    )
    quantity_used: Mapped[float | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )
    unit: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
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

    livestock: Mapped["Livestock"] = relationship(
        back_populates="vaccination_records"
    )


# =========================================================
# LIVESTOCK REPRODUCTION HISTORY
# =========================================================

class LivestockReproductionRecord(Base):
    __tablename__ = "livestock_reproduction_records"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    livestock_id: Mapped[int] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=False,
        index=True,
    )
    record_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    event_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    partner_reference: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    breeding_method: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    breeder_male_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    breeder_female_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    confirmed_pregnant_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    eggs_set: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    fertile_eggs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    incubation_method: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    reproductive_status: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        index=True,
    )
    expected_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    actual_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    offspring_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    alive_offspring: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    male_offspring: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    female_offspring: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    loss_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    source_production_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock_production_records.id"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    offspring_livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
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


# =========================================================
# LIVESTOCK PRODUCTION HISTORY
# =========================================================

class LivestockProductionRecord(Base):
    __tablename__ = "livestock_production_records"
    __table_args__ = (
        Index(
            "ux_livestock_production_records_crop_yield_record_id",
            "crop_yield_record_id",
            unique=True,
            mssql_where=text("crop_yield_record_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Livestock",
        server_default=text("'Livestock'"),
        index=True,
    )
    livestock_id: Mapped[int | None] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=True,
        index=True,
    )
    crop_id: Mapped[int | None] = mapped_column(
        ForeignKey("crops.id"),
        nullable=True,
        index=True,
    )
    crop_yield_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("crop_yield_records.id"),
        nullable=True,
    )
    output_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )
    record_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    period_start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    period_end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    source_head_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    source_female_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    source_active_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    gross_quantity: Mapped[float | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )
    loss_quantity: Mapped[float | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )
    farm_use_quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    reserved_quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )
    unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    quality_grade: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    destination: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    track_sale_inventory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
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


# =========================================================
# LIVESTOCK FEEDING HISTORY
# =========================================================

class LivestockFeedingRecord(Base):
    __tablename__ = "livestock_feeding_records"
    __table_args__ = (
        UniqueConstraint(
            "livestock_id",
            "feeding_date",
            "feeding_slot",
            name="uq_livestock_feeding_date_slot",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    livestock_id: Mapped[int] = mapped_column(
        ForeignKey("livestock.id"),
        nullable=False,
        index=True,
    )
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"),
        nullable=False,
        index=True,
    )
    feeding_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    feeding_slot: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    scheduled_times: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    feed_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    planned_quantity_kg: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )
    actual_quantity_kg: Mapped[float] = mapped_column(
        Numeric(12, 3),
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
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    livestock: Mapped["Livestock"] = relationship(
        back_populates="feeding_records"
    )
