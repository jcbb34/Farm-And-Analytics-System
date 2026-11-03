import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import date, timedelta, time
from types import ModuleType

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, func, select
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
from app.models import (  # noqa: F401 - register all tables
    Crop,
    Employee,
    FarmActivity,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    ResourceUsage,
    Role,
    StaffLeave,
    TaskLeaveCoverage,
    TaskSubmission,
    User,
)
from app.routers.inventory import create_stock_adjustment
from app.routers.livestock import create_feeding_record
from app.routers.workforce import review_task, start_task, submit_task, void_task
from app.schemas.inventory import InventoryStockAdjustmentCreate
from app.schemas.livestock import LivestockFeedingCreate
from app.schemas.workforce import TaskReviewRequest, TaskStartRequest, TaskSubmitRequest, TaskVoidRequest


class TaskInventoryTransactionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()
        self.ids = self._seed(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def _seed(db):
        worker_role = Role(name="Inventory Worker", description="submit")
        worker_role.set_permissions(["workforce:submit"])
        manager_role = Role(name="Inventory Manager", description="manage")
        manager_role.set_permissions(["workforce:manage", "workforce:review"])
        db.add_all([worker_role, manager_role])
        db.flush()

        worker_user = User(
            user_code="USR-TASKINV-W",
            full_name="Inventory Worker",
            username="inventory.worker",
            password_hash="test",
            role=worker_role,
            status="Active",
        )
        manager_user = User(
            user_code="USR-TASKINV-M",
            full_name="Inventory Manager",
            username="inventory.manager",
            password_hash="test",
            role=manager_role,
            status="Active",
        )
        db.add_all([worker_user, manager_user])
        db.flush()

        employee = Employee(
            employee_code="EMP-TASKINV-1",
            full_name="Inventory Worker",
            position="Farm Worker",
            employment_status="Active",
            login_user_id=worker_user.id,
        )
        db.add(employee)
        db.flush()

        crop = Crop(
            crop_code="CRP-TASKINV-1",
            name="Eggplant",
            variety="Purple Long",
            field="Field A",
            area_hectares=1,
            quantity_planted=100,
            current_surviving=100,
            planting_date=date.today() - timedelta(days=20),
            estimated_harvest=date.today() + timedelta(days=60),
            status="Growing",
        )
        item = InventoryItem(
            item_code="INV-FERT-TASK-1",
            name="Complete Fertilizer",
            category="Fertilizer",
            quantity=10,
            unit="kg",
            reorder_level=2,
            cost=100,
            price=120,
            supplier="Test Supplier",
            date_acquired=date.today() - timedelta(days=10),
            location="Storage A",
        )
        feed_item = InventoryItem(
            item_code="INV-FEED-TASK-1",
            name="Grower Feed",
            category="Livestock Feed",
            quantity=10,
            unit="kg",
            reorder_level=2,
            cost=50,
            price=60,
            supplier="Test Supplier",
            date_acquired=date.today() - timedelta(days=10),
            location="Feed Room",
        )
        db.add_all([crop, item, feed_item])
        db.flush()

        livestock = Livestock(
            animal_code="LIV-TASKINV-1",
            record_name="Test Grower Pigs",
            animal_type="Pig",
            breed="Large White",
            quantity=2,
            sex="Mixed",
            date_of_birth=date.today() - timedelta(days=100),
            weight_kg=30,
            pen_location="Pig Pen 1",
            date_acquired=date.today() - timedelta(days=90),
            feed_inventory_item_id=feed_item.id,
            daily_feed_kg=1.5,
            feed_times="Twice Daily",
            feed_type="Grower Feed",
        )
        db.add(livestock)
        db.flush()

        task = FarmActivity(
            activity_code="ACT-TASKINV-001",
            name="Apply fertilizer",
            category="Crop Care",
            related_to="Eggplant — Field A",
            location="Field A",
            activity_date=date.today(),
            start_time=time(8, 0),
            assigned_by=manager_user.full_name,
            assigned_to=employee.full_name,
            assigned_employee_id=employee.id,
            status="Pending",
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
            source_module="Crop",
            source_type="care_template_step",
            source_record_id=crop.id,
            planned_inventory_item_id=item.id,
            planned_usage_type="Fertilizer",
            planned_quantity=2,
            planned_unit="kg",
        )
        db.add(task)
        db.commit()
        return {
            "worker_user": worker_user.id,
            "manager_user": manager_user.id,
            "employee": employee.id,
            "crop": crop.id,
            "item": item.id,
            "feed_item": feed_item.id,
            "livestock": livestock.id,
            "task": task.id,
        }

    def worker(self, db=None):
        return (db or self.db).get(User, self.ids["worker_user"])

    def manager(self, db=None):
        return (db or self.db).get(User, self.ids["manager_user"])

    def administrator(self):
        role = Role(name="Void Test Administrator", is_active=True)
        role.set_permissions(["*"])
        account = User(user_code="VOID-TEST-ADMIN", username="void.test.admin", full_name="Void Test Administrator", password_hash="test", role=role, status="Active")
        self.db.add(account)
        self.db.commit()
        return account

    def task(self, db=None):
        return (db or self.db).get(FarmActivity, self.ids["task"])

    def item(self, db=None):
        return (db or self.db).get(InventoryItem, self.ids["item"])

    def submit(self, quantity, key, *, db=None, user=None, **extra):
        db = db or self.db
        payload = TaskSubmitRequest(actual_quantity=quantity, actual_unit="kg", **extra)
        return submit_task(self.ids["task"], payload, db, user or self.worker(db), key)

    def movement_types(self, db=None):
        db = db or self.db
        return list(db.scalars(
            select(InventoryStockRecord.adjustment_type)
            .where(InventoryStockRecord.inventory_item_id == self.ids["item"])
            .order_by(InventoryStockRecord.id)
        ).all())

    def test_submit_reserves_inventory_without_deducting(self):
        result = self.submit(2, "task-submit-1")
        self.assertEqual(result.status, "Submitted for Review")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), [])
        usage = self.db.scalar(select(ResourceUsage).where(ResourceUsage.activity_id == self.ids["task"]))
        self.assertIsNone(usage)
        submission = self.db.scalar(select(TaskSubmission).where(TaskSubmission.activity_id == self.ids["task"]))
        self.assertIsNotNone(submission)
        self.assertEqual(submission.review_status, "Submitted")

    def test_full_worker_manager_lifecycle_posts_once_and_reverses_on_void(self):
        task_id = self.ids["task"]
        start_task(task_id, TaskStartRequest(), self.db, self.worker())
        self.assertEqual(self.task().status, "In Progress")

        self.submit(2, "release-first-attempt")
        self.assertEqual(self.task().status, "Submitted for Review")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        review_task(
            task_id,
            TaskReviewRequest(decision="Return", feedback="Correct the amount used."),
            self.db,
            self.manager(),
        )
        self.assertEqual(self.task().status, "Returned")
        self.assertEqual(self.movement_types(), [])

        start_task(task_id, TaskStartRequest(), self.db, self.worker())
        self.submit(3, "release-corrected-attempt")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        review_task(task_id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertEqual(self.task().status, "Completed")
        self.assertAlmostEqual(float(self.item().quantity), 7.0)
        self.assertEqual(self.movement_types(), ["Task Usage"])

        with self.assertRaises(HTTPException):
            review_task(task_id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        with self.assertRaises(HTTPException) as denied:
            void_task(self.ids["task"], TaskVoidRequest(reason="Manager needs owner approval"), self.db, self.manager())
        self.assertEqual(denied.exception.status_code, 403)
        void_task(
            task_id,
            TaskVoidRequest(reason="The manager found the corrected entry was invalid."),
            self.db,
            self.administrator(),
        )
        self.assertEqual(self.task().status, "Voided")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), ["Task Usage", "Usage Reversal"])
    def test_duplicate_submit_same_key_returns_one_reservation_and_one_approval_deduction(self):
        first = self.submit(2, "task-duplicate-1")
        second = self.submit(2, "task-duplicate-1")
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.scalar(select(func.count(TaskSubmission.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(InventoryStockRecord.id))), 0)
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
    
        review_task(
            self.ids["task"],
            TaskReviewRequest(decision="Approve"),
            self.db,
            self.manager(),
        )
        self.assertEqual(self.db.scalar(select(func.count(InventoryStockRecord.id))), 1)
        self.assertAlmostEqual(float(self.item().quantity), 8.0)
    def test_leave_coverage_submission_reserves_then_approval_posts_inventory_once(self):
        task = self.task()
        cover = self.db.get(Employee, self.ids["employee"])
        original = Employee(
            employee_code="EMP-TASKINV-ORIGINAL",
            full_name="Original Worker",
            position="Farm Worker",
            employment_status="Active",
        )
        self.db.add(original)
        self.db.flush()
        crop = self.db.get(Crop, self.ids["crop"])
        crop.assigned_employee_id = original.id
        leave = StaffLeave(
            employee_id=original.id,
            leave_type="Vacation Leave",
            start_date=date.today(),
            end_date=date.today(),
            status="Approved",
            reason="Approved leave",
            decided_by_user_id=self.ids["manager_user"],
        )
        self.db.add(leave)
        self.db.flush()
        task.assigned_employee_id = cover.id
        task.assigned_to = cover.full_name
        task.assignment_source = "Leave Coverage"
        self.db.add(TaskLeaveCoverage(
            activity_id=task.id,
            leave_id=leave.id,
            original_employee_id=original.id,
            covering_employee_id=cover.id,
            coverage_start_date=leave.start_date,
            coverage_end_date=leave.end_date,
            status="Active",
            reason="Vacation Leave coverage",
            approved_by_user_id=self.ids["manager_user"],
            source_module=task.source_module,
            source_type=task.source_type,
            source_record_id=task.source_record_id,
        ))
        self.db.commit()
    
        first = self.submit(2, "coverage-task-submit-1")
        second = self.submit(2, "coverage-task-submit-1")
        submission = self.db.scalar(select(TaskSubmission).where(TaskSubmission.activity_id == task.id))
        self.assertEqual(first.id, second.id)
        self.assertEqual(submission.employee_id, cover.id)
        self.assertEqual(self.db.scalar(select(func.count(TaskSubmission.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(InventoryStockRecord.id))), 0)
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
    
        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertEqual(self.db.scalar(select(func.count(InventoryStockRecord.id))), 1)
        self.assertAlmostEqual(float(self.item().quantity), 8.0)
    def test_concurrent_same_key_creates_one_attempt_and_no_preapproval_deduction(self):
        self.db.close()
        self.engine.dispose()
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(
                f"sqlite+pysqlite:///{tmp}/concurrent.db",
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)
            seed = Session()
            ids = self._seed(seed)
            seed.close()
            barrier = threading.Barrier(2)
            results = []
            errors = []
    
            def run_submit():
                db = Session()
                try:
                    barrier.wait(timeout=5)
                    result = submit_task(
                        ids["task"],
                        TaskSubmitRequest(actual_quantity=2, actual_unit="kg"),
                        db,
                        db.get(User, ids["worker_user"]),
                        "task-concurrent-1",
                    )
                    results.append(result.status)
                except Exception as exc:  # pragma: no cover - assertion below reports details
                    errors.append(exc)
                finally:
                    db.close()
    
            threads = [threading.Thread(target=run_submit), threading.Thread(target=run_submit)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
    
            verify = Session()
            try:
                self.assertEqual(errors, [])
                self.assertEqual(len(results), 2)
                self.assertEqual(verify.scalar(select(func.count(TaskSubmission.id))), 1)
                self.assertEqual(verify.scalar(select(func.count(InventoryStockRecord.id))), 0)
                self.assertAlmostEqual(float(verify.get(InventoryItem, ids["item"]).quantity), 10.0)
            finally:
                verify.close()
                engine.dispose()
    
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
    def test_database_allows_only_one_active_resource_posting_per_task(self):
        self.submit(2, "task-unique-active-1")
        review_task(self.ids["task"], TaskReviewRequest(decision="Approve"), self.db, self.manager())
        duplicate = ResourceUsage(
            inventory_item_id=self.ids["item"],
            module="Crop",
            crop_id=self.ids["crop"],
            activity_id=self.ids["task"],
            task_submission_id=None,
            task_posting_active=True,
            usage_type="Fertilizer",
            quantity=0.5,
            unit="kg",
            usage_date=date.today(),
            recorded_by_user_id=self.ids["worker_user"],
        )
        self.db.add(duplicate)
        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()
        self.assertEqual(
            self.db.scalar(select(func.count(ResourceUsage.id)).where(ResourceUsage.task_posting_active == True)),
            1,
        )
    def test_return_resubmit_increase_deducts_only_final_approved_quantity(self):
        self.submit(2, "task-increase-1")
        review_task(
            self.ids["task"],
            TaskReviewRequest(decision="Return", feedback="Correct the actual amount."),
            self.db,
            self.manager(),
        )
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), [])
    
        self.submit(3, "task-increase-2")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), [])
        review_task(self.ids["task"], TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.item().quantity), 7.0)
        self.assertEqual(self.movement_types(), ["Task Usage"])
        movements = list(self.db.scalars(select(InventoryStockRecord).order_by(InventoryStockRecord.id)).all())
        self.assertAlmostEqual(float(movements[-1].quantity), 3.0)
        self.assertEqual(self.db.scalar(select(func.count(TaskSubmission.id))), 2)
    def test_return_resubmit_decrease_deducts_only_final_approved_quantity(self):
        self.submit(2, "task-decrease-1")
        review_task(
            self.ids["task"],
            TaskReviewRequest(decision="Return", feedback="Correct the actual amount."),
            self.db,
            self.manager(),
        )
        self.submit(1, "task-decrease-2")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), [])
        review_task(self.ids["task"], TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.item().quantity), 9.0)
        self.assertEqual(self.movement_types(), ["Task Usage"])
        movements = list(self.db.scalars(select(InventoryStockRecord).order_by(InventoryStockRecord.id)).all())
        self.assertAlmostEqual(float(movements[-1].quantity), 1.0)
        self.assertAlmostEqual(float(movements[-1].previous_quantity), 10.0)
        self.assertAlmostEqual(float(movements[-1].new_quantity), 9.0)
    def test_approve_is_the_only_normal_inventory_deduction_point(self):
        self.submit(2, "task-approve-1")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), [])
        review_task(
            self.ids["task"],
            TaskReviewRequest(decision="Approve"),
            self.db,
            self.manager(),
        )
        self.assertEqual(self.task().status, "Completed")
        self.assertAlmostEqual(float(self.item().quantity), 8.0)
        self.assertEqual(self.movement_types(), ["Task Usage"])
    def test_void_pending_submission_is_rejected_without_stock_movement(self):
        self.submit(2, "task-void-1")
        with self.assertRaises(HTTPException) as caught:
            review_task(
                self.ids["task"],
                TaskReviewRequest(decision="Void", feedback="Work record was invalid and must be voided."),
                self.db,
                self.manager(),
            )
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(self.task().status, "Submitted for Review")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), [])
        usage = self.db.scalar(select(ResourceUsage).where(ResourceUsage.activity_id == self.ids["task"]))
        self.assertIsNone(usage)
    def test_completed_task_can_be_explicitly_voided_and_reversed(self):
        task = self.task()
        task.requires_review = False  # legacy metadata must not enable employee self-approval
        self.db.commit()
        submit_task(
            self.ids["task"],
            TaskSubmitRequest(
                actual_quantity=2,
                actual_unit="kg",
                actual_quantity_confirmed=True,
                performed_by_employee_id=self.ids["employee"],
                assisted_reason="Manager observed the completed work.",
                approve_now=True,
            ),
            self.db,
            self.manager(),
            "task-complete-void-1",
        )
        self.assertEqual(self.task().status, "Completed")
        with self.assertRaises(HTTPException) as denied:
            void_task(self.ids["task"], TaskVoidRequest(reason="Manager needs owner approval"), self.db, self.manager())
        self.assertEqual(denied.exception.status_code, 403)
        void_task(
            self.ids["task"],
            TaskVoidRequest(reason="Manager confirmed the completion entry was invalid."),
            self.db,
            self.administrator(),
        )
        self.assertEqual(self.task().status, "Voided")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.movement_types(), ["Task Usage", "Usage Reversal"])

    def test_insufficient_unreserved_stock_rolls_back_submission_and_stock(self):
        item = self.item()
        item.quantity = 1
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.submit(2, "task-insufficient-1")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("Insufficient unreserved stock", str(caught.exception.detail))
        self.db.rollback()
        self.assertAlmostEqual(float(self.item().quantity), 1.0)
        self.assertEqual(self.db.scalar(select(func.count(TaskSubmission.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(InventoryStockRecord.id))), 0)
    def test_unit_mismatch_is_rejected_before_posting(self):
        with self.assertRaises(HTTPException) as caught:
            submit_task(
                self.ids["task"],
                TaskSubmitRequest(actual_quantity=2, actual_unit="L"),
                self.db,
                self.worker(),
                "task-unit-1",
            )
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("inventory unit (kg)", str(caught.exception.detail))
        self.db.rollback()
        self.assertAlmostEqual(float(self.item().quantity), 10.0)
        self.assertEqual(self.db.scalar(select(func.count(TaskSubmission.id))), 0)

    def test_negative_stock_requires_authorized_override_and_reason_at_approval(self):
        item = self.item()
        item.quantity = 1
        self.db.commit()
        with self.assertRaises(HTTPException) as worker_ctx:
            self.submit(
                2,
                "task-worker-override",
                allow_negative_inventory=True,
                inventory_override_reason="Emergency verified usage.",
            )
        self.assertEqual(worker_ctx.exception.status_code, 403)
        self.db.rollback()
    
        result = self.submit(
            2,
            "task-manager-override",
            user=self.manager(),
            performed_by_employee_id=self.ids["employee"],
            assisted_reason="Manager observed completed work",
            actual_quantity_confirmed=True,
            allow_negative_inventory=True,
            inventory_override_reason="Physical stock count will be reconciled after emergency field use.",
        )
        self.assertEqual(result.status, "Submitted for Review")
        self.assertAlmostEqual(float(self.item().quantity), 1.0)
        submission = self.db.scalar(select(TaskSubmission))
        self.assertTrue(submission.inventory_override_used)
        self.assertIn("reconciled", submission.inventory_override_reason)
    
        review_task(self.ids["task"], TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.item().quantity), -1.0)
        self.assertEqual(self.movement_types(), ["Task Usage"])

    def test_manager_assisted_resource_entry_requires_actual_quantity_confirmation(self):
        with self.assertRaises(HTTPException) as caught:
            self.submit(
                2,
                "task-assisted-unconfirmed-actual",
                user=self.manager(),
                performed_by_employee_id=self.ids["employee"],
                assisted_reason="Employee forgot to submit before the deadline.",
            )
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("actual amount used", str(caught.exception.detail))
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count(TaskSubmission.id))), 0)

        result = self.submit(
            2,
            "task-assisted-confirmed-actual",
            user=self.manager(),
            performed_by_employee_id=self.ids["employee"],
            assisted_reason="Employee forgot to submit before the deadline.",
            actual_quantity_confirmed=True,
        )
        self.assertEqual(result.status, "Submitted for Review")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)

    def test_livestock_page_feeding_confirmation_retries_then_deducts_once_on_approval(self):
        livestock = self.db.get(Livestock, self.ids["livestock"])
        livestock.assigned_employee_id = self.ids["employee"]
        source_key = f"livestock:feeding:{livestock.id}:{date.today().isoformat()}:morning"
        task = FarmActivity(
            activity_code="ACT-TASKINV-FEED-PAGE",
            name="Morning Feeding - Test Grower Pigs",
            category="Livestock Feeding",
            related_to=livestock.record_name,
            location=livestock.pen_location,
            activity_date=date.today(),
            start_time=time(7, 0),
            assigned_by=self.manager().full_name,
            assigned_to=self.db.get(Employee, self.ids["employee"]).full_name,
            assigned_employee_id=self.ids["employee"],
            status="Pending",
            priority="Medium",
            requires_review=True,
            source_module="Livestock",
            source_type="livestock_feeding",
            source_record_id=livestock.id,
            source_key=source_key,
            planned_inventory_item_id=self.ids["feed_item"],
            planned_usage_type="Feed",
            planned_unit="kg",
            planned_quantity=1.5,
        )
        self.db.add(task)
        self.db.commit()
        payload = LivestockFeedingCreate(
            inventory_item_id=self.ids["feed_item"],
            feeding_date=date.today(),
            feeding_slot="Morning",
            actual_quantity_kg=1.5,
            performed_by_employee_id=self.ids["employee"],
        )
    
        with patch("app.routers.livestock.evaluate_automatic_tasks", return_value=[]):
            first = create_feeding_record(
                livestock.id, payload, self.db, self.manager(), "feeding-page-retry-1"
            )
            second = create_feeding_record(
                livestock.id, payload, self.db, self.manager(), "feeding-page-retry-1"
            )
    
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            self.db.scalar(select(func.count(TaskSubmission.id)).where(TaskSubmission.activity_id == task.id)),
            1,
        )
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["feed_item"])),
            0,
        )
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["feed_item"]).quantity), 10.0)
    
        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertEqual(
            self.db.scalar(select(func.count(InventoryStockRecord.id)).where(InventoryStockRecord.inventory_item_id == self.ids["feed_item"])),
            1,
        )
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["feed_item"]).quantity), 8.5)
    def test_crop_pesticide_reserves_then_posts_on_approval(self):
        pesticide = InventoryItem(
            item_code="INV-PEST-TASK-1",
            name="Crop Pesticide",
            category="Pesticide",
            quantity=5,
            unit="L",
            reorder_level=1,
            cost=250,
            price=300,
            supplier="Test Supplier",
            date_acquired=date.today() - timedelta(days=5),
            location="Chemical Storage",
        )
        self.db.add(pesticide)
        self.db.flush()
        task = self.task()
        task.name = "Apply pesticide"
        task.instructions = "Apply the linked pesticide according to the approved farm protocol."
        task.planned_inventory_item_id = pesticide.id
        task.planned_usage_type = "Pesticide"
        task.planned_quantity = 0.75
        task.planned_unit = "L"
        self.db.commit()
    
        submit_task(
            task.id,
            TaskSubmitRequest(actual_quantity=0.75, actual_unit="L"),
            self.db,
            self.worker(),
            "task-pesticide-1",
        )
        self.assertAlmostEqual(float(self.db.get(InventoryItem, pesticide.id).quantity), 5.0)
        self.assertIsNone(self.db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.inventory_item_id == pesticide.id)))
    
        review_task(task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(self.db.get(InventoryItem, pesticide.id).quantity), 4.25)
        movement = self.db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.inventory_item_id == pesticide.id))
        self.assertEqual(movement.adjustment_type, "Task Usage")
        usage = self.db.scalar(select(ResourceUsage).where(ResourceUsage.activity_id == task.id))
        self.assertEqual(usage.usage_type, "Pesticide")
        self.assertTrue(usage.task_posting_active)
    def test_livestock_feed_reserves_then_posts_on_approval(self):
        feed_task = FarmActivity(
            activity_code="ACT-TASKINV-FEED",
            name="Morning feeding",
            category="Feeding",
            related_to="Test Grower Pigs",
            location="Pig Pen 1",
            activity_date=date.today(),
            start_time=time(7, 0),
            assigned_by=self.manager().full_name,
            assigned_to=self.db.get(Employee, self.ids["employee"]).full_name,
            assigned_employee_id=self.ids["employee"],
            status="Pending",
            priority="Medium",
            requires_review=True,
            source_module="Livestock",
            source_type="livestock_feeding",
            source_record_id=self.ids["livestock"],
            planned_inventory_item_id=self.ids["feed_item"],
            planned_usage_type="Feed",
            planned_unit="kg",
            planned_quantity=1.5,
        )
        self.db.add(feed_task)
        self.db.commit()
        submit_task(
            feed_task.id,
            TaskSubmitRequest(actual_quantity=1.5, actual_unit="kg"),
            self.db,
            self.worker(),
            "task-feed-1",
        )
        feed = self.db.get(InventoryItem, self.ids["feed_item"])
        self.assertAlmostEqual(float(feed.quantity), 10.0)
        self.assertIsNone(self.db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.inventory_item_id == feed.id)))
    
        review_task(feed_task.id, TaskReviewRequest(decision="Approve"), self.db, self.manager())
        self.assertAlmostEqual(float(feed.quantity), 8.5)
        movement = self.db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.inventory_item_id == feed.id))
        self.assertEqual(movement.adjustment_type, "Task Usage")
        usage = self.db.scalar(select(ResourceUsage).where(ResourceUsage.activity_id == feed_task.id))
        self.assertEqual(usage.usage_type, "Feed")
        self.assertTrue(usage.task_posting_active)
    def test_pending_submission_reservation_prevents_overbooking_and_return_releases_it(self):
        self.submit(7, "reservation-first")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)

        employee = self.db.get(Employee, self.ids["employee"])
        second_task = FarmActivity(
            activity_code="ACT-TASKINV-RESERVE-2",
            name="Second fertilizer application",
            category="Crop Care",
            related_to="Eggplant — Field A",
            location="Field A",
            activity_date=date.today(),
            start_time=time(9, 0),
            assigned_by=self.manager().full_name,
            assigned_to=employee.full_name,
            assigned_employee_id=employee.id,
            status="Pending",
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
            source_module="Crop",
            source_type="care_template_step",
            source_record_id=self.ids["crop"],
            planned_inventory_item_id=self.ids["item"],
            planned_usage_type="Fertilizer",
            planned_quantity=4,
            planned_unit="kg",
        )
        self.db.add(second_task)
        self.db.commit()

        with self.assertRaises(HTTPException) as caught:
            submit_task(
                second_task.id,
                TaskSubmitRequest(actual_quantity=4, actual_unit="kg"),
                self.db,
                self.worker(),
                "reservation-second-blocked",
            )
        self.assertIn("already reserved", str(caught.exception.detail))
        self.db.rollback()
        self.assertAlmostEqual(float(self.item().quantity), 10.0)

        review_task(
            self.ids["task"],
            TaskReviewRequest(decision="Return", feedback="Correct first submission."),
            self.db,
            self.manager(),
        )
        submitted = submit_task(
            second_task.id,
            TaskSubmitRequest(actual_quantity=4, actual_unit="kg"),
            self.db,
            self.worker(),
            "reservation-second-after-release",
        )
        self.assertEqual(submitted.status, "Submitted for Review")
        self.assertAlmostEqual(float(self.item().quantity), 10.0)

    def test_manual_stock_adjustment_retry_is_idempotent(self):
        payload = InventoryStockAdjustmentCreate(
            adjustment_type="Restock",
            quantity=5,
            adjustment_date=date.today(),
            reason="Reorder received",
            reference="PO-TEST-001",
            supplier="Test Supplier",
        )
        first_background = BackgroundTasks()
        first = create_stock_adjustment(
            self.ids["item"],
            payload,
            first_background,
            self.db,
            self.manager(),
            "inventory-adjust-test-1",
        )
        second_background = BackgroundTasks()
        second = create_stock_adjustment(
            self.ids["item"],
            payload,
            second_background,
            self.db,
            self.manager(),
            "inventory-adjust-test-1",
        )

        self.assertEqual(first.id, second.id)
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["item"]).quantity), 15.0)
        self.assertEqual(
            self.db.scalar(
                select(func.count(InventoryStockRecord.id)).where(
                    InventoryStockRecord.inventory_item_id == self.ids["item"],
                    InventoryStockRecord.idempotency_key == "inventory-adjust-test-1",
                )
            ),
            1,
        )
        self.assertEqual(len(first_background.tasks), 1)
        self.assertEqual(len(second_background.tasks), 0)

    def test_manual_stock_adjustment_rejects_key_reuse_for_changed_payload(self):
        first_payload = InventoryStockAdjustmentCreate(
            adjustment_type="Restock",
            quantity=5,
            adjustment_date=date.today(),
            reason="Reorder received",
            reference="PO-TEST-002",
            supplier="Test Supplier",
        )
        create_stock_adjustment(
            self.ids["item"],
            first_payload,
            BackgroundTasks(),
            self.db,
            self.manager(),
            "inventory-adjust-test-2",
        )

        changed_payload = InventoryStockAdjustmentCreate(
            adjustment_type="Restock",
            quantity=8,
            adjustment_date=date.today(),
            reason="Reorder received",
            reference="PO-TEST-002",
            supplier="Test Supplier",
        )
        with self.assertRaises(HTTPException) as context:
            create_stock_adjustment(
                self.ids["item"],
                changed_payload,
                BackgroundTasks(),
                self.db,
                self.manager(),
                "inventory-adjust-test-2",
            )
        self.assertEqual(context.exception.status_code, 409)
        self.assertAlmostEqual(float(self.db.get(InventoryItem, self.ids["item"]).quantity), 15.0)



if __name__ == "__main__":
    unittest.main()
