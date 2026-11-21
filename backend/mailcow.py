"""Small Mailcow API adapter used for hosted domain/mailbox provisioning."""

import httpx

from . import config
from .providers import ProviderError


def configured():
    return bool(config.MAILCOW_API_URL and config.MAILCOW_API_KEY)


def _call(method, path, payload=None):
    if not configured():
        raise ProviderError("Mailcow provisioning is not configured")
    if not config.MAILCOW_API_URL.startswith("https://"):
        raise ProviderError("Mailcow management requires a trusted HTTPS endpoint")
    try:
        with httpx.Client(
            timeout=30,
            trust_env=False,
            headers={"X-API-Key": config.MAILCOW_API_KEY},
        ) as client:
            response = client.request(
                method,
                config.MAILCOW_API_URL + path,
                json=payload,
            )
        if response.status_code == 401:
            raise ProviderError("Mailcow rejected its management API key")
        if not response.is_success:
            raise ProviderError(f"Mailcow returned HTTP {response.status_code}")
        result = response.json()
    except (httpx.HTTPError, ValueError) as ex:
        raise ProviderError("Could not reach the Mailcow management API") from ex
    rows = result if isinstance(result, list) else [result]
    failures = [row for row in rows if isinstance(row, dict) and row.get("type") in ("error", "danger")]
    if failures:
        messages = []
        for row in failures:
            value = row.get("msg", [])
            messages.extend(value if isinstance(value, list) else [value])
        raise ProviderError("Mailcow rejected the request" + (": " + ", ".join(messages) if messages else ""))
    return result


def _add_domain(domain):
    _call(
        "POST",
        "/api/v1/add/domain",
        {
            "active": True,
            "domain": domain,
            "description": "Managed by Postlane",
            "aliases": 400,
            "mailboxes": 100,
            "maxquota": 10240,
            "quota": 102400,
            "defquota": 3072,
            "backupmx": False,
            "relay_all_recipients": False,
            "relay_unknown_only": False,
            "restart_sogo": True,
        },
    )


def ensure_domains(domains):
    rows = _call("GET", "/api/v1/get/domain/all")
    existing = {
        str(row.get("domain_name", "")).lower()
        for row in rows
        if isinstance(row, dict)
    }
    for domain in {value.strip().lower() for value in domains if value.strip()}:
        if domain not in existing:
            _add_domain(domain)
            existing.add(domain)


def ensure_domain(domain):
    ensure_domains([domain])


def get_catchall(domain):
    rows = _call("GET", "/api/v1/get/alias/all")
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("domain", "")).lower() == domain.lower()
        and (
            row.get("is_catch_all") in (1, "1", True)
            or str(row.get("address", "")).lower() == "@" + domain.lower()
        )
    ]
    if not matches:
        return None
    row = matches[0]
    return {
        "id": str(row.get("id")),
        "address": row.get("address", "@" + domain),
        "destination": row.get("goto", ""),
        "active": row.get("active") in (1, "1", True),
    }


def set_catchall(domain, destination):
    current = get_catchall(domain)
    if current:
        _call(
            "POST",
            "/api/v1/edit/alias",
            {
                "items": [current["id"]],
                "attr": {
                    "active": True,
                    "address": "@" + domain,
                    "goto": destination,
                    "private_comment": "Managed by Postlane",
                },
            },
        )
    else:
        _call(
            "POST",
            "/api/v1/add/alias",
            {
                "active": True,
                "address": "@" + domain,
                "goto": destination,
                "private_comment": "Managed by Postlane",
            },
        )
    return get_catchall(domain)


def delete_catchall(domain):
    current = get_catchall(domain)
    if current:
        _call("POST", "/api/v1/delete/alias", [current["id"]])


def ensure_mailbox(email, name, password):
    rows = _call("GET", "/api/v1/get/mailbox/all")
    if any(str(row.get("username", "")).lower() == email.lower() for row in rows if isinstance(row, dict)):
        return
    local, domain = email.rsplit("@", 1)
    _call(
        "POST",
        "/api/v1/add/mailbox",
        {
            "active": True,
            "domain": domain,
            "local_part": local,
            "name": name,
            "authsource": "mailcow",
            "password": password,
            "password2": password,
            "quota": 3072,
            "force_pw_update": False,
            "force_tfa": False,
            "tls_enforce_in": True,
            "tls_enforce_out": True,
        },
    )


def delete_mailbox(email):
    rows = _call("GET", "/api/v1/get/mailbox/all")
    if not any(
        isinstance(row, dict) and str(row.get("username", "")).lower() == email.lower()
        for row in rows
    ):
        # Keep deletion idempotent when a previous partial provisioning failed.
        return
    # Mailcow's delete API expects the JSON request body itself to be an array.
    _call("POST", "/api/v1/delete/mailbox", [email])


def dkim(domain):
    result = _call("GET", "/api/v1/get/dkim/" + domain)
    return result if isinstance(result, dict) else {}
