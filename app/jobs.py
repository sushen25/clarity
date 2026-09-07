from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from .db import get_db, new_id, now, row_dict


def _is_transient(error: Exception) -> bool:
    try:
        from botocore.exceptions import (
            ConnectTimeoutError,
            ConnectionClosedError,
            EndpointConnectionError,
            ReadTimeoutError,
        )
        if isinstance(error, (ConnectTimeoutError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError)):
            return True
        response = getattr(error, "response", {}) or {}
        code = (response.get("Error", {}) or {}).get("Code", "")
        return code in {
            "InternalServerException", "ModelNotReadyException", "ModelTimeoutException",
            "ServiceUnavailableException", "ThrottlingException", "TooManyRequestsException",
        }
    except ImportError:
        return isinstance(error, (ConnectionError, TimeoutError))


def enqueue(job_type: str, case_id: str | None, payload: dict) -> dict:
    job_id = new_id()
    timestamp = now()
    get_db().execute(
        "INSERT INTO jobs(id,case_id,job_type,payload_json,status,available_at,created_at,updated_at) VALUES(?,?,?,?,'queued',?,?,?)",
        (job_id, case_id, job_type, json.dumps(payload), timestamp, timestamp, timestamp),
    )
    get_db().commit()
    return row_dict(get_db().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def claim_next_job():
    db = get_db()
    current = now()
    db.execute("BEGIN IMMEDIATE")
    # Drafting a whole report in one model request legitimately runs past ten minutes, so
    # the lock has to outlast it. A single worker cannot reclaim its own running job (it
    # only claims while idle), but a second worker could, and would draft the case twice.
    stale = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    db.execute(
        "UPDATE jobs SET status='queued',locked_at=NULL,available_at=?,updated_at=? WHERE status='running' AND locked_at<?",
        (current, current, stale),
    )
    row = db.execute(
        "SELECT * FROM jobs WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT 1", (current,)
    ).fetchone()
    if not row:
        db.commit()
        return None
    changed = db.execute(
        "UPDATE jobs SET status='running',locked_at=?,attempts=attempts+1,updated_at=? WHERE id=? AND status='queued'",
        (current, current, row["id"]),
    ).rowcount
    db.commit()
    return row_dict(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()) if changed else None


def complete(job_id: str) -> None:
    get_db().execute("UPDATE jobs SET status='completed',locked_at=NULL,updated_at=? WHERE id=?", (now(), job_id))
    get_db().commit()


def fail(job: dict, error: Exception) -> dict:
    attempts = int(job["attempts"])
    error_code = getattr(error, "job_error_code", type(error).__name__)
    if attempts < 3 and _is_transient(error):
        delay = 2 ** attempts * 10
        available = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        status = "queued"
    else:
        available = now()
        status = "failed"
    get_db().execute(
        "UPDATE jobs SET status=?,last_error=?,available_at=?,locked_at=NULL,updated_at=? WHERE id=?",
        (status, error_code, available, now(), job["id"]),
    )
    get_db().commit()
    return {"status": status, "error_code": error_code, "attempts": attempts}
