import importlib.util
import os
import sys
import unittest
from datetime import date, timedelta, time
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine, func, select
from fastapi import HTTPException
from sqlalchemy.orm import DeclarativeBase, sessionmaker

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-that-is-long-enough-for-review-tests")

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    if "app.core.database" not in sys.modules:
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
    Crop,
    CropYieldRecord,
    Employee,
    FarmActivity,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    ResourceUsage,
    Role,
    TaskSubmission,
    User,
)
from app.routers.workforce import create_task, get_task_review_report, list_tasks, review_task, submit_task
from app.routers.crops import _annotate_pending_harvest_workflows
from app.services.crop_harvest_service import record_harvest
from app.schemas.workforce import TaskCreate, TaskReviewRequest, TaskSubmitRequest
from app.services.task_engine import _upsert_automatic_task


def _load_review_migration():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "w7f3b0d6e248_enforce_employee_task_review.py"
    spec = importlib.util.spec_from_file_location("review_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TaskReviewEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()
        self.ids = self._seed()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _seed(self):
        worker_role = Role(name="Review Worker", description="submit")
        worker_role.set_permissions(["workforce:submit"])
        manager_role = Role(name="Review Manager", description="manage/review")
        manager_role.set_permissions(["workforce:manage", "workforce:review"])
        self.db.add_all([worker_role, manager_role])
        self.db.flush()

        worker = User(
            user_code="USR-REVIEW-W",
            full_name="Review Worker",
            username="review.worker",
            password_hash="test",
            role=worker_role,
            status="Active",
        )
        manager = User(
            user_code="USR-REVIEW-M",
            full_name="Review Manager",
            username="review.manager",
            password_hash="test",
            role=manager_role,
            status="Active",
        )
        self.db.add_all([worker, manager])
        self.db.flush()

        employee = Employee(
            employee_code="EMP-REVIEW-1",
            full_name="Review Worker",
            position="Farm Worker",
            employment_status="Active",
            login_user_id=worker.id,
        )
        self.db.add(employee)
        self.db.flush()

        crop = Crop(
            crop_code="CRP-REVIEW-1",
            name="Tomato",
            variety="Roma",
            field="Field Review",
            area_hectares=1,
            quantity_planted=100,
            current_surviving=95,
            planting_date=date.today() - timedelta(days=30),
            estimated_harvest=date.today() + timedelta(days=45),
            status="Growing",
            assigned_employee_id=employee.id,
        )
        fertilizer = InventoryItem(
            item_code="INV-REVIEW-FERT",
            name="Review Fertilizer",
            category="Fertilizer",
            quantity=20,
            unit="kg",
            reorder_level=2,
            cost=100,
            price=120,
            supplier="Review Supplier",
            date_acquired=date.today() - timedelta(days=5),
            location="Storage",
        )
        feed = InventoryItem(
            item_code="INV-REVIEW-FEED",
            name="Review Grower Feed",
            category="Livestock Feed",
            quantity=20,
            unit="kg",
            reorder_level=2,
            cost=50,
            price=60,
            supplier="Review Supplier",
            date_acquired=date.today() - timedelta(days=5),
            location="Feed Room",
        )
        self.db.add_all([crop, fertilizer, feed])
        self.db.flush()

        livestock = Livestock(
            animal_code="LIV-REVIEW-1",
            record_name="Review Pigs",
            animal_type="Pig",
            breed="Large White",
            quantity=2,
            sex="Mixed",
            date_of_birth=date.today() - timedelta(days=120),
            weight_kg=35,
            pen_location="Review Pen",
            date_acquired=date.today() - timedelta(days=100),
            assigned_employee_id=employee.id,
            feed_inventory_item_id=feed.id,
            daily_feed_kg=1.5,
            feed_times="Twice Daily",
            feed_type=feed.name,
        )
        self.db.add(livestock)
        self.db.commit()
        return {
            "worker": worker.id,
            "manager": manager.id,
            "employee": employee.id,
            "crop": crop.id,
            "fertilizer": fertilizer.id,
            "feed": feed.id,
            "livestock": livestock.id,
        }

    def worker(self):
        return self.db.get(User, self.ids["worker"])

    def manager(self):
        return self.db.get(User, self.ids["manager"])

    def _task(self, *, code, source_module=None, source_type="manual_work", inventory_id=None, quantity=None, unit=None, automatic=False, requires_review=False):
        task = FarmActivity(
            activity_code=code,
            name="Review workflow task",
            category="Farm Work",
            related_to="Review target",
            location="Jorros Farm",
            activity_date=date.today(),
            start_time=time(8, 0),
            assigned_by=self.manager().full_name,
            assigned_to=self.db.get(Employee, self.ids["employee"]).full_name,
            assigned_employee_id=self.ids["employee"],
            status="Pending",
            priority="Medium",
            requires_review=requires_review,
            source_module=source_module,
            source_type=source_type,
            source_record_id=(self.ids["crop"] if source_module == "Crop" else self.ids["livestock"] if source_module == "Livestock" else None),
            planned_inventory_item_id=inventory_id,
            planned_quantity=quantity,
            planned_unit=unit,
            planned_usage_type=("Fertilizer" if source_module == "Crop" and inventory_id else "Feed" if source_type == "livestock_feeding" else None),
            is_automatic=automatic,
            source_key=f"review:{code}" if automatic else None,
        )
        self.db.add(task)
        self.db.commit()
        return task

    def test_manual_employee_task_requires_review_even_if_requested_false(self):
        created = create_task(
            TaskCreate(
                name="Manual review task",
                category="General Care",
                activity_date=date.today(),
                employee_id=self.ids["employee"],
                requires_review=False,
            ),
            self.db,
            self.manager(),
        )
        self.assertTrue(created.requires_review)

        result = submit_task(
            created.id,
            TaskSubmitRequest(worker_notes="Manual work completed."),
            self.db,
            self.worker(),
            "review-manual-1",
        )
        self.assertEqual(result.status, "Submitted for Review")
        self.assertIsNotNone(result.latest_submission)
        self.assertEqual(result.latest_submission.review_status, "Submitted")
        self.assertEqual(result.latest_submission.worker_notes, "Manual work completed.")

    def test_automatic_livestock_feeding_submission_reserves_until_review(self):
        task = self._task(
            code="ACT-REVIEW-FEED",
            source_module="Livestock",
            source_type="livestock_feeding",
            inventory_id=self.ids["feed"],
            quantity=1.5,
            unit="kg",
            automatic=True,
            requires_review=False,
        )
        result = submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=1.5, actual_unit="kg", worker_notes="Feeding completed."),
            self.db,
            self.worker(),
            "review-feed-1",
        )
        self.assertEqual(result.status, "Submitted for Review")
        self.assertEqual(result.latest_submission.review_status, "Submitted")
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["feed"]).quantity), 20.0)
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["feed"])),
            0,
        )
    
        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["feed"]).quantity), 18.5)
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["feed"])),
            1,
        )
    def test_automatic_crop_resource_submission_is_returned_by_admin_reload(self):
        task = self._task(
            code="ACT-REVIEW-CROP",
            source_module="Crop",
            source_type="care_template_step",
            inventory_id=self.ids["fertilizer"],
            quantity=2,
            unit="kg",
            automatic=True,
            requires_review=False,
        )
        result = submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=2, actual_unit="kg", worker_notes="Applied fertilizer."),
            self.db,
            self.worker(),
            "review-crop-1",
        )
        self.assertEqual(result.status, "Submitted for Review")

        # Simulate Task Management reload using its default Actionable Now API query.
        reloaded = list_tasks(
            employee_id=None,
            task_status=None,
            date_from=None,
            date_to=None,
            source_module=None,
            source_record_id=None,
            open_only=False,
            actionable_only=True,
            db=self.db,
            current_user=self.manager(),
        )
        match = next((row for row in reloaded if row.id == task.id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match.status, "Submitted for Review")
        self.assertEqual(match.latest_submission.review_status, "Submitted")
        self.assertEqual(match.latest_submission.employee_id, self.ids["employee"])
        self.assertEqual(match.latest_submission.worker_notes, "Applied fertilizer.")
        self.assertAlmostEqual(match.latest_submission.actual_quantity, 2.0)
        self.assertEqual(match.latest_submission.actual_unit, "kg")

    def test_manager_assisted_approve_now_is_explicit_immediate_completion_exception(self):
        task = self._task(code="ACT-REVIEW-ASSIST", requires_review=False)
        result = submit_task(
            task.id,
            TaskSubmitRequest(
                performed_by_employee_id=self.ids["employee"],
                assisted_reason="Manager directly observed the completed work.",
                approve_now=True,
                worker_notes="Recorded with employee present.",
            ),
            self.db,
            self.manager(),
            "review-assisted-1",
        )
        self.assertEqual(result.status, "Completed")
        self.assertEqual(result.latest_submission.review_status, "Approved")
        self.assertEqual(result.latest_submission.reviewed_by_user_id, self.ids["manager"])

    def test_manager_assisted_record_work_is_blocked_until_reassignment_is_resolved(self):
        task = self._task(code="ACT-REVIEW-ASSIST-REASSIGN", requires_review=True)
        task.needs_reassignment = True
        self.db.commit()

        with self.assertRaises(HTTPException) as blocked:
            submit_task(
                task.id,
                TaskSubmitRequest(
                    performed_by_employee_id=self.ids["employee"],
                    assisted_reason="Manager observed the work.",
                ),
                self.db,
                self.manager(),
                "review-assisted-needs-reassignment",
            )
        self.assertEqual(blocked.exception.status_code, 400)
        self.assertIn("Reassign this task", blocked.exception.detail)
        self.assertEqual(self.db.get(FarmActivity, task.id).status, "Pending")

    def test_manager_assisted_record_work_is_blocked_when_task_has_no_current_assignee(self):
        task = self._task(code="ACT-REVIEW-ASSIST-UNASSIGNED", requires_review=True)
        task.assigned_employee_id = None
        task.assigned_to = "Unassigned"
        task.needs_reassignment = True
        self.db.commit()

        with self.assertRaises(HTTPException) as blocked:
            submit_task(
                task.id,
                TaskSubmitRequest(
                    performed_by_employee_id=self.ids["employee"],
                    assisted_reason="Manager observed the work.",
                ),
                self.db,
                self.manager(),
                "review-assisted-unassigned",
            )
        self.assertEqual(blocked.exception.status_code, 400)
        self.assertIn("Reassign this task", blocked.exception.detail)

    def test_scheduler_preserves_existing_occurrence_review_state(self):
        task = self._task(
            code="ACT-REVIEW-SCHED",
            source_module="Crop",
            source_type="crop_watering",
            automatic=True,
            requires_review=False,
        )
        original_employee_id = task.assigned_employee_id
        _, result = _upsert_automatic_task(
            self.db,
            source_key=task.source_key,
            source_module="Crop",
            source_type="crop_watering",
            source_record_id=self.ids["crop"],
            source_detail_id=None,
            source_code="CRP-REVIEW-1",
            source_path="/crops",
            name="Water Tomato — Morning",
            category="Crop Watering",
            related_to="Tomato — Field Review",
            location="Field Review",
            description="Existing occurrence refresh.",
            activity_date=date.today(),
            start_time=time(6, 0),
            assigned_to="Farm Staff",
            priority="Medium",
        )
        self.assertEqual(result, "updated")
        self.assertEqual(task.assigned_employee_id, original_employee_id)
        self.assertFalse(task.requires_review)

    def test_mssql_migration_replaces_existing_default_constraint_before_adding_new_default(self):
        migration = _load_review_migration()

        class _Dialect:
            name = "mssql"

        class _Bind:
            dialect = _Dialect()

            def __init__(self):
                self.statements = []

            def execute(self, statement):
                self.statements.append(str(statement))

        bind = _Bind()
        migration._set_requires_review_default(bind, True)

        self.assertEqual(len(bind.statements), 1)
        sql = bind.statements[0]
        self.assertIn("sys.default_constraints", sql)
        self.assertIn("DROP CONSTRAINT", sql)
        self.assertIn("DF_farm_activities_requires_review", sql)
        self.assertIn("DEFAULT (1)", sql)
        self.assertIn("DECLARE @sql nvarchar(max)", sql)
        self.assertIn("EXEC sys.sp_executesql @sql", sql)
        self.assertNotIn("EXEC(\n        N'ALTER TABLE ' + QUOTENAME", sql)

    def test_migration_repairs_open_review_state_and_preserves_terminal_history(self):
        open_task = self._task(code="ACT-REVIEW-LEGACY-OPEN", requires_review=False)
        submitted_task = self._task(code="ACT-REVIEW-LEGACY-SUB", requires_review=False)
        terminal = []
        for status in ["Completed", "Voided", "Cancelled", "Resolved", "Approved"]:
            row = self._task(code=f"ACT-REVIEW-{status.upper()}", requires_review=False)
            row.status = status
            terminal.append(row)
        archived = self._task(code="ACT-REVIEW-ARCHIVED", requires_review=False)
        archived.is_archived = True

        self.db.add(TaskSubmission(
            activity_id=submitted_task.id,
            employee_id=self.ids["employee"],
            recorded_by_user_id=self.ids["worker"],
            attempt_number=1,
            review_status="Submitted",
            worker_notes="Legacy submitted work",
        ))
        self.db.commit()

        migration = _load_review_migration()
        bind = self.db.connection()
        migration._repair_open_employee_tasks(bind)
        migration._repair_submitted_task_status(bind)
        self.db.commit()
        self.db.expire_all()

        self.assertTrue(self.db.get(FarmActivity, open_task.id).requires_review)
        repaired = self.db.get(FarmActivity, submitted_task.id)
        self.assertTrue(repaired.requires_review)
        self.assertEqual(repaired.status, "Submitted for Review")
        for row in terminal:
            preserved = self.db.get(FarmActivity, row.id)
            self.assertFalse(preserved.requires_review)
            self.assertEqual(preserved.status, row.status)
        preserved_archived = self.db.get(FarmActivity, archived.id)
        self.assertFalse(preserved_archived.requires_review)
        self.assertTrue(preserved_archived.is_archived)

    def test_review_report_contains_reserved_inventory_and_previous_history(self):
        task = self._task(
            code="ACT-REVIEW-REPORT",
            source_module="Crop",
            source_type="care_template_step",
            inventory_id=self.ids["fertilizer"],
            quantity=2,
            unit="kg",
            automatic=True,
            requires_review=True,
        )
        submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=2, actual_unit="kg", worker_notes="First application complete."),
            self.db,
            self.worker(),
            "review-report-1",
        )
        first_report = get_task_review_report(task.id, self.db, self.manager())
        self.assertEqual(first_report.task.id, task.id)
        self.assertEqual(first_report.current_submission.attempt_number, 1)
        self.assertEqual(first_report.current_submission.worker_notes, "First application complete.")
        self.assertTrue(first_report.resource_usage.tracked)
        self.assertEqual(first_report.resource_usage.inventory_item_name, "Review Fertilizer")
        self.assertEqual(first_report.resource_usage.deduction_status, "Reserved - Awaiting Approval")
        self.assertEqual(len(first_report.resource_usage.movements), 0)
        self.assertIsNone(first_report.resource_usage.resource_usage_id)
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["fertilizer"]).quantity), 20.0)
    
        review_task(
            task.id,
            TaskReviewRequest(decision="Return", feedback="Use the verified actual quantity."),
            self.db,
            self.manager(),
        )
        submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=3, actual_unit="kg", worker_notes="Corrected actual quantity."),
            self.db,
            self.worker(),
            "review-report-2",
        )
        corrected = get_task_review_report(task.id, self.db, self.manager())
        self.assertEqual(corrected.current_submission.attempt_number, 2)
        self.assertEqual(corrected.resource_usage.quantity_difference, 1.0)
        self.assertEqual(corrected.resource_usage.deduction_status, "Reserved - Awaiting Approval")
        self.assertEqual(corrected.resource_usage.movements, [])
        self.assertEqual(len(corrected.previous_submissions), 1)
        self.assertEqual(corrected.previous_submissions[0].review_status, "Returned")
        self.assertEqual(corrected.previous_submissions[0].reviewed_by_name, self.manager().full_name)
        self.assertEqual(corrected.previous_submissions[0].review_feedback, "Use the verified actual quantity.")
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["fertilizer"]).quantity), 20.0)
    
        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["fertilizer"]).quantity), 17.0)
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["fertilizer"])),
            1,
        )
    def test_review_report_is_forbidden_to_employee_and_stale_review_is_conflict(self):
        task = self._task(code="ACT-REVIEW-REPORT-AUTH", requires_review=True)
        submit_task(
            task.id,
            TaskSubmitRequest(worker_notes="Ready for review."),
            self.db,
            self.worker(),
            "review-report-auth",
        )
        with self.assertRaises(HTTPException) as unauthorized:
            get_task_review_report(task.id, self.db, self.worker())
        self.assertEqual(unauthorized.exception.status_code, 403)

        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        with self.assertRaises(HTTPException) as stale_report:
            get_task_review_report(task.id, self.db, self.manager())
        self.assertEqual(stale_report.exception.status_code, 409)
        with self.assertRaises(HTTPException) as stale_decision:
            review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertEqual(stale_decision.exception.status_code, 409)


    def test_crop_harvest_submission_waits_for_task_management_and_preserves_partial_intent(self):
        crop = self.db.get(Crop, self.ids["crop"])
        crop.status = "Ready for Harvest"
        crop.growth_stage = "Harvest Ready"
        crop.estimated_harvest = date.today()
        task = self._task(
            code="ACT-REVIEW-HARVEST-REL",
            source_module="Crop",
            source_type="crop_harvest",
            requires_review=True,
        )

        with self.assertRaises(HTTPException) as missing_type:
            submit_task(
                task.id,
                TaskSubmitRequest(actual_quantity=4, actual_unit="kg"),
                self.db,
                self.worker(),
                "harvest-intent-missing",
            )
        self.assertEqual(missing_type.exception.status_code, 400)
        self.assertIn("Partial Harvest or Final Harvest", missing_type.exception.detail)

        submitted = submit_task(
            task.id,
            TaskSubmitRequest(
                actual_quantity=4,
                actual_unit="kg",
                harvest_type_intent="Partial Harvest",
                worker_notes="First picking only; more fruit remains.",
            ),
            self.db,
            self.worker(),
            "harvest-intent-partial",
        )
        self.assertEqual(submitted.status, "Submitted for Review")
        report = get_task_review_report(task.id, self.db, self.manager())
        self.assertEqual(report.current_submission.harvest_type_intent, "Partial Harvest")
        self.assertIsNone(report.current_submission.harvest_type_confirmed)

        _annotate_pending_harvest_workflows(self.db, [crop])
        self.assertEqual(crop.pending_harvest_task_id, task.id)
        self.assertEqual(crop.pending_harvest_type, "Partial Harvest")
        self.assertEqual(crop.pending_harvest_message, "Waiting for Partial Harvest Confirmation")

        with self.assertRaises(HTTPException) as duplicate_path:
            record_harvest(
                self.db,
                crop=crop,
                harvest_date=date.today(),
                quantity_kg=4,
                harvest_type="Partial Harvest",
                actor=self.manager(),
                performed_by_employee_id=self.ids["employee"],
                manual_reason="Should not bypass the linked task",
            )
        self.assertEqual(duplicate_path.exception.status_code, 409)
        self.assertIn("Waiting for Partial Harvest Confirmation", duplicate_path.exception.detail)

        with self.assertRaises(HTTPException) as silent_change:
            review_task(
                task.id,
                TaskReviewRequest(decision="Approve", harvest_type="Final Harvest", final_harvest_confirmed=True),
                self.db,
                self.manager(),
            )
        self.assertEqual(silent_change.exception.status_code, 400)
        self.assertIn("employee submitted this as Partial Harvest", silent_change.exception.detail)

        approved = review_task(
            task.id,
            TaskReviewRequest(decision="Approve", harvest_type="Partial Harvest"),
            self.db,
            self.manager(),
        )
        self.assertEqual(approved.status, "Completed")
        submission = self.db.scalar(select(TaskSubmission).where(TaskSubmission.activity_id == task.id))
        self.assertEqual(submission.harvest_type_intent, "Partial Harvest")
        self.assertEqual(submission.harvest_type_confirmed, "Partial Harvest")
        yield_row = self.db.scalar(select(CropYieldRecord).where(CropYieldRecord.related_task_id == task.id))
        self.assertIsNotNone(yield_row)
        self.assertEqual(yield_row.harvest_type, "Partial Harvest")
        self.assertEqual(crop.status, "Harvesting")

    def test_review_can_confirm_first_final_yield_for_legacy_completed_crop(self):
        crop = self.db.get(Crop, self.ids["crop"])
        crop.status = "Harvested"  # Older data can be marked complete without a final yield.
        task = self._task(
            code="ACT-REVIEW-LEGACY-FINAL",
            source_module="Crop", source_type="crop_harvest", requires_review=True,
        )
        submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=26, actual_unit="kg", harvest_type_intent="Final Harvest"),
            self.db, self.worker(), "legacy-final-26kg",
        )
        report = get_task_review_report(task.id, self.db, self.manager())
        self.assertEqual(report.crop_status, "Harvested")
        self.assertIsNone(report.harvest_approval_blocker)

        approved = review_task(
            task.id,
            TaskReviewRequest(decision="Approve", harvest_type="Final Harvest", final_harvest_confirmed=True),
            self.db, self.manager(),
        )
        self.assertEqual(approved.status, "Completed")
        yields = list(self.db.scalars(select(CropYieldRecord).where(CropYieldRecord.crop_id == crop.id)).all())
        self.assertEqual(len(yields), 1)
        self.assertEqual(yields[0].related_task_id, task.id)
        self.assertEqual(float(yields[0].quantity_kg), 26.0)
        self.assertEqual(crop.status, "Harvested")
        with self.assertRaises(HTTPException) as repeated:
            review_task(
                task.id,
                TaskReviewRequest(decision="Approve", harvest_type="Final Harvest", final_harvest_confirmed=True),
                self.db, self.manager(),
            )
        self.assertEqual(repeated.exception.status_code, 409)
        self.assertEqual(self.db.scalar(select(func.count(CropYieldRecord.id)).where(CropYieldRecord.crop_id == crop.id)), 1)

    def test_review_blocks_duplicate_final_yield_and_explains_conflict(self):
        crop = self.db.get(Crop, self.ids["crop"])
        crop.status = "Ready for Harvest"
        record_harvest(
            self.db, crop=crop, harvest_date=date.today(), quantity_kg=14,
            harvest_type="Final Harvest", actor=self.manager(),
            performed_by_employee_id=self.ids["employee"],
            manual_reason="Existing recorded final yield", final_harvest_confirmed=True,
        )
        task = self._task(
            code="ACT-REVIEW-DUPLICATE-FINAL",
            source_module="Crop", source_type="crop_harvest", requires_review=True,
        )
        submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=26, actual_unit="kg", harvest_type_intent="Final Harvest"),
            self.db, self.worker(), "duplicate-final-26kg",
        )
        report = get_task_review_report(task.id, self.db, self.manager())
        self.assertIn("already has a Final Harvest of 14 kg", report.harvest_approval_blocker)

        with self.assertRaises(HTTPException) as blocked:
            review_task(
                task.id,
                TaskReviewRequest(decision="Approve", harvest_type="Final Harvest", final_harvest_confirmed=True),
                self.db, self.manager(),
            )
        self.assertEqual(blocked.exception.status_code, 409)
        self.assertIn("count it twice", blocked.exception.detail)
        self.assertEqual(self.db.get(FarmActivity, task.id).status, "Submitted for Review")
        self.assertEqual(self.db.scalar(select(func.count(CropYieldRecord.id)).where(CropYieldRecord.crop_id == crop.id)), 1)
        submission = self.db.scalar(select(TaskSubmission).where(TaskSubmission.activity_id == task.id))
        self.assertIsNone(submission.harvest_type_confirmed)

    def test_review_blocks_historical_final_before_later_recorded_harvest(self):
        crop = self.db.get(Crop, self.ids["crop"])
        crop.status = "Ready for Harvest"
        record_harvest(
            self.db, crop=crop, harvest_date=date.today(), quantity_kg=5,
            harvest_type="Partial Harvest", actor=self.manager(),
            performed_by_employee_id=self.ids["employee"],
            manual_reason="Later recorded harvest",
        )
        crop.status = "Harvested"  # Legacy completion without a Final Harvest row.
        task = self._task(
            code="ACT-REVIEW-EARLIER-FINAL",
            source_module="Crop", source_type="crop_harvest", requires_review=True,
        )
        task.activity_date = date.today() - timedelta(days=1)
        self.db.commit()
        submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=26, actual_unit="kg", harvest_type_intent="Final Harvest"),
            self.db, self.worker(), "earlier-final-26kg",
        )
        report = get_task_review_report(task.id, self.db, self.manager())
        self.assertIn("after this task's", report.harvest_approval_blocker)
        with self.assertRaises(HTTPException) as blocked:
            review_task(
                task.id,
                TaskReviewRequest(decision="Approve", harvest_type="Final Harvest", final_harvest_confirmed=True),
                self.db, self.manager(),
            )
        self.assertEqual(blocked.exception.status_code, 409)
        self.assertEqual(self.db.scalar(select(func.count(CropYieldRecord.id)).where(CropYieldRecord.crop_id == crop.id)), 1)

    def test_manager_can_record_a_forgotten_harvest_for_employee_then_review_it(self):
        crop = self.db.get(Crop, self.ids["crop"])
        crop.status = "Ready for Harvest"
        crop.growth_stage = "Harvest Ready"
        crop.estimated_harvest = date.today()
        task = self._task(
            code="ACT-REVIEW-HARVEST-ASSISTED",
            source_module="Crop",
            source_type="crop_harvest",
            requires_review=True,
        )

        with self.assertRaises(HTTPException) as unconfirmed:
            submit_task(
                task.id,
                TaskSubmitRequest(
                    actual_quantity=6.25,
                    actual_unit="kg",
                    harvest_type_intent="Partial Harvest",
                    performed_by_employee_id=self.ids["employee"],
                    assisted_reason="Employee forgot to submit the completed harvest.",
                ),
                self.db,
                self.manager(),
                "harvest-assisted-unconfirmed",
            )
        self.assertEqual(unconfirmed.exception.status_code, 400)
        self.assertIn("actual harvested yield", unconfirmed.exception.detail)
        self.db.rollback()

        submitted = submit_task(
            task.id,
            TaskSubmitRequest(
                actual_quantity=6.25,
                actual_quantity_confirmed=True,
                actual_unit="kg",
                harvest_type_intent="Partial Harvest",
                performed_by_employee_id=self.ids["employee"],
                assisted_reason="Employee forgot to submit the completed harvest.",
                worker_notes="Manager recorded the employee's verified field result.",
            ),
            self.db,
            self.manager(),
            "harvest-assisted-confirmed",
        )
        self.assertEqual(submitted.status, "Submitted for Review")
        self.assertEqual(submitted.latest_submission.employee_id, self.ids["employee"])
        self.assertEqual(submitted.latest_submission.recorded_by_user_id, self.ids["manager"])
        self.assertEqual(submitted.latest_submission.harvest_type_intent, "Partial Harvest")
        self.assertAlmostEqual(submitted.latest_submission.actual_quantity, 6.25)

        approved = review_task(
            task.id,
            TaskReviewRequest(decision="Approve", harvest_type="Partial Harvest"),
            self.db,
            self.manager(),
        )
        self.assertEqual(approved.status, "Completed")
        yield_row = self.db.scalar(select(CropYieldRecord).where(CropYieldRecord.related_task_id == task.id))
        self.assertIsNotNone(yield_row)
        self.assertAlmostEqual(float(yield_row.quantity_kg), 6.25)
        self.assertEqual(yield_row.performed_by_employee_id, self.ids["employee"])

    def test_duplicate_retry_reserves_once_and_review_deducts_once(self):
        task = self._task(
            code="ACT-REVIEW-IDEMP",
            source_module="Crop",
            source_type="care_template_step",
            inventory_id=self.ids["fertilizer"],
            quantity=2,
            unit="kg",
            automatic=True,
            requires_review=False,
        )
        payload = TaskSubmitRequest(actual_quantity=2, actual_unit="kg")
        first = submit_task(task.id, payload, self.db, self.worker(), "review-idempotent-1")
        second = submit_task(task.id, payload, self.db, self.worker(), "review-idempotent-1")
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            self.db.scalar(select(func.count(TaskSubmission.id)).where(TaskSubmission.activity_id == task.id)),
            1,
        )
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["fertilizer"])),
            0,
        )
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["fertilizer"]).quantity), 20.0)
    
        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["fertilizer"]).quantity), 18.0)
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["fertilizer"])),
            1,
        )

if __name__ == "__main__":
    unittest.main()
