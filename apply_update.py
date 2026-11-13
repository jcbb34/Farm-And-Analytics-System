"""Apply the Joross source update, or roll back saved source files.

Stop Joross first. Run with --project pointing to the existing project root.
The manifest contains code paths only. Database and environment files are never
modified. A conflicting local edit stops the update before any source changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROLLBACK_DIRECTORY = "_update_rollback"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def source_path(root, relative):
    name = PurePosixPath(relative)
    if (name.is_absolute() or ".." in name.parts or "\\" in relative
            or not name.parts or (name.parts[0] not in {"Jorros Frontend", "Jorros Backend"} and relative != "run_farm.py")):
        raise ValueError(f"Invalid update path: {relative}")
    if any(part.startswith(".env") or part in {"storage", "uploads", "backups", "node_modules", ".venv", ".next"} for part in name.parts):
        raise ValueError(f"Protected path: {relative}")
    path = root.joinpath(*name.parts)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
        raise ValueError(f"Symbolic link is not an update target: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path outside project: {relative}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Expected a regular file: {relative}")
    return path


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".update-" + uuid4().hex)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def rollback(project, directory):
    directory = directory.resolve()
    if not directory.is_relative_to((project / ROLLBACK_DIRECTORY).resolve()):
        raise ValueError("Choose a rollback folder inside this project's _update_rollback directory.")
    journal = json.loads((directory / "rollback.json").read_text(encoding="utf-8"))
    operations = journal["operations"]
    # Preflight every target and saved original before changing anything.
    for item in operations:
        path = source_path(project, item["path"])
        if digest(path) not in {item["before_sha256"], item["after_sha256"]}:
            raise ValueError(f"File changed after this update; preserve your edit first: {item['path']}")
        if item["before_sha256"] and digest(source_path(directory / "files", item["path"])) != item["before_sha256"]:
            raise ValueError(f"Saved original is missing or changed: {item['path']}")
    for item in reversed(operations):
        target = source_path(project, item["path"])
        if item["before_sha256"]:
            atomic_copy(source_path(directory / "files", item["path"]), target)
        else:
            target.unlink(missing_ok=True)
    print(f"Restored {len(operations)} source files. Rebuild the frontend before restarting Joross. No database downgrade is required for this patch.")


def apply(project):
    manifest = json.loads((HERE / "update_manifest.json").read_text(encoding="utf-8"))
    for item in manifest.get("requires", []):
        if digest(source_path(project, item["path"])) != item["sha256"]:
            raise ValueError(
                "Install the Data Reliability and Clean Shutdown updates (November 12) first. "
                "Required source is missing or differs: " + item["path"] + ". No files changed."
            )
    operations = []
    # Validate all payload hashes and existing versions before creating backups.
    for item in manifest["files"]:
        payload = source_path(HERE, item["path"])
        if digest(payload) != item["sha256"]:
            raise ValueError(f"Update file is missing or damaged: {item['path']}")
        target = source_path(project, item["path"])
        before = digest(target)
        if before == item["sha256"]:
            continue
        if before not in item["accepted_before_sha256"]:
            raise ValueError(f"Different or locally edited source file: {item['path']}. No files changed.")
        operations.append({"path": item["path"], "before_sha256": before, "after_sha256": item["sha256"]})
    for item in manifest.get("remove", []):
        before = digest(source_path(project, item["path"]))
        if before is None:
            continue
        if before != item["sha256"]:
            raise ValueError(f"Legacy file has local changes: {item['path']}. No files changed.")
        operations.append({"path": item["path"], "before_sha256": before, "after_sha256": None})
    if not operations:
        print("This update is already applied. No files changed. Ensure the earlier a7b8c9d0e1f2 database revision is applied, rebuild the frontend, then restart.")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    directory = project / ROLLBACK_DIRECTORY / (manifest["update_id"] + "-" + stamp)
    directory.mkdir(parents=True)
    for item in operations:
        if item["before_sha256"]:
            atomic_copy(source_path(project, item["path"]), source_path(directory / "files", item["path"]))
    (directory / "rollback.json").write_text(json.dumps({"update_id": manifest["update_id"], "database_migration": manifest.get("database_migration"), "operations": operations}, indent=2) + "\n", encoding="utf-8")
    try:
        for item in operations:
            target = source_path(project, item["path"])
            if digest(target) != item["before_sha256"]:
                raise ValueError(f"Source changed while applying: {item['path']}")
            if item["after_sha256"]:
                atomic_copy(source_path(HERE, item["path"]), target)
            else:
                target.unlink()
    except BaseException:
        print(f"Update interrupted. Saved originals: {directory}", file=sys.stderr)
        print("Use --rollback with that folder to restore source files.", file=sys.stderr)
        raise
    print(f"Updated {len(operations)} source files. Database, photos and configuration were not modified.")
    print(f"Rollback folder: {directory}")
    print("Ensure the earlier edit_version migration is applied: python -m alembic upgrade head in Jorros Backend.")
    print("Run scripts/check_installation.py --json, then npm run build in Jorros Frontend and restart run_farm.py --production.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="Existing Captone Data Analysis project folder")
    parser.add_argument("--rollback", type=Path, help="Saved source rollback folder. This patch requires no database downgrade. Rebuild the frontend after restoring the source.")
    args = parser.parse_args()
    project = args.project.resolve()
    if not (project / "run_farm.py").is_file() or not (project / "Jorros Frontend" / "package.json").is_file():
        parser.error("--project must contain run_farm.py and the Jorros Frontend and Jorros Backend folders.")
    if project == HERE or HERE.is_relative_to(project):
        parser.error("Extract the update outside the installed project folder before running this installer.")
    try:
        if args.rollback:
            rollback(project, args.rollback)
        else:
            apply(project)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Update stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
