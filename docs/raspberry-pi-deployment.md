# Raspberry Pi deployment runbook

This runbook deploys Clarity on a Raspberry Pi 5 using the repository's Docker Compose stack. The Pi hosts Caddy, Flask/Gunicorn, the React application, the background worker, SQLite, uploaded documents, and generated reports. Amazon Bedrock remains an AWS service; only the worker sends approved case material to it.

The procedure deliberately keeps application data, AWS credentials, and backups off the unencrypted Raspberry Pi OS volume. Commands assume Raspberry Pi OS 64-bit and a dedicated external SSD. Replace every value in angle brackets with the exact value for this installation.

> **Live-data gate:** the current application is a proof of concept. Use synthetic or fully de-identified cases until TOTP MFA, the privacy impact assessment, threat assessment, restoration rehearsal, and clinical validation gates are complete.

## 1. Required hardware and external services

- Raspberry Pi 5 with at least 8 GB RAM
- Official-quality power supply, active cooling, and a small UPS
- Raspberry Pi OS 64-bit installed on the system disk
- Dedicated external SSD for the application and clinical data
- A second encrypted disk or approved encrypted remote destination for backups
- Ethernet rather than Wi-Fi where practical
- Router access for a DHCP reservation and TCP 443 forwarding
- A public DNS name, such as `reports.example.com`
- An AWS account with the restricted Bedrock runtime identity described in [Connecting Clarity to Amazon Bedrock](aws-bedrock-connection.md)

The public deployment path also requires a public IPv4 address or working IPv6 ingress. If the internet service uses carrier-grade NAT, ordinary router port forwarding will not work; obtain a public address from the ISP or use an approved private-network design. Do not introduce an unassessed third-party tunnel for health information.

## 2. Prepare Raspberry Pi OS

Use Raspberry Pi Imager to install the current 64-bit Raspberry Pi OS. In Imager's customisation screen:

1. Set a unique hostname and non-default administrator username.
2. Configure the locale and time zone.
3. Enable SSH with **public-key authentication only**.
4. Do not expose SSH to the public internet.

After booting, connect from a trusted machine on the practice network:

```sh
ssh <pi-admin>@<pi-lan-address>
```

Update the host, confirm its architecture, and reboot:

```sh
sudo apt update
sudo apt full-upgrade -y
dpkg --print-architecture
sudo reboot
```

The architecture must be `arm64`. Give the Pi a DHCP reservation in the router so its LAN address does not change. Confirm time synchronisation after reboot:

```sh
timedatectl status
```

## 3. Encrypt and mount the application SSD

This section erases the selected SSD partition. Disconnect unrelated removable disks first. Run the following inspection command and record the exact SSD device, size, model, and partition:

```sh
lsblk -o NAME,PATH,SIZE,MODEL,FSTYPE,MOUNTPOINTS
```

> **Destructive boundary:** `luksFormat` and `mkfs.ext4` permanently erase the selected partition. Do not continue until the exact dedicated SSD partition has been identified. Never substitute the system disk, a broad path, or an unresolved shell variable.

Install the encryption utility. Partition a new SSD using the Raspberry Pi disk tool or `fdisk`, then encrypt only the verified data partition:

```sh
sudo apt install -y cryptsetup
sudo cryptsetup luksFormat /dev/<exact-ssd-partition>
sudo cryptsetup open /dev/<exact-ssd-partition> clarity-data
sudo mkfs.ext4 /dev/mapper/clarity-data
sudo install -d -m 700 /srv/clarity
sudo mount /dev/mapper/clarity-data /srv/clarity
sudo chown <pi-admin>:<pi-admin> /srv/clarity
sudo chmod 750 /srv/clarity
findmnt /srv/clarity
```

Use a strong, separately retained LUKS passphrase. Manual unlock is the safer POC default because storing the unlock key on the unencrypted system disk substantially weakens protection.

Record the partition UUID for the operating runbook:

```sh
sudo cryptsetup luksUUID /dev/<exact-ssd-partition>
```

After every cold boot, unlock and mount the disk **before starting Docker**:

```sh
sudo cryptsetup open /dev/<exact-ssd-partition> clarity-data
sudo mount /dev/mapper/clarity-data /srv/clarity
findmnt /srv/clarity
```

Do not add an unreviewed key file to the system disk. If automatic encrypted-volume startup is later required, design and test a mount-aware boot unit and an appropriate key-protection mechanism as a separate security change.

## 4. Install Docker from Docker's repository

Remove conflicting unofficial packages if they are installed, then add Docker's official Raspberry Pi OS repository:

```sh
sudo apt remove -y docker.io docker-compose docker-doc podman-docker containerd runc
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/raspbian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/raspbian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run --rm hello-world
sudo docker compose version
```

Membership in the `docker` group is effectively root access. This runbook intentionally uses `sudo docker` instead of adding clinician accounts to that group.

### Prevent startup before the encrypted disk is mounted

