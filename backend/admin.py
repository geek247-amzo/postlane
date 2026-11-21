"""Operator recovery via server console. Never pass passwords as command arguments."""

import argparse
import getpass
from sqlalchemy import select, delete, update
from .models import SessionLocal, User, LoginSession, TrustedDevice, ApiKey, Draft, audit
from .security import passwords


def main():
    parser = argparse.ArgumentParser(
        description="CloudMonkey Postlane account recovery"
    )
    parser.add_argument("email")
    parser.add_argument(
        "--disable-mfa",
        action="store_true",
        help="Explicitly reset MFA after verifying the account owner's identity",
    )
    args = parser.parse_args()
    password = getpass.getpass("New password (at least 14 characters): ")
    if len(password) < 14 or password != getpass.getpass("Confirm new password: "):
        raise SystemExit("Password too short or confirmation does not match")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if not user:
            raise SystemExit("User not found")
        user.password_hash = passwords.hash(password)
        if args.disable_mfa:
            user.totp_secret = user.totp_pending = ""
            user.totp_last_step = 0
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user.id))
        db.execute(update(ApiKey).where(ApiKey.user_id == user.id).values(revoked=True))
        db.execute(
            update(Draft)
            .where(Draft.user_id == user.id, Draft.status == "queued")
            .values(
                status="draft",
                scheduled_at=0,
                approved_hash="",
                version=Draft.version + 1,
            )
        )
        audit(db, "server-operator", "auth.recovered", user.id)
        db.commit()
    print(
        "Password updated; sessions and API keys revoked, queued sends cancelled. Re-enroll MFA if it was reset."
    )


if __name__ == "__main__":
    main()
