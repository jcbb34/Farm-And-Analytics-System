"""OAuth, restricted file access, resumable uploads and verified downloads."""

import base64
import hashlib
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
import httpx
from app.core.config import settings
from app.core.recovery_runtime import HostLock, session_epoch
from .catalog import now
from .crypto import BackupError

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "openid email https://www.googleapis.com/auth/drive.file"
BLOCK = 8 * 1024 * 1024


class DriveError(BackupError):
    """An operator-safe message; only temporary failures should auto-retry."""

    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


ERROR_ACTIONS = (
    (
        {"SERVICE_DISABLED", "accessNotConfigured"},
        "Enable Google Drive API if disabled in this OAuth client's Google Cloud project. If already enabled, check the project's status and API restrictions. Then retry the cloud copy.",
        False,
        False,
    ),
    (
        {"storageQuotaExceeded"},
        "This Google account has insufficient storage. Free Google account storage before retrying this cloud copy.",
        False,
        False,
    ),
    (
        {
            "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
            "insufficientPermissions",
            "authError",
            "invalidCredentials",
            "invalid_grant",
        },
        "Google access is expired, revoked or missing required backup permissions. Reconnect Google Drive and approve the requested access.",
        False,
        True,
    ),
    (
        {"invalid_client", "unauthorized_client"},
        "Check the backend OAuth client ID and matching client secret, restart the server, then reconnect Google Drive.",
        False,
        True,
    ),
    (
        {"insufficientFilePermissions", "teamDriveMembershipRequired"},
        "The Google account cannot access this backup file or folder. Choose an accessible writable backup folder using Change Folder / Storage.",
        False,
        False,
    ),
    (
        {"notFound"},
        "The cloud file or backup folder is unavailable to this app. Check the connected account and choose an accessible backup folder.",
        False,
        False,
    ),
    (
        {
            "rateLimitExceeded",
            "userRateLimitExceeded",
            "dailyLimitExceeded",
            "RATE_LIMIT_EXCEEDED",
        },
        "Google Drive's request limit was reached. Retry after the limit resets; check the project quota if this continues.",
        True,
        False,
    ),
)


def file_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
        raise BackupError("Invalid Google file identifier.")
    return value


