"""Audit round 3 (2026-09-26): invariants the corpus cases cannot state.

- Greek words (`2πr`, `fλ`, `Δx`) become one span; units, Greek prose,
  long Latin words and identifiers keep their earlier shape.
- `canonicalize` closes the last group of a span that was never closed
  (`$\\frac{1}{2$`), never guessing an empty argument, and `audit` is clean
  afterwards.
- Both rules are idempotent and never move or drop a digit.
"""

from __future__ import annotations

import re

import pytest

import pupiltree_latex as L
from pupiltree_latex.unicode_math import greek_word_at

GREEK_WORD_INPUTS = [
    "Area = 2πr and πr²",
    "Circumference 2πr",
    "v = fλ",
    "E = hν",
    "Δx·Δp ≥ ħ/2",
    "ωt + φ",
    "ρL",
    "2πrh",
    "sin θ",
    "nλ = d sinθ",
    "ΔG = ΔH − TΔS",
    "2.5λ and ₹2π",
    "x≤2πr and 3×πr",
    "πr^2 and 2πr_1",
    "ΔH₂O",
    "e^{iπ}",
    "Cost \\$5π",
    "q_π and २π and πक",
]

# Units keep exactly the shape they had before audit round 3.
UNITS = {
    "5 µs": "5 $\\mu$s",
    "10 kΩ": "10 k$\\Omega$",
    "3 MΩ": "3 M$\\Omega$",
    "2 µm": "2 $\\mu$m",
    "5 µg": "5 $\\mu$g",
    "4 mΩ": "4 m$\\Omega$",
    "Ω·m": "$\\Omega\\cdot$m",
    "J·s": "J$\\cdot$s",
    "10Ω": "10$\\Omega$",
    "5μs": "5$\\mu$s",
    "10kΩ": "10k$\\Omega$",
    "2 GΩ": "2 G$\\Omega$",
    "3 µF": "3 $\\mu$F",
    "1 μΩ": "1 $\\mu\\Omega$",
    "kΩm": "k$\\Omega$m",
    "5 μm²": "5 $\\mu m^{2}$",  # merged by merge_adjacent_math, as before
}

BRACE_FIXED = {
    "$\\frac{1}{2$": "$\\frac{1}{2}$",
    "$x^{2$": "$x^{2}$",
    "$\\sqrt{x+1$": "$\\sqrt{x+1}$",
    "$x_{i$ and $\\vec{F$": "$x_{i}$ and $\\vec{F}$",
    "$\\frac{a}{b$ and $y$": "$\\frac{a}{b}$ and $y$",
    # `$y$` is a span, so the text segment before it holds exactly one pair.
    "$x^{2$ and $y$ and $z": "$x^{2}$ and $y$ and $z",
}

BRACE_KEPT = [
    "$\\frac{1}{$",
    "$\\frac{$",
    "$x^{$",
    "$x^{2^$",
    "$\\frac{1}{\\sqrt$",
    "$\\frac{\\frac{1}{2$",
    "$\\left( x^{2$",
    "$\\begin{matrix} x^{2$",
    "$a}{b$",
    "$\\{x$",
    "$\\frac{1}{2 $",
    "$\\frac{1}{2$5",
    "$$\\frac{1}{2$$",
    "$x^{2$ and $z",  # odd count of dollars on the line
]

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")


def _digits(s: str) -> list[str]:
    return re.findall(r"\d", s.translate(_SUP))


@pytest.mark.parametrize("text", GREEK_WORD_INPUTS + list(UNITS) + list(BRACE_FIXED))
def test_idempotent_and_digits_kept(text):
    out = L.fix(text)
    assert L.fix(out) == out
    assert _digits(out) == _digits(text)


@pytest.mark.parametrize("text,expected", sorted(UNITS.items()))
def test_units_keep_their_shape(text, expected):
    assert L.fix(text) == expected


def test_greek_word_spans():
    assert L.fix("Circumference 2πr") == "Circumference $2\\pi r$"
    assert L.fix("v = fλ") == "v = $f\\lambda$"
    assert L.fix("E = hν") == "E = $h\\nu$"
    assert L.fix("ωt + φ") == "$\\omega t$ + $\\phi$"
    assert L.fix("ρL") == "$\\rho L$"
    assert L.fix("2πrh") == "$2\\pi rh$"
    assert L.fix("sin θ") == "sin $\\theta$"
    assert L.fix("Δx·Δp ≥ ħ/2") == "$\\Delta x\\cdot\\Delta p \\geq \\hbar$/2"


