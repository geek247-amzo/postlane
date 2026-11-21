# Postlane — Created by CloudMonkey

**Open-source email workspace · Self-hosted · Human-controlled AI assistance**

[Documentation](docs/README.md) · [Developer/agent setup](docs/agent-setup.md) · [Security](SECURITY.md) · [Deployment acceptance](docs/release-checklist.md) · [Changelog](CHANGELOG.md)

Postlane is a self-hosted email workspace for people and teams. Run it on infrastructure you control and configure your own mail providers, credentials, retention, backups and access policies.

This public repository contains the application source, development guidance and a generic self-hosting example. Mail delivery and provider integrations depend on your own configuration and should be validated in your environment. See [feature status](docs/status.md) for the implementation boundary.

## Mailbox ownership and Hermes

Release 0.3 adds Human / Shared / AI inbox views, initial per-user mailbox permissions, editable shared access and a Hermes webhook assistant settings page. Direct agent sending is restricted to explicitly enabled AI-only mailboxes. See [configuration, API and webhook contract](docs/ai-mailboxes-and-hermes.md) and the [additive migration/rollback plan](docs/migrations/0003-ai-mailboxes.md).

## Included

- **CloudMonkey Work:** private AI chat, OpenAI/Gemini/Claude/DeepSeek keys, optional Codex account sign-in, ClickUp/Notion/Drive/mail connections and LinkedIn/Facebook/Instagram actions. Reads run automatically on selected connections; changes and posts require approval. See [Work setup](docs/work.md).
- React/TypeScript interface with unified inbox, mailbox filters, search, local folders/labels, stars, snooze, bulk actions, drafts, signatures, reply/forward, and private team notes.
- Python/FastAPI API, PostgreSQL in Docker, SQLite for local development, and a durable background worker.
- Password authentication, TOTP MFA, server-side sessions, CSRF checks, per-mailbox read/write/send grants, encrypted connection credentials, scoped expiring API keys, and audit history.
- IMAP/SMTP adapters plus Google and Microsoft OAuth adapters, recent-message synchronization, delayed/scheduled submission, cancellation, and uncertain-delivery handling.
- Domain ownership verification and DNS inspection; optional Stalwart receiving-alias management.
- Per-mailbox external AI opt-in and mandatory human approval for generated replies. Automation tokens can prepare drafts but cannot approve or send them.
- Signed webhook outbox with retries and delivery history, an OpenAPI schema, and an importable n8n example.
- Docker Compose with HTTPS proxy, app, worker, PostgreSQL, and optional Stalwart mail server.

## Run the sample workspace locally

Requires Python 3.13 and Node 22.12+ (Node 24 is used in Docker).

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.lock
npm ci
./scripts/dev.ps1
```

Open **http://127.0.0.1:5173/** and choose **Open sample workspace**. The demo creates fictional messages across 3 `.demo` domains and 10 mailboxes. It cannot connect live accounts, send email, or call external AI. All sample mailbox changes persist locally in `data/postlane.db`.

On Linux/macOS, start these in separate terminals:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm ci
DEMO_MODE=true APP_ENV=development APP_URL=http://127.0.0.1:5173 .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```sh
npm run dev
```

For a clean non-demo local installation, use a separate database via `DATABASE_URL`, set `DEMO_MODE=false`, and set a unique `BOOTSTRAP_TOKEN`. Never reuse the sample database for production. The worker is not needed to explore the demo; real connections require `python -m backend.worker` running alongside the API.

## Deploy on Ubuntu

Follow [deployment.md](docs/deployment.md) for secrets, HTTPS, mail providers, OAuth, AI, backups and deployment validation.

```sh
python3 scripts/configure.py --host inbox.yourdomain.com --mail-host mail.yourdomain.com
docker compose config --quiet
docker compose up -d --build
docker compose --profile mail up -d stalwart
```

Postlane and Stalwart each require initial setup. The application does not automatically create DNS records, issue mail-server certificates, or provision mailbox accounts in Stalwart. No real mail credentials or customer data are included.

## Validate

```powershell
npm run build
.venv/Scripts/python -m pytest -q
```

The API schema is served at `/api/openapi.json`. Integration examples are in [examples](examples). The [original product brief](docs/product-architecture.md) describes the wider planned scope, not a list of completed features.

## Project layout

```text
src/                  React workspace and administration interface
backend/              API, permissions, adapters, models, and worker
tests/                Authorization, approval, delivery, and integration tests
deploy/               HTTPS proxy configuration
examples/             n8n workflow and webhook signature verification
scripts/              Local startup and per-installation secret generation
docs/                 Setup, integrations, API, operations, and feature status
compose.yaml          Private Ubuntu deployment
```

CloudMonkey attribution is included in the application and container metadata. This repository contains application source and synthetic test fixtures only. See [NOTICE.md](NOTICE.md) for attribution and third-party distribution notes.
