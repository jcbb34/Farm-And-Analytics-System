"""Backend versioned livestock growth profiles and acquired-adult age provenance.

Revision ID: z0j6e3g9b571
Revises: y9i5d2f8a460
"""

from datetime import date

from alembic import op
import sqlalchemy as sa

revision = "z0j6e3g9b571"
down_revision = "y9i5d2f8a460"
branch_labels = None
depends_on = None


def _seed_profile(bind, *, family, name, species, breed, purpose, status, approval, source_title, source_url, source_notes, stages):
    existing = bind.execute(sa.text(
        "SELECT id FROM livestock_growth_profiles WHERE profile_family_code=:family AND version=1"
    ), {"family": family}).first()
    if existing:
        return
    bind.execute(sa.text("""
        INSERT INTO livestock_growth_profiles
            (profile_family_code, version, name, species, breed_strain, production_purpose,
             sex, status, approval_status, source_title, source_url, source_notes,
             last_reviewed_date, is_active)
        VALUES
            (:family, 1, :name, :species, :breed, :purpose,
             NULL, :status, :approval, :source_title, :source_url, :source_notes,
             :reviewed, 1)
    """), {
        "family": family, "name": name, "species": species, "breed": breed,
        "purpose": purpose, "status": status, "approval": approval,
        "source_title": source_title, "source_url": source_url,
        "source_notes": source_notes, "reviewed": date(2026, 9, 11),
    })
    profile_id = bind.execute(sa.text(
        "SELECT id FROM livestock_growth_profiles WHERE profile_family_code=:family AND version=1"
    ), {"family": family}).scalar_one()
    for row in stages:
        bind.execute(sa.text("""
            INSERT INTO livestock_growth_profile_stages
                (profile_id, sequence_number, stage_name, age_start_days, age_end_days,
                 expected_min_weight_kg, expected_max_weight_kg, notes)
            VALUES
                (:profile_id, :seq, :stage, :start_day, :end_day, :min_w, :max_w, :notes)
        """), {
            "profile_id": profile_id, "seq": row[0], "stage": row[1],
            "start_day": row[2], "end_day": row[3], "min_w": row[4],
            "max_w": row[5], "notes": row[6],
        })


