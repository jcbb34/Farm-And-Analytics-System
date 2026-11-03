from app.services.query_batching import (
    SQL_IN_BATCH_SIZE,
    scalar_rows_in_batches,
    sql_in_batches,
)


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _RecordingSession:
    def __init__(self):
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        return _ScalarResult(statement)


def test_large_sql_in_values_are_split_below_sql_server_parameter_limit():
    task_ids = list(range(1, 2_207))

    batches = list(sql_in_batches(task_ids))

    assert SQL_IN_BATCH_SIZE == 1_000
    assert [len(batch) for batch in batches] == [1_000, 1_000, 206]
    assert [item for batch in batches for item in batch] == task_ids
    assert all(len(batch) < 2_100 for batch in batches)


def test_batching_deduplicates_ids_and_loader_executes_each_batch():
    session = _RecordingSession()
    values = [*range(1, 1_101), *range(1, 101)]

    rows = scalar_rows_in_batches(session, values, lambda batch: list(batch))

    assert len(session.statements) == 2
    assert [len(statement) for statement in session.statements] == [1_000, 100]
    assert rows == list(range(1, 1_101))


def test_batch_size_must_be_positive():
    try:
        list(sql_in_batches([1], batch_size=0))
    except ValueError as error:
        assert str(error) == "batch_size must be at least 1"
    else:
        raise AssertionError("Expected a ValueError for an invalid batch size.")
