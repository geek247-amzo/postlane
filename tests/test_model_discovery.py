import pytest
from fastapi import HTTPException
from backend import work, work_providers
from backend.models import SessionLocal
from backend.work_models import WorkConnection
from sqlalchemy import select


def test_discovery_authenticated_csrf_and_no_storage(client, owner, monkeypatch):
    calls = []

    def discover(provider, token):
        calls.append((provider, token))
        return [{"id": "example-chat", "name": "Example"}]

    monkeypatch.setattr(work, "list_models", discover)
    response = client.post(
        "/api/work/provider-models",
        json={"provider": "openai", "token": "fixture-secret"},
    )
    assert response.status_code == 200
    assert response.json()["models"][0]["id"] == "example-chat"
    assert "fixture-secret" not in response.text
    assert calls == [("openai", "fixture-secret")]
    with SessionLocal() as db:
        assert db.scalar(select(WorkConnection)) is None
    client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            "/api/work/provider-models",
            json={"provider": "openai", "token": "fixture-secret"},
        ).status_code
        == 403
    )
    assert len(calls) == 1


def test_discovery_rejects_invalid_provider_and_failure(client, owner, monkeypatch):
    def fail(*args):
        raise HTTPException(
            502, "Provider returned HTTP 401; check credentials, access and limits"
        )

    monkeypatch.setattr(work, "list_models", fail)
    assert (
        client.post(
            "/api/work/provider-models",
            json={"provider": "http://127.0.0.1", "token": "fixture-secret"},
        ).status_code
        == 422
    )
    response = client.post(
        "/api/work/provider-models",
        json={"provider": "openai", "token": "fixture-secret"},
    )
    assert response.status_code == 502
    assert "fixture-secret" not in response.text


@pytest.mark.parametrize(
    "provider,host,header",
    [
        ("openai", "https://api.openai.com/v1/models", "Authorization"),
        ("deepseek", "https://api.deepseek.com/models", "Authorization"),
        ("claude", "https://api.anthropic.com/v1/models", "x-api-key"),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/models",
            "x-goog-api-key",
        ),
    ],
)
def test_fixed_origin_and_normalized_models(monkeypatch, provider, host, header):
    def call(method, url, **kwargs):
        assert method == "GET" and url == host
        assert "fixture-key" in kwargs["headers"][header]
        assert "fixture-key" not in url
        if provider == "gemini":
            return {
                "models": [
                    {
                        "name": "models/gemini-test",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embed-test",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                    {"name": None},
                ]
            }
        return {
            "data": [
                {"id": "gpt-test"},
                {"id": "gpt-image-test"},
                {"id": "../bad"},
                {"id": None},
            ]
        }

    monkeypatch.setattr(work_providers, "call_json", call)
    models = work_providers.list_models(provider, "fixture-key")
    assert any(
        m["id"] == ("gemini-test" if provider == "gemini" else "gpt-test")
        for m in models
    )
    assert all(m["id"] != "../bad" for m in models)
    if provider == "openai":
        assert all("image" not in m["id"] for m in models)


def test_model_pagination_and_empty_response(monkeypatch):
    calls = []

    def call(method, url, **kwargs):
        calls.append(kwargs["params"])
        if len(calls) == 1:
            return {
                "models": [
                    {
                        "name": "models/first",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ],
                "nextPageToken": "next",
            }
        return {
            "models": [
                {
                    "name": "models/second",
                    "supportedGenerationMethods": ["generateContent"],
                }
            ]
        }

    monkeypatch.setattr(work_providers, "call_json", call)
    assert [m["id"] for m in work_providers.list_models("gemini", "fixture-key")] == [
        "first",
        "second",
    ]
    assert calls[1]["pageToken"] == "next"
    monkeypatch.setattr(work_providers, "call_json", lambda *a, **kw: {"data": []})
    with pytest.raises(HTTPException) as error:
        work_providers.list_models("openai", "fixture-key")
    assert error.value.status_code == 422
