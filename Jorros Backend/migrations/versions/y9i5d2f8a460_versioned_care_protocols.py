"""Evolve care templates into versioned care protocols.

Revision ID: y9i5d2f8a460
Revises: x8h4c1e7f359
"""

from alembic import op
import sqlalchemy as sa

revision = "y9i5d2f8a460"
down_revision = "x8h4c1e7f359"
branch_labels = None
depends_on = None

DRAFT_APPROVAL = "Draft - Needs Veterinarian/Agriculturist Approval"


def _add_protocol_columns() -> None:
    cols = [
        sa.Column("protocol_family_code", sa.String(40), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("target_breed", sa.String(100), nullable=True),
        sa.Column("target_variety", sa.String(100), nullable=True),
        sa.Column("production_purpose", sa.String(100), nullable=True),
        sa.Column("growth_stage", sa.String(100), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'Published'")),
        sa.Column("approval_status", sa.String(80), nullable=False, server_default=sa.text("'Legacy - Review Recommended'")),
        sa.Column("source_title", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("citations_json", sa.Text(), nullable=True),
        sa.Column("last_reviewed_date", sa.Date(), nullable=True),
        sa.Column("supersedes_template_id", sa.Integer(), nullable=True),
        sa.Column("copied_from_template_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("published_by_user_id", sa.Integer(), nullable=True),
    ]
    for col in cols:
        op.add_column("care_templates", col)

    op.create_foreign_key("fk_care_templates_supersedes", "care_templates", "care_templates", ["supersedes_template_id"], ["id"])
    op.create_foreign_key("fk_care_templates_copied_from", "care_templates", "care_templates", ["copied_from_template_id"], ["id"])
    op.create_foreign_key("fk_care_templates_published_by", "care_templates", "users", ["published_by_user_id"], ["id"])

    for name, cols in [
        ("ix_care_templates_protocol_family_code", ["protocol_family_code"]),
        ("ix_care_templates_target_breed", ["target_breed"]),
        ("ix_care_templates_target_variety", ["target_variety"]),
        ("ix_care_templates_production_purpose", ["production_purpose"]),
        ("ix_care_templates_growth_stage", ["growth_stage"]),
        ("ix_care_templates_effective_from", ["effective_from"]),
        ("ix_care_templates_effective_to", ["effective_to"]),
        ("ix_care_templates_status", ["status"]),
        ("ix_care_templates_approval_status", ["approval_status"]),
        ("ix_care_templates_supersedes_template_id", ["supersedes_template_id"]),
        ("ix_care_templates_copied_from_template_id", ["copied_from_template_id"]),
    ]:
        op.create_index(name, "care_templates", cols)


def _add_step_columns() -> None:
    cols = [
        sa.Column("timing_anchor", sa.String(40), nullable=False, server_default=sa.text("'base_date'")),
        sa.Column("age_start_days", sa.Integer(), nullable=True),
        sa.Column("age_end_days", sa.Integer(), nullable=True),
        sa.Column("previous_step_sequence", sa.Integer(), nullable=True),
        sa.Column("recurrence_interval_days", sa.Integer(), nullable=True),
        sa.Column("recurrence_occurrences", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("dose_basis", sa.String(60), nullable=True),
        sa.Column("resource_product_name", sa.String(150), nullable=True),
        sa.Column("resource_category", sa.String(80), nullable=True),
        sa.Column("safety_notes", sa.Text(), nullable=True),
        sa.Column("withdrawal_interval_days", sa.Integer(), nullable=True),
        sa.Column("preharvest_interval_days", sa.Integer(), nullable=True),
        sa.Column("source_citation", sa.Text(), nullable=True),
    ]
    for col in cols:
        op.add_column("care_template_steps", col)
    op.create_index("ix_care_template_steps_timing_anchor", "care_template_steps", ["timing_anchor"])
    op.create_index("ix_care_template_steps_resource_product_name", "care_template_steps", ["resource_product_name"])
    op.create_index("ix_care_template_steps_resource_category", "care_template_steps", ["resource_category"])


def _seed_presets(bind) -> None:
    presets = [
        {
            "code": "PRESET-CORN", "family": "PRESET-CORN", "name": "Corn Crop Care Review - Philippine Draft",
            "module": "Crop", "target": "Corn",
            "source_title": "Corn Production: 9 Basic Steps Towards Bountiful Corn Harvest",
            "source_url": "https://ati2.da.gov.ph/ati-5/content/sites/default/files/users/user17/Corn%20Production%20%289%20Basic%20Steps%20for%20Bountiful%20Harvest%29.pdf",
            "step_title": "Crop care and condition inspection", "category": "inspection", "offset": 41,
            "instructions": "Inspect crop condition, weeds, and unusual disease signs. Escalate unusual or epidemic signs to the farm technician/agriculturist. This draft does not prescribe a pesticide or fertilizer product.",
            "citation": "DA-ATI Bicol/CAR corn guide: crop care and maintenance is described for flowering until before harvest (about 41-95 DAP).",
        },
        {
            "code": "PRESET-TOMATO", "family": "PRESET-TOMATO", "name": "Tomato Harvest Readiness Review - Philippine Draft",
            "module": "Crop", "target": "Tomato",
            "source_title": "Gabay sa Produksyon ng Kamatis / Techno Guide on Organic Tomato Production",
            "source_url": "https://ati2.da.gov.ph/ati-4b/content/gabay-sa-produksyon-ng-kamatis",
            "step_title": "Harvest readiness inspection", "category": "inspection", "offset": 55,
            "instructions": "Inspect fruit maturity and crop condition before harvest decisions. Confirm the variety-specific harvest window with the farm agriculturist. No chemical application is prescribed by this preset.",
            "citation": "DA-ATI tomato production materials describe harvest timing as variety/production dependent; this is an inspection trigger only and requires agriculturist approval.",
        },
        {
            "code": "PRESET-OKRA", "family": "PRESET-OKRA", "name": "Okra Flowering and Harvest Review - Philippine Draft",
            "module": "Crop", "target": "Okra",
            "source_title": "Okra Production Guide",
            "source_url": "https://ati2.da.gov.ph/ati-car/content/sites/default/files/2022-12/okra_production_flyer_.pdf",
            "step_title": "Flowering and harvest readiness inspection", "category": "inspection", "offset": 40,
            "instructions": "Inspect for flowering and tender harvestable pods. Record pest/disease observations and ask the agriculturist before any pesticide or fertilizer application.",
            "citation": "DA-ATI Cordillera okra guide states flowering may begin around 40-75 days after planting and harvest follows flowering; this preset is observation-only.",
        },
        {
            "code": "PRESET-PIG", "family": "PRESET-PIG", "name": "Pig Daily Welfare Check - Philippine Draft",
            "module": "Livestock", "target": "Pig",
            "source_title": "Code of Practice and Minimum Standards for the Welfare of Pigs",
            "source_url": "https://www.bai.gov.ph/media/2qoldtid/compendium-of-animal-welfare-legislation-policies-and-issuances-in-the-philippines.pdf",
            "step_title": "Feed, water, and welfare inspection", "category": "inspection", "offset": 0,
            "instructions": "Check access to sufficient feed and fresh water, general condition, and feeder/waterer function. Veterinary treatment or medication requires competent veterinary advice/prescription.",
            "citation": "DA-BAI pig welfare code requires sufficient feed/water and regular monitoring; veterinary medication is subject to competent veterinary advice.",
        },
        {
            "code": "PRESET-CHICKEN", "family": "PRESET-CHICKEN", "name": "Chicken Daily Welfare Check - Philippine Draft",
            "module": "Livestock", "target": "Chicken",
            "source_title": "Compendium of Animal Welfare Legislation, Policies and Issuances in the Philippines",
            "source_url": "https://ww2.bai.gov.ph/media/dn1dabnl/compendium-of-animal-welfare-legislation-policies-and-issuances-in-the-philippines.pdf",
            "step_title": "Feed, water, and flock health inspection", "category": "inspection", "offset": 0,
            "instructions": "Check feed and water access, flock behavior, and signs of disease or distress. Vaccination, antibiotics, and other veterinary drugs must follow the attending veterinarian and applicable veterinary drug requirements.",
            "citation": "DA-BAI poultry welfare provisions require access to water, health observation, and veterinarian-directed health programs and records.",
        },
        {
            "code": "PRESET-GOAT", "family": "PRESET-GOAT", "name": "Goat Husbandry Review - Philippine Draft",
            "module": "Livestock", "target": "Goat",
            "source_title": "How to Raise Organic Small Ruminants for Food and Profit",
            "source_url": "https://ati2.da.gov.ph/ati-car/content/sites/default/files/2022-12/how_to_raise_organic_small_ruminants_for_food_and_profit.pdf",
            "step_title": "Husbandry and health observation", "category": "inspection", "offset": 0,
            "instructions": "Review forage/feed access, housing, body condition, and visible health concerns. Confirm any vaccination, medication, deworming, or dose schedule with the farm veterinarian.",
            "citation": "DA-ATI small-ruminant materials cover goat breeds, feeding, housing and health management; exact veterinary schedules remain expert-controlled.",
        },
        {
            "code": "PRESET-DUCK", "family": "PRESET-DUCK", "name": "Duck Husbandry Review - Philippine Draft",
            "module": "Livestock", "target": "Duck",
            "source_title": "Integrated Rice-Duck Farming System",
            "source_url": "https://ati2.da.gov.ph/ati-10/content/sites/default/files/users/user32/Rice%20Duck%20Farming%20System_compressed.pdf",
            "step_title": "Water, housing, and flock condition inspection", "category": "inspection", "offset": 0,
            "instructions": "Inspect water access, housing/brooder condition, feeders, fencing, and flock condition. Exact feed doses, medicines, and vaccination schedules require veterinarian-approved farm protocols.",
            "citation": "DA-ATI rice-duck material identifies clean water, housing, drinkers/feeders and brooder facilities as production requirements; this preset does not invent veterinary schedules.",
        },
    ]
    for p in presets:
        exists = bind.execute(sa.text("SELECT COUNT(*) FROM care_templates WHERE template_code=:code"), {"code": p["code"]}).scalar()
        if exists:
            continue
        bind.execute(sa.text("""
            INSERT INTO care_templates
            (template_code, protocol_family_code, version, name, module, target_type, description,
             status, approval_status, source_title, source_url, citations_json, is_active)
            VALUES (:code, :family, 1, :name, :module, :target,
                    'Curated Philippine-source draft preset. Expert approval is required before publication or operational use.',
                    'Draft', :approval, :source_title, :source_url, :citations, 1)
        """), {**p, "approval": DRAFT_APPROVAL, "citations": '["' + p["source_url"] + '"]'})
        tid = bind.execute(sa.text("SELECT id FROM care_templates WHERE template_code=:code"), {"code": p["code"]}).scalar_one()
        bind.execute(sa.text("""
            INSERT INTO care_template_steps
            (template_id, sequence_number, title, category, offset_days, timing_anchor,
             recurrence_occurrences, instructions, priority, requires_review, requires_evidence,
             source_citation)
            VALUES (:tid, 1, :step_title, :category, :offset, 'base_date', 1,
                    :instructions, 'Medium', 1, 1, :citation)
        """), {**p, "tid": tid})


def upgrade() -> None:
    _add_protocol_columns()
    _add_step_columns()
    op.add_column("farm_activities", sa.Column("source_protocol_family_code", sa.String(40), nullable=True))
    op.add_column("farm_activities", sa.Column("source_protocol_version", sa.Integer(), nullable=True))
    op.create_index("ix_farm_activities_source_protocol_family_code", "farm_activities", ["source_protocol_family_code"])

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE care_templates SET protocol_family_code = template_code WHERE protocol_family_code IS NULL"))
    bind.execute(sa.text("UPDATE care_templates SET version = 1 WHERE version IS NULL"))
    # Adding the non-null status column gives existing rows the temporary server
    # default ('Published'). Recompute every legacy row from its prior is_active
    # value so disabled Care Templates do not become operational again.
    bind.execute(sa.text("UPDATE care_templates SET status = CASE WHEN is_active = 1 THEN 'Published' ELSE 'Inactive' END"))
    bind.execute(sa.text("UPDATE care_templates SET approval_status = 'Legacy - Review Recommended' WHERE approval_status IS NULL OR approval_status = ''"))
    bind.execute(sa.text("""
        UPDATE fa
        SET source_protocol_family_code = ct.protocol_family_code,
            source_protocol_version = ct.version
        FROM farm_activities AS fa
        INNER JOIN care_template_steps AS cs ON cs.id = fa.source_detail_id
        INNER JOIN care_templates AS ct ON ct.id = cs.template_id
        WHERE fa.source_type = 'care_template_step'
          AND fa.source_protocol_family_code IS NULL
    """)) if bind.dialect.name == "mssql" else None
    if bind.dialect.name != "mssql":
        rows = bind.execute(sa.text("""
            SELECT fa.id AS task_id, ct.protocol_family_code, ct.version
            FROM farm_activities fa
            JOIN care_template_steps cs ON cs.id = fa.source_detail_id
            JOIN care_templates ct ON ct.id = cs.template_id
            WHERE fa.source_type='care_template_step' AND fa.source_protocol_family_code IS NULL
        """)).mappings().all()
        for row in rows:
            bind.execute(sa.text("UPDATE farm_activities SET source_protocol_family_code=:family, source_protocol_version=:version WHERE id=:id"), {"family": row["protocol_family_code"], "version": row["version"], "id": row["task_id"]})

    # SQL Server does not allow ALTER COLUMN while an index depends on
    # protocol_family_code. Drop the index temporarily, make the column
    # required, then recreate the same index.
    if bind.dialect.name == "mssql":
        op.drop_index(
            "ix_care_templates_protocol_family_code",
            table_name="care_templates",
        )

    op.alter_column(
        "care_templates",
        "protocol_family_code",
        existing_type=sa.String(40),
        nullable=False,
    )

    if bind.dialect.name == "mssql":
        op.create_index(
            "ix_care_templates_protocol_family_code",
            "care_templates",
            ["protocol_family_code"],
        )

    op.create_unique_constraint(
        "uq_care_template_family_version",
        "care_templates",
        ["protocol_family_code", "version"],
    )
    _seed_presets(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for code in ["PRESET-CORN", "PRESET-TOMATO", "PRESET-OKRA", "PRESET-PIG", "PRESET-CHICKEN", "PRESET-GOAT", "PRESET-DUCK"]:
        tid = bind.execute(sa.text("SELECT id FROM care_templates WHERE template_code=:code"), {"code": code}).scalar()
        if tid:
            bind.execute(sa.text("DELETE FROM care_template_steps WHERE template_id=:id"), {"id": tid})
            bind.execute(sa.text("DELETE FROM care_templates WHERE id=:id"), {"id": tid})

    op.drop_constraint("uq_care_template_family_version", "care_templates", type_="unique")
    op.drop_index("ix_farm_activities_source_protocol_family_code", table_name="farm_activities")
    op.drop_column("farm_activities", "source_protocol_version")
    op.drop_column("farm_activities", "source_protocol_family_code")

    for name in ["ix_care_template_steps_resource_category", "ix_care_template_steps_resource_product_name", "ix_care_template_steps_timing_anchor"]:
        op.drop_index(name, table_name="care_template_steps")
    for col in ["source_citation", "preharvest_interval_days", "withdrawal_interval_days", "safety_notes", "resource_category", "resource_product_name", "dose_basis", "recurrence_occurrences", "recurrence_interval_days", "previous_step_sequence", "age_end_days", "age_start_days", "timing_anchor"]:
        op.drop_column("care_template_steps", col)

    for name in ["ix_care_templates_copied_from_template_id", "ix_care_templates_supersedes_template_id", "ix_care_templates_approval_status", "ix_care_templates_status", "ix_care_templates_effective_to", "ix_care_templates_effective_from", "ix_care_templates_growth_stage", "ix_care_templates_production_purpose", "ix_care_templates_target_variety", "ix_care_templates_target_breed", "ix_care_templates_protocol_family_code"]:
        op.drop_index(name, table_name="care_templates")
    op.drop_constraint("fk_care_templates_published_by", "care_templates", type_="foreignkey")
    op.drop_constraint("fk_care_templates_copied_from", "care_templates", type_="foreignkey")
    op.drop_constraint("fk_care_templates_supersedes", "care_templates", type_="foreignkey")
    for col in ["published_by_user_id", "published_at", "copied_from_template_id", "supersedes_template_id", "last_reviewed_date", "citations_json", "source_url", "source_title", "approval_status", "status", "effective_to", "effective_from", "growth_stage", "production_purpose", "target_variety", "target_breed", "version", "protocol_family_code"]:
        op.drop_column("care_templates", col)
