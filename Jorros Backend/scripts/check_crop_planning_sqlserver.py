"""Exercise migrations and concurrency in a new synthetic SQL Server database only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys
from threading import Barrier
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.database import Base, engine
from app.models import (Crop, CropField, CropSection, FarmActivity, Employee, EmployeeWorkSchedule, EmployeeWorkScheduleDay)
from app.services.backup_recovery.native import SqlServer, identifier
from app.services.crop_land import allocate
from app.services.workforce_intervals import interval_conflict
from scripts.check_installation import inspect_installation


def main():
    adapter = SqlServer(engine)
    name = "JorossRecovery_CropUpdateTest_" + uuid4().hex[:12]
    assert name.startswith("JorossRecovery_CropUpdateTest_") and name != adapter.database
    print("Creating synthetic isolated SQL Server database: " + name, flush=True)
    adapter.create_empty(name)
    target = adapter.target_engine(name)
    result = {"database": name, "synthetic_data_only": True}
    try:
        with target.begin() as connection:
            assert connection.scalar(text("SELECT DB_NAME()")) == name
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "a7b8c9d0e1f2")
            print("Baseline migrations passed; applying crop update with synthetic legacy records.", flush=True)
            # A representative old crop and its linked history survive migration.
            connection.exec_driver_sql("INSERT INTO crops (crop_code,name,variety,field,area_hectares,current_growth,growth_stage,quantity_planted,current_surviving,status,planting_date,estimated_harvest,is_archived) VALUES ('SYN-LEGACY','Legacy synthetic crop','Unrecorded cultivar','Legacy text location',0.20,25,'Seedling',125,115,'Growing','2026-10-01','2026-12-01',0)")
            legacy_id = connection.scalar(text("SELECT id FROM crops WHERE crop_code='SYN-LEGACY'"))
            connection.execute(text("INSERT INTO crop_growth_records (crop_id,growth_percentage,growth_stage,current_surviving,status,update_date) VALUES (:id,25,'Seedling',115,'Growing','2026-11-01')"), {"id": legacy_id})
            command.upgrade(config, "head")
            print("Crop migration applied; checking schema and preserved relationships.", flush=True)
            check = inspect_installation(connection, Base.metadata, "c9d0e1f2a3b4")
            assert check["status"] == "passed", check
            row = connection.execute(text("SELECT id,field,section_id,planting_date,quantity_planted,current_surviving FROM crops WHERE crop_code='SYN-LEGACY'")).mappings().one()
            assert row["id"] == legacy_id and row["section_id"] is None and row["field"] == "Legacy text location"
            assert row["quantity_planted"] == 125 and row["current_surviving"] == 115
            assert connection.scalar(text("SELECT crop_id FROM crop_growth_records")) == legacy_id
            assert connection.scalar(text("SELECT COUNT(*) FROM sys.indexes WHERE object_id=OBJECT_ID('crops') AND name='ix_crops_scheduler_harvest_due'")) == 1
            result["migration_and_legacy_relationships"] = "passed"
        with Session(target) as db:
            field = CropField(name="Synthetic measured field", area_m2=10000, unavailable_area_m2=0)
            db.add(field); db.flush()
            section = CropSection(field_id=field.id, name="Synthetic final-space section", area_m2=2000, unavailable_area_m2=0)
            employee = Employee(employee_code="SYN-WORKER", full_name="Synthetic worker", employment_status="Active")
            db.add_all([section, employee]); db.flush()
            schedule = EmployeeWorkSchedule(employee_id=employee.id, effective_from=date.today()-timedelta(days=1))
            db.add(schedule); db.flush()
            for day in range(7):
                db.add(EmployeeWorkScheduleDay(schedule_id=schedule.id, day_of_week=day, is_working_day=True,
                    start_time=time(7), end_time=time(17), break_start_time=time(12), break_end_time=time(13)))
            db.commit()
            section_id, employee_id = section.id, employee.id
        barrier = Barrier(2)
        def allocate_last_space(index):
            with Session(target) as db:
                crop = Crop(crop_code=f"SYN-CONCURRENT-{index}", name="Synthetic concurrent crop", variety="Unknown",
                    field="Synthetic measured field", area_hectares=Decimal("0.15"), current_growth=None,
                    quantity_planted=None, current_surviving=10, registration_kind="existing", status="Growing",
                    growth_stage="Not estimated", planting_date=None, estimated_harvest=None)
                barrier.wait(timeout=10)
                try:
                    allocate(db, crop, section_id=section_id)
                    db.add(crop); db.commit()
                    return "saved"
                except HTTPException as error:
                    db.rollback()
                    assert error.status_code == 409
                    return "rejected"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(allocate_last_space, [1, 2]))
        assert sorted(outcomes) == ["rejected", "saved"], outcomes
        result["concurrent_last_area_allocation"] = "passed"
        barrier = Barrier(2)
        def assign_same_interval(index):
            with Session(target) as db:
                barrier.wait(timeout=10)
                conflict = interval_conflict(db, employee_id, date.today(), time(10), 45)
                if conflict:
                    db.rollback()
                    return "rejected"
                task = FarmActivity(activity_code=f"SYN-INTERVAL-{index}", name="Synthetic shared work",
                    category="Farm Inspection", related_to="Synthetic", location="Synthetic", activity_date=date.today(),
                    start_time=time(10), end_time=time(10, 45), assigned_employee_id=employee_id,
                    assigned_by="Synthetic", assigned_to="Synthetic worker", status="Pending", priority="Medium",
                    source_module="Crop" if index == 1 else "Livestock")
                db.add(task); db.commit()
                return "saved"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(assign_same_interval, [1, 2]))
        assert sorted(outcomes) == ["rejected", "saved"], outcomes
        result["concurrent_crop_livestock_employee_interval"] = "passed"
        result["status"] = "passed"
        output = ROOT / "backups/crop_update_validation"
        output.mkdir(exist_ok=True)
        (output / "sqlserver_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        target.dispose()
        assert name.startswith("JorossRecovery_CropUpdateTest_") and name != adapter.database
        with adapter.admin() as connection:
            connection.exec_driver_sql("ALTER DATABASE " + identifier(name) + " SET SINGLE_USER WITH ROLLBACK IMMEDIATE").close()
            connection.exec_driver_sql("DROP DATABASE " + identifier(name)).close()


if __name__ == "__main__":
    main()
