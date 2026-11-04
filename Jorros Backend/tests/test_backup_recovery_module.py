"""Generated data only: isolated databases, photos, OAuth and SQL command contracts."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, MetaData, String, Table, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from test_resource_monitoring import farm, submit, review
from app.core.config import settings
from app.core.database import get_db
from app.core.recovery_runtime import HostLock, RecoveryBusy, runtime, write_runtime
from app.core.security import (
    create_access_token,
    decode_access_token_claims,
    hash_password,
)
from app.models import User, Crop
from app.routers import backup_recovery as api
from app.services.backup_recovery.catalog import Catalog
from app.services.backup_recovery.crypto import BackupError, Keyring, sha256_file
from app.services.backup_recovery.drive import Drive
from app.services.backup_recovery.manager import RecoveryManager
from app.services.backup_recovery.options import BackupOptions, next_run
from app.services.backup_recovery.packages import (
    current_revision,
    signatures,
    native_assets,
    inspect_assets,
)
from app.services.backup_recovery.worker import RecoveryGateMiddleware
from app.services.backup_service import _snapshot_database


@pytest.fixture(autouse=True)
def private_control(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_control_dir", str(tmp_path / "control"))


@pytest.fixture
def recovery(farm, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_activation_enabled", True)
    assert submit(farm, "Crop")[0].status_code == 200
    assert review(farm, "Crop").status_code == 200
    version = Table(
        "alembic_version",
        MetaData(),
        Column("version_num", String(32), primary_key=True),
    )
    version.create(farm.engine)
    with farm.engine.begin() as c:
        c.execute(version.insert().values(version_num=current_revision()))
    with Session(farm.engine) as db:
        db.get(User, farm.users["manager"]).password_hash = hash_password(
            "Synthetic-Password"
        )
        db.commit()
    source = tmp_path / "farm.sqlite3"
    with farm.engine.connect() as c:
        destination = sqlite3.connect(source)
        c.connection.driver_connection.backup(destination)
        destination.close()
    engine = create_engine("sqlite+pysqlite:///" + str(source), poolclass=NullPool)
    service = RecoveryManager(engine)
    app = FastAPI()
    app.include_router(api.router)
    app.add_middleware(RecoveryGateMiddleware)
    app.dependency_overrides[api.manager] = lambda: service

    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield SimpleNamespace(
            service=service, engine=engine, source=source, client=client, farm=farm
        )
    engine.dispose()


def backup(service):
    job = service.queue_backup({"format": "zip"}, "Test Admin", "one-command")
    service.tick()
    result = service.catalog.job(job["id"])
    assert result["status"] == "Completed", result
    return service.catalog.get("backup", result["result"]["backup_id"])


def candidate(service):
    value = backup(service)
    selected = service.candidate_from_set(value["id"], "zip")
    service.test_candidate(selected["id"], lambda message: None)
    return selected


def test_encrypted_zip_roundtrip_verifies_records_photos_and_preserves_live_farm(
    recovery,
):
    service = recovery.service
    value = backup(service)
    assert (
        service.artifact_path(value["artifacts"]["zip"])
        .read_bytes()
        .startswith(b"JOROSS-ENC1")
    )
    assert (
        value["photo_count"] == 2
        and value["file_validated"]
        and not value.get("restore_tested_at")
    )
    selected = service.candidate_from_set(value["id"], "zip")
    before = sha256_file(recovery.source)
    assert (
        service.test_candidate(selected["id"], lambda message: None)["status"]
        == "Ready"
    )
    assert sha256_file(recovery.source) == before
    assert service.catalog.get("backup", value["id"])["tested_formats"] == ["zip"]


def test_activation_requires_test_invalidates_sessions_and_preserves_rollback(recovery):
    service = recovery.service
    value = backup(service)
    selected = service.candidate_from_set(value["id"], "zip")
    with pytest.raises(BackupError, match="successful staged restore"):
        service.activate(selected["id"], lambda message: None, "Admin", offline=True)
    service.test_candidate(selected["id"], lambda message: None)
    with recovery.engine.begin() as c:
        c.execute(text("UPDATE crops SET name='Current copy'"))
    token, _ = create_access_token(recovery.farm.users["manager"])
    assert decode_access_token_claims(token)
    assert service.activate(
        selected["id"], lambda message: None, "Admin", offline=True
    )["sign_in_required"]
    assert decode_access_token_claims(token) is None
    with Session(recovery.engine) as db:
        assert db.scalar(select(Crop)).name != "Current copy"
    previous = service.catalog.list("rollback")[0]
    rollback = service.prepare_rollback(previous["id"])
    service.activate(rollback["id"], lambda message: None, "Admin", offline=True)
    with Session(recovery.engine) as db:
        assert db.scalar(select(Crop)).name == "Current copy"
    assert service.catalog.get("rollback", previous["id"])["status"] == "Consumed"
    assert not runtime().get("maintenance") and not runtime().get("activation")


def test_tampered_staged_records_cannot_be_activated(recovery):
    service = recovery.service
    selected = candidate(service)
    target = service.target_for(service.catalog.get("candidate", selected["id"]))
    with target.begin() as c:
        c.execute(text("UPDATE crops SET name='Changed staged copy'"))
    target.dispose()
    with pytest.raises(BackupError, match="checksums and counts"):
        service.activate(selected["id"], lambda message: None, "Admin", offline=True)
    assert not runtime().get("maintenance")


def test_photo_switch_failure_reinstates_exact_previous_farm(recovery, monkeypatch):
    from app.services.backup_recovery import manager as module

    service = recovery.service
    selected = candidate(service)
    with recovery.engine.begin() as c:
        c.execute(text("UPDATE crops SET name='Keep current records'"))
    expected = signatures(_snapshot_database(source_engine=recovery.engine)[0])
    original = module.os.replace
    failed = False

    def fail_once(source, target):
        nonlocal failed
        if Path(source).name.startswith(".joross-activate-") and not failed:
            failed = True
            raise OSError("Synthetic disk failure")
        return original(source, target)

    monkeypatch.setattr(module.os, "replace", fail_once)
    with pytest.raises(
        BackupError, match="previous database and photos were reinstated"
    ):
        service.activate(selected["id"], lambda message: None, "Admin", offline=True)
    assert (
        failed
        and signatures(_snapshot_database(source_engine=recovery.engine)[0]) == expected
    )
    assert not runtime().get("activation") and not runtime().get("maintenance")


def test_operator_repair_checks_safety_records_before_reopening(recovery):
    from scripts.backup_control import repair_previous
    from app.services.evidence_storage import get_evidence_storage

    service = recovery.service
    value = backup(service)
    write_runtime(
        maintenance={"operation": "activation"},
        activation={
            "candidate_id": "interrupted",
            "safety_backup_id": value["id"],
            "source_file": str(recovery.source),
            "previous_file": str(service.root / "absent.sqlite3"),
            "live_photos": str(get_evidence_storage().root),
            "previous_photos": str(service.root / "absent-photos"),
        },
    )
    with recovery.engine.begin() as c:
        original = c.scalar(text("SELECT name FROM crops LIMIT 1"))
        c.execute(text("UPDATE crops SET name='Wrong copy'"))
    with pytest.raises(BackupError, match="checksums and counts"):
        repair_previous(service)
    assert runtime().get("maintenance")
    with recovery.engine.begin() as c:
        c.execute(text("UPDATE crops SET name=:name"), {"name": original})
    assert repair_previous(service)["sign_in_required"] and not runtime().get(
        "maintenance"
    )


def test_encryption_rejects_wrong_keys_and_changed_ciphertext(tmp_path):
    first, second = Keyring(tmp_path / "first"), Keyring(tmp_path / "second")
    source, sealed, plain = [tmp_path / v for v in ("source", "sealed", "plain")]
    source.write_bytes(b"Synthetic farm data" * 100)
    first.encrypt(source, sealed)
    with pytest.raises(BackupError):
        second.decrypt(sealed, plain)
    assert not plain.exists()
    first.decrypt(sealed, plain)
    assert plain.read_bytes() == source.read_bytes()
    changed = bytearray(sealed.read_bytes())
    changed[-20] ^= 1
    sealed.write_bytes(changed)
    with pytest.raises(BackupError):
        first.decrypt(sealed, plain)
    assert not plain.exists()


def test_missing_master_key_is_not_regenerated(tmp_path):
    value = Keyring(tmp_path / "keys")
    value.path.unlink()
    with pytest.raises(BackupError, match="missing"):
        Keyring(tmp_path / "keys")


def test_catalog_migration_and_dedup_preserve_existing_jobs():
    first = Catalog()
    value = first.enqueue("backup", {"format": "zip"}, "Admin", "stable-command")
    second = Catalog()
    assert (
        second.enqueue("backup", {"format": "zip"}, "Admin", "stable-command")["id"]
        == value["id"]
    )
    with second.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="matching"):
        Catalog()


def test_worker_lock_prevents_overlap(recovery):
    service = recovery.service
    job = service.queue_backup({"format": "zip"}, "Admin")
    with HostLock("backup-worker"):
        service.tick()
        assert service.catalog.job(job["id"])["status"] == "Queued"
    service.tick()
    assert service.catalog.job(job["id"])["status"] == "Completed"


def test_local_controls_work_when_cloud_transport_cannot_initialize(
    recovery, monkeypatch
):
    from app.services.backup_recovery import drive

    def unavailable(*args, **kwargs):
        raise ImportError("Synthetic unavailable cloud proxy")

    monkeypatch.setattr(drive.httpx, "Client", unavailable)
    assert recovery.service.overview()["drive"]["status"] is None
    assert backup(recovery.service)["status"] == "Completed"


def test_permissions_fresh_credentials_and_private_downloads(recovery):
    client, farm = recovery.client, recovery.farm
    root = "/api/v1/backup-recovery"
    assert client.get(root + "/overview").status_code == 401
    assert (
        client.get(root + "/overview", headers=farm.headers["worker"]).status_code
        == 403
    )
    assert (
        client.post(
            root + "/recovery-key",
            headers=farm.headers["manager"],
            json={"password": "Wrong"},
        ).status_code
        == 403
    )
    response = client.post(
        root + "/recovery-key",
        headers=farm.headers["manager"],
        json={"password": "Synthetic-Password"},
    )
    assert (
        response.status_code == 200
        and len(response.content) == 44
        and response.headers["cache-control"] == "no-store"
    )
    value = backup(recovery.service)
    response = client.get(
        root + "/backups/" + value["id"] + "/download/zip",
        headers=farm.headers["manager"],
    )
    assert (
        response.content.startswith(b"JOROSS-ENC1")
        and response.headers["cache-control"] == "no-store"
    )
    public = client.get(root + "/overview", headers=farm.headers["manager"]).json()
    assert "recovery.key" not in json.dumps(public) and '"tokens"' not in json.dumps(
        public
    )


def test_upload_authorization_precedes_multipart_parsing_and_limits_size(
    recovery, monkeypatch
):
    root = "/api/v1/backup-recovery/candidates/import"
    client = recovery.client
    assert (
        client.post(
            root, content=b"unparsed", headers={"content-type": "multipart/form-data"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            root,
            content=b"unparsed",
            headers={
                **recovery.farm.headers["worker"],
                "content-type": "multipart/form-data",
            },
        ).status_code
        == 403
    )
    monkeypatch.setattr(settings, "backup_max_upload_bytes", 1024)
    assert (
        client.post(
            root,
            content=b"",
            headers={
                **recovery.farm.headers["manager"],
                "content-length": str(3 * 1024 * 1024),
            },
        ).status_code
        == 413
    )


def test_deletion_keeps_newest_and_last_tested_sets(recovery):
    service = recovery.service
    first = backup(service)
    with pytest.raises(BackupError, match="newest verified"):
        service.delete_set(first["id"], "Admin")
    selected = service.candidate_from_set(first["id"], "zip")
    service.test_candidate(selected["id"], lambda message: None)
    second = service.capture({"format": "zip"}, "Admin")
    for value in (first, second):
        with pytest.raises(BackupError):
            service.delete_set(value["id"], "Admin")


def test_space_failure_keeps_existing_backup(recovery, monkeypatch):
    from app.services.backup_recovery import manager as module

    first = backup(recovery.service)
    monkeypatch.setattr(
        module.shutil, "disk_usage", lambda path: SimpleNamespace(free=0)
    )
    with pytest.raises(BackupError, match="local storage"):
        recovery.service.capture({"format": "zip"}, "Admin")
    assert recovery.service.artifact_path(first["artifacts"]["zip"]).is_file()


def test_schedules_use_manila_clamp_months_and_queue_one_catchup(recovery):
    assert (
        next_run(
            BackupOptions(frequency="weekly", weekday=0, hour=8),
            datetime(2026, 11, 4, tzinfo=timezone.utc),
        )
        == "2026-11-09T00:00:00+00:00"
    )
    assert (
        next_run(
            BackupOptions(frequency="monthly", month_day=31, hour=8),
            datetime(2027, 2, 1, tzinfo=timezone.utc),
        )
        == "2027-02-28T00:00:00+00:00"
    )
    service = recovery.service
    service.catalog.put(
        "settings",
        "backup",
        BackupOptions(
            format="zip", encrypted=False, schedule_enabled=True
        ).model_dump(),
    )
    service.catalog.put("schedule", "next", {"at": "2026-01-01T00:00:00+00:00"})
    service.schedule()
    service.schedule()
    assert len(service.catalog.jobs()) == 1


def test_native_companion_is_bound_to_exact_bak_and_photos(recovery, tmp_path):
    service = recovery.service
    value = backup(service)
    logical = service.plaintext(value["artifacts"]["zip"], tmp_path / "logical.zip")
    bak = tmp_path / "synthetic.bak"
    bak.write_bytes(b"Native contract fixture")
    companion = tmp_path / "photos.zip"
    native_assets(logical, bak, companion, "same-id", {"version": "16.0.0"})
    assert len(inspect_assets(companion, bak)["evidence_files"]) == 2
    bak.write_bytes(b"Different native file")
    with pytest.raises(BackupError, match="matching photo"):
        inspect_assets(companion, bak)


def test_native_commands_use_autocommit_master_and_drain_late_sql_errors(monkeypatch):
    from app.services.backup_recovery import native
    from sqlalchemy.engine import make_url

    calls = []

    class Connection:
        def execution_options(self, **values):
            calls.append(values)
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            calls.append("disposed")

    def factory(url, **kwargs):
        assert (
            "DATABASE=master" in url.query["odbc_connect"]
            and kwargs["poolclass"] is NullPool
        )
        return Engine()

    monkeypatch.setattr(native, "create_engine", factory)
    source = SimpleNamespace(
        dialect=SimpleNamespace(name="mssql"),
        url=make_url("mssql+pyodbc://").update_query_dict(
            {
                "odbc_connect": "DRIVER={Synthetic};SERVER=synthetic;DATABASE=Actual_Farm;Trusted_Connection=yes;"
            }
        ),
    )
    server = native.SqlServer(source)
    assert server.database == "Actual_Farm"
    with server.admin():
        pass
    assert calls == [{"isolation_level": "AUTOCOMMIT"}, "disposed"]

    class Cursor:
        description = None

        def execute(self, *args):
            pass

        def nextset(self):
            raise RuntimeError("Late SQL error")

        def close(self):
            calls.append("closed")

    with pytest.raises(RuntimeError, match="Late SQL"):
        server.command(
            SimpleNamespace(
                connection=SimpleNamespace(
                    driver_connection=SimpleNamespace(cursor=lambda: Cursor())
                )
            ),
            "RESTORE",
        )
    assert calls[-1] == "closed"
    with pytest.raises(BackupError):
        native.identifier("farm]; DROP DATABASE master--")
    with pytest.raises(BackupError):
        server.drop_recovery("Actual_Farm")


def connected(tmp_path):
    catalog = Catalog()
    keys = Keyring(tmp_path / "keys")
    catalog.put(
        "drive",
        "connection",
        {
            "status": "Connected",
            "subject": "synthetic-owner",
            "folder_id": "folder123",
            "tokens": keys.seal(
                {
                    "access_token": "synthetic-access",
                    "refresh_token": "synthetic-refresh",
                }
            ),
            "expires": 9999999999,
        },
    )
    return catalog, keys


def test_google_upload_reconciles_completion_without_duplicate_files(tmp_path):
    catalog, keys = connected(tmp_path)
    source = tmp_path / "backup.enc"
    source.write_bytes(b"Synthetic backup")
    digest = hashlib.md5(source.read_bytes(), usedforsecurity=False).hexdigest()
    calls = []
    uploaded = False

    def handler(request):
        nonlocal uploaded
        calls.append((request.method, str(request.url)))
        if request.url.path.endswith("/generateIds"):
            return httpx.Response(200, json={"ids": ["stableFile123"]})
        if request.method == "GET":
            return (
                httpx.Response(
                    200,
                    json={
                        "id": "stableFile123",
                        "size": str(source.stat().st_size),
                        "md5Checksum": digest,
                    },
                )
                if uploaded
                else httpx.Response(404)
            )
        if request.method == "POST":
            return httpx.Response(
                200,
                headers={
                    "location": "https://www.googleapis.com/upload/drive/v3/files?upload_id=test"
                },
            )
        if request.headers.get("content-range", "").startswith("bytes */"):
            return httpx.Response(308)
        uploaded = True
        return httpx.Response(200, json={"id": "stableFile123"})

    drive = Drive(catalog, keys, httpx.Client(transport=httpx.MockTransport(handler)))
    transfer = {}
    assert drive.upload(source, {}, transfer, lambda value: None)["checksum_verified"]
    assert (
        drive.upload(source, {}, transfer, lambda value: None)["id"] == "stableFile123"
    )
    assert sum(method == "POST" for method, url in calls) == 1


def test_expired_google_session_keeps_remote_identity_for_retry(tmp_path):
    catalog, keys = connected(tmp_path)
    source = tmp_path / "backup.enc"
    source.write_bytes(b"Synthetic backup")
    transfer = {
        "id": "stableFile123",
        "subject": "synthetic-owner",
        "session": keys.seal(
            "https://www.googleapis.com/upload/drive/v3/files?upload_id=expired"
        ),
    }

    def handler(request):
        return httpx.Response(404) if request.method == "GET" else httpx.Response(410)

    drive = Drive(catalog, keys, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(BackupError, match="expired"):
        drive.upload(source, {}, transfer, lambda value: None)
    assert transfer["id"] == "stableFile123" and "session" not in transfer


def test_revoked_google_refresh_requires_reconnection(tmp_path):
    catalog, keys = connected(tmp_path)
    value = catalog.get("drive", "connection")
    value["expires"] = 0
    catalog.put("drive", "connection", value)
    drive = Drive(
        catalog,
        keys,
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(400))
        ),
    )
    with pytest.raises(BackupError, match="renewed"):
        drive.token()
    assert drive.connection()["status"] == "Needs reconnection"


def test_google_oauth_is_one_use_actor_bound_and_encrypts_tokens(tmp_path, monkeypatch):
    from google.oauth2 import id_token

    catalog, keys = Catalog(), Keyring(tmp_path / "keys")
    for name, value in [
        ("backup_google_client_id", "synthetic-client"),
        ("backup_google_client_secret", "synthetic-secret"),
        (
            "backup_google_redirect_uri",
            "http://localhost/api/v1/backup-recovery/drive/callback",
        ),
    ]:
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(
        id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": "owner123",
            "email": "synthetic@example.test",
            "email_verified": True,
        },
    )

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            assert b"code_verifier=" in request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "access",
                    "refresh_token": "private-refresh",
                    "id_token": "signed-fixture",
                    "scope": "https://www.googleapis.com/auth/drive.file",
                },
            )
        return httpx.Response(200, json={"id": "folder123", "name": "Farm Backups"})

    drive = Drive(catalog, keys, httpx.Client(transport=httpx.MockTransport(handler)))
    state = parse_qs(urlsplit(drive.start(12, 3)).query)["state"][0]
    pending = catalog.list("oauth")[0]
    assert keys.unseal(pending["verifier"]) not in json.dumps(pending)
    actors = []
    drive.finish(state, "synthetic-code", lambda *args: actors.append(args))
    assert actors == [(12, 3)]
    assert "private-refresh" not in json.dumps(catalog.get("drive", "connection"))
    with pytest.raises(BackupError, match="expired"):
        drive.finish(
            state, "replayed-code", lambda *args: pytest.fail("Replayed OAuth")
        )


def test_activation_rechecks_queued_approvers_current_authorization(recovery):
    service = recovery.service
    selected = candidate(service)
    response = recovery.client.post(
        "/api/v1/backup-recovery/candidates/" + selected["id"] + "/activate",
        headers=recovery.farm.headers["manager"],
        json={"password": "Synthetic-Password", "confirmation": "RESTORE"},
    )
    assert response.status_code == 202
    with Session(recovery.engine) as db:
        db.get(User, recovery.farm.users["manager"]).auth_version += 1
        db.commit()
    before = sha256_file(recovery.source)
    service.tick()
    job = service.catalog.job(response.json()["id"])
    assert job["status"] == "Failed" and "no longer authorized" in job["error"]
    assert sha256_file(recovery.source) == before
    assert not runtime().get("maintenance") and not runtime().get("activation")


def test_key_export_requires_enabled_two_factor_code(recovery):
    import pyotp

    secret = pyotp.random_base32()
    with Session(recovery.engine) as db:
        user = db.get(User, recovery.farm.users["manager"])
        user.two_factor_enabled = True
        user.two_factor_secret = secret
        db.commit()
    path = "/api/v1/backup-recovery/recovery-key"
    headers = recovery.farm.headers["manager"]
    assert (
        recovery.client.post(
            path, headers=headers, json={"password": "Synthetic-Password"}
        ).status_code
        == 403
    )
    assert (
        recovery.client.post(
            path,
            headers=headers,
            json={
                "password": "Synthetic-Password",
                "otp_code": pyotp.TOTP(secret).now(),
            },
        ).status_code
        == 200
    )


def test_interrupted_restore_test_stays_visible_and_can_be_discarded(recovery):
    service = recovery.service
    selected = service.candidate_from_set(backup(service)["id"], "zip")
    value = service.catalog.get("candidate", selected["id"])
    value.update(status="Testing")
    service.catalog.put("candidate", selected["id"], value)
    job = service.catalog.enqueue("test", {"candidate_id": selected["id"]}, "Admin")
    service.catalog.update_job(job["id"], status="Running")
    service.tick()
    assert service.catalog.job(job["id"])["status"] == "Incomplete"
    assert service.catalog.get("candidate", selected["id"])["status"] == "Test failed"
    assert service.discard(selected["id"])["status"] == "Discarded"
