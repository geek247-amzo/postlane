# Changelog

## 0.3.0 — 2026-11-20

- Human, shared and AI mailbox categories with inbox filtering and explicit agent-send policy.
- Atomic initial mailbox grants for new users and editable shared-mailbox rights.
- Key-bound agent drafts and queue-time/execution-time authorization checks; human/shared mailboxes reject direct API sends.
- Hermes webhook settings with encrypted secrets, administrator-approved public HTTPS origins, revocation, signed/pinned transport and a connection test.
- Preserve the live keyboard-shortcut and DNS-copy interface changes in source, plus the owner-supplied logo and PWA icon.
- Create empty optional Compose secret mounts during fresh setup without enabling integrations or replacing existing credentials.


## 0.2.0 — 2026-09-22

Added CloudMonkey Work: per-user encrypted AI keys and business connections, private chat histories, automatic bounded reads, explicit approval for changes and public posts, and durable action results with duplicate-execution protection. Adapters cover OpenAI, Gemini, Claude, DeepSeek, ClickUp, Notion, Drive, existing mail, LinkedIn, Facebook Pages and Instagram single-image publishing. An optional isolated Codex app-server bridge supports account device sign-in. See docs/work.md for setup, scope and live-validation requirements.

## 0.1.0 — 2026-09-19

Initial CloudMonkey Postlane pilot: multi-mailbox workspace, local organization, drafts and approval, team grants, TOTP, encrypted connection credentials, IMAP/SMTP and OAuth adapters, receiving aliases, scoped API keys, optional external AI drafts, signed webhooks and an n8n example.

Includes Ubuntu Docker configuration, core mounted secrets, database/worker health checks, installation status, password change/operator recovery, developer and security runbooks, and automated API/build checks. See [deployment acceptance](docs/release-checklist.md) for live validation requirements and unimplemented features.
