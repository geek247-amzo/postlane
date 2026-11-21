# 0003: mailbox categories, agent queue authority and Hermes approvals

The additive migration adds `management_mode` (non-null, default human) and `ai_send_enabled` (non-null, default false) to mailboxes, plus new `agent_draft_authority` and `hermes_allowed_origins` tables. Existing mailboxes, grants, account identities, encrypted credentials and messages remain intact. No automatic AI sending or webhook destination is enabled.

`backend.mailbox_modes.migrate(engine)` is idempotent. PostgreSQL uses a transaction advisory lock while checking/adding columns; application and worker startup call it. Fresh installations create the full schema. Tests remove the two columns in a disposable database, migrate twice and verify the existing mailbox/grant records and old query projections still work.

Before production rollout: stop only Postlane worker then app, retain their image IDs and private Compose configuration, take a consistent custom-format PostgreSQL dump, and verify it is readable by pg_restore. Keep backup directory 0700/files 0600. Build and test the candidate image before stopping services. Start the new app first to apply the migration, verify readiness, then start the worker. Do not change Mailcow, routing, mail-server accounts or existing grants.

Rollback uses the saved application and worker images/configuration. Keep the additive tables/columns in place: old code ignores them, avoiding mail loss from restoring an older database. Pause the worker before rollback, reconcile any in-flight submissions and observe existing uncertain-delivery rules. Never drop the new tables/columns or restore an old database over new messages as an automatic rollback step. No generated secrets or database dump belongs in Git.

An intentional downgrade restores the old API-send implementation. Pause or revoke send-enabled automation tokens before a downgrade so the old version cannot restore broader human/shared-mailbox sending authority.
