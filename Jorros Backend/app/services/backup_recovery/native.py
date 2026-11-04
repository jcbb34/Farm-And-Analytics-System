"""SQL Server commands use dedicated master/AUTOCOMMIT connections."""

from contextlib import contextmanager
from pathlib import Path
import re
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.core.config import settings
from .crypto import BackupError


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9_][A-Za-z0-9_ -]{0,127}", value
    ):
        raise BackupError("Unsupported database name for recovery.")
    return "[" + value + "]"


def literal(value):
    return "N'" + str(value).replace("'", "''") + "'"


class SqlServer:
    def __init__(self, engine):
        self.engine = engine
        self.database = engine.url.database or settings.db_name
        if "odbc_connect" in engine.url.query:
            found = re.search(
                r"(?i)(?:^|;)DATABASE=([^;]+)", engine.url.query["odbc_connect"]
            )
            if found:
                self.database = found[1].strip("{}")

    def url_for(self, name):
        identifier(name)
        url = self.engine.url
        if "odbc_connect" in url.query:
            connection, count = re.subn(
                r"(?i)(^|;)DATABASE=[^;]*",
                lambda m: m[1] + "DATABASE=" + name,
                url.query["odbc_connect"],
            )
            if not count:
                connection = connection.rstrip(";") + ";DATABASE=" + name + ";"
            return url.update_query_dict({"odbc_connect": connection})
        return url.set(database=name)

    @contextmanager
    def admin(self):
        if self.engine.dialect.name != "mssql":
            raise BackupError(
                "Native BAK operations require your SQL Server installation."
            )
        engine = create_engine(
            self.url_for("master"), poolclass=NullPool, pool_pre_ping=True
        )
        try:
            with engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                yield connection
        finally:
            engine.dispose()

    @staticmethod
    def command(connection, statement, parameters=()):
        cursor = connection.connection.driver_connection.cursor()
        rows = []
        try:
            cursor.execute(statement, parameters)
            while True:
                if cursor.description:
                    rows.extend(cursor.fetchall())
                if not cursor.nextset():
                    break
            return rows
        finally:
            cursor.close()

    def probe(self):
        with self.admin() as c:
            data = (
                c.execute(
                    text(
                        "SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) version, CAST(SERVERPROPERTY('Edition') AS nvarchar(128)) edition, IS_SRVROLEMEMBER('sysadmin') admin, IS_SRVROLEMEMBER('dbcreator') creator"
                    )
                )
                .mappings()
                .one()
            )
            c.exec_driver_sql("USE " + identifier(self.database)).close()
            can_backup = c.scalar(
                text("SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','BACKUP DATABASE')")
            )
        return {
            "available": bool(can_backup or data["admin"]),
            "restore_available": bool(data["admin"] or data["creator"]),
            "version": data["version"],
            "edition": data["edition"],
        }

    def exists(self, name):
        with self.admin() as c:
            return c.scalar(text("SELECT DB_ID(:name)"), {"name": name}) is not None

    def backup(self, path):
        if Path(path).exists():
            raise BackupError("The native destination already exists.")
        with self.admin() as c:
            self.command(
                c,
                "BACKUP DATABASE "
                + identifier(self.database)
                + " TO DISK = ? WITH COPY_ONLY, CHECKSUM, INIT, STOP_ON_ERROR",
                (str(Path(path).resolve()),),
            )
        if not Path(path).is_file() or not Path(path).stat().st_size:
            raise BackupError(
                "SQL Server created no accessible BAK. Check the shared backup folder and service permissions."
            )
        self.verify(path)

    def verify(self, path):
        with self.admin() as c:
            self.command(
                c,
                "RESTORE VERIFYONLY FROM DISK = ? WITH CHECKSUM, STOP_ON_ERROR",
                (str(Path(path).resolve()),),
            )

    def target_engine(self, name):
        return create_engine(self.url_for(name), poolclass=NullPool, pool_pre_ping=True)

    def create_empty(self, name):
        if not name.startswith("JorossRecovery_"):
            raise BackupError("Only generated recovery databases can be created.")
        with self.admin() as c:
            if c.scalar(text("SELECT DB_ID(:name)"), {"name": name}) is not None:
                raise BackupError("Recovery database already exists.")
            c.exec_driver_sql("CREATE DATABASE " + identifier(name)).close()

    def restore(self, path, name, source_version):
        if not name.startswith("JorossRecovery_"):
            raise BackupError("Native restore requires a generated recovery database.")
        with self.admin() as c:
            if c.scalar(text("SELECT DB_ID(:name)"), {"name": name}) is not None:
                raise BackupError("Recovery database already exists.")
            version = str(c.scalar(text("SELECT SERVERPROPERTY('ProductVersion')")))
            if int(version.split(".")[0]) < int(str(source_version).split(".")[0]):
                raise BackupError(
                    "This SQL Server is older than the server that created the BAK."
                )
            files = (
                c.exec_driver_sql(
                    "RESTORE FILELISTONLY FROM DISK = ?", (str(Path(path).resolve()),)
                )
                .mappings()
                .all()
            )
            base = c.scalar(text("SELECT SERVERPROPERTY('InstanceDefaultDataPath')"))
            if not base or not files or len(files) > 64:
                raise BackupError(
                    "SQL Server did not provide safe recovery file locations."
                )
            moves = []
            for i, file in enumerate(files):
                if file["Type"] not in ("D", "L"):
                    raise BackupError(
                        "Only standard SQL data and log files are supported."
                    )
                name_on_disk = (
                    str(base).rstrip("/\\")
                    + ("\\" if "\\" in str(base) else "/")
                    + name
                    + "_"
                    + str(i)
                    + (".ldf" if file["Type"] == "L" else ".mdf")
                )
                moves.append(
                    "MOVE "
                    + literal(file["LogicalName"])
                    + " TO "
                    + literal(name_on_disk)
                )
            self.command(
                c,
                "RESTORE DATABASE "
                + identifier(name)
                + " FROM DISK = "
                + literal(Path(path).resolve())
                + " WITH CHECKSUM, RECOVERY, "
                + ", ".join(moves),
            )
        self.check(name)

    def check(self, name):
        with self.admin() as c:
            if self.command(
                c,
                "DBCC CHECKDB ("
                + identifier(name)
                + ") WITH NO_INFOMSGS, ALL_ERRORMSGS",
            ):
                raise BackupError(
                    "SQL Server reported an integrity problem in the recovery copy."
                )

    def rename(self, old, new):
        with self.admin() as c:
            if c.scalar(text("SELECT DB_ID(:name)"), {"name": new}) is not None:
                raise BackupError("The destination database already exists.")
            c.exec_driver_sql(
                "ALTER DATABASE "
                + identifier(old)
                + " SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            ).close()
            try:
                c.exec_driver_sql(
                    "ALTER DATABASE "
                    + identifier(old)
                    + " MODIFY NAME = "
                    + identifier(new)
                ).close()
            except Exception:
                c.exec_driver_sql(
                    "ALTER DATABASE " + identifier(old) + " SET MULTI_USER"
                ).close()
                raise
            c.exec_driver_sql(
                "ALTER DATABASE " + identifier(new) + " SET MULTI_USER"
            ).close()

    def drop_recovery(self, name):
        if (
            not name.startswith("JorossRecovery_")
            or name.casefold() == self.database.casefold()
        ):
            raise BackupError(
                "Only unused generated recovery databases can be removed."
            )
        with self.admin() as c:
            c.exec_driver_sql(
                "IF DB_ID("
                + literal(name)
                + ") IS NOT NULL BEGIN ALTER DATABASE "
                + identifier(name)
                + " SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE "
                + identifier(name)
                + "; END"
            ).close()
