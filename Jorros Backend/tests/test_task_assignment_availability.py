import os
import sys
import unittest
from datetime import date, timedelta
from types import ModuleType

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Keep tests isolated from developer/private SQL Server configuration.
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
    test_security_module = ModuleType("app.core.security")

    def _unused_security_stub(*args, **kwargs):
        return None

    for _name in (
        "create_access_token",
        "create_two_factor_challenge",
        "decode_access_token",
        "decode_access_token_claims",
        "decode_two_factor_challenge",
        "hash_password",
        "verify_password",
    ):
        setattr(test_security_module, _name, _unused_security_stub)
    sys.modules["app.core.security"] = test_security_module

from app.core.database import Base
from app.models import (  # noqa: F401 - registers all mapped tables
    Crop,
    Employee,
    FarmActivity,
    Role,
    StaffAttendance,
    StaffLeave,
    TaskAssignmentHistory,
    User,
)
from app.routers.workforce import (
    cancel_leave,
    create_leave,
    update_task_assignment,
    upsert_attendance,
)
from app.schemas.workforce import (
    AttendanceUpsert,
    LeaveCreate,
    TaskAssignmentUpdate,
)
from app.services.task_engine import evaluate_automatic_tasks


class AutomaticTaskAssignmentAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()
        self.today = date.today()

        role = Role(name="Admin", description="Test administrator")
        employee_role = Role(name="Employee", description="Employee task account")
        employee_role.set_permissions(["workforce:submit"])
        self.admin = User(
            user_code="USR-ASSIGN-ADMIN",
            full_name="Assignment Manager",
            username="assignment.manager",
            password_hash="not-a-real-password-hash",
            role=role,
        )
        regular_user = User(
            user_code="USR-ASSIGN-REGULAR",
            full_name="Regular Employee",
            username="assignment.regular",
            password_hash="not-a-real-password-hash",
            role=employee_role,
            status="Active",
        )
        cover_user = User(
            user_code="USR-ASSIGN-COVER",
            full_name="Cover Employee",
            username="assignment.cover",
            password_hash="not-a-real-password-hash",
            role=employee_role,
            status="Active",
        )
        self.db.add_all([role, employee_role, self.admin, regular_user, cover_user])
        self.db.flush()
        self.regular = Employee(
            employee_code="EMP-REGULAR",
            full_name="Regular Employee",
            employment_status="Active",
            login_user_id=regular_user.id,
        )
        self.cover = Employee(
            employee_code="EMP-COVER",
            full_name="Cover Employee",
            employment_status="Active",
            login_user_id=cover_user.id,
        )
        self.db.add_all([self.regular, self.cover])
        self.db.flush()

        self.crop = Crop(
            crop_code="CRP-ASSIGN-001",
            name="Eggplant",
            variety="Test Variety",
            field="Field A",
            area_hectares=0.50,
            current_growth=30,
            growth_stage="Vegetative",
            quantity_planted=20,
            current_surviving=20,
            status="Growing",
            planting_date=self.today,
            estimated_harvest=self.today + timedelta(days=60),
            fertilizer_quantity_kg=0,
            watering_schedule="Daily | Morning",
            assigned_employee_id=self.regular.id,
        )
        self.db.add(self.crop)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _watering_task(self, task_date: date) -> FarmActivity:
        key = f"crop:watering:{self.crop.id}:{task_date.isoformat()}:morning"
        task = self.db.scalar(select(FarmActivity).where(FarmActivity.source_key == key))
        self.assertIsNotNone(task, f"Expected watering occurrence {key}")
        return task

    def test_manager_reassignment_persists_across_scheduler_runs_and_is_audited(self):
        self.db.add(
            StaffAttendance(
                employee_id=self.regular.id,
                attendance_date=self.today,
                status="Absent",
                recorded_by_user_id=self.admin.id,
            )
        )
        self.db.commit()

        evaluate_automatic_tasks(self.db)
        task = self._watering_task(self.today)
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(task.assignment_source, "automatic_default")
        self.assertTrue(task.needs_reassignment)

        update_task_assignment(
            task.id,
            TaskAssignmentUpdate(
                employee_id=self.cover.id,
                reason="Covering the regular employee's approved absence.",
            ),
            self.db,
            self.admin,
        )
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assignment_source, "reassignment")
        self.assertFalse(task.needs_reassignment)

        # The source record still points at the regular employee. A scheduler
        # pass must preserve the manager's task-occurrence reassignment.
        self.assertEqual(self.crop.assigned_employee_id, self.regular.id)
        evaluate_automatic_tasks(self.db)
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assigned_to, self.cover.full_name)
        self.assertEqual(task.assignment_source, "reassignment")
        self.assertFalse(task.needs_reassignment)

        history = list(
            self.db.scalars(
                select(TaskAssignmentHistory)
                .where(TaskAssignmentHistory.activity_id == task.id)
                .order_by(TaskAssignmentHistory.id)
            ).all()
        )
        self.assertEqual(len(history), 2)
        self.assertIsNone(history[0].old_employee_id)
        self.assertEqual(history[0].new_employee_id, self.regular.id)
        self.assertEqual(history[0].assignment_source, "automatic_default")
        self.assertEqual(history[0].actor_name, "System")
        self.assertEqual(history[1].old_employee_id, self.regular.id)
        self.assertEqual(history[1].new_employee_id, self.cover.id)
        self.assertEqual(history[1].assignment_source, "reassignment")
        self.assertEqual(history[1].actor_user_id, self.admin.id)
        self.assertIn("approved absence", history[1].reason)

    def test_manager_override_source_persists_when_reassignment_is_not_required(self):
        evaluate_automatic_tasks(self.db)
        task = self._watering_task(self.today)
        self.assertFalse(task.needs_reassignment)

        update_task_assignment(
            task.id,
            TaskAssignmentUpdate(
                employee_id=self.cover.id,
                reason="Manager chose a different employee for this occurrence.",
            ),
            self.db,
            self.admin,
        )
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assignment_source, "manager_override")

        evaluate_automatic_tasks(self.db)
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assignment_source, "manager_override")
        self.assertFalse(task.needs_reassignment)

    def test_future_automatic_task_created_during_approved_leave_is_flagged(self):
        task_date = self.today + timedelta(days=3)
        self.db.add(
            StaffLeave(
                employee_id=self.regular.id,
                leave_type="Vacation Leave",
                start_date=task_date,
                end_date=task_date,
                status="Approved",
                reason="Approved test leave",
                recorded_by_user_id=self.admin.id,
            )
        )
        self.db.commit()

        evaluate_automatic_tasks(self.db)
        task = self._watering_task(task_date)
        self.assertIsNone(task.assigned_employee_id)
        self.assertEqual(task.assignment_source, "Leave Coverage")
        self.assertTrue(task.needs_reassignment)

    def test_absence_to_present_recalculates_reassignment_flag(self):
        evaluate_automatic_tasks(self.db)
        task = self._watering_task(self.today)
        self.assertFalse(task.needs_reassignment)

        upsert_attendance(
            AttendanceUpsert(
                employee_id=self.regular.id,
                attendance_date=self.today,
                status="Absent",
                notes="Unavailable today",
            ),
            self.db,
            self.admin,
        )
        self.db.refresh(task)
        self.assertTrue(task.needs_reassignment)

        upsert_attendance(
            AttendanceUpsert(
                employee_id=self.regular.id,
                attendance_date=self.today,
                status="Present",
                notes="Attendance corrected",
            ),
            self.db,
            self.admin,
        )
        self.db.refresh(task)
        self.assertFalse(task.needs_reassignment)

    def test_cancelling_leave_recalculates_reassignment_flag(self):
        task_date = self.today + timedelta(days=2)
        evaluate_automatic_tasks(self.db)
        task = self._watering_task(task_date)
        self.assertFalse(task.needs_reassignment)

        leave = create_leave(
            LeaveCreate(
                employee_id=self.regular.id,
                leave_type="Vacation Leave",
                start_date=task_date,
                end_date=task_date,
                reason="Planned leave",
            ),
            self.db,
            self.admin,
        )
        self.db.refresh(task)
        self.assertEqual(leave.status, "Approved")
        self.assertTrue(task.needs_reassignment)

        cancelled = cancel_leave(leave.id, self.db, self.admin)
        self.db.refresh(task)
        self.assertEqual(cancelled.status, "Cancelled")
        self.assertFalse(task.needs_reassignment)

    def test_completed_task_assignment_is_protected(self):
        evaluate_automatic_tasks(self.db)
        task = self._watering_task(self.today)
        self.assertEqual(task.assigned_employee_id, self.regular.id)

        task.status = "Completed"
        self.db.commit()
        self.crop.assigned_employee_id = self.cover.id
        self.db.commit()

        evaluate_automatic_tasks(self.db)
        self.db.refresh(task)
        self.assertEqual(task.status, "Completed")
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(task.assignment_source, "automatic_default")

        with self.assertRaises(HTTPException) as caught:
            update_task_assignment(
                task.id,
                TaskAssignmentUpdate(employee_id=self.cover.id, reason="Should be blocked"),
                self.db,
                self.admin,
            )
        self.assertEqual(caught.exception.status_code, 400)
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.regular.id)


if __name__ == "__main__":
    unittest.main()
