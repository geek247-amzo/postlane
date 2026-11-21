# Security — CloudMonkey Postlane

This release is an initial implementation, not an independently audited mail platform. Use the [deployment checklist](docs/release-checklist.md) before accepting business mail. Report vulnerabilities privately to the repository owner through your established CloudMonkey support channel; do not attach credentials or customer mail to issues.

## Boundaries

Authentication uses Argon2 passwords, hashed server sessions, CSRF tokens, and TOTP. Production administrators must enroll in MFA. Mailbox grants apply even to administrators. API keys are scoped, hashed, expiring and revocable; they cannot approve or send drafts. Generated reply approvals bind content and version. Worker submission rechecks grants. Operator recovery requires shell access, revokes sessions and keys, and is audited.

Provider credentials are encrypted with Fernet. Message text and metadata are stored in the database without field-level encryption. Deploy on encrypted host storage and encrypt all off-host backups. Docker administrators and root can access installation secrets and mail; this is not protection from a compromised host. Losing ENCRYPTION_KEY loses access to encrypted provider credentials.

## Ubuntu and Docker baseline

- Install supported Ubuntu security updates and Docker from its official repository. Restrict SSH to keys and trusted administration networks. Docker group membership is effectively host administration.
- App and worker run as UID 10001, with read-only roots, writable data/tmp only, no Linux capabilities, no privilege escalation, PID limits, and bounded logs. Never mount the Docker socket or use privileged mode.
- PostgreSQL and API have no host-published ports. Database uses an internal network. Mail administration ports bind to loopback. Keep the customer on a separate VM when reselling; a Docker network alone is not a hostile-tenant boundary.
- Core database, encryption and bootstrap secrets are generated alongside .env in secrets/ and mounted through Compose file secrets. The host directory is mode 0700; files are 0644 so the unprivileged container UID can read the mounted files. Protect the parent directory and never expose it through a web server. Optional provider credentials currently use container environment variables; host administrators can inspect them. `_FILE` is supported for sensitive provider credentials when supplying a custom secret mount. Compose secrets do not replace encryption at rest or protect against host root.
- Restrict .env and backups to their operator, normally mode 0600 and a private parent directory. Never run `docker compose config` without `--quiet` in shared logs; interpolation can expose optional secrets.
- Harden the mail-server and database images according to their own requirements. Do not blindly remove capabilities required by a third-party image's entrypoint or low-numbered listeners. This repository only asserts non-root/read-only hardening for the application image.
- Docker-published ports can bypass UFW rules. Apply provider firewall rules and Docker-aware forwarding rules, then probe from outside. See [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/) and [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/).

| Host port | Purpose | Exposure |
| --- | --- | --- |
| 22 | SSH | Trusted operator addresses only |
| 80, 443 | Application HTTPS and certificate issuance | Public |
| 25 | Server-to-server SMTP | Public with relay rejection |
| 465, 587 | Authenticated mail submission | Public, TLS required |
| 993 | IMAP over TLS | Public, TLS required |
| 8080, 8443 | Stalwart administration | Host loopback only; SSH tunnel |
| 5432, 8000 | Database and app | Never publish |

Outbound DNS, HTTPS, SMTP and configured IMAP destinations are needed. Limit egress using infrastructure policy where practical. Do not enable unused protocols. Configure Stalwart abuse limits, quotas, spam filtering, and attachment scanning according to your mail policy; the app does not supply antivirus.

## AI and automation

Work is a separate, user-authorized agent surface. Connections and conversations are owned by individual users; only selected connections are available in a conversation. Reads can run automatically, while changes and public posts require immutable action approval. Mail access additionally requires current mailbox grants and per-mailbox AI opt-in. Work cannot send email. Provider keys are encrypted; conversation text and result history use normal database storage. Read results are sent to the selected AI provider under conversation consent. See [Work security and Codex isolation](docs/work.md) for token storage, limits, social publishing and optional account authentication.

External AI is optional per mailbox, receives only bounded selected-message text, and has no tools. It cannot send replies. A read API key can export mail to its holder's systems: grant only intended mailboxes and trust the workflow operator. Do not place model or mail-server management credentials in n8n workflow JSON. Verify webhook HMAC over raw bytes, enforce timestamp freshness, and durably deduplicate event IDs before side effects.

## Incident response

Disable affected users, revoke API/provider tokens, stop worker submissions if sending is suspect, and preserve sanitized audit evidence. Rotate compromised credentials at the provider as well as in this app. Do not replace the encryption key without migrating encrypted values. For lost MFA use the shell recovery command in [operations](docs/operations.md). Restore only from a verified backup and investigate the host before reconnecting it to production.
