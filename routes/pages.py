"""All rendered HTML page routes. Kept in one blueprint because each page
is small; phases add routes here rather than spawning micro-blueprints."""
from __future__ import annotations

from datetime import date, datetime
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import text

from auth import student_only, verify_password
from extensions import db
from models import (
    Attempt,
    Note,
    Paper,
    PastPaper,
    Question,
    RevisionNote,
    Session,   # SessionRow — used to look up past_paper.session_id
    SubPart,
    Syllabus,
    Topic,
    User,
)
from services.revision import (
    STYLE_SYSTEM_PROMPTS,
    compute_cache_key,
    generate_revision_note,
)
from services.style_classifier import QUIZ, VALID_STYLES, classify

pages_bp = Blueprint("pages", __name__)


def _current_syllabus() -> Syllabus | None:
    if current_user.is_authenticated and current_user.syllabus_id:
        return db.session.get(Syllabus, current_user.syllabus_id)
    code = session.get("syllabus_code")
    if code:
        return Syllabus.query.filter_by(code=code).first()
    return None


# --- Phase 0 carry-over ---


@pages_bp.route("/health")
def health():
    """Deploy smoke test — probes Postgres + volume."""
    import os

    checks: dict[str, str] = {"status": "ok"}
    try:
        db.session.execute(text("SELECT 1"))
        checks["db"] = "connected"
    except Exception as e:
        checks["db"] = f"error: {type(e).__name__}"
        checks["status"] = "degraded"
    try:
        probe = os.path.join(current_app.config["UPLOAD_DIR"], ".health-probe")
        os.makedirs(current_app.config["UPLOAD_DIR"], exist_ok=True)
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        checks["volume"] = "writable"
    except Exception as e:
        checks["volume"] = f"error: {type(e).__name__}"
        checks["status"] = "degraded"
    return checks


# --- Phase 1 — Notes + Syllabus ---


@pages_bp.route("/")
def index():
    """Auth-first flow:
        anonymous          → /login
        authed admin       → /admin (they manage, don't study)
        authed, no syll    → /syllabus (student picks)
        authed, syll set   → /notes
    If the DB is empty (pre-seed), fall back to the legacy bundled static
    page — only happens when Railway's preDeployCommand hasn't run yet.
    """
    if not current_user.is_authenticated:
        return redirect(url_for("pages.login"))
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    syllabus = _current_syllabus()
    if syllabus is None:
        if Syllabus.query.count() == 0:
            return render_template("index.html")
        return redirect(url_for("pages.syllabus_select"))
    return redirect(url_for("pages.notes"))


@pages_bp.route("/syllabus", methods=["GET", "POST"])
@student_only
def syllabus_select():
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        s = Syllabus.query.filter_by(code=code).first()
        if s is None:
            flash("Unknown syllabus code.", "error")
            return redirect(url_for("pages.syllabus_select"))
        # Syllabus is a data filter, not an account attribute. Persist it
        # as the user's default only for students (so next login opens to
        # their syllabus). Admins manage all syllabi — switching just
        # changes what they're browsing this session; User.syllabus_id stays null.
        session["syllabus_code"] = s.code
        if not current_user.is_admin:
            current_user.syllabus_id = s.id
            db.session.commit()
        return redirect(url_for("pages.notes"))
    syllabi = Syllabus.query.order_by(Syllabus.code).all()
    return render_template("syllabus.html", syllabi=syllabi, current=_current_syllabus())


@pages_bp.route("/notes")
@student_only
def notes():
    syllabus = _current_syllabus()
    if syllabus is None:
        return redirect(url_for("pages.syllabus_select"))
    topics = (
        Topic.query.filter_by(syllabus_id=syllabus.id)
        .order_by(Topic.number)
        .all()
    )
    # Preserve insertion order of area codes (already sorted by topic.number).
    seen: dict[str, str] = {}
    for t in topics:
        if t.area_code and t.area_code not in seen:
            seen[t.area_code] = t.area_name or t.area_code
    areas = list(seen.items())
    return render_template(
        "notes.html",
        syllabus=syllabus,
        topics=topics,
        areas=areas,
        today=date.today(),
    )


# --- Phase 2 — auth ---


@pages_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.notes"))
    if request.method == "POST":
        identifier_raw = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        # Accept either email (lowercased) or username (exact case).
        identifier_lower = identifier_raw.lower()
        user = (
            User.query.filter(
                (User.email == identifier_lower) | (User.username == identifier_raw)
            )
            .first()
        )
        if user is None or not verify_password(user.password_hash, password):
            flash("Invalid login or password.", "error")
            return redirect(url_for("pages.login"))
        login_user(user)
        if user.syllabus_id:
            syll = db.session.get(Syllabus, user.syllabus_id)
            if syll:
                session["syllabus_code"] = syll.code
        # Post-login routing:
        #   explicit ?next=... wins
        #   admin → /admin dashboard (they manage, don't study a syllabus)
        #   student with syllabus set → /notes
        #   student without → /syllabus picker
        next_url = request.args.get("next")
        if next_url:
            return redirect(next_url)
        if user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        if user.syllabus_id:
            return redirect(url_for("pages.notes"))
        return redirect(url_for("pages.syllabus_select"))
    return render_template("login.html")


