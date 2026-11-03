"""add smart data import history and row audit

Revision ID: f9d2b7c84a10
Revises: e8c4f1a62b91
Create Date: 2026-08-12 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9d2b7c84a10"
down_revision: Union[str, Sequence[str], None] = "e8c4f1a62b91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_import_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_code", sa.String(length=40), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=700), nullable=False),
        sa.Column("file_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'Previewed'"), nullable=False),
        sa.Column("sheet_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("detected_types_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("valid_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("imported_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("imported_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rollback_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["rollback_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_data_import_batches_batch_code", "data_import_batches", ["batch_code"], unique=True)
    op.create_index("ix_data_import_batches_file_hash_sha256", "data_import_batches", ["file_hash_sha256"], unique=False)
    op.create_index("ix_data_import_batches_file_type", "data_import_batches", ["file_type"], unique=False)
    op.create_index("ix_data_import_batches_status", "data_import_batches", ["status"], unique=False)
    op.create_index("ix_data_import_batches_imported_by_user_id", "data_import_batches", ["imported_by_user_id"], unique=False)
    op.create_index("ix_data_import_batches_created_at", "data_import_batches", ["created_at"], unique=False)
    op.create_index("ix_data_import_batches_completed_at", "data_import_batches", ["completed_at"], unique=False)
    op.create_index("ix_data_import_batches_rolled_back_at", "data_import_batches", ["rolled_back_at"], unique=False)

    op.create_table(
        "data_import_rows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=150), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("detected_type", sa.String(length=60), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("confidence", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("mapping_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("mapped_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("validation_errors_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("warnings_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("duplicate_status", sa.String(length=30), server_default=sa.text("'New'"), nullable=False),
        sa.Column("existing_record_id", sa.Integer(), nullable=True),
        sa.Column("generated_code", sa.String(length=40), nullable=True),
        sa.Column("requested_action", sa.String(length=20), server_default=sa.text("'skip'"), nullable=False),
        sa.Column("result_record_id", sa.Integer(), nullable=True),
        sa.Column("result_metadata_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("before_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("after_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'Ready'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["data_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_data_import_rows_import_batch_id", "data_import_rows", ["import_batch_id"], unique=False)
    op.create_index("ix_data_import_rows_sheet_name", "data_import_rows", ["sheet_name"], unique=False)
    op.create_index("ix_data_import_rows_detected_type", "data_import_rows", ["detected_type"], unique=False)
    op.create_index("ix_data_import_rows_target_type", "data_import_rows", ["target_type"], unique=False)
    op.create_index("ix_data_import_rows_duplicate_status", "data_import_rows", ["duplicate_status"], unique=False)
    op.create_index("ix_data_import_rows_status", "data_import_rows", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_data_import_rows_status", table_name="data_import_rows")
    op.drop_index("ix_data_import_rows_duplicate_status", table_name="data_import_rows")
    op.drop_index("ix_data_import_rows_target_type", table_name="data_import_rows")
    op.drop_index("ix_data_import_rows_detected_type", table_name="data_import_rows")
    op.drop_index("ix_data_import_rows_sheet_name", table_name="data_import_rows")
    op.drop_index("ix_data_import_rows_import_batch_id", table_name="data_import_rows")
    op.drop_table("data_import_rows")

    op.drop_index("ix_data_import_batches_rolled_back_at", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_completed_at", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_created_at", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_imported_by_user_id", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_status", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_file_type", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_file_hash_sha256", table_name="data_import_batches")
    op.drop_index("ix_data_import_batches_batch_code", table_name="data_import_batches")
    op.drop_table("data_import_batches")
