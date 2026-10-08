"""Behavioural tests that the JSON corpus cannot express: deep walkers,
non-string passthrough, prompt injection, fast paths, the ftfy switch."""

from __future__ import annotations

import datetime
import json

import pytest

import pupiltree_latex as L
from pupiltree_latex import mojibake
from pupiltree_latex.audit import ALL_KINDS, DETECTORS


@pytest.mark.parametrize("fn", [L.repair, L.normalize, L.canonicalize, L.to_plain])
def test_string_functions_pass_non_strings_through(fn):
    for value in (None, 5, 2.5, True, {"a": 1}, ["x"]):
        assert fn(value) is value


def test_segment_and_audit_on_non_strings():
    assert L.segment(None) == []
    assert L.segment("") == []
    assert L.audit(None) == []
    assert L.audit(7) == []
    assert L.contains_math(None) is False


def test_repair_deep_touches_every_string_and_nothing_else():
    doc = {
        "question": "Area \x0crac{1}{2}",
        "options": [
            "\x08eta decay",
            {"text": "\times"},
        ],  # TAB + "imes" is a decoded \times
        "url": "https://x/\x0crac.png",  # repair is safe even on URLs
        "n": 3,
        "when": datetime.datetime(2026, 9, 25, 10, 0),
    }
    out = L.repair_deep(doc)
    assert out["question"] == "Area \\frac{1}{2}"
    assert out["options"][0] == "\\beta decay"
    assert out["options"][1]["text"] == "\\times"
    assert out["url"] == "https://x/\\frac.png"
    assert out["n"] == 3
    assert out["when"] == doc["when"]


def test_canonicalize_deep_skips_non_content_keys_and_urls():
    doc = {
        "_id": "ahs_69e74f5e84fd",
        "audioUrl": "https://s/ahs_69e74f5e84fd_vocab_20260425.wav",
        "className": "10_A",
        "status": "in_progress",
        "question": "Water is H_{2}O at 3 × 10^8",
        "options": [{"id": "opt_a_1", "text": "π"}],
        "createdAt": datetime.datetime(2026, 9, 25, 10, 0),
        "nested": {"description": "see https://a/b_c.png here"},
    }
    out = L.canonicalize_deep(doc)
    assert out["_id"] == doc["_id"]
    assert out["audioUrl"] == doc["audioUrl"]
    assert out["className"] == "10_A"
    assert out["status"] == "in_progress"
    assert out["question"] == "Water is $H_{2}O$ at 3 $\\times$ $10^8$"
    assert out["options"][0]["id"] == "opt_a_1"
    assert out["options"][0]["text"] == "$\\pi$"
    assert out["createdAt"] == "2026-09-25T10:00:00+00:00"
    assert out["nested"]["description"] == "see https://a/b_c.png here"


def test_canonicalize_is_idempotent_on_typical_content():
    samples = [
        "The price is $50 and the ratio is 1/\\sqrt{2}",
        "Cost $60 and $x^2$",
        "\\left[ $\\frac12$ \\right] $\\frac{q^2}{a^2}$",
        "H_{2}O and MCQ_SINGLE and 3^{\\circ}C",
        "√2 and ħω and π and 3 × 10^8",
        "{{IMAGE:59_1}} then \\frac{a}{b}",
    ]
    for s in samples:
        once = L.canonicalize(s)
        assert L.canonicalize(once) == once, s


def test_normalize_is_idempotent_on_typical_content():
    samples = [
        "\\(\\theta\\) costs $5000 and $\\frac14$ then \\nNext",
        "Cost \\$60 and $x^2$ end \\( orphan",
        "Ï€ is Ã— fun with âˆš2",
        "$5-$10 and $2x + 3$",
    ]
    for s in samples:
        once = L.normalize(s)
        assert L.normalize(once) == once, s


def test_normalize_never_wraps_or_converts():
    assert (
        L.normalize("√2 and π and \\frac{1}{2} and H_{2}O")
        == "√2 and π and \\frac{1}{2} and H_{2}O"
    )
    assert (
        L.normalize("https://a/b_c.png {{IMAGE:59_1}}")
        == "https://a/b_c.png {{IMAGE:59_1}}"
    )


def test_step_order_theta_inside_paren_delimiters():
    # B5: decoding prose escapes before normalising delimiters turned
    # `\(\theta\)` into TAB + "heta" (script_editor #420, tutor #383).
    assert (
        L.normalize("\\(\\theta\\) and \\(\\times 2\\)") == "$\\theta$ and $\\times 2$"
    )


