"""Evidence-based study-preference quiz + classifier.

Replaces the earlier 5-question "learning-style" quiz with the 14-question
instrument from learning-styles-research.md. The quiz items adapt
Felder–Silverman ILS (V/V, S/G), ASSIST (depth of study), and MSLQ
(self-regulation) items.

Three dimensions are scored per item:
  V — Visual ↔ Verbal processing (positive = visual)
  S — Sequential ↔ Global organisation (positive = sequential)
  D — Depth of study approach + self-regulation (positive = deep / high SR)

The 2×2 V×S grid yields four profiles; a Balanced hybrid covers near-midpoint
scorers. An SR Booster overlay is assigned when D ≤ +3 — the research calls
this the single most important signal for students at risk of a surface
approach.

IMPORTANT: this is a study-preference profile, NOT a "learning style". All
profiles receive the same evidence-based core (retrieval, spacing, dual
coding, elaboration, interleaving, concrete examples). Only the surface
structure of the notes changes. See learning-styles-research.md §1.5.
"""
from __future__ import annotations


# Each question is a dict with:
#   id     — 1..14 for stable scoring
#   prompt — the question text shown to the student
#   choices — list of (letter, label, scores) where scores is a dict mapping
#             dimension → signed int. Example: {"S": 1, "V": 1}.
# See research doc §4.1 for the item-to-dimension scoring table.

