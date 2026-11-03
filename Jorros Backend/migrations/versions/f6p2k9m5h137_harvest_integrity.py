"""Unify harvest task, crop yield, and production stock integrity.

Revision ID: f6p2k9m5h137
Revises: e5o1j8l4g026
"""

from alembic import op
import sqlalchemy as sa


revision = "f6p2k9m5h137"
down_revision = "e5o1j8l4g026"
branch_labels = None
depends_on = None


def _drop_mssql_default_constraint(bind, table_name: str, column_name: str) -> None:
    """Drop SQL Server's separately stored DEFAULT before dropping a column."""
    if bind.dialect.name != "mssql":
        return
    bind.execute(
        sa.text(
            f"""
DECLARE @constraint_name sysname;
DECLARE @schema_name sysname;

SELECT TOP (1)
    @constraint_name = dc.name,
    @schema_name = s.name
FROM sys.default_constraints AS dc
INNER JOIN sys.columns AS c ON c.default_object_id = dc.object_id
INNER JOIN sys.tables AS t ON t.object_id = c.object_id
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
WHERE t.name = N'{table_name}'
  AND c.name = N'{column_name}';

IF @constraint_name IS NOT NULL
BEGIN
    DECLARE @sql nvarchar(max) =
        N'ALTER TABLE ' + QUOTENAME(@schema_name) + N'.' + QUOTENAME(N'{table_name}') +
        N' DROP CONSTRAINT ' + QUOTENAME(@constraint_name) + N';';
    EXEC sys.sp_executesql @sql;
END;
"""
        )
    )


def upgrade() -> None:
    op.add_column("crops", sa.Column("harvest_cycle_reopened_at", sa.DateTime(), nullable=True))
    op.add_column(
        "crops",
        sa.Column("harvest_cycle_reopened_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_crops_harvest_cycle_reopened_by_user_id_users",
        "crops",
        "users",
        ["harvest_cycle_reopened_by_user_id"],
        ["id"],
    )

    op.alter_column(
        "crop_yield_records",
        "quantity_kg",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(12, 3),
        existing_nullable=False,
    )

    for column_name in (
        "farm_use_quantity_kg",
        "damaged_quantity_kg",
        "reserved_quantity_kg",
    ):
        op.alter_column(
            "crop_yield_records",
            column_name,
            existing_type=sa.Numeric(12, 2),
            type_=sa.Numeric(12, 3),
            existing_nullable=False,
        )
    op.alter_column(
        "crop_yield_records",
        "yield_per_hectare",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(12, 3),
        existing_nullable=True,
    )

    op.add_column(
        "crop_yield_records",
        sa.Column("is_voided", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("crop_yield_records", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("crop_yield_records", sa.Column("voided_at", sa.DateTime(), nullable=True))
    op.add_column("crop_yield_records", sa.Column("voided_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_crop_yield_records_voided_by_user_id_users",
        "crop_yield_records",
        "users",
        ["voided_by_user_id"],
        ["id"],
    )
    op.create_index("ix_crop_yield_records_is_voided", "crop_yield_records", ["is_voided"])

    op.add_column("task_submissions", sa.Column("performed_date", sa.Date(), nullable=True))
    op.add_column("task_submissions", sa.Column("harvest_quality", sa.String(length=50), nullable=True))
    for column_name in (
        "harvest_farm_use_quantity_kg",
        "harvest_damaged_quantity_kg",
        "harvest_reserved_quantity_kg",
    ):
        op.add_column(
            "task_submissions",
            sa.Column(column_name, sa.Numeric(12, 3), nullable=False, server_default=sa.text("0")),
        )

    op.add_column(
        "livestock_production_records",
        sa.Column("is_voided", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("livestock_production_records", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("livestock_production_records", sa.Column("voided_at", sa.DateTime(), nullable=True))
    op.add_column(
        "livestock_production_records",
        sa.Column("voided_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_livestock_production_records_voided_by_user_id_users",
        "livestock_production_records",
        "users",
        ["voided_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_livestock_production_records_is_voided",
        "livestock_production_records",
        ["is_voided"],
    )

    op.execute(
        sa.text(
            "UPDATE farm_activities "
            "SET requires_review = 1, requires_evidence = 1 "
            "WHERE source_module = 'Crop' "
            "AND source_type = 'crop_harvest' "
            "AND status IN ('Pending', 'In Progress', 'Submitted for Review', 'Returned') "
            "AND is_archived = 0"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        "ix_livestock_production_records_is_voided",
        table_name="livestock_production_records",
    )
    op.drop_constraint(
        "fk_livestock_production_records_voided_by_user_id_users",
        "livestock_production_records",
        type_="foreignkey",
    )
    op.drop_column("livestock_production_records", "voided_by_user_id")
    op.drop_column("livestock_production_records", "voided_at")
    op.drop_column("livestock_production_records", "void_reason")
    _drop_mssql_default_constraint(bind, "livestock_production_records", "is_voided")
    op.drop_column("livestock_production_records", "is_voided")

    _drop_mssql_default_constraint(bind, "task_submissions", "harvest_reserved_quantity_kg")
    op.drop_column("task_submissions", "harvest_reserved_quantity_kg")
    _drop_mssql_default_constraint(bind, "task_submissions", "harvest_damaged_quantity_kg")
    op.drop_column("task_submissions", "harvest_damaged_quantity_kg")
    _drop_mssql_default_constraint(bind, "task_submissions", "harvest_farm_use_quantity_kg")
    op.drop_column("task_submissions", "harvest_farm_use_quantity_kg")
    op.drop_column("task_submissions", "harvest_quality")
    op.drop_column("task_submissions", "performed_date")

    op.drop_index("ix_crop_yield_records_is_voided", table_name="crop_yield_records")
    op.drop_constraint(
        "fk_crop_yield_records_voided_by_user_id_users",
        "crop_yield_records",
        type_="foreignkey",
    )
    op.drop_column("crop_yield_records", "voided_by_user_id")
    op.drop_column("crop_yield_records", "voided_at")
    op.drop_column("crop_yield_records", "void_reason")
    _drop_mssql_default_constraint(bind, "crop_yield_records", "is_voided")
    op.drop_column("crop_yield_records", "is_voided")

    op.alter_column(
        "crop_yield_records",
        "yield_per_hectare",
        existing_type=sa.Numeric(12, 3),
        type_=sa.Numeric(12, 2),
        existing_nullable=True,
    )
    for column_name in (
        "reserved_quantity_kg",
        "damaged_quantity_kg",
        "farm_use_quantity_kg",
    ):
        op.alter_column(
            "crop_yield_records",
            column_name,
            existing_type=sa.Numeric(12, 3),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )
    op.alter_column(
        "crop_yield_records",
        "quantity_kg",
        existing_type=sa.Numeric(12, 3),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )

    op.drop_constraint(
        "fk_crops_harvest_cycle_reopened_by_user_id_users",
        "crops",
        type_="foreignkey",
    )
    op.drop_column("crops", "harvest_cycle_reopened_by_user_id")
    op.drop_column("crops", "harvest_cycle_reopened_at")
