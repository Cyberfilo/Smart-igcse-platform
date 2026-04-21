"""Password hashing + role-based decorators. Uses Werkzeug's built-in hasher
(pbkdf2:sha256, ~260k iterations by default) — ships with Flask, no extra dep."""
from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plaintext: str) -> str:
    return generate_password_hash(plaintext, method="pbkdf2:sha256", salt_length=16)


def verify_password(stored_hash: str, plaintext: str) -> bool:
    return check_password_hash(stored_hash, plaintext)


def admin_required(view):
    """Admin-only routes (dashboard, user management, paper ingestion, cost)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("pages.login", next=request.path))
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def student_only(view):
    """Student-only routes (notes, exercise, revision, chat, attempts).
    Admins are NOT students — they manage the platform, they don't study it.
    A logged-in admin hitting a student URL gets bounced to /admin.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("pages.login", next=request.path))
        if current_user.is_admin:
            flash("Admins don't have a student view — use the admin dashboard.", "info")
            return redirect(url_for("admin.dashboard"))
        return view(*args, **kwargs)

    return wrapper
