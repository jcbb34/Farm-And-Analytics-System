"""Exercise the deployed app entry point and local startup checks, without SQL Server."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from test_archives import archive_farm, pending, post, ledger_count
from test_resource_monitoring import farm
from app.core.database import get_db
from app.models import Crop
from app.main import app


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[2]
checker = load_file("archive_api_check", ROOT / "Jorros Backend/scripts/check_archive_api.py")
launcher = load_file("archive_launcher", ROOT / "run_farm.py")


@pytest.fixture
def actual_api(archive_farm):
    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = archive_farm.client.app.dependency_overrides[get_db]
    # A plain TestClient sends real ASGI requests without starting lifespan
    # schedulers or opening the user's configured SQL Server connection.
    client = TestClient(app)
    try:
        yield archive_farm, client
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


@pytest.mark.parametrize("module", ["Crop", "Livestock", "Inventory", "Report"])
def test_actual_app_serves_archive_rows_counts_and_impact(actual_api, module):
    state, client = actual_api
    if module in {"Crop", "Livestock"}: pending(state, module)
    assert post(state, module).status_code == 200
    for query in ({"module": module}, {"module": module, "counts_only": True}):
        response = client.get("/api/v1/archives", params=query, headers=state.headers["manager"])
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["counts"][module] == 1 and data["total"] == 1
        if not query.get("counts_only"): assert data["items"][0]["sourceId"] == state.ids[module]
    response = client.get(f"/api/v1/archives/{module}/{state.ids[module]}/impact", headers=state.headers["manager"])
    assert response.status_code == 200 and response.json()["already_archived"]


def test_actual_app_exposes_legacy_eggplant_without_requiring_a_new_archive_event(actual_api):
    state, client = actual_api
    with Session(state.engine) as db:
        crop = db.get(Crop, state.ids["Crop"])
        crop.name, crop.crop_code, crop.is_archived = "Eggplant", "CRP-1027", True
        db.commit()
    response = client.get("/api/v1/archives?module=Crop", headers=state.headers["manager"])
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["recordName"] == "Eggplant (CRP-1027)" and row["archivedDate"] is None
    assert ledger_count(state, "Crop") == 0


def test_actual_app_keeps_archive_auth_and_required_reason_checks(actual_api):
    state, client = actual_api
    assert client.get("/api/v1/archives?module=Crop").status_code == 401
    assert client.get("/api/v1/archives?module=Crop", headers=state.headers["worker"]).status_code == 403
    path = f"/api/v1/archives/Crop/{state.ids['Crop']}/archive"
    assert client.post(path, json={"reason": " "}, headers=state.headers["manager"]).status_code == 422
    assert ledger_count(state, "Crop") == 0


def test_local_route_check_loads_app_main_without_a_database(capsys):
    with patch("app.main.SessionLocal", side_effect=AssertionError("Local check must not open a database")):
        assert checker.main(["--local"]) == 0
    assert "no database opened" in capsys.readouterr().out


def test_route_check_rejects_a_running_older_backend_and_never_opens_a_database(monkeypatch, capsys):
    monkeypatch.setattr(checker, "live_schema", lambda *_: {"paths": {"/api/v1/crops": {"get": {}}}})
    assert checker.main([]) == 1
    text = capsys.readouterr().err
    assert "running backend" in text and "Missing route: GET /api/v1/archives" in text
    assert "No database reset or migration" in text


@pytest.mark.parametrize("operation", checker.REQUIRED_ROUTES)
def test_route_check_catches_each_missing_archive_operation(operation):
    schema = {"paths": {}}
    for path, method in checker.REQUIRED_ROUTES: schema["paths"].setdefault(path, {})[method] = {}
    del schema["paths"][operation[0]][operation[1]]
    assert checker.missing_routes(schema) == [operation]


def test_launcher_refuses_a_busy_backend_port_without_stopping_its_process():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0)); listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match="already in use"):
            launcher.ensure_port_available(port, "Backend")
        assert listener.fileno() >= 0


def test_launcher_fails_readiness_before_starting_a_frontend(monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match="frontend was not started"):
        launcher.verify_archive_api(port=8000)


def test_live_checker_detects_an_old_server_and_recovers_using_only_its_public_schema(capsys):
    state = {"schema": {"paths": {}}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(state["schema"]).encode())

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            command = ["--url", f"http://127.0.0.1:{server.server_port}"]
            assert checker.main(command) == 1
            state["schema"] = app.openapi()
            assert checker.main(command) == 0
            assert state["requests"] == ["/openapi.json", "/openapi.json"]
        finally:
            server.shutdown(); thread.join(timeout=3)
