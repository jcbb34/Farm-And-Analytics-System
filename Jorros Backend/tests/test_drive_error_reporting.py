"""Google responses are synthetic; jobs and file integrity use the real catalog."""

from contextlib import closing
import hashlib
import json

import httpx
import pytest
from sqlalchemy import create_engine

from app.core.config import settings
from app.services.backup_recovery import manager as manager_module
from app.services.backup_recovery.crypto import BackupError, sha256_file
from app.services.backup_recovery.drive import Drive
from app.services.backup_recovery.manager import RecoveryManager


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_control_dir", str(tmp_path / "control"))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    value = RecoveryManager(engine)
    value.catalog.put(
        "drive",
        "connection",
        {
            "status": "Connected",
            "subject": "synthetic-owner",
            "folder_id": "folder123",
            "expires": 9999999999,
            "tokens": value.keys.seal(
                {"access_token": "private-access", "refresh_token": "private-refresh"}
            ),
        },
    )
    yield value
    engine.dispose()


def google_error(reason, *, modern=False):
    field = "details" if modern else "errors"
    return {
        "error": {
            "message": "PRIVATE raw text: private-refresh, private-access, private-secret",
            field: [{"reason": reason}],
        }
    }


def client_for(service, handler):
    return Drive(
        service.catalog,
        service.keys,
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    "status,reason,modern,expected,retryable,reconnect",
    [
        (403, "SERVICE_DISABLED", True, "Enable Google Drive API", False, False),
        (403, "accessNotConfigured", False, "Google Drive API", False, False),
        (403, "storageQuotaExceeded", False, "storage", False, False),
        (
            403,
            "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
            True,
            "Reconnect Google Drive",
            False,
            True,
        ),
        (403, "insufficientPermissions", False, "Reconnect Google Drive", False, True),
        (403, "insufficientFilePermissions", False, "folder", False, False),
        (403, "rateLimitExceeded", False, "limit", True, False),
        (403, "userRateLimitExceeded", False, "limit", True, False),
        (401, "authError", False, "Reconnect Google Drive", False, True),
        (404, "notFound", False, "unavailable", False, False),
    ],
)
def test_drive_errors_have_safe_reasons_and_specific_actions(
    service, status, reason, modern, expected, retryable, reconnect
):
    with closing(
        client_for(
            service,
            lambda request: httpx.Response(
                status, json=google_error(reason, modern=modern)
            ),
        )
    ) as drive:
        with pytest.raises(BackupError) as failure:
            drive.quota()
        message = str(failure.value)
        assert f"HTTP {status}" in message
        assert reason in message
        assert expected in message
        assert getattr(failure.value, "retryable", None) is retryable
        assert (drive.connection()["status"] == "Needs reconnection") is reconnect
        assert "private-" not in message and "PRIVATE" not in message


@pytest.mark.parametrize(
    "payload",
    [
        None,
        ["private-access"],
        {"error": []},
        {
            "error": {
                "message": "private-access",
                "errors": ["private-refresh", {"reason": ["private-secret"]}],
                "details": "private-secret",
            }
        },
        google_error("private-secret"),
    ],
)
def test_unknown_or_malformed_google_errors_do_not_expose_response_data(
    service, payload
):
    with closing(
        client_for(service, lambda request: httpx.Response(403, json=payload))
    ) as drive:
        with pytest.raises(BackupError) as failure:
            drive.quota()
        assert "HTTP 403" in str(failure.value)
        assert "private-" not in str(failure.value)
        assert getattr(failure.value, "retryable", None) is False


