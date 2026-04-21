"""HTMX and JSON endpoints. These return HTML partials or JSON, never full
pages — kept separate so Phase 1's notes-partial pattern is obvious."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import db
from models import Attempt, ErrorProfile, Note, SubPart, Topic
from services.marking import auto_mark
from services.ocr import diagnose

api_bp = Blueprint("api", __name__)


# --- Phase 1 — HTMX partials ---


@api_bp.route("/notes/<int:topic_id>/partial")
def note_partial(topic_id: int):
    topic = db.session.get(Topic, topic_id)
    if topic is None:
        abort(404)
    note = Note.query.filter_by(topic_id=topic.id).order_by(Note.display_order).first()
    if note is None:
        abort(404)
    return render_template("_topic_card.html", topic=topic, note=note)


# --- Phase 4 — attempt submission (digital input) ---


def _bump_error_profile(user_id: int, topic_id: int | None, weight_delta: float):
    if topic_id is None:
        return
    row = ErrorProfile.query.filter_by(user_id=user_id, topic_id=topic_id).first()
    if row is None:
        row = ErrorProfile(user_id=user_id, topic_id=topic_id, count=0, weight=0.0)
        db.session.add(row)
    row.count += 1
    row.weight += weight_delta
    from datetime import datetime, timezone

    row.last_seen = datetime.now(timezone.utc)


@api_bp.route("/attempt/<int:subpart_id>", methods=["POST"])
@login_required
def submit_attempt(subpart_id: int):
    sp = db.session.get(SubPart, subpart_id)
    if sp is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    submitted = payload.get("answer")

    verdict = auto_mark(sp.answer_schema, submitted, sp.correct_answer)

    # Phase 7 — bump error profile on non-optimal verdicts.
    if verdict != "correct_optimal":
        # Weight scheme: incorrect=1.0, suboptimal=0.3 (soft).
        delta = 1.0 if verdict == "incorrect" else 0.3
        _bump_error_profile(current_user.id, sp.question.topic_id, delta)

    attempt = Attempt(
        user_id=current_user.id,
        subpart_id=sp.id,
        submitted_answer=submitted,
        verdict=verdict,
        error_tags=[],
    )
    db.session.add(attempt)
    db.session.commit()
    return jsonify({"verdict": verdict, "attempt_id": attempt.id})


# --- Phase 5 — photo attempt (feature-flagged inside services.ocr) ---


@api_bp.route("/attempt/<int:subpart_id>/photo", methods=["POST"])
@login_required
def submit_photo_attempt(subpart_id: int):
    import os

    from flask import current_app

    sp = db.session.get(SubPart, subpart_id)
    if sp is None:
        abort(404)

    submitted_answer = request.form.get("answer")
    file = request.files.get("photo")
    if file is None or file.filename == "":
        return jsonify({"error": "No photo attached"}), 400

    # Persist the photo under /data/student-uploads/<user_id>/
    upload_dir = os.path.join(current_app.config["UPLOAD_DIR"], str(current_user.id))
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"{subpart_id}-{file.filename}"
    # Path-traversal guard — filename sanitisation.
    from werkzeug.utils import secure_filename

    safe = secure_filename(fname)
    abs_path = os.path.join(upload_dir, safe)
    file.save(abs_path)

    photo_bytes = open(abs_path, "rb").read()
    result = diagnose(
        photo_bytes=photo_bytes,
        subpart_body=sp.body_html,
        canonical_method=sp.canonical_method,
        marking_alternatives=sp.marking_alternatives or [],
        correct_answer=sp.correct_answer,
        submitted_answer=submitted_answer,
    )

    verdict = result.get("verdict", "incorrect")
    if verdict != "correct_optimal":
        delta = 1.0 if verdict == "incorrect" else 0.3
        _bump_error_profile(current_user.id, sp.question.topic_id, delta)

    attempt = Attempt(
        user_id=current_user.id,
        subpart_id=sp.id,
        submitted_answer=submitted_answer,
        working_photo_path=abs_path,
        ocr_transcript=result.get("transcript"),
        verdict=verdict,
        error_tags=result.get("error_tags") or [],
        diagnostic_feedback_html=_feedback_html(result),
    )
    db.session.add(attempt)
    db.session.commit()

    # Invalidate revision cache for this topic so next /revision regenerates
    # with fresh error context (Phase 7 wiring).
    if sp.question.topic_id is not None:
        from models import RevisionNote

        RevisionNote.query.filter_by(
            user_id=current_user.id, topic_id=sp.question.topic_id
        ).delete()
        db.session.commit()

    return jsonify(
        {
            "verdict": verdict,
            "attempt_id": attempt.id,
            "feedback_html": attempt.diagnostic_feedback_html,
            "transcript": result.get("transcript", ""),
        }
    )


def _feedback_html(result: dict) -> str:
    verdict = result.get("verdict", "incorrect")
    correction = result.get("suggested_correction", "")
    if verdict == "correct_optimal":
        return (
            "<div class='tip-box'><span class='tip-label'>Nicely done</span>"
            "Answer correct and method matches the canonical marking scheme.</div>"
        )
    if verdict == "correct_suboptimal":
        return (
            "<div class='tip-box'><span class='tip-label'>Right answer — faster way available</span>"
            f"{correction}</div>"
        )
    return (
        "<div class='example-box'><span class='eg-label'>Where it went wrong</span>"
        f"{correction}</div>"
    )
