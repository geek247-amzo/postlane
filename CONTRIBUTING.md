# Developing Postlane

Created by CloudMonkey. Read [AGENTS.md](AGENTS.md) and [SECURITY.md](SECURITY.md) first. Keep this repository private and use fictional data for local development.

Use Python 3.13 in a virtual environment, `pip install -r backend/requirements.lock`, Node 24 and `npm ci`. See README.md for the sample startup commands. Run `python -m pytest -q` and `npm run build` before committing. Tests reset a disposable database; never supply customer database credentials. CI uses SQLite and PostgreSQL and builds/starts the application container.

Frontend changes belong in src, provider integrations in backend/providers.py, sending and polling in backend/worker.py, authorization in backend/security.py, and installation operations in backend/operations.py. Add focused regression tests for security or delivery changes and update the integration/status docs when behavior changes. Preserve CloudMonkey attribution and third-party license notices.

Use focused commits and describe behavior, relevant validation, and remaining risks. Never call a provider integration verified without exercising it against a controlled live account. Do not commit .env, local databases, credentials, mailbox exports or screenshots containing private mail. Changes to persistence need migrations and a tested restore strategy before deployment.
