"""Optional refresh contention must not crash requests or roll back real work."""

from datetime import time
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from test_calendar_event_creation import events, farm
from app.core.exception_handlers import database_lock_busy_handler
from app.models import Crop, FarmActivity
from app.services import db_concurrency, task_engine, farm_automation_scheduler


@pytest.mark.parametrize("result", [-1, -2, -3])
def test_expected_lock_conflicts_are_retryable_but_never_grant_a_lock(
    monkeypatch, result
):
    monkeypatch.setattr(
        db_concurrency, "_transaction_lock_result", lambda *args, **kwargs: result
    )
    with pytest.raises(db_concurrency.DatabaseLockBusy):
        db_concurrency.acquire_transaction_lock(None, "automation:tasks")
    assert (
        db_concurrency.try_acquire_transaction_lock(
            None, "automation:tasks", timeout_ms=0
        )
        is False
    )


def test_invalid_lock_configuration_is_still_an_error(monkeypatch):
    monkeypatch.setattr(
        db_concurrency, "_transaction_lock_result", lambda *args, **kwargs: -999
    )
    with pytest.raises(RuntimeError):
        db_concurrency.try_acquire_transaction_lock(None, "automation:tasks")


def test_busy_refresh_returns_immediately_and_preserves_pending_transaction(
    events, monkeypatch
):
    lock = Mock(return_value=False)
    monkeypatch.setattr(task_engine, "try_acquire_transaction_lock", lock)
    with Session(events.engine) as db:
        crop = db.get(Crop, events.ids["Crop"])
        crop.name = "Synthetic pending edit"
        commit, rollback = Mock(wraps=db.commit), Mock(wraps=db.rollback)
        monkeypatch.setattr(db, "commit", commit)
        monkeypatch.setattr(db, "rollback", rollback)
        result = task_engine.evaluate_automatic_tasks(
            db, commit=False, skip_if_busy=True
        )
        assert result["skipped"] == 1
        assert db.is_modified(crop) and crop.name == "Synthetic pending edit"
        commit.assert_not_called()
        rollback.assert_not_called()
        assert lock.call_args.kwargs["timeout_ms"] == 0


def test_evaluate_api_reports_busy_without_500_and_keeps_reads_available(
    events, monkeypatch
):
    monkeypatch.setattr(
        task_engine, "try_acquire_transaction_lock", lambda *args, **kwargs: False
    )
    response = events.client.post(
        "/api/v1/activities/evaluate", headers=events.headers["manager"]
    )
    assert response.status_code == 200 and response.json()["skipped"] == 1
    assert (
        events.client.get(
            "/api/v1/activities", headers=events.headers["manager"]
        ).status_code
        == 200
    )


def test_required_mutation_lock_conflict_is_503_with_retry_guidance():
    app = FastAPI()
    app.add_exception_handler(
        db_concurrency.DatabaseLockBusy, database_lock_busy_handler
    )

    @app.post("/save")
    def save():
        raise db_concurrency.DatabaseLockBusy("automation:tasks", -1)

    response = TestClient(app).post("/save")
    assert response.status_code == 503 and response.json()["code"] == "DATABASE_BUSY"
    assert response.headers["Retry-After"] == "2"


def test_scheduler_busy_pass_is_skipped_without_failure_or_evidence_cleanup(
    events, monkeypatch
):
    monkeypatch.setattr(
        farm_automation_scheduler, "SessionLocal", lambda: Session(events.engine)
    )
    monkeypatch.setattr(
        farm_automation_scheduler,
        "evaluate_automatic_tasks",
        lambda *args, **kwargs: {"skipped": 1},
    )
    cleanup = Mock()
    monkeypatch.setattr(
        farm_automation_scheduler, "cleanup_expired_task_evidence", cleanup
    )
    result = farm_automation_scheduler._run_task_evaluation("synthetic-busy-pass")
    assert result["errors"] == 0 and result["skipped"] == 1
    cleanup.assert_not_called()


def test_unchanged_native_occurrence_is_not_rewritten_every_evaluation(events):
    with Session(events.engine, autoflush=False) as db:
        crop = db.get(Crop, events.ids["Crop"])
        values = dict(
            source_key=f"crop:harvest:{crop.id}:{events.today}",
            source_module="Crop",
            source_type="crop_harvest",
            source_record_id=crop.id,
            source_detail_id=None,
            source_code=crop.crop_code,
            source_path="/crops",
            name="Harvest crop",
            category="Harvesting",
            related_to=crop.name,
            location=crop.field,
            description="Synthetic unchanged occurrence",
            activity_date=events.today,
            start_time=time(7),
            assigned_to="Farm Staff",
            priority="Medium",
        )
        task, result = task_engine._upsert_automatic_task(db, **values)
        assert result == "created"
        db.commit()
        updates = []

        def record(connection, cursor, statement, *args):
            if statement.lstrip().upper().startswith("UPDATE FARM_ACTIVITIES"):
                updates.append(statement)

        event.listen(events.engine, "before_cursor_execute", record)
        try:
            same, result = task_engine._upsert_automatic_task(db, **values)
            assert same.id == task.id and result == "updated"
            db.commit()
            assert updates == []
        finally:
            event.remove(events.engine, "before_cursor_execute", record)
