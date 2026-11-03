from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ImportAction = Literal["skip", "update", "new"]


class ImportSheetReview(BaseModel):
    sheet_name: str = Field(min_length=1, max_length=150)
    target_type: str = Field(min_length=1, max_length=60)
    include: bool = True
    column_mapping: dict[str, str | None] = Field(default_factory=dict)


class ImportReviewRequest(BaseModel):
    sheets: list[ImportSheetReview]


class ImportCommitRequest(BaseModel):
    row_actions: dict[int, ImportAction] = Field(default_factory=dict)
    force_exact_duplicate: bool = False


class ImportRollbackRequest(BaseModel):
    force: bool = False


class ImportRowResponse(BaseModel):
    id: int
    sheet_name: str
    row_number: int
    detected_type: str
    target_type: str
    confidence: int
    source: dict[str, Any]
    mapping: dict[str, Any]
    mapped: dict[str, Any]
    validation_errors: list[str]
    warnings: list[str]
    duplicate_status: str
    existing_record_id: int | None = None
    generated_code: str | None = None
    requested_action: str
    result_record_id: int | None = None
    status: str
    error_message: str | None = None


class ImportSheetResponse(BaseModel):
    sheet_name: str
    target_type: str
    detected_type: str
    confidence: int
    supported: bool
    included: bool = True
    row_count: int
    source_columns: list[str]
    column_mapping: dict[str, str | None]
    required_fields: list[str]
    optional_fields: list[str]
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    generated_code_rows: int
    rows: list[ImportRowResponse]


class ImportBatchSummary(BaseModel):
    id: int
    batch_code: str
    original_filename: str
    file_hash_sha256: str
    file_size_bytes: int
    file_type: str
    status: str
    sheet_count: int
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    imported_rows: int
    updated_rows: int
    skipped_rows: int
    error_rows: int
    imported_by_user_id: int | None = None
    imported_by_name: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    rolled_back_at: datetime | None = None
    notes: str | None = None
    can_rollback: bool = False


class ImportPreviewResponse(BaseModel):
    already_imported: bool = False
    exact_duplicate_batch: ImportBatchSummary | None = None
    batch: ImportBatchSummary | None = None
    sheets: list[ImportSheetResponse] = Field(default_factory=list)
    field_catalog: dict[str, Any] = Field(default_factory=dict)
    requires_admin: bool = False
    admin_reasons: list[str] = Field(default_factory=list)
    message: str = ""


class ImportCommitResponse(BaseModel):
    batch: ImportBatchSummary
    message: str


class ImportRollbackResponse(BaseModel):
    batch: ImportBatchSummary
    message: str
