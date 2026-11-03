"""Dashboard event creation uses real employee tasks and approval-only stock posting."""

from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm  # Shared isolated SQLite/HTTP fixture.
from app.models import (
    Employee,
    EmployeeWorkSchedule,
    EmployeeWorkScheduleDay,
    FarmActivity,
    FarmCreationCommand,
    InventoryItem,
    InventoryStockRecord,
    LivestockPen,
    ResourceUsage,
    Role,
    TaskAssignmentHistory,
    User,
)
from app.routers import activities, farm_locations, inventory


@pytest.fixture
def events(farm):
    for router in (activities.router, farm_locations.router, inventory.router):
        farm.client.app.include_router(router)
    with Session(farm.engine) as db:
        for key in ("worker", "other"):
            db.get(User, farm.users[key]).role.set_permissions(
                ["workforce:submit", "activities:view"]
            )
        items = [
            InventoryItem(
                item_code=f"EVENT-{category}",
                name=f"Test {category}",
                category=category,
                quantity=20,
                unit=unit,
                supplier="Test supplier",
                date_acquired=farm.today,
                location="Storage A",
            )
            for category, unit in (
                ("Livestock Feed", "kg"),
                ("Vaccine", "doses"),
                ("Fertilizer", "kg"),
            )
        ]
        db.add_all(items)
        db.add_all(
            [
                LivestockPen(name="Pen A", status="Active"),
                LivestockPen(name="Hidden pen", status="Active", is_archived=True),
                LivestockPen(name="Closed pen", status="Inactive"),
            ]
        )
        db.flush()
        farm.stock = {item.category: item.id for item in items}
        db.commit()
    return farm


def payload(events, **changes):
    value = {
        "name": "Inspect fences",
        "category": "Farm Inspection",
        "related_to": "Joross Farm",
        "location": "Field A",
        "activity_date": str(events.today),
        "start_time": "08:00",
        "end_time": "09:00",
        "assigned_by": "Untrusted actor name",
        "assigned_to": "Wrong person",
        "assigned_employee_id": events.employees["worker"],
        "status": "Pending",
        "requires_review": False,
        "requires_evidence": True,
    }
    value.update(changes)
    return value


def create(events, value=None, key="calendar-event-1", actor="manager"):
    return events.client.post(
        "/api/v1/activities",
        json=value or payload(events),
        headers={**events.headers[actor], "Idempotency-Key": key},
    )


def count(events, model):
    with Session(events.engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_real_identity_task_visibility_and_exact_create_retry(events):
    before = count(events, FarmActivity)
    first = create(events)
    assert first.status_code == 201, first.text
    event = first.json()
    assert event["assigned_employee_id"] == events.employees["worker"]
    assert event["assigned_to"] == "Monitoring worker"
    assert event["assigned_by"] == "Monitoring manager"
    assert event["requires_review"] is True
    assert event["requires_employee_submission"] is True
    assert event["can_complete_directly"] is False
    assert create(events).json()["id"] == event["id"]
    assert count(events, FarmActivity) == before + 1
    assert count(events, FarmCreationCommand) == 1
    with Session(events.engine) as db:
        history = db.scalars(
            select(TaskAssignmentHistory).where(
                TaskAssignmentHistory.activity_id == event["id"]
            )
        ).all()
        assert len(history) == 1
        assert history[0].new_employee_id == events.employees["worker"]
    for actor, visible in (("worker", True), ("other", False)):
        response = events.client.get(
            "/api/v1/workforce/my-tasks", headers=events.headers[actor]
        )
        assert response.status_code == 200, response.text
        assert (event["id"] in [row["id"] for row in response.json()]) is visible
    assert events.client.get(
        f"/api/v1/activities/{event['id']}", headers=events.headers["other"]
    ).status_code in {403, 404}
    assert create(events, payload(events, location="Another field")).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "Completed"},
        {"status": "Submitted for Review"},
        {"name": "  "},
        {"end_time": "08:00"},
        {"end_time": "07:00"},
        {"assigned_employee_id": 99999},
    ],
)
def test_invalid_create_cannot_leave_partial_task_or_command(events, changes):
    before = count(events, FarmActivity)
    assert create(events, payload(events, **changes)).status_code in {404, 422}
    assert count(events, FarmActivity) == before
    assert count(events, FarmCreationCommand) == 0


