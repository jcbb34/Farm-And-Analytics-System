from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


# Smart Import can touch most operational farm tables in one transaction.
# Background automation uses the same guard so it never scans those tables
# while a large import is committing.
SMART_IMPORT_AUTOMATION_GUARD = "farm:smart-import-vs-automation"
FARM_AUTOMATION_LEADER_GUARD = "farm:automation-scheduler-leader"


def _transaction_lock_result(
    db: Session,
    resource: str,
    *,
    timeout_ms: int,
) -> int:
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "mssql":
        return 0

    result = db.execute(
        text(
            "DECLARE @result int; "
            "EXEC @result = sp_getapplock "
            "@Resource=:resource, "
            "@LockMode='Exclusive', "
            "@LockOwner='Transaction', "
            "@LockTimeout=:timeout_ms; "
            "SELECT @result AS result;"
        ),
        {
            "resource": str(resource)[:255],
            "timeout_ms": int(timeout_ms),
        },
    ).scalar_one()
    return int(result)


def acquire_transaction_lock(
    db: Session,
    resource: str,
    *,
    timeout_ms: int = 10000,
) -> None:
    """Serialize a sensitive transaction section on SQL Server.

    SQL Server's sp_getapplock is transaction-scoped, so the lock is released
    automatically when the surrounding transaction commits or rolls back.
    Other databases (including SQLite used by tests) safely no-op here.
    """
    result = _transaction_lock_result(
        db,
        resource,
        timeout_ms=timeout_ms,
    )

    # sp_getapplock returns >= 0 for success and negative values for timeout,
    # cancellation, or deadlock victim status.
    if result < 0:
        raise RuntimeError(
            f"Unable to acquire database lock for {resource!r} (code {result})."
        )


def try_acquire_transaction_lock(
    db: Session,
    resource: str,
    *,
    timeout_ms: int = 0,
) -> bool:
    """Attempt a transaction-scoped SQL Server application lock.

    This is intended for optional background work. A busy foreground operation
    should cause the scheduler to skip its current cycle rather than block or
    participate in a database deadlock.
    """
    return _transaction_lock_result(
        db,
        resource,
        timeout_ms=timeout_ms,
    ) >= 0


def try_acquire_session_lock(
    connection: Connection,
    resource: str,
    *,
    timeout_ms: int = 0,
) -> bool:
    """Elect one long-lived scheduler leader on SQL Server.

    Session-owned application locks survive transaction boundaries and are
    automatically released if the owning connection closes. Non-SQL Server
    engines are used only by local tests and do not need cross-process leader
    election.
    """

    if connection.dialect.name != "mssql":
        return True

    result = connection.execute(
        text(
            "DECLARE @result int; "
            "EXEC @result = sp_getapplock "
            "@Resource=:resource, "
            "@LockMode='Exclusive', "
            "@LockOwner='Session', "
            "@LockTimeout=:timeout_ms; "
            "SELECT @result AS result;"
        ),
        {
            "resource": str(resource)[:255],
            "timeout_ms": int(timeout_ms),
        },
    ).scalar_one()
    connection.commit()
    return int(result) >= 0


def session_lock_is_held(connection: Connection, resource: str) -> bool:
    if connection.dialect.name != "mssql":
        connection.execute(text("SELECT 1"))
        return True

    mode = connection.execute(
        text("SELECT APPLOCK_MODE('public', :resource, 'Session')"),
        {"resource": str(resource)[:255]},
    ).scalar_one_or_none()
    connection.commit()
    return str(mode or "NoLock") != "NoLock"


def release_session_lock(connection: Connection, resource: str) -> None:
    if connection.dialect.name != "mssql":
        return

    connection.execute(
        text(
            "EXEC sp_releaseapplock "
            "@Resource=:resource, @LockOwner='Session';"
        ),
        {"resource": str(resource)[:255]},
    )
    connection.commit()
