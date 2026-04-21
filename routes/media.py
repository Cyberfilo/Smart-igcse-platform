"""Auth-gated static media serving out of the Railway volume. Used by past-paper
diagrams and student working photos. Includes a path-traversal guard — a
SubPart body that references /media/../../etc/passwd must 404, not 500."""
from __future__ import annotations

import os

from flask import Blueprint, abort, current_app, send_file
from flask_login import current_user, login_required

media_bp = Blueprint("media", __name__, url_prefix="/media")


def _safe_join(base: str, rel: str) -> str | None:
    """Return an absolute path if rel is safely within base; else None."""
    abs_base = os.path.abspath(base)
    abs_target = os.path.abspath(os.path.join(abs_base, rel))
    if not abs_target.startswith(abs_base + os.sep) and abs_target != abs_base:
        return None
    return abs_target


@media_bp.route("/past-papers/<path:rel>")
@login_required
def past_paper_media(rel: str):
    base = current_app.config["PAST_PAPERS_DIR"]
    full = _safe_join(base, rel)
    if full is None or not os.path.isfile(full):
        abort(404)
    return send_file(full)


@media_bp.route("/uploads/<int:user_id>/<path:rel>")
@login_required
def upload_media(user_id: int, rel: str):
    # Users can only view their own uploads; admins see anyone's.
    if current_user.id != user_id and not current_user.is_admin:
        abort(403)
    base = os.path.join(current_app.config["UPLOAD_DIR"], str(user_id))
    full = _safe_join(base, rel)
    if full is None or not os.path.isfile(full):
        abort(404)
    return send_file(full)
