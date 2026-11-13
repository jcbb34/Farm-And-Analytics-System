"""Durable PDF lifecycle, authenticated downloads and streamed CSV contracts."""

import csv
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
import test_data_display_pages as fixture
from app.models import FarmReport
from app.models.report_pdf_job import ReportPdfJob
from app.routers import reports
from app.services import report_pdf, report_pdf_jobs as jobs
from app.services.report_csv import build_report_csv, iter_report_csv


class PdfJobsAndStreamingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.DataDisplayPagesTests(methodName="runTest")
        self.fixture.setUp()
        self.engine, self.client = self.fixture.engine, self.fixture.client
        self.client.app.include_router(reports.router)
        self.temp = tempfile.TemporaryDirectory()
        self.directory = patch.object(
            report_pdf, "REPORT_DIRECTORY", Path(self.temp.name)
        )
        self.directory.start()
        with Session(self.engine) as db:
            report = FarmReport(
                report_code="RPT-JOB",
                title="Original",
                category="Farm",
                report_type="Farm Overview",
                start_date=self.fixture.today,
                end_date=self.fixture.today,
                generated_date=self.fixture.today,
                prepared_by="Test Admin",
                status="Draft",
                summary="Test",
                snapshot_json="{}",
            )
            db.add(report)
            db.commit()
            self.report_id = report.id
        self.factory = lambda: Session(self.engine, expire_on_commit=False)

    def tearDown(self):
        self.directory.stop()
        self.temp.cleanup()
        self.fixture.tearDown()

    def queue(self):
        with self.factory() as db:
            job = jobs.queue_pdf(db, db.get(FarmReport, self.report_id))
            db.commit()
            return job.id

    def render(self, report):
        path = (
            Path(self.temp.name) / f"RPT_PDF-{report_pdf.PDF_LAYOUT_VERSION}_test.pdf"
        )
        path.write_bytes(b"%PDF-1.4\nsynthetic test\n%%EOF")
        return path

    def test_queue_coalesces_requests_and_worker_persists_ready(self):
        self.assertEqual(self.queue(), self.queue())
        with patch.object(
            jobs, "generate_report_pdf", side_effect=self.render
        ) as render:
            self.assertTrue(jobs.process_next_pdf_job(self.factory))
            self.assertFalse(jobs.process_next_pdf_job(self.factory))
            self.assertEqual(render.call_count, 1)
        with self.factory() as db:
            job = db.scalar(select(ReportPdfJob))
            report = db.get(FarmReport, self.report_id)
            self.assertEqual(
                (job.status, job.attempts, report.status), ("Ready", 1, "Draft")
            )
            self.assertIsNotNone(jobs.ready_file(report))
            self.assertEqual(jobs.queue_pdf(db, report).status, "Ready")
            # Restored backups may retain the job while the rebuildable PDF cache is absent.
            jobs.ready_file(report).unlink()
            self.assertEqual(jobs.job_statuses(db, [self.report_id])[0]["status"], "Not Requested")
            self.assertEqual(jobs.queue_pdf(db, report).status, "Queued")

    def test_failed_generation_retries_and_interrupted_job_resumes(self):
        self.queue()
        with patch.object(
            jobs,
            "generate_report_pdf",
            side_effect=RuntimeError("private internal failure"),
        ):
            self.assertTrue(jobs.process_next_pdf_job(self.factory))
        with self.factory() as db:
            report = db.get(FarmReport, self.report_id)
            job = db.scalar(select(ReportPdfJob))
            self.assertEqual(job.status, "Failed")
            self.assertNotIn("private", job.error)
            self.assertEqual(
                jobs.queue_pdf(db, report, retry_failed=True).status, "Queued"
            )
            db.commit()
            job.status = "Generating"
            db.commit()
        with patch.object(jobs, "generate_report_pdf", side_effect=self.render):
            jobs.process_next_pdf_job(self.factory)
        with self.factory() as db:
            job = db.scalar(select(ReportPdfJob))
            self.assertEqual((job.status, job.attempts), ("Ready", 2))
            self.assertEqual(db.get(FarmReport, self.report_id).status, "Draft")

    def test_report_changed_during_render_requeues_stale_result(self):
        self.queue()

        def edit_while_rendering(report):
            path = self.render(report)
            with self.factory() as db:
                db.get(FarmReport, self.report_id).title = "Updated while rendering"
                db.commit()
            return path

        with patch.object(
            jobs, "generate_report_pdf", side_effect=edit_while_rendering
        ):
            jobs.process_next_pdf_job(self.factory)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(ReportPdfJob.status)), "Queued")
            self.assertIsNone(db.get(FarmReport, self.report_id).pdf_filename)
        with patch.object(jobs, "generate_report_pdf", side_effect=self.render):
            jobs.process_next_pdf_job(self.factory)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(ReportPdfJob.status)), "Ready")

    def test_http_pending_then_authenticated_pdf_and_lightweight_status(self):
        url = f"/api/v1/reports/{self.report_id}/pdf"
        headers = self.fixture.headers("ADMIN")
        response = self.client.get(url, headers=headers)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["status"], "Queued")
        self.assertEqual(response.headers["retry-after"], "2")
        with patch.object(jobs, "generate_report_pdf", side_effect=self.render):
            jobs.process_next_pdf_job(self.factory)
        response = self.client.get(url, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.content.startswith(b"%PDF"))
        status = self.client.get(
            "/api/v1/reports/pdf-jobs/status",
            params={"report_ids": str(self.report_id)},
            headers=headers,
        )
        self.assertEqual(status.json()[0]["status"], "Ready")
        self.assertNotIn("snapshot", status.text)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(
            self.client.get(url, headers=self.fixture.headers("WORKER1")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/reports/pdf-jobs/status",
                params={"report_ids": ",".join(map(str, range(1, 102)))},
                headers=headers,
            ).status_code,
            422,
        )

    def test_csv_chunks_preserve_all_rows_and_formula_protection(self):
        with self.factory() as db:
            report = db.get(FarmReport, self.report_id)
            report.title = '=HYPERLINK("untrusted")'
            report.snapshot_json = json.dumps(
                {
                    "report_kind": "operational_factual",
                    "operational_rows": [
                        {"number": i, "notes": "=1+1" if i == 0 else "x" * 100}
                        for i in range(1000)
                    ],
                }
            )
            db.commit()
            chunks = list(iter_report_csv(report, chunk_size=1024))
            joined = "".join(chunks)
            self.assertGreater(len(chunks), 10)
            self.assertEqual(joined, build_report_csv(report))
            rows = list(csv.reader(StringIO(joined)))
            self.assertEqual(
                next(row for row in rows if row and row[0] == "Title")[1],
                "'" + report.title,
            )
            self.assertIn(["999", "x" * 100], rows)
            self.assertIn(["0", "'=1+1"], rows)
        response = self.client.get(
            f"/api/v1/reports/{self.report_id}/data.csv",
            headers=self.fixture.headers("ADMIN"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, joined)
        self.assertIn("supporting-data.csv", response.headers["content-disposition"])

    def test_worker_guard_releases_after_database_factory_failure(self):
        def broken():
            raise RuntimeError("database unavailable")

        with self.assertRaises(RuntimeError):
            jobs.process_next_pdf_job(broken)
        self.queue()
        with patch.object(jobs, "generate_report_pdf", side_effect=self.render):
            self.assertTrue(jobs.process_next_pdf_job(self.factory))


def test_pdf_job_migration_round_trip_preserves_reports():
    path = (
        Path(__file__).parents[1]
        / "migrations/versions/f6a7b8c9d0e1_report_pdf_jobs.py"
    )
    spec = importlib.util.spec_from_file_location("pdf_job_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE farm_reports (id INTEGER PRIMARY KEY, title TEXT)")
        )
        connection.execute(
            text("INSERT INTO farm_reports VALUES (1, 'Preserve this report')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "report_pdf_jobs" in inspect(connection).get_table_names()
            migration.downgrade()
        assert "report_pdf_jobs" not in inspect(connection).get_table_names()
        assert (
            connection.execute(text("SELECT title FROM farm_reports")).scalar_one()
            == "Preserve this report"
        )
    engine.dispose()
