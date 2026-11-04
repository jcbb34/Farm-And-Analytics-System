import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.services.recovery_service import (
    inspect_recovery_package,
    _safe_file,
    MAX_PACKAGE_BYTES,
)
from .crypto import BackupError, sha256_file

BACKEND = Path(__file__).resolve().parents[3]


def current_revision():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def signatures(payload):
    result = {}
    for name, data in payload["tables"].items():
        if name in ("alembic_version", "system_backups"):
            continue
        rows = sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            for row in data["rows"]
        )
        result[name] = {
            "rows": len(rows),
            "columns": sorted(data["columns"]),
            "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
        }
    return result


def metadata(payload):
    return {
        "revision": payload["database"]["alembic_revision"],
        "created_at": payload["created_at"],
        "table_signatures": signatures(payload),
        "evidence_files": payload["recovery"]["evidence_files"],
    }


def native_assets(recovery, bak, target, backup_id, info):
    payload = inspect_recovery_package(recovery)
    manifest = {
        **metadata(payload),
        "format": "joross-native-assets",
        "version": 1,
        "backup_id": backup_id,
        "bak_sha256": sha256_file(bak),
        "sql_version": info["version"],
    }
    with ZipFile(recovery) as source, ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for item in manifest["evidence_files"]:
            archive.writestr(
                "evidence/" + item["name"], source.read("evidence/" + item["name"])
            )
    inspect_assets(target, bak)


def inspect_assets(path, bak, evidence=None):
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            members = archive.infolist()
            if (
                len(names) != len(set(names))
                or len(names) > 200000
                or sum(v.file_size for v in members) > MAX_PACKAGE_BYTES
            ):
                raise BackupError(
                    "The native photo package exceeds its supported limits."
                )
            if (
                any((v.external_attr >> 16) & 0o170000 == 0o120000 for v in members)
                or archive.getinfo("manifest.json").file_size > 2 * 1024 * 1024
            ):
                raise BackupError("Invalid native photo metadata.")
            data = json.loads(archive.read("manifest.json"))
            if (
                data.get("format") != "joross-native-assets"
                or data.get("version") != 1
                or data["revision"] != current_revision()
                or data["bak_sha256"] != sha256_file(bak)
            ):
                raise BackupError(
                    "Choose the matching photo package and application version for this BAK."
                )
            expected = {"manifest.json"}
            if evidence:
                Path(evidence).mkdir(parents=True, exist_ok=True)
            for item in data["evidence_files"]:
                name = _safe_file(item["name"])
                expected.add("evidence/" + name)
                raw = archive.read("evidence/" + name)
                if (
                    len(raw) != item["size"]
                    or hashlib.sha256(raw).hexdigest() != item["sha256"]
                ):
                    raise BackupError(
                        "A native companion photo failed its integrity check."
                    )
                if evidence:
                    (Path(evidence) / name).write_bytes(raw)
            if set(names) != expected or not data["table_signatures"]:
                raise BackupError(
                    "The native companion contains unexpected files or no table checks."
                )
            return data
    except BackupError:
        raise
    except Exception:
        raise BackupError(
            "The native photo package is damaged or incomplete."
        ) from None


def write_kit(target, backup_id):
    root = BACKEND.parent
    files = set()
    excluded = {
        ".git",
        ".venv",
        "node_modules",
        ".next",
        "__pycache__",
        "storage",
        "backups",
        "uploads",
        "test-results",
    }
    for directory, suffixes in [
        ("Jorros Backend/app", {".py", ".sql"}),
        ("Jorros Backend/migrations", {".py", ".mako"}),
        ("Jorros Backend/scripts", {".py", ".sql"}),
        ("Jorros Backend/reference_data", {".json"}),
        ("Jorros Frontend/src", {".js", ".jsx", ".css"}),
        (
            "Jorros Frontend/public",
            {
                ".png",
                ".jpg",
                ".ico",
                ".svg",
                ".woff",
                ".woff2",
                ".json",
                ".js",
                ".css",
                ".webmanifest",
            },
        ),
    ]:
        files.update(
            p
            for p in (root / directory).rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and p.suffix in suffixes
            and not set(p.parts) & excluded
        )
    for name in [
        "run_farm.py",
        "requirements.txt",
        "Jorros Backend/requirements.txt",
        "Jorros Backend/.env.example",
        "Jorros Backend/alembic.ini",
        "Jorros Frontend/package.json",
        "Jorros Frontend/package-lock.json",
        "Jorros Frontend/next.config.mjs",
        "Jorros Frontend/jsconfig.json",
        "Jorros Frontend/.env.local.example",
    ]:
        if (root / name).is_file():
            files.add(root / name)
    digest = hashlib.sha256()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            relative = path.relative_to(root).as_posix()
            raw = path.read_bytes()
            digest.update(relative.encode() + b"\0" + hashlib.sha256(raw).digest())
            archive.writestr("application/" + relative, raw)
        archive.writestr(
            "version.json",
            json.dumps(
                {
                    "format": "joross-recovery-kit",
                    "version": 1,
                    "backup_id": backup_id,
                    "application_version": digest.hexdigest(),
                    "schema_revision": current_revision(),
                }
            ),
        )
        archive.writestr(
            "RECOVERY_INSTRUCTIONS.md", (BACKEND / "BACKUP_RECOVERY.md").read_bytes()
        )
        archive.writestr(
            "CONFIGURATION.txt",
            "Install the matching dependencies. Reconfigure SQL and Google credentials on the replacement server. Live environment files, farm records, tokens, SQL certificates and recovery keys are excluded. Keep the recovery key separately.",
        )
    return digest.hexdigest()
