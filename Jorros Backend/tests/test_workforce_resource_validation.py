import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from datetime import date

from pydantic import ValidationError

from app.schemas.workforce import CareTemplateStepInput, TaskCreate


class WorkforceResourceValidationTests(unittest.TestCase):
    def base_task(self):
        return {
            "name": "Fertilize Eggplant",
            "category": "Crop Care",
            "related_to": "Eggplant — Field A",
            "location": "Field A",
            "activity_date": date(2026, 9, 8),
        }

    def test_inventory_resource_requires_specific_farm_record(self):
        payload = {
            **self.base_task(),
            "planned_inventory_item_id": 10,
            "planned_quantity": 3,
        }
        with self.assertRaises(ValidationError):
            TaskCreate.model_validate(payload)

    def test_inventory_resource_requires_planned_quantity(self):
        payload = {
            **self.base_task(),
            "source_module": "Crop",
            "source_record_id": 4,
            "planned_inventory_item_id": 10,
        }
        with self.assertRaises(ValidationError):
            TaskCreate.model_validate(payload)

    def test_linked_resource_task_is_valid_with_plan(self):
        payload = {
            **self.base_task(),
            "source_module": "Crop",
            "source_record_id": 4,
            "planned_inventory_item_id": 10,
            "planned_quantity": 3,
        }
        task = TaskCreate.model_validate(payload)
        self.assertEqual(task.planned_inventory_item_id, 10)
        self.assertEqual(task.planned_quantity, 3)

    def test_care_template_inventory_step_requires_plan(self):
        with self.assertRaises(ValidationError):
            CareTemplateStepInput.model_validate({
                "sequence_number": 1,
                "title": "Vaccinate Piglets",
                "category": "Vaccination",
                "inventory_item_id": 8,
            })

    def test_create_task_rejects_planned_quantity_above_available_stock(self):
        try:
            import pyodbc  # noqa: F401
            import pyotp  # noqa: F401
            import qrcode  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("SQL Server/auth runtime packages are not installed in this test environment")
        from app.routers import workforce

        payload = TaskCreate.model_validate({
            **self.base_task(),
            "source_module": "Crop",
            "source_record_id": 4,
            "planned_inventory_item_id": 10,
            "planned_quantity": 1.0,
        })
        inventory_item = SimpleNamespace(
            id=10,
            is_archived=False,
            quantity=0.55,
            unit="kg",
            name="Complete Fertilizer 14-14-14",
            category="Fertilizer",
        )

        class FakeSession:
            def get(self, model, item_id):
                return inventory_item if item_id == 10 else None

        with patch.object(workforce, "_require_workforce_access", return_value=None):
            with self.assertRaises(HTTPException) as caught:
                workforce.create_task(payload, FakeSession(), SimpleNamespace(id=1, full_name="Admin"))

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("Insufficient stock for assignment", caught.exception.detail)
        self.assertIn("0.55 kg", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
