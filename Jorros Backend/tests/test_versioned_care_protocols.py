import json
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

from fastapi import HTTPException
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
from app.models import CareTemplate, CareTemplateStep, Crop, Employee, FarmActivity, InventoryItem, Role, User
from app.routers.workforce import (
    copy_care_template,
    import_care_protocols,
    list_care_templates,
    match_care_protocols,
    publish_care_template,
    update_care_template,
)
from app.schemas.workforce import (
    CareProtocolCopyRequest,
    CareProtocolImportRequest,
    CareProtocolPublishRequest,
    CareTemplateCreate,
    CareTemplateStepInput,
    CareTemplateUpdate,
)
from app.services.care_task_workflow import generate_care_tasks_for_target, reconcile_same_template_future_schedule, validate_care_template_for_target


class VersionedCareProtocolTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        role = Role(name="Admin", permissions_json=json.dumps(["*"]))
        self.admin = User(
            user_code="USR-PROTOCOL-ADMIN", full_name="Protocol Admin", username="protocol.admin",
            password_hash="test", role=role,
        )
        self.db.add_all([role, self.admin]); self.db.flush()
        self.crop = Crop(
            crop_code="CRP-PROT-TOM", name="Tomato", variety="Roma", field="Field P",
            area_hectares=1, current_growth=10, growth_stage="Vegetative", quantity_planted=100,
            current_surviving=95, status="Planted", planting_date=date.today(),
            estimated_harvest=date.today()+timedelta(days=90), fertilizer_quantity_kg=0,
        )
        self.db.add(self.crop); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _published(self, *, title="Inspect crop", offset=3, recurring=1, interval=None, resource=False):
        protocol = CareTemplate(
            template_code=f"CARE-{title.replace(' ', '-')[:15]}", protocol_family_code="PROT-TOMATO",
            version=1, name="Tomato Protocol", module="Crop", target_type="Tomato", target_variety="Roma",
            status="Published", approval_status="Approved", source_title="DA-ATI source",
            source_url="https://ati2.da.gov.ph/example", last_reviewed_date=date.today(), is_active=True,
        )
        self.db.add(protocol); self.db.flush()
        step = CareTemplateStep(
            template_id=protocol.id, sequence_number=1, title=title, category="inspection",
            offset_days=offset, timing_anchor="planting_date", recurrence_occurrences=recurring,
            recurrence_interval_days=interval, instructions="Inspect and document.", priority="Medium",
            requires_review=True, requires_evidence=True,
            planned_quantity=1 if resource else None, planned_unit="kg" if resource else None,
            resource_category="Fertilizer" if resource else None,
        )
        self.db.add(step); self.db.commit()
        return protocol, step

    def test_published_update_creates_new_draft_version_and_keeps_original_immutable(self):
        original, _ = self._published()
        response = update_care_template(
            original.id,
            CareTemplateUpdate(name="Tomato Protocol Revised", steps=[CareTemplateStepInput(
                sequence_number=1, title="Revised inspection", category="inspection", timing_anchor="planting_date",
                offset_days=5, instructions="Revised draft instruction.", requires_review=True,
            )]),
            self.db, self.admin,
        )
        self.db.refresh(original)
        self.assertEqual(original.version, 1)
        self.assertEqual(original.name, "Tomato Protocol")
        self.assertEqual(original.status, "Published")
        self.assertEqual(response.version, 2)
        self.assertEqual(response.status, "Draft")
        self.assertEqual(response.protocol_family_code, original.protocol_family_code)
        self.assertEqual(response.steps[0].title, "Revised inspection")

    def test_exact_target_matching_honors_variety_and_rejects_mismatch(self):
        protocol, _ = self._published()
        matched = match_care_protocols("Crop", self.crop.id, self.db, self.admin)
        self.assertEqual([row.id for row in matched], [protocol.id])
        self.crop.variety = "Cherry"; self.db.commit()
        with self.assertRaises(HTTPException):
            validate_care_template_for_target(self.db, template_id=protocol.id, module="Crop", target=self.crop)
        self.assertEqual(match_care_protocols("Crop", self.crop.id, self.db, self.admin), [])

    def test_generation_pins_protocol_version_and_recurring_occurrences_are_idempotent(self):
        protocol, _ = self._published(recurring=3, interval=2)
        first = generate_care_tasks_for_target(self.db, module="Crop", target=self.crop, template=protocol, current_user=self.admin)
        self.db.commit()
        second = generate_care_tasks_for_target(self.db, module="Crop", target=self.crop, template=protocol, current_user=self.admin)
        self.db.commit()
        self.assertEqual(len(first), 3)
        self.assertEqual(len({row.id for row in second}), 3)
        rows = list(self.db.scalars(select(FarmActivity).where(FarmActivity.source_type == "care_template_step")).all())
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.source_protocol_family_code == protocol.protocol_family_code for row in rows))
        self.assertTrue(all(row.source_protocol_version == 1 for row in rows))
        self.assertEqual([r.activity_date for r in rows], [self.crop.planting_date+timedelta(days=d) for d in (3,5,7)])

    def test_reconciliation_preserves_recurring_assignment_and_timing_policy(self):
        default_employee = Employee(employee_code="EMP-PROT-DEFAULT", full_name="Protocol Default", employment_status="Active", is_archived=False)
        backup_employee = Employee(employee_code="EMP-PROT-BACKUP", full_name="Protocol Backup", employment_status="Active", is_archived=False)
        self.db.add_all([default_employee, backup_employee]); self.db.flush()
        self.crop.assigned_employee_id = default_employee.id
        protocol, step = self._published(offset=5, recurring=2, interval=2)
        generated = generate_care_tasks_for_target(
            self.db, module="Crop", target=self.crop, template=protocol, current_user=self.admin,
            employee_id=default_employee.id, backup_employee_id=backup_employee.id,
            time_sensitive=True, controlled_rescheduling=True, max_delay_minutes=45,
        )
        self.db.commit()
        self.assertEqual(len(generated), 2)
        self.assertTrue(all(row.default_employee_id == default_employee.id for row in generated))
        self.assertTrue(all(row.backup_employee_id == backup_employee.id for row in generated))
        self.assertTrue(all(row.time_sensitive for row in generated))
        self.assertTrue(all(row.controlled_rescheduling for row in generated))
        self.assertTrue(all(row.max_delay_minutes == 45 for row in generated))

        # Change the future schedule so reconciliation must update/rebuild occurrences.
        step.offset_days = 6
        self.db.commit()
        reconciled = reconcile_same_template_future_schedule(
            self.db, module="Crop", target=self.crop, template=protocol, current_user=self.admin,
        )
        self.db.commit()
        self.assertEqual(len(reconciled), 2)
        self.assertTrue(all(row.default_employee_id == default_employee.id for row in reconciled))
        self.assertTrue(all(row.backup_employee_id == backup_employee.id for row in reconciled))
        self.assertTrue(all(row.time_sensitive for row in reconciled))
        self.assertTrue(all(row.controlled_rescheduling for row in reconciled))
        self.assertTrue(all(row.max_delay_minutes == 45 for row in reconciled))

    def test_generic_resource_reference_resolves_current_inventory_lot(self):
        item = InventoryItem(
            item_code="INV-FERT-001", name="Complete Fertilizer", category="Fertilizer", quantity=20,
            unit="kg", reorder_level=2, cost=1, price=1, supplier="Test", date_acquired=date.today(),
            expiration_date=date.today()+timedelta(days=100), location="Storage", is_archived=False,
        )
        self.db.add(item); self.db.commit()
        protocol, step = self._published(resource=True)
        step.resource_product_name = None
        step.resource_category = "Fertilizer"
        self.db.commit()
        tasks = generate_care_tasks_for_target(self.db, module="Crop", target=self.crop, template=protocol, current_user=self.admin)
        self.db.commit()
        self.assertEqual(tasks[0].planned_inventory_item_id, item.id)
        self.assertEqual(tasks[0].planned_unit, "kg")
        self.assertIsNone(step.inventory_item_id)

    def test_publish_requires_expert_approval_and_source_metadata(self):
        draft = CareTemplate(
            template_code="CARE-DRAFT-P", protocol_family_code="PROT-DRAFT-P", version=1,
            name="Draft", module="Crop", target_type="Tomato", status="Draft",
            approval_status="Draft - Needs Veterinarian/Agriculturist Approval", is_active=True,
        )
        self.db.add(draft); self.db.flush()
        self.db.add(CareTemplateStep(template_id=draft.id, sequence_number=1, title="Check", category="inspection", offset_days=0))
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            publish_care_template(draft.id, CareProtocolPublishRequest(), self.db, self.admin)
        self.assertEqual(ctx.exception.status_code, 400)
        draft.approval_status="Approved"; draft.source_title="ATI"; draft.source_url="https://ati2.da.gov.ph/source"; draft.last_reviewed_date=date.today(); self.db.commit()
        published = publish_care_template(draft.id, CareProtocolPublishRequest(), self.db, self.admin)
        self.assertEqual(published.status, "Published")

    def test_copy_creates_new_family_draft(self):
        source, _ = self._published()
        copy = copy_care_template(source.id, CareProtocolCopyRequest(name="Tomato Copy"), self.db, self.admin)
        self.assertNotEqual(copy.protocol_family_code, source.protocol_family_code)
        self.assertEqual(copy.version, 1)
        self.assertEqual(copy.status, "Draft")
        self.assertEqual(copy.copied_from_template_id, source.id)

    def test_json_import_creates_draft_protocol(self):
        payload = CareProtocolImportRequest(protocols=[CareTemplateCreate(
            name="Imported Tomato", module="Crop", target_type="Tomato", target_variety="Roma",
            source_title="ATI", source_url="https://ati2.da.gov.ph/source", citations=["ATI source"],
            steps=[CareTemplateStepInput(sequence_number=1, title="Imported inspection", category="inspection")],
        )])
        rows = import_care_protocols(payload, self.db, self.admin)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "Draft")
        self.assertEqual(rows[0].version, 1)

    def test_default_list_excludes_drafts_but_protocol_library_can_include_all_versions(self):
        published, _ = self._published()
        draft = CareTemplate(template_code="CARE-DRAFT-LIST", protocol_family_code="PROT-DRAFT-LIST", version=1,
            name="Draft list", module="Crop", target_type="Tomato", status="Draft", is_active=True)
        self.db.add(draft); self.db.commit()
        operational = list_care_templates(None, False, self.db, self.admin, False)
        library = list_care_templates(None, True, self.db, self.admin, True)
        self.assertIn(published.id, [r.id for r in operational])
        self.assertNotIn(draft.id, [r.id for r in operational])
        self.assertIn(draft.id, [r.id for r in library])

    def test_migration_backfills_and_curated_presets_are_draft_only(self):
        text = Path("migrations/versions/y9i5d2f8a460_versioned_care_protocols.py").read_text(encoding="utf-8")
        self.assertIn('down_revision = "x8h4c1e7f359"', text)
        self.assertIn("protocol_family_code = template_code", text)
        self.assertIn("source_protocol_version", text)
        self.assertIn("PRESET-CORN", text)
        self.assertIn("PRESET-CHICKEN", text)
        self.assertIn("Draft - Needs Veterinarian/Agriculturist Approval", text)
        self.assertNotIn("vaccination on day", text.lower())
        self.assertNotIn("automatic vaccination interval", text.lower())

    def test_migration_preserves_inactive_legacy_templates_and_single_head_contract(self):
        text = Path("migrations/versions/y9i5d2f8a460_versioned_care_protocols.py").read_text(encoding="utf-8")
        self.assertIn("UPDATE care_templates SET status = CASE WHEN is_active = 1 THEN 'Published' ELSE 'Inactive' END", text)
        self.assertIn('revision = "y9i5d2f8a460"', text)
        self.assertIn('down_revision = "x8h4c1e7f359"', text)

    def test_expert_import_templates_include_versioned_protocol_safety_fields(self):
        json_text = Path("protocol_import_templates/care_protocol_template.json").read_text(encoding="utf-8")
        csv_text = Path("protocol_import_templates/care_protocol_template.csv").read_text(encoding="utf-8")
        for token in ["approval_status", "source_url", "source_citation", "dose_basis", "resource_product_name", "withdrawal_interval_days", "preharvest_interval_days"]:
            self.assertIn(token, json_text)
            self.assertIn(token, csv_text)
        self.assertIn("Replace with exact", json_text)



if __name__ == "__main__":
    unittest.main()