def test_non_json_service_error_is_retryable_and_does_not_expose_body(service):
    with closing(
        client_for(
            service,
            lambda request: httpx.Response(503, text="private-secret: upstream failed"),
        )
    ) as drive:
        with pytest.raises(BackupError) as failure:
            drive.quota()
        assert "HTTP 503" in str(failure.value)
        assert "private-secret" not in str(failure.value)
        assert failure.value.retryable is True


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_errors_have_safe_actionable_messages(service, error_type):
    def handler(request):
        raise error_type(
            "private-access, private-secret, private-refresh", request=request
        )

    with closing(client_for(service, handler)) as drive:
        with pytest.raises(BackupError) as failure:
            drive.quota()
        assert "Google" in str(failure.value)
        assert "private-" not in str(failure.value)
        assert failure.value.retryable is True


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("invalid_grant", "Reconnect Google Drive"),
        ("invalid_client", "OAuth client"),
    ],
)
def test_refresh_errors_distinguish_revoked_access_from_oauth_configuration(
    service, reason, expected
):
    connection = service.catalog.get("drive", "connection")
    connection["expires"] = 0
    service.catalog.put("drive", "connection", connection)
    with closing(
        client_for(
            service,
            lambda request: httpx.Response(
                400, json={"error": reason, "error_description": "private-secret"}
            ),
        )
    ) as drive:
        with pytest.raises(BackupError) as failure:
            drive.token()
        assert reason in str(failure.value)
        assert expected in str(failure.value)
        assert "private-secret" not in str(failure.value)
        assert failure.value.retryable is False
        assert drive.connection()["status"] == "Needs reconnection"


def backup_record(service, tmp_path):
    source = tmp_path / "synthetic.recovery.zip"
    source.write_bytes(b"Synthetic encrypted backup content")
    folder = service.root / "sets" / "synthetic-set"
    folder.mkdir()
    artifact = service.store(source, folder, True)
    value = {
        "id": "synthetic-set",
        "status": "Completed",
        "format": "zip",
        "file_validated": True,
        "artifacts": {"zip": artifact},
        "cloud_status": "Queued",
    }
    service.catalog.put("backup", value["id"], value)
    return value, service.artifact_path(artifact)


@pytest.mark.parametrize(
    "status,reason,expected_status",
    [
        (403, "SERVICE_DISABLED", "Failed"),
        (403, "insufficientPermissions", "Failed"),
        (403, "storageQuotaExceeded", "Failed"),
        (403, "rateLimitExceeded", "Retrying"),
        (503, "unknown", "Retrying"),
    ],
)
def test_worker_retries_transient_failures_but_preserves_backups_on_setup_failure(
    service, tmp_path, monkeypatch, status, reason, expected_status
):
    value, local = backup_record(service, tmp_path)
    original_digest = sha256_file(local)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=google_error(reason, modern=True))

    monkeypatch.setattr(
        manager_module, "Drive", lambda *args: client_for(service, handler)
    )
    job = service.catalog.enqueue(
        "upload", {"backup_id": value["id"]}, "Synthetic Admin"
    )
    service.tick()
    result = service.catalog.job(job["id"])
    assert result["status"] == expected_status
    assert "Checking Google Drive" in result["stage"]
    assert "private-" not in json.dumps(service.public_job(result))
    assert service.catalog.get("backup", value["id"])["status"] == "Completed"
    assert sha256_file(local) == original_digest
    service.tick()
    assert len(calls) == 1
    if expected_status == "Retrying":
        for attempt in range(2, 6):
            service.catalog.update_job(
                job["id"], next_attempt="2000-01-01T00:00:00+00:00"
            )
            service.tick()
            result = service.catalog.job(job["id"])
            assert result["attempts"] == attempt
        assert result["status"] == "Failed" and result["next_attempt"] is None
        assert len(calls) == 5
    else:
        assert result["attempts"] == 1 and result["next_attempt"] is None


