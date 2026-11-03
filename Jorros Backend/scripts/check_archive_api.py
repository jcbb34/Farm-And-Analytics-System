"""Read-only check of archive routes in the source or the running local API."""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


REQUIRED_ROUTES = (
    ("/api/v1/archives", "get"),
    ("/api/v1/archives/{module}/{record_id}/impact", "get"),
    ("/api/v1/archives/{module}/{record_id}/archive", "post"),
    ("/api/v1/archives/{module}/{record_id}/restore", "post"),
    ("/api/v1/archives/{module}/{record_id}", "delete"),
)
REPAIR_HINT = "Apply both application folders, stop the old backend, and restart from this project's Jorros Backend folder. No database reset or migration is needed for missing routes."


def missing_routes(schema):
    paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
    if not isinstance(paths, dict): paths = {}
    return [(path, method) for path, method in REQUIRED_ROUTES if not isinstance(paths.get(path), dict) or method not in paths[path]]


def local_schema():
    # Importing the application builds its route table. Do not enter its
    # lifespan, call health/database checks, or create a database session.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.main import app
    return app.openapi()


def live_schema(base_url, wait=0):
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Use the local backend origin, for example http://127.0.0.1:8000.")
    deadline = time.monotonic() + wait
    opener = build_opener(ProxyHandler({}))  # Loopback must not use an internet proxy.
    while True:
        try:
            with opener.open(base_url.rstrip("/") + "/openapi.json", timeout=3) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("The running server returned an unexpected API schema.")
            return json.loads(data)
        except HTTPError as error:
            raise ValueError(f"The running backend did not expose its API schema (HTTP {error.code}).") from None
        except (URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise ValueError("The local backend could not be reached. Start it and check the backend port.") from None
            time.sleep(0.25)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("The running server returned an invalid API schema.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--local", action="store_true", help="Inspect app.main without opening a database or contacting a server")
    source.add_argument("--url", default="http://127.0.0.1:8000", help="Local running backend origin")
    parser.add_argument("--wait", type=float, default=0, help="Seconds to wait for a starting backend, up to 60")
    args = parser.parse_args(argv)
    if not 0 <= args.wait <= 60:
        parser.error("--wait must be between 0 and 60 seconds.")
    try:
        schema = local_schema() if args.local else live_schema(args.url, args.wait)
    except Exception:
        # Configuration/import exceptions can contain environment values.
        print("Unable to inspect the local source. Check the complete backend source, dependencies and configuration." if args.local else "Unable to verify the running local backend. Check its address and startup errors.", file=sys.stderr)
        print(REPAIR_HINT, file=sys.stderr)
        return 1
    missing = missing_routes(schema)
    if missing:
        print("Archive API is missing from the local source." if args.local else "The running backend does not expose the required archive API.", file=sys.stderr)
        for path, method in missing:
            print(f"Missing route: {method.upper()} {path}", file=sys.stderr)
        print(REPAIR_HINT, file=sys.stderr)
        return 1
    print("Archive API verified in app.main; no database opened." if args.local else "Archive API verified on the running backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
