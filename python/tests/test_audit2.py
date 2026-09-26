"""Audit round 2 (2026-09-26): invariants the corpus cases cannot state.

- A span created by `fix` never ends right before a digit or opens against a
  literal `$` (the renderers would drop it and a later pass nested `$$`).
- `fix` is idempotent on every audit input.
- The mojibake table repairs currency and keeps repeated Greek letters, with
  and without ftfy.
- `fix_deep` leaves taxonomy lists (`tags`, `labels`, `keywords`) alone.
"""

from __future__ import annotations

import importlib
import re

import pytest

import pupiltree_latex as L
from pupiltree_latex.commands import KATEX_COMMANDS

mojibake = importlib.import_module("pupiltree_latex.mojibake")

AUDIT_INPUTS = [
    "The product 3×4×5=60 is easy.",
    "If x≤5 then y≥2.",
    "Find 3.14×10⁻⁵ in standard form.",
    "3×10⁸ m/s and $E=mc^2$",
    "6.022×10²³ particles",
    "6.022 × 10²³ mol⁻¹",
    "CuSO₄·5H₂O",
    "Take n→∞ and x→0.",
    "Given ε₀ and μ₀, find c.",
    "λ₁, λ₂ are eigenvalues.",
    "σ₁₂",
    "µ₀ = 4π × 10⁻⁷ T·m/A",
    "x\\leq5 holds",
    "x$\\leq$5 holds",
    "Use \\pi2 here",
    "2×10 and 3 \\times4",
    "\\alpha_1 and \\beta^2",
    "\\\\\\frac{1}{2}",
    "\\\\$\\frac{1}{2}$",
    "$ H₂",
    "$H₂O",
    "$×5",
    "$\\leq 5",
    "Solve $ x^2 + 1 = 0 $ now",
    "Let $ \\theta = 30° $ here",
    "I paid $ 5 and got $ 3 back",
    "m/s² and per mm³ and x²5",
    "यदि x≤५ है",
    "\\sqrt{2}3 and \\frac{1}{2}4",
    "â‚¬5 and Â£3",
    "ππ and Ï€Ï€",
    "2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°",
]

_CMD_RE = re.compile(r"\\([A-Za-z]+)")


@pytest.mark.parametrize("s", AUDIT_INPUTS)
def test_fix_is_idempotent(s):
    once = L.fix(s)
    assert L.fix(once) == once


@pytest.mark.parametrize("s", AUDIT_INPUTS)
def test_fix_never_creates_display_math(s):
    out = L.fix(s)
    if "$$" in s or "\\[" in s:
        return
    assert not any(seg["display"] for seg in L.segment(out))
    assert not re.search(r"(?<!\\)\$\$", out), out


@pytest.mark.parametrize("s", AUDIT_INPUTS)
def test_no_katex_command_left_next_to_a_dollar_in_prose(s):
    """A `\\cmd` in a text segment right beside a `$` means a span broke."""
    for seg in L.segment(L.fix(s)):
        if seg["kind"] != "text":
            continue
        raw = seg["raw"]
        for m in _CMD_RE.finditer(raw):
            if m.group(1) not in KATEX_COMMANDS:
                continue
            before = raw[m.start() - 1] if m.start() else ""
            after = raw[m.end()] if m.end() < len(raw) else ""
            assert before != "$" and after != "$", (s, raw)


def test_prose_digits_are_byte_identical():
    s = "2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°"
    assert L.fix(s) == s
    assert L.canonicalize(s) == s


@pytest.mark.parametrize("with_ftfy", [True, False])
def test_currency_mojibake(monkeypatch, with_ftfy):
    if not with_ftfy:
        monkeypatch.setattr(mojibake, "HAS_FTFY", False)
    elif not mojibake.HAS_FTFY:
        pytest.skip("ftfy not installed")
    assert L.fix("â‚¬5") == "€5"
    assert L.canonicalize("â‚¬5") == "€5"
    assert L.fix("Price Â£5, â‚¹500, Â¥3") == "Price £5, ₹500, ¥3"
    assert "neg" not in L.fix("â‚¬5 and â‚¹2,50,000")


@pytest.mark.parametrize("with_ftfy", [True, False])
def test_repeated_greek_is_kept(monkeypatch, with_ftfy):
    if not with_ftfy:
        monkeypatch.setattr(mojibake, "HAS_FTFY", False)
    elif not mojibake.HAS_FTFY:
        pytest.skip("ftfy not installed")
    assert L.fix("ππ") == "$\\pi\\pi$"
    assert L.fix("ωω") == "$\\omega\\omega$"
    assert L.fix("Ï€Ï€") == "$\\pi\\pi$"
    assert L.normalize("αα and λλ") == "αα and λλ"


def test_table_still_collapses_a_pair_made_by_a_context_rule():
    # `Ï` next to a real π is mojibake of the same letter: one π, not two.
    assert L.fix_mojibake_table("2Ïπ") == "2π"


def test_fix_deep_skips_taxonomy_lists():
    doc = {
        "tags": ["x_1", "E_n"],
        "labels": ["a^2"],
        "keywords": ["H₂O"],
        "text": "x_1",
    }
    out = L.fix_deep(doc)
    assert out["tags"] == ["x_1", "E_n"]
    assert out["labels"] == ["a^2"]
    assert out["keywords"] == ["H₂O"]
    assert out["text"] == "$x_1$"
    assert L.canonicalize_deep(doc)["tags"] == ["x_1", "E_n"]
