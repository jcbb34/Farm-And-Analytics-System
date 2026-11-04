"""Regression checks for shared creation and operational records, using generated data only."""

from datetime import timedelta
from io import BytesIO

from PIL import Image
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from test_calendar_event_creation import events, farm, create, payload
from app.models import (
    Crop,
    CropYieldRecord,
    FarmActivity,
    InventoryItem,
    Livestock,
    LivestockFeedingRecord,
    LivestockProductionRecord,
    ResourceUsage,
    TaskAssignmentHistory,
    TaskSubmission,
    User,
)
from app.routers import resource_usages, workforce_handlers
from app.services import task_engine


def manual(events, **changes):
    value = {
        "name": "Inspect fence",
        "category": "Farm Inspection",
        "activity_date": str(events.today),
        "start_time": "08:00",
        "employee_id": events.employees["worker"],
        "requires_evidence": False,
    }
    value.update(changes)
    return value


def post_manual(events, value, key="same-task-command"):
    return events.client.post(
        "/api/v1/workforce/tasks",
        json=value,
        headers={**events.headers["manager"], "Idempotency-Key": key},
    )


def complete(events, task, **details):
    body = {"worker_notes": "Synthetic performed work", **details}
    if task.get("requires_evidence"):
        data = BytesIO()
        Image.new("RGB", (100, 100), "green").save(data, format="PNG")
        photo = events.client.post(
            f"/api/v1/workforce/tasks/{task['id']}/evidence",
            headers=events.headers["worker"],
            files={"file": ("review.png", data.getvalue(), "image/png")},
        )
        assert photo.status_code == 201, photo.text
        body["evidence_url"] = photo.json()["evidence_url"]
    response = events.client.post(
        f"/api/v1/workforce/tasks/{task['id']}/submit",
        json=body,
        headers={**events.headers["worker"], "Idempotency-Key": f"submit-{task['id']}"},
    )
    assert response.status_code == 200, response.text
    approval = events.client.post(
        f"/api/v1/workforce/tasks/{task['id']}/review",
        json={
            "decision": "Approve",
            **(
                {"harvest_type": details["harvest_type_intent"]}
                if details.get("harvest_type_intent")
                else {}
            ),
        },
        headers=events.headers["manager"],
    )
    assert approval.status_code == 200, approval.text
    return approval.json()


def test_assignment_and_calendar_each_reuse_their_creation_command(events):
    first = post_manual(events, manual(events))
    second = post_manual(events, manual(events))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert create(events).json()["id"] == create(events).json()["id"]
    conflict = post_manual(events, manual(events, name="Different task"))
    assert conflict.status_code == 409


@pytest.mark.parametrize("archived", [False, True])
def test_both_entry_points_reject_missing_or_archived_target(events, archived):
    target_id = events.ids["Crop"] if archived else 999999
    if archived:
        with Session(events.engine) as db:
            db.get(Crop, target_id).is_archived = True
            db.commit()
    changes = dict(
        source_module="Crop", source_type="manual_work", source_record_id=target_id
    )
    assert post_manual(events, manual(events, **changes)).status_code == 422
    assert create(events, payload(events, **changes)).status_code == 422


def test_both_entry_points_reject_unlinked_consuming_work(events):
    changes = dict(
        name="Feed pigs",
        category="Livestock Feeding",
        source_module="Livestock",
        source_type="manual_work",
        source_record_id=events.ids["Livestock"],
    )
    assert post_manual(events, manual(events, **changes)).status_code == 422
    assert create(events, payload(events, **changes)).status_code == 422


