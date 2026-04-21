"""Password hashing + role-based decorators. Uses Werkzeug's built-in hasher
(pbkdf2:sha256, ~260k iterations by default) — ships with Flask, no extra dep."""
from functools import wraps

from flask import abort
from flask_login import current_user
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plaintext: str) -> str:
    return generate_password_hash(plaintext, method="pbkdf2:sha256", salt_length=16)


def verify_password(stored_hash: str, plaintext: str) -> bool:
    return check_password_hash(stored_hash, plaintext)


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return view(*args, **kwargs)

    return wrapper
