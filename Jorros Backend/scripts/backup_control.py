"""Protected local recovery when a working farm login/database is unavailable."""

import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from app.core.config import settings
from app.core.recovery_runtime import (
    HostLock,
    control_root,
    farm_access,
    runtime,
    write_runtime,
)
from app.services.backup_recovery.crypto import BackupError, Keyring
from app.services.backup_recovery.manager import RecoveryManager


def privileged():
    if not (
        bool(ctypes.windll.shell32.IsUserAnAdmin())
        if os.name == "nt"
        else os.geteuid() == 0
    ):
        raise BackupError(
            "Run destructive recovery locally as an operating-system administrator."
        )


def confirm(args, word):
    privileged()
    if args.confirm != word or args.expected_database != settings.db_name:
        raise BackupError(
            "Provide the exact confirmation and --expected-database matching DB_NAME."
        )


def repair_previous(service):
    journal = runtime().get("activation")
    if not journal or not journal.get("safety_backup_id"):
        raise BackupError(
            "No verified previous safety backup is recorded. Keep maintenance active and have the SQL administrator inspect the journal and retained copies."
        )
    with HostLock("backup-worker", timeout=10), farm_access(exclusive=True, timeout=90):
        expected = service.safety_meta(journal["safety_backup_id"])
        service.engine.dispose()
        if service.engine.dialect.name == "mssql":
            if service.native.exists(journal["previous_database"]):
                if service.native.exists(journal["source_database"]):
                    service.native.rename(
                        journal["source_database"],
                        "JorossRecovery_failed_" + uuid4().hex,
                    )
                service.native.rename(
                    journal["previous_database"], journal["source_database"]
                )
        else:
            source, previous = Path(journal["source_file"]), Path(
                journal["previous_file"]
            )
            if previous.is_file():
                if source.exists():
                    os.replace(
                        source,
                        service.root
                        / "staging"
                        / ("failed-" + uuid4().hex + ".sqlite3"),
                    )
                os.replace(previous, source)
        live, previous = Path(journal["live_photos"]), Path(journal["previous_photos"])
        if previous.is_dir():
            if live.exists():
                os.replace(
                    live, service.root / "staging" / ("failed-photos-" + uuid4().hex)
                )
            os.replace(previous, live)
        service.engine.dispose()
        service.verify_target(service.engine, live, expected)
        value = service.catalog.get("candidate", journal["candidate_id"])
        if value:
            value.update(
                status="Test failed",
                restore_tested=False,
                error="Interrupted activation repaired. Prepare a fresh staged copy.",
            )
            service.catalog.put("candidate", value["id"], value)
        service.catalog.event("Local administrator", "interrupted_activation_repaired")
        write_runtime(activation=None, maintenance=None, epoch=uuid4().hex)
    return {"status": "Previous copy verified and reinstated", "sign_in_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-missing-key", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "worker-once"):
        commands.add_parser(name)
    backup = commands.add_parser("backup")
    backup.add_argument("--format", choices=["zip", "bak", "both"], default="both")
    imported = commands.add_parser("import")
    imported.add_argument("package", type=Path)
    imported.add_argument("--photos", type=Path)
    imported.add_argument("--key-file", type=Path)
    tested = commands.add_parser("test")
    tested.add_argument("candidate_id")
    for name, word in [
        ("activate", "RESTORE"),
        ("repair-previous", "ROLLBACK"),
        ("discard", "DISCARD"),
    ]:
        command = commands.add_parser(name)
        if name != "repair-previous":
            command.add_argument("candidate_id")
        command.add_argument("--confirm", required=True)
        command.add_argument("--expected-database", required=True)
        if name == "activate":
            command.add_argument("--skip-current-backup", action="store_true")
    args = parser.parse_args()
    if args.restore_missing_key:
        privileged()
        folder = control_root() / "secrets"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = folder / "recovery.key"
        marker = folder / "key-id"
        raw = Keyring.parse(args.restore_missing_key.read_bytes())
        if destination.exists() or (
            marker.exists()
            and marker.read_text().strip() != hashlib.sha256(raw).hexdigest()[:32]
        ):
            raise BackupError(
                "An existing key cannot be overwritten and a different key cannot unlock this catalog."
            )
        with os.fdopen(
            os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
        ) as file:
            file.write(base64.urlsafe_b64encode(raw))
    service = RecoveryManager()
    if args.command == "init":
        return {
            "status": "Initialized",
            "catalog_schema": 1,
            "farm_migration": "Unchanged",
        }
    if args.command == "status":
        return service.overview()
    if args.command == "worker-once":
        service.tick()
        return {"status": "Worker cycle completed"}
    if args.command == "repair-previous":
        confirm(args, "ROLLBACK")
        return repair_previous(service)
    with HostLock("backup-worker", timeout=5):
        if args.command == "backup":
            return service.public_set(
                service.capture({"format": args.format}, "Local administrator")
            )
        if args.command == "import":
            return service.import_candidate(
                args.package.resolve(),
                args.photos.resolve() if args.photos else None,
                key=args.key_file.read_bytes() if args.key_file else None,
            )
        if args.command == "test":
            return service.test_candidate(
                args.candidate_id, lambda message: print(message, file=sys.stderr)
            )
        if args.command == "activate":
            confirm(args, "RESTORE")
            return service.activate(
                args.candidate_id,
                lambda message: print(message, file=sys.stderr),
                "Local administrator",
                offline=True,
                skip_current_backup=args.skip_current_backup,
            )
        if args.command == "discard":
            confirm(args, "DISCARD")
            return service.discard(args.candidate_id)


if __name__ == "__main__":
    try:
        print(json.dumps(main(), indent=2))
    except Exception as error:
        print(
            (
                str(error)
                if isinstance(error, BackupError)
                else "Recovery did not complete. Keep all files and inspect the protected catalog and activation journal."
            ),
            file=sys.stderr,
        )
        sys.exit(1)
