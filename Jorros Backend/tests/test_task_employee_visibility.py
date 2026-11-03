import os
import sys
import unittest
from datetime import date, time, timedelta
from types import ModuleType

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session
from starlette.responses import Response

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
from app.models import (  # noqa: F401
    Employee,
    FarmActivity,
    Role,
    StaffAttendance,
    TaskAssignmentHistory,
    User,
)
from app.routers.workforce import (
    create_employee,
    list_employees,
    list_tasks,
    my_tasks,
    my_tasks_summary,
    repair_employee_account_links,
    update_task_assignment,
)
from app.schemas.workforce import (
    EmployeeCreate,
    TaskAssignmentUpdate,
    WeeklyScheduleInput,
    WorkScheduleDayInput,
)
from app.services.work_schedule_service import reconcile_employee_future_tasks


class TaskEmployeeVisibilityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.today = date.today()

        self.manager_role = Role(name="Manager", description="Manager")
        self.manager_role.set_permissions(["workforce:manage", "workforce:review", "workforce:attendance"])
        self.employee_role = Role(name="Employee", description="Employee")
        self.employee_role.set_permissions(["workforce:submit"])
        self.db.add_all([self.manager_role, self.employee_role])
        self.db.flush()

        # Deliberately create several authentication rows before employee rows so
        # User IDs cannot accidentally equal Employee IDs in the regression test.
        self.manager = self._user("USR-VIS-MGR", "Farm Manager", "visibility.manager", self.manager_role)
        self._user("USR-VIS-FILL-1", "Filler One", "visibility.fill1", self.manager_role)
        self._user("USR-VIS-FILL-2", "Filler Two", "visibility.fill2", self.manager_role)
        self.john_user = self._user("USR-VIS-JOHN", "John Worker", "visibility.john", self.employee_role, "john@farm.test")
        self.steph_user = self._user("USR-VIS-STEPH", "Stephanie Worker", "visibility.steph", self.employee_role, "steph@farm.test")
        self.db.flush()

        self.john = self._employee("EMP-VIS-JOHN", "John Worker", self.john_user.id, "john@farm.test")
        self.steph = self._employee("EMP-VIS-STEPH", "Stephanie Worker", self.steph_user.id, "steph@farm.test")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _user(self, code, name, username, role, email=None, *, status="Active"):
        row = User(
            user_code=code,
            full_name=name,
            username=username,
            email=email,
            password_hash="test",
            role=role,
            status=status,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _employee(self, code, name, login_user_id=None, email=None, *, status="Active"):
        row = Employee(
            employee_code=code,
            full_name=name,
            email=email,
            employment_status=status,
            login_user_id=login_user_id,
            is_archived=False,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _task(
        self,
        code,
        employee,
        *,
        status="Pending",
        activity_date=None,
        source="manual",
        needs_reassignment=False,
        archived=False,
        automatic=False,
    ):
        row = FarmActivity(
            activity_code=code,
            name=f"Task {code}",
            category="General Care",
            related_to="Visibility Regression",
            location="Jorros Farm",
            activity_date=activity_date or self.today,
            start_time=time(8, 0),
            assigned_by="Farm Manager",
            assigned_to=employee.full_name,
            assigned_employee_id=employee.id,
            default_employee_id=employee.id,
            assignment_source=source,
            status=status,
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
            needs_reassignment=needs_reassignment,
            is_archived=archived,
            is_automatic=automatic,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _fixed_schedule(self):
        days = []
        for day_of_week in range(7):
            if day_of_week == 6:
                days.append(WorkScheduleDayInput(day_of_week=day_of_week, state="Rest Day"))
            else:
                days.append(
                    WorkScheduleDayInput(
                        day_of_week=day_of_week,
                        state="Working Day",
                        start_time=time(8, 0),
                        end_time=time(17, 0),
                        break_start_time=time(12, 0),
                        break_end_time=time(13, 0),
                    )
                )
        return WeeklyScheduleInput(effective_from=self.today, days=days)

    def test_exact_john_to_stephanie_reassignment_is_visible_only_to_stephanie(self):
        task = self._task("ACT-VIS-001", self.john, automatic=True)
        self.db.commit()

        updated = update_task_assignment(
            task.id,
            TaskAssignmentUpdate(employee_id=self.steph.id, reason="Manager assigned Stephanie."),
            self.db,
            self.manager,
        )
        self.assertEqual(updated.assigned_employee_id, self.steph.id)
        self.assertNotEqual(self.steph.id, self.steph_user.id)
        self.assertEqual(self.db.get(FarmActivity, task.id).assigned_employee_id, self.steph.id)

        # Exercise the same future-task reconciliation path used after schedule changes.
        reconcile_employee_future_tasks(
            self.db,
            self.john.id,
            from_date=self.today,
            actor_user_id=self.manager.id,
            actor_name=self.manager.full_name,
        )
        self.db.commit()
        self.assertEqual(self.db.get(FarmActivity, task.id).assigned_employee_id, self.steph.id)

        response = Response()
        steph_rows = my_tasks(False, self.db, self.steph_user, view="active", response=response)
        john_rows = my_tasks(False, self.db, self.john_user, view="active")
        self.assertIn(task.id, [row.id for row in steph_rows])
        self.assertNotIn(task.id, [row.id for row in john_rows])
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["vary"], "Authorization")

        history = self.db.scalar(
            select(TaskAssignmentHistory).where(TaskAssignmentHistory.activity_id == task.id)
        )
        self.assertIsNotNone(history)
        self.assertEqual(history.old_employee_id, self.john.id)
        self.assertEqual(history.new_employee_id, self.steph.id)
        self.assertEqual(history.actor_user_id, self.manager.id)
        self.assertIn("Stephanie", history.reason)
        self.assertIsNotNone(history.changed_at)

    def test_employee_id_not_user_id_and_same_names_do_not_cross_assignments(self):
        same_user = self._user(
            "USR-VIS-SAME", "Stephanie Worker", "visibility.steph2", self.employee_role, "steph2@farm.test"
        )
        same_employee = self._employee(
            "EMP-VIS-SAME", "Stephanie Worker", same_user.id, "steph2@farm.test"
        )
        steph_task = self._task("ACT-VIS-STEPH", self.steph)
        same_task = self._task("ACT-VIS-SAME", same_employee)
        self.db.commit()

        self.assertNotEqual(self.steph.id, self.steph_user.id)
        self.assertEqual(steph_task.assigned_employee_id, self.steph.id)
        self.assertEqual([row.id for row in my_tasks(False, self.db, self.steph_user, view="active")], [steph_task.id])
        self.assertEqual([row.id for row in my_tasks(False, self.db, same_user, view="active")], [same_task.id])

    def test_needs_reassignment_coverage_overdue_returned_review_and_upcoming_remain_visible(self):
        rows = [
            self._task("ACT-VIS-NEEDS", self.steph, needs_reassignment=True),
            self._task("ACT-VIS-REST", self.steph, source="Rest-Day Coverage"),
            self._task("ACT-VIS-LEAVE", self.steph, source="Leave Coverage"),
            self._task("ACT-VIS-OVERDUE", self.steph, activity_date=self.today - timedelta(days=2)),
            self._task("ACT-VIS-RETURN", self.steph, status="Returned"),
            self._task("ACT-VIS-REVIEW", self.steph, status="Submitted for Review"),
            self._task("ACT-VIS-UPCOMING", self.steph, activity_date=self.today + timedelta(days=30)),
        ]
        self.db.commit()
        visible_ids = {row.id for row in my_tasks(False, self.db, self.steph_user, view="active")}
        self.assertEqual(visible_ids, {row.id for row in rows})

    def test_timeline_scope_avoids_far_future_payload_but_all_scope_and_summary_preserve_discoverability(self):
        overdue = self._task("ACT-PERF-OVERDUE", self.steph, activity_date=self.today - timedelta(days=2))
        near = self._task("ACT-PERF-NEAR", self.steph, activity_date=self.today + timedelta(days=5))
        far = self._task("ACT-PERF-FAR", self.steph, activity_date=self.today + timedelta(days=30))
        self.db.commit()

        timeline_ids = {row.id for row in my_tasks(False, self.db, self.steph_user, view="active", scope="timeline")}
        all_ids = {row.id for row in my_tasks(False, self.db, self.steph_user, view="active", scope="all")}
        self.assertEqual(timeline_ids, {overdue.id, near.id})
        self.assertEqual(all_ids, {overdue.id, near.id, far.id})

        summary = my_tasks_summary(self.db, self.steph_user)
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.missed, 1)
        self.assertEqual(summary.upcoming, 1)

    def test_completed_and_approved_are_history_not_active(self):
        completed = self._task("ACT-VIS-COMP", self.steph, status="Completed")
        approved = self._task("ACT-VIS-APP", self.steph, status="Approved")
        active = self._task("ACT-VIS-ACT", self.steph)
        self.db.commit()
        active_ids = {row.id for row in my_tasks(False, self.db, self.steph_user, view="active")}
        history_ids = {row.id for row in my_tasks(False, self.db, self.steph_user, view="history")}
        self.assertIn(active.id, active_ids)
        self.assertNotIn(completed.id, active_ids)
        self.assertNotIn(approved.id, active_ids)
        self.assertIn(completed.id, history_ids)
        self.assertIn(approved.id, history_ids)

    def test_task_only_user_cannot_query_another_employee_by_parameter(self):
        john_task = self._task("ACT-VIS-J2", self.john)
        steph_task = self._task("ACT-VIS-S2", self.steph)
        self.db.commit()
        rows = list_tasks(
            employee_id=self.steph.id,
            task_status=None,
            date_from=None,
            date_to=None,
            source_module=None,
            source_record_id=None,
            open_only=False,
            actionable_only=False,
            db=self.db,
            current_user=self.john_user,
        )
        self.assertEqual([row.id for row in rows], [john_task.id])
        self.assertNotIn(steph_task.id, [row.id for row in rows])

    def test_unlinked_account_returns_clear_error_instead_of_empty_tasks(self):
        orphan_login = self._user(
            "USR-VIS-ORPHAN", "Unlinked Worker", "visibility.orphan", self.employee_role, "orphan@farm.test"
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            my_tasks(False, self.db, orphan_login, view="active")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("not linked", str(ctx.exception.detail).lower())

    def test_manager_cannot_assign_portal_work_to_employee_without_login(self):
        unlinked = self._employee("EMP-VIS-NOLOGIN", "No Login Worker", None, "nologin@farm.test")
        task = self._task("ACT-VIS-NOLOGIN", self.john)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            update_task_assignment(
                task.id,
                TaskAssignmentUpdate(employee_id=unlinked.id, reason="Portal assignment"),
                self.db,
                self.manager,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("No Login Account", str(ctx.exception.detail))
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.john.id)

    def test_unavailable_assignment_requires_override_and_remains_visible_when_overridden(self):
        task = self._task("ACT-VIS-OVERRIDE", self.john)
        self.db.add(
            StaffAttendance(
                employee_id=self.steph.id,
                attendance_date=task.activity_date,
                status="Absent",
                recorded_by_user_id=self.manager.id,
            )
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            update_task_assignment(
                task.id,
                TaskAssignmentUpdate(employee_id=self.steph.id, reason="Need coverage"),
                self.db,
                self.manager,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("unavailable", str(ctx.exception.detail).lower())

        update_task_assignment(
            task.id,
            TaskAssignmentUpdate(
                employee_id=self.steph.id,
                reason="Authorized manager override despite absence",
                allow_unavailable_override=True,
            ),
            self.db,
            self.manager,
        )
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.steph.id)
        self.assertTrue(task.needs_reassignment)
        self.assertIn(task.id, [row.id for row in my_tasks(False, self.db, self.steph_user, view="active")])

    def test_employee_creation_creates_and_links_employee_role_account_transactionally(self):
        result = create_employee(
            EmployeeCreate(
                full_name="Portal Created Worker",
                email="created.worker@farm.test",
                create_login_account=True,
                login_username="created.worker",
                login_password="StrongPass123!",
                weekly_schedule=self._fixed_schedule(),
            ),
            self.db,
            self.manager,
        )
        employee = self.db.get(Employee, result["id"])
        linked = self.db.get(User, employee.login_user_id)
        self.assertIsNotNone(linked)
        self.assertEqual(linked.role.name, "Employee")
        self.assertEqual(linked.status, "Active")
        self.assertEqual(result["account_status"], "Account Linked")
        self.assertTrue(result["portal_assignment_ready"])

    def test_deterministic_email_repair_never_uses_name_only(self):
        candidate = self._user(
            "USR-VIS-REPAIR", "Different Display Name", "visibility.repair", self.employee_role, "repair@farm.test"
        )
        target = self._employee("EMP-VIS-REPAIR", "Repair Target", None, "repair@farm.test")
        name_only = self._employee("EMP-VIS-NAME", "Different Display Name", None, "nomatch@farm.test")
        self.db.commit()
        result = repair_employee_account_links(self.db, self.manager)
        self.db.refresh(target)
        self.db.refresh(name_only)
        self.assertEqual(target.login_user_id, candidate.id)
        self.assertIsNone(name_only.login_user_id)
        self.assertIn(target.id, [row["employee_id"] for row in result["repaired"]])

    def test_employee_list_exposes_account_health_and_username(self):
        broken = self._employee("EMP-VIS-BROKEN", "Broken Portal", None, "broken@farm.test")
        self.db.commit()
        rows = list_employees(False, False, self.db, self.manager)
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id[self.steph.id]["account_status"], "Account Linked")
        self.assertEqual(by_id[self.steph.id]["login_username"], self.steph_user.username)
        self.assertEqual(by_id[broken.id]["account_status"], "No Login Account")
        self.assertFalse(by_id[broken.id]["portal_assignment_ready"])


if __name__ == "__main__":
    unittest.main()
