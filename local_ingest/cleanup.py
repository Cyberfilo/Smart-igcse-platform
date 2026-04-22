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


SYSTEM_PROMPT = """You are a meticulous Cambridge IGCSE textbook editor.

You are given:
- The full text of one Cambridge IGCSE exam question, extracted from the PDF
  (often with mathematical expressions split into isolated digit fragments).
- The rendered page image(s) showing exactly how the question appears on paper.
- Per-subpart HINT flags (slots / show_that) from the rule-based extractor
  — they tell you how many answer blanks there are and whether it's a
  "Show that…" prompt (which has no fill-in underscores at all).

Use the images to reconstruct math correctly, then output clean HTML.

Rules — follow strictly:
1. MATH: every mathematical expression goes in MathJax delimiters.
   - Inline: \\( ... \\)
   - Display (equations on their own line): \\[ ... \\]
   - Read the math from the IMAGE, not from the garbled text. The text is
     only there to anchor question wording.
2. NO ANSWER BLANKS: dotted fill-in lines ('.........') NEVER appear in your
   output. Remove them entirely. Remove placeholder '$' or ' cm² ' units
   that sit alone on an answer line — but if a blank carries a unit hint
   ("....... ml"), encode that unit as a hint on the corresponding input
   (NOT in body_html).
3. NO MARKS IN TEXT: '[2]', '[3 marks]' NEVER appear in body_html — put the
   integer in the 'marks' field instead.
4. NO HEADERS/FOOTERS: '© UCLES', '© Cambridge University Press & Assessment',
   '[Turn over]', paper codes ('0580/42/M/J/24'), page numbers, candidate
   barcodes, 'BLANK PAGE', 'Question X is printed on the next page' — all
   skipped.
5. SUBPART HIERARCHY: Cambridge uses (a)(b)(c) as peers and (i)(ii)(iii) as
   children. In the JSON, use flat dotted letters:
     top-level letter subparts:   "a", "b", "c"
     nested roman subparts:       "a(i)", "a(ii)", "b(i)", "b(ii)", …
6. INPUT TYPE per leaf subpart (what the student actually writes):
   - "scalar"     = one numeric/algebraic answer (most common)
   - "multi_cell" = several blanks in ONE sub-part (e.g. "....... ml
                    ....... ml ....... ml" — three volumes to enter; or
                    table cells to complete). input_count = number of
                    blanks/cells the extractor hint says. If the hint is
                    > 1, use "multi_cell" even if you'd otherwise pick
                    scalar. Tables: complete the table → multi_cell.
   - "mcq"        = pick from labelled options (A/B/C/D). Populate mcq_choices.
                    Table-row MCQs: each table row is an option; the option
                    letter sits in the leftmost cell.
   - "graphical"  = answer is a drawing/plot: "draw the graph of …",
                    "plot these points", "sketch the curve", "mark the
                    position", "construct the perpendicular bisector",
                    "shade the region", "draw a best-fit line". These can't
                    be marked digitally — set input_count = 0.
   - "none"       = container with no direct input (e.g. "(a)" that wraps
                    "(i)(ii)(iii)"). input_count = 0.
7. "SHOW THAT…" sub-parts: when the hint says show_that=true, or the body
   starts with "Show that", set input_type="scalar" BUT input_count=0 — the
   student writes working in blank space, there's nothing to grade digitally.
   Preserve the full target statement (e.g. "Show that the probability is
   \\(\\frac{3}{38}\\).") in body_html.
8. PRESERVE WORDING: only fix formatting. Do not paraphrase, do not shorten.
9. UNICODE: use proper characters — ≤ ≥ ≠ ± × ÷ − (true minus) · × ° √
   π λ θ Ω μ → ⇌ ↑ ↓. For 0580 set-theory notation ξ is the universal set
   (Greek lower-case xi, U+03BE). A′ = A complement. Bold italic vectors
   like AB in geometry.
10. CHEMISTRY: subscripts/superscripts in formulas (H₂O, CO₂, H₂SO₄, Na⁺,
    Cu²⁺, CO₃²⁻) — use real Unicode sub/super characters, not HTML <sub>/
    <sup>, so they survive copy-paste. For half-equations / state symbols:
    "NaCl(s)", "CO₂(g)", "H₂O(l)", "H⁺(aq)".

Output JSON schema (strict — no prose, no markdown fences):

{
  "stem_html": "<p>Shared setup text, before (a). Empty string if none.</p>",
  "subparts": [
    {
      "letter": "a",
      "body_html": "<p>Clean question text with \\\\(math\\\\) in MathJax.</p>",
      "input_type": "scalar|multi_cell|mcq|graphical|none",
      "input_count": 1,
      "mcq_choices": [{"id": "A", "html": "..."}, ...] or null,
      "marks": 2
    }
  ],
  "total_marks": 7
}

If the raw question has no subparts, emit ONE subpart with letter='a'
carrying the whole question body."""


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
    """Flatten question+parts+subparts into an annotated prompt payload.
    Each leaf includes [slots=N] and [show_that] markers derived by the
    rule-based extractor — these are reliable hints for input_count + type."""
    def hints(leaf: dict) -> str:
        parts: list[str] = []
        slots = leaf.get("slot_count")
        if slots and slots > 1:
            parts.append(f"slots={slots}")
        if leaf.get("show_that"):
            parts.append("show_that")
        return f"  [{', '.join(parts)}]" if parts else ""

    lines: list[str] = []
    stem = raw_q.get("stem", "").strip()
    if stem:
        lines.append(f"STEM: {stem}")
    for p in raw_q.get("parts", []):
        ptext = p.get("text", "").strip()
        pmarks = p.get("marks")
        suffix = (f"  [{pmarks}]" if pmarks else "") + hints(p)
        lines.append(f"  {p['part']} {ptext}{suffix}")
        for s in p.get("subparts", []):
            stext = s.get("text", "").strip()
            smarks = s.get("marks")
            ssuffix = (f"  [{smarks}]" if smarks else "") + hints(s)
            lines.append(f"    {s['sub']} {stext}{ssuffix}")
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
