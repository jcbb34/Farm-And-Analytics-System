"""farm-wide crop and livestock production sales

Revision ID: k5d2f8a7c930
Revises: j4a9c7e2d615
Create Date: 2026-08-16 16:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "k5d2f8a7c930"
down_revision: Union[str, Sequence[str], None] = "j4a9c7e2d615"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Crop harvest allocation: harvested output is split into saleable, farm use,
    # damaged/spoiled and reserved quantities without creating another harvest form.
    op.add_column("crop_yield_records", sa.Column("farm_use_quantity_kg", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False))
    op.add_column("crop_yield_records", sa.Column("damaged_quantity_kg", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False))
    op.add_column("crop_yield_records", sa.Column("reserved_quantity_kg", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False))

    # Existing livestock production ledger becomes the shared farm-output ledger.
    op.add_column("livestock_production_records", sa.Column("source_type", sa.String(20), server_default=sa.text("'Livestock'"), nullable=False))
    op.add_column("livestock_production_records", sa.Column("crop_id", sa.Integer(), nullable=True))
    op.add_column("livestock_production_records", sa.Column("crop_yield_record_id", sa.Integer(), nullable=True))
    op.add_column("livestock_production_records", sa.Column("farm_use_quantity", sa.Numeric(12, 3), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock_production_records", sa.Column("reserved_quantity", sa.Numeric(12, 3), server_default=sa.text("0"), nullable=False))
    op.alter_column("livestock_production_records", "livestock_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_livestock_production_records_source_type", "livestock_production_records", ["source_type"], unique=False)
    op.create_index("ix_livestock_production_records_crop_id", "livestock_production_records", ["crop_id"], unique=False)
    op.create_index(
        "ux_livestock_production_records_crop_yield_record_id",
        "livestock_production_records",
        ["crop_yield_record_id"],
        unique=True,
        mssql_where=sa.text("crop_yield_record_id IS NOT NULL"),
    )
    op.create_foreign_key("fk_production_crop_id", "livestock_production_records", "crops", ["crop_id"], ["id"])
    op.create_foreign_key("fk_production_crop_yield_record_id", "livestock_production_records", "crop_yield_records", ["crop_yield_record_id"], ["id"])

    # Egg-setting can reserve actual egg stock so hatching eggs cannot also be sold.
    op.add_column("livestock_reproduction_records", sa.Column("source_production_record_id", sa.Integer(), nullable=True))
    op.create_index("ix_livestock_reproduction_records_source_production_record_id", "livestock_reproduction_records", ["source_production_record_id"], unique=False)
    op.create_foreign_key("fk_reproduction_source_production", "livestock_reproduction_records", "livestock_production_records", ["source_production_record_id"], ["id"])

    # Sales can now originate from a crop product lot or livestock/product lot.
    op.add_column("livestock_sales", sa.Column("source_type", sa.String(20), server_default=sa.text("'Livestock'"), nullable=False))
    op.add_column("livestock_sales", sa.Column("crop_id", sa.Integer(), nullable=True))
    op.alter_column("livestock_sales", "livestock_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_livestock_sales_source_type", "livestock_sales", ["source_type"], unique=False)
    op.create_index("ix_livestock_sales_crop_id", "livestock_sales", ["crop_id"], unique=False)
    op.create_foreign_key("fk_sales_crop_id", "livestock_sales", "crops", ["crop_id"], ["id"])

    # Preserve all existing records as livestock sources.
    op.execute("UPDATE livestock_production_records SET source_type = 'Livestock' WHERE source_type IS NULL OR LTRIM(RTRIM(source_type)) = ''")
    op.execute("UPDATE livestock_sales SET source_type = 'Livestock' WHERE source_type IS NULL OR LTRIM(RTRIM(source_type)) = ''")

    # Existing crop yield history becomes crop sale stock automatically. New yield
    # records are connected transactionally by the crop endpoint.
    op.execute("""
        INSERT INTO livestock_production_records (
            source_type, livestock_id, crop_id, crop_yield_record_id,
            output_type, record_date, period_start_date, period_end_date,
            source_head_quantity, source_female_quantity, source_active_quantity,
            gross_quantity, loss_quantity, farm_use_quantity, reserved_quantity,
            quantity, unit, quality_grade, destination, track_sale_inventory,
            notes, recorded_by_user_id, created_at
        )
        SELECT
            'Crop', NULL, y.crop_id, y.id,
            c.name, y.harvest_date, y.harvest_date, y.harvest_date,
            NULL, NULL, NULL,
            y.quantity_kg, 0, 0, 0,
            y.quantity_kg, 'kg', y.quality, 'Available for sale', 1,
            y.notes, y.recorded_by_user_id, y.created_at
        FROM crop_yield_records y
        INNER JOIN crops c ON c.id = y.crop_id
        WHERE NOT EXISTS (
            SELECT 1 FROM livestock_production_records p
            WHERE p.crop_yield_record_id = y.id
        )
    """)


def downgrade() -> None:
    # Crop-specific sale/output rows cannot be represented by the prior livestock-only schema.
    op.execute("DELETE FROM livestock_sales WHERE source_type = 'Crop' OR crop_id IS NOT NULL")
    op.execute("DELETE FROM livestock_production_records WHERE source_type = 'Crop' OR crop_id IS NOT NULL")

    op.drop_constraint("fk_sales_crop_id", "livestock_sales", type_="foreignkey")
    op.drop_index("ix_livestock_sales_crop_id", table_name="livestock_sales")
    op.drop_index("ix_livestock_sales_source_type", table_name="livestock_sales")
    op.drop_column("livestock_sales", "crop_id")
    op.drop_column("livestock_sales", "source_type")
    op.alter_column("livestock_sales", "livestock_id", existing_type=sa.Integer(), nullable=False)

    op.drop_constraint("fk_reproduction_source_production", "livestock_reproduction_records", type_="foreignkey")
    op.drop_index("ix_livestock_reproduction_records_source_production_record_id", table_name="livestock_reproduction_records")
    op.drop_column("livestock_reproduction_records", "source_production_record_id")

    op.drop_constraint("fk_production_crop_yield_record_id", "livestock_production_records", type_="foreignkey")
    op.drop_constraint("fk_production_crop_id", "livestock_production_records", type_="foreignkey")
    op.drop_index("ux_livestock_production_records_crop_yield_record_id", table_name="livestock_production_records")
    op.drop_index("ix_livestock_production_records_crop_id", table_name="livestock_production_records")
    op.drop_index("ix_livestock_production_records_source_type", table_name="livestock_production_records")
    op.drop_column("livestock_production_records", "reserved_quantity")
    op.drop_column("livestock_production_records", "farm_use_quantity")
    op.drop_column("livestock_production_records", "crop_yield_record_id")
    op.drop_column("livestock_production_records", "crop_id")
    op.drop_column("livestock_production_records", "source_type")
    op.alter_column("livestock_production_records", "livestock_id", existing_type=sa.Integer(), nullable=False)

    op.drop_column("crop_yield_records", "reserved_quantity_kg")
    op.drop_column("crop_yield_records", "damaged_quantity_kg")
    op.drop_column("crop_yield_records", "farm_use_quantity_kg")
