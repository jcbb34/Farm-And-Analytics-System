"""Durable PDF jobs; a single worker owns generation across backend processes."""

from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from threading import Event, Lock, Thread
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.models import FarmReport
from app.models.report_pdf_job import ReportPdfJob
from app.services.db_concurrency import (
    acquire_transaction_lock,
    try_acquire_session_lock,
    release_session_lock,
)
from app.services.report_pdf import generate_report_pdf, resolve_report_pdf_path

LOGGER = logging.getLogger("joross.report-pdf")
WORKER_GUARD = "reports:pdf-worker"
LOCAL_GUARD = Lock()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_pdf_schema(db):
    if not inspect(db.connection()).has_table("report_pdf_jobs"):
        raise HTTPException(
            503,
            "PDF jobs require the database update. Run python -m alembic upgrade head from Jorros Backend.",
        )


def fingerprint(report):
    values = {
        column.name: getattr(report, column.name)
        for column in FarmReport.__table__.columns
        if column.name not in {"updated_at", "pdf_filename"}
    }
    return sha256(
        json.dumps(values, default=str, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def ready_file(report):
    path = resolve_report_pdf_path(report.pdf_filename, require_current=True)
    return path if path is not None and path.is_file() else None


def queue_pdf(db, report, *, force=False, retry_failed=False):
    ensure_pdf_schema(db)
    acquire_transaction_lock(db, f"report:pdf:{report.id}")
    job = db.scalar(select(ReportPdfJob).where(ReportPdfJob.report_id == report.id))
    signature = fingerprint(report)
    if job is None:
        job = ReportPdfJob(
            report_id=report.id,
            status="Ready" if ready_file(report) and not force else "Queued",
            fingerprint=signature,
            attempts=0,
            requested_at=now(),
        )
        db.add(job)
    elif (
        job.fingerprint != signature
        or (job.status == "Ready" and (not ready_file(report) or force))
        or (job.status == "Failed" and retry_failed)
    ):
        job.status = "Queued"
        job.fingerprint = signature
        job.requested_at = now()
        job.error = None
        job.finished_at = None
    return job


def job_payload(job):
    return {
        "report_id": job.report_id,
        "status": job.status,
        "error": job.error,
        "attempts": job.attempts,
    }


def job_statuses(db, ids):
    ensure_pdf_schema(db)
    rows = db.execute(
        select(
            FarmReport.id,
            FarmReport.pdf_filename,
            ReportPdfJob.status,
            ReportPdfJob.error,
        )
        .outerjoin(ReportPdfJob, ReportPdfJob.report_id == FarmReport.id)
        .where(FarmReport.id.in_(ids))
    ).all()
    result = []
    for identifier, filename, status, error in rows:
        if status in {None, "Ready"}:
            path = resolve_report_pdf_path(filename, require_current=True)
            status = "Ready" if path is not None and path.is_file() else "Not Requested"
        result.append({"report_id": identifier, "status": status, "error": error})
    return result


def process_next_pdf_job(factory):
    if not LOCAL_GUARD.acquire(blocking=False):
        return False
    db = None
    try:
        db = factory()
        bind = db.get_bind()
        if not inspect(db.connection()).has_table("report_pdf_jobs"):
            return False
        with (
            bind.connect() if bind.dialect.name == "mssql" else nullcontext(None)
        ) as leader:
            if leader is not None and not try_acquire_session_lock(
                leader, WORKER_GUARD, timeout_ms=0
            ):
                return False
            try:
                job = db.scalar(
                    select(ReportPdfJob)
                    .where(ReportPdfJob.status.in_(["Queued", "Generating"]))
                    .order_by(ReportPdfJob.requested_at, ReportPdfJob.id)
                    .limit(1)
                )
                if job is None:
                    return False
                report = db.get(FarmReport, job.report_id)
                if report is None:
                    db.delete(job)
                    db.commit()
                    return True
                report_id, job_id = report.id, job.id
                signature = fingerprint(report)
                job.fingerprint = signature
                job.status = "Generating"
                job.started_at = now()
                job.error = None
                job.attempts += 1
                db.commit()
                try:
                    path = generate_report_pdf(report)
                    db.expire_all()
                    current = db.get(FarmReport, report_id)
                    job = db.get(ReportPdfJob, job_id)
                    if current is None or job is None:
                        return True
                    if (
                        fingerprint(current) != signature
                        or job.fingerprint != signature
                    ):
                        job.status = "Queued"
                        job.fingerprint = fingerprint(current)
                    else:
                        current.pdf_filename = path.name
                        job.status = "Ready"
                        job.finished_at = now()
                    db.commit()
                except Exception:
                    db.rollback()
                    job = db.get(ReportPdfJob, job_id)
                    if job is not None:
                        job.status = "Failed"
                        job.error = "PDF generation failed. Retry the PDF job."
                        job.finished_at = now()
                        db.commit()
                    LOGGER.exception("A report PDF job failed")
                return True
            finally:
                if leader is not None:
                    release_session_lock(leader, WORKER_GUARD)
    finally:
        if db is not None:
            db.close()
        LOCAL_GUARD.release()


class ReportPdfWorker:
    def __init__(self, factory):
        self.factory = factory
        self.stop_event = Event()
        self.thread = Thread(target=self.run, name="report-pdf-worker", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def run(self):
        from app.core.recovery_runtime import farm_access, RecoveryBusy

        warned = False
        while not self.stop_event.is_set():
            worked = False
            try:
                with farm_access():
                    worked = process_next_pdf_job(self.factory)
                warned = False
            except RecoveryBusy:
                pass
            except Exception:
                if not warned:
                    LOGGER.warning(
                        "PDF worker cannot access the database. Check connectivity and apply database migrations."
                    )
                warned = True
            self.stop_event.wait(0.25 if worked else 2)

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
