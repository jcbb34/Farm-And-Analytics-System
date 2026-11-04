import unittest

from datetime import date

from pydantic import ValidationError

from test_calendar_event_creation import events, farm

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



# This check exercises the real API and transaction with generated SQLite records;
# it does not require a SQL Server driver or a FakeSession tied to handler internals.
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import InventoryItem, FarmActivity, FarmCreationCommand


def test_create_task_rejects_planned_quantity_above_available_stock(events):
    with Session(events.engine) as db:
        db.get(InventoryItem, events.stock["Fertilizer"]).quantity = 0.55
        before = db.scalar(select(func.count()).select_from(FarmActivity))
        db.commit()
    response = events.client.post("/api/v1/workforce/tasks", headers={
        **events.headers["manager"], "Idempotency-Key": "insufficient-stock-assignment",
    }, json={
        "name": "Fertilize crop", "category": "Fertilization", "activity_date": str(events.today),
        "employee_id": events.employees["worker"], "source_module": "Crop",
        "source_record_id": events.ids["Crop"], "planned_inventory_item_id": events.stock["Fertilizer"],
        "planned_quantity": 1,
    })
    assert response.status_code == 422, response.text
    assert "Insufficient stock for assignment" in response.json()["detail"]
    assert "0.55 kg" in response.json()["detail"]
    with Session(events.engine) as db:
        assert db.scalar(select(func.count()).select_from(FarmActivity)) == before
        assert db.scalar(select(FarmCreationCommand).where(FarmCreationCommand.idempotency_key == "insufficient-stock-assignment")) is None
        assert float(db.get(InventoryItem, events.stock["Fertilizer"]).quantity) == 0.55


if __name__ == "__main__":
    unittest.main()
