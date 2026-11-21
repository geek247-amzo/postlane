import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete
from backend import work, config
from backend.models import SessionLocal, User, Mailbox, Grant, Draft
from backend.security import encrypt, decrypt, passwords
from backend.work_models import WorkConnection, WorkAction
from backend.work_tools import execute, validated


def connect(client, provider="openai", settings=None, token="test-secret-not-real"):
    settings = settings if settings is not None else {"model": "test-model"}
    r = client.post(
        "/api/work/connections",
        json={
            "name": provider,
            "provider": provider,
            "settings": settings,
            "token": token,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def conversation(client, connections=None):
    ai = connect(client)
    r = client.post(
        "/api/work/chats",
        json={
            "provider_id": ai["id"],
            "connection_ids": [c["id"] for c in (connections or [])],
            "consent": True,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def propose(monkeypatch, conn, operation="create_task", arguments=None):
    arguments = (
        arguments
        if arguments is not None
        else {"title": "Review launch", "body": "Review the plan"}
    )
    monkeypatch.setattr(
        work,
        "generate",
        lambda *a: json.dumps(
            {
                "reply": "Here is the proposed action.",
                "actions": [
                    {
                        "connection_id": conn["id"],
                        "operation": operation,
                        "arguments": arguments,
                    }
                ],
            }
        ),
    )


def post_message(client, chat):
    return client.post(
        f"/api/work/chats/{chat}/messages", json={"content": "Help with our launch"}
    )


def test_secret_encryption_and_no_round_trip(client, owner):
    saved = connect(client)
    assert "test-secret-not-real" not in json.dumps(saved)
    assert "test-secret-not-real" not in client.get("/api/work/connections").text
    with SessionLocal() as db:
        row = db.get(WorkConnection, saved["id"])
        assert row.secret != "test-secret-not-real"
        assert decrypt(row.secret)["token"] == "test-secret-not-real"


def test_other_user_cannot_access_connections_or_chats(client, owner):
    chat = conversation(client)
    with SessionLocal() as db:
        other = User(
            email="other@example.com",
            name="Other",
            password_hash=passwords.hash("other-secure-password-123"),
        )
        db.add(other)
        db.commit()
    client.post("/api/auth/logout")
    r = client.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": "other-secure-password-123"},
    )
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert client.get("/api/work/connections").json() == []
    assert client.get("/api/work/chats/" + chat).status_code == 404
    assert post_message(client, chat).status_code == 404


def test_write_is_proposed_and_approved_exactly_once(client, owner, monkeypatch):
    conn = connect(client, "clickup", {"list_id": "123"})
    chat = conversation(client, [conn])
    propose(monkeypatch, conn)
    executed = []
    monkeypatch.setattr(
        work, "execute", lambda *args: executed.append(args[2]) or {"id": "created"}
    )
    result = post_message(client, chat)
    assert result.status_code == 200, result.text
    assert executed == []
    action = result.json()["actions"][0]
    assert action["status"] == "pending"
    assert (
        client.post("/api/work/actions/" + action["id"] + "/approve").json()["status"]
        == "completed"
    )
    assert executed == [{"title": "Review launch", "body": "Review the plan"}]
    assert (
        client.post("/api/work/actions/" + action["id"] + "/approve").status_code == 409
    )
    assert len(executed) == 1


def test_reads_execute_automatically_and_feed_next_turn(client, owner, monkeypatch):
    conn = connect(client, "clickup", {"list_id": "123"})
    chat = conversation(client, [conn])
    prompts = []

    def model(_, prompt, user):
        prompts.append(prompt)
        return json.dumps(
            {
                "reply": "Reading tasks" if len(prompts) == 1 else "Found Launch task",
                "actions": [
                    {
                        "connection_id": conn["id"],
                        "operation": "list_tasks",
                        "arguments": {},
                    }
                ]
                if len(prompts) == 1
                else [],
            }
        )

    monkeypatch.setattr(work, "generate", model)
    monkeypatch.setattr(work, "execute", lambda *args: [{"name": "Launch task"}])
    result = post_message(client, chat)
    assert result.status_code == 200, result.text
    assert len(prompts) == 2 and "Launch task" in prompts[1]
    assert "test-secret-not-real" not in prompts[0]
    assert result.json()["actions"][0]["status"] == "completed"
    assert [e["role"] for e in result.json()["entries"]] == [
        "user",
        "assistant",
        "result",
        "assistant",
    ]


def test_agent_loop_is_bounded(client, owner, monkeypatch):
    conn = connect(client, "clickup", {"list_id": "123"})
    chat = conversation(client, [conn])
    propose(monkeypatch, conn, "list_tasks", {})
    calls = []
    monkeypatch.setattr(work, "execute", lambda *a: calls.append(1) or [])
    assert post_message(client, chat).status_code == 200
    assert len(calls) == 3


def test_disable_connection_cancels_approval(client, owner, monkeypatch):
    conn = connect(client, "clickup", {"list_id": "123"})
    chat = conversation(client, [conn])
    propose(monkeypatch, conn)
    action = post_message(client, chat).json()["actions"][0]
    assert (
        client.patch(
            "/api/work/connections/" + conn["id"], json={"enabled": False}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/work/actions/" + action["id"] + "/approve").status_code == 409
    )
    with SessionLocal() as db:
        assert db.get(WorkAction, action["id"]).status == "cancelled"


def test_ambiguous_write_never_retries(client, owner, monkeypatch):
    conn = connect(client, "clickup", {"list_id": "123"})
    chat = conversation(client, [conn])
    propose(monkeypatch, conn)
    action = post_message(client, chat).json()["actions"][0]

    def fail(*args):
        raise HTTPException(502, "timeout")

    monkeypatch.setattr(work, "execute", fail)
    assert (
        client.post("/api/work/actions/" + action["id"] + "/approve").json()["status"]
        == "uncertain"
    )
    assert (
        client.post("/api/work/actions/" + action["id"] + "/approve").status_code == 409
    )


def test_unselected_connection_is_never_executed(client, owner, monkeypatch):
    conn = connect(client, "clickup", {"list_id": "123"})
    chat = conversation(client)
    propose(monkeypatch, conn)
    monkeypatch.setattr(
        work, "execute", lambda *args: pytest.fail("Unexpected execution")
    )
    assert post_message(client, chat).status_code == 502


def test_mail_requires_ai_consent_and_current_grant(
    client, owner, mailbox, monkeypatch
):
    conn = connect(client, "mail", {"mailbox_id": mailbox["id"]}, "")
    ai = connect(client)
    body = {"provider_id": ai["id"], "connection_ids": [conn["id"]], "consent": True}
    assert client.post("/api/work/chats", json=body).status_code == 403
    with SessionLocal() as db:
        db.get(Mailbox, mailbox["id"]).ai_enabled = True
        db.commit()
    chat = client.post("/api/work/chats", json=body).json()["id"]
    with SessionLocal() as db:
        db.execute(delete(Grant).where(Grant.mailbox_id == mailbox["id"]))
        db.commit()
    assert post_message(client, chat).status_code == 404
    assert client.get("/api/work/chats/" + chat).status_code == 404


def test_work_drafts_remain_approval_required(client, owner, mailbox, monkeypatch):
    with SessionLocal() as db:
        db.get(Mailbox, mailbox["id"]).ai_enabled = True
        db.commit()
    conn = connect(client, "mail", {"mailbox_id": mailbox["id"]}, "")
    chat = conversation(client, [conn])
    propose(
        monkeypatch,
        conn,
        "create_draft",
        {"to": "client@example.com", "title": "Hello", "body": "A reviewed reply"},
    )
    action = post_message(client, chat).json()["actions"][0]
    result = client.post("/api/work/actions/" + action["id"] + "/approve").json()
    assert result["status"] == "completed"
    with SessionLocal() as db:
        draft = db.scalar(select(Draft))
        assert (
            draft.ai_generated and draft.status == "draft" and not draft.approved_hash
        )


def test_invalid_url_and_arbitrary_arguments_denied():
    with pytest.raises(HTTPException):
        validated(
            "clickup",
            "create_task",
            {"title": "X", "body": "Y", "url": "http://localhost"},
        )
    with pytest.raises(HTTPException):
        validated("mail", "send", {})
    with pytest.raises(HTTPException):
        validated(
            "instagram",
            "publish_image",
            {"body": "Hi", "image_url": "https://127.0.0.1/a.jpg"},
        )


def test_sample_mode_blocks_live_connections(client, owner, monkeypatch):
    monkeypatch.setattr(config, "DEMO", True)
    assert (
        client.post(
            "/api/work/connections",
            json={
                "provider": "openai",
                "name": "Demo",
                "token": "fake",
                "settings": {"model": "model"},
            },
        ).status_code
        == 409
    )
    assert client.post("/api/work/codex/login").status_code == 409


def test_work_catalog_exposes_integration_setup_state(client, owner, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "microsoft-secret")
    catalog = client.get("/api/work/catalog").json()
    assert catalog["gmail_oauth_configured"] is True
    assert catalog["google_oauth_configured"] is True
    assert catalog["microsoft_oauth_configured"] is True
    assert catalog["mail_oauth_callback"] == "http://testserver/api/oauth/callback"
    assert (
        catalog["work_oauth_callback"]
        == "http://testserver/api/work/oauth/callback"
    )


def test_codex_requires_operator_bridge(client, owner, monkeypatch):
    monkeypatch.delenv("CODEX_BRIDGE_URL", raising=False)
    assert client.post("/api/work/codex/status").status_code == 409


def test_google_callback_is_browser_bound(client, owner):
    assert (
        client.get("/api/work/oauth/callback?state=forged&code=fake").status_code == 400
    )


@pytest.mark.parametrize(
    "provider,response",
    [
        (
            "openai",
            {"output": [{"content": [{"type": "output_text", "text": "hello"}]}]},
        ),
        ("claude", {"content": [{"type": "text", "text": "hello"}]}),
        ("gemini", {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}),
        ("deepseek", {"choices": [{"message": {"content": "hello"}}]}),
    ],
)
def test_ai_provider_contracts(provider, response, monkeypatch):
    from backend import work_providers

    requests = []
    monkeypatch.setattr(
        work_providers,
        "call_json",
        lambda *a, **kw: requests.append((a, kw)) or response,
    )
    row = WorkConnection(
        provider=provider,
        secret=encrypt({"token": "private-test-key"}),
        settings=json.dumps({"model": "test-model"}),
    )
    assert work_providers.generate(row, "private request", "user") == "hello"
    assert "private-test-key" not in json.dumps(requests[0][1]["json"])
    assert requests[0][0][1].startswith("https://")
    if provider == "openai":
        assert requests[0][1]["json"]["store"] is False


def test_instagram_publishes_only_after_container(monkeypatch):
    from backend import work_tools

    calls = []
    monkeypatch.setattr(
        work_tools, "call_json", lambda *a, **kw: calls.append((a, kw)) or {"id": "123"}
    )
    row = WorkConnection(
        provider="instagram",
        secret=encrypt({"token": "test"}),
        settings=json.dumps({"account_id": "456"}),
    )
    execute(
        row,
        "publish_image",
        {"body": "Approved caption", "image_url": "https://example.com/photo.jpg"},
        None,
        None,
    )
    assert calls[0][0][1].endswith("/456/media")
    assert calls[1][1]["json"] == {"creation_id": "123"}
