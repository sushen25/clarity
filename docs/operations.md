# Operations runbook

## Routine checks

### Daily

- Confirm the HTTPS site and `/api/health` respond.
- Check that `web`, `worker`, and `caddy` are running and that the web health check is passing.
- Review failed jobs by status and exception class; do not paste clinical inputs into tickets or chat.
- Check free space on the encrypted application and backup volumes.
- Confirm the daily backup completed and its directory contains both `app.db` and `storage`.

### Weekly

- Review account, login-failure, upload, approval, download, archive, and any deletion audit events.
- Confirm Caddy certificate renewal is healthy.
- Check OS/container security updates and plan a backed-up maintenance window.
- Inspect UPS health and verify system time synchronisation.

### Quarterly and after material changes

- Restore a backup into an isolated test location and open representative generated files.
- Review access lists and rotate credentials according to practice policy.
- Re-run authentication, authorization, clinical safety, rendering, and outage tests.
- Review the privacy impact assessment, threat model, model/profile selection, prompt version, and clinical validation status.

## Job behaviour

The worker atomically claims one `queued` job at a time. Jobs become `running`, then `completed`. A failure records only the exception class and returns the job to the queue with exponential delay while fewer than three attempts have occurred. The third failure becomes `failed`.

A job left `running` for more than ten minutes is considered stale and returned to the queue during the next claim. Extraction and rendering handlers must therefore remain idempotent: retrying must replace or reuse the intended result, not create uncontrolled report versions.

When investigating a failed job:

1. Record the job ID, type, timestamps, attempt count, and exception class.
2. Confirm the source/report path exists and the encrypted volume is mounted.
3. Check free disk space and filesystem permissions.
4. For extraction, confirm the file is supported, not encrypted/malformed, and contains text.
5. For drafting, confirm connectivity, AWS identity, model access, consent, model ID, and validated response shape.
6. For rendering, confirm the template exists and `soffice` is available.
7. Correct the operational cause and allow a queued retry. A terminal failed job currently requires an administrator/developer to enqueue the equivalent action again through the normal UI/API flow.

## Backups

Run the included backup utility once daily from the host, targeting a mounted encrypted backup disk or encrypted remote destination:

```sh
python scripts/backup.py \
  --database data/app.db \
  --storage storage \
  --destination backups
```

The utility uses SQLite’s online backup API for a consistent database copy, then copies source and generated files into a UTC timestamped directory. With one run per day, retention keeps the most recent seven days plus Monday snapshots within four weeks. The destination itself must already be encrypted; the utility does not encrypt it.

Monitor exit status and free space. A backup is incomplete if either `app.db` or `storage` is absent. Keep at least one copy physically or logically separate from the Pi, with access restricted to authorised practice staff.

## Restoration rehearsal

Perform restoration first in an isolated directory or test Pi. Do not overwrite the live instance as the first validation.

1. Stop the test web and worker so no writes occur.
2. Verify the selected timestamped backup includes `app.db` and `storage` and is on encrypted media.
3. Preserve the current test `data` and `storage` directories by renaming them with a timestamp.
4. Copy the backup database to the configured `DATABASE_PATH` and the backup storage tree to `STORAGE_ROOT`.
5. Apply the same restricted ownership and permissions used by the containers.
6. Start web and worker, then check health, login, case counts, source availability, evidence, approved snapshots, DOCX downloads, and previews.
7. Generate and render a new synthetic draft to verify the restored database is writable.
8. Record the restoration date, operator, selected backup, result, and any corrective action without clinical narrative.

A real disaster recovery follows the same sequence after the incident lead confirms the exact recovery point and retention obligations.

## Upgrades and rollback

1. Read release notes and identify changes to schemas, templates, prompts, model identifiers, and environment variables.
2. Complete and verify a fresh encrypted backup.
3. Rehearse the upgrade against a restored copy when a schema or rendering change is involved.
4. Build images before the maintenance window where practical.
5. Stop new clinician work, allow current jobs to finish, and stop services.
6. Deploy the new version, run migrations when introduced, start services, and execute the deployment verification checks.
7. If verification fails, stop services and restore the prior code/image plus matching database and storage snapshot. Do not run older code against a newly migrated database unless backward compatibility was explicitly tested.

Prompt, model, and template changes are clinical-output changes and require representative snapshot and psychologist review, not merely an infrastructure deployment.

## Account operations

- Create the first administrator with `manage.py create-admin`; subsequent users are admin-created through the protected API/UI.
- Do not share accounts. Audit attribution depends on one identity per clinician.
- There is no email password reset. A future administrative reset flow must authenticate the operator, follow practice identity checks, invalidate sessions, and create an audit event.
- Disable departed or compromised accounts directly through an approved administrative procedure until a UI is implemented. Preserve the user record so historical audit and approval attribution remain intact.
- After five failed logins within 15 minutes, wait for the 30-minute lock to expire unless a documented security investigation justifies an administrative intervention.

## Common incidents

### Disk nearly full

Stop new uploads and drafting, verify the encrypted mount has not failed, and determine whether growth is in originals, reports, previews, logs, Docker layers, or backups. Do not delete clinical records ad hoc. Move or clean only data covered by the practice retention policy, then verify database and file integrity.

### LibreOffice preview failure

DOCX generation and PDF preview are separate outcomes. Confirm `soffice` exists, the output directory is writable, fonts are installed, and the DOCX opens correctly. Clinicians must not approve a visually uninspected report merely because the DOCX download exists.

### Internet or Bedrock outage

Existing local records and review remain available. Draft/extraction jobs retry safely and can remain queued/failed without inventing results. Do not bypass consent or switch models/regions informally. Record the outage and resume after the approved service and profile are verified.

### Suspected privacy or credential breach

1. Contain access: disconnect public exposure if needed and disable/rotate suspected credentials.
2. Preserve relevant logs, audit metadata, timestamps, and system state without copying patient narrative into the incident log.
3. Notify the practice privacy/security lead and follow the approved data-breach response plan.
4. Assess affected people, records, AWS requests, backups, and access timeframes, including applicable notification duties.
5. Restore service only after the cause is corrected, access is reviewed, and evidence is retained appropriately.

## Monitoring boundary

The POC has a health endpoint and Docker health check but no external alerting stack. Before live use, connect uptime, backup failure, disk-capacity, repeated login failure, and terminal job failure alerts to an approved channel that carries identifiers and status only—never clinical content.
