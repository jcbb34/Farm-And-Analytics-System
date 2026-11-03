from pydantic import BaseModel, Field, field_validator


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = None
    is_active: bool | None = None

    @field_validator("name", "permissions", "is_active", mode="after")
    @classmethod
    def role_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value
