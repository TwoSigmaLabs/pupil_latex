"""Quick manual probes (used while reading the code)."""

import os, sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python")
)
from pupiltree_latex import (
    fix,
    normalize,
    canonicalize,
    to_plain,
    audit_kinds,
    segment,
    loads_latex_aware,
)
from pupiltree_latex.unicode_math import wrap_bare_unicode_math
from pupiltree_latex.mojibake import fix_mojibake_ftfy

cases = [
    "Ξσ₂",
    "q_001_easy_2026C⁻",
    "5\\i\\",
    "\\·",
    "2^10",
    "x_12",
    "\\frac{π}{2}",
    "\\sqrt2",
    "\\frac12",
    "\\vec F",
    "Let x be \\alpha",
    "यह \\alpha कण है",
    "{{IMAGE:x_1}} \\alpha = 3",
    "a b",
    "&amp;amp;",
    "x—¹y",
    "\\ref{eq1}",
    "Class 10_A students",
    "my_var = 3",
    "$$a \\\\\\frac{1}{2}$$",
    "H₂O",
    "3 × 10⁸",
    "$\\text{H₂O}$",
    "$\\text{25°C}$",
    "$\\text{5 × 3}$",
    "\\textsc{abc}",
    "a \\\\nb",
    "$x^10$ and 2^10",
    "$\\sqrt$2",
    "√2",
    "ab⃗",
    "SO₄²⁻",
    "Fe³⁺",
    "The angle is 30° and π/2",
    "x⃗ · y⃗",
    "a … b",
    "\\theta is \\theta",
    "Cost: $5 and $\\frac14$",
    "$5 $",
    "$5$",
    "US$ 5",
    "\\text{costs $5}",
    "5\\ \\text{m}",
    "x \\in A",
    "See \\ref{fig}",
    "\\\\cdots",
    "\\\\ce{H2O}",
    "\\hbar\\omega",
    "ħω",
]
for s in cases:
    f1 = fix(s)
    f2 = fix(f1)
    flag = "" if f1 == f2 else "   NOT IDEMPOTENT -> " + repr(f2)
    print(repr(s), "->", repr(f1), flag)
print()
print("canon Ξσ₂       :", repr(canonicalize("Ξσ₂")))
print("wrap  Ξσ₂       :", repr(wrap_bare_unicode_math("Ξσ₂")))
print(
    "ftfy  2026C⁻    :",
    repr(fix_mojibake_ftfy("2026C⁻")),
    repr(fix_mojibake_ftfy("q_001_easy_2026C⁻")),
)
print(
    "ftfy  abc       :", repr(fix_mojibake_ftfy("x⁻")), repr(fix_mojibake_ftfy("2026C"))
)
print(
    "to_plain:",
    [
        to_plain(x)
        for x in [
            "\\neg p",
            "\\top",
            "\\inf",
            "\\pmod{n}",
            "a \\leqslant b",
            "\\newline",
            "\\intercal",
        ]
    ],
)
print(
    "tts     :",
    [
        to_plain(x, "tts")
        for x in ["$x^{20}$", "$\\frac{\\frac{1}{2}}{3}$", "$x^{30}$", "$\\pmatrix$"]
    ],
)
for j in ['{"q": "5\\\\ \\\\text{m}"}', '{"q": "a\\\\1"}', '{"q": "a \\\\\\\\ b"}']:
    try:
        print("json", j, "->", repr(loads_latex_aware(j)))
    except Exception as e:
        print("json", j, "-> RAISES", type(e).__name__, e)
