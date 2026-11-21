"""Fixed-origin AI adapters. Keys never enter prompts, responses or logs."""

import json
import re
import httpx
from fastapi import HTTPException
from .security import decrypt
from . import config

AI_PROVIDERS = {"openai", "gemini", "claude", "deepseek", "codex", "hermes"}


def call_text(url, headers):
    try:
        with httpx.Client(
            timeout=30, trust_env=False, follow_redirects=False
        ) as client:
            with client.stream("GET", url, headers=headers) as response:
                if not response.is_success:
                    raise HTTPException(
                        502, f"Provider returned HTTP {response.status_code}"
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 200_000:
                        raise HTTPException(
                            502, "Document exceeds the text reading limit"
                        )
                return data.decode("utf-8", errors="replace")[:20000]
    except httpx.HTTPError:
        raise HTTPException(502, "Document could not be read") from None


def call_json(method, url, *, headers=None, **kwargs):
    try:
        with httpx.Client(
            timeout=90, trust_env=False, follow_redirects=False
        ) as client:
            with client.stream(method, url, headers=headers, **kwargs) as response:
                if not response.is_success:
                    raise HTTPException(
                        502,
                        f"Provider returned HTTP {response.status_code}; check credentials, access and limits",
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise HTTPException(
                            502, "Provider response exceeded the size limit"
                        )
                return (
                    json.loads(data)
                    if data
                    else {"id": response.headers.get("x-restli-id", ""), "ok": True}
                )
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            502, "Provider request failed; check connection and provider availability"
        ) from None


KEY_PROVIDERS = {"openai", "gemini", "claude", "deepseek"}


def list_models(provider, token):
    """Validate credentials against fixed provider origins without a generation call."""
    if (
        provider not in KEY_PROVIDERS
        or not token.strip()
        or any(ord(c) < 33 or ord(c) > 126 for c in token.strip())
    ):
        raise HTTPException(422, "Enter a valid provider API key")
    urls = {
        "openai": "https://api.openai.com/v1/models",
        "claude": "https://api.anthropic.com/v1/models",
        "deepseek": "https://api.deepseek.com/models",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    }
    headers = {"Authorization": "Bearer " + token.strip()}
    if provider == "claude":
        headers = {"x-api-key": token.strip(), "anthropic-version": "2023-06-01"}
    elif provider == "gemini":
        headers = {"x-goog-api-key": token.strip()}
    models = {}
    params = (
        {"limit": 100}
        if provider == "claude"
        else {"pageSize": 100}
        if provider == "gemini"
        else {}
    )
    for _ in range(10):
        data = call_json("GET", urls[provider], headers=headers, params=params)
        if not isinstance(data, dict):
            raise HTTPException(502, "Provider returned an invalid model list")
        items = data.get("models" if provider == "gemini" else "data")
        if not isinstance(items, list):
            raise HTTPException(502, "Provider returned an invalid model list")
        for item in items:
            if not isinstance(item, dict):
                continue
            if provider == "gemini" and "generateContent" not in item.get(
                "supportedGenerationMethods", []
            ):
                continue
            raw_model = (
                item.get("name", "") if provider == "gemini" else item.get("id", "")
            )
            model = (
                raw_model.removeprefix("models/")
                if provider == "gemini" and isinstance(raw_model, str)
                else raw_model
            )
            if not isinstance(model, str) or not re.fullmatch(
                r"[A-Za-z0-9._:-]{1,120}", model
            ):
                continue
            # The Work adapters generate text; exclude known non-chat OpenAI families.
            if provider == "openai" and (
                not model.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4"))
                or any(
                    x in model
                    for x in (
                        "image",
                        "audio",
                        "realtime",
                        "transcribe",
                        "tts",
                        "search",
                        "instruct",
                    )
                )
            ):
                continue
            label = item.get("displayName") or item.get("display_name") or model
            models[model] = {"id": model, "name": str(label)[:160]}
        if provider == "gemini" and data.get("nextPageToken"):
            cursor = data["nextPageToken"]
            if not isinstance(cursor, str) or len(cursor) > 2000:
                raise HTTPException(502, "Provider returned invalid pagination")
            params = {"pageSize": 100, "pageToken": cursor}
        elif provider == "claude" and data.get("has_more"):
            cursor = data.get("last_id")
            if not isinstance(cursor, str) or not re.fullmatch(
                r"[A-Za-z0-9._:-]{1,120}", cursor
            ):
                raise HTTPException(502, "Provider returned invalid pagination")
            params = {"limit": 100, "after_id": cursor}
        else:
            break
    else:
        raise HTTPException(502, "Provider model list exceeded the page limit")
    if not models:
        raise HTTPException(
            422, "The key was accepted but no compatible text models are available"
        )
    return sorted(models.values(), key=lambda item: item["id"])


def generate(connection, prompt, user_id):
    settings = json.loads(connection.settings)
    if connection.provider == "hermes":
        from .hermes_webhook import request

        return request(
            settings["url"],
            prompt,
            decrypt(connection.secret).get("token", ""),
            user_id,
        )
    model = settings.get("model", "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", model):
        raise HTTPException(
            422, "Enter a valid model ID available to your provider account"
        )
    key = decrypt(connection.secret).get("token", "")
    if connection.provider == "codex":
        from .work_codex import bridge

        return bridge(user_id, "chat", {"prompt": prompt, "model": model})["text"]
    headers = {"Authorization": "Bearer " + key}
    if connection.provider == "openai":
        result = call_json(
            "POST",
            "https://api.openai.com/v1/responses",
            headers=headers,
            json={
                "model": model,
                "input": prompt,
                "store": False,
                "max_output_tokens": 4096,
            },
        )
        return "\n".join(
            c.get("text", "")
            for item in result.get("output", [])
            for c in item.get("content", [])
            if c.get("type") == "output_text"
        )
    if connection.provider == "claude":
        result = call_json(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return "\n".join(
            c.get("text", "")
            for c in result.get("content", [])
            if c.get("type") == "text"
        )
    if connection.provider == "gemini":
        result = call_json(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 4096,
                    "responseMimeType": "application/json",
                },
            },
        )
        return "\n".join(
            p.get("text", "")
            for c in result.get("candidates", [])[:1]
            for p in c.get("content", {}).get("parts", [])
            if not p.get("thought")
        )
    if connection.provider == "deepseek":
        result = call_json(
            "POST",
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
            },
        )
        return result["choices"][0]["message"]["content"]
    raise HTTPException(422, "Unsupported AI provider")
