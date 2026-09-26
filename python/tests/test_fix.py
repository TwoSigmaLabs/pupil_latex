"""Behaviour of the one-call entry point and its two extra steps."""

from __future__ import annotations

import pupiltree_latex as L


def test_fix_is_the_composition_and_idempotent():
    s = "Cost $5 and \\(\\theta\\) with \x0crac{1}{2} and π and H₂O and 3 \\times 10^8"
    out = L.fix(s)
    assert out == (
        "Cost \\$5 and $\\theta$ with $\\frac{1}{2}$ and $\\pi$ and "
        "$\\text{H}_{2}\\text{O}$ and 3 $\\times 10^8$"
    )
    assert L.fix(out) == out
    assert L.audit_kinds(out) == []
    assert L.fix(None) is None
    assert L.fix("") == ""


def test_fix_deep_skips_non_content_and_urls():
    doc = {
        "_id": "q_001_easy_2026",
        "imageUrl": "https://s/x/uuid_page0.png",
        "status": "in_progress",
        "questionText": "Balance 2H₂ + O₂ → 2H₂O at 25 °C",
        "options": [{"id": "opt_a_1", "text": "√2 and $x^10$"}],
    }
    out = L.fix_deep(doc)
    assert out["_id"] == doc["_id"]
    assert out["imageUrl"] == doc["imageUrl"]
    assert out["status"] == doc["status"]
    assert out["questionText"] == (
        "Balance $\\text{2H}_{2}$ + $\\text{O}_{2} \\rightarrow \\text{2H}_{2}\\text{O}$ at 25 °C"
    )
    assert out["options"][0] == {"id": "opt_a_1", "text": "$\\sqrt{2}$ and $x^{10}$"}


def test_wrap_bare_symbol_commands_only_outside_math():
    assert (
        L.wrap_bare_symbol_commands("a \\times b and $c \\times d$")
        == "a $\\times$ b and $c \\times d$"
    )
    assert (
        L.wrap_bare_symbol_commands("\\timesx") == "\\timesx"
    )  # not a whole command name
    assert L.wrap_bare_symbol_commands("no commands") == "no commands"
    assert (
        L.wrap_bare_symbol_commands("\\frac{1}{2}") == "\\frac{1}{2}"
    )  # structural: canonicalize's job


def test_merge_adjacent_math_rules():
    assert L.merge_adjacent_math("$a$ $b$ $c$") == "$a b c$"
    assert L.merge_adjacent_math("$a$\t$b$") == "$a b$"
    assert L.merge_adjacent_math("$a$ x $b$") == "$a$ x $b$"
    assert L.merge_adjacent_math("$$a$$ $$b$$") == "$$a$$ $$b$$"
    assert L.merge_adjacent_math("$a$ $b$\nnext") == "$a b$\nnext"
    assert L.merge_adjacent_math("cost \\$5 \\$6") == "cost \\$5 \\$6"


def test_wrap_unicode_chemistry_shapes():
    cases = {
        "H₂O": "$\\text{H}_{2}\\text{O}$",
        "SO₄²⁻": "$\\text{SO}_{4}^{2-}$",
        "Fe³⁺": "$\\text{Fe}^{3+}$",
        "Ca(OH)₂": "$\\text{Ca(OH)}_{2}$",
        "(H₂O)": "($\\text{H}_{2}\\text{O}$)",
        "2H₂O": "$\\text{2H}_{2}\\text{O}$",
        "10⁸": "10⁸",
        "mc²": "mc²",
        "H2O": "H2O",
        "$H₂O$": "$H₂O$",
    }
    for inp, expected in cases.items():
        assert L.wrap_unicode_chemistry(inp) == expected, inp
