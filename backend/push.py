"""Browser push notifications with VAPID."""

import json
import logging
from . import config

log = logging.getLogger("postlane.push")


def configured():
    return bool(
        config.PUSH_VAPID_PUBLIC_KEY
        and config.PUSH_VAPID_PRIVATE_KEY
        and config.PUSH_VAPID_SUBJECT
    )


def send(subscription, title, body, url="/"):
    if not configured():
        return True
    try:
        from pywebpush import webpush

        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=config.PUSH_VAPID_PRIVATE_KEY,
            vapid_claims={"sub": config.PUSH_VAPID_SUBJECT},
        )
        return True
    except Exception as ex:
        response = getattr(ex, "response", None)
        if response is not None and getattr(response, "status_code", 0) in (404, 410):
            return False
        log.warning("Push delivery failed: %s", type(ex).__name__)
        return True
