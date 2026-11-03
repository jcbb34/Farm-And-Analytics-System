from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FarmCreationCommand
from app.services.db_concurrency import acquire_transaction_lock


def request_fingerprint(payload: BaseModel) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_idempotency_key(value: str | None) -> str | None:
    key = str(value or "").strip()
    if not key:
        return None
    if len(key) > 100:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 100 characters or fewer.")
    return key


def begin_creation_command(
    db: Session,
    *,
    idempotency_key: str | None,
    command_type: str,
    request_hash: str,
    user_id: int | None,
) -> FarmCreationCommand | None:
    """Lock and return an existing command when this is a retry."""
    key = normalize_idempotency_key(idempotency_key)
    if key is None:
        return None

    acquire_transaction_lock(db, f"farm-create:{key}")
    existing = db.scalar(
        select(FarmCreationCommand).where(FarmCreationCommand.idempotency_key == key)
    )
    if existing is None:
        return None
    if existing.command_type != command_type or existing.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="This Idempotency-Key was already used for a different create request.",
        )
    if existing.created_by_user_id != user_id:
        raise HTTPException(
            status_code=409,
            detail="This Idempotency-Key belongs to a different create request.",
        )
    return existing


def record_creation_command(
    db: Session,
    *,
    idempotency_key: str | None,
    command_type: str,
    request_hash: str,
    target_id: int,
    user_id: int | None,
) -> FarmCreationCommand | None:
    key = normalize_idempotency_key(idempotency_key)
    if key is None:
        return None
    command = FarmCreationCommand(
        idempotency_key=key,
        command_type=command_type,
        request_hash=request_hash,
        target_id=int(target_id),
        created_by_user_id=user_id,
    )
    db.add(command)
    db.flush()
    return command
