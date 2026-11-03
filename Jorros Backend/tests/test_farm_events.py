"""Policy and real-database round trips for manual farm declarations."""
import os
os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

from datetime import datetime, time, timedelta
import importlib.util
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func, inspect
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.database import Base
from app.models import (Employee, Role, User, EmployeeWorkSchedule, EmployeeWorkScheduleDay, FarmActivity,
                        FarmEvent, FarmEventTask, FarmEventAudit, FarmEventAcknowledgement, StaffAttendance, StaffLeave)
from app.schemas.farm_event import FarmEventCreate, FarmEventUpdate, EventDecision, EventAcknowledgement, EventTaskDecision
from app.routers import farm_events as api
from app.services import farm_event_service as service, work_schedule_service as schedule, attendance_service as attendance


@pytest.fixture
def farm(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    clock = [datetime(2026, 11, 2, 9)]
    for module in (service, schedule, attendance, api):
        monkeypatch.setattr(module, "farm_now_naive", lambda: clock[0])
    monkeypatch.setattr(attendance, "farm_today", lambda: clock[0].date())
    roles = [Role(name="System Administrator"), Role(name="Manager"), Role(name="Employee")]
    users = [User(user_code=f"EV-U-{i}", username=f"event.user.{i}", full_name=f"Event User {i}",
                  password_hash="test", status="Active", role=roles[min(i, 2)]) for i in range(4)]
    db.add_all(roles + users)
    db.flush()
    employees = [Employee(employee_code=f"EV-E-{i}", full_name=f"Event Worker {i}", employment_status="Active",
                          is_archived=False, assigned_area=f"Area {i}", login_user_id=users[i + 2].id) for i in range(2)]
    db.add_all(employees)
    db.flush()
    for employee in employees:
        weekly = EmployeeWorkSchedule(employee_id=employee.id, effective_from=clock[0].date() - timedelta(days=30),
                                       timezone="Asia/Manila", schedule_type="Fixed", status="Active")
        db.add(weekly)
        db.flush()
        for dow in range(7):
            db.add(EmployeeWorkScheduleDay(schedule_id=weekly.id, day_of_week=dow, is_working_day=True,
                                            start_time=time(8), end_time=time(17)))
    db.commit()
    yield db, users, employees, clock
    db.close()
    engine.dispose()


def draft(farm, **changes):
    db, users, employees, clock = farm
    values = dict(title="Farm preparation", kind="Planned No-Work Day", starts_at=clock[0].replace(hour=0),
                  ends_at=clock[0].replace(hour=23, minute=59), reason="Authorized no-work declaration",
                  request_key="event-test-command-0001")
    values.update(changes)
    return api.create_event(FarmEventCreate(**values), db=db, user=users[0])


def approve(farm, event):
    db, users, employees, clock = farm
    preview = api.preview_event(event["id"], db=db, user=users[0])
    return api.approve_event(event["id"], EventDecision(expected_version=event["version"], reason="Reviewed affected work and employees",
                                                       preview_token=preview["preview_token"]), db=db, user=users[0])


def task(farm, *, status="Pending", essential=False, employee=0, start=time(8)):
    db, users, employees, clock = farm
    count = db.scalar(select(func.count()).select_from(FarmActivity)) or 0
    value = FarmActivity(activity_code=f"EV-T-{count}", name="Feeding" if essential else "Field maintenance", category="General Care",
                          related_to="Farm", location=f"Area {employee}", activity_date=clock[0].date(), start_time=start,
                          assigned_by="Manager", assigned_to=employees[employee].full_name,
                          assigned_employee_id=employees[employee].id, default_employee_id=employees[employee].id,
                          assignment_source="automatic_default", status=status, priority="Medium", is_automatic=True,
                          is_archived=False, time_sensitive=essential, requires_review=True, requires_evidence=False)
    db.add(value)
    db.commit()
    return value


def test_drafts_do_not_exempt_attendance_or_hold_work(farm):
    db, users, employees, clock = farm
    work = task(farm)
    event = draft(farm)
    assert schedule.resolve_employee_availability(db, employees[0].id, clock[0].date()).status != "Authorized Day Off"
    assert not service.task_hold_info(db, work)["work_suspended"]
    assert api.list_events(clock[0].date(), clock[0].date(), db=db, user=users[2]) == []


def test_approval_holds_pending_work_without_changing_completed_history(farm):
    db, users, employees, clock = farm
    work, completed = task(farm), task(farm, status="Completed")
    event = approve(farm, draft(farm))
    assert event["status"] == "Active"
    assert db.scalar(select(func.count()).select_from(FarmEventTask)) == 1
    assert work.status == "Pending" and completed.status == "Completed"
    assert service.task_hold_info(db, work)["work_suspended"]
    resolved = schedule.resolve_employee_availability(db, employees[0].id, clock[0].date())
    assert resolved.status == "Authorized Day Off" and not resolved.available
    with pytest.raises(HTTPException) as error:
        service.assert_task_available(db, work)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(StaffAttendance)) == 0


