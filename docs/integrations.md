# Integration setup and acceptance

Created by CloudMonkey. Values marked configured in Settings have not necessarily passed live verification. Environment changes require `docker compose up -d app worker` to recreate containers; a restart alone does not apply new environment values.

| Integration        | Required configuration                                          | Acceptance test                                                                   |
| ------------------ | --------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Hosted Stalwart    | Wizard, domains/accounts, trusted TLS, MAIL_ALLOWED_HOSTS       | Receive externally, sync, send to approved recipient, reject open relay           |
| External IMAP/SMTP | Exact allowlisted hostnames, TLS ports and account credentials  | Sync recent mail, change read state, send, revoke credentials and observe failure |
| Gmail              | GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET                         | Consent, bounded sync, send, token refresh and revocation                         |
| Microsoft          | MICROSOFT_CLIENT_ID / MICROSOFT_CLIENT_SECRET                   | Organizational consent, sync/send, refresh and revoked consent                    |
| Receiving aliases  | STALWART_API_URL / STALWART_API_TOKEN                           | Create/list/remove alias, actual delivery, unauthorized domain denied             |
| External AI        | AI_BASE_URL / AI_API_KEY / AI_MODEL and mailbox opt-in          | Disabled mailbox denied; selected-message draft; approval required after edits    |
| n8n API            | Mailbox-scoped expiring bearer key                              | Invoice labeling works; unrelated mailbox and sending denied                      |
| Webhooks           | Exact WEBHOOK_ALLOWED_ORIGINS; optional WEBHOOK_PRIVATE_ORIGINS | Valid signature accepted, bad/stale rejected, retries deduplicated                |

## OAuth

Use `https://APP_HOST/api/oauth/callback` exactly for both registrations. Keep client secrets server-side. Complete consent in the initiating browser. Gmail requests `gmail.modify`; Microsoft requests delegated `offline_access User.Read Mail.ReadWrite Mail.Send`. Google verification/test-user restrictions and Microsoft tenant/admin consent may limit deployment; complete those requirements before customer onboarding. See [Google OAuth web server flow](https://developers.google.com/identity/protocols/oauth2/web-server) and [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

CloudMonkey Work uses the same Google client for Drive, with one additional redirect URI:

```text
https://APP_HOST/api/work/oauth/callback
```

For Gmail inside Work, connect the Gmail account as a mailbox first, sync it, enable external AI for that mailbox, then add a **Gmail & connected mail** Work connection that targets the mailbox. For ClickUp, create a Work connection with a personal API token and one list ID; reads are automatic in selected conversations, while task creation requires human approval.

## Stalwart

Use the pinned v0.16 API, with an HTTPS endpoint ending `/api`. The Compose MAIL_HOST network alias routes app/worker connections directly to Stalwart while retaining certificate hostname verification. Its HTTPS listener needs a trusted certificate. Public port 443 belongs to the application gateway; public JMAP discovery is not routed by this deployment.

The management credential needs `sysDomainQuery`, `sysDomainGet`, `sysAccountQuery`, `sysAccountGet`, and `sysAccountUpdate`. Restrict further where your server supports it. Account update permission is powerful: store the token only on the host. The adapter exposes receiving-alias changes, never an arbitrary management proxy. Domains must exist in Stalwart and be verified in Postlane. See [Stalwart Account API](https://stalw.art/docs/ref/object/account/).

## n8n and AI

Import [the example workflow](../examples/n8n-label-invoices.json), replace both host placeholders and assign a Header Auth credential to both HTTP nodes. Its key needs `messages:read` and `messages:write`, restricted to one intended mailbox. It processes the first page of matching recent mail, preserves labels, is inactive by default and never sends replies. For larger workloads add explicit pagination/checkpointing. n8n is not bundled.

Webhook payloads contain metadata, not mail bodies. Verify exact raw bytes using [verify_webhook.py](../examples/verify_webhook.py), a five-minute freshness window, and durable event-ID deduplication. Never acknowledge a side effect as processed before storing its durable result. Inspect dead deliveries in Automations and fix the receiver before replaying through an operator-reviewed process.

AI uses a configured compatible HTTPS chat-completions endpoint with no tools. It transmits subject and selected message text (up to 16,000 body characters), excluding attachments and internal notes. Choose the provider under your privacy agreement. Local AI deployment and automated classification are not implemented. API draft creation can support a separate trusted classifier, but any read key can export permitted mail and must be handled accordingly.
