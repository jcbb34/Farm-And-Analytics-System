import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from types import ModuleType

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    class _TestBase(DeclarativeBase):
        pass

    test_database_module = ModuleType("app.core.database")
    test_database_module.Base = _TestBase

    def _test_get_db():
        yield None

    test_database_module.get_db = _test_get_db
    sys.modules.setdefault("app.core.database", test_database_module)

try:
    import pyotp  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pyotp"] = ModuleType("pyotp")

try:
    import pwdlib  # noqa: F401
except ModuleNotFoundError:
    test_pwdlib_module = ModuleType("pwdlib")

    class _TestPasswordHash:
        @classmethod
        def recommended(cls):
            return cls()

        def hash(self, password):
            return f"test-hash::{password}"

        def verify(self, plain_password, hashed_password):
            return hashed_password == f"test-hash::{plain_password}"

    test_pwdlib_module.PasswordHash = _TestPasswordHash
    sys.modules["pwdlib"] = test_pwdlib_module

from app.core.config import settings
from app.core.database import Base
from app.models import Employee, FarmActivity, Role, TaskEvidence, TaskSubmission, User  # noqa: F401
from app.routers.workforce import submit_task, upload_task_evidence, view_task_evidence
from app.schemas.workforce import TaskSubmitRequest
from app.services.evidence_storage import cleanup_expired_task_evidence, get_evidence_storage


class _Upload:
    def __init__(self, data: bytes, filename: str, content_type: str):
        self._data = data
        self.filename = filename
        self.content_type = content_type

    async def read(self, size: int = -1):
        return self._data if size < 0 else self._data[:size]


def _image_bytes(fmt="PNG", size=(320, 240)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (30, 120, 60)).save(output, format=fmt)
    return output.getvalue()


class TaskEvidenceSecurityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = settings.workforce_evidence_local_dir
        self.old_max = settings.workforce_evidence_max_bytes
        settings.workforce_evidence_local_dir = self.tmp.name
        settings.workforce_evidence_max_bytes = 6 * 1024 * 1024

        submit_role = Role(name="Photo Worker", description="task submit")
        submit_role.set_permissions(["workforce:submit"])
        manager_role = Role(name="Photo Manager", description="manager")
        manager_role.set_permissions(["workforce:manage"])
        reviewer_role = Role(name="Photo Reviewer", description="reviewer")
        reviewer_role.set_permissions(["workforce:review"])
        no_access_role = Role(name="Photo Visitor", description="no workforce")
        no_access_role.set_permissions(["inventory:view"])
        self.db.add_all([submit_role, manager_role, reviewer_role, no_access_role])
        self.db.flush()

        self.worker_user = self._user("USR-PHOTO-1", "photo.worker", submit_role)
        self.other_user = self._user("USR-PHOTO-2", "photo.other", submit_role)
        self.manager = self._user("USR-PHOTO-M", "photo.manager", manager_role)
        self.reviewer = self._user("USR-PHOTO-R", "photo.reviewer", reviewer_role)
        self.visitor = self._user("USR-PHOTO-V", "photo.visitor", no_access_role)
        self.db.flush()

        self.worker = Employee(
            employee_code="EMP-PHOTO-1",
            full_name="Assigned Photo Worker",
            position="Farm Worker",
            employment_status="Active",
            login_user_id=self.worker_user.id,
        )
        self.other_worker = Employee(
            employee_code="EMP-PHOTO-2",
            full_name="Other Photo Worker",
            position="Farm Worker",
            employment_status="Active",
            login_user_id=self.other_user.id,
        )
        self.db.add_all([self.worker, self.other_worker])
        self.db.flush()
        self.task = FarmActivity(
            activity_code="ACT-PHOTO-001",
            name="Secure evidence task",
            category="General Care",
            related_to="Evidence Test",
            location="Joross Farm",
            activity_date=date.today(),
            start_time=time(8, 0),
            assigned_by="Photo Manager",
            assigned_to=self.worker.full_name,
            assigned_employee_id=self.worker.id,
            status="Pending",
            priority="Medium",
            requires_review=True,
            requires_evidence=True,
            is_automatic=False,
        )
        self.db.add(self.task)
        self.db.commit()

    def tearDown(self):
        settings.workforce_evidence_local_dir = self.old_dir
        settings.workforce_evidence_max_bytes = self.old_max
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def _user(self, code, username, role):
        user = User(
            user_code=code,
            full_name=username.replace(".", " ").title(),
            username=username,
            password_hash="test",
            role=role,
            status="Active",
        )
        self.db.add(user)
        return user

    def _upload(self, user=None, data=None, filename="evidence.png", content_type="image/png"):
        return asyncio.run(
            upload_task_evidence(
                self.task.id,
                _Upload(data if data is not None else _image_bytes(), filename, content_type),
                self.db,
                user or self.worker_user,
            )
        )

    def test_upload_authorization_is_task_scoped_and_management_roles_are_allowed(self):
        with self.assertRaises(HTTPException) as other_ctx:
            self._upload(user=self.other_user)
        self.assertEqual(other_ctx.exception.status_code, 404)

        with self.assertRaises(HTTPException) as visitor_ctx:
            self._upload(user=self.visitor)
        self.assertEqual(visitor_ctx.exception.status_code, 403)

        manager_result = self._upload(user=self.manager)
        reviewer_result = self._upload(user=self.reviewer)
        self.assertTrue(manager_result.evidence_id)
        self.assertTrue(reviewer_result.evidence_id)

        # Viewing follows the same task privacy boundary.
        with self.assertRaises(HTTPException) as view_ctx:
            view_task_evidence(manager_result.evidence_id, self.db, self.other_user)
        self.assertEqual(view_ctx.exception.status_code, 404)
        self.assertEqual(view_task_evidence(manager_result.evidence_id, self.db, self.manager).status_code, 200)
        self.assertEqual(view_task_evidence(reviewer_result.evidence_id, self.db, self.reviewer).status_code, 200)

    def test_fake_image_is_rejected_even_when_extension_and_browser_mime_claim_jpeg(self):
        with self.assertRaises(HTTPException) as ctx:
            self._upload(data=b"\xff\xd8\xffthis-is-not-a-real-image", filename="fake.jpg", content_type="image/jpeg")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.db.scalar(select(TaskEvidence).where(TaskEvidence.activity_id == self.task.id)), None)

    def test_oversized_file_is_rejected_before_decoding(self):
        settings.workforce_evidence_max_bytes = 1024 * 1024
        with self.assertRaises(HTTPException) as ctx:
            self._upload(data=b"\x89PNG\r\n\x1a\n" + (b"x" * (1024 * 1024 + 10)), filename="large.png", content_type="image/png")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("1 MB or smaller", str(ctx.exception.detail))

    def test_valid_image_is_reencoded_audited_and_bound_to_submission(self):
        result = self._upload(filename="../../worker photo.png")
        self.assertTrue(result.evidence_url.startswith("/workforce/evidence-assets/"))
        self.assertNotIn(self.tmp.name, result.evidence_url)

        evidence = self.db.scalar(select(TaskEvidence).where(TaskEvidence.public_id == result.evidence_id))
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.activity_id, self.task.id)
        self.assertEqual(evidence.uploader_user_id, self.worker_user.id)
        self.assertEqual(evidence.original_display_name, "worker photo.png")
        self.assertEqual(evidence.status, "Temporary")
        self.assertEqual(len(evidence.sha256), 64)
        self.assertNotIn("worker", evidence.storage_identifier)
        self.assertGreaterEqual(evidence.width, 64)
        self.assertGreaterEqual(evidence.height, 64)

        submit_task(
            self.task.id,
            TaskSubmitRequest(
                evidence_url=result.evidence_url,
                worker_notes="Work completed with secured photo evidence.",
            ),
            self.db,
            self.worker_user,
        )
        self.db.refresh(evidence)
        submission = self.db.scalar(select(TaskSubmission).where(TaskSubmission.activity_id == self.task.id))
        self.assertIsNotNone(submission)
        self.assertEqual(evidence.submission_id, submission.id)
        self.assertEqual(evidence.status, "Attached")
        self.assertIsNone(evidence.expires_at)
        self.assertEqual(submission.evidence_url, result.evidence_url)

    def test_external_evidence_url_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            submit_task(
                self.task.id,
                TaskSubmitRequest(evidence_url="https://untrusted.example/evidence.jpg"),
                self.db,
                self.worker_user,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("External evidence URLs are disabled", str(ctx.exception.detail))

    def test_orphan_cleanup_removes_expired_file_but_keeps_audit_record(self):
        result = self._upload()
        evidence = self.db.scalar(select(TaskEvidence).where(TaskEvidence.public_id == result.evidence_id))
        evidence.expires_at = datetime.now() - timedelta(minutes=1)
        self.db.commit()

        storage = get_evidence_storage()
        original_path = storage.path_for_response(evidence.storage_identifier)
        thumbnail_path = storage.path_for_response(evidence.thumbnail_storage_identifier)
        self.assertTrue(original_path.exists())
        self.assertTrue(thumbnail_path.exists())

        deleted = cleanup_expired_task_evidence(self.db, now=datetime.now())
        self.assertEqual(deleted, 1)
        self.db.refresh(evidence)
        self.assertEqual(evidence.status, "Deleted")
        self.assertIsNotNone(evidence.deleted_at)
        self.assertEqual(evidence.uploader_user_id, self.worker_user.id)
        self.assertEqual(evidence.activity_id, self.task.id)
        self.assertEqual(len(evidence.sha256), 64)
        self.assertFalse(original_path.exists())
        self.assertFalse(thumbnail_path.exists())


if __name__ == "__main__":
    unittest.main()
