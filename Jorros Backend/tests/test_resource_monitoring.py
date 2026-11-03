"""Real HTTP approval, history and scheduler regression coverage."""
import os
from datetime import timedelta, time
from io import BytesIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.farm_time import farm_today
from app.core.security import create_access_token
from app.models import (Crop, CropGrowthRecord, Livestock, LivestockGrowthRecord, Employee,
                        FarmActivity, Role, User, TaskSubmission, InventoryStockRecord)
from app.models.alert import AlertSettings
from app.routers import workforce, crops, livestock
from app.services.task_engine import evaluate_automatic_tasks
from app.services.crop_growth import calculate_crop_progress


@pytest.fixture
def farm():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    today = farm_today()
    with Session(engine, expire_on_commit=False) as db:
        tokens, users, employees = {}, {}, {}
        for name, permissions in [("worker", ["workforce:submit"]), ("other", ["workforce:submit"]),
                                  ("manager", ["*"]), ("reviewer", ["workforce:review"])]:
            role = Role(name=f"Monitoring {name}", is_active=True)
            role.set_permissions(permissions)
            user = User(user_code=f"MON-{name}", username=f"monitoring.{name}", full_name=f"Monitoring {name}",
                        password_hash="test-only", status="Active", role=role)
            db.add(user); db.flush()
            employee = Employee(employee_code=f"MON-{name}", full_name=user.full_name,
                                login_user_id=user.id, employment_status="Active", is_archived=False)
            db.add(employee); db.flush()
            tokens[name] = {"Authorization": f"Bearer {create_access_token(user.id)[0]}"}
            users[name], employees[name] = user.id, employee.id
        crop = Crop(crop_code="MON-CROP", name="Test crop", variety="Test variety", field="Test field",
                    area_hectares=1, planting_date=today-timedelta(days=30), estimated_harvest=today+timedelta(days=30),
                    quantity_planted=100, current_surviving=100, current_growth=50, growth_stage="Vegetative", status="Growing",
                    assigned_employee_id=employees["worker"], monitoring_enabled=True,
                    monitoring_start_date=today, monitoring_end_date=today+timedelta(days=30))
        animal = Livestock(animal_code="MON-ANIMAL", record_name="Test group", animal_type="Pig", breed="Test breed",
                           quantity=10, weight_kg=20, min_weight_kg=18, max_weight_kg=22, pen_location="Test pen",
                           date_of_birth=today-timedelta(days=90), date_acquired=today-timedelta(days=30),
                           health_status="Healthy", healthy_quantity=10, growth_status="Growing", daily_feed_kg=0,
                           lifecycle_status="Active", last_checkup=today, assigned_employee_id=employees["worker"],
                           monitoring_enabled=True, monitoring_start_date=today, monitoring_frequency_days=2)
        db.add_all([crop, animal, AlertSettings(crop_growth_check_frequency=3)]); db.flush()
        task_ids = {}
        for module, resource in [("Crop", crop), ("Livestock", animal)]:
            task = FarmActivity(activity_code=f"MON-TASK-{module}", name=f"Monitor {module}", category="Farm Inspection",
                                related_to="Test resource", location="Test farm", activity_date=today, start_time=time(8),
                                assigned_by="System", assigned_to="Monitoring worker", assigned_employee_id=employees["worker"],
                                default_employee_id=employees["worker"], assignment_source="automatic_default",
                                status="In Progress", priority="Medium", requires_review=True, requires_evidence=True,
                                source_module=module, source_type=f"{module.lower()}_growth_check", source_record_id=resource.id,
                                is_automatic=True, source_key=f"{module.lower()}:growth-check:{resource.id}:{today.isoformat()}")
            db.add(task); db.flush(); task_ids[module] = task.id
        db.commit()
        ids = {"Crop": crop.id, "Livestock": animal.id}
    app = FastAPI()
    app.include_router(workforce.router); app.include_router(crops.router); app.include_router(livestock.router)

    def test_db():
        with Session(engine, expire_on_commit=False, autoflush=False) as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    old_dir = settings.workforce_evidence_local_dir
    with TemporaryDirectory() as directory:
        settings.workforce_evidence_local_dir = directory
        try:
            with TestClient(app) as client:
                yield SimpleNamespace(engine=engine, client=client, headers=tokens, users=users,
                                      employees=employees, ids=ids, tasks=task_ids, today=today)
        finally:
            settings.workforce_evidence_local_dir = old_dir
    engine.dispose()


