"""Service-layer unit tests. No Flask app context required — these exercise
pure logic (marking, feature flags, OCR stub, style classification)."""
from __future__ import annotations

import pytest

from services.marking import auto_mark, mark_mcq, mark_multi_cell, mark_scalar
from services.ocr import _stub_verdict, diagnose
from services.openai_client import feature_flag
from services.revision import compute_cache_key, generate_revision_note
from services.style_classifier import QUIZ, classify


def test_feature_flag_default_off():
    assert feature_flag("NONEXISTENT_FLAG") is False


def test_feature_flag_truthy_values(monkeypatch):
    for val in ("1", "true", "yes", "on", "TRUE", "YeS"):
        monkeypatch.setenv("X_FLAG", val)
        assert feature_flag("X_FLAG") is True


def test_mark_scalar_normalises_whitespace_and_case():
    assert mark_scalar("  4.5 ", "4.5") == "correct_optimal"
    assert mark_scalar("YES", "yes") == "correct_optimal"
    assert mark_scalar("4.5", "4.6") == "incorrect"


def test_mark_mcq_single_and_multi_correct():
    assert mark_mcq("A", ["A"]) == "correct_optimal"
    assert mark_mcq("B", ["A"]) == "incorrect"
    assert mark_mcq(["A", "B"], ["A", "B"]) == "correct_optimal"
    assert mark_mcq(["A"], ["A", "B"]) == "incorrect"


def test_mark_multi_cell_length_and_values():
    assert mark_multi_cell(["1", "2"], ["1", "2"]) == "correct_optimal"
    assert mark_multi_cell(["1", "2", "3"], ["1", "2"]) == "incorrect"
    assert mark_multi_cell(["1", "3"], ["1", "2"]) == "incorrect"


def test_auto_mark_unknown_schema_is_incorrect():
    assert auto_mark("graphical", "whatever", "whatever") == "incorrect"


def test_ocr_stub_respects_feature_flag(monkeypatch):
    # Flag off → always stub path, never hits OpenAI
    monkeypatch.delenv("FEATURE_OCR", raising=False)
    result = diagnose(
        photo_bytes=b"\x00",
        subpart_body="x",
        canonical_method=None,
        marking_alternatives=[],
        correct_answer="4",
        submitted_answer="4",
    )
    assert result["verdict"] == "correct_optimal"
    assert "OCR disabled" in result["transcript"]


def test_ocr_stub_detects_wrong_answer():
    result = _stub_verdict("3", "4")
    assert result["verdict"] == "incorrect"
    assert "Expected: 4" in result["suggested_correction"]


def test_revision_stub_renders_article_when_llm_off(monkeypatch):
    monkeypatch.delenv("FEATURE_REVISION_LLM", raising=False)
    html = generate_revision_note(
        topic_name="Functions",
        style="formula_first",
        error_tags=["algebraic_error"],
        topic_summary_html="<p>stub</p>",
    )
    assert "Functions" in html
    assert "formula first" in html
    assert "algebraic_error" in html


def test_cache_key_stable_for_same_snapshot():
    a = compute_cache_key(1, 2, "narrative", {"count": 3, "tags": ["sign_error"]})
    b = compute_cache_key(1, 2, "narrative", {"tags": ["sign_error"], "count": 3})
    assert a == b


def test_cache_key_changes_on_error_delta():
    a = compute_cache_key(1, 2, "narrative", {"count": 3})
    b = compute_cache_key(1, 2, "narrative", {"count": 4})
    assert a != b


def test_style_classifier_all_formula_first():
    answers = {q["id"]: "C" for q in QUIZ}  # C = formula_first in every question
    assert classify(answers) == "formula_first"


def test_style_classifier_empty_defaults_to_formula_first():
    assert classify({}) == "formula_first"


def test_style_classifier_all_narrative():
    answers = {q["id"]: "B" for q in QUIZ}
    assert classify(answers) == "narrative"


# Filename parser tests moved to local_ingest (it's the canonical owner now).
