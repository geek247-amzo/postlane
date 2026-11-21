"""Installation status and account lifecycle, restricted to authenticated people."""

import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import Session
import pyotp
from . import config
from .models import (
    User,
    Mailbox,
    Domain,
    LoginSession,
    TrustedDevice,
    ApiKey,
    Draft,
    Delivery,
    get_db,
    audit,
)
from .schemas import PasswordChangeInput, UserStateInput
from .security import (
    current,
    Principal,
    admin,
    human,
    decrypt,
    digest,
    passwords,
    verify_password,
)
from .runtime import worker_status

router = APIRouter()


@router.get("/api/installation")
def installation(p: Principal = Depends(current), db: Session = Depends(get_db)):
    admin(p)

    def configured(*names):
        return all(bool(config.secret_value(name)) for name in names)

    return {
        "product": "Postlane",
        "created_by": "CloudMonkey",
        "version": "0.3.0",
        "mode": "sample"
        if config.DEMO
        else "production"
        if config.PRODUCTION
        else "development",
        "database": "postgresql"
        if config.DATABASE_URL.startswith("postgresql")
        else "sqlite",
        "worker": worker_status(),
        "domains_verified": db.scalar(
            select(func.count(Domain.id)).where(Domain.verified == True)
        ),
        "mailboxes": db.scalar(select(func.count(Mailbox.id))),
        "connected_mailboxes": db.scalar(
            select(func.count(Mailbox.id)).where(Mailbox.status == "connected")
        ),
        "queued_submissions": db.scalar(
            select(func.count(Draft.id)).where(Draft.status == "queued")
        ),
        "uncertain_submissions": db.scalar(
            select(func.count(Draft.id)).where(Draft.status == "uncertain")
        ),
        "failed_webhooks": db.scalar(
            select(func.count(Delivery.id)).where(Delivery.status == "dead")
        ),
        "integrations": {
            "gmail": configured("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
            "microsoft": configured("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
            "ai": configured("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"),
            "aliases": configured("STALWART_API_URL", "STALWART_API_TOKEN"),
            "webhooks": bool(os.getenv("WEBHOOK_ALLOWED_ORIGINS")),
            "imap": bool(os.getenv("MAIL_ALLOWED_HOSTS")),
        },
        "oauth_callback": config.ORIGIN + "/api/oauth/callback",
    }


@router.get("/api/admin/mailboxes")
def admin_mailboxes(p: Principal = Depends(current), db: Session = Depends(get_db)):
    admin(p)
    # Administrative metadata only: never grants implicit access to content.
    return [
        {"id": b.id, "email": b.email, "name": b.name, "provider": b.provider}
        for b in db.scalars(select(Mailbox).order_by(Mailbox.email))
    ]


@router.patch("/api/users/{user_id}")
def set_user_state(
    user_id: str,
    data: UserStateInput,
    p: Principal = Depends(current),
    db: Session = Depends(get_db),
):
    admin(p)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == p.user.id and not data.active:
        raise HTTPException(409, "Ask another administrator to disable your account")
    user.active = data.active
    if not data.active:
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user.id))
        db.execute(update(ApiKey).where(ApiKey.user_id == user.id).values(revoked=True))
        db.execute(
            update(Draft)
            .where(Draft.user_id == user.id, Draft.status == "queued")
            .values(
                status="draft",
                scheduled_at=0,
                approved_hash="",
                version=Draft.version + 1,
            )
        )
    audit(db, p.user.email, "user.enabled" if data.active else "user.disabled", user.id)
    db.commit()
    return {"id": user.id, "active": user.active}


@router.post("/api/auth/password")
def change_password(
    data: PasswordChangeInput,
    request: Request,
    p: Principal = Depends(current),
    db: Session = Depends(get_db),
):
    human(p)
    from .main import limit_login

    limit_login("password:" + p.user.id)
    if not verify_password(data.current_password, p.user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    if p.user.totp_secret and not pyotp.TOTP(
        decrypt(p.user.totp_secret)["secret"]
    ).verify(data.code):
        raise HTTPException(403, "A valid authenticator code is required")
    p.user.password_hash = passwords.hash(data.new_password)
    current_hash = digest(request.cookies.get("postlane_session", ""))
    db.execute(
        delete(LoginSession).where(
            LoginSession.user_id == p.user.id, LoginSession.token_hash != current_hash
        )
    )
    db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == p.user.id))
    audit(db, p.user.email, "auth.password_changed", p.user.id)
    db.commit()
    return {"ok": True, "other_sessions_revoked": True}
