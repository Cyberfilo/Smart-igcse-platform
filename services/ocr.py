"""Handwriting OCR + diagnostic feedback (Phase 5). Gated by FEATURE_OCR env
flag per plan.md risk #1 — ships OFF until the parallel prototype returns
GREEN (.claude/state/phase-5-feasibility.md)."""
from __future__ import annotations

import base64
import json
from typing import Any

from services.openai_client import VISION_MODEL, feature_flag, get_client

SYSTEM_PROMPT = """You are an IGCSE Mathematics exam marker. You are shown:
1. The sub-part question body.
2. The canonical method the marking scheme expects.
3. Marking scheme alternatives (e.g. oe / FT / nfww gates).
4. A photo of the student's handwritten working.

Transcribe the working, then judge against the marking scheme. Return strict JSON:

{
  "transcript": "<student working as plain text, preserving line breaks>",
  "steps": [{"line":"<text>", "valid":true|false, "note":"<optional>"}],
  "verdict": "correct_optimal" | "correct_suboptimal" | "incorrect",
  "suggested_correction": "<plain-text fix if verdict != correct_optimal, else ''>",
  "error_tags": ["arithmetic_slip"|"wrong_method"|"sign_error"|"units_missed"|"algebraic_error"|"other"]
}

correct_optimal = right answer + method that matches canonical.
correct_suboptimal = right answer but a valid alternative method (mark it gently, soft-notice "faster way" available).
incorrect = wrong answer OR right answer by accident with invalid method."""


def _stub_verdict(submitted_answer: Any, correct: Any) -> dict[str, Any]:
    """Deterministic stub used when FEATURE_OCR is off. Gives the UI something
    to render so the flow can be developed without live vision calls."""
    match_ok = str(submitted_answer).strip().lower() == str(correct).strip().lower()
    return {
        "transcript": "(OCR disabled — set FEATURE_OCR=1 after Phase 5 prototype GREEN)",
        "steps": [],
        "verdict": "correct_optimal" if match_ok else "incorrect",
        "suggested_correction": "" if match_ok else f"Expected: {correct}",
        "error_tags": [] if match_ok else ["other"],
    }


def diagnose(
    photo_bytes: bytes,
    subpart_body: str,
    canonical_method: str | None,
    marking_alternatives: Any,
    correct_answer: Any,
    submitted_answer: Any,
) -> dict[str, Any]:
    """Returns verdict payload per SYSTEM_PROMPT schema. Falls back to stub
    when FEATURE_OCR is off."""
    if not feature_flag("FEATURE_OCR"):
        return _stub_verdict(submitted_answer, correct_answer)

    image_b64 = base64.b64encode(photo_bytes).decode("ascii")
    user_content = [
        {
            "type": "text",
            "text": (
                f"SUBPART:\n{subpart_body}\n\n"
                f"CANONICAL_METHOD:\n{canonical_method or '(not supplied)'}\n\n"
                f"MARKING_ALTERNATIVES:\n{json.dumps(marking_alternatives)}\n\n"
                f"CORRECT_ANSWER:\n{correct_answer}\n\n"
                f"STUDENT_SUBMITTED_ANSWER:\n{submitted_answer}"
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
        },
    ]
    client = get_client()
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, IndexError, AttributeError):
        return _stub_verdict(submitted_answer, correct_answer)
