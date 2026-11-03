"""HTTP/transaction regressions for the five system audit findings (isolated DB)."""
import json
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_calendar_event_creation import events, create, payload
from test_resource_monitoring import farm
from app.models import AuditLog, FarmActivity, FarmCreationCommand, InventoryItem, InventoryStockRecord, ResourceUsage, TaskSubmission, User
from app.routers import activities, inventory
from app.schemas.activity import FarmActivityUpdate
from app.schemas.inventory import InventoryCreate, InventoryUpdate


def inventory_body(events, **changes):
    return dict(name="New fertilizer", category="Fertilizer", quantity=10, unit="kg",
                reorder_level=0, cost=0, price=0, supplier="Test supplier",
                date_acquired=str(events.today), location="Warehouse B", **changes)


def post_inventory(events, body=None, key="inventory-audit-1", actor="manager"):
    return events.client.post("/api/v1/inventory", json=body or inventory_body(events),
                              headers={**events.headers[actor], "Idempotency-Key": key})


def total(events, model):
    with Session(events.engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def submit_resource_task(events, *, approve):
    response = create(events, payload(events, name="Vaccination", category="Vaccination",
        source_module="Livestock", source_record_id=events.ids["Livestock"],
        planned_inventory_item_id=events.stock["Vaccine"], planned_quantity=3))
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    photo = BytesIO()
    Image.new("RGB", (100, 100), "green").save(photo, format="PNG")
    evidence = events.client.post(f"/api/v1/workforce/tasks/{task_id}/evidence",
        files={"file": ("synthetic.png", photo.getvalue(), "image/png")}, headers=events.headers["worker"])
    assert evidence.status_code == 201, evidence.text
    response = events.client.post(f"/api/v1/workforce/tasks/{task_id}/submit",
        json={"actual_quantity": 2, "actual_unit": "doses", "evidence_url": evidence.json()["evidence_url"],
              "worker_notes": "Inspected and completed"}, headers=events.headers["worker"])
    assert response.status_code == 200, response.text
    if approve:
        response = events.client.post(f"/api/v1/workforce/tasks/{task_id}/review",
                                      json={"decision": "Approve"}, headers=events.headers["manager"])
        assert response.status_code == 200, response.text
    return task_id


@pytest.mark.parametrize("approve", [False, True])
def test_submitted_and_approved_manual_work_cannot_be_reopened_or_rewritten(events, approve):
    task_id = submit_resource_task(events, approve=approve)
    # Ordinary management permissions must not bypass the authoritative workflow.
    with Session(events.engine) as db:
        manager = db.get(User, events.users["manager"])
        manager.role.set_permissions(["activities:view", "activities:update", "workforce:manage", "workforce:review"])
        expected_status = db.get(FarmActivity, task_id).status
        completed_at = db.get(FarmActivity, task_id).completed_at
        db.commit()
    cases = [{"status": value} for value in ["Pending", "In Progress", "Returned", "Cancelled", "Resolved"]]
    cases += [{"requires_review": False, "requires_evidence": False},
              {"assigned_employee_id": None}, {"assigned_to": "Someone else"},
              {"name": "Changed task", "planned_quantity": 999}, {"location": "Another pen"}]
    for changes in cases:
        response = events.client.put(f"/api/v1/activities/{task_id}", json=changes, headers=events.headers["manager"])
        assert response.status_code == 400, (changes, response.text)
    for action in ["start", "resolve"]:
        response = events.client.post(f"/api/v1/workforce/tasks/{task_id}/{action}", json={}, headers=events.headers["manager"])
        assert response.status_code == 400, (action, response.text)
    same = events.client.put(f"/api/v1/activities/{task_id}", json={"status": expected_status}, headers=events.headers["manager"])
    assert same.status_code == 200, same.text
    with Session(events.engine) as db:
        task = db.get(FarmActivity, task_id)
        assert task.status == expected_status and task.completed_at == completed_at
        assert task.name == "Vaccination" and task.assigned_employee_id == events.employees["worker"]
        assert task.requires_review and task.requires_evidence and task.planned_quantity == 3
        submission = db.scalar(select(TaskSubmission).where(TaskSubmission.activity_id == task_id))
        assert submission.review_status == ("Approved" if approve else "Submitted")
        assert db.get(InventoryItem, events.stock["Vaccine"]).quantity == (18 if approve else 20)
        usages = db.scalars(select(ResourceUsage).where(ResourceUsage.activity_id == task_id)).all()
        assert len(usages) == int(approve)
        assert all(usage.task_posting_active for usage in usages)


def test_open_task_cannot_forge_review_state_but_safe_metadata_can_change(events):
    task_id = create(events).json()["id"]
    for changes in [{"status": status} for status in ["Submitted for Review", "Returned", "Cancelled", "Resolved", "In Progress"]] + [{"requires_evidence": False}]:
        response = events.client.put(f"/api/v1/activities/{task_id}", json=changes, headers=events.headers["manager"])
        assert response.status_code == 400, response.text
    response = events.client.put(f"/api/v1/activities/{task_id}", json={"priority": "Critical", "instructions": "Inspect the fence"}, headers=events.headers["manager"])
    assert response.status_code == 200, response.text
    assert response.json()["priority"] == "Critical"


def test_rejected_activity_edits_leave_no_dirty_partial_state(events):
    task_id = create(events).json()["id"]
    with Session(events.engine) as db:
        task = db.get(FarmActivity, task_id)
        actor = db.get(User, events.users["manager"])
        with pytest.raises(Exception) as error:
            activities.update_activity(task_id, FarmActivityUpdate(name="Partial edit", location="  "), db=db, current_user=actor)
        assert error.value.status_code == 400
        assert not db.is_modified(task)
        assert task.name == "Inspect fences"


def test_standalone_calendar_activity_keeps_its_direct_completion_flow(events):
    response = create(events, payload(events, assigned_employee_id=None, requires_review=False))
    task_id = response.json()["id"]
    for status in ["In Progress", "Completed"]:
        response = events.client.put(f"/api/v1/activities/{task_id}", json={"status": status}, headers=events.headers["manager"])
        assert response.status_code == 200, response.text
    assert response.json()["completed_at"]


def test_inventory_create_retry_has_one_record_one_opening_movement_and_one_audit(events):
    baseline = total(events, InventoryItem)
    first = post_inventory(events)
    assert first.status_code == 201, first.text
    second = post_inventory(events)
    assert second.status_code == 201 and first.json()["id"] == second.json()["id"]
    assert total(events, InventoryItem) == baseline + 1
    with Session(events.engine) as db:
        item = db.get(InventoryItem, first.json()["id"])
        assert item.quantity == 10
        assert len(db.scalars(select(InventoryStockRecord).where(InventoryStockRecord.inventory_item_id == item.id)).all()) == 1
        assert len(db.scalars(select(FarmCreationCommand).where(FarmCreationCommand.command_type == "inventory_create")).all()) == 1
        entries = db.scalars(select(AuditLog).where(AuditLog.entity_id == item.item_code)).all()
        assert {entry.event_type for entry in entries} == {"audit", "timeline"} and len(entries) == 2
        assert all(entry.actor_user_id == events.users["manager"] for entry in entries)
    assert post_inventory(events, {**inventory_body(events), "quantity": 20}).status_code == 409
    # A genuinely separate acquisition is allowed with a new command.
    third = post_inventory(events, key="inventory-second-acquisition")
    assert third.status_code == 201 and third.json()["id"] != first.json()["id"]


def test_inventory_key_cannot_be_reused_by_another_actor_or_another_command(events):
    assert post_inventory(events).status_code == 201
    with Session(events.engine) as db:
        db.get(User, events.users["other"]).role.set_permissions(["inventory:view", "inventory:create"])
        db.commit()
    assert post_inventory(events, actor="other").status_code == 409
    assert create(events, key="inventory-audit-1").status_code == 409


def test_inventory_update_audits_before_after_atomically_without_browser_post(events):
    item_id = events.stock["Fertilizer"]
    response = events.client.put(f"/api/v1/inventory/{item_id}",
        json={"supplier": " New supplier ", "location": "Warehouse B", "cost": 5}, headers=events.headers["manager"])
    assert response.status_code == 200, response.text
    with Session(events.engine) as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.event_type == "audit", AuditLog.entity_id == response.json()["item_code"]))
        assert entry.actor_user_id == events.users["manager"] and entry.action == "Updated inventory record"
        changes = json.loads(entry.details)["changes"]
        assert changes["supplier"] == {"before": "Test supplier", "after": "New supplier"}
        assert changes["location"] == {"before": "Storage A", "after": "Warehouse B"}
        assert "quantity" not in changes
    count_before = total(events, AuditLog)
    same = events.client.put(f"/api/v1/inventory/{item_id}", json={"supplier": "New supplier"}, headers=events.headers["manager"])
    assert same.status_code == 200 and total(events, AuditLog) == count_before


