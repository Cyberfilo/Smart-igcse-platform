"""Past-paper PDF ingestion (Phase 3 — real path).

Two-stage pipeline:
  1. extract_questions_from_pdf() — pymupdf-based text + image extraction.
     No LLM calls. Segments a QP into Question/SubPart structures by font-size
     transitions (Cambridge uses 12pt Arial Bold for question numbers, 11pt
     Regular for body).
  2. The marking scheme is parsed separately by services/marking_scheme.py
     using one vision call per MS PDF for the 'Partial Marks' column.

Topic tagging (text-only GPT) lives in tag_topic(); called per-question.

Gated by FEATURE_INGESTION for topic tagging only — extraction always runs.
"""
from __future__ import annotations

import io
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from services.openai_client import DEFAULT_MODEL, feature_flag, get_client


# ── Data classes — mirror schema in models.py ──


@dataclass
class ExtractedSubPart:
    letter: str
    body_html: str
    answer_schema: str = "scalar"
    correct_answer: Any = None
    mcq_choices: list[dict[str, Any]] | None = None
    marking_alternatives: list[dict[str, Any]] = field(default_factory=list)
    marks: int | None = None


@dataclass
class ExtractedQuestion:
    question_number: int
    topic_guess: str | None
    body_html: str
    marks_total: int | None
    images: list[str]
    subparts: list[ExtractedSubPart]


# ── Filename parser — Cambridge convention ──

_FNAME_RE = re.compile(
    r"^(?P<syllabus>\d{4})_"
    r"(?P<series>[msw])(?P<yy>\d{2})_"
    r"(?P<kind>qp|ms)_"
    r"(?P<paper>\d)(?P<variant>\d)"
    r"\.pdf$",
    re.IGNORECASE,
)

SERIES_CODE_TO_NAME = {"m": "F/M", "s": "M/J", "w": "O/N"}


@dataclass
class ParsedFilename:
    syllabus: str
    series: str  # 'F/M' / 'M/J' / 'O/N'
    year: int   # full 4-digit
    kind: str   # 'qp' or 'ms'
    paper: int
    variant: int


def parse_filename(name: str) -> ParsedFilename | None:
    m = _FNAME_RE.match(name)
    if not m:
        return None
    yy = int(m.group("yy"))
    # Cambridge 2-digit years: 00-79 → 2000s, 80-99 → 1900s. Safe bet for IGCSE era.
    year = 2000 + yy if yy < 80 else 1900 + yy
    return ParsedFilename(
        syllabus=m.group("syllabus"),
        series=SERIES_CODE_TO_NAME[m.group("series").lower()],
        year=year,
        kind=m.group("kind").lower(),
        paper=int(m.group("paper")),
        variant=int(m.group("variant")),
    )


# ── pymupdf extraction ──

# Empirically calibrated against 0580 Feb/March 2018 papers — the font is
# TimesNewRomanPS-BoldMT @ 11.0pt for question numbers AND page numbers, so
# size alone isn't enough — we also use y-range to exclude the page-number
# strip at the top of every page and the UCLES/copyright strip at the bottom.
QNUM_FONT_SIZE_MIN = 11.0
BOLD_FLAG = 16              # bit in span.flags indicating bold (pymupdf convention)

# Page-range policy:
#   Page 0: cover — always skip (logo/syllabus/session banner, no question text).
#   Page 1+: question content starts here. Some 0580 variants have a formula
#            sheet on page 1 — our y-range filter keeps it out of the question
#            stream since formula-box text isn't bold integers at qnum y-positions.
#   Last page: often "Permission to reproduce…" + blank. Scanning it is cheap;
#              blank pages produce no spans, and the copyright page has no bold
#              monotonic digit sequence, so the monotone-check rejects anything.
FIRST_CONTENT_PAGE = 1
LAST_CONTENT_TAIL = 0

