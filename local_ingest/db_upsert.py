"""Database upserts. Uses the main app's SQLAlchemy models so we write to
exactly the same rows the web service reads. Idempotent — re-running the
ingestion on the same paper updates bodies/answers in place.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from extensions import db
from models import (
    Paper,
    PastPaper,
    Question,
    Session as SessionRow,
    SubPart,
    Syllabus,
    Topic,
)

from local_ingest.extract import PaperMeta

log = logging.getLogger(__name__)


def _syllabus(code: str) -> Syllabus | None:
    return Syllabus.query.filter_by(code=code).first()


def _paper(syllabus_id: int, number: int) -> Paper | None:
    return Paper.query.filter_by(syllabus_id=syllabus_id, number=number).first()


def _session(year: int, series: str) -> SessionRow:
    row = SessionRow.query.filter_by(year=year, series=series).first()
    if row is None:
        row = SessionRow(year=year, series=series)
        db.session.add(row)
        db.session.flush()
    return row


def upsert_past_paper(meta: PaperMeta, ms_path: Path | None) -> PastPaper | None:
    """Upserts PastPaper keyed on (syllabus, paper, session, variant)."""
    syllabus = _syllabus(meta.syllabus)
    if syllabus is None:
        log.warning("syllabus %s not seeded — skipping %s", meta.syllabus, meta.path.name)
        return None
    paper = _paper(syllabus.id, meta.paper_number)
    if paper is None:
        log.warning(
            "paper P%d not seeded for syllabus %s — skipping %s",
            meta.paper_number, meta.syllabus, meta.path.name,
        )
        return None
    sess = _session(meta.full_year, meta.series)

    row = PastPaper.query.filter_by(
        syllabus_id=syllabus.id,
        paper_id=paper.id,
        session_id=sess.id,
        variant=meta.variant_number,
    ).first()
    if row is None:
        row = PastPaper(
            syllabus_id=syllabus.id,
            paper_id=paper.id,
            session_id=sess.id,
            variant=meta.variant_number,
            source_pdf_path=str(meta.path),
            formula_sheet_ref=str(ms_path) if ms_path else "",
        )
        db.session.add(row)
        db.session.flush()
    else:
        row.source_pdf_path = str(meta.path)
        row.formula_sheet_ref = str(ms_path) if ms_path else row.formula_sheet_ref
    return row


def _build_body_html(cleaned: dict, image_files: list[str], media_prefix: str) -> str:
    """Assembles the full question body (stem + diagrams) for storage on
    Question.body_html. Subparts store their own individual body_html so the
    Exercise page can render each with its own input field."""
    stem = cleaned.get("stem_html", "") or ""
    imgs_html = ""
    for fname in image_files:
        src = f"/media/past-papers/_images/{media_prefix}/{fname}"
        imgs_html += f'<p><img src="{src}" alt="diagram" class="paper-img"></p>'
    return stem + imgs_html


def _infer_answer_schema(input_type: str | None) -> str:
    """Maps the cleanup layer's input_type to our DB enum."""
    if input_type in ("scalar", "mcq", "multi_cell", "graphical", "none"):
        return input_type
    return "scalar"


def upsert_question(
    past_paper: PastPaper,
    raw_q: dict,
    cleaned: dict,
    ms_answers: dict[str, dict],
    topic_id: int | None,
    image_files: list[str],
    media_prefix: str,
) -> Question:
    """Upserts Question + its SubParts. Keyed on (past_paper_id, question_number)."""
    qnum = int(raw_q["q"])

    # Precompute the question-level body (stem + diagrams).
    q_body_html = _build_body_html(cleaned, image_files, media_prefix)

    q_row = Question.query.filter_by(
        past_paper_id=past_paper.id, question_number=qnum
    ).first()
    if q_row is None:
        q_row = Question(
            past_paper_id=past_paper.id,
            question_number=qnum,
            topic_id=topic_id,
            body_html=q_body_html,
            images=image_files or None,
            marks_total=cleaned.get("total_marks") or raw_q.get("total_marks"),
            extraction_status="admin_approved",   # local run, trusted
        )
        db.session.add(q_row)
        db.session.flush()
    else:
        q_row.body_html = q_body_html
        q_row.images = image_files or q_row.images
        q_row.marks_total = (
            cleaned.get("total_marks") or raw_q.get("total_marks") or q_row.marks_total
        )
        if topic_id and q_row.topic_id is None:
            q_row.topic_id = topic_id
        q_row.extraction_status = "admin_approved"

    # Upsert subparts. We do a simple delete-and-recreate because the letter
    # structure can differ between runs (the cleanup layer may re-nest things)
    # and there are no foreign keys pointing at SubPart.id for a fresh run.
    # If an Attempt row ever references a SubPart whose letter changes, we
    # lose that Attempt — acceptable at this stage (no real attempts yet).
    SubPart.query.filter_by(question_id=q_row.id).delete()

    for sp in cleaned.get("subparts", []):
        letter = sp.get("letter", "a")
        body_html = sp.get("body_html", "")
        schema = _infer_answer_schema(sp.get("input_type"))
        input_count = sp.get("input_count") or 1
        marks = sp.get("marks")

        # Pull the MS answer at the deepest matching level.
        # First try the full dotted key e.g. "1(a)(i)" → MS key "1(a)(i)"
        ms_key = _subpart_to_ms_key(qnum, letter)
        ms_row = ms_answers.get(ms_key)
        # Fall back to shallower match.
        if ms_row is None and "(" in letter:
            parent_letter = letter.split("(")[0]
            ms_key_parent = _subpart_to_ms_key(qnum, parent_letter)
            ms_row = ms_answers.get(ms_key_parent)
        if ms_row is None:
            ms_row = ms_answers.get(str(qnum))

        correct_answer: Any = None
        marking_alts: list = []
        if ms_row:
            guidance = ms_row.get("guidance") or ""
            # If the MS says this answer is a diagram/plot, override the
            # cleanup layer's guess to "graphical" and leave correct_answer
            # null — there's nothing to auto-mark.
            if ms_row.get("is_diagram"):
                schema = "graphical"
                if guidance:
                    marking_alts = [{"gate": "diagram_rubric", "condition":
                                     (ms_row.get("answer") or "") + " " + guidance}]
            else:
                correct_answer = ms_row.get("answer") or None
                if guidance:
                    marking_alts = [{"gate": "guidance", "condition": guidance}]
            if marks is None and ms_row.get("marks"):
                marks = ms_row["marks"]

        new_sp = SubPart(
            question_id=q_row.id,
            letter=letter,
            body_html=body_html,
            answer_schema=schema,
            correct_answer=correct_answer,
            mcq_choices=sp.get("mcq_choices"),
            marking_alternatives=marking_alts,
            marks=marks,
        )
        db.session.add(new_sp)

    db.session.commit()
    return q_row


def _subpart_to_ms_key(qnum: int, letter: str) -> str:
    """Translate our internal 'a' / 'a(i)' letter form to the MS key format
    emitted by ms_parse.parse_ms ('1', '1(a)', '1(a)(i)')."""
    if not letter or letter == "a" and qnum == qnum:  # trivial single-subpart
        # We can't easily tell if this is a top-level "1" vs "1(a)" — try (a) first.
        return f"{qnum}({letter})"
    # letter may be "a", "b(i)", "a(ii)" etc.
    if "(" in letter:
        outer, rest = letter.split("(", 1)
        return f"{qnum}({outer})({rest}"
    return f"{qnum}({letter})"
