"""Export read-only query and index metadata from the configured SQL Server."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sort", choices=("duration", "cpu", "reads"), default="duration", help="Rank by total execution time, CPU time or logical reads")
    parser.add_argument("--include-sql", action="store_true", help="Include the text of the selected queries")
    parser.add_argument("--output", type=Path, help="Write a JSON report to this file")
    args = parser.parse_args()
    if not 1 <= args.hours <= 168 or not 1 <= args.limit <= 100:
        parser.error("--hours must be 1–168 and --limit must be 1–100")
    try:
        from app.core.database import engine
        from app.services.performance_diagnostics import collect_performance_diagnostics
        with engine.connect() as connection:
            report = collect_performance_diagnostics(connection, hours=args.hours, limit=args.limit, include_sql=args.include_sql, sort_by=args.sort)
        rendered = json.dumps(report, indent=2, default=str) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Saved read-only diagnostics to {args.output}")
            print(f"Query Store: {report['collection_status']}. {report['next_action']}")
        else:
            print(rendered)
    except Exception:
        print("Diagnostics could not connect or read the configured SQL Server. Check the backend environment, driver and database permissions. No database changes were requested.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
