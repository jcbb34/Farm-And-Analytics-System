"""Checked recovery archives and restoration into an empty, separate database."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import shutil
import tempfile
from datetime import date, datetime, time
from decimal import Decimal, DecimalException
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from sqlalchemy import Column, MetaData, String, Table, func, inspect, select, text

from app.core.config import settings
from app.services.evidence_storage import get_evidence_storage


MAX_PACKAGE_BYTES = 4 * 1024**3
MAX_JSON_BYTES = 256 * 1024**2
SAFE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,139}\Z")


class RecoveryError(ValueError):
    pass


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _safe_file(name):
    if not isinstance(name, str) or not SAFE_FILE.fullmatch(name):
        raise RecoveryError('Invalid evidence filename in recovery package.')
    return name


def write_recovery_package(payload, json_path: Path, package_path: Path):
    """Read only the evidence referenced by the transaction's database snapshot."""
    if not payload.get('database', {}).get('alembic_revision'):
        raise RecoveryError('The database migration revision is missing; check alembic current before creating a recovery backup.')
    storage = get_evidence_storage()
    files = {}
    for row in payload.get('tables', {}).get('task_evidence', {}).get('rows', []):
        if str(row.get('status', '')).lower() == 'deleted':
            continue
        for column in ('storage_identifier', 'thumbnail_storage_identifier'):
            name = _safe_file(row.get(column))
            try:
                source = storage.path_for_response(name)
            except (OSError, ValueError) as exc:
                raise RecoveryError('A referenced evidence file is missing or unavailable. Restore the file before creating a backup.') from exc
            if source.is_symlink() or not source.resolve().is_relative_to(storage.root.resolve()):
                raise RecoveryError('An evidence file is outside the configured storage directory.')
            try:
                raw = source.read_bytes()
            except OSError as exc:
                raise RecoveryError('A referenced evidence file is missing or unavailable. Restore the file before creating a backup.') from exc
            digest = _digest(raw)
            if column == 'storage_identifier' and digest != row.get('sha256'):
                raise RecoveryError('A referenced evidence photo failed its checksum check.')
            files[name] = {'name': name, 'size': len(raw), 'sha256': digest}
    payload['recovery'] = {'version': 1, 'evidence_files': list(files.values())}
    database_raw = _json_bytes(payload)
    if len(database_raw) > MAX_JSON_BYTES or len(database_raw) + sum(f['size'] for f in files.values()) > MAX_PACKAGE_BYTES:
        raise RecoveryError('This recovery package exceeds the supported size limit.')
    json_path.write_bytes(database_raw)
    with ZipFile(package_path, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('database.json', database_raw)
        archive.writestr('manifest.json', _json_bytes({'format': 'joross-recovery', 'version': 1,
                                                    'database_sha256': _digest(database_raw)}))
        for name, info in files.items():
            raw = storage.path_for_response(name).read_bytes()
            if len(raw) != info['size'] or _digest(raw) != info['sha256']:
                raise RecoveryError('Evidence changed while the backup was being created; retry the backup.')
            archive.writestr('evidence/' + name, raw)


def _read_package(archive, *, expected_database_sha256=None):
    try:
        return _read_package_contents(archive, expected_database_sha256=expected_database_sha256)
    except RecoveryError:
        raise
    except (BadZipFile, OSError, KeyError, TypeError, AttributeError, ValueError, DecimalException) as exc:
        raise RecoveryError('Recovery package could not be read or has invalid metadata.') from exc


def _read_package_contents(archive, *, expected_database_sha256=None):
    members = archive.infolist()
    names = [m.filename for m in members]
    if len(names) != len(set(names)) or len(names) > 200_000:
        raise RecoveryError('Recovery package has duplicate entries or too many files.')
    if sum(m.file_size for m in members) > MAX_PACKAGE_BYTES:
        raise RecoveryError('Recovery package exceeds the supported size limit.')
    by_name = {m.filename: m for m in members}
    if not {'database.json', 'manifest.json'}.issubset(by_name):
        raise RecoveryError('Recovery package is missing its database or manifest.')
    if any((m.external_attr >> 16) & 0o170000 == 0o120000 for m in members):
        raise RecoveryError('Recovery packages cannot contain symbolic links.')
    if by_name['database.json'].file_size > MAX_JSON_BYTES or by_name['manifest.json'].file_size > 4096:
        raise RecoveryError('Recovery metadata exceeds its supported size limit.')
    raw = archive.read('database.json')
    manifest = json.loads(archive.read('manifest.json'))
    if manifest.get('format') != 'joross-recovery' or manifest.get('version') != 1:
        raise RecoveryError('Unsupported recovery package format.')
    digest = _digest(raw)
    if digest != manifest.get('database_sha256') or (expected_database_sha256 and digest != expected_database_sha256):
        raise RecoveryError('The recovery database failed its checksum check.')
    payload = json.loads(raw)
    if payload.get('format_version') != '1.0' or payload.get('recovery', {}).get('version') != 1:
        raise RecoveryError('Unsupported database backup format.')
    files = payload['recovery'].get('evidence_files', [])
    expected_names = {'database.json', 'manifest.json'}
    for info in files:
        name = 'evidence/' + _safe_file(info.get('name'))
        if name in expected_names or name not in by_name or by_name[name].file_size != info.get('size'):
            raise RecoveryError('Invalid evidence manifest.')
        expected_names.add(name)
        digestor = hashlib.sha256()
        with archive.open(name) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digestor.update(chunk)
        if digestor.hexdigest() != info.get('sha256'):
            raise RecoveryError('A recovery evidence file failed its checksum check.')
    if set(names) != expected_names:
        raise RecoveryError('Recovery package contains unexpected files.')
    tables = payload.get('tables')
    if not isinstance(tables, dict) or not tables:
        raise RecoveryError('Recovery database contains no table metadata.')
    count = 0
    for table in tables.values():
        rows = table.get('rows')
        columns = table.get('columns')
        if not isinstance(rows, list) or not isinstance(columns, list) or len(set(columns)) != len(columns):
            raise RecoveryError('Invalid recovery table metadata.')
        if table.get('row_count') != len(rows) or any(set(row) != set(columns) for row in rows):
            raise RecoveryError('Recovery row counts or columns do not match the manifest.')
        for row in rows:
            for value in row.values():
                _value(value)
        count += len(rows)
    if payload.get('table_count') != len(tables) or payload.get('row_count') != count:
        raise RecoveryError('Recovery totals do not match the database snapshot.')
    revision = payload.get('database', {}).get('alembic_revision')
    if tables.get('alembic_version', {}).get('rows') != [{'version_num': revision}] or not revision:
        raise RecoveryError('The backup migration revision does not match its version record.')
    evidence = {info['name']: info for info in files}
    referenced = set()
    for row in tables.get('task_evidence', {}).get('rows', []):
        if str(row.get('status', '')).lower() == 'deleted':
            continue
        original = _safe_file(row.get('storage_identifier'))
        thumbnail = _safe_file(row.get('thumbnail_storage_identifier'))
        referenced.update((original, thumbnail))
        if (original not in evidence or thumbnail not in evidence or evidence[original]['sha256'] != row.get('sha256')
                or evidence[original]['size'] != row.get('size_bytes')):
            raise RecoveryError('Evidence references do not match the recovery manifest.')
    if referenced != set(evidence):
        raise RecoveryError('Recovery evidence does not match the database snapshot.')
    return payload


def inspect_recovery_package(path, *, expected_database_sha256=None):
    try:
        with ZipFile(path) as archive:
            return _read_package(archive, expected_database_sha256=expected_database_sha256)
    except (BadZipFile, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RecoveryError('Recovery package could not be read or has invalid metadata.') from exc


def _value(value):
    if not isinstance(value, dict):
        if isinstance(value, float) and not math.isfinite(value):
            raise RecoveryError("Non-finite number in recovery data.")
        return value
    kind, raw = value.get('__type__'), value.get('value')
    decoders = {'datetime': datetime.fromisoformat, 'date': date.fromisoformat,
                'time': time.fromisoformat, 'decimal': Decimal,
                'bytes': lambda item: base64.b64decode(item, validate=True), 'string': str}
    if kind not in decoders or set(value) != {'__type__', 'value'}:
        raise RecoveryError('Unsupported value in recovery database.')
    decoded = decoders[kind](raw)
    if isinstance(decoded, Decimal) and not decoded.is_finite():
        raise RecoveryError('Non-finite number in recovery data.')
    return decoded


def _ordered_rows(table, rows):
    self_refs = [fk for fk in table.foreign_keys if fk.column.table.name == table.name]
    if not self_refs:
        return rows
    remaining, ordered = list(rows), []
    while remaining:
        pending = {fk.column.name: {row[fk.column.name] for row in remaining} for fk in self_refs}
        ready = [row for row in remaining if all(row.get(fk.parent.name) is None or
                 row.get(fk.parent.name) not in pending[fk.column.name] or
                 row.get(fk.parent.name) == row.get(fk.column.name) for fk in self_refs)]
        if not ready:
            raise RecoveryError('Recovery rows contain a cyclic self-reference.')
        ordered.extend(ready)
        remaining = [row for row in remaining if row not in ready]
    return ordered


def restore_recovery_package(path, target_engine, evidence_directory, *, apply=False, initialize=False):
    """Validate by default. Apply only to an empty matching schema, never replace rows."""
    destination = Path(evidence_directory).resolve()
    configured_evidence = get_evidence_storage().root.resolve()
    if destination == configured_evidence or destination.is_relative_to(configured_evidence) or configured_evidence.is_relative_to(destination):
        raise RecoveryError('Choose a separate recovery evidence directory, outside the running application storage.')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise RecoveryError('Recovery evidence directory must be absent or empty.')
    installed, stage = False, None
    try:
        with ZipFile(path) as archive:
            payload = _read_package(archive)
            revision = payload.get('database', {}).get('alembic_revision')
            if not revision:
                raise RecoveryError('The backup migration revision is missing.')
            with target_engine.execution_options(isolation_level="SERIALIZABLE").begin() as connection:
                dialect = connection.dialect.name
                if dialect == 'mssql':
                    actual_name = connection.scalar(text('SELECT DB_NAME()'))
                    protected = {str(settings.db_name).casefold(), str(payload['database'].get('name', '')).casefold()}
                    if str(actual_name).casefold() in protected:
                        raise RecoveryError('Restoration into the running or source database is prohibited.')
                    connection.exec_driver_sql('SET XACT_ABORT ON')
                elif dialect == 'sqlite':
                    source_path = payload['database'].get('sqlite_source_path')
                    target_path = target_engine.url.database
                    if source_path and target_path and Path(target_path).resolve() == Path(source_path).resolve():
                        raise RecoveryError('Restoration into the source database is prohibited.')
                else:
                    raise RecoveryError('Recovery supports SQL Server and isolated SQLite validation databases.')
                if dialect == 'sqlite':
                    connection.exec_driver_sql('PRAGMA foreign_keys=ON')
                    if not connection.scalar(text('PRAGMA foreign_keys')):
                        raise RecoveryError('Foreign key validation could not be enabled.')
                    if not connection.connection.driver_connection.in_transaction:
                        connection.exec_driver_sql('BEGIN IMMEDIATE')
                inspector = inspect(connection)
                names = set(inspector.get_table_names())
                tables = payload['tables']
                if initialize:
                    from alembic.config import Config
                    from alembic.script import ScriptDirectory
                    from app.core.database import Base
                    import app.models  # Register the complete application schema.
                    backend = Path(__file__).resolve().parents[2]
                    config = Config(str(backend / 'alembic.ini'))
                    config.set_main_option('script_location', str(backend / 'migrations'))
                    if ScriptDirectory.from_config(config).get_current_head() != revision:
                        raise RecoveryError('Use source matching the backup Alembic head before initializing a recovery target.')
                    if names:
                        raise RecoveryError('Initialization requires a new database with no existing tables.')
                    expected = set(Base.metadata.tables) - {'system_backups'}
                    if set(tables) - {'alembic_version'} != expected or any(
                        set(tables[name]['columns']) != set(Base.metadata.tables[name].columns.keys()) for name in expected):
                        raise RecoveryError('The backup schema does not match this source version.')
                    if not apply:
                        return {'tables': len(expected), 'rows': sum(t['row_count'] for name, t in tables.items() if name != 'alembic_version'),
                                'evidence_files': len(payload['recovery']['evidence_files']), 'revision': revision,
                                'applied': False, 'initialize': True}
                    Base.metadata.create_all(connection)
                    version = Table('alembic_version', MetaData(), Column('version_num', String(32), primary_key=True))
                    version.create(connection)
                    connection.execute(version.insert().values(version_num=revision))
                    names = set(inspect(connection).get_table_names())
                if set(tables) - names:
                    raise RecoveryError('The target database schema is incomplete. Prepare the matching schema first.')
                if 'alembic_version' not in names or connection.scalars(text('SELECT version_num FROM alembic_version')).all() != [revision]:
                    raise RecoveryError('The recovery target must already have the same Alembic revision as the backup; no stamping is performed.')
                metadata = MetaData()
                metadata.reflect(bind=connection)
                if dialect == 'mssql' and connection.scalar(text(
                    'SELECT (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled = 1) + '
                    '(SELECT COUNT(*) FROM sys.check_constraints WHERE is_disabled = 1)')):
                    raise RecoveryError('The recovery schema has disabled constraints. Enable validation before restoring.')
                for name in names - {'alembic_version'}:
                    if connection.scalar(select(func.count()).select_from(metadata.tables[name])):
                        raise RecoveryError('Recovery target contains records. Use a separate empty database.')
                if names - {'system_backups', 'alembic_version'} != set(tables) - {'alembic_version'}:
                    raise RecoveryError('Target and backup table sets differ.')
                for name, data in tables.items():
                    if set(data['columns']) != set(metadata.tables[name].columns.keys()):
                        raise RecoveryError('Target and backup columns differ: ' + name)
                result = {'tables': len(tables) - ('alembic_version' in tables),
                          'rows': sum(t['row_count'] for name, t in tables.items() if name != 'alembic_version'),
                          'evidence_files': len(payload['recovery']['evidence_files']), 'revision': revision, 'applied': apply}
                if not apply:
                    return result
                destination.parent.mkdir(parents=True, exist_ok=True)
                stage = Path(tempfile.mkdtemp(prefix='.joross-recovery-', dir=destination.parent))
                for info in payload['recovery']['evidence_files']:
                    name = _safe_file(info['name'])
                    with archive.open('evidence/' + name) as source, (stage / name).open('wb') as target:
                        shutil.copyfileobj(source, target)
                for table in metadata.sorted_tables:
                    if table.name not in tables or table.name == 'alembic_version':
                        continue
                    rows = [{key: _value(value) for key, value in row.items()} for row in tables[table.name]['rows']]
                    rows = _ordered_rows(table, rows)
                    # SQLAlchemy's MSSQL dialect manages IDENTITY_INSERT for explicit primary keys.
                    for row in rows:
                        connection.execute(table.insert().values(**row))
                    if connection.scalar(select(func.count()).select_from(table)) != len(rows):
                        raise RecoveryError('Restored row count mismatch: ' + table.name)
                if destination.exists():
                    destination.rmdir()  # Only the verified empty recovery directory.
                stage.rename(destination)
                stage, installed = None, True
            return result
    except Exception:
        if installed:
            shutil.rmtree(destination)
        raise
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
