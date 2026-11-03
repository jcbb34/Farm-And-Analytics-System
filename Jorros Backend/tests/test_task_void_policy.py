"""HTTP regressions for voiding only approved, eligible performed work."""
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import (AuditLog, CropGrowthRecord, FarmActivity, InventoryItem,
                        InventoryStockRecord, LivestockGrowthRecord, ResourceUsage, TaskSubmission)
from test_resource_monitoring import farm, submit as submit_monitoring, review as review_monitoring


@pytest.fixture
def work(farm):
    with Session(farm.engine) as db:
        item = InventoryItem(item_code="VOID-INV", name="Test Fertilizer", category="Fertilizer", quantity=10,
                             unit="kg", reorder_level=1, cost=1, price=1, supplier="Test supplier",
                             date_acquired=farm.today, location="Test storage")
        db.add(item); db.flush()
        task = db.get(FarmActivity, farm.tasks["Crop"])
        task.name, task.category, task.source_type = "Apply test resource", "Crop Care", "scheduled_resource_work"
        task.status, task.requires_evidence = "Pending", False
        task.planned_inventory_item_id, task.planned_quantity, task.planned_unit = item.id, 2, "kg"
        task.planned_usage_type = "Fertilizer"
        db.commit()
        farm.item_id = item.id
    farm.task_url = f"/api/v1/workforce/tasks/{farm.tasks['Crop']}"
    return farm


def seed_attempt(work, status, review_status=None):
    with Session(work.engine) as db:
        task = db.get(FarmActivity, work.tasks["Crop"])
        task.status = status
        if review_status:
            db.add(TaskSubmission(activity_id=task.id, employee_id=work.employees["worker"],
                                  recorded_by_user_id=work.users["worker"], attempt_number=1,
                                  actual_quantity=2, actual_unit="kg", review_status=review_status))
        db.commit()


def approve(work, *, resource=True):
    if not resource:
        with Session(work.engine) as db:
            task = db.get(FarmActivity, work.tasks["Crop"])
            task.name, task.category, task.source_type, task.source_module, task.source_record_id = "Inspect fence", "Maintenance", None, None, None
            task.planned_inventory_item_id, task.planned_quantity, task.planned_unit, task.planned_usage_type = None, None, None, None
            db.commit()
    payload = {"actual_quantity": 2, "actual_unit": "kg"} if resource else {"worker_notes": "Fence checked"}
    response = work.client.post(work.task_url + "/submit", json=payload, headers=work.headers["worker"])
    assert response.status_code == 200, response.text
    response = work.client.post(work.task_url + "/review", json={"decision": "Approve", "feedback": "Verified original work"}, headers=work.headers["manager"])
    assert response.status_code == 200, response.text
    assert response.json()["can_void"] is True
    return response.json()


@pytest.mark.parametrize("status,review_status", [
    ("Pending", None), ("In Progress", None), ("Submitted for Review", "Submitted"),
    ("Returned", "Returned"), ("Completed", None), ("Completed", "Submitted"),
    ("Completed", "Returned"), ("Voided", "Voided"), ("Resolved", None), ("Cancelled", None),
])
def test_unapproved_or_terminal_work_cannot_be_voided(work, status, review_status):
    seed_attempt(work, status, review_status)
    detail = work.client.get(work.task_url, headers=work.headers["manager"])
    assert detail.status_code == 200 and detail.json()["can_void"] is False
    response = work.client.post(work.task_url + "/void", json={"reason": "Invalid entry"}, headers=work.headers["manager"])
    assert response.status_code == 409
    with Session(work.engine) as db:
        assert db.get(FarmActivity, work.tasks["Crop"]).status == status
        assert float(db.get(InventoryItem, work.item_id).quantity) == 10
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
        latest = db.scalar(select(TaskSubmission))
        assert latest is None or latest.review_status == review_status


@pytest.mark.parametrize("decision", ["Void", "Reject"])
def test_review_endpoint_cannot_bypass_approval_with_legacy_decision(work, decision):
    seed_attempt(work, "Submitted for Review", "Submitted")
    response = work.client.post(work.task_url + "/review", json={"decision": decision, "feedback": "Invalid entry"}, headers=work.headers["manager"])
    assert response.status_code == 400
    with Session(work.engine) as db:
        assert db.get(FarmActivity, work.tasks["Crop"]).status == "Submitted for Review"
        assert db.scalar(select(TaskSubmission)).review_status == "Submitted"
        assert float(db.get(InventoryItem, work.item_id).quantity) == 10


