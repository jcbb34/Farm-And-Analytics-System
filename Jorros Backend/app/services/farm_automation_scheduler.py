from __future__ import annotations
from app.core.recovery_runtime import RecoveryBusy, guarded_background

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import socket
from threading import Event, Lock
from time import monotonic
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models.scheduler_status import SchedulerStatus
from app.services.alert_engine import evaluate_automatic_alerts
from app.services.db_concurrency import (
    FARM_AUTOMATION_LEADER_GUARD,
    SMART_IMPORT_AUTOMATION_GUARD,
    release_session_lock,
    session_lock_is_held,
    try_acquire_session_lock,
    try_acquire_transaction_lock,
)
from app.services.evidence_storage import cleanup_expired_task_evidence
from app.services.change_events import prune_change_events
from app.services.task_engine import evaluate_automatic_tasks


LOGGER = logging.getLogger("joross.scheduler.farm_automation")
SCHEDULER_NAME = "farm-automation"
AUTOMATION_GUARD_TIMEOUT_MS = 100
INSTANCE_ID = (
    settings.farm_automation_scheduler_instance_id.strip()
    or f"{socket.gethostname()}:{os.getpid()}"
)

_cycle_lock = Lock()
_health_lock = Lock()
_local_health = {
    "instance_id": INSTANCE_ID,
    "role": "starting" if settings.farm_automation_scheduler_enabled else "disabled",
    "current_run_id": None,
}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _structured_log(level: int, event: str, **fields) -> None:
    payload = {
        "event": event,
        "scheduler": SCHEDULER_NAME,
        "instance_id": INSTANCE_ID,
        **fields,
    }
    LOGGER.log(level, json.dumps(payload, default=str, sort_keys=True))


def _set_local_health(**fields) -> None:
    with _health_lock:
        _local_health.update(fields)


def _begin_evaluation(db: Session, evaluation: str) -> bool:
    """Acquire second-layer transaction guards for one due evaluation."""

    if not try_acquire_transaction_lock(
        db,
        SMART_IMPORT_AUTOMATION_GUARD,
        timeout_ms=AUTOMATION_GUARD_TIMEOUT_MS,
    ):
        db.rollback()
        return False

    if not try_acquire_transaction_lock(
        db,
        f"farm:automation:{evaluation}",
        timeout_ms=AUTOMATION_GUARD_TIMEOUT_MS,
    ):
        db.rollback()
        return False

    return True


