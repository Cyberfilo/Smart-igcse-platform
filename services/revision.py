"""Personalised revision-note generation (Phase 6). Per-user × per-topic ×
per-learning-style, cached in RevisionNote. Gated by FEATURE_REVISION_LLM —
stub content ships when flag is off so the flow is developable."""
from __future__ import annotations

import hashlib
import json

from services.openai_client import DEFAULT_MODEL, feature_flag, get_client

STYLE_SYSTEM_PROMPTS = {
    "schema_heavy": (
        "Render the topic as a concept map: top-level schema → sub-schemas → "
        "concrete formulas. Use bullet lists. Emphasise structure over prose."
    ),
    "narrative": (
        "Render the topic as a short teaching story. Connect ideas with "
        "'therefore', 'because', 'so'. Minimal lists; maximal connective prose."
    ),
    "formula_first": (
        "Render the topic as a formula reference card: every formula up front, "
        "tightly packed, with a one-line hint under each."
    ),
    "worked_example": (
        "Render the topic through 3 worked examples of increasing difficulty. "
        "Show every step. Formulas appear only as they're used."
    ),
}


def compute_cache_key(user_id: int, topic_id: int, style: str, error_snapshot: dict) -> str:
    """Cache invalidates when error-profile snapshot for this topic changes."""
    payload = json.dumps({"u": user_id, "t": topic_id, "s": style, "e": error_snapshot}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _stub_note(topic_name: str, style: str, errors: list[str]) -> str:
    err_html = (
        f"<div class='tip-box'><span class='tip-label'>Focus on</span>{', '.join(errors)}</div>"
        if errors
        else ""
    )
    return (
        f"<article class='topic-card'>"
        f"<div class='topic-header'><div class='topic-num color-purple'>•</div>"
        f"<h3 class='topic-title'>{topic_name} — {style.replace('_', ' ')}</h3></div>"
        f"<p class='topic-intro'>(LLM revision notes disabled — set FEATURE_REVISION_LLM=1)</p>"
        f"{err_html}"
        f"</article>"
    )


def generate_revision_note(
    topic_name: str,
    style: str,
    error_tags: list[str],
    topic_summary_html: str,
) -> str:
    if style not in STYLE_SYSTEM_PROMPTS:
        style = "formula_first"

    if not feature_flag("FEATURE_REVISION_LLM"):
        return _stub_note(topic_name, style, error_tags)

    client = get_client()
    system_prompt = (
        "You render IGCSE Mathematics/Sciences revision notes as HTML. Reuse "
        "the existing class names: .topic-card, .topic-header, .topic-num, "
        ".color-purple|teal|coral|pink|blue|amber|purple-alt, .section-h, "
        ".formula-box, .tip-box, .example-box, .fact-list, .grid-2. "
        "Return ONE <article class='topic-card'>...</article> block. No <html>, "
        "no <body>. " + STYLE_SYSTEM_PROMPTS[style]
    )
    user_msg = (
        f"Topic: {topic_name}\n"
        f"Current canonical notes (for reference, do not just echo):\n{topic_summary_html}\n\n"
        f"Student is struggling with these error tags: {', '.join(error_tags) if error_tags else '(none recorded yet)'}.\n"
        f"Render the topic in the '{style}' style. Bias examples toward the error tags."
    )
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or _stub_note(topic_name, style, error_tags)
