import os
import sys
import unittest
from datetime import date, time, timedelta
from types import ModuleType

from pydantic import ValidationError
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
    test_database_module.get_db = lambda: iter((None,))
    sys.modules.setdefault("app.core.database", test_database_module)

try:
    import pyotp  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pyotp"] = ModuleType("pyotp")

try:
    import pwdlib  # noqa: F401
except ModuleNotFoundError:
    test_security_module = ModuleType("app.core.security")
    for _name in (
        "create_access_token", "create_two_factor_challenge", "decode_access_token",
        "decode_access_token_claims", "decode_two_factor_challenge", "hash_password", "verify_password",
    ):
        setattr(test_security_module, _name, lambda *args, **kwargs: None)
    sys.modules["app.core.security"] = test_security_module

from app.core.database import Base
from app.core.farm_time import farm_today
from app.models import (  # noqa: F401
    Employee,
    EmployeeWorkSchedule,
    EmployeeWorkScheduleDay,
    FarmActivity,
    StaffAttendance,
    StaffLeave,
    StaffShift,
    TaskAssignmentHistory,
)
from app.schemas.workforce import EmployeeCreate
from app.services.work_schedule_service import (
    REST_COVERAGE_SOURCE,
    apply_schedule_aware_assignment,
    reconcile_employee_future_tasks,
    resolve_employee_availability,
)


class RestDayScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.today = farm_today()
        self.sunday = self.today + timedelta(days=(6 - self.today.weekday()) % 7 or 7)
        self.monday = self.sunday + timedelta(days=1)
        self.john = self._employee("EMP-JOHN", "Test Worker One")
        self.step = self._employee("EMP-STEP", "Step Cover")
        self.other = self._employee("EMP-OTHER", "Other Cover")
        self.schedule = self._schedule(self.john, backup=self.step)
        self._schedule(self.step, backup=None, sunday_rest=False)
        self._schedule(self.other, backup=None, sunday_rest=False)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _employee(self, code, name):
        row = Employee(employee_code=code, full_name=name, employment_status="Active", is_archived=False)
        self.db.add(row)
        self.db.flush()
        return row

    def _schedule(self, employee, *, backup=None, sunday_rest=True):
        schedule = EmployeeWorkSchedule(
            employee_id=employee.id,
            effective_from=self.today - timedelta(days=30),
            timezone="Asia/Manila",
            schedule_type="Fixed",
            backup_employee_id=backup.id if backup else None,
            status="Active",
        )
        self.db.add(schedule)
        self.db.flush()
        for dow in range(7):
            working = not (sunday_rest and dow == 6)
            self.db.add(EmployeeWorkScheduleDay(
                schedule_id=schedule.id,
                day_of_week=dow,
                is_working_day=working,
                start_time=time(8, 0) if working else None,
                end_time=time(17, 0) if working else None,
                break_start_time=time(12, 0) if working else None,
                break_end_time=time(13, 0) if working else None,
            ))
        self.db.flush()
        return schedule

    def _task(self, when, *, backup_id=None, source="automatic_default", assigned=None, status="Pending"):
        assigned = self.john if assigned is None else assigned
        task = FarmActivity(
            activity_code=f"T-{when.isoformat()}-{len(self.db.new)}-{source}",
            name="Water Eggplant",
            category="Crop Care",
            related_to="Eggplant",
            location="Field A",
            activity_date=when,
            start_time=time(7, 0),
            assigned_by="System",
            assigned_to=assigned.full_name if assigned else "Unassigned",
            assigned_employee_id=assigned.id if assigned else None,
            assignment_source=source,
            default_employee_id=self.john.id,
            backup_employee_id=backup_id,
            time_sensitive=True,
            controlled_rescheduling=False,
            status=status,
            priority="High",
            is_automatic=True,
            source_module="Crop",
            source_type="watering",
            source_key=f"crop:watering:test:{when.isoformat()}:{source}:{len(self.db.new)}",
            is_archived=False,
        )
        self.db.add(task)
        self.db.flush()
        return task

    def test_employee_creation_requires_complete_weekly_schedule(self):
        with self.assertRaises(ValidationError):
            EmployeeCreate(full_name="New Employee")

    def test_sunday_occurrence_uses_configured_schedule_backup(self):
        task = self._task(self.sunday)
        result = apply_schedule_aware_assignment(self.db, task)
        self.assertEqual(result, "covered")
        self.assertEqual(task.assigned_employee_id, self.step.id)
        self.assertEqual(task.assignment_source, REST_COVERAGE_SOURCE)
        self.assertFalse(task.needs_reassignment)
        history = self.db.scalar(select(TaskAssignmentHistory).where(TaskAssignmentHistory.activity_id == task.id))
        self.assertEqual(history.default_employee_id, self.john.id)
        self.assertEqual(history.new_employee_id, self.step.id)
        self.assertEqual(history.coverage_date, self.sunday)
        self.assertIn("scheduled rest day", history.reason)

    def test_task_specific_backup_precedes_weekly_schedule_backup(self):
        task = self._task(self.sunday, backup_id=self.other.id)
        result = apply_schedule_aware_assignment(self.db, task)
        self.assertEqual(result, "covered")
        self.assertEqual(task.assigned_employee_id, self.other.id)
        self.assertNotEqual(task.assigned_employee_id, self.step.id)

    def test_unavailable_backup_keeps_required_task_and_marks_needs_coverage(self):
        step_sunday = resolve_employee_availability(self.db, self.step.id, self.sunday)
        self.assertTrue(step_sunday.available)
        self.db.add(StaffLeave(
            employee_id=self.step.id,
            leave_type="Vacation Leave",
            start_date=self.sunday,
            end_date=self.sunday,
            status="Approved",
        ))
        self.db.flush()
        task = self._task(self.sunday)
        result = apply_schedule_aware_assignment(self.db, task)
        self.assertEqual(result, "needs-coverage")
        self.assertIsNone(task.assigned_employee_id)
        self.assertTrue(task.needs_reassignment)
        self.assertEqual(task.assignment_source, REST_COVERAGE_SOURCE)

    def test_monday_occurrence_returns_to_default_employee(self):
        task = self._task(self.monday)
        result = apply_schedule_aware_assignment(self.db, task)
        self.assertEqual(result, "default")
        self.assertEqual(task.assigned_employee_id, self.john.id)
        self.assertEqual(task.assignment_source, "automatic_default")

    def test_completed_sunday_coverage_remains_credited_to_covering_employee(self):
        task = self._task(self.sunday, source=REST_COVERAGE_SOURCE, assigned=self.step, status="Completed")
        result = apply_schedule_aware_assignment(self.db, task)
        self.assertEqual(result, "protected")
        self.assertEqual(task.assigned_employee_id, self.step.id)
        self.assertEqual(task.assignment_source, REST_COVERAGE_SOURCE)

    def test_approved_leave_beats_working_day_override(self):
        self.db.add(StaffShift(
            employee_id=self.john.id,
            work_date=self.sunday,
            start_time=time(8, 0),
            end_time=time(17, 0),
            status="Scheduled",
            exception_type="Working Day Override",
            exception_reason="Special Sunday work",
        ))
        self.db.add(StaffLeave(
            employee_id=self.john.id,
            leave_type="Emergency Leave",
            start_date=self.sunday,
            end_date=self.sunday,
            status="Approved",
        ))
        self.db.flush()
        availability = resolve_employee_availability(self.db, self.john.id, self.sunday)
        self.assertFalse(availability.available)
        self.assertEqual(availability.status, "On Leave")
        self.assertIsNotNone(availability.leave_id)

    def test_present_attendance_does_not_override_weekly_rest_day(self):
        self.db.add(StaffAttendance(employee_id=self.john.id, attendance_date=self.sunday, status="Present"))
        self.db.flush()
        availability = resolve_employee_availability(self.db, self.john.id, self.sunday, allow_future_attendance=True)
        self.assertFalse(availability.available)
        self.assertEqual(availability.status, "Rest Day")
        self.assertIsNone(availability.attendance_status)

    def test_dated_working_override_affects_only_selected_sunday(self):
        self.db.add(StaffShift(
            employee_id=self.john.id,
            work_date=self.sunday,
            start_time=time(9, 0),
            end_time=time(16, 0),
            status="Scheduled",
            exception_type="Working Day Override",
        ))
        self.db.flush()
        selected = resolve_employee_availability(self.db, self.john.id, self.sunday)
        following = resolve_employee_availability(self.db, self.john.id, self.sunday + timedelta(days=7))
        self.assertTrue(selected.available)
        self.assertEqual(selected.status, "Working Day")
        self.assertFalse(following.available)
        self.assertEqual(following.status, "Rest Day")

    def test_schedule_change_reconciles_future_coverage_but_preserves_manager_override(self):
        covered = self._task(self.sunday)
        self.assertEqual(apply_schedule_aware_assignment(self.db, covered), "covered")
        overridden = self._task(self.sunday + timedelta(days=7), source="manager_override", assigned=self.step)
        sunday_day = self.db.scalar(select(EmployeeWorkScheduleDay).where(
            EmployeeWorkScheduleDay.schedule_id == self.schedule.id,
            EmployeeWorkScheduleDay.day_of_week == 6,
        ))
        sunday_day.is_working_day = True
        sunday_day.start_time = time(8, 0)
        sunday_day.end_time = time(17, 0)
        self.db.flush()
        summary = reconcile_employee_future_tasks(self.db, self.john.id, from_date=self.sunday)
        self.assertGreaterEqual(summary["checked"], 1)
        self.assertEqual(covered.assigned_employee_id, self.john.id)
        self.assertEqual(covered.assignment_source, "automatic_default")
        self.assertEqual(overridden.assigned_employee_id, self.step.id)
        self.assertEqual(overridden.assignment_source, "manager_override")

    def test_repeated_scheduler_assignment_is_idempotent_for_history(self):
        task = self._task(self.sunday)
        self.assertEqual(apply_schedule_aware_assignment(self.db, task), "covered")
        self.db.flush()
        first_count = len(list(self.db.scalars(select(TaskAssignmentHistory).where(TaskAssignmentHistory.activity_id == task.id)).all()))
        self.assertEqual(apply_schedule_aware_assignment(self.db, task), "covered")
        self.db.flush()
        second_count = len(list(self.db.scalars(select(TaskAssignmentHistory).where(TaskAssignmentHistory.activity_id == task.id)).all()))
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)


if __name__ == "__main__":
    unittest.main()