def test_owner_permission_and_scoped_employee_privacy(farm):
    db, users, employees, clock = farm
    event = draft(farm, scope_type="Employees", scope_values=[str(employees[0].id)])
    with pytest.raises(HTTPException) as error:
        api.approve_event(event["id"], EventDecision(expected_version=1, reason="Unauthorized attempt"), db=db, user=users[2])
    assert error.value.status_code == 403
    event = approve(farm, event)
    with pytest.raises(HTTPException) as error:
        api.get_event(event["id"], db=db, user=users[3])
    assert error.value.status_code == 404
    mine = api.get_event(event["id"], db=db, user=users[2])
    assert "audit" not in mine and "impact" not in mine and mine["scope_values"] == []
    assert schedule.resolve_employee_availability(db, employees[1].id, clock[0].date()).available


def test_duplicate_create_approval_and_acknowledgement_are_idempotent(farm):
    db, users, employees, clock = farm
    event = draft(farm)
    assert draft(farm)["id"] == event["id"]
    preview = api.preview_event(event["id"], db=db, user=users[0])
    decision = EventDecision(expected_version=1, reason="Approved planned closure", preview_token=preview["preview_token"])
    api.approve_event(event["id"], decision, db=db, user=users[0])
    api.approve_event(event["id"], decision, db=db, user=users[0])
    for _ in range(2):
        api.acknowledge_event(event["id"], EventAcknowledgement(notice_version=1), db=db, user=users[2])
    assert db.scalar(select(func.count()).select_from(FarmEvent)) == 1
    assert db.scalar(select(func.count()).select_from(FarmEventAudit).where(FarmEventAudit.action == "Approved")) == 1
    assert db.scalar(select(func.count()).select_from(FarmEventAcknowledgement)) == 1
    assert db.scalar(select(func.count()).select_from(StaffAttendance)) == 0


def test_stale_draft_and_changed_preview_are_rejected(farm):
    db, users, employees, clock = farm
    event = draft(farm)
    preview = api.preview_event(event["id"], db=db, user=users[0])
    task(farm)
    with pytest.raises(HTTPException) as error:
        api.approve_event(event["id"], EventDecision(expected_version=1, reason="Approve stale preview", preview_token=preview["preview_token"]), db=db, user=users[0])
    assert error.value.status_code == 409
    assert db.get(FarmEvent, event["id"]).status == "Draft"
    values = {k: event[k] for k in ("title", "kind", "starts_at", "ends_at", "scope_type", "scope_values", "reason")}
    api.update_event(event["id"], FarmEventUpdate(**values, expected_version=1), db=db, user=users[0])
    with pytest.raises(HTTPException) as error:
        api.update_event(event["id"], FarmEventUpdate(**values, expected_version=1), db=db, user=users[0])
    assert error.value.status_code == 409


def test_partial_day_excludes_excused_hours_from_lateness(farm):
    db, users, employees, clock = farm
    approve(farm, draft(farm, starts_at=clock[0].replace(hour=8), ends_at=clock[0].replace(hour=12)))
    with pytest.raises(attendance.AttendanceError):
        attendance.check_in(db, employees[0].id, actor_user_id=users[2].id, actor_name="Employee", source=attendance.SELF_SERVICE, now=clock[0])
    db.rollback()
    clock[0] = clock[0].replace(hour=12, minute=3)
    record = attendance.check_in(db, employees[0].id, actor_user_id=users[2].id, actor_name="Employee", source=attendance.SELF_SERVICE, now=clock[0])
    assert record.status == "On Time" and record.minutes_late == 0
    assert schedule.resolve_employee_availability(db, employees[0].id, clock[0].date()).status == "Working Day"


