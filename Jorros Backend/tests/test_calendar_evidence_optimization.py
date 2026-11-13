"""Filtered staffing keeps coverage links and private thumbnail access intact."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import test_staff_calendar_timezone as calendar_fixture
import test_task_evidence_security as evidence_fixture
import test_release_http_authorization as http_fixture
from app.core.config import settings
from app.core.farm_time import farm_today
from app.models import Employee, FarmActivity, StaffAttendance, StaffLeave, TaskLeaveCoverage, TaskSubmission, InventoryStockRecord
from app.routers.workforce import my_schedule, staff_calendar, view_task_evidence_thumbnail, view_task_evidence
from app.services.attendance_service import get_or_create_attendance_settings


class CalendarEmployeeFilterTests(TestCase):
    def setUp(self):
        self.fixture = calendar_fixture.StaffCalendarTimezoneTests(); self.fixture.setUp()
        self.db = self.fixture.db

    def tearDown(self):
        self.fixture.tearDown()

    def coverage(self, task, original, covering):
        leave = StaffLeave(employee_id=original.id, leave_type="Vacation", reason="Synthetic filter test", status="Approved",
            start_date=self.fixture.today, end_date=self.fixture.today)
        self.db.add(leave); self.db.flush()
        row = TaskLeaveCoverage(activity_id=task.id, leave_id=leave.id, original_employee_id=original.id,
            covering_employee_id=covering.id, coverage_start_date=self.fixture.today, coverage_end_date=self.fixture.today,
            status="Active", reason="Synthetic filter test")
        self.db.add(row); self.db.commit()
        return row

    def load(self, employee_id):
        return staff_calendar(self.fixture.today, self.fixture.today, employee_id, self.db, self.fixture.manager)

    def test_filter_preserves_tasks_for_original_employee_and_current_cover(self):
        f = self.fixture
        task = f._task(f.today, f.other)
        self.coverage(task, f.employee, f.other)
        self.assertEqual([row["id"] for row in self.load(f.employee.id)["tasks"]], [task.id])
        self.assertEqual([row["id"] for row in self.load(f.other.id)["tasks"]], [task.id])
        payload = self.load(f.employee.id)
        self.assertTrue(all(row["employee_id"] == f.employee.id for row in payload["availability"]))

    def test_filter_uses_latest_coverage_and_matches_existing_all_employee_display(self):
        f = self.fixture
        third = Employee(employee_code="EMP-CAL-THIRD", full_name="Synthetic Third", employment_status="Active")
        self.db.add(third); self.db.commit()
        task = f._task(f.today, f.other)
        self.coverage(task, f.employee, f.other)
        self.coverage(task, third, f.other)
        all_tasks = self.load(None)["tasks"]
        expected = [row["id"] for row in all_tasks if f.employee.id in (row["assigned_employee_id"], row["original_employee_id"], row["covering_employee_id"])]
        self.assertEqual([row["id"] for row in self.load(f.employee.id)["tasks"]], expected)
        self.assertEqual(expected, [])

    def test_self_service_does_not_disclose_another_workers_reassigned_task(self):
        f = self.fixture
        task = f._task(f.today, f.other)
        self.coverage(task, f.employee, f.other)
        self.assertEqual(my_schedule(f.today, f.today, self.db, f.employee_user)["tasks"], [])
        self.assertEqual([row["id"] for row in my_schedule(f.today, f.today, self.db, f.other_user)["tasks"]], [task.id])


class EvidenceThumbnailTests(TestCase):
    def test_thumbnail_is_smaller_task_authorized_and_keeps_original(self):
        f = evidence_fixture.TaskEvidenceSecurityTests(); f.setUp()
        try:
            uploaded = f._upload(data=evidence_fixture._image_bytes(size=(1600, 1200)))
            original = view_task_evidence(uploaded.evidence_id, f.db, f.manager)
            thumb = view_task_evidence_thumbnail(uploaded.evidence_id, f.db, f.worker_user)
            self.assertNotEqual(original.path, thumb.path)
            before = Path(original.path).read_bytes()
            with Image.open(thumb.path) as image:
                self.assertLessEqual(max(image.size), settings.workforce_evidence_thumbnail_pixels)
                self.assertLess(max(image.size), 1600)
            self.assertLess(len(Path(thumb.path).read_bytes()), len(before))
            self.assertEqual(thumb.headers["Cache-Control"], "private, no-store")
            with self.assertRaises(HTTPException) as blocked:
                view_task_evidence_thumbnail(uploaded.evidence_id, f.db, f.other_user)
            self.assertEqual(blocked.exception.status_code, 404)
            self.assertEqual(Path(original.path).read_bytes(), before)
        finally:
            f.tearDown()


class ParallelStaffReadTests(TestCase):
    def test_admin_employee_attendance_and_photo_requests_overlap_without_cross_user_data(self):
        f = http_fixture.ReleaseHttpAuthorizationTests(); f.setUp()
        temporary = TemporaryDirectory()
        try:
            # Each request uses its own session/connection, as in the real API.
            engine = create_engine(f"sqlite+pysqlite:///{temporary.name}/parallel.db", connect_args={"check_same_thread": False, "timeout": 10})
            source = f.engine.raw_connection(); target = engine.raw_connection()
            try:
                source.driver_connection.backup(target.driver_connection)
            finally:
                source.close(); target.close()
            f.engine.dispose(); f.engine = engine
            with Session(engine) as db:
                ids = dict(db.execute(select(Employee.login_user_id, Employee.id)).all())
                task = db.scalar(select(FarmActivity).where(FarmActivity.assigned_employee_id == ids[f.user_ids["WORKER1"]]))
                task_id = task.id
                task.activity_date = farm_today(); db.commit()
                get_or_create_attendance_settings(db); db.commit()
            uploaded = f.client.post(f"/api/v1/workforce/tasks/{task_id}/evidence", headers=f.headers("WORKER1"),
                files={"file": ("test.png", evidence_fixture._image_bytes(), "image/png")})
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            public_id = uploaded.json()["evidence_id"]
            today = farm_today().isoformat(); query = f"date_from={today}&date_to={today}"
            requests = [
                ("ADMIN", "GET", f"/api/v1/workforce/calendar?{query}&employee_id={ids[f.user_ids['WORKER1']]}", 200),
                ("WORKER1", "POST", "/api/v1/workforce/my-attendance/check-in", 200),
                ("WORKER2", "GET", f"/api/v1/workforce/my-schedule?{query}", 200),
                ("MANAGER", "GET", f"/api/v1/workforce/evidence-assets/{public_id}/thumbnail", 200),
                ("WORKER1", "GET", f"/api/v1/workforce/evidence-assets/{public_id}", 200),
                ("WORKER2", "GET", f"/api/v1/workforce/evidence-assets/{public_id}/thumbnail", 404),
            ]
            barrier = Barrier(len(requests))
            def request(row):
                user, method, path, expected = row
                with TestClient(f.client.app, raise_server_exceptions=False) as client:
                    barrier.wait(timeout=10)
                    response = client.request(method, path, headers=f.headers(user), **({"json": {}} if method == "POST" else {}))
                return row, response
            with ThreadPoolExecutor(max_workers=len(requests)) as workers:
                results = list(workers.map(request, requests))
            for (user, method, path, expected), response in results:
                self.assertEqual(response.status_code, expected, f"{user} {path}: {response.text[:150]}")
                if "/my-schedule" in path:
                    self.assertTrue(all(row["assigned_employee_id"] == ids[f.user_ids[user]] for row in response.json()["tasks"]))
            with Session(engine) as db:
                attendance = list(db.scalars(select(StaffAttendance)).all())
                self.assertEqual(len(attendance), 1)
                self.assertEqual(attendance[0].employee_id, ids[f.user_ids["WORKER1"]])
                self.assertIsNotNone(attendance[0].check_in_at)
                self.assertEqual(db.scalar(select(func.count(TaskSubmission.id))), 0)
                self.assertEqual(db.scalar(select(func.count(InventoryStockRecord.id))), 0)
        finally:
            f.tearDown(); temporary.cleanup()
