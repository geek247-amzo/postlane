import os
import tempfile
from pathlib import Path

_directory = tempfile.TemporaryDirectory(prefix="postlane-tests-")
test_database = os.getenv("POSTLANE_TEST_DATABASE_URL", "")
if test_database:
    from sqlalchemy.engine import make_url

    if make_url(test_database).database != "postlane_test":
        raise RuntimeError(
            "Integration tests require a disposable database named postlane_test"
        )
os.environ["DATABASE_URL"] = test_database or "sqlite:///" + str(
    Path(_directory.name) / "test.db"
)
os.environ["APP_ENV"] = "test"
os.environ["DEMO_MODE"] = "false"
os.environ["BOOTSTRAP_TOKEN"] = "test-installation-token"
os.environ["APP_URL"] = "http://testserver"

import pytest
from fastapi.testclient import TestClient
from backend.main import app, attempts
from backend.models import Base, engine, SessionLocal, Mailbox, Grant, Message, User


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _directory.cleanup()


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def owner(client):
    r = client.post(
        "/api/auth/setup",
        json={
            "name": "Owner",
            "email": "owner@example.com",
            "password": "long-test-password-123",
            "token": "test-installation-token",
        },
    )
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    return r.json()["user"]


@pytest.fixture
def mailbox(owner):
    with SessionLocal() as db:
        box = Mailbox(email="hello@example.com", name="Business", provider="imap")
        db.add(box)
        db.flush()
        db.add(
            Grant(user_id=owner["id"], mailbox_id=box.id, can_write=True, can_send=True)
        )
        msg = Message(
            mailbox_id=box.id,
            sender="Client <client@example.com>",
            recipients=box.email,
            subject="A private conversation",
            body="Confidential content",
        )
        db.add(msg)
        db.commit()
        return {"id": box.id, "message_id": msg.id}
