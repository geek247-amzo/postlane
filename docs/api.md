# API and automation

Created by CloudMonkey. The exact request/response schemas are generated at `/api/openapi.json`. `/api/docs` links to that schema. Requests use JSON over HTTPS. Errors use `detail`; handle 401/403 authorization failures, 404 inaccessible resources, 409 stale/conflicting changes, 422 validation errors and 429 throttling. Never retry a send blindly after a timeout.

Browser operations use an HttpOnly session cookie and the CSRF token returned by login in `X-CSRF-Token`. Keep the same origin. Human-only operations include administration and draft approval. API clients instead use `Authorization: Bearer <scoped key>`; never put tokens in query strings or exported workflow JSON.

Create expiring keys in Automations with only the target mailboxes and required scopes. `messages:read` permits message retrieval; `messages:write` permits workspace organization; `drafts:write` permits draft preparation; `mail:send` permits direct queued sending only from an AI-only mailbox with agent sending enabled and the key owner's current send grant. `aliases:manage` is an admin-issued scope for receiving-alias management. An automation key with both `drafts:write` and `mail:send` may send only drafts it created itself; Human/shared mailboxes and human-created drafts require a signed-in person. Agent drafts are bound to their exact originating key; key revocation and mailbox policy are checked again before SMTP submission. Scope names and constraints in the runtime schema/code are authoritative.

| Endpoint | Purpose |
| --- | --- |
| GET /api/mailboxes | Accessible mailboxes |
| GET /api/messages | Search/filter/paginate accessible messages; management_mode=human/shared/ai/all |
| GET /api/messages/{id} | Message text and details |
| GET /api/attachments/{id} | Download an attachment from an accessible message |
| GET /api/spam/review | List suspicious, unreviewed messages for the Spam Manager |
| POST /api/messages/{id}/spam-feedback | Mark a message `spam` or `not_spam` and learn its sender for that mailbox |
| PATCH /api/messages/{id} | Read state, labels and organization |
| GET/PUT/DELETE /api/domains/{id}/catchall | Inspect, enable, route, or disable a domain catch-all mailbox |
| POST /api/drafts | Prepare a draft; does not send |
| POST /api/mailboxes/{id}/send | Queue a message from an explicitly enabled AI-only mailbox (`mail:send`) |
| PATCH /api/drafts/{id} | Edit a draft; invalidates approval |
| DELETE /api/drafts/{id} | Delete an unsent draft and its stored attachments |
| GET/POST /api/mailboxes/{id}/aliases | List/create hosted receiving aliases |
| DELETE /api/mailboxes/{id}/aliases/{alias_id} | Remove receiving alias |
| GET /api/installation | Human administrator installation status, no secrets |
| GET /api/ready | Database readiness probe |

Fetch the current draft version before approval or submission and pass the version required by the schema. Every edit invalidates approval. Worker execution also checks current grants and content approval. An uncertain provider submission is never automatically retried.

Webhooks are at-least-once metadata events, signed with `X-Postlane-Signature` and `X-Postlane-Timestamp`. See [integrations](integrations.md) for signature verification and durable deduplication. A receiver needing message bodies must use a separate scoped read key.

Direct API sends are queued for the worker and return a submission record; `sent` means the SMTP provider accepted the submission, not that the recipient received it. Use signed webhooks for `submission.accepted`/`submission.failed` and poll the mailbox for replies.

Incoming messages expose `spam_score`, `spam_verdict`, and `spam_reasons`. The local detector always runs. An AI classification pass runs only when the mailbox's external AI setting is enabled and the operator has configured an HTTPS AI endpoint.

Draft and direct-send requests accept both `body` (plain text) and optional `html_body` (HTML). Postlane sanitizes the HTML, adds the selected mailbox signature/logo, and sends both alternatives as a standards-compatible `multipart/alternative` message. Mailbox settings expose `signature`, `signature_html`, and an HTTPS `logo_url`.

Outbound API drafts and direct sends also accept attachments. Send a Discord/Hermes screenshot as base64 JSON, or forward an attachment already stored on an accessible message:

```json
{
  "to": "recipient@example.com",
  "subject": "Screenshot requested",
  "body": "Here is the screenshot.",
  "attachments": [
    {
      "filename": "screen.png",
      "content_type": "image/png",
      "content_base64": "iVBORw0KGgo..."
    }
  ],
  "forward_attachment_ids": ["attachment-id-from-GET-/api/messages/{id}"]
}
```

Attachments are stored with the draft and sent as MIME attachments. Files and the combined message attachments are limited to 10 MB, and the API accepts up to 20 attachments. `forward_attachment_ids` is authorization-checked against the API key's mailbox access; Discord itself is not connected by Postlane, so Hermes must download the Discord file and pass its bytes in `content_base64` when forwarding it.

See [AI mailboxes and Hermes settings](ai-mailboxes-and-hermes.md) for per-agent keys, shared grants, assistant origin approvals and the webhook contract.
