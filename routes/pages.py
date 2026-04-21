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

from auth import verify_password
from extensions import db
from models import (
    Attempt,
    Note,
    Paper,
    PastPaper,
    Question,
    RevisionNote,
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
@login_required
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
@login_required
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


@pages_bp.route("/exercise")
@login_required
def exercise_select():
    syllabus = _current_syllabus()
    if syllabus is None:
        return redirect(url_for("pages.syllabus_select"))
    topics = Topic.query.filter_by(syllabus_id=syllabus.id).order_by(Topic.number).all()
    papers = Paper.query.filter_by(syllabus_id=syllabus.id).order_by(Paper.number).all()
    return render_template("exercise_select.html", syllabus=syllabus, topics=topics, papers=papers)


@pages_bp.route("/exercise/subpart/<int:subpart_id>")
@login_required
def exercise_subpart(subpart_id: int):
    sp = db.session.get(SubPart, subpart_id)
    if sp is None:
        abort(404)
    question = sp.question
    return render_template("exercise_subpart.html", subpart=sp, question=question)


# --- Phase 6 — Onboarding + Revision ---


@pages_bp.route("/onboarding/style", methods=["GET", "POST"])
@login_required
def onboarding_style():
    if request.method == "POST":
        answers: dict[int, str] = {}
        for q in QUIZ:
            val = request.form.get(f"q{q['id']}")
            if val:
                answers[q["id"]] = val
        style = classify(answers)
        current_user.learning_style_profile = style
        db.session.commit()
        flash(f"Your revision style: {style.replace('_', ' ')}", "info")
        return redirect(url_for("pages.revision"))
    return render_template("onboarding.html", quiz=QUIZ)


@pages_bp.route("/revision")
@login_required
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

    return render_template(
        "revision.html",
        syllabus=syllabus,
        rendered=rendered,
        style=style,
        style_labels={k: k.replace("_", " ") for k in VALID_STYLES},
    )
