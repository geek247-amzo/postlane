import time
import uuid
from sqlalchemy import (
    create_engine,
    String,
    Text,
    Integer,
    Boolean,
    LargeBinary,
    ForeignKey,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL


def uid():
    return uuid.uuid4().hex


def now():
    return int(time.time())


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    hide_parameters=True,
    **(
        {"connect_args": {"check_same_thread": False}}
        if DATABASE_URL.startswith("sqlite")
        else {}
    ),
)
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="member")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret: Mapped[str] = mapped_column(Text, default="")
    totp_pending: Mapped[str] = mapped_column(Text, default="")
    totp_last_step: Mapped[int] = mapped_column(Integer, default=0)
    default_mailbox_id: Mapped[str] = mapped_column(String(32), default="")


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[int] = mapped_column(Integer)


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_agent_hash: Mapped[str] = mapped_column(String(64))
    ip_address: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires: Mapped[int] = mapped_column(Integer)


class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    verification: Mapped[str] = mapped_column(String(64), default=uid)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    dns_status: Mapped[str] = mapped_column(Text, default="{}")


class Mailbox(Base):
    __tablename__ = "mailboxes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(20), default="imap")
    color: Mapped[str] = mapped_column(String(20), default="#408978")
    config: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="not_connected")
    error: Mapped[str] = mapped_column(String(250), default="")
    last_sync: Mapped[int] = mapped_column(Integer, default=0)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    management_mode: Mapped[str] = mapped_column(String(20), default="human", server_default="human")
    ai_send_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    signature: Mapped[str] = mapped_column(Text, default="")
    signature_html: Mapped[str] = mapped_column(Text, default="")
    logo_url: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    device: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (UniqueConstraint("user_id", "mailbox_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"))
    can_write: Mapped[bool] = mapped_column(Boolean, default=True)
    can_send: Mapped[bool] = mapped_column(Boolean, default=False)


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("mailbox_id", "name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("mailbox_id", "remote_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"), index=True)
    remote_id: Mapped[str] = mapped_column(String(512), default=uid)
    thread_id: Mapped[str] = mapped_column(String(512), default="")
    sender: Mapped[str] = mapped_column(String(500))
    recipients: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(String(1000), default="(No subject)")
    body: Mapped[str] = mapped_column(Text, default="")
    html_body: Mapped[str] = mapped_column(Text, default="")
    folder: Mapped[str] = mapped_column(String(120), default="inbox", index=True)
    labels: Mapped[str] = mapped_column(Text, default="[]")
    unread: Mapped[bool] = mapped_column(Boolean, default=True)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[int] = mapped_column(Integer, default=now, index=True)
    snoozed_until: Mapped[int] = mapped_column(Integer, default=0)
    assigned_to: Mapped[str] = mapped_column(String(32), default="")
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    spam_score: Mapped[int] = mapped_column(Integer, default=0)
    spam_verdict: Mapped[str] = mapped_column(String(20), default="unchecked")
    spam_reasons: Mapped[str] = mapped_column(Text, default="[]")
    spam_checked_at: Mapped[int] = mapped_column(Integer, default=0)
    spam_reviewed_at: Mapped[int] = mapped_column(Integer, default=0)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500), default="attachment")
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    content_id: Mapped[str] = mapped_column(String(500), default="")
    inline: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class SpamRule(Base):
    __tablename__ = "spam_rules"
    __table_args__ = (UniqueConstraint("mailbox_id", "sender"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"), index=True)
    sender: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(20), default="spam")
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    to: Mapped[str] = mapped_column(Text, default="")
    cc: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(String(1000), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    html_body: Mapped[str] = mapped_column(Text, default="")
    reply_to: Mapped[str] = mapped_column(String(32), default="")
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    error: Mapped[str] = mapped_column(Text, default="")
    attachments_hash: Mapped[str] = mapped_column(String(64), default="")
    scheduled_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}


class DraftAttachment(Base):
    __tablename__ = "draft_attachments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500), default="attachment")
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    content_id: Mapped[str] = mapped_column(String(500), default="")
    inline: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(20))
    scopes: Mapped[str] = mapped_column(Text)
    mailbox_ids: Mapped[str] = mapped_column(Text)
    expires: Mapped[int] = mapped_column(Integer)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Webhook(Base):
    __tablename__ = "webhooks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"))
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    webhook_id: Mapped[str] = mapped_column(ForeignKey("webhooks.id"))
    payload: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[int] = mapped_column(Integer, default=now)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    response: Mapped[str] = mapped_column(String(200), default="")


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(100), default="")
    at: Mapped[int] = mapped_column(Integer, default=now)


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[int] = mapped_column(Integer, default=now)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"))
    verifier: Mapped[str] = mapped_column(Text)
    expires: Mapped[int] = mapped_column(Integer)


def get_db():
    with SessionLocal() as db:
        yield db


def audit(db, actor, action, resource=""):
    db.add(Audit(actor=actor, action=action, resource=resource))


class AgentDraftAuthority(Base):
    __tablename__ = "agent_draft_authority"
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), primary_key=True)
    key_id: Mapped[str] = mapped_column(ForeignKey("api_keys.id"))
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    queued: Mapped[bool] = mapped_column(Boolean, default=False)


class HermesAllowedOrigin(Base):
    __tablename__ = "hermes_allowed_origins"
    origin: Mapped[str] = mapped_column(String(512), primary_key=True)
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
