from app.schemas.personal_details import PersonalDetailsPayload, PersonalDetailsCreationPayload
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(PersonalDetailsCreationPayload):
    full_name: str = Field(
        min_length=2,
        max_length=120,
    )

    username: str = Field(
        min_length=3,
        max_length=50,
    )

    email: EmailStr | None = None

    contact_number: str | None = Field(
        default=None,
        max_length=20,
    )

    position: str | None = Field(
        default=None,
        max_length=100,
    )

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    role_name: str = Field(
        min_length=2,
        max_length=50,
    )


class UserUpdate(PersonalDetailsPayload):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
    )

    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=50,
    )

    email: EmailStr | None = None

    contact_number: str | None = Field(
        default=None,
        max_length=20,
    )

    position: str | None = Field(
        default=None,
        max_length=100,
    )

    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
    )

    role_name: str | None = Field(
        default=None,
        max_length=50,
    )

    status: str | None = Field(
        default=None,
        max_length=20,
    )


    @field_validator(
        "full_name", "username", "password", "role_name", "status",
        mode="after",
    )
    @classmethod
    def required_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value

class UserProfileUpdate(PersonalDetailsPayload):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
    )

    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=50,
    )

    email: EmailStr | None = None

    contact_number: str | None = Field(
        default=None,
        max_length=20,
    )

    position: str | None = Field(
        default=None,
        max_length=100,
    )

    @field_validator("full_name", "username", mode="after")
    @classmethod
    def required_profile_updates_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value
