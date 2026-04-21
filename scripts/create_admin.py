"""Create (or upgrade to admin) a user. Bootstraps the first admin when the
DB has no users yet — otherwise chicken-and-egg since /admin/users requires
admin login.

Admins manage all syllabi; they aren't enrolled in one. DO NOT pass --syllabus
unless you also want the admin to open to /notes of that syllabus on login
(the switcher in the topnav lets them browse any syllabus anyway).

Usage (run inside Railway so DATABASE_URL resolves):

    # Recommended — username + your own password, no syllabus
    railway run python -m scripts.create_admin admin \\
        --password 'YourPasswordHere'

    # Email-style login
    railway run python -m scripts.create_admin filo@menghi.dev \\
        --password 'YourPasswordHere'

    # Random auto-generated password (printed once)
    railway run python -m scripts.create_admin admin

If the email/username already exists, promotes the account to admin and
updates the password only if --password is passed (otherwise leaves it).
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from auth import hash_password  # noqa: E402
from extensions import db  # noqa: E402
from models import Syllabus, User  # noqa: E402


def run(email: str, syllabus_code: str | None, password: str | None) -> None:
    email = email.strip().lower()
    app = create_app()
    with app.app_context():
        syll = Syllabus.query.filter_by(code=syllabus_code).first() if syllabus_code else None
        if syllabus_code and syll is None:
            print(
                f"Warning: syllabus '{syllabus_code}' not found in DB. "
                "User will be created with no default syllabus."
            )

        existing = User.query.filter_by(email=email).first()

        if existing:
            existing.role = "admin"
            if syll:
                existing.syllabus_id = syll.id
            if password:
                existing.password_hash = hash_password(password)
                print(f"Upgraded {email} to admin; password updated.")
            else:
                print(f"Upgraded existing user {email} to admin (password unchanged).")
            db.session.commit()
            return

        chosen_password = password or secrets.token_urlsafe(16)
        user = User(
            email=email,
            password_hash=hash_password(chosen_password),
            role="admin",
            syllabus_id=syll.id if syll else None,
        )
        db.session.add(user)
        db.session.commit()

        print(f"\nCreated admin user:  {email}")
        if password:
            print("Password:            (the one you passed via --password)")
        else:
            print(f"Password:            {chosen_password}")
            print("                     COPY NOW — random, not shown again.")
        print("\nSign in at https://igcse.menghi.dev/login")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or promote an admin user.")
    parser.add_argument("email", help="Login identifier (email or username — any unique string)")
    parser.add_argument("--syllabus", "-s", default=None,
                        help="Default syllabus code (0580 or 0654). Optional.")
    parser.add_argument("--password", "-p", default=None,
                        help="Custom password. If omitted, a random 16-char password is generated.")
    args = parser.parse_args()
    run(args.email, args.syllabus, args.password)
