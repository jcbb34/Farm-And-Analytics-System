"""Synthetic HTTP coverage for measured land, snapshots, positions and unknown dates."""
import json
from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm
from app.models import (Crop, CropField, CropSection, CropFootprint, CropPositionEvent, CropSpacingProfile,
    FarmLandConfiguration, FarmActivity, TaskSubmission, EmployeeWorkSchedule, EmployeeWorkScheduleDay, Livestock)
from app.routers import crop_planning
from app.services.crop_planting import seed_profiles


def prepare(farm, area="2000"):
    farm.client.app.include_router(crop_planning.router)
    with Session(farm.engine) as db:
        db.add(FarmLandConfiguration(id=1, total_area_m2=18000, unavailable_area_m2=0))
        field = CropField(name="Measured synthetic field", area_m2=Decimal("10000"), unavailable_area_m2=0)
        db.add(field); db.flush()
        section = CropSection(name="Synthetic section", field_id=field.id, area_m2=Decimal(area), unavailable_area_m2=0)
        db.add(section)
        seed_profiles(db)
        worker = farm.employees["worker"]
        schedule = EmployeeWorkSchedule(employee_id=worker, effective_from=farm.today-timedelta(days=10))
        db.add(schedule); db.flush()
        for day in range(7):
            db.add(EmployeeWorkScheduleDay(schedule_id=schedule.id, day_of_week=day, is_working_day=True,
                start_time=time(7), end_time=time(17), break_start_time=time(12), break_end_time=time(13)))
        # Existing fixture resources are unrelated legacy records, with no new care schedules.
        for row in db.scalars(select(FarmActivity)).all():
            row.is_archived = True
        db.get(Crop, farm.ids["Crop"]).monitoring_enabled = False
        db.get(Livestock, farm.ids["Livestock"]).monitoring_enabled = False
        db.commit()
        profiles = {x.profile_key: x.id for x in db.scalars(select(CropSpacingProfile)).all()}
        return field.id, section.id, profiles


def payload(farm, section, profiles, key="saba-block", **changes):
    with Session(farm.engine) as db:
        profile = db.get(CropSpacingProfile, profiles[key])
        data = dict(name=profile.crop_name, variety=profile.variety_name, field="Measured synthetic field",
            area_hectares="0.20", registration_kind="existing", crop_reference=profile.crop_key,
            variety_reference=profile.variety_key, section_id=section, spacing_profile_id=profile.id,
            planting_date_precision="unknown", planting_date=None, estimated_harvest=None,
            quantity_planted=125, current_surviving=115, initial_status="Growing", care_schedules=[])
    data.update(changes)
    return data


def register(farm, data, key="synthetic-crop"):
    return farm.client.post("/api/v1/crops", json=data, headers={**farm.headers["manager"], "Idempotency-Key": key})


def test_partial_allocation_precision_and_measured_limits(farm):
    field, section, profiles = prepare(farm)
    first = register(farm, payload(farm, section, profiles, area_hectares="0.12"))
    assert first.status_code == 201, first.text
    second = register(farm, payload(farm, section, profiles, area_hectares="0.05", duplicate_acknowledged=True), "second")
    assert second.status_code == 201, second.text
    land = farm.client.get("/api/v1/crop-planning/land", headers=farm.headers["manager"]).json()
    assert Decimal(land["fields"][0]["sections"][0]["available_area_m2"]) == Decimal("300")
    assert land["fields"][0]["sections"][0]["status"] == "Partly Occupied"
    third = register(farm, payload(farm, section, profiles, area_hectares="0.030001", duplicate_acknowledged=True), "excess")
    assert third.status_code == 409
    tiny = register(farm, payload(farm, section, profiles, "basil-genovese", area_hectares="0.000123", quantity_planted=1, current_surviving=1), "tiny-bed")
    assert tiny.status_code == 201, tiny.text
    with Session(farm.engine) as db:
        assert db.get(Crop, tiny.json()["id"]).area_hectares == Decimal("0.000123")
        assert db.scalar(select(func.count()).select_from(CropFootprint)) == 3


