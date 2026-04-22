"""Post-process sweep: reclassify "NOT TO SCALE + no question verb" questions
as graphical.

CAIE papers put the question INSIDE the diagram for geometry / similarity /
trig items. pdfplumber + vision cleanup can't recover the intended prompt
in those cases — the body_html ends up as a bag of floating labels like
"B 16 m NOT TO A 57° 32 m SCALE 19 m C 75° D". Those questions are
currently classified as `scalar` (because their subparts have numeric
answers in the MS), so they show up in the Exercise pool and render as
junk text to students.

This script finds questions where:
  1. The question body contains "NOT TO SCALE" (possibly scrambled OCR),
     AND
  2. Neither the question body nor any subpart body contains a real
     question verb (Find, Work out, Calculate, Show, Determine, Solve,
     Evaluate, Prove, Express, Write down, Give, State, Explain).
  3. At least one subpart is currently markable (scalar/mcq/multi_cell).

For matches, it flips every markable subpart to `graphical`, which makes
the Exercise pool skip the question entirely (see routes/pages.py —
`Question.subparts.any(SubPart.answer_schema.in_(("scalar","mcq")))`).

Dry-run by default. Pass --apply to commit. Always prints the per-question
list so the admin can eyeball before the change.

Run from dev machine against Railway Postgres (DATABASE_URL in env):

    DATABASE_URL='postgresql://...' python -m scripts.flag_graphical_not_to_scale
    DATABASE_URL='postgresql://...' python -m scripts.flag_graphical_not_to_scale --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Allow the script to be run via `python -m scripts.flag_graphical_not_to_scale`
# from the repo root without a Flask app context.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


# "NOT TO SCALE" as a literal string OR scrambled with arbitrary tokens
# between "NOT TO" and "SCALE" — handles the OCR case where diagram labels
# interleave with the annotation. Case-insensitive, single-line via DOTALL
# so newlines in body_html don't break it.
NOT_TO_SCALE_RE = re.compile(r"\bNOT\s+TO\b.{0,80}?\bSCALE\b", re.IGNORECASE | re.DOTALL)

# A "question verb" signals that somewhere in the prose the student is
# actually being asked to do something. If any of these appear in the
# question body OR in a subpart body, we do NOT flip — the real prompt
# exists, even if the surrounding text is messy.
QUESTION_VERBS_RE = re.compile(
    r"\b("
    r"find|work\s+out|calculate|show|determine|solve|evaluate|prove|"
    r"express|write\s+down|give|state|explain|how\s+many|what\s+is|"
    r"which\s+of|describe|complete|draw|construct|measure|estimate"
    r")\b",
    re.IGNORECASE,
)


def _strip_tags(html: str | None) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html)


def _has_question_verb(*html_chunks: str | None) -> bool:
    for chunk in html_chunks:
        if chunk and QUESTION_VERBS_RE.search(_strip_tags(chunk)):
            return True
    return False


def find_candidates(session: Session) -> list[dict]:
    """Return a list of questions that should be flipped to graphical."""
    rows = session.execute(text("""
        select q.id as qid,
               q.question_number,
               q.body_html as q_body,
               ss.year, ss.series, p.number as paper_num, pp.variant
        from questions q
        join past_papers pp on pp.id = q.past_paper_id
        join sessions ss    on ss.id = pp.session_id
        join papers p       on p.id  = pp.paper_id
        where q.body_html is not null
          and q.body_html ilike '%SCALE%'
    """)).fetchall()

    candidates: list[dict] = []
    for r in rows:
        q_body = r.q_body or ""
        if not NOT_TO_SCALE_RE.search(_strip_tags(q_body)):
            continue
        subparts = session.execute(text("""
            select id, letter, body_html, answer_schema
            from subparts
            where question_id = :qid
            order by letter
        """), {"qid": r.qid}).fetchall()

        markable_ids = [sp.id for sp in subparts if sp.answer_schema in ("scalar", "mcq", "multi_cell")]
        if not markable_ids:
            # Already graphical or container-only — nothing to flip.
            continue

        all_bodies = [q_body] + [sp.body_html for sp in subparts]
        if _has_question_verb(*all_bodies):
            continue

        candidates.append({
            "qid": r.qid,
            "paper_label": f"{r.year} {r.series} P{r.paper_num}V{r.variant} Q{r.question_number}",
            "subpart_ids": markable_ids,
            "stem_preview": _strip_tags(q_body)[:140].strip(),
        })
    return candidates


def apply_flips(session: Session, candidates: list[dict]) -> int:
    """Flip every markable subpart in `candidates` to answer_schema='graphical'.
    Returns number of subparts updated."""
    total = 0
    for c in candidates:
        for sp_id in c["subpart_ids"]:
            session.execute(
                text("update subparts set answer_schema = 'graphical' where id = :sid"),
                {"sid": sp_id},
            )
            total += 1
    session.commit()
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Commit the flips. Without this flag the script runs in dry-run mode.")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL env var not set", file=sys.stderr)
        return 2

    engine = create_engine(db_url)
    with Session(engine) as sess:
        candidates = find_candidates(sess)

        if not candidates:
            print("No candidates — nothing to flip.")
            return 0

        total_subparts = sum(len(c["subpart_ids"]) for c in candidates)
        print(f"Found {len(candidates)} question(s) — {total_subparts} subpart(s) to flip:\n")
        for c in candidates:
            ids = ",".join(str(s) for s in c["subpart_ids"])
            print(f"  qid={c['qid']:<5}  {c['paper_label']}  subparts=[{ids}]")
            print(f"    stem: {c['stem_preview']!r}\n")

        if not args.apply:
            print("Dry-run. Re-run with --apply to commit.")
            return 0

        n = apply_flips(sess, candidates)
        print(f"Flipped {n} subpart(s) to graphical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
