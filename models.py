"""All SQLAlchemy models across every phase. Kept in one file so Alembic's
autogenerate picks them up without import-order surprises.

Phase-gated sections are labelled with `# --- Phase N ---` so future migrations
remain intelligible."""
from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import JSON, UniqueConstraint

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Phase 1 — syllabus / paper / session / topic / note ---


class Syllabus(db.Model):
    __tablename__ = "syllabi"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(8), unique=True, nullable=False)  # "0580", "0654"
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    topics = db.relationship("Topic", back_populates="syllabus", cascade="all, delete-orphan")
    papers = db.relationship("Paper", back_populates="syllabus", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Syllabus {self.code}>"


class Paper(db.Model):
    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("syllabus_id", "number", name="uq_paper_syllabus_number"),)

    id = db.Column(db.Integer, primary_key=True)
    syllabus_id = db.Column(db.Integer, db.ForeignKey("syllabi.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)  # 2, 4, 6
    supports_digital_input = db.Column(db.Boolean, default=False, nullable=False)  # 0654 P2 = True

    syllabus = db.relationship("Syllabus", back_populates="papers")
    past_papers = db.relationship("PastPaper", back_populates="paper")


class Session(db.Model):
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("year", "series", name="uq_session_year_series"),)

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    series = db.Column(db.String(4), nullable=False)  # F/M, M/J, O/N


class Topic(db.Model):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("syllabus_id", "number", name="uq_topic_syllabus_number"),)

    id = db.Column(db.Integer, primary_key=True)
    syllabus_id = db.Column(db.Integer, db.ForeignKey("syllabi.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    short_name = db.Column(db.String(32), nullable=True)  # nav-button label
    color_class = db.Column(db.String(32), nullable=False, default="color-purple")
    # Area grouping for nav filter (e.g. "C1"/"Number" for 0580; "BIO"/"Biology" for 0654).
    area_code = db.Column(db.String(16), nullable=True, index=True)
    area_name = db.Column(db.String(80), nullable=True)
    syllabus_ref = db.Column(db.String(24), nullable=True)  # e.g. "C1.1", "E2.13", "B5.1"
    description = db.Column(db.Text, nullable=True)

    syllabus = db.relationship("Syllabus", back_populates="topics")
    notes = db.relationship("Note", back_populates="topic", cascade="all, delete-orphan")


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    content_html = db.Column(db.Text, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    topic = db.relationship("Topic", back_populates="notes")


# --- Phase 2 — auth ---


class Cohort(db.Model):
    __tablename__ = "cohorts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    # Circular FK: Cohort.admin_id → users.id AND User.cohort_id → cohorts.id.
    # `use_alter=True` makes Alembic emit this FK as a separate ALTER TABLE
    # after both tables are created. Postgres otherwise rejects the migration.
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", use_alter=True, name="fk_cohorts_admin_id"),
        nullable=True,
    )
    visibility_rules = db.Column(JSON, nullable=True)  # {"topic_ids": [1,2,3]}
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=True)  # optional, alt login + display
    password_hash = db.Column(db.String(255), nullable=False)
    # Three password fields — all for a closed-network classroom where the
    # admin manages a small cohort and accepts plaintext-at-rest as the
    # tradeoff for recoverable credentials. If the DB leaks, every live
    # password leaks with it. Do not copy this pattern to a public-internet
    # app.
    #   generated_password : the one-time password printed on the credential
    #                        sheet at account creation. Unchanged after the
    #                        user rotates — kept as an audit of what was
    #                        originally issued.
    #   current_password   : the password the user chose on first login.
    #                        null until rotation. Used for the admin CSV
    #                        export so a teacher can still recover it.
    #   must_change_password : when True, every request (except /auth/
    #                        set-password and /logout) bounces to the
    #                        set-password form. Flips to False on rotation.
    generated_password = db.Column(db.String(64), nullable=True)
    current_password = db.Column(db.String(64), nullable=True)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    role = db.Column(db.String(16), default="student", nullable=False)  # student / admin
    syllabus_id = db.Column(db.Integer, db.ForeignKey("syllabi.id"), nullable=True)
    cohort_id = db.Column(db.Integer, db.ForeignKey("cohorts.id"), nullable=True)
    # Study-preference profile (NOT "learning style" per the research). One
    # of the values in services.style_classifier.VALID_STYLES.
    learning_style_profile = db.Column(db.String(40), nullable=True)
    # Raw V/S/D dimension scores from the 14-item quiz. Kept so admins can
    # see fine-grained positioning (e.g. strong-visual vs balanced-visual)
    # and so the SR overlay decision is auditable.
    learning_style_scores = db.Column(JSON, nullable=True)
    # Self-Regulation Booster flag — set when D ≤ +3 at classification time.
    # Triggers retrieval warm-up + weekly review scaffolds on revision notes.
    sr_overlay = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def display_name(self) -> str:
        """Human-readable name shown in nav + greetings. Prefers username
        (format: name.surname) → title-cased "Name Surname"; else email
        local-part unchanged."""
        src = self.username or self.email.split("@")[0]
        parts = src.split(".")
        if len(parts) >= 2 and all(p.isalpha() for p in parts):
            return " ".join(p.capitalize() for p in parts)
        return src

    @property
    def initials(self) -> str:
        parts = (self.username or self.email.split("@")[0]).split(".")
        if len(parts) >= 2:
            return (parts[0][:1] + parts[-1][:1]).upper()
        return (self.username or self.email)[:2].upper()


# --- Phase 3 — past-paper ingestion ---


class PastPaper(db.Model):
    __tablename__ = "past_papers"
    __table_args__ = (
        UniqueConstraint(
            "syllabus_id", "paper_id", "session_id", "variant", name="uq_pp_full"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    syllabus_id = db.Column(db.Integer, db.ForeignKey("syllabi.id"), nullable=False)
    paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    variant = db.Column(db.Integer, nullable=False)  # 1, 2, 3
    source_pdf_path = db.Column(db.String(512), nullable=False)
    formula_sheet_ref = db.Column(db.String(512), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    syllabus = db.relationship("Syllabus")
    paper = db.relationship("Paper", back_populates="past_papers")
    session = db.relationship("Session")


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    past_paper_id = db.Column(db.Integer, db.ForeignKey("past_papers.id"), nullable=False)
    question_number = db.Column(db.Integer, nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=True)
    body_html = db.Column(db.Text, nullable=False, default="")
    images = db.Column(JSON, nullable=True)  # list of relative paths under /data/past-papers/
    marks_total = db.Column(db.Integer, nullable=True)
    difficulty = db.Column(db.String(16), nullable=True)  # easy/medium/hard
    extraction_status = db.Column(
        db.String(24), default="auto", nullable=False
    )  # auto / admin_approved / admin_edited

    past_paper = db.relationship("PastPaper")
    topic = db.relationship("Topic")
    subparts = db.relationship("SubPart", back_populates="question", cascade="all, delete-orphan")


class SubPart(db.Model):
    __tablename__ = "subparts"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    letter = db.Column(db.String(16), nullable=False)  # a, b, c, a(i), a(ii), b(iii)
    body_html = db.Column(db.Text, nullable=False, default="")
    answer_schema = db.Column(
        db.String(16), default="scalar", nullable=False
    )  # scalar / multi_cell / mcq / graphical
    correct_answer = db.Column(JSON, nullable=True)  # scalar value, array for multi_cell, list of valid mcq IDs
    mcq_choices = db.Column(JSON, nullable=True)  # [{"id":"A","html":"..."}] when answer_schema='mcq'
    canonical_method = db.Column(db.Text, nullable=True)
    marking_alternatives = db.Column(JSON, nullable=True)  # parsed Partial Marks column
    marks = db.Column(db.Integer, nullable=True)

    question = db.relationship("Question", back_populates="subparts")


# --- Phase 4 + 5 — attempts ---


class Attempt(db.Model):
    __tablename__ = "attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subpart_id = db.Column(db.Integer, db.ForeignKey("subparts.id"), nullable=False)
    submitted_answer = db.Column(JSON, nullable=True)
    working_photo_path = db.Column(db.String(512), nullable=True)  # Phase 5
    ocr_transcript = db.Column(db.Text, nullable=True)  # Phase 5
    verdict = db.Column(
        db.String(24), nullable=True
    )  # correct_optimal / correct_suboptimal / incorrect
    error_tags = db.Column(JSON, nullable=True)
    diagnostic_feedback_html = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


# --- Phase 6 — revision + learning style ---


class RevisionNote(db.Model):
    __tablename__ = "revision_notes"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", "style_used", name="uq_revnote_ut_style"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    generated_content_html = db.Column(db.Text, nullable=False)
    style_used = db.Column(db.String(32), nullable=False)
    cache_key = db.Column(db.String(64), nullable=False)  # hash of error-profile snapshot
    generated_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


# --- Phase 7 — error profile ---


class ErrorProfile(db.Model):
    __tablename__ = "error_profiles"
    __table_args__ = (UniqueConstraint("user_id", "topic_id", name="uq_ep_user_topic"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    count = db.Column(db.Integer, default=0, nullable=False)
    weight = db.Column(db.Float, default=0.0, nullable=False)
    last_seen = db.Column(db.DateTime, default=_utcnow, nullable=False)


# --- Phase 8 — rate limit ---


class RateLimit(db.Model):
    __tablename__ = "rate_limits"
    __table_args__ = (
        UniqueConstraint("user_id", "day", "endpoint", name="uq_rl_user_day_endpoint"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    day = db.Column(db.Date, nullable=False)
    endpoint = db.Column(db.String(64), nullable=False)
    count = db.Column(db.Integer, default=0, nullable=False)


# --- Phase 9 — user-curated revision list ---
#
# Distinct from RevisionNote (which caches LLM-generated re-explanations) and
# from ErrorProfile (which drives auto-priority). This table lets a student
# bookmark topics from /notes for personal review, mark them done, and remove
# them — i.e. a manual study queue independent of error-profile heuristics.


class RevisionListItem(db.Model):
    __tablename__ = "revision_list_items"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_revlist_user_topic"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    # Nullable so a row represents "in list, pending"; setting completed_at
    # marks it done while keeping it visible (with strikethrough). Removing
    # the row deletes the bookmark entirely.
    completed_at = db.Column(db.DateTime, nullable=True)
