"""Auto-marking for digital-input SubParts (Phase 4). No vision involved —
covers mcq and scalar answer schemas; multi_cell is an exact-array match."""
from __future__ import annotations

from typing import Any


def _normalise_scalar(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "")


def mark_mcq(submitted: Any, correct: Any) -> str:
    """correct is a list of valid choice IDs (multiple correct allowed)."""
    if submitted is None or correct is None:
        return "incorrect"
    sub = submitted if isinstance(submitted, list) else [submitted]
    correct_set = set(correct) if isinstance(correct, list) else {correct}
    return "correct_optimal" if set(sub) == correct_set else "incorrect"


def mark_scalar(submitted: Any, correct: Any) -> str:
    if _normalise_scalar(submitted) == _normalise_scalar(correct):
        return "correct_optimal"
    return "incorrect"


def mark_multi_cell(submitted: Any, correct: Any) -> str:
    if not isinstance(submitted, list) or not isinstance(correct, list):
        return "incorrect"
    if len(submitted) != len(correct):
        return "incorrect"
    for s, c in zip(submitted, correct):
        if _normalise_scalar(s) != _normalise_scalar(c):
            return "incorrect"
    return "correct_optimal"


def auto_mark(answer_schema: str, submitted: Any, correct: Any) -> str:
    """Return verdict: correct_optimal / correct_suboptimal / incorrect.
    suboptimal verdict only comes from OCR (Phase 5) — digital input gives no
    method evidence, so correctness is binary here."""
    if answer_schema == "mcq":
        return mark_mcq(submitted, correct)
    if answer_schema == "scalar":
        return mark_scalar(submitted, correct)
    if answer_schema == "multi_cell":
        return mark_multi_cell(submitted, correct)
    # graphical: cannot auto-mark, flag for manual
    return "incorrect"
