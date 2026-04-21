"""Per-topic clarifying-question chat. Feature-flagged behind FEATURE_CHAT.

When off: returns a deterministic stub so the UI is developable without
burning OpenAI credits. When on: calls the OpenAI Chat Completions API with
the topic's canonical note as system context."""
from __future__ import annotations

from typing import Any

from services.openai_client import DEFAULT_MODEL, feature_flag, get_client

MAX_HISTORY = 12  # cap context window — last N user+assistant turns


def _system_prompt(topic_name: str, syllabus_ref: str | None, canonical_html: str) -> str:
    ref_line = f" (Cambridge ref: {syllabus_ref})" if syllabus_ref else ""
    return (
        f"You are a patient IGCSE tutor helping a student with '{topic_name}'{ref_line}. "
        "Answer questions clearly and concisely. For maths, use LaTeX: inline with "
        "\\( ... \\), display with \\[ ... \\]. For chemistry equations, use subscripts "
        "and superscripts directly (H₂O, O₂⁺). Keep replies under 200 words unless "
        "the student asks for more depth. If the question goes beyond IGCSE scope, say so.\n\n"
        "Here is the canonical revision note the student is reading:\n\n"
        f"{canonical_html}\n\n"
        "When giving further examples or alternative explanations, anchor them in this note. "
        "Do NOT invent new formulas not taught at IGCSE level."
    )


def _stub_reply(question: str) -> str:
    return (
        f"(Chat disabled — set `FEATURE_CHAT=1` in Railway env to enable OpenAI-backed replies.)\n\n"
        f"You asked: \"{question}\". With chat enabled I'd answer using the topic's canonical note "
        f"as context and render any maths in LaTeX."
    )


def ask(
    question: str,
    history: list[dict[str, Any]],
    topic_name: str,
    syllabus_ref: str | None,
    canonical_html: str,
) -> str:
    """history: list of {'role': 'user'|'assistant', 'content': str} — capped to MAX_HISTORY."""
    if not feature_flag("FEATURE_CHAT"):
        return _stub_reply(question)

    truncated_history = history[-MAX_HISTORY:] if len(history) > MAX_HISTORY else history
    messages = [
        {"role": "system", "content": _system_prompt(topic_name, syllabus_ref, canonical_html)},
        *truncated_history,
        {"role": "user", "content": question},
    ]

    client = get_client()
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=400,
    )
    content = (resp.choices[0].message.content or "").strip()
    return content or _stub_reply(question)
