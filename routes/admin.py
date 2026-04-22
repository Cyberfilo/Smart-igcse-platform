"""Admin dashboard routes.

Ingestion runs LOCALLY (see local_ingest/) — this blueprint's ingest endpoints
are for uploading the resulting images zip to the Railway volume, and for
showing DB counts so the admin can see the extraction landed.
"""
from __future__ import annotations

import csv
import io
import os
import re
import secrets
import zipfile
from pathlib import Path

from flask import (
    Blueprint, Response, abort, current_app, flash, jsonify, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required

from auth import admin_required, hash_password
from extensions import db
from models import PastPaper, Paper, Question, SubPart, Syllabus, Topic, User


# ── School email conventions ─────────────────────────────────────────
#
# Student: name.surname@students.bdcschool.eu   (two dot-parts before @)
# Admin:   n.surname@bdcschool.eu               (one-char first + surname)
#
# Anything else gets rejected — admin has to use the schemes above.

STUDENT_DOMAIN = "students.bdcschool.eu"
ADMIN_DOMAIN = "bdcschool.eu"

_STUDENT_RE = re.compile(r"^([a-z]+\.[a-z]+)@" + re.escape(STUDENT_DOMAIN) + r"$", re.I)
_ADMIN_RE = re.compile(r"^([a-z]\.[a-z]+)@" + re.escape(ADMIN_DOMAIN) + r"$", re.I)


def _parse_school_email(email: str) -> tuple[str, str] | None:
    """Returns (role, username) for a valid school email, else None.
    Username is always the email local part, lowercased."""
    email = email.strip().lower()
    m = _STUDENT_RE.match(email)
    if m:
        return "student", m.group(1)
    m = _ADMIN_RE.match(email)
    if m:
        return "admin", m.group(1)
    return None

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        users_count=User.query.count(),
        questions_count=Question.query.count(),
        pending_review=Question.query.filter_by(extraction_status="auto").count(),
    )


# --- User management ---


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    """Add-user flow parses the school email → (role, username). We also
    persist the generated password (in generated_password) so the admin
    can re-export it later. The password_hash column is still the auth
    source-of-truth — plaintext is ONLY kept for the credential sheet."""
    just_created: dict | None = None

    if request.method == "POST":
        email_raw = (request.form.get("email") or "").strip()
        default_syllabus = (request.form.get("syllabus_code") or "").strip() or None

        parsed = _parse_school_email(email_raw)
        if parsed is None:
            flash(
                f"Email must be either name.surname@{STUDENT_DOMAIN} (student) "
                f"or n.surname@{ADMIN_DOMAIN} (admin).",
                "error",
            )
        elif User.query.filter_by(email=email_raw.lower()).first():
            flash(f"User {email_raw} already exists.", "error")
        else:
            role, username = parsed
            if User.query.filter_by(username=username).first():
                flash(f"Username {username} already taken.", "error")
            else:
                syll = None
                if default_syllabus:
                    syll = Syllabus.query.filter_by(code=default_syllabus).first()
                password = secrets.token_urlsafe(12)
                user = User(
                    email=email_raw.lower(),
                    username=username,
                    password_hash=hash_password(password),
                    generated_password=password,
                    role=role,
                    syllabus_id=syll.id if (syll and role == "student") else None,
                )
                db.session.add(user)
                db.session.commit()
                just_created = {
                    "email": user.email,
                    "username": user.username,
                    "password": password,
                    "role": role,
                    "display_name": user.display_name,
                }

    role_filter = (request.args.get("role") or "all").lower()
    q_search = (request.args.get("q") or "").strip().lower()

    query = User.query
    if role_filter in ("student", "admin"):
        query = query.filter_by(role=role_filter)
    if q_search:
        like = f"%{q_search}%"
        query = query.filter(
            db.or_(User.email.ilike(like), User.username.ilike(like))
        )

    all_users = query.order_by(User.created_at.desc()).all()
    counts = {
        "all": User.query.count(),
        "student": User.query.filter_by(role="student").count(),
        "admin": User.query.filter_by(role="admin").count(),
    }
    all_syllabi = Syllabus.query.order_by(Syllabus.code).all()

    return render_template(
        "admin/users.html",
        users=all_users,
        syllabi=all_syllabi,
        just_created=just_created,
        role_filter=role_filter,
        q_search=q_search,
        counts=counts,
        student_domain=STUDENT_DOMAIN,
        admin_domain=ADMIN_DOMAIN,
    )


