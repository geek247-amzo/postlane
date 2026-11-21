import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from backend import mail_ai
from backend.models import SessionLocal, Mailbox, Draft, User
from backend.work_models import WorkConnection
from backend.security import encrypt, passwords


def connection(db, user_id, provider="openai", enabled=True):
    row = WorkConnection(
        user_id=user_id,
        provider=provider,
        name="Private AI",
        settings=json.dumps({"model": "fixture-model"}),
        secret=encrypt({"token": "fixture-secret"}),
        enabled=enabled,
    )
    db.add(row)
    db.commit()
    return row


def test_reply_uses_current_users_work_key_and_stays_unsent(
    client, mailbox, owner, monkeypatch
):
    calls = []
    with SessionLocal() as db:
        box = db.get(Mailbox, mailbox["id"])
        box.ai_enabled = True
        c = connection(db, owner["id"])
        cid = c.id

    def generate(c, prompt, user_id):
        assert c.id == cid and user_id == owner["id"]
        assert "untrusted" in prompt and "No tools" in prompt
        calls.append(c.id)
        return "Thank you for your email."

    monkeypatch.setattr(mail_ai, "generate", generate)
    result = client.post("/api/messages/" + mailbox["message_id"] + "/ai-draft")
    assert result.status_code == 200, result.text
    assert "fixture-secret" not in result.text
    assert len(calls) == 1
    with SessionLocal() as db:
        draft = db.get(Draft, result.json()["id"])
        assert draft.ai_generated and draft.status == "draft"
        assert not draft.approved_hash


def test_personal_ai_not_shared_with_other_user(client, owner, monkeypatch):
    monkeypatch.setattr(mail_ai.config, "secret_value", lambda *a: "")
    with SessionLocal() as db:
        other = User(
            email="other@example.com",
            name="Other",
            password_hash=passwords.hash("fixture-long-password"),
        )
        db.add(other)
        db.commit()
        connection(db, other.id)
        monkeypatch.setattr(
            mail_ai,
            "generate",
            lambda *a: pytest.fail("Must not use another person’s key"),
        )
        with pytest.raises(HTTPException) as error:
            mail_ai.generate_mail_text(db, owner["id"], "System", {})
        assert error.value.status_code == 409
        assert "Work" in error.value.detail


def test_disabled_connections_not_used_for_mail(client, owner, monkeypatch):
    monkeypatch.setattr(mail_ai.config, "secret_value", lambda *a: "")
    with SessionLocal() as db:
        connection(db, owner["id"], enabled=False)
        monkeypatch.setattr(
            mail_ai,
            "generate",
            lambda *a: pytest.fail("Must not invoke disabled connection or webhook"),
        )
        with pytest.raises(HTTPException) as error:
            mail_ai.generate_mail_text(db, owner["id"], "System", {})
        assert error.value.status_code == 409


def test_work_key_does_not_bypass_mailbox_opt_in(client, mailbox, owner, monkeypatch):
    with SessionLocal() as db:
        connection(db, owner["id"])
    monkeypatch.setattr(
        mail_ai,
        "generate",
        lambda *a: pytest.fail("No external data sharing without opt-in"),
    )
    assert (
        client.post("/api/messages/" + mailbox["message_id"] + "/ai-draft").status_code
        == 403
    )


def test_compose_uses_work_model_without_saving_or_sending(
    client, mailbox, owner, monkeypatch
):
    with SessionLocal() as db:
        db.get(Mailbox, mailbox["id"]).ai_enabled = True
        connection(db, owner["id"])
    monkeypatch.setattr(
        mail_ai,
        "generate",
        lambda *a: json.dumps({"subject": "A draft", "body": "For human review."}),
    )
    response = client.post(
        "/api/ai/compose",
        json={
            "mailbox_id": mailbox["id"],
            "instruction": "Write a thank-you email",
            "mode": "custom",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["subject"] == "A draft"
    with SessionLocal() as db:
        assert db.scalar(select(Draft)) is None


def test_hermes_reply_does_not_execute_actions(client, owner, monkeypatch):
    with SessionLocal() as db:
        hermes = connection(db, owner["id"], provider="hermes")
        connection(db, owner["id"], provider="openai")
        monkeypatch.setattr(
            mail_ai,
            "generate",
            lambda *a: json.dumps({"reply": "For human review", "actions": []}),
        )
        assert (
            mail_ai.generate_mail_text(db, owner["id"], "System", {})
            == "For human review"
        )
        monkeypatch.setattr(
            mail_ai,
            "generate",
            lambda *a: json.dumps(
                {"reply": "Unsafe", "actions": [{"operation": "send"}]}
            ),
        )
        with pytest.raises(HTTPException) as error:
            mail_ai.generate_mail_text(db, owner["id"], "System", {})
        assert error.value.status_code == 502
