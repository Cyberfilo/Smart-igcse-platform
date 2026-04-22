"""CAIE past-paper PDF extractor.

Adapted from the reference implementation in ~/Downloads/ext/caie_extractor.py
(credit: the author's STRUCTURE.md analysis — page layout rules below).

Strategy:
- pdfplumber for text + positions (x-tolerance=2, y-tolerance=3 groups words
  into lines without over- or under-merging).
- Rule-based segmentation:
    top-level question `N`:  line-starting integer at x < 60
    letter subpart `(a)`:    pattern ^\([a-z]\)$ at indented x
    roman sub-subpart `(i)`: pattern ^\([ivx]+\)$ at deeper indent
    marks marker `[N]`:      \[\d+\] anywhere on the line
- pymupdf for image cropping (pdfplumber can't render).
- Diagram detection: page has raster images OR >30 vector path operations.

No LLM calls in this module — those happen in cleanup.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF — rendering only
import pdfplumber


# ── Filename ─────────────────────────────────────────────────────────────

FILENAME_RE = re.compile(
    r"^(?P<syllabus>\d{4})_(?P<session>[smw])(?P<year>\d{2})_"
    r"(?P<type>qp|ms)_(?P<variant>\d{2})\.pdf$",
    re.IGNORECASE,
)
SESSION_SERIES = {"s": "M/J", "w": "O/N", "m": "F/M"}


@dataclass
class PaperMeta:
    syllabus: str     # "0580"
    session: str      # "s" / "w" / "m"
    year: str         # "24" (2-digit)
    type: str         # "qp" / "ms"
    variant: str      # "42"
    path: Path

    @property
    def full_year(self) -> int:
        yy = int(self.year)
        return 2000 + yy if yy < 80 else 1900 + yy

    @property
    def series(self) -> str:
        return SESSION_SERIES[self.session.lower()]

    @property
    def paper_number(self) -> int:
        return int(self.variant[0])

    @property
    def variant_number(self) -> int:
        return int(self.variant[1])

    @property
    def pair_key(self) -> str:
        return f"{self.syllabus}_{self.session}{self.year}_{self.variant}"


def parse_filename(path: Path) -> PaperMeta | None:
    m = FILENAME_RE.match(path.name)
    if not m:
        return None
    return PaperMeta(
        syllabus=m["syllabus"],
        session=m["session"].lower(),
        year=m["year"],
        type=m["type"].lower(),
        variant=m["variant"],
        path=path,
    )


# ── Question-paper parsing ───────────────────────────────────────────────

TOP_Q_RE = re.compile(r"^(\d{1,2})$")
LETTER_PART_RE = re.compile(r"^\(([a-z])\)$")
ROMAN_PART_RE = re.compile(r"^\(([ivx]+)\)$")
MARKS_RE = re.compile(r"\[\s*(\d+)\s*\]")

# "....... ml ....... ml ....... ml [3]" = three answer blanks in one sub-part.
# Treat as input_count=N so the cleanup layer emits N fields instead of 1.
# Research ref: paper-parsing.md §4, §19.
MULTI_SLOT_RE = re.compile(r"(?:\.{3,}[^\[\n]{0,40}){2,5}\s*\[\d+\]")

# "Show that …" sub-parts have NO dotted underscores — just blank workspace + [N].
# Don't strip "dots" on these; leave the text intact so the cleanup layer sees the prompt.
SHOW_THAT_RE = re.compile(r"\bshow\s+that\b", re.IGNORECASE)

# 0580 stats tables encode ≤/≥ as literal G/H in Frutiger subset fonts.
# Only apply inside contexts that look numeric-interval: "0  <num>  X  <num>".
# Research ref: paper-parsing.md §6 "Known corruption".
_LEQ_FIX_RE = re.compile(r"(\d)\s*G\s*(?=\d)")
_GEQ_FIX_RE = re.compile(r"(\d)\s*H\s*(?=\d)")

# Noise patterns — stripped from every line before segmentation.
FOOTER_PATTERNS = [
    re.compile(r"©\s*UCLES", re.I),
    re.compile(r"\[?Turn\s*over\]?", re.I),
    re.compile(r"^\d{4}/\d{2}/[A-Z]/[A-Z]/\d{2}$"),    # 0580/42/M/J/24
    re.compile(r"^Cambridge\s+.*IGCSE", re.I),
    re.compile(r"^\*[0-9\s]+\*$"),                     # candidate barcode
    re.compile(r"DO\s+NOT\s+WRITE\s+IN\s+(THIS|THE)\s+MARGIN", re.I),
]


def _is_footer(line: str) -> bool:
    s = line.strip()
    return bool(s) and any(p.search(s) for p in FOOTER_PATTERNS)


def _extract_marks(text: str) -> int | None:
    m = MARKS_RE.search(text)
    return int(m.group(1)) if m else None


def _strip_marks(text: str) -> str:
    return MARKS_RE.sub("", text).strip()


# Strip answer-line dots that pdfplumber captures as runs of "." in the text.
# These have 15+ dots usually; we also strip short runs when they're at end of line.
_DOT_RUN_RE = re.compile(r"\.{5,}")

# Cambridge uses spaced dots too: ". . . . . ."
_SPACED_DOT_RE = re.compile(r"(?:\.\s){5,}\.?")


def _strip_dotted(text: str) -> str:
    t = _DOT_RUN_RE.sub("", text)
    t = _SPACED_DOT_RE.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def _post_process_chars(text: str) -> str:
    """G↔≤ / H↔≥ fix inside detected numeric-interval contexts. See paper-parsing.md §6."""
    t = _LEQ_FIX_RE.sub(r"\1 ≤ ", text)
    t = _GEQ_FIX_RE.sub(r"\1 ≥ ", t)
    return t


_FORMULA_SHEET_MARKERS = re.compile(
    r"\b(list of formulas?|formul[ae] sheet|you may use the following formul[ae])\b",
    re.IGNORECASE,
)


def _is_formula_sheet_page(page) -> bool:
    """Heuristic: page is a formula sheet when it contains the marker text
    AND doesn't contain a top-level question number in the usual spot."""
    try:
        text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    except Exception:
        return False
    if _FORMULA_SHEET_MARKERS.search(text):
        return True
    # Fallback: dense equations at top of page, no bold "1" at left margin.
    return False


