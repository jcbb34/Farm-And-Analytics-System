"""sales processing payment accuracy

Revision ID: h2e7a1c4d930
Revises: g1c4e8a2d590
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h2e7a1c4d930"
down_revision: Union[str, Sequence[str], None] = "g1c4e8a2d590"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "livestock_production_records",
        "quantity",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(12, 3),
        existing_nullable=False,
    )

    op.add_column(
        "livestock_production_records",
        sa.Column("period_start_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "livestock_production_records",
        sa.Column("period_end_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "livestock_production_records",
        sa.Column("source_head_quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "livestock_production_records",
        sa.Column("source_female_quantity", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_livestock_production_records_period_start_date",
        "livestock_production_records",
        ["period_start_date"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_production_records_period_end_date",
        "livestock_production_records",
        ["period_end_date"],
        unique=False,
    )

    op.add_column(
        "livestock_sales",
        sa.Column(
            "amount_paid",
            sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "livestock_sales",
        sa.Column(
            "balance_due",
            sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # Existing completed sales can be backfilled safely. For historical Partial
    # rows there is no reliable paid-amount source in the old schema, so they
    # retain amount_paid=0 and the full transaction amount as balance_due.
    op.execute(
        """
        UPDATE livestock_sales
        SET amount_paid = CASE
                WHEN LOWER(LTRIM(RTRIM(payment_status))) = 'paid' THEN total_amount
                ELSE 0
            END,
            balance_due = CASE
                WHEN LOWER(LTRIM(RTRIM(payment_status))) = 'paid' THEN 0
                ELSE total_amount
            END
        """
    )

    op.create_table(
        "livestock_sale_payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["livestock_sales.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_livestock_sale_payments_sale_id",
        "livestock_sale_payments",
        ["sale_id"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_sale_payments_payment_date",
        "livestock_sale_payments",
        ["payment_date"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_sale_payments_created_at",
        "livestock_sale_payments",
        ["created_at"],
        unique=False,
    )

    # Preserve historical fully-paid sales in collection analytics. The previous
    # schema stored the paid status but had no separate payment ledger.
    op.execute(
        """
        INSERT INTO livestock_sale_payments
            (sale_id, payment_date, amount, payment_method, notes, recorded_by_user_id)
        SELECT
            id,
            sale_date,
            amount_paid,
            payment_method,
            'Historical initial payment backfilled during sales payment upgrade.',
            recorded_by_user_id
        FROM livestock_sales
        WHERE is_voided = 0
          AND amount_paid > 0
        """
    )

    op.create_table(
        "livestock_processing_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livestock_id", sa.Integer(), nullable=False),
        sa.Column("production_record_id", sa.Integer(), nullable=False),
        sa.Column("processing_date", sa.Date(), nullable=False),
        sa.Column("animals_processed", sa.Integer(), nullable=False),
        sa.Column("male_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("female_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unknown_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("healthy_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("live_weight_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column("meat_output_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("quality_grade", sa.String(length=80), nullable=True),
        sa.Column("destination", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["livestock_id"], ["livestock.id"]),
        sa.ForeignKeyConstraint(
            ["production_record_id"], ["livestock_production_records.id"]
        ),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("production_record_id"),
    )
    op.create_index(
        "ix_livestock_processing_records_livestock_id",
        "livestock_processing_records",
        ["livestock_id"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_processing_records_production_record_id",
        "livestock_processing_records",
        ["production_record_id"],
        unique=True,
    )
    op.create_index(
        "ix_livestock_processing_records_processing_date",
        "livestock_processing_records",
        ["processing_date"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_processing_records_is_voided",
        "livestock_processing_records",
        ["is_voided"],
        unique=False,
    )
    op.create_index(
        "ix_livestock_processing_records_created_at",
        "livestock_processing_records",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("livestock_processing_records")
    op.drop_table("livestock_sale_payments")

    op.drop_column("livestock_sales", "balance_due")
    op.drop_column("livestock_sales", "amount_paid")

    op.drop_index(
        "ix_livestock_production_records_period_end_date",
        table_name="livestock_production_records",
    )
    op.drop_index(
        "ix_livestock_production_records_period_start_date",
        table_name="livestock_production_records",
    )
    op.drop_column("livestock_production_records", "source_female_quantity")
    op.drop_column("livestock_production_records", "source_head_quantity")
    op.drop_column("livestock_production_records", "period_end_date")
    op.drop_column("livestock_production_records", "period_start_date")
    op.alter_column(
        "livestock_production_records",
        "quantity",
        existing_type=sa.Numeric(12, 3),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )
