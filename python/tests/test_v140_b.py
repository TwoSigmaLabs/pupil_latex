"""1.4.0 Group B behaviour that the corpus cannot express (deep walks,
positions, keyword options). Tags v140-b<n>."""

from __future__ import annotations

import json

import pytest

import pupiltree_latex as L

NARRATIVE = ("story_script", "transcript", "script@transcript")


def test_fix_deep_narrative_keys_get_repair_only():
    doc = {
        "question": "Area = πr²",
        "story_script": "Then π \x0crac{1}{2} and H₂O",
        "podcast": {"transcript": "x² is πr", "script": "x² here"},
        "lesson": {"script": "x² here"},
        "_id": "q_1",
    }
    out = L.fix_deep(doc, narrative_keys=NARRATIVE)
    assert out["question"] == "Area = $\\pi r^{2}$"
    # Class B: lossless repair only, never upgraded to LaTeX.
    assert out["story_script"] == "Then π \\frac{1}{2} and H₂O"
    assert out["podcast"]["transcript"] == "x² is πr"
    # `script@transcript`: a script beside a transcript is narration ...
    assert out["podcast"]["script"] == "x² here"
    # ... and a lesson script elsewhere is Class A.
    assert out["lesson"]["script"] == "$x^{2}$ here"
    assert out["_id"] == "q_1"


def test_fix_deep_without_narrative_keys_is_unchanged_behaviour():
    doc = {"transcript": "x²", "items": ["π", {"story_script": "π"}]}
    assert L.fix_deep(doc) == {
        "transcript": "$x^{2}$",
        "items": ["$\\pi$", {"story_script": "$\\pi$"}],
    }


def test_fix_deep_narrative_lists_and_nested_values():
    doc = {"story_sections": [{"text": "π \x0crac{1}{2}"}, "x²"]}
    out = L.fix_deep(doc, narrative_keys=["story_sections"])
    assert out == {"story_sections": [{"text": "π \\frac{1}{2}"}, "x²"]}


def test_canonicalize_deep_narrative_keys():
    doc = {"q": "π", "transcript": "π", "script": "π"}
    out = L.canonicalize_deep(doc, narrative_keys=NARRATIVE)
    assert out == {"q": "$\\pi$", "transcript": "π", "script": "π"}


def test_currency_spans_positions():
    text = "Rs $5 and \\$10.50, ₹ 45,00,000 and $x^2$"
    spans = L.currency_spans(text)
    assert [s["text"] for s in spans] == ["$5", "\\$10.50", "₹ 45,00,000"]
    for s in spans:
        assert text[s["start"] : s["end"]] == s["text"]
    assert L.currency_spans(None) == []
    assert L.currency_spans("") == []


def test_needs_fix_non_strings_and_chemistry_option():
    assert L.needs_fix(None) is False
    assert L.needs_fix(5) is False
    assert L.needs_fix("\\ce{H2O}") is True
    assert L.needs_fix("\\ce{H2O}", chemistry=False) is False


def test_normalize_option_text_non_strings_and_idempotent():
    assert L.normalize_option_text(None) is None
    assert L.normalize_option_text("") == ""
    for text in ("$\\text{H_{2}O}$", "$50 \\text{ %}$", "\\text{rises} when $x > 0$"):
        once = L.normalize_option_text(text)
        assert L.normalize_option_text(once) == once


def test_normalize_code_spans_keyword_only_and_default_off():
    assert L.normalize("`x^2`") == "`x^2`"
    assert L.normalize("`x^2`", code_spans_as_math=True) == "$x^2$"
    with pytest.raises(TypeError):
        L.normalize("`x^2`", True)  # type: ignore[misc]


def test_loads_model_json_lenient_flag():
    assert L.loads_model_json('{"a": "\\q"}') == {"a": "\\q"}
    assert L.loads_model_json('{"a": "\\q"}', lenient=True) == {"a": "\\q"}
    with pytest.raises(json.JSONDecodeError):
        L.loads_model_json('{"a": "\\q"}', lenient=False)
    with pytest.raises(json.JSONDecodeError):
        L.loads_model_json('{"a": "x\ny"}', lenient=False)
    assert L.loads_latex_aware('{"a": "\\q"}', strict=False) == {"a": "\\q"}


def test_repair_currency_aware_span_needs_guess_whitespace():
    text = "costs $5.\nangle ABC costs $10"
    assert L.repair(text, guess_whitespace=True) == text
    assert L.repair(text, guess_whitespace=False) == text


def test_lost_escape_is_not_an_error_kind():
    assert "lost_escape" in L.ALL_KINDS
    assert not L.is_error(["lost_escape"])
    assert L.is_error(L.audit_kinds("a\x7fb"))


@pytest.mark.parametrize(
    "text",
    [
        "$x}$",
        "${{x}}$ and $\\fre{a}{b}$",
        "What is $x + 1",
        "\\$1.56 \\text{ m}$",
        "$\\AA$ and \\text{\\AA}",
        "costs $5.\nangle ABC costs $10",
    ],
)
def test_fix_idempotent_on_new_repairs(text):
    once = L.fix(text)
    assert L.fix(once) == once