def test_crop_editor_cannot_bypass_approved_task_correction(events):
    events.client.app.include_router(resource_usages.router)
    task = create(
        events,
        payload(
            events,
            name="Fertilize crop",
            category="Fertilization",
            source_module="Crop",
            source_type="manual_work",
            source_record_id=events.ids["Crop"],
            planned_inventory_item_id=events.stock["Fertilizer"],
            planned_quantity=5,
        ),
    )
    assert task.status_code == 201, task.text
    complete(
        events,
        task.json(),
        actual_quantity=5,
        actual_unit="kg",
        actual_quantity_confirmed=True,
    )
    with Session(events.engine) as db:
        usage_id = db.scalar(
            select(ResourceUsage.id).where(
                ResourceUsage.activity_id == task.json()["id"]
            )
        )
        db.get(User, events.users["other"]).role.set_permissions(
            ["crops:view", "crops:update"]
        )
        db.commit()
    correction = events.client.put(
        f"/api/v1/resource-usages/{usage_id}",
        json={"quantity": 2},
        headers=events.headers["other"],
    )
    assert correction.status_code == 409
    rows = events.client.get(
        "/api/v1/resource-usages", headers=events.headers["other"]
    ).json()
    row = next(row for row in rows if row["id"] == usage_id)
    assert row["activity_id"] == task.json()["id"] and row["task_submission_id"]
    with Session(events.engine) as db:
        submission = db.scalar(
            select(TaskSubmission).where(
                TaskSubmission.activity_id == task.json()["id"]
            )
        )
        assert (
            float(submission.actual_quantity)
            == float(db.get(ResourceUsage, usage_id).quantity)
            == 5
        )
        assert submission.review_status == "Approved"
        assert float(db.get(InventoryItem, events.stock["Fertilizer"]).quantity) == 15


@pytest.mark.parametrize("via", ["calendar", "task"])
def test_feeding_approval_updates_one_canonical_occurrence_and_stock(events, via):
    with Session(events.engine) as db:
        animal = db.get(Livestock, events.ids["Livestock"])
        animal.feed_inventory_item_id = events.stock["Livestock Feed"]
        animal.daily_feed_kg = 10
        animal.feed_times = "Morning"
        db.commit()
    changes = dict(
        name="Feed pigs",
        category="Livestock Feeding",
        source_module="Livestock",
        source_type="manual_work",
        source_record_id=events.ids["Livestock"],
        planned_inventory_item_id=events.stock["Livestock Feed"],
        planned_quantity=2,
    )
    response = (
        create(events, payload(events, **changes))
        if via == "calendar"
        else post_manual(events, manual(events, **changes))
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["source_type"] == "livestock_feeding"
    complete(
        events,
        task,
        actual_quantity=2,
        actual_unit="kg",
        actual_quantity_confirmed=True,
    )
    with Session(events.engine) as db:
        task_engine.evaluate_automatic_tasks(db)
        feeding = db.scalars(select(LivestockFeedingRecord)).one()
        assert (
            feeding.feeding_slot == "Morning" and float(feeding.actual_quantity_kg) == 2
        )
        assert (
            float(db.get(InventoryItem, events.stock["Livestock Feed"]).quantity) == 18
        )
        rows = db.scalars(
            select(FarmActivity).where(
                FarmActivity.source_type == "livestock_feeding",
                FarmActivity.source_record_id == events.ids["Livestock"],
                FarmActivity.activity_date == events.today,
            )
        ).all()
        assert (
            len(rows) == 1
            and rows[0].id == task["id"]
            and rows[0].status == "Completed"
        )


@pytest.mark.parametrize("via", ["calendar", "task"])
def test_harvest_approval_creates_yield_and_production_once(events, via):
    with Session(events.engine) as db:
        crop = db.get(Crop, events.ids["Crop"])
        crop.status = "Ready for Harvest"
        crop.estimated_harvest = events.today
        db.commit()
    changes = dict(
        name="Harvest crop",
        category="Harvesting",
        source_module="Crop",
        source_type="manual_work",
        source_record_id=events.ids["Crop"],
    )
    response = (
        create(events, payload(events, **changes))
        if via == "calendar"
        else post_manual(events, manual(events, **changes))
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["source_type"] == "crop_harvest"
    completed = complete(
        events,
        task,
        actual_quantity=25,
        actual_unit="kg",
        harvest_type_intent="Partial Harvest",
    )
    assert completed["status"] == "Completed"
    with Session(events.engine) as db:
        task_engine.evaluate_automatic_tasks(db)
        yield_row = db.scalars(select(CropYieldRecord)).one()
        assert (
            float(yield_row.quantity_kg) == 25
            and yield_row.related_task_id == task["id"]
        )
        assert (
            db.scalar(select(func.count()).select_from(LivestockProductionRecord)) == 1
        )
        assert db.get(Crop, events.ids["Crop"]).status == "Harvesting"
        assert (
            db.scalar(
                select(func.count())
                .select_from(FarmActivity)
                .where(
                    FarmActivity.source_type == "crop_harvest",
                    FarmActivity.source_record_id == events.ids["Crop"],
                    FarmActivity.activity_date == events.today,
                )
            )
            == 1
        )


def test_inactive_manual_recurrence_is_rejected_instead_of_silently_saved(events):
    assert (
        post_manual(events, manual(events, recurring_rule="Daily")).status_code == 422
    )
    assert create(events, payload(events, recurring_rule="Weekly")).status_code == 422


def test_both_entry_points_record_initial_assignment_and_require_review(events):
    task = post_manual(events, manual(events, requires_review=False))
    event = create(events, payload(events, requires_review=False))
    assert task.status_code == event.status_code == 201
    assert task.json()["requires_review"] and event.json()["requires_review"]
    with Session(events.engine) as db:
        for response in (task, event):
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TaskAssignmentHistory)
                    .where(TaskAssignmentHistory.activity_id == response.json()["id"])
                )
                == 1
            )


