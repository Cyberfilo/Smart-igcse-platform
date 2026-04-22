"""Password hashing + role-based decorators. Uses Werkzeug's built-in hasher
(pbkdf2:sha256, ~260k iterations by default) — ships with Flask, no extra dep."""
from functools import wraps

from flask import abort, redirect, request, url_for
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
    """Gates the student-facing surface (notes, exercise, revision, chat,
    attempts) behind authentication. Admins are allowed through so they
    can preview the student UI — the pages will render with the admin's
    own (empty) personalised data, which is enough for layout QA but not
    for testing a specific student's flow.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("pages.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper
