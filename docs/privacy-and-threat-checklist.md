# Pre-live privacy and threat checklist

This implementation is a proof of concept, not a certification of legal or clinical compliance. A registered psychologist and the practice privacy owner must complete this checklist before identifiable patient information is used.

## Privacy impact

- Confirm the lawful collection purpose, patient notice, consent wording, access/correction process, retention schedule, deletion process, and breach-response contacts.
- Document that Bedrock processing uses the Australian geographic inference profile and whether Sydney/Melbourne processing is acceptable.
- Confirm that each proprietary instrument licence permits uploading its scored exports and incorporating selected charts in a report.
- Record all subprocessors, administrators, backup locations, and people with physical access to the Pi.
- Verify the practice’s obligations under the Privacy Act 1988, Australian Privacy Principles, Victorian Health Records Act 2001, and professional record-keeping standards.

## Threat assessment

- Require TOTP MFA before routine live use; password-only access is a POC limitation.
- Encrypt the system and backup SSDs with LUKS; store recovery material separately.
- Permit inbound 443 only. Restrict SSH by firewall/VPN, require keys, disable root login, and install security updates promptly.
- Rotate the Flask secret, AWS credential, administrator passwords, and recovery keys. Grant AWS only `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` for the configured model/profile.
- Review Caddy, application, audit, and operating-system logs without adding patient content to them.
- Test account lockout, CSRF protection, cross-account case access, backup restore, Pi loss, storage exhaustion, worker restart, and Bedrock outage.
- Keep a UPS attached and rehearse a clean shutdown and recovery.

## Clinical release gate

- Validate at least five de-identified historical reports spanning adult and adolescent cohorts.
- Confirm every factual paragraph can be traced to verified evidence and that contradictions remain visible.
- Confirm the clinician must decide every criterion and write the final diagnostic conclusion.
- Confirm rating scales alone cannot pass the approval gate.
- Visually inspect every generated DOCX/PDF and verify the editable DOCX in Microsoft Word.

