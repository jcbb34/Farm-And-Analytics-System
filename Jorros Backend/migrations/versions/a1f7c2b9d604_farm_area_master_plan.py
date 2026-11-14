"""Editable draft Joross Farm master plan, no automatic area verification or livestock records.

Revision ID: a1f7c2b9d604
Revises: z0j6e3g9b571, c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1f7c2b9d604'
down_revision = ('z0j6e3g9b571', 'c9d0e1f2a3b4')
branch_labels = None
depends_on = None

# Stable codes never change when the owner edits the label or proposed size.
ZONES = [
    ('A', None, 'field', 'Field A — Coconut Plantation', 9500, '89 Coconut Tall', 89),
    ('B', None, 'field', 'Field B — Banana Plantation', 1400, '65 Lakatan, 36 Saba', 101),
    ('C', None, 'field', 'Field C — Root Crops', 1100, 'Cassava, taro and sweet potato', 797),
    ('D', None, 'field', 'Field D — Herb Plantation', 100, '20 Basil plants', 20),
    ('FAC', None, 'facility', 'Facilities, Storage and Livestock', 5900, None, None),
    ('A1', 'A', 'section', 'Section A1', 9500, '89 Coconut Tall', 89),
    ('B1', 'B', 'section', 'Section B1', 700, '65 Banana Lakatan', 65),
    ('B2', 'B', 'section', 'Section B2', 700, '36 Banana Saba', 36),
    ('C1', 'C', 'section', 'Section C1', 600, '400 Cassava Lakan 1', 400),
    ('C2', 'C', 'section', 'Section C2', 125, '105 Taro Morondon', 105),
    ('C3', 'C', 'section', 'Section C3', 125, '100 Taro Iniito', 100),
    ('C4', 'C', 'section', 'Section C4', 125, '100 Sweet Potato SP20', 100),
    ('C5', 'C', 'section', 'Section C5', 125, '92 Sweet Potato SP30', 92),
    ('D1', 'D', 'section', 'Section D1', 50, '10 Basil Siam Queen', 10),
    ('D2', 'D', 'section', 'Section D2', 50, '10 Basil Genovese', 10),
    ('L1', 'FAC', 'livestock', 'Native Pig Area', 900, '20 Native Pigs', 20),
    ('L2', 'FAC', 'livestock', 'Large Black Pig Area', 350, '3 Large Black Pigs (1 female, 2 males)', 3),
    ('L3', 'FAC', 'livestock', '40-Day Chicken Area', 250, '30 Chickens (approximately 40 days old)', 30),
    ('L4', 'FAC', 'livestock', 'Native Chicken Area', 250, '10 Native Roosters, 10 Native Hens', 20),
    ('L5', 'FAC', 'livestock', 'Goat Housing and Activity Area', 700, '3 Goats', 3),
    ('S1', 'FAC', 'storage', 'Storage House 1', 100, 'Animal feed and supplements (suggested)', None),
    ('S2', 'FAC', 'storage', 'Storage House 2', 100, 'Farm tools and equipment (suggested)', None),
    ('S3', 'FAC', 'storage', 'Storage House 3', 100, 'Seeds, fertilizer and supplies (suggested)', None),
    ('S4', 'FAC', 'storage', 'Storage House 4', 100, 'Harvested products and packaging (suggested)', None),
    ('O1', 'FAC', 'office', 'Farm Office', 150, 'Administration', None),
    ('R1', 'FAC', 'infrastructure', 'Roads, Drainage, Biosecurity and Waste Management', 2900, 'Shared infrastructure; area not allocated to crops', None),
]


def upgrade():
    op.create_table('farm_area_zones',
        sa.Column('code', sa.String(24), primary_key=True),
        sa.Column('parent_code', sa.String(24), sa.ForeignKey('farm_area_zones.code'), nullable=True),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('proposed_area_m2', sa.Numeric(16, 4), nullable=False),
        sa.Column('measured_area_m2', sa.Numeric(16, 4), nullable=True),
        sa.Column('target_description', sa.String(180), nullable=True),
        sa.Column('expected_quantity', sa.Integer(), nullable=True),
        sa.Column('crop_field_id', sa.Integer(), sa.ForeignKey('crop_fields.id'), nullable=True),
        sa.Column('crop_section_id', sa.Integer(), sa.ForeignKey('crop_sections.id'), nullable=True),
        sa.Column('livestock_pen_id', sa.Integer(), sa.ForeignKey('livestock_pens.id'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('edit_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('proposed_area_m2 > 0', name='ck_zone_positive_proposal'),
        sa.CheckConstraint('measured_area_m2 IS NULL OR measured_area_m2 > 0', name='ck_zone_positive_measurement'),
    )
    op.create_index('ix_farm_area_zones_parent_code', 'farm_area_zones', ['parent_code'])
    op.create_index('ix_farm_area_zones_kind', 'farm_area_zones', ['kind'])
    bind = op.get_bind()
    # Never claim to know surveyed dimensions. Draft fields are seeded only when
    # no real crop field has been configured. Preexisting field data is untouched.
    create_crop_templates = not bind.execute(sa.text('SELECT COUNT(*) FROM crop_fields')).scalar()
    if create_crop_templates:
        for code, parent, kind, name, *_ in ZONES:
            if kind != 'field':
                continue
            bind.execute(sa.text('INSERT INTO crop_fields (name, area_m2, unavailable_area_m2, edit_version) VALUES (:name, NULL, 0, 1)'), {'name': name})
        for code, parent, kind, name, *_ in ZONES:
            if kind != 'section':
                continue
            field_name = next(z[3] for z in ZONES if z[0] == parent)
            field_id = bind.execute(sa.text('SELECT id FROM crop_fields WHERE name=:name'), {'name': field_name}).scalar_one()
            bind.execute(sa.text('INSERT INTO crop_sections (field_id, name, area_m2, unavailable_area_m2, edit_version) VALUES (:field_id, :name, NULL, 0, 1)'), {'field_id': field_id, 'name': name})
    # Seed selectable animal housing but not animal counts or pen capacities.
    # Capacity remains NULL until housing dimensions are verified.
    for code, parent, kind, name, *_ in ZONES:
        if kind == 'livestock':
            exists = bind.execute(sa.text('SELECT id FROM livestock_pens WHERE name=:name'), {'name': name}).scalar()
            if not exists:
                bind.execute(sa.text('INSERT INTO livestock_pens (name, animal_type, capacity, location_area, status, purpose, is_archived) '
                    'VALUES (:name, :animal, NULL, :area, :status, :purpose, 0)'), {
                    'name': name, 'animal': 'Pig' if code in ('L1', 'L2') else 'Chicken' if code in ('L3','L4') else 'Goat',
                    'area': 'Joross Farm facility zone · ' + code, 'status': 'Active', 'purpose': 'General'})
    # Add the missing Lakatan variety spacing default. The DA guide gives two
    # valid arrangements: 2x2.5 m and 3x3 m. The wider option is a draft default.
    if not bind.execute(sa.text("SELECT id FROM crop_spacing_profiles WHERE profile_key=:key AND version=1"),
                        {'key': 'lakatan-separate-block'}).scalar():
        bind.execute(sa.text("""
            INSERT INTO crop_spacing_profiles
                (profile_key, crop_key, crop_name, variety_key, variety_name,
                 label, row_spacing_m, plant_spacing_m, layout, count_unit,
                 version, source_url, source_urls_json, evidence_scope,
                 harvest_parts_json, harvest_behavior, guidance, is_default)
            VALUES
                (:key, 'banana', 'Banana', 'lakatan', 'Lakatan', :label,
                 3, 3, 'square', 'banana mat/clump', 1, :url, :related,
                 :evidence, :parts, 'mat', :guidance, 1)
        """), {
            'key':'lakatan-separate-block',
            'label':'Lakatan Separate Block (3 x 3 m)',
            'url':'https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/Banana-Production-Manual.pdf',
            'related':'["https://www.pca.gov.ph/pdf/cocoTech/intercropping/CoconutBananaIntercropping.pdf"]',
            'evidence':'The DA guide offers 2 x 2.5 m and 3 x 3 m for Lakatan. Wider 3 x 3 m is the chosen editable planning default; not a surveyed mat arrangement.',
            'parts':'["fruit"]',
            'guidance':'A fruiting pseudostem is harvested once; banana mats survive through followers. Preserve land occupancy until the actual mat is cleared.',
        })
    for code, parent, kind, name, area, description, count in ZONES:
        field_id = bind.execute(sa.text('SELECT id FROM crop_fields WHERE name=:name'), {'name': name}).scalar() if kind == 'field' else None
        section_id = None
        if kind == 'section':
            section_id = bind.execute(sa.text('SELECT id FROM crop_sections WHERE name=:name'), {'name': name}).scalar()
        pen_id = bind.execute(sa.text('SELECT id FROM livestock_pens WHERE name=:name'), {'name': name}).scalar() if kind == 'livestock' else None
        bind.execute(sa.text('INSERT INTO farm_area_zones (code, parent_code, kind, name, proposed_area_m2, measured_area_m2, target_description, expected_quantity, crop_field_id, crop_section_id, livestock_pen_id, is_active, edit_version) '
            'VALUES (:code, :parent, :kind, :name, :area, NULL, :description, :count, :field_id, :section_id, :pen_id, 1, 1)'), dict(
            code=code, parent=parent, kind=kind, name=name, area=area, description=description, count=count,
            field_id=field_id, section_id=section_id, pen_id=pen_id))


def downgrade():
    # Never delete seeded fields/pens: crop, workforce and livestock history might reference them.
    op.drop_index('ix_farm_area_zones_kind', table_name='farm_area_zones')
    op.drop_index('ix_farm_area_zones_parent_code', table_name='farm_area_zones')
    op.drop_table('farm_area_zones')
