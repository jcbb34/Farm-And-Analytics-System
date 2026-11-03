from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pyotp
import qrcode
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import (
    Session,
    joinedload,
)

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_two_factor_challenge,
    decode_access_token,
    decode_access_token_claims,
    decode_two_factor_challenge,
    hash_password,
    verify_password,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.models import (
    LoginHistory,
    User,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    LoginHistoryResponse,
    TwoFactorDisableRequest,
    TwoFactorLoginChallengeResponse,
    TwoFactorLoginRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
    UserResponse,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


bearer_scheme = HTTPBearer(
    auto_error=False
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    token_claims = decode_access_token_claims(
        credentials.credentials
    )

    if token_claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user_id, token_auth_version = token_claims

    statement = (
        select(User)
        .options(
            joinedload(User.role)
        )
        .where(
            User.id == user_id
        )
    )

    user = db.scalar(statement)

    if (
        user is None
        or user.status != "Active"
        or user.role is None
        or not user.role.is_active
        or int(user.auth_version or 0) != int(token_auth_version)
        or (
            user.active_session_expires_at is not None
            and (
                user.active_session_expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)
                or user.active_session_auth_version != token_auth_version
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account or session is unavailable.",
        )

    return user




def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _enforce_login_rate_limit(
    db: Session,
    *,
    username: str,
    request: Request,
) -> None:
    if not settings.login_rate_limit_enabled:
        return

    maximum = max(int(settings.login_max_failed_attempts or 0), 1)
    window_minutes = max(int(settings.login_failure_window_minutes or 0), 1)
    ip_address = _client_ip(request)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=window_minutes
    )

    conditions = [
        LoginHistory.username == username,
        LoginHistory.created_at >= cutoff,
    ]
    if ip_address is None:
        conditions.append(LoginHistory.ip_address.is_(None))
    else:
        conditions.append(LoginHistory.ip_address == ip_address)

    latest_success = db.scalar(
        select(func.max(LoginHistory.created_at)).where(
            *conditions,
            LoginHistory.success == True,
        )
    )

    failure_conditions = list(conditions)
    if latest_success is not None:
        failure_conditions.append(LoginHistory.created_at > latest_success)

    failed_attempts = int(
        db.scalar(
            select(func.count(LoginHistory.id)).where(
                *failure_conditions,
                LoginHistory.success == False,
            )
        )
        or 0
    )

    if failed_attempts >= maximum:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many failed sign-in attempts from this device. "
                f"Try again after {window_minutes} minutes."
            ),
            headers={"Retry-After": str(window_minutes * 60)},
        )


def _record_login(
    db: Session,
    *,
    user: User | None,
    username: str,
    success: bool,
    request: Request,
) -> None:
    db.add(
        LoginHistory(
            user_id=user.id if user else None,
            username=username,
            success=success,
            ip_address=_client_ip(request),
            user_agent=request.headers.get(
                "user-agent"
            ),
        )
    )


def _has_active_session(user: User) -> bool:
    return (
        user.active_session_expires_at is not None
        and user.active_session_expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
        and user.active_session_auth_version == user.auth_version
    )


def _claim_login_session(db: Session, user: User) -> None:
    """Claim this account atomically, even when API requests reach different workers."""
    acquire_transaction_lock(db, f"auth:login:{user.id}")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    result = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.status == "Active",
            or_(
                User.active_session_expires_at.is_(None),
                User.active_session_expires_at <= now,
                User.active_session_auth_version != User.auth_version,
            ),
        )
        .values(
            auth_version=User.auth_version + 1,
            active_session_auth_version=User.auth_version + 1,
            active_session_expires_at=expires_at,
            last_login=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Someone is already using this account. Ask them to log out "
                "or wait for their session to expire."
            ),
        )
    db.refresh(user)


def _verify_totp(user: User, otp_code: str | None) -> bool:
    if not user.two_factor_enabled:
        return True

    if not user.two_factor_secret or not otp_code:
        return False

    return pyotp.TOTP(
        user.two_factor_secret
    ).verify(
        str(otp_code).strip(),
        valid_window=1,
    )


@router.post(
    "/login",
    response_model=(
        LoginResponse
        | TwoFactorLoginChallengeResponse
    ),
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    username = payload.username.strip().lower()
    _enforce_login_rate_limit(
        db,
        username=username,
        request=request,
    )

    statement = (
        select(User)
        .options(
            joinedload(User.role)
        )
        .where(
            User.username == username
        )
    )

    user = db.scalar(statement)

    valid_password = (
        user is not None
        and verify_password(
            payload.password,
            user.password_hash,
        )
    )

    if not valid_password:
        _record_login(
            db,
            user=user,
            username=username,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
        )

    if user.status != "Active":
        _record_login(
            db,
            user=user,
            username=username,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active.",
        )

    if user.role is None or not user.role.is_active:
        _record_login(
            db,
            user=user,
            username=username,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The assigned user role is inactive.",
        )

    if _has_active_session(user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Someone is already using this account. Ask them to log out or wait for their session to expire.",
        )

    # Password verification precedes the short-lived authenticator challenge.
    if user.two_factor_enabled and not payload.otp_code:
        challenge_token, challenge_expires_in = (
            create_two_factor_challenge(user.id, user.auth_version)
        )

        return TwoFactorLoginChallengeResponse(
            challenge_token=challenge_token,
            challenge_expires_in=challenge_expires_in,
            username=user.username,
        )

    # Accept an authenticator code included with the password request.
    if not _verify_totp(user, payload.otp_code):
        _record_login(
            db,
            user=user,
            username=username,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication code is invalid or expired.",
        )

    _claim_login_session(db, user)
    _record_login(
        db,
        user=user,
        username=username,
        success=True,
        request=request,
    )

    access_token, expires_in = (
        create_access_token(user.id, user.auth_version)
    )

    db.commit()
    db.refresh(user)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        user=user,
    )


