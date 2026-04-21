"""Admin dashboard routes (Phase 2, 3, 8)."""
from __future__ import annotations

import secrets

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
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
