import json
import os
import sys
import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from types import ModuleType

from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import create_engine
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

from app.core.database import Base
from app.core.dependencies import has_permission, is_task_only_user
from app.models import Employee, FarmActivity, Role, TaskSubmission, User  # noqa: F401
from app.routers.workforce import (
    WORKFORCE_PERMISSION_MATRIX,
    _require_workforce_access,
    get_employee_work_assignments,
    get_my_employee_profile,
    list_attendance,
    list_care_templates,
    list_employees,
    list_tasks,
    my_tasks,
    router as workforce_router,
    staff_calendar,
    start_task,
    submit_task,
    update_employee,
)
from app.schemas.workforce import EmployeeUpdate, TaskStartRequest, TaskSubmitRequest


class WorkforcePermissionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()

        self.owner_role = Role(name="Owner", description="Owner")
        self.admin_role = Role(name="System Administrator", description="System Administrator")
        self.manager_role = Role(name="Manager", description="Manager")
        # Simulate a legacy Employee role that still has stale broad permissions.
        self.employee_role = Role(
            name="Employee",
            description="Employee",
            permissions_json=json.dumps([
                "workforce:submit",
                "workforce:view",
                "settings:view",
                "activities:view",
            ]),
        )
        self.custom_role = Role(name="Harvest Crew", description="Custom field role")
        self.custom_role.set_permissions(["workforce:submit"])
        self.db.add_all([
            self.owner_role,
            self.admin_role,
            self.manager_role,
            self.employee_role,
            self.custom_role,
        ])
        self.db.flush()

        self.owner = User(
            user_code="USR-OWNER-PERM",
            full_name="Farm Owner",
            username="farm.owner",
            password_hash="test",
            role=self.owner_role,
            status="Active",
        )
        self.admin = User(
            user_code="USR-ADMIN-PERM",
            full_name="System Administrator",
            username="system.admin",
            password_hash="test",
            role=self.admin_role,
            status="Active",
        )
        self.manager = User(
            user_code="USR-MANAGER-PERM",
            full_name="Farm Manager",
            username="farm.manager",
            password_hash="test",
            role=self.manager_role,
            status="Active",
        )
        self.employee_user = User(
            user_code="USR-EMP-PERM",
            full_name="Regular Worker Login",
            username="regular.worker",
            password_hash="test",
            role=self.employee_role,
            status="Active",
        )
        self.custom_user = User(
            user_code="USR-CUSTOM-PERM",
            full_name="Custom Worker Login",
            username="custom.worker",
            password_hash="test",
            role=self.custom_role,
            status="Active",
        )
        self.db.add_all([self.owner, self.admin, self.manager, self.employee_user, self.custom_user])
        self.db.flush()

        self.employee_profile = Employee(
            employee_code="EMP-PERM-001",
            full_name="Regular Worker",
            contact_number="09170000001",
            email="regular@example.test",
            address="Private employee address",
            position="Farm Worker",
            assigned_area="Field A",
            emergency_contact_name="Private Emergency Contact",
            employment_status="Active",
            login_user_id=self.employee_user.id,
        )
        self.custom_profile = Employee(
            employee_code="EMP-PERM-002",
            full_name="Custom Worker",
            contact_number="09170000002",
            email="custom@example.test",
            address="Other private address",
            position="Harvest Worker",
            assigned_area="Field B",
            emergency_contact_name="Other Private Contact",
            employment_status="Active",
            login_user_id=self.custom_user.id,
        )
        self.other_profile = Employee(
            employee_code="EMP-PERM-003",
            full_name="Other Worker",
            position="Farm Worker",
            employment_status="Active",
        )
        self.db.add_all([self.employee_profile, self.custom_profile, self.other_profile])
        self.db.flush()

        self.custom_task = self._task("ACT-PERM-OWN", self.custom_profile.id, "Custom worker task")
        self.other_task = self._task("ACT-PERM-OTHER", self.other_profile.id, "Other worker task")
        self.employee_task = self._task("ACT-PERM-EMP", self.employee_profile.id, "Employee task")
        self.db.add_all([self.custom_task, self.other_task, self.employee_task])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _task(self, code, employee_id, name):
        employee = self.db.get(Employee, employee_id)
        return FarmActivity(
            activity_code=code,
            name=name,
            category="General Care",
            related_to="Permission Test",
            location="Jorros Farm",
            activity_date=date.today(),
            start_time=time(8, 0),
            assigned_by="Manager",
            assigned_to=employee.full_name,
            assigned_employee_id=employee.id,
            status="Pending",
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
            is_automatic=False,
        )

    def assert_http_status(self, expected_status, callable_):
        with self.assertRaises(HTTPException) as ctx:
            callable_()
        self.assertEqual(ctx.exception.status_code, expected_status)
        return ctx.exception

    def test_permission_matrix_covers_every_workforce_endpoint(self):
        endpoint_names = {
            route.endpoint.__name__
            for route in workforce_router.routes
            if isinstance(route, APIRoute)
        }
        self.assertEqual(endpoint_names, set(WORKFORCE_PERMISSION_MATRIX))

    def test_legacy_employee_permissions_are_ceilinged_to_task_only(self):
        self.assertTrue(is_task_only_user(self.employee_user))
        self.assertTrue(has_permission(self.employee_user, "workforce:submit"))
        self.assertFalse(has_permission(self.employee_user, "workforce:view"))
        self.assertFalse(has_permission(self.employee_user, "settings:view"))
        self.assertFalse(has_permission(self.employee_user, "activities:view"))

        self.assert_http_status(403, lambda: list_employees(False, False, self.db, self.employee_user))
        self.assert_http_status(
            403,
            lambda: get_employee_work_assignments(self.other_profile.id, False, self.db, self.employee_user),
        )
        self.assert_http_status(403, lambda: list_attendance(None, None, None, self.db, self.employee_user))
        self.assert_http_status(
            403,
            lambda: staff_calendar(date.today(), date.today(), None, self.db, self.employee_user),
        )
        self.assert_http_status(403, lambda: list_care_templates(None, False, self.db, self.employee_user))

    def test_custom_submit_role_uses_linked_identity_and_cannot_open_other_tasks(self):
        self.assertEqual(self.custom_user.role.name, "Harvest Crew")
        self.assertTrue(is_task_only_user(self.custom_user))

        # Supplying another employee_id does not escape self scope.
        rows = list_tasks(
            employee_id=self.other_profile.id,
            task_status=None,
            date_from=None,
            date_to=None,
            source_module=None,
            source_record_id=None,
            open_only=False,
            actionable_only=False,
            db=self.db,
            current_user=self.custom_user,
        )
        self.assertEqual([row.id for row in rows], [self.custom_task.id])

        mine = my_tasks(False, self.db, self.custom_user)
        self.assertEqual([row.id for row in mine], [self.custom_task.id])

        # Another employee's task is intentionally hidden as 404, not 403.
        self.assert_http_status(
            404,
            lambda: start_task(self.other_task.id, TaskStartRequest(), self.db, self.custom_user),
        )
        own_started = start_task(self.custom_task.id, TaskStartRequest(), self.db, self.custom_user)
        self.assertEqual(own_started.status, "In Progress")

        profile = get_my_employee_profile(self.db, self.custom_user)
        self.assertEqual(profile.employee_code, self.custom_profile.employee_code)
        self.assertEqual(profile.username, self.custom_user.username)
        self.assertNotIn("address", profile.model_dump())
        self.assertNotIn("emergency_contact_name", profile.model_dump())
        self.assertNotIn("login_user_id", profile.model_dump())


    def test_future_task_cannot_be_started_or_submitted_before_scheduled_day(self):
        future_task = self._task("ACT-PERM-FUTURE", self.custom_profile.id, "Future custom worker task")
        future_task.activity_date = date(2026, 9, 13)
        self.db.add(future_task)
        self.db.commit()

        with patch("app.routers.workforce.farm_today", return_value=date(2026, 9, 12)):
            start_error = self.assert_http_status(
                400,
                lambda: start_task(future_task.id, TaskStartRequest(), self.db, self.custom_user),
            )
            self.assertIn("future task", start_error.detail.lower())

            submit_error = self.assert_http_status(
                400,
                lambda: submit_task(future_task.id, TaskSubmitRequest(), self.db, self.custom_user),
            )
            self.assertIn("future task", submit_error.detail.lower())

        self.db.refresh(future_task)
        self.assertEqual(future_task.status, "Pending")

    def test_my_tasks_explicit_views_do_not_mix_active_and_completed_history(self):
        in_progress = self._task("ACT-PERM-INPROGRESS", self.custom_profile.id, "In progress task")
        in_progress.status = "In Progress"
        returned = self._task("ACT-PERM-RETURNED", self.custom_profile.id, "Returned task")
        returned.status = "Returned"
        review = self._task("ACT-PERM-REVIEW", self.custom_profile.id, "Review task")
        review.status = "Submitted for Review"
        completed = self._task("ACT-PERM-COMPLETED", self.custom_profile.id, "Completed task")
        completed.status = "Completed"
        completed.completed_at = datetime.now()
        cancelled = self._task("ACT-PERM-CANCELLED", self.custom_profile.id, "Cancelled task")
        cancelled.status = "Cancelled"
        resolved = self._task("ACT-PERM-RESOLVED", self.custom_profile.id, "Resolved task")
        resolved.status = "Resolved"
        voided = self._task("ACT-PERM-VOIDED", self.custom_profile.id, "Voided task")
        voided.status = "Voided"
        archived = self._task("ACT-PERM-ARCHIVED", self.custom_profile.id, "Archived completed task")
        archived.status = "Completed"
        archived.is_archived = True
        self.db.add_all([in_progress, returned, review, completed, cancelled, resolved, voided, archived])
        self.db.commit()

        active = my_tasks(False, self.db, self.custom_user, view="active")
        self.assertEqual(
            {row.status for row in active},
            {"Pending", "In Progress", "Returned", "Submitted for Review"},
        )
        self.assertNotIn(completed.id, {row.id for row in active})

        history = my_tasks(False, self.db, self.custom_user, view="completed")
        self.assertEqual({row.status for row in history}, {"Completed"})
        self.assertEqual({row.id for row in history}, {completed.id})

        all_rows = my_tasks(False, self.db, self.custom_user, view="all")
        all_ids = {row.id for row in all_rows}
        self.assertIn(self.custom_task.id, all_ids)
        self.assertIn(completed.id, all_ids)
        self.assertIn(cancelled.id, all_ids)
        self.assertIn(resolved.id, all_ids)
        self.assertIn(voided.id, all_ids)
        self.assertNotIn(archived.id, all_ids)

        history = my_tasks(False, self.db, self.custom_user, view="history")
        history_ids = {row.id for row in history}
        self.assertNotIn(self.custom_task.id, history_ids)
        self.assertIn(completed.id, history_ids)
        self.assertIn(cancelled.id, history_ids)
        self.assertIn(resolved.id, history_ids)
        self.assertIn(voided.id, history_ids)
        self.assertIn(archived.id, history_ids)
        archived_response = next(row for row in history if row.id == archived.id)
        self.assertTrue(archived_response.is_archived)

    def test_completed_view_sorts_by_effective_completion_time_with_approved_fallback(self):
        older = self._task("ACT-PERM-COMP-OLD", self.custom_profile.id, "Older completed")
        older.status = "Completed"
        older.completed_at = datetime.now() - timedelta(days=2)
        newer = self._task("ACT-PERM-COMP-NEW", self.custom_profile.id, "Newer completed fallback")
        newer.status = "Completed"
        newer.completed_at = None
        self.db.add_all([older, newer])
        self.db.flush()
        approved_at = datetime.now() - timedelta(hours=2)
        self.db.add(TaskSubmission(
            activity_id=newer.id,
            employee_id=self.custom_profile.id,
            recorded_by_user_id=self.custom_user.id,
            reviewed_by_user_id=self.manager.id,
            attempt_number=1,
            review_status="Approved",
            reviewed_at=approved_at,
            submitted_at=approved_at - timedelta(minutes=10),
        ))
        self.db.commit()

        rows = my_tasks(False, self.db, self.custom_user, view="completed")
        selected = [row for row in rows if row.id in {older.id, newer.id}]
        self.assertEqual([row.id for row in selected], [newer.id, older.id])
        newer_response = next(row for row in selected if row.id == newer.id)
        self.assertIsNotNone(newer_response.completed_at)
        self.assertEqual(newer_response.completed_at.replace(microsecond=0), approved_at.replace(microsecond=0))

    def test_my_tasks_legacy_include_completed_query_remains_compatible(self):
        completed = self._task("ACT-PERM-LEGACY-COMP", self.custom_profile.id, "Legacy history")
        completed.status = "Completed"
        self.db.add(completed)
        self.db.commit()
        legacy_rows = my_tasks(True, self.db, self.custom_user)
        ids = {row.id for row in legacy_rows}
        self.assertIn(self.custom_task.id, ids)
        self.assertIn(completed.id, ids)

    def test_manager_has_staff_operations_but_not_admin_care_protocol_definition(self):
        employees = list_employees(False, False, self.db, self.manager)
        self.assertEqual(len(employees), 3)
        calendar = staff_calendar(date.today(), date.today(), None, self.db, self.manager)
        self.assertIn("tasks", calendar)
        _require_workforce_access(self.manager, "review_task")
        self.assert_http_status(
            403,
            lambda: _require_workforce_access(self.manager, "create_care_template"),
        )


    def test_system_administrator_has_admin_workforce_authority_but_no_tasks_without_employee_link(self):
        _require_workforce_access(self.admin, "create_care_template")
        employees = list_employees(False, False, self.db, self.admin)
        self.assertEqual(len(employees), 3)
        self.assert_http_status(409, lambda: my_tasks(False, self.db, self.admin))

    def test_owner_admin_is_not_farm_staff_until_linked_to_employee_profile(self):
        self.assert_http_status(409, lambda: my_tasks(False, self.db, self.owner))

        owner_employee = Employee(
            employee_code="EMP-PERM-OWNER",
            full_name="Owner Farm Worker Profile",
            position="Owner",
            employment_status="Active",
            login_user_id=self.owner.id,
        )
        self.db.add(owner_employee)
        self.db.flush()
        owner_task = self._task("ACT-PERM-OWNER", owner_employee.id, "Owner assigned farm task")
        self.db.add(owner_task)
        self.db.commit()

        mine = my_tasks(False, self.db, self.owner)
        self.assertEqual([row.id for row in mine], [owner_task.id])
        _require_workforce_access(self.owner, "create_care_template")

    def test_manager_can_link_owner_account_without_overwriting_admin_identity(self):
        original_name = self.owner.full_name
        original_status = self.owner.status
        target = Employee(
            employee_code="EMP-PERM-LINK",
            full_name="Owner Operational Profile",
            email="different@example.test",
            position="Farm Coverage",
            employment_status="Active",
        )
        self.db.add(target)
        self.db.commit()

        result = update_employee(
            target.id,
            EmployeeUpdate(login_user_id=self.owner.id),
            self.db,
            self.manager,
        )
        self.assertEqual(result["login_user_id"], self.owner.id)
        self.db.refresh(self.owner)
        self.assertEqual(self.owner.role.name, "Owner")
        self.assertEqual(self.owner.full_name, original_name)
        self.assertEqual(self.owner.status, original_status)


if __name__ == "__main__":
    unittest.main()