def test_missing_backup_folder_is_created_on_retry_after_google_setup_succeeds(
    service, tmp_path, monkeypatch
):
    value, local = backup_record(service, tmp_path)
    connection = service.catalog.get("drive", "connection")
    connection.pop("folder_id")
    service.catalog.put("drive", "connection", connection)
    digest = hashlib.md5(local.read_bytes(), usedforsecurity=False).hexdigest()
    uploaded = False
    folders = []

    def handler(request):
        nonlocal uploaded
        path = request.url.path
        if path.endswith("/about"):
            return httpx.Response(
                200, json={"storageQuota": {"limit": "9999999999", "usage": "0"}}
            )
        if path == "/drive/v3/files" and request.method == "POST":
            folders.append(json.loads(request.content))
            return httpx.Response(
                200, json={"id": "recoveredFolder", "name": "Joross Farm Backups"}
            )
        if path.endswith("/generateIds"):
            return httpx.Response(200, json={"ids": ["stableFile123"]})
        if request.method == "GET":
            return (
                httpx.Response(
                    200,
                    json={
                        "id": "stableFile123",
                        "size": str(local.stat().st_size),
                        "md5Checksum": digest,
                    },
                )
                if uploaded
                else httpx.Response(404)
            )
        if request.method == "POST":
            assert json.loads(request.content)["parents"] == ["recoveredFolder"]
            return httpx.Response(
                200,
                headers={
                    "location": "https://www.googleapis.com/upload/drive/v3/files?upload_id=synthetic-private"
                },
            )
        if request.headers.get("content-range", "").startswith("bytes */"):
            return httpx.Response(308)
        uploaded = True
        return httpx.Response(200, json={"id": "stableFile123"})

    monkeypatch.setattr(
        manager_module, "Drive", lambda *args: client_for(service, handler)
    )
    job = service.catalog.enqueue(
        "upload", {"backup_id": value["id"]}, "Synthetic Admin"
    )
    service.tick()
    assert service.catalog.job(job["id"])["status"] == "Completed"
    assert service.catalog.get("backup", value["id"])["cloud_status"] == "Completed"
    assert service.catalog.get("drive", "connection")["folder_id"] == "recoveredFolder"
    assert len(folders) == 1 and uploaded


def test_cloud_storage_preflight_stops_until_space_is_available(
    service, tmp_path, monkeypatch
):
    value, local = backup_record(service, tmp_path)
    digest = sha256_file(local)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"storageQuota": {"limit": "100", "usage": "100"}}
        )

    monkeypatch.setattr(
        manager_module, "Drive", lambda *args: client_for(service, handler)
    )
    job = service.catalog.enqueue(
        "upload", {"backup_id": value["id"]}, "Synthetic Admin"
    )
    service.tick()
    result = service.catalog.job(job["id"])
    assert result["status"] == "Failed" and result["next_attempt"] is None
    assert "not have enough free storage" in result["error"]
    service.tick()
    assert len(calls) == 1 and sha256_file(local) == digest


def test_disconnected_drive_stops_upload_until_reconnected(
    service, tmp_path, monkeypatch
):
    value, local = backup_record(service, tmp_path)
    service.catalog.delete("drive", "connection")
    calls = []

    def handler(request):
        calls.append(request)
        raise AssertionError("Disconnected uploads must not contact Google.")

    monkeypatch.setattr(
        manager_module, "Drive", lambda *args: client_for(service, handler)
    )
    job = service.catalog.enqueue(
        "upload", {"backup_id": value["id"]}, "Synthetic Admin"
    )
    service.tick()
    result = service.catalog.job(job["id"])
    assert result["status"] == "Failed" and result["next_attempt"] is None
    assert "Reconnect Google Drive" in result["error"]
    assert not calls and local.is_file()


@pytest.mark.parametrize("probe", [False, True])
def test_upload_metadata_and_session_failures_retain_google_reason(
    service, tmp_path, probe
):
    source = tmp_path / "synthetic.enc"
    source.write_bytes(b"Synthetic file")
    transfer = {"id": "stableFile123", "subject": "synthetic-owner"}
    if probe:
        transfer["session"] = service.keys.seal(
            "https://www.googleapis.com/upload/drive/v3/files?upload_id=private-session"
        )

    def handler(request):
        if probe and request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(403, json=google_error("SERVICE_DISABLED", modern=True))

    with closing(client_for(service, handler)) as drive:
        with pytest.raises(BackupError) as failure:
            drive.upload(source, {}, transfer, lambda value: None)
        assert "SERVICE_DISABLED" in str(failure.value)
        assert "HTTP 403" in str(failure.value)
        assert "private-session" not in str(failure.value)
        assert failure.value.retryable is False
