# JSON API

## Conventions

- Base path: `/api`.
- Authentication uses a server-side signed session cookie. Login and session responses also return a CSRF token.
- Every state-changing request after login must include `X-CSRF-Token: <token>`.
- When `PUBLIC_ORIGIN` is set, a supplied `Origin` header on state-changing requests must match it.
- Cookies are `Secure`, `HttpOnly`, and `SameSite=Strict` in the normal deployment. Set `COOKIE_SECURE=false` only for local HTTP development.
- Clinicians can access only cases assigned to them. Administrators can access all cases. Unavailable and unauthorised cases both return `case_not_found` to reduce identifier disclosure.
- JSON-backed database fields are returned without the `_json` suffix: for example, `demographics_json` becomes `demographics`.
- Boolean database flags are returned as JSON booleans.

Common response codes are `200` success, `201` created, `202` job accepted, `204` success with no body, `400` validation error, `401` unauthenticated or expired, `403` CSRF/origin/role failure, `404` not found, `409` invalid state transition, `413` upload too large, and `429` account locked.

Errors have at least an `error` code:

```json
{
  "error": "approval_requirements_not_met",
  "requirements": ["All 18 criterion outcomes must be reviewed."]
}
```

## Authentication

### `POST /auth/login`

No CSRF token is required. Login is limited to five failures in 15 minutes; the account is then locked for 30 minutes.

```json
{
  "username": "clinician",
  "password": "a-strong-password"
}
```

The response contains the public user record and CSRF token. The token must be kept in memory and sent on later mutations.

### `GET /auth/session`

Returns the current public user and a fresh view of the session CSRF token. Sessions have a 30-minute idle timeout and an eight-hour absolute limit.

### `POST /auth/logout`

Requires CSRF and clears the session. Returns `204`.

### `POST /auth/users`

Administrators can call this endpoint directly or use the interactive `scripts/create_user.sh` helper documented in [Operations](operations.md). The helper keeps passwords out of command-line arguments and handles login cookies and the CSRF token.

Administrator only. There is no public registration or email reset.

```json
{
  "username": "jane.smith",
  "full_name": "Dr Jane Smith",
  "registration_number": "PSY0000000000",
  "role": "clinician",
  "password": "FourteenChars1Plus"
}
```

Passwords require at least 14 characters with upper-case, lower-case, and numeric characters. Valid roles are `admin` and `clinician`.

## Cases

### `GET /cases`

Returns assigned cases ordered by most recently updated; administrators receive all cases.

### `POST /cases`

Creates the case and its 18 initially `unreviewed` criterion records.

```json
{
  "cohort": "adult",
  "patient_initials": "AB",
  "demographics": {"age": 34, "pronouns": "they/them"},
  "referral_question": "Clarify longstanding attention and organisation concerns.",
  "assessment_dates": ["2026-08-05"],
  "instruments": ["Authorised scored export"],
  "cloud_consent": true,
  "assigned_user_id": "optional-admin-only-target-user-id"
}
```

Required fields are `cohort` (`adult` or `adolescent`) and `patient_initials`. Non-admin users are always assigned their own cases.

### `GET /cases/{case_id}`

Returns one aggregate object containing `case`, `sources`, `evidence`, `criteria`, `instruments`, `drafts`, the 20 most recent `jobs`, and computed `warnings`. Extracted source text and internal storage paths are not exposed.

### `PATCH /cases/{case_id}`

Accepts any of `patient_initials`, `demographics`, `referral_question`, `assessment_dates`, `instruments`, `cloud_consent`, and `final_diagnostic_conclusion`.

```json
{
  "cloud_consent": true,
  "final_diagnostic_conclusion": "Clinician-authored conclusion after review."
}
```

### `POST /cases/{case_id}/archive`

Sets the case status to `archived` and returns `204`. The POC archives rather than automatically deletes clinical records.

## Sources and evidence

### `POST /cases/{case_id}/sources`

Send `multipart/form-data` with:

