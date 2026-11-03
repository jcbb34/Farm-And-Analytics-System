"""Read-only local database/schema verification. Never applies migrations or edits data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from sqlalchemy import UniqueConstraint, column, inspect, select, table


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SAFETY_TABLES = {
    "farm_creation_commands", "inventory_stock_records", "resource_usages",
    "task_submissions", "farm_activities", "employees", "task_evidence",
}


def _columns(values):
    return tuple(sorted(str(value).casefold() for value in values if value is not None))


def _required_unique_keys(metadata):
    keys = {}
    for model_table in metadata.tables.values():
        if model_table.name not in SAFETY_TABLES:
            continue
        signatures = {_columns(col.name for col in item.columns)
                      for item in model_table.indexes if item.unique}
        signatures.update(_columns(col.name for col in item.columns)
                          for item in model_table.constraints if isinstance(item, UniqueConstraint))
        keys[model_table.name] = {signature for signature in signatures if signature}
    return keys


def _reflected_unique_keys(inspector, table_name, dialect_name):
    keys = {_columns(item.get("column_names") or [])
            for item in inspector.get_indexes(table_name) if item.get("unique")}
    try:
        constraints = inspector.get_unique_constraints(table_name)
    except NotImplementedError:
        # MSSQL exposes UNIQUE constraints as unique indexes. SQLAlchemy's
        # MSSQL/pyodbc dialect intentionally has no get_unique_constraints()
        # implementation; get_indexes() includes their backing indexes.
        if dialect_name != "mssql":
            raise
        constraints = []
    keys.update(_columns(item.get("column_names") or []) for item in constraints)
    return keys


def inspect_installation(connection, metadata, expected_revision, *, progress=None):
    """Inspect migration identity, required columns and retry/workflow unique keys.

    This uses a Core connection and metadata reads only. It does not create a
    Session, seed users, start schedulers, execute DDL or change farm records.
    """
    if not metadata.tables or not str(expected_revision or "").strip():
        raise ValueError("Source schema and a single expected revision are required.")
    def mark(stage, table_name=None):
        if progress is not None:
            progress(stage, table_name)
    mark("read_table_list")
    inspector = inspect(connection)
    actual_names = {name.casefold(): name for name in inspector.get_table_names()}
    versions = []
    revision_table = actual_names.get("alembic_version")
    if revision_table:
        mark("read_migration_revision", "alembic_version")
        version_columns = {item["name"].casefold(): item["name"] for item in inspector.get_columns(revision_table)}
        if "version_num" in version_columns:
            statement = select(table(revision_table, column(version_columns["version_num"])).c[version_columns["version_num"]])
            versions = sorted(str(value).strip() for value in connection.execute(statement).scalars())
    revision_ok = versions == [expected_revision]
    checks = [dict(name="migration_revision", status="passed" if revision_ok else "failed",
                   expected=expected_revision, actual=versions)]

    missing_tables, missing_columns = [], []
    for model_table in sorted(metadata.tables.values(), key=lambda item: item.name):
        actual_name = actual_names.get(model_table.name.casefold())
        if actual_name is None:
            missing_tables.append(model_table.name)
            continue
        mark("read_columns", model_table.name)
        actual_columns = {item["name"].casefold() for item in inspector.get_columns(actual_name)}
        missing_columns.extend(f"{model_table.name}.{col.name}" for col in model_table.columns
                               if col.name.casefold() not in actual_columns)
    checks.append(dict(name="required_tables_and_columns",
                       status="failed" if missing_tables or missing_columns else "passed",
                       required_table_count=len(metadata.tables), missing_tables=missing_tables,
                       missing_columns=sorted(missing_columns)))

    missing_keys = []
    for model_name, expected_keys in sorted(_required_unique_keys(metadata).items()):
        actual_name = actual_names.get(model_name.casefold())
        actual_keys = set()
        if actual_name:
            mark("read_unique_keys", model_name)
            actual_keys = _reflected_unique_keys(inspector, actual_name, connection.dialect.name)
        missing_keys.extend(f"{model_name}({', '.join(columns)})" for columns in sorted(expected_keys - actual_keys))
    checks.append(dict(name="workflow_unique_keys", status="failed" if missing_keys else "passed",
                       missing_unique_keys=missing_keys))
    return dict(status="passed" if all(item["status"] == "passed" for item in checks) else "failed",
                scope="read_only_database_schema", checks=checks,
                next_step="Complete the device, workflow and recovery acceptance checks in the setup notes.")


def safe_error_details(error, stage):
    """Report diagnostic codes/types, never connection strings or SQL parameters."""
    cause = getattr(error, "orig", None) or error
    sqlstate = None
    native_codes = set()
    for arg in getattr(cause, "args", ()):
        if not isinstance(arg, str):
            continue
        if re.fullmatch(r"(?:[0-9]{2}[0-9A-Z]{3}|IM[0-9]{3}|HY[0-9A-Z]{3})", arg):
            sqlstate = sqlstate or arg
        states = re.findall(r"\[((?:[0-9]{2}[0-9A-Z]{3}|IM[0-9]{3}|HY[0-9A-Z]{3}))\]", arg)
        if states:
            sqlstate = sqlstate or states[0]
        # Only recognized SQL Server diagnostic numbers are exposed.
        native_codes.update(int(value) for value in re.findall(r"\((\d{1,5})\)", arg)
                            if int(value) in {207, 208, 229, 916, 4060, 4064, 18456})
    hint = "Send the failure stage, error type and diagnostic codes shown here so the remaining cause can be identified."
    category = "database_connection_failed" if stage == "database_connection" else "database_inspection_failed"
    if sqlstate in {"IM002", "IM003", "IM014"}:
        category, hint = "odbc_driver_unavailable", "Check that DB_DRIVER matches an installed SQL Server ODBC driver compatible with this Python installation."
    elif native_codes & {4060, 4064, 916}:
        category, hint = "database_access_failed", "Check DB_NAME and whether the Windows/login account running this command can open that database in SQL Server Management Studio."
    elif sqlstate == "28000" or 18456 in native_codes:
        category, hint = "database_login_failed", "Check the configured authentication and the database access of the account running this command."
    elif 229 in native_codes:
        category, hint = "database_permission_denied", "The database rejected a read. Have the database administrator review access to the indicated schema/metadata."
    elif sqlstate in {"HYT00", "HYT01"}:
        category, hint = "database_timeout", "The connection or metadata query timed out. Check the configured SQL Server instance, service and network availability."
    elif sqlstate and sqlstate.startswith("08"):
        category, hint = "database_connection_failed", "Check the configured SQL Server instance, service, network and connection security settings."
    elif isinstance(cause, NotImplementedError):
        category, hint = "unsupported_metadata_inspection", "The database dialect cannot perform this inspection. Send the stage and error type so the checker can be corrected."
    elif isinstance(cause, (TypeError, KeyError, AttributeError, ValueError)):
        category, hint = "checker_metadata_error", "The checker could not process metadata at this stage. Send these diagnostic lines; this does not establish that the database is unavailable."
    return dict(error_code=category, error_type=type(cause).__name__, sqlstate=sqlstate,
                sql_server_codes=sorted(native_codes), hint=hint)


def load_runtime():
    # Resolve .env and Alembic paths from this backend, even when launched from
    # the project root. No environment values are printed.
    os.chdir(BACKEND_ROOT)
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.core.database import Base, engine
    from app.core.farm_time import farm_timezone, farm_timezone_name
    import app.models  # noqa: F401 - register all mapped tables

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise ValueError("A single source migration head is required.")
    farm_timezone()  # Uses the application's Windows-compatible timezone rule.
    return engine, Base.metadata, heads[0], farm_timezone_name()


def print_result(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    print("Joross Farm local installation check (read-only)")
    for check in result.get("checks", []):
        print(f"{check['status'].upper()}: {check['name']}")
        if check["name"] == "migration_revision":
            print(f"  Expected: {check['expected']}; database: {', '.join(check['actual']) or 'no revision recorded'}")
        for key in ("missing_tables", "missing_columns", "missing_unique_keys"):
            for value in check.get(key, []):
                print(f"  Missing: {value}")
    if result.get("message"):
        print(result["message"])
    if result.get("failure_stage"):
        print(f"Failure stage: {result['failure_stage']}")
    if result.get("failed_table"):
        print(f"Table: {result['failed_table']}")
    if result.get("error_code"):
        print(f"Error code: {result['error_code']}")
    if result.get("error_type"):
        print(f"Error type: {result['error_type']}")
    if result.get("sqlstate"):
        print(f"SQLSTATE: {result['sqlstate']}")
    if result.get("sql_server_codes"):
        print("SQL Server codes: " + ", ".join(str(value) for value in result["sql_server_codes"]))
    if result.get("hint"):
        print("Next step: " + result["hint"])
    print(f"Result: {result['status'].upper()} ({result['scope']})")
    if result.get("next_step"):
        print(result["next_step"])


def main(argv=None, *, runtime_loader=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result without credentials or farm records.")
    args = parser.parse_args(argv)
    try:
        engine, metadata, expected_revision, timezone_name = (runtime_loader or load_runtime)()
    except Exception:
        result = dict(status="failed", scope="configuration", error_code="configuration_unavailable",
                      message="Could not load the backend configuration or migration graph. Check the complete source, dependencies and local environment file.")
        print_result(result, args.json)
        return 2
    stage = dict(name="database_connection", table=None)
    connection_checks = []
    def progress(name, table_name=None):
        stage.update(name=name, table=table_name)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1").scalar_one()
            connection_checks.append(dict(name="database_connection", status="passed"))
            result = inspect_installation(connection, metadata, expected_revision, progress=progress)
            result["checks"] = connection_checks + result["checks"]
            # Closing this read-only connection rolls back its implicit read transaction.
    except Exception as error:
        result = dict(status="failed", scope="read_only_database_schema", checks=connection_checks,
                      failure_stage=stage["name"], failed_table=stage["table"],
                      message="The installation check stopped before schema verification completed.",
                      **safe_error_details(error, stage["name"]))
        print_result(result, args.json)
        return 2
    result["farm_timezone"] = timezone_name
    if result["status"] != "passed":
        result["message"] = "Database verification is incomplete. Review the missing revision/schema requirements using the upgrade instructions; this check changed no data."
    print_result(result, args.json)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