def test_both_entry_points_derive_the_linked_record_location(events):
    changes = dict(
        source_module="Crop",
        source_type="manual_work",
        source_record_id=events.ids["Crop"],
        location="Wrong warehouse",
    )
    task = post_manual(events, manual(events, **changes))
    event = create(events, payload(events, **changes))
    assert task.status_code == event.status_code == 201
    assert task.json()["location"] == event.json()["location"] == "Test field"


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "   "},
        {"end_time": "07:00"},
        {"priority": "Not a priority"},
        {"start_time": "25:99"},
    ],
)
def test_both_entry_points_validate_text_times_and_priority(events, changes):
    assert post_manual(events, manual(events, **changes)).status_code == 422
    assert create(events, payload(events, **changes)).status_code == 422


@pytest.mark.parametrize("via", ["calendar", "task"])
def test_expired_stock_is_rejected_at_creation(events, via):
    with Session(events.engine) as db:
        item = db.get(InventoryItem, events.stock["Fertilizer"])
        item.date_acquired = events.today - timedelta(days=20)
        item.expiration_date = events.today - timedelta(days=1)
        db.commit()
    changes = dict(
        name="Fertilize crop",
        category="Fertilization",
        source_module="Crop",
        source_type="manual_work",
        source_record_id=events.ids["Crop"],
        planned_inventory_item_id=events.stock["Fertilizer"],
        planned_quantity=2,
    )
    response = (
        create(events, payload(events, **changes))
        if via == "calendar"
        else post_manual(events, manual(events, **changes))
    )
    assert response.status_code == 422 and "expires" in response.text


