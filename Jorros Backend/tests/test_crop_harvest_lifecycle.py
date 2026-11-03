import os
import sys
import unittest
from datetime import date, timedelta, time
from types import ModuleType

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-long-enough-for-crop-harvest")

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    from sqlalchemy.orm import DeclarativeBase
    class _TestBase(DeclarativeBase):
        pass
    test_database_module = ModuleType("app.core.database")
    test_database_module.Base = _TestBase
    def _test_get_db():
        yield None
    test_database_module.get_db = _test_get_db
    sys.modules.setdefault("app.core.database", test_database_module)

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    Crop,
    CropYieldRecord,
    Employee,
    FarmActivity,
    FarmAlert,
    LivestockProductionRecord,
    Role,
    User,
)
from app.services.crop_harvest_service import record_harvest, reopen_crop_cycle
from app.services.report_builder import _build_crop_snapshot
from app.services.operational_report_builder import build_operational_report_snapshot
from app.core.farm_time import farm_now_naive, farm_today
from app.routers.crops import get_crop, list_crop_details, list_crops, reopen_completed_crop
from app.schemas.crops import CropReopenRequest


class CropHarvestLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        role = Role(name="Crop Lifecycle Manager", description="tests")
        role.set_permissions(["crops:update", "crops:full-edit", "workforce:review"])
        self.db.add(role)
        self.db.flush()
        self.manager = User(
            user_code="USR-HARVEST-MGR",
            full_name="Harvest Manager",
            username="harvest.manager",
            password_hash="test",
            role=role,
            status="Active",
        )
        self.db.add(self.manager)
        self.db.flush()
        self.employee = Employee(
            employee_code="EMP-HARVEST-1",
            full_name="Harvest Worker",
            position="Farm Worker",
            employment_status="Active",
        )
        self.db.add(self.employee)
        self.db.flush()
        self.crop = Crop(
            crop_code="CRP-HARVEST-1",
            name="Eggplant",
            variety="Long Purple",
            field="Field H",
            area_hectares=1.0,
            current_growth=100,
            growth_stage="Harvest Ready",
            quantity_planted=100,
            current_surviving=96,
            status="Ready for Harvest",
            planting_date=date.today() - timedelta(days=90),
            estimated_harvest=date.today() - timedelta(days=2),
            fertilizer_quantity_kg=0,
            is_archived=False,
        )
        self.db.add(self.crop)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def harvest(self, qty, kind="Partial Harvest", **kwargs):
        return record_harvest(
            self.db,
            crop=self.crop,
            harvest_date=date.today(),
            quantity_kg=qty,
            harvest_type=kind,
            actor=self.manager,
            performed_by_employee_id=self.employee.id,
            manual_reason=kwargs.pop("manual_reason", "Manager recorded field harvest"),
            final_harvest_confirmed=(kind == "Final Harvest"),
            **kwargs,
        )

    def test_multiple_partial_harvests_keep_cycle_active_and_sync_each_once(self):
        first = self.harvest(12)
        second = self.harvest(8)
        self.db.flush()
        self.assertEqual(self.crop.status, "Harvesting")
        self.assertNotEqual(first.id, second.id)
        yields = self.db.scalars(select(CropYieldRecord).where(CropYieldRecord.crop_id == self.crop.id)).all()
        production = self.db.scalars(select(LivestockProductionRecord).where(LivestockProductionRecord.source_type == "Crop")).all()
        self.assertEqual(len(yields), 2)
        self.assertEqual(len(production), 2)
        self.assertEqual(sum(float(row.gross_quantity or 0) for row in production), 20.0)

    def test_final_harvest_adds_only_new_quantity_closes_cycle_and_preserves_started_work(self):
        self.harvest(10)
        future_pending = FarmActivity(
            activity_code="ACT-FUTURE-PENDING",
            name="Water crop",
            category="Crop Watering",
            related_to=self.crop.name,
            location=self.crop.field,
            activity_date=date.today() + timedelta(days=1),
            start_time=time(7, 0),
            assigned_by=self.manager.full_name,
            assigned_to=self.employee.full_name,
            status="Pending",
            source_module="Crop",
            source_type="crop_watering",
            source_record_id=self.crop.id,
            is_automatic=True,
        )
        future_started = FarmActivity(
            activity_code="ACT-FUTURE-STARTED",
            name="Inspect crop",
            category="Crop Inspection",
            related_to=self.crop.name,
            location=self.crop.field,
            activity_date=date.today() + timedelta(days=1),
            start_time=time(8, 0),
            assigned_by=self.manager.full_name,
            assigned_to=self.employee.full_name,
            status="In Progress",
            source_module="Crop",
            source_type="crop_inspection",
            source_record_id=self.crop.id,
            is_automatic=True,
        )
        alert = FarmAlert(
            alert_name="Harvest ready",
            category="Crop",
            subject=self.crop.name,
            alert_type="Harvest Reminder",
            condition="On or Before",
            threshold="Ready",
            description="Ready",
            priority="High",
            source_type="crop_harvest",
            source_id=self.crop.id,
            status="Active",
            is_automatic=True,
        )
        self.db.add_all([future_pending, future_started, alert])
        self.db.flush()
        final = self.harvest(5, "Final Harvest")
        self.db.flush()
        self.assertEqual(final.quantity_kg, 5)
        self.assertEqual(self.crop.status, "Harvested")
        self.assertIsNotNone(self.crop.completed_at)
        self.assertEqual(future_pending.status, "Voided")
        self.assertEqual(future_started.status, "In Progress")
        self.assertEqual(alert.status, "Resolved")
        production = self.db.scalars(select(LivestockProductionRecord).where(LivestockProductionRecord.source_type == "Crop")).all()
        self.assertEqual(len(production), 2)
        self.assertEqual(sum(float(row.gross_quantity or 0) for row in production), 15.0)

    def test_additional_harvest_rejected_after_final(self):
        self.harvest(7, "Final Harvest")
        with self.assertRaises(HTTPException) as ctx:
            self.harvest(1)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Fully Harvested", ctx.exception.detail)

    def test_task_link_is_idempotent_for_yield_and_production(self):
        task = FarmActivity(
            activity_code="ACT-HARVEST-TASK",
            name="Harvest eggplant",
            category="Crop Harvest",
            related_to=self.crop.name,
            location=self.crop.field,
            activity_date=date.today(),
            start_time=time(7, 0),
            assigned_by=self.manager.full_name,
            assigned_to=self.employee.full_name,
            status="Submitted for Review",
            source_module="Crop",
            source_type="crop_harvest",
            source_record_id=self.crop.id,
            is_automatic=True,
        )
        self.db.add(task)
        self.db.flush()
        kwargs = dict(
            db=self.db,
            crop=self.crop,
            harvest_date=date.today(),
            quantity_kg=4,
            harvest_type="Partial Harvest",
            actor=self.manager,
            performed_by_employee_id=self.employee.id,
            related_task_id=task.id,
        )
        first = record_harvest(**kwargs)
        second = record_harvest(**kwargs)
        self.db.flush()
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(CropYieldRecord).count(), 1)
        self.assertEqual(self.db.query(LivestockProductionRecord).filter(LivestockProductionRecord.source_type == "Crop").count(), 1)

    def test_reopen_preserves_final_harvest_and_production_history(self):
        final = self.harvest(6, "Final Harvest")
        self.db.flush()
        production_id = self.db.scalar(select(LivestockProductionRecord.id).where(LivestockProductionRecord.crop_yield_record_id == final.id))
        reopen_crop_cycle(
            self.db,
            crop=self.crop,
            actor=self.manager,
            reason="Final harvest was entered too early; more fruit remains.",
            new_status="Harvesting",
        )
        self.db.flush()
        self.assertEqual(self.crop.status, "Harvesting")
        self.assertIsNone(self.crop.completed_at)
        self.assertIsNotNone(self.db.get(CropYieldRecord, final.id))
        self.assertIsNotNone(self.db.get(LivestockProductionRecord, production_id))

    def test_reopen_api_and_crop_reads_keep_the_new_status_after_an_old_final_harvest(self):
        self.harvest(6, "Final Harvest")
        self.db.commit()
        with Session(self.engine, expire_on_commit=False) as request_db:
            reopened = reopen_completed_crop(
                self.crop.id, CropReopenRequest(reason="More produce remains on the plants.", new_status="Harvesting"),
                db=request_db, current_user=self.manager,
            )
            self.assertEqual(reopened.status, "Harvesting")

        with Session(self.engine, expire_on_commit=False) as request_db:
            self.assertEqual(get_crop(self.crop.id, db=request_db, _=self.manager).status, "Harvesting")
            self.assertEqual(
                next(row for row in list_crops(include_archived=False, db=request_db, _=self.manager) if row.id == self.crop.id).status,
                "Harvesting",
            )
            self.assertEqual(
                next(row for row in list_crop_details(include_archived=False, db=request_db, _=self.manager) if row.id == self.crop.id).status,
                "Harvesting",
            )
            request_db.commit()  # A GET must not close the reopened crop either.

        with Session(self.engine, expire_on_commit=False) as request_db:
            self.assertEqual(request_db.get(Crop, self.crop.id).status, "Harvesting")
            with self.assertRaises(HTTPException) as error:
                reopen_completed_crop(
                    self.crop.id, CropReopenRequest(reason="Duplicate reopen", new_status="Harvesting"),
                    db=request_db, current_user=self.manager,
                )
            self.assertEqual(error.exception.status_code, 400)

    def test_reopen_as_ready_preserves_selected_status_after_prior_partial_and_final_yields(self):
        self.harvest(3)
        self.harvest(5, "Final Harvest")
        self.db.commit()
        with Session(self.engine, expire_on_commit=False) as request_db:
            reopened = reopen_completed_crop(
                self.crop.id, CropReopenRequest(reason="The next harvest is physically ready.", new_status="Ready for Harvest"),
                db=request_db, current_user=self.manager,
            )
            self.assertEqual(reopened.status, "Ready for Harvest")
        with Session(self.engine, expire_on_commit=False) as request_db:
            self.assertEqual(get_crop(self.crop.id, db=request_db, _=self.manager).status, "Ready for Harvest")
            self.assertEqual(request_db.get(Crop, self.crop.id).status, "Ready for Harvest")

    def test_reopen_manual_completion_without_a_yield_stays_harvesting(self):
        self.crop.status = "Harvested"
        self.crop.growth_stage = "Harvested"
        self.crop.completed_at = farm_now_naive()
        self.db.commit()
        with Session(self.engine, expire_on_commit=False) as request_db:
            reopened = reopen_completed_crop(
                self.crop.id, CropReopenRequest(reason="More produce remains.", new_status="Harvesting"),
                db=request_db, current_user=self.manager,
            )
            self.assertEqual(reopened.status, "Harvesting")
        with Session(self.engine, expire_on_commit=False) as request_db:
            self.assertEqual(get_crop(self.crop.id, db=request_db, _=self.manager).status, "Harvesting")

    def test_reopen_keeps_past_reports_and_allows_a_new_final_harvest(self):
        yesterday = farm_today() - timedelta(days=1)
        first = record_harvest(
            self.db, crop=self.crop, actor=self.manager, harvest_date=yesterday,
            quantity_kg=6, harvest_type="Final Harvest", final_harvest_confirmed=True,
            performed_by_employee_id=self.employee.id, manual_reason="First confirmed harvest",
        )
        self.db.commit()
        before = _build_crop_snapshot(self.db, "Crop Production", yesterday, yesterday)
        operational_before = build_operational_report_snapshot(
            self.db, "Crop Yield and Input Usage", yesterday, yesterday, {"crop_id": self.crop.id},
        )

        reopen_crop_cycle(
            self.db, crop=self.crop, actor=self.manager,
            reason="Another harvest is required after the first final harvest.",
            new_status="Harvesting",
        )
        self.db.commit()
        after = _build_crop_snapshot(self.db, "Crop Production", yesterday, yesterday)
        operational_after = build_operational_report_snapshot(
            self.db, "Crop Yield and Input Usage", yesterday, yesterday, {"crop_id": self.crop.id},
        )
        self.assertEqual(after["metrics"], before["metrics"])
        self.assertEqual(after["status_distribution"], before["status_distribution"])
        self.assertEqual(after["yield_records"], before["yield_records"])
        self.assertEqual(operational_after["operational_rows"], operational_before["operational_rows"])
        self.assertEqual(after["metrics"]["completed_crop_records"], 1)
        self.assertEqual(after["metrics"]["total_harvest_kg"], 6)

        current = _build_crop_snapshot(self.db, "Crop Production", farm_today(), farm_today())
        self.assertEqual(current["metrics"]["active_crop_records"], 1)
        second = self.harvest(4, "Final Harvest")
        self.db.commit()
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(self.crop.status, "Harvested")
        self.assertEqual(self.db.query(CropYieldRecord).count(), 2)
        self.assertEqual(
            self.db.query(LivestockProductionRecord).filter(LivestockProductionRecord.source_type == "Crop").count(), 2,
        )
        after_second_final = _build_crop_snapshot(self.db, "Crop Production", yesterday, yesterday)
        self.assertEqual(after_second_final["metrics"], before["metrics"])
        self.assertEqual(after_second_final["yield_records"], before["yield_records"])

    def test_reopen_preserves_manually_completed_period_without_a_yield(self):
        yesterday = farm_today() - timedelta(days=1)
        self.crop.status = "Harvested"
        self.crop.completed_at = farm_now_naive() - timedelta(days=2)
        self.db.commit()
        previous = _build_crop_snapshot(self.db, "Crop Production", yesterday, yesterday)
        reopen_crop_cycle(
            self.db, crop=self.crop, actor=self.manager,
            reason="Completion was entered too early", new_status="Ready for Harvest",
        )
        self.db.commit()
        regenerated = _build_crop_snapshot(self.db, "Crop Production", yesterday, yesterday)
        self.assertEqual(regenerated["metrics"], previous["metrics"])
        self.assertEqual(regenerated["status_distribution"], previous["status_distribution"])
        current = build_operational_report_snapshot(
            self.db, "Crop Yield and Input Usage", farm_today(), farm_today(), {"crop_id": self.crop.id},
        )
        self.assertEqual(current["operational_rows"][0]["crop_cycle_status"], "Ready for Harvest")

    def test_archiving_does_not_remove_historical_harvest(self):
        yesterday = farm_today() - timedelta(days=1)
        record_harvest(
            self.db, crop=self.crop, actor=self.manager, harvest_date=yesterday,
            quantity_kg=5, harvest_type="Final Harvest", final_harvest_confirmed=True,
            performed_by_employee_id=self.employee.id, manual_reason="Completed field harvest",
        )
        self.db.commit()
        self.crop.is_archived = True
        self.crop.updated_at = farm_now_naive()
        self.db.commit()
        snapshot = _build_crop_snapshot(self.db, "Crop Production", yesterday, yesterday)
        self.assertEqual(snapshot["metrics"]["total_harvest_kg"], 5)
        self.assertEqual(snapshot["metrics"]["completed_crop_records"], 1)

    def test_manual_harvest_requires_performer_reason_and_final_confirmation(self):
        with self.assertRaises(HTTPException):
            record_harvest(
                self.db, crop=self.crop, harvest_date=date.today(), quantity_kg=2,
                harvest_type="Partial Harvest", actor=self.manager,
                performed_by_employee_id=None, manual_reason=None,
            )
        with self.assertRaises(HTTPException) as ctx:
            record_harvest(
                self.db, crop=self.crop, harvest_date=date.today(), quantity_kg=2,
                harvest_type="Final Harvest", actor=self.manager,
                performed_by_employee_id=self.employee.id, manual_reason="manual",
                final_harvest_confirmed=False,
            )
        self.assertIn("explicit confirmation", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