def test_fields_sections_and_shrink_reject_overallocation(farm):
    field, section, profiles = prepare(farm)
    assert register(farm, payload(farm, section, profiles)).status_code == 201
    response = farm.client.put(f"/api/v1/crop-planning/sections/{section}", headers=farm.headers["manager"],
        json={"name": "Synthetic section", "area_m2": "1900", "expected_version": 1})
    assert response.status_code == 409
    assert farm.client.post("/api/v1/crop-planning/fields", headers=farm.headers["manager"], json={"name": "Too much", "area_m2": "9000"}).status_code == 409
    assert farm.client.post(f"/api/v1/crop-planning/fields/{field}/sections", headers=farm.headers["manager"], json={"name": "Too much", "area_m2": "9000"}).status_code == 409
    assert farm.client.post("/api/v1/crop-planning/fields", headers=farm.headers["worker"], json={"name": "Unauthorized"}).status_code == 403


def test_unconfigured_sections_do_not_invent_area(farm):
    field, section, profiles = prepare(farm)
    response = farm.client.post(f"/api/v1/crop-planning/fields/{field}/sections", headers=farm.headers["manager"], json={"name": "Unmeasured"})
    assert response.status_code == 200
    unknown = next(x for x in response.json()["fields"][0]["sections"] if x["name"] == "Unmeasured")
    assert unknown["status"] == "Unconfigured" and unknown["available_area_m2"] is None
    assert register(farm, payload(farm, unknown["id"], profiles)).status_code == 409


def test_retries_duplicates_and_failure_are_atomic(farm):
    _, section, profiles = prepare(farm)
    data = payload(farm, section, profiles, area_hectares="0.10")
    response = register(farm, data)
    assert response.status_code == 201, response.text
    assert register(farm, data).json()["id"] == response.json()["id"]
    assert register(farm, {**data, "area_hectares": "0.09"}).status_code == 409
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropFootprint)) == 1
    # Transaction rollback after allocation/crop insertion must leave no orphan rows.
    with patch("app.services.crop_direct_care.sync_direct_care", side_effect=ValueError("synthetic downstream failure")):
        with pytest.raises(ValueError):
            register(farm, {**data, "area_hectares": "0.01", "duplicate_acknowledged": True}, "rollback")
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropFootprint)) == 1


def test_capacity_snapshot_does_not_rewrite_actual_counts(farm):
    _, section, profiles = prepare(farm)
    response = register(farm, payload(farm, section, profiles))
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["estimated_capacity"] == 125
    assert data["quantity_planted"] == 125 and data["current_surviving"] == 115
    changed = farm.client.post(f"/api/v1/crop-planning/profiles/{profiles['saba-block']}/versions", headers=farm.headers["manager"],
        json={"row_spacing_m": 5, "plant_spacing_m": 5, "layout": "square", "source_url": "https://example.org/synthetic", "evidence_scope": "Synthetic measured adjustment"})
    assert changed.status_code == 200, changed.text
    again = farm.client.get(f"/api/v1/crops/{data['id']}", headers=farm.headers["manager"]).json()
    assert again["estimated_capacity"] == 125 and again["current_surviving"] == 115
    assert json.loads(again["spacing_snapshot_json"])["version"] == 1