# Y-range inside a page (in PDF points; A4 portrait is 841.89 pt tall).
#   Top 50 pt: running header with printed page number — skip.
#   Bottom 40 pt: UCLES © + paper code + '[Turn over' — skip.
Y_HEADER_CUTOFF = 50.0
Y_FOOTER_MARGIN = 40.0

# IGCSE question numbers are 1..~30. Prevents random '1990' in a year from being
# misread as a question number.
MAX_QUESTION_NUMBER = 40

_QNUM_RE = re.compile(r"^\s*(\d{1,2})\s*$")  # a span whose only content is a small integer
_SUBPART_RE = re.compile(r"^\s*\(([a-z])\)\s*(.*)$", re.DOTALL)
_MARKS_RE = re.compile(r"\[\s*(\d+)\s*\]")


def _is_bold(span: dict) -> bool:
    """pymupdf exposes bold via font name OR the flags bitmap."""
    if span.get("flags", 0) & BOLD_FLAG:
        return True
    name = span.get("font", "").lower()
    return "bold" in name or "black" in name


def _content_page_range(doc: fitz.Document) -> range:
    n = doc.page_count
    first = min(FIRST_CONTENT_PAGE, max(0, n - 1))
    last = max(first + 1, n - LAST_CONTENT_TAIL)
    return range(first, last)


@dataclass
class _TextBlock:
    page: int
    y: float
    text: str
    is_qnum: bool  # True if this span is a bold integer (candidate question number)
    qnum_value: int | None  # parsed integer if is_qnum


def _iter_blocks(doc: fitz.Document) -> list[_TextBlock]:
    """Flatten all text spans across content pages into a reading-order stream,
    flagging bold-integer spans as question-number candidates.

    Filters applied:
      - Skip cover page (FIRST_CONTENT_PAGE=1)
      - Skip header strip (y < Y_HEADER_CUTOFF) — catches printed page numbers
      - Skip footer strip (y > page_height - Y_FOOTER_MARGIN) — catches UCLES
        copyright line and '[Turn over' markers
      - Require bold + size ≥ 11.0 + pure digit text for qnum candidates
    """
    out: list[_TextBlock] = []
    for pno in _content_page_range(doc):
        page = doc.load_page(pno)
        page_height = page.rect.height
        y_max = page_height - Y_FOOTER_MARGIN
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type", 0) != 0:  # 0=text, 1=image
                continue
            for line in block.get("lines", []):
                y = line.get("bbox", [0, 0, 0, 0])[1]
                # Y-range filter — excludes header page-number strip and footer copyright.
                if y < Y_HEADER_CUTOFF or y > y_max:
                    continue

                line_text = "".join(s.get("text", "") for s in line.get("spans", []))

                # Question-number detection: the line's first span is a small
                # bold integer on its own (with optional trailing whitespace
                # before the question body continues in the next span).
                is_qnum = False
                qnum_val: int | None = None
                spans = line.get("spans", [])
                if spans:
                    first = spans[0]
                    first_text = first.get("text", "").strip()
                    if (
                        _is_bold(first)
                        and first.get("size", 0) >= QNUM_FONT_SIZE_MIN
                        and first_text.isdigit()
                    ):
                        n = int(first_text)
                        if 1 <= n <= MAX_QUESTION_NUMBER:
                            is_qnum = True
                            qnum_val = n

                out.append(
                    _TextBlock(
                        page=pno, y=y, text=line_text, is_qnum=is_qnum, qnum_value=qnum_val
                    )
                )
    return out