@pytest.mark.parametrize("operation", ["create", "update"])
def test_inventory_audit_failure_rolls_back_record_stock_and_command(events, operation):
    count_before = total(events, InventoryItem)
    with Session(events.engine) as db:
        actor = db.get(User, events.users["manager"])
        item_id = events.stock["Fertilizer"]
        original = db.get(InventoryItem, item_id).supplier
        def failed_audit(*args, **kwargs):
            raise RuntimeError("Synthetic audit storage failure")
        with patch.object(inventory, "record_inventory_change", side_effect=failed_audit):
            with pytest.raises(RuntimeError):
                if operation == "create":
                    inventory.create_inventory_item(InventoryCreate(**inventory_body(events)), db=db, current_user=actor, idempotency_key="audit-rollback")
                else:
                    inventory.update_inventory_item(item_id, InventoryUpdate(supplier="Unsaved supplier"), db=db, current_user=actor)
        assert db.get(InventoryItem, item_id).supplier == original
    assert total(events, InventoryItem) == count_before
    assert total(events, InventoryStockRecord) == 0
    assert total(events, FarmCreationCommand) == 0
    assert total(events, AuditLog) == 0
    # Rollback also releases the command so a legitimate retry can succeed.
    assert post_inventory(events, key="audit-rollback").status_code == 201


