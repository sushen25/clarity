# Deployment guide

## Environment configuration

Copy `.env.example` to `.env`; `.env` is excluded from source control. Production values must not use the development defaults.

| Variable | Default/example | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | replace | Random secret of at least 32 bytes for signed sessions |
| `LOG_LEVEL` | `INFO` | Application log threshold; `INFO` shows AI provider and Bedrock request lifecycle records |
| `DATABASE_PATH` | `data/app.db` | SQLite database path; Compose overrides it with `/data/app.db` |
| `STORAGE_ROOT` | `storage` | Source and generated-document root; Compose overrides it with `/storage` |
| `COOKIE_SECURE` | `false` locally | Send the session cookie only over HTTPS; must be `true` in deployment |
| `PUBLIC_ORIGIN` | `http://localhost:8000` locally | Exact allowed browser origin for mutations; replace with the HTTPS production origin |
| `PUBLIC_DOMAIN` | `reports.example.com` | Caddy hostname and certificate name |
| `BEDROCK_ENABLED` | `false` | Enables real AWS model calls when `true` |
| `AWS_REGION` | `ap-southeast-2` | Bedrock client region |
| `BEDROCK_MODEL_ID` | `au.anthropic.claude-sonnet-4-6` | Pinned Australian geographic inference profile |
| `BEDROCK_CONNECT_TIMEOUT_SECONDS` | `10` | Maximum time to establish a Bedrock connection |
| `BEDROCK_READ_TIMEOUT_SECONDS` | `600` | Maximum wait for one non-streaming Bedrock response |
| `BEDROCK_SDK_MAX_ATTEMPTS` | `2` | Total initial and retry HTTP attempts made by the AWS SDK |
| `BEDROCK_EXTRACTION_MAX_TOKENS` | `8000` | Maximum model output for an extraction request |
| `BEDROCK_DRAFT_MAX_TOKENS` | `7000` | Maximum model output for a report-drafting request |
| `PROMPT_VERSION` | `2026-08-poc-v2` | Version recorded with generated drafts |
| `REPORT_TEMPLATE` | `templates/adhd_report_template.docx` | De-identified template; Compose overrides it with the container path |
| `LIBREOFFICE_BIN` | `soffice` | Headless preview converter executable |
| `MAX_UPLOAD_MB` | `25` | Whole-request upload limit in MB |
| `WORKER_POLL_SECONDS` | `2` | Worker idle polling interval; optional |

The application also uses the standard AWS credential provider chain. Give the deployment identity only the permissions needed to invoke the configured Bedrock model/profile. Do not grant broad administrator permissions. Store credentials in the protected deployment environment or another supported credential provider, never in Git, images, reports, or logs.

## Local development

