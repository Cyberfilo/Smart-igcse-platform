"""HTMX and JSON endpoints. These return HTML partials or JSON, never full
pages — kept separate so Phase 1's notes-partial pattern is obvious."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request, session
from flask_login import current_user

from auth import student_only
from extensions import db
from models import Attempt, ErrorProfile, Note, Question, SubPart, Topic
from services.chat import ask as chat_ask
from services.marking import auto_mark
from services.ocr import diagnose

api_bp = Blueprint("api", __name__)


# --- Per-topic chat (clarifying questions) ---


@api_bp.route("/api/chat/<int:topic_id>", methods=["POST"])
@student_only
def topic_chat(topic_id: int):
    """Stateless chat endpoint. Client sends conversation history + new
    question; server returns the assistant reply. No DB writes — keeps
    per-topic conversations entirely client-side for v1 (privacy-friendly +
    no schema yet)."""
    topic = db.session.get(Topic, topic_id)
    if topic is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    question = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not question:
        return jsonify({"error": "message required"}), 400
    if not isinstance(history, list):
        return jsonify({"error": "history must be a list"}), 400

    # Use the first Note attached to this topic as the canonical grounding text.
    note = Note.query.filter_by(topic_id=topic.id).order_by(Note.display_order).first()
    canonical = note.content_html if note else ""

    reply = chat_ask(
        question=question,
        history=[
            {"role": m.get("role"), "content": m.get("content", "")}
            for m in history
            if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
        ],
        topic_name=topic.name,
        syllabus_ref=topic.syllabus_ref,
        canonical_html=canonical,
    )
    return jsonify({"reply": reply, "topic_id": topic.id})


# --- Phase 1 — HTMX partials ---


@api_bp.route("/notes/<int:topic_id>/partial")
@student_only
def note_partial(topic_id: int):
    topic = db.session.get(Topic, topic_id)
    if topic is None:
        abort(404)
    note = Note.query.filter_by(topic_id=topic.id).order_by(Note.display_order).first()
    if note is None:
        abort(404)
    return render_template("_topic_card.html", topic=topic, note=note)


# --- Phase 4 — attempt submission (digital input) ---


def _bump_practice_state_question(question_id: int, paper_id: int, all_correct: bool) -> None:
    """Record an answered Question in the practice-session state. Called by
    the batch /attempt/question/<id> endpoint."""
    practice = session.get("practice") or {}
    key = str(paper_id)
    state = practice.get(key)
    if state is None:
        return
    answered = state.setdefault("answered_questions", [])
    if question_id not in answered:
        answered.append(question_id)
        if all_correct:
            state["correct"] = state.get("correct", 0) + 1
        session["practice"] = practice
        session.modified = True


def _bump_practice_state(subpart: SubPart, verdict: str) -> None:
    """Legacy per-subpart tracker — kept only so the single-subpart deep-link
    path keeps working. New per-question flow uses _bump_practice_state_question."""
    from models import PastPaper, Question

    q = subpart.question or db.session.get(Question, subpart.question_id)
    if q is None:
        return
    pp = db.session.get(PastPaper, q.past_paper_id)
    if pp is None:
        return
    practice = session.get("practice") or {}
    key = str(pp.paper_id)
    state = practice.get(key)
    if state is None:
        return
    legacy = state.setdefault("answered", [])
    if subpart.id not in legacy:
        legacy.append(subpart.id)
        if verdict == "correct_optimal":
            state["correct"] = state.get("correct", 0) + 1
        session["practice"] = practice
        session.modified = True


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
@student_only
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
    _bump_practice_state(sp, verdict)
    return jsonify({"verdict": verdict, "attempt_id": attempt.id})


# --- Phase 5 — photo attempt (feature-flagged inside services.ocr) ---


@api_bp.route("/attempt/<int:subpart_id>/photo", methods=["POST"])
@student_only
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
    _bump_practice_state(sp, verdict)

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


# --- Per-Question batch submission ---


@api_bp.route("/attempt/question/<int:question_id>", methods=["POST"])
@student_only
def submit_question(question_id: int):
    """Accepts answers for every leaf subpart of a question in one request.
    Returns a per-subpart verdict array. Records one Attempt row per subpart,
    bumps error profile on wrong leaves, and updates practice-session state
    keyed by question_id (for the Next-button flow)."""
    q = db.session.get(Question, question_id)
    if q is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    answers_by_subpart: dict[int, str] = {
        int(k): v for k, v in (payload.get("answers") or {}).items()
    }
    if not answers_by_subpart:
        return jsonify({"error": "answers required"}), 400

    verdicts: list[dict] = []
    all_correct = True
    for sp in q.subparts:
        if sp.answer_schema not in ("scalar", "mcq", "multi_cell"):
            # Container ('none') or graphical — not markable, skip.
            continue
        submitted = answers_by_subpart.get(sp.id)
        if submitted is None:
            verdicts.append(
                {"subpart_id": sp.id, "letter": sp.letter, "verdict": "missing"}
            )
            all_correct = False
            continue

        verdict = auto_mark(sp.answer_schema, submitted, sp.correct_answer)
        if verdict != "correct_optimal":
            all_correct = False
            delta = 1.0 if verdict == "incorrect" else 0.3
            _bump_error_profile(current_user.id, q.topic_id, delta)

        attempt = Attempt(
            user_id=current_user.id,
            subpart_id=sp.id,
            submitted_answer=submitted,
            verdict=verdict,
            error_tags=[],
        )
        db.session.add(attempt)
        verdicts.append({
            "subpart_id": sp.id,
            "letter": sp.letter,
            "verdict": verdict,
            "expected": sp.correct_answer,
        })
    db.session.commit()

    # Update practice-session state for the Next button.
    from models import PastPaper

    pp = db.session.get(PastPaper, q.past_paper_id)
    if pp:
        _bump_practice_state_question(q.id, pp.paper_id, all_correct)

    return jsonify({"question_id": q.id, "all_correct": all_correct, "verdicts": verdicts})


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


# --- Phase 9 — user-curated revision list ---
#
# All three endpoints return small HTML partials so HTMX can swap them in
# place. They are POST-only so a stale tab can't unintentionally toggle a
# row via a GET preload. Auth is enforced by @student_only.


@api_bp.route("/api/revision-list/toggle/<int:topic_id>", methods=["POST"])
@student_only
def revlist_toggle(topic_id: int):
    """Add the topic to the user's revision list, or remove it if already
    present. Returns the updated button partial. Idempotent."""
    from models import RevisionListItem

    topic = db.session.get(Topic, topic_id)
    if topic is None:
        abort(404)

    existing = RevisionListItem.query.filter_by(
        user_id=current_user.id, topic_id=topic_id
    ).first()
    if existing:
        db.session.delete(existing)
        in_list = False
    else:
        db.session.add(RevisionListItem(
            user_id=current_user.id, topic_id=topic_id,
        ))
        in_list = True
    db.session.commit()
    return render_template("_revlist_button.html", topic_id=topic_id, in_list=in_list)


@api_bp.route("/api/revision-list/<int:topic_id>/done", methods=["POST"])
@student_only
def revlist_done(topic_id: int):
    """Toggle the completed state on a revision-list row. Returns the row
    partial so HTMX can swap it in place (with strikethrough or restored)."""
    from datetime import datetime, timezone

    from models import RevisionListItem

    item = RevisionListItem.query.filter_by(
        user_id=current_user.id, topic_id=topic_id
    ).first()
    if item is None:
        abort(404)
    item.completed_at = None if item.completed_at else datetime.now(timezone.utc)
    db.session.commit()
    return render_template("_revlist_row.html", item=item)


@api_bp.route("/api/revision-list/<int:topic_id>/remove", methods=["POST"])
@student_only
def revlist_remove(topic_id: int):
    """Delete a row from the user's revision list. Returns an empty body —
    HTMX `hx-swap='outerHTML'` then removes the row from the DOM."""
    from models import RevisionListItem

    item = RevisionListItem.query.filter_by(
        user_id=current_user.id, topic_id=topic_id
    ).first()
    if item is not None:
        db.session.delete(item)
        db.session.commit()
    return ("", 200)
