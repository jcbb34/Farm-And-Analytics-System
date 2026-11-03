import os
import sys
import unittest
from datetime import date, time
from types import ModuleType

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-that-is-long-enough-for-dashboard-workflow")

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    if "app.core.database" not in sys.modules:
        class _TestBase(DeclarativeBase):
            pass

        database_module = ModuleType("app.core.database")
        database_module.Base = _TestBase

        def _test_get_db():
            yield None

        database_module.get_db = _test_get_db
        sys.modules.setdefault("app.core.database", database_module)

try:
    import pyotp  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pyotp"] = ModuleType("pyotp")

try:
    import pwdlib  # noqa: F401
except ModuleNotFoundError:
    pwdlib_module = ModuleType("pwdlib")

    class _PasswordHash:
        @classmethod
        def recommended(cls):
            return cls()

        def hash(self, password):
            return f"test::{password}"

        def verify(self, plain_password, hashed_password):
            return hashed_password == f"test::{plain_password}"

    pwdlib_module.PasswordHash = _PasswordHash
    sys.modules["pwdlib"] = pwdlib_module

from app.core.database import Base
from app.models import Employee, FarmActivity, Role, TaskSubmission, User  # noqa: F401
from app.routers.activities import _activity_response, get_activity, update_activity
from app.schemas.activity import FarmActivityUpdate


class DashboardActivityWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()

        manager_role = Role(name="Dashboard Manager", description="manager")
        manager_role.set_permissions(["activities:view", "activities:update", "workforce:manage", "workforce:review"])
        employee_role = Role(name="Dashboard Employee", description="employee")
        employee_role.set_permissions(["activities:view", "dashboard:view", "workforce:submit"])
        self.db.add_all([manager_role, employee_role])
        self.db.flush()

        self.manager = User(
            user_code="USR-DASH-M",
            full_name="Dashboard Manager",
            username="dashboard.manager",
            password_hash="test",
            role=manager_role,
            status="Active",
        )
        self.worker = User(
            user_code="USR-DASH-W",
            full_name="Dashboard Worker",
            username="dashboard.worker",
            password_hash="test",
            role=employee_role,
            status="Active",
        )
        self.db.add_all([self.manager, self.worker])
        self.db.flush()

        self.employee = Employee(
            employee_code="EMP-DASH-1",
            full_name="Dashboard Worker",
            position="Farm Worker",
            employment_status="Active",
            login_user_id=self.worker.id,
        )
        self.db.add(self.employee)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def activity(self, *, code, status="In Progress", employee=True, requires_review=True, automatic=False, source_module=None, source_type=None, source_path=None):
        row = FarmActivity(
            activity_code=code,
            name=f"Activity {code}",
            category="Farm Work",
            related_to="Jorros Farm",
            location="Farm",
            activity_date=date.today(),
            start_time=time(8, 0),
            assigned_by=self.manager.full_name,
            assigned_to=self.employee.full_name if employee else "Farm Manager",
            assigned_employee_id=self.employee.id if employee else None,
            assignment_source="manual",
            requires_review=requires_review,
            requires_evidence=False,
            status=status,
            priority="Medium",
            is_automatic=automatic,
            source_module=source_module,
            source_type=source_type,
            source_path=source_path,
            is_archived=False,
            created_by_user_id=self.manager.id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_manager_workforce_task_uses_open_task_and_assisted_submission_not_complete(self):
        task = self.activity(code="ACT-DASH-1", status="In Progress")
        response = _activity_response(task, self.manager)
        self.assertEqual(response.workflow_type, "workforce_task")
        self.assertEqual(response.linked_task_id, task.id)
        self.assertFalse(response.can_complete_directly)
        self.assertTrue(response.requires_employee_submission)
        self.assertTrue(response.requires_manager_review)
        self.assertEqual(response.available_actions[:2], ["open_task", "assisted_submission"])
        self.assertNotIn("complete_directly", response.available_actions)

    def test_manager_status_actions_match_review_return_reassignment_and_report_workflow(self):
        submitted = self.activity(code="ACT-DASH-2", status="Submitted for Review")
        self.assertEqual(_activity_response(submitted, self.manager).available_actions, ["review_submission"])

        returned = self.activity(code="ACT-DASH-3", status="Returned")
        self.assertEqual(_activity_response(returned, self.manager).available_actions, ["view_returned_task"])

        returned.needs_reassignment = True
        self.db.commit()
        self.assertEqual(_activity_response(returned, self.manager).available_actions, ["resolve_assignment"])

        completed = self.activity(code="ACT-DASH-4", status="Completed")
        self.assertEqual(_activity_response(completed, self.manager).available_actions, ["view_report"])

    def test_employee_receives_only_own_task_workflow_actions(self):
        task = self.activity(code="ACT-DASH-5", status="Pending")
        self.assertEqual(_activity_response(task, self.worker, current_employee_id=self.employee.id).available_actions, ["open_my_tasks"])
        task.status = "Returned"
        self.assertEqual(_activity_response(task, self.worker, current_employee_id=self.employee.id).available_actions, ["correct_submission"])
        task.status = "Submitted for Review"
        self.assertEqual(_activity_response(task, self.worker, current_employee_id=self.employee.id).available_actions, ["view_submission"])
        task.status = "Completed"
        self.assertEqual(_activity_response(task, self.worker, current_employee_id=self.employee.id).available_actions, ["view_history"])

    def test_standalone_activity_retains_backend_authorized_direct_completion(self):
        standalone = self.activity(
            code="ACT-DASH-6",
            status="In Progress",
            employee=False,
            requires_review=False,
            automatic=False,
        )
        response = _activity_response(standalone, self.manager)
        self.assertEqual(response.workflow_type, "standalone_activity")
        self.assertTrue(response.can_complete_directly)
        self.assertEqual(response.available_actions, ["complete_directly"])

        updated = update_activity(
            standalone.id,
            FarmActivityUpdate(status="Completed"),
            db=self.db,
            current_user=self.manager,
        )
        self.assertEqual(updated.status, "Completed")
        self.assertNotIn("complete_directly", updated.available_actions)

    def test_workforce_direct_complete_protection_remains_enforced(self):
        task = self.activity(code="ACT-DASH-7", status="In Progress")
        with self.assertRaises(HTTPException) as captured:
            update_activity(
                task.id,
                FarmActivityUpdate(status="Completed"),
                db=self.db,
                current_user=self.manager,
            )
        self.assertEqual(captured.exception.status_code, 400)
        self.assertIn("cannot be marked Completed directly", captured.exception.detail)
        self.db.refresh(task)
        self.assertEqual(task.status, "In Progress")

    def test_task_linked_care_activity_is_classified_from_persisted_source_metadata(self):
        care = self.activity(
            code="ACT-DASH-8",
            status="Pending",
            source_module="Livestock",
            source_type="livestock_feeding",
            automatic=True,
        )
        response = _activity_response(care, self.manager)
        self.assertEqual(response.workflow_type, "care_task")
        self.assertEqual(response.linked_task_id, care.id)
        self.assertIn("open_task", response.available_actions)
        self.assertNotIn("complete_directly", response.available_actions)

    def test_employee_activity_detail_cannot_reveal_another_employee_task(self):
        other_user = User(
            user_code="USR-DASH-O",
            full_name="Other Dashboard Worker",
            username="dashboard.other",
            password_hash="test",
            role=self.worker.role,
            status="Active",
        )
        self.db.add(other_user)
        self.db.flush()
        other_employee = Employee(
            employee_code="EMP-DASH-2",
            full_name="Other Dashboard Worker",
            position="Farm Worker",
            employment_status="Active",
            login_user_id=other_user.id,
        )
        self.db.add(other_employee)
        self.db.commit()

        task = self.activity(code="ACT-DASH-SEC", status="Pending")
        own = get_activity(task.id, db=self.db, current_user=self.worker)
        self.assertEqual(own.id, task.id)

        with self.assertRaises(HTTPException) as captured:
            get_activity(task.id, db=self.db, current_user=other_user)
        self.assertEqual(captured.exception.status_code, 404)

    def test_system_informational_activity_routes_to_persisted_source(self):
        info = self.activity(
            code="ACT-DASH-9",
            status="In Progress",
            employee=False,
            requires_review=False,
            automatic=True,
            source_module="Crop",
            source_type="crop_growth_check",
            source_path="/crops?cropId=5",
        )
        response = _activity_response(info, self.manager)
        self.assertEqual(response.workflow_type, "system_informational")
        self.assertEqual(response.available_actions, ["open_source"])
        self.assertFalse(response.can_complete_directly)


if __name__ == "__main__":
    unittest.main()
