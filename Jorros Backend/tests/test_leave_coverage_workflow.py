import os
import sys
import unittest
from unittest.mock import patch
from datetime import date, datetime, time, timedelta
from types import ModuleType, SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
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
from app.core.farm_time import farm_today
from app.models import (  # noqa: E402,F401
    Crop,
    Employee,
    FarmActivity,
    Role,
    StaffAttendance,
    StaffLeave,
    TaskAssignmentHistory,
    TaskLeaveCoverage,
    User,
)
from app.routers import workforce  # noqa: E402
from app.schemas.workforce import (  # noqa: E402
    LeaveCancelRequest,
    LeaveCoverageTaskSelection,
    LeaveDecisionRequest,
    LeaveRequestCreate,
    TaskAssignmentUpdate,
)
from app.services.leave_coverage_service import (  # noqa: E402
    approve_leave_with_coverage,
    reconcile_expired_leave_coverage,
)
from app.services.task_engine import _upsert_automatic_task  # noqa: E402


class LeaveCoverageWorkflowTests(unittest.TestCase):
    def setUp(self):
        # This suite's dated task/leave fixtures describe September 2026.
        # Keep request eligibility on the same clock as those fixed fixtures.
        request_clock = patch("app.schemas.workforce.farm_today", return_value=date(2026, 9, 11))
        request_clock.start()
        self.addCleanup(request_clock.stop)
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

        submit_role = Role(name="Leave Staff", description="staff")
        submit_role.set_permissions(["workforce:submit"])
        manager_role = Role(name="Leave Manager", description="manager")
        manager_role.set_permissions(["workforce:manage", "workforce:attendance", "workforce:review"])
        owner_role = Role(name="Leave Owner", description="owner")
        owner_role.set_permissions(["*"])
        self.db.add_all([submit_role, manager_role, owner_role])
        self.db.flush()

        self.staff_user = User(
            user_code="USR-LEAVE-STAFF",
            full_name="Regular Worker",
            username="leave.staff",
            password_hash="test",
            role=submit_role,
            status="Active",
        )
        self.cover_user = User(
            user_code="USR-LEAVE-COVER",
            full_name="Cover Worker",
            username="leave.cover",
            password_hash="test",
            role=submit_role,
            status="Active",
        )
        self.manager_user = User(
            user_code="USR-LEAVE-MGR",
            full_name="Farm Manager",
            username="leave.manager",
            password_hash="test",
            role=manager_role,
            status="Active",
        )
        self.owner_user = User(
            user_code="USR-LEAVE-OWNER",
            full_name="Farm Owner",
            username="leave.owner",
            password_hash="test",
            role=owner_role,
            status="Active",
        )
        self.db.add_all([self.staff_user, self.cover_user, self.manager_user, self.owner_user])
        self.db.flush()

        self.regular = self._employee("EMP-LEAVE-REG", "Regular Worker", self.staff_user.id, area="Field A")
        self.cover = self._employee("EMP-LEAVE-COVER", "Cover Worker", self.cover_user.id, area="Field A")
        self.other_cover_user = User(
            user_code="USR-LEAVE-ALT",
            full_name="Alternate Worker",
            username="leave.alt",
            password_hash="test",
            role=submit_role,
            status="Active",
        )
        self.db.add(self.other_cover_user)
        self.db.flush()
        self.other_cover = self._employee("EMP-LEAVE-ALT", "Alternate Worker", self.other_cover_user.id, area="Field A")
        self.crop = Crop(
            crop_code="CRP-LEAVE-1",
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
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _employee(self, code, name, login_user_id=None, *, area=None, status="Active", archived=False):
        row = Employee(
            employee_code=code,
            full_name=name,
            position="Farm Worker",
            assigned_area=area,
            skills="General crop care",
            employment_status=status,
            is_archived=archived,
            login_user_id=login_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _leave(self, *, status="Pending", start=date(2026, 9, 15), end=date(2026, 9, 17), requested=True):
        row = StaffLeave(
            employee_id=self.regular.id,
            leave_type="Vacation Leave",
            start_date=start,
            end_date=end,
            status=status,
            reason="Family commitment",
            recorded_by_user_id=self.staff_user.id if requested else self.manager_user.id,
            requested_by_user_id=self.staff_user.id if requested else None,
            decided_by_user_id=self.manager_user.id if status == "Approved" else None,
            decided_at=datetime(2026, 9, 11, 9, 0) if status == "Approved" else None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _task(self, code, work_date, *, status="Pending", employee=None, automatic=True, archived=False):
        employee = self.regular if employee is None else employee
        row = FarmActivity(
            activity_code=code,
            name="Inspect Crop Growth",
            category="Crop Monitoring",
            related_to=self.crop.name,
            location=self.crop.field,
            description="Record crop growth.",
            activity_date=work_date,
            start_time=time(8, 0),
            assigned_by="System" if automatic else self.manager_user.full_name,
            assigned_to=employee.full_name if employee else "Unassigned",
            assigned_employee_id=employee.id if employee else None,
            assignment_source="automatic_default" if automatic else "manual",
            status=status,
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
            is_automatic=automatic,
            source_module="Crop",
            source_type="crop_growth_check",
            source_record_id=self.crop.id,
            source_code=self.crop.crop_code,
            source_path="/crops",
            is_archived=archived,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _approve(self, leave, *, cover_id=None, selections=None, user=None):
        selections = selections or []
        return workforce.decide_leave(
            leave.id,
            LeaveDecisionRequest(
                decision="Approved",
                notes="Temporary coverage approved",
                default_covering_employee_id=cover_id,
                task_coverages=selections,
            ),
            self.db,
            user or self.manager_user,
        )

    def _legacy_future_coverage(self, leave, task, *, cover=None, status="Active"):
        cover = cover or self.cover
        task.assigned_employee_id = cover.id
        task.assigned_to = cover.full_name
        task.assigned_by = self.manager_user.full_name
        task.assignment_source = "Leave Coverage"
        task.needs_reassignment = False
        row = TaskLeaveCoverage(
            activity_id=task.id,
            leave_id=leave.id,
            original_employee_id=self.regular.id,
            covering_employee_id=cover.id,
            coverage_start_date=leave.start_date,
            coverage_end_date=leave.end_date,
            status=status,
            reason="Vacation Leave coverage",
            approved_by_user_id=self.manager_user.id,
            approved_at=leave.decided_at or datetime(2026, 9, 11, 9, 0),
            source_module=task.source_module,
            source_type=task.source_type,
            source_record_id=task.source_record_id,
            source_detail_id=task.source_detail_id,
            recurring_series_key=task.recurring_series_key,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def test_employee_creates_own_pending_leave_and_can_view_it(self):
        result = workforce.request_my_leave(
            LeaveRequestCreate(
                leave_type="Vacation Leave",
                start_date=date(2026, 9, 15),
                end_date=date(2026, 9, 17),
                reason="Family commitment",
            ),
            self.db,
            self.staff_user,
        )
        self.assertEqual(result.employee_id, self.regular.id)
        self.assertEqual(result.status, "Pending")
        mine = workforce.my_leave_requests(self.db, self.staff_user)
        self.assertEqual([row.id for row in mine], [result.id])

    def test_inactive_employee_and_overlapping_leave_are_rejected(self):
        self._leave(status="Pending")
        self.db.commit()
        with self.assertRaises(HTTPException) as overlap:
            workforce.request_my_leave(
                LeaveRequestCreate(
                    leave_type="Sick Leave",
                    start_date=date(2026, 9, 16),
                    end_date=date(2026, 9, 18),
                    reason="Overlap",
                ), self.db, self.staff_user,
            )
        self.assertEqual(overlap.exception.status_code, 409)

        self.regular.employment_status = "Inactive"
        self.db.commit()
        with self.assertRaises(HTTPException) as inactive:
            workforce.request_my_leave(
                LeaveRequestCreate(
                    leave_type="Emergency Leave",
                    start_date=date(2026, 10, 1),
                    end_date=date(2026, 10, 1),
                ), self.db, self.staff_user,
            )
        self.assertEqual(inactive.exception.status_code, 400)

    def test_employee_cannot_approve_own_leave_even_with_manager_permission(self):
        leave = self._leave(status="Pending")
        # Simulate an employee account that was also granted management authority.
        leave.requested_by_user_id = self.manager_user.id
        self.regular.login_user_id = self.manager_user.id
        self.db.flush()
        with self.assertRaises(HTTPException) as ctx:
            self._approve(leave, cover_id=self.cover.id, user=self.manager_user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(leave.status, "Pending")

    def test_manager_can_approve_and_owner_can_reject(self):
        leave = self._leave(status="Pending")
        approved = self._approve(leave, cover_id=self.cover.id)
        self.assertEqual(approved.status, "Approved")
        self.assertEqual(approved.reviewed_by_name, self.manager_user.full_name)

        second = StaffLeave(
            employee_id=self.regular.id,
            leave_type="Emergency Leave",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 1),
            status="Pending",
            requested_by_user_id=self.staff_user.id,
        )
        self.db.add(second)
        self.db.commit()
        rejected = workforce.decide_leave(
            second.id,
            LeaveDecisionRequest(decision="Rejected", notes="Coverage unavailable"),
            self.db,
            self.owner_user,
        )
        self.assertEqual(rejected.status, "Rejected")

    def test_pending_and_rejected_leave_do_not_change_tasks(self):
        task = self._task("ACT-LEAVE-PENDING", date(2026, 9, 16))
        leave = self._leave(status="Pending")
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        workforce.decide_leave(
            leave.id,
            LeaveDecisionRequest(decision="Rejected", notes="Not approved"),
            self.db,
            self.manager_user,
        )
        self.db.refresh(task)
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(task.assignment_source, "automatic_default")
        self.assertFalse(task.needs_reassignment)

    def test_approved_leave_changes_only_tasks_inside_leave_dates(self):
        before = self._task("ACT-LEAVE-BEFORE", date(2026, 9, 14))
        inside = self._task("ACT-LEAVE-INSIDE", date(2026, 9, 16))
        after = self._task("ACT-LEAVE-AFTER", date(2026, 9, 18))
        leave = self._leave(status="Pending")
        self._approve(leave, cover_id=self.cover.id)
        self.assertEqual(inside.assigned_employee_id, self.cover.id)
        self.assertEqual(inside.assignment_source, "Leave Coverage")
        self.assertEqual(before.assigned_employee_id, self.regular.id)
        self.assertEqual(after.assigned_employee_id, self.regular.id)

    def test_selected_cover_is_applied_per_task_and_structured_history_is_saved(self):
        task_a = self._task("ACT-LEAVE-COVER-A", date(2026, 9, 15))
        task_b = self._task("ACT-LEAVE-COVER-B", date(2026, 9, 16))
        leave = self._leave(status="Pending")
        self._approve(
            leave,
            cover_id=self.cover.id,
            selections=[LeaveCoverageTaskSelection(task_id=task_b.id, covering_employee_id=self.other_cover.id)],
        )
        self.assertEqual(task_a.assigned_employee_id, self.cover.id)
        self.assertEqual(task_b.assigned_employee_id, self.other_cover.id)
        coverage = self.db.scalar(select(TaskLeaveCoverage).where(TaskLeaveCoverage.activity_id == task_b.id))
        self.assertEqual(coverage.original_employee_id, self.regular.id)
        self.assertEqual(coverage.covering_employee_id, self.other_cover.id)
        history = self.db.scalar(select(TaskAssignmentHistory).where(TaskAssignmentHistory.activity_id == task_b.id))
        self.assertEqual(history.leave_id, leave.id)
        self.assertEqual(history.old_assignment_source, "automatic_default")
        self.assertEqual(history.new_assignment_source, "Leave Coverage")
        self.assertFalse(history.is_automatic)

    def test_no_cover_unassigns_pending_task_and_marks_needs_reassignment(self):
        task = self._task("ACT-LEAVE-NOCOVER", date(2026, 9, 16))
        leave = self._leave(status="Pending")
        self._approve(leave)
        self.assertIsNone(task.assigned_employee_id)
        self.assertEqual(task.assigned_to, "Unassigned")
        self.assertEqual(task.assignment_source, "Leave Coverage")
        self.assertTrue(task.needs_reassignment)
        coverage = self.db.scalar(select(TaskLeaveCoverage).where(TaskLeaveCoverage.activity_id == task.id))
        self.assertEqual(coverage.status, "Needs Reassignment")

    def test_in_progress_task_is_not_silently_transferred(self):
        task = self._task("ACT-LEAVE-INPROGRESS", date(2026, 9, 16), status="In Progress")
        leave = self._leave(status="Pending")
        self._approve(leave, cover_id=self.cover.id)
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(task.status, "In Progress")
        self.assertTrue(task.needs_reassignment)
        coverage = self.db.scalar(select(TaskLeaveCoverage).where(TaskLeaveCoverage.activity_id == task.id))
        self.assertEqual(coverage.status, "Urgent Review")

    def test_protected_task_statuses_and_archived_tasks_remain_unchanged(self):
        statuses = ["Submitted for Review", "Completed", "Approved", "Voided", "Cancelled", "Resolved"]
        tasks = [self._task(f"ACT-LEAVE-PROT-{idx}", date(2026, 9, 16), status=value) for idx, value in enumerate(statuses)]
        archived = self._task("ACT-LEAVE-ARCHIVED", date(2026, 9, 16), archived=True)
        leave = self._leave(status="Pending")
        self._approve(leave, cover_id=self.cover.id)
        for task, status in zip(tasks, statuses):
            self.assertEqual(task.status, status)
            self.assertEqual(task.assigned_employee_id, self.regular.id)
            self.assertNotEqual(task.assignment_source, "Leave Coverage")
        self.assertEqual(archived.assigned_employee_id, self.regular.id)

    def test_new_automatic_occurrence_during_leave_uses_valid_cover(self):
        leave = self._leave(status="Approved")
        leave.default_covering_employee_id = self.cover.id
        self.db.commit()
        task, _ = _upsert_automatic_task(
            self.db,
            source_key="crop:leave:covered:new",
            source_module="Crop",
            source_type="crop_growth_check",
            source_record_id=self.crop.id,
            source_detail_id=None,
            source_code=self.crop.crop_code,
            source_path="/crops",
            name="Inspect Crop Growth",
            category="Crop Monitoring",
            related_to=self.crop.name,
            location=self.crop.field,
            description="Record crop growth.",
            activity_date=date(2026, 9, 16),
            start_time=time(8, 0),
            assigned_to="Farm Staff",
            priority="Medium",
        )
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assignment_source, "Leave Coverage")

    def test_new_occurrence_after_leave_uses_regular_default_employee(self):
        leave = self._leave(status="Approved")
        leave.default_covering_employee_id = self.cover.id
        self.db.commit()
        task, _ = _upsert_automatic_task(
            self.db,
            source_key="crop:leave:after:new",
            source_module="Crop",
            source_type="crop_growth_check",
            source_record_id=self.crop.id,
            source_detail_id=None,
            source_code=self.crop.crop_code,
            source_path="/crops",
            name="Inspect Crop Growth",
            category="Crop Monitoring",
            related_to=self.crop.name,
            location=self.crop.field,
            description="Record crop growth.",
            activity_date=date(2026, 9, 18),
            start_time=time(8, 0),
            assigned_to="Farm Staff",
            priority="Medium",
        )
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(task.assignment_source, "automatic_default")

    def test_future_pending_legacy_coverage_returns_after_leave_and_is_idempotent(self):
        leave = self._leave(status="Approved", start=date(2026, 9, 10), end=date(2026, 9, 12))
        task = self._task("ACT-LEAVE-RETURN", date(2026, 9, 13))
        coverage = self._legacy_future_coverage(leave, task)
        self.db.commit()
        first = reconcile_expired_leave_coverage(self.db, as_of_date=date(2026, 9, 14))
        self.assertEqual(first["returned"], 1)
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(coverage.status, "Returned")
        second = reconcile_expired_leave_coverage(self.db, as_of_date=date(2026, 9, 14))
        self.assertEqual(second["returned"], 0)
        count = self.db.scalar(select(func.count(TaskAssignmentHistory.id)).where(TaskAssignmentHistory.event_key == f"leave-return:{coverage.id}"))
        self.assertEqual(count, 1)

    def test_completed_and_in_progress_coverage_tasks_never_auto_return(self):
        leave = self._leave(status="Approved", start=date(2026, 9, 10), end=date(2026, 9, 12))
        completed = self._task("ACT-LEAVE-RET-COMP", date(2026, 9, 13), status="Completed")
        in_progress = self._task("ACT-LEAVE-RET-PROG", date(2026, 9, 13), status="In Progress")
        self._legacy_future_coverage(leave, completed)
        self._legacy_future_coverage(leave, in_progress)
        self.db.commit()
        reconcile_expired_leave_coverage(self.db, as_of_date=date(2026, 9, 14))
        self.assertEqual(completed.assigned_employee_id, self.cover.id)
        self.assertEqual(in_progress.assigned_employee_id, self.cover.id)

    def test_later_manager_override_is_preserved(self):
        leave = self._leave(status="Approved", start=date(2026, 9, 10), end=date(2026, 9, 12))
        task = self._task("ACT-LEAVE-OVERRIDE", date(2026, 9, 13))
        self._legacy_future_coverage(leave, task)
        self.db.commit()
        workforce.update_task_assignment(
            task.id,
            TaskAssignmentUpdate(employee_id=self.other_cover.id, reason="Manager chose alternate specialist"),
            self.db,
            self.manager_user,
        )
        reconcile_expired_leave_coverage(self.db, as_of_date=date(2026, 9, 14))
        self.assertEqual(task.assigned_employee_id, self.other_cover.id)
        self.assertEqual(task.assignment_source, "manager_override")

    def test_early_leave_cancellation_restores_only_eligible_future_pending_task(self):
        leave_start = farm_today() + timedelta(days=1)
        task = self._task("ACT-LEAVE-CANCEL-RETURN", leave_start + timedelta(days=1))
        leave = self._leave(
            status="Pending",
            start=leave_start,
            end=leave_start + timedelta(days=2),
        )
        self._approve(leave, cover_id=self.cover.id)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        workforce.cancel_leave(
            leave.id,
            LeaveCancelRequest(reason="Employee returned early"),
            self.db,
            self.manager_user,
        )
        self.assertEqual(leave.status, "Cancelled")
        self.assertEqual(leave.cancellation_reason, "Employee returned early")
        self.assertEqual(task.assigned_employee_id, self.regular.id)
        self.assertEqual(task.assignment_source, "automatic_default")

    def test_unavailable_original_employee_does_not_receive_automatic_return(self):
        leave = self._leave(status="Approved", start=date(2026, 9, 10), end=date(2026, 9, 12))
        task = self._task("ACT-LEAVE-RETURN-BLOCK", date(2026, 9, 13))
        self._legacy_future_coverage(leave, task)
        self.db.add(StaffAttendance(employee_id=self.regular.id, attendance_date=task.activity_date, status="Absent"))
        self.db.commit()
        result = reconcile_expired_leave_coverage(self.db, as_of_date=date(2026, 9, 14))
        self.assertEqual(result["returned"], 0)
        self.assertEqual(task.assigned_employee_id, self.cover.id)
        self.assertEqual(task.assignment_source, "Leave Coverage")

    def test_leave_review_payload_shows_affected_tasks_and_candidate_availability(self):
        task = self._task("ACT-LEAVE-REVIEW", date(2026, 9, 16))
        leave = self._leave(status="Pending")
        self.db.commit()
        review = workforce.review_leave_request(leave.id, self.db, self.manager_user)
        self.assertEqual(review.leave.id, leave.id)
        self.assertIn(task.id, [row.id for row in review.affected_tasks])
        candidate_ids = {row.employee_id for row in review.covering_candidates}
        self.assertIn(self.cover.id, candidate_ids)
        self.assertGreaterEqual(review.leave.affected_task_count, 1)


if __name__ == "__main__":
    unittest.main()