def _run_task_evaluation(run_id: str) -> dict:
    db = SessionLocal()
    started = monotonic()

    try:
        if not _begin_evaluation(db, "tasks"):
            return {"generated": 0, "resolved": 0, "errors": 0, "skipped": 1}

        counters = evaluate_automatic_tasks(db, skip_if_busy=True)
        if counters.get("skipped"):
            _structured_log(logging.INFO, "scheduler_evaluation_skipped", run_id=run_id,
                            evaluation="tasks", reason="task_generation_busy")
            return {"generated": 0, "resolved": 0, "errors": 0, "skipped": 1}
        expired_evidence = cleanup_expired_task_evidence(db)
        result = {
            "generated": int(counters.get("created", 0)),
            "resolved": int(counters.get("completed", 0)) + int(expired_evidence),
            "errors": 0,
            "skipped": 0,
        }
        _structured_log(
            logging.INFO,
            "scheduler_evaluation_completed",
            run_id=run_id,
            evaluation="tasks",
            duration_ms=round((monotonic() - started) * 1000),
            **result,
            task_counts=counters,
            expired_evidence=expired_evidence,
        )
        return result
    except Exception as error:
        db.rollback()
        result = {"generated": 0, "resolved": 0, "errors": 1, "skipped": 0}
        _structured_log(
            logging.ERROR,
            "scheduler_evaluation_failed",
            run_id=run_id,
            evaluation="tasks",
            duration_ms=round((monotonic() - started) * 1000),
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception("Task evaluation traceback")
        return {**result, "error": str(error)}
    finally:
        db.close()


def _run_alert_evaluation(run_id: str) -> dict:
    db = SessionLocal()
    started = monotonic()

    try:
        if not _begin_evaluation(db, "alerts"):
            return {"generated": 0, "resolved": 0, "errors": 0, "skipped": 1}

        metrics = evaluate_automatic_alerts(db, return_metrics=True)
        result = {
            "generated": int(metrics.get("created", 0)),
            "resolved": int(metrics.get("resolved", 0)),
            "errors": 0,
            "skipped": 0,
        }
        _structured_log(
            logging.INFO,
            "scheduler_evaluation_completed",
            run_id=run_id,
            evaluation="alerts",
            duration_ms=round((monotonic() - started) * 1000),
            **result,
            alert_counts=metrics,
        )
        return result
    except Exception as error:
        db.rollback()
        result = {"generated": 0, "resolved": 0, "errors": 1, "skipped": 0}
        _structured_log(
            logging.ERROR,
            "scheduler_evaluation_failed",
            run_id=run_id,
            evaluation="alerts",
            duration_ms=round((monotonic() - started) * 1000),
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception("Alert evaluation traceback")
        return {**result, "error": str(error)}
    finally:
        db.close()


def _persist_run(summary: dict) -> None:
    db = SessionLocal()
    try:
        row = db.get(SchedulerStatus, SCHEDULER_NAME)
        if row is None:
            row = SchedulerStatus(scheduler_name=SCHEDULER_NAME)
            db.add(row)

        row.leader_instance_id = INSTANCE_ID
        row.last_run_id = summary["run_id"]
        row.last_started_at = summary["started_at"]
        row.last_duration_ms = summary["duration_ms"]
        row.generated_count = summary["generated"]
        row.resolved_count = summary["resolved"]
        row.error_count = summary["errors"]
        row.last_error = summary.get("last_error")
        row.updated_at = _utc_now_naive()
        if summary["errors"] == 0:
            row.last_success_at = summary["completed_at"]
        db.commit()
    except Exception as error:
        db.rollback()
        _structured_log(
            logging.ERROR,
            "scheduler_status_persist_failed",
            run_id=summary.get("run_id"),
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception("Scheduler status persistence traceback")
    finally:
        db.close()


@guarded_background
def run_farm_automation_cycle() -> dict:
    """Run one observable, non-overlapping task and alert evaluation cycle."""

    if not _cycle_lock.acquire(blocking=False):
        _structured_log(logging.WARNING, "scheduler_cycle_skipped", reason="already_running")
        return {
            "run_id": None,
            "generated": 0,
            "resolved": 0,
            "errors": 0,
            "skipped": 1,
        }

    run_id = str(uuid4())
    started_at = _utc_now_naive()
    started = monotonic()
    _set_local_health(current_run_id=run_id, role="leader")
    _structured_log(logging.INFO, "scheduler_cycle_started", run_id=run_id)

    try:
        task_result = _run_task_evaluation(run_id)
        alert_result = _run_alert_evaluation(run_id)
        errors = int(task_result["errors"]) + int(alert_result["errors"])
        error_messages = [
            result.get("error")
            for result in (task_result, alert_result)
            if result.get("error")
        ]
        summary = {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": _utc_now_naive(),
            "duration_ms": round((monotonic() - started) * 1000),
            "generated": int(task_result["generated"]) + int(alert_result["generated"]),
            "resolved": int(task_result["resolved"]) + int(alert_result["resolved"]),
            "errors": errors,
            "skipped": int(task_result["skipped"]) + int(alert_result["skipped"]),
            "last_error": "; ".join(error_messages)[:4000] or None,
        }
        _persist_run(summary)
        _structured_log(
            logging.INFO if errors == 0 else logging.ERROR,
            "scheduler_cycle_completed",
            run_id=run_id,
            started_at=started_at.isoformat() + "Z",
            completed_at=summary["completed_at"].isoformat() + "Z",
            duration_ms=summary["duration_ms"],
            generated=summary["generated"],
            resolved=summary["resolved"],
            errors=summary["errors"],
            skipped=summary["skipped"],
            last_error=summary["last_error"],
        )
        return summary
    finally:
        _set_local_health(current_run_id=None)
        _cycle_lock.release()


def scheduler_health(db: Session | None = None) -> dict:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        row = session.get(SchedulerStatus, SCHEDULER_NAME)
    except Exception as error:
        if owns_session:
            session.rollback()
        row = None
        persistence_error = str(error)
    else:
        persistence_error = None
    finally:
        if owns_session:
            session.close()

    with _health_lock:
        local = dict(_local_health)

    now = _utc_now_naive()
    last_success = row.last_success_at if row else None
    age_seconds = (
        max(0, int((now - last_success).total_seconds()))
        if last_success
        else None
    )
    stale_after = max(180, settings.farm_automation_scheduler_interval_seconds * 3)

    if not settings.farm_automation_scheduler_enabled:
        status = "disabled"
    elif persistence_error:
        status = "degraded"
    elif row is None:
        status = "starting" if local["role"] != "standby" else "standby"
    elif row.error_count:
        status = "degraded"
    elif age_seconds is not None and age_seconds > stale_after:
        status = "stale"
    else:
        status = "healthy"

    return {
        "status": status,
        "enabled": settings.farm_automation_scheduler_enabled,
        "scheduler": SCHEDULER_NAME,
        "instance_id": local["instance_id"],
        "instance_role": local["role"],
        "leader_instance_id": row.leader_instance_id if row else None,
        "current_run_id": local["current_run_id"],
        "last_run_id": row.last_run_id if row else None,
        "last_started_at": row.last_started_at if row else None,
        "last_success_at": last_success,
        "last_success_age_seconds": age_seconds,
        "last_duration_ms": row.last_duration_ms if row else None,
        "generated_count": row.generated_count if row else 0,
        "resolved_count": row.resolved_count if row else 0,
        "error_count": row.error_count if row else 0,
        "last_error": row.last_error if row else persistence_error,
        "interval_seconds": settings.farm_automation_scheduler_interval_seconds,
    }


def _scheduler_worker(stop_event: Event) -> None:
    if stop_event.wait(settings.farm_automation_scheduler_startup_delay_seconds):
        return

    interval = max(5, settings.farm_automation_scheduler_interval_seconds)
    last_event_prune = 0.0

    while not stop_event.is_set():
        connection = None
        leader = False
        try:
            connection = engine.connect()
            leader = try_acquire_session_lock(
                connection,
                FARM_AUTOMATION_LEADER_GUARD,
                timeout_ms=0,
            )
            if not leader:
                _set_local_health(role="standby", current_run_id=None)
                if stop_event.wait(interval):
                    return
                continue

            _set_local_health(role="leader")
            _structured_log(logging.INFO, "scheduler_leadership_acquired")

            while not stop_event.is_set():
                if not session_lock_is_held(connection, FARM_AUTOMATION_LEADER_GUARD):
                    _structured_log(logging.WARNING, "scheduler_leadership_lost")
                    break
                try:
                    run_farm_automation_cycle()
                except RecoveryBusy:
                    _structured_log(
                        logging.INFO,
                        "scheduler_cycle_skipped",
                        reason="backup_or_recovery_maintenance",
                    )
                    if stop_event.wait(interval):
                        break
                    continue
                if monotonic() - last_event_prune >= 3600:
                    prune_db = SessionLocal()
                    try:
                        removed = guarded_background(prune_change_events)(prune_db)
                        last_event_prune = monotonic()
                        _structured_log(logging.INFO, "change_events_pruned", removed=removed, retention_days=14)
                    except RecoveryBusy:
                        prune_db.rollback()
                        _structured_log(
                            logging.INFO,
                            "change_event_prune_skipped",
                            reason="backup_or_recovery_maintenance",
                        )
                    except Exception as error:
                        last_event_prune = monotonic()
                        prune_db.rollback()
                        _structured_log(logging.ERROR, "change_event_prune_failed",
                                        error_type=type(error).__name__, error=str(error))
                        LOGGER.exception("Change event pruning traceback")
                    finally:
                        prune_db.close()
                if stop_event.wait(interval):
                    break
        except Exception as error:
            _set_local_health(role="degraded", current_run_id=None)
            _structured_log(
                logging.ERROR,
                "scheduler_worker_failed",
                error_type=type(error).__name__,
                error=str(error),
            )
            LOGGER.exception("Scheduler worker traceback")
            stop_event.wait(min(interval, 10))
        finally:
            if connection is not None:
                if leader:
                    try:
                        release_session_lock(connection, FARM_AUTOMATION_LEADER_GUARD)
                    except Exception as error:
                        _structured_log(
                            logging.WARNING,
                            "scheduler_leadership_release_failed",
                            error_type=type(error).__name__,
                            error=str(error),
                        )
                connection.close()

    _set_local_health(role="stopped", current_run_id=None)


async def farm_automation_scheduler_loop() -> None:
    """Run the blocking leader loop in one dedicated worker thread."""

    stop_event = Event()
    worker = asyncio.create_task(asyncio.to_thread(_scheduler_worker, stop_event))
    try:
        await worker
    except asyncio.CancelledError:
        stop_event.set()
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            pass
        raise