def test_partial_day_allows_checkout_and_excludes_excused_early_departure(farm):
    db, users, employees, clock = farm
    clock[0] = clock[0].replace(hour=8, minute=0)
    record = attendance.check_in(db, employees[0].id, actor_user_id=users[2].id, actor_name="Employee", source=attendance.SELF_SERVICE, now=clock[0])
    db.commit()
    approve(farm, draft(farm, starts_at=clock[0].replace(hour=16), ends_at=clock[0].replace(hour=17)))
    clock[0] = clock[0].replace(hour=16)
    record = attendance.check_out(db, employees[0].id, actor_user_id=users[2].id, actor_name="Employee", source=attendance.SELF_SERVICE, now=clock[0])
    assert record.status == "Checked Out" and record.minutes_early == 0


def test_full_suspension_blocks_false_absence_but_preserves_raw_history(farm):
    db, users, employees, clock = farm
    original = StaffAttendance(employee_id=employees[0].id, attendance_date=clock[0].date(), status="Absent")
    db.add(original)
    db.commit()
    approve(farm, draft(farm))
    assert attendance.effective_attendance_status(db, original) == "Authorized Day Off"
    assert original.status == "Absent"
    with pytest.raises(attendance.AttendanceError):
        attendance.set_confirmed_status(db, employees[0].id, clock[0].date(), status="Absent", actor_user_id=users[0].id, actor_name="Admin")


def test_emergency_stays_active_until_explicit_reopening_and_survives_new_session(farm):
    db, users, employees, clock = farm
    event = approve(farm, draft(farm, kind="Emergency Suspension", ends_at=clock[0].replace(hour=10)))
    clock[0] = clock[0].replace(hour=14)
    db.expire_all()
    assert service.lifecycle(db.get(FarmEvent, event["id"])) == "Active"
    assert schedule.resolve_employee_availability(db, employees[0].id, clock[0].date()).status == "Work Suspended"
    ended = api.end_event(event["id"], EventDecision(expected_version=event["version"], reason="Inspection and reopening approved"), db=db, user=users[0])
    assert ended["status"] == "Ended"
    assert not schedule.resolve_employee_availability(db, employees[0].id, clock[0].date()).attendance_suspended_now


def test_overlaps_remain_blocking_until_each_declaration_is_ended_and_reviewed(farm):
    db, users, employees, clock = farm
    work = task(farm)
    first = approve(farm, draft(farm))
    second = approve(farm, draft(farm, request_key="event-test-command-0002", title="Overlapping closure"))
    api.end_event(first["id"], EventDecision(expected_version=first["version"], reason="First closure ended"), db=db, user=users[0])
    assert service.task_hold_info(db, work)["work_suspended"]
    assert schedule.resolve_employee_availability(db, employees[0].id, clock[0].date()).attendance_suspended_now
    api.end_event(second["id"], EventDecision(expected_version=second["version"], reason="Second closure ended"), db=db, user=users[0])
    for event in (first, second):
        hold = db.scalar(select(FarmEventTask).where(FarmEventTask.event_id == event["id"]))
        api.review_event_task(event["id"], hold.id, EventTaskDecision(expected_version=hold.version, action="Release", reason="Reviewed original routine work"), db=db, user=users[0])
    assert not service.task_hold_info(db, work)["work_suspended"]


