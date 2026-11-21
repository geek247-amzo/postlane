"""Operator-allowlisted Hermes assistant adapter with pinned TLS and bounded replies."""
import hashlib
import hmac
import http.client
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit
from fastapi import HTTPException
from .events import validate_webhook
from .models import now, uid, SessionLocal, HermesAllowedOrigin, User


def endpoint_origin(url):
    if not isinstance(url, str) or len(url) > 2000:
        raise HTTPException(422, 'Hermes endpoint is too long')
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or len(parts.hostname) > 253 or len(parts.netloc) > 512 or any(ord(c) < 33 or ord(c) == 127 for c in url) or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Invalid endpoint')
        _ = parts.port
        return 'https://' + parts.netloc
    except (ValueError, TypeError):
        raise HTTPException(422, 'Use an HTTPS endpoint without URL credentials, query strings or fragments') from None


def validate_endpoint(url, approved_origin=None):
    origin = endpoint_origin(url)
    try:
        return validate_webhook(url)
    except ValueError:
        pass
    if origin != approved_origin:
        with SessionLocal() as db:
            row = db.get(HermesAllowedOrigin, origin)
            owner = db.get(User, row.approved_by) if row else None
            if not row or not row.active or not owner or not owner.active or owner.role != 'admin':
                raise HTTPException(422, 'Ask a workspace administrator to approve this exact Hermes HTTPS origin in Hermes settings')
    return urlsplit(url)


def request(url, prompt, secret, user_id):
    parts = validate_endpoint(url)
    port = parts.port or 443
    body = json.dumps({'version': 1, 'type': 'postlane.assistant.request', 'request_id': uid(), 'user_id': user_id, 'prompt': prompt}, separators=(',', ':')).encode()
    if len(body) > 300_000:
        raise HTTPException(422, 'Hermes request exceeds the context limit')
    stamp = str(now())
    signature = hmac.new(secret.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    from os import getenv
    private = f'https://{parts.netloc}' in getenv('WEBHOOK_PRIVATE_ORIGINS', '').split(',')
    conn = None
    sock = None
    try:
        addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError('No destination')
        for a in addresses:
            ip = ipaddress.ip_address(a[4][0])
            if ip.is_link_local or ip.is_multicast or ip.is_unspecified or (not private and not ip.is_global):
                raise ValueError('Destination rejected')
        sock = socket.create_connection((addresses[0][4][0], port), timeout=10)
        sock.settimeout(120)
        tls_context = ssl.create_default_context()
        ca_file = getenv('POSTLANE_JEFF_CA_FILE', '')
        if ca_file:
            tls_context.load_verify_locations(cafile=ca_file)
        sock = tls_context.wrap_socket(sock, server_hostname=parts.hostname)
        conn = http.client.HTTPConnection(parts.hostname, port, timeout=30)
        conn.sock = sock
        conn.request('POST', parts.path or '/', body, {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + secret, 'X-Postlane-Timestamp': stamp, 'X-Postlane-Signature': 'sha256=' + signature, 'Idempotency-Key': json.loads(body)['request_id']})
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise HTTPException(502, f'Hermes returned HTTP {response.status}; check endpoint authorization and availability')
        raw = response.read(200_001)
        if len(raw) > 200_000:
            raise ValueError('Reply too large')
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get('reply'), str):
            raise ValueError('Reply contract')
        # The caller validates the existing AgentReply action schema and applies
        # the same ownership, connection and human-approval boundaries as other AI.
        return json.dumps(result)
    except HTTPException:
        raise
    except (OSError, ValueError, http.client.HTTPException):
        raise HTTPException(502, 'Hermes could not return a valid bounded assistant reply; check the configured endpoint') from None
    finally:
        if conn:
            conn.close()
        elif sock:
            sock.close()
