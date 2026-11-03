import os
import sys
import unittest
from unittest.mock import patch
from datetime import date, datetime, time, timedelta, timezone
from types import ModuleType

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")
os.environ.setdefault("FARM_TIMEZONE", "Asia/Manila")

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
        "create_access_token", "create_two_factor_challenge", "decode_access_token",
        "decode_access_token_claims", "decode_two_factor_challenge", "hash_password", "verify_password",
    ):
        setattr(test_security_module, _name, _unused_security_stub)
    sys.modules["app.core.security"] = test_security_module

from app.core.database import Base
from app.core.farm_time import farm_today
from app.models import AuditLog, Crop, Employee, FarmActivity, Role, StaffAttendance, StaffLeave, StaffShift, User
from app.routers import analytics as analytics_router
from app.routers.workforce import (
    cancel_leave,
    create_leave,
    create_shift,
    decide_leave,
    my_schedule,
    request_my_leave,
    staff_calendar,
    upsert_attendance,
)
from app.schemas.workforce import (
    AttendanceUpsert,
    LeaveCreate,
    LeaveDecisionRequest,
    LeaveRequestCreate,
    ShiftCreate,
)
from app.services.task_engine import evaluate_automatic_tasks


class StaffCalendarTimezoneTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()
        self.today = farm_today()

        manager_role = Role(name="Manager", description="Manager")
        employee_role = Role(name="Employee", description="Employee")
        self.manager = User(
            user_code="USR-CAL-MGR", full_name="Calendar Manager", username="calendar.manager",
            password_hash="test", role=manager_role, status="Active",
        )
        self.employee_user = User(
            user_code="USR-CAL-EMP", full_name="Calendar Employee", username="calendar.employee",
            password_hash="test", role=employee_role, status="Active",
        )
        self.other_user = User(
            user_code="USR-CAL-OTHER", full_name="Other Employee", username="calendar.other",
            password_hash="test", role=employee_role, status="Active",
        )
        self.db.add_all([manager_role, employee_role, self.manager, self.employee_user, self.other_user])
        self.db.flush()
        self.employee = Employee(
            employee_code="EMP-CAL-001", full_name="Calendar Employee", employment_status="Active",
            assigned_area="Field A", login_user_id=self.employee_user.id,
        )
        self.other = Employee(
            employee_code="EMP-CAL-002", full_name="Other Employee", employment_status="Active",
            assigned_area="Field B", login_user_id=self.other_user.id,
        )
        self.db.add_all([self.employee, self.other])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _task(self, when: date, employee=None, status="Pending"):
        employee = employee or self.employee
        task = FarmActivity(
            activity_code=f"ACT-CAL-{when.strftime('%m%d')}-{employee.id}-{status[:1]}",
            name="Calendar task", category="General Care", related_to="Test",
            location="Field A", activity_date=when, start_time=time(8, 0),
            assigned_by="Manager", assigned_to=employee.full_name,
            assigned_employee_id=employee.id, status=status, priority="Medium",
            requires_review=True, requires_evidence=False, is_automatic=False,
        )
        self.db.add(task)
        self.db.commit()
        return task

    def test_manila_midnight_uses_next_farm_date(self):
        # 16:30 UTC is already 00:30 on the following day in Asia/Manila.
        instant = datetime(2026, 9, 10, 16, 30, tzinfo=timezone.utc)
        self.assertEqual(farm_today(instant), date(2026, 9, 11))

    def test_trend_period_uses_same_farm_date_as_intelligence_overview(self):
        # After midnight in Manila, Trends must include October even if the
        # API host is still on September 30 in UTC.
        with patch.object(analytics_router, "farm_today", return_value=date(2026, 10, 1)), \
             patch.object(analytics_router, "build_trend_analysis", side_effect=lambda _db, start, end: (start, end)):
            start, end = analytics_router.get_trend_analysis(months=3, db=self.db)

        self.assertEqual((start, end), (date(2026, 8, 1), date(2026, 10, 1)))

    def test_manila_fallback_works_when_windows_tzdata_is_unavailable(self):
        from app.core import farm_time

        instant = datetime(2026, 9, 10, 16, 30, tzinfo=timezone.utc)
        with patch.object(
            farm_time,
            "ZoneInfo",
            side_effect=farm_time.ZoneInfoNotFoundError("No time zone found with key Asia/Manila"),
        ):
            zone = farm_time.farm_timezone()
            self.assertEqual(zone.utcoffset(instant), timedelta(hours=8))
            self.assertEqual(farm_time.farm_today(instant), date(2026, 9, 11))

    def test_approved_leave_flags_open_task_and_cancellation_restores_flag(self):
        when = self.today + timedelta(days=2)
        task = self._task(when)
        leave = create_leave(
            LeaveCreate(
                employee_id=self.employee.id, leave_type="Vacation Leave",
                start_date=when, end_date=when, reason="Family appointment", status="Approved",
            ),
            self.db,
            self.manager,
        )
        self.db.refresh(task)
        self.assertEqual(leave.status, "Approved")
        self.assertTrue(task.needs_reassignment)

        cancelled = cancel_leave(leave.id, self.db, self.manager)
        self.db.refresh(task)
        self.assertEqual(cancelled.status, "Cancelled")
        self.assertFalse(task.needs_reassignment)
        self.assertEqual(cancelled.cancelled_by_user_id, self.manager.id)
        self.assertIsNotNone(cancelled.cancelled_at)
        cancel_audit = self.db.scalar(select(AuditLog).where(
            AuditLog.event_type == "audit",
            AuditLog.action == "Leave cancelled",
            AuditLog.entity_id == f"leave:{leave.id}",
        ))
        self.assertIsNotNone(cancel_audit)
        self.assertEqual(cancel_audit.actor_user_id, self.manager.id)

    def test_employee_leave_request_is_pending_and_only_manager_can_approve(self):
        when = self.today + timedelta(days=4)
        request = request_my_leave(
            LeaveRequestCreate(
                leave_type="Emergency Leave", start_date=when, end_date=when, reason="Personal emergency"
            ),
            self.db,
            self.employee_user,
        )
        self.assertEqual(request.employee_id, self.employee.id)
        self.assertEqual(request.status, "Pending")
        self.assertIsNone(request.decided_by_user_id)

        with self.assertRaises(HTTPException) as ctx:
            decide_leave(request.id, LeaveDecisionRequest(decision="Approved"), self.db, self.employee_user)
        self.assertEqual(ctx.exception.status_code, 403)

        approved = decide_leave(
            request.id,
            LeaveDecisionRequest(decision="Approved", notes="Approved by manager"),
            self.db,
            self.manager,
        )
        self.assertEqual(approved.status, "Approved")
        self.assertEqual(approved.decided_by_user_id, self.manager.id)
        self.assertIsNotNone(approved.decided_at)

    def test_overlapping_roster_and_leave_are_detected(self):
        when = self.today + timedelta(days=5)
        shift = create_shift(
            ShiftCreate(
                employee_id=self.employee.id, work_date=when,
                start_time=time(7, 0), end_time=time(16, 0), assigned_area="Field A",
            ),
            self.db,
            self.manager,
        )
        self.assertEqual(shift.status, "Scheduled")

        with self.assertRaises(HTTPException) as duplicate_ctx:
            create_shift(
                ShiftCreate(employee_id=self.employee.id, work_date=when, assigned_area="Field B"),
                self.db,
                self.manager,
            )
        self.assertEqual(duplicate_ctx.exception.status_code, 409)

        first_pending = request_my_leave(
            LeaveRequestCreate(
                leave_type="Vacation Leave", start_date=when + timedelta(days=2),
                end_date=when + timedelta(days=3), reason="First request",
            ),
            self.db,
            self.employee_user,
        )
        self.assertEqual(first_pending.status, "Pending")
        with self.assertRaises(HTTPException) as leave_overlap_ctx:
            request_my_leave(
                LeaveRequestCreate(
                    leave_type="Emergency Leave", start_date=when + timedelta(days=3),
                    end_date=when + timedelta(days=4), reason="Overlapping request",
                ),
                self.db,
                self.employee_user,
            )
        self.assertEqual(leave_overlap_ctx.exception.status_code, 409)

        pending = request_my_leave(
            LeaveRequestCreate(
                leave_type="Vacation Leave", start_date=when, end_date=when, reason="Requested day off"
            ),
            self.db,
            self.employee_user,
        )
        approved = decide_leave(
            pending.id,
            LeaveDecisionRequest(decision="Approved", notes="Shift remains visible for reviewer context"),
            self.db,
            self.manager,
        )
        self.assertEqual(approved.status, "Approved")
        # Prompt 9.1 requires overlapping shifts to be shown to the reviewer,
        # not to block an otherwise valid leave approval.
        self.assertEqual(self.db.get(StaffShift, shift.id).status, "Scheduled")

    def test_absent_attendance_flags_task_and_present_restores_it(self):
        # Future attendance states are intentionally suppressed; exercise the same
        # reassignment/correction behavior on a completed work date.
        when = self.today - timedelta(days=1)
        task = self._task(when)
        upsert_attendance(
            AttendanceUpsert(employee_id=self.employee.id, attendance_date=when, status="Absent", notes="Absent"),
            self.db,
            self.manager,
        )
        self.db.refresh(task)
        self.assertTrue(task.needs_reassignment)

        upsert_attendance(
            AttendanceUpsert(employee_id=self.employee.id, attendance_date=when, status="Present", notes="Corrected"),
            self.db,
            self.manager,
        )
        self.db.refresh(task)
        self.assertFalse(task.needs_reassignment)
        present_audit = self.db.scalar(select(AuditLog).where(
            AuditLog.event_type == "audit",
            AuditLog.action == "Attendance updated",
            AuditLog.entity_id == f"attendance:{self.employee.id}:{when.isoformat()}",
        ).order_by(AuditLog.id.desc()))
        self.assertIsNotNone(present_audit)
        self.assertIn("Absent -> Present", present_audit.details)
        self.assertEqual(present_audit.actor_user_id, self.manager.id)

    def test_future_automatic_task_created_during_leave_is_immediately_flagged(self):
        when = self.today + timedelta(days=3)
        crop = Crop(
            crop_code="CRP-CAL-001", name="Eggplant", variety="Test", field="Field A",
            area_hectares=0.5, current_growth=20, growth_stage="Vegetative", quantity_planted=10,
            current_surviving=10, status="Growing", planting_date=self.today,
            estimated_harvest=self.today + timedelta(days=60), fertilizer_quantity_kg=0,
            watering_schedule="Daily | Morning", assigned_employee_id=self.employee.id,
        )
        leave = StaffLeave(
            employee_id=self.employee.id, leave_type="Vacation Leave", start_date=when, end_date=when,
            status="Approved", recorded_by_user_id=self.manager.id, requested_by_user_id=self.manager.id,
            decided_by_user_id=self.manager.id,
        )
        self.db.add_all([crop, leave])
        self.db.commit()

        evaluate_automatic_tasks(self.db)
        task = self.db.scalar(select(FarmActivity).where(
            FarmActivity.source_key == f"crop:watering:{crop.id}:{when.isoformat()}:morning"
        ))
        self.assertIsNotNone(task)
        self.assertTrue(task.needs_reassignment)

    def test_future_automatic_task_created_during_absence_is_immediately_flagged(self):
        when = self.today + timedelta(days=6)
        crop = Crop(
            crop_code="CRP-CAL-ABS", name="Okra", variety="Test", field="Field A",
            area_hectares=0.4, current_growth=20, growth_stage="Vegetative", quantity_planted=10,
            current_surviving=10, status="Growing", planting_date=self.today,
            estimated_harvest=self.today + timedelta(days=60), fertilizer_quantity_kg=0,
            watering_schedule="Daily | Morning", assigned_employee_id=self.employee.id,
        )
        self.db.add(crop)
        self.db.add(StaffAttendance(
            employee_id=self.employee.id, attendance_date=when, status="Absent",
            recorded_by_user_id=self.manager.id,
        ))
        self.db.commit()

        evaluate_automatic_tasks(self.db)
        task = self.db.scalar(select(FarmActivity).where(
            FarmActivity.source_key == f"crop:watering:{crop.id}:{when.isoformat()}:morning"
        ))
        self.assertIsNotNone(task)
        self.assertTrue(task.needs_reassignment)


    def test_employee_cannot_access_administrative_staff_calendar(self):
        with self.assertRaises(HTTPException) as ctx:
            staff_calendar(self.today, self.today, None, self.db, self.employee_user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_late_attendance_is_supported_without_marking_employee_unavailable(self):
        when = self.today
        task = self._task(when)
        attendance = upsert_attendance(
            AttendanceUpsert(employee_id=self.employee.id, attendance_date=when, status="Late", notes="Arrived late"),
            self.db,
            self.manager,
        )
        self.db.refresh(task)
        self.assertEqual(attendance.status, "Late")
        self.assertFalse(task.needs_reassignment)

    def test_pending_leave_does_not_flag_tasks_until_approved(self):
        when = self.today + timedelta(days=7)
        task = self._task(when)
        pending = request_my_leave(
            LeaveRequestCreate(
                leave_type="Vacation Leave", start_date=when, end_date=when, reason="Pending request"
            ),
            self.db,
            self.employee_user,
        )
        self.db.refresh(task)
        self.assertEqual(pending.status, "Pending")
        self.assertFalse(task.needs_reassignment)

        decide_leave(
            pending.id,
            LeaveDecisionRequest(decision="Approved", notes="Approved for coverage"),
            self.db,
            self.manager,
        )
        self.db.refresh(task)
        self.assertTrue(task.needs_reassignment)

    def test_calendar_range_returns_bulk_staff_data_without_per_leave_serializer(self):
        when = self.today + timedelta(days=8)
        self._task(when)
        self.db.add_all([
            StaffShift(employee_id=self.employee.id, work_date=when, status="Scheduled", assigned_area="Field A"),
            StaffLeave(
                employee_id=self.employee.id, leave_type="Vacation Leave", start_date=when, end_date=when,
                status="Pending", recorded_by_user_id=self.manager.id, requested_by_user_id=self.employee_user.id,
            ),
        ])
        self.db.commit()

        payload = staff_calendar(when, when, None, self.db, self.manager)
        self.assertEqual(payload["date_from"], when.isoformat())
        self.assertEqual(payload["date_to"], when.isoformat())
        self.assertEqual(len(payload["tasks"]), 1)
        self.assertEqual(len(payload["leave"]), 1)
        self.assertEqual(len(payload["shifts"]), 1)
        self.assertEqual(payload["leave"][0]["status"], "Pending")


    def test_calendar_task_query_count_does_not_grow_per_task(self):
        self._task(self.today)
        queries: list[int] = []

        def count_query(*_args, **_kwargs):
            queries.append(1)

        event.listen(self.engine, "before_cursor_execute", count_query)
        try:
            staff_calendar(self.today, self.today, None, self.db, self.manager)
            one_task_queries = len(queries)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_query)

        for offset in range(1, 10):
            self._task(self.today + timedelta(days=offset))

        queries.clear()
        event.listen(self.engine, "before_cursor_execute", count_query)
        try:
            staff_calendar(self.today, self.today + timedelta(days=9), None, self.db, self.manager)
            many_task_queries = len(queries)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_query)

        self.assertLessEqual(
            many_task_queries,
            one_task_queries + 1,
            f"Calendar query count grew with task count: {one_task_queries} -> {many_task_queries}",
        )

    def test_employee_my_schedule_is_scoped_to_linked_profile(self):
        when = self.today
        self._task(when, self.employee)
        self._task(when, self.other)
        self.db.add_all([
            StaffShift(employee_id=self.employee.id, work_date=when, status="Scheduled", assigned_area="Field A"),
            StaffShift(employee_id=self.other.id, work_date=when, status="Scheduled", assigned_area="Field B"),
        ])
        self.db.commit()
        payload = my_schedule(when, when, self.db, self.employee_user)
        self.assertEqual({row["assigned_employee_id"] for row in payload["tasks"]}, {self.employee.id})
        self.assertEqual({row["employee_id"] for row in payload["shifts"]}, {self.employee.id})
        self.assertEqual(payload["timezone"], "Asia/Manila")


if __name__ == "__main__":
    unittest.main()
