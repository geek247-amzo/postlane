import os
from pathlib import Path
from urllib.parse import urlsplit, quote
from dotenv import load_dotenv

load_dotenv()


def secret_value(name, default=""):
    """Support Docker secrets without exposing their values through container env."""
    secret_file = os.getenv(name + "_FILE")
    if secret_file:
        return Path(secret_file).read_text(encoding="utf-8").strip()
    return os.getenv(name, default)


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA / 'postlane.db'}")
if os.getenv("DATABASE_HOST") and not os.getenv("DATABASE_URL"):
    database_password = secret_value("DATABASE_PASSWORD")
    if not database_password:
        raise RuntimeError("DATABASE_PASSWORD or DATABASE_PASSWORD_FILE is required")
    DATABASE_URL = (
        "postgresql+psycopg://postlane:"
        + quote(database_password, safe="")
        + "@"
        + os.environ["DATABASE_HOST"]
        + ":5432/postlane"
    )
PRODUCTION = os.getenv("APP_ENV") == "production"
DEMO = os.getenv("DEMO_MODE", "false").lower() == "true"
ORIGIN = os.getenv("APP_URL", "http://127.0.0.1:5173").rstrip("/")
MAIL_HOST = os.getenv("MAIL_HOST", "").strip()
MAILCOW_API_URL = os.getenv("MAILCOW_API_URL", "").rstrip("/")
MAILCOW_API_KEY = secret_value("MAILCOW_API_KEY")
MAIL_SPF_VALUE = os.getenv("MAIL_SPF_VALUE", "").strip()
PUSH_VAPID_PUBLIC_KEY = os.getenv("PUSH_VAPID_PUBLIC_KEY", "").strip()
PUSH_VAPID_PRIVATE_KEY = secret_value("PUSH_VAPID_PRIVATE_KEY")
PUSH_VAPID_SUBJECT = os.getenv("PUSH_VAPID_SUBJECT", "mailto:postmaster@example.com").strip()
ENCRYPTION_KEY = secret_value("ENCRYPTION_KEY")
BOOTSTRAP_TOKEN = secret_value("BOOTSTRAP_TOKEN")
if PRODUCTION and (DEMO or not ORIGIN.startswith("https://") or not ENCRYPTION_KEY):
    raise RuntimeError("Production requires HTTPS, ENCRYPTION_KEY, and DEMO_MODE=false")
if PRODUCTION and not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        "Production requires PostgreSQL; sample SQLite databases must not be deployed"
    )
if (
    urlsplit(ORIGIN).path
    or urlsplit(ORIGIN).query
    or urlsplit(ORIGIN).fragment
    or urlsplit(ORIGIN).username
):
    raise RuntimeError(
        "APP_URL must be an origin: scheme, hostname, and optional port only"
    )
if not ENCRYPTION_KEY:
    from cryptography.fernet import Fernet

    key_path = DATA / "development.key"
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
    ENCRYPTION_KEY = key_path.read_text().strip()
