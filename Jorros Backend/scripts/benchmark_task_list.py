"""Reproducible SQLite fixture benchmark; never touches a farm database."""
import json
import statistics
import sys
import time
from datetime import date, time as clock
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_release_http_authorization import ReleaseHttpAuthorizationTests  # noqa: E402
from app.models import FarmActivity  # noqa: E402


def main():
    fixture = ReleaseHttpAuthorizationTests()
    fixture.setUp()
    try:
        with Session(fixture.engine) as db:
            db.add_all([FarmActivity(
                activity_code=f"ACT-BENCH-{number}", name=f"Feed and check plot {number}",
                category="General Care", related_to="Farm", location="Test field",
                activity_date=date(2026, 9, 29), start_time=clock(8),
                assigned_by="Manager", assigned_to="Test Worker One", assigned_employee_id=1,
                status="Pending", priority="Medium", requires_review=True,
                requires_evidence=False, needs_reassignment=False, is_archived=False,
            ) for number in range(3, 1003)])
            db.commit()
        measurements = {}
        for label, url, role in [
            ("manager_legacy", "/api/v1/workforce/tasks", "MANAGER"),
            ("employee_legacy", "/api/v1/workforce/my-tasks?view=active&scope=timeline", "WORKER1"),
            ("manager_page", "/api/v1/workforce/tasks/page?limit=25", "MANAGER"),
            ("employee_page", "/api/v1/workforce/my-tasks/page?view=active&limit=25", "WORKER1"),
            ("manager_summary", "/api/v1/workforce/tasks/summary", "MANAGER"),
        ]:
            durations, sizes, select_counts, rows = [], [], [], []
            for _ in range(5):
                queries = [0]

                def count_query(_conn, _cursor, statement, _params, _context, _many):
                    if statement.lstrip().lower().startswith("select"):
                        queries[0] += 1

                event.listen(fixture.engine, "before_cursor_execute", count_query)
                try:
                    start = time.perf_counter()
                    response = fixture.client.get(url, headers=fixture.headers(role))
                    durations.append(round((time.perf_counter() - start) * 1000, 2))
                finally:
                    event.remove(fixture.engine, "before_cursor_execute", count_query)
                response.raise_for_status()
                payload = response.json()
                rows.append(len(payload.get("items", [])) if isinstance(payload, dict) else len(payload))
                sizes.append(len(response.content))
                select_counts.append(queries[0])
            measurements[label] = {"records": rows[-1], "median_ms": statistics.median(durations),
                                   "response_bytes": sizes[-1], "select_queries": select_counts[-1],
                                   "samples_ms": durations}
        print(json.dumps(measurements, indent=2))
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
