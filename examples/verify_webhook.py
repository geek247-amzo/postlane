"""Receiver-side reference: verify the original request bytes BEFORE parsing JSON."""

import hashlib
import hmac
import json
import time


def verify_event(raw_body: bytes, timestamp: str, signature: str, secret: str) -> dict:
    if len(raw_body) > 65536:
        raise ValueError("Event exceeds payload limit")
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("Invalid event timestamp")
    if abs(time.time() - sent_at) > 300:
        raise ValueError("Expired event")
    expected = (
        "sha256="
        + hmac.new(
            secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256
        ).hexdigest()
    )
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid signature")
    event = json.loads(raw_body)
    if event.get("version") != 1 or not event.get("id"):
        raise ValueError("Unsupported event envelope")
    return event


# Store event['id'] in a durable table with a UNIQUE constraint before acting.
# Repeated event IDs must not re-run side effects. Do not log raw_body or secret.
