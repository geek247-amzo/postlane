"""Materialize private Compose secret files without printing their contents."""

import os
from pathlib import Path


def sync(root):
    values = {}
    for line in (root / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    directory = root / "secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise SystemExit("Refusing symlink secrets directory")
    os.chmod(directory, 0o700)
    mapping = {
        "database_password": "POSTGRES_PASSWORD",
        "encryption_key": "ENCRYPTION_KEY",
        "bootstrap_token": "BOOTSTRAP_TOKEN",
    }
    for filename, key in mapping.items():
        value = values.get(key, "")
        if not value or value.startswith("GENERATE_"):
            raise SystemExit(f"{key} must contain a generated installation secret")
        target = directory / filename
        if target.is_symlink():
            raise SystemExit("Refusing symlink secret file")
        if target.exists() and target.read_text(encoding="utf-8").strip() != value:
            raise SystemExit(
                f"{key} differs from the existing secret file. Follow the credential rotation runbook; refusing automatic replacement."
            )
    for filename, key in mapping.items():
        target = directory / filename
        if not target.exists():
            # Host access is restricted by the 0700 parent. Read access inside
            # the container is necessary for the unprivileged application UID.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(values[key])
            os.chmod(target, 0o644)
    # Compose mounts these optional files even when the integration is disabled.
    # Never generate an integration key or replace an existing credential here.
    for filename, key in {"mailcow_api_key": "MAILCOW_API_KEY", "push_vapid_private_key": "PUSH_VAPID_PRIVATE_KEY"}.items():
        target = directory / filename
        value = values.get(key, "")
        if target.is_symlink():
            raise SystemExit("Refusing symlink secret file")
        if target.exists():
            if value and target.read_text(encoding="utf-8").strip() != value:
                raise SystemExit(f"{key} differs from the existing secret file; use the credential rotation runbook")
            continue
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.chmod(target, 0o644)
    print(
        "Compose secret files prepared. Protect the secrets directory and include it in encrypted backups."
    )


if __name__ == "__main__":
    sync(Path(__file__).resolve().parent.parent)
