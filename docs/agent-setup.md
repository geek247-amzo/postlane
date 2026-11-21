# Developer and agent installation runbook

Created by CloudMonkey. This runbook targets a fresh customer installation: 3 domains, 10 mailboxes, one API process and one worker. Read [SECURITY.md](../SECURITY.md) before executing. Do not import sample data or reuse another customer's volumes.

## 1. Collect required inputs

Record the Ubuntu host, SSH operator, application/mail hostnames, three domains, static IP/PTR, DNS access, desired users/grants, ten mailboxes/quotas, backup destination, approved test recipients, and monitoring owner. Obtain secrets securely on the host, never through Git commits. Existing account connections additionally need OAuth registrations or TLS IMAP/SMTP credentials. AI and n8n are optional and stay disabled until configured.

## 2. Prepare and boot

Install supported Docker Engine and Compose using the official Ubuntu guide linked in deployment.md. Check RAM, disk growth allowance and available space rather than assuming ten mailboxes have a fixed storage need. Configure host updates, firewall, disk encryption, time synchronization, restricted SSH, and encrypted backup storage.

Clone the private repository into a directory accessible only to operators. Run `python3 scripts/configure.py --host inbox.example.com --mail-host mail.example.com`, restrict .env to mode 0600, and record the unique COMPOSE_PROJECT_NAME. Configure APP_HOST DNS before Caddy certificate issuance. Run `docker compose config --quiet`, then `docker compose up -d --build`. Inspect `docker compose ps`; `/api/ready` must return HTTP 200. Do not log expanded configuration.

## 3. Establish workspace security

Open the HTTPS application, use the bootstrap token locally, and create the owner. Enroll MFA from Settings and sign in again. Check Installation checks: PostgreSQL, recent worker heartbeat, no sample mode. Create team users and explicit read/write/send grants. Test a restricted user's denial of another mailbox. Store MFA recovery material in the operator's protected password manager.

## 4. Configure hosted email

Start `docker compose --profile mail up -d stalwart`. Follow the pinned Stalwart version's setup wizard through the SSH tunnel documented in deployment.md. Provision the domains, ten mail-server accounts, quotas, relay restrictions, DKIM, spam policy and trusted SMTP/IMAP certificates. These accounts are separate from workspace users.

Configure MX, A/PTR, SPF, DKIM and DMARC. Validate IPv6 before publishing AAAA. Mail TLS requires DNS-01 or operator-installed certificates; Caddy's app certificate is separate. Use the same MAIL_HOST as the certificate name and the Compose network alias, so app/worker can reach the mail server internally while validating TLS. Verify the listener inside Stalwart matches ports in compose.yaml.

Add domains in Postlane, publish ownership TXT records, and verify them. Connect hosted accounts with IMAP/SMTP credentials and the allowlisted MAIL_HOST. Set the trusted internal management endpoint `https://mail.example.com/api` and a restricted Stalwart token if receiving aliases are needed. Recreate app and worker after .env changes. Confirm aliases in Stalwart itself and by receiving a test message.

## 5. Connect existing providers and automation

Follow [integrations](integrations.md). Register the exact HTTPS callback; connect a controlled Gmail and Microsoft account and verify token refresh as well as initial login. Test IMAP authentication and SMTP TLS. Inspect mailbox connection errors without logging credentials.

Import the inactive n8n example, configure a scoped credential and replace host placeholders. Test label updates first. Configure signed webhooks only to explicitly allowlisted destinations; test signature rejection, retries and deduplication. If enabling AI, get the mailbox owner's agreement to the provider, enable only that mailbox, generate a draft, edit it, and verify approval is invalidated. Confirm automation cannot approve or send.

## 6. Validate every user flow

Use a real desktop and mobile browser: setup/login/logout/MFA, inbox and mailbox switching, search and pagination, local folders/labels, bulk actions, stars/snooze, message view/notes, compose/drafts/replies, approval/edit/reapproval, scheduled send/cancel, domains/DNS, connections/aliases, team/grants, keys/webhooks/history, Settings/password/audit. Check loading, empty and failure states, keyboard focus and narrow screens. Do not substitute a screenshot for interaction checks.

Test actual inbound and outbound delivery against approved external recipients. Check SPF/DKIM/DMARC results and confirm unauthenticated relay rejection. Restart app and worker with queued work; uncertain submissions must require investigation instead of automatic resending. Complete backup/restore rehearsal on isolated infrastructure.

## 7. Handover

Complete [release-checklist.md](release-checklist.md) with sanitized evidence, deployed Git SHA/image IDs, DNS records, certificate renewal plan, backup restore result, provider consent status and named operational owners. Record feature limitations (bounded sync, local organization, no attachments/send-as) in the customer handover. Switch MX/import business mail only within the owner's authorized cutover plan. Each resale installation starts with fresh secrets, empty storage, and its own completed checklist.
