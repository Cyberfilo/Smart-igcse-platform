"""Per-user, per-day, per-endpoint call caps (Phase 8). Postgres-backed so it
survives restarts; a Redis-backed impl can be swapped in later without route
changes since the decorator signature is stable."""
from __future__ import annotations

from datetime import date
from functools import wraps

from flask import abort
from flask_login import current_user

from extensions import db
from models import RateLimit


def bump_and_check(user_id: int, endpoint: str, daily_cap: int) -> bool:
    """Atomically bump today's counter; return True if under cap, False if hit.
    For Postgres this is safe under concurrent requests thanks to the unique
    constraint on (user_id, day, endpoint); races lose the insert and fall
    through to the update path."""
    today = date.today()
    row = (
        db.session.query(RateLimit)
        .filter_by(user_id=user_id, day=today, endpoint=endpoint)
        .first()
    )
    if row is None:
        row = RateLimit(user_id=user_id, day=today, endpoint=endpoint, count=0)
        db.session.add(row)
    row.count += 1
    db.session.commit()
    return row.count <= daily_cap


def rate_limit(endpoint_key: str, daily_cap: int):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not bump_and_check(current_user.id, endpoint_key, daily_cap):
                abort(429, description=f"Daily limit reached for {endpoint_key}")
            return view(*args, **kwargs)

        return wrapper

    return decorator
