"""Inspect a recovery ZIP or restore it into a separate empty database."""
import argparse
import json
from pathlib import Path
import re
import sys
from zipfile import BadZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.services.recovery_service import RecoveryError, inspect_recovery_package, restore_recovery_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--target-database', help='Existing, separate SQL Server recovery database; never the farm database.')
    target.add_argument('--sqlite-file', type=Path, help='Isolated local database for a recovery drill.')
    parser.add_argument('--evidence-directory', type=Path)
    parser.add_argument('--initialize-empty-target', action='store_true', help='Create the verified schema only in a database with no tables.')
    parser.add_argument('--apply', action='store_true', help='Restore records and files after validation. Default is inspection/validation only.')
    args = parser.parse_args()
    if not args.target_database and not args.sqlite_file:
        if args.apply:
            parser.error('--apply requires an explicit recovery target.')
        data = inspect_recovery_package(args.package)
        print(json.dumps({'valid': True, 'revision': data['database']['alembic_revision'],
                          'tables': data['table_count'], 'rows': data['row_count'],
                          'evidence_files': len(data['recovery']['evidence_files'])}))
        return
    if not args.evidence_directory:
        parser.error('A separate --evidence-directory is required for target validation or restoration.')
    if args.sqlite_file:
        engine = create_engine(URL.create('sqlite+pysqlite', database=str(args.sqlite_file.resolve())))
    else:
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_ -]{0,127}', args.target_database):
            parser.error('The recovery database name contains unsupported characters.')
        if args.target_database.casefold() == settings.db_name.casefold():
            parser.error('The running farm database cannot be a recovery target.')
        connection_string = (f'DRIVER={{{settings.db_driver}}};SERVER={settings.db_server};'
                             f'DATABASE={args.target_database};Trusted_Connection={settings.db_trusted_connection};'
                             f'Encrypt=yes;TrustServerCertificate={settings.db_trust_server_certificate};')
        engine = create_engine(URL.create('mssql+pyodbc', query={'odbc_connect': connection_string}), pool_pre_ping=True)
    try:
        print(json.dumps(restore_recovery_package(args.package, engine, args.evidence_directory,
                          apply=args.apply, initialize=args.initialize_empty_target)))
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except RecoveryError as error:
        print('Recovery refused: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except (SQLAlchemyError, OSError, ValueError, BadZipFile):
        # Database exceptions may contain private values or connection details.
        print('Recovery failed. No replacement of existing farm records was attempted; inspect the separate recovery target.', file=sys.stderr)
        sys.exit(1)