@pytest.mark.parametrize(
    "state", ["archived", "inactive", "no_login", "disabled_login"]
)
def test_unassignable_employee_is_rejected(events, state):
    with Session(events.engine) as db:
        employee = db.get(Employee, events.employees["worker"])
        if state == "archived":
            employee.is_archived = True
        if state == "inactive":
            employee.employment_status = "Inactive"
        if state == "no_login":
            employee.login_user_id = None
        if state == "disabled_login":
            db.get(User, events.users["worker"]).status = "Inactive"
        db.commit()
    before = count(events, FarmActivity)
    assert create(events).status_code in {400, 404, 409}
    assert count(events, FarmActivity) == before


def test_creator_permission_does_not_grant_employee_assignment(events):
    with Session(events.engine) as db:
        db.get(User, events.users["other"]).role.set_permissions(
            ["activities:view", "activities:create"]
        )
        db.commit()
    assert create(events, actor="other").status_code == 403
    standalone = create(
        events,
        payload(
            events,
            assigned_employee_id=None,
            assigned_to="Unassigned",
            requires_review=False,
        ),
        actor="other",
    )
    assert standalone.status_code == 201, standalone.text
    assert standalone.json()["requires_employee_submission"] is False
    assert (
        events.client.get(
            "/api/v1/activities/event-resources", headers=events.headers["other"]
        ).status_code
        == 403
    )


def test_rest_day_cannot_receive_calendar_assignment_without_schedule_review(events):
    with Session(events.engine) as db:
        schedule = EmployeeWorkSchedule(
            employee_id=events.employees["worker"],
            effective_from=events.today,
            timezone="Asia/Manila",
            schedule_type="Fixed",
            status="Active",
        )
        db.add(schedule)
        db.flush()
        for day in range(7):
            db.add(
                EmployeeWorkScheduleDay(
                    schedule_id=schedule.id, day_of_week=day, is_working_day=False
                )
            )
        db.commit()
    before = count(events, FarmActivity)
    response = create(events)
    assert response.status_code == 409, response.text
    assert "unavailable" in response.json()["detail"]
    assert count(events, FarmActivity) == before


def test_failure_after_flush_rolls_back_and_can_be_retried(events):
    before = count(events, FarmActivity)
    with patch(
        "app.routers.activities.record_creation_command",
        side_effect=HTTPException(503, "Temporary failure"),
    ):
        assert create(events).status_code == 503
    assert count(events, FarmActivity) == before
    assert count(events, FarmCreationCommand) == 0
    assert create(events).status_code == 201


def test_legacy_activity_edit_cannot_remove_or_replace_task_assignment(events):
    task_id = create(events).json()["id"]
    for changes in (
        {"assigned_employee_id": None, "requires_review": False},
        {"assigned_employee_id": events.employees["other"]},
    ):
        response = events.client.put(
            f"/api/v1/activities/{task_id}",
            json=changes,
            headers=events.headers["manager"],
        )
        assert response.status_code == 400
    with Session(events.engine) as db:
        task = db.get(FarmActivity, task_id)
        assert task.assigned_employee_id == events.employees["worker"]
        assert task.requires_review is True


