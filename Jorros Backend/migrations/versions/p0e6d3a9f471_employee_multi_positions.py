"""Employee multi-position catalog and expanded profile information.

Revision ID: p0e6d3a9f471
Revises: o9d5c2f8e360
"""

from alembic import op
import sqlalchemy as sa

revision = "p0e6d3a9f471"
down_revision = "o9d5c2f8e360"
branch_labels = None
depends_on = None


POSITIONS = [
    # Management & administration
    ("Management & Administration", "Farm Owner / Proprietor", "Owns the farm and oversees overall direction."),
    ("Management & Administration", "Farm Manager", "Manages day-to-day farm operations and staff."),
    ("Management & Administration", "Assistant Farm Manager", "Supports the farm manager and coordinates operations."),
    ("Management & Administration", "Farm Supervisor", "Supervises field and livestock work crews."),
    ("Management & Administration", "Operations Supervisor", "Coordinates operational schedules and resources."),
    ("Management & Administration", "Farm Administrator", "Handles farm administrative records and coordination."),
    ("Management & Administration", "Office Assistant", "Supports farm office documentation and communication."),
    ("Management & Administration", "Payroll / Timekeeping Clerk", "Maintains attendance, timekeeping, and payroll records."),
    ("Management & Administration", "Human Resources Assistant", "Supports employee records, schedules, and workforce administration."),

    # General farm operations
    ("General Farm Operations", "General Farmer / Farm Worker", "Performs mixed crop, livestock, and general farm duties."),
    ("General Farm Operations", "Farm Hand", "Assists with routine farm work across different areas."),
    ("General Farm Operations", "Farm Caretaker", "Provides general care and upkeep for farm areas and assets."),
    ("General Farm Operations", "Utility Farm Worker", "Performs flexible support work across farm operations."),
    ("General Farm Operations", "Seasonal Farm Worker", "Supports seasonal planting, harvesting, and other peak work."),
    ("General Farm Operations", "Groundskeeper", "Maintains farm grounds, paths, fences, and surrounding areas."),
    ("General Farm Operations", "Farm Laborer", "Performs manual farm production and maintenance work."),

    # Crop production
    ("Crop Production", "Crop Farmer", "Handles crop production activities from planting to harvest."),
    ("Crop Production", "Crop Caretaker", "Maintains assigned crops and field areas."),
    ("Crop Production", "Field Worker", "Performs routine crop-field operations."),
    ("Crop Production", "Land Preparation Worker", "Prepares fields and growing areas before planting."),
    ("Crop Production", "Planting Worker", "Handles direct seeding and planting work."),
    ("Crop Production", "Transplanting Worker", "Moves seedlings into production fields or beds."),
    ("Crop Production", "Weeding Worker", "Controls weeds manually or using approved farm methods."),
    ("Crop Production", "Fertilizer Applicator", "Applies fertilizer according to approved crop plans."),
    ("Crop Production", "Pesticide Applicator", "Applies approved crop protection products safely."),
    ("Crop Production", "Crop Scout", "Inspects crops for pests, diseases, stress, and growth condition."),
    ("Crop Production", "Crop Monitoring Assistant", "Records crop growth and field observations."),
    ("Crop Production", "Harvest Worker", "Harvests mature crops according to schedule."),
    ("Crop Production", "Post-Harvest Worker", "Handles crops after harvest, including cleaning and preparation."),
    ("Crop Production", "Fruit Tree Caretaker", "Maintains fruit trees, pruning, care, and harvest readiness."),
    ("Crop Production", "Vegetable Grower", "Specializes in vegetable crop production."),
    ("Crop Production", "Root Crop Worker", "Supports production and harvest of root crops."),
    ("Crop Production", "Corn Production Worker", "Supports corn planting, care, and harvest."),

    # Nursery, horticulture & protected culture
    ("Nursery & Horticulture", "Nursery Worker", "Maintains nursery plants and propagation areas."),
    ("Nursery & Horticulture", "Seedling Caretaker", "Cares for seedlings before field transfer."),
    ("Nursery & Horticulture", "Plant Propagation Worker", "Handles seed, cutting, grafting, and propagation tasks."),
    ("Nursery & Horticulture", "Greenhouse Worker", "Maintains greenhouse crops and facilities."),
    ("Nursery & Horticulture", "Hydroponics Worker", "Supports routine hydroponic crop care."),
    ("Nursery & Horticulture", "Hydroponics Technician", "Maintains hydroponic systems, nutrients, and monitoring."),
    ("Nursery & Horticulture", "Horticulture Worker", "Performs specialized care for horticultural crops."),
    ("Nursery & Horticulture", "Pruning / Training Worker", "Prunes and trains crops or fruit-bearing plants."),

    # Irrigation, water & soil
    ("Irrigation, Water & Soil", "Irrigation Worker", "Operates and checks crop irrigation activities."),
    ("Irrigation, Water & Soil", "Irrigation Technician", "Maintains irrigation lines, valves, timers, and systems."),
    ("Irrigation, Water & Soil", "Pump Operator", "Operates water pumps and monitors water delivery."),
    ("Irrigation, Water & Soil", "Water System Technician", "Maintains farm water distribution systems."),
    ("Irrigation, Water & Soil", "Soil Preparation Worker", "Prepares soil, beds, and amendments for planting."),
    ("Irrigation, Water & Soil", "Compost Worker", "Produces and manages compost and organic materials."),
    ("Irrigation, Water & Soil", "Compost Technician", "Monitors compost condition, handling, and application."),
    ("Irrigation, Water & Soil", "Soil / Fertility Assistant", "Supports soil sampling and fertility-related records."),

    # Livestock general
    ("Livestock - General", "Livestock Caretaker", "Provides daily care for livestock animals."),
    ("Livestock - General", "Animal Caretaker", "Performs general animal care and welfare tasks."),
    ("Livestock - General", "Livestock Handler", "Handles and moves animals safely for farm operations."),
    ("Livestock - General", "Pen / Barn Attendant", "Maintains animal housing and assists with routine care."),
    ("Livestock - General", "Livestock Monitoring Assistant", "Records animal condition, growth, and observations."),
    ("Livestock - General", "Livestock Records Assistant", "Maintains livestock-related farm records."),
    ("Livestock - General", "Pasture Worker", "Maintains grazing and pasture areas."),

    # Goat & sheep
    ("Goat & Sheep", "Goat Caretaker", "Provides daily care for goats."),
    ("Goat & Sheep", "Sheep Caretaker", "Provides daily care for sheep."),
    ("Goat & Sheep", "Goat / Sheep Feeding Assistant", "Handles feeding and water tasks for goats and sheep."),
    ("Goat & Sheep", "Goat / Sheep Breeding Assistant", "Supports breeding, pregnancy, and reproduction records."),
    ("Goat & Sheep", "Kid / Lamb Caretaker", "Provides specialized care for young goats or sheep."),

    # Swine
    ("Swine", "Swine Caretaker", "Provides daily care for pigs."),
    ("Swine", "Piglet Caretaker", "Provides specialized care for piglets."),
    ("Swine", "Farrowing Attendant", "Supports sow farrowing and newborn piglet care."),
    ("Swine", "Swine Feeding Assistant", "Handles feeding and water tasks for pigs."),
    ("Swine", "Swine Breeding Assistant", "Supports breeding and reproduction management for pigs."),
    ("Swine", "Swine Pen Attendant", "Maintains pig pens and supports animal handling."),

    # Cattle & carabao
    ("Cattle & Carabao", "Cattle Caretaker", "Provides routine care for cattle."),
    ("Cattle & Carabao", "Carabao Caretaker", "Provides routine care for carabao."),
    ("Cattle & Carabao", "Dairy Worker / Milker", "Handles milking and dairy-animal care."),
    ("Cattle & Carabao", "Cattle Feeding Assistant", "Handles cattle feeding and water tasks."),
    ("Cattle & Carabao", "Cattle Breeding Assistant", "Supports breeding and reproduction management for cattle."),

    # Poultry & ducks
    ("Poultry & Ducks", "Poultry Caretaker", "Provides general poultry care."),
    ("Poultry & Ducks", "Chicken Caretaker", "Provides daily care for chickens."),
    ("Poultry & Ducks", "Duck Caretaker", "Provides daily care for ducks."),
    ("Poultry & Ducks", "Broiler Caretaker", "Manages broiler feeding, housing, and growth care."),
    ("Poultry & Ducks", "Layer Caretaker", "Manages laying birds and egg-production care."),
    ("Poultry & Ducks", "Chick Brooder Attendant", "Provides brooder care for chicks."),
    ("Poultry & Ducks", "Duckling Brooder Attendant", "Provides brooder care for ducklings."),
    ("Poultry & Ducks", "Poultry Feeding Assistant", "Handles poultry feed and water duties."),
    ("Poultry & Ducks", "Egg Collection Worker", "Collects, records, and handles eggs."),
    ("Poultry & Ducks", "Poultry House Attendant", "Maintains poultry housing and sanitation."),

    # Animal health, breeding & welfare
    ("Animal Health, Breeding & Welfare", "Animal Health Assistant", "Supports routine livestock health activities."),
    ("Animal Health, Breeding & Welfare", "Veterinary Aide", "Assists with farm veterinary procedures and records."),
    ("Animal Health, Breeding & Welfare", "Vaccination Assistant", "Supports scheduled livestock vaccination activities."),
    ("Animal Health, Breeding & Welfare", "Medication / Treatment Assistant", "Supports approved animal treatment activities."),
    ("Animal Health, Breeding & Welfare", "Breeding / Reproduction Assistant", "Supports animal breeding and reproduction tracking."),
    ("Animal Health, Breeding & Welfare", "Livestock Growth Checker", "Conducts or assists with scheduled animal growth checks."),
    ("Animal Health, Breeding & Welfare", "Animal Welfare Monitor", "Monitors animal condition, housing, and welfare concerns."),
    ("Animal Health, Breeding & Welfare", "Isolation / Sick Pen Attendant", "Provides care for animals in isolation or treatment pens."),

    # Feed & nutrition
    ("Feed & Nutrition", "Feeding Assistant", "Performs scheduled feeding work across livestock groups."),
    ("Feed & Nutrition", "Feed Preparation Worker", "Prepares feed according to approved feeding plans."),
    ("Feed & Nutrition", "Feed Mixer", "Mixes feed ingredients and prepared rations."),
    ("Feed & Nutrition", "Feed Storekeeper", "Controls feed storage, issuance, and stock condition."),
    ("Feed & Nutrition", "Feed Inventory Assistant", "Records feed stock and usage."),
    ("Feed & Nutrition", "Nutrition / Feeding Records Assistant", "Maintains feeding-plan and actual-usage records."),

    # Aquaculture (optional farm expansion)
    ("Aquaculture", "Fishpond Caretaker", "Maintains fishponds and routine fish care."),
    ("Aquaculture", "Aquaculture Worker", "Performs routine aquaculture production activities."),
    ("Aquaculture", "Fish Feeding Assistant", "Handles scheduled feeding for cultured fish."),
    ("Aquaculture", "Pond Water Quality Assistant", "Supports pond water-quality monitoring."),

    # Inventory, warehouse & procurement
    ("Inventory, Warehouse & Procurement", "Inventory Storekeeper", "Controls farm inventory storage and issuance."),
    ("Inventory, Warehouse & Procurement", "Inventory Assistant", "Supports inventory counts, receipts, and usage records."),
    ("Inventory, Warehouse & Procurement", "Warehouse Clerk", "Maintains warehouse records and stock organization."),
    ("Inventory, Warehouse & Procurement", "Warehouse Worker", "Handles receipt, storage, and movement of farm supplies."),
    ("Inventory, Warehouse & Procurement", "Procurement Assistant", "Supports sourcing and purchasing of farm supplies."),
    ("Inventory, Warehouse & Procurement", "Purchasing Officer", "Coordinates approved farm purchases and suppliers."),
    ("Inventory, Warehouse & Procurement", "Receiving Clerk", "Receives and checks delivered farm supplies."),
    ("Inventory, Warehouse & Procurement", "Stock / Reorder Monitor", "Monitors stock levels and reorder needs."),

    # Production, processing & quality
    ("Production, Processing & Quality", "Production Assistant", "Supports farm production and post-production activities."),
    ("Production, Processing & Quality", "Processing Worker", "Handles approved farm-product processing tasks."),
    ("Production, Processing & Quality", "Packing Worker", "Packs farm products for storage, sale, or delivery."),
    ("Production, Processing & Quality", "Sorting / Grading Worker", "Sorts and grades farm products by quality."),
    ("Production, Processing & Quality", "Quality Control Assistant", "Checks product quality and production records."),
    ("Production, Processing & Quality", "Food Safety Assistant", "Supports sanitation and food-safety procedures."),
    ("Production, Processing & Quality", "Production Records Assistant", "Maintains production quantities and output records."),

    # Sales, logistics & delivery
    ("Sales, Logistics & Delivery", "Sales Assistant", "Supports farm-product sales and customer transactions."),
    ("Sales, Logistics & Delivery", "Farm Market Seller", "Handles direct farm-market selling."),
    ("Sales, Logistics & Delivery", "Order Fulfillment Assistant", "Prepares farm orders for pickup or delivery."),
    ("Sales, Logistics & Delivery", "Delivery Driver", "Delivers farm products or supplies."),
    ("Sales, Logistics & Delivery", "Farm Driver", "Operates farm transport vehicles for approved work."),
    ("Sales, Logistics & Delivery", "Loader / Delivery Helper", "Assists with loading, unloading, and delivery."),
    ("Sales, Logistics & Delivery", "Logistics Assistant", "Coordinates movement of farm products and supplies."),

    # Equipment & maintenance
    ("Equipment & Maintenance", "Farm Equipment Operator", "Operates approved farm equipment."),
    ("Equipment & Maintenance", "Tractor Operator", "Operates tractor equipment for farm work."),
    ("Equipment & Maintenance", "Machine Operator", "Operates farm machinery and processing equipment."),
    ("Equipment & Maintenance", "Maintenance Worker", "Performs routine farm facility and equipment maintenance."),
    ("Equipment & Maintenance", "Farm Mechanic", "Repairs and services farm machinery and vehicles."),
    ("Equipment & Maintenance", "Electrician", "Maintains approved farm electrical systems."),
    ("Equipment & Maintenance", "Carpenter / Repair Worker", "Handles basic carpentry and farm-structure repairs."),
    ("Equipment & Maintenance", "Welder / Fabrication Worker", "Performs approved welding and fabrication work."),
    ("Equipment & Maintenance", "Fence / Pen Repair Worker", "Maintains fences, gates, pens, and animal enclosures."),

    # Safety, sanitation & biosecurity
    ("Safety, Sanitation & Biosecurity", "Sanitation Worker", "Performs cleaning and sanitation of farm work areas."),
    ("Safety, Sanitation & Biosecurity", "Cleaning Crew", "Maintains cleanliness of farm facilities and equipment."),
    ("Safety, Sanitation & Biosecurity", "Biosecurity Assistant", "Supports farm biosecurity procedures and records."),
    ("Safety, Sanitation & Biosecurity", "Biosecurity Officer", "Coordinates and monitors farm biosecurity controls."),
    ("Safety, Sanitation & Biosecurity", "Waste Management Worker", "Handles farm waste according to approved procedures."),
    ("Safety, Sanitation & Biosecurity", "Pest Control Worker", "Supports approved pest-control activities around facilities."),
    ("Safety, Sanitation & Biosecurity", "Farm Safety Officer", "Monitors workplace safety procedures and incidents."),

    # Records, technology & monitoring
    ("Records, Technology & Monitoring", "Farm Records Clerk", "Maintains farm operational records and documents."),
    ("Records, Technology & Monitoring", "Data Encoder", "Encodes farm records into the monitoring system."),
    ("Records, Technology & Monitoring", "Farm Monitoring Assistant", "Supports regular data collection and monitoring."),
    ("Records, Technology & Monitoring", "Weather / Field Monitoring Assistant", "Records weather and field observations."),
    ("Records, Technology & Monitoring", "IT / System Assistant", "Supports farm system devices and basic technical needs."),
    ("Records, Technology & Monitoring", "Sensor / Device Monitoring Assistant", "Monitors supported farm sensors and connected devices."),
]


