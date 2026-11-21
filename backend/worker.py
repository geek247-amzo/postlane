"""One worker process per installation. Durable submission and webhook state."""

import json
import logging
import time
from sqlalchemy import select, update, delete
from . import config
from .models import *
from .providers import fetch_messages, send_message, ProviderError, DeliveryUncertain
from .security import decrypt, draft_hash
from .events import emit, post_webhook
from .runtime import heartbeat
from . import push
from . import mailcow
from . import mailbox_modes
from .spam import sender_address, assess_message, ai_assess_message

log = logging.getLogger("postlane.worker")


def replace_attachments(db, message, rows):
    db.execute(delete(Attachment).where(Attachment.message_id == message.id))
    for row in rows[:50]:
        content = row.get("content", b"")
        if not content or len(content) > 5_000_000:
            continue
        db.add(
            Attachment(
                message_id=message.id,
                filename=str(row.get("filename") or "attachment")[:500],
                content_type=str(row.get("content_type") or "application/octet-stream")[:255],
                size=len(content),
                content_id=str(row.get("content_id") or "")[:500],
                inline=bool(row.get("inline")),
                content=content,
            )
        )


def sync_mailbox(db, box):
    try:
        rows = fetch_messages(box)
        rules = list(db.scalars(select(SpamRule).where(SpamRule.mailbox_id == box.id)))
        spam_senders = {rule.sender for rule in rules if rule.action == "spam"}
        trusted_senders = {rule.sender for rule in rules if rule.action == "trusted"}
        count = 0
        new_messages = []
        for item in rows:
            attachments = item.pop("attachments", [])
            authentication = item.pop("authentication", "")
            assessment = assess_message(
                item.get("sender", ""),
                item.get("subject", ""),
                item.get("body", ""),
                item.get("html_body", ""),
                authentication,
            )
            ai_assessment = ai_assess_message(
                box,
                item.get("sender", ""),
                item.get("subject", ""),
                item.get("body", ""),
                item.get("html_body", ""),
            )
            if ai_assessment:
                assessment = {
                    "score": max(assessment["score"], ai_assessment["score"]),
                    "verdict": "spam" if "spam" in (assessment["verdict"], ai_assessment["verdict"]) else "likely_spam" if "likely_spam" in (assessment["verdict"], ai_assessment["verdict"]) else "clean",
                    "reasons": list(dict.fromkeys(assessment["reasons"] + ai_assessment["reasons"]))[:8],
                }
            normalized_sender = sender_address(item.get("sender", ""))
            if normalized_sender in trusted_senders:
                assessment = {"score": 0, "verdict": "clean", "reasons": ["Sender marked not spam by a user."]}
            item["spam_score"] = assessment["score"]
            item["spam_verdict"] = assessment["verdict"]
            item["spam_reasons"] = json.dumps(assessment["reasons"])
            item["spam_checked_at"] = now()
            if assessment["verdict"] == "spam" and item.get("folder") == "inbox":
                item["folder"] = "spam"
            existing = db.scalar(
                select(Message).where(
                    Message.mailbox_id == box.id, Message.remote_id == item["remote_id"]
                )
            )
            if existing:
                # Workspace folders and labels remain local; provider read state stays authoritative.
                existing.unread = item["unread"]
                existing.body = item["body"]
                existing.html_body = item.get("html_body", "")
                existing.spam_score = item["spam_score"]
                existing.spam_verdict = item["spam_verdict"]
                existing.spam_reasons = item["spam_reasons"]
                existing.spam_checked_at = item["spam_checked_at"]
                if item.get("folder") == "spam" and existing.folder == "inbox":
                    existing.folder = "spam"
                replace_attachments(db, existing, attachments)
                if sender_address(item.get("sender", "")) in spam_senders:
                    existing.folder = "spam"
                continue
            if sender_address(item.get("sender", "")) in spam_senders:
                item["folder"] = "spam"
            m = Message(mailbox_id=box.id, **item)
            db.add(m)
            db.flush()
            replace_attachments(db, m, attachments)
            emit(db, "message.received", box.id, m.id)
            new_messages.append(m)
            count += 1
        box.status = "connected"
        box.error = ""
        box.last_sync = now()
        db.commit()
        if new_messages and push.configured():
            user_ids = list(
                db.scalars(
                    select(Grant.user_id).where(
                        Grant.mailbox_id == box.id, Grant.can_write == True
                    )
                )
            )
            subscriptions = list(
                db.scalars(
                    select(PushSubscription).where(PushSubscription.user_id.in_(user_ids))
                )
            )
            for m in new_messages:
                for subscription in subscriptions:
                    if not push.send(
                        subscription,
                        "New email",
                        f"{m.sender}: {m.subject}",
                        "/",
                    ):
                        db.delete(subscription)
            db.commit()
        return count
    except Exception as ex:
        db.rollback()
        box = db.get(Mailbox, box.id)
        box.status = "error"
        box.error = (
            "Sync failed. Check credentials, connectivity, or reconnect your account."
        )
        db.commit()
        log.warning("Mailbox sync failed: %s (%s)", box.id, type(ex).__name__)
        raise ProviderError(box.error) from ex


