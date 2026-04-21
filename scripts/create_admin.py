"""Create (or upgrade to admin) a user. Used to bootstrap the first admin when
the DB has no users yet, which is otherwise a chicken-and-egg problem since
/admin/users requires admin login.

Usage (run inside Railway so DATABASE_URL resolves):
    railway run python -m scripts.create_admin <email>

On success prints the generated password ONCE — copy it immediately.
If the email already exists, promotes the account to admin (password unchanged).
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from auth import hash_password  # noqa: E402
from extensions import db  # noqa: E402
from models import Syllabus, User  # noqa: E402


def run(email: str, syllabus_code: str | None = None) -> None:
    app = create_app()
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.role = "admin"
            db.session.commit()
            print(f"Upgraded existing user {email} to role=admin.")
            print("(Password unchanged — use their existing password to log in.)")
            return

        password = secrets.token_urlsafe(16)
        syll = Syllabus.query.filter_by(code=syllabus_code).first() if syllabus_code else None
        user = User(
            email=email.strip().lower(),
            password_hash=hash_password(password),
            role="admin",
            syllabus_id=syll.id if syll else None,
        )
        db.session.add(user)
        db.session.commit()
        print(f"\nCreated admin user: {email}")
        print(f"Password (COPY NOW — won't be shown again): {password}")
        print(f"\nSign in at https://igcse.menghi.dev/login")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_admin <email> [syllabus_code]")
        sys.exit(1)
    email = sys.argv[1]
    code = sys.argv[2] if len(sys.argv) > 2 else None
    run(email, code)
