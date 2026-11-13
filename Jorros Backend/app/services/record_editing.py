"""Reject stale form snapshots before applying changes; ORM versions close save races."""
from fastapi import HTTPException

CONFLICT_MESSAGE = "This record changed after you opened it. Your edits have been kept. Reload the latest record and review your changes before saving."


def check_edit_version(record, expected_version):
    if expected_version is None:
        raise HTTPException(
            status_code=428,
            detail="Reload the latest record before saving edits. The record version is required.",
            headers={"X-Record-Conflict": "RECORD_VERSION_REQUIRED"},
        )
    if expected_version != record.edit_version:
        raise HTTPException(
            status_code=409,
            detail=CONFLICT_MESSAGE,
            headers={"X-Record-Conflict": "RECORD_CONFLICT"},
        )
