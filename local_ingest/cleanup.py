"""GPT-5.4 vision cleanup for extracted question bodies.

Why vision: pdfplumber gives us great page layout + reliable subpart detection,
but Cambridge typesets math by rasterising each glyph, so a fraction like
5/32 extracts as "5\n3\n2" — unrecoverable from text alone. GPT-5.4 gets
the question's page as an image alongside the raw text, so it can see what
the math SHOULD look like and emit clean MathJax.

Input: one question dict from extract.parse_qp + path to the QP PDF.
Output: {stem_html, subparts[{letter, body_html, input_type, input_count,
mcq_choices, marks}], total_marks} with LaTeX math, no dotted lines, proper
subpart hierarchy.

Cost: ~7K tokens input (page image at low detail + text) + ~800 tokens output
per question ≈ $0.025. For 2000 questions: ~$50. Pay for quality.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import fitz  # for page rendering
from openai import OpenAI

log = logging.getLogger(__name__)

CLEANUP_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")

# Render DPI for the page image. 144 gives legible math without blowing up
# the token cost; vision pricing is by image tiles, and 144 dpi on A4 keeps
# us in the 2-tile range.
RENDER_DPI = 144

_client: OpenAI | None = None


def _client_singleton() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


SYSTEM_PROMPT = """You are a meticulous IGCSE textbook editor.

You are given:
- The full text of one Cambridge IGCSE exam question, extracted from the PDF
  (often with mathematical expressions split into isolated digit fragments).
- The rendered page image(s) showing exactly how the question appears on paper.

Use the images to reconstruct math correctly, then output clean HTML.

Rules — follow strictly:
1. MATH: every mathematical expression goes in MathJax delimiters.
   - Inline: \\( ... \\)
   - Display (equations on their own line): \\[ ... \\]
   - Read the math from the IMAGE, not from the garbled text. The text is
     only there to anchor question wording.
2. NO ANSWER BLANKS: dotted fill-in lines ('.........') NEVER appear in your
   output. Remove them entirely. Remove placeholder '$' or ' cm² ' units
   that sit alone on an answer line.
3. NO MARKS IN TEXT: '[2]', '[3 marks]' NEVER appear in body_html — put the
   integer in the 'marks' field instead.
4. NO HEADERS/FOOTERS: '© UCLES', '[Turn over]', paper codes, page numbers,
   candidate barcodes — all skipped.
5. SUBPART HIERARCHY: Cambridge uses (a)(b)(c) as peers and (i)(ii)(iii) as
   children. In the JSON, use flat dotted letters:
     top-level letter subparts:   "a", "b", "c"
     nested roman subparts:       "a(i)", "a(ii)", "b(i)", "b(ii)", …
6. INPUT TYPE per leaf subpart:
   - "scalar"     = one numeric/algebraic answer (most common)
   - "mcq"        = pick from labelled options (A/B/C/D). Populate mcq_choices.
   - "multi_cell" = table / grid with multiple cells. input_count = cells.
   - "none"       = container with no direct input (e.g. "(a)" that wraps
                    "(i)(ii)(iii)"). input_count = 0.
7. PRESERVE WORDING: only fix formatting. Do not paraphrase, do not shorten.

Output JSON schema (strict — no prose, no markdown fences):

{
  "stem_html": "<p>Shared setup text, before (a). Empty string if none.</p>",
  "subparts": [
    {
      "letter": "a",
      "body_html": "<p>Clean question text with \\\\(math\\\\) in MathJax.</p>",
      "input_type": "scalar",
      "input_count": 1,
      "mcq_choices": null,
      "marks": 2
    }
  ],
  "total_marks": 7
}

If the raw question has no subparts, emit ONE subpart with letter='a' carrying
the whole question body."""


def _render_page_jpeg(pdf_path: Path, page_1indexed: int) -> bytes:
    """Render a single PDF page to JPEG bytes at RENDER_DPI."""
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_1indexed - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72), alpha=False)
        return pix.tobytes("jpeg")
    finally:
        doc.close()


def _render_raw_question(raw_q: dict) -> str:
    lines: list[str] = []
    stem = raw_q.get("stem", "").strip()
    if stem:
        lines.append(f"STEM: {stem}")
    for p in raw_q.get("parts", []):
        ptext = p.get("text", "").strip()
        pmarks = p.get("marks")
        lines.append(f"  {p['part']} {ptext}" + (f"  [{pmarks}]" if pmarks else ""))
        for s in p.get("subparts", []):
            stext = s.get("text", "").strip()
            smarks = s.get("marks")
            lines.append(f"    {s['sub']} {stext}" + (f"  [{smarks}]" if smarks else ""))
    return "\n".join(lines)


def cleanup_question(raw_q: dict, pdf_path: Path) -> dict | None:
    """Returns cleaned {stem_html, subparts[], total_marks} or None on failure."""
    raw_text = _render_raw_question(raw_q)
    pages = raw_q.get("pages") or []
    if not pages:
        log.warning("Q%s has no pages — skipping vision", raw_q.get("q"))
        return None

    # Build multi-modal user message: text prompt + page images.
    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Question number: {raw_q['q']}\n"
                f"Page(s): {pages}\n"
                f"Total marks (from PDF markup): {raw_q.get('total_marks') or 'unknown'}\n"
                f"Has diagram: {'yes' if raw_q.get('has_image') else 'no'}\n\n"
                f"Raw text extraction (use for wording, NOT for math):\n{raw_text}"
            ),
        }
    ]
    try:
        for p_idx in pages:
            jpeg = _render_page_jpeg(pdf_path, p_idx)
            b64 = base64.b64encode(jpeg).decode("ascii")
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "low",  # "low" = 85 tokens/image, plenty for math OCR
                    },
                }
            )
    except Exception:
        log.exception("page render failed for Q%s", raw_q.get("q"))
        return None

    try:
        client = _client_singleton()
        resp = client.chat.completions.create(
            model=CLEANUP_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        if not isinstance(data, dict) or "subparts" not in data:
            log.warning("cleanup returned malformed JSON for Q%s", raw_q.get("q"))
            return None
        return data
    except Exception:
        log.exception("cleanup_question failed for Q%s", raw_q.get("q"))
        return None
