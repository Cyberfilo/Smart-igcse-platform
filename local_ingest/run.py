"""Local ingestion orchestrator.

Runs on the dev machine, writes to Railway Postgres via DATABASE_URL.

Usage:
    # pilot — one paper, verify quality
    python -m local_ingest.run past_papers/ --limit 1

    # full run
    python -m local_ingest.run past_papers/

    # single syllabus
    python -m local_ingest.run past_papers/ --syllabus 0580

    # skip already-ingested (by default it re-runs everything idempotently)
    python -m local_ingest.run past_papers/ --skip-existing

Pre-reqs:
    export DATABASE_URL='postgresql://…@shinkansen.proxy.rlwy.net:PORT/railway'
    export OPENAI_API_KEY=…                  (global env usually has this)
    export SECRET_KEY=dev                    (Config.validate() needs it)
    export UPLOAD_DIR=/tmp/ignored           (not used locally)
    export PAST_PAPERS_DIR=./past_papers     (where the PDFs live)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Ensure the app package is importable when this module runs as __main__.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# App config/env. We use a lightweight app context so SQLAlchemy sessions work.
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("UPLOAD_DIR", "/tmp/local-ingest-uploads")
os.environ.setdefault("PAST_PAPERS_DIR", "./past_papers")

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import PastPaper, Question, SubPart, Syllabus, Topic  # noqa: E402

from local_ingest.cleanup import cleanup_question  # noqa: E402
from local_ingest.db_upsert import upsert_past_paper, upsert_question  # noqa: E402
from local_ingest.extract import (  # noqa: E402
    PaperMeta,
    crop_question_images,
    parse_filename,
    parse_qp,
)
from local_ingest.ms_parse import parse_ms  # noqa: E402
from local_ingest.topic_tag import tag_topic  # noqa: E402

log = logging.getLogger("local_ingest")

IMAGES_DIR = Path(__file__).resolve().parent / "images"


def find_pairs(root: Path) -> list[tuple[PaperMeta, PaperMeta | None]]:
    """Walks root/**/*.pdf, groups by (syllabus, session, year, variant),
    returns [(qp_meta, ms_meta_or_None)] pairs sorted by key."""
    by_key: dict[str, dict[str, PaperMeta]] = defaultdict(dict)
    for pdf in root.rglob("*.pdf"):
        # Skip macOS junk zip leftovers if they snuck in.
        if pdf.name.startswith("._") or "__MACOSX" in pdf.parts:
            continue
        meta = parse_filename(pdf)
        if meta is None or meta.type not in ("qp", "ms"):
            continue
        by_key[meta.pair_key][meta.type] = meta

    out: list[tuple[PaperMeta, PaperMeta | None]] = []
    for key, pair in sorted(by_key.items()):
        qp = pair.get("qp")
        ms = pair.get("ms")
        if qp is None:
            log.warning("MS without QP: %s", key)
            continue
        out.append((qp, ms))
    return out


def _media_prefix(meta: PaperMeta) -> str:
    """Prefix used both on the local image filename namespace and in the
    /media/past-papers/_images/<prefix>/ URL served from Railway's volume."""
    series_clean = meta.series.replace("/", "")
    return f"{meta.syllabus}/{meta.full_year}-{series_clean}/p{meta.paper_number}v{meta.variant_number}"


