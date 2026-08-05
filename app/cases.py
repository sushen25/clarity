from __future__ import annotations

import hashlib
import json
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .auth import login_required
from .clinical import CRITERIA, DOMAINS, DOMAIN_DEFINITIONS, OUTCOMES, clinical_gaps
from .db import audit, get_db, new_id, now, row_dict
from .jobs import enqueue
from .parsers import ALLOWED_EXTENSIONS

cases_bp = Blueprint("cases", __name__, url_prefix="/api")


def _case_or_error(case_id: str):
    row = get_db().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not row:
        return None, (jsonify({"error": "case_not_found"}), 404)
    if g.user["role"] != "admin" and row["assigned_user_id"] != g.user["id"]:
        return None, (jsonify({"error": "case_not_found"}), 404)
    return row_dict(row), None


def _source_or_error(case_id: str, source_id: str):
    case, error = _case_or_error(case_id)
    if error:
        return None, error
    row = get_db().execute("SELECT * FROM source_documents WHERE id=? AND case_id=?", (source_id, case_id)).fetchone()
    return (row_dict(row), None) if row else (None, (jsonify({"error": "source_not_found"}), 404))


@cases_bp.get("/cases")
@login_required
def list_cases():
    if g.user["role"] == "admin":
        rows = get_db().execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
    else:
        rows = get_db().execute("SELECT * FROM cases WHERE assigned_user_id=? ORDER BY updated_at DESC", (g.user["id"],)).fetchall()
    return jsonify([row_dict(row) for row in rows])


@cases_bp.post("/cases")
@login_required
def create_case():
    body = request.get_json(silent=True) or {}
    cohort = body.get("cohort")
    initials = str(body.get("patient_initials", "")).strip()
    if cohort not in {"adult", "adolescent"} or not initials:
        return jsonify({"error": "cohort_and_patient_initials_required"}), 400
    case_id, timestamp = new_id(), now()
    assigned = body.get("assigned_user_id") if g.user["role"] == "admin" else g.user["id"]
    if not assigned:
        assigned = g.user["id"]
    get_db().execute(
        "INSERT INTO cases(id,cohort,patient_initials,demographics_json,referral_question,assessment_dates_json,instruments_json,cloud_consent,assigned_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (case_id, cohort, initials, json.dumps(body.get("demographics", {})), str(body.get("referral_question", "")),
         json.dumps(body.get("assessment_dates", [])), json.dumps(body.get("instruments", [])), int(bool(body.get("cloud_consent"))), assigned, timestamp, timestamp),
    )
    for criterion in CRITERIA:
        get_db().execute(
            "INSERT INTO criterion_assessments(id,case_id,criterion_id,updated_at) VALUES(?,?,?,?)",
            (new_id(), case_id, criterion, timestamp),
        )
    get_db().commit()
    audit("case.created", g.user["id"], case_id, metadata={"cohort": cohort})
    return jsonify(row_dict(get_db().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())), 201


@cases_bp.get("/cases/<case_id>")
@login_required
def get_case(case_id: str):
    case, error = _case_or_error(case_id)
    if error:
        return error
    case["sources"] = [row_dict(row) for row in get_db().execute("SELECT * FROM source_documents WHERE case_id=? ORDER BY created_at", (case_id,))]
    for source in case["sources"]:
        source.pop("extracted_text", None)
        source.pop("storage_name", None)
    evidence = [row_dict(row) for row in get_db().execute("SELECT * FROM evidence_items WHERE case_id=? ORDER BY created_at", (case_id,))]
    criteria = [row_dict(row) for row in get_db().execute("SELECT * FROM criterion_assessments WHERE case_id=? ORDER BY criterion_id", (case_id,))]
    instruments = [row_dict(row) for row in get_db().execute("SELECT * FROM instrument_summaries WHERE case_id=? ORDER BY created_at", (case_id,))]
    drafts = [row_dict(row) for row in get_db().execute("SELECT * FROM report_drafts WHERE case_id=? ORDER BY version DESC", (case_id,))]
    jobs = [row_dict(row) for row in get_db().execute("SELECT * FROM jobs WHERE case_id=? ORDER BY created_at DESC LIMIT 20", (case_id,))]
    evidence_domains = [
        {"value": value, "label": value.replace("_", " ").title(), "description": description}
        for value, description in DOMAIN_DEFINITIONS.items()
    ]
    return jsonify({"case": case, "sources": case["sources"], "evidence": evidence, "evidence_domains": evidence_domains,
                    "criteria": criteria, "instruments": instruments, "drafts": drafts, "jobs": jobs,
                    "warnings": clinical_gaps(case, evidence, case["sources"])})


