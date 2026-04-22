"""Admin dashboard routes (Phase 2, 3, 8)."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import zipfile
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth import admin_required, hash_password
from extensions import db
from models import PastPaper, Paper, Question, Session, SubPart, Syllabus, User
from services.ingestion import (
    ExtractedQuestion,
    extract_questions_from_pdf,
    save_uploaded_pdf,
)

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


# --- Phase 2 — user management ---


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    new_password: str | None = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        role = request.form.get("role", "student")
        syllabus_code = request.form.get("syllabus_code") or None
        if not email:
            flash("Email required.", "error")
        elif User.query.filter_by(email=email).first():
            flash(f"User {email} already exists.", "error")
        else:
            syll = Syllabus.query.filter_by(code=syllabus_code).first() if syllabus_code else None
            password = secrets.token_urlsafe(16)
            user = User(
                email=email,
                password_hash=hash_password(password),
                role=role,
                syllabus_id=syll.id if syll else None,
            )
            db.session.add(user)
            db.session.commit()
            new_password = password
            flash(
                f"Created {email}. Copy the password now — it cannot be retrieved later.",
                "success",
            )

    all_users = User.query.order_by(User.created_at.desc()).all()
    all_syllabi = Syllabus.query.order_by(Syllabus.code).all()
    return render_template(
        "admin/users.html",
        users=all_users,
        syllabi=all_syllabi,
        new_password=new_password,
    )


# --- Phase 3 — past-paper ingestion ---


@admin_bp.route("/papers/upload", methods=["GET", "POST"])
@login_required
@admin_required
def upload_paper():
    if request.method == "POST":
        syllabus_id = int(request.form["syllabus_id"])
        paper_id = int(request.form["paper_id"])
        year = int(request.form["year"])
        series = request.form["series"]
        variant = int(request.form["variant"])
        question_pdf = request.files.get("question_pdf")
        scheme_pdf = request.files.get("scheme_pdf")
        if question_pdf is None or scheme_pdf is None:
            flash("Both PDFs required.", "error")
            return redirect(url_for("admin.upload_paper"))

        session_row = Session.query.filter_by(year=year, series=series).first()
        if session_row is None:
            session_row = Session(year=year, series=series)
            db.session.add(session_row)
            db.session.flush()

        upload_dir = current_app.config["PAST_PAPERS_DIR"]
        qpath = save_uploaded_pdf(question_pdf, upload_dir)
        save_uploaded_pdf(scheme_pdf, upload_dir)  # ref'd by formula_sheet_ref later

        pp = PastPaper(
            syllabus_id=syllabus_id,
            paper_id=paper_id,
            session_id=session_row.id,
            variant=variant,
            source_pdf_path=qpath,
        )
        db.session.add(pp)
        db.session.flush()

        extracted: list[ExtractedQuestion] = extract_questions_from_pdf(qpath)
        for eq in extracted:
            q = Question(
                past_paper_id=pp.id,
                question_number=eq.question_number,
                body_html=eq.body_html,
                images=eq.images,
                marks_total=eq.marks_total,
                extraction_status="auto",
            )
            db.session.add(q)
            db.session.flush()
            for es in eq.subparts:
                sp = SubPart(
                    question_id=q.id,
                    letter=es.letter,
                    body_html=es.body_html,
                    answer_schema=es.answer_schema,
                    correct_answer=es.correct_answer,
                    mcq_choices=es.mcq_choices,
                    marking_alternatives=es.marking_alternatives,
                    marks=es.marks,
                )
                db.session.add(sp)
        db.session.commit()
        flash(
            f"Uploaded paper + extracted {len(extracted)} questions — review queue updated.",
            "success",
        )
        return redirect(url_for("admin.review_queue"))

    syllabi = Syllabus.query.order_by(Syllabus.code).all()
    papers = Paper.query.order_by(Paper.syllabus_id, Paper.number).all()
    return render_template("admin/upload_paper.html", syllabi=syllabi, papers=papers)


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
    from models import Topic

    topics = Topic.query.order_by(Topic.number).all()
    return render_template("admin/review_question.html", question=q, topics=topics)


# --- Phase 8 — cost dashboard ---


# --- Phase 3 — bulk PDF ingestion ---


@admin_bp.route("/ingest", methods=["GET"])
@login_required
@admin_required
def ingest_home():
    """Upload form + progress view for the bulk past-paper ingestion flow."""
    log_path = Path(os.environ.get("INGEST_LOG_PATH", "/data/ingest.log"))
    last_lines: list[str] = []
    if log_path.exists():
        try:
            with log_path.open("r", errors="replace") as fh:
                # Cheap tail — read last ~8KB and split.
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 8192))
                last_lines = fh.read().splitlines()[-40:]
        except OSError:
            pass

    papers_root = Path(current_app.config["PAST_PAPERS_DIR"])
    pdf_count = 0
    if papers_root.exists():
        try:
            pdf_count = sum(1 for _ in papers_root.rglob("*.pdf"))
        except OSError:
            pdf_count = 0

    return render_template(
        "admin/ingest.html",
        pdf_count=pdf_count,
        papers_root=str(papers_root),
        questions_count=Question.query.count(),
        subparts_count=SubPart.query.count(),
        pending_review=Question.query.filter_by(extraction_status="auto").count(),
        log_tail="\n".join(last_lines),
    )


@admin_bp.route("/ingest/upload", methods=["POST"])
@login_required
@admin_required
def ingest_upload():
    """Accepts past_papers.zip, extracts under PAST_PAPERS_DIR. The zip can be
    either flat (PDFs at top level) or include nested folders — the ingestion
    walker is recursive, so both work. Only *.pdf members are extracted;
    path-traversal entries (absolute paths, '..') are rejected per member."""
    file = request.files.get("zipfile")
    if file is None or file.filename == "":
        flash("No zip file attached.", "error")
        return redirect(url_for("admin.ingest_home"))

    target = Path(current_app.config["PAST_PAPERS_DIR"])
    target.mkdir(parents=True, exist_ok=True)

    extracted = 0
    skipped = 0
    try:
        with zipfile.ZipFile(file.stream) as zf:
            for member in zf.infolist():
                name = member.filename
                if member.is_dir():
                    continue
                if not name.lower().endswith(".pdf"):
                    skipped += 1
                    continue
                # Reject path-traversal or absolute entries.
                norm = os.path.normpath(name)
                if norm.startswith("..") or os.path.isabs(norm):
                    skipped += 1
                    continue
                dest = target / norm
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, dest.open("wb") as out:
                    # Stream in 1 MiB chunks to keep RAM flat on a 260 MB zip.
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
        f"Extracted {extracted} PDF(s) into {target} (skipped {skipped} non-PDF entries).",
        "success",
    )
    return redirect(url_for("admin.ingest_home"))


@admin_bp.route("/ingest/run", methods=["POST"])
@login_required
@admin_required
def ingest_run():
    """Fallback trigger for the web service — spawns a detached subprocess.
    The canonical path is the dedicated Railway worker service, but this is
    handy for local dev and for kicking a one-off rerun without a redeploy.
    Subprocess is idempotent + resumable (see scripts/ingest_papers.py)."""
    pilot = request.form.get("pilot") == "1"
    syllabus = request.form.get("syllabus") or None

    cmd: list[str] = [sys.executable, "-m", "scripts.ingest_papers"]
    if pilot:
        cmd.append("--pilot")
    if syllabus in ("0580", "0654"):
        cmd.extend(["--syllabus", syllabus])

    log_path = Path(os.environ.get("INGEST_LOG_PATH", "/data/ingest.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_path.open("a")
    try:
        subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach — survives gunicorn worker recycling
        )
    finally:
        # Popen duplicates the fd; close ours so the handle is owned by the child.
        log_fh.close()

    flash(f"Ingestion kicked off ({' '.join(cmd)}). Refresh to watch progress.", "info")
    return redirect(url_for("admin.ingest_home"))


@admin_bp.route("/ingest/progress", methods=["GET"])
@login_required
@admin_required
def ingest_progress():
    """JSON progress endpoint — for a polling UI / external monitoring."""
    return jsonify(
        questions=Question.query.count(),
        subparts=SubPart.query.count(),
        pending_review=Question.query.filter_by(extraction_status="auto").count(),
        past_papers=PastPaper.query.count(),
    )


# --- Phase 8 — cost dashboard ---


@admin_bp.route("/cost")
@login_required
@admin_required
def cost_dashboard():
    """Cross-reference OpenAI usage (fetched lazily) with per-user rate-limit
    counters. The OpenAI /v1/usage pull requires a separate 'admin API key' —
    until that's wired on Railway, we render per-user rate-limit counts only."""
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
        openai_usage=None,  # placeholder; wire to OpenAI /v1/usage in user's admin-API-key era
    )
