import json
import os
import sys
import unittest
from datetime import date, timedelta
from types import ModuleType

from sqlalchemy import create_engine, select
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
    test_database_module.get_db = lambda: None
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
        def recommended(cls): return cls()
        def hash(self, password): return f"test::{password}"
        def verify(self, plain_password, hashed_password): return hashed_password == f"test::{plain_password}"
    test_pwdlib_module.PasswordHash = _TestPasswordHash
    sys.modules["pwdlib"] = test_pwdlib_module

from app.core.database import Base
from app.models import (
    CareTemplate,
    CareTemplateStep,
    FarmActivity,
    Livestock,
    LivestockGrowthProfile,
    LivestockGrowthProfileStage,
    LivestockPen,
    Role,
    User,
)
from app.routers.livestock import (
    create_growth_profile_version,
    override_growth_stage,
    record_growth_measurement,
)
from app.schemas.livestock import (
    GrowthProfileCreate,
    GrowthProfileStageInput,
    GrowthStageOverrideRequest,
)
from app.services.care_task_workflow import generate_care_tasks_for_target
from app.services.growth_profile_service import assess_livestock_growth, biological_age_days


class GrowthProfilePrompt9Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        role = Role(name="Manager", permissions_json=json.dumps(["livestock:view", "livestock:update", "workforce:manage"]))
        self.manager = User(
            user_code="USR-GROWTH-MGR", full_name="Growth Manager", username="growth.manager",
            password_hash="test", role=role,
        )
        self.db.add_all([role, self.manager])
        self.db.flush()
        self.pen = LivestockPen(name="Test Pen", animal_type=None, purpose="General", status="Active", is_archived=False)
        self.db.add(self.pen)
        self.db.flush()
        self._seed_profiles()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _profile(self, family, species, stages, *, breed=None, purpose=None, status="Draft"):
        row = LivestockGrowthProfile(
            profile_family_code=family, version=1, name=family, species=species,
            breed_strain=breed, production_purpose=purpose, status=status,
            approval_status="Approved" if status == "Published" else "Draft - Needs Veterinarian/Agriculturist Approval",
            source_title="Test source", source_url="https://example.test/source", is_active=True,
        )
        self.db.add(row)
        self.db.flush()
        for index, (name, start, end, low, high) in enumerate(stages, 1):
            self.db.add(LivestockGrowthProfileStage(
                profile_id=row.id, sequence_number=index, stage_name=name,
                age_start_days=start, age_end_days=end,
                expected_min_weight_kg=low, expected_max_weight_kg=high,
            ))
        self.db.flush()
        return row

    def _seed_profiles(self):
        self._profile(
            "GROW-ROSS308AP", "Chicken",
            [("Brooding", 0, 7, 0.04, 0.26), ("Growing", 8, 21, 0.20, 1.15),
             ("Finisher", 22, 35, 1.0, 2.7), ("Ready for Market", 36, 45, 2.2, 3.6)],
            breed="Ross 308 AP", purpose="Meat", status="Published",
        )
        self._profile(
            "GROW-NATIVE", "Chicken",
            [("Brooding", 0, 42, 0.03, 0.55), ("Growing", 43, 125, 0.35, 1.4),
             ("Pre-Laying", 126, 153, 0.7, 1.8), ("Mature", 154, None, 0.9, 2.8)],
            breed="Camarines",
        )
        self._profile(
            "GROW-PIG", "Pig",
            [("Newborn", 0, 56, 0.8, 25), ("Weaned", 57, 90, 8, 40),
             ("Growing", 91, 179, 20, 100), ("Mature", 180, None, 55, 300)],
        )
        self.db.commit()

    def _livestock(self, *, animal_type, breed, purpose, age_days=None, dob=None, weight=1.0, stage="Growing", acquired_days_ago=0):
        today = date.today()
        acquired = today - timedelta(days=acquired_days_ago)
        row = Livestock(
            animal_code=f"C-{1000 + len(self.db.scalars(select(Livestock.id)).all()) + 1}",
            record_name=f"{breed} Test", animal_type=animal_type, breed=breed,
            quantity=1, sex="Female", record_type="Individual", lifecycle_status="Active",
            pen_id=self.pen.id, male_quantity=0, female_quantity=1, unknown_sex_quantity=0,
            date_of_birth=dob, weight_kg=weight, min_weight_kg=weight, max_weight_kg=weight,
            pen_location=self.pen.name, health_status="Healthy", healthy_quantity=1,
            at_risk_quantity=0, sick_quantity=0, under_treatment_quantity=0,
            growth_status=stage, production_purpose=purpose,
            vaccination_status="Not Vaccinated", daily_feed_kg=0,
            age_is_estimated=dob is None,
            estimated_age_days=age_days if dob is None else None,
            estimated_age_as_of_date=today if dob is None else None,
            estimated_age_confidence="Medium" if dob is None else None,
            estimated_age_source="Seller transfer record" if dob is None else None,
            acquisition_stage=stage, medical_history_status="Unknown - Needs Review",
            date_acquired=acquired, is_archived=False,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def test_fast_growing_broiler_has_approximately_45_day_market_stage(self):
        bird = self._livestock(
            animal_type="Chicken", breed="Ross 308 AP", purpose="Meat",
            dob=date.today() - timedelta(days=42), weight=3.0,
        )
        result = assess_livestock_growth(self.db, bird)
        self.assertEqual(result["profile_family_code"], "GROW-ROSS308AP")
        self.assertEqual(result["suggested_stage"], "Ready for Market")
        self.assertEqual(result["age_days"], 42)
        self.assertEqual(result["profile_status"], "Published")


    def test_unrelated_commercial_chicken_does_not_receive_native_profile(self):
        bird = self._livestock(
            animal_type="Chicken", breed="Sasso", purpose="Meat",
            dob=date.today() - timedelta(days=45), weight=0.8,
        )
        result = assess_livestock_growth(self.db, bird)
        self.assertIsNone(result["profile_family_code"])
        self.assertIsNone(result["suggested_stage"])

    def test_growth_profile_new_version_preserves_family_and_increments_version(self):
        source = self.db.scalar(
            select(LivestockGrowthProfile).where(
                LivestockGrowthProfile.profile_family_code == "GROW-ROSS308AP"
            )
        )
        payload = GrowthProfileCreate(
            name="Ross 308 AP Local Review",
            species="Chicken",
            breed_strain="Ross 308 AP",
            production_purpose="Meat",
            source_title="Updated reviewed source",
            source_url="https://example.test/ross-reviewed",
            last_reviewed_date=date.today(),
            approval_status="Draft - Needs Veterinarian/Agriculturist Approval",
            stages=[
                GrowthProfileStageInput(
                    sequence_number=1, stage_name="Brooding", age_start_days=0, age_end_days=7,
                    expected_min_weight_kg=0.04, expected_max_weight_kg=0.26,
                ),
                GrowthProfileStageInput(
                    sequence_number=2, stage_name="Growing", age_start_days=8, age_end_days=21,
                    expected_min_weight_kg=0.20, expected_max_weight_kg=1.15,
                ),
            ],
        )
        created = create_growth_profile_version(source.id, payload, self.db, self.manager)
        self.assertEqual(created.profile_family_code, source.profile_family_code)
        self.assertEqual(created.version, 2)
        self.assertEqual(created.status, "Draft")
        self.assertEqual(len(created.stages), 2)

    def test_native_chicken_is_not_treated_like_45_day_broiler(self):
        native = self._livestock(
            animal_type="Chicken", breed="Camarines", purpose="Meat",
            dob=date.today() - timedelta(days=45), weight=0.45,
        )
        result = assess_livestock_growth(self.db, native)
        self.assertEqual(result["profile_family_code"], "GROW-NATIVE")
        self.assertEqual(result["suggested_stage"], "Growing")
        self.assertEqual(result["profile_status"], "Draft")

    def test_piglet_under_six_months_uses_biological_age(self):
        pig = self._livestock(
            animal_type="Pig", breed="Large White", purpose="Meat",
            dob=date.today() - timedelta(days=120), weight=45,
        )
        result = assess_livestock_growth(self.db, pig)
        self.assertEqual(result["age_days"], 120)
        self.assertEqual(result["suggested_stage"], "Growing")

    def test_mature_purchased_pig_age_is_not_reset_to_acquisition_date(self):
        pig = self._livestock(
            animal_type="Pig", breed="Large White", purpose="Breeding",
            dob=date.today() - timedelta(days=400), weight=150,
            stage="Mature", acquired_days_ago=5,
        )
        result = assess_livestock_growth(self.db, pig)
        self.assertEqual(result["age_days"], 400)
        self.assertEqual(result["suggested_stage"], "Mature")
        self.assertNotEqual(result["age_days"], 5)

    def test_unknown_age_transferred_animal_advances_from_dated_estimate(self):
        today = date.today()
        pig = self._livestock(
            animal_type="Pig", breed="Native", purpose="Meat",
            age_days=210, weight=80, stage="Mature", acquired_days_ago=10,
        )
        pig.estimated_age_as_of_date = today - timedelta(days=10)
        pig.estimated_age_days = 200
        self.assertEqual(biological_age_days(pig, today), 210)
        result = assess_livestock_growth(self.db, pig)
        self.assertEqual(result["suggested_stage"], "Mature")
        self.assertEqual(result["age_source"], "Dated age estimate")

    def test_growth_measurement_snapshots_expectation_and_cannot_be_silently_rewritten(self):
        bird = self._livestock(
            animal_type="Chicken", breed="Ross 308 AP", purpose="Meat",
            dob=date.today() - timedelta(days=42), weight=3.0,
        )
        first = record_growth_measurement(self.db, bird, date.today(), 3.0, self.manager.id)
        self.db.flush()
        self.assertEqual(first.expected_stage, "Ready for Market")
        self.assertEqual(first.growth_profile_family_code, "GROW-ROSS308AP")
        with self.assertRaises(Exception) as ctx:
            record_growth_measurement(self.db, bird, date.today(), 3.2, self.manager.id)
        self.assertIn("immutable", str(ctx.exception).lower())

    def test_manager_override_records_audit_reason(self):
        pig = self._livestock(
            animal_type="Pig", breed="Large White", purpose="Meat",
            dob=date.today() - timedelta(days=120), weight=45, stage="Growing",
        )
        self.db.commit()
        result = override_growth_stage(
            pig.id, GrowthStageOverrideRequest(stage="Mature", reason="Veterinarian confirmed adult dentition and prior records."),
            self.db, self.manager,
        )
        self.assertEqual(result.current_stage, "Mature")
        from app.models import LivestockGrowthStageOverrideAudit
        audit = self.db.scalar(select(LivestockGrowthStageOverrideAudit).where(LivestockGrowthStageOverrideAudit.livestock_id == pig.id))
        self.assertIsNotNone(audit)
        self.assertIn("Veterinarian", audit.reason)

    def test_acquired_adult_care_skips_expired_early_life_step_and_schedules_current_window(self):
        pig = self._livestock(
            animal_type="Pig", breed="Large White", purpose="Meat",
            age_days=200, weight=90, stage="Mature", acquired_days_ago=1,
        )
        protocol = CareTemplate(
            template_code="CARE-PIG-AGE", protocol_family_code="PROT-PIG-AGE", version=1,
            name="Pig Age Care", module="Livestock", target_type="Pig", status="Published",
            approval_status="Approved", source_title="Test", source_url="https://example.test/care",
            is_active=True,
        )
        self.db.add(protocol); self.db.flush()
        self.db.add_all([
            CareTemplateStep(
                template_id=protocol.id, sequence_number=1, title="Neonatal check", category="inspection",
                timing_anchor="age_window", age_start_days=1, age_end_days=7, offset_days=0,
            ),
            CareTemplateStep(
                template_id=protocol.id, sequence_number=2, title="Adult condition check", category="inspection",
                timing_anchor="age_window", age_start_days=180, age_end_days=240, offset_days=0,
            ),
        ])
        self.db.commit()
        tasks = generate_care_tasks_for_target(
            self.db, module="Livestock", target=pig, template=protocol, current_user=self.manager,
            base_date=pig.date_acquired,
        )
        titles = [row.name for row in tasks]
        self.assertNotIn("Neonatal check", titles)
        self.assertIn("Adult condition check", titles)
        self.assertTrue(all(row.activity_date >= date.today() for row in tasks))


if __name__ == "__main__":
    unittest.main()