| Field | Required | Meaning |
| --- | --- | --- |
| `file` | Yes | `.txt`, `.docx`, or `.pdf`, up to the configured limit |
| `source_type` | No | Defaults to `transcript` |
| `reporter` | No | Patient, parent, teacher, partner, clinician, or another supplied label |
| `setting` | No | Home, school, work, clinic, or another supplied label |
| `instrument` | No | Instrument identity for an authorised result export |

The server stores a SHA-256 hash and returns `202` with `source_id` and an `extract_source` job. Poll the job endpoint or reload the case.

### `PATCH /cases/{case_id}/evidence/{evidence_id}`

Accepted fields are `domain`, `source_location`, `supporting_text`, `reporter`, `setting`, `confidence`, `contradiction_status`, and `verified`.

`domain` is validated against the clinical domain catalog returned as `evidence_domains` by `GET /api/cases/{case_id}`. Invalid values return `400 invalid_domain` with `allowed_domains`.

```json
{
  "domain": "impairment",
  "source_location": "paragraph 12",
  "reporter": "patient",
  "setting": "work",
  "confidence": 0.92,
  "contradiction_status": "none",
  "verified": true
}
```

Setting `verified` is a clinician action; extraction never sets it automatically.

## Criteria and instruments

### `PUT /cases/{case_id}/criteria/{criterion_id}`

Criterion identifiers are the nine inattentive and nine hyperactive/impulsive identifiers defined by the versioned clinical schema. Evidence identifiers must belong to the same case.

```json
{
  "evidence_ids": ["evidence-uuid"],
  "settings": ["home", "work"],
  "impairment": "Clinician-entered functional impact.",
  "clinician_outcome": "met",
  "notes": "Clinician reasoning and qualifications."
}
```

Valid outcomes are `unreviewed`, `met`, `not_met`, and `insufficient`. An invalid identifier, outcome, or cross-case evidence reference returns `400`.

### `POST /cases/{case_id}/instruments`

```json
{
  "instrument": "Instrument name",
  "version": "Version supplied in the export",
  "respondent": "patient",
  "scores": {"authorised_scale_label": "verified supplied value"},
  "interpretation": "Clinician interpretation; not an automated diagnosis.",
  "verified": true
}
```

The API stores already-scored values; it does not accept raw answers for proprietary scoring.

## Drafts, approval, and files

### `POST /cases/{case_id}/drafts`

Queues `generate_draft` and returns `202`. If Bedrock is enabled, the case must already record cloud consent.

### `PATCH /cases/{case_id}/drafts/{draft_id}`

Updates an editable draft and queues rendering.

```json
{
  "sections": [
    {
      "key": "referral",
      "heading": "Referral and presenting concerns",
      "paragraphs": [
        {"text": "Clinician-reviewed text.", "evidence_ids": ["evidence-uuid"]}
      ]
    }
  ],
  "warnings_acknowledged": true,
  "state": "review-ready"
}
```

Valid editable states are `draft` and `review-ready`. A `clinician-approved` draft is immutable and returns `409` on edit.

### `POST /cases/{case_id}/drafts/{draft_id}/approve`

Requires a review-ready draft, warning acknowledgement where warnings exist, cloud-processing consent, a clinician-authored final conclusion, all 18 criteria reviewed, and at least one verified evidence item. On success, the snapshot becomes `clinician-approved` and a final render job is queued.

### `GET /cases/{case_id}/drafts/{draft_id}/docx`

Downloads the editable Word report when rendering is complete.

### `GET /cases/{case_id}/drafts/{draft_id}/preview`

Displays the generated PDF preview when LibreOffice conversion is complete. A missing converter or not-yet-finished render returns `404` with `report_file_not_ready`.

## Jobs

### `GET /jobs/{job_id}`

Returns a job only if the current user can access its case. Relevant fields are `job_type`, `status`, `attempts`, `available_at`, `last_error`, and timestamps. `last_error` contains only an exception class, not clinical text.

Job statuses are `queued`, `running`, `completed`, and `failed`. Transient failures retry twice after the first attempt with bounded exponential delays; a third failed attempt becomes terminal.
