# Deploying to the Pi

How to ship a change from a development machine to the running Clarity deployment. This is the recurring release loop for a Pi that is **already installed**.

For first-time installation — OS, encrypted storage, Docker, the AWS runtime identity, DNS, and TLS — use the [Raspberry Pi deployment runbook](raspberry-pi-deployment.md) instead. For the meaning of each environment variable, see [Deployment](deployment.md); for incidents and routine checks, see [Operations](operations.md).

## The deployment as it stands

| Item | Value |
| --- | --- |
| SSH alias | `ssh pi` (user `sushen`, host `sushens-raspberry-pi`) |
| LAN address | `192.168.0.69` |
| Hardware | Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM |
| OS | Debian 13 (trixie), `aarch64` |
| Application directory | `/home/sushen/clarity/clarity` |
| Git remote | `git@github.com:sushen25/clarity.git`, branch `main` |
| Public URL | `https://clarity.sushensatturu.com` |
| Containers | `clarity-web-1`, `clarity-worker-1`, `clarity-caddy-1` |
| Published ports | 443/tcp and 443/udp only — port 8000 is never published on the host |
| AI provider | Bedrock enabled, `au.anthropic.claude-sonnet-4-6`, `ap-southeast-2` |
| AWS credentials | `/srv/clarity/secrets/aws`, mounted read-only into the worker |
| Data and storage | `./data` and `./storage` under the application directory, owned by UID 10001 |

Two host facts shape every command below:

- **Docker needs `sudo`.** The `sushen` account is not in the `docker` group. Passwordless sudo is configured, and the Makefile already prefixes Compose with `$(SUDO)`, so `make deploy*` targets work as written. A bare `docker compose ps` will fail with a socket permission error — use `make deploy-ps` or add `sudo`.
- **Docker starts at boot** (`systemctl is-enabled docker` → `enabled`) and all three services use `restart: unless-stopped`, so the stack returns by itself after a reboot or power loss.

## Before you deploy

The Pi pulls from GitHub; it never receives files from your laptop directly. `make deploy-update` runs `git pull --ff-only`, so anything not pushed to `origin/main` will not ship.

```bash
git status --short && git push origin main
```

Then confirm what the Pi is about to pick up:

```bash
ssh pi 'cd ~/clarity/clarity && git fetch --quiet && git log --oneline HEAD..origin/main'
```

Read that list before continuing. Three kinds of change need more than an infrastructure smoke test afterwards:

- **Prompt or model changes** (`app/drafting.py`, `app/ai.py`, `PROMPT_VERSION`) — regenerate a draft on a synthetic persona and read the output.
- **Schema changes** (`app/schema.sql`, the migration block in `app/db.py`) — these apply automatically at web-container start and are additive only. Back up first.
- **Template or rendering changes** (`app/reporting.py`, `templates/`) — download a DOCX and open it.

