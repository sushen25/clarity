from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from flask import current_app, g


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE_PATH"], timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        g.db = db
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    with current_app.open_resource("schema.sql") as handle:
        db.executescript(handle.read().decode("utf-8"))
    db.commit()


def row_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for key in list(result):
        if key.endswith("_json"):
            result[key[:-5]] = json.loads(result.pop(key) or "null")
        elif key in {"active", "cloud_consent", "verified", "warnings_acknowledged"}:
            result[key] = bool(result[key])
    return result


def audit(action: str, actor_user_id: str | None, case_id: str | None = None,
          target_id: str | None = None, metadata: dict | None = None) -> None:
    get_db().execute(
        "INSERT INTO audit_events(id,actor_user_id,action,case_id,target_id,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (new_id(), actor_user_id, action, case_id, target_id, json.dumps(metadata or {}), now()),
    )
    get_db().commit()

