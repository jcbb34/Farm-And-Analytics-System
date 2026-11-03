import unittest
import os
import sys
from types import ModuleType
from datetime import date, time, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Keep the regression test independent from a developer's private .env file.
# These values are never used to connect because the test binds its own
# in-memory SQLite session.
os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")

# The production database module builds the SQL Server engine at import time.
# In lightweight CI/sandbox environments where the native pyodbc package is
# unavailable, provide only the Base/get_db surface needed by these SQLite
# regression tests. Production environments with pyodbc use the real module.
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

# workforce imports the authentication router, which imports pyotp even though
# this lifecycle test never exercises 2FA behavior.
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
from app.models import (  # noqa: F401 - importing registers all mapped tables
    CareTemplate,
    CareTemplateStep,
    Crop,
    FarmActivity,
    Role,
    User,
)
from app.routers.workforce import generate_care_tasks
from app.schemas.workforce import GenerateCareTasksRequest
from app.services.task_engine import evaluate_automatic_tasks


class CareTemplateTaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()

        role = Role(name="Admin", description="Test administrator")
        self.admin = User(
            user_code="USR-TEST-ADMIN",
            full_name="Test Administrator",
            username="test.admin",
            password_hash="not-a-real-password-hash",
            role=role,
        )
        self.crop = Crop(
            crop_code="CRP-CARE-001",
            name="Eggplant",
            variety="Test Variety",
            field="Field A",
            area_hectares=0.50,
            current_growth=100,
            growth_stage="Harvesting / Production",
            quantity_planted=20,
            current_surviving=20,
            status="Harvesting",
            planting_date=date.today() - timedelta(days=90),
            estimated_harvest=date.today() - timedelta(days=1),
            fertilizer_quantity_kg=0,
            watering_schedule=None,
        )
        self.template = CareTemplate(
            template_code="CARE-TEST-001",
            name="Eggplant General Care",
            module="Crop",
            target_type="Eggplant",
            description="Lifecycle regression template.",
            created_by_user_id=None,
        )
        self.db.add_all([role, self.admin, self.crop, self.template])
        self.db.flush()

        self.step = CareTemplateStep(
            template_id=self.template.id,
            sequence_number=1,
            title="Inspect and care for eggplant",
            category="General Care",
            offset_days=0,
            instructions="Follow the approved farm care protocol.",
            priority="Medium",
            requires_review=True,
            requires_evidence=False,
        )
        self.db.add(self.step)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _generate(self):
        return generate_care_tasks(
            GenerateCareTasksRequest(
                module="Crop",
                target_id=self.crop.id,
                template_id=self.template.id,
                base_date=date.today(),
            ),
            self.db,
            self.admin,
        )

    def _activity(self, *, code, source_key, source_type, status="Pending", is_automatic=True, is_archived=False):
        return FarmActivity(
            activity_code=code,
            name="Lifecycle fixture",
            category="Test",
            related_to="Test record",
            location="Jorros Farm",
            description="Regression fixture",
            activity_date=date.today(),
            start_time=time(8, 0),
            assigned_by="System",
            assigned_to="Farm Staff",
            status=status,
            priority="Medium",
            is_automatic=is_automatic,
            source_module="Inventory" if source_type == "inventory_restock" else "Test",
            source_type=source_type,
            source_record_id=999,
            source_path="/inventory" if source_type == "inventory_restock" else "/test",
            source_key=source_key,
            is_archived=is_archived,
        )

    def test_care_generation_survives_scheduler_and_is_idempotent(self):
        first = self._generate()
        self.assertEqual(len(first), 1)

        source_key = (
            f"care:crop:{self.crop.id}:{self.template.id}:"
            f"{self.step.id}:{date.today().isoformat()}"
        )
        care_task = self.db.scalar(
            select(FarmActivity).where(FarmActivity.source_key == source_key)
        )
        self.assertIsNotNone(care_task)
        self.assertEqual(care_task.source_type, "care_template_step")
        self.assertEqual(care_task.status, "Pending")

        # A scheduler pass must not reconcile a workforce-owned care task merely
        # because its care: key is absent from the built-in evaluator key set.
        evaluate_automatic_tasks(self.db)
        self.db.refresh(care_task)
        self.assertEqual(care_task.status, "Pending")

        second = self._generate()
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].id, care_task.id)
        occurrence_count = self.db.scalar(
            select(func.count(FarmActivity.id)).where(FarmActivity.source_key == source_key)
        )
        self.assertEqual(occurrence_count, 1)

        # In-progress care work is equally workforce-owned and remains actionable.
        care_task.status = "In Progress"
        self.db.commit()
        evaluate_automatic_tasks(self.db)
        self.db.refresh(care_task)
        self.assertEqual(care_task.status, "In Progress")

    def test_cleanup_resolves_only_open_non_archived_evaluator_owned_tasks(self):
        obsolete_owned = self._activity(
            code="ACT-OWNED-OBSOLETE",
            source_key="inventory:restock:999:initial",
            source_type="inventory_restock",
        )
        manual_task = self._activity(
            code="ACT-MANUAL-SAFE",
            source_key=None,
            source_type=None,
            is_automatic=False,
        )
        submitted_task = self._activity(
            code="ACT-SUBMITTED-SAFE",
            source_key="inventory:restock:998:initial",
            source_type="inventory_restock",
            status="Submitted for Review",
        )
        approved_task = self._activity(
            code="ACT-APPROVED-SAFE",
            source_key="inventory:restock:997:initial",
            source_type="inventory_restock",
            status="Completed",
        )
        archived_task = self._activity(
            code="ACT-ARCHIVED-SAFE",
            source_key="inventory:restock:996:initial",
            source_type="inventory_restock",
            status="Pending",
            is_archived=True,
        )
        unowned_auto_task = self._activity(
            code="ACT-CARE-SAFE",
            source_key="care:crop:999:999:999:2026-09-09",
            source_type="care_template_step",
        )
        self.db.add_all(
            [
                obsolete_owned,
                manual_task,
                submitted_task,
                approved_task,
                archived_task,
                unowned_auto_task,
            ]
        )
        self.db.commit()

        evaluate_automatic_tasks(self.db)

        for task in (
            obsolete_owned,
            manual_task,
            submitted_task,
            approved_task,
            archived_task,
            unowned_auto_task,
        ):
            self.db.refresh(task)

        self.assertEqual(obsolete_owned.status, "Resolved")
        self.assertEqual(manual_task.status, "Pending")
        self.assertEqual(submitted_task.status, "Submitted for Review")
        self.assertEqual(approved_task.status, "Completed")
        self.assertEqual(archived_task.status, "Pending")
        self.assertEqual(unowned_auto_task.status, "Pending")


if __name__ == "__main__":
    unittest.main()
