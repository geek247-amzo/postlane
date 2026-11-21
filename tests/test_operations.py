import pyotp

from backend import config
from backend.models import SessionLocal, User
from backend.security import encrypt, passwords


def test_readiness(client):
    assert client.get("/api/ready").status_code == 200


def test_installation_requires_admin(client, owner):
    status = client.get("/api/installation")
    assert status.status_code == 200
    assert status.json()["created_by"] == "CloudMonkey"
    assert "ENCRYPTION_KEY" not in status.text
    with SessionLocal() as db:
        db.get(User, owner["id"]).role = "member"
        db.commit()
    assert client.get("/api/installation").status_code == 403


def test_password_change_checks_current_password(client, owner):
    data = {"current_password": "wrong", "new_password": "new-long-password-123"}
    assert client.post("/api/auth/password", json=data).status_code == 403
    data["current_password"] = "long-test-password-123"
    assert client.post("/api/auth/password", json=data).status_code == 200
    with SessionLocal() as db:
        assert passwords.verify(
            db.get(User, owner["id"]).password_hash, data["new_password"]
        )


def test_cannot_disable_self(client, owner):
    assert (
        client.patch("/api/users/" + owner["id"], json={"active": False}).status_code
        == 409
    )


def test_mfa_setup_indicator(client, owner, monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", True)
    assert client.get("/api/auth/me").json()["mfa_required"] is True
    assert client.get("/api/installation").status_code == 403
    assert client.post("/api/auth/mfa/setup").status_code == 200


def test_mfa_can_be_disconnected_with_password_and_code(client, owner):
    secret = pyotp.random_base32()
    with SessionLocal() as db:
        db.get(User, owner["id"]).totp_secret = encrypt({"secret": secret})
        db.commit()

    response = client.post(
        "/api/auth/mfa/disable",
        json={
            "current_password": "long-test-password-123",
            "code": pyotp.TOTP(secret).now(),
        },
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(User, owner["id"]).totp_secret == ""


def test_oversized_body_without_length(client):
    assert (
        client.post("/api/auth/login", content=iter([b"x" * 1_100_000])).status_code
        == 413
    )


def test_secret_file(monkeypatch, tmp_path):
    path = tmp_path / "secret"
    path.write_text("file-value\n")
    monkeypatch.setenv("EXAMPLE_SECRET", "environment-value")
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(path))
    assert config.secret_value("EXAMPLE_SECRET") == "file-value"
