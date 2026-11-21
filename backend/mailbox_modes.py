"""Mailbox categories and explicit API submission authority; never infer access from a category."""
import json
from fastapi import HTTPException
from sqlalchemy import inspect, text, select
from .models import Mailbox, ApiKey, Grant, AgentDraftAuthority, now
from .security import draft_hash


def migrate(engine):
    """Idempotent additive migration; existing mailboxes stay human-managed."""
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(1886352241)"))
        names = {c['name'] for c in inspect(conn).get_columns('mailboxes')}
        if 'management_mode' not in names:
            conn.execute(text("ALTER TABLE mailboxes ADD COLUMN management_mode VARCHAR(20) NOT NULL DEFAULT 'human'"))
        if 'ai_send_enabled' not in names:
            conn.execute(text("ALTER TABLE mailboxes ADD COLUMN ai_send_enabled BOOLEAN NOT NULL DEFAULT FALSE"))


def mode_ids(db, ids, mode):
    if mode == 'all':
        return ids
    if mode not in ('human', 'shared', 'ai'):
        raise HTTPException(422, 'Choose human, shared, ai or all mailboxes')
    modes = ['human', 'shared'] if mode == 'human' else [mode]
    return list(db.scalars(select(Mailbox.id).where(Mailbox.id.in_(ids), Mailbox.management_mode.in_(modes))))


def api_send_allowed(box):
    # Direct agent delivery is confined to explicitly enabled AI-only boxes.
    if box.management_mode != 'ai':
        raise HTTPException(403, 'Direct API sending is only allowed from AI-only mailboxes; prepare a draft for human review instead')
    if not box.ai_send_enabled:
        raise HTTPException(403, 'This AI mailbox requires a person to approve and send drafts')


def bind_agent_draft(db, draft, key):
    row = db.get(AgentDraftAuthority, draft.id)
    if row and row.key_id != key.id:
        raise HTTPException(403, 'An agent can modify or send only its own drafts')
    if not row:
        row = AgentDraftAuthority(draft_id=draft.id, key_id=key.id)
        db.add(row)
    return row


def authorize_agent_queue(db, draft, key, box):
    api_send_allowed(box)
    row = bind_agent_draft(db, draft, key)
    row.content_hash = draft_hash(draft)
    row.queued = True
    draft.approved_hash = ""


def agent_submission_valid(db, draft, box):
    row = db.get(AgentDraftAuthority, draft.id)
    if not row or not row.queued:
        return False
    key = db.get(ApiKey, row.key_id)
    if not key or key.revoked or key.expires <= now() or key.user_id != draft.user_id:
        return False
    if 'mail:send' not in json.loads(key.scopes):
        return False
    allowed = json.loads(key.mailbox_ids)
    if '*' not in allowed and draft.mailbox_id not in allowed:
        return False
    if box.management_mode != 'ai' or not box.ai_send_enabled:
        return False
    return row.content_hash == draft_hash(draft)
