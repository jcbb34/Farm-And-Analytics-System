"""Validate new employee leave requests through authenticated HTTP calls."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models import AuditLog, Employee, Role, StaffLeave, User
from app.routers.workforce import router


@pytest.fixture
def leave_api():
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        employee_role = Role(name="Employee", is_active=True)
        employee_role.set_permissions(["workforce:submit"])
        viewer_role = Role(name="Viewer", is_active=True)
        viewer_role.set_permissions(["inventory:view"])
        employee_user = User(user_code="LEAVE-EMP", username="leave.employee", full_name="Leave Employee",
                             role=employee_role, status="Active", password_hash="test-only")
        viewer = User(user_code="LEAVE-VIEW", username="leave.viewer", full_name="Leave Viewer",
                      role=viewer_role, status="Active", password_hash="test-only")
        db.add_all([employee_user, viewer])
        db.flush()
        employee = Employee(employee_code="LEAVE-EMP", full_name="Leave Employee",
                            login_user_id=employee_user.id, employment_status="Active", is_archived=False)
        db.add(employee)
        db.commit()
        token, _ = create_access_token(employee_user.id)
        viewer_token, _ = create_access_token(viewer.id)
        employee_id = employee.id

    app = FastAPI()
    app.include_router(router)

    def test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    previous_timezone = settings.farm_timezone
    settings.farm_timezone = "Asia/Manila"
    try:
        # UTC is still October 28; the farm is already on October 29.
        with patch("app.core.farm_time.datetime") as clock, TestClient(app) as client:
            clock.now.return_value = datetime(2026, 10, 28, 16, 30, tzinfo=timezone.utc)
            yield SimpleNamespace(client=client, engine=engine, employee_id=employee_id,
                                  headers={"Authorization": f"Bearer {token}"},
                                  viewer_headers={"Authorization": f"Bearer {viewer_token}"})
    finally:
        settings.farm_timezone = previous_timezone
        engine.dispose()


def submit(api, **changes):
    payload = {"leave_type": "Vacation Leave", "start_date": "2026-10-30", "end_date": "2026-10-30"}
    payload.update(changes)
    return api.client.post("/api/v1/workforce/leave/request", json=payload, headers=api.headers)


def assert_no_request_writes(api):
    with Session(api.engine) as db:
        assert db.scalar(select(func.count()).select_from(StaffLeave)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(("start", "end"), [
    ("2026-10-28", "2026-10-28"),  # Yesterday, though it is today's UTC date.
    ("2026-10-29", "2026-10-29"),  # Farm-local today.
    ("2026-10-29", "2026-10-30"),  # A future end does not rescue a current start.
    ("2026-10-28", "2026-10-31"),
    ("2026-10-30", "2026-10-29"),
])
def test_today_and_past_dates_are_rejected_without_writes(leave_api, start, end):
    response = submit(leave_api, start_date=start, end_date=end)
    assert response.status_code == 422
    assert_no_request_writes(leave_api)


@pytest.mark.parametrize("changes", [{}, {"reason": None}, {"reason": ""}, {"reason": "   "}, {"reason": "\t\n\u00a0"}])
def test_other_requires_a_non_whitespace_reason(leave_api, changes):
    response = submit(leave_api, leave_type="Other", **changes)
    assert response.status_code == 422
    assert "reason is required" in response.text
    assert_no_request_writes(leave_api)


def test_other_reason_is_trimmed_and_tomorrow_is_a_valid_single_day(leave_api):
    response = submit(leave_api, leave_type="Other", reason="  Personal appointment  ")
    assert response.status_code == 201
    assert response.json()["status"] == "Pending"
    assert response.json()["reason"] == "Personal appointment"
    assert response.json()["employee_id"] == leave_api.employee_id
    with Session(leave_api.engine) as db:
        record = db.scalar(select(StaffLeave))
        assert record.reason == "Personal appointment"
        assert record.decided_by_user_id is None


@pytest.mark.parametrize("leave_type", ["Sick Leave", "Vacation Leave", "Emergency Leave", "Day Off"])
def test_other_existing_types_keep_the_reason_optional(leave_api, leave_type):
    response = submit(leave_api, leave_type=leave_type)
    assert response.status_code == 201
    assert response.json()["reason"] is None


def test_future_end_cannot_precede_future_start(leave_api):
    response = submit(leave_api, start_date="2026-11-02", end_date="2026-11-01")
    assert response.status_code == 422
    assert "end date cannot be before start date" in response.text
    assert_no_request_writes(leave_api)


def test_retried_valid_request_keeps_one_pending_record(leave_api):
    assert submit(leave_api).status_code == 201
    assert submit(leave_api).status_code == 409
    with Session(leave_api.engine) as db:
        assert db.scalar(select(func.count()).select_from(StaffLeave)) == 1


def test_request_authentication_and_permissions_are_preserved(leave_api):
    payload = {"leave_type": "Other", "start_date": "2026-10-30", "end_date": "2026-10-31", "reason": "Appointment"}
    assert leave_api.client.post("/api/v1/workforce/leave/request", json=payload).status_code == 401
    assert leave_api.client.post("/api/v1/workforce/leave/request", json=payload,
                                 headers=leave_api.viewer_headers).status_code == 403
    assert_no_request_writes(leave_api)