def test_losses_are_positions_and_replacements_keep_dates(farm):
    _, section, profiles = prepare(farm)
    data = register(farm, payload(farm, section, profiles)).json()
    url = f"/api/v1/crop-planning/plantings/{data['id']}/positions"
    state = farm.client.get(url, headers=farm.headers["manager"]).json()
    assert state["potential_replacement_positions"] == 10 and state["verified_cleared_positions"] == 0
    def event(kind, count, key):
        return farm.client.post(url, headers={**farm.headers["manager"], "Idempotency-Key": key}, json={
            "event_type": kind, "event_date": str(farm.today), "quantity": count, "notes": "Synthetic position event"})
    assert event("replacement", 10, "unverified").status_code == 400
    assert event("verified_cleared", 10, "checked").status_code == 200
    assert event("replacement", 10, "replacement-1").status_code == 200
    assert event("replacement", 10, "replacement-1").status_code == 200
    assert event("mortality", 10, "loss-2").status_code == 200
    assert event("verified_cleared", 10, "checked-2").status_code == 200
    assert event("replacement", 10, "replacement-2").status_code == 200
    with Session(farm.engine) as db:
        crop = db.get(Crop, data["id"])
        assert crop.quantity_planted == 125 and crop.current_surviving == 125
        assert crop.planting_date is None
        assert db.scalar(select(func.sum(CropPositionEvent.quantity)).where(CropPositionEvent.crop_id == crop.id, CropPositionEvent.event_type == "replacement")) == 20
        assert db.get(CropFootprint, crop.footprint_id).area_m2 == 2000


@pytest.mark.parametrize("key,part,removed", [("coconut-tall", "nuts", 0), ("saba-block", "fruit", 0), ("basil-genovese", "leaves/shoots", 0),
    ("cassava-lakan-1", "roots", 5), ("sweet-potato-nsic-sp20", "leaves/shoots", 0), ("taro-iniito-vg2", "corms", 5), ("taro-morondon", "leaves", 0)])
def test_actual_harvest_parts_retain_or_remove_plants_without_releasing_land(farm, key, part, removed):
    _, section, profiles = prepare(farm)
    crop = register(farm, payload(farm, section, profiles, key, quantity_planted=100, current_surviving=100)).json()
    body = {"harvest_date": str(farm.today), "quantity_kg": 10, "harvested_part": part,
        "plants_harvested_out": removed, "performed_by_employee_id": farm.employees["worker"], "manual_reason": "Synthetic actual harvest"}
    for index in range(2):
        response = farm.client.post(f"/api/v1/crops/{crop['id']}/yield-records", json=body,
            headers={**farm.headers["manager"], "Idempotency-Key": f"part-harvest-{index}"})
        assert response.status_code == 201, response.text
    with Session(farm.engine) as db:
        record = db.get(Crop, crop["id"])
        assert record.current_surviving == 100 - 2 * removed
        assert record.status == "Harvesting" and record.current_growth is None
        assert db.get(CropFootprint, record.footprint_id).released_at is None
    state = farm.client.get(f"/api/v1/crop-planning/plantings/{crop['id']}/positions", headers=farm.headers["manager"]).json()
    assert state["harvested_out"] == 2 * removed and state["mortality"] == 0
    if removed:
        from app.services.report_builder import _build_crop_snapshot
        with Session(farm.engine) as db:
            legacy = db.get(Crop, farm.ids["Crop"])
            legacy_losses = max(0, legacy.quantity_planted - legacy.current_surviving)
            metrics = _build_crop_snapshot(db, "Crop Production", farm.today, farm.today)["metrics"]
            assert metrics["harvested_out_count"] == 2 * removed
            assert metrics["plant_loss_count"] == legacy_losses


def test_shared_footprint_counted_once_and_released_only_after_all_clear(farm):
    _, section, profiles = prepare(farm)
    coconut = register(farm, payload(farm, section, profiles, "coconut-tall"), "coconut").json()
    banana = register(farm, payload(farm, section, profiles, "saba-under-coconut", shared_footprint_crop_id=coconut["id"],
        shared_footprint_reason="Synthetic intercropping arrangement"), "banana")
    assert banana.status_code == 201, banana.text
    assert banana.json()["estimated_capacity"] == 80
    def clear(record):
        current = farm.client.get(f"/api/v1/crops/{record['id']}", headers=farm.headers["manager"]).json()
        return farm.client.post(f"/api/v1/crop-planning/plantings/{record['id']}/end", json={
            "expected_version": current["edit_version"], "reason": "Synthetic clearing confirmation", "confirm_area_cleared": True}, headers=farm.headers["manager"])
    assert clear(coconut).status_code == 200
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropFootprint)) == 1
        assert db.get(CropFootprint, coconut["footprint_id"]).released_at is None
    assert clear(banana.json()).status_code == 200
    with Session(farm.engine) as db:
        assert db.get(CropFootprint, coconut["footprint_id"]).released_at is not None


