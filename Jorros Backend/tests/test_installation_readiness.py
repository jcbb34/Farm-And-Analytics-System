"""Read-only readiness checks must reject stale or partially upgraded databases."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import Column, Index, Integer, MetaData, String, Table, create_engine, event, select


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installation_readiness", ROOT / "scripts/check_installation.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
HEAD = "test-current-head"


def model_schema(*, omit_table=False, omit_column=False, unique=True):
    metadata = MetaData()
    if not omit_table:
        columns = [Column("id", Integer, primary_key=True), Column("idempotency_key", String(100), nullable=False)]
        if not omit_column:
            columns.append(Column("request_hash", String(64), nullable=False))
        Table("farm_creation_commands", metadata, *columns)
        Index("ix_command_key", metadata.tables["farm_creation_commands"].c.idempotency_key, unique=unique)
    records = Table("inventory_stock_records", metadata,
        Column("id", Integer, primary_key=True), Column("idempotency_key", String(100)))
    Index("ix_stock_key", records.c.idempotency_key, unique=unique,
          sqlite_where=records.c.idempotency_key.is_not(None))
    Table("test_records", metadata, Column("id", Integer, primary_key=True), Column("name", String(80)))
    return metadata


@pytest.fixture
def installation():
    engines = []
    def create(*, revisions=(HEAD,), omit_table=False, omit_column=False, unique=True, version_table=True):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        engines.append(engine)
        expected = model_schema()
        actual = model_schema(omit_table=omit_table, omit_column=omit_column, unique=unique)
        actual.create_all(engine)
        versions = Table("alembic_version", MetaData(), Column("version_num", String(80), primary_key=True))
        with engine.begin() as connection:
            if version_table:
                versions.create(connection)
                if revisions:
                    connection.execute(versions.insert(), [{"version_num": value} for value in revisions])
            connection.execute(actual.tables["test_records"].insert(), {"id": 1, "name": "Synthetic farm record"})
        return SimpleNamespace(engine=engine, expected=expected, actual=actual,
                               runtime=lambda: (engine, expected, HEAD, "Asia/Manila"))
    yield create
    for engine in engines:
        engine.dispose()


def result(state):
    with state.engine.connect() as connection:
        return checker.inspect_installation(connection, state.expected, HEAD)


def check_named(report, name):
    return next(check for check in report["checks"] if check["name"] == name)


def test_current_revision_and_complete_schema_pass(installation):
    report = result(installation())
    assert report["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["checks"])
    assert report["scope"] == "read_only_database_schema"


@pytest.mark.parametrize("revisions", [("old-head",), (), (HEAD, "divergent-head")])
def test_old_empty_and_multiple_database_revisions_fail_even_with_complete_tables(installation, revisions):
    report = result(installation(revisions=revisions))
    assert report["status"] == "failed"
    revision = check_named(report, "migration_revision")
    assert revision["status"] == "failed" and revision["expected"] == HEAD
    assert check_named(report, "required_tables_and_columns")["status"] == "passed"


def test_missing_alembic_table_cannot_report_a_verified_installation(installation):
    report = result(installation(version_table=False))
    assert report["status"] == "failed"
    assert check_named(report, "migration_revision")["actual"] == []


def test_current_revision_stamp_cannot_hide_a_missing_table(installation):
    report = result(installation(omit_table=True))
    assert check_named(report, "migration_revision")["status"] == "passed"
    assert check_named(report, "required_tables_and_columns")["missing_tables"] == ["farm_creation_commands"]
    assert report["status"] == "failed"


def test_current_revision_stamp_cannot_hide_a_missing_column(installation):
    report = result(installation(omit_column=True))
    assert report["status"] == "failed"
    assert check_named(report, "required_tables_and_columns")["missing_columns"] == ["farm_creation_commands.request_hash"]


def test_nonunique_retry_indexes_are_rejected(installation):
    report = result(installation(unique=False))
    assert report["status"] == "failed"
    keys = check_named(report, "workflow_unique_keys")["missing_unique_keys"]
    assert keys == ["farm_creation_commands(idempotency_key)", "inventory_stock_records(idempotency_key)"]


def test_checker_executes_no_writes_and_preserves_existing_records(installation):
    state = installation()
    statements = []
    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(state.engine, "before_cursor_execute", capture)
    assert result(state)["status"] == "passed"
    assert not any(statement.lstrip().split()[0].upper() in {
        "INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE", "MERGE", "REPLACE"
    } for statement in statements)
    with state.engine.connect() as connection:
        assert connection.execute(select(state.actual.tables["test_records"].c.name)).scalars().all() == ["Synthetic farm record"]


@pytest.mark.parametrize("revisions,exit_code", [((HEAD,), 0), (("old-head",), 1)])
def test_json_cli_returns_an_unambiguous_status_and_exit_code(installation, capsys, revisions, exit_code):
    state = installation(revisions=revisions)
    assert checker.main(["--json"], runtime_loader=state.runtime) == exit_code
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == ("passed" if exit_code == 0 else "failed")
    assert report["farm_timezone"] == "Asia/Manila"


def test_configuration_errors_fail_without_printing_environment_secrets(capsys):
    def fail():
        raise RuntimeError("Synthetic private password must not be printed")
    assert checker.main(["--json"], runtime_loader=fail) == 2
    output = capsys.readouterr().out
    assert "private password" not in output
    assert json.loads(output)["error_code"] == "configuration_unavailable"


def test_connection_failure_does_not_print_driver_connection_details(installation, capsys):
    state = installation()
    with patch.object(state.engine, "connect", side_effect=RuntimeError("Synthetic secret connection string")):
        assert checker.main(["--json"], runtime_loader=state.runtime) == 2
    output = capsys.readouterr().out
    assert "secret connection" not in output
    assert json.loads(output)["error_code"] == "database_connection_failed"


def test_loading_actual_runtime_resolves_source_head_without_opening_a_database(monkeypatch, tmp_path):
    from app.core.database import engine
    monkeypatch.chdir(tmp_path)
    with patch.object(engine, "connect", side_effect=AssertionError("Must not connect while loading runtime")):
        actual_engine, metadata, head, timezone_name = checker.load_runtime()
    assert actual_engine is engine and metadata.tables
    assert head == "e5f6a7b8c9d0" and timezone_name == "Asia/Manila"


def test_registered_application_schema_and_workflow_keys_pass_in_an_isolated_database():
    from app.core.database import Base
    import app.models  # noqa: F401
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        versions = Table("alembic_version", MetaData(), Column("version_num", String(80), primary_key=True))
        with engine.begin() as connection:
            versions.create(connection)
            connection.execute(versions.insert(), {"version_num": HEAD})
        with engine.connect() as connection:
            report = checker.inspect_installation(connection, Base.metadata, HEAD)
        assert report["status"] == "passed", report
        assert check_named(report, "required_tables_and_columns")["required_table_count"] == len(Base.metadata.tables)
        assert check_named(report, "workflow_unique_keys")["missing_unique_keys"] == []
    finally:
        engine.dispose()
