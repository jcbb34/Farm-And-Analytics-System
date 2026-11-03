from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.db_concurrency import (
    FARM_AUTOMATION_LEADER_GUARD,
    SMART_IMPORT_AUTOMATION_GUARD,
    acquire_transaction_lock,
    release_session_lock,
    session_lock_is_held,
    try_acquire_session_lock,
    try_acquire_transaction_lock,
)


def test_sqlite_transaction_locks_are_safe_noops():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with Session(engine) as db:
            acquire_transaction_lock(db, "test-resource")
            assert try_acquire_transaction_lock(db, "test-resource", timeout_ms=0) is True
    finally:
        engine.dispose()


def test_smart_import_automation_guard_has_stable_name():
    assert SMART_IMPORT_AUTOMATION_GUARD == "farm:smart-import-vs-automation"


def test_sqlite_session_locks_are_safe_noops():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert try_acquire_session_lock(
                connection,
                FARM_AUTOMATION_LEADER_GUARD,
                timeout_ms=0,
            ) is True
            assert session_lock_is_held(
                connection,
                FARM_AUTOMATION_LEADER_GUARD,
            ) is True
            release_session_lock(connection, FARM_AUTOMATION_LEADER_GUARD)
    finally:
        engine.dispose()


def test_scheduler_leader_guard_has_stable_name():
    assert FARM_AUTOMATION_LEADER_GUARD == "farm:automation-scheduler-leader"
