"""Narrow Stalwart v0.16 management adapter. No arbitrary JMAP proxy."""

import os
from urllib.parse import urlsplit
import httpx
from . import config
from .providers import ProviderError


def call(method, args):
    url = os.getenv("STALWART_API_URL", "").rstrip("/")
    token = config.secret_value("STALWART_API_TOKEN")
    if not url or not token:
        raise ProviderError(
            "Configure STALWART_API_URL and its restricted API token to manage aliases"
        )
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ProviderError("Stalwart management requires a trusted HTTPS endpoint")
    try:
        with httpx.Client(timeout=25, trust_env=False) as client:
            r = client.post(
                url,
                headers={"Authorization": "Bearer " + token},
                json={
                    "using": ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"],
                    "methodCalls": [[method, args, "call"]],
                },
            )
        if not r.is_success:
            raise ProviderError(f"Stalwart returned HTTP {r.status_code}")
        name, result, _ = r.json()["methodResponses"][0]
        if name == "error" or any(
            result.get(k) for k in ("notCreated", "notUpdated", "notDestroyed")
        ):
            raise ProviderError(
                "Stalwart rejected the operation. Check permissions or a conflicting address."
            )
        return result
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as ex:
        raise ProviderError(
            "Could not complete the Stalwart management request"
        ) from ex


def find_domain(name):
    result = call("x:Domain/query", {"filter": {"name": name}, "limit": 20})
    rows = call(
        "x:Domain/get", {"ids": result.get("ids", []), "properties": ["id", "name"]}
    ).get("list", [])
    matches = [d for d in rows if d.get("name", "").lower() == name.lower()]
    if len(matches) != 1:
        raise ProviderError(
            "Create this domain in Stalwart before managing its aliases"
        )
    return matches[0]["id"]


def find_account(address):
    local, domain = address.rsplit("@", 1)
    domain_id = find_domain(domain)
    result = call(
        "x:Account/query",
        {"filter": {"name": local, "domainId": domain_id}, "limit": 20},
    )
    fetched = call(
        "x:Account/get",
        {
            "ids": result.get("ids", []),
            "properties": ["id", "name", "domainId", "emailAddress", "aliases"],
        },
    )
    matches = [
        a
        for a in fetched.get("list", [])
        if a.get("name") == local and a.get("domainId") == domain_id
    ]
    if len(matches) != 1:
        raise ProviderError("Hosted account not found in Stalwart")
    return matches[0], fetched.get("state")


def aliases(address):
    account, _ = find_account(address)
    raw = account.get("aliases", {})
    entries = (
        list(raw.items())
        if isinstance(raw, dict)
        else [(str(i), v) for i, v in enumerate(raw)]
    )
    domain_ids = list({v["domainId"] for _, v in entries})
    domains = (
        call("x:Domain/get", {"ids": domain_ids, "properties": ["id", "name"]}).get(
            "list", []
        )
        if domain_ids
        else []
    )
    names = {d["id"]: d["name"] for d in domains}
    return [
        {
            "id": key,
            "email": v["name"] + "@" + names.get(v["domainId"], "unknown"),
            "enabled": v.get("enabled", True),
        }
        for key, v in entries
    ]


def add_alias(address, alias):
    account, state = find_account(address)
    raw = account.get("aliases", {})
    if not isinstance(raw, dict):
        raise ProviderError("Unsupported alias representation from the mail server")
    local, domain = alias.rsplit("@", 1)
    domain_id = find_domain(domain)
    if any(
        v.get("name") == local and v.get("domainId") == domain_id for v in raw.values()
    ):
        raise ProviderError("This alias already exists")
    from .models import uid

    raw[uid()] = {
        "name": local,
        "domainId": domain_id,
        "enabled": True,
        "description": "Managed by Postlane",
    }
    args = {"update": {account["id"]: {"aliases": raw}}}
    if state:
        args["ifInState"] = state
    result = call("x:Account/set", args)
    if account["id"] not in result.get("updated", {}):
        raise ProviderError("Mail server did not confirm the alias update")


def remove_alias(address, alias_id):
    account, state = find_account(address)
    raw = account.get("aliases", {})
    if not isinstance(raw, dict) or alias_id not in raw:
        raise ProviderError("Alias not found")
    del raw[alias_id]
    args = {"update": {account["id"]: {"aliases": raw}}}
    if state:
        args["ifInState"] = state
    result = call("x:Account/set", args)
    if account["id"] not in result.get("updated", {}):
        raise ProviderError("Mail server did not confirm the alias removal")
