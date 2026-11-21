# Ubuntu Docker deployment

Created by CloudMonkey. See the [agent setup runbook](agent-setup.md), [security baseline](../SECURITY.md) and [acceptance checklist](release-checklist.md).

The configuration generator writes core secrets to the protected secrets/ directory for read-only Compose mounts; optional provider credentials use container environment variables. For an existing .env without secret files, run `python3 scripts/sync_secrets.py`. It refuses to replace an existing value. Both storage forms remain accessible to host administrators. For the optional Stalwart management connection, the Compose network aliases MAIL_HOST to Stalwart internally. Configure a trusted certificate on its HTTPS listener and set STALWART_API_URL to `https://mail.example.com/api`, using your actual MAIL_HOST. Public port 443 remains assigned to the application gateway.

This is an initial implementation for 3 domains and 10 mailboxes. The application build and API tests run locally. Docker startup, PostgreSQL integration, Stalwart administration, OAuth consent, and real email delivery still require validation on the target server. Do not import production mail until the installation checks below pass.

## 1. Configure a fresh installation

Use one Ubuntu host or VM per customer. Install Docker Engine and the Compose plugin using [Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/). Copy this project to a private directory on the server.

```sh
python3 scripts/configure.py --host inbox.yourdomain.com --mail-host mail.yourdomain.com
chmod 600 .env
docker compose config --quiet
docker compose up -d --build
```

The generator creates unique secrets and refuses to overwrite an existing `.env`. Set an A record for the application hostname to this host. Caddy obtains the application HTTPS certificate using ports 80/443. Keep `.env` outside source control and restrict host administration. Docker environment variables remain visible to host/Docker administrators.

Visit the application HTTPS URL. Read `BOOTSTRAP_TOKEN` from `.env` locally and enter it on the first-run page. Choose a password of at least 14 characters. Enable authenticator-based MFA in Settings before using production administrative features. Store the authenticator secret in your password manager as a recovery method. Workspace users and mail-server accounts are distinct.

The application and worker use PostgreSQL. The database and API ports are not published; only the HTTPS proxy is public. Use exactly one application process and one worker in this release. Horizontal scaling requires distributed authentication throttling, coordinated synchronization, and worker lease recovery that are not yet implemented.

## 2. Start the mail server

```sh
docker compose --profile mail up -d stalwart
docker compose logs stalwart
```