def photo(farm, module):
    data = BytesIO(); Image.new("RGB", (100, 100), "green").save(data, format="PNG")
    response = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks[module]}/evidence",
                               files={"file": ("inspection.png", data.getvalue(), "image/png")}, headers=farm.headers["worker"])
    assert response.status_code == 201, response.text
    return response.json()["evidence_url"]


def observation(farm, module, **changes):
    value = {"resource_type": module, "observation_date": str(farm.today)}
    value.update({"observed_stage": "Flowering", "current_surviving": 93} if module == "Crop" else
                 {"animals_measured": 4, "average_weight_kg": 30, "total_measured_weight_kg": 120,
                  "min_weight_kg": 25, "max_weight_kg": 35, "observed_stage": "Mature"})
    value.update(changes)
    return value


def submit(farm, module, **changes):
    payload = {"monitoring": observation(farm, module), "evidence_url": photo(farm, module), "worker_notes": "Field inspection"}
    payload.update(changes)
    response = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks[module]}/submit", json=payload,
                               headers={**farm.headers["worker"], "Idempotency-Key": f"monitoring-{module}-attempt"})
    return response, payload


def review(farm, module, role="manager", **changes):
    return farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks[module]}/review",
                           json={"decision": "Approve", **changes}, headers=farm.headers[role])


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_pending_then_approval_posts_once_without_inventory(farm, module):
    response, payload = submit(farm, module)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Submitted for Review"
    model = CropGrowthRecord if module == "Crop" else LivestockGrowthRecord
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(model)) == 0
    # Exact retry returns the existing attempt and cannot duplicate work.
    retry = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks[module]}/submit", json=payload,
                            headers={**farm.headers["worker"], "Idempotency-Key": f"monitoring-{module}-attempt"})
    assert retry.status_code == 200
    assert review(farm, module).status_code == 200
    assert review(farm, module).status_code == 409
    with Session(farm.engine) as db:
        rows = db.scalars(select(model)).all()
        assert len(rows) == 1
        assert rows[0].related_task_id == farm.tasks[module]
        assert rows[0].approved_by_user_id == farm.users["manager"]
        assert db.scalar(select(func.count()).select_from(TaskSubmission)) == 1
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord)) == 0
        if module == "Crop":
            crop = db.get(Crop, farm.ids[module])
            assert crop.current_surviving == 93
            assert crop.observed_growth_stage == "Flowering"
            crops.apply_automatic_progress(crop)
            assert crop.growth_stage == "Flowering"
            assert crop.estimated_progress == 50
        else:
            animal = db.get(Livestock, farm.ids[module])
            assert float(animal.weight_kg) == 30
            assert float(animal.min_weight_kg) == 25
            assert float(animal.max_weight_kg) == 35
            assert animal.growth_status == "Growing"  # Proposal alone does not change it.


@pytest.mark.parametrize("decision,expected_status", [("Return", 200), ("Void", 400)])
def test_unapproved_work_never_changes_crop_records(farm, decision, expected_status):
    assert submit(farm, "Crop")[0].status_code == 200
    response = review(farm, "Crop", decision=decision, feedback="Please verify the count")
    assert response.status_code == expected_status
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropGrowthRecord)) == 0
        assert db.get(Crop, farm.ids["Crop"]).current_surviving == 100


def test_early_harvest_readiness_requires_explicit_confirmation(farm):
    assert submit(farm, "Crop", monitoring=observation(farm, "Crop", observed_stage="Harvest Ready"))[0].status_code == 200
    assert review(farm, "Crop").status_code == 400
    assert review(farm, "Crop", confirm_harvest_ready=True).status_code == 200
    with Session(farm.engine) as db:
        crop = db.get(Crop, farm.ids["Crop"])
        assert crop.status == "Ready for Harvest" and crop.confirmed_ready_at is not None
        assert crop.estimated_progress == 50
        assert float(crop.current_growth) == 100  # Compatibility; estimate remains separate.


