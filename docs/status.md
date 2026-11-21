# Postlane — Created by CloudMonkey

## Product contract

Build a private email workspace for business teams, initially 3 domains and 10 mailboxes. Each resale customer gets a separate Ubuntu Docker installation, database, mail storage, secrets, and backups. Both hosted Stalwart accounts and existing Google/Microsoft/IMAP accounts are supported. Follow [the setup runbook](docs/agent-setup.md) and [feature status](docs/status.md).

## Before changing code

Read README.md, SECURITY.md, docs/product-architecture.md, and the relevant integration adapter. Inspect current code and tests before assuming a feature exists. Keep CloudMonkey attribution visible in login, Settings, repository documentation, and image metadata. Do not describe configured adapters as live-verified integrations.

## Security invariants

- External AI defaults off per mailbox. Only a human can approve or send. Edits invalidate content approval; review and submission must use the current draft version.
- Admin role never implies access to mailbox content. Enforce grants and API scopes on every operation, including worker execution. Automation keys cannot approve mail. Direct API sending is allowed only from explicitly enabled AI-only mailboxes, with the key owner’s send grant, mail:send scope and exact mailbox restriction rechecked before submission. Human/shared mailboxes require human-controlled sending.
- Treat email and AI output as untrusted data. Render text safely and do not fetch remote images. Mail reply generation has no tools. The user-authorized Work agent can automatically read selected connections; changes and public posts require authenticated human approval. Never expose arbitrary HTTP, SQL, shell, or provider credentials to a model.
- TLS certificate validation stays enabled. Mail destinations and webhook origins require explicit operator allowlists. Hermes public HTTPS origins can also be explicitly approved by a signed-in workspace administrator; private destinations still require operator policy. Preserve webhook DNS pinning, private-address protections, signatures, retries, and deduplication contract.
- Never log or commit message bodies, credentials, session cookies, OAuth codes, MFA seeds, .env, database files, backups, or private keys. Never print fully expanded Compose configuration or decrypted connection records.
- Keep production MFA, CSRF, secure cookies, origin validation, request limits, and authentication throttling. No production demo data or SQLite.
- An uncertain send must not automatically retry: provider acceptance may already have occurred.

## Implementation and checks

Frontend: React/TypeScript in src. Backend: FastAPI/SQLAlchemy in backend. Worker owns synchronization, scheduled submission, and outbox delivery. Docker builds Node 24 and Python 3.13. Exactly one API process and worker are supported.

Install with `npm ci` and `python -m pip install -r backend/requirements.lock` in an isolated virtual environment. Run `npm run build` and `python -m pytest -q`. CI also runs against a disposable PostgreSQL database and builds/starts the Docker image. Never point tests at customer storage: tests drop tables. Format changed frontend files with Prettier; Python with Ruff if installed.

Change schema only with a reviewed migration and a tested restore/rollback plan. `create_all` is initial schema creation, not a migration tool. Extend meaningful authorization and failure-path tests when changing security boundaries or sending behavior. Do not replace live adapters with mock success responses to make pages appear ready.

## Deployment authority and evidence

Proceed with authorized local fixes, documentation, tests, and private repository updates. Obtain actual server access and integration credentials through a secure channel before dependent setup; never invent DNS verification or delivery success. Use the operator's approved domains and test recipients for real sends. Do not switch customer MX or migrate/delete live mail without explicit cutover authorization. Never use `docker compose down -v` against an installation containing mail.

Follow docs/agent-setup.md in order. Record commands, versions, pass/fail results and sanitized evidence in a private deployment record. A deployment is not ready until docs/release-checklist.md passes. Report remaining feature gaps explicitly. Keep repositories private and exclude all local/customer state from commits.
