"""Mark-scheme table extractor.

CAIE MS papers (2017+) use a 4-column table with visible borders:
    Question | Answer | Marks | Partial Marks / Guidance

pdfplumber's `extract_tables(vertical_strategy="lines", horizontal_strategy="lines")`
walks the border geometry, which is deterministic on typeset PDFs. Much more
reliable than heuristic text clustering, and way cheaper than GPT vision.

Keys in the returned dict look like: "1", "1(a)", "1(a)(i)".
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


MS_Q_KEY_RE = re.compile(
    r"^\d{1,2}(?:\([a-z]\))?(?:\([ivx]+\))?$",
    re.IGNORECASE,
)


def _normalise_key(q_cell: str) -> str | None:
    if not q_cell:
        return None
    cleaned = re.sub(r"\s+", "", q_cell)
    if not MS_Q_KEY_RE.match(cleaned):
        return None
    return cleaned.lower()


def parse_ms(pdf_path: Path) -> dict[str, dict]:
    """Returns {question_key: {"answer": str, "marks": int|None, "guidance": str}}."""
    answers: dict[str, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_y_tolerance": 5,
                }
            )
            for table in tables:
                if not table or len(table[0]) < 3:
                    continue
                for row in table:
                    # pdfplumber splits cells on every internal ruling line, so a
                    # visually 4-column 'Question | Answer | Marks | Partial Marks'
                    # layout often comes back as 12 cells — content cells at
                    # positions 0, 3, 6, 9 and empty spacer cells between.
                    # Treat the row as a sequence of non-empty values positionally.
                    non_empty = [(c or "").strip() for c in row if (c or "").strip()]
                    if not non_empty:
                        continue

                    q_cell = non_empty[0]
                    ans_cell = non_empty[1] if len(non_empty) > 1 else ""
                    marks_cell = non_empty[2] if len(non_empty) > 2 else ""
                    guide_cell = " ".join(non_empty[3:]) if len(non_empty) > 3 else ""

                    # Skip header rows.
                    if q_cell.lower() in ("question", "q", "part") or \
                            ans_cell.lower() in ("answer", "answers"):
                        continue

                    key = _normalise_key(q_cell)
                    if not key:
                        continue

                    try:
                        marks = int(re.search(r"\d+", marks_cell).group())
                    except (AttributeError, ValueError):
                        marks = None

                    # Flatten newlines inside cells — table extraction preserves
                    # wrapping that we don't want in the final answer text.
                    ans_flat = re.sub(r"\s*\n\s*", " ", ans_cell).strip()
                    guide_flat = re.sub(r"\s*\n\s*", " ", guide_cell).strip()

                    answers[key] = {
                        "answer": ans_flat,
                        "marks": marks,
                        "guidance": guide_flat,
                    }
    return answers