The image is pinned to Stalwart `v0.16.22`, using the current `/etc/stalwart` and `/var/lib/stalwart` volume layout. Follow the [Stalwart Docker setup wizard](https://stalw.art/docs/install/platform/docker/) for initial server configuration. The admin ports in this Compose file bind only to host loopback; access the wizard through an SSH tunnel:

```sh
ssh -L 8080:127.0.0.1:8080 admin@YOUR_SERVER
```

Open `http://127.0.0.1:8080` locally, then complete the wizard. For ongoing HTTPS management, configure a trusted certificate and tunnel the mail-server HTTPS listener as needed. Stalwart's public discovery URL is a deployment setting: the default `https://MAIL_HOST` must be changed or routed by your proxy before relying on public JMAP discovery. Postlane's IMAP/SMTP connection does not depend on that discovery URL.

Configure Stalwart's mail TLS certificate using DNS-01 ACME or a certificate installed by your operator. Caddy owns public port 443 for the workspace, so Stalwart TLS-ALPN validation cannot independently use that port with this layout. Caddy's application certificate does not automatically provision SMTP/IMAP TLS.

In Stalwart, create your domains, mailbox accounts, quotas, spam policy, and domain signing keys. Configure authenticated submission, reject unauthorized relay, and keep unused protocols disabled. The application currently connects to existing mail-server accounts; it does not automatically run Stalwart's setup wizard or create server accounts.

For each domain, configure and verify:

- MX pointing to the mail hostname; A/AAAA matching actual reachable addresses.
- PTR/reverse DNS configured by your IP provider and matching forward DNS.
- SPF listing only authorized senders, DKIM public keys from the mail server, and DMARC reporting/policy suited to the deployment.
- Trusted TLS on submission and IMAP, inbound/outbound port 25, sending quotas and queue monitoring.

Only publish AAAA if IPv6 delivery and reverse DNS actually work. Test receiving and sending with external mail systems, open-relay rejection, and certificate renewal. DNS authentication alone does not guarantee inbox placement. See [Google's sender requirements](https://support.google.com/mail/answer/81126).

## 3. Connect Postlane mailboxes

Add each domain in Postlane and publish its `_postlane` TXT ownership record. Postlane automatically creates the domain in Mailcow and the worker periodically reconciles all Postlane domains back to Mailcow, so a manually removed Mailcow domain is recreated. Use **Check DNS** to verify. Add a hosted mailbox, then configure its IMAP/SMTP connection in mailbox settings. Use the mail server's trusted certificate hostname; include it in `MAIL_ALLOWED_HOSTS`. Restart the app and worker after configuration changes.

For Google and Microsoft, register OAuth applications with this exact callback:

```text
https://YOUR_APP_HOST/api/oauth/callback
```

Configure the appropriate client ID and secret in `.env`, recreate the app and worker, add the account, and choose **Authorize**. Google uses delegated `gmail.modify`; Microsoft uses delegated `offline_access User.Read Mail.ReadWrite Mail.Send`. Provider verification, test-user limitations, organizational consent policies, and SMTP policy remain provider-controlled. Authorization must finish in the same browser that started it.

Connection secrets are encrypted with `ENCRYPTION_KEY`; losing that key makes them unrecoverable. Do not change it without re-encrypting stored credentials. Mail bodies and application metadata are not encrypted at the field level: use encrypted host disks, encrypted off-host backups, and tightly restricted database access.

The current sync imports up to the most recent 100 messages per configured IMAP folder, 100 Google messages, or 100 messages in each of Microsoft Inbox/Sent. It polls every two minutes. This is bounded recent-mail synchronization, not a complete historical migration or deletion reconciliation engine. Workspace folders, labels, snoozes, and stars are local. Read state synchronizes back to the provider. Remote moves/deletes and historical backfill require further implementation.

## 4. Hosted receiving aliases

Set `STALWART_API_URL` to the full trusted HTTPS management endpoint ending in `/api` and `STALWART_API_TOKEN` to a restricted Stalwart credential. Required management permissions: `sysDomainQuery`, `sysDomainGet`, `sysAccountQuery`, `sysAccountGet`, and `sysAccountUpdate`. Keep this credential on the server; never put it in a browser or n8n workflow. Supply only the minimum permissions your Stalwart deployment supports for this operation.

Use **Mailbox settings → Receiving aliases** to list, add, and remove aliases on the actual Stalwart account. The alias domain must already exist in Stalwart and be verified in Postlane. Changes use JMAP state preconditions to avoid silently overwriting another administrator's update. This adapter follows the [Stalwart Account API](https://stalw.art/docs/ref/object/account/); it has not been tested against a live server in this environment.

Receiving aliases do not grant send-as permission. Sending from alias identities is not implemented in this release. n8n can manage receiving aliases through a separately issued, mailbox-scoped `aliases:manage` token created by an administrator through the API.

## 5. AI and n8n

External AI is off for every mailbox. Configure a trusted HTTPS `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` for a compatible chat-completions endpoint. Enable AI only for selected mailboxes. A draft request sends the selected message's text and subject, bounded to 16,000 body characters. It sends no attachments, internal notes, or other mailbox context. The model has no tools. Review recipient addresses and content before approval. Any edit invalidates approval.

For n8n, import `examples/n8n-label-invoices.json`, replace both `YOUR_POSTLANE_HOST` placeholders, and choose an n8n Header Auth credential containing `Authorization: Bearer YOUR_SCOPED_KEY` in each HTTP node. Create a key with `messages:read` and `messages:write` for just the intended mailbox. The example searches the first page of recent invoice conversations and adds a Finance label while preserving other labels. It is inactive by default, uses no external AI, and never sends mail. Validate it in your installed n8n version before activating it.

Signed webhooks are also available. Add an exact origin to `WEBHOOK_ALLOWED_ORIGINS`. A private n8n endpoint additionally needs its origin in `WEBHOOK_PRIVATE_ORIGINS`; do not allow arbitrary internal destinations. Verification uses the exact body bytes and `HMAC-SHA256(secret, timestamp + '.' + body)`. `examples/verify_webhook.py` demonstrates signature and freshness verification. Persist event IDs to deduplicate at-least-once delivery before performing side effects. Message bodies are omitted from events; retrieving them needs a scoped API key. Trust API-key holders with any mail their read scope allows, including data they choose to transmit outside Postlane.

## 6. Backups and operations

Back up PostgreSQL, Stalwart's configuration/data, application configuration, encryption keys, and TLS material. Use a dedicated encrypted backup system such as an operator-managed restic repository; no backup destination or schedule is configured by this project. Configure monitoring for disk use, mail queue age, bounce rates, certificate expiry, container health, and backup age.

For a consistent initial backup, stop the app and worker to quiesce application writes, dump PostgreSQL using `pg_dump`, and take a Stalwart-supported backup or stop Stalwart before snapshotting its volumes. A raw copy of a live database volume is not a reliable database backup. Capture keys/configuration in the same protected recovery set, encrypt off-host, then restart services. Test restoring to an isolated installation before accepting production mail.

Images are version-pinned, but no automatic upgrade or database migration framework is installed yet. The initial schema is created at startup. Before deploying future schema changes, add a reviewed migration, test it against a restored database, and document whether rollback requires a backup restore. Do not downgrade database or Stalwart versions against newer data directories.

For resale, generate a new `.env` and new volumes on each customer's VM. Never copy your live database, sessions, MFA secrets, provider tokens, or API keys. Review third-party licenses before distributing a bundled product. n8n is an external integration; it is not bundled in this Compose stack.

## Remaining production validation

- Build and boot this Compose stack on Ubuntu; test PostgreSQL transactions and restart behavior.
- Verify external SMTP/IMAP delivery, provider OAuth refresh, aliases, quotas, and relay rejection.
- Verify UI behavior and accessibility in a real browser; no browser was available during this build.
- Exercise n8n import, event retries, receiver-side signature verification, and workflow deduplication.
- Complete backup restoration, monitoring, credential rotation, and security review before production cutover.