class Drive:
    def __init__(self, catalog, keys, client=None):
        self.catalog, self.keys = catalog, keys
        self._client = client

    @property
    def client(self):
        # Local backup controls must work even if cloud networking/proxies are
        # unavailable. Open a network transport only for an actual Drive call.
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(60, connect=15), follow_redirects=False
            )
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()

    def _send(self, method, url, **kwargs):
        try:
            return self.client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            raise DriveError(
                "Google Drive timed out. Check the server's internet connection and retry the cloud copy.",
                retryable=True,
            ) from None
        except httpx.RequestError:
            raise DriveError(
                "The server could not reach Google Drive. Check its internet connection, proxy and firewall, then retry the cloud copy.",
                retryable=True,
            ) from None

    def _response_error(self, response, fallback=None):
        # Provider messages can contain credentials, URLs or user data. Export
        # only recognized reason codes and our own operator instructions.
        try:
            data = response.json()
        except ValueError:
            data = None
        error = data.get("error") if isinstance(data, dict) else None
        reasons = [error] if isinstance(error, str) else []
        if isinstance(error, dict):
            for field in ("details", "errors"):
                entries = error.get(field)
                if isinstance(entries, list):
                    reasons.extend(
                        entry["reason"]
                        for entry in entries
                        if isinstance(entry, dict)
                        and isinstance(entry.get("reason"), str)
                    )
        reason = None
        reconnect = response.status_code == 401
        retryable = (
            response.status_code in (408, 409, 429) or response.status_code >= 500
        )
        if reconnect:
            message = "Google access could not be verified. Reconnect Google Drive."
        elif retryable:
            message = "Google Drive is temporarily unavailable or limiting requests. Retry the cloud copy shortly."
        elif response.status_code == 403:
            message = "Google Drive denied access. Check API enablement, granted backup permissions and folder access."
        else:
            message = "Google Drive rejected this operation. Check the connection and selected backup folder."
        message = fallback or message
        for codes, action, temporary, needs_reconnection in ERROR_ACTIONS:
            match = next((value for value in reasons if value in codes), None)
            if match:
                reason, message, retryable = match, action, temporary
                reconnect = reconnect or needs_reconnection
                break
        if reconnect:
            value = self.catalog.get("drive", "connection", {})
            self.catalog.put(
                "drive", "connection", {**value, "status": "Needs reconnection"}
            )
        status = f"HTTP {response.status_code}" + (f"; {reason}" if reason else "")
        return DriveError(
            f"Google Drive request failed ({status}). {message}", retryable=retryable
        )

    def connection(self):
        value = self.catalog.get("drive", "connection", {})
        return {
            key: value.get(key)
            for key in (
                "status",
                "email",
                "subject",
                "folder_id",
                "folder_name",
                "connected_at",
            )
        } | {
            "configured": bool(
                settings.backup_google_client_id
                and settings.backup_google_client_secret
                and settings.backup_google_redirect_uri
            )
        }

    def start(self, user_id, auth_version):
        if not self.connection()["configured"]:
            raise BackupError(
                "Configure Google OAuth on the backend before connecting Drive."
            )
        url = urlsplit(settings.backup_google_redirect_uri)
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1")
        ):
            raise BackupError("Use HTTPS for Google OAuth, or localhost during setup.")
        state, verifier = secrets.token_urlsafe(48), secrets.token_urlsafe(64)
        self.catalog.put(
            "oauth",
            hashlib.sha256(state.encode()).hexdigest(),
            {
                "user_id": user_id,
                "auth_version": auth_version,
                "epoch": session_epoch(),
                "expires": time.time() + 600,
                "verifier": self.keys.seal(verifier),
            },
        )
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": settings.backup_google_client_id,
                "redirect_uri": settings.backup_google_redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
                "access_type": "offline",
                "prompt": "consent select_account",
                "code_challenge_method": "S256",
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode()).digest()
                )
                .rstrip(b"=")
                .decode(),
            }
        )

    def finish(self, state, code, authorize):
        identifier = hashlib.sha256(state.encode()).hexdigest()
        with HostLock("oauth-state", timeout=10):
            pending = self.catalog.get("oauth", identifier)
            self.catalog.delete("oauth", identifier)
        if (
            not pending
            or pending["expires"] < time.time()
            or pending["epoch"] != session_epoch()
        ):
            raise BackupError("Google connection expired. Start again.")
        authorize(pending["user_id"], pending["auth_version"])
        response = self._send(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.backup_google_client_id,
                "client_secret": settings.backup_google_client_secret,
                "redirect_uri": settings.backup_google_redirect_uri,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": self.keys.unseal(pending["verifier"]),
            },
        )
        if response.status_code != 200:
            raise self._response_error(response) from None
        tokens = response.json()
        from google.oauth2.id_token import verify_oauth2_token
        from google.auth.transport.requests import Request

        try:
            identity = verify_oauth2_token(
                tokens.get("id_token", ""), Request(), settings.backup_google_client_id
            )
        except Exception:
            raise BackupError("Google identity verification failed.") from None
        if (
            not identity.get("email_verified")
            or not tokens.get("refresh_token")
            or "https://www.googleapis.com/auth/drive.file"
            not in tokens.get("scope", SCOPE).split()
        ):
            raise BackupError(
                "Use a verified Google account and grant background access to backup files."
            )
        old = self.catalog.get("drive", "connection", {})
        value = {
            "status": "Connected",
            "subject": identity["sub"],
            "email": identity["email"],
            "connected_at": now(),
            "tokens": self.keys.seal(tokens),
            "expires": time.time() + int(tokens.get("expires_in", 3600)) - 60,
        }
        if old.get("subject") == identity["sub"]:
            value.update(
                folder_id=old.get("folder_id"), folder_name=old.get("folder_name")
            )
        self.catalog.put("drive", "connection", value)
        if not value.get("folder_id"):
            self.create_folder("Joross Farm Backups")
        self.catalog.event(pending["user_id"], "google_connected")

    def token(self):
        with HostLock("google-token", timeout=30):
            value = self.catalog.get("drive", "connection", {})
            if value.get("status") != "Connected" or not value.get("tokens"):
                raise DriveError(
                    "Reconnect Google Drive before retrying the cloud copy. Local backups remain available."
                )
            tokens = self.keys.unseal(value["tokens"])
            if value.get("expires", 0) <= time.time():
                response = self._send(
                    "POST",
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.backup_google_client_id,
                        "client_secret": settings.backup_google_client_secret,
                        "refresh_token": tokens["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                if response.status_code != 200:
                    if response.status_code in (400, 401):
                        self.catalog.put(
                            "drive",
                            "connection",
                            {**value, "status": "Needs reconnection"},
                        )
                    raise self._response_error(
                        response,
                        "Google access could not be renewed. Reconnect Google Drive before retrying the cloud copy.",
                    ) from None
                tokens.update(response.json())
                value.update(
                    tokens=self.keys.seal(tokens),
                    expires=time.time() + int(tokens.get("expires_in", 3600)) - 60,
                )
                self.catalog.put("drive", "connection", value)
            return tokens["access_token"]

    def request(self, method, url, **kwargs):
        response = self._send(
            method,
            url,
            headers={
                "Authorization": "Bearer " + self.token(),
                **kwargs.pop("headers", {}),
            },
            **kwargs,
        )
        if response.status_code >= 400:
            raise self._response_error(response) from None
        return response

    def quota(self):
        return (
            self.request("GET", API + "/about", params={"fields": "storageQuota"})
            .json()
            .get("storageQuota", {})
        )

    def folders(self):
        return (
            self.request(
                "GET",
                API + "/files",
                params={
                    "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
                    "fields": "files(id,name)",
                    "pageSize": 100,
                },
            )
            .json()
            .get("files", [])
        )

    def create_folder(self, name):
        value = self.request(
            "POST",
            API + "/files",
            params={"fields": "id,name"},
            json={
                "name": name[:100],
                "mimeType": "application/vnd.google-apps.folder",
                "appProperties": {"app": "joross-backup"},
            },
        ).json()
        record = self.catalog.get("drive", "connection", {})
        self.catalog.put(
            "drive",
            "connection",
            {**record, "folder_id": value["id"], "folder_name": value["name"]},
        )
        return self.connection()

    def select_folder(self, identifier):
        value = self.request(
            "GET",
            API + "/files/" + file_id(identifier),
            params={"fields": "id,name,mimeType,capabilities(canAddChildren)"},
        ).json()
        if value.get(
            "mimeType"
        ) != "application/vnd.google-apps.folder" or not value.get(
            "capabilities", {}
        ).get(
            "canAddChildren"
        ):
            raise BackupError(
                "Choose an accessible folder that permits backup uploads."
            )
        record = self.catalog.get("drive", "connection", {})
        self.catalog.put(
            "drive",
            "connection",
            {**record, "folder_id": value["id"], "folder_name": value["name"]},
        )
        return self.connection()

    def disconnect(self, actor):
        value = self.catalog.get("drive", "connection", {})
        if value.get("tokens"):
            response = self.client.post(
                "https://oauth2.googleapis.com/revoke",
                data={
                    "token": self.keys.unseal(value["tokens"]).get("refresh_token", "")
                },
            )
            if response.status_code not in (200, 400):
                raise BackupError(
                    "Access could not be revoked. Retry or revoke access in Google account settings."
                )
        self.catalog.delete("drive", "connection")
        self.catalog.event(actor, "google_disconnected")

    def upload(self, path, metadata, transfer, persist):
        path = Path(path)
        owner = self.connection()
        if transfer.get("subject") and transfer["subject"] != owner["subject"]:
            raise BackupError("Reconnect the Google account that owns this upload.")
        if not transfer.get("id"):
            transfer.update(
                id=self.request(
                    "GET",
                    API + "/files/generateIds",
                    params={"count": 1, "space": "drive"},
                ).json()["ids"][0],
                subject=owner["subject"],
                offset=0,
            )
            persist(transfer)
        identifier = file_id(transfer["id"])
        size = path.stat().st_size
        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as file:
            for block in iter(lambda: file.read(BLOCK), b""):
                digest.update(block)
        expected = digest.hexdigest()
        existing = self._send(
            "GET",
            API + "/files/" + identifier,
            headers={"Authorization": "Bearer " + self.token()},
            params={"fields": "id,size,md5Checksum"},
        )
        if (
            existing.status_code == 200
            and int(existing.json().get("size", -1)) == size
            and existing.json().get("md5Checksum") == expected
        ):
            transfer.update(status="Completed", offset=size, checksum_verified=True)
            transfer.pop("session", None)
            persist(transfer)
            return transfer
        if existing.status_code not in (200, 404):
            raise self._response_error(existing) from None
        if not transfer.get("session"):
            updating = existing.status_code == 200
            body = {
                "name": path.name,
                "appProperties": {"app": "joross-backup", **metadata},
            }
            if not updating:
                body.update(id=identifier, parents=[file_id(owner["folder_id"])])
            response = self.request(
                "PATCH" if updating else "POST",
                UPLOAD + ("/" + identifier if updating else ""),
                params={"uploadType": "resumable"},
                json=body,
                headers={
                    "X-Upload-Content-Length": str(size),
                    "X-Upload-Content-Type": "application/octet-stream",
                },
            )
            transfer["session"] = self.keys.seal(response.headers["location"])
            persist(transfer)
        uri = self.keys.unseal(transfer["session"])
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.googleapis.com"
            or not parsed.path.startswith("/upload/drive/")
        ):
            raise BackupError("Unexpected Google upload location.")
        response = self._send(
            "PUT",
            uri,
            content=b"",
            headers={
                "Authorization": "Bearer " + self.token(),
                "Content-Range": f"bytes */{size}",
                "Content-Length": "0",
            },
        )
        if response.status_code in (404, 410):
            transfer.pop("session", None)
            transfer["offset"] = 0
            persist(transfer)
            raise BackupError(
                "Upload session expired. Retry reuses the same cloud file identity."
            )
        if response.status_code == 308:
            transfer["offset"] = (
                int(response.headers["range"].split("-")[-1]) + 1
                if response.headers.get("range")
                else 0
            )
        elif response.status_code in (200, 201):
            transfer["offset"] = size
        else:
            raise self._response_error(response) from None
        with path.open("rb") as file:
            while transfer["offset"] < size:
                start = transfer["offset"]
                file.seek(start)
                block = file.read(BLOCK)
                response = self.request(
                    "PUT",
                    uri,
                    content=block,
                    headers={
                        "Content-Range": f"bytes {start}-{start+len(block)-1}/{size}",
                        "Content-Length": str(len(block)),
                    },
                )
                offset = (
                    size
                    if response.status_code in (200, 201)
                    else (
                        int(response.headers["range"].split("-")[-1]) + 1
                        if response.status_code == 308 and response.headers.get("range")
                        else -1
                    )
                )
                if offset <= start or offset > size:
                    raise BackupError("Google upload progress could not be confirmed.")
                transfer["offset"] = offset
                persist(transfer)
        verified = self.request(
            "GET",
            API + "/files/" + identifier,
            params={"fields": "id,size,md5Checksum"},
        ).json()
        if (
            int(verified.get("size", -1)) != size
            or verified.get("md5Checksum") != expected
        ):
            raise BackupError("The uploaded file failed its Drive integrity check.")
        transfer.update(status="Completed", checksum_verified=True)
        transfer.pop("session", None)
        persist(transfer)
        return transfer

    def remote_sets(self):
        result = {}
        page = None
        for _ in range(100):
            params = {
                "q": "appProperties has { key='app' and value='joross-backup' } and trashed=false",
                "fields": "nextPageToken,files(id,name,size,createdTime,appProperties)",
                "pageSize": 100,
            }
            if page:
                params["pageToken"] = page
            data = self.request("GET", API + "/files", params=params).json()
            for file in data.get("files", []):
                props = file.get("appProperties", {})
                if props.get("artifact") not in (
                    "zip",
                    "bak",
                    "assets",
                    "kit",
                ) or not props.get("backup_id"):
                    continue
                value = result.setdefault(
                    props["backup_id"],
                    {
                        "id": props["backup_id"],
                        "created_at": file.get("createdTime"),
                        "artifacts": {},
                    },
                )
                value["artifacts"][props["artifact"]] = {
                    "id": file["id"],
                    "name": file["name"],
                    "size": file["size"],
                    "sha256": props.get("sha256"),
                }
            page = data.get("nextPageToken")
            if not page:
                return list(result.values())
        raise BackupError(
            "Too many cloud backups. Archive older files in the connected account."
        )

    def download(self, remote, target, maximum):
        digest = hashlib.sha256()
        size = 0
        try:
            with self.client.stream(
                "GET",
                API + "/files/" + file_id(remote["id"]),
                params={"alt": "media"},
                headers={"Authorization": "Bearer " + self.token()},
            ) as response:
                if response.status_code != 200:
                    raise BackupError("Cloud backup download failed.")
                with Path(target).open("wb") as file:
                    for block in response.iter_bytes(BLOCK):
                        size += len(block)
                        if size > maximum:
                            raise BackupError(
                                "Cloud backup exceeds the supported upload size."
                            )
                        digest.update(block)
                        file.write(block)
            if size != int(remote["size"]) or digest.hexdigest() != remote.get(
                "sha256"
            ):
                raise BackupError("Cloud backup failed its integrity check.")
        except Exception:
            Path(target).unlink(missing_ok=True)
            raise
