# Clarity documentation

This directory is the source of truth for how the ADHD assessment report POC is designed, operated, tested, and extended. It documents the implementation as it exists today; future changes should update the relevant document in the same change.

Do not place patient information, real transcripts, credentials, or identifiable screenshots in this directory. Examples must be synthetic or fully de-identified.

## Documentation map

| Document | Purpose |
| --- | --- |
| [Architecture](architecture.md) | System boundaries, component responsibilities, data flow, and technical decisions |
| [Clinical workflow](clinical-workflow.md) | Clinician journey, evidence safeguards, diagnostic controls, and approval gates |
| [API](api.md) | Authentication, request conventions, endpoints, and example payloads |
| [Data model](data-model.md) | SQLite entities, lifecycle states, filesystem layout, and versioning |
| [Deployment](deployment.md) | Local setup, Bedrock configuration, Raspberry Pi deployment, TLS, and verification |
| [Raspberry Pi deployment runbook](raspberry-pi-deployment.md) | Full hardware-to-production walkthrough for encrypted storage, Docker, AWS, HTTPS, backups, boot, and verification |
| [Deploying to the Pi](pi-release-runbook.md) | Recurring release loop for the installed Pi: push, pull, rebuild, verify, and roll back |
| [AWS Bedrock connection](aws-bedrock-connection.md) | End-to-end model access, IAM, credentials, local/Pi configuration, testing, monitoring, and troubleshooting |
| [Operations](operations.md) | Health checks, jobs, backups, restoration, upgrades, and incident response |
| [Development and testing](development.md) | Repository layout, coding conventions, test commands, and extension points |
| [Privacy and threat checklist](privacy-and-threat-checklist.md) | Required privacy, security, and clinical checks before live use |
| [DOCX template contract](template-artifact.md) | De-identification, template construction, and visual fidelity requirements |

## Product status

This is a proof of concept for clinician-supervised drafting. It is not a diagnostic device, autonomous clinical decision-maker, patient portal, practice-management system, or production-ready health-record platform. Password-only authentication is provided for evaluation; TOTP MFA and the pre-live checklist remain mandatory before routine use with live patient information.

## Documentation conventions

- `Case`, `EvidenceItem`, and similar capitalised names refer to domain records described in [the data model](data-model.md).
- API paths are relative to `/api` unless otherwise noted.
- Times are stored in UTC as ISO 8601 strings and displayed in the clinician's local time where the UI supports it.
- “Verified evidence” means a clinician has reviewed and accepted an extracted evidence item. It does not mean the application has independently established clinical truth.
- “Approval” means a clinician-approved report snapshot. The software itself never approves a diagnosis.