def test_interval_break_and_cross_module_conflicts_and_rollbacks(farm):
    _, section, profiles = prepare(farm)
    schedule = dict(activity="observation", enabled=True, start_date=str(farm.today), end_date=str(farm.today),
        frequency_days=1, weekdays=[], start_time="11:45", duration_minutes=30, employee_id=farm.employees["worker"])
    data = payload(farm, section, profiles, "coconut-tall", assigned_employee_id=farm.employees["worker"], care_schedules=[schedule])
    assert register(farm, data, "break-overlap").status_code == 409
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropFootprint)) == 0
    schedule["start_time"] = "10:00"
    first = register(farm, data, "valid-shift")
    assert first.status_code == 201, first.text
    with Session(farm.engine) as db:
        task = db.scalar(select(FarmActivity).where(FarmActivity.source_record_id == first.json()["id"], FarmActivity.source_module == "Crop"))
        assert task.start_time == time(10) and task.end_time == time(10, 30)
    livestock = farm.client.post("/api/v1/workforce/tasks", json={"name": "Competing livestock work", "category": "Livestock Care",
        "activity_date": str(farm.today), "start_time": "10:15", "end_time": "10:45", "employee_id": farm.employees["worker"],
        "source_module": "Livestock", "source_record_id": farm.ids["Livestock"], "source_type": "manual", "requires_evidence": False}, headers=farm.headers["manager"])
    assert livestock.status_code == 409, livestock.text


def test_existing_unknown_date_coconut_complete_workflow(farm, tmp_path, monkeypatch):
    from test_farm_workflow_integration import test_employee_approval_to_stock_sale_and_report
    _, section, profiles = prepare(farm, area="10000")
    schedule = dict(activity="observation", enabled=True, start_date=str(farm.today), end_date=str(farm.today),
        frequency_days=1, weekdays=[], start_time="10:00", duration_minutes=30, employee_id=farm.employees["worker"])
    response = register(farm, payload(farm, section, profiles, "coconut-tall", area_hectares="1.0",
        quantity_planted=100, current_surviving=100, assigned_employee_id=farm.employees["worker"], care_schedules=[schedule]))
    assert response.status_code == 201, response.text
    crop_id = response.json()["id"]
    with Session(farm.engine) as db:
        task = db.scalar(select(FarmActivity).where(FarmActivity.source_record_id == crop_id, FarmActivity.source_module == "Crop"))
        farm.tasks["Crop"] = task.id
    farm.ids["Crop"] = crop_id
    started = farm.client.post(f"/api/v1/workforce/tasks/{farm.tasks['Crop']}/start", json={}, headers=farm.headers["worker"])
    assert started.status_code == 200, started.text
    # Uses real HTTP submission/evidence upload, authorized review, stock usage,
    # actual harvest, production, sale, stored report and background PDF export.
    test_employee_approval_to_stock_sale_and_report(farm, "Crop", tmp_path, monkeypatch)
    with Session(farm.engine) as db:
        crop = db.get(Crop, crop_id)
        assert crop.planting_date is None and crop.estimated_harvest is None
        assert crop.current_growth is None and crop.status == "Harvesting"
        assert crop.current_surviving == 93
        assert db.get(CropFootprint, crop.footprint_id).released_at is None