def _extract_images(doc: fitz.Document, output_dir: Path, prefix: str) -> list[tuple[int, float, str]]:
    """Extract all embedded images from content pages. Returns list of
    (page_index, y_top, rel_path) so the caller can associate images with
    the nearest-preceding question marker."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[int, float, str]] = []
    seen_xrefs: set[int] = set()
    for pno in _content_page_range(doc):
        page = doc.load_page(pno)
        for img_idx, img_info in enumerate(page.get_images(full=True)):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                bbox_list = page.get_image_rects(xref) or page.get_image_bbox(xref)
            except Exception:
                continue
            bbox = bbox_list[0] if isinstance(bbox_list, list) and bbox_list else bbox_list
            try:
                y_top = float(bbox.y0) if hasattr(bbox, "y0") else 0.0
            except Exception:
                y_top = 0.0
            try:
                image_info = doc.extract_image(xref)
            except Exception:
                continue
            ext = image_info.get("ext", "png")
            data = image_info.get("image")
            if not data:
                continue
            fname = f"{prefix}_p{pno+1}_i{img_idx}.{ext}"
            full = output_dir / fname
            full.write_bytes(data)
            results.append((pno, y_top, fname))
    return results


def _split_subparts(body: str) -> list[ExtractedSubPart]:
    """Given a question body (already stripped of its question-number prefix),
    split into SubParts by '(a)(b)(c)...' markers at line starts.

    If no subpart markers exist, wrap the whole body as a single 'a' subpart —
    the schema always has at least one SubPart per Question.
    """
    # Find (a) (b) (c) at line starts. Use multiline regex.
    pattern = re.compile(r"(?:^|\n)\s*\(([a-z])\)", re.MULTILINE)
    matches = list(pattern.finditer(body))
    if not matches:
        return [_build_subpart("a", body)]

    subparts: list[ExtractedSubPart] = []
    for i, m in enumerate(matches):
        letter = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = body[start:end].strip()
        subparts.append(_build_subpart(letter, chunk))
    return subparts


def _build_subpart(letter: str, chunk: str) -> ExtractedSubPart:
    marks_match = _MARKS_RE.search(chunk)
    marks = int(marks_match.group(1)) if marks_match else None
    body_text = chunk.strip()
    # Strip the trailing [N] marker from displayed body to avoid duplication.
    if marks_match:
        body_text = (chunk[: marks_match.start()] + chunk[marks_match.end():]).strip()
    return ExtractedSubPart(
        letter=letter,
        body_html=_text_to_html(body_text),
        answer_schema="scalar",
        marks=marks,
    )


def _text_to_html(text: str) -> str:
    """Minimal text→HTML: paragraph breaks on blank lines, escape <>&."""
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", escaped) if p.strip()]
    if not paragraphs:
        return ""
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)


def _attach_image_tags(body_html: str, images: list[str], media_prefix: str) -> str:
    """Append <img> tags for each image attributed to this question/subpart.
    Served via /media/past-papers/<rel_path>."""
    if not images:
        return body_html
    tags = "".join(
        f'<p><img src="/media/past-papers/{media_prefix}/{fname}" '
        f'alt="diagram" class="paper-img"></p>'
        for fname in images
    )
    return body_html + tags


def extract_questions_from_pdf(
    pdf_path: str,
    image_output_dir: str | None = None,
    media_prefix: str = "",
) -> list[ExtractedQuestion]:
    """Parse a QP PDF into Question + SubPart dataclasses. No LLM calls in
    this function — that's the whole point of the hybrid approach.

    Arguments:
      pdf_path: absolute path to a question paper PDF.
      image_output_dir: where to save cropped images. If None, images are skipped.
      media_prefix: relative prefix used in <img src="/media/past-papers/…">.

    Returns [] if the PDF can't be opened. Raises no exceptions on parse
    weirdness — the admin review queue is the safety net.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []

    try:
        blocks = _iter_blocks(doc)
        images_with_pos: list[tuple[int, float, str]] = []
        if image_output_dir:
            images_with_pos = _extract_images(
                doc, Path(image_output_dir), prefix=Path(pdf_path).stem
            )

        # Segment blocks into questions.
        questions: list[tuple[int, list[_TextBlock]]] = []
        current_num: int | None = None
        current_blocks: list[_TextBlock] = []

        for b in blocks:
            if b.is_qnum and b.qnum_value is not None:
                # Monotone sanity check — question numbers should increase.
                if current_num is not None and b.qnum_value <= current_num:
                    # Out-of-order integer; probably not a question number.
                    # Treat as body text of current question.
                    current_blocks.append(b)
                    continue
                if current_num is not None:
                    questions.append((current_num, current_blocks))
                current_num = b.qnum_value
                # After a question-number line, keep the SAME line's text as body.
                remainder = b.text.strip()
                if remainder.isdigit():
                    # Line was just the number (body starts on next line).
                    current_blocks = []
                else:
                    # Strip leading number from text and keep remainder.
                    stripped = re.sub(r"^\s*\d+\s+", "", b.text, count=1)
                    current_blocks = [
                        _TextBlock(
                            page=b.page, y=b.y, text=stripped, is_qnum=False, qnum_value=None
                        )
                    ]
            else:
                if current_num is not None:
                    current_blocks.append(b)
        if current_num is not None:
            questions.append((current_num, current_blocks))

        # Assign images to questions by (page, y) — image belongs to the most
        # recent question boundary on or above that page+y.
        def image_owner(img_page: int, img_y: float) -> int | None:
            owner: int | None = None
            for qnum, qblocks in questions:
                if not qblocks:
                    continue
                first = qblocks[0]
                if first.page < img_page or (first.page == img_page and first.y <= img_y):
                    owner = qnum
                else:
                    break
            return owner

        qnum_to_images: dict[int, list[str]] = {}
        for img_page, img_y, fname in images_with_pos:
            owner = image_owner(img_page, img_y)
            if owner is not None:
                qnum_to_images.setdefault(owner, []).append(fname)

        # Build ExtractedQuestion objects.
        out: list[ExtractedQuestion] = []
        for qnum, qblocks in questions:
            body_text = "\n".join(b.text for b in qblocks).strip()
            subparts = _split_subparts(body_text)
            imgs = qnum_to_images.get(qnum, [])

            # If the question has any images, attach them to the first subpart's
            # body_html — that's where the diagram typically belongs visually.
            if imgs and subparts:
                subparts[0].body_html = _attach_image_tags(
                    subparts[0].body_html, imgs, media_prefix
                )

            marks_total = sum((sp.marks or 0) for sp in subparts) or None
            out.append(
                ExtractedQuestion(
                    question_number=qnum,
                    topic_guess=None,  # tag_topic() fills this in
                    body_html="",  # whole-question body stays in subparts
                    marks_total=marks_total,
                    images=imgs,
                    subparts=subparts,
                )
            )
        return out
    finally:
        doc.close()