QUIZ: list[dict] = [
    {
        "id": 1,
        "prompt": "When a teacher starts a new topic, I understand it best when…",
        "choices": [
            ("A", "She starts with an overview of how the whole topic fits together, then fills in the details.", {"S": -1}),
            ("B", "She starts at step 1 and builds up step by step to the full picture.", {"S": 1}),
            ("C", "She gives us a worked example first and explains as she goes.", {"S": 1}),
            ("D", "She shows a diagram of the main idea and then talks through it.", {"S": -1, "V": 1}),
        ],
    },
    {
        "id": 2,
        "prompt": "When I think back to a science lesson from yesterday, the first thing that comes to mind is…",
        "choices": [
            ("A", "A picture, diagram or scene from the lesson.", {"V": 1}),
            ("B", "Words the teacher said or a phrase from the board.", {"V": -1}),
            ("C", "The feeling of doing an activity or experiment.", {"V": 1}),
            ("D", "An outline or list of what was covered.", {"V": -1}),
        ],
    },
    {
        "id": 3,
        "prompt": "My class notes usually look like…",
        "choices": [
            ("A", "Mostly written sentences and bullet points, organised under headings.", {"V": -1}),
            ("B", "Words plus arrows, boxes and small diagrams everywhere.", {"V": 1}),
            ("C", "Mostly diagrams, mind maps or sketches with short labels.", {"V": 2, "S": -1}),
            ("D", "Copied directly from the board with little reorganisation.", {"D": -1}),
        ],
    },
    {
        "id": 4,
        "prompt": "I feel I have really understood something when…",
        "choices": [
            ("A", "I can repeat the definition or formula accurately.", {"D": -1}),
            ("B", "I can explain it in my own words to a friend and answer their 'why?' questions.", {"D": 2}),
            ("C", "I can do the past-paper questions on it without mistakes.", {"D": 1}),
            ("D", "I've highlighted the important bits in the textbook.", {"D": -1}),
        ],
    },
    {
        "id": 5,
        "prompt": "When revising for an exam, I mostly…",
        "choices": [
            ("A", "Re-read my notes and the textbook several times.", {"D": -1}),
            ("B", "Do past papers and quiz myself without looking.", {"D": 2}),
            ("C", "Re-write my notes neatly, maybe in different colours.", {"D": 0}),
            ("D", "Make flashcards or a list of questions and test myself over several days.", {"D": 2}),
        ],
    },
    {
        "id": 6,
        "prompt": "When I'm studying a hard chapter, I prefer to…",
        "choices": [
            ("A", "Read it carefully from start to finish in order.", {"S": 1}),
            ("B", "Skim the whole chapter first, then go back to the start.", {"S": -1}),
            ("C", "Jump to the worked examples and figure out the theory from them.", {"S": 1, "V": 1}),
            ("D", "Look at the summary or diagrams at the end first to see where we're going.", {"S": -1}),
        ],
    },
    {
        "id": 7,
        "prompt": "In a group project, I'm usually the person who…",
        "choices": [
            ("A", "Suggests ideas out loud and wants to try things quickly.", {}),
            ("B", "Listens, takes notes, and thinks about it before speaking.", {"D": 1}),
            ("C", "Organises the plan, the deadlines, and who does what.", {"D": 1}),
            ("D", "Explains the topic to other group members to make sure everyone understands.", {"D": 1}),
        ],
    },
    {
        "id": 8,
        "prompt": "When I'm stuck on a homework problem, my first move is to…",
        "choices": [
            ("A", "Ask a friend or family member for the answer.", {"D": -1}),
            ("B", "Re-read the relevant part of my notes or textbook.", {"D": 0}),
            ("C", "Try to work out what step I'm stuck on and check a similar example.", {"D": 2}),
            ("D", "Leave it and move on to something easier.", {"D": -1}),
        ],
    },
    {
        "id": 9,
        "prompt": "When I finish studying a topic, I usually…",
        "choices": [
            ("A", "Feel done and don't think about it again until the exam.", {"D": -1}),
            ("B", "Test myself on it a few days later to see what I've forgotten.", {"D": 2}),
            ("C", "Re-read my notes once more just to be sure.", {"D": 0}),
            ("D", "Check off the topic on my revision checklist.", {"D": 1}),
        ],
    },
    {
        "id": 10,
        "prompt": "Which kind of resource makes difficult ideas click for me?",
        "choices": [
            ("A", "A clear written explanation with headings and paragraphs.", {"V": -1}),
            ("B", "A labelled diagram or flowchart.", {"V": 1}),
            ("C", "A teacher or video explaining it out loud, step by step.", {"V": -1}),
            ("D", "A worked example I can follow line by line.", {"V": 1, "S": 1}),
        ],
    },
    {
        "id": 11,
        "prompt": "When I take notes in class, I mostly…",
        "choices": [
            ("A", "Write down the teacher's words as completely as I can.", {"D": -1, "V": -1}),
            ("B", "Write the key points and add my own arrows and diagrams.", {"V": 1, "D": 1}),
            ("C", "Listen, then write a short summary after a few minutes.", {"D": 1, "V": -1}),
            ("D", "Write a rough outline and fill in details later at home.", {"S": 1, "D": 1}),
        ],
    },
    {
        "id": 12,
        "prompt": "When studying a subject I find harder, I would rather…",
        "choices": [
            ("A", "Have a detailed weekly plan with specific study times I stick to.", {"D": 2}),
            ("B", "Study when I feel motivated, without a fixed plan.", {"D": -1}),
            ("C", "Study with a friend who keeps me on track.", {"D": 1}),
            ("D", "Do a little every day, same time, as a routine.", {"D": 2}),
        ],
    },
    {
        "id": 13,
        "prompt": "Which is closer to how you think about your school subjects?",
        "choices": [
            ("A", "I try to remember exactly what the teacher and textbook said.", {"D": -1}),
            ("B", "I try to understand the ideas so well that I could explain them in a new example.", {"D": 2}),
            ("C", "I focus on what is most likely to come up in the exam.", {"D": 1}),
            ("D", "I mostly do what I'm told and hope it will be enough.", {"D": -1}),
        ],
    },
    {
        "id": 14,
        "prompt": "When a diagram and a paragraph explain the same thing, I…",
        "choices": [
            ("A", "Read the paragraph carefully first, then glance at the diagram.", {"V": -1}),
            ("B", "Look at the diagram first, then use the paragraph to confirm details.", {"V": 1}),
            ("C", "Use both equally — they feel like one thing together.", {}),
            ("D", "Only use the one I need, depending on the question.", {}),
        ],
    },
]