def test_opening_harvesting_status_does_not_create_yield_or_invent_original_counts(farm):
    _, section, profiles = prepare(farm)
    response = register(farm, payload(farm, section, profiles, "coconut-tall", quantity_planted=None,
        current_surviving=18, initial_status="Harvesting", confirm_ready=True))
    assert response.status_code == 201, response.text
    crop = response.json()
    assert crop["quantity_planted"] is None and crop["current_surviving"] == 18
    assert crop["current_growth"] is None and crop["estimated_progress"] is None
    assert crop["status"] == "Harvesting" and crop["harvest_count"] == 0 and crop["total_harvest_quantity_kg"] == 0
    from app.models import LivestockProductionRecord
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(LivestockProductionRecord)) == 0


def test_root_final_harvest_requires_removing_the_remaining_plants_and_never_releases_area(farm):
    _, section, profiles = prepare(farm)
    crop = register(farm, payload(farm, section, profiles, "cassava-lakan-1", quantity_planted=100, current_surviving=100)).json()
    body = {"harvest_date": str(farm.today), "quantity_kg": 10, "harvested_part": "roots", "harvest_type": "Final Harvest",
        "plants_harvested_out": 10, "final_harvest_confirmed": True, "performed_by_employee_id": farm.employees["worker"], "manual_reason": "Synthetic root harvest"}
    url = f"/api/v1/crops/{crop['id']}/yield-records"
    assert farm.client.post(url, json=body, headers=farm.headers["manager"]).status_code == 400
    body["plants_harvested_out"] = 100
    response = farm.client.post(url, json=body, headers=farm.headers["manager"])
    assert response.status_code == 201, response.text
    with Session(farm.engine) as db:
        assert db.get(Crop, crop["id"]).current_surviving == 0
        assert db.get(CropFootprint, crop["footprint_id"]).released_at is None
    current = farm.client.get(f"/api/v1/crops/{crop['id']}", headers=farm.headers["manager"]).json()
    reopened = farm.client.put(f"/api/v1/crops/{crop['id']}", headers=farm.headers["manager"], json={
        "expected_version": current["edit_version"], "initial_status": "Growing"})
    assert reopened.status_code == 409, reopened.text


def test_schedule_edits_keep_started_returned_and_review_history(farm):
    _, section, profiles = prepare(farm)
    first = farm.today + timedelta(days=1)
    last = first + timedelta(days=2)
    schedule = dict(activity="watering", enabled=True, start_date=str(first), end_date=str(last),
        frequency_days=1, weekdays=[], start_time="10:00", duration_minutes=30, employee_id=farm.employees["worker"])
    response = register(farm, payload(farm, section, profiles, "coconut-tall", care_schedules=[schedule]))
    assert response.status_code == 201, response.text
    crop = response.json()
    with Session(farm.engine) as db:
        tasks = list(db.scalars(select(FarmActivity).where(FarmActivity.source_module == "Crop", FarmActivity.source_record_id == crop["id"]).order_by(FarmActivity.activity_date)).all())
        assert len(tasks) == 3
        ids = [task.id for task in tasks]
        tasks[0].status = "In Progress"
        tasks[1].status = "Returned"
        db.add(TaskSubmission(activity_id=tasks[1].id, employee_id=farm.employees["worker"],
            recorded_by_user_id=farm.users["worker"], review_status="Returned", worker_notes="Preserve submitted work",
            evidence_url="/synthetic-existing-evidence"))
        db.commit()
    current = farm.client.get(f"/api/v1/crops/{crop['id']}", headers=farm.headers["manager"]).json()
    schedule["start_time"] = "10:15"  # Would overlap started work if it were incorrectly regenerated.
    response = farm.client.put(f"/api/v1/crops/{crop['id']}", headers=farm.headers["manager"], json={
        "expected_version": current["edit_version"], "care_schedules": [schedule], "schedule_effective_date": str(first)})
    assert response.status_code == 200, response.text
    with Session(farm.engine) as db:
        tasks = [db.get(FarmActivity, id) for id in ids]
        assert tasks[0].status == "In Progress" and tasks[0].start_time == time(10)
        assert tasks[1].status == "Returned" and tasks[1].start_time == time(10)
        assert tasks[2].status == "Pending" and tasks[2].start_time == time(10, 15)
        assert db.scalar(select(func.count()).select_from(TaskSubmission)) == 1
        assert db.scalar(select(TaskSubmission.evidence_url)) == "/synthetic-existing-evidence"


