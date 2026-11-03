import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
    connection_url,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
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
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return True

    except Exception as error:
        LOGGER.exception("Database connection failed: %s", error)

        return False
