from __future__ import annotations

import json
import time
from pathlib import Path

from flask import current_app

from . import create_app
from .ai import get_ai
from .clinical import clinical_gaps
from .drafting import REFERENCE_VERSION
from .db import audit, get_db, new_id, now, row_dict
from .jobs import claim_next_job, complete, fail
from .parsers import validate_and_extract
from .reporting import generate_docx, render_preview


def _case(case_id: str) -> dict:
    row = get_db().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not row:
        raise ValueError("Case no longer exists")
    return row_dict(row)


def process_extract(payload: dict, case_id: str) -> None:
    source = row_dict(get_db().execute("SELECT * FROM source_documents WHERE id=? AND case_id=?", (payload["source_id"], case_id)).fetchone())
    if not source:
        raise ValueError("Source no longer exists")
    path = Path(current_app.config["STORAGE_ROOT"]) / source["storage_name"]
    text, mime = validate_and_extract(path, source["original_filename"])
    result = get_ai().extract(text, source, _case(case_id)["cohort"])
    db = get_db()
    db.execute("DELETE FROM evidence_items WHERE source_id=?", (source["id"],))
    for item in result.evidence:
        value = item.model_dump()
        db.execute(
            "INSERT INTO evidence_items(id,case_id,source_id,domain,source_location,supporting_text,reporter,setting,confidence,contradiction_status,assessment_type,criterion_ids_json,timeframe,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), case_id, source["id"], value["domain"], value["source_location"], value["supporting_text"],
             value["reporter"], value["setting"], value["confidence"], value["contradiction_status"],
             value["assessment_type"], json.dumps(value["criterion_ids"]), value["timeframe"], now()),
        )
    db.execute("UPDATE source_documents SET extracted_text=?,mime_type=?,extraction_status='completed' WHERE id=?", (text, mime, source["id"]))
    db.commit()
    audit("source.extracted", None, case_id, source["id"], {"evidence_count": len(result.evidence)})


def process_draft(payload: dict, case_id: str) -> None:
    case = _case(case_id)
    evidence = [row_dict(row) for row in get_db().execute(
        "SELECT e.*,s.source_type,s.instrument AS source_instrument FROM evidence_items e JOIN source_documents s ON s.id=e.source_id WHERE e.case_id=? AND e.verified=1", (case_id,)
    )]
    criteria = [row_dict(row) for row in get_db().execute("SELECT * FROM criterion_assessments WHERE case_id=?", (case_id,))]
    instruments = [row_dict(row) for row in get_db().execute("SELECT * FROM instrument_summaries WHERE case_id=? AND verified=1", (case_id,))]
    sources = [row_dict(row) for row in get_db().execute("SELECT * FROM source_documents WHERE case_id=?", (case_id,))]
    if not evidence:
        raise ValueError("At least one verified evidence item is required")
    result = get_ai().draft(case, evidence, criteria, instruments)
    version = get_db().execute("SELECT COALESCE(MAX(version),0)+1 FROM report_drafts WHERE case_id=?", (case_id,)).fetchone()[0]
    draft_id = new_id()
    timestamp = now()
    warnings = clinical_gaps(case, evidence, sources) + result.validation_warnings
    get_db().execute(
        "INSERT INTO report_drafts(id,case_id,version,sections_json,warnings_json,input_snapshot_json,template_version,prompt_version,model_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,'reference-v2',?,?, 'draft',?,?)",
        (draft_id, case_id, version, json.dumps(result.model_dump()["sections"]), json.dumps(warnings),
         json.dumps({"case": case, "criteria": criteria, "evidence": evidence, "instruments": instruments,
                     "guideline_reference_version": REFERENCE_VERSION}),
         current_app.config["PROMPT_VERSION"], current_app.config["BEDROCK_MODEL_ID"] if current_app.config["BEDROCK_ENABLED"] else "local-heuristic", timestamp, timestamp),
    )
    get_db().execute("UPDATE cases SET status='draft',updated_at=? WHERE id=?", (timestamp, case_id))
    get_db().commit()
    _generate_files(draft_id)
    audit("draft.generated", None, case_id, draft_id, {"version": version, "warning_count": len(warnings)})


def _generate_files(draft_id: str) -> None:
    draft = row_dict(get_db().execute("SELECT * FROM report_drafts WHERE id=?", (draft_id,)).fetchone())
    # Never rewrite an already-rendered approved artefact, including pre-migration reports.
    if draft["state"] == "clinician-approved" and draft.get("docx_path") and (
        not draft.get("input_snapshot") or draft.get("rendered_state") == "clinician-approved"
    ):
        return
    case = _case(draft["case_id"])
    clinician = row_dict(get_db().execute("SELECT * FROM users WHERE id=?", (case["assigned_user_id"],)).fetchone())
    criteria = [row_dict(row) for row in get_db().execute(
        "SELECT * FROM criterion_assessments WHERE case_id=? ORDER BY criterion_id", (case["id"],)
    )]
    snapshot = draft.get("input_snapshot") or {}
    case = snapshot.get("case", case)
    criteria = snapshot.get("criteria", criteria)
    root = Path(current_app.config["STORAGE_ROOT"])
    docx_rel = Path("reports") / case["id"] / f"report-v{draft['version']}.docx"
    pdf_dir = root / "previews" / case["id"] / f"v{draft['version']}"
    generate_docx(
        Path(current_app.config["REPORT_TEMPLATE"]), root / docx_rel, case, draft,
        clinician, criteria,
    )
    preview = render_preview(root / docx_rel, pdf_dir, current_app.config["LIBREOFFICE_BIN"])
    preview_rel = str(preview.relative_to(root)) if preview else None
    get_db().execute("UPDATE report_drafts SET docx_path=?,preview_path=?,rendered_state=?,updated_at=? WHERE id=?",
                     (str(docx_rel), preview_rel, draft["state"], now(), draft_id))
    get_db().commit()


def process_job(job: dict) -> None:
    if job["job_type"] == "extract_source":
        process_extract(job["payload"], job["case_id"])
    elif job["job_type"] == "generate_draft":
        process_draft(job["payload"], job["case_id"])
    elif job["job_type"] == "render_draft":
        _generate_files(job["payload"]["draft_id"])
    else:
        raise ValueError("Unknown job type")


def run_forever() -> None:
    app = create_app()
    with app.app_context():
        while True:
            job = claim_next_job()
            if not job:
                time.sleep(app.config["WORKER_POLL_SECONDS"])
                continue
            try:
                process_job(job)
                complete(job["id"])
            except Exception as exc:
                if job["job_type"] == "extract_source" and int(job["attempts"]) >= 3:
                    get_db().execute("UPDATE source_documents SET extraction_status='failed' WHERE id=?", (job["payload"].get("source_id"),))
                    get_db().commit()
                outcome = fail(job, exc)
                current_app.logger.warning(
                    "job.processing_failed job_type=%s status=%s attempt=%d error_code=%s",
                    job["job_type"], outcome["status"], outcome["attempts"], outcome["error_code"],
                )
                audit(
                    f"job.{outcome['status']}", None, job["case_id"], job["id"],
                    {"job_type": job["job_type"], "attempt": outcome["attempts"], "error_code": outcome["error_code"]},
                )


if __name__ == "__main__":
    run_forever()