def test_recurring_leave_is_checked_and_later_conflicts_are_flagged_at_the_original_time(farm):
    from app.models import StaffLeave
    from app.services.crop_direct_care import sync_direct_care
    _, section, profiles = prepare(farm)
    first = farm.today + timedelta(days=1)
    blocked = first + timedelta(days=1)
    schedule = dict(activity="watering", enabled=True, start_date=str(first), end_date=str(blocked),
        frequency_days=1, weekdays=[], start_time="10:00", duration_minutes=30, employee_id=farm.employees["worker"])
    with Session(farm.engine) as db:
        leave = StaffLeave(employee_id=farm.employees["worker"], leave_type="Personal Leave", start_date=blocked, end_date=blocked, status="Approved")
        db.add(leave); db.commit(); leave_id = leave.id
    data = payload(farm, section, profiles, "coconut-tall", care_schedules=[schedule])
    assert register(farm, data, "future-leave").status_code == 409
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(CropFootprint)) == 0
        db.get(StaffLeave, leave_id).status = "Cancelled"
        db.commit()
    response = register(farm, data, "without-leave")
    assert response.status_code == 201, response.text
    with Session(farm.engine) as db:
        db.get(StaffLeave, leave_id).status = "Approved"
        db.flush()
        sync_direct_care(db, db.get(Crop, response.json()["id"]))
        db.commit()
        task = db.scalar(select(FarmActivity).where(FarmActivity.source_record_id == response.json()["id"],
            FarmActivity.source_module == "Crop", FarmActivity.activity_date == blocked))
        assert task.start_time == time(10) and task.end_time == time(10, 30)
        assert task.needs_reassignment and task.assigned_employee_id is None and task.problem_report

def test_allocation_edits_cannot_orphan_a_footprint_or_reopen_cleared_space(farm):
    _, section, profiles = prepare(farm, area='10000')
    coconut = register(farm, payload(farm, section, profiles, 'coconut-tall'), 'coconut').json()
    banana = register(farm, payload(farm, section, profiles, 'saba-block'), 'banana').json()
    response = farm.client.put(f"/api/v1/crops/{banana['id']}", headers=farm.headers['manager'], json={
        'expected_version': banana['edit_version'], 'section_id': section,
        'shared_footprint_crop_id': coconut['id'], 'shared_footprint_reason': 'Synthetic changed arrangement'})
    assert response.status_code == 409, response.text
    with Session(farm.engine) as db:
        assert db.get(Crop, banana['id']).footprint_id == banana['footprint_id']
        assert db.scalar(select(func.sum(CropFootprint.area_m2)).where(CropFootprint.released_at.is_(None))) == 4000
    cleared = farm.client.post(f"/api/v1/crop-planning/plantings/{banana['id']}/end", headers=farm.headers['manager'], json={
        'expected_version': banana['edit_version'], 'reason': 'Synthetic cleared old season', 'confirm_area_cleared': True})
    assert cleared.status_code == 200, cleared.text
    current = farm.client.get(f"/api/v1/crops/{banana['id']}", headers=farm.headers['manager']).json()
    response = farm.client.put(f"/api/v1/crops/{banana['id']}", headers=farm.headers['manager'], json={
        'expected_version': current['edit_version'], 'section_id': section, 'area_hectares': '0.15'})
    assert response.status_code == 409, response.text
    new_season = register(farm, payload(farm, section, profiles, 'saba-block'), 'new-season')
    assert new_season.status_code == 201, new_season.text
    assert new_season.json()['id'] != banana['id']
    assert new_season.json()['footprint_id'] != banana['footprint_id']
    with Session(farm.engine) as db:
        assert db.get(CropFootprint, banana['footprint_id']).released_at is not None
        assert db.get(Crop, banana['id']).area_cleared_at is not None


