"""Calendar and Assign Task share supported work and approved monitoring records."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm, observation, photo
from test_calendar_event_creation import events, create, payload
from test_workflow_consistency import manual, post_manual
from app.models import Crop, CropGrowthRecord, FarmActivity, InventoryItem, Livestock, LivestockGrowthRecord
from app.services.monitoring_scheduler import sync_monitoring_tasks


def schedule(events, entry, module, **changes):
    values = dict(category="Crop Growth Monitoring" if module == "Crop" else "Weight Monitoring",
                  source_module=module, source_record_id=events.ids[module], source_type="manual_work",
                  activity_date=str(events.today - timedelta(days=1)))
    values.update(changes)
    return (create(events, payload(events, **values)) if entry == "calendar"
            else post_manual(events, manual(events, **values)))


@pytest.mark.parametrize("entry", ["calendar", "assignment"])
@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_manual_monitoring_posts_only_after_authorized_review(events, entry, module):
    response = schedule(events, entry, module)
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["source_type"] == f"{module.lower()}_growth_check"
    assert task["requires_review"] is True
    assert task["requires_evidence"] is True
    detail = events.client.get(f"/api/v1/workforce/tasks/{task['id']}", headers=events.headers["manager"])
    assert detail.json()["monitoring_context"]["resource_type"] == module
    history = CropGrowthRecord if module == "Crop" else LivestockGrowthRecord
    resource = Crop if module == "Crop" else Livestock
    def current():
        with Session(events.engine) as db:
            row = db.get(resource, events.ids[module])
            return row.current_surviving if module == "Crop" else float(row.weight_kg)
    before = current()
    events.tasks[module] = task["id"]
    submitted = events.client.post(f"/api/v1/workforce/tasks/{task['id']}/submit",
        json={"monitoring": observation(events, module), "evidence_url": photo(events, module)},
        headers=events.headers["worker"])
    assert submitted.status_code == 200, submitted.text
    assert current() == before
    with Session(events.engine) as db:
        assert db.scalar(select(func.count()).select_from(history)) == 0
    denied = events.client.post(f"/api/v1/workforce/tasks/{task['id']}/review",
        json={"decision": "Approve"}, headers=events.headers["other"])
    assert denied.status_code == 403
    reviewed = events.client.post(f"/api/v1/workforce/tasks/{task['id']}/review",
        json={"decision": "Approve"}, headers=events.headers["manager"])
    assert reviewed.status_code == 200, reviewed.text
    assert current() == (93 if module == "Crop" else 30)
    with Session(events.engine) as db:
        assert db.scalar(select(func.count()).select_from(history)) == 1
        assert db.scalar(select(history)).related_task_id == task["id"]
        assert all(float(item.quantity) == 20 for item in db.scalars(select(InventoryItem)).all())


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_monitoring_reuses_native_occurrence_and_does_not_duplicate_cross_entry(events, module):
    duplicate = schedule(events, "calendar", module, activity_date=str(events.today))
    assert duplicate.status_code == 409
    assert duplicate.headers["X-Existing-Task-Id"] == str(events.tasks[module])
    first = schedule(events, "calendar", module)
    assert first.status_code == 201, first.text
    other = schedule(events, "assignment", module)
    assert other.status_code == 409
    assert other.headers["X-Existing-Task-Id"] == str(first.json()["id"])
    with Session(events.engine) as db:
        sync_monitoring_tasks(db, today=events.today, active_keys=set(), counters={"created": 0, "updated": 0, "unchanged": 0, "completed": 0})
        db.commit()
        key = f"{module.lower()}:growth-check:{events.ids[module]}:{events.today - timedelta(days=1)}"
        assert db.scalar(select(func.count()).select_from(FarmActivity).where(FarmActivity.source_key == key)) == 1


@pytest.mark.parametrize("entry", ["calendar", "assignment"])
@pytest.mark.parametrize("changes", [
    {"source_module": None, "source_record_id": None},
    {"source_module": "Crop"},
    {"status": "Completed"},
    {"activity_date": "2099-01-01"},
])
def test_monitoring_rejects_invalid_record_or_workflow(events, entry, changes):
    # Livestock has no end date by default; give it a finite monitoring period.
    with Session(events.engine) as db:
        db.get(Livestock, events.ids["Livestock"]).monitoring_end_date = events.today + timedelta(days=7)
        db.commit()
    response = schedule(events, entry, "Livestock", **changes)
    if entry == "assignment" and changes.get("status") == "Completed":
        # TaskCreate ignores client status and always constructs Pending work.
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "Pending"
    else:
        assert response.status_code == 422, response.text


@pytest.mark.parametrize("entry", ["calendar", "assignment"])
def test_unsupported_equipment_work_is_rejected_in_both_entry_points(events, entry):
    values = {"category": "Equipment Maintenance", "source_module": None, "source_record_id": None}
    response = (create(events, payload(events, **values)) if entry == "calendar"
                else post_manual(events, manual(events, **values)))
    assert response.status_code == 422
    assert "not a supported farm activity" in response.text


def test_restock_source_type_cannot_bypass_a_crop_inventory_workflow(events):
    values = dict(category="Fertilization", name="Fertilize crop", source_type="inventory_restock_plan",
                  source_module="Crop", source_record_id=events.ids["Crop"],
                  planned_inventory_item_id=events.stock["Fertilizer"], planned_quantity=2, planned_unit="kg")
    for entry in ["calendar", "assignment"]:
        response = (create(events, payload(events, **values)) if entry == "calendar"
                    else post_manual(events, manual(events, **values)))
        assert response.status_code == 422
        assert "must link an inventory item" in response.text
    with Session(events.engine) as db:
        assert float(db.get(InventoryItem, events.stock["Fertilizer"]).quantity) == 20


def test_weight_monitoring_rejects_inactive_livestock(events):
    with Session(events.engine) as db:
        db.get(Livestock, events.ids["Livestock"]).lifecycle_status = "Sold"
        db.commit()
    response = schedule(events, "calendar", "Livestock")
    assert response.status_code == 422
    assert "active livestock" in response.text