def test_greek_word_refusals():
    # 3+ Latin letters, Greek prose, identifiers, scripts, other scripts.
    for text in ("αβγtest", "Thetaα", "λmax", "sinθ", "λόγος", "Ελλάδα", "q_π"):
        out = L.fix(text)
        assert not re.search(r"\\[A-Za-z]+ [A-Za-z]", out), (text, out)
    assert greek_word_at("αβγtest", 0) is None
    assert greek_word_at("λόγος", 0) is None
    assert greek_word_at("x^iπ", 3) is None
    assert greek_word_at("२π", 1) is None
    assert greek_word_at("πक", 0) is None
    assert greek_word_at("10 kΩ", 4) is None
    assert greek_word_at("5μs", 1) is None
    assert greek_word_at("ΔH₂O", 0) is None
    assert greek_word_at("a 2πr b", 3) == (2, 5)
    assert greek_word_at("2.5λ", 3) == (0, 4)


def test_radical_coefficient_untouched():
    assert L.fix("2√3") == "2$\\sqrt{3}$"
    assert L.fix("2$\\sqrt{3}$") == "2$\\sqrt{3}$"


@pytest.mark.parametrize("text,expected", sorted(BRACE_FIXED.items()))
def test_unclosed_group_is_closed(text, expected):
    assert L.canonicalize(text) == expected
    assert L.fix(text) == expected
    # The trailing `$z` of one case is a real unbalanced dollar.
    assert [f for f in L.audit(expected) if f.kind != "unbalanced_dollar"] == []


@pytest.mark.parametrize("text", BRACE_KEPT)
def test_unclosed_group_kept_when_closing_would_guess(text):
    assert L.canonicalize(text) == text


def test_brace_close_is_not_a_normalize_or_repair_rule():
    assert L.normalize("$\\frac{1}{2$") == "$\\frac{1}{2$"
    assert L.repair("$\\frac{1}{2$") == "$\\frac{1}{2$"


# ---------------------------------------------------------------------------
# audit3-script-group: no `$` inside an open brace group of a math span
# ---------------------------------------------------------------------------

SCRIPT_GROUP_INPUTS = [
    "e^{iπ}",
    "e^{iπt}",
    "x_{α}",
    "10^{-3}μ",
    "\\frac{π}{2}",
    "\\sqrt{2π}",
    "sin^{2}θ",
    "a_{αβ} and e^{i×π}",
    "\\text{π} and \\vec{α}",
    "\\frac{π} and x^{π",
    "the set {α, β}",
    "q_{π}_x",
]


def _dollar_in_open_group(value: str) -> bool:
    depth = 0
    i = 0
    while i < len(value):
        c = value[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c == "$" and depth > 0:
            return True
        i += 1
    return False


def _all_corpus_inputs() -> list[str]:
    import json
    from pathlib import Path

    out: list[str] = []
    for path in sorted((Path(__file__).resolve().parents[2] / "corpus").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("function") == "json_transport":
            continue
        out += [c["input"] for c in data["cases"] if isinstance(c.get("input"), str)]
    return list(dict.fromkeys(out + SCRIPT_GROUP_INPUTS))


def test_fix_never_puts_a_dollar_inside_an_open_group_of_a_math_span():
    bad = []
    for text in _all_corpus_inputs():
        out = L.fix(text)
        # A span that was already in the input as written (Backend's
        # `$\text{VS} = $\frac{\text{CS}$}{R}$` is left alone on purpose)
        # is not something fix introduced.
        before = {s["value"] for s in L.segment(L.repair(text)) if s["kind"] == "math"}
        for seg in L.segment(out):
            if (
                seg["kind"] == "math"
                and _dollar_in_open_group(seg["value"])
                and seg["value"] not in before
            ):
                bad.append((text, out))
    assert bad == []


@pytest.mark.parametrize("text", SCRIPT_GROUP_INPUTS)
def test_script_groups_idempotent_and_digits_kept(text):
    out = L.fix(text)
    assert L.fix(out) == out
    assert _digits(out) == _digits(text)
