import json
import time
import hashlib
import hmac
import pytest
from backend import stalwart
from backend.models import *
from examples.verify_webhook import verify_event


def test_webhook_signature_and_replay_window():
    body = json.dumps(
        {"id": "evt-1", "version": 1, "event": "message.received"}
    ).encode()
    timestamp = str(int(time.time()))
    signature = (
        "sha256="
        + hmac.new(
            b"secret", timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
    )
    assert verify_event(body, timestamp, signature, "secret")["id"] == "evt-1"
    with pytest.raises(ValueError):
        verify_event(body + b" ", timestamp, signature, "secret")
    with pytest.raises(ValueError):
        verify_event(body, "1", signature, "secret")


def test_alias_update_preserves_existing_aliases_and_uses_state(monkeypatch):
    account = {
        "id": "acct1",
        "name": "hello",
        "domainId": "domain1",
        "aliases": {
            "existing": {"name": "support", "domainId": "domain1", "enabled": True}
        },
    }
    monkeypatch.setattr(stalwart, "find_account", lambda address: (account, "state1"))
    monkeypatch.setattr(stalwart, "find_domain", lambda name: "domain1")
    calls = []

    def fake_call(method, args):
        calls.append((method, args))
        return {"updated": {"acct1": None}}

    monkeypatch.setattr(stalwart, "call", fake_call)
    stalwart.add_alias("hello@example.com", "sales@example.com")
    args = calls[0][1]
    assert args["ifInState"] == "state1"
    aliases = args["update"]["acct1"]["aliases"]
    assert aliases["existing"]["name"] == "support"
    assert any(a["name"] == "sales" for a in aliases.values())


def test_alias_api_requires_verified_domain(client, mailbox, monkeypatch):
    with SessionLocal() as db:
        db.get(Mailbox, mailbox["id"]).provider = "hosted"
        db.commit()
    calls = []
    monkeypatch.setattr(stalwart, "add_alias", lambda *a: calls.append(a))
    path = f"/api/mailboxes/{mailbox['id']}/aliases"
    assert client.post(path, json={"email": "sales@example.com"}).status_code == 422
    assert not calls
    with SessionLocal() as db:
        db.add(Domain(name="example.com", verified=True))
        db.commit()
    assert client.post(path, json={"email": "sales@example.com"}).status_code == 201
    assert calls == [("hello@example.com", "sales@example.com")]


def test_oauth_callback_requires_browser_binding(client, owner):
    assert (
        client.get("/api/oauth/callback?state=stolen-state&code=example").status_code
        == 400
    )


def test_read_only_user_cannot_edit_or_send(client, mailbox, owner):
    r = client.post(
        "/api/users",
        json={
            "name": "Reader",
            "email": "reader@example.com",
            "password": "reader-password-123",
        },
    )
    reader = r.json()
    client.post(
        "/api/grants",
        json={
            "user_id": reader["id"],
            "mailbox_id": mailbox["id"],
            "can_write": False,
            "can_send": False,
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "reader@example.com", "password": "reader-password-123"},
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert client.get("/api/messages/" + mailbox["message_id"]).status_code == 200
    assert (
        client.patch(
            "/api/messages/" + mailbox["message_id"], json={"starred": True}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/drafts", json={"mailbox_id": mailbox["id"], "body": "Not allowed"}
        ).status_code
        == 404
    )


def test_mfa_production_gate(client, owner, monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "PRODUCTION", True)
    assert client.get("/api/mailboxes").status_code == 403
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/mfa/setup").status_code == 200


def test_queued_send_is_idempotent_and_cancellable(client, mailbox):
    from backend.security import encrypt

    with SessionLocal() as db:
        db.get(Mailbox, mailbox["id"]).config = encrypt({"configured": True})
        db.commit()
    draft = client.post(
        "/api/drafts",
        json={
            "mailbox_id": mailbox["id"],
            "to": "client@example.com",
            "subject": "Hello",
            "body": "Hello",
        },
    ).json()
    path = "/api/drafts/" + draft["id"]
    assert client.post(path + "/send", json={}).status_code == 200
    assert client.post(path + "/send", json={}).status_code == 409
    assert client.post(path + "/cancel").json()["status"] == "draft"


def test_n8n_workflow_contains_no_embedded_credentials():
    from pathlib import Path

    workflow = json.loads(Path("examples/n8n-label-invoices.json").read_text())
    assert workflow["active"] is False
    http_nodes = [
        n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert len(http_nodes) == 2
    for node in http_nodes:
        assert node["parameters"]["genericAuthType"] == "httpHeaderAuth"
        assert "credentials" not in node
