from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

from app.db import get_db
from app.jobs import claim_next_job, complete
from app.jobs import enqueue
from app.worker import process_job


def _run_jobs(app):
    with app.app_context():
        while job := claim_next_job():
            process_job(job)
            complete(job["id"])


def test_complete_clinician_workflow(app, authenticated, sample_txt):
    client, headers = authenticated
    created = client.post("/api/cases", headers=headers, json={
        "cohort": "adult", "patient_initials": "T. C.", "referral_question": "Assessment for possible ADHD",
        "cloud_consent": True, "assessment_dates": ["2026-08-01"], "instruments": ["DIVA-5"],
    })
    assert created.status_code == 201
    case_id = created.json["id"]

    uploaded = client.post(
        f"/api/cases/{case_id}/sources", headers=headers,
        data={"file": sample_txt, "source_type": "transcript", "reporter": "patient", "setting": "clinical"},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 202
    _run_jobs(app)

    detail = client.get(f"/api/cases/{case_id}").json
    assert detail["sources"][0]["extraction_status"] == "completed"
    assert detail["evidence"]
    for item in detail["evidence"]:
        result = client.patch(f"/api/cases/{case_id}/evidence/{item['id']}", headers=headers, json={"verified": True})
        assert result.status_code == 200

    requested = client.post(f"/api/cases/{case_id}/drafts", headers=headers, json={})
    assert requested.status_code == 202
    _run_jobs(app)
    detail = client.get(f"/api/cases/{case_id}").json
    draft = detail["drafts"][0]
    assert draft["docx_path"]
    assert all(set(p["evidence_ids"]).issubset({e["id"] for e in detail["evidence"]})
               for section in draft["sections"] for p in section["paragraphs"])

    blocked = client.post(f"/api/cases/{case_id}/drafts/{draft['id']}/approve", headers=headers, json={})
    assert blocked.status_code == 409
    assert "All 18 criterion outcomes" in " ".join(blocked.json["requirements"])

    client.patch(f"/api/cases/{case_id}", headers=headers, json={"final_diagnostic_conclusion": "The clinician concludes that available information is insufficient for an ADHD diagnosis."})
    for criterion in detail["criteria"]:
        result = client.put(f"/api/cases/{case_id}/criteria/{criterion['criterion_id']}", headers=headers,
                            json={"clinician_outcome": "not_met", "evidence_ids": [], "settings": [], "impairment": "", "notes": "Reviewed by clinician."})
        assert result.status_code == 200
    client.patch(f"/api/cases/{case_id}/drafts/{draft['id']}", headers=headers,
                 json={"state": "review-ready", "warnings_acknowledged": True})
    _run_jobs(app)
    approved = client.post(f"/api/cases/{case_id}/drafts/{draft['id']}/approve", headers=headers, json={})
    assert approved.status_code == 200
    assert approved.json["state"] == "clinician-approved"
    _run_jobs(app)
    assert client.get(f"/api/cases/{case_id}/drafts/{draft['id']}/docx").status_code == 200

    immutable = client.patch(f"/api/cases/{case_id}/drafts/{draft['id']}", headers=headers, json={"state": "draft"})
    assert immutable.status_code == 409


def test_csrf_and_case_authorization(app, authenticated):
    client, headers = authenticated
    assert client.post("/api/cases", json={"cohort": "adult", "patient_initials": "X"}).status_code == 403
    new_user = client.post("/api/auth/users", headers=headers, json={
        "username": "other", "full_name": "Other Clinician", "password": "Another-Strong-Password-2026", "role": "clinician",
    })
    assert new_user.status_code == 201
    case = client.post("/api/cases", headers=headers, json={"cohort": "adolescent", "patient_initials": "A. A."}).json
    other = app.test_client()
    login = other.post("/api/auth/login", json={"username": "other", "password": "Another-Strong-Password-2026"})
    assert login.status_code == 200
    assert other.get(f"/api/cases/{case['id']}").status_code == 404


def test_login_lockout(client):
    for _ in range(5):
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
        assert response.status_code == 401
    response = client.post("/api/auth/login", json={"username": "admin", "password": "A-very-long-Test-Password-2026"})
    assert response.status_code == 429


def test_five_sessions_and_atomic_job_claiming(app):
    def session_request(_index):
        client = app.test_client()
        login = client.post("/api/auth/login", json={"username": "admin", "password": "A-very-long-Test-Password-2026"})
        return login.status_code, client.get("/api/cases").status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert list(pool.map(session_request, range(5))) == [(200, 200)] * 5

    with app.app_context():
        first = enqueue("render_draft", None, {"draft_id": "one"})
        second = enqueue("render_draft", None, {"draft_id": "two"})

    def claim(_index):
        with app.app_context():
            job = claim_next_job()
            return job["id"] if job else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(claim, range(2)))
    assert set(claimed) == {first["id"], second["id"]}
