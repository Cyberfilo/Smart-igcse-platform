"""Marking-scheme parser (Phase 3). One vision call per MS PDF.

Why vision (not text extraction): the `Partial Marks` column encodes method
marks and alternatives in dense shorthand — `M1`, `B1`, `oe` (or equivalent),
`nfww` (not from wrong working), `isw` (ignore subsequent working), `FT`
(follow through). The information is tabular and benefits from visual layout
context. Text extraction flattens the table and loses the mark-scheme gate →
answer relationship.

Gated by FEATURE_INGESTION. When off, returns {} so callers degrade to
correct_answer=None.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from services.openai_client import VISION_MODEL, feature_flag, get_client


# MS structure (from plan.md notes):
#  - Pages 1–5: boilerplate marking principles. Skip.
#  - Pages 6+: Question | Answer | Marks | Partial Marks table.
MS_FIRST_CONTENT_PAGE = 5   # 0-indexed — skip first 5 pages


MS_SYSTEM_PROMPT = """You are parsing a Cambridge IGCSE marking scheme.
The pages supplied contain a table with columns: Question | Answer | Marks | Partial Marks.

Return strict JSON, no prose, no markdown:

{
  "answers": [
    {
      "question_number": 1,
      "subpart_letter": "a",
      "correct_answer": "scalar value OR array for multi-cell OR null if graphical",
      "marks": 3,
      "marking_alternatives": [
        {"gate": "M1", "condition": "for substitution into P(1+r/100)^n",
         "oe": true, "nfww": false, "isw": false, "ft": false},
        {"gate": "B1", "condition": "for 2315.25 nfww",
         "oe": false, "nfww": true, "isw": false, "ft": false}
      ]
    }
  ]
}

Rules:
- One object per (question_number, subpart_letter). If no subparts, letter=''.
- Convention flags: oe='or equivalent', nfww='not from wrong working',
  isw='ignore subsequent working', ft='follow through'. Mark each boolean
  from the presence of those tokens in the Partial Marks cell.
- correct_answer: preserve the cell verbatim if scalar. For multi-cell table
  answers, return an array of cell strings. For 'mark position on diagram'
  type answers, return null (graphical).
- If a sub-part is purely a drawing/diagram answer, set correct_answer=null.
- Preserve symbolic answers as-is (e.g. \"x = 3 or x = -2\" stays a string)."""


def _render_ms_pages_to_jpegs(pdf_path: str, dpi: int = 150) -> list[bytes]:
    """Render content pages (page 6+) to JPEG bytes. Lower DPI keeps tokens down."""
    out: list[bytes] = []
    doc = fitz.open(pdf_path)
    try:
        for pno in range(MS_FIRST_CONTENT_PAGE, doc.page_count):
            page = doc.load_page(pno)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            jpeg_bytes = pix.tobytes("jpeg")
            out.append(jpeg_bytes)
    finally:
        doc.close()
    return out


def _stub_empty() -> dict:
    return {"answers": []}


def parse_marking_scheme(pdf_path: str) -> dict[tuple[int, str], dict[str, Any]]:
    """Returns {(question_number, subpart_letter): {correct_answer, marks,
    marking_alternatives}} for every answer row the vision model produced.

    Empty dict when FEATURE_INGESTION is off OR vision call fails.
    """
    if not feature_flag("FEATURE_INGESTION"):
        return {}

    try:
        pages = _render_ms_pages_to_jpegs(pdf_path)
    except Exception:
        return {}
    if not pages:
        return {}

    try:
        client = get_client()
    except RuntimeError:
        return {}

    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": "Extract every answer row from these pages as JSON."}
    ]
    for jpeg_bytes in pages:
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        user_content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        )

    try:
        resp = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": MS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return {}

    result: dict[tuple[int, str], dict[str, Any]] = {}
    for row in data.get("answers", []):
        qn = row.get("question_number")
        letter = (row.get("subpart_letter") or "").strip().lower()
        if qn is None:
            continue
        key = (int(qn), letter or "a")  # default empty letter to 'a' to match extractor
        result[key] = {
            "correct_answer": row.get("correct_answer"),
            "marks": row.get("marks"),
            "marking_alternatives": row.get("marking_alternatives") or [],
        }
    return result