def test_stage_override_is_explicit_authorized_and_audited(farm):
    assert submit(farm, "Livestock")[0].status_code == 200
    assert review(farm, "Livestock", role="reviewer", confirmed_growth_stage="Mature", feedback="Observed stage confirmed").status_code == 403
    assert review(farm, "Livestock", confirmed_growth_stage="Mature").status_code == 400
    assert review(farm, "Livestock", confirmed_growth_stage="Mature", feedback="Observed stage confirmed").status_code == 200
    from app.models import LivestockGrowthStageOverrideAudit
    with Session(farm.engine) as db:
        assert db.get(Livestock, farm.ids["Livestock"]).growth_status == "Mature"
        audit = db.scalar(select(LivestockGrowthStageOverrideAudit))
        assert audit.previous_stage == "Growing" and audit.override_stage == "Mature"


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_authentication_ownership_and_evidence_are_enforced(farm, module):
    url = f"/api/v1/workforce/tasks/{farm.tasks[module]}/submit"
    value = {"monitoring": observation(farm, module)}
    assert farm.client.post(url, json=value).status_code == 401
    assert farm.client.post(url, json=value, headers=farm.headers["other"]).status_code == 404
    assert farm.client.post(url, json=value, headers=farm.headers["worker"]).status_code == 400
    assert farm.client.post(url, json={"evidence_url": photo(farm, module)}, headers=farm.headers["worker"]).status_code == 400


def test_failed_approval_rolls_back_observation_and_resource_changes(farm):
    assert submit(farm, "Crop")[0].status_code == 200
    with patch("app.routers.workforce_handlers._post_submission_inventory_on_approval", side_effect=RuntimeError("test failure")):
        with pytest.raises(RuntimeError):
            review(farm, "Crop")
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropGrowthRecord)) == 0
        assert db.get(Crop, farm.ids["Crop"]).current_surviving == 100
        assert db.get(FarmActivity, farm.tasks["Crop"]).status == "Submitted for Review"
    assert review(farm, "Crop").status_code == 200


def test_backdated_crop_inspection_preserves_latest_counts_and_uses_its_own_date(farm):
    latest_date = farm.today-timedelta(days=2)
    with Session(farm.engine) as db:
        crop = db.get(Crop, farm.ids["Crop"])
        crop.current_surviving, crop.observed_growth_stage, crop.last_observation_date = 95, "Fruiting", latest_date
        db.add(CropGrowthRecord(crop_id=crop.id, update_date=latest_date, growth_percentage=45, growth_stage="Vegetative", observed_stage="Fruiting", current_surviving=95, status="Growing"))
        db.commit()
    older = farm.today-timedelta(days=10)
    response = farm.client.post(f"/api/v1/crops/{farm.ids['Crop']}/growth-records",
                               json={"update_date": str(older), "current_surviving": 80, "observed_stage": "Flowering"}, headers=farm.headers["manager"])
    assert response.status_code == 201, response.text
    assert response.json()["growth_percentage"] == calculate_crop_progress(farm.today-timedelta(days=30), farm.today+timedelta(days=30), today=older)
    with Session(farm.engine) as db:
        crop = db.get(Crop, farm.ids["Crop"])
        assert crop.current_surviving == 95 and crop.observed_growth_stage == "Fruiting"


def test_backdated_livestock_preserves_latest_average_minimum_maximum_and_recalculates_gain(farm):
    url = f"/api/v1/livestock/{farm.ids['Livestock']}/growth-records"
    values = [(-1, 30, 25, 35), (-10, 20, 15, 25)]
    for days, average, low, high in values:
        payload = {"measurement_date": str(farm.today+timedelta(days=days)), "weight_kg": average,
                   "animals_measured": 4, "min_weight_kg": low, "max_weight_kg": high}
        response = farm.client.post(url, json=payload, headers=farm.headers["manager"])
        assert response.status_code == 201, response.text
    assert farm.client.post(url, json=payload, headers=farm.headers["manager"]).status_code == 409
    with Session(farm.engine) as db:
        animal = db.get(Livestock, farm.ids["Livestock"])
        assert (float(animal.weight_kg), float(animal.min_weight_kg), float(animal.max_weight_kg)) == (30, 25, 35)
        last = db.scalar(select(LivestockGrowthRecord).order_by(LivestockGrowthRecord.measurement_date.desc()))
        assert float(last.weight_change_kg) == 10 and last.days_since_previous == 9


