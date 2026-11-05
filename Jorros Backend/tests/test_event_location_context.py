"""Contextual event record choices, location fallbacks and non-consuming plans."""

from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from test_resource_monitoring import farm
from test_calendar_event_creation import events, create, payload
from app.models import InventoryItem, InventoryStockRecord, ResourceUsage, User


def locations(events, context="events", **params):
    response = events.client.get(
        "/api/v1/farm-locations",
        params={"context": context, **params},
        headers=events.headers["manager"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_crop_and_inventory_names_never_mix(events):
    assert locations(events, "crops")["items"] == ["Test field"]
    assert locations(events, "inventory")["items"] == ["Storage A"]


@pytest.mark.parametrize(
    "event_type,domain,expected",
    [
        ("Fertilization", "Crop", ["Test field"]),
        ("Irrigation", "Crop", ["Test field"]),
        ("Vaccination", "Livestock", ["Pen A", "Test pen"]),
        ("Livestock Feeding", "Livestock", ["Pen A", "Test pen"]),
        ("Inventory Restocking", "Inventory", ["Storage A"]),
    ],
)
def test_event_locations_follow_selected_type(events, event_type, domain, expected):
    response = locations(events, event_type=event_type)
    assert response["domain"] == domain
    assert response["items"] == expected


def test_selected_livestock_limits_locations_to_its_own_pen(events):
    assert locations(
        events,
        event_type="Vaccination",
        source_module="Livestock",
        source_record_id=events.ids["Livestock"],
    )["items"] == ["Test pen"]


def test_legacy_equipment_locations_remain_readable_but_new_work_is_unsupported(events):
    with Session(events.engine) as db:
        item = InventoryItem(
            item_code="EVENT-TOOL",
            name="Feed dispenser",
            category="Equipment",
            quantity=1,
            unit="pieces",
            supplier="Test supplier",
            date_acquired=events.today,
            location="Equipment shed",
        )
        db.add(item)
        db.commit()
        item_id = item.id
    assert locations(events, event_type="Equipment Maintenance")["items"] == [
        "Equipment shed"
    ]
    result = create(
        events,
        payload(
            events,
            name="Maintain feed dispenser",
            category="Equipment Maintenance",
            source_module="Inventory",
            source_record_id=item_id,
            location="Fake field",
        ),
    )
    assert result.status_code == 422, result.text
    assert "not a supported farm activity" in result.text


@pytest.mark.parametrize(
    "changes",
    [
        {"source_module": "Crop"},
        {"source_record_id": None},
        {"source_record_id": 999999},
        {"planned_inventory_item_id": 1},
    ],
)
def test_invalid_restock_plan_cannot_link_a_crop_or_consume_inventory(events, changes):
    value = payload(
        events,
        name="Restock grower feed",
        category="Inventory Restocking",
        source_module="Inventory",
        source_record_id=events.stock["Livestock Feed"],
    )
    value.update(changes)
    assert create(events, value).status_code == 422
    with Session(events.engine) as db:
        assert (
            float(db.get(InventoryItem, events.stock["Livestock Feed"]).quantity) == 20
        )


def test_restock_plan_uses_actual_item_and_warehouse_and_approval_never_changes_stock(
    events,
):
    result = create(
        events,
        payload(
            events,
            name="Restock grower feed",
            category="Inventory Restocking",
            source_module="Inventory",
            source_record_id=events.stock["Livestock Feed"],
            location="Field A",
            related_to="Untrusted item",
            source_type="manual_work",
        ),
    )
    assert result.status_code == 201, result.text
    saved = result.json()
    assert saved["location"] == "Storage A"
    assert saved["related_to"] == "Test Livestock Feed"
    assert saved["source_type"] == "inventory_restock_plan"
    task_id = saved["id"]
    tasks = events.client.get(
        "/api/v1/workforce/my-tasks", headers=events.headers["worker"]
    ).json()
    task = next(row for row in tasks if row["id"] == task_id)
    assert task["resource_required"] is False
    photo = BytesIO()
    Image.new("RGB", (100, 100), "green").save(photo, format="PNG")
    uploaded = events.client.post(
        f"/api/v1/workforce/tasks/{task_id}/evidence",
        files={"file": ("delivery.png", photo.getvalue(), "image/png")},
        headers=events.headers["worker"],
    )
    assert uploaded.status_code == 201
    submitted = events.client.post(
        f"/api/v1/workforce/tasks/{task_id}/submit",
        json={
            "evidence_url": uploaded.json()["evidence_url"],
            "worker_notes": "Delivery inspected. Stock entry will be recorded in Inventory.",
        },
        headers=events.headers["worker"],
    )
    assert submitted.status_code == 200, submitted.text
    approved = events.client.post(
        f"/api/v1/workforce/tasks/{task_id}/review",
        json={"decision": "Approve"},
        headers=events.headers["manager"],
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Completed"
    with Session(events.engine) as db:
        assert (
            float(db.get(InventoryItem, events.stock["Livestock Feed"]).quantity) == 20
        )
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord)) == 0
        assert db.scalar(select(func.count()).select_from(ResourceUsage)) == 0


def test_event_records_obey_view_permissions_without_requiring_assignment_permission(
    events,
):
    with Session(events.engine) as db:
        db.get(User, events.users["other"]).role.set_permissions(
            ["activities:view", "inventory:view"]
        )
        db.commit()
    response = events.client.get(
        "/api/v1/activities/event-resources", headers=events.headers["other"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["crops"] == response.json()["livestock"] == []
    assert response.json()["inventory"][0]["location"] == "Storage A"


def test_legacy_inventory_without_warehouse_cannot_create_a_mislocated_restock(events):
    with Session(events.engine) as db:
        db.get(InventoryItem, events.stock["Livestock Feed"]).location = "   "
        db.commit()
    result = create(
        events,
        payload(
            events,
            name="Restock feed",
            category="Inventory Restocking",
            source_module="Inventory",
            source_record_id=events.stock["Livestock Feed"],
            location="Field A",
        ),
    )
    assert result.status_code == 422
    assert "warehouse" in result.json()["detail"]


def test_launcher_detects_a_backend_without_contextual_location_parameters():
    from scripts.check_event_planning_api import missing_features

    params = [
        {"name": name, "in": "query"}
        for name in ["context", "event_type", "source_module", "source_record_id"]
    ]
    schema = {
        "paths": {
            "/api/v1/farm-locations": {"get": {"parameters": params}},
            "/api/v1/activities/event-resources": {"get": {}},
        }
    }
    assert missing_features(schema) == []
    schema["paths"]["/api/v1/farm-locations"]["get"]["parameters"] = params[:1]
    assert "location query parameter: event_type" in missing_features(schema)
    schema["paths"].pop("/api/v1/activities/event-resources")
    assert "GET /api/v1/activities/event-resources" in missing_features(schema)


@pytest.mark.parametrize(
    "category,module,expected",
    [
        ("Fertilization", "Crop", "Test field"),
        ("Livestock Health Check", "Livestock", "Test pen"),
    ],
)
def test_linked_event_uses_the_record_location_instead_of_an_unrelated_warehouse(
    events, category, module, expected
):
    result = create(
        events,
        payload(
            events,
            name="Planned work",
            category=category,
            assigned_employee_id=None,
            requires_review=False,
            source_module=module,
            source_record_id=events.ids[module],
            location="Wrong warehouse",
        ),
    )
    assert result.status_code == 201, result.text
    assert result.json()["location"] == expected