def test_audit_deep_paths_and_skips():
    doc = {
        "question": "Area \x0crac{1}{2}",
        "raw_response": "\\(ignored\\)",
        "audio_url": "https://x/\\(y\\).wav",
        "options": [{"text": "$x^10$"}, {"text": "fine"}],
        "meta": json.dumps({"explanation": "\\(json leaf\\)"}),
    }
    found = L.audit_deep(doc)
    paths = {p: f.kind for p, f in found}
    assert paths["question"] == "control_char"
    assert paths["options[0].text"] == "script_missing_braces"
    assert paths["meta(json).explanation"] == "legacy_delimiter"
    assert not any(
        p.startswith("raw_response") or p.startswith("audio_url") for p in paths
    )


def test_audit_snippet_makes_control_chars_visible():
    (f,) = [x for x in L.audit("Area \x0crac{1}{2}") if x.kind == "control_char"]
    assert "<0x0C>" in f.snippet
    assert L.is_error(["control_char"]) is True
    assert L.is_error(["mojibake"]) is False
    assert L.count_by_kind(L.audit("\\(a\\) \\[b\\]")) == {"legacy_delimiter": 4}


def test_audit_unsupported_command_inside_math_only():
    assert L.audit_kinds("$\\frac{1}{2}$") == []
    assert L.audit_kinds("$\\ce{H2O}$") == []
    assert L.audit_kinds("$\\notacommand{x}$") == ["unsupported_command"]
    assert L.audit_kinds("prose \\notacommand{x}") == []
    assert L.audit_kinds("$\\mathscr{L}$") == ["unsupported_command"]
    assert L.audit_kinds("\\mathfrak{g}") == ["unsupported_command"]


def test_is_plain_prose_fast_path():
    assert L.is_plain_prose("Water boils at 100 degrees.") is True
    assert L.is_plain_prose("Water is $H_2O$") is False
    assert L.is_plain_prose("Use \\frac here") is False
    assert L.is_plain_prose("**bold**") is False
    assert L.is_plain_prose("- item") is False
    assert L.is_plain_prose("a\n\nb") is False
    assert L.is_plain_prose(None) is False


def test_contains_math():
    assert L.contains_math("$x$") is True
    assert L.contains_math("\\frac{1}{2}") is True
    assert L.contains_math("costs $5 and $10") is False
    assert L.contains_math("plain") is False


def test_prompt_rules_injection_is_idempotent():
    p = L.inject_latex_rules("Generate 5 questions.")
    assert p.startswith("\n=== MATHEMATICAL NOTATION")
    assert L.inject_latex_rules(p) == p
    n = L.inject_narrative_prose_rules("Write a story.")
    assert L.inject_narrative_prose_rules(n) == n
    assert L.has_formatting_contract(p) and L.has_formatting_contract(n)
    assert L.has_formatting_contract("nothing") is False
    ex = L.narrative_field_exemption("story_script", "sections[].content")
    assert "   - story_script" in ex and "   - sections[].content" in ex


def test_to_plain_rejects_unknown_style():
    with pytest.raises(ValueError):
        L.to_plain("$x$", "html")


def test_mojibake_table_and_ftfy_agree_on_common_patterns():
    for bad, good in (("Ï€", "π"), ("Ã—", "×"), ("âˆš2", "√2"), ("â‰¤", "≤")):
        assert L.fix_mojibake_table(bad) == good
        assert L.fix_mojibake_ftfy(bad) == good  # falls back to the table without ftfy


def test_mojibake_leaves_legitimate_accents_alone():
    assert L.fix_mojibake_table("Ångström and café") == "Ångström and café"
    assert L.fix_mojibake_table("plain ascii") == "plain ascii"


def test_export_tables_covers_every_shared_constant(tmp_path):
    from pupiltree_latex.export_tables import TABLES, export

    written = export(tmp_path)
    assert {p.stem for p in written} == set(TABLES)
    katex = json.loads((tmp_path / "katex_commands.json").read_text(encoding="utf-8"))
    assert "frac" in katex["value"] and katex["version"] == L.VERSION


def test_loads_model_json_raises_on_invalid_and_keeps_latex():
    assert L.loads_model_json('{"a": "\\frac{1}{2}"}') == {"a": "\\frac{1}{2}"}
    with pytest.raises(json.JSONDecodeError):
        L.loads_model_json('{"a": ')


def test_all_kinds_are_produced_by_some_detector():
    assert set(ALL_KINDS) == {
        "control_char",
        "legacy_delimiter",
        "unbalanced_dollar",
        "command_missing_argument",
        "frac_missing_args",
        "script_missing_braces",
        "mojibake",
        "double_escaped_command",
        "unsupported_command",
        "bare_unicode_math",
        "unicode_chemistry",
        "bare_left_brace",
        "lost_escape",
    }
    assert len(DETECTORS) == len(ALL_KINDS)


def test_has_ftfy_flag_matches_import():
    try:
        import ftfy  # noqa: F401

        assert mojibake.HAS_FTFY is True
    except ImportError:
        assert mojibake.HAS_FTFY is False
