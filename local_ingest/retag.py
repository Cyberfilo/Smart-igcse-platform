"""Serial topic re-tagger. One call at a time, no concurrency — so the
150-topic prompt lands reliably even under tight OpenAI limits.

Targets only Question rows with topic_id IS NULL, which means running this
multiple times is idempotent: tagged questions are skipped automatically.
Progress committed every 10 questions so a crash mid-run loses at most 10
calls. Resumable by just re-invoking.

Usage:
    export DATABASE_URL=postgresql://…@shinkansen.proxy.rlwy.net:PORT/railway
    export OPENAI_API_KEY=…
    export SECRET_KEY=dev
    export UPLOAD_DIR=/tmp/x
    export PAST_PAPERS_DIR=./past_papers
    python -m local_ingest.retag --syllabus 0580
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("UPLOAD_DIR", "/tmp/local-ingest-uploads")
os.environ.setdefault("PAST_PAPERS_DIR", "./past_papers")

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import PastPaper, Question, SubPart, Syllabus, Topic  # noqa: E402

from local_ingest.topic_tag import tag_topic  # noqa: E402

log = logging.getLogger("retag")


def _build_topic_cache() -> dict[int, list[dict]]:
    """Build {syllabus_id: [{"id", "name", "syllabus_ref"}]} once so we're
    not re-querying 150 topics per question."""
    cache: dict[int, list[dict]] = {}
    for syll in Syllabus.query.all():
        topics = Topic.query.filter_by(syllabus_id=syll.id).order_by(Topic.number).all()
        cache[syll.id] = [
            {"id": t.id, "name": t.name, "syllabus_ref": t.syllabus_ref}
            for t in topics
        ]
    return cache


def _question_text(q: Question) -> str:
    """Concatenate stem + all subpart bodies for the tagger. We favour the
    subpart text because Question.body_html is often empty by design — the
    cleanup layer stores content on the subparts."""
    parts: list[str] = []
    if q.body_html:
        parts.append(q.body_html)
    for sp in q.subparts:
        if sp.body_html:
            parts.append(sp.body_html)
    return " ".join(parts)[:2000]


def main() -> int:
    parser = argparse.ArgumentParser(description="Serial topic re-tagger")
    parser.add_argument("--syllabus", choices=["0580", "0654"])
    parser.add_argument("--limit", type=int, default=0,
                        help="Max questions to process (0 = all).")
    parser.add_argument("--commit-every", type=int, default=10,
                        help="Flush to DB every N successful tags.")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent OpenAI calls. 1 = serial (safest). 4-6 "
                             "is fine on recharged balance. >10 risks 429s.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    app = create_app()
    with app.app_context():
        cache = _build_topic_cache()
        # Question has no direct syllabus_id; resolve via PastPaper.
        base = (
            db.session.query(Question, PastPaper.syllabus_id)
            .join(PastPaper, Question.past_paper_id == PastPaper.id)
            .filter(Question.topic_id.is_(None))
            .order_by(Question.id)
        )
        if args.syllabus:
            syll = Syllabus.query.filter_by(code=args.syllabus).first()
            if syll is None:
                log.error("syllabus %s not found", args.syllabus)
                return 1
            base = base.filter(PastPaper.syllabus_id == syll.id)
        if args.limit:
            base = base.limit(args.limit)

        pending = base.all()
        total = len(pending)
        log.info("retagger: %d questions pending", total)
        if not total:
            return 0

        # Phase 1: build per-question payloads in the main thread (DB reads are
        # NOT thread-safe on a single session). Skip rows that have no topic
        # list or no text upfront.
        payloads: list[tuple[int, str, list[dict]]] = []
        skipped = 0
        id_to_question: dict[int, Question] = {}
        for q, syll_id in pending:
            topic_list = cache.get(syll_id, [])
            text = _question_text(q)
            if not topic_list or not text:
                skipped += 1
                continue
            payloads.append((q.id, text, topic_list))
            id_to_question[q.id] = q

        log.info("retagger: %d callable (%d skipped) · %d worker(s)",
                 len(payloads), skipped, args.workers)

        # Phase 2: fan out the OpenAI calls through a thread pool but receive
        # results IN ORDER via pool.map. Workers do no DB work — the main
        # thread serialises every UPDATE so SQLAlchemy's session stays safe.
        def _tag(p):
            q_id, text, topic_list = p
            return (q_id, tag_topic(text, topic_list))

        hits = 0
        misses = skipped
        committed_since = 0
        t0 = time.time()
        total_to_call = len(payloads)

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for i, (q_id, topic_id) in enumerate(pool.map(_tag, payloads), 1):
                if topic_id:
                    id_to_question[q_id].topic_id = topic_id
                    hits += 1
                    committed_since += 1
                    if committed_since >= args.commit_every:
                        db.session.commit()
                        committed_since = 0
                else:
                    misses += 1

                if i % 20 == 0 or i == total_to_call:
                    rate = i / max(0.01, time.time() - t0)
                    eta_min = (total_to_call - i) / max(0.01, rate) / 60
                    log.info(
                        "[%d/%d] hits=%d misses=%d  %.1f q/s  ETA %.1f min",
                        i, total_to_call, hits, misses, rate, eta_min,
                    )

        # Final flush.
        db.session.commit()
        log.info("done — %d tagged, %d still untagged in %.1fs",
                 hits, misses, time.time() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