def test_feeding_slot_is_explicit_and_duplicate_links_to_existing_occurrence(events):
    with Session(events.engine) as db:
        animal = db.get(Livestock, events.ids["Livestock"])
        animal.feed_inventory_item_id = events.stock["Livestock Feed"]
        animal.feed_times = "Morning and Evening"
        db.commit()
    changes = dict(
        name="Feed pigs",
        category="Livestock Feeding",
        source_module="Livestock",
        source_type="manual_work",
        source_record_id=events.ids["Livestock"],
        planned_inventory_item_id=events.stock["Livestock Feed"],
        planned_quantity=2,
    )
    assert create(events, payload(events, **changes)).status_code == 422
    first = create(events, payload(events, feeding_slot="Evening", **changes))
    assert first.status_code == 201, first.text
    duplicate = post_manual(events, manual(events, feeding_slot="Evening", **changes))
    assert duplicate.status_code == 409
    assert duplicate.headers["X-Existing-Task-Id"] == str(first.json()["id"])
    with Session(events.engine) as db:
        task_engine.evaluate_automatic_tasks(db)
        evening = db.scalars(
            select(FarmActivity).where(FarmActivity.source_key.like("%:evening"))
        ).all()
        assert len(evening) == 1 and evening[0].id == first.json()["id"]
        assert float(evening[0].planned_quantity) == 2


def test_task_create_command_and_assignment_are_atomic_on_failure(events, monkeypatch):
    from fastapi import HTTPException
    from app.services import idempotency

    original = idempotency.record_creation_command

    def fail(*args, **kwargs):
        raise HTTPException(503, "Temporary failure")

    with Session(events.engine) as db:
        before = db.scalar(select(func.count()).select_from(FarmActivity))
    monkeypatch.setattr(idempotency, "record_creation_command", fail)
    assert post_manual(events, manual(events)).status_code == 503
    with Session(events.engine) as db:
        assert db.scalar(select(func.count()).select_from(FarmActivity)) == before
    monkeypatch.setattr(idempotency, "record_creation_command", original)
    assert post_manual(events, manual(events)).status_code == 201


def test_unassigned_linked_harvest_keeps_its_operational_identity_when_assigned_later(
    events,
):
    response = create(
        events,
        payload(
            events,
            name="Harvest crop",
            category="Harvesting",
            assigned_employee_id=None,
            source_module="Crop",
            source_record_id=events.ids["Crop"],
            source_type="manual_work",
        ),
    )
    assert response.status_code == 201, response.text
    assert response.json()["source_type"] == "crop_harvest"
    assigned = events.client.put(
        f"/api/v1/workforce/tasks/{response.json()['id']}/assignment",
        json={"employee_id": events.employees["worker"]},
        headers=events.headers["manager"],
    )
    assert assigned.status_code == 200, assigned.text
    complete(
        events,
        assigned.json(),
        actual_quantity=10,
        actual_unit="kg",
        harvest_type_intent="Partial Harvest",
    )
    with Session(events.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropYieldRecord)) == 1


def test_legacy_generic_feeding_is_blocked_without_reinterpreting_its_history(events):
    response = create(events)
    assert response.status_code == 201
    with Session(events.engine) as db:
        task = db.get(FarmActivity, response.json()["id"])
        task.category = "Livestock Feeding"
        task.source_module = "Livestock"
        task.source_type = "manual_work"
        task.source_record_id = events.ids["Livestock"]
        task.planned_inventory_item_id = events.stock["Livestock Feed"]
        task.planned_usage_type = "Feed"
        db.commit()
    submitted = events.client.post(
        f"/api/v1/workforce/tasks/{response.json()['id']}/submit",
        json={"actual_quantity": 2, "actual_unit": "kg"},
        headers=events.headers["worker"],
    )
    assert submitted.status_code == 409 and "older calendar reminder" in submitted.text
    with Session(events.engine) as db:
        assert (
            float(db.get(InventoryItem, events.stock["Livestock Feed"]).quantity) == 20
        )
        assert db.get(FarmActivity, response.json()["id"]).source_type == "manual_work"


@pytest.mark.parametrize("schedule, expected", [("Morning and Evening", 10), ("4× daily", 5)])
def test_per_feeding_plan_uses_the_same_slots_as_the_native_schedule(schedule, expected):
    from types import SimpleNamespace
    task = SimpleNamespace(planned_quantity=None)
    livestock = SimpleNamespace(daily_feed_kg=2, quantity=10, feed_times=schedule)
    assert workforce_handlers._planned_feed(task, livestock) == expected
