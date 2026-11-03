from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DataImportBatch(Base):
    __tablename__ = "data_import_batches"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    batch_code: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_path: Mapped[str] = mapped_column(
        String(700),
        nullable=False,
    )

    file_hash_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Previewed",
        server_default=text("'Previewed'"),
        index=True,
    )

    sheet_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    detected_types_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default=text("'[]'"),
    )

    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    valid_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    invalid_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    duplicate_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    imported_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    updated_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    skipped_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    error_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    imported_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    rollback_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    rolled_back_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    rows: Mapped[list["DataImportRow"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="DataImportRow.id.asc()",
    )


class DataImportRow(Base):
    __tablename__ = "data_import_rows"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("data_import_batches.id"),
        nullable=False,
        index=True,
    )

    sheet_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    detected_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )

    target_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )

    confidence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    source_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    mapping_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    mapped_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    validation_errors_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default=text("'[]'"),
    )

    warnings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default=text("'[]'"),
    )

    duplicate_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="New",
        server_default=text("'New'"),
        index=True,
    )

    existing_record_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    generated_code: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    requested_action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="skip",
        server_default=text("'skip'"),
    )

    result_record_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    result_metadata_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    before_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    after_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default=text("'{}'"),
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Ready",
        server_default=text("'Ready'"),
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    batch: Mapped["DataImportBatch"] = relationship(
        back_populates="rows"
    )