def test_invalid_square_layout_and_second_precision_intervals(farm):
    from app.schemas.crop_planning import DirectCropSchedule, SpacingAdjustment
    from app.services.workforce_intervals import interval_conflict, available_slots
    from pydantic import ValidationError
    _, section, profiles = prepare(farm)
    with pytest.raises(ValidationError):
        SpacingAdjustment(row_spacing_m=1, plant_spacing_m='.5', layout='square',
            source_url='https://example.org/measured', evidence_scope='Synthetic measured arrangement')
    with pytest.raises(ValidationError):
        DirectCropSchedule(activity='watering', start_date=farm.today, start_time='23:30:01', duration_minutes=30)
    with Session(farm.engine) as db:
        assert interval_conflict(db, farm.employees['worker'], farm.today, time(11, 30, 1), 30)
        assert interval_conflict(db, farm.employees['worker'], farm.today, time(11, 30), 30) is None
        day = db.scalar(select(EmployeeWorkScheduleDay).where(EmployeeWorkScheduleDay.day_of_week == farm.today.weekday()))
        day.start_time = time(7, 0, 30)
        db.flush()
        slots = available_slots(db, farm.employees['worker'], farm.today, 30)
        assert slots['slots'][0]['start_time'] == '07:00:30'


def test_recovery_round_trip_retains_land_unknown_dates_snapshots_and_position_history(farm, tmp_path, monkeypatch):
    from sqlalchemy import Column, MetaData, String, Table, create_engine
    from app.models import SystemBackup
    from app.routers.backups import router as backup_router
    from app.services import backup_service
    from app.services.recovery_service import restore_recovery_package
    from pathlib import Path
    _, section, profiles = prepare(farm)
    crop = register(farm, payload(farm, section, profiles, 'coconut-tall', quantity_planted=None, current_surviving=18)).json()
    response = farm.client.post(f"/api/v1/crop-planning/plantings/{crop['id']}/positions",
        headers={**farm.headers['manager'], 'Idempotency-Key':'synthetic-mortality'}, json={
        'event_type':'mortality', 'event_date':str(farm.today), 'quantity':1, 'notes':'Synthetic observed mortality'})
    assert response.status_code == 200, response.text
    version = Table('alembic_version', MetaData(), Column('version_num', String(32), primary_key=True))
    version.create(farm.engine)
    with farm.engine.begin() as connection:
        connection.execute(version.insert().values(version_num='c9d0e1f2a3b4'))
    monkeypatch.setattr(backup_service, 'engine', farm.engine)
    monkeypatch.setattr(backup_service, 'BACKUP_FOLDER', tmp_path/'backups')
    farm.client.app.include_router(backup_router)
    backup = farm.client.post('/api/v1/backups', headers=farm.headers['manager'])
    assert backup.status_code == 201, backup.text
    with Session(farm.engine) as db:
        package = Path(db.get(SystemBackup, backup.json()['id']).storage_path).with_suffix('.recovery.zip')
    target = create_engine(f"sqlite+pysqlite:///{tmp_path/'restored-crops.db'}")
    try:
        result = restore_recovery_package(package, target, tmp_path/'restored-evidence', apply=True, initialize=True)
        assert result['applied']
        with Session(target) as db:
            restored = db.get(Crop, crop['id'])
            assert restored.planting_date is None and restored.estimated_harvest is None
            assert restored.quantity_planted is None and restored.current_surviving == 17
            assert restored.footprint_id == crop['footprint_id'] and restored.section_id == section
            assert json.loads(restored.spacing_snapshot_json)['profile_key'] == 'coconut-tall'
            event = db.scalar(select(CropPositionEvent).where(CropPositionEvent.crop_id == restored.id))
            assert event.event_type == 'mortality' and event.quantity == 1
            assert db.get(CropFootprint, restored.footprint_id).area_m2 == Decimal('2000')
            assert db.scalar(select(func.count()).select_from(CropSpacingProfile)) == 13
    finally:
        target.dispose()