def test_essential_duty_requires_owner_review_and_does_not_move_care_to_tomorrow(farm):
    db, users, employees, clock = farm
    work = task(farm, essential=True)
    event = approve(farm, draft(farm, kind="Emergency Suspension"))
    hold = db.scalar(select(FarmEventTask).where(FarmEventTask.event_id == event["id"]))
    with pytest.raises(HTTPException):
        api.review_event_task(event["id"], hold.id, EventTaskDecision(expected_version=1, action="Reschedule", reason="Move care tomorrow", new_date=clock[0].date()+timedelta(days=1), start_time=time(8)), db=db, user=users[0])
    api.review_event_task(event["id"], hold.id, EventTaskDecision(expected_version=1, action="Essential Duty", reason="Approved essential-care arrangement", employee_id=employees[0].id), db=db, user=users[0])
    assert work.activity_date == clock[0].date()
    assert not service.task_hold_info(db, work)["work_suspended"]
    assert not schedule.resolve_employee_availability(db, employees[0].id, clock[0].date()).attendance_suspended_now
    assert schedule.resolve_employee_availability(db, employees[1].id, clock[0].date()).attendance_suspended_now


def test_new_work_is_captured_idempotently_after_an_approved_declaration(farm):
    db, users, employees, clock = farm
    event = approve(farm, draft(farm))
    new_work = task(farm)
    assert service.task_hold_info(db, new_work)["work_suspended"]
    assert service.reconcile_event_holds(db) == 1
    assert service.reconcile_event_holds(db) == 0
    assert db.scalar(select(func.count()).select_from(FarmEventTask)) == 1


def test_new_migration_adds_only_new_tables_and_can_be_reversed():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    new_names = {"farm_events", "farm_event_tasks", "farm_event_acknowledgements", "farm_event_audits", "farm_event_reports"}
    old_tables = [t for t in Base.metadata.sorted_tables if t.name not in new_names]
    Base.metadata.create_all(engine, tables=old_tables)
    spec = importlib.util.spec_from_file_location("event_revision", Path(__file__).parents[1]/"migrations/versions/e5f6a7b8c9d0_farm_events_and_suspensions.py")
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            assert new_names.issubset(set(inspect(connection).get_table_names()))
            for name in new_names:
                assert {x["name"] for x in inspect(connection).get_columns(name)} == set(Base.metadata.tables[name].columns.keys())
            revision.downgrade()
            assert not new_names.intersection(inspect(connection).get_table_names())
    engine.dispose()


def test_future_cancellation_releases_tasks_without_excusing_a_day(farm):
    db, users, employees, clock = farm
    work = task(farm)
    tomorrow = clock[0] + timedelta(days=1)
    work.activity_date = tomorrow.date(); db.commit()
    event = approve(farm, draft(farm, starts_at=tomorrow.replace(hour=0), ends_at=tomorrow.replace(hour=23)))
    assert service.task_hold_info(db, work)["work_suspended"]
    api.cancel_event(event["id"], EventDecision(expected_version=2, reason="Planned closure cancelled before it starts"), db=db, user=users[0])
    assert not service.task_hold_info(db, work)["work_suspended"]
    assert schedule.resolve_employee_availability(db, employees[0].id, tomorrow.date()).available


def test_area_scope_only_affects_matching_work_and_employee_area(farm):
    db, users, employees, clock = farm
    affected, other = task(farm), task(farm, employee=1)
    event = approve(farm, draft(farm, scope_type="Areas", scope_values=["Area 0"]))
    assert service.task_hold_info(db, affected)["work_suspended"]
    assert not service.task_hold_info(db, other)["work_suspended"]
    assert schedule.resolve_employee_availability(db, employees[1].id, clock[0].date()).available


def test_manager_cannot_approve_reopen_or_authorize_essential_duty(farm):
    db, users, employees, clock = farm
    work = task(farm, essential=True)
    event = draft(farm)
    preview = api.preview_event(event["id"], db=db, user=users[1])
    with pytest.raises(HTTPException) as error:
        api.approve_event(event["id"], EventDecision(expected_version=1, reason="Manager cannot approve", preview_token=preview["preview_token"]), db=db, user=users[1])
    assert error.value.status_code == 403
    event = approve(farm, event)
    with pytest.raises(HTTPException) as error:
        api.end_event(event["id"], EventDecision(expected_version=2, reason="Manager cannot reopen"), db=db, user=users[1])
    assert error.value.status_code == 403
    hold = db.scalar(select(FarmEventTask))
    with pytest.raises(HTTPException) as error:
        api.review_event_task(event["id"], hold.id, EventTaskDecision(expected_version=1, action="Essential Duty", reason="Manager cannot authorize", employee_id=employees[0].id), db=db, user=users[1])
    assert error.value.status_code == 403


