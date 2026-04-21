"""Learning-style quiz (Phase 6). 5 questions, each maps A/B/C/D to one of:
schema_heavy / narrative / formula_first / worked_example. Winner by count."""
from __future__ import annotations

from collections import Counter

QUIZ = [
    {
        "id": 1,
        "prompt": "When you meet a new topic, what helps you click with it first?",
        "choices": [
            ("A", "A diagram showing how ideas fit together", "schema_heavy"),
            ("B", "A story that walks me through an example", "narrative"),
            ("C", "The key formulas, listed plainly", "formula_first"),
            ("D", "A fully worked-out example I can copy", "worked_example"),
        ],
    },
    {
        "id": 2,
        "prompt": "You've forgotten how to do compound interest mid-exam. What do you wish you had?",
        "choices": [
            ("A", "A mental map of 'growth vs. decay vs. simple'", "schema_heavy"),
            ("B", "A short reminder of how the formula was derived", "narrative"),
            ("C", "Just the formula, one line", "formula_first"),
            ("D", "A solved £2000-at-5%-for-3-years example", "worked_example"),
        ],
    },
    {
        "id": 3,
        "prompt": "Which kind of note page do you re-read most often?",
        "choices": [
            ("A", "Concept maps with arrows and categories", "schema_heavy"),
            ("B", "Paragraphs that explain why something works", "narrative"),
            ("C", "Dense formula sheets with one-line hints", "formula_first"),
            ("D", "Pages that are 90% example, 10% formula", "worked_example"),
        ],
    },
    {
        "id": 4,
        "prompt": "A friend asks for help with vectors. You start with...",
        "choices": [
            ("A", "Drawing the relationships — point, vector, parallelogram", "schema_heavy"),
            ("B", "Telling them how a vector is 'just a journey'", "narrative"),
            ("C", "Writing AB = b − a on the page and going from there", "formula_first"),
            ("D", "Doing a specific question side-by-side", "worked_example"),
        ],
    },
    {
        "id": 5,
        "prompt": "You've got 10 minutes before an exam. What do you revise?",
        "choices": [
            ("A", "The topic map — what connects to what", "schema_heavy"),
            ("B", "A mental walkthrough of a tricky past paper", "narrative"),
            ("C", "The formula sheet, cover to cover", "formula_first"),
            ("D", "Re-solve 2 short examples from memory", "worked_example"),
        ],
    },
]

VALID_STYLES = ("schema_heavy", "narrative", "formula_first", "worked_example")


def classify(answers: dict[int, str]) -> str:
    """answers: {question_id: chosen_letter}. Returns winning style.
    Ties broken by preferred order: formula_first > worked_example > schema_heavy > narrative
    (so ambiguous results default to a style with minimal LLM token load)."""
    tally: Counter[str] = Counter()
    for q in QUIZ:
        choice = answers.get(q["id"])
        if not choice:
            continue
        for letter, _label, style in q["choices"]:
            if letter == choice:
                tally[style] += 1
                break
    if not tally:
        return "formula_first"
    max_count = max(tally.values())
    tied = [s for s, c in tally.items() if c == max_count]
    for preferred in ("formula_first", "worked_example", "schema_heavy", "narrative"):
        if preferred in tied:
            return preferred
    return "formula_first"
