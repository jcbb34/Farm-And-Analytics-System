import sys
import types
import unittest
from types import SimpleNamespace
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# The production project uses pyodbc on Windows. The CI/sandbox used for the
# source-level unit tests may not have the native driver, but these tests do not
# open a database connection. A tiny DBAPI stub lets SQLAlchemy construct the
# engine so the pure Smart Import helpers can be imported and tested.
try:
    import pyodbc  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    pyodbc = types.ModuleType("pyodbc")
    pyodbc.paramstyle = "qmark"
    pyodbc.threadsafety = 1
    pyodbc.apilevel = "2.0"
    pyodbc.version = "5.0.0"
    pyodbc.Error = Exception
    pyodbc.ProgrammingError = Exception
    pyodbc.Cursor = type("Cursor", (), {})
    pyodbc.Connection = type("Connection", (), {})
    pyodbc.connect = lambda *args, **kwargs: None
    sys.modules["pyodbc"] = pyodbc

import app.models  # noqa: F401 - registers model metadata for the SQLite integration test
from app.core.database import Base
import app.services.import_service as import_service

from app.services.import_service import (
    SUPPORTED_TARGETS,
    _commit_sort_key,
    _is_utility_sheet,
    detect_target,
    map_and_validate_row,
    suggest_mapping,
)


class SmartImportPenTests(unittest.TestCase):
    PEN_COLUMNS = [
        "Pen Name",
        "Purpose",
        "Animal Type",
        "Capacity",
        "Location Area",
        "Status",
        "Notes",
    ]

    def test_livestock_pen_is_supported_and_detected(self):
        self.assertIn("Livestock Pen", SUPPORTED_TARGETS)
        target, confidence, mapping = detect_target("Livestock Pens", self.PEN_COLUMNS)
        self.assertEqual(target, "Livestock Pen")
        self.assertGreaterEqual(confidence, 90)
        self.assertEqual(mapping["name"], "Pen Name")
        self.assertEqual(mapping["capacity"], "Capacity")

    def test_valid_pen_row_maps_cleanly(self):
        mapping = suggest_mapping("Livestock Pen", self.PEN_COLUMNS)
        source = {
            "Pen Name": "Poultry Pen 5",
            "Purpose": "Meat / Finisher",
            "Animal Type": "Chicken",
            "Capacity": 20,
            "Location Area": "Poultry House",
            "Status": "Active",
            "Notes": "Broiler pen",
        }
        mapped, errors, warnings = map_and_validate_row("Livestock Pen", source, mapping)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(mapped["name"], "Poultry Pen 5")
        self.assertEqual(mapped["capacity"], 20)
        self.assertEqual(mapped["status"], "Active")

    def test_pen_defaults_and_validation(self):
        mapping = suggest_mapping("Livestock Pen", self.PEN_COLUMNS)
        source = {
            "Pen Name": "Duck Pen 1",
            "Purpose": "",
            "Animal Type": "Duck",
            "Capacity": 20,
            "Location Area": "Waterfowl Area",
            "Status": "",
            "Notes": "",
        }
        mapped, errors, _ = map_and_validate_row("Livestock Pen", source, mapping)
        self.assertEqual(errors, [])
        self.assertEqual(mapped["purpose"], "General")
        self.assertEqual(mapped["status"], "Active")

        source["Purpose"] = "Typo Purpose"
        _, errors, _ = map_and_validate_row("Livestock Pen", source, mapping)
        self.assertTrue(any("Purpose" in message for message in errors))

    def test_commit_order_puts_pen_and_inventory_before_livestock(self):
        rows = [
            SimpleNamespace(target_type="Sales", id=6),
            SimpleNamespace(target_type="Livestock", id=4),
            SimpleNamespace(target_type="Livestock Feeding", id=5),
            SimpleNamespace(target_type="Inventory", id=3),
            SimpleNamespace(target_type="Crop", id=2),
            SimpleNamespace(target_type="Livestock Pen", id=1),
        ]
        ordered = [row.target_type for row in sorted(rows, key=_commit_sort_key)]
        self.assertEqual(
            ordered,
            [
                "Livestock Pen",
                "Crop",
                "Inventory",
                "Livestock",
                "Livestock Feeding",
                "Sales",
            ],
        )

    def test_import_instructions_is_utility_sheet(self):
        self.assertTrue(_is_utility_sheet("Import Instructions"))
        self.assertFalse(_is_utility_sheet("Livestock Pens"))

    def test_pen_then_inventory_then_livestock_can_be_created_in_one_transaction(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        original_lock = import_service.acquire_transaction_lock
        import_service.acquire_transaction_lock = lambda db, resource: 0
        try:
            with Session(engine) as db:
                user = SimpleNamespace(id=1)
                pen = import_service._create_record(
                    db,
                    "Livestock Pen",
                    {
                        "name": "Poultry Pen 5",
                        "purpose": "Meat / Finisher",
                        "animal_type": "Chicken",
                        "capacity": 20,
                        "location_area": "Poultry House",
                        "status": "Active",
                        "notes": "Imported pen",
                    },
                    user,
                )
                feed = import_service._create_record(
                    db,
                    "Inventory",
                    {
                        "item_code": "INV-1045",
                        "name": "Chicken Breeder Feed",
                        "category": "Livestock Feed",
                        "batch_number": None,
                        "quantity": 100.0,
                        "unit": "kg",
                        "reorder_level": 10.0,
                        "cost": 30.0,
                        "price": 35.0,
                        "supplier": "Test Supplier",
                        "date_acquired": date(2026, 8, 1),
                        "expiration_date": date(2027, 8, 1),
                        "location": "Feed Storage",
                        "description": "Feed",
                        "notes": None,
                    },
                    user,
                )
                livestock = import_service._create_record(
                    db,
                    "Livestock",
                    {
                        "animal_code": "CHKN-B-0001",
                        "record_type": "Batch",
                        "record_name": "Test Chicken Batch",
                        "animal_type": "Chicken",
                        "breed": "Broiler",
                        "quantity": 3,
                        "sex": "Mixed",
                        "male_quantity": 2,
                        "female_quantity": 1,
                        "unknown_sex_quantity": 0,
                        "date_of_birth": date(2026, 6, 1),
                        "weight_kg": 2.0,
                        "min_weight_kg": 1.8,
                        "max_weight_kg": 2.2,
                        "pen_location": "Poultry Pen 5",
                        "health_status": "Healthy",
                        "healthy_quantity": 3,
                        "at_risk_quantity": 0,
                        "sick_quantity": 0,
                        "under_treatment_quantity": 0,
                        "growth_status": "Finisher",
                        "production_purpose": "Market Ready",
                        "last_checkup": date(2026, 8, 1),
                        "health_notes": None,
                        "vaccination_status": "Up to Date",
                        "next_vaccination": None,
                        "feed_times": "2× daily",
                        "feed_type": "Chicken Breeder Feed",
                        "daily_feed_kg": 0.18,
                        "feeding_notes": None,
                        "date_acquired": date(2026, 6, 1),
                        "acquired_from": "Test Source",
                    },
                    user,
                )
                self.assertEqual(livestock.pen_id, pen.id)
                self.assertEqual(livestock.feed_inventory_item_id, feed.id)
        finally:
            import_service.acquire_transaction_lock = original_lock
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
