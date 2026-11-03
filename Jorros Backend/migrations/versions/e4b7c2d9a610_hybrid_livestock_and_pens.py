"""hybrid livestock records and pen management

Revision ID: e4b7c2d9a610
Revises: d3f1b8c9a440
Create Date: 2026-08-14 16:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c2d9a610"
down_revision: Union[str, Sequence[str], None] = "d3f1b8c9a440"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "livestock_pens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("animal_type", sa.String(length=50), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("location_area", sa.String(length=150), nullable=True),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'Active'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_livestock_pens_name"),
    )
    op.create_index(op.f("ix_livestock_pens_name"), "livestock_pens", ["name"], unique=False)
    op.create_index(op.f("ix_livestock_pens_status"), "livestock_pens", ["status"], unique=False)
    op.create_index(op.f("ix_livestock_pens_is_archived"), "livestock_pens", ["is_archived"], unique=False)

    op.add_column(
        "livestock",
        sa.Column("record_type", sa.String(length=20), server_default=sa.text("'Batch'"), nullable=False),
    )
    op.add_column(
        "livestock",
        sa.Column("lifecycle_status", sa.String(length=30), server_default=sa.text("'Active'"), nullable=False),
    )
    op.add_column("livestock", sa.Column("pen_id", sa.Integer(), nullable=True))
    op.add_column("livestock", sa.Column("origin_livestock_id", sa.Integer(), nullable=True))

    op.create_index(op.f("ix_livestock_record_type"), "livestock", ["record_type"], unique=False)
    op.create_index(op.f("ix_livestock_lifecycle_status"), "livestock", ["lifecycle_status"], unique=False)
    op.create_index(op.f("ix_livestock_pen_id"), "livestock", ["pen_id"], unique=False)
    op.create_index(op.f("ix_livestock_origin_livestock_id"), "livestock", ["origin_livestock_id"], unique=False)

    op.create_foreign_key(
        "fk_livestock_pen_id",
        "livestock",
        "livestock_pens",
        ["pen_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_livestock_origin_livestock_id",
        "livestock",
        "livestock",
        ["origin_livestock_id"],
        ["id"],
    )

    op.execute(
        """
        INSERT INTO dbo.livestock_pens (name, status, is_archived)
        SELECT DISTINCT LTRIM(RTRIM(pen_location)), 'Active', 0
        FROM dbo.livestock
        WHERE pen_location IS NOT NULL
          AND LTRIM(RTRIM(pen_location)) <> ''
        """
    )
    op.execute(
        """
        UPDATE l
        SET l.pen_id = p.id
        FROM dbo.livestock AS l
        INNER JOIN dbo.livestock_pens AS p
            ON LTRIM(RTRIM(l.pen_location)) = p.name
        """
    )
    op.execute(
        """
        UPDATE dbo.livestock
        SET record_type = CASE WHEN quantity = 1 THEN 'Individual' ELSE 'Batch' END,
            lifecycle_status = 'Active'
        """
    )

    op.create_table(
        "livestock_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("from_livestock_id", sa.Integer(), nullable=True),
        sa.Column("to_livestock_id", sa.Integer(), nullable=True),
        sa.Column("from_pen_id", sa.Integer(), nullable=True),
        sa.Column("to_pen_id", sa.Integer(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["from_livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["to_livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(["from_pen_id"], ["livestock_pens.id"]),
        sa.ForeignKeyConstraint(["to_pen_id"], ["livestock_pens.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_livestock_transactions_livestock_id"), "livestock_transactions", ["livestock_id"], unique=False)
    op.create_index(op.f("ix_livestock_transactions_transaction_type"), "livestock_transactions", ["transaction_type"], unique=False)
    op.create_index(op.f("ix_livestock_transactions_event_date"), "livestock_transactions", ["event_date"], unique=False)
    op.create_index(op.f("ix_livestock_transactions_from_livestock_id"), "livestock_transactions", ["from_livestock_id"], unique=False)
    op.create_index(op.f("ix_livestock_transactions_to_livestock_id"), "livestock_transactions", ["to_livestock_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_livestock_transactions_to_livestock_id"), table_name="livestock_transactions")
    op.drop_index(op.f("ix_livestock_transactions_from_livestock_id"), table_name="livestock_transactions")
    op.drop_index(op.f("ix_livestock_transactions_event_date"), table_name="livestock_transactions")
    op.drop_index(op.f("ix_livestock_transactions_transaction_type"), table_name="livestock_transactions")
    op.drop_index(op.f("ix_livestock_transactions_livestock_id"), table_name="livestock_transactions")
    op.drop_table("livestock_transactions")

    op.drop_constraint("fk_livestock_origin_livestock_id", "livestock", type_="foreignkey")
    op.drop_constraint("fk_livestock_pen_id", "livestock", type_="foreignkey")
    op.drop_index(op.f("ix_livestock_origin_livestock_id"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_pen_id"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_lifecycle_status"), table_name="livestock")
    op.drop_index(op.f("ix_livestock_record_type"), table_name="livestock")
    op.drop_column("livestock", "origin_livestock_id")
    op.drop_column("livestock", "pen_id")
    op.drop_column("livestock", "lifecycle_status")
    op.drop_column("livestock", "record_type")

    op.drop_index(op.f("ix_livestock_pens_is_archived"), table_name="livestock_pens")
    op.drop_index(op.f("ix_livestock_pens_status"), table_name="livestock_pens")
    op.drop_index(op.f("ix_livestock_pens_name"), table_name="livestock_pens")
    op.drop_table("livestock_pens")