@pages_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.pop("syllabus_code", None)
    return redirect(url_for("pages.login"))


# --- Phase 4 — Exercise ---
#
# Per-paper random-across-sessions practice flow:
#   /exercise                               → paper picker (P2 / P4 / P6)
#   /exercise/paper/<paper_id>/start        → POST, resets practice session
#   /exercise/paper/<paper_id>/next         → GET, random unanswered SubPart
#   /exercise/paper/<paper_id>/end          → GET, summary screen
#   /exercise/subpart/<id>                  → GET, direct render (kept for deep-link)
#
# Session state lives under session['practice'][paper_id] and tracks
# answered subpart ids + correct count — no schema change needed.

from sqlalchemy import func


def _practice_state(paper_id: int) -> dict:
    all_state = session.setdefault("practice", {})
    # JSON session keys are strings — normalise to int via str cast.
    key = str(paper_id)
    state = all_state.get(key)
    if state is None:
        state = {"answered": [], "correct": 0}
        all_state[key] = state
        session.modified = True
    return state


def _record_attempt_in_practice(paper_id: int, subpart_id: int, correct: bool) -> None:
    state = _practice_state(paper_id)
    if subpart_id not in state["answered"]:
        state["answered"].append(subpart_id)
        if correct:
            state["correct"] += 1
        session.modified = True


@pages_bp.route("/exercise")
@student_only
def exercise_select():
    syllabus = _current_syllabus()
    if syllabus is None:
        return redirect(url_for("pages.syllabus_select"))
    papers = (
        Paper.query.filter_by(syllabus_id=syllabus.id)
        .order_by(Paper.number)
        .all()
    )
    # Per-paper subpart availability so the picker can show counts + disable
    # papers with zero questions.
    availability: dict[int, int] = {}
    for p in papers:
        count = (
            db.session.query(func.count(SubPart.id))
            .join(Question, SubPart.question_id == Question.id)
            .join(PastPaper, Question.past_paper_id == PastPaper.id)
            .filter(PastPaper.paper_id == p.id)
            .scalar()
        )
        availability[p.id] = int(count or 0)
    return render_template(
        "exercise_select.html",
        syllabus=syllabus,
        papers=papers,
        availability=availability,
    )


@pages_bp.route("/exercise/paper/<int:paper_id>/start", methods=["POST"])
@student_only
def exercise_paper_start(paper_id: int):
    paper = db.session.get(Paper, paper_id)
    if paper is None:
        abort(404)
    # Reset this paper's practice state.
    session.setdefault("practice", {})[str(paper_id)] = {"answered": [], "correct": 0}
    session.modified = True
    return redirect(url_for("pages.exercise_paper_next", paper_id=paper_id))


@pages_bp.route("/exercise/paper/<int:paper_id>/next")
@student_only
def exercise_paper_next(paper_id: int):
    """Pick a random Question (not SubPart) for this paper that hasn't been
    seen yet in the current practice session. Renders the whole question with
    all its subparts, each getting its own input field."""
    paper = db.session.get(Paper, paper_id)
    if paper is None:
        abort(404)

    state = _practice_state(paper_id)
    # Per-question tracking (new) — fall back to old per-subpart key for safety.
    answered_q_ids = state.get("answered_questions") or [0]

    # Only surface questions that have at least one markable (scalar/mcq) leaf
    # subpart — otherwise we'd render a question with no inputs.
    question = (
        db.session.query(Question)
        .join(PastPaper, Question.past_paper_id == PastPaper.id)
        .filter(PastPaper.paper_id == paper_id)
        .filter(
            Question.subparts.any(SubPart.answer_schema.in_(("scalar", "mcq")))
        )
        .filter(~Question.id.in_(answered_q_ids))
        .order_by(func.random())
        .first()
    )

    if question is None:
        return redirect(url_for("pages.exercise_paper_end", paper_id=paper_id))

    past_paper = question.past_paper or db.session.get(PastPaper, question.past_paper_id)
    session_row = db.session.get(Session, past_paper.session_id) if past_paper else None
    topic = question.topic
    subparts = sorted(question.subparts, key=lambda sp: sp.letter)

    total_in_pool = (
        db.session.query(func.count(Question.id))
        .join(PastPaper, Question.past_paper_id == PastPaper.id)
        .filter(PastPaper.paper_id == paper_id)
        .filter(
            Question.subparts.any(SubPart.answer_schema.in_(("scalar", "mcq")))
        )
        .scalar()
    )
    progress = {
        "answered": len(state.get("answered_questions") or []),
        "correct": state.get("correct", 0),
        "total": int(total_in_pool or 0),
    }
    return render_template(
        "exercise_question.html",
        question=question,
        subparts=subparts,
        paper=paper,
        past_paper=past_paper,
        session_row=session_row,
        topic=topic,
        progress=progress,
    )


