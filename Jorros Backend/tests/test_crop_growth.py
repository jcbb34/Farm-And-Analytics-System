import unittest
from datetime import date

from app.services.crop_growth import (
    GROWTH_STAGE_PROGRESS,
    calculate_crop_progress,
    growth_stage_progress,
    stage_for_progress,
    status_for_growth_stage,
    status_for_progress,
    survival_rate,
    validate_survival_counts,
)


class CropGrowthTests(unittest.TestCase):
    def test_automatic_progress_uses_schedule_dates(self):
        planting = date(2026, 8, 1)
        harvest = date(2026, 8, 21)
        self.assertEqual(calculate_crop_progress(planting, harvest, date(2026, 8, 1)), 0.0)
        self.assertEqual(calculate_crop_progress(planting, harvest, date(2026, 8, 11)), 50.0)
        self.assertEqual(calculate_crop_progress(planting, harvest, date(2026, 8, 21)), 100.0)

    def test_stage_is_derived_from_automatic_progress(self):
        self.assertEqual(stage_for_progress(0), "Seeded")
        self.assertEqual(stage_for_progress(15), "Germination")
        self.assertEqual(stage_for_progress(30), "Seedling")
        self.assertEqual(stage_for_progress(50), "Vegetative")
        self.assertEqual(stage_for_progress(65), "Flowering")
        self.assertEqual(stage_for_progress(80), "Fruiting")
        self.assertEqual(stage_for_progress(90), "Maturity")
        self.assertEqual(stage_for_progress(100), "Harvest Ready")

    def test_status_is_derived_from_automatic_progress(self):
        self.assertEqual(status_for_progress(0), "Planted")
        self.assertEqual(status_for_progress(45), "Growing")
        self.assertEqual(status_for_progress(90), "Ready for Harvest")
        self.assertEqual(status_for_progress(100), "Ready for Harvest")

    def test_legacy_stage_helpers_remain_compatible(self):
        values = [
            growth_stage_progress(stage)
            for stage in [
                "Seeded", "Germination", "Seedling", "Vegetative",
                "Flowering", "Fruiting", "Maturity", "Harvest Ready", "Harvested",
            ]
        ]
        self.assertEqual(values, sorted(values))
        self.assertEqual(growth_stage_progress("Unknown"), 0.0)
        self.assertEqual(status_for_growth_stage("Harvested"), "Harvested")

    def test_survival_validation_and_rate(self):
        validate_survival_counts(500, 462)
        self.assertEqual(survival_rate(500, 462), 92.4)

    def test_surviving_cannot_exceed_planted(self):
        with self.assertRaises(ValueError):
            validate_survival_counts(100, 101)

    def test_stage_catalog_has_expected_values(self):
        self.assertEqual(GROWTH_STAGE_PROGRESS["Flowering"], 65.0)
        self.assertEqual(GROWTH_STAGE_PROGRESS["Maturity"], 90.0)


if __name__ == "__main__":
    unittest.main()
