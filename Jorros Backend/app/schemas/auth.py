from app.schemas.personal_details import PersonalDetails
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str
    otp_code: str | None = Field(default=None, min_length=6, max_length=8)


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True
    )


class UserResponse(BaseModel):
    personal_details: PersonalDetails | None = None
    id: int
    user_code: str
    full_name: str
    username: str
    email: str | None
    contact_number: str | None
    position: str | None
    status: str
    role: RoleResponse
    permissions: list[str] = Field(default_factory=list)
    two_factor_enabled: bool = False

    model_config = ConfigDict(
        from_attributes=True
    )


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse




class TwoFactorLoginChallengeResponse(BaseModel):
    requires_two_factor: bool = True
    challenge_token: str
    challenge_expires_in: int
    username: str


class TwoFactorLoginRequest(BaseModel):
    challenge_token: str = Field(min_length=1)
    otp_code: str = Field(min_length=6, max_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code_data_url: str


class TwoFactorVerifyRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=8)


class TwoFactorDisableRequest(BaseModel):
    current_password: str = Field(min_length=1)
    otp_code: str = Field(min_length=6, max_length=8)


class LoginHistoryResponse(BaseModel):
    id: int
    success: bool
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
