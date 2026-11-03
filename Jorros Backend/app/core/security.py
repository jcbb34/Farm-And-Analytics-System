from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hasher.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(
    user_id: int,
    auth_version: int = 0,
) -> tuple[str, int]:
    expire_minutes = (
        settings.jwt_access_token_expire_minutes
    )

    expires_at = datetime.now(
        timezone.utc
    ) + timedelta(
        minutes=expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "ver": int(auth_version),
        "purpose": "access",
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return token, expire_minutes * 60


def create_two_factor_challenge(
    user_id: int,
    auth_version: int = 0,
    expire_minutes: int = 5,
) -> tuple[str, int]:
    expires_at = datetime.now(
        timezone.utc
    ) + timedelta(
        minutes=expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "purpose": "two_factor_login",
        "ver": int(auth_version),
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return token, expire_minutes * 60


def decode_two_factor_challenge(
    token: str,
) -> tuple[int, int] | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[
                settings.jwt_algorithm
            ],
        )

        if payload.get("purpose") != "two_factor_login":
            return None

        subject = payload.get("sub")

        if subject is None:
            return None

        return int(subject), int(payload.get("ver", 0))

    except (
        InvalidTokenError,
        ValueError,
        TypeError,
    ):
        return None


def decode_access_token_claims(
    token: str,
) -> tuple[int, int] | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        # Older access tokens had no purpose claim. Keep those sessions valid,
        # but never allow a signed login challenge to authorize API requests.
        if payload.get("purpose", "access") != "access":
            return None
        subject = payload.get("sub")
        if subject is None:
            return None
        return int(subject), int(payload.get("ver", 0))
    except (InvalidTokenError, ValueError, TypeError):
        return None


def decode_access_token(
    token: str,
) -> int | None:
    claims = decode_access_token_claims(token)
    return claims[0] if claims is not None else None
