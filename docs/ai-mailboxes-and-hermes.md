# Human, shared and AI mailboxes (0.3)

Created by CloudMonkey.

## Inbox and access

Use Human / Shared / AI agents / All in the inbox navigation. Human includes individual and shared human-managed mailboxes. The API applies the same category filter; categories never grant access. Existing mailboxes become `human` on upgrade and keep their current users, connections and grants.

In Mailboxes, create or manage a mailbox and select its management type. A shared mailbox is one real mailbox with multiple explicit user grants, not a copied inbox or alias. In Team, add a person and choose their initial mailbox access, or grant/edit/revoke access for existing users. Read, organize/draft and send are independent server-enforced permissions. Initial user creation and selected grants commit together. Administrators do not automatically gain mail-content access.

## AI-only email accounts

The owner approved direct agent sending on AI-only mailboxes. Select AI agent mailbox and explicitly enable agent sending in its settings. Create one named, expiring API key for each agent under Integrations, selecting only its intended mailbox and required permissions. Do not share a workspace-wide key between agents.

- Receive/read: `GET /api/messages?management_mode=ai&mailbox_id=...`, then authorized message/attachment reads. Existing signed `message.received` webhooks send identifiers; agents fetch content through their own scoped key.
- Prepare a draft: `POST /api/drafts` with `drafts:write` and a write grant. A key can edit/send only drafts bound to that exact key; a different key belonging to the same user does not inherit them.
- Send: `POST /api/mailboxes/{id}/send` with `mail:send`, the owner's send grant, the matching mailbox restriction and the enabled AI-only policy. Draft-to-send uses the same policy.
- The queue records the originating key and exact queued-content hash. Before submission the worker rechecks expiration/revocation, scope, mailbox restriction, active user, current send grant, content and AI-only policy. Revoking authority stops a queued job; it cannot recall a message already accepted by SMTP.
- `approval_source=agent_policy` distinguishes agent authorization from human approval. Human and shared mailboxes reject direct API sends; agents can prepare drafts for a person to approve/send.

Compatibility change: existing API integrations that directly sent from human/shared mailboxes must move to an explicitly enabled AI-only mailbox, or switch to human-reviewed drafts. No existing mailbox is reclassified or granted autonomy automatically. Drafts without a recorded originating key remain available to their human owner; agents must create a new key-bound draft. Existing pending submissions authorized before the upgrade are not silently deleted; inspect queues before a policy cutover.

## Hermes assistant settings

Open Assistant / Work → Hermes settings. Enter your HTTPS webhook URL and its bearer/signing secret; the secret is encrypted and never included in chat prompts or returned by the API. An administrator can explicitly approve that exact HTTPS origin in the connection form. Ordinary users may use approved origins but cannot approve new ones. Origins can be revoked from Hermes settings. Server-approved origins remain controlled by server policy.

Workspace approval permits public HTTPS destinations only. Private destinations additionally require the operator's exact `WEBHOOK_PRIVATE_ORIGINS` entry and normal trusted TLS; credentials in URLs, fragments, query-string tokens, link-local/metadata addresses, DNS rebinding and redirects are rejected. Both origin approval and DNS addresses are checked again at request time.

Use Test webhook to send only a synthetic connection request. It validates the response without executing returned actions in Postlane. Credentials saved is not proof of a live connection. The production Hermes URL/secret remain unset until the owner enters them.

Select Hermes as the AI provider for a new Work conversation, then select the business connections that conversation may use and confirm consent. The webhook receives only that conversation/prompt and the user-approved connection context/results. Postlane validates returned actions against the existing typed operation allowlist, ownership and permissions. Reads run automatically; changes/posts require existing human approval. The Work mail tool prepares drafts and cannot send human/shared mail. An external Hermes service's independently granted credentials and actions remain its operator's responsibility.

### Webhook contract

POST the saved endpoint with `Authorization: Bearer <shared secret>`, `Content-Type: application/json`, `Idempotency-Key`, `X-Postlane-Timestamp` and `X-Postlane-Signature: sha256=<HMAC>`. The signature is HMAC-SHA256 over `timestamp + '.' + exact body` using the same shared secret. Verify it with a short replay window and deduplicate the request ID. Never log the bearer header or secret. This secret is separate from the scoped Postlane API key used by an agent.

Request shape:

```json
{"version":1,"type":"postlane.assistant.request","request_id":"unique-id","user_id":"workspace-user-id","prompt":"bounded assistant context"}
```

Respond synchronously with JSON:

```json
{"reply":"Assistant response","actions":[]}
```

Optional actions use the existing Work `{connection_id, operation, arguments}` proposal contract and at most five actions. The receiver may need an adapter to translate this contract to its Hermes runtime. No generic webhook URL is assumed compatible. Postlane pins a checked DNS address, validates the TLS hostname, does not follow redirects, uses a 30-second socket timeout and caps replies at 200 KB. Error details and bearer credentials are not echoed. A timeout is not proof that an external agent performed no action; use receiver-side idempotency and inspect its activity before retrying.

## Verification

The feature passed 79 API tests on isolated SQLite and disposable PostgreSQL databases, including repeated upgrade from the old mailbox schema and unchanged existing grants. Browser checks used a separate synthetic installation: Human/Shared/AI switching, user creation with initial access, editing shared rights, restricted member login, Hermes settings controls and mobile layout all passed with no JavaScript errors. No production message or customer record was used by those tests; no external Hermes endpoint or real email send was invoked.
