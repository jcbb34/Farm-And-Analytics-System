import os
import sys
import unittest
from datetime import date, time, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

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
from app.core.farm_time import farm_today
from app.models import (
    AuditLog,
    Crop,
    Employee,
    FarmActivity,
    Role,
    StaffAttendance,
    StaffLeave,
    User,
)
from app.routers import workforce
from app.schemas.workforce import (
    AttendanceUpsert,
    LeaveCancelRequest,
    TaskAssignmentUpdate,
)
from app.services.task_engine import _upsert_automatic_task
from app.services.workforce_assignment_service import (
    recalculate_employee_task_availability,
)


class WorkforceAssignmentAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.manager = SimpleNamespace(
            id=None,
            full_name="Farm Manager",
            permissions=["workforce:manage", "workforce:attendance"],
        )
        self.employee_role = Role(name="Employee", description="Employee task account")
        self.employee_role.set_permissions(["workforce:submit"])
        self.db.add(self.employee_role)
        self.db.flush()
        self.regular = self._employee("EMP-REGULAR", "Regular Worker")
        self.cover = self._employee("EMP-COVER", "Cover Worker")
        self.crop = Crop(
            crop_code="CRP-ASSIGNMENT-1",
            name="Eggplant",
            variety="Long Purple",
            field="Field A",
            area_hectares=0.5,
            current_growth=20,
            growth_stage="Seedling",
            quantity_planted=100,
            current_surviving=100,
            status="Planted",
            planting_date=date(2026, 9, 1),
            estimated_harvest=date(2026, 12, 1),
            fertilizer_quantity_kg=0,
            assigned_employee_id=self.regular.id,
            is_archived=False,
        )
        self.db.add(self.crop)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _employee(self, code, name):
        suffix = code.lower().replace("emp-", "")
        user = User(
            user_code=f"USR-{code}",
            full_name=name,
            username=f"portal.{suffix}",
            password_hash="test",
            role=self.employee_role,
            status="Active",
        )
        self.db.add(user)
        self.db.flush()
        employee = Employee(
            employee_code=code,
            full_name=name,
            employment_status="Active",
            is_archived=False,
            login_user_id=user.id,
        )
        self.db.add(employee)
        self.db.flush()
        return employee

    def _upsert(self, source_key, work_date, source_record_id=None):
        return _upsert_automatic_task(
            self.db,
            source_key=source_key,
            source_module="Crop",
            source_type="crop_growth_check",
            source_record_id=source_record_id or self.crop.id,
            source_detail_id=None,
            source_code=self.crop.crop_code,
            source_path="/crops",
            name="Inspect Crop Growth",
            category="Crop Monitoring",
            related_to=self.crop.name,
            location=self.crop.field,
            description="Record crop growth.",
            activity_date=work_date,
            start_time=time(8, 0),
            assigned_to="Farm Staff",
            priority="Medium",
        )

    def test_manager_reassignment_survives_scheduler_and_is_audited(self):
        task, result = self._upsert(
            "crop:growth:assignment-test",
            date(2026, 9, 15),
        )
        self.assertEqual(result, "created")
        self.assertEqual(task.assigned_employee_id, self.regular.id)

        with patch.object(workforce, "_require_manager", return_value=None):
            workforce.update_task_assignment(
                task.id,
                TaskAssignmentUpdate(
                    employee_id=self.cover.id,
                    reason="Covering approved sick leave",
                ),
                self.db,
                self.manager,
            )

        task = self.db.get(FarmActivity, task.id)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assigned_by, self.manager.full_name)
        self.assertFalse(task.needs_reassignment)

        task_after_scheduler, result = self._upsert(
            "crop:growth:assignment-test",
            date(2026, 9, 15),
        )
        self.assertEqual(result, "updated")
        self.assertEqual(task_after_scheduler.assigned_employee_id, self.cover.id)
        self.assertEqual(task_after_scheduler.assigned_by, self.manager.full_name)

        history = self.db.scalar(
            select(AuditLog).where(
                AuditLog.event_type == "audit",
                AuditLog.action == "Task reassigned",
                AuditLog.entity_id == str(task.id),
            )
        )
        self.assertIsNotNone(history)
        self.assertIn("Regular Worker", history.details)
        self.assertIn("Cover Worker", history.details)
        self.assertIn("Manager Reassignment", history.details)
        self.assertIn("Covering approved sick leave", history.details)

        future_task, _ = self._upsert(
            "crop:growth:next-occurrence",
            date(2026, 9, 22),
        )
        self.assertEqual(future_task.assigned_employee_id, self.regular.id)

    def test_future_automatic_task_during_approved_leave_is_flagged(self):
        self.db.add(
            StaffLeave(
                employee_id=self.regular.id,
                leave_type="Vacation Leave",
                start_date=date(2026, 9, 20),
                end_date=date(2026, 9, 25),
                status="Approved",
            )
        )
        self.db.flush()

        task, _ = self._upsert(
            "crop:growth:during-leave",
            date(2026, 9, 22),
        )

        self.assertIsNone(task.assigned_employee_id)
        self.assertEqual(task.assignment_source, "Leave Coverage")
        self.assertTrue(task.needs_reassignment)

    def test_absent_then_present_recalculates_open_task(self):
        # Attendance confirmation is intentionally prohibited for future dates.
        # Keep this regression anchored to a completed/present work date.
        attendance_date = farm_today() - timedelta(days=1)
        task, _ = self._upsert(
            "crop:growth:attendance",
            attendance_date,
        )
        self.assertFalse(task.needs_reassignment)

        with patch.object(workforce, "_manager", return_value=True):
            workforce.upsert_attendance(
                AttendanceUpsert(
                    employee_id=self.regular.id,
                    attendance_date=attendance_date,
                    status="Absent",
                ),
                self.db,
                self.manager,
            )
        self.assertTrue(self.db.get(FarmActivity, task.id).needs_reassignment)

        with patch.object(workforce, "_manager", return_value=True):
            workforce.upsert_attendance(
                AttendanceUpsert(
                    employee_id=self.regular.id,
                    attendance_date=attendance_date,
                    status="Present",
                ),
                self.db,
                self.manager,
            )
        self.assertFalse(self.db.get(FarmActivity, task.id).needs_reassignment)

    def test_cancelling_past_leave_keeps_unassigned_task_flagged(self):
        leave_start = farm_today() - timedelta(days=2)
        leave = StaffLeave(
            employee_id=self.regular.id,
            leave_type="Emergency Leave",
            start_date=leave_start,
            end_date=leave_start + timedelta(days=1),
            status="Approved",
        )
        self.db.add(leave)
        self.db.flush()
        task, _ = self._upsert(
            "crop:growth:cancelled-leave",
            leave_start,
        )
        self.assertTrue(task.needs_reassignment)

        with patch.object(workforce, "_require_manager", return_value=None):
            response = workforce.cancel_leave(
                leave.id,
                LeaveCancelRequest(reason="Employee is available again"),
                self.db,
                self.manager,
            )

        self.assertEqual(response.status, "Cancelled")
        # Cancelling a past leave does not assign unfinished historical work.
        # Until someone takes the unassigned task, it still needs reassignment.
        task = self.db.get(FarmActivity, task.id)
        self.assertIsNone(task.assigned_employee_id)
        self.assertTrue(task.needs_reassignment)

    def test_completed_and_archived_tasks_are_not_reassigned(self):
        task, _ = self._upsert(
            "crop:growth:completed",
            date(2026, 9, 12),
        )
        task.assigned_employee_id = self.cover.id
        task.assigned_to = self.cover.full_name
        task.assigned_by = self.manager.full_name
        task.status = "Completed"
        self.db.flush()

        unchanged, result = self._upsert(
            "crop:growth:completed",
            date(2026, 9, 12),
        )
        self.assertEqual(result, "unchanged")
        self.assertEqual(unchanged.assigned_employee_id, self.cover.id)

        with patch.object(workforce, "_require_manager", return_value=None):
            with self.assertRaises(HTTPException) as caught:
                workforce.update_task_assignment(
                    task.id,
                    TaskAssignmentUpdate(
                        employee_id=self.regular.id,
                        reason="Should be rejected",
                    ),
                    self.db,
                    self.manager,
                )
        self.assertEqual(caught.exception.status_code, 400)

        task.status = "Pending"
        task.is_archived = True
        self.db.flush()
        unchanged, result = self._upsert(
            "crop:growth:completed",
            date(2026, 9, 12),
        )
        self.assertEqual(result, "unchanged")
        self.assertEqual(unchanged.assigned_employee_id, self.cover.id)

    def test_inactive_employee_flag_clears_after_reactivation(self):
        task, _ = self._upsert(
            "crop:growth:employment-status",
            date(2026, 9, 30),
        )
        self.regular.employment_status = "Inactive"
        self.db.flush()
        recalculate_employee_task_availability(self.db, self.regular.id)
        self.assertTrue(task.needs_reassignment)

        self.regular.employment_status = "Active"
        self.db.flush()
        recalculate_employee_task_availability(self.db, self.regular.id)
        self.assertFalse(task.needs_reassignment)


if __name__ == "__main__":
    unittest.main()
