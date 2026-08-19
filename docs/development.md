# Development and testing

## Repository layout

```text
app/                 Flask API, clinical rules, database, AI adapter, jobs, parsers, reporting
frontend/            React/Vite clinician interface and frontend tests
templates/           De-identified report template
scripts/             Operational and template-building utilities
tests/               Backend workflow, security, parser, and report tests
deploy/              Caddy configuration
docs/                Implementation and operating documentation
Dockerfile           Multi-stage frontend and Python/LibreOffice image
docker-compose.yml   Web, worker, and Caddy deployment
manage.py            Administrative commands
```

## Development principles

- Keep clinical decisions explicit and clinician-controlled. Never introduce automatic diagnosis or approval as a convenience.
- Treat uploaded content and model output as untrusted data.
- Keep AI access behind the adapter and return schema-validated objects.
- Maintain evidence provenance through source and evidence identifiers.
- Keep rendering deterministic; model text cannot modify DOCX layout or execute code.
- Do not log patient information, prompts, source text, generated prose, credentials, or session tokens.
- Add or update documentation with every material code, schema, workflow, deployment, or clinical-control change.
- Use synthetic/de-identified fixtures only. Never commit the supplied example report or derived patient information.

## Backend workflow

Create a virtual environment and install dependencies as described in [deployment](deployment.md). The Flask application factory initialises directories and the SQLite schema. Run the API and worker as separate processes so asynchronous behaviour matches deployment.

Useful commands:

```sh
make bootstrap
make dev
# In a second terminal:
make dev-worker

make test
make test-backend
make frontend-test
make personas
```

`make dev` builds the React application and runs Flask at `http://localhost:8000` in the foreground. It forces local HTTP settings and the non-diagnostic local organiser; it does not make Bedrock requests. `make dev-up` and `make dev-down` provide the equivalent background processes and write only ignored `.run/` PID/log files. Use `make help` to see every supported command.

Backend tests should use temporary databases and storage roots. Never point tests at a live or clinician-used database.

### Resetting local development data

Stop Flask and the background worker, then run this command from the repository root:

```sh
make reset-local-data CONFIRM=DELETE
```

The target permanently removes the local `data` and `storage` directories, including accounts, cases, evidence, jobs, uploaded sources, previews, and generated reports. It recreates empty directories and deliberately leaves `backups` untouched. It refuses to run without the exact confirmation value, outside the project root, or when `lsof` reports that the SQLite database is still open.

Create a fresh administrator afterward:

```sh
python manage.py create-admin --username admin --full-name "Clinical Administrator"
```

## Frontend workflow

```sh
cd frontend
npm install
npm test
npm run build
```

The production Flask container serves `frontend/dist`. Rebuild it after UI changes. UI controls are usability aids; authorization, validation, approval gates, and consent checks must remain enforced by Flask.

## Required test coverage

The reproducible synthetic persona library is documented in [`test-data/README.md`](../test-data/README.md). Regenerate it with `python scripts/generate_test_personas.py`. Expected-review files are test oracles and must never be uploaded as case sources.

### Clinical safety

- Adult and adolescent fixtures with multiple reporters and settings.
- Contradictory observations and low-confidence extraction.
- Missing developmental, medical, mental-health, impairment, differential, strengths, setting, and collateral evidence.
- Positive, negative, and uncertain conclusions.
- Rating-scale-only cases that cannot reach approval without clinician evidence and decisions.
- Unsupported claims, invented scores, and ungrounded recommendations visibly rejected or flagged.
- All 18 criteria and the final conclusion remain clinician-set.

### File processing

- Valid TXT, DOCX, and text PDFs.
- Scanned/non-text PDF, malformed document, encrypted document, macro-enabled document, spoofed extension, unsafe filename, and oversized upload.
- Source locations remain stable enough for a clinician to find the supporting passage.

### Security and permissions

- Correct/incorrect login, five-attempt lockout, idle and absolute expiry.
- CSRF and mismatched origin rejection.
- Admin versus clinician permissions and cross-user case/job access.
- Audit coverage without clinical text.
- Approved-draft immutability.

### Reliability and rendering

- Bedrock timeout and invalid structured output.
- Internet outage, worker crash, stale job recovery, Pi/container restart, full disk, and failed LibreOffice conversion.
- Five browser sessions and two simultaneous jobs without an unresponsive UI or SQLite lock failures.
- Report versions are not duplicated during retries.
- Generated DOCX files remain editable and representative rendered pages match the template contract.

## DOCX visual QA

When the template or report mapping changes:

1. Generate representative adult and adolescent reports using synthetic fixtures.
2. Render each DOCX through headless LibreOffice to PDF and page images.
3. Inspect cover page, headings, body typography, tables, headers/footers, page breaks, criteria, recommendations, appendices, clipping, and blank pages.
4. Open the DOCX in Word or a compatible editor and confirm paragraphs and tables remain editable.
5. Compare representative pages with the de-identified visual tokens in [the template contract](template-artifact.md).
6. Record a new template version when layout meaningfully changes.

Do not use the original identifiable report as a checked-in golden file.

## Extending a source format

1. Confirm the format is clinically authorised and can be parsed without executing embedded content.
2. Add an explicit extension and content-signature/MIME policy; an extension alone is insufficient for high-risk formats.
3. Implement bounded local extraction with page/paragraph locations and safe failure messages.
4. Prevent macros, embedded executables, external-resource fetching, decompression bombs, and path traversal.
5. Add valid, malformed, encrypted, oversized, and spoofed fixtures.
6. Update [the clinical workflow](clinical-workflow.md), [API](api.md), and deployment dependencies.

OCR and audio transcription need a separate privacy, accuracy, consent, resource, and provenance design; they should not be added as a silent parser fallback.

## Changing a clinical schema

Adult and adolescent schemas and report structures are versioned clinical artefacts. A change requires:

1. rationale and registered-psychologist review;
2. schema validation and backward-compatibility decisions for existing cases;
3. updated completeness rules and approval-gate tests;
4. prompt and local-adapter alignment;
5. DOCX mapping and visual QA;
6. documentation and fixture updates; and
7. an explicit new schema/prompt/template version where applicable.

Never rewrite an already approved snapshot to a new schema.

## Changing the AI provider or model

Implement the existing extraction and drafting interface rather than passing provider-specific objects into routes or database records. Pin and store the provider model identifier and prompt version. Validate structured output, enforce consent and regional-processing requirements, bound retries, and repeat clinical safety testing on the historical de-identified validation set.

AgentCore or Strands may later orchestrate the same interfaces, but they must not weaken schema validation, evidence provenance, approval gates, audit boundaries, or clinician control.

## Definition of done

A change is complete when its tests pass, relevant threat and failure paths are covered, generated documents are visually verified when affected, no patient data is present in the diff, and the affected documents in this directory describe the new behaviour accurately.