# Profile identifiers stored in User.learning_style_profile.
# These are study-preference labels, not "learning styles" — see §1.5.
VALID_STYLES = (
    "diagram_led_synthesiser",    # Visual × Global  (Profile 1)
    "structured_builder",         # Verbal × Sequential (Profile 2)
    "active_experimenter",        # Visual × Sequential (Profile 3)
    "reflective_theorist",        # Verbal × Global (Profile 4)
    "balanced_hybrid",            # near midpoint on V and S
)

# One-line human-readable summary — rendered on the post-quiz card.
PROFILE_TAGLINES = {
    "diagram_led_synthesiser":
        "You process spatial relationships most fluently and want the big picture before the details.",
    "structured_builder":
        "You learn best from ordered chains of reasoning expressed in precise written language.",
    "active_experimenter":
        "You understand by doing — visual worked examples and step-by-step practice are where it clicks.",
    "reflective_theorist":
        "You engage with ideas through language and reflection — why and how it fits matter most.",
    "balanced_hybrid":
        "Your preferences are near-midpoint on every axis — the hybrid template gives you the best of each profile.",
}

# Accent colour per profile for UI.
PROFILE_COLORS = {
    "diagram_led_synthesiser": "oklch(50% 0.14 200)",   # teal
    "structured_builder":      "oklch(45% 0.13 264)",   # indigo
    "active_experimenter":     "oklch(52% 0.13 30)",    # coral
    "reflective_theorist":     "oklch(45% 0.12 150)",   # forest
    "balanced_hybrid":         "oklch(45% 0.05 264)",   # muted slate
}

# Human-readable name on cards.
PROFILE_NAMES = {
    "diagram_led_synthesiser": "Diagram-Led Synthesiser",
    "structured_builder":      "Structured Builder",
    "active_experimenter":     "Active Experimenter",
    "reflective_theorist":     "Reflective Theorist",
    "balanced_hybrid":         "Balanced",
}


# ── Scoring ──────────────────────────────────────────────────────────


def score_answers(answers: dict[int, str]) -> dict[str, int]:
    """Compute V / S / D totals from {question_id: chosen_letter}.

    Returns a dict {V: int, S: int, D: int}. Missing/invalid answers contribute 0.
    """
    totals = {"V": 0, "S": 0, "D": 0}
    for q in QUIZ:
        chosen = answers.get(q["id"])
        if not chosen:
            continue
        for letter, _label, scores in q["choices"]:
            if letter == chosen:
                for dim, delta in scores.items():
                    if dim in totals:
                        totals[dim] += delta
                break
    return totals


def classify(answers: dict[int, str]) -> dict:
    """Run the full classification pipeline. Returns:
      {
        "profile":    one of VALID_STYLES,
        "scores":     {"V": int, "S": int, "D": int},
        "sr_overlay": bool,
      }

    Classification rule (learning-styles-research §4.3):
      - V ≥ +2 → Visual; V ≤ −2 → Verbal; else Balanced on V.
      - S ≥ +2 → Sequential; S ≤ −2 → Global; else Balanced on S.
      - Balanced on BOTH → balanced_hybrid.
      - Otherwise take the non-balanced axis as decisive.
    SR overlay applies when D ≤ +3.
    """
    scores = score_answers(answers)
    v, s, d = scores["V"], scores["S"], scores["D"]

    v_side = "visual" if v >= 2 else "verbal" if v <= -2 else "balanced"
    s_side = "sequential" if s >= 2 else "global" if s <= -2 else "balanced"

    if v_side == "balanced" and s_side == "balanced":
        profile = "balanced_hybrid"
    else:
        # When one axis is balanced, the other axis is decisive: pick the
        # profile in the row/column of the non-balanced axis using the
        # tie-breaks from §4.3.
        if v_side == "balanced":
            v_side = "visual" if v >= 0 else "verbal"
        if s_side == "balanced":
            s_side = "sequential" if s >= 0 else "global"

        if v_side == "visual" and s_side == "global":
            profile = "diagram_led_synthesiser"
        elif v_side == "verbal" and s_side == "sequential":
            profile = "structured_builder"
        elif v_side == "visual" and s_side == "sequential":
            profile = "active_experimenter"
        else:
            profile = "reflective_theorist"

    return {
        "profile": profile,
        "scores": scores,
        "sr_overlay": d <= 3,
    }