# ── Topic tagging ──


def tag_topic(question_body_html: str, topic_list: list[dict[str, Any]]) -> int | None:
    """Given a question body and a list of {'id': int, 'name': str, 'syllabus_ref': str}
    topics for this syllabus, return the best-guess Topic.id or None.

    No-op when FEATURE_INGESTION is off (stub extraction never sets topic)."""
    if not feature_flag("FEATURE_INGESTION"):
        return None
    if not question_body_html or not topic_list:
        return None

    plain = re.sub(r"<[^>]+>", " ", question_body_html)[:800]
    topic_lines = "\n".join(
        f"{t['id']}: {t['name']}"
        + (f" ({t['syllabus_ref']})" if t.get("syllabus_ref") else "")
        for t in topic_list
    )
    try:
        client = get_client()
    except RuntimeError:
        return None

    try:
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify IGCSE past-paper questions to a topic. "
                        "Respond with ONLY the numeric topic id from the list — "
                        "no prose, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Topics:\n{topic_lines}\n\nQuestion:\n{plain}\n\nTopic id:",
                },
            ],
            temperature=0.0,
            max_tokens=8,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\d+", raw)
        if m:
            tid = int(m.group(0))
            if any(t["id"] == tid for t in topic_list):
                return tid
    except Exception:
        return None
    return None


# ── Legacy helpers kept for backward compat with single-paper admin upload ──


def save_uploaded_pdf(file_storage, target_dir: str) -> str:
    """Writes FileStorage under target_dir with a uuid filename, returns path."""
    os.makedirs(target_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.pdf"
    full_path = os.path.join(target_dir, fname)
    file_storage.save(full_path)
    return full_path
