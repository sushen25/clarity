# Clarity — ADHD assessment report drafting POC

Clarity is a clinician-only workflow for organising adult and adolescent ADHD assessment evidence and producing an editable, clinician-reviewed Word report. It runs the web application, SQLite database, file processing, and report rendering on a Raspberry Pi; optional drafting calls Amazon Bedrock in Australia.

The system does **not** diagnose patients, score proprietary instruments, reproduce test items, or approve a report. Every evidence item, DSM criterion outcome, warning acknowledgement, and final diagnostic conclusion remains under clinician control.

Complete implementation, clinical, API, deployment, operations, security, and testing documentation is indexed in [docs/README.md](docs/README.md).

The root [Makefile](Makefile) provides the standard local-development and Raspberry Pi deployment commands. Run `make help` for the complete list.

## What is implemented

- Admin-created clinician accounts with Argon2id password hashing, secure sessions, CSRF protection, lockout, and case-level authorization.
- Adult/adolescent cases, consent acknowledgement, source uploads, local TXT/DOCX/PDF extraction, evidence verification, instrument summaries, 18 criterion decisions, report warnings, and audit events.
- SQLite-backed resumable jobs with one background worker and bounded retries.
- Bedrock adapter for `au.anthropic.claude-sonnet-4-6`, plus a non-diagnostic local organiser for development without AWS credentials.
- Versioned drafts, evidence-linked paragraphs, immutable clinician approval, editable DOCX output, and PDF preview when LibreOffice is available.
- React clinician workspace, Pi-ready Docker Compose deployment, Caddy HTTPS termination, and consistent backup tooling.

## Local development

Prerequisites: Python 3.12+, Node 22+, and LibreOffice for PDF previews.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py create-admin --username admin --full-name "Clinical Administrator"
cd frontend && npm install && npm run build && cd ..
flask --app 'app:create_app()' run --debug --port 8000
```

In a second terminal:

```sh
. .venv/bin/activate
python -m app.worker
```

Open `http://localhost:8000`. Development defaults to the local evidence organiser. Set `BEDROCK_ENABLED=true` only after configuring the restricted AWS credential and completing the consent/privacy review.

## Raspberry Pi deployment

1. Use a 64-bit Raspberry Pi OS on a Pi 5 with 8 GB+ RAM, external SSD, active cooling, and UPS.
2. Put `data`, `storage`, and `backups` on a LUKS-encrypted volume. The application does not claim to encrypt an unencrypted host filesystem by itself.
3. Copy `.env.example` to `.env`, generate a random `SECRET_KEY`, set `PUBLIC_DOMAIN` and `PUBLIC_ORIGIN`, and change `COOKIE_SECURE=true`. Docker Compose supplies the container paths for the database, storage, and template. Configure the restricted Bedrock credential outside source control.
4. Point the domain to the clinic’s public IP and forward TCP/UDP 443 only to the Pi. Restrict SSH separately.
5. Run `docker compose build` and `docker compose up -d`.
6. Bootstrap the first account with `docker compose run --rm web python manage.py create-admin ...` before allowing clinician access.
7. Schedule `python scripts/backup.py` daily to an encrypted backup target and perform a restoration test.

## Bedrock and privacy

The configured model ID is the Australian geographic inference profile, which can process requests in Sydney or Melbourne. The model and prompt IDs are stored with each draft. Application logs and audit metadata exclude patient narrative, but source documents and extracted evidence are health records and must reside on encrypted storage.

Read [the pre-live checklist](docs/privacy-and-threat-checklist.md). TOTP MFA, a completed privacy impact assessment, and clinical validation on five de-identified cases are mandatory before routine use with live patient data.

## Tests

```sh
pytest
cd frontend && npm test
```

The reference report itself is never copied into the repository. The checked-in DOCX template was newly built from de-identified visual tokens recorded in [the template contract](docs/template-artifact.md).
