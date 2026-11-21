import json
import pytest
from sqlalchemy import select
from backend.models import *
from backend.security import encrypt, decrypt, passwords, draft_hash
from backend import config
from backend.providers import parse_mime, ProviderError, DeliveryUncertain
from backend.events import validate_webhook, post_webhook


def make_draft(client, mailbox, **extra):
    r = client.post(
        "/api/drafts",
        json={
            "mailbox_id": mailbox["id"],
            "to": "client@example.com",
            "subject": "Reply",
            "body": "Thank you",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_private_endpoints_require_authentication(client):
    for path in [
        "/api/mailboxes",
        "/api/messages",
        "/api/users",
        "/api/keys",
        "/api/audit",
    ]:
        assert client.get(path).status_code == 401


def test_bootstrap_cannot_be_reused(client, owner):
    r = client.post(
        "/api/auth/setup",
        json={
            "name": "Intruder",
            "email": "intruder@example.com",
            "password": "other-password-123",
            "token": "test-installation-token",
        },
    )
    assert r.status_code == 409


def test_csrf_and_cross_origin_rejected(client, mailbox):
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        client.patch(
            "/api/messages/" + mailbox["message_id"], json={"starred": True}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    assert (
        client.patch(
            "/api/messages/" + mailbox["message_id"],
            json={"starred": True},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/messages/" + mailbox["message_id"], json={"starred": True}
        ).status_code
        == 200
    )


def test_mailbox_grants_prevent_cross_user_reads(client, mailbox):
    client.post(
        "/api/users",
        json={
            "name": "Other",
            "email": "other@example.com",
            "password": "other-password-123",
        },
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": "other-password-123"},
    )
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert client.get("/api/mailboxes").json() == []
    assert client.get("/api/messages").json()["items"] == []
    assert client.get("/api/messages/" + mailbox["message_id"]).status_code == 404
    assert (
        client.patch(
            "/api/messages/" + mailbox["message_id"], json={"starred": True}
        ).status_code
        == 404
    )
    assert client.get("/api/users").status_code == 403


def test_api_key_scope_and_revocation(client, mailbox):
    key = client.post(
        "/api/keys",
        json={
            "name": "Reader",
            "scopes": ["messages:read"],
            "mailbox_ids": [mailbox["id"]],
        },
    ).json()
    h = {"Authorization": "Bearer " + key["token"]}
    assert client.get("/api/messages", headers=h).status_code == 200
    assert (
        client.patch(
            "/api/messages/" + mailbox["message_id"], json={"starred": True}, headers=h
        ).status_code
        == 403
    )
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.delete("/api/keys/" + key["id"]).status_code == 200
    assert client.get("/api/messages", headers=h).status_code == 401


def test_api_key_cannot_gain_another_mailbox(client, mailbox):
    with SessionLocal() as db:
        second = Mailbox(email="private@example.com", name="Private")
        db.add(second)
        db.commit()
        other = second.id
    assert (
        client.post(
            "/api/keys",
            json={
                "name": "Escalation",
                "scopes": ["messages:read"],
                "mailbox_ids": [other],
            },
        ).status_code
        == 403
    )


def test_automation_drafts_require_human_approval(client, mailbox):
    key = client.post(
        "/api/keys",
        json={
            "name": "n8n",
            "scopes": ["messages:read", "drafts:write"],
            "mailbox_ids": [mailbox["id"]],
        },
    ).json()
    headers = {"Authorization": "Bearer " + key["token"]}
    d = client.post(
        "/api/drafts",
        json={
            "mailbox_id": mailbox["id"],
            "to": "client@example.com",
            "body": "AI reply",
        },
        headers=headers,
    ).json()
    assert d["ai_generated"] is True
    assert (
        client.post(
            "/api/drafts/" + d["id"] + "/approve",
            json={"version": d["version"]},
            headers=headers,
        ).status_code
        == 403
    )
    send_key = client.post(
        "/api/keys",
        json={
            "name": "Send",
            "scopes": ["mail:send"],
            "mailbox_ids": [mailbox["id"]],
        },
    )
    assert send_key.status_code == 201


def test_send_scoped_api_key_queues_through_ai_only_mailbox(client, mailbox):
    assert client.patch("/api/mailboxes/"+mailbox["id"],json={"management_mode":"ai","ai_send_enabled":True}).status_code == 200
    with SessionLocal() as db:
        db.get(Mailbox, mailbox["id"]).config = "configured"
        db.commit()
    key = client.post(
        "/api/keys",
        json={
            "name": "mailer-agent",
            "scopes": ["mail:send"],
            "mailbox_ids": [mailbox["id"]],
        },
    ).json()
    response = client.post(
        "/api/mailboxes/" + mailbox["id"] + "/send",
        headers={"Authorization": "Bearer " + key["token"]},
        json={
            "to": "client@example.com",
            "subject": "Agent message",
            "body": "Queued by the mailbox agent",
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["ai_generated"] is True
    assert response.json()["approval_source"] == "agent_policy"
    assert response.json()["approved"] is False


def test_edit_invalidates_approval_and_rejects_stale_version(client, mailbox):
    d = make_draft(client, mailbox)
    with SessionLocal() as db:
        row = db.get(Draft, d["id"])
        row.ai_generated = True
        db.commit()
        version = row.version
    assert (
        client.post(
            "/api/drafts/" + d["id"] + "/approve", json={"version": d["version"]}
        ).status_code
        == 409
    )
    approved = client.post(
        "/api/drafts/" + d["id"] + "/approve", json={"version": version}
    ).json()
    assert approved["approved"]
    payload = {
        k: approved[k]
        for k in ["mailbox_id", "to", "cc", "subject", "body", "reply_to", "version"]
    }
    payload["body"] = "Changed recipient instructions"
    result = client.put("/api/drafts/" + d["id"], json=payload)
    assert result.status_code == 200, result.text
    assert not result.json()["approved"]
    assert result.json()["ai_generated"]
    assert client.put("/api/drafts/" + d["id"], json=payload).status_code == 409


def test_login_cookie_is_httponly_and_logout_revokes(client, owner):
    token = client.cookies.get("postlane_session")
    assert token
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set("postlane_session", token)
    assert client.get("/api/auth/me").status_code == 401


def test_provider_credentials_encrypted():
    value = encrypt({"password": "highly-private-secret"})
    assert "highly-private-secret" not in value
    assert decrypt(value)["password"] == "highly-private-secret"


def test_html_email_is_plain_text():
    raw = b'From: test@example.com\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<script>steal()</script><p>Hello <b>Alex</b></p><img src="https://tracker.example/pixel">'
    parsed = parse_mime(raw)
    assert "Hello Alex" in parsed["body"]
    assert "steal" not in parsed["body"]
    assert "<img" not in parsed["body"]


def test_webhooks_require_explicit_origin(monkeypatch):
    monkeypatch.setenv("WEBHOOK_ALLOWED_ORIGINS", "https://n8n.example.com")
    assert (
        validate_webhook("https://n8n.example.com/webhook/mail").hostname
        == "n8n.example.com"
    )
    for url in [
        "http://169.254.169.254/latest",
        "https://n8n.example.com.attacker.com/hook",
        "https://user:pass@n8n.example.com/hook",
    ]:
        with pytest.raises(ValueError):
            validate_webhook(url)


def test_webhook_dns_rebinding_rejected(monkeypatch):
    monkeypatch.setenv("WEBHOOK_ALLOWED_ORIGINS", "https://n8n.example.com")
    monkeypatch.setattr(
        "backend.events.socket.getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError):
        post_webhook("https://n8n.example.com/hook", b"{}", "secret")


def test_ai_is_opt_in_and_makes_no_request(client, mailbox, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network request should be made")

    monkeypatch.setattr("backend.main.httpx.Client", forbidden)
    assert (
        client.post("/api/messages/" + mailbox["message_id"] + "/ai-draft").status_code
        == 403
    )


def test_header_injection_is_rejected(client, mailbox):
    assert (
        client.post(
            "/api/drafts",
            json={
                "mailbox_id": mailbox["id"],
                "subject": "Subject\r\nBcc: attacker@example.com",
            },
        ).status_code
        == 422
    )


def test_sent_worker_never_submits_twice(client, mailbox, monkeypatch):
    from backend.worker import run_submissions

    d = make_draft(client, mailbox)
    with SessionLocal() as db:
        row = db.get(Draft, d["id"])
        row.status = "queued"
        row.scheduled_at = now() - 1
        db.commit()
    calls = []
    monkeypatch.setattr("backend.worker.send_message", lambda *a: calls.append("sent"))
    run_submissions()
    run_submissions()
    assert calls == ["sent"]
    with SessionLocal() as db:
        assert db.get(Draft, d["id"]).status == "sent"


def test_uncertain_delivery_not_retried(client, mailbox, monkeypatch):
    from backend.worker import run_submissions

    d = make_draft(client, mailbox)
    with SessionLocal() as db:
        row = db.get(Draft, d["id"])
        row.status = "queued"
        row.scheduled_at = now() - 1
        db.commit()
    calls = []

    def uncertain(*a):
        calls.append(1)
        raise DeliveryUncertain("Connection lost")

    monkeypatch.setattr("backend.worker.send_message", uncertain)
    run_submissions()
    run_submissions()
    assert calls == [1]
    with SessionLocal() as db:
        assert db.get(Draft, d["id"]).status == "uncertain"


def test_revoked_send_grant_stops_queued_submission(
    client, mailbox, owner, monkeypatch
):
    from backend.worker import run_submissions

    d = make_draft(client, mailbox)
    with SessionLocal() as db:
        row = db.get(Draft, d["id"])
        row.status = "queued"
        row.scheduled_at = now() - 1
        grant = db.scalar(
            select(Grant).where(
                Grant.user_id == owner["id"], Grant.mailbox_id == mailbox["id"]
            )
        )
        grant.can_send = False
        db.commit()
    calls = []

    def forbidden(*a):
        calls.append(1)

    monkeypatch.setattr("backend.worker.send_message", forbidden)
    run_submissions()
    assert calls == []
    with SessionLocal() as db:
        assert db.get(Draft, d["id"]).status == "failed"


def test_folder_and_star_persist(client, mailbox):
    assert (
        client.post(
            "/api/folders", json={"mailbox_id": mailbox["id"], "name": "Clients"}
        ).status_code
        == 201
    )
    r = client.patch(
        "/api/messages/" + mailbox["message_id"],
        json={"folder": "Clients", "starred": True, "labels": ["Important"]},
    )
    assert r.status_code == 200
    assert client.get("/api/messages?folder=inbox").json()["total"] == 0
    assert client.get("/api/messages?folder=Clients").json()["total"] == 1
    assert client.get("/api/messages?folder=starred").json()["items"][0]["labels"] == [
        "Important"
    ]


def test_notes_not_in_message_body_or_outgoing_draft(client, mailbox):
    assert (
        client.post(
            "/api/messages/" + mailbox["message_id"] + "/notes",
            json={"text": "Internal pricing strategy"},
        ).status_code
        == 200
    )
    assert (
        "Internal pricing"
        not in client.get("/api/messages/" + mailbox["message_id"]).json()["body"]
    )
    assert "Internal pricing" not in make_draft(client, mailbox)["body"]
