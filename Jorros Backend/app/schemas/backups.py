from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
)


class BackupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    backup_code: str
    filename: str
    format_version: str
    status: str
    file_size_bytes: int
    table_count: int
    row_count: int
    checksum_sha256: str | None = None
    notes: str | None = None
    created_by_user_id: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
    recovery_available: bool = False
    recovery_file_size_bytes: int = 0