def test_held_tasks_are_separate_from_overdue_in_summaries_and_reports(farm, monkeypatch):
    from app.routers import workforce_handlers as workforce
    from app.services import operational_report_builder as reports
    db, users, employees, clock = farm
    work = task(farm)
    approve(farm, draft(farm))
    clock[0] += timedelta(days=1)
    monkeypatch.setattr(workforce, "farm_today", lambda: clock[0].date())
    monkeypatch.setattr(reports, "farm_today", lambda: clock[0].date())
    summary = workforce.task_management_summary(db=db, current_user=users[0])
    assert summary["held"] == 1 and summary["overdue"] == 0
    mine = workforce.my_tasks_summary(db=db, current_user=users[2])
    assert mine.held == 1 and mine.missed == 0
    report = reports._build_task_performance(db, work.activity_date, work.activity_date, {})
    assert report["metrics"]["held"] == 1 and report["metrics"]["overdue"] == 0
    assert report["sections"]["task_details"][0]["status"] == "Held for declaration review"


def test_active_closure_holds_attempts_on_older_overdue_work(farm):
    db, users, employees, clock = farm
    work = task(farm)
    work.activity_date -= timedelta(days=2); db.commit()
    event = approve(farm, draft(farm))
    assert service.task_hold_info(db, work)["work_suspended"]
    assert api.event_tasks(event["id"], offset=0, limit=25, db=db, user=users[0])["total"] == 1


def test_reassigning_an_employee_scoped_hold_to_an_unaffected_worker(farm):
    db, users, employees, clock = farm
    work = task(farm)
    work.needs_reassignment = True; db.commit()
    event = approve(farm, draft(farm, scope_type="Employees", scope_values=[str(employees[0].id)]))
    hold = db.scalar(select(FarmEventTask))
    api.review_event_task(event["id"], hold.id, EventTaskDecision(expected_version=1, action="Reassign", reason="Unaffected qualified employee covers this routine work", employee_id=employees[1].id), db=db, user=users[0])
    assert work.assigned_employee_id == employees[1].id and not work.needs_reassignment
    assert not service.task_hold_info(db, work)["work_suspended"]


def test_rescheduled_occurrence_keeps_its_date_after_generator_runs(farm):
    from app.services.task_engine import _upsert_automatic_task
    db, users, employees, clock = farm
    work = task(farm)
    old_date = work.activity_date
    work.source_key = "event-reschedule-occurrence"; db.commit()
    event = approve(farm, draft(farm))
    clock[0] = clock[0].replace(hour=18)
    event = api.end_event(event["id"], EventDecision(expected_version=2, reason="Work reopened after inspection"), db=db, user=users[0])
    hold = db.scalar(select(FarmEventTask))
    new_date = old_date + timedelta(days=1)
    api.review_event_task(event["id"], hold.id, EventTaskDecision(expected_version=1, action="Reschedule", reason="Routine work moved after reopening", new_date=new_date, start_time=time(10)), db=db, user=users[0])
    _, state = _upsert_automatic_task(db, source_key=work.source_key, source_module="Crop", source_type="routine",
        source_record_id=999, source_detail_id=None, source_code=None, source_path="/crops", name="Generated routine work",
        category="General Care", related_to="Farm", location="Area 0", description="Generator proposal",
        activity_date=old_date, start_time=time(8), assigned_to="System", priority="Medium")
    assert state == "unchanged" and work.activity_date == new_date and work.start_time == time(10)
    assert service.json_value(hold.original_json)["date"] == old_date.isoformat()


def test_reopening_releases_only_future_unaffected_occurrences(farm):
    db, users, employees, clock = farm
    past, future = task(farm), task(farm)
    future.activity_date += timedelta(days=2); db.commit()
    event = approve(farm, draft(farm, kind="Emergency Suspension"))
    clock[0] = clock[0].replace(hour=12)
    api.end_event(event["id"], EventDecision(expected_version=2, reason="Inspected and approved reopening"), db=db, user=users[0])
    assert service.task_hold_info(db, past)["work_suspended"]
    assert not service.task_hold_info(db, future)["work_suspended"]