@pages_bp.route("/exercise/paper/<int:paper_id>/end")
@student_only
def exercise_paper_end(paper_id: int):
    paper = db.session.get(Paper, paper_id)
    if paper is None:
        abort(404)
    state = _practice_state(paper_id)
    total_in_pool = (
        db.session.query(func.count(SubPart.id))
        .join(Question, SubPart.question_id == Question.id)
        .join(PastPaper, Question.past_paper_id == PastPaper.id)
        .filter(PastPaper.paper_id == paper_id)
        .filter(SubPart.answer_schema.in_(("scalar", "mcq")))
        .scalar()
    )
    return render_template(
        "exercise_end.html",
        paper=paper,
        answered=len(state["answered"]),
        correct=state["correct"],
        total=int(total_in_pool or 0),
    )


@pages_bp.route("/exercise/subpart/<int:subpart_id>")
@student_only
def exercise_subpart(subpart_id: int):
    sp = db.session.get(SubPart, subpart_id)
    if sp is None:
        abort(404)
    question = sp.question
    return render_template(
        "exercise_subpart.html",
        subpart=sp,
        question=question,
        practice_mode=False,
    )


# --- Phase 6 — Onboarding + Revision ---


@pages_bp.route("/onboarding/style", methods=["GET", "POST"])
@student_only
def onboarding_style():
    """Post-quiz: classify via V/S/D scoring, store profile + scores + SR
    overlay flag on the user, redirect to revision. Supports the step-by-step
    UI which POSTs all 14 answers in one submission."""
    if request.method == "POST":
        answers: dict[int, str] = {}
        for q in QUIZ:
            val = request.form.get(f"q{q['id']}")
            if val:
                answers[q["id"]] = val

        result = classify(answers)
        current_user.learning_style_profile = result["profile"]
        current_user.learning_style_scores = result["scores"]
        current_user.sr_overlay = result["sr_overlay"]
        db.session.commit()
        return redirect(url_for("pages.revision"))
    return render_template("onboarding.html", quiz=QUIZ)


@pages_bp.route("/revision")
@student_only
def revision():
    from services.ratelimit import bump_and_check

    style = current_user.learning_style_profile
    if not style:
        return redirect(url_for("pages.onboarding_style"))

    syllabus = _current_syllabus()
    if syllabus is None:
        return redirect(url_for("pages.syllabus_select"))

    topics = Topic.query.filter_by(syllabus_id=syllabus.id).order_by(Topic.number).all()

    from models import ErrorProfile

    profile_rows = (
        ErrorProfile.query.filter_by(user_id=current_user.id)
        .order_by(ErrorProfile.weight.desc())
        .all()
    )
    priority = {p.topic_id: p.weight for p in profile_rows}
    topics.sort(key=lambda t: priority.get(t.id, 0.0), reverse=True)

    rendered: list[dict] = []
    for t in topics[:5]:
        # Compute cache key from current error snapshot for this topic.
        snap = {"count": 0, "tags": []}
        ep = next((p for p in profile_rows if p.topic_id == t.id), None)
        if ep:
            snap["count"] = ep.count
        ck = compute_cache_key(current_user.id, t.id, style, snap)

        cached = (
            RevisionNote.query.filter_by(
                user_id=current_user.id, topic_id=t.id, style_used=style
            )
            .filter_by(cache_key=ck)
            .first()
        )
        if cached is None:
            # Cap LLM calls per day — revision page is expensive.
            ok = bump_and_check(current_user.id, "revision_note", daily_cap=50)
            if not ok:
                rendered.append(
                    {
                        "topic": t,
                        "html": "<article class='topic-card'><p class='topic-intro'>Daily revision-generation cap reached. Try again tomorrow.</p></article>",
                    }
                )
                continue
            canonical_html = (t.notes[0].content_html if t.notes else "")
            html = generate_revision_note(
                topic_name=t.name,
                style=style,
                error_tags=[],
                topic_summary_html=canonical_html,
                sr_overlay=bool(current_user.sr_overlay),
            )
            # Replace any stale row for this user/topic/style; cache_key is the
            # invalidation signal.
            RevisionNote.query.filter_by(
                user_id=current_user.id, topic_id=t.id, style_used=style
            ).delete()
            rn = RevisionNote(
                user_id=current_user.id,
                topic_id=t.id,
                generated_content_html=html,
                style_used=style,
                cache_key=ck,
            )
            db.session.add(rn)
            db.session.commit()
            rendered.append({"topic": t, "html": html})
        else:
            rendered.append({"topic": t, "html": cached.generated_content_html})

    from services.style_classifier import PROFILE_COLORS, PROFILE_NAMES, PROFILE_TAGLINES

    return render_template(
        "revision.html",
        syllabus=syllabus,
        rendered=rendered,
        style=style,
        style_labels=PROFILE_NAMES,
        style_colors=PROFILE_COLORS,
        style_taglines=PROFILE_TAGLINES,
        sr_overlay=bool(current_user.sr_overlay),
        style_scores=current_user.learning_style_scores or {},
    )
