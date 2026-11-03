from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditLogCreate(BaseModel):
    event_type: str = Field(default="audit", pattern="^(audit|timeline)$")
    action: str = Field(min_length=1, max_length=180)
    module: str = Field(default="System", max_length=60)
    record_name: str | None = Field(default=None, max_length=180)
    entity_id: str | None = Field(default=None, max_length=80)
    details: str | None = None
    icon: str | None = Field(default=None, max_length=50)


class AuditLogResponse(BaseModel):
    id: int
    event_type: str
    action: str
    module: str
    record_name: str | None
    entity_id: str | None
    details: str | None
    icon: str | None
    actor_user_id: int | None
    actor_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