@pytest.mark.parametrize(
    "category,module,stock",
    [
        ("Livestock Feeding", "Livestock", "Livestock Feed"),
        ("Vaccination", "Livestock", "Vaccine"),
        ("Fertilization", "Crop", "Fertilizer"),
    ],
)
def test_assigned_resource_event_reaches_approval_and_posts_stock_once(
    events, category, module, stock
):
    value = payload(
        events,
        name=category,
        category=category,
        source_module=module,
        source_record_id=events.ids[module],
        planned_inventory_item_id=events.stock[stock],
        planned_quantity=3,
    )
    unlinked = {**value, "planned_inventory_item_id": None}
    assert create(events, unlinked, key="unlinked").status_code == 422
    response = create(events, value)
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    with Session(events.engine) as db:
        assert float(db.get(InventoryItem, events.stock[stock]).quantity) == 20
    direct = events.client.put(
        f"/api/v1/activities/{task_id}",
        json={"status": "Completed"},
        headers=events.headers["manager"],
    )
    assert direct.status_code == 400
    data = BytesIO()
    Image.new("RGB", (100, 100), "green").save(data, format="PNG")
    photo = events.client.post(
        f"/api/v1/workforce/tasks/{task_id}/evidence",
        files={"file": ("work.png", data.getvalue(), "image/png")},
        headers=events.headers["worker"],
    )
    assert photo.status_code == 201, photo.text
    submit_body = {
        "actual_quantity": 2,
        "actual_unit": "doses" if stock == "Vaccine" else "kg",
        "evidence_url": photo.json()["evidence_url"],
        "worker_notes": "Completed inspected work",
    }
    submitted = events.client.post(
        f"/api/v1/workforce/tasks/{task_id}/submit",
        json=submit_body,
        headers=events.headers["worker"],
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "Submitted for Review"
    with Session(events.engine) as db:
        assert float(db.get(InventoryItem, events.stock[stock]).quantity) == 20
    approved = events.client.post(
        f"/api/v1/workforce/tasks/{task_id}/review",
        json={"decision": "Approve"},
        headers=events.headers["manager"],
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Completed"
    assert (
        events.client.post(
            f"/api/v1/workforce/tasks/{task_id}/review",
            json={"decision": "Approve"},
            headers=events.headers["manager"],
        ).status_code
        == 409
    )
    with Session(events.engine) as db:
        assert float(db.get(InventoryItem, events.stock[stock]).quantity) == 18
        assert (
            db.scalar(
                select(func.count())
                .select_from(ResourceUsage)
                .where(ResourceUsage.activity_id == task_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(InventoryStockRecord)
                .where(InventoryStockRecord.inventory_item_id == events.stock[stock])
            )
            == 1
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"planned_quantity": 21},
        {"planned_quantity": 0},
        {"source_record_id": 99999},
        {"planned_inventory_item_id": 99999},
    ],
)
def test_resource_validation_leaves_stock_and_activity_untouched(events, changes):
    value = payload(
        events,
        name="Feeding",
        category="Livestock Feeding",
        source_module="Livestock",
        source_record_id=events.ids["Livestock"],
        planned_inventory_item_id=events.stock["Livestock Feed"],
        planned_quantity=2,
    )
    value.update(changes)
    before = count(events, FarmActivity)
    assert create(events, value).status_code == 422
    assert count(events, FarmActivity) == before
    assert count(events, InventoryStockRecord) == 0


def test_incompatible_or_archived_stock_cannot_be_linked_to_an_event(events):
    value = payload(
        events,
        name="Vaccination",
        category="Vaccination",
        source_module="Livestock",
        source_record_id=events.ids["Livestock"],
        planned_inventory_item_id=events.stock["Livestock Feed"],
        planned_quantity=2,
    )
    assert create(events, value).status_code == 400
    with Session(events.engine) as db:
        db.get(InventoryItem, events.stock["Vaccine"]).is_archived = True
        db.commit()
    value["planned_inventory_item_id"] = events.stock["Vaccine"]
    assert create(events, value).status_code == 422
    choices = events.client.get(
        "/api/v1/activities/event-resources", headers=events.headers["manager"]
    )
    assert choices.status_code == 200
    assert events.stock["Vaccine"] not in [
        item["id"] for item in choices.json()["inventory"]
    ]


def test_location_scopes_custom_persistence_and_permissions(events):
    headers = events.headers["manager"]

    def choices(context):
        response = events.client.get(
            "/api/v1/farm-locations", params={"context": context}, headers=headers
        )
        assert response.status_code == 200, response.text
        return response.json()["items"]

    assert choices("crops") == ["Test field"]
    assert choices("inventory") == ["Storage A"]
    combined = choices("events")
    assert "Pen A" in combined and "Test farm" in combined
    assert "Hidden pen" not in combined and "Closed pen" not in combined
    crop = events.client.put(
        f"/api/v1/crops/{events.ids['Crop']}",
        json={"field": "Custom hillside"},
        headers=headers,
    )
    assert crop.status_code == 200, crop.text
    assert "Custom hillside" in choices("crops")
    item = events.client.post(
        "/api/v1/inventory",
        json={
            "name": "Test tools",
            "category": "Equipment",
            "unit": "pieces",
            "quantity": 1,
            "supplier": "Test supplier",
            "date_acquired": str(events.today),
            "location": "Custom shed",
        },
        headers=headers,
    )
    assert item.status_code == 201, item.text
    assert "Custom shed" in choices("inventory")
    assert "Custom shed" in choices("events")
    assert (
        events.client.get(
            "/api/v1/farm-locations?context=inventory", headers=events.headers["worker"]
        ).status_code
        == 403
    )
    assert (
        events.client.get(
            "/api/v1/farm-locations?context=unknown", headers=headers
        ).status_code
        == 422
    )


def test_archived_and_duplicate_location_names_are_not_suggestions(events):
    with Session(events.engine) as db:
        items = db.scalars(select(InventoryItem).order_by(InventoryItem.id)).all()
        items[0].location, items[1].location = "  Storage   A ", "storage a"
        items[2].location, items[2].is_archived = "Hidden store", True
        db.commit()
    response = events.client.get(
        "/api/v1/farm-locations?context=inventory", headers=events.headers["manager"]
    )
    assert response.json()["items"] == ["Storage A"]
