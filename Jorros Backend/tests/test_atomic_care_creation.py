import os
import sys
import unittest
from datetime import date, timedelta
from types import ModuleType
from unittest.mock import patch

from fastapi import HTTPException
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
from app.models import (  # noqa: F401 - registers all tables
    CareTemplate,
    CareTemplateStep,
    Crop,
    FarmActivity,
    FarmCreationCommand,
    Livestock,
    LivestockPen,
    Role,
    User,
)
from app.routers.crops import create_crop, update_crop
from app.routers.livestock import create_livestock
from app.routers.workforce import update_care_template
from app.schemas.crops import CropCreate, CropUpdate
from app.schemas.livestock import LivestockCreate
from app.schemas.workforce import CareTemplateStepInput, CareTemplateUpdate


class AtomicCareCreationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=False)
        self.db = self.Session()
        self.today = date.today()

        role = Role(name="Admin", description="Atomic workflow test role")
        self.admin = User(
            user_code="USR-ATOMIC-ADMIN",
            full_name="Atomic Workflow Manager",
            username="atomic.manager",
            password_hash="not-a-real-password-hash",
            role=role,
        )
        self.crop_template = CareTemplate(
            template_code="CARE-CROP-ATOMIC",
            name="Eggplant Care",
            module="Crop",
            target_type="Eggplant",
            description="Atomic crop care template",
        )
        self.livestock_template = CareTemplate(
            template_code="CARE-GOAT-ATOMIC",
            name="Goat Care",
            module="Livestock",
            target_type="Goat",
            description="Atomic livestock care template",
        )
        self.pen = LivestockPen(
            name="Goat Pen Atomic",
            animal_type="Goat",
            capacity=20,
            status="Active",
            purpose="General",
        )
        self.db.add_all([
            role,
            self.admin,
            self.crop_template,
            self.livestock_template,
            self.pen,
        ])
        self.db.flush()
        self.crop_step = CareTemplateStep(
            template_id=self.crop_template.id,
            sequence_number=1,
            title="Future crop inspection",
            category="General Care",
            offset_days=10,
            instructions="Inspect the crop using the approved farm protocol.",
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
        )
        self.goat_step = CareTemplateStep(
            template_id=self.livestock_template.id,
            sequence_number=1,
            title="Future goat inspection",
            category="General Care",
            offset_days=7,
            instructions="Inspect the livestock using the approved farm protocol.",
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
        )
        self.db.add_all([self.crop_step, self.goat_step])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _crop_payload(self, *, template_id=None, name="Eggplant"):
        return CropCreate(
            name=name,
            variety="Test Variety",
            field="Field Atomic",
            area_hectares=0.5,
            quantity_planted=20,
            current_surviving=20,
            planting_date=self.today + timedelta(days=1),
            estimated_harvest=self.today + timedelta(days=90),
            fertilizer_quantity_kg=0,
            watering_schedule=None,
            notes="Atomic workflow test",
            care_template_id=template_id,
        )

    def _livestock_payload(self, *, template_id=None):
        return LivestockCreate(
            record_name="Atomic Goat Batch",
            animal_type="Goat",
            breed="Test Breed",
            quantity=2,
            sex="Mixed",
            record_type="Batch",
            lifecycle_status="Active",
            pen_id=self.pen.id,
            male_quantity=1,
            female_quantity=1,
            unknown_sex_quantity=0,
            date_of_birth=self.today - timedelta(days=200),
            weight_kg=30,
            min_weight_kg=28,
            max_weight_kg=32,
            pen_location=self.pen.name,
            health_status="Healthy",
            healthy_quantity=2,
            growth_status="Mature",
            production_purpose="General",
            vaccination_status="Not Vaccinated",
            daily_feed_kg=0,
            date_acquired=self.today,
            care_template_id=template_id,
        )

    def test_crop_create_commits_record_and_care_tasks_together(self):
        crop = create_crop(
            self._crop_payload(template_id=self.crop_template.id),
            self.db,
            self.admin,
            "crop-success-1",
        )
        self.assertIsNotNone(crop.id)
        tasks = list(self.db.scalars(select(FarmActivity).where(
            FarmActivity.source_module == "Crop",
            FarmActivity.source_record_id == crop.id,
            FarmActivity.source_type == "care_template_step",
        )).all())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].status, "Pending")
        command = self.db.scalar(select(FarmCreationCommand).where(
            FarmCreationCommand.idempotency_key == "crop-success-1"
        ))
        self.assertEqual(command.target_id, crop.id)

    def test_livestock_create_commits_record_growth_and_care_tasks_together(self):
        livestock = create_livestock(
            self._livestock_payload(template_id=self.livestock_template.id),
            self.db,
            self.admin,
            "livestock-success-1",
        )
        self.assertIsNotNone(livestock.id)
        task_count = self.db.scalar(select(func.count(FarmActivity.id)).where(
            FarmActivity.source_module == "Livestock",
            FarmActivity.source_record_id == livestock.id,
            FarmActivity.source_type == "care_template_step",
        ))
        self.assertEqual(task_count, 1)

    def test_generation_failure_rolls_back_new_crop_and_idempotency_record(self):
        payload = self._crop_payload(template_id=self.crop_template.id)
        with patch(
            "app.routers.crops.generate_care_tasks_for_target",
            side_effect=RuntimeError("simulated care generation failure"),
        ):
            with self.assertRaises(RuntimeError):
                create_crop(payload, self.db, self.admin, "crop-failure-1")

        self.assertEqual(self.db.scalar(select(func.count(Crop.id))), 0)
        self.assertEqual(
            self.db.scalar(select(func.count(FarmCreationCommand.id)).where(
                FarmCreationCommand.idempotency_key == "crop-failure-1"
            )),
            0,
        )
        self.assertEqual(self.db.scalar(select(func.count(FarmActivity.id))), 0)

    def test_same_idempotency_key_returns_original_result_without_duplicate(self):
        payload = self._crop_payload(template_id=self.crop_template.id)
        first = create_crop(payload, self.db, self.admin, "crop-network-retry-1")
        second = create_crop(payload, self.db, self.admin, "crop-network-retry-1")

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.scalar(select(func.count(Crop.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(FarmActivity.id)).where(
            FarmActivity.source_module == "Crop",
            FarmActivity.source_record_id == first.id,
            FarmActivity.source_type == "care_template_step",
        )), 1)
        self.assertEqual(self.db.scalar(select(func.count(FarmCreationCommand.id))), 1)

    def test_template_target_mismatch_rejects_and_rolls_back(self):
        with self.assertRaises(HTTPException) as ctx:
            create_crop(
                self._crop_payload(template_id=self.crop_template.id, name="Tomato"),
                self.db,
                self.admin,
                "crop-mismatch-1",
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("target type", str(ctx.exception.detail).lower())
        self.assertEqual(self.db.scalar(select(func.count(Crop.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(FarmActivity.id))), 0)

    def test_editing_schedule_updates_only_future_pending_occurrence(self):
        crop = create_crop(
            self._crop_payload(template_id=self.crop_template.id),
            self.db,
            self.admin,
            "crop-edit-schedule-1",
        )
        pending = self.db.scalar(select(FarmActivity).where(
            FarmActivity.source_record_id == crop.id,
            FarmActivity.source_type == "care_template_step",
            FarmActivity.status == "Pending",
        ))
        self.assertIsNotNone(pending)
        original_task_id = pending.id
        original_date = pending.activity_date

        protected = FarmActivity(
            activity_code="ACT-PROTECTED-ATOMIC",
            name="Submitted care history",
            category="General Care",
            related_to=crop.name,
            location=crop.field,
            description="Historical submitted care task",
            activity_date=self.today + timedelta(days=20),
            start_time=pending.start_time,
            assigned_by="System",
            assigned_to="Unassigned",
            status="Submitted for Review",
            priority="Medium",
            is_automatic=True,
            source_module="Crop",
            source_type="care_template_step",
            source_record_id=crop.id,
            source_detail_id=self.crop_step.id,
            source_code=self.crop_template.template_code,
            source_path="/crops",
            source_key=f"care:crop:{crop.id}:{self.crop_template.id}:{self.crop_step.id}:protected",
        )
        self.db.add(protected)
        self.db.commit()

        updated = update_crop(
            crop.id,
            CropUpdate(planting_date=crop.planting_date + timedelta(days=3)),
            self.db,
            self.admin,
        )
        self.assertEqual(updated.id, crop.id)

        self.db.refresh(pending)
        self.db.refresh(protected)
        self.assertEqual(pending.id, original_task_id)
        self.assertEqual(pending.status, "Pending")
        self.assertEqual(pending.activity_date, original_date + timedelta(days=3))
        self.assertEqual(protected.status, "Submitted for Review")
        self.assertEqual(protected.activity_date, self.today + timedelta(days=20))

    def test_editing_published_protocol_creates_new_draft_and_preserves_existing_task_history(self):
        crop = create_crop(
            self._crop_payload(template_id=self.crop_template.id),
            self.db,
            self.admin,
            "crop-protocol-edit-1",
        )
        pending = self.db.scalar(select(FarmActivity).where(
            FarmActivity.source_record_id == crop.id,
            FarmActivity.source_type == "care_template_step",
            FarmActivity.status == "Pending",
        ))
        original_id = pending.id
        protected = FarmActivity(
            activity_code="ACT-COMPLETED-PROTOCOL-HISTORY",
            name="Completed protocol history",
            category="General Care",
            related_to=crop.name,
            location=crop.field,
            description="Protected completed history",
            activity_date=self.today + timedelta(days=25),
            start_time=pending.start_time,
            assigned_by="System",
            assigned_to="Unassigned",
            status="Completed",
            priority="Medium",
            is_automatic=True,
            source_module="Crop",
            source_type="care_template_step",
            source_record_id=crop.id,
            source_detail_id=self.crop_step.id,
            source_code=self.crop_template.template_code,
            source_path="/crops",
            source_key=f"care:crop:{crop.id}:{self.crop_template.id}:{self.crop_step.id}:completed-history",
        )
        self.db.add(protected)
        self.db.commit()

        draft = update_care_template(
            self.crop_template.id,
            CareTemplateUpdate(
                steps=[
                    CareTemplateStepInput(
                        sequence_number=1,
                        title="Future crop inspection - revised",
                        category="General Care",
                        offset_days=14,
                        instructions="Use the revised approved farm protocol.",
                        priority="High",
                        requires_review=True,
                        requires_evidence=False,
                    )
                ]
            ),
            self.db,
            self.admin,
        )

        self.db.refresh(pending)
        self.db.refresh(protected)
        self.assertEqual(draft.protocol_family_code, self.crop_template.protocol_family_code)
        self.assertEqual(draft.version, self.crop_template.version + 1)
        self.assertEqual(draft.status, "Draft")
        self.assertEqual(draft.steps[0].title, "Future crop inspection - revised")
        self.assertEqual(pending.id, original_id)
        self.assertEqual(pending.status, "Pending")
        self.assertEqual(pending.name, "Future crop inspection")
        self.assertEqual(protected.status, "Completed")
        self.assertEqual(protected.name, "Completed protocol history")

    def test_deactivating_protocol_requires_explicit_future_task_decision(self):
        crop = create_crop(
            self._crop_payload(template_id=self.crop_template.id),
            self.db,
            self.admin,
            "crop-protocol-deactivate-1",
        )
        pending = self.db.scalar(select(FarmActivity).where(
            FarmActivity.source_record_id == crop.id,
            FarmActivity.source_type == "care_template_step",
            FarmActivity.status == "Pending",
        ))

        with self.assertRaises(HTTPException) as ctx:
            update_care_template(
                self.crop_template.id,
                CareTemplateUpdate(is_active=False),
                self.db,
                self.admin,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.db.refresh(self.crop_template)
        self.assertTrue(self.crop_template.is_active)

        update_care_template(
            self.crop_template.id,
            CareTemplateUpdate(is_active=False, future_task_action="resolve"),
            self.db,
            self.admin,
        )
        self.db.refresh(crop)
        self.db.refresh(pending)
        self.db.refresh(self.crop_template)
        self.assertFalse(self.crop_template.is_active)
        self.assertIsNone(crop.care_template_id)
        self.assertEqual(pending.status, "Resolved")



if __name__ == "__main__":
    unittest.main()
