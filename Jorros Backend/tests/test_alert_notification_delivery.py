"""The alert bell stays bounded while event streams are open."""

import os
from datetime import datetime, timedelta

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models import FarmAlert, Role, User
from app.routers.alerts import router as alerts_router
from app.routers.events import router as events_router


def test_notification_preview_is_bounded_ordered_authorized_and_indexed(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'alerts.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 10, 29, 12)
    with Session(engine) as db:
        admin_role = Role(name="Alert tester", is_active=True)
        admin_role.set_permissions(["*"])
        worker_role = Role(name="Alert worker", is_active=True)
        worker_role.set_permissions(["workforce:submit"])
        admin = User(user_code="ALERT-ADMIN", username="alert.admin", full_name="Alert Admin",
                     password_hash="test-only", status="Active", role=admin_role)
        worker = User(user_code="ALERT-WORKER", username="alert.worker", full_name="Alert Worker",
                      password_hash="test-only", status="Active", role=worker_role)
        db.add_all([admin, worker])
        db.flush()
        headers = {"Authorization": f"Bearer {create_access_token(admin.id)[0]}"}
        worker_headers = {"Authorization": f"Bearer {create_access_token(worker.id)[0]}"}
        db.add_all([
            FarmAlert(alert_name=f"Alert {i}", category="Inventory", subject="Feed",
                      alert_type="Threshold", condition="Below", threshold="5",
                      status="Resolved" if i % 7 == 0 else "Active",
                      last_triggered=now + timedelta(minutes=i // 2) if i % 11 else None)
            for i in range(250)
        ])
        db.commit()
        expected_ids = [row.id for row in db.query(FarmAlert).filter(FarmAlert.last_triggered.is_not(None))
                        .order_by(FarmAlert.last_triggered.desc(), FarmAlert.id.desc()).limit(30)]

    app = FastAPI()
    app.include_router(alerts_router)

    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        response = client.get("/api/v1/alerts/notification-preview?limit=30", headers=headers)
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()] == expected_ids
        assert response.json()[0]["last_triggered"] is not None
        assert client.get("/api/v1/alerts/notification-preview", headers=worker_headers).status_code == 403
        assert client.get("/api/v1/alerts/notification-preview").status_code == 401

    with engine.connect() as connection:
        plan = connection.execute(text("EXPLAIN QUERY PLAN SELECT * FROM farm_alerts "
                                       "WHERE last_triggered IS NOT NULL "
                                       "ORDER BY last_triggered DESC, id DESC LIMIT 30")).all()
        assert any("ix_farm_alerts_triggered_preview" in str(row) for row in plan), plan
        assert not any("TEMP B-TREE" in str(row) for row in plan), plan
    engine.dispose()


def test_stream_releases_auth_connection_before_its_body_is_sent(tmp_path, monkeypatch):
    # One checked-out stream connection would exhaust a small production pool.
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'stream.db'}",
                           pool_size=1, max_overflow=0, pool_timeout=0.5)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        role = Role(name="Stream tester", is_active=True)
        role.set_permissions(["*"])
        user = User(user_code="STREAM-ADMIN", username="stream.admin", full_name="Stream Admin",
                    password_hash="test-only", status="Active", role=role)
        db.add(user)
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id)[0]}"}

    app = FastAPI()
    app.include_router(events_router)

    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    checked_out_during_stream = []

    async def disconnect_immediately(self):
        checked_out_during_stream.append(engine.pool.checkedout())
        return True

    monkeypatch.setattr(Request, "is_disconnected", disconnect_immediately)
    with TestClient(app) as client:
        assert client.get("/api/v1/events/stream").status_code == 401
        response = client.get("/api/v1/events/stream", headers=headers)
        assert response.status_code == 200, response.text
        assert "event: ready" in response.text
    assert checked_out_during_stream and checked_out_during_stream == [0], checked_out_during_stream
    assert engine.pool.checkedout() == 0
    engine.dispose()
