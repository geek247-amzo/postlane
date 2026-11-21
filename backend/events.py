import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import socket
import ssl
from urllib.parse import urlsplit
from sqlalchemy import select
from .models import Webhook, Delivery, now, uid


def emit(db, event, mailbox_id, resource_id):
    payload = json.dumps(
        {
            "id": uid(),
            "version": 1,
            "event": event,
            "timestamp": now(),
            "mailbox_id": mailbox_id,
            "resource_id": resource_id,
        },
        separators=(",", ":"),
    )
    for hook in db.scalars(
        select(Webhook).where(Webhook.mailbox_id == mailbox_id, Webhook.active == True)
    ):
        db.add(Delivery(webhook_id=hook.id, payload=payload))


def validate_webhook(url):
    parts = urlsplit(url)
    allowed = {
        s.strip()
        for s in os.getenv("WEBHOOK_ALLOWED_ORIGINS", "").split(",")
        if s.strip()
    }
    origin = f"{parts.scheme}://{parts.netloc}"
    if (
        parts.scheme not in ("https", "http")
        or parts.username
        or parts.password
        or parts.fragment
        or origin not in allowed
    ):
        raise ValueError(
            "Webhook origin must be explicitly approved in WEBHOOK_ALLOWED_ORIGINS"
        )
    if parts.scheme != "https" and origin not in os.getenv(
        "WEBHOOK_PRIVATE_ORIGINS", ""
    ).split(","):
        raise ValueError("Public webhooks require HTTPS")
    return parts


def post_webhook(url, body, secret):
    parts = validate_webhook(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    private = f"{parts.scheme}://{parts.netloc}" in os.getenv(
        "WEBHOOK_PRIVATE_ORIGINS", ""
    ).split(",")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or (not private and not ip.is_global)
        ):
            raise ValueError("Webhook destination is not an allowed address")
    # Pin the checked address for this connection, including TLS hostname verification.
    address = addresses[0][4][0]
    conn = http.client.HTTPConnection(parts.hostname, port, timeout=15)
    sock = socket.create_connection((address, port), timeout=15)
    if parts.scheme == "https":
        sock = ssl.create_default_context().wrap_socket(
            sock, server_hostname=parts.hostname
        )
    conn.sock = sock
    timestamp = str(now())
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    try:
        conn.request(
            "POST",
            (parts.path or "/") + ("?" + parts.query if parts.query else ""),
            body,
            {
                "Content-Type": "application/json",
                "X-Postlane-Timestamp": timestamp,
                "X-Postlane-Signature": "sha256=" + signature,
            },
        )
        result = conn.getresponse()
        return result.status
    finally:
        conn.close()