def process_pair(qp_meta: PaperMeta, ms_meta: PaperMeta | None, skip_existing: bool) -> int:
    """Returns the number of questions ingested for this pair."""
    paper_id = qp_meta.pair_key
    log.info("→ %s  qp=%s  ms=%s", paper_id, qp_meta.path.name, ms_meta.path.name if ms_meta else "(none)")

    pp = upsert_past_paper(qp_meta, ms_meta.path if ms_meta else None)
    if pp is None:
        return 0

    if skip_existing and Question.query.filter_by(past_paper_id=pp.id).count() > 0:
        log.info("  skip — already has questions in DB")
        return 0

    t0 = time.time()
    raw_questions = parse_qp(qp_meta.path)
    log.info("  parse_qp: %d questions in %.1fs", len(raw_questions), time.time() - t0)

    if not raw_questions:
        log.warning("  no questions extracted")
        return 0

    # Image directory: local first, uploaded to Railway volume at run end.
    image_dir = IMAGES_DIR / _media_prefix(qp_meta)
    t0 = time.time()
    crop_question_images(qp_meta.path, raw_questions, image_dir, paper_id)
    log.info("  image cropping in %.1fs", time.time() - t0)

    ms_answers = {}
    if ms_meta:
        t0 = time.time()
        ms_answers = parse_ms(ms_meta.path)
        log.info("  parse_ms: %d answer rows in %.1fs", len(ms_answers), time.time() - t0)

    # Topic list for this syllabus, passed into the tagger per question.
    syllabus = Syllabus.query.filter_by(code=qp_meta.syllabus).first()
    topics = (
        Topic.query.filter_by(syllabus_id=syllabus.id).order_by(Topic.number).all()
        if syllabus
        else []
    )
    topic_list = [
        {"id": t.id, "name": t.name, "syllabus_ref": t.syllabus_ref} for t in topics
    ]

    media_prefix = _media_prefix(qp_meta)

    # Parallelise the cleanup + tag calls (I/O bound on OpenAI) across questions
    # in this paper. DB writes stay sequential — SQLAlchemy session isn't thread-safe.
    def _clean_and_tag(raw_q: dict) -> tuple[dict, dict, int | None]:
        cleaned = cleanup_question(raw_q, qp_meta.path)
        if cleaned is None:
            cleaned = {
                "stem_html": f"<p>{raw_q.get('stem', '')}</p>",
                "subparts": [
                    {"letter": "a", "body_html": f"<p>{raw_q.get('stem', '')}</p>",
                     "input_type": "scalar", "input_count": 1, "mcq_choices": None,
                     "marks": raw_q.get("total_marks")}
                ],
                "total_marks": raw_q.get("total_marks"),
            }
        combined = cleaned.get("stem_html", "") + " ".join(
            sp.get("body_html", "") for sp in cleaned.get("subparts", [])
        )
        topic_id = tag_topic(combined, topic_list)
        return raw_q, cleaned, topic_id

    t_batch = time.time()
    results: list[tuple[dict, dict, int | None]] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for item in pool.map(_clean_and_tag, raw_questions):
            results.append(item)
    log.info("  cleaned %d questions in %.1fs", len(results), time.time() - t_batch)

    done = 0
    for raw_q, cleaned, topic_id in results:
        try:
            upsert_question(
                pp, raw_q, cleaned, ms_answers, topic_id,
                raw_q.get("image_files", []) or [], media_prefix,
            )
            done += 1
        except Exception:
            log.exception("  upsert failed for Q%s", raw_q["q"])
            db.session.rollback()
    return done


def configure_logging(log_path: Path) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    file_handler = logging.FileHandler(log_path, mode="a")
    file_handler.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers = [stream, file_handler]
    root.setLevel(logging.INFO)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local CAIE past-paper ingestion")
    parser.add_argument("root", type=Path, help="Folder containing past-paper PDFs")
    parser.add_argument("--syllabus", choices=["0580", "0654"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip papers that already have questions in the DB.")
    parser.add_argument("--log", type=Path,
                        default=Path(__file__).resolve().parent / "ingest.log")
    args = parser.parse_args(argv)

    configure_logging(args.log)

    if not args.root.exists():
        log.error("root folder not found: %s", args.root)
        return 1

    app = create_app()
    with app.app_context():
        pairs = find_pairs(args.root)
        if args.syllabus:
            pairs = [p for p in pairs if p[0].syllabus == args.syllabus]
        if args.limit:
            pairs = pairs[: args.limit]
        log.info("%d pair(s) to process", len(pairs))

        t0 = time.time()
        total_q = 0
        for idx, (qp, ms) in enumerate(pairs, 1):
            log.info("[%d/%d]", idx, len(pairs))
            try:
                total_q += process_pair(qp, ms, args.skip_existing)
            except Exception:
                log.exception("failure on %s", qp.path.name)
                db.session.rollback()
        log.info(
            "done — %d questions across %d papers in %.1fs",
            total_q, len(pairs), time.time() - t0,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