def _first_content_page(pdf) -> int:
    """Return the 0-indexed page where questions start. Skips cover (always
    page 0) and optionally a formula sheet on page 1 (0580 P4 May/June + Oct/Nov;
    NOT Feb/March). Detected dynamically via marker text rather than hardcoded
    per paper number — Feb/March P4 papers don't have the formula sheet, so
    any static rule misclassifies them."""
    if pdf.pages:
        # Page 0 is cover on every CAIE paper.
        if len(pdf.pages) > 1 and _is_formula_sheet_page(pdf.pages[1]):
            return 2
    return 1


def _extend_bbox(q: dict, line_words: list[dict], page_idx: int) -> None:
    if page_idx not in q["pages"]:
        q["pages"].append(page_idx)
    q["bbox"] = [
        min(q["bbox"][0], *(w["x0"] for w in line_words)),
        min(q["bbox"][1], *(w["top"] for w in line_words)),
        max(q["bbox"][2], *(w["x1"] for w in line_words)),
        max(q["bbox"][3], *(w["bottom"] for w in line_words)),
    ]


def parse_qp(pdf_path: Path) -> list[dict]:
    """Parse a CAIE question paper into a list of question dicts.

    Each question looks like:
      {"q": "1", "stem": "...", "parts": [...], "pages": [2,3],
       "bbox": [x0,y0,x1,y1], "total_marks": 8}

    Each part: {"part": "(a)", "text": "...", "marks": 2, "subparts": [...],
                "slot_count": 1, "show_that": False}
    Each subpart: {"sub": "(i)", "text": "...", "marks": 1,
                   "slot_count": 1, "show_that": False}

    slot_count > 1 indicates multi-blank sub-parts ("....... ml ....... ml [3]")
    so the cleanup layer knows to render N inputs. show_that suppresses dotted-
    line artefacts — those questions just have blank workspace + [N].
    """
    questions: list[dict] = []
    current: dict | None = None
    current_part: dict | None = None
    current_sub: dict | None = None

    with pdfplumber.open(pdf_path) as pdf:
        # Detect whether page 1 is a formula sheet or straight into Q1.
        first_page = _first_content_page(pdf)
        for page_idx, page in enumerate(pdf.pages, start=1):
            if page_idx - 1 < first_page:
                continue
            words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
            if not words:
                continue

            # Group words into lines by rounded y-position.
            lines: dict[int, list[dict]] = {}
            for w in words:
                y_key = round(w["top"] / 2) * 2
                lines.setdefault(y_key, []).append(w)

            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda w: w["x0"])
                line_text = " ".join(w["text"] for w in line_words).strip()
                line_text = _strip_dotted(line_text)
                if not line_text or _is_footer(line_text):
                    continue

                first = line_words[0]
                first_x = first["x0"]
                first_tok = first["text"]

                # Top-level question number — must be a small integer at left margin.
                if first_x < 60 and TOP_Q_RE.match(first_tok):
                    qnum = first_tok
                    rest = _strip_dotted(
                        " ".join(w["text"] for w in line_words[1:])
                    ).strip()
                    current = {
                        "q": qnum,
                        "stem": rest,
                        "parts": [],
                        "pages": [page_idx],
                        "bbox": [first["x0"], first["top"], line_words[-1]["x1"], first["bottom"]],
                    }
                    current_part = None
                    current_sub = None
                    questions.append(current)
                    continue

                # Letter subpart (a), (b), …
                if current is not None and LETTER_PART_RE.match(first_tok):
                    letter = LETTER_PART_RE.match(first_tok).group(1)
                    rest = _strip_dotted(
                        " ".join(w["text"] for w in line_words[1:])
                    ).strip()
                    current_part = {
                        "part": f"({letter})",
                        "text": rest,
                        "subparts": [],
                        "marks": _extract_marks(rest),
                    }
                    current["parts"].append(current_part)
                    current_sub = None
                    _extend_bbox(current, line_words, page_idx)
                    continue

                # Roman sub-subpart (i), (ii), …
                if current_part is not None and ROMAN_PART_RE.match(first_tok):
                    roman = ROMAN_PART_RE.match(first_tok).group(1)
                    rest = _strip_dotted(
                        " ".join(w["text"] for w in line_words[1:])
                    ).strip()
                    current_sub = {
                        "sub": f"({roman})",
                        "text": rest,
                        "marks": _extract_marks(rest),
                    }
                    current_part["subparts"].append(current_sub)
                    _extend_bbox(current, line_words, page_idx)
                    continue

                # Continuation text — appended to whatever level is currently open.
                if current is not None:
                    if current_sub is not None:
                        current_sub["text"] += " " + line_text
                        current_sub["marks"] = current_sub["marks"] or _extract_marks(line_text)
                    elif current_part is not None:
                        current_part["text"] += " " + line_text
                        current_part["marks"] = current_part["marks"] or _extract_marks(line_text)
                    else:
                        current["stem"] += " " + line_text
                    _extend_bbox(current, line_words, page_idx)

    # Post-process: strip trailing [N] markers, apply G↔≤ / H↔≥ fix, annotate
    # multi-slot + show-that flags, compute totals.
    def _annotate(leaf: dict) -> None:
        raw_text = leaf.get("text", "")
        # Slot count BEFORE stripping marks/dots — the regex needs the [N] anchor.
        m = MULTI_SLOT_RE.search(raw_text)
        slots = 1
        if m:
            # Count dot-runs inside the matched span.
            dot_groups = re.findall(r"\.{3,}", m.group(0))
            slots = max(1, len(dot_groups))
        leaf["slot_count"] = slots
        leaf["show_that"] = bool(SHOW_THAT_RE.search(raw_text))
        # Clean the text: marks + character post-process. Dotted-strip was
        # already done at line-ingest time; don't repeat it here.
        leaf["text"] = _post_process_chars(_strip_marks(raw_text))

    for q in questions:
        q["stem"] = _post_process_chars(_strip_marks(q.get("stem", "")))
        for p in q["parts"]:
            _annotate(p)
            for s in p["subparts"]:
                _annotate(s)
        total = 0
        for p in q["parts"]:
            if p["subparts"]:
                total += sum((s.get("marks") or 0) for s in p["subparts"])
            else:
                total += p.get("marks") or 0
        q["total_marks"] = total
    return questions


