import unittest
from datetime import date

from pydantic import ValidationError

from app.schemas.livestock import LivestockCreate


class LivestockSchemaTests(unittest.TestCase):
    def _payload(self, **changes):
        payload = {
            "record_name": "Layer Batch A",
            "animal_type": "Chicken",
            "breed": "Rhode Island Red",
            "quantity": 10,
            "sex": "Mixed",
            "record_type": "Batch",
            "date_of_birth": date(2026, 4, 1),
            "weight_kg": 1.5,
            "pen_location": "Layer Pen 1",
            "health_status": "Healthy",
            "growth_status": "Pre-Laying",
            "vaccination_status": "Up to Date",
            "date_acquired": date(2026, 5, 1),
        }
        payload.update(changes)
        return payload

    def test_extended_growth_statuses_are_valid(self):
        for status in ("Brooding", "Pre-Laying", "Laying", "Ready for Market", "Lactating"):
            record = LivestockCreate(**self._payload(growth_status=status))
            self.assertEqual(record.growth_status, status)

    def test_aggregate_counts_must_match_quantity(self):
        with self.assertRaises(ValidationError):
            LivestockCreate(
                **self._payload(
                    male_quantity=3,
                    female_quantity=3,
                    unknown_sex_quantity=0,
                )
            )

    def test_health_breakdown_sets_mixed_status(self):
        record = LivestockCreate(
            **self._payload(
                healthy_quantity=8,
                at_risk_quantity=2,
                sick_quantity=0,
                under_treatment_quantity=0,
            )
        )
        self.assertEqual(record.health_status, "Mixed")


if __name__ == "__main__":
    unittest.main()
