"""Past-paper ingestion runner (Phase 3 worker).

Walks $PAST_PAPERS_DIR for QP/MS pairs, extracts questions, populates the DB.
Designed to run as a Railway worker service (see RAILWAY.md §"Worker service")
OR locally with `python -m scripts.ingest_papers`.

Idempotent + resumable: every Question and SubPart is looked up by a natural
key before insert, so a crashed or restarted run picks up cleanly. Each
question commits independently, so interruption loses at most one question's
worth of work.

Logs to both stdout (captured by Railway) and $INGEST_LOG_PATH
(default: /data/ingest.log) so progress survives restarts.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Paper,
    PastPaper,
    Question,
    Session,
    SubPart,
    Syllabus,
    Topic,
)
from services.ingestion import (  # noqa: E402
    ExtractedQuestion,
    ParsedFilename,
    extract_questions_from_pdf,
    parse_filename,
    tag_topic,
)
from services.marking_scheme import parse_marking_scheme  # noqa: E402

log = logging.getLogger("ingest")


# ── Walker ──


def find_pdf_pairs(root: Path) -> list[tuple[ParsedFilename, Path, Path]]:
    """Walks root/**/qp/*.pdf, finds the matching ms by filename key.

    Returns (parsed_qp, qp_path, ms_path) tuples. Skips unpaired or malformed
    filenames (logged at WARNING).
    """
    pairs: list[tuple[ParsedFilename, Path, Path]] = []
    # Group QP + MS by (syllabus, series, year, paper, variant). Discover
    # all PDFs under qp/ and ms/ subdirs anywhere in the tree.
    by_key: dict[tuple, dict[str, Path]] = defaultdict(dict)
    for pdf in root.rglob("*.pdf"):
        parsed = parse_filename(pdf.name)
        if parsed is None:
            log.warning("skip unparseable filename: %s", pdf)
            continue
        key = (parsed.syllabus, parsed.series, parsed.year, parsed.paper, parsed.variant)
        by_key[key][parsed.kind] = pdf

    for key, kinds in sorted(by_key.items()):
        qp = kinds.get("qp")
        ms = kinds.get("ms")
        if qp is None:
            log.warning("no qp for key %s (ms=%s) — skipped", key, ms)
            continue
        parsed = parse_filename(qp.name)
        if parsed is None:
            continue
        if ms is None:
            log.warning("no ms for qp %s — proceeding without answers", qp.name)
        pairs.append((parsed, qp, ms or qp))  # fall through to qp as ms placeholder
    return pairs


# ── Upsert helpers ──


def upsert_session(year: int, series: str) -> Session:
    row = Session.query.filter_by(year=year, series=series).first()
    if row is None:
        row = Session(year=year, series=series)
        db.session.add(row)
        db.session.flush()
    return row


def get_syllabus(code: str) -> Syllabus | None:
    return Syllabus.query.filter_by(code=code).first()


def get_paper(syllabus_id: int, number: int) -> Paper | None:
    return Paper.query.filter_by(syllabus_id=syllabus_id, number=number).first()


def upsert_past_paper(
    syllabus_id: int,
    paper_id: int,
    session_id: int,
    variant: int,
    qp_path: str,
    ms_path: str,
) -> PastPaper:
    row = PastPaper.query.filter_by(
        syllabus_id=syllabus_id,
        paper_id=paper_id,
        session_id=session_id,
        variant=variant,
    ).first()
    if row is None:
        row = PastPaper(
            syllabus_id=syllabus_id,
            paper_id=paper_id,
            session_id=session_id,
            variant=variant,
            source_pdf_path=qp_path,
            formula_sheet_ref=ms_path,
        )
        db.session.add(row)
        db.session.flush()
    else:
        # Update paths in case the volume layout changed.
        row.source_pdf_path = qp_path
        row.formula_sheet_ref = ms_path
    return row


def upsert_question(past_paper_id: int, eq: ExtractedQuestion, topic_id: int | None) -> Question:
    q = Question.query.filter_by(
        past_paper_id=past_paper_id, question_number=eq.question_number
    ).first()
    if q is None:
        q = Question(
            past_paper_id=past_paper_id,
            question_number=eq.question_number,
            topic_id=topic_id,
            body_html=eq.body_html or "",
            images=eq.images,
            marks_total=eq.marks_total,
            extraction_status="auto",
        )
        db.session.add(q)
        db.session.flush()
    else:
        q.body_html = eq.body_html or q.body_html
        q.images = eq.images or q.images
        q.marks_total = eq.marks_total or q.marks_total
        if topic_id and q.topic_id is None:
            q.topic_id = topic_id
    return q


def upsert_subpart(question_id: int, sp_extract, ms_row: dict | None) -> SubPart:
    sp = SubPart.query.filter_by(question_id=question_id, letter=sp_extract.letter).first()
    if sp is None:
        sp = SubPart(
            question_id=question_id,
            letter=sp_extract.letter,
            body_html=sp_extract.body_html,
            answer_schema=sp_extract.answer_schema,
            correct_answer=(ms_row or {}).get("correct_answer") if ms_row else None,
            mcq_choices=sp_extract.mcq_choices,
            marking_alternatives=(ms_row or {}).get("marking_alternatives")
            or sp_extract.marking_alternatives
            or [],
            marks=(ms_row or {}).get("marks") or sp_extract.marks,
        )
        db.session.add(sp)
        db.session.flush()
    else:
        sp.body_html = sp_extract.body_html or sp.body_html
        if ms_row:
            if sp.correct_answer is None and ms_row.get("correct_answer") is not None:
                sp.correct_answer = ms_row["correct_answer"]
            if not sp.marking_alternatives and ms_row.get("marking_alternatives"):
                sp.marking_alternatives = ms_row["marking_alternatives"]
            if not sp.marks and ms_row.get("marks"):
                sp.marks = ms_row["marks"]
        if not sp.marks and sp_extract.marks:
            sp.marks = sp_extract.marks
    return sp


# ── Main loop ──


def process_pair(
    parsed: ParsedFilename,
    qp_path: Path,
    ms_path: Path,
    images_root: Path,
) -> int:
    """Process one qp+ms pair. Returns number of questions ingested (new or refreshed)."""
    syllabus = get_syllabus(parsed.syllabus)
    if syllabus is None:
        log.warning("syllabus %s not seeded — run scripts.seed_syllabi first", parsed.syllabus)
        return 0
    paper = get_paper(syllabus.id, parsed.paper)
    if paper is None:
        log.warning(
            "paper P%d not seeded for syllabus %s — skipping %s",
            parsed.paper, parsed.syllabus, qp_path.name,
        )
        return 0

    sess = upsert_session(parsed.year, parsed.series)
    pp = upsert_past_paper(
        syllabus_id=syllabus.id,
        paper_id=paper.id,
        session_id=sess.id,
        variant=parsed.variant,
        qp_path=str(qp_path),
        ms_path=str(ms_path) if ms_path != qp_path else "",
    )

    # Per-paper image directory under the past-papers volume.
    img_dir = (
        images_root
        / parsed.syllabus
        / f"{parsed.year}-{parsed.series.replace('/', '')}"
        / f"p{parsed.paper}v{parsed.variant}"
    )
    media_prefix = (
        f"{parsed.syllabus}/"
        f"{parsed.year}-{parsed.series.replace('/', '')}/"
        f"p{parsed.paper}v{parsed.variant}"
    )

    extracted = extract_questions_from_pdf(
        str(qp_path),
        image_output_dir=str(img_dir),
        media_prefix=media_prefix,
    )
    if not extracted:
        log.warning("no questions extracted from %s", qp_path.name)
        return 0

    # Parse MS once per pair. Empty dict if FEATURE_INGESTION off or vision fails.
    ms_answers = {}
    if ms_path != qp_path:
        ms_answers = parse_marking_scheme(str(ms_path))

    # Topic list for this syllabus — passed to tag_topic per question.
    topics = Topic.query.filter_by(syllabus_id=syllabus.id).order_by(Topic.number).all()
    topic_list = [
        {"id": t.id, "name": t.name, "syllabus_ref": t.syllabus_ref}
        for t in topics
    ]

    done = 0
    for eq in extracted:
        topic_id = tag_topic(
            " ".join(sp.body_html for sp in eq.subparts), topic_list
        )
        q = upsert_question(pp.id, eq, topic_id)
        for sp_extract in eq.subparts:
            key = (eq.question_number, sp_extract.letter)
            ms_row = ms_answers.get(key)
            upsert_subpart(q.id, sp_extract, ms_row)
        db.session.commit()
        done += 1
    return done


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    file_handler = logging.FileHandler(log_path, mode="a")
    file_handler.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers = [stream, file_handler]
    root.setLevel(logging.INFO)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest past-paper PDFs into the DB.")
    parser.add_argument(
        "--pilot", action="store_true",
        help="Ingest only one session (first match) — for testing the pipeline.",
    )
    parser.add_argument(
        "--syllabus", choices=["0580", "0654"], default=None,
        help="Restrict to a single syllabus code.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max qp/ms pairs to process (0 = no limit).",
    )
    args = parser.parse_args(argv)

    papers_root = Path(os.environ.get("PAST_PAPERS_DIR", "/data/past-papers"))
    log_path = Path(os.environ.get("INGEST_LOG_PATH", "/data/ingest.log"))
    configure_logging(log_path)

    log.info("ingest start — root=%s log=%s", papers_root, log_path)
    if not papers_root.exists():
        log.error("past-papers dir does not exist: %s", papers_root)
        return 1

    app = create_app()
    with app.app_context():
        pairs = find_pdf_pairs(papers_root)
        if args.syllabus:
            pairs = [p for p in pairs if p[0].syllabus == args.syllabus]
        if args.pilot:
            # Keep only the first matching session (same year+series) to bound the pilot.
            if pairs:
                first = pairs[0][0]
                pairs = [
                    p for p in pairs
                    if p[0].syllabus == first.syllabus
                    and p[0].year == first.year
                    and p[0].series == first.series
                ]
        if args.limit:
            pairs = pairs[: args.limit]

        log.info("%d qp/ms pairs to process", len(pairs))
        t0 = time.time()
        total_questions = 0
        images_root = Path(os.environ.get("PAST_PAPERS_DIR", "/data/past-papers")) / "_images"

        for idx, (parsed, qp, ms) in enumerate(pairs, 1):
            log.info(
                "[%d/%d] %s %d %s P%dV%d",
                idx, len(pairs), parsed.syllabus, parsed.year,
                parsed.series, parsed.paper, parsed.variant,
            )
            try:
                n = process_pair(parsed, qp, ms, images_root)
                total_questions += n
                log.info("  ingested %d questions (total=%d)", n, total_questions)
            except Exception:
                log.exception("failure on %s — continuing", qp.name)
                db.session.rollback()

        elapsed = time.time() - t0
        log.info(
            "ingest done — %d questions across %d papers in %.1fs",
            total_questions, len(pairs), elapsed,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
