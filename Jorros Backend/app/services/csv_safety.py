from __future__ import annotations

from collections.abc import Iterable
from typing import Any


DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet programs from executing user-entered CSV formulas."""
    if not isinstance(value, str):
        return value

    stripped = value.lstrip()
    if stripped.startswith(DANGEROUS_FORMULA_PREFIXES):
        return "'" + value

    return value


class SafeCsvWriter:
    def __init__(self, writer):
        self._writer = writer

    def writerow(self, row: Iterable[Any]):
        return self._writer.writerow([safe_csv_cell(value) for value in row])

    def writerows(self, rows: Iterable[Iterable[Any]]):
        return self._writer.writerows(
            [safe_csv_cell(value) for value in row]
            for row in rows
        )
