"""Exercise protected workforce URLs with real bearer tokens and role checks."""

import os
import sys
import tempfile
import unittest
from datetime import date, time, timedelta
from io import BytesIO
from types import ModuleType

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    if "app.core.database" not in sys.modules:
        class _TestBase(DeclarativeBase):
            pass

        database_module = ModuleType("app.core.database")
        database_module.Base = _TestBase

        def _get_db():
            yield None

        database_module.get_db = _get_db
        sys.modules["app.core.database"] = database_module

from app.core.database import Base, get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.models import Employee, FarmActivity, Role, User
from app.routers import workforce


class ReleaseHttpAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.evidence_dir = tempfile.TemporaryDirectory()
        self.previous_evidence_dir = settings.workforce_evidence_local_dir
        settings.workforce_evidence_local_dir = self.evidence_dir.name
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            employee_role = Role(name="Employee", description="Worker")
            employee_role.set_permissions(["workforce:submit"])
            manager_role = Role(name="Manager", description="Manager")
            manager_role.set_permissions(["workforce:manage", "workforce:review"])
            admin_role = Role(name="System Administrator", description="Admin")
            admin_role.set_permissions(["*"])
            db.add_all([employee_role, manager_role, admin_role])
            db.flush()

            users = []
            for code, name, role in (
                ("WORKER1", "Test Worker One", employee_role),
                ("WORKER2", "Test Worker Two", employee_role),
                ("MANAGER", "Test Manager", manager_role),
                ("ADMIN", "Test Admin", admin_role),
            ):
                user = User(
                    user_code=f"USR-REL-{code}",
                    full_name=name,
                    username=f"release.{code.lower()}",
                    password_hash="test-only",
                    role=role,
                    status="Active",
                )
                db.add(user)
                users.append(user)
            db.flush()
            self.user_ids = {user.user_code.rsplit("-", 1)[-1]: user.id for user in users}

            for index, user in enumerate(users[:2], 1):
                employee = Employee(
                    employee_code=f"EMP-REL-{index}",
                    full_name=user.full_name,
                    login_user_id=user.id,
                    employment_status="Active",
                    is_archived=False,
                )
                db.add(employee)
                db.flush()
                db.add(FarmActivity(
                    activity_code=f"ACT-REL-{index}",
                    name=f"Test task {index}",
                    category="General Care",
                    related_to="Release test",
                    location="Test field",
                    activity_date=date.today() - timedelta(days=1),
                    start_time=time(8, 0),
                    assigned_by="Test Manager",
                    assigned_to=user.full_name,
                    assigned_employee_id=employee.id,
                    status="Pending",
                    priority="Medium",
                    requires_review=True,
                    requires_evidence=False,
                    needs_reassignment=False,
                    is_archived=False,
                ))
            db.commit()

        app = FastAPI()
        app.include_router(workforce.router)

        def test_db():
            with Session(self.engine, expire_on_commit=False) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        settings.workforce_evidence_local_dir = self.previous_evidence_dir
        self.evidence_dir.cleanup()

    def headers(self, user_code):
        token, _ = create_access_token(self.user_ids[user_code])
        return {"Authorization": f"Bearer {token}"}

    def test_direct_employee_manager_admin_access_and_task_isolation(self):
        base = "/api/v1/workforce"
        self.assertEqual(self.client.get(f"{base}/employees").status_code, 401)

        worker = self.headers("WORKER1")
        self.assertEqual(self.client.get(f"{base}/employees", headers=worker).status_code, 403)
        protocol_url = f"{base}/care-templates/999/deactivate?future_task_action=keep"
        self.assertEqual(self.client.post(protocol_url, headers=worker).status_code, 403)
        own = self.client.get(f"{base}/my-tasks?view=active", headers=worker)
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual([task["activity_code"] for task in own.json()], ["ACT-REL-1"])
        filtered = self.client.get(f"{base}/tasks?employee_id=2", headers=worker)
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual([task["activity_code"] for task in filtered.json()], ["ACT-REL-1"])

        manager = self.headers("MANAGER")
        self.assertEqual(self.client.get(f"{base}/employees", headers=manager).status_code, 200)
        self.assertEqual(len(self.client.get(f"{base}/tasks", headers=manager).json()), 2)
        self.assertEqual(self.client.post(protocol_url, headers=manager).status_code, 403)

        admin = self.headers("ADMIN")
        self.assertEqual(self.client.get(f"{base}/employees", headers=admin).status_code, 200)
        self.assertEqual(self.client.post(protocol_url, headers=admin).status_code, 404)

    def test_admin_creates_linked_login_manager_assigns_and_worker_submits_photo(self):
        base = "/api/v1/workforce"
        today = date.today()
        work_date = today - timedelta(days=1) if today.weekday() == 6 else today
        schedule = {
            "effective_from": (today - timedelta(days=7)).isoformat(),
            "days": [
                {"day_of_week": day, "state": "Rest Day" if day == 6 else "Working Day",
                 **({} if day == 6 else {"start_time": "08:00", "end_time": "17:00"})}
                for day in range(7)
            ],
        }
        created = self.client.post(
            f"{base}/employees",
            json={
                "full_name": "Release Created Worker",
                "email": "created@farm.test",
                "weekly_schedule": schedule,
                "create_login_account": True,
                "login_username": "release.created.worker",
                "login_password": "TestStrongPass123!",
            },
            headers=self.headers("ADMIN"),
        )
        self.assertEqual(created.status_code, 201, created.text)
        employee_id = created.json()["id"]
        self.assertEqual(created.json()["account_status"], "Account Linked")
        with Session(self.engine) as db:
            employee = db.get(Employee, employee_id)
            self.assertIsNotNone(employee.login_user_id)
            worker_id = employee.login_user_id

        assigned = self.client.post(
            f"{base}/tasks",
            json={
                "name": "Check test crop",
                "category": "General Care",
                "activity_date": work_date.isoformat(),
                "employee_id": employee_id,
                "requires_evidence": True,
            },
            headers=self.headers("MANAGER"),
        )
        self.assertEqual(assigned.status_code, 201, assigned.text)
        task_id = assigned.json()["id"]
        token, _ = create_access_token(worker_id)
        worker = {"Authorization": f"Bearer {token}"}
        visible = self.client.get(f"{base}/my-tasks?view=active", headers=worker)
        self.assertEqual(visible.status_code, 200, visible.text)
        self.assertIn(task_id, [task["id"] for task in visible.json()])
        self.assertNotIn(task_id, [task["id"] for task in self.client.get(f"{base}/my-tasks?view=active", headers=self.headers("WORKER1")).json()])

        started = self.client.post(f"{base}/tasks/{task_id}/start", json={}, headers=worker)
        self.assertEqual(started.status_code, 200, started.text)
        photo = BytesIO()
        Image.new("RGB", (128, 128), (30, 120, 60)).save(photo, format="PNG")
        uploaded = self.client.post(
            f"{base}/tasks/{task_id}/evidence",
            files={"file": ("test-work.png", photo.getvalue(), "image/png")},
            headers=worker,
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        submitted = self.client.post(
            f"{base}/tasks/{task_id}/submit",
            json={"evidence_ids": [uploaded.json()["evidence_id"]], "worker_notes": "Test work completed."},
            headers={**worker, "Idempotency-Key": "release-photo-attempt-1"},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["status"], "Submitted for Review")
        self.assertEqual(self.client.get(f"{base}/tasks/{task_id}/review-report", headers=worker).status_code, 403)
        manager = self.headers("MANAGER")
        reviewed = self.client.post(f"{base}/tasks/{task_id}/review", json={"decision": "Approve"}, headers=manager)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["status"], "Completed")


if __name__ == "__main__":
    unittest.main()
