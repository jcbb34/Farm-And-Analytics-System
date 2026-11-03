import unittest
from datetime import date
from types import SimpleNamespace

try:
    from fastapi import HTTPException
    from app.services.resource_usage_service import (
        _ensure_stock,
        _usage_basis,
        _validate_category,
        _validate_expiration,
    )
    RESOURCE_USAGE_IMPORTABLE = True
    RESOURCE_USAGE_IMPORT_ERROR = ""
except ModuleNotFoundError as exc:
    # The lightweight validation container does not include the SQL Server
    # pyodbc driver. 
    RESOURCE_USAGE_IMPORTABLE = False
    RESOURCE_USAGE_IMPORT_ERROR = str(exc)


@unittest.skipUnless(
    RESOURCE_USAGE_IMPORTABLE,
    f"Install backend SQL Server requirements to run resource usage tests: {RESOURCE_USAGE_IMPORT_ERROR}",
)
class ResourceUsageTests(unittest.TestCase):
    def test_crop_and_livestock_categories_match_usage_types(self):
        fertilizer = SimpleNamespace(name="Complete Fertilizer", category="Fertilizer")
        feed = SimpleNamespace(name="Hog Grower", category="Livestock Feed")
        vaccine = SimpleNamespace(name="Newcastle Vaccine", category="Vaccine")

        _validate_category(fertilizer, "Fertilizer")
        _validate_category(feed, "Feed")
        _validate_category(vaccine, "Vaccine")

    def test_wrong_inventory_category_is_rejected(self):
        item = SimpleNamespace(name="Hog Grower", category="Livestock Feed")
        with self.assertRaises(HTTPException):
            _validate_category(item, "Fertilizer")

    def test_usage_cannot_exceed_available_stock(self):
        item = SimpleNamespace(name="Chicken Feed", unit="kg", quantity=5)
        _ensure_stock(item, 5)
        with self.assertRaises(HTTPException):
            _ensure_stock(item, 5.01)

    def test_expired_stock_cannot_be_used_after_expiration(self):
        item = SimpleNamespace(
            name="Vaccine A",
            expiration_date=date(2026, 8, 10),
        )
        _validate_expiration(item, date(2026, 8, 10))
        with self.assertRaises(HTTPException):
            _validate_expiration(item, date(2026, 8, 11))

    def test_usage_basis_snapshots_area_or_animal_count(self):
        crop = SimpleNamespace(area_hectares=0.5)
        livestock = SimpleNamespace(quantity=20)
        self.assertEqual(_usage_basis("Crop", crop), (0.5, "ha"))
        self.assertEqual(_usage_basis("Livestock", livestock), (20.0, "animals"))


if __name__ == "__main__":
    unittest.main()
