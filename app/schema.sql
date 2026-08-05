PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL,
  registration_number TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','clinician')),
  active INTEGER NOT NULL DEFAULT 1,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  first_failed_at TEXT,
  locked_until TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  cohort TEXT NOT NULL CHECK(cohort IN ('adult','adolescent')),
  patient_initials TEXT NOT NULL,
  demographics_json TEXT NOT NULL DEFAULT '{}',
  referral_question TEXT NOT NULL DEFAULT '',
  assessment_dates_json TEXT NOT NULL DEFAULT '[]',
  instruments_json TEXT NOT NULL DEFAULT '[]',
  cloud_consent INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  final_diagnostic_conclusion TEXT NOT NULL DEFAULT '',
  assigned_user_id TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_documents (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  reporter TEXT NOT NULL DEFAULT '',
  setting TEXT NOT NULL DEFAULT '',
  instrument TEXT NOT NULL DEFAULT '',
  original_filename TEXT NOT NULL,
  storage_name TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  extraction_status TEXT NOT NULL DEFAULT 'pending',
  extracted_text TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_items (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
  domain TEXT NOT NULL,
  source_location TEXT NOT NULL,
  supporting_text TEXT NOT NULL,
  reporter TEXT NOT NULL DEFAULT '',
  setting TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0,
  contradiction_status TEXT NOT NULL DEFAULT 'none',
  verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instrument_summaries (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  instrument TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT '',
  respondent TEXT NOT NULL DEFAULT '',
  scores_json TEXT NOT NULL DEFAULT '{}',
  interpretation TEXT NOT NULL DEFAULT '',
  verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS criterion_assessments (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  criterion_id TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  settings_json TEXT NOT NULL DEFAULT '[]',
  impairment TEXT NOT NULL DEFAULT '',
  clinician_outcome TEXT NOT NULL DEFAULT 'unreviewed',
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  UNIQUE(case_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS report_drafts (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  sections_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  warnings_acknowledged INTEGER NOT NULL DEFAULT 0,
  template_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  model_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'draft',
  approved_by TEXT REFERENCES users(id),
  approved_at TEXT,
  docx_path TEXT,
  preview_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(case_id, version)
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  case_id TEXT REFERENCES cases(id) ON DELETE CASCADE,
  job_type TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  available_at TEXT NOT NULL,
  locked_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  actor_user_id TEXT REFERENCES users(id),
  action TEXT NOT NULL,
  case_id TEXT REFERENCES cases(id) ON DELETE SET NULL,
  target_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(assigned_user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_sources_case ON source_documents(case_id);
CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence_items(case_id);
CREATE INDEX IF NOT EXISTS idx_jobs_ready ON jobs(status, available_at);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id, created_at);