def upgrade() -> None:
    op.alter_column("livestock", "date_of_birth", existing_type=sa.Date(), nullable=True)
    op.add_column("livestock", sa.Column("estimated_age_as_of_date", sa.Date(), nullable=True))
    op.add_column("livestock", sa.Column("estimated_age_confidence", sa.String(30), nullable=True))
    op.add_column("livestock", sa.Column("estimated_age_source", sa.String(255), nullable=True))
    op.add_column("livestock", sa.Column("acquisition_stage", sa.String(40), nullable=True))
    op.add_column("livestock", sa.Column("acquisition_vaccination_history", sa.Text(), nullable=True))
    op.add_column("livestock", sa.Column("acquisition_treatment_history", sa.Text(), nullable=True))
    op.add_column("livestock", sa.Column(
        "medical_history_status", sa.String(50), nullable=False,
        server_default=sa.text("'Unknown - Needs Review'")
    ))
    op.create_index("ix_livestock_medical_history_status", "livestock", ["medical_history_status"])

    for name, coltype in [
        ("biological_age_days", sa.Integer()),
        ("expected_stage", sa.String(40)),
        ("expected_min_weight_kg", sa.Numeric(10, 3)),
        ("expected_max_weight_kg", sa.Numeric(10, 3)),
        ("growth_profile_family_code", sa.String(40)),
        ("growth_profile_version", sa.Integer()),
        ("growth_profile_status", sa.String(20)),
        ("deviation_status", sa.String(40)),
        ("deviation_message", sa.Text()),
    ]:
        op.add_column("livestock_growth_records", sa.Column(name, coltype, nullable=True))
    op.create_index("ix_livestock_growth_records_growth_profile_family_code", "livestock_growth_records", ["growth_profile_family_code"])
    op.create_index("ix_livestock_growth_records_deviation_status", "livestock_growth_records", ["deviation_status"])

    op.create_table(
        "livestock_growth_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_family_code", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("species", sa.String(50), nullable=False),
        sa.Column("breed_strain", sa.String(100), nullable=True),
        sa.Column("production_purpose", sa.String(80), nullable=True),
        sa.Column("sex", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Draft'")),
        sa.Column("approval_status", sa.String(100), nullable=False, server_default=sa.text("'Draft - Needs Veterinarian/Agriculturist Approval'")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_title", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("source_notes", sa.Text(), nullable=True),
        sa.Column("last_reviewed_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("profile_family_code", "version", name="uq_livestock_growth_profile_family_version"),
    )
    for name, cols in [
        ("ix_livestock_growth_profiles_profile_family_code", ["profile_family_code"]),
        ("ix_livestock_growth_profiles_species", ["species"]),
        ("ix_livestock_growth_profiles_breed_strain", ["breed_strain"]),
        ("ix_livestock_growth_profiles_production_purpose", ["production_purpose"]),
        ("ix_livestock_growth_profiles_sex", ["sex"]),
        ("ix_livestock_growth_profiles_status", ["status"]),
        ("ix_livestock_growth_profiles_is_active", ["is_active"]),
    ]:
        op.create_index(name, "livestock_growth_profiles", cols)

    op.create_table(
        "livestock_growth_profile_stages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("livestock_growth_profiles.id"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(40), nullable=False),
        sa.Column("age_start_days", sa.Integer(), nullable=False),
        sa.Column("age_end_days", sa.Integer(), nullable=True),
        sa.Column("expected_min_weight_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("expected_max_weight_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("profile_id", "sequence_number", name="uq_livestock_growth_profile_stage_sequence"),
    )
    op.create_index("ix_livestock_growth_profile_stages_profile_id", "livestock_growth_profile_stages", ["profile_id"])
    op.create_index("ix_livestock_growth_profile_stages_stage_name", "livestock_growth_profile_stages", ["stage_name"])

    op.create_table(
        "livestock_growth_stage_override_audits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("livestock_id", sa.Integer(), sa.ForeignKey("livestock.id"), nullable=False),
        sa.Column("previous_stage", sa.String(40), nullable=False),
        sa.Column("suggested_stage", sa.String(40), nullable=True),
        sa.Column("override_stage", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("overridden_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_livestock_growth_stage_override_audits_livestock_id", "livestock_growth_stage_override_audits", ["livestock_id"])

    bind = op.get_bind()
    _seed_profile(
        bind,
        family="GROW-ROSS308AP",
        name="Ross 308 AP Broiler Growth Reference",
        species="Chicken",
        breed="Ross 308 AP",
        purpose="Meat",
        status="Published",
        approval="Approved - Source-backed performance objective",
        source_title="Ross 308 AP Broiler Performance Objectives 2022",
        source_url="https://ap.aviagen.com/assets/Tech_Center/Ross_Broiler/RossxRoss308AP-BroilerPerformanceObjectives2022-EN.pdf",
        source_notes="Aviagen performance objectives are genetic-performance targets, not diagnoses. Stage weight bands are conservative envelopes derived from the published daily body-weight objectives; local farm conditions may differ.",
        stages=[
            (1, "Brooding", 0, 7, 0.040, 0.260, "Fast-growing broiler chick; published objectives are approximately 44 g at day 0 and 214 g at day 7."),
            (2, "Growing", 8, 21, 0.200, 1.150, "Rapid broiler growth phase; as-hatched objective is about 1.0 kg around day 21."),
            (3, "Finisher", 22, 35, 1.000, 2.700, "Fast-growing finisher phase; intentionally distinct from slower native chicken profiles."),
            (4, "Ready for Market", 36, 45, 2.200, 3.600, "Approximate 45-day broiler market-cycle window where applicable; actual market timing is farm/market dependent."),
            (5, "Ready for Market", 46, 56, 2.700, 4.500, "Later broiler market window; use actual weights and welfare/market requirements."),
        ],
    )
    _seed_profile(
        bind,
        family="GROW-PH-CAMARINES-NATIVE",
        name="Camarines Native Chicken Provisional Growth Profile",
        species="Chicken",
        breed="Camarines",
        purpose=None,
        status="Draft",
        approval="Draft - Needs Veterinarian/Agriculturist Approval",
        source_title="PCAARRD Philippine Native Chicken and Itik PINAS Information System",
        source_url="https://pab-is.pcaarrd.dost.gov.ph/nativepoultry/",
        source_notes="PCAARRD supports the slower Philippine native-chicken production timeline and reports onset of laying around 20-22 weeks. This profile is targeted to the farm breed label Camarines; its weight bands are provisional planning ranges and remain Draft until breed-specific expert verification.",
        stages=[
            (1, "Brooding", 0, 42, 0.030, 0.550, "Provisional native-chicken chick range; not a published PCAARRD weight curve."),
            (2, "Growing", 43, 125, 0.350, 1.400, "Slower native grower period than commercial broilers."),
            (3, "Pre-Laying", 126, 153, 0.700, 1.800, "Aligns conservatively with native chickens approaching the reported 20-22 week laying onset."),
            (4, "Mature", 154, None, 0.900, 2.800, "Provisional mature range; breed- and sex-specific verification is still required."),
        ],
    )
    _seed_profile(
        bind,
        family="GROW-PIG-GENERIC",
        name="Pig Provisional Biological-Age Growth Profile",
        species="Pig",
        breed=None,
        purpose=None,
        status="Draft",
        approval="Draft - Needs Veterinarian/Agriculturist Approval",
        source_title="Joross Farm provisional swine age-stage planning profile",
        source_url=None,
        source_notes="No single verified breed/sex/feed-system curve was suitable for every farm pig. This generic profile exists only as a Draft planning fallback; breed-specific expert-approved profiles should supersede it.",
        stages=[
            (1, "Newborn", 0, 56, 0.8, 25.0, "Provisional early-life range."),
            (2, "Weaned", 57, 90, 8.0, 40.0, "Provisional post-weaning range."),
            (3, "Growing", 91, 179, 20.0, 100.0, "Pig under six months remains in a growing stage unless a more specific approved profile applies."),
            (4, "Mature", 180, None, 55.0, 300.0, "Broad acquired-adult fallback; actual production purpose and breed should use a more specific profile."),
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_livestock_growth_stage_override_audits_livestock_id", table_name="livestock_growth_stage_override_audits")
    op.drop_table("livestock_growth_stage_override_audits")
    op.drop_index("ix_livestock_growth_profile_stages_stage_name", table_name="livestock_growth_profile_stages")
    op.drop_index("ix_livestock_growth_profile_stages_profile_id", table_name="livestock_growth_profile_stages")
    op.drop_table("livestock_growth_profile_stages")
    for name in [
        "ix_livestock_growth_profiles_is_active",
        "ix_livestock_growth_profiles_status",
        "ix_livestock_growth_profiles_sex",
        "ix_livestock_growth_profiles_production_purpose",
        "ix_livestock_growth_profiles_breed_strain",
        "ix_livestock_growth_profiles_species",
        "ix_livestock_growth_profiles_profile_family_code",
    ]:
        op.drop_index(name, table_name="livestock_growth_profiles")
    op.drop_table("livestock_growth_profiles")
    op.drop_index("ix_livestock_growth_records_deviation_status", table_name="livestock_growth_records")
    op.drop_index("ix_livestock_growth_records_growth_profile_family_code", table_name="livestock_growth_records")
    for name in [
        "deviation_message", "deviation_status", "growth_profile_status", "growth_profile_version",
        "growth_profile_family_code", "expected_max_weight_kg", "expected_min_weight_kg",
        "expected_stage", "biological_age_days",
    ]:
        op.drop_column("livestock_growth_records", name)
    op.drop_index("ix_livestock_medical_history_status", table_name="livestock")
    for name in [
        "medical_history_status", "acquisition_treatment_history", "acquisition_vaccination_history",
        "acquisition_stage", "estimated_age_source", "estimated_age_confidence", "estimated_age_as_of_date",
    ]:
        op.drop_column("livestock", name)
    op.alter_column("livestock", "date_of_birth", existing_type=sa.Date(), nullable=False)
