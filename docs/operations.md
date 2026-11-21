# Operations and recovery

Created by CloudMonkey. Run commands from the installation directory. Keep a private inventory of deployed Git SHA, image IDs, .env location, volumes, domains, keys, backup schedule and operational contacts.

## Health and troubleshooting

Use `docker compose ps`, `docker compose logs --tail 100 app worker`, and `curl --fail https://YOUR_APP_HOST/api/ready`. Health endpoint `/api/health` reports process liveness; `/api/ready` checks the database. Worker health checks a shared heartbeat with a 180-second freshness limit; a long provider operation can produce a stale heartbeat and warrants investigation. Docker marks unhealthy containers but does not automatically restart them solely for being unhealthy.

Settings shows integration configuration and worker status; Automations shows delivery failures. Mailbox errors distinguish configuration/connection failures. Check trusted TLS names, exact allowlists, DNS, clock synchronization and provider consent. Never disable TLS verification to fix connectivity. A configured integration is not proof of successful mail delivery.

For an uncertain send, inspect provider Sent and server submission logs before deciding what happened. Never bulk-reset sending/uncertain rows to queued. Provider submission is not exactly-once and automatic retries could duplicate mail.

## Account recovery and offboarding

For a user with a working session, Settings supports password change and invalidates other browser sessions. Administrators can disable another user with `PATCH /api/users/{id}` and `{"active":false}` using an authenticated CSRF-protected session. This revokes sessions/API keys and cancels queued drafts. In-flight provider submission may already have happened. Remove separate provider access during offboarding too.

If an administrator loses access, an authorized server operator can run:

```sh
docker compose exec app python -m backend.admin owner@example.com --disable-mfa
```

The command prompts privately for a new password, clears MFA only with the explicit flag, revokes sessions and API keys, cancels queued drafts, and records recovery in audit history. Re-enroll MFA immediately after login. Verify the requester's identity before operator recovery. No email reset endpoint is exposed.

## Backup and restore

Choose an encrypted off-host backup system and retention policy; none is automatically configured. Protect .env/encryption keys, PostgreSQL logical dumps, Stalwart configuration/mail storage, and TLS material together. Losing encryption keys makes stored provider credentials unusable. A live filesystem copy of PostgreSQL storage is not a consistent backup.

For a planned application backup on Ubuntu:

```sh
umask 077
mkdir -p backups
docker compose stop app worker
docker compose exec -T db pg_dump -U postlane -d postlane -Fc > backups/postlane.dump
docker compose up -d app worker
```

Check pg_dump's exit status and nonempty output before accepting the backup. This only backs up the application database. Separately take a Stalwart-supported backup, or stop Stalwart before snapshotting its configuration and mail volumes; stopping mail reception is an operational maintenance window. Copy protected configuration/keys into the recovery set, encrypt it and transfer off-host. Do not leave plaintext dumps on a shared server or commit backups.

Restore first on an isolated host with outbound SMTP blocked, no customer DNS routing, and worker stopped. Restore matching configuration/ENCRYPTION_KEY and Stalwart storage, initialize an empty PostgreSQL database, then use `pg_restore -U postlane -d postlane --exit-on-error` with the dump inside the database container. Verify users, grants, messages, aliases and credential decryption before starting a worker. Review queued/uncertain submissions so restored state cannot resend old mail. Record actual restore duration and recovery point. Promote only through an approved cutover.

## Updates and rollback

Back up first. Read dependency release notes, build the new image and test against restored data. Initial schema creation uses create_all; no migration framework is present. Never assume it upgrades an existing schema. Schema changes require a reviewed migration and rollback plan. Record old image IDs and retain backups. Reverting code cannot safely undo every schema change; restore may be required. Never downgrade PostgreSQL/Stalwart against newer data directories.

Monitor disk/quotas, mail queue age and bounces, worker health, certificates, dependency vulnerabilities, backup freshness and restore success. Rotate OAuth/API/webhook credentials with consumers coordinated; rotating a webhook secret can invalidate outstanding events signed with the previous secret. Never run `docker compose down -v` on customer data.

Core secrets also exist in the protected secrets/ directory and must match .env. sync_secrets.py materializes missing files but refuses different existing values. For planned database-password rotation, stop app/worker, change the database role password through a protected PostgreSQL administration session, update .env and its mounted secret file, then recreate services and verify readiness. Avoid passwords in shell history. For encryption-key rotation, first implement and test re-encryption of every encrypted credential against a backup; replacing a file alone breaks decryption. Back up both .env and secrets/ with the database recovery set.