The Compose services use `restart: unless-stopped`. If Docker starts while `/srv/clarity` is not mounted, bind-mount directories could be created on the unencrypted system disk. For the manual-unlock POC, disable automatic Docker socket/service startup:

```sh
sudo systemctl disable docker.service docker.socket
```

This does not uninstall Docker. At each boot, unlock and verify `/srv/clarity`, then start Docker explicitly:

```sh
findmnt /srv/clarity
sudo systemctl start docker
```

Never start Docker when `findmnt /srv/clarity` fails. The UPS reduces unplanned shutdowns but does not replace this control.

## 5. Install the application on the encrypted SSD

Clone the repository into the mounted encrypted volume:

```sh
sudo install -d -m 750 -o <pi-admin> -g <pi-admin> /srv/clarity/app
git clone https://github.com/sushen25/clarity.git /srv/clarity/app
cd /srv/clarity/app
```

For a private repository, use a read-only GitHub deploy key instead of embedding a token in a command or URL. Do not copy the development `.env`, database, uploads, reports, or AWS credentials from another computer.

The application containers run as UID/GID `10001`. Create their writable directories with restricted ownership:

```sh
sudo install -d -m 700 -o 10001 -g 10001 /srv/clarity/app/data
sudo install -d -m 700 -o 10001 -g 10001 /srv/clarity/app/storage
sudo install -d -m 700 -o 10001 -g 10001 /srv/clarity/secrets/aws
```

## 6. Configure the unattended AWS runtime identity

Complete the IAM and model-access steps in [Connecting Clarity to Amazon Bedrock](aws-bedrock-connection.md). The container runtime must use a dedicated, least-privilege, unattended identity. Do not mount a profile that depends on `aws login`, SSO browser interaction, or `credential_process`; the application image does not include the AWS CLI or an interactive login cache.

Place only the restricted runtime profile in `/srv/clarity/secrets/aws`. Create these files using `sudoedit` or securely copy them from a trusted administrator machine. Their shapes are:

`/srv/clarity/secrets/aws/config`:

```ini
[profile clarity-bedrock]
region = ap-southeast-2
output = json
```

`/srv/clarity/secrets/aws/credentials`:

```ini
[clarity-bedrock]
aws_access_key_id = <restricted-runtime-access-key-id>
aws_secret_access_key = <restricted-runtime-secret-access-key>
```

Apply the permissions required by the worker container:

```sh
sudo chown 10001:10001 /srv/clarity/secrets/aws/config /srv/clarity/secrets/aws/credentials
sudo chmod 600 /srv/clarity/secrets/aws/config /srv/clarity/secrets/aws/credentials
```

Never print the credentials, commit them, put them in `.env`, or include them in a backup that lacks equivalent encryption and access controls.

## 7. Configure the production environment

Create the application environment file:

```sh
cd /srv/clarity/app
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
```

Copy the generated random value directly into `SECRET_KEY`; do not reuse it elsewhere. Edit `.env` so it contains the following production values plus the existing timeout/token settings:

```dotenv
SECRET_KEY=<at-least-32-random-bytes>
LOG_LEVEL=INFO
COOKIE_SECURE=true
PUBLIC_DOMAIN=reports.example.com
PUBLIC_ORIGIN=https://reports.example.com

BEDROCK_ENABLED=true
AWS_PROFILE=clarity-bedrock
AWS_CONFIG_DIR=/srv/clarity/secrets/aws
AWS_REGION=ap-southeast-2
BEDROCK_MODEL_ID=au.anthropic.claude-sonnet-4-6
BEDROCK_CONNECT_TIMEOUT_SECONDS=10
BEDROCK_READ_TIMEOUT_SECONDS=600
BEDROCK_SDK_MAX_ATTEMPTS=2
BEDROCK_EXTRACTION_MAX_TOKENS=8000
BEDROCK_DRAFT_MAX_TOKENS=7000
PROMPT_VERSION=2026-08-poc-v4
```

Replace `reports.example.com` in both places with the exact production hostname. Keep `DATABASE_PATH`, `STORAGE_ROOT`, `REPORT_TEMPLATE`, `LIBREOFFICE_BIN`, and `MAX_UPLOAD_MB` from `.env.example`; Compose supplies the corresponding container paths where required.

## 8. Configure DNS, router, and HTTPS

1. Create a public DNS `A` record for `PUBLIC_DOMAIN` pointing to the practice's public IPv4 address.
2. Create an `AAAA` record only when working public IPv6 ingress is deliberately configured. Remove an incorrect `AAAA` record because clients may prefer it and fail.
3. Forward **TCP 443** from the router to TCP 443 on the Pi's reserved LAN address.
4. Optionally forward **UDP 443** to enable HTTP/3.
5. Do not forward ports 8000, 22, database ports, or file-sharing ports.

The supplied Caddy configuration uses the TLS-ALPN challenge on TCP 443, so port 80 is not required for certificate issuance in this deployment. Because port 80 is not exposed, plain HTTP requests will not redirect; users must use the HTTPS address.

