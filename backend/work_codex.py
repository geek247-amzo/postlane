"""Only the operator-configured private Codex bridge may receive account requests."""

import os
from fastapi import HTTPException
from .config import secret_value
from .work_providers import call_json


def bridge(user_id, operation, payload):
    url = os.getenv("CODEX_BRIDGE_URL", "")
    token = secret_value("CODEX_BRIDGE_TOKEN")
    if url != "http://codex-bridge:8090" or not token:
        raise HTTPException(
            409, "The operator must enable the private Codex bridge first"
        )
    return call_json(
        "POST",
        url + "/" + operation,
        headers={"Authorization": "Bearer " + token},
        json={"user_id": user_id, **payload},
    )
