from __future__ import annotations

import hashlib
import json
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .auth import login_required
from .clinical import CRITERIA, DOMAINS, DOMAIN_DEFINITIONS, OUTCOMES, ASSESSMENT_TYPES, TIMEFRAMES, DraftResult, outcome_columns, clinical_gaps
from pydantic import ValidationError
from .drafting import validate_draft
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
    if not isinstance(body.get("demographics", {}), dict):
        return jsonify({"error": "invalid_demographics"}), 400
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
    if "demographics" in body and not isinstance(body["demographics"], dict):
        return jsonify({"error": "invalid_demographics"}), 400
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
    assessment_type = request.form.get("assessment_type", "other")
    if assessment_type not in ASSESSMENT_TYPES:
        return jsonify({"error": "invalid_assessment_type"}), 400
    source_id = new_id()
    rel = Path("sources") / case_id / f"{source_id}{suffix}"
    target = Path(current_app.config["STORAGE_ROOT"]) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    upload.save(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    timestamp = now()
    get_db().execute(
        "INSERT INTO source_documents(id,case_id,source_type,reporter,setting,instrument,assessment_type,original_filename,storage_name,sha256,mime_type,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,'application/octet-stream',?)",
        (source_id, case_id, request.form.get("source_type", "transcript"), request.form.get("reporter", ""),
         request.form.get("setting", ""), request.form.get("instrument", ""), assessment_type, Path(upload.filename).name, str(rel), digest, timestamp),
    )
    get_db().commit()
    job = enqueue("extract_source", case_id, {"source_id": source_id})
    audit("source.uploaded", g.user["id"], case_id, source_id, {"extension": suffix, "sha256": digest})
    return jsonify({"source_id": source_id, "job": job}), 202


@cases_bp.delete("/cases/<case_id>/sources/<source_id>")
@login_required
def delete_source(case_id: str, source_id: str):
    source, error = _source_or_error(case_id, source_id)
    if error:
        return error
    db = get_db()
    evidence_count = db.execute("SELECT COUNT(*) FROM evidence_items WHERE source_id=?", (source_id,)).fetchone()[0]
    extraction_job_ids = [
        row["id"] for row in db.execute("SELECT id,payload_json FROM jobs WHERE case_id=? AND job_type='extract_source'", (case_id,))
        if json.loads(row["payload_json"]).get("source_id") == source_id
    ]
    if extraction_job_ids:
        db.execute(f"DELETE FROM jobs WHERE id IN ({','.join('?' for _ in extraction_job_ids)})", extraction_job_ids)
    db.execute("DELETE FROM source_documents WHERE id=? AND case_id=?", (source_id, case_id))
    db.commit()

    storage_root = Path(current_app.config["STORAGE_ROOT"]).resolve()
    stored_file = (storage_root / source["storage_name"]).resolve()
    if stored_file.is_relative_to(storage_root) and stored_file.is_file():
        stored_file.unlink()
    audit("source.deleted", g.user["id"], case_id, source_id, {"evidence_count": evidence_count})
    return "", 204


@cases_bp.patch("/cases/<case_id>/sources/<source_id>")
@login_required
def rename_source(case_id: str, source_id: str):
    source, error = _source_or_error(case_id, source_id)
    if error:
        return error
    body = request.get_json(silent=True) or {}
    raw_filename = str(body.get("original_filename", source["original_filename"])).strip()
    filename = Path(raw_filename).name
    if not filename or filename != raw_filename or len(filename) > 255:
        return jsonify({"error": "invalid_filename"}), 400
    if Path(filename).suffix.lower() != Path(source["original_filename"]).suffix.lower():
        return jsonify({"error": "file_extension_cannot_change"}), 400
    assessment_type = body.get("assessment_type", source["assessment_type"])
    if assessment_type not in ASSESSMENT_TYPES:
        return jsonify({"error": "invalid_assessment_type"}), 400
    get_db().execute("UPDATE source_documents SET original_filename=?,assessment_type=?,instrument=? WHERE id=? AND case_id=?",
                     (filename, assessment_type, str(body.get("instrument", source["instrument"])), source_id, case_id))
    get_db().commit()
    audit("source.renamed", g.user["id"], case_id, source_id)
    return jsonify(row_dict(get_db().execute("SELECT * FROM source_documents WHERE id=?", (source_id,)).fetchone()))


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
    allowed = {"domain", "source_location", "supporting_text", "reporter", "setting", "confidence", "contradiction_status", "verified", "assessment_type", "criterion_ids", "timeframe"}
    if "assessment_type" in body and body["assessment_type"] not in ASSESSMENT_TYPES:
        return jsonify({"error": "invalid_assessment_type"}), 400
    if "timeframe" in body and body["timeframe"] not in TIMEFRAMES:
        return jsonify({"error": "invalid_timeframe"}), 400
    if "criterion_ids" in body and (not isinstance(body["criterion_ids"], list) or any(x not in CRITERIA for x in body["criterion_ids"])):
        return jsonify({"error": "invalid_criterion_ids"}), 400
    if set(body) & {"assessment_type", "criterion_ids", "timeframe", "supporting_text", "reporter", "domain", "setting", "source_location"}:
        body.setdefault("verified", False)
    if "domain" in body and body["domain"] not in DOMAINS:
        return jsonify({"error": "invalid_domain", "allowed_domains": list(DOMAINS)}), 400
    if "supporting_text" in body:
        supporting_text = str(body["supporting_text"]).strip()
        if not supporting_text or len(supporting_text) > 800:
            return jsonify({"error": "invalid_supporting_text"}), 400
        body["supporting_text"] = supporting_text
    if "confidence" in body:
        try:
            confidence = float(body["confidence"])
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_confidence"}), 400
        if not 0 <= confidence <= 1:
            return jsonify({"error": "invalid_confidence"}), 400
        body["confidence"] = confidence
    if "contradiction_status" in body and body["contradiction_status"] not in {"none", "possible", "confirmed"}:
        return jsonify({"error": "invalid_contradiction_status"}), 400
    fields, values = [], []
    for key in allowed:
        if key in body:
            fields.append(f"{'criterion_ids_json' if key == 'criterion_ids' else key}=?")
            values.append(json.dumps(body[key]) if key == "criterion_ids" else int(bool(body[key])) if key == "verified" else body[key])
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
    existing = row_dict(get_db().execute("SELECT * FROM criterion_assessments WHERE case_id=? AND criterion_id=?", (case_id, criterion_id)).fetchone())
    outcomes = {field: body.get(field, existing[field]) for field in ("clinician_outcome", "adulthood_outcome", "childhood_outcome")}
    if any(value not in OUTCOMES for value in outcomes.values()):
        return jsonify({"error": "invalid_outcome"}), 400
    evidence_ids = body.get("evidence_ids", existing["evidence_ids"])
    if evidence_ids:
        count = get_db().execute(
            f"SELECT COUNT(*) FROM evidence_items WHERE case_id=? AND id IN ({','.join('?' for _ in evidence_ids)})",
            (case_id, *evidence_ids),
        ).fetchone()[0]
        if count != len(set(evidence_ids)):
            return jsonify({"error": "invalid_evidence_reference"}), 400
    get_db().execute(
        "UPDATE criterion_assessments SET evidence_ids_json=?,settings_json=?,impairment=?,clinician_outcome=?,adulthood_outcome=?,childhood_outcome=?,notes=?,updated_at=? WHERE case_id=? AND criterion_id=?",
        (json.dumps(evidence_ids), json.dumps(body.get("settings", existing["settings"])), str(body.get("impairment", existing["impairment"])),
         outcomes["clinician_outcome"], outcomes["adulthood_outcome"], outcomes["childhood_outcome"], str(body.get("notes", existing["notes"])), now(), case_id, criterion_id),
    )
    get_db().commit()
    audit("criterion.updated", g.user["id"], case_id, criterion_id, {"outcomes": outcomes})
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
    assessment_type = body.get("assessment_type", "other")
    if assessment_type not in ASSESSMENT_TYPES:
        return jsonify({"error": "invalid_assessment_type"}), 400
    if not isinstance(body.get("scores", {}), dict):
        return jsonify({"error": "invalid_scores"}), 400
    item_id, timestamp = new_id(), now()
    get_db().execute(
        "INSERT INTO instrument_summaries(id,case_id,instrument,version,respondent,scores_json,interpretation,verified,assessment_type,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, case_id, str(body["instrument"]), str(body.get("version", "")), str(body.get("respondent", "")),
         json.dumps(body.get("scores", {})), str(body.get("interpretation", "")), int(bool(body.get("verified"))), assessment_type, timestamp, timestamp),
    )
    get_db().commit()
    audit("instrument.created", g.user["id"], case_id, item_id, {"instrument": str(body["instrument"])})
    return jsonify(row_dict(get_db().execute("SELECT * FROM instrument_summaries WHERE id=?", (item_id,)).fetchone())), 201