def test_approved_work_void_reverses_inventory_once_and_preserves_approval_audit(work):
    approved = approve(work)
    assert work.client.get(work.task_url, headers=work.headers["manager"]).json()["can_void"] is True
    response = work.client.post(work.task_url + "/void", json={"reason": "  Incorrect reported work  "}, headers=work.headers["manager"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Voided" and response.json()["can_void"] is False
    assert response.json()["latest_submission"]["review_feedback"] == "Incorrect reported work"
    assert work.client.post(work.task_url + "/void", json={"reason": "Incorrect reported work"}, headers=work.headers["manager"]).status_code == 409
    with Session(work.engine) as db:
        assert float(db.get(InventoryItem, work.item_id).quantity) == 10
        movements = db.scalars(select(InventoryStockRecord.adjustment_type).order_by(InventoryStockRecord.id)).all()
        assert movements == ["Task Usage", "Usage Reversal"]
        entries = db.scalars(select(AuditLog).where(AuditLog.action == "Voided approved work", AuditLog.event_type == "audit")).all()
        assert len(entries) == 1
        assert entries[0].actor_user_id == work.users["manager"]
        assert "Incorrect reported work" in entries[0].details and "Verified original work" in entries[0].details
        assert str(approved["latest_submission"]["id"]) in entries[0].details


def test_approved_work_without_inventory_is_voidable_and_audited(work):
    approve(work, resource=False)
    assert work.client.post(work.task_url + "/void", json={"reason": "Incorrect fence report"}, headers=work.headers["manager"]).status_code == 200
    with Session(work.engine) as db:
        assert db.get(FarmActivity, work.tasks["Crop"]).status == "Voided"
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "Voided approved work", AuditLog.event_type == "audit")) == 1


@pytest.mark.parametrize("reason", ["", "   ", " a "])
def test_reason_is_required_before_any_inventory_reversal(work, reason):
    approve(work)
    assert work.client.post(work.task_url + "/void", json={"reason": reason}, headers=work.headers["manager"]).status_code == 422
    with Session(work.engine) as db:
        assert db.get(FarmActivity, work.tasks["Crop"]).status == "Completed"
        assert float(db.get(InventoryItem, work.item_id).quantity) == 8


def test_employee_cannot_void_an_approved_task(work):
    approve(work)
    assert work.client.post(work.task_url + "/void", json={"reason": "Invalid entry"}, headers=work.headers["worker"]).status_code == 403


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_approved_monitoring_remains_immutable(farm, module):
    assert submit_monitoring(farm, module)[0].status_code == 200
    result = review_monitoring(farm, module)
    assert result.status_code == 200 and result.json()["can_void"] is False
    response = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks[module]}/void", json={"reason": "Incorrect observation"}, headers=farm.headers["manager"])
    assert response.status_code == 409
    model = CropGrowthRecord if module == "Crop" else LivestockGrowthRecord
    with Session(farm.engine) as db:
        assert db.get(FarmActivity, farm.tasks[module]).status == "Completed"
        assert db.scalar(select(func.count()).select_from(model)) == 1


def test_harvest_completion_cannot_be_voided_without_reversing_its_linked_yield(work):
    seed_attempt(work, "Completed", "Approved")
    with Session(work.engine) as db:
        db.get(FarmActivity, work.tasks["Crop"]).source_type = "crop_harvest"
        db.commit()
    assert work.client.get(work.task_url, headers=work.headers["manager"]).json()["can_void"] is False
    response = work.client.post(work.task_url + "/void", json={"reason": "Incorrect harvest report"}, headers=work.headers["manager"])
    assert response.status_code == 409 and "harvest" in response.json()["detail"]


def test_failed_void_rolls_back_inventory_and_task_then_allows_retry(work):
    approve(work)
    with patch("app.routers.workforce_handlers._add_workforce_audit", side_effect=RuntimeError("test audit failure")):
        with pytest.raises(RuntimeError):
            work.client.post(work.task_url + "/void", json={"reason": "Incorrect entry"}, headers=work.headers["manager"])
    with Session(work.engine) as db:
        assert db.get(FarmActivity, work.tasks["Crop"]).status == "Completed"
        assert db.scalar(select(TaskSubmission)).review_status == "Approved"
        assert float(db.get(InventoryItem, work.item_id).quantity) == 8
        assert db.scalar(select(ResourceUsage)).is_voided is False
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord)) == 1
    assert work.client.post(work.task_url + "/void", json={"reason": "Incorrect entry"}, headers=work.headers["manager"]).status_code == 200
