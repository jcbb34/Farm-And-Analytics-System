from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from app.core.recovery_runtime import control_root, HostLock


def now():
    return datetime.now(timezone.utc).isoformat()


class Catalog:
    def __init__(self):
        self.root = control_root()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with HostLock("catalog-schema", timeout=10), self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError(
                    "Install the application matching this newer recovery catalog."
                )
            if version == 0:
                db.executescript(
                    (Path(__file__).parent / "migrations/001_catalog.sql").read_text()
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "catalog.sqlite3", timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, kind, identifier, default=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT data FROM documents WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, kind, identifier, data):
        with self.connect() as db:
            db.execute(
                "INSERT INTO documents VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data",
                (kind, identifier, json.dumps(data)),
            )
        return data

    def delete(self, kind, identifier):
        with self.connect() as db:
            db.execute(
                "DELETE FROM documents WHERE kind=? AND id=?", (kind, identifier)
            )

    def list(self, kind):
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM documents WHERE kind=? ORDER BY rowid DESC",
                    (kind,),
                )
            ]

    def enqueue(self, kind, payload, actor, dedup=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if dedup:
                old = db.execute(
                    "SELECT data FROM jobs WHERE dedup=?", (dedup,)
                ).fetchone()
                if old:
                    return json.loads(old[0])
            data = {
                "id": uuid4().hex,
                "kind": kind,
                "payload": payload,
                "actor": str(actor),
                "status": "Queued",
                "stage": "Waiting for the worker",
                "attempts": 0,
                "created_at": now(),
                "updated_at": now(),
            }
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?)", (data["id"], dedup, json.dumps(data))
            )
            return data

    def jobs(self):
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT data FROM jobs ORDER BY rowid DESC")
            ]

    def job(self, identifier):
        return next((v for v in self.jobs() if v["id"] == identifier), None)

    def update_job(self, identifier, **values):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM jobs WHERE id=?", (identifier,)
            ).fetchone()
            if not row:
                raise ValueError("Job not found.")
            data = {**json.loads(row[0]), **values, "updated_at": now()}
            db.execute(
                "UPDATE jobs SET data=? WHERE id=?", (json.dumps(data), identifier)
            )
            return data

    def event(self, actor, action, result="Completed", **details):
        data = {
            "actor": str(actor),
            "action": action,
            "result": result,
            "created_at": now(),
            "details": details,
        }
        with self.connect() as db:
            db.execute("INSERT INTO audit(data) VALUES(?)", (json.dumps(data),))

    def events(self):
        with self.connect() as db:
            return [
                {"id": row[0], **json.loads(row[1])}
                for row in db.execute(
                    "SELECT id,data FROM audit ORDER BY id DESC LIMIT 100"
                )
            ]
