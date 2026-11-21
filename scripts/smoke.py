"""Read-only/sample-only container check. Never sends mail or configures providers."""

import json
import urllib.request
import http.cookiejar

base = "http://127.0.0.1:8000"
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)


def request(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        base + path, data=body, headers={"Content-Type": "application/json"}
    )
    with opener.open(req, timeout=10) as response:
        return json.load(response)


assert request("/api/ready")["status"] == "ready"
assert request("/api/auth/status")["demo"] is True, (
    "Smoke test only runs against a sample installation"
)
request("/api/auth/demo", {})
assert len(request("/api/mailboxes")) == 10
assert len(request("/api/domains")) == 3
assert request("/api/messages")["total"] > 0
with opener.open(base, timeout=10) as page:
    assert "CloudMonkey" in page.read().decode()
print(
    "Container smoke passed: health, sample login, 10 mailboxes, 3 domains, messages, branded frontend."
)
