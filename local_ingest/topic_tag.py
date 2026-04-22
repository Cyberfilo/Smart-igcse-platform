"""Topic classifier using GPT-5.4 (text only).

Given a cleaned question body and the list of syllabus topics (seeded by
scripts/seed_syllabi.py — 63 for 0580, 88 for 0654), returns the best-fit
Topic.id or None.

Cached per-question — if a question already has topic_id in the DB, we skip.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from openai import OpenAI

log = logging.getLogger(__name__)

TAGGER_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")

_client: OpenAI | None = None


def _client_singleton() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def tag_topic(question_body_html: str, topic_list: list[dict[str, Any]]) -> int | None:
    """topic_list: [{"id": int, "name": str, "syllabus_ref": str | None}, ...]."""
    if not question_body_html or not topic_list:
        return None

    # Strip HTML + MathJax to plain prose. The model doesn't need formatting
    # to classify, and stripped text costs fewer tokens.
    plain = re.sub(r"<[^>]+>", " ", question_body_html)
    plain = re.sub(r"\\\\\((.*?)\\\\\)", r"\1", plain)  # remove MathJax delimiters
    plain = re.sub(r"\s+", " ", plain).strip()[:1200]

    topic_lines = "\n".join(
        f"{t['id']}: {t['name']}"
        + (f" ({t['syllabus_ref']})" if t.get("syllabus_ref") else "")
        for t in topic_list
    )

    try:
        client = _client_singleton()
        resp = client.chat.completions.create(
            model=TAGGER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify Cambridge IGCSE past-paper questions to a single "
                        "topic from the supplied list. Reply with ONLY the numeric topic "
                        "id. No prose. No markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Topics:\n{topic_lines}\n\nQuestion:\n{plain}\n\nTopic id:",
                },
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\d+", raw)
        if not m:
            return None
        tid = int(m.group(0))
        if any(t["id"] == tid for t in topic_list):
            return tid
    except Exception:
        log.exception("tag_topic failed")
    return None
