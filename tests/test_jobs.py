from __future__ import annotations

from botocore.exceptions import ReadTimeoutError

from app.db import get_db
from app.jobs import claim_next_job, enqueue, fail


def test_validation_failure_is_not_retried(app):
    with app.app_context():
        queued = enqueue("generate_draft", None, {})
        job = claim_next_job()
        assert job["id"] == queued["id"]

        outcome = fail(job, ValueError("sensitive validation detail"))
        stored = get_db().execute("SELECT status,attempts,last_error FROM jobs WHERE id=?", (job["id"],)).fetchone()

        assert outcome == {"status": "failed", "error_code": "ValueError", "attempts": 1}
        assert tuple(stored) == ("failed", 1, "ValueError")


def test_read_timeout_is_retried_with_sanitized_error(app):
    with app.app_context():
        queued = enqueue("generate_draft", None, {})
        job = claim_next_job()
        assert job["id"] == queued["id"]

        outcome = fail(job, ReadTimeoutError(endpoint_url="https://bedrock-runtime.example.invalid"))
        stored = get_db().execute("SELECT status,attempts,last_error FROM jobs WHERE id=?", (job["id"],)).fetchone()

        assert outcome == {"status": "queued", "error_code": "ReadTimeoutError", "attempts": 1}
        assert tuple(stored) == ("queued", 1, "ReadTimeoutError")