@cases_bp.patch("/cases/<case_id>")
@login_required
def update_case(case_id: str):
    case, error = _case_or_error(case_id)
    if error:
        return error
    body = request.get_json(silent=True) or {}
    allowed = {
        "patient_initials": ("patient_initials", str), "demographics": ("demographics_json", json.dumps),
        "referral_question": ("referral_question", str), "assessment_dates": ("assessment_dates_json", json.dumps),
        "instruments": ("instruments_json", json.dumps), "cloud_consent": ("cloud_consent", lambda x: int(bool(x))),
        "final_diagnostic_conclusion": ("final_diagnostic_conclusion", str),
    }
    assignments, values = [], []
    for key, (column, transform) in allowed.items():
        if key in body:
            assignments.append(f"{column}=?")
            values.append(transform(body[key]))
    if not assignments:
        return jsonify({"error": "no_supported_fields"}), 400
    values.extend([now(), case_id])
    get_db().execute(f"UPDATE cases SET {','.join(assignments)},updated_at=? WHERE id=?", values)
    get_db().commit()
    audit("case.updated", g.user["id"], case_id, metadata={"fields": sorted(set(body) & set(allowed))})
    return jsonify(row_dict(get_db().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()))


@cases_bp.post("/cases/<case_id>/archive")
@login_required
def archive_case(case_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    get_db().execute("UPDATE cases SET status='archived',updated_at=? WHERE id=?", (now(), case_id))
    get_db().commit()
    audit("case.archived", g.user["id"], case_id)
    return "", 204


@cases_bp.post("/cases/<case_id>/sources")
@login_required
def upload_source(case_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "file_required"}), 400
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "unsupported_file_type"}), 400
    source_id = new_id()
    rel = Path("sources") / case_id / f"{source_id}{suffix}"
    target = Path(current_app.config["STORAGE_ROOT"]) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    upload.save(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    timestamp = now()
    get_db().execute(
        "INSERT INTO source_documents(id,case_id,source_type,reporter,setting,instrument,original_filename,storage_name,sha256,mime_type,created_at) VALUES(?,?,?,?,?,?,?,?,?,'application/octet-stream',?)",
        (source_id, case_id, request.form.get("source_type", "transcript"), request.form.get("reporter", ""),
         request.form.get("setting", ""), request.form.get("instrument", ""), Path(upload.filename).name, str(rel), digest, timestamp),
    )
    get_db().commit()
    job = enqueue("extract_source", case_id, {"source_id": source_id})
    audit("source.uploaded", g.user["id"], case_id, source_id, {"extension": suffix, "sha256": digest})
    return jsonify({"source_id": source_id, "job": job}), 202


@cases_bp.patch("/cases/<case_id>/evidence/<evidence_id>")
@login_required
def update_evidence(case_id: str, evidence_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    row = get_db().execute("SELECT * FROM evidence_items WHERE id=? AND case_id=?", (evidence_id, case_id)).fetchone()
    if not row:
        return jsonify({"error": "evidence_not_found"}), 404
    body = request.get_json(silent=True) or {}
    allowed = {"domain", "source_location", "supporting_text", "reporter", "setting", "confidence", "contradiction_status", "verified"}
    if "domain" in body and body["domain"] not in DOMAINS:
        return jsonify({"error": "invalid_domain", "allowed_domains": list(DOMAINS)}), 400
    fields, values = [], []
    for key in allowed:
        if key in body:
            fields.append(f"{key}=?")
            values.append(int(bool(body[key])) if key == "verified" else body[key])
    if not fields:
        return jsonify({"error": "no_supported_fields"}), 400
    get_db().execute(f"UPDATE evidence_items SET {','.join(fields)} WHERE id=? AND case_id=?", (*values, evidence_id, case_id))
    get_db().commit()
    audit("evidence.updated", g.user["id"], case_id, evidence_id, {"fields": sorted(set(body) & allowed)})
    return jsonify(row_dict(get_db().execute("SELECT * FROM evidence_items WHERE id=?", (evidence_id,)).fetchone()))


@cases_bp.put("/cases/<case_id>/criteria/<criterion_id>")
@login_required
def update_criterion(case_id: str, criterion_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    if criterion_id not in CRITERIA:
        return jsonify({"error": "invalid_criterion"}), 400
    body = request.get_json(silent=True) or {}
    outcome = body.get("clinician_outcome", "unreviewed")
    if outcome not in OUTCOMES:
        return jsonify({"error": "invalid_outcome"}), 400
    evidence_ids = body.get("evidence_ids", [])
    if evidence_ids:
        count = get_db().execute(
            f"SELECT COUNT(*) FROM evidence_items WHERE case_id=? AND id IN ({','.join('?' for _ in evidence_ids)})",
            (case_id, *evidence_ids),
        ).fetchone()[0]
        if count != len(set(evidence_ids)):
            return jsonify({"error": "invalid_evidence_reference"}), 400
    get_db().execute(
        "UPDATE criterion_assessments SET evidence_ids_json=?,settings_json=?,impairment=?,clinician_outcome=?,notes=?,updated_at=? WHERE case_id=? AND criterion_id=?",
        (json.dumps(evidence_ids), json.dumps(body.get("settings", [])), str(body.get("impairment", "")), outcome,
         str(body.get("notes", "")), now(), case_id, criterion_id),
    )
    get_db().commit()
    audit("criterion.updated", g.user["id"], case_id, criterion_id, {"outcome": outcome})
    return jsonify(row_dict(get_db().execute("SELECT * FROM criterion_assessments WHERE case_id=? AND criterion_id=?", (case_id, criterion_id)).fetchone()))


@cases_bp.post("/cases/<case_id>/instruments")
@login_required
def create_instrument(case_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    body = request.get_json(silent=True) or {}
    if not str(body.get("instrument", "")).strip():
        return jsonify({"error": "instrument_required"}), 400
    item_id, timestamp = new_id(), now()
    get_db().execute(
        "INSERT INTO instrument_summaries(id,case_id,instrument,version,respondent,scores_json,interpretation,verified,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (item_id, case_id, str(body["instrument"]), str(body.get("version", "")), str(body.get("respondent", "")),
         json.dumps(body.get("scores", {})), str(body.get("interpretation", "")), int(bool(body.get("verified"))), timestamp, timestamp),
    )
    get_db().commit()
    audit("instrument.created", g.user["id"], case_id, item_id, {"instrument": str(body["instrument"])})
    return jsonify(row_dict(get_db().execute("SELECT * FROM instrument_summaries WHERE id=?", (item_id,)).fetchone())), 201


@cases_bp.post("/cases/<case_id>/drafts")
@login_required
def generate_draft(case_id: str):
    case, error = _case_or_error(case_id)
    if error:
        return error
    if current_app.config["BEDROCK_ENABLED"] and not case["cloud_consent"]:
        return jsonify({"error": "cloud_consent_required"}), 409
    active = get_db().execute(
        "SELECT * FROM jobs WHERE case_id=? AND job_type='generate_draft' AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    if active:
        return jsonify(row_dict(active)), 202
    job = enqueue("generate_draft", case_id, {})
    audit("draft.requested", g.user["id"], case_id, job["id"])
    return jsonify(job), 202


@cases_bp.patch("/cases/<case_id>/drafts/<draft_id>")
@login_required
def update_draft(case_id: str, draft_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    draft = row_dict(get_db().execute("SELECT * FROM report_drafts WHERE id=? AND case_id=?", (draft_id, case_id)).fetchone())
    if not draft:
        return jsonify({"error": "draft_not_found"}), 404
    if draft["state"] == "clinician-approved":
        return jsonify({"error": "approved_draft_is_immutable"}), 409
    body = request.get_json(silent=True) or {}
    sections = body.get("sections", draft["sections"])
    acknowledged = int(bool(body.get("warnings_acknowledged", draft["warnings_acknowledged"])))
    state = body.get("state", draft["state"])
    if state not in {"draft", "review-ready"}:
        return jsonify({"error": "invalid_draft_state"}), 400
    get_db().execute("UPDATE report_drafts SET sections_json=?,warnings_acknowledged=?,state=?,updated_at=? WHERE id=?",
                     (json.dumps(sections), acknowledged, state, now(), draft_id))
    get_db().execute("UPDATE cases SET status=?,updated_at=? WHERE id=?", (state, now(), case_id))
    get_db().commit()
    enqueue("render_draft", case_id, {"draft_id": draft_id})
    audit("draft.updated", g.user["id"], case_id, draft_id, {"state": state})
    return jsonify(row_dict(get_db().execute("SELECT * FROM report_drafts WHERE id=?", (draft_id,)).fetchone()))


@cases_bp.post("/cases/<case_id>/drafts/<draft_id>/approve")
@login_required
def approve_draft(case_id: str, draft_id: str):
    case, error = _case_or_error(case_id)
    if error:
        return error
    draft = row_dict(get_db().execute("SELECT * FROM report_drafts WHERE id=? AND case_id=?", (draft_id, case_id)).fetchone())
    if not draft:
        return jsonify({"error": "draft_not_found"}), 404
    failures = []
    if draft["state"] != "review-ready": failures.append("Draft must be marked review-ready.")
    if draft["warnings"] and not draft["warnings_acknowledged"]: failures.append("Clinical warnings must be acknowledged.")
    if not case["cloud_consent"]: failures.append("Cloud-processing consent must be acknowledged.")
    if not case["final_diagnostic_conclusion"].strip(): failures.append("A clinician-authored diagnostic conclusion is required.")
    criteria = get_db().execute("SELECT clinician_outcome FROM criterion_assessments WHERE case_id=?", (case_id,)).fetchall()
    if len(criteria) != 18 or any(row[0] == "unreviewed" for row in criteria): failures.append("All 18 criterion outcomes must be reviewed.")
    if not get_db().execute("SELECT 1 FROM evidence_items WHERE case_id=? AND verified=1", (case_id,)).fetchone(): failures.append("At least one evidence item must be verified.")
    if failures:
        return jsonify({"error": "approval_requirements_not_met", "requirements": failures}), 409
    timestamp = now()
    get_db().execute("UPDATE report_drafts SET state='clinician-approved',approved_by=?,approved_at=?,updated_at=? WHERE id=?",
                     (g.user["id"], timestamp, timestamp, draft_id))
    get_db().execute("UPDATE cases SET status='clinician-approved',updated_at=? WHERE id=?", (timestamp, case_id))
    get_db().commit()
    enqueue("render_draft", case_id, {"draft_id": draft_id})
    audit("draft.approved", g.user["id"], case_id, draft_id, {"version": draft["version"]})
    return jsonify(row_dict(get_db().execute("SELECT * FROM report_drafts WHERE id=?", (draft_id,)).fetchone()))


def _download(case_id: str, draft_id: str, field: str, mimetype: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    row = get_db().execute(f"SELECT {field},version FROM report_drafts WHERE id=? AND case_id=?", (draft_id, case_id)).fetchone()
    if not row or not row[field]:
        return jsonify({"error": "report_file_not_ready"}), 404
    storage_root = Path(current_app.config["STORAGE_ROOT"]).resolve()
    path = (storage_root / row[field]).resolve()
    if not path.is_relative_to(storage_root):
        return jsonify({"error": "report_file_missing"}), 404
    if not path.is_file():
        return jsonify({"error": "report_file_missing"}), 404
    audit(f"draft.{field}.downloaded", g.user["id"], case_id, draft_id, {"version": row["version"]})
    return send_file(path, mimetype=mimetype, as_attachment=field == "docx_path", download_name=path.name)


@cases_bp.get("/cases/<case_id>/drafts/<draft_id>/docx")
@login_required
def download_docx(case_id: str, draft_id: str):
    return _download(case_id, draft_id, "docx_path", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@cases_bp.get("/cases/<case_id>/drafts/<draft_id>/preview")
@login_required
def preview_pdf(case_id: str, draft_id: str):
    return _download(case_id, draft_id, "preview_path", "application/pdf")


@cases_bp.get("/jobs/<job_id>")
@login_required
def get_job(job_id: str):
    row = get_db().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "job_not_found"}), 404
    if row["case_id"]:
        _case, error = _case_or_error(row["case_id"])
        if error:
            return error
    return jsonify(row_dict(row))
