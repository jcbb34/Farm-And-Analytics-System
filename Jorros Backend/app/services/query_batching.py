from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any, TypeVar


T = TypeVar("T")

# SQL Server allows at most 2,100 bound parameters in one statement. Keeping
# each IN-list at 1,000 leaves room for other filters in the same query.
SQL_IN_BATCH_SIZE = 1_000


def sql_in_batches(
    values: Iterable[T],
    *,
    batch_size: int = SQL_IN_BATCH_SIZE,
) -> Iterator[tuple[T, ...]]:
    """Yield unique values in parameter-safe batches.

    Large task histories can exceed SQL Server's statement parameter limit
    when every ID is placed in one ``IN (...)`` clause. Deduplicating first
    also avoids spending parameters on repeated IDs.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    unique_values = tuple(dict.fromkeys(values))
    for start in range(0, len(unique_values), batch_size):
        yield unique_values[start:start + batch_size]


def scalar_rows_in_batches(
    db: Any,
    values: Iterable[T],
    statement_for_batch: Callable[[tuple[T, ...]], Any],
    *,
    batch_size: int = SQL_IN_BATCH_SIZE,
) -> list[Any]:
    """Execute one scalar-select statement per safe parameter batch."""

    rows: list[Any] = []
    for batch in sql_in_batches(values, batch_size=batch_size):
        rows.extend(db.scalars(statement_for_batch(batch)).all())
    return rows
