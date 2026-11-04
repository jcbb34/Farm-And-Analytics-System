"""Build a source-only Joross Farm ZIP from explicit, reviewed paths.

Run from the project root: py -3.12 .\\create_source_release.py
Use --output PATH to choose the resulting archive. No database is accessed.
"""

import argparse
from datetime import datetime
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
ARCHIVE_ROOT = "Joross_Farm"
ROOT_FILES = (
    "create_source_release.py",
    "BACKUP_RECOVERY_RELEASE.md",
    "run_farm.py",
    "verify_upgrade.ps1",
    "cleanup_project.ps1",
    "requirements.txt",
    ".gitignore",
)
BACKEND_FILES = (
    "alembic.ini",
    "BACKUP_RECOVERY.md",
    "requirements.txt",
    "requirements-dev.txt",
    ".env.example",
    "migrations/README",
    "migrations/env.py",
    "migrations/script.py.mako",
)
FRONTEND_FILES = (
    ".gitignore",
    "jsconfig.json",
    "next.config.mjs",
    "package.json",
    "package-lock.json",
    ".env.local.example",
    "playwright.config.mjs",
)
DIRECTORIES = {
    "Jorros Backend/reference_data": {".json"},
    "Jorros Backend/app": {".py", ".sql"},
    "Jorros Backend/tests": {".py"},
    "Jorros Backend/scripts": {".py", ".sql"},
    "migrations": {".py", ".mako"},
    "Jorros Backend/protocol_import_templates": {".json", ".csv"},
    "Jorros Frontend/tests": {".mjs"},
    "Jorros Frontend/browser-tests": {".mjs"},
    "Jorros Frontend/scripts": {".mjs"},
    "Jorros Backend/migrations/versions": {".py"},
    "Jorros Frontend/src": {".js", ".jsx", ".css"},
    "Jorros Frontend/public/reference-data": {".json"},
    "Jorros Frontend/public": {".webmanifest", ".js", ".html", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff2", ".woff", ".css", ".txt"},
}
FORBIDDEN_PARTS = {
    ".venv", "node_modules", ".next", ".vs", "__pycache__", ".pytest_cache",
    "test-results", "playwright-report",
    "generated_reports", "import_uploads", "uploads", "backups", "storage", "tmp", "temp",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{32,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
)
SETTING_PATTERN = re.compile(r"(?im)^[ \t]*(?:JWT_SECRET_KEY|SEED_ADMIN_PASSWORD|OPENWEATHER_API_KEY)[ \t]*=[ \t]*([^\s#]*)")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def release_files():
    # The public dropdown choices must use exactly the catalogue validated by
    # the API. Refuse incomplete or mismatched source updates before packaging.
    canonical_reference = ROOT / "Jorros Backend/reference_data/philippine_locations.json"
    bundled_reference = ROOT / "Jorros Frontend/public/reference-data/philippine_locations.2026-Q3.json"
    if canonical_reference.read_bytes() != bundled_reference.read_bytes():
        raise ValueError("Frontend and backend address reference catalogues must match.")
    selected = {ROOT / name for name in ROOT_FILES}
    selected.update(ROOT / "Jorros Backend" / name for name in BACKEND_FILES)
    selected.update(ROOT / "Jorros Frontend" / name for name in FRONTEND_FILES)
    for directory, suffixes in DIRECTORIES.items():
        folder = ROOT / directory
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError(f"Required source directory missing or linked: {directory}")
        selected.update(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)

    for path in sorted(selected):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Required source file missing or linked: {relative}")
        if any(part.lower() in FORBIDDEN_PARTS for part in relative.parts):
            raise ValueError(f"Generated/private directory in source selection: {relative}")
        if path.name.lower() in {".env", ".env.local"} or path.suffix.lower() in {".bak", ".db", ".sqlite", ".xlsx", ".xls", ".pdf", ".zip", ".pyc"}:
            raise ValueError(f"Private/generated file in source selection: {relative}")
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2"}:
            contents = path.read_text(encoding="utf-16" if path.read_bytes().startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
            if any(pattern.search(contents) for pattern in SECRET_PATTERNS):
                raise ValueError(f"Potential credential in source file: {relative}")
            for match in SETTING_PATTERN.finditer(contents):
                value = match.group(1).strip("\"'")
                if value and not value.startswith(("replace-", "example-", "test-", "<")):
                    raise ValueError(f"Potential configured credential in source file: {relative}")
            for match in EMAIL_PATTERN.finditer(contents):
                local, domain = match.group().rsplit("@", 1)
                if domain not in {"example.com", "example.test", "farm.test"} and not (domain == "gmail.com" and local == "name"):
                    raise ValueError(f"Potential personal email in source file: {relative}")
        yield path, relative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    today = datetime.now(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d")
    output = args.output or ROOT.parent / f"Joross_Farm_Source_Release_{today}.zip"
    output = output.resolve()
    files = list(release_files())
    if not files:
        raise ValueError("The source selection is empty.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for path, relative in files:
                archive_path = f"{ARCHIVE_ROOT}/{relative.as_posix()}"
                archive.write(path, arcname=archive_path)
        with ZipFile(temporary) as archive:
            names = archive.namelist()
            if len(names) != len(files) or len(names) != len(set(names)) or archive.testzip() is not None:
                raise ValueError("The source ZIP failed its integrity check.")
            if any(any(part.lower() in FORBIDDEN_PARTS for part in Path(name).parts) for name in names):
                raise ValueError("The source ZIP contains a forbidden directory.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Created {output.name}: {len(files)} source files, {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