@admin_bp.route("/users/export.csv")
@login_required
@admin_required
def users_export():
    """Download every user's credentials + study-profile data as CSV. Columns:
    email, username, display_name, role, syllabus, password, study_profile,
    sr_overlay, V_score, S_score, D_score. Scores are null for users who
    haven't taken the quiz yet."""
    from services.style_classifier import PROFILE_NAMES

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "email", "username", "display_name", "role", "syllabus", "password",
        "study_profile", "sr_overlay", "V_score", "S_score", "D_score",
    ])
    for u in User.query.order_by(User.role, User.username).all():
        syll_code = ""
        if u.syllabus_id:
            syll = db.session.get(Syllabus, u.syllabus_id)
            syll_code = syll.code if syll else ""
        scores = u.learning_style_scores or {}
        writer.writerow([
            u.email,
            u.username or "",
            u.display_name,
            u.role,
            syll_code,
            u.generated_password or "",
            PROFILE_NAMES.get(u.learning_style_profile or "", "") or "",
            "yes" if u.sr_overlay else "",
            scores.get("V", ""),
            scores.get("S", ""),
            scores.get("D", ""),
        ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=igcse-users.csv"},
    )


# --- Ingestion bookkeeping (image zip upload + DB progress) ---


@admin_bp.route("/ingest", methods=["GET"])
@login_required
@admin_required
def ingest_home():
    """Shows DB state + the image-zip upload form.

    The actual question extraction runs locally (see local_ingest/) and writes
    directly to this DB via the TCP proxy. The only thing Railway needs from the
    local run is the cropped diagrams, which get zipped and uploaded here."""
    papers_root = Path(current_app.config["PAST_PAPERS_DIR"])
    images_dir = papers_root / "_images"
    image_count = 0
    if images_dir.exists():
        try:
            image_count = sum(1 for _ in images_dir.rglob("*"))
        except OSError:
            image_count = 0

    return render_template(
        "admin/ingest.html",
        images_root=str(images_dir),
        image_count=image_count,
        questions_count=Question.query.count(),
        subparts_count=SubPart.query.count(),
        past_papers_count=PastPaper.query.count(),
    )


@admin_bp.route("/ingest/images", methods=["POST"])
@login_required
@admin_required
def ingest_images():
    """Accepts images.zip, extracts into PAST_PAPERS_DIR/_images/.

    Streaming + 1 MiB chunks to keep RAM flat. Rejects path-traversal entries
    and drops macOS AppleDouble sidecars."""
    file = request.files.get("zipfile")
    if file is None or file.filename == "":
        flash("No zip file attached.", "error")
        return redirect(url_for("admin.ingest_home"))

    target = Path(current_app.config["PAST_PAPERS_DIR"]) / "_images"
    target.mkdir(parents=True, exist_ok=True)

    extracted = 0
    skipped = 0
    try:
        with zipfile.ZipFile(file.stream) as zf:
            for member in zf.infolist():
                name = member.filename
                if member.is_dir():
                    continue
                norm = os.path.normpath(name)
                if norm.startswith("..") or os.path.isabs(norm):
                    skipped += 1
                    continue
                basename = os.path.basename(norm)
                if "__MACOSX" in norm.split(os.sep) or basename.startswith("._"):
                    skipped += 1
                    continue
                # Accept common diagram formats.
                if not basename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    skipped += 1
                    continue
                dest = target / norm
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, dest.open("wb") as out:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                extracted += 1
    except zipfile.BadZipFile:
        flash("That file isn't a valid zip.", "error")
        return redirect(url_for("admin.ingest_home"))

    flash(
        f"Extracted {extracted} image(s) into {target} (skipped {skipped} non-image entries).",
        "success",
    )
    return redirect(url_for("admin.ingest_home"))


@admin_bp.route("/ingest/progress", methods=["GET"])
@login_required
@admin_required
def ingest_progress():
    """JSON progress endpoint — polled by /admin/ingest to update counters live
    while the local ingestion run commits questions to Postgres."""
    return jsonify(
        questions=Question.query.count(),
        subparts=SubPart.query.count(),
        pending_review=Question.query.filter_by(extraction_status="auto").count(),
        past_papers=PastPaper.query.count(),
    )


# --- Review queue ---


@admin_bp.route("/review")
@login_required
@admin_required
def review_queue():
    pending = (
        Question.query.filter_by(extraction_status="auto")
        .order_by(Question.id)
        .limit(50)
        .all()
    )
    return render_template("admin/review_queue.html", questions=pending)


@admin_bp.route("/review/<int:question_id>", methods=["GET", "POST"])
@login_required
@admin_required
def review_question(question_id: int):
    q = db.session.get(Question, question_id)
    if q is None:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "approve":
            q.extraction_status = "admin_approved"
            flash(f"Question {q.id} approved.", "success")
        elif action == "edit":
            q.body_html = request.form.get("body_html", q.body_html)
            topic_id = request.form.get("topic_id")
            q.topic_id = int(topic_id) if topic_id else None
            q.extraction_status = "admin_edited"
            flash(f"Question {q.id} saved.", "success")
        db.session.commit()
        return redirect(url_for("admin.review_queue"))
    topics = Topic.query.order_by(Topic.number).all()
    return render_template("admin/review_question.html", question=q, topics=topics)


# --- Cost dashboard ---


@admin_bp.route("/cost")
@login_required
@admin_required
def cost_dashboard():
    """Per-user rate-limit counters. OpenAI /v1/usage pull needs an admin-API
    key, not yet wired — placeholder UI until then."""
    from datetime import date
    from models import RateLimit

    today = date.today()
    rows = (
        db.session.query(RateLimit, User)
        .join(User, RateLimit.user_id == User.id)
        .filter(RateLimit.day == today)
        .order_by(RateLimit.count.desc())
        .all()
    )
    return render_template(
        "admin/cost.html",
        today=today,
        rows=rows,
        openai_usage=None,
    )
