from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.code_counter import CodeCounter
from app.services.db_concurrency import acquire_transaction_lock


def next_record_code(
    db: Session,
    *,
    namespace: str,
    prefix: str,
    seed_model=None,
    code_column=None,
    minimum: int = 1001,
) -> str:
    """Reserve the next code inside the caller's database transaction.

    A short application lock serializes initialization and increments on SQL
    Server. The counter row is also selected for update, which provides a
    second database-level guard on engines that support row locking. Existing
    installations are seeded from MAX(primary-key), never by scanning and
    parsing every historical code. An indexed equality probe protects upgraded
    databases whose historical code suffixes do not align with row IDs.
    """

    normalized_namespace = str(namespace).strip().lower()
    normalized_prefix = str(prefix).strip().upper()
    if not normalized_namespace or not normalized_prefix:
        raise ValueError("Code namespace and prefix are required.")

    acquire_transaction_lock(db, f"code-counter:{normalized_namespace}")

    counter = db.scalar(
        select(CodeCounter)
        .where(CodeCounter.namespace == normalized_namespace)
        .with_for_update()
    )

    if counter is None:
        value = minimum
        if seed_model is not None:
            highest_id = int(db.scalar(select(func.max(seed_model.id))) or 0)
            value = max(minimum, 1000 + highest_id + 1)

        counter = CodeCounter(
            namespace=normalized_namespace,
            next_value=value,
        )
        db.add(counter)
        db.flush()
    else:
        value = max(minimum, int(counter.next_value))

    if seed_model is not None and code_column is not None:
        while db.scalar(
            select(seed_model.id)
            .where(code_column == f"{normalized_prefix}-{value}")
            .limit(1)
        ) is not None:
            value += 1

    counter.next_value = value + 1
    db.flush()

    return f"{normalized_prefix}-{value}"