@cases_bp.patch("/cases/<case_id>/instruments/<instrument_id>")
@login_required
def update_instrument(case_id: str, instrument_id: str):
    _case, error = _case_or_error(case_id)
    if error:
        return error
    existing = row_dict(get_db().execute("SELECT * FROM instrument_summaries WHERE id=? AND case_id=?", (instrument_id, case_id)).fetchone())
    if not existing:
        return jsonify({"error": "instrument_not_found"}), 404
    body = request.get_json(silent=True) or {}
    assessment_type = body.get("assessment_type", existing["assessment_type"])
    if assessment_type not in ASSESSMENT_TYPES:
        return jsonify({"error": "invalid_assessment_type"}), 400
    scores = body.get("scores", existing["scores"])
    if not isinstance(scores, dict):
        return jsonify({"error": "invalid_scores"}), 400
    if not str(body.get("instrument", existing["instrument"])).strip():
        return jsonify({"error": "instrument_required"}), 400
    # Revised content needs verification again unless explicitly verified in this save.
    verified = bool(body.get("verified", False))
    get_db().execute(
        "UPDATE instrument_summaries SET instrument=?,version=?,assessment_type=?,scores_json=?,interpretation=?,respondent=?,verified=?,updated_at=? WHERE id=? AND case_id=?",
        (str(body.get("instrument", existing["instrument"])), str(body.get("version", existing["version"])), assessment_type, json.dumps(scores), str(body.get("interpretation", existing["interpretation"])),
         str(body.get("respondent", existing["respondent"])), int(verified), now(), instrument_id, case_id),
    )
    get_db().commit()
    audit("instrument.updated", g.user["id"], case_id, instrument_id)
    return jsonify(row_dict(get_db().execute("SELECT * FROM instrument_summaries WHERE id=?", (instrument_id,)).fetchone()))


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
    try:
        parsed = DraftResult.model_validate({"sections": sections})
    except ValidationError:
        return jsonify({"error": "invalid_report_sections"}), 400
    if "sections" in body:
        if [s.key for s in parsed.sections] != [s["key"] for s in draft["sections"]]:
            return jsonify({"error": "report_structure_cannot_change"}), 400
        original_owned = [(s["key"], p) for s in draft["sections"] for p in s["paragraphs"] if p.get("kind", "narrative") != "narrative"]
        supplied_owned = [(s["key"], p) for s in sections for p in s["paragraphs"] if p.get("kind", "narrative") != "narrative"]
        if supplied_owned != original_owned:
            return jsonify({"error": "generated_notices_and_intake_cannot_change", "message": "Update case intake or the clinician conclusion, then generate a new draft."}), 400
        evidence = [row_dict(r) for r in get_db().execute("SELECT * FROM evidence_items WHERE case_id=? AND verified=1", (case_id,))]
        instruments = [row_dict(r) for r in get_db().execute("SELECT * FROM instrument_summaries WHERE case_id=? AND verified=1", (case_id,))]
        checked = validate_draft(parsed, (draft.get("input_snapshot") or {}).get("case", _case), evidence, instruments)
        blocked = [w for w in checked.validation_warnings if "model paragraph(s) blocked" in w]
        if blocked:
            return jsonify({"error": "invalid_report_support", "requirements": blocked}), 400
        sections = parsed.model_dump()["sections"]
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
    if draft["state"] == "clinician-approved":
        return jsonify({"error": "approved_draft_is_immutable"}), 409
    if draft["state"] != "review-ready": failures.append("Draft must be marked review-ready.")
    if draft["warnings"] and not draft["warnings_acknowledged"]: failures.append("Clinical warnings must be acknowledged.")
    if not case["cloud_consent"]: failures.append("Cloud-processing consent must be acknowledged.")
    if not case["final_diagnostic_conclusion"].strip(): failures.append("A clinician-authored diagnostic conclusion is required.")
    criteria = [row_dict(r) for r in get_db().execute("SELECT * FROM criterion_assessments WHERE case_id=? ORDER BY criterion_id", (case_id,))]
    snapshot = draft.get("input_snapshot") or {}
    applicable_criteria = snapshot.get("criteria", criteria)
    if len(applicable_criteria) != 18 or any(row.get(field, "unreviewed") == "unreviewed" for row in applicable_criteria for field, _ in outcome_columns(case["cohort"])):
        failures.append("All 18 criteria must be reviewed for each applicable age period. Generate a new draft after reviewing decisions.")
    if snapshot:
        if sorted(snapshot["criteria"], key=lambda c: c["criterion_id"]) != criteria or any(
            snapshot["case"].get(field) != case.get(field) for field in ("final_diagnostic_conclusion", "demographics", "referral_question", "assessment_dates", "instruments")
        ):
            failures.append("Clinical inputs changed after drafting. Generate a new draft before approval.")
        current_evidence = [row_dict(r) for r in get_db().execute(
            "SELECT e.*,s.source_type,s.instrument AS source_instrument FROM evidence_items e JOIN source_documents s ON s.id=e.source_id WHERE e.case_id=? AND e.verified=1", (case_id,))]
        current_instruments = [row_dict(r) for r in get_db().execute("SELECT * FROM instrument_summaries WHERE case_id=? AND verified=1", (case_id,))]
        if any(sorted(snapshot.get(key, []), key=lambda x: x["id"]) != sorted(current, key=lambda x: x["id"])
               for key, current in (("evidence", current_evidence), ("instruments", current_instruments))):
            failures.append("Verified evidence or instrument summaries changed after drafting. Generate a new draft before approval.")
    conclusions = [p for section in draft["sections"] if section["key"] == "summary" for p in section["paragraphs"]
                   if p["text"] == case["final_diagnostic_conclusion"]]
    if len(conclusions) != 1:
        failures.append("The summary must contain the current clinician conclusion exactly once.")
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
