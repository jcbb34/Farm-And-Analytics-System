import os
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, date, time, timedelta
from types import ModuleType, SimpleNamespace

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
    database_module = ModuleType("app.core.database")
    database_module.Base = _TestBase
    database_module.get_db = lambda: iter((None,))
    sys.modules.setdefault("app.core.database", database_module)

from app.core.database import Base
from app.core.farm_time import farm_today
from app.models import (  # noqa: F401
    AttendanceSettings,
    Employee,
    EmployeeWorkSchedule,
    EmployeeWorkScheduleDay,
    FarmActivity,
    StaffAttendance,
    StaffAttendanceAudit,
    StaffLeave,
    StaffShift,
    TaskAssignmentHistory,
)
from app.services.attendance_service import (
    AttendanceError,
    ATTENDANCE_COVERAGE_SOURCE,
    MANAGER_ASSISTED,
    SELF_SERVICE,
    check_in,
    check_out,
    correct_attendance,
    get_or_create_attendance_settings,
    set_confirmed_status,
)
from app.services.work_schedule_service import resolve_availability_range, resolve_employee_availability
from app.routers.workforce_handlers import bulk_mark_scheduled_present


class AttendanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        today = farm_today()
        self.monday = today - timedelta(days=today.weekday())
        self.tuesday = self.monday + timedelta(days=1)
        self.sunday = self.monday + timedelta(days=6)
        self.employee = self._employee("EMP-ATT-1", "Attendance Worker")
        self.backup = self._employee("EMP-ATT-2", "Attendance Backup")
        self._schedule(self.employee, backup=self.backup, sunday_rest=True)
        self._schedule(self.backup, backup=None, sunday_rest=False)
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _employee(self, code, name):
        row = Employee(employee_code=code, full_name=name, employment_status="Active", is_archived=False)
        self.db.add(row); self.db.flush(); return row

    def _schedule(self, employee, *, backup=None, sunday_rest=True):
        row = EmployeeWorkSchedule(
            employee_id=employee.id,
            effective_from=self.monday - timedelta(days=30),
            timezone="Asia/Manila",
            schedule_type="Fixed",
            backup_employee_id=backup.id if backup else None,
            status="Active",
        )
        self.db.add(row); self.db.flush()
        for dow in range(7):
            working = not (sunday_rest and dow == 6)
            self.db.add(EmployeeWorkScheduleDay(
                schedule_id=row.id, day_of_week=dow, is_working_day=working,
                start_time=time(7, 0) if working else None,
                end_time=time(16, 0) if working else None,
                break_start_time=time(12, 0) if working else None,
                break_end_time=time(13, 0) if working else None,
            ))
        self.db.flush(); return row

    def _task(self, when):
        task = FarmActivity(
            activity_code=f"ATT-TASK-{when.isoformat()}-{len(self.db.new)}",
            name="Feed livestock", category="Livestock Care", related_to="Batch A", location="Pen 1",
            activity_date=when, start_time=time(8, 0), assigned_by="System",
            assigned_to=self.employee.full_name, assigned_employee_id=self.employee.id,
            default_employee_id=self.employee.id, assignment_source="automatic_default",
            status="Pending", priority="High", is_automatic=True, time_sensitive=True,
            source_module="Livestock", source_type="livestock_feeding",
            source_key=f"attendance-test:{when.isoformat()}:{len(self.db.new)}", is_archived=False,
        )
        self.db.add(task); self.db.flush(); return task

    def test_server_controlled_self_check_in_on_time(self):
        server_now = datetime.combine(self.monday, time(6, 58))
        row = check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=server_now)
        self.assertEqual(row.check_in_at, server_now)
        self.assertEqual(row.status, "On Time")
        self.assertEqual(row.minutes_late, 0)
        self.assertEqual(row.attendance_source, SELF_SERVICE)

    def test_late_and_early_departure_calculation(self):
        check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(7, 6)))
        row = check_out(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(15, 30)))
        self.assertEqual(row.minutes_late, 6)
        self.assertEqual(row.status, "Early Departure")
        self.assertEqual(row.minutes_early, 30)

    def test_duplicate_check_in_and_checkout_are_idempotent(self):
        first = check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(7, 0)))
        second = check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(7, 10)))
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.check_in_at.time(), time(7, 0))
        out1 = check_out(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(16, 0)))
        out2 = check_out(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(16, 30)))
        self.assertEqual(out1.check_out_at, out2.check_out_at)

    def test_checkout_requires_check_in(self):
        with self.assertRaises(AttendanceError):
            check_out(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(16, 0)))

    def test_approved_leave_and_rest_day_block_self_service(self):
        self.db.add(StaffLeave(employee_id=self.employee.id, leave_type="Vacation Leave", start_date=self.tuesday, end_date=self.tuesday, status="Approved"))
        self.db.flush()
        with self.assertRaises(AttendanceError):
            check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.tuesday, time(7, 0)))
        with self.assertRaises(AttendanceError):
            check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.sunday, time(7, 0)))

    def test_manager_assisted_attendance_records_source(self):
        row = check_in(self.db, self.employee.id, actor_user_id=99, actor_name="Manager", source=MANAGER_ASSISTED, now=datetime.combine(self.monday, time(7, 2)))
        self.assertEqual(row.attendance_source, MANAGER_ASSISTED)
        self.assertEqual(row.recorded_by_user_id, 99)

    def test_missed_check_in_is_possible_absence_until_manager_confirms(self):
        before_cutoff = resolve_employee_availability(
            self.db,
            self.employee.id,
            self.monday,
            now=datetime.combine(self.monday, time(7, 19)),
        )
        self.assertEqual(before_cutoff.status, "Working Day")

        task = self._task(self.monday)
        after_cutoff = resolve_availability_range(
            self.db,
            [self.employee.id],
            self.monday,
            self.monday,
            now=datetime.combine(self.monday, time(7, 20)),
        )[0]
        self.assertEqual(after_cutoff.status, "Possible Absence")
        self.assertTrue(after_cutoff.available)
        self.assertIn("Manager confirmation", after_cutoff.reason)
        self.assertEqual(task.assigned_employee_id, self.employee.id)
        self.assertIsNone(self.db.scalar(select(StaffAttendance).where(
            StaffAttendance.employee_id == self.employee.id,
            StaffAttendance.attendance_date == self.monday,
        )))

        checked_in = check_in(
            self.db,
            self.employee.id,
            actor_user_id=1,
            actor_name="Worker",
            source=SELF_SERVICE,
            now=datetime.combine(self.monday, time(7, 21)),
        )
        self.assertEqual(checked_in.status, "Late")
        resolved = resolve_employee_availability(
            self.db,
            self.employee.id,
            self.monday,
            now=datetime.combine(self.monday, time(7, 22)),
        )
        self.assertEqual(resolved.status, "Working Day")
        self.assertEqual(resolved.attendance_status, "Late")

    def test_absent_reassigns_pending_task_to_configured_backup_once(self):
        task = self._task(self.monday)
        row, summary = set_confirmed_status(self.db, self.employee.id, self.monday, status="Absent", actor_user_id=99, actor_name="Manager", notes="No show")
        self.assertEqual(row.status, "Absent")
        self.assertEqual(summary["covered"], 1)
        self.assertEqual(task.assigned_employee_id, self.backup.id)
        self.assertEqual(task.assignment_source, ATTENDANCE_COVERAGE_SOURCE)
        set_confirmed_status(self.db, self.employee.id, self.monday, status="Absent", actor_user_id=99, actor_name="Manager", notes="No show")
        history = list(self.db.scalars(select(TaskAssignmentHistory).where(TaskAssignmentHistory.activity_id == task.id)).all())
        self.assertEqual(len(history), 1)

    def test_sick_without_available_backup_marks_needs_coverage(self):
        task = self._task(self.monday)
        self.backup.employment_status = "Inactive"; self.db.flush()
        _, summary = set_confirmed_status(self.db, self.employee.id, self.monday, status="Sick", actor_user_id=99, actor_name="Manager")
        self.assertEqual(summary["needs_coverage"], 1)
        self.assertIsNone(task.assigned_employee_id)
        self.assertTrue(task.needs_reassignment)

    def test_correction_restores_only_pending_automatic_attendance_coverage(self):
        task = self._task(self.monday)
        set_confirmed_status(self.db, self.employee.id, self.monday, status="Absent", actor_user_id=99, actor_name="Manager")
        self.assertEqual(task.assigned_employee_id, self.backup.id)
        row, summary = correct_attendance(
            self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager",
            reason="Employee was present", status="Present", check_in_at=datetime.combine(self.monday, time(7, 0)),
        )
        self.assertEqual(row.status, "Present")
        self.assertEqual(summary["returned"], 1)
        self.assertEqual(task.assigned_employee_id, self.employee.id)
        self.assertEqual(task.assignment_source, "automatic_default")

    def test_correction_requires_reason_and_creates_audit(self):
        check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=datetime.combine(self.monday, time(7, 10)))
        with self.assertRaises(AttendanceError):
            correct_attendance(self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager", reason="", status="Present")
        row, _ = correct_attendance(
            self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager",
            reason="Verified paper log", status="Present", check_in_at=datetime.combine(self.monday, time(7, 0)),
        )
        audits = list(self.db.scalars(select(StaffAttendanceAudit).where(StaffAttendanceAudit.attendance_id == row.id)).all())
        self.assertTrue(any(item.action == "Attendance Correction" and item.reason == "Verified paper log" for item in audits))

    def test_status_only_correction_preserves_check_in_and_check_out(self):
        original_in = datetime.combine(self.monday, time(7, 10))
        original_out = datetime.combine(self.monday, time(16, 0))
        check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=original_in)
        check_out(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=original_out)
        row, _ = correct_attendance(
            self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager",
            reason="Verified attendance", status="Present",
        )
        self.assertEqual((row.check_in_at, row.check_out_at), (original_in, original_out))
        audits = list(self.db.scalars(select(StaffAttendanceAudit).where(StaffAttendanceAudit.attendance_id == row.id)).all())
        self.assertEqual((audits[-1].old_check_in_at, audits[-1].new_check_in_at), (original_in, original_in))

    def test_explicit_null_clears_times_but_out_only_uses_existing_check_in(self):
        original_in = datetime.combine(self.monday, time(7, 0))
        new_out = datetime.combine(self.monday, time(16, 0))
        check_in(self.db, self.employee.id, actor_user_id=1, actor_name="Worker", source=SELF_SERVICE, now=original_in)
        row, _ = correct_attendance(
            self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager",
            reason="Verified check-out", status="Checked Out", check_out_at=new_out,
        )
        self.assertEqual((row.check_in_at, row.check_out_at), (original_in, new_out))
        with self.assertRaises(AttendanceError):
            correct_attendance(
                self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager",
                reason="Invalid check-out", status="Checked Out", check_in_at=None,
            )
        row, _ = correct_attendance(
            self.db, self.employee.id, self.monday, actor_user_id=99, actor_name="Manager",
            reason="Clear incorrect timestamps", status="Present", check_in_at=None, check_out_at=None,
        )
        self.assertIsNone(row.check_in_at)
        self.assertIsNone(row.check_out_at)
        self.assertIsNone(row.minutes_late)

    def test_bulk_attendance_reports_skipped_leave_and_missing_schedule(self):
        unscheduled = self._employee("EMP-ATT-3", "Unscheduled Worker")
        self.db.add(StaffLeave(
            employee_id=self.employee.id, leave_type="Vacation Leave",
            start_date=self.monday, end_date=self.monday, status="Approved",
        ))
        self.db.commit()
        actor = SimpleNamespace(id=99, full_name="Manager")
        with patch("app.routers.workforce_handlers._require_workforce_access"), \
             patch("app.routers.workforce_handlers.farm_today", return_value=self.monday), \
             patch("app.services.attendance_service.farm_now_naive", return_value=datetime.combine(self.monday, time(8))):
            result = bulk_mark_scheduled_present(db=self.db, current_user=actor)
            self.assertEqual(result.recorded_count, 1)
            self.assertEqual(result.skipped_count, 2)
            self.assertEqual(result.skipped_reasons, {"On Leave": 1, "Schedule Needs Setup": 1})
            self.assertNotIn(unscheduled.id, [row.employee_id for row in result.records])
            repeated = bulk_mark_scheduled_present(db=self.db, current_user=actor)
            self.assertEqual(repeated.recorded_count, 0)
            self.assertEqual(repeated.preserved_count, 1)
            self.assertEqual(repeated.skipped_reasons, result.skipped_reasons)

    def test_settings_are_singleton_and_future_absence_is_rejected(self):
        first = get_or_create_attendance_settings(self.db)
        second = get_or_create_attendance_settings(self.db)
        self.assertEqual(first.id, second.id)
        with self.assertRaises(AttendanceError):
            set_confirmed_status(self.db, self.employee.id, farm_today() + timedelta(days=1), status="Absent", actor_user_id=99, actor_name="Manager")


if __name__ == "__main__":
    unittest.main()
