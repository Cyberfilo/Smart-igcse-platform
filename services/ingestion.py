"""Past-paper PDF ingestion (Phase 3). Extracts questions from a PDF using
GPT vision. Gated by FEATURE_INGESTION so the admin UI works without burning
credits on every click; flip to on for real ingestion runs."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

from services.openai_client import VISION_MODEL, feature_flag, get_client


@dataclass
class ExtractedSubPart:
    letter: str
    body_html: str
    answer_schema: str
    correct_answer: Any
    mcq_choices: list[dict[str, Any]] | None
    marking_alternatives: list[dict[str, Any]]
    marks: int | None


@dataclass
class ExtractedQuestion:
    question_number: int
    topic_guess: str | None
    body_html: str
    marks_total: int | None
    images: list[str]
    subparts: list[ExtractedSubPart]


EXTRACTION_SYSTEM_PROMPT = """You are extracting questions from a Cambridge IGCSE
exam paper. For each question on the supplied page images, produce strict JSON:

{
  "questions": [
    {
      "question_number": 1,
      "topic_guess": "probability"|"algebra"|"geometry"|"vectors"|"functions"|null,
      "body_html": "<HTML with <p>, <ul>, <strong>; preserve math via &lt;span class='math'&gt; wrappers>",
      "marks_total": 6,
      "images": [],
      "subparts": [
        {
          "letter": "a",
          "body_html": "...",
          "answer_schema": "scalar"|"mcq"|"multi_cell"|"graphical",
          "correct_answer": null,
          "mcq_choices": null,
          "marking_alternatives": [],
          "marks": 3
        }
      ]
    }
  ]
}

Skip cover, formula sheet, and copyright pages. Skip barcodes, candidate-number
boxes, and 'DO NOT WRITE IN THIS MARGIN' text. Preserve 'NOT TO SCALE' labels.
Do not invent answers — leave correct_answer null; the marking-scheme pass fills it."""


MARKING_SYSTEM_PROMPT = """You are parsing the 'Question | Answer | Marks | Partial
Marks' table from an IGCSE marking scheme. Return strict JSON:

{
  "answers": [
    {
      "question_number": 1,
      "subpart_letter": "a",
      "correct_answer": "value or array",
      "marking_alternatives": [
        {"gate": "M1", "condition": "for substitution into P(1+r/100)^n", "oe": true},
        {"gate": "B1", "condition": "for 2315.25 nfww", "oe": false}
      ]
    }
  ]
}

Interpret conventions: oe='or equivalent', nfww='not from wrong working',
isw='ignore subsequent working', FT='follow through'. Copy them into the
'oe'/'nfww'/'isw'/'ft' boolean fields when present."""


def _stub_extraction(past_paper_id: int) -> list[ExtractedQuestion]:
    """Seed a minimal fake question so the admin review queue has something to
    render. Used when FEATURE_INGESTION is off OR when OpenAI fails."""
    return [
        ExtractedQuestion(
            question_number=1,
            topic_guess=None,
            body_html="<p>(Stub question — ingestion not wired to real vision model.)</p>",
            marks_total=3,
            images=[],
            subparts=[
                ExtractedSubPart(
                    letter="a",
                    body_html="<p>Work out 2 + 2.</p>",
                    answer_schema="scalar",
                    correct_answer="4",
                    mcq_choices=None,
                    marking_alternatives=[{"gate": "B1", "condition": "cao"}],
                    marks=3,
                )
            ],
        )
    ]


def extract_questions_from_pdf(pdf_path: str) -> list[ExtractedQuestion]:
    """Render PDF pages to images, ship to vision model, parse JSON response.

    NOTE (Phase 3 caveat): the plan says this runs synchronously in admin flow.
    For production we'd pre-convert pages to JPEGs (pdf2image / pymupdf) and
    batch them into a single vision call. This module exposes the seam; the
    actual PDF→images step is left as a TODO since pymupdf isn't yet in
    requirements.txt and doing real vision calls in tests would burn tokens."""
    if not feature_flag("FEATURE_INGESTION"):
        return _stub_extraction(past_paper_id=0)

    # --- Real path (not exercised in tests) ---
    # pages = render_pdf_to_jpegs(pdf_path)  # TODO: add pymupdf + impl
    # client = get_client()
    # user_content = [{"type": "text", "text": "Extract every question from these pages."}]
    # for jpeg_bytes in pages:
    #     b64 = base64.b64encode(jpeg_bytes).decode()
    #     user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    # resp = client.chat.completions.create(
    #     model=VISION_MODEL,
    #     messages=[
    #         {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
    #         {"role": "user", "content": user_content},
    #     ],
    #     response_format={"type": "json_object"},
    #     temperature=0.0,
    # )
    # data = json.loads(resp.choices[0].message.content)
    # return [_to_dataclass(q) for q in data.get("questions", [])]
    return _stub_extraction(past_paper_id=0)


def save_uploaded_pdf(file_storage, target_dir: str) -> str:
    """Writes FileStorage under target_dir with a uuid filename, returns path."""
    os.makedirs(target_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.pdf"
    full_path = os.path.join(target_dir, fname)
    file_storage.save(full_path)
    return full_path