def test_scheduling_honors_settings_retries_and_future_reassignment(farm):
    with Session(farm.engine, expire_on_commit=False) as db:
        evaluate_automatic_tasks(db)
        before = list(db.scalars(select(FarmActivity).where(FarmActivity.source_type.in_(["crop_growth_check", "livestock_growth_check"]))).all())
        ids = {task.id for task in before}
        crop_dates = {task.activity_date for task in before if task.source_module == "Crop"}
        assert crop_dates == {farm.today+timedelta(days=day) for day in [0, 3, 6]}
        evaluate_automatic_tasks(db)
        assert {task.id for task in db.scalars(select(FarmActivity).where(FarmActivity.source_type.in_(["crop_growth_check", "livestock_growth_check"]))).all()} == ids
        animal = db.get(Livestock, farm.ids["Livestock"])
        animal.assigned_employee_id = farm.employees["other"]
        evaluate_automatic_tasks(db)
        for task in before:
            db.refresh(task)
            if task.source_module == "Livestock" and task.status == "Pending":
                assert task.assigned_employee_id == farm.employees["other"]
        assert db.get(FarmActivity, farm.tasks["Livestock"]).assigned_employee_id == farm.employees["worker"]


def test_schedule_change_and_resumption_preserve_occurrence_identity(farm):
    with Session(farm.engine, expire_on_commit=False) as db:
        evaluate_automatic_tasks(db)
        future = db.scalar(select(FarmActivity).where(FarmActivity.source_type == "livestock_growth_check", FarmActivity.activity_date == farm.today+timedelta(days=2)))
        original_id = future.id
        animal = db.get(Livestock, farm.ids["Livestock"])
        animal.monitoring_enabled = False
        evaluate_automatic_tasks(db)
        assert future.status == "Resolved"
        animal.monitoring_enabled = True
        evaluate_automatic_tasks(db)
        assert future.status == "Pending" and future.id == original_id


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_history_range_includes_boundaries_and_rejects_reversed_range(farm, module):
    assert submit(farm, module)[0].status_code == 200
    assert review(farm, module).status_code == 200
    base = "crops" if module == "Crop" else "livestock"
    url = f"/api/v1/{base}/{farm.ids[module]}/growth-records"
    headers = farm.headers["manager"]
    assert len(farm.client.get(url, params={"date_from": str(farm.today), "date_to": str(farm.today)}, headers=headers).json()) == 1
    assert farm.client.get(url, params={"date_to": str(farm.today-timedelta(days=1))}, headers=headers).json() == []
    assert farm.client.get(url, params={"date_from": str(farm.today), "date_to": str(farm.today-timedelta(days=1))}, headers=headers).status_code == 400


def test_direct_count_edit_cannot_be_overwritten_by_older_inspection(farm):
    url = f"/api/v1/crops/{farm.ids['Crop']}"
    edited = farm.client.put(url, json={"current_surviving": 89}, headers=farm.headers["manager"])
    assert edited.status_code == 200, edited.text
    assert edited.json()["survival_count_date"] == str(farm.today)
    response = farm.client.post(url + "/growth-records", json={"update_date": str(farm.today-timedelta(days=3)), "current_surviving": 96, "observed_stage": "Flowering"}, headers=farm.headers["manager"])
    assert response.status_code == 201, response.text
    with Session(farm.engine) as db:
        crop = db.get(Crop, farm.ids["Crop"])
        assert crop.current_surviving == 89
        assert crop.survival_count_date == farm.today
        assert db.scalar(select(CropGrowthRecord)).current_surviving == 96


def test_returned_observation_can_be_corrected_without_posting_rejected_values(farm):
    assert submit(farm, "Crop")[0].status_code == 200
    assert review(farm, "Crop", decision="Return", feedback="Please recount the plants").status_code == 200
    corrected = {"monitoring": observation(farm, "Crop", current_surviving=91), "evidence_url": photo(farm, "Crop"), "worker_notes": "Corrected count"}
    response = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks['Crop']}/submit", json=corrected, headers={**farm.headers["worker"], "Idempotency-Key": "monitoring-corrected"})
    assert response.status_code == 200, response.text
    assert review(farm, "Crop").status_code == 200
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(TaskSubmission)) == 2
        assert db.scalar(select(func.count()).select_from(CropGrowthRecord)) == 1
        assert db.get(Crop, farm.ids["Crop"]).current_surviving == 91


