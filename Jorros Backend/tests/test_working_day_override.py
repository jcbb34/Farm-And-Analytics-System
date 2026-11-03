"""Persisted rest-day changes must agree across calendar and employee APIs."""
import os
import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models import (
    Employee, EmployeeWorkSchedule, EmployeeWorkScheduleDay, Role,
    StaffAttendance, StaffAttendanceAudit, StaffLeave, StaffShift, User,
)
from app.routers.workforce import create_shift, update_shift, staff_calendar, my_schedule
from app.schemas.workforce import ShiftCreate, ShiftUpdate
from app.services.attendance_service import SELF_SERVICE, check_in
from app.services.work_schedule_service import resolve_availability_range, resolve_employee_availability


class WorkingDayOverrideTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.day = date(2026, 11, 1)
        self.now = datetime.combine(self.day, time(7, 55))
        self.admin = User(user_code="WD-ADMIN", username="wd.admin", full_name="Test Admin",
                          password_hash="test", role=Role(name="System Administrator"), status="Active")
        self.user = User(user_code="WD-USER", username="wd.worker", full_name="Test Worker",
                         password_hash="test", role=Role(name="Employee"), status="Active")
        self.db.add_all([self.admin, self.user])
        self.db.flush()
        self.employee = Employee(employee_code="WD-EMP", full_name="Test Worker", employment_status="Active",
                                 is_archived=False, login_user_id=self.user.id)
        self.db.add(self.employee)
        self.db.flush()
        schedule = EmployeeWorkSchedule(employee_id=self.employee.id, effective_from=self.day - timedelta(days=30),
                                        timezone="Asia/Manila", schedule_type="Fixed", status="Active")
        self.db.add(schedule)
        self.db.flush()
        for dow in range(7):
            working = dow != 6
            self.db.add(EmployeeWorkScheduleDay(schedule_id=schedule.id, day_of_week=dow, is_working_day=working,
                                                start_time=time(8) if working else None,
                                                end_time=time(17) if working else None))
        self.shift = StaffShift(employee_id=self.employee.id, work_date=self.day, status="Scheduled",
                                exception_type="Rest Day Override", exception_reason="Original rest day")
        self.db.add(self.shift)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _override(self, **changes):
        payload = {"exception_type": "Working Day Override", "start_time": time(8), "end_time": time(17),
                   "exception_reason": "Required for work today", **changes}
        return update_shift(self.shift.id, ShiftUpdate(**payload), db=self.db, current_user=self.admin)

    def _resolved(self, now=None):
        return resolve_employee_availability(self.db, self.employee.id, self.day, now=now or self.now)

    def test_saved_override_supersedes_unclocked_day_off_in_both_apis_without_erasing_history(self):
        attendance = StaffAttendance(employee_id=self.employee.id, attendance_date=self.day, status="Day Off",
                                     notes="Previously recorded rest day")
        self.db.add(attendance)
        self.db.commit()
        self._override()
        self.db.expire_all()
        with patch("app.services.work_schedule_service.farm_now_naive", return_value=self.now):
            calendar = staff_calendar(self.day, self.day, employee_id=self.employee.id, db=self.db, current_user=self.admin)
            mine = my_schedule(self.day, self.day, db=self.db, current_user=self.user)
        self.assertEqual(calendar["availability"], mine["availability"])
        result = calendar["availability"][0]
        self.assertEqual(result["status"], "Working Day")
        self.assertTrue(result["available"])
        self.assertTrue(result["is_working_day"])
        self.assertEqual(result["start_time"], "08:00:00")
        self.assertIsNone(result["attendance_status"])
        self.assertEqual(self._resolved().as_dict(), resolve_availability_range(
            self.db, [self.employee.id], self.day, self.day, now=self.now)[0].as_dict())
        self.assertEqual(calendar["attendance"][0]["status"], "Day Off")
        self.assertEqual(self.db.get(StaffAttendance, attendance.id).notes, "Previously recorded rest day")
        self.assertIsNone(self.db.get(StaffAttendance, attendance.id).check_in_at)
        following = resolve_employee_availability(self.db, self.employee.id, self.day + timedelta(days=7), now=self.now)
        self.assertEqual(following.status, "Rest Day")

    def test_overridden_day_off_becomes_possible_absence_only_after_the_check_in_window(self):
        self.db.add(StaffAttendance(employee_id=self.employee.id, attendance_date=self.day, status="Day Off"))
        self.db.commit()
        self._override()
        late = datetime.combine(self.day, time(9))
        self.assertEqual(self._resolved(late).status, "Possible Absence")
        bulk = resolve_availability_range(self.db, [self.employee.id], self.day, self.day, now=late)[0]
        self.assertEqual(bulk.status, "Possible Absence")
        self.assertTrue(bulk.available)

    def test_check_in_reuses_old_row_and_audits_the_real_clock_action(self):
        old = StaffAttendance(employee_id=self.employee.id, attendance_date=self.day, status="Day Off")
        self.db.add(old)
        self.db.commit()
        self._override()
        with patch("app.services.work_schedule_service.farm_now_naive", return_value=self.now):
            checked = check_in(self.db, self.employee.id, actor_user_id=self.user.id,
                               actor_name=self.user.full_name, source=SELF_SERVICE, now=self.now)
        self.db.commit()
        self.assertEqual(checked.id, old.id)
        self.assertEqual(checked.status, "On Time")
        self.assertEqual(checked.check_in_at, self.now)
        audits = list(self.db.scalars(select(StaffAttendanceAudit)).all())
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].old_status, "Day Off")
        self.assertEqual(audits[0].new_status, "On Time")

    def test_confirmed_unavailability_is_preserved_by_working_override(self):
        self._override()
        attendance = StaffAttendance(employee_id=self.employee.id, attendance_date=self.day, status="Absent")
        self.db.add(attendance)
        for status in ("Absent", "Sick", "Sick Leave", "Approved Leave"):
            with self.subTest(status=status):
                attendance.status = status
                self.db.flush()
                single = self._resolved()
                bulk = resolve_availability_range(self.db, [self.employee.id], self.day, self.day, now=self.now)[0]
                self.assertFalse(single.available)
                self.assertEqual(single.attendance_status, status)
                self.assertEqual(single.as_dict(), bulk.as_dict())

    def test_working_override_cannot_bypass_approved_leave(self):
        self.db.add(StaffLeave(employee_id=self.employee.id, start_date=self.day, end_date=self.day,
                              leave_type="Vacation Leave", status="Approved"))
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self._override()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self._resolved().status, "On Leave")

    def test_changed_shift_also_supersedes_an_unclocked_rest_marker(self):
        self.db.add(StaffAttendance(employee_id=self.employee.id, attendance_date=self.day, status="Day Off"))
        self.db.commit()
        self._override(exception_type="Changed Shift", start_time=time(9), end_time=time(18))
        self.assertEqual(self._resolved().status, "Changed Shift")
        self.assertEqual(self._resolved().start_time, time(9))
        self.assertEqual(resolve_availability_range(
            self.db, [self.employee.id], self.day, self.day, now=self.now)[0].as_dict(), self._resolved().as_dict())

    def test_a_clocked_day_off_record_is_preserved_for_authorized_correction(self):
        attendance = StaffAttendance(employee_id=self.employee.id, attendance_date=self.day, status="Day Off",
                                     check_in_at=datetime.combine(self.day, time(7, 30)))
        self.db.add(attendance)
        self.db.commit()
        self._override()
        self.assertFalse(self._resolved().available)
        self.assertEqual(self._resolved().attendance_status, "Day Off")
        self.assertEqual(attendance.check_in_at.time(), time(7, 30))

    def test_regular_roster_on_a_weekly_working_day_remains_supported(self):
        monday = self.day + timedelta(days=1)
        record = create_shift(ShiftCreate(employee_id=self.employee.id, work_date=monday, start_time=time(8), end_time=time(17)),
                              db=self.db, current_user=self.admin)
        self.assertIsNone(record.exception_type)
        self.assertEqual(resolve_employee_availability(self.db, self.employee.id, monday, now=self.now).status, "Working Day")

    def test_regular_roster_cannot_silently_claim_to_make_a_rest_day_a_working_day(self):
        self.db.delete(self.shift)
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            create_shift(ShiftCreate(employee_id=self.employee.id, work_date=self.day, start_time=time(8), end_time=time(17)),
                         db=self.db, current_user=self.admin)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("Working Day Override", caught.exception.detail)
        self.assertIsNone(self.db.scalar(select(StaffShift)))

    def test_removing_an_override_on_a_weekly_rest_day_requires_an_explicit_choice(self):
        self._override()
        with self.assertRaises(HTTPException) as caught:
            update_shift(self.shift.id, ShiftUpdate(exception_type=None), db=self.db, current_user=self.admin)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.get(StaffShift, self.shift.id).exception_type, "Working Day Override")
        update_shift(self.shift.id, ShiftUpdate(status="Cancelled", exception_type=None), db=self.db, current_user=self.admin)
        self.assertEqual(self._resolved().status, "Rest Day")