Take a backup before any deploy that touches the database or the report template. See [Backups](#backups-are-not-configured-yet) — this needs setting up before live data.

## Deploy

```bash
ssh pi
cd ~/clarity/clarity
make deploy-update
```

`deploy-update` pulls, validates the Compose configuration, rebuilds both images, recreates changed containers, and prints the resulting service table. The build compiles the React frontend inside a `node:22-alpine` stage and installs LibreOffice Writer, so expect several minutes on ARM; the running stack stays up until the new images are ready.

To rebuild without pulling — after editing `.env`, for instance — use `make deploy`. To restart the current images with no rebuild at all, use `make deploy-recreate`.

### When a release changes `.env`

`.env` lives only on the Pi and is not in Git, so new or renamed variables never arrive with a pull. Compare against the shipped example after pulling:

```bash
ssh pi 'cd ~/clarity/clarity && diff <(sed -E "s/=.*//" .env | sort) <(sed -E "s/=.*//" .env.example | sort)'
```

The one difference to watch for is `PROMPT_VERSION`. It is pinned in `.env` and may lag the default in `app/config.py`. The `.env` value always wins and is recorded against every draft, so bumping the code default alone changes nothing. When a release advances the prompt, edit `.env` deliberately and run `make deploy` so the version stamped on new drafts is honest.

`AWS_CONFIG_DIR` must also be present — `deploy/compose.aws-profile.yml` fails fast without it — and it points at the protected host directory holding the runtime AWS profile, `/srv/clarity/secrets/aws` on this Pi.

Values in `.env` take effect on container start, so a change there needs `make deploy` or `make deploy-recreate`, not just a reload.

## Verify

```bash
make deploy-ps
make deploy-health
```

`deploy-health` probes the container directly and then the public URL. It reads that URL from `PUBLIC_ORIGIN` in `.env`, so on this Pi it targets `https://clarity.sushensatturu.com` with nothing to pass. Override it with `APP_URL=https://…` to check a different host; the target refuses to run if the value is empty or has no scheme.

Expect `clarity-web-1` to report `(healthy)` — the healthcheck polls `/api/health` every 30s and takes about a minute to settle after a recreate — with `clarity-worker-1` and `clarity-caddy-1` up. Both health probes should return `{"status":"ok"}`.

Then watch the worker while you exercise the application:

```bash
make deploy-logs SERVICE=worker
```

Sign in at `https://clarity.sushensatturu.com`, open a synthetic case, and generate a draft. With `LOG_LEVEL=INFO` a healthy Bedrock run emits:

```text
clinical_ai.provider_selected provider=bedrock region=ap-southeast-2 model_id=au.anthropic.claude-sonnet-4-6
bedrock.request_started operation=draft ...
bedrock.http_attempt operation=draft attempt=1 max_attempts=2
bedrock.response_received operation=draft ... stop_reason=end_turn input_tokens=... output_tokens=...
```

`provider=local-heuristic` means `BEDROCK_ENABLED` did not reach the container — check `.env` and recreate. `bedrock.request_failed` carries the exception type, AWS error code, and request ID; transient errors retry automatically up to three job attempts, while validation failures fail immediately by design.

Full acceptance criteria — upload, extraction, edit, preview, download, cross-user isolation — are in [Deployment](deployment.md#first-deployment-verification).

## Roll back

Images are rebuilt in place and not tagged per release, so rollback means checking out the previous commit and rebuilding:

```bash
ssh pi
cd ~/clarity/clarity
git log --oneline -5
git checkout <previous-good-sha>
make deploy
```

This leaves the Pi with a detached HEAD; the next `make deploy-update` will fail its `--ff-only` pull until you `git checkout main`. Do that once the fix is on `main`.

A rollback does **not** revert the database. The migration block in `app/db.py` only ever adds columns, so older code tolerates a newer database, but a schema change combined with a data problem needs a restore rather than a checkout. Approved report snapshots are immutable and are never rewritten by a redeploy — `_generate_files()` refuses to overwrite an approved artefact.

## Accounts

```bash
make deploy-admin USERNAME=admin FULL_NAME="Clinical Administrator"
make deploy-user  USERNAME=jane.smith FULL_NAME="Dr Jane Smith" \
  REGISTRATION_NUMBER=PSY0001234567
```

`deploy-admin` runs a one-off container against the same database and prompts for the new password twice. `deploy-user` goes through the HTTPS API as an existing admin at the `.env` origin; it prompts first for the administrator's password and then twice for the new user's, which must be at least 14 characters with upper case, lower case, and a digit.

Both are interactive and cannot be scripted or piped. Choose the password in a password manager first, then paste it at the prompt, and deliver it to the clinician through a secure channel.

## Open items on this Pi

Two gaps are worth closing before this deployment handles anything beyond synthetic data.

### Storage is not encrypted

`data/` and `storage/` sit on the Pi's internal 119 GB card (`/dev/mmcblk0p2`, 13% used). There is no external SSD and no LUKS volume. The architecture and privacy documents both require clinical records to live on an encrypted volume, and directory permissions are not disk encryption. The current layout is suitable only for synthetic and de-identified material. Section 3 of the [Raspberry Pi deployment runbook](raspberry-pi-deployment.md) covers moving to an encrypted SSD at `/srv/clarity`.

### Backups are not configured yet

There is no backup destination mounted, no `~/backups` directory, and no cron entry or systemd timer running `scripts/backup.py`. Nothing is being captured. `make backup` deliberately refuses to run unless the destination is a real mount point:

```bash
make backup BACKUP_DEST=/mnt/clarity-backup
```

`scripts/backup.py` takes a consistent SQLite snapshot via the online backup API, copies `storage/`, and prunes to seven daily plus four Monday-weekly copies. Schedule it daily to an encrypted target and rehearse a restore before live use — see [Operations](operations.md#backups).

## Quick reference

All commands run from `~/clarity/clarity` on the Pi.

```bash
make deploy-ps                                              # service state
make deploy-logs SERVICE=worker                             # follow one service
make deploy-logs                                            # follow everything
make deploy-health                                          # container + public health
make deploy-update                                          # pull, rebuild, restart
make deploy                                                 # rebuild without pulling
make deploy-recreate                                        # restart current images
make deploy-down                                            # stop the stack
```

Do not `curl http://localhost:8000` on the Pi host — that port is intentionally unpublished. Reach the application through Caddy on 443, or use `make deploy-health`, which probes inside the container.

Certificate or startup problems appear in the proxy log:

```bash
make deploy-logs SERVICE=caddy
```
