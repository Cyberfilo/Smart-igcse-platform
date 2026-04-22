"""Per-profile revision-note generation (Phase 6).

Every profile ships the same evidence-based CORE (retrieval, spacing, dual
coding, elaboration, interleaving, concrete examples). Only the SURFACE
STRUCTURE of the notes changes — per learning-styles-research.md §2. The
profile-specific prompts below encode the note-adaptation rules verbatim.

Gated by FEATURE_REVISION_LLM — stub content ships when flag is off so the
flow is developable without OpenAI spend.
"""
from __future__ import annotations

import hashlib
import json
import os

from services.openai_client import DEFAULT_MODEL, feature_flag, get_client


# ── Per-profile note-adaptation prompts ──────────────────────────────
#
# Each prompt describes only the SURFACE rules that differ between profiles.
# The universal core (Section 2 intro of the research doc) lives in CORE_RULES
# and is concatenated automatically.

CORE_RULES = """Universal core (applies to every profile):
- Retrieval prompts: include a question column / flashcards section so the
  student can self-test.
- Spacing cues: include a suggested review date on the note.
- Elaboration: include at least one "why?" / "how does this connect?" prompt.
- Worked example followed by a near-identical self-practice question.
- Dual-code: pair verbal content with a diagram or sketch at least once.
- Evidence-based framing — language like "practice testing" and "spacing"
  rather than "learning style matching"."""

STYLE_SYSTEM_PROMPTS: dict[str, str] = {
    "diagram_led_synthesiser": """Surface structure for the Diagram-Led Synthesiser (Visual × Global):
- OPEN WITH a one-page concept map: central concept + 4–7 branches. Render
  it as a <figure> with an inline <svg> showing the topology. This is the
  opening element; linear prose comes after.
- Dual-code everything: every definition, process, or causal chain gets a
  small sketch/flow diagram on the same row. Keep image and text adjacent
  (spatial-contiguity principle).
- Hierarchical colour coding with AT MOST three tones: main concept,
  sub-concept, example. Use the existing .color-teal/.color-coral/.color-pink
  CSS classes (already in static/css/style.css).
- Text density LOW: bullets capped at ~10 words each. Prefer annotated
  diagrams over prose paragraphs.
- Open each topic with a 3-sentence "zoom-out" placing it in the wider
  syllabus — what it connects to before, and what comes after.
- Counter the global-learner blind spot: every procedural topic MUST
  include one fully worked linear example with numbered steps before the
  student's own practice.
- Retrieval prompts take the form of BLANK diagrams the student redraws.""",

    "structured_builder": """Surface structure for the Structured Builder (Verbal × Sequential):
- Linear Cornell-style layout: a narrow left column with CUE QUESTIONS and
  a wider right column with the notes. Render with a CSS grid (left: 30%,
  right: 70%). At the bottom, a short 2–3-sentence summary strip IN THE
  STUDENT'S OWN WORDS (mark it "write here").
- Numbered steps for every procedure: one step per <li>, each with a
  brief "why this step?" rationale inline.
- Definition-first: each new term <strong>bolded</strong> and defined in
  ONE sentence before being used in context.
- Parallel worked-example + self-practice pair per concept. The pair must
  be visibly adjacent (two-column layout or stacked cards).
- Inject one concept-level prompt per section: "How does this connect to
  X we did last week?" — counters the sequential blind spot of memorising
  steps without the schema.
- Controlled dual coding: ONE small icon or diagram per major concept,
  never page-dominant. Verbal dominance means diagrams support, don't lead.
- Include a "weekly global page" pointer at the bottom: "This fits in
  topic area: ___ (see weekly review)".""",

    "active_experimenter": """Surface structure for the Active Experimenter (Visual × Sequential):
- Worked-example / self-practice PAIRS are the backbone. The note is
  built around the examples, not around prose.
- Every procedure rendered as a FLOWCHART: "If X → A, else → B". Use
  inline <svg> boxes + arrows.
- Interleaved problem set at the end: 5 problems mixing the LAST THREE
  topics (not just the current one). This counters blocked-practice
  comfort (Rohrer & Taylor 2007).
- "EXPLAIN IT BACK" box on every page: two lines where the student
  writes the rule in plain words AFTER doing the practice. Render as a
  <div class="tip-box"> with placeholder lines.
- Diagrams EMBEDDED IN problems, not separate: each practice question
  annotated with the relevant figure.
- Retrieval quiz every 3 concepts: 5 short questions mixing recall,
  application, and "why?" items.
- Explicit ERROR LOG slot at the bottom: "Errors I made in practice →
  corrections" — builds the metacognition active-sequentials under-develop.""",

    "reflective_theorist": """Surface structure for the Reflective Theorist (Verbal × Global):
- Prose-plus-outline HYBRID. Each topic opens with a short narrative
  paragraph explaining the big idea (3–5 sentences, serif typography),
  followed by a bulleted outline of components.
- "QUESTION OF THE TOPIC" at the very top: a single overarching
  conceptual question the notes will answer. Anchors global comprehension.
- Comparison tables for contrastable concepts (e.g. ionic vs covalent,
  linear vs quadratic sequences). Use a <table class="grid-2"> — compare
  on the same row.
- Explicit elaboration prompts after each section: "Why is this true?
  What would happen if it weren't?" (Dunlosky moderate-utility strategy).
- PAST-PAPER INTEGRATION on every topic: at least one past-paper question
  with a mapped answer structure. This is the strategic lever reflective
  theorists typically under-use.
- Time-boxed retrieval: include a "10-minute blank-page recall, twice"
  instruction to combat re-reading (a Dunlosky low-utility technique).
- Minimal dual coding: ONE small diagram or causal-chain sketch per major
  concept, not decorative. Gives verbal-dominant reflectives the proven
  dual-coding benefit without disrupting preferred prose format.""",

    "balanced_hybrid": """Surface structure for the Balanced Hybrid (near-midpoint on V and S):
- Combine the best of all four profiles — this is effectively best-practice
  note design:
  1. Cornell-style layout (from Structured Builder).
  2. Opening concept map per topic (from Diagram-Led Synthesiser).
  3. Worked-example + self-practice pairs (from Active Experimenter).
  4. One elaboration prompt per section (from Reflective Theorist).
- Safe default for any ambiguous scorer.""",
}