Prerequisites are Python 3.12+, Node 22+, and LibreOffice when PDF preview testing is required.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cd frontend
npm install
npm run build
cd ..
python manage.py create-admin --username admin --full-name "Clinical Administrator"
COOKIE_SECURE=false flask --app 'app:create_app()' run --debug --port 8000
```

In a second terminal:

```sh
. .venv/bin/activate
COOKIE_SECURE=false python -m app.worker
```

The example file is deliberately configured for local HTTP. Set `COOKIE_SECURE=true` and replace `PUBLIC_ORIGIN` with the exact HTTPS origin for every deployed instance. Docker Compose overrides the local database, storage, and template paths with its mounted container paths.

## Bedrock enablement

Before enabling Bedrock:

1. Confirm access to the Australian geographic inference profile in the chosen AWS account.
2. Create a least-privilege IAM identity limited to the required Bedrock invocation actions and model/profile resource where IAM supports it.
3. Configure AWS credentials outside the repository and test credential rotation.
4. Confirm `AWS_REGION=ap-southeast-2` and `BEDROCK_MODEL_ID=au.anthropic.claude-sonnet-4-6`.
5. Complete the privacy impact and threat assessments and confirm the patient-facing notice/consent wording.
6. Set `BEDROCK_ENABLED=true`, restart web and worker, and run a synthetic extraction and draft.
7. Verify that draft records contain the expected model and prompt versions and that logs contain no submitted text.

Never enable cloud processing merely to make a local test pass. The local organiser exists for offline workflow development and is intentionally non-diagnostic.

### Confirming which AI provider is active

Run the background worker in the foreground while testing. With `LOG_LEVEL=INFO`, it emits a privacy-safe provider record for every extraction or drafting job. When Bedrock is enabled, a successful call produces lines resembling:

```text
clinical_ai.provider_selected provider=bedrock region=ap-southeast-2 model_id=au.anthropic.claude-sonnet-4-6
bedrock.request_started operation=extract region=ap-southeast-2 model_id=au.anthropic.claude-sonnet-4-6
bedrock.http_attempt operation=extract attempt=1 max_attempts=2
bedrock.response_received operation=extract region=ap-southeast-2 model_id=au.anthropic.claude-sonnet-4-6 duration_ms=1234 http_attempts=1 request_id=... stop_reason=end_turn input_tokens=... output_tokens=...
```

If cloud processing is disabled, the provider line instead contains `provider=local-heuristic bedrock_enabled=false`. Bedrock failures produce `bedrock.request_failed` with the exception type, AWS error code, and AWS request ID before the job retry mechanism handles the failure.

These records deliberately omit source text, prompts, model output, patient identifiers, credentials, and exception messages. Do not enable Boto3/Botocore wire-level debug logging when processing clinical material because those logs can include request content.

Bedrock uses a 10-minute read timeout for each non-streaming request and at most two total SDK HTTP attempts. Each attempt emits `bedrock.http_attempt`, making an SDK retry visible without enabling unsafe wire logging. Extraction and drafting use separate output limits so a draft cannot silently inherit an unnecessarily large extraction allowance. The SQLite job queue can still retry a failed job according to its bounded retry policy.

Only transient network, timeout, throttling, model-not-ready, and Bedrock service errors are retried. JSON, schema, evidence-link, and other deterministic validation failures fail immediately to avoid repeated paid calls. The Report screen shows queued/running attempts and sanitized failure codes, and the API returns an existing active draft job instead of creating a duplicate.

## Raspberry Pi deployment

### Host preparation

- Raspberry Pi 5 with at least 8 GB RAM, 64-bit Raspberry Pi OS, active cooling, and a UPS.
- External SSD for `data`, `storage`, and `backups`; encrypt it with LUKS or an equivalent host-level mechanism.
- Docker Engine and Compose plugin installed from the supported Raspberry Pi/Debian packages.
- Stable time synchronisation, because sessions, locks, audit events, TLS, and backups depend on correct time.
- A static LAN address or DHCP reservation.

Place the repository on the encrypted volume or ensure that every writable bind mount points there. Restrict ownership and permissions to the deployment administrator and the container runtime. Ensure the encrypted volume is mounted before Docker starts; otherwise Docker may silently create unencrypted directories at the mount point.

### Build and start

```sh
cp .env.example .env
# Edit SECRET_KEY, PUBLIC_DOMAIN, PUBLIC_ORIGIN, and set COOKIE_SECURE=true.
docker compose build
docker compose run --rm web python manage.py create-admin --username admin --full-name "Clinical Administrator"
docker compose up -d
docker compose ps
```

The image builds the React frontend, installs the Python application and LibreOffice Writer, and runs Gunicorn with two workers and two threads. A separate container runs the single background worker. Both containers mount the same database and storage directories.

### Network and TLS

1. Point the selected DNS name to the practice’s public IP.
2. Set `PUBLIC_DOMAIN` and the matching `PUBLIC_ORIGIN=https://<domain>`.
3. Forward TCP and UDP port 443 to the Pi. Do not expose port 8000 or the database/storage shares.
4. Caddy obtains and renews the HTTPS certificate and proxies requests to the web container.
5. Keep SSH key-only, disable password login, and limit source IPs through the router/firewall or VPN where available.

If the site is intended only for practice-network/VPN access, use a compatible private DNS and certificate strategy rather than bypassing TLS checks.

## First-deployment verification

- `docker compose ps` reports the web service healthy and worker/Caddy running.
- `https://<domain>/api/health` returns success without revealing configuration or patient data.
- Login succeeds, logout clears the session, and a wrong browser origin is rejected.
- A synthetic TXT, DOCX, and text PDF can be uploaded and extracted.
- A synthetic draft can be generated, edited, rendered, previewed, and downloaded.
- A worker/container restart does not duplicate a report version.
- Cross-user case access returns `404`.
- A backup completes to the encrypted destination and a restoration rehearsal succeeds.
- Proxy, application, Docker, and AWS diagnostic logs contain no patient names, narrative, prompts, or model responses.

Do not load live patient material until every mandatory item in [the privacy and threat checklist](privacy-and-threat-checklist.md) is complete.
