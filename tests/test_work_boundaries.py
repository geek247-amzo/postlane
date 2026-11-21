import json
from fastapi.testclient import TestClient
from backend.models import SessionLocal, ApiKey, now
from backend.security import digest
from codex_bridge import server


def test_automation_keys_cannot_use_work(client, owner, mailbox):
    token = "fake-scoped-key"
    with SessionLocal() as db:
        db.add(
            ApiKey(
                user_id=owner["id"],
                name="Automation",
                prefix="fake-test",
                token_hash=digest(token),
                scopes=json.dumps(["messages:read"]),
                mailbox_ids=json.dumps([mailbox["id"]]),
                expires=now() + 3600,
            )
        )
        db.commit()
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/work/connections", headers=headers).status_code == 403
    assert client.post("/api/work/codex/login", headers=headers).status_code == 403


def test_bridge_requires_secret_and_valid_identity(monkeypatch, tmp_path):
    path = tmp_path / "secret"
    path.write_text("test-bridge-secret")
    monkeypatch.setenv("CODEX_BRIDGE_TOKEN_FILE", str(path))
    client = TestClient(server.app)
    assert client.post("/status", json={"user_id": "a" * 32}).status_code == 401
    assert (
        client.post(
            "/status",
            headers={"Authorization": "Bearer test-bridge-secret"},
            json={"user_id": "../../someone"},
        ).status_code
        == 422
    )


def test_bridge_status_never_returns_credentials(monkeypatch, tmp_path):
    path = tmp_path / "secret"
    path.write_text("test-bridge-secret")
    monkeypatch.setenv("CODEX_BRIDGE_TOKEN_FILE", str(path))
    import threading

    seen = []

    class Fake:
        lock = threading.Lock()

        def rpc(self, method, params):
            return {
                "account": {
                    "type": "chatgpt",
                    "email": "owner@example.com",
                    "planType": "test",
                    "accessToken": "must-not-return",
                }
            }

    monkeypatch.setattr(
        server, "session", lambda user_id: seen.append(user_id) or Fake()
    )
    client = TestClient(server.app)
    r = client.post(
        "/status",
        headers={"Authorization": "Bearer test-bridge-secret"},
        json={"user_id": "a" * 32},
    )
    assert r.status_code == 200 and r.json()["signed_in"]
    assert seen == ["a" * 32]
    assert "must-not-return" not in r.text


def test_google_scope_and_pkce(client, owner, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    c = client.post(
        "/api/work/connections",
        json={"name": "Drive", "provider": "drive", "settings": {}},
    ).json()
    r = client.post("/api/work/connections/" + c["id"] + "/google")
    from urllib.parse import urlsplit, parse_qs

    query = parse_qs(urlsplit(r.json()["url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://testserver/api/work/oauth/callback"]
    assert "drive.readonly" in query["scope"][0]
    assert "test-client-secret" not in r.text