def upgrade() -> None:
    op.add_column("employees", sa.Column("email", sa.String(length=120), nullable=True))
    op.add_column("employees", sa.Column("address", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("date_hired", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("employment_type", sa.String(length=30), nullable=True))
    op.add_column("employees", sa.Column("assigned_area", sa.String(length=120), nullable=True))
    op.add_column("employees", sa.Column("skills", sa.Text(), nullable=True))
    op.add_column("employees", sa.Column("emergency_contact_name", sa.String(length=120), nullable=True))
    op.add_column("employees", sa.Column("emergency_contact_relationship", sa.String(length=60), nullable=True))
    op.add_column("employees", sa.Column("emergency_contact_number", sa.String(length=20), nullable=True))

    op.create_table(
        "farm_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_farm_positions_name", "farm_positions", ["name"], unique=True)
    op.create_index("ix_farm_positions_category", "farm_positions", ["category"], unique=False)
    op.create_index("ix_farm_positions_active", "farm_positions", ["is_active"], unique=False)

    op.create_table(
        "employee_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id"], ["farm_positions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "position_id", name="uq_employee_position"),
    )
    op.create_index("ix_employee_positions_employee", "employee_positions", ["employee_id"], unique=False)
    op.create_index("ix_employee_positions_position", "employee_positions", ["position_id"], unique=False)
    op.create_index("ix_employee_positions_primary", "employee_positions", ["is_primary"], unique=False)
    op.create_index(
        "ix_employee_positions_one_primary",
        "employee_positions",
        ["employee_id"],
        unique=True,
        mssql_where=sa.text("is_primary = 1"),
        sqlite_where=sa.text("is_primary = 1"),
    )

    position_table = sa.table(
        "farm_positions",
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(position_table, [
        {"name": name, "category": category, "description": description, "sort_order": index, "is_active": True}
        for index, (category, name, description) in enumerate(POSITIONS, start=1)
    ])

    # Preserve any employee position text created before this migration.  If a
    # legacy/custom title is not in the seeded catalog, add it under a custom
    # category and link it as that employee's primary position.
    bind = op.get_bind()
    position_rows = bind.execute(sa.text("SELECT id, name FROM farm_positions")).all()
    position_ids = {str(name).strip().lower(): int(position_id) for position_id, name in position_rows}
    employees = bind.execute(
        sa.text("SELECT id, position FROM employees WHERE position IS NOT NULL AND LTRIM(RTRIM(position)) <> ''")
    ).all()

    for employee_id, position_name in employees:
        clean_name = str(position_name).strip()
        key = clean_name.lower()
        if key not in position_ids:
            bind.execute(
                sa.text(
                    "INSERT INTO farm_positions (name, category, description, sort_order, is_active) "
                    "VALUES (:name, :category, :description, :sort_order, 1)"
                ),
                {
                    "name": clean_name,
                    "category": "Custom / Legacy",
                    "description": "Position preserved from an employee record created before multi-position support.",
                    "sort_order": 10000,
                },
            )
            position_ids[key] = int(bind.execute(
                sa.text("SELECT id FROM farm_positions WHERE name = :name"),
                {"name": clean_name},
            ).scalar_one())
        bind.execute(
            sa.text(
                "INSERT INTO employee_positions (employee_id, position_id, is_primary) "
                "VALUES (:employee_id, :position_id, 1)"
            ),
            {"employee_id": int(employee_id), "position_id": position_ids[key]},
        )


def downgrade() -> None:
    op.drop_index("ix_employee_positions_one_primary", table_name="employee_positions")
    op.drop_index("ix_employee_positions_primary", table_name="employee_positions")
    op.drop_index("ix_employee_positions_position", table_name="employee_positions")
    op.drop_index("ix_employee_positions_employee", table_name="employee_positions")
    op.drop_table("employee_positions")

    op.drop_index("ix_farm_positions_active", table_name="farm_positions")
    op.drop_index("ix_farm_positions_category", table_name="farm_positions")
    op.drop_index("ix_farm_positions_name", table_name="farm_positions")
    op.drop_table("farm_positions")

    op.drop_column("employees", "emergency_contact_number")
    op.drop_column("employees", "emergency_contact_relationship")
    op.drop_column("employees", "emergency_contact_name")
    op.drop_column("employees", "skills")
    op.drop_column("employees", "assigned_area")
    op.drop_column("employees", "employment_type")
    op.drop_column("employees", "date_hired")
    op.drop_column("employees", "address")
    op.drop_column("employees", "email")