@pytest.mark.parametrize("module,changes,status", [
    ("Crop", {"current_surviving": 101}, 400),
    ("Crop", {"observation_date": "2099-01-01"}, 400),
    ("Livestock", {"animals_measured": 11, "total_measured_weight_kg": 330}, 400),
    ("Livestock", {"min_weight_kg": 40}, 422),
    ("Livestock", {"min_weight_kg": None}, 422),
    ("Livestock", {"total_measured_weight_kg": 100}, 422),
])
def test_invalid_monitoring_cannot_be_submitted(farm, module, changes, status):
    response = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks[module]}/submit", json={"monitoring": observation(farm, module, **changes), "evidence_url": photo(farm, module)}, headers=farm.headers["worker"])
    assert response.status_code == status, response.text
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(TaskSubmission)) == 0


def test_readiness_checkbox_cannot_confirm_a_different_stage(farm):
    assert submit(farm, "Crop")[0].status_code == 200
    assert review(farm, "Crop", confirm_harvest_ready=True).status_code == 400
    with Session(farm.engine) as db:
        assert db.get(Crop, farm.ids["Crop"]).confirmed_ready_at is None
        assert db.scalar(select(func.count()).select_from(CropGrowthRecord)) == 0


def test_frequency_change_preserves_overdue_work_and_manual_assignment(farm):
    with Session(farm.engine, expire_on_commit=False) as db:
        task = db.get(FarmActivity, farm.tasks["Crop"])
        task.activity_date = farm.today-timedelta(days=3)
        task.source_key = f"crop:growth-check:{farm.ids['Crop']}:{task.activity_date}"
        task.status = "Pending"
        evaluate_automatic_tasks(db)
        future = db.scalar(select(FarmActivity).where(FarmActivity.source_type == "crop_growth_check", FarmActivity.activity_date == farm.today+timedelta(days=3)))
        future.assigned_employee_id = farm.employees["manager"]
        future.assignment_source = "manager_override"
        crop = db.get(Crop, farm.ids["Crop"])
        crop.assigned_employee_id = farm.employees["other"]
        evaluate_automatic_tasks(db)
        assert future.assigned_employee_id == farm.employees["manager"]
        crop.monitoring_frequency_days = 5
        evaluate_automatic_tasks(db)
        assert task.status == "Pending" and task.activity_date < farm.today
        assert future.status == "Resolved"


@pytest.mark.parametrize("module", ["Crop", "Livestock"])
def test_workers_cannot_browse_resource_history(farm, module):
    base = "crops" if module == "Crop" else "livestock"
    response = farm.client.get(f"/api/v1/{base}/{farm.ids[module]}/growth-records", headers=farm.headers["worker"])
    assert response.status_code == 403