def run_submissions():
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(Draft.id).where(
                    Draft.status == "queued", Draft.scheduled_at <= now()
                )
            )
        )
    for draft_id in ids:
        with SessionLocal() as db:
            claimed = db.execute(
                update(Draft)
                .where(Draft.id == draft_id, Draft.status == "queued")
                .values(status="sending", version=Draft.version + 1)
            )
            db.commit()
            if not claimed.rowcount:
                continue
            d = db.get(Draft, draft_id)
            box = db.get(Mailbox, d.mailbox_id)
            user = db.get(User, d.user_id)
            grant = db.scalar(
                select(Grant).where(
                    Grant.user_id == d.user_id,
                    Grant.mailbox_id == d.mailbox_id,
                    Grant.can_send == True,
                )
            )
            try:
                d.error = ""
                if config.DEMO or not user or not user.active or not grant:
                    raise ProviderError("Sending permission is unavailable")
                authority = db.get(AgentDraftAuthority, d.id)
                if authority and authority.queued and not mailbox_modes.agent_submission_valid(db, d, box):
                    raise ProviderError("Agent sending authority was revoked, expired or changed")
                if not (authority and authority.queued) and d.ai_generated and d.approved_hash != draft_hash(d):
                    raise ProviderError("Draft approval no longer matches")
                attachments = list(
                    db.scalars(
                        select(DraftAttachment).where(DraftAttachment.draft_id == d.id)
                    )
                )
                send_message(box, d, attachments)
                d.status = "sent"
                # A sent record means submission was accepted, not recipient delivery.
                db.add(
                    Message(
                        mailbox_id=box.id,
                        remote_id="submission:" + d.id,
                        sender=box.email,
                        recipients=d.to,
                        subject=d.subject,
                        body=d.body,
                        html_body=d.html_body,
                        folder="sent",
                        unread=False,
                    )
                )
                emit(db, "submission.accepted", box.id, d.id)
                audit(db, user.email, "submission.accepted", d.id)
            except DeliveryUncertain as ex:
                d.status = "uncertain"
                d.error = str(ex)[:1000]
                audit(db, "worker", "submission.uncertain", d.id)
            except Exception as ex:
                d.status = "failed"
                d.error = str(ex)[:1000] or type(ex).__name__
                emit(db, "submission.failed", box.id, d.id)
                audit(db, "worker", "submission.failed", d.id)
                log.warning("Submission failed: %s (%s) %s", d.id, type(ex).__name__, d.error)
            db.commit()


def run_deliveries():
    if config.DEMO:
        return
    with SessionLocal() as db:
        for d in db.scalars(
            select(Delivery)
            .where(Delivery.status == "pending", Delivery.next_at <= now())
            .limit(20)
        ):
            hook = db.get(Webhook, d.webhook_id)
            user = db.get(User, hook.user_id)
            grant = db.scalar(
                select(Grant).where(
                    Grant.user_id == hook.user_id, Grant.mailbox_id == hook.mailbox_id
                )
            )
            if not hook.active or not user or not user.active or not grant:
                d.status = "cancelled"
                continue
            d.attempts += 1
            try:
                code = post_webhook(
                    hook.url, d.payload.encode(), decrypt(hook.secret)["secret"]
                )
                d.response = f"HTTP {code}"
                if 200 <= code < 300:
                    d.status = "delivered"
            except Exception as ex:
                d.response = type(ex).__name__
            if d.status != "delivered":
                d.status = "dead" if d.attempts >= 8 else "pending"
                d.next_at = now() + min(3600, 15 * 2**d.attempts)
        db.commit()


def reconcile_mailcow_domains():
    if not mailcow.configured():
        return
    with SessionLocal() as db:
        domains = [d.name for d in db.scalars(select(Domain))]
    if domains:
        mailcow.ensure_domains(domains)


def run():
    logging.basicConfig(level=logging.INFO)
    Base.metadata.create_all(engine)
    mailbox_modes.migrate(engine)
    # Never automatically retry an SMTP submission interrupted by a worker restart.
    with SessionLocal() as db:
        db.execute(
            update(Draft).where(Draft.status == "sending").values(status="uncertain")
        )
        db.commit()
    last_sync = 0
    while True:
        try:
            heartbeat()
            run_submissions()
            run_deliveries()
            if now() - last_sync >= 120:
                try:
                    reconcile_mailcow_domains()
                except ProviderError as ex:
                    log.warning("Mailcow domain reconciliation failed: %s", ex)
                with SessionLocal() as db:
                    for box in db.scalars(
                        select(Mailbox).where(
                            Mailbox.provider != "demo", Mailbox.config != ""
                        )
                    ):
                        heartbeat()
                        try:
                            sync_mailbox(db, box)
                        except ProviderError:
                            pass
                last_sync = now()
        except Exception as ex:
            log.error("Worker cycle failed (%s)", type(ex).__name__)
        time.sleep(5)


if __name__ == "__main__":
    run()