# ── Image cropping ───────────────────────────────────────────────────────

def crop_question_images(
    pdf_path: Path, questions: list[dict], out_dir: Path, paper_id: str, dpi: int = 180
) -> None:
    """For each question, if its bounding region contains raster images or
    heavy vector drawings, rasterize the region to PNG. Sets q['image_files']
    to the list of saved filenames (relative to out_dir).

    The 30-path-operations threshold catches Cambridge's vector diagrams while
    ignoring tiny vector flourishes (answer lines etc.)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    try:
        for q in questions:
            pages = q.get("pages", [])
            if not pages:
                q["has_image"] = False
                continue

            has_visual = False
            for p_idx in pages:
                if p_idx - 1 >= len(doc):
                    continue
                page = doc[p_idx - 1]
                if page.get_images(full=True):
                    has_visual = True
                    break
                drawings = page.get_drawings()
                path_count = sum(len(d.get("items", [])) for d in drawings)
                if path_count > 30:
                    has_visual = True
                    break

            if not has_visual:
                q["has_image"] = False
                q["image_files"] = []
                continue

            q["has_image"] = True
            image_paths: list[str] = []
            x0, y0, x1, y1 = q["bbox"]
            pad = 8
            for p_idx in pages:
                page = doc[p_idx - 1]
                if len(pages) > 1:
                    # Multi-page question — snap to whole page to capture continuation.
                    rect = page.rect
                else:
                    rect = fitz.Rect(
                        max(0, x0 - pad),
                        max(0, y0 - pad),
                        min(page.rect.width, x1 + pad + 40),
                        min(page.rect.height, y1 + pad),
                    )
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=rect)
                fname = f"{paper_id}_q{q['q']}_p{p_idx}.png"
                (out_dir / fname).write_bytes(pix.tobytes("png"))
                image_paths.append(fname)
            q["image_files"] = image_paths
    finally:
        doc.close()