@router.post(
    "/login/2fa",
    response_model=LoginResponse,
)
def verify_login_two_factor(
    payload: TwoFactorLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    challenge_claims = decode_two_factor_challenge(
        payload.challenge_token
    )

    if challenge_claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "The sign-in verification session expired. "
                "Return to login and enter your username and password again."
            ),
        )

    user_id, challenge_auth_version = challenge_claims

    statement = (
        select(User)
        .options(
            joinedload(User.role)
        )
        .where(
            User.id == user_id
        )
    )

    user = db.scalar(statement)

    if (
        user is None
        or user.status != "Active"
        or user.role is None
        or not user.role.is_active
        or int(user.auth_version or 0) != int(challenge_auth_version)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account or role is unavailable.",
        )


    if not user.two_factor_enabled or not user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Two-factor authentication is no longer enabled for this account. "
                "Return to login and try again."
            ),
        )

    _enforce_login_rate_limit(
        db,
        username=user.username.strip().lower(),
        request=request,
    )

    if not _verify_totp(user, payload.otp_code):
        _record_login(
            db,
            user=user,
            username=user.username,
            success=False,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication code is invalid or expired.",
        )

    _claim_login_session(db, user)
    _record_login(
        db,
        user=user,
        username=user.username,
        success=True,
        request=request,
    )

    access_token, expires_in = (
        create_access_token(user.id, user.auth_version)
    )

    db.commit()
    db.refresh(user)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        user=user,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(
        get_current_user
    ),
):
    return current_user




@router.get(
    "/me/login-history",
    response_model=list[LoginHistoryResponse],
)
def get_my_login_history(
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list(
        db.scalars(
            select(LoginHistory)
            .where(LoginHistory.user_id == current_user.id)
            .order_by(LoginHistory.created_at.desc(), LoginHistory.id.desc())
            .limit(limit)
        ).all()
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(
        payload.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect.",
        )

    if verify_password(
        payload.new_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different from the current password.",
        )

    current_user.password_hash = hash_password(
        payload.new_password
    )
    current_user.auth_version = int(current_user.auth_version or 0) + 1
    current_user.active_session_auth_version = None
    current_user.active_session_expires_at = None
    db.commit()

    return {
        "success": True,
        "reauthenticate": True,
        "message": "Password changed successfully. Sign in again with the new password.",
    }


@router.post(
    "/2fa/setup",
    response_model=TwoFactorSetupResponse,
)
def setup_two_factor(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled.",
        )

    secret = pyotp.random_base32()
    current_user.two_factor_secret = secret
    db.commit()

    issuer = "JoRoss Farm"
    account_name = current_user.email or current_user.username
    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(
        name=account_name,
        issuer_name=issuer,
    )

    image = qrcode.make(otpauth_uri)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    qr_data_url = (
        "data:image/png;base64," +
        base64.b64encode(buffer.getvalue()).decode("ascii")
    )

    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=otpauth_uri,
        qr_code_data_url=qr_data_url,
    )


@router.post("/2fa/enable")
def enable_two_factor(
    payload: TwoFactorVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start two-factor setup before enabling it.",
        )

    verified = pyotp.TOTP(
        current_user.two_factor_secret
    ).verify(
        payload.otp_code.strip(),
        valid_window=1,
    )

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The authentication code is invalid or expired.",
        )

    current_user.two_factor_enabled = True
    # Security-setting changes revoke previously issued access tokens so
    # the next session must pass the newly enabled second factor.
    current_user.auth_version = int(current_user.auth_version or 0) + 1
    db.commit()

    return {
        "success": True,
        "two_factor_enabled": True,
        "reauthenticate": True,
        "message": "Two-factor authentication enabled. Sign in again to continue.",
    }


@router.post("/2fa/disable")
def disable_two_factor(
    payload: TwoFactorDisableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.two_factor_enabled:
        return {
            "success": True,
            "two_factor_enabled": False,
            "message": "Two-factor authentication is already disabled.",
        }

    if not verify_password(
        payload.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect.",
        )

    if not _verify_totp(current_user, payload.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The authentication code is invalid or expired.",
        )

    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    current_user.auth_version = int(current_user.auth_version or 0) + 1
    db.commit()

    return {
        "success": True,
        "two_factor_enabled": False,
        "reauthenticate": True,
        "message": "Two-factor authentication disabled. Sign in again to continue.",
    }


@router.post("/logout")
def logout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.auth_version = int(current_user.auth_version or 0) + 1
    db.commit()
    return {
        "success": True,
        "message": "Logout successful. The current access token has been revoked.",
    }
