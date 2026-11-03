"""Create/edit boundary and authoritative history checks for farm records."""
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm
from test_calendar_event_creation import events
from app.models import AuditLog, Crop, FarmCreationCommand, Livestock, LivestockGrowthRecord, User
from app.routers import livestock
from app.schemas.livestock import LivestockCreate, LivestockUpdate


def body(events, module):
    if module == "Crop":
        return dict(name="New crop", variety="Test variety", field="Field A", area_hectares=1,
                    planting_date=str(events.today), estimated_harvest=str(events.today + timedelta(days=90)),
                    quantity_planted=10, monitoring_enabled=False)
    return dict(record_name="New goat batch", animal_type="Goat", breed="Test breed", quantity=2,
                date_of_birth=str(events.today - timedelta(days=100)), weight_kg=10, pen_location="Pen A",
                date_acquired=str(events.today), monitoring_enabled=False)


def count(events, model):
    with Session(events.engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_livestock_metadata_update_writes_authenticated_before_after_audit(events):
    response = events.client.put(f"/api/v1/livestock/{events.ids['Livestock']}",
        json={"record_name": "Renamed batch", "acquired_from": "New supplier"}, headers=events.headers["manager"])
    assert response.status_code == 200, response.text
    with Session(events.engine) as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.module == "Livestock")).all()
        assert len(rows) == 2
        assert {row.event_type for row in rows} == {"audit", "timeline"}
        assert all(row.actor_user_id == events.users["manager"] for row in rows)
        changes = json.loads(rows[0].details)["changes"]
        assert changes["record_name"] == {"before": "Test group", "after": "Renamed batch"}
        assert changes["acquired_from"]["after"] == "New supplier"
    before = count(events, AuditLog)
    assert events.client.put(f"/api/v1/livestock/{events.ids['Livestock']}",
        json={"record_name": "Renamed batch"}, headers=events.headers["manager"]).status_code == 200
    assert count(events, AuditLog) == before


@pytest.mark.parametrize("module,field", [("Crop", "name"), ("Crop", "variety"), ("Crop", "field"),
    ("Livestock", "record_name"), ("Livestock", "animal_type"), ("Livestock", "breed"), ("Livestock", "pen_location")])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_required_record_text_is_validated_after_trim_before_any_write(events, module, field, operation):
    route = "crops" if module == "Crop" else "livestock"
    before = (count(events, Crop), count(events, Livestock), count(events, FarmCreationCommand), count(events, AuditLog))
    if operation == "create":
        response = events.client.post(f"/api/v1/{route}", json={**body(events, module), field: "   \t  "},
            headers={**events.headers["manager"], "Idempotency-Key": f"blank-{module}-{field}"})
    else:
        response = events.client.put(f"/api/v1/{route}/{events.ids[module]}",
            json={field: "   \t  ", "notes" if module == "Crop" else "health_notes": "Must not be saved"}, headers=events.headers["manager"])
    assert response.status_code == 422, response.text
    assert before == (count(events, Crop), count(events, Livestock), count(events, FarmCreationCommand), count(events, AuditLog))


def test_livestock_create_retry_writes_one_authoritative_audit_pair(events):
    headers = {**events.headers["manager"], "Idempotency-Key": "livestock-audited-create"}
    first = events.client.post("/api/v1/livestock", json=body(events, "Livestock"), headers=headers)
    assert first.status_code == 201, first.text
    second = events.client.post("/api/v1/livestock", json=body(events, "Livestock"), headers=headers)
    assert second.status_code == 201 and second.json()["id"] == first.json()["id"]
    with Session(events.engine) as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.module == "Livestock", AuditLog.entity_id == first.json()["animal_code"])).all()
        assert len(rows) == 2
        assert all(row.actor_user_id == events.users["manager"] for row in rows)


@pytest.mark.parametrize("operation", ["create", "update"])
def test_livestock_audit_failure_rolls_back_parent_growth_and_creation_command(events, operation):
    before = (count(events, Livestock), count(events, LivestockGrowthRecord), count(events, FarmCreationCommand))
    with Session(events.engine) as db:
        actor = db.get(User, events.users["manager"])
        with patch.object(livestock, "record_livestock_change", side_effect=RuntimeError("Synthetic audit failure")):
            with pytest.raises(RuntimeError):
                if operation == "create":
                    livestock.create_livestock(LivestockCreate(**body(events, "Livestock")), db=db, current_user=actor, idempotency_key="livestock-failed-audit")
                else:
                    livestock.update_livestock(events.ids["Livestock"], LivestockUpdate(record_name="Unsaved batch", weight_kg=21), db=db, current_user=actor)
        assert db.get(Livestock, events.ids["Livestock"]).record_name == "Test group"
    assert before == (count(events, Livestock), count(events, LivestockGrowthRecord), count(events, FarmCreationCommand))


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_record_names_and_locations_are_trimmed_and_retained(events, module):
    value = body(events, module)
    fields = ["name", "variety", "field"] if module == "Crop" else ["record_name", "breed", "pen_location"]
    for field in fields:
        value[field] = f"  {value[field]}  "
    route = "crops" if module == "Crop" else "livestock"
    response = events.client.post(f"/api/v1/{route}", json=value, headers=events.headers["manager"])
    assert response.status_code == 201, response.text
    assert all(response.json()[field] == value[field].strip() for field in fields)


def estimated_age(events):
    return dict(estimated_age_days=100, estimated_age_as_of_date=str(events.today),
                estimated_age_confidence="Medium", estimated_age_source="Supplier's age estimate")


def test_unknown_birth_livestock_can_be_edited_with_its_existing_age_provenance(events):
    value = {**body(events, "Livestock"), "date_of_birth": None, **estimated_age(events)}
    created = events.client.post("/api/v1/livestock", json=value, headers=events.headers["manager"])
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    saved = events.client.put(f"/api/v1/livestock/{record_id}",
        json={"record_name": "Updated estimated-age batch", "date_of_birth": None, **estimated_age(events)},
        headers=events.headers["manager"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["date_of_birth"] is None and saved.json()["age_is_estimated"] is True
    assert saved.json()["estimated_age_source"] == "Supplier's age estimate"
    # A later documented birth date can replace the estimate.
    known = events.client.put(f"/api/v1/livestock/{record_id}",
        json={"date_of_birth": str(events.today - timedelta(days=100)), "estimated_age_days": None,
              "estimated_age_as_of_date": None, "estimated_age_confidence": None, "estimated_age_source": None},
        headers=events.headers["manager"])
    assert known.status_code == 200, known.text
    assert known.json()["age_is_estimated"] is False


@pytest.mark.parametrize("missing", ["estimated_age_days", "estimated_age_as_of_date", "estimated_age_confidence", "estimated_age_source"])
def test_clearing_known_birth_still_requires_complete_age_provenance(events, missing):
    value = {"date_of_birth": None, **estimated_age(events), missing: None, "record_name": "Must not be saved"}
    response = events.client.put(f"/api/v1/livestock/{events.ids['Livestock']}", json=value, headers=events.headers["manager"])
    assert response.status_code == 400, response.text
    with Session(events.engine) as db:
        record = db.get(Livestock, events.ids["Livestock"])
        assert record.date_of_birth is not None and record.record_name == "Test group"
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
