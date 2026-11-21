"""Generate installation-specific secrets. Existing configuration is never overwritten."""

import argparse
import base64
import os
import re
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="inbox.example.com")
parser.add_argument("--mail-host", default="mail.example.com")
parser.add_argument("--demo", action="store_true")
args = parser.parse_args()
for host in (args.host, args.mail_host):
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        parser.error("Hostnames may only contain letters, numbers, dots, and hyphens")
root = Path(__file__).resolve().parent.parent
output = root / ".env"
if output.exists():
    raise SystemExit(
        ".env already exists; edit it directly. Existing secrets were preserved."
    )
content = (
    (root / ".env.example")
    .read_text()
    .replace("inbox.example.com", args.host)
    .replace("mail.example.com", args.mail_host)
)
for placeholder, value in [
    ("GENERATE_POSTGRES_PASSWORD", secrets.token_hex(32)),
    (
        "GENERATE_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    ),
    ("GENERATE_BOOTSTRAP_TOKEN", secrets.token_urlsafe(40)),
]:
    content = content.replace(placeholder, value)
if args.demo:
    content = (
        content.replace("APP_ENV=production", "APP_ENV=development")
        .replace("DEMO_MODE=false", "DEMO_MODE=true")
        .replace("APP_URL=https://" + args.host, "APP_URL=http://127.0.0.1:5173")
    )
fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(content)
from sync_secrets import sync

sync(root)
print(
    "Created .env with unique installation secrets. Keep this file private and include it in encrypted backups."
)
if not args.demo:
    print(
        "Use BOOTSTRAP_TOKEN from .env on the first-run setup page. Configure DNS and TLS before connecting mail."
    )
