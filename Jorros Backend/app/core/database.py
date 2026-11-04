import logging
from threading import Lock

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


LOGGER = logging.getLogger("joross.database")


connection_string = (
    f"DRIVER={{{settings.db_driver}}};"
    f"SERVER={settings.db_server};"
    f"DATABASE={settings.db_name};"
    f"Trusted_Connection={settings.db_trusted_connection};"
    f"Encrypt=yes;"
    f"TrustServerCertificate="
    f"{settings.db_trust_server_certificate};"
)


connection_url = URL.create(
    "mssql+pyodbc",
    query={
        "odbc_connect": connection_string
    },
)


engine = create_engine(
    settings.database_url or connection_url,
    pool_pre_ping=True,
)


_last_epoch = None
_epoch_lock = Lock()

def ensure_recovery_epoch():
    global _last_epoch
    from app.core.recovery_runtime import session_epoch
    current = session_epoch()
    if current != _last_epoch:
        with _epoch_lock:
            if _last_epoch is not None and current != _last_epoch: engine.dispose()
            _last_epoch = current

class RecoveryAwareSession(Session):
    def __init__(self, *args, **kwargs):
        ensure_recovery_epoch()
        super().__init__(*args, **kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    class_=RecoveryAwareSession,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def check_database_connection():
    try:
        ensure_recovery_epoch()
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return True

    except Exception as error:
        LOGGER.exception("Database connection failed: %s", error)

        return False
