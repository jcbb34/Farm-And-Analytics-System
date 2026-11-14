"""Measured crop allocations, spacing snapshots, unknown dates and direct care.

Existing IDs/history remain intact. Legacy free-text locations remain unmapped.
Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _alter(table, definitions):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            for name, old_type, new_type, old_nullable, nullable in definitions:
                batch.alter_column(name, existing_type=old_type, type_=new_type,
                                   existing_nullable=old_nullable, nullable=nullable)
        return
    inspector = sa.inspect(bind)
    affected = {item[0] for item in definitions}
    indexes = [idx for idx in inspector.get_indexes(table)
               if affected.intersection((idx.get("column_names") or []) + (idx.get("include_columns") or []))]
    for idx in indexes:
        op.drop_index(idx["name"], table_name=table)
    defaults = list(bind.execute(sa.text(
        "SELECT dc.name, col.name AS column_name, dc.definition FROM sys.default_constraints dc "
        "JOIN sys.columns col ON col.object_id=dc.parent_object_id AND col.column_id=dc.parent_column_id "
        "WHERE dc.parent_object_id=OBJECT_ID(:table)"), {"table": "dbo." + table}).mappings())
    defaults = [d for d in defaults if d["column_name"] in affected]
    quote = bind.dialect.identifier_preparer.quote
    for default in defaults:
        op.execute(sa.text("ALTER TABLE " + quote(table) + " DROP CONSTRAINT " + quote(default["name"])))
    for name, old_type, new_type, old_nullable, nullable in definitions:
        op.alter_column(table, name, existing_type=old_type, type_=new_type,
                        existing_nullable=old_nullable, nullable=nullable)
    for default in defaults:
        op.execute(sa.text("ALTER TABLE " + quote(table) + " ADD CONSTRAINT " + quote(default["name"])
                          + " DEFAULT " + default["definition"] + " FOR " + quote(default["column_name"])))
    for idx in indexes:
        options = idx.get("dialect_options") or {}
        op.create_index(idx["name"], table, idx["column_names"], unique=idx["unique"],
                        mssql_where=sa.text(str(options["mssql_where"])) if options.get("mssql_where") else None,
                        mssql_include=idx.get("include_columns") or [])


def upgrade():
    op.create_table('crop_fields',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('area_m2', sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column('unavailable_area_m2', sa.Numeric(precision=16, scale=4), nullable=False, server_default=sa.text('0')),
        sa.Column('unavailable_reason', sa.String(length=500), nullable=True),
        sa.Column('edit_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.UniqueConstraint('name', name='uq_crop_field_name'),
        sa.CheckConstraint('area_m2 > 0 AND unavailable_area_m2 >= 0 AND unavailable_area_m2 <= area_m2', name='ck_crop_field_area')
    )
    op.create_table('farm_land_configuration',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True, autoincrement=False),
        sa.Column('total_area_m2', sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column('unavailable_area_m2', sa.Numeric(precision=16, scale=4), nullable=False, server_default=sa.text('0')),
        sa.Column('unavailable_reason', sa.String(length=500), nullable=True),
        sa.Column('edit_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.CheckConstraint('total_area_m2 > 0 AND unavailable_area_m2 >= 0 AND unavailable_area_m2 <= total_area_m2', name='ck_farm_land_area'),
        sa.CheckConstraint('id = 1', name='ck_farm_land_singleton')
    )
    op.create_table('crop_sections',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('field_id', sa.Integer(), sa.ForeignKey('crop_fields.id'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('area_m2', sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column('unavailable_area_m2', sa.Numeric(precision=16, scale=4), nullable=False, server_default=sa.text('0')),
        sa.Column('unavailable_reason', sa.String(length=500), nullable=True),
        sa.Column('edit_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.CheckConstraint('area_m2 > 0 AND unavailable_area_m2 >= 0 AND unavailable_area_m2 <= area_m2', name='ck_crop_section_area'),
        sa.UniqueConstraint('field_id', 'name', name='uq_crop_section_name')
    )
    op.create_index('ix_crop_sections_field_id', 'crop_sections', ['field_id'], unique=False)
    op.create_table('crop_footprints',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('section_id', sa.Integer(), sa.ForeignKey('crop_sections.id'), nullable=False),
        sa.Column('area_m2', sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column('shared_reason', sa.String(length=500), nullable=True),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('area_m2 > 0', name='ck_crop_footprint_positive')
    )
    op.create_index('ix_crop_footprints_section_id', 'crop_footprints', ['section_id'], unique=False)
    op.create_table('crop_spacing_profiles',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('profile_key', sa.String(length=100), nullable=False),
        sa.Column('crop_key', sa.String(length=60), nullable=False),
        sa.Column('crop_name', sa.String(length=100), nullable=False),
        sa.Column('variety_key', sa.String(length=80), nullable=False),
        sa.Column('variety_name', sa.String(length=100), nullable=False),
        sa.Column('label', sa.String(length=150), nullable=False),
        sa.Column('row_spacing_m', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('plant_spacing_m', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('layout', sa.String(length=20), nullable=False),
        sa.Column('count_unit', sa.String(length=30), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('source_url', sa.String(length=1000), nullable=False),
        sa.Column('source_urls_json', sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('evidence_scope', sa.Text(), nullable=False),
        sa.Column('harvest_parts_json', sa.Text(), nullable=False),
        sa.Column('harvest_behavior', sa.String(length=40), nullable=False),
        sa.Column('guidance', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.CheckConstraint('row_spacing_m > 0 AND plant_spacing_m > 0 AND version > 0', name='ck_crop_spacing_positive'),
        sa.UniqueConstraint('profile_key', 'version', name='uq_crop_spacing_version')
    )
    op.create_index('ix_crop_spacing_profiles_profile_key', 'crop_spacing_profiles', ['profile_key'], unique=False)
    op.create_table('crop_position_events',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('crop_id', sa.Integer(), sa.ForeignKey('crops.id'), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('event_key', sa.String(length=150), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('event_key', name='uq_crop_position_event_key'),
        sa.CheckConstraint('quantity > 0', name='ck_crop_position_event_positive')
    )
    op.create_index('ix_crop_position_events_crop_id', 'crop_position_events', ['crop_id'], unique=False)
    op.add_column('crops', sa.Column('registration_kind', sa.String(length=20), nullable=False, server_default=sa.text("'legacy'")))
    op.add_column('crops', sa.Column('crop_reference', sa.String(length=60), nullable=True))
    op.add_column('crops', sa.Column('variety_reference', sa.String(length=80), nullable=True))
    op.add_column('crops', sa.Column('section_id', sa.Integer(), sa.ForeignKey('crop_sections.id'), nullable=True))
    op.add_column('crops', sa.Column('footprint_id', sa.Integer(), sa.ForeignKey('crop_footprints.id'), nullable=True))
    op.add_column('crops', sa.Column('spacing_snapshot_json', sa.Text(), nullable=True))
    op.add_column('crops', sa.Column('estimated_capacity', sa.Integer(), nullable=True))
    op.add_column('crops', sa.Column('planting_date_precision', sa.String(length=20), nullable=False, server_default=sa.text("'known'")))
    op.add_column('crops', sa.Column('initial_surviving', sa.Integer(), nullable=True))
    op.add_column('crops', sa.Column('care_schedules_json', sa.Text(), nullable=True))
    op.add_column('crops', sa.Column('schedule_effective_date', sa.Date(), nullable=True))
    op.add_column('crops', sa.Column('ended_at', sa.DateTime(), nullable=True))
    op.add_column('crops', sa.Column('area_cleared_at', sa.DateTime(), nullable=True))
    op.add_column('crops', sa.Column('area_cleared_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_crops_footprint_id', 'crops', ['footprint_id'], unique=False)
    op.create_index('ix_crops_section_id', 'crops', ['section_id'], unique=False)
    op.add_column('crop_yield_records', sa.Column('harvested_part', sa.String(length=40), nullable=True))
    op.add_column('crop_yield_records', sa.Column('plants_harvested_out', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('crop_yield_records', sa.Column('idempotency_key', sa.String(length=100), nullable=True))
    op.add_column('task_submissions', sa.Column('harvested_part', sa.String(length=40), nullable=True))
    op.add_column('task_submissions', sa.Column('plants_harvested_out', sa.Integer(), nullable=False, server_default=sa.text('0')))
    _alter("crops", [
        ("area_hectares", sa.Numeric(10, 2), sa.Numeric(14, 6), False, False),
        ("current_growth", sa.Numeric(5, 2), sa.Numeric(5, 2), False, True),
        ("quantity_planted", sa.Integer(), sa.Integer(), False, True),
        ("current_surviving", sa.Integer(), sa.Integer(), False, True),
        ("planting_date", sa.Date(), sa.Date(), False, True),
        ("estimated_harvest", sa.Date(), sa.Date(), False, True),
    ])
    _alter("crop_growth_records", [("growth_percentage", sa.Numeric(5, 2), sa.Numeric(5, 2), False, True)])
    _alter("crop_yield_records", [
        ("quantity_kg", sa.Numeric(12, 2), sa.Numeric(14, 3), False, False),
        ("farm_use_quantity_kg", sa.Numeric(12, 2), sa.Numeric(14, 3), False, False),
        ("damaged_quantity_kg", sa.Numeric(12, 2), sa.Numeric(14, 3), False, False),
        ("reserved_quantity_kg", sa.Numeric(12, 2), sa.Numeric(14, 3), False, False),
        ("yield_per_hectare", sa.Numeric(12, 2), sa.Numeric(14, 3), True, True),
    ])
    op.execute(sa.text("UPDATE crops SET initial_surviving = current_surviving"))
    configuration = sa.table("farm_land_configuration", sa.column("id"), sa.column("total_area_m2"), sa.column("unavailable_area_m2"), sa.column("edit_version"))
    op.bulk_insert(configuration, [{"id": 1, "total_area_m2": 18000, "unavailable_area_m2": 0, "edit_version": 1}])
    profiles = sa.table("crop_spacing_profiles", sa.column('profile_key'), sa.column('crop_name'), sa.column('crop_key'), sa.column('variety_name'), sa.column('variety_key'), sa.column('label'), sa.column('row_spacing_m'), sa.column('plant_spacing_m'), sa.column('layout'), sa.column('count_unit'), sa.column('version'), sa.column('source_url'), sa.column('evidence_scope'), sa.column('harvest_behavior'), sa.column('guidance'), sa.column('is_default'), sa.column('harvest_parts_json'), sa.column('source_urls_json'))
    op.bulk_insert(profiles, [{'profile_key': 'coconut-tall',
      'crop_name': 'Coconut',
      'crop_key': 'coconut',
      'variety_name': 'Tall',
      'variety_key': 'tall',
      'label': 'Coconut Tall',
      'row_spacing_m': '10',
      'plant_spacing_m': '10',
      'layout': 'square',
      'count_unit': 'tree',
      'version': 1,
      'source_url': 'https://www.fertilizer.org/wp-content/uploads/1992/06/IFA_World_Fertilizer_Use_Manual.pdf',
      'evidence_scope': 'General coconut type guidance; Tall and Dwarf are broad types, not exact cultivar '
                        'identities. Square layout is the selected farm arrangement.',
      'harvest_behavior': 'repeated',
      'guidance': 'Ordinary nut harvest retains living palms and occupied land.',
      'is_default': True,
      'harvest_parts_json': '["nuts"]',
      'source_urls_json': '["https://www.pca.gov.ph/images/cocotech/PNS_BAFS_238_2018_Code_of_Good_Agricultural_Practices_for_Coconut.pdf"]'},
     {'profile_key': 'coconut-dwarf',
      'crop_name': 'Coconut',
      'crop_key': 'coconut',
      'variety_name': 'Dwarf (Short)',
      'variety_key': 'dwarf',
      'label': 'Coconut Dwarf',
      'row_spacing_m': '8',
      'plant_spacing_m': '8',
      'layout': 'square',
      'count_unit': 'tree',
      'version': 1,
      'source_url': 'https://www.fertilizer.org/wp-content/uploads/1992/06/IFA_World_Fertilizer_Use_Manual.pdf',
      'evidence_scope': 'General coconut type guidance; Tall and Dwarf are broad types, not exact cultivar '
                        'identities. Square layout is the selected farm arrangement.',
      'harvest_behavior': 'repeated',
      'guidance': 'Ordinary nut harvest retains living palms and occupied land.',
      'is_default': True,
      'harvest_parts_json': '["nuts"]',
      'source_urls_json': '["https://www.pca.gov.ph/images/cocotech/PNS_BAFS_238_2018_Code_of_Good_Agricultural_Practices_for_Coconut.pdf"]'},
     {'profile_key': 'saba-block',
      'crop_name': 'Banana',
      'crop_key': 'banana',
      'variety_name': 'Saba',
      'variety_key': 'saba',
      'label': 'Saba Block',
      'row_spacing_m': '4',
      'plant_spacing_m': '4',
      'layout': 'square',
      'count_unit': 'banana mat/clump',
      'version': 1,
      'source_url': 'https://pcaarrd.dost.gov.ph/index.php/quick-information-dispatch-qid-articles/tissue-cultured-and-macropropagated-disease-free-saba-plantlets-to-boost-production-and-empower-farmers-in-cagayan-valley',
      'evidence_scope': 'PCAARRD Cagayan Valley separate row planting guidance for Saba/Cardaba.',
      'harvest_behavior': 'mat',
      'guidance': 'One fruiting stem bears once; a living mat continues through suckers. Count occupied mats, '
                  'not individual stems.',
      'is_default': True,
      'harvest_parts_json': '["fruit"]',
      'source_urls_json': '["https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/Banana-Production-Manual.pdf", '
                          '"https://ask.ifas.ufl.edu/publication/MG040"]'},
     {'profile_key': 'saba-under-coconut',
      'crop_name': 'Banana',
      'crop_key': 'banana',
      'variety_name': 'Saba',
      'variety_key': 'saba',
      'label': 'Saba Under Coconut',
      'row_spacing_m': '5',
      'plant_spacing_m': '5',
      'layout': 'square',
      'count_unit': 'banana mat/clump',
      'version': 1,
      'source_url': 'https://www.pca.gov.ph/pdf/cocoTech/intercropping/CoconutBananaIntercropping.pdf',
      'evidence_scope': 'PCA coconut intercropping context for Cardaba/Saba; explicitly share an existing '
                        'coconut footprint.',
      'harvest_behavior': 'mat',
      'guidance': 'Nut and banana harvests do not automatically clear their shared land.',
      'is_default': False,
      'harvest_parts_json': '["fruit"]',
      'source_urls_json': '["https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/Banana-Production-Manual.pdf", '
                          '"https://ask.ifas.ufl.edu/publication/MG040"]'},
     {'profile_key': 'latundan-coconut-context',
      'crop_name': 'Banana',
      'crop_key': 'banana',
      'variety_name': 'Latundan',
      'variety_key': 'latundan',
      'label': 'Latundan Coconut Context',
      'row_spacing_m': '3',
      'plant_spacing_m': '3',
      'layout': 'square',
      'count_unit': 'banana mat/clump',
      'version': 1,
      'source_url': 'https://www.pca.gov.ph/pdf/cocoTech/intercropping/CoconutBananaIntercropping.pdf',
      'evidence_scope': 'PCA guidance for Lakatan/Latundan in coconut interspaces; assess light and actual '
                        'arrangement.',
      'harvest_behavior': 'mat',
      'guidance': 'A harvested stem does not mean its whole mat has died.',
      'is_default': True,
      'harvest_parts_json': '["fruit"]',
      'source_urls_json': '["https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/Banana-Production-Manual.pdf", '
                          '"https://ask.ifas.ufl.edu/publication/MG040"]'},
     {'profile_key': 'cassava-lakan-1',
      'crop_name': 'Cassava',
      'crop_key': 'cassava',
      'variety_name': 'Lakan 1',
      'variety_key': 'lakan-1',
      'label': 'Cassava Lakan 1',
      'row_spacing_m': '1',
      'plant_spacing_m': '1',
      'layout': 'square',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://www.iita.org/wp-content/uploads/2016/06/Cassava_system_cropping_guide.pdf',
      'evidence_scope': 'General cassava guidance, not a separately verified Lakan 1 optimum.',
      'harvest_behavior': 'root',
      'guidance': 'Root harvest uproots counted plants; record harvested-out plants separately from mortality. '
                  'Variety name does not establish food/feed safety.',
      'is_default': True,
      'harvest_parts_json': '["roots", "leaves"]',
      'source_urls_json': '["https://www.ukdr.uplb.edu.ph/pas/vol109/iss2/18/"]'},
     {'profile_key': 'sweet-potato-nsic-sp20',
      'crop_name': 'Sweet Potato / Kamote',
      'crop_key': 'sweet-potato',
      'variety_name': 'NSIC Sp20',
      'variety_key': 'nsic-sp20',
      'label': 'Sweet Potato Nsic Sp20',
      'row_spacing_m': '0.75',
      'plant_spacing_m': '0.3',
      'layout': 'rectangular',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://cagayanvalley.da.gov.ph/wp-content/uploads/2018/02/sweet_potato.pdf',
      'evidence_scope': 'General DA ridge and hill spacing; no cultivar-specific optimum claimed.',
      'harvest_behavior': 'root',
      'guidance': 'Leaf/shoot picking retains plants. Dig/lift roots carefully to avoid damage; record plants '
                  'removed.',
      'is_default': True,
      'harvest_parts_json': '["roots", "leaves/shoots"]',
      'source_urls_json': '["https://atr.vsu.edu.ph/article/view/9", '
                          '"https://agris.fao.org/search/en/providers/122631/records/67bdad8efd06341431d85374"]'},
     {'profile_key': 'sweet-potato-nsic-sp30',
      'crop_name': 'Sweet Potato / Kamote',
      'crop_key': 'sweet-potato',
      'variety_name': 'NSIC Sp30',
      'variety_key': 'nsic-sp30',
      'label': 'Sweet Potato Nsic Sp30',
      'row_spacing_m': '0.75',
      'plant_spacing_m': '0.3',
      'layout': 'rectangular',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://cagayanvalley.da.gov.ph/wp-content/uploads/2018/02/sweet_potato.pdf',
      'evidence_scope': 'General DA ridge and hill spacing; no cultivar-specific optimum claimed.',
      'harvest_behavior': 'root',
      'guidance': 'Leaf/shoot picking retains plants. Dig/lift roots carefully to avoid damage; record plants '
                  'removed.',
      'is_default': True,
      'harvest_parts_json': '["roots", "leaves/shoots"]',
      'source_urls_json': '["https://atr.vsu.edu.ph/article/view/9", '
                          '"https://agris.fao.org/search/en/providers/122631/records/67bdad8efd06341431d85374"]'},
     {'profile_key': 'sweet-potato-sp30-vsu-trial',
      'crop_name': 'Sweet Potato / Kamote',
      'crop_key': 'sweet-potato',
      'variety_name': 'NSIC Sp30',
      'variety_key': 'nsic-sp30',
      'label': 'Sweet Potato Sp30 Vsu Trial',
      'row_spacing_m': '0.75',
      'plant_spacing_m': '0.25',
      'layout': 'rectangular',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://agris.fao.org/search/en/providers/122631/records/67bdad8efd06341431d85374',
      'evidence_scope': 'Explicit VSU trial alternative on alluvial Inceptisol in Baybay, Leyte; not a universal '
                        'optimum.',
      'harvest_behavior': 'root',
      'guidance': 'Select only when adopting this trial arrangement. Timing guidance never physically confirms '
                  'readiness.',
      'is_default': False,
      'harvest_parts_json': '["roots", "leaves/shoots"]',
      'source_urls_json': '["https://atr.vsu.edu.ph/article/view/9"]'},
     {'profile_key': 'taro-iniito-vg2',
      'crop_name': 'Taro / Gabi',
      'crop_key': 'taro',
      'variety_name': 'Iniito/VG2',
      'variety_key': 'iniito-vg2',
      'label': 'Taro Iniito Vg2',
      'row_spacing_m': '1',
      'plant_spacing_m': '0.5',
      'layout': 'rectangular',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://files.peacecorps.gov/documents/R0006_New-Crop-Production-Handbook.pdf',
      'evidence_scope': 'General taro baseline: the Peace Corps handbook gives 1 m rows and 0.50-0.60 m within '
                        'rows. The supplied DA Bicol PDF is a tissue-culture propagation guide and does not '
                        'verify this spacing. No separate optimum is established for Iniito/VG2 or Morondon.',
      'harvest_behavior': 'corm',
      'guidance': 'Selective leaf harvest retains plants; corm lifting changes remaining plants. Do not close a '
                  'leaf-production planting using a corm rule.',
      'is_default': True,
      'harvest_parts_json': '["corms", "leaves"]',
      'source_urls_json': '["https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/TARO-Production-Guide.pdf", '
                          '"https://ispweb.pcaarrd.dost.gov.ph/st-based-agricultural-farming-interventions-on-the-production-of-camote-and-gabi/"]'},
     {'profile_key': 'taro-morondon',
      'crop_name': 'Taro / Gabi',
      'crop_key': 'taro',
      'variety_name': 'Morondon',
      'variety_key': 'morondon',
      'label': 'Taro Morondon',
      'row_spacing_m': '1',
      'plant_spacing_m': '0.5',
      'layout': 'rectangular',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://files.peacecorps.gov/documents/R0006_New-Crop-Production-Handbook.pdf',
      'evidence_scope': 'General taro baseline: the Peace Corps handbook gives 1 m rows and 0.50-0.60 m within '
                        'rows. The supplied DA Bicol PDF is a tissue-culture propagation guide and does not '
                        'verify this spacing. No separate optimum is established for Iniito/VG2 or Morondon.',
      'harvest_behavior': 'corm',
      'guidance': 'Selective leaf harvest retains plants; corm lifting changes remaining plants. Do not close a '
                  'leaf-production planting using a corm rule.',
      'is_default': True,
      'harvest_parts_json': '["corms", "leaves"]',
      'source_urls_json': '["https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/TARO-Production-Guide.pdf", '
                          '"https://ispweb.pcaarrd.dost.gov.ph/st-based-agricultural-farming-interventions-on-the-production-of-camote-and-gabi/"]'},
     {'profile_key': 'basil-genovese',
      'crop_name': 'Basil',
      'crop_key': 'basil',
      'variety_name': 'Genovese',
      'variety_key': 'genovese',
      'label': 'Basil Genovese',
      'row_spacing_m': '0.91',
      'plant_spacing_m': '0.61',
      'layout': 'rectangular',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://hgic.clemson.edu/factsheet/basil/',
      'evidence_scope': 'Clemson general 3-foot row/2-foot plant spacing, rounded to metres; Genovese spacing is '
                        'not a Philippine field trial optimum.',
      'harvest_behavior': 'repeated',
      'guidance': 'Pick leaves or shoot tips while leaving foliage for regrowth. End an exhausted planting '
                  'explicitly.',
      'is_default': True,
      'harvest_parts_json': '["leaves/shoots"]',
      'source_urls_json': '["https://extension.rutgers.edu/fs1279"]'},
     {'profile_key': 'basil-siam-queen',
      'crop_name': 'Basil',
      'crop_key': 'basil',
      'variety_name': 'Siam Queen',
      'variety_key': 'siam-queen',
      'label': 'Basil Siam Queen',
      'row_spacing_m': '0.61',
      'plant_spacing_m': '0.61',
      'layout': 'square',
      'count_unit': 'plant',
      'version': 1,
      'source_url': 'https://all-americaselections.org/product/basil-siam-queen/',
      'evidence_scope': 'AAS 2-foot garden spacing, rounded to metres; square layout is a proposed arrangement '
                        'rather than a validated field-row optimum.',
      'harvest_behavior': 'repeated',
      'guidance': 'Retain foliage for regrowth. Seed and transplant harvest intervals have different starting '
                  'events.',
      'is_default': True,
      'harvest_parts_json': '["leaves/shoots"]',
      'source_urls_json': '["https://extension.rutgers.edu/fs1279"]'}])



def downgrade():
    """Planting allocations and position history must not be discarded on rollback."""
    raise RuntimeError("Use the verified pre-upgrade backup with its matching source for recovery; this revision preserves farm history and has no destructive downgrade.")
