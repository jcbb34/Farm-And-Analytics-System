"""Use the configured SQL Server connection for Alembic's canonical history."""

from alembic import context


def run_migrations_offline() -> None:
    # Rendering a revision range does not require pyodbc or a live database.
    context.configure(dialect_name="mssql", literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from app.core.database import Base, engine
    import app.models  # noqa: F401 - register every mapped table

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
