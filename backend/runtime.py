"""Local process readiness; one worker per installation in this release."""

import json
import os
import time
from .config import DATA

HEARTBEAT = DATA / "worker-heartbeat.json"


def heartbeat():
    temporary = DATA / f"worker-heartbeat.{os.getpid()}.tmp"
    temporary.write_text(json.dumps({"at": int(time.time())}), encoding="utf-8")
    os.replace(temporary, HEARTBEAT)


def worker_status():
    try:
        age = max(0, int(time.time()) - json.loads(HEARTBEAT.read_text())["at"])
        return {"healthy": age < 180, "age_seconds": age}
    except (OSError, ValueError, KeyError):
        return {"healthy": False, "age_seconds": None}


if __name__ == "__main__":
    raise SystemExit(0 if worker_status()["healthy"] else 1)