Docker-published ports have special firewall behaviour. Enforce the public exposure boundary primarily at the router and, if host filtering is added, use Docker's documented `DOCKER-USER` chain rather than assuming a simple UFW rule protects a published container port.

## 9. Validate configuration, build, and create the administrator

Always supply both Compose files so the worker receives the protected AWS profile:

```sh
cd /srv/clarity/app
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml config
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml build
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml run --rm web \
  python manage.py create-admin --username admin --full-name "Clinical Administrator"
```

Review the rendered Compose configuration carefully. It must show `/srv/clarity/secrets/aws` mounted read-only at `/home/app/.aws` in the worker. It must not print AWS secret values because those values are not part of `.env`.

Use a unique strong administrator password. There is no public registration or email password reset.

## 10. Start and verify the deployment

Start the stack:

```sh
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml up -d
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml ps
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml logs --tail=100 web worker caddy
```

Confirm the worker resolves the expected AWS identity without displaying credentials:

```sh
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml exec worker \
  python -c "import boto3; print(boto3.client('sts').get_caller_identity()['Arn'])"
```

After DNS propagation and router forwarding are active, test from a device outside the practice LAN as well as inside it:

```sh
curl --fail --show-error https://reports.example.com/api/health
```

Then perform this browser acceptance test:

1. Open the exact HTTPS address and sign in.
2. Create a synthetic adult or adolescent case.
3. Acknowledge Australian cloud processing.
4. Upload a synthetic TXT source and generate evidence.
5. Verify evidence and set the required clinician decisions.
6. Generate a draft and watch the worker log.
7. Confirm `provider=bedrock`, the Australian model ID, and a successful response record.
8. Edit the draft, render the preview, and download/open the DOCX.
9. Restart the worker and confirm no duplicate report version appears.

Watch only privacy-safe application lifecycle logs:

```sh
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml logs -f worker
```

Do not enable Boto3/Botocore wire debug logs or Bedrock model invocation logging. Both can capture submitted clinical content.

## 11. Configure encrypted backups

Use a physically or logically separate encrypted destination; a directory on the application SSD is not a disaster-recovery backup. After mounting the approved backup volume at `/mnt/clarity-backup`, run:

```sh
cd /srv/clarity/app
findmnt /mnt/clarity-backup
sudo python3 scripts/backup.py \
  --database data/app.db \
  --storage storage \
  --destination /mnt/clarity-backup
```

The utility creates a consistent SQLite backup and copies the storage tree. With daily runs it retains seven daily and four weekly snapshots. It does not encrypt the destination itself.

Do not automate this command until it refuses to run when the backup mount is absent and the restoration procedure has been rehearsed. Follow [Operations](operations.md) to validate the backup in an isolated test location. Record the result without clinical narrative.

## 12. Normal boot, shutdown, and maintenance

### After a cold boot

```sh
sudo cryptsetup open /dev/<exact-ssd-partition> clarity-data
sudo mount /dev/mapper/clarity-data /srv/clarity
findmnt /srv/clarity
sudo systemctl start docker
cd /srv/clarity/app
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml up -d
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml ps
```

### Before a planned shutdown

```sh
cd /srv/clarity/app
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml stop
sudo systemctl stop docker docker.socket
sudo umount /srv/clarity
sudo cryptsetup close clarity-data
sudo poweroff
```

Wait for the Pi to power down before disconnecting power or storage.

### Deploy an application update

1. Confirm no report job is running and complete a verified encrypted backup.
2. Read the release notes and inspect configuration/template/prompt changes.
3. Update and rebuild in a maintenance window:

```sh
cd /srv/clarity/app
git pull --ff-only
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml build
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml up -d
sudo docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml ps
```

4. Repeat the health, synthetic Bedrock, preview, and DOCX checks.

Prompt, model, schema, and template changes require representative clinical and rendering validation, not only an infrastructure smoke test.

## 13. Final pre-live checklist

Before any identifiable patient information is used, all of these must be complete:

- TOTP MFA is implemented and tested.
- The [privacy and threat checklist](privacy-and-threat-checklist.md) is signed off.
- Australian cloud-processing consent wording is approved and operational.
- A registered psychologist has validated at least five de-identified adult/adolescent historical cases.
- Backup restoration has succeeded on an isolated system.
- SSH, router exposure, account ownership, AWS permissions, and credential rotation are reviewed.
- Disk-full, network-loss, Pi-restart, worker-crash, and failed-render tests pass.
- An incident-response contact and record-retention/deletion procedure are documented.

Until then, keep the deployment restricted to synthetic or fully de-identified POC data.

## Official platform references

- [Docker Engine on Raspberry Pi OS](https://docs.docker.com/engine/install/raspberry-pi-os/)
- [Docker Engine on Debian and firewall considerations](https://docs.docker.com/engine/install/debian/)
- [Raspberry Pi remote access and SSH key authentication](https://www.raspberrypi.com/documentation/computers/remote-access.html)
- [Caddy automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https)
- [Amazon Bedrock Claude Sonnet 4.6 model details](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html)