def test_creating_crop_immediately_schedules_monitoring_and_retries_do_not_duplicate(farm):
    payload = {"name": "New monitored crop", "variety": "Test variety", "field": "Field B", "area_hectares": 1,
               "quantity_planted": 50, "planting_date": str(farm.today), "estimated_harvest": str(farm.today+timedelta(days=60)),
               "assigned_employee_id": farm.employees["worker"], "monitoring_start_date": str(farm.today), "monitoring_frequency_days": 4}
    headers = {**farm.headers["manager"], "Idempotency-Key": "create-monitored-crop"}
    first = farm.client.post("/api/v1/crops", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    again = farm.client.post("/api/v1/crops", json=payload, headers=headers)
    assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
    with Session(farm.engine) as db:
        tasks = db.scalars(select(FarmActivity).where(FarmActivity.source_type == "crop_growth_check", FarmActivity.source_record_id == first.json()["id"])).all()
        assert {task.activity_date for task in tasks} == {farm.today, farm.today+timedelta(days=4)}
        assert len(tasks) == 2
        assert all(task.assigned_employee_id == farm.employees["worker"] and task.requires_evidence for task in tasks)



def test_stale_snapshot_cannot_overwrite_a_newer_approved_survival_count(farm):
    from app.services.resource_monitoring import record_crop_observation
    with Session(farm.engine) as db:
        db.get(Crop, farm.ids["Crop"]).survival_count_date = farm.today-timedelta(days=10)
        db.commit()
    with Session(farm.engine) as stale_db:
        stale = stale_db.get(Crop, farm.ids["Crop"])
        with Session(farm.engine) as current_db:
            current = current_db.get(Crop, farm.ids["Crop"])
            record_crop_observation(current_db, current, observation_date=farm.today, surviving=90)
            current_db.commit()
        record_crop_observation(stale_db, stale, observation_date=farm.today-timedelta(days=5), surviving=96)
        stale_db.commit()
    with Session(farm.engine) as db:
        assert db.get(Crop, farm.ids["Crop"]).current_surviving == 90
        assert db.scalar(select(func.count()).select_from(CropGrowthRecord)) == 2



def test_edit_enable_monitoring_persists_and_employee_receives_tasks(farm):
    with Session(farm.engine) as db:
        animal = Livestock(animal_code="MON-EDIT", record_name="Editable group", animal_type="Pig", breed="Test breed",
                           quantity=10, weight_kg=20, pen_location="Test pen", date_of_birth=farm.today-timedelta(days=90),
                           date_acquired=farm.today-timedelta(days=30), health_status="Healthy", healthy_quantity=10,
                           growth_status="Growing", lifecycle_status="Active", daily_feed_kg=0, monitoring_enabled=False)
        db.add(animal); db.commit(); animal_id = animal.id
    url = f"/api/v1/livestock/{animal_id}"
    payload = {"monitoring_enabled": True, "monitoring_start_date": str(farm.today),
               "monitoring_end_date": str(farm.today+timedelta(days=20)), "monitoring_frequency_days": 3,
               "assigned_employee_id": farm.employees["worker"]}
    response = farm.client.put(url, json=payload, headers=farm.headers["manager"])
    assert response.status_code == 200, response.text
    assert response.json()["monitoring_enabled"] is True
    assert response.json()["monitoring_summary"]["next_date"] == str(farm.today)
    reread = farm.client.get(url, headers=farm.headers["manager"])
    assert reread.status_code == 200
    for key, value in payload.items():
        assert reread.json()[key] == value
    listing = farm.client.get("/api/v1/livestock", headers=farm.headers["manager"])
    assert next(row for row in listing.json() if row["id"] == animal_id)["monitoring_enabled"] is True
    tasks = farm.client.get("/api/v1/workforce/my-tasks/page", params={"view": "active", "scope": "timeline", "limit": 100}, headers=farm.headers["worker"])
    assert tasks.status_code == 200, tasks.text
    monitoring = [task for task in tasks.json()["items"] if task["source_type"] == "livestock_growth_check" and task["source_record_id"] == animal_id]
    assert {task["activity_date"] for task in monitoring} == {str(farm.today+timedelta(days=day)) for day in [0, 3, 6]}
    assert all(task["assigned_employee_id"] == farm.employees["worker"] for task in monitoring)

    before = {task["id"] for task in monitoring}
    assert farm.client.put(url, json=payload, headers=farm.headers["manager"]).status_code == 200
    repeated = farm.client.get("/api/v1/workforce/my-tasks/page", params={"limit": 100}, headers=farm.headers["worker"]).json()["items"]
    assert {task["id"] for task in repeated if task["source_type"] == "livestock_growth_check" and task["source_record_id"] == animal_id} == before
    outsider = farm.client.get("/api/v1/workforce/my-tasks/page", params={"limit": 100}, headers=farm.headers["other"]).json()["items"]
    assert not any(task["id"] in before for task in outsider)


def test_monitoring_edit_and_task_generation_roll_back_together(farm):
    with Session(farm.engine) as db:
        animal = db.get(Livestock, farm.ids["Livestock"])
        animal.monitoring_enabled = False
        db.commit()
    with patch("app.routers.livestock.evaluate_automatic_tasks", side_effect=RuntimeError("test scheduling failure")):
        with pytest.raises(RuntimeError):
            farm.client.put(f"/api/v1/livestock/{farm.ids['Livestock']}", json={"monitoring_enabled": True}, headers=farm.headers["manager"])
    with Session(farm.engine) as db:
        assert db.get(Livestock, farm.ids["Livestock"]).monitoring_enabled is False


def test_monitoring_edit_rejects_incomplete_plan_without_saving(farm):
    url = f"/api/v1/livestock/{farm.ids['Livestock']}"
    response = farm.client.put(url, json={"monitoring_enabled": True, "monitoring_frequency_days": None}, headers=farm.headers["manager"])
    assert response.status_code == 400
    with Session(farm.engine) as db:
        assert db.get(Livestock, farm.ids["Livestock"]).monitoring_frequency_days == 2
    assert farm.client.put(url, json={"monitoring_enabled": False}, headers=farm.headers["worker"]).status_code == 403
