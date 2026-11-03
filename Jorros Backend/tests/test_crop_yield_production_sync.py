import unittest
import sys
from datetime import date
from types import ModuleType, SimpleNamespace

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    if "app.core.database" not in sys.modules:
        from sqlalchemy.orm import DeclarativeBase

        class _TestBase(DeclarativeBase):
            pass

        database_module = ModuleType("app.core.database")
        database_module.Base = _TestBase

        def _get_db():
            yield None

        database_module.get_db = _get_db
        sys.modules["app.core.database"] = database_module

try:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.core.database import Base
    from app.models import Crop, CropYieldRecord, LivestockProductionRecord
    from app.services.production_sales_service import create_crop_production_from_yield
    PRODUCTION_SYNC_IMPORTABLE = True
    PRODUCTION_SYNC_IMPORT_ERROR = ""
except ModuleNotFoundError as exc:
    PRODUCTION_SYNC_IMPORTABLE = False
    PRODUCTION_SYNC_IMPORT_ERROR = str(exc)


@unittest.skipUnless(
    PRODUCTION_SYNC_IMPORTABLE,
    f"Install backend SQL Server requirements to run crop production sync tests: {PRODUCTION_SYNC_IMPORT_ERROR}",
)
class CropYieldProductionSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = SimpleNamespace(id=None, full_name="System Administrator", username="admin")
        self.crop = Crop(
            crop_code="CRP-TEST-1",
            name="Eggplant",
            variety="Long Purple",
            field="Field A",
            area_hectares=0.5,
            current_growth=100,
            growth_stage="Harvested",
            quantity_planted=100,
            current_surviving=95,
            status="Harvested",
            planting_date=date(2026, 1, 1),
            estimated_harvest=date(2026, 4, 1),
            fertilizer_quantity_kg=0,
            is_archived=False,
        )
        self.db.add(self.crop)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_creates_crop_production_from_imported_yield(self):
        yield_record = CropYieldRecord(
            crop_id=self.crop.id,
            harvest_date=date(2026, 4, 1),
            quantity_kg=1518,
            farm_use_quantity_kg=0,
            damaged_quantity_kg=0,
            reserved_quantity_kg=0,
            quality="Good",
        )
        self.db.add(yield_record)
        self.db.flush()

        result = create_crop_production_from_yield(
            self.db,
            yield_record,
            self.crop,
            self.user,
        )

        production = self.db.get(LivestockProductionRecord, result["id"])
        self.assertEqual(production.source_type, "Crop")
        self.assertEqual(production.crop_yield_record_id, yield_record.id)
        self.assertEqual(float(production.gross_quantity), 1518.0)
        self.assertEqual(float(production.quantity), 1518.0)
        self.assertTrue(production.track_sale_inventory)

    def test_sync_is_idempotent_and_updates_existing_row(self):
        yield_record = CropYieldRecord(
            crop_id=self.crop.id,
            harvest_date=date(2026, 4, 1),
            quantity_kg=100,
            farm_use_quantity_kg=5,
            damaged_quantity_kg=2,
            reserved_quantity_kg=3,
        )
        self.db.add(yield_record)
        self.db.flush()

        first = create_crop_production_from_yield(self.db, yield_record, self.crop, self.user)
        yield_record.quantity_kg = 120
        second = create_crop_production_from_yield(self.db, yield_record, self.crop, self.user)

        self.assertEqual(first["id"], second["id"])
        rows = self.db.query(LivestockProductionRecord).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0].gross_quantity), 120.0)
        self.assertEqual(float(rows[0].quantity), 110.0)

    def test_imported_1518_kg_harvest_appears_once_after_update_and_retry(self):
        from app.routers.production_sales import list_production
        from app.services.import_service import _create_record, _find_child_duplicate, _update_record

        mapped = {
            "crop_code": self.crop.crop_code,
            "harvest_date": date(2026, 4, 1),
            "quantity_kg": 1518,
            "quality": "Good",
            "harvest_type": "Final Harvest",
        }
        imported = _create_record(self.db, "Crop Yield", mapped, self.user)
        original_production = self.db.scalar(
            select(LivestockProductionRecord).where(LivestockProductionRecord.crop_yield_record_id == imported.id)
        )
        self.assertIsNotNone(original_production)

        # An identical worksheet row must match the existing yield instead of
        # creating a second production row for the same harvested crop.
        match, _ = _find_child_duplicate(self.db, "Crop Yield", mapped, self.crop.id)
        self.assertEqual(match.id, imported.id)

        mapping = {"quantity_kg": "Yield (kg)"}
        for amount in (1518, 1520, 1518):
            _update_record(self.db, imported, "Crop Yield", {"quantity_kg": amount}, mapping)
            self.db.flush()
            create_crop_production_from_yield(self.db, imported, self.crop, self.user)

        production = list_production(
            livestock_id=None,
            crop_id=self.crop.id,
            source_type="crop",
            available_only=False,
            limit=100,
            db=self.db,
            _=self.user,
        )
        self.assertEqual(len(production), 1)
        self.assertEqual(production[0]["id"], original_production.id)
        self.assertEqual(float(production[0]["gross_quantity"]), 1518.0)
        self.assertEqual(float(production[0]["quantity"]), 1518.0)


if __name__ == "__main__":
    unittest.main()
