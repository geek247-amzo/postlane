# Deployment acceptance record

Created by CloudMonkey. Copy this checklist into the customer's private operational records. Record evidence and date for each item; unchecked items are not implied to work.

- [ ] Git SHA and built image IDs recorded; repository private; no customer state in source.
- [ ] Backend tests and production frontend build pass; CI PostgreSQL and Docker jobs pass.
- [ ] Fresh Ubuntu Compose boot succeeds; app/database/worker health pass after restart.
- [ ] Host firewall externally probed; admin/database/API ports inaccessible publicly.
- [ ] Fresh secrets, protected .env, encrypted storage, supported host patches, restricted SSH.
- [ ] HTTPS and mail TLS trusted; renewal tested; DNS/MX/PTR/SPF/DKIM/DMARC checked.
- [ ] Owner MFA works; restricted user/mailbox grants and revoked tokens deny access.
- [ ] Three domains and ten intended mailboxes provisioned; quotas and abuse controls set.
- [ ] Actual inbound/outbound mail verified; open relay rejected; failure/uncertain sends handled.
- [ ] Each enabled provider passes OAuth refresh or IMAP/SMTP tests and revocation checks.
- [ ] Receiving aliases create/delete and actual delivery verified if enabled.
- [ ] AI disabled by default; per-mailbox opt-in and human review/edit/reapproval verified.
- [ ] n8n workflow imported/tested; signatures, freshness, retries and deduplication verified.
- [ ] All application pages and key flows tested in desktop/mobile browsers with real errors.
- [ ] Encrypted off-host backup, isolated restore, monitoring and incident owner confirmed.
- [ ] Customer accepts documented feature limits and has authorized cutover.

## Known release limits

Synchronization covers bounded recent mail, not complete migration or remote deletion reconciliation. Organization folders/labels are local. Attachment download/upload, rich HTML composition, alias send-as, automatic Stalwart account provisioning, calendars/contacts, full threaded conversation UI, distributed workers and autonomous AI classification are not implemented. The source contains working adapters, but live provider consent, server certificates, DNS, delivery and n8n behavior need installation-specific validation. This release is a pilot foundation, not a claim that every planned email-suite feature is complete.
