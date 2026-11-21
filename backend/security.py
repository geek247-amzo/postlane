import hashlib
import json
import secrets
from dataclasses import dataclass
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import config
from .models import User, LoginSession, ApiKey, Grant, Mailbox, get_db, now

passwords = PasswordHasher()
fernet = Fernet(config.ENCRYPTION_KEY.encode())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def encrypt(value):
    return fernet.encrypt(json.dumps(value).encode()).decode()


def decrypt(value):
    return json.loads(fernet.decrypt(value.encode())) if value else {}


def verify_password(value, hashed):
    try:
        return passwords.verify(hashed, value)
    except (VerificationError, InvalidHashError):
        return False


@dataclass
class Principal:
    user: User
    key: ApiKey | None = None
    csrf: str = ""


def current(request: Request, db: Session = Depends(get_db)):
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer "):
        key = db.scalar(
            select(ApiKey).where(
                ApiKey.token_hash == digest(bearer[7:]),
                ApiKey.revoked == False,
                ApiKey.expires > now(),
            )
        )
        user = db.get(User, key.user_id) if key else None
        if not user or not user.active:
            raise HTTPException(401, "Invalid or expired API key")
        if config.PRODUCTION and user.role == "admin" and not user.totp_secret:
            raise HTTPException(
                403, "Administrator MFA must be enabled before using API keys"
            )
        return Principal(user, key)
    session = db.get(LoginSession, digest(request.cookies.get("postlane_session", "")))
    if not session or session.expires < now():
        raise HTTPException(401, "Sign in to continue")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account unavailable")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), session.csrf
        ):
            raise HTTPException(403, "Invalid CSRF token")
    if (
        config.PRODUCTION
        and user.role == "admin"
        and not user.totp_secret
        and not request.url.path.startswith("/api/auth/")
    ):
        raise HTTPException(
            403,
            "Set up two-factor authentication before administering this installation",
        )
    return Principal(user, csrf=session.csrf)


def human(p: Principal):
    if p.key:
        raise HTTPException(403, "A signed-in person must perform this action")


def admin(p: Principal):
    human(p)
    if p.user.role != "admin":
        raise HTTPException(403, "Administrator access required")


def scope(p: Principal, value: str):
    if p.key and value not in json.loads(p.key.scopes):
        raise HTTPException(403, f"Missing scope: {value}")


def mailbox_ids(db, p, permission="read"):
    query = select(Grant.mailbox_id).where(Grant.user_id == p.user.id)
    if permission == "write":
        query = query.where(Grant.can_write == True)
    if permission == "send":
        query = query.where(Grant.can_send == True)
    ids = list(db.scalars(query))
    if not p.key:
        return ids
    allowed_ids = json.loads(p.key.mailbox_ids)
    if "*" in allowed_ids:
        return ids
    return [v for v in ids if v in allowed_ids]


def mailbox_access(db, p, mailbox_id, permission="read"):
    scope(
        p,
        {"read": "messages:read", "write": "messages:write", "send": "mail:send"}[
            permission
        ],
    )
    if mailbox_id not in mailbox_ids(db, p, permission):
        raise HTTPException(404, "Mailbox not found or not permitted")
    box = db.get(Mailbox, mailbox_id)
    if not box:
        raise HTTPException(404, "Mailbox not found")
    return box


def draft_hash(d):
    return digest(
        json.dumps(
            [d.mailbox_id, d.to, d.cc, d.subject, d.body, d.html_body, d.reply_to, d.attachments_hash],
            separators=(",", ":"),
        )
    )
