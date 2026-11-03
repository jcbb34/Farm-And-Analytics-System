"""Check event/location planning routes without opening a database."""

import argparse
import sys

try:
    from scripts.check_archive_api import local_schema, live_schema, REPAIR_HINT
except ModuleNotFoundError:
    from check_archive_api import local_schema, live_schema, REPAIR_HINT


def missing_features(schema):
    paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
    errors = []
    for path in ("/api/v1/farm-locations", "/api/v1/activities/event-resources"):
        if not isinstance(paths.get(path), dict) or "get" not in paths[path]:
            errors.append("GET " + path)
    operation = paths.get("/api/v1/farm-locations", {}).get("get", {})
    parameters = {
        item.get("name")
        for item in operation.get("parameters", [])
        if item.get("in") == "query"
    }
    for parameter in ("context", "event_type", "source_module", "source_record_id"):
        if parameter not in parameters:
            errors.append("location query parameter: " + parameter)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--wait", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.wait <= 60:
        parser.error("--wait must be between 0 and 60 seconds")
    try:
        schema = local_schema() if args.local else live_schema(args.url, args.wait)
        missing = missing_features(schema)
    except Exception:
        print(
            "Event/location API could not be verified. Check the complete backend source and startup errors.",
            file=sys.stderr,
        )
        print(REPAIR_HINT, file=sys.stderr)
        return 1
    if missing:
        print("The event/location API is outdated or incomplete:", file=sys.stderr)
        for feature in missing:
            print("Missing " + feature, file=sys.stderr)
        print(REPAIR_HINT, file=sys.stderr)
        return 1
    print(
        "Event and location API verified in app.main; no database opened."
        if args.local
        else "Event and location API verified on the running backend."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