# Legacy aliases for users whose profile hasn't been migrated from the old
# 5-question quiz yet. Kept so the function never raises KeyError during the
# transition window.
_LEGACY_STYLE_MAP = {
    "schema_heavy":    "diagram_led_synthesiser",
    "narrative":       "reflective_theorist",
    "formula_first":   "structured_builder",
    "worked_example":  "active_experimenter",
}


SR_OVERLAY_RULES = """SR BOOSTER OVERLAY (student scored low on self-regulation, D ≤ +3):
Additionally apply:
- Place a "REVIEW ON" date one week from today at the top of the note.
- Open with a "PREDICT BEFORE YOU STUDY" line: one sentence the student
  completes before reading — checked at the end (metacognitive monitoring).
- Include a 5-minute DAILY RETRIEVAL WARM-UP section — 3 questions from
  last week's topics.
- One EFFORT-REGULATION CUE: a sentence like "I will study this for 25
  minutes even when it feels hard" at the top.
These scaffold the MSLQ subscales that best predict grades (metacognitive
self-regulation, effort regulation, time/study-environment)."""


def compute_cache_key(user_id: int, topic_id: int, style: str, error_snapshot: dict) -> str:
    payload = json.dumps(
        {"u": user_id, "t": topic_id, "s": style, "e": error_snapshot},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _stub_note(topic_name: str, style: str, errors: list[str]) -> str:
    err_html = (
        f"<div class='tip-box'><span class='tip-label'>Focus on</span>"
        f"{', '.join(errors)}</div>"
        if errors else ""
    )
    return (
        f"<article class='topic-card'>"
        f"<div class='topic-header'><div class='topic-num color-purple'>•</div>"
        f"<h3 class='topic-title'>{topic_name} — {style.replace('_', ' ')}</h3></div>"
        f"<p class='topic-intro'>(LLM revision notes disabled — set FEATURE_REVISION_LLM=1)</p>"
        f"{err_html}</article>"
    )


def generate_revision_note(
    topic_name: str,
    style: str,
    error_tags: list[str],
    topic_summary_html: str,
    sr_overlay: bool = False,
) -> str:
    """Return one <article class='topic-card'>...</article> block styled to
    the student's profile. When FEATURE_REVISION_LLM is off, returns a stub.

    style values come from services.style_classifier.VALID_STYLES. Legacy
    values from the old 5-q quiz are silently remapped.
    """
    effective = _LEGACY_STYLE_MAP.get(style, style)
    if effective not in STYLE_SYSTEM_PROMPTS:
        effective = "balanced_hybrid"

    if not feature_flag("FEATURE_REVISION_LLM"):
        return _stub_note(topic_name, effective, error_tags)

    profile_rules = STYLE_SYSTEM_PROMPTS[effective]
    overlay_rules = SR_OVERLAY_RULES if sr_overlay else ""

    system_prompt = (
        "You render IGCSE Mathematics / Sciences revision notes as HTML for a "
        "specific student study-preference profile.\n\n"
        + CORE_RULES
        + "\n\n"
        + profile_rules
        + ("\n\n" + overlay_rules if overlay_rules else "")
        + "\n\n"
        "TECHNICAL CONSTRAINTS:\n"
        "- Use the existing class names: .topic-card, .topic-header, .topic-num, "
        ".color-purple|teal|coral|pink|blue|amber|purple-alt, .section-h, "
        ".formula-box, .tip-box, .example-box, .fact-list, .grid-2.\n"
        "- Return ONE <article class='topic-card'>...</article>. No <html>, "
        "no <body>, no markdown fences.\n"
        "- Math in MathJax delimiters: \\( ... \\) inline, \\[ ... \\] display.\n"
        "- For inline SVG diagrams, keep under ~2KB each, use currentColor so "
        "they adapt to dark mode."
    )

    client = get_client()
    user_msg = (
        f"Topic: {topic_name}\n"
        f"Canonical notes (reference — do not just echo):\n{topic_summary_html}\n\n"
        f"Student is struggling with: "
        f"{', '.join(error_tags) if error_tags else '(no errors recorded yet)'}.\n"
        f"Bias examples toward those error tags."
    )

    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or _stub_note(topic_name, effective, error_tags)