@pytest.mark.parametrize("field", ["name", "category", "unit", "supplier", "location"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_whitespace_required_inventory_fields_are_rejected_before_any_write(events, field, operation):
    count_before = total(events, InventoryItem)
    if operation == "create":
        response = post_inventory(events, {**inventory_body(events), field: " \t  "})
    else:
        response = events.client.put(f"/api/v1/inventory/{events.stock['Fertilizer']}",
            json={"description": "Must not be saved", field: " \t  "}, headers=events.headers["manager"])
    assert response.status_code == 422, response.text
    assert total(events, InventoryItem) == count_before
    assert total(events, InventoryStockRecord) == total(events, FarmCreationCommand) == total(events, AuditLog) == 0
    with Session(events.engine) as db:
        assert db.get(InventoryItem, events.stock["Fertilizer"]).description is None


def test_inventory_normalizes_optional_text_and_accepts_zero_values(events):
    body = {**inventory_body(events), "name": "  New fertilizer  ", "quantity": 0, "batch_number": "   ", "notes": "\t"}
    response = post_inventory(events, body)
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "New fertilizer" and response.json()["batch_number"] is None and response.json()["notes"] is None
    assert response.json()["quantity"] == response.json()["price"] == response.json()["cost"] == 0
    assert total(events, InventoryStockRecord) == 0
