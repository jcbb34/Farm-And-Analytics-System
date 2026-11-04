"""Exercise maintenance pauses, automatic resumption and real scheduler failures."""

import asyncio
import json
import logging
from unittest.mock import Mock

import pytest

from app.core.config import settings
from app.core.recovery_runtime import guarded_background, write_runtime
from app.services import farm_automation_scheduler as farm
from app.services import report_scheduler as reports


class ControlledStop:
    def __init__(self, after_pause):
        self.stopped = False
        self.waits = []
        self.after_pause = after_pause

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.waits.append(seconds)
        if len(self.waits) == 2:
            self.after_pause()
        if len(self.waits) == 3:
            self.stopped = True
        return self.stopped


@pytest.fixture(autouse=True)
def isolated_control(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_control_dir", str(tmp_path / "control"))
    monkeypatch.setattr(settings, "farm_automation_scheduler_startup_delay_seconds", 0)
    monkeypatch.setattr(settings, "farm_automation_scheduler_interval_seconds", 30)
    monkeypatch.setattr(farm, "_local_health", dict(farm._local_health))


@pytest.fixture
def leader(monkeypatch):
    connection = Mock()
    engine = Mock()
    engine.connect.return_value = connection
    monkeypatch.setattr(farm, "engine", engine)
    monkeypatch.setattr(farm, "try_acquire_session_lock", Mock(return_value=True))
    monkeypatch.setattr(farm, "session_lock_is_held", Mock(return_value=True))
    release = Mock()
    monkeypatch.setattr(farm, "release_session_lock", release)
    return engine, connection, release


def events(caplog):
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.message.startswith('{"')
    ]


def test_farm_worker_skips_maintenance_then_resumes_without_losing_leadership(
    monkeypatch, caplog, leader
):
    write_runtime(maintenance={"operation": "backup"})
    caplog.set_level(logging.INFO, logger=farm.LOGGER.name)
    monkeypatch.setattr(farm, "monotonic", lambda: 0)
    evaluate_tasks = Mock(
        return_value={"generated": 1, "resolved": 0, "errors": 0, "skipped": 0}
    )
    evaluate_alerts = Mock(
        return_value={"generated": 0, "resolved": 0, "errors": 0, "skipped": 0}
    )
    persist = Mock()
    monkeypatch.setattr(farm, "_run_task_evaluation", evaluate_tasks)
    monkeypatch.setattr(farm, "_run_alert_evaluation", evaluate_alerts)
    monkeypatch.setattr(farm, "_persist_run", persist)

    def end_maintenance():
        assert farm._local_health["role"] == "leader"
        evaluate_tasks.assert_not_called()
        evaluate_alerts.assert_not_called()
        persist.assert_not_called()
        write_runtime(maintenance=None)

    stop = ControlledStop(end_maintenance)
    farm._scheduler_worker(stop)

    evaluate_tasks.assert_called_once()
    evaluate_alerts.assert_called_once()
    persist.assert_called_once()
    assert persist.call_args.args[0]["errors"] == 0
    engine, connection, release = leader
    engine.connect.assert_called_once()
    release.assert_called_once_with(connection, farm.FARM_AUTOMATION_LEADER_GUARD)
    connection.close.assert_called_once()
    assert stop.waits == [0, 30, 30]
    assert any(
        item["event"] == "scheduler_cycle_skipped"
        and item["reason"] == "backup_or_recovery_maintenance"
        for item in events(caplog)
    )
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_pruning_paused_between_cycle_and_cleanup_retries_after_maintenance(
    monkeypatch, caplog, leader
):
    caplog.set_level(logging.INFO, logger=farm.LOGGER.name)
    monkeypatch.setattr(farm, "monotonic", lambda: 10000)
    calls = []

    def cycle():
        calls.append("cycle")
        if len(calls) == 1:
            write_runtime(maintenance={"operation": "backup"})

    monkeypatch.setattr(farm, "run_farm_automation_cycle", cycle)
    session = Mock()
    monkeypatch.setattr(farm, "SessionLocal", Mock(return_value=session))
    prune = Mock(return_value=7)
    monkeypatch.setattr(farm, "prune_change_events", prune)
    stop = ControlledStop(lambda: write_runtime(maintenance=None))
    farm._scheduler_worker(stop)

    assert len(calls) == 2
    prune.assert_called_once_with(session)
    session.rollback.assert_called_once()
    assert session.close.call_count == 2
    assert any(item["event"] == "change_event_prune_skipped" for item in events(caplog))
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_real_farm_cycle_failure_remains_an_error(monkeypatch, caplog, leader):
    caplog.set_level(logging.INFO, logger=farm.LOGGER.name)
    monkeypatch.setattr(
        farm,
        "run_farm_automation_cycle",
        Mock(side_effect=RuntimeError("Synthetic failure")),
    )
    stop = ControlledStop(lambda: setattr(stop, "stopped", True))
    farm._scheduler_worker(stop)

    assert any(
        item["event"] == "scheduler_worker_failed"
        and item["error_type"] == "RuntimeError"
        for item in events(caplog)
    )
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    leader[1].close.assert_called_once()


def test_report_worker_skips_maintenance_and_resumes(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=reports.LOGGER.name)
    write_runtime(maintenance={"operation": "backup"})
    generate = Mock(return_value=["RPT-SYNTHETIC"])
    monkeypatch.setattr(
        reports, "_run_report_scheduler_once", guarded_background(generate)
    )
    waits = []

    async def next_iteration(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            generate.assert_not_called()
            write_runtime(maintenance=None)
        elif len(waits) == 3:
            raise asyncio.CancelledError()

    monkeypatch.setattr(reports.asyncio, "sleep", next_iteration)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(reports.report_scheduler_loop())

    generate.assert_called_once()
    assert waits == [5, 60, 60]
    assert any(item["event"] == "report_scheduler_skipped" for item in events(caplog))
    assert any(
        item["event"] == "automatic_reports_generated" for item in events(caplog)
    )
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_real_report_failure_remains_an_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=reports.LOGGER.name)
    monkeypatch.setattr(
        reports,
        "_run_report_scheduler_once",
        Mock(side_effect=RuntimeError("Synthetic failure")),
    )
    waits = []

    async def stop_after_failure(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(reports.asyncio, "sleep", stop_after_failure)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(reports.report_scheduler_loop())

    assert any(
        item["event"] == "report_scheduler_failed"
        and item["error_type"] == "RuntimeError"
        for item in events(caplog)
    )
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
