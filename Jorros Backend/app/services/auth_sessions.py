"""Idle leases use the existing account-session columns; reads never renew them."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, or_, update

from app.core.session_policy import IDLE_TIMEOUT_SECONDS, WARNING_SECONDS, epoch, utc_now
from app.models import User


def invalid_session(message="Your session expired. Please sign in again."):
    return HTTPException(401, message, headers={"X-Session-Expired": "true"})


def check_session(db, user, claims):
    now = utc_now()
    absolute = datetime.fromtimestamp(claims["exp"], timezone.utc).replace(tzinfo=None)
    issued = datetime.fromtimestamp(claims["iat"], timezone.utc).replace(tzinfo=None)
    if now >= absolute:
        raise invalid_session()
    version = int(claims.get("ver", 0))
    if user.active_session_expires_at is None or user.active_session_expires_at > now + timedelta(seconds=IDLE_TIMEOUT_SECONDS + 5):
        # Trusted internal token issuers can bootstrap a lease once. Its first
        # deadline is anchored to issuance, never to a later polling request.
        deadline = min(issued + timedelta(seconds=IDLE_TIMEOUT_SECONDS), absolute)
        if deadline <= now:
            raise invalid_session()
        db.execute(update(User).where(
            User.id == user.id, User.auth_version == version,
            or_(User.active_session_expires_at.is_(None), User.active_session_expires_at > now + timedelta(seconds=IDLE_TIMEOUT_SECONDS + 5)),
        ).values(active_session_auth_version=version, active_session_expires_at=deadline)
          .execution_options(synchronize_session=False))
        db.commit()
        db.refresh(user)
    if (user.active_session_auth_version != version or user.auth_version != version
            or user.active_session_expires_at is None or user.active_session_expires_at <= now):
        raise invalid_session()
    user._session_absolute_deadline = absolute
    user._session_epoch = claims.get("epoch", "0")
    return absolute


def session_status(user):
    absolute = user._session_absolute_deadline
    return {
        "session_id": f"{user.id}:{user.auth_version}:{getattr(user, '_session_epoch', '0')}",
        "server_time": epoch(utc_now()),
        "idle_expires_at": epoch(min(user.active_session_expires_at, absolute)),
        "absolute_expires_at": epoch(absolute),
        "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
        "warning_seconds": WARNING_SECONDS,
    }


def renew_session(db, user):
    now = utc_now()
    deadline = min(now + timedelta(seconds=IDLE_TIMEOUT_SECONDS), user._session_absolute_deadline)
    # Compare the current version and live lease in SQL. A late heartbeat must
    # neither revive an expired session nor modify a newer login's lease.
    result = db.execute(update(User).where(
        User.id == user.id, User.status == "Active", User.auth_version == user.auth_version,
        User.active_session_auth_version == user.auth_version,
        User.active_session_expires_at > now,
    ).values(active_session_expires_at=case(
        (User.active_session_expires_at > user._session_absolute_deadline, user._session_absolute_deadline),
        (User.active_session_expires_at < deadline, deadline),
        else_=User.active_session_expires_at,
    )).execution_options(synchronize_session=False))
    if result.rowcount != 1 or deadline <= now:
        db.rollback()
        raise invalid_session()
    db.commit()
    db.refresh(user)
    return session_status(user)
