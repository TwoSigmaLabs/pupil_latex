"""Property fuzzer for pupiltree_latex (review deliverable, spec task 2).

    set PYTHONPATH=..\..\python
    python fuzz.py [N] [seed]

Generates N random inputs (default 20000) from grammars that mix prose,
currency, math, Unicode math, chemistry, control characters, mojibake, image
markers, URLs, ids, JSON, markdown, long strings and odd Unicode, then checks
for every input:

  (a) fix idempotent                       (b) fix never throws
  (c) fix runtime < 50 ms per 10 kB        (d) prose words / URLs / ids / markers survive verbatim
  (e) audit(fix(x)) has no control_char, legacy_delimiter, mojibake,
      bare_left_brace, double_escaped_command
  (f) every math segment of fix(x) parses with KaTeX (+mhchem); blamed on fix
      only when the input's own math segments parsed (or the input had none)
  (g) to_plain(fix(x)) has no \\cmd, $, {, } residue
  (h) loads_latex_aware(json.dumps({"q": x}))["q"] == x for control-free x;
      loads_latex_aware('{"q": "' + raw + '"}') never yields control chars

Failures are minimised (atom-level then character-level delta debugging),
classified by a root-cause signature and written to fuzz_results.json.
"""

from __future__ import annotations

import json
import os
import random
from functools import lru_cache
import re
import sys
import time
import traceback
from collections import Counter, defaultdict

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python")
)

from pupiltree_latex import (  # noqa: E402
    KATEX_COMMANDS,
    MOJIBAKE_TABLE,
    UNICODE_MATH,
    audit_kinds,
    canonicalize,
    fix,
    loads_latex_aware,
    normalize,
    segment,
    to_plain,
)
from katex_client import KaTeX  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KATEX = KaTeX()
FIX = lru_cache(maxsize=300000)(fix)

# ---------------------------------------------------------------------------
# Atom grammar. Every atom is (text, kind, must_keep) where must_keep lists
# substrings that a content-preserving fix must keep verbatim.
# ---------------------------------------------------------------------------

PROSE_WORDS = (
    "apple river school teacher student number answer water force energy motion "
    "chapter question option because through velocity speed distance angle circle "
    "triangle square value equal solve simplify explain describe compare marks "
    "example figure diagram table graph reaction element compound acid base salt "
    "photosynthesis cell nucleus plant animal history geography language grammar "
    "sentence paragraph story poem lesson class board grade section board exam "
    "nutrients digestion respiration wavelength frequency amplitude resistance "
    "current voltage power work heat temperature pressure volume density mass "
    "weight gravity friction momentum impulse torque orbit planet satellite "
    "electron proton neutron isotope valency molecule solution mixture filter"
).split()
SHORT_WORDS = (
    "a an the of in on at to is be it x y z we he if so or by Let Use for and".split()
)
HINDI = ["यह एक प्रश्न है", "पानी का सूत्र", "बल और गति", "उत्तर लिखिए", "कक्षा दस"]
RTL = ["مرحبا بالعالم", "שלום"]
EMOJI = ["😀", "👍🏽", "👨‍👩‍👧", "🧪", "​", "﻿", "\U0001f600‍"]
SURROGATES = ["\ud83d", "\ude00", "\ud800x"]
IDS = [
    "MCQ_SINGLE",
    "q_001_easy_2026",
    "ahs_69e74f5e84fd",
    "69e74f5e84fd1a2b3c4d5e6f",
    "FILL_BLANK",
    "TRUE_FALSE",
    "sess_2026_09_25",
    "10_A",
    "12_PCM_A",
    "my_var",
    "x_train",
    "file_name",
    "is_valid",
]
URLS = [
    "https://storage.googleapis.com/pupiltree/a_b/c_d.png",
    "http://example.com/path_with_under^caret?x=1&y=2",
    "gs://bucket/dir_1/img_2.jpg",
    "https://a.b/c_1.png?q=x_y^z#frag",
]
IMAGES = [
    "{{IMAGE:x_1}}",
    "{{IMAGE:q2_fig}}",
    "{{IMAGE:69e74f5e84fd}}",
    "{{IMAGE:diagram_a_b}}",
]
JSONISH = [
    '{"key": "value"}',
    '{"a": 1, "b": [2, 3]}',
    '{"q": "$x^2$"}',
    "[1, 2, 3]",
    '{"frac": "\\\\frac{1}{2}"}',
]
MARKDOWN = [
    "**bold**",
    "*italic*",
    "- item one",
    "1. first",
    "## Heading",
    "`code_x`",
    "> quote",
    "| a | b |",
    "---",
]
CURRENCY = [
    "$5",
    "$5,000.50",
    "\\$5",
    "$5-$10",
    "US$ 5",
    "$ 5",
    "costs $5.",
    "$5 $",
    "$5$",
    "$50 and $100",
    "$1,000",
    "$1.5e-3",
    "$5 to $10",
    "Rs. 5",
    "$5,",
    "($5)",
    "$5)",
    "5$",
    "$5x",
    "$100k",
]
CHEM = [
    "H₂O",
    "SO₄²⁻",
    "Fe³⁺",
    "Ca(OH)₂",
    "CO₂",
    "NH₄⁺",
    "H2O",
    "C₆H₁₂O₆",
    "Na⁺",
    "Cl⁻",
    "O₂ + 2H₂ → 2H₂O",
]
SCI = [
    "3 × 10⁸",
    "3 x 10^8",
    "3e8",
    "1.5e-3",
    "6.022 × 10²³",
    "10⁻³",
    "2^10",
    "x^10",
    "a_12",
    "10^{-3}",
    "5 × 10^3",
    "3·10⁸",
]
GREEK = "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΥΦΨΩ"
ESCAPES_LITERAL = [
    "\\n",
    "\\t",
    "\\r\\n",
    "\\r",
    "\\nStatement",
    "\\theta",
    "\\times",
    "\\text{a}",
    "\\nu",
    "\\ne",
    "\\ni",
    "\\not",
    "\\neg",
    "\\newline",
    "\\nabla",
    "\\rho",
    "\\right",
    "\\ref{x}",
    "\\tan",
    "\\to",
    "\\top",
    "\\tt",
    "\\nnext",
    "\\tHeta",
]
DOUBLE_ESC = [
    "\\\\frac{1}{2}",
    "\\\\alpha",
    "\\\\\\\\theta",
    "\\\\times",
    "\\\\cdots",
    "\\\\ce{H2O}",
    "\\\\mathscr{L}",
    "\\\\text{m}",
    "\\\\displaystyle",
    "\\\\left(",
    "\\\\right)",
]
LEFT_RIGHT = [
    "\\left{ x \\right}",
    "\\left\\{ x \\right\\}",
    "$\\left{$ and $\\right}$",
    "\\left( \\frac{a}{b} \\right)",
    "\\left[ x \\right]",
    "\\left. x \\right|",
]
ORPHANS = ["\\(", "\\)", "\\[", "\\]", "$", "$$", "\\\\[2pt]", "\\\\(", "\\\\)"]
MISC = [
    "%",
    "#",
    "&",
    "\\%",
    "\\#",
    "\\&",
    "~",
    "^",
    "_",
    "{",
    "}",
    "\\{",
    "\\}",
    "\\\\",
    "\\",
    "'",
    '"',
    "<b>",
    "&amp;",
    "&lt;",
    "&nbsp;",
    " ",
    "—¹",
    "5 km",
    "…",
    "·",
    "°C",
    "45°",
    "µm",
    "Ω",
    "K",
    "Å",
    "−5",
    "x‐y",
]
CONTROL_CHARS = [chr(c) for c in range(0x00, 0x20)] + ["\x7f"]
CMD_BY_LETTER = defaultdict(list)
for _c in sorted(KATEX_COMMANDS):
    if _c[0] in "bfntrv" and len(_c) >= 2:
        CMD_BY_LETTER[_c[0]].append(_c)
CTRL_FOR_LETTER = {
    "b": "\x08",
    "f": "\x0c",
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "v": "\x0b",
}
UNICODE_MATH_CHARS = list(UNICODE_MATH)
MOJIBAKE_KEYS = list(MOJIBAKE_TABLE)
MATH_UNICODE_SAMPLES = [
    "π",
    "√2",
    "√(x+1)",
    "√x",
    "√2gh",
    "α + β",
    "θ = 30°",
    "×",
    "≤",
    "→",
    "∞",
    "∫",
    "∑",
    "ℏω",
    "πr²",
    "½",
    "…",
    "∆x",
    "µ",
    "Ω",
    "x⃗",
    "a⃗ + b⃗",
    "∛8",
    "ħω",
    "−",
    "≠",
    "∈",
]


def _pick(rng, seq):
    return seq[rng.randrange(len(seq))]


def gen_math_body(rng, depth=0):
    """A random math body (the part between delimiters)."""
    choices = [
        lambda: _pick(
            rng,
            [
                "x^2",
                "x^{10}",
                "x^10",
                "a_12",
                "a_{12}",
                "x_i",
                "E = mc^2",
                "v = u + at",
                "F = ma",
                "a^2 + b^2 = c^2",
                "x^{-1}",
                "x^-1",
                "10^{-3}",
                "e^{i\\pi}",
                "x_1 + x_2",
                "x^10^2",
                "a_b_c",
                "2^{10}",
            ],
        ),
        lambda: (
            "\\frac{%s}{%s}"
            % (
                gen_math_body(rng, depth + 1) if depth < 2 else "1",
                gen_math_body(rng, depth + 1) if depth < 2 else "2",
            )
        ),
        lambda: _pick(
            rng,
            [
                "\\frac12",
                "\\frac 1 2",
                "\\sqrt2",
                "\\sqrt{2}",
                "\\sqrt[3]{8}",
                "\\sqrt",
                "\\vec F",
                "\\vec{F}",
                "\\hat n",
                "\\bar x",
                "\\frac{1}{2}",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "\\alpha",
                "\\beta",
                "\\theta",
                "\\pi",
                "\\omega",
                "\\Delta",
                "\\mu",
                "\\nu",
                "\\rho",
                "\\tau",
                "\\Omega",
                "\\epsilon",
                "\\varphi",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "\\times",
                "\\div",
                "\\pm",
                "\\leq",
                "\\geq",
                "\\neq",
                "\\approx",
                "\\to",
                "\\rightarrow",
                "\\infty",
                "\\cdot",
                "\\ldots",
                "\\cdots",
                "\\in",
                "\\not\\subset",
                "\\ne",
                "\\ni",
                "\\not",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "\\left( x \\right)",
                "\\left[ \\frac{a}{b} \\right]",
                "\\left\\{ x \\right\\}",
                "\\left{ x \\right}",
                "\\left. x \\right|",
                "\\left( x",
                "x \\right)",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "\\text{ m/s}",
                "\\text{if } x > 0",
                "\\text{H}_{2}\\text{O}",
                "\\text{costs $5}",
                "\\text{costs \\$5}",
                "\\text{50\\%}",
                "\\text{50%}",
                "\\text{a & b}",
                "\\text{π}",
                "\\text{H₂O}",
                "\\text{25°C}",
                "\\text{5 × 3}",
                "\\text{ and }",
                "\\text{Force}",
                "\\textbf{x}",
                "\\text{x^{2}}",
                "\\text{{a}}",
                "\\mathrm{H_2O}",
                "\\text{→}",
                "\\text{यह}",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "\\ce{H2O}",
                "\\ce{SO4^{2-}}",
                "\\ce{Ca(OH)2}",
                "\\pu{5 m/s}",
                "\\ce{2H2 + O2 -> 2H2O}",
                "\\mathscr{L}",
                "\\mathfrak{g}",
                "\\cal C",
                "\\boxed{42}",
                "\\textmu m",
                "\\cbrt{8}",
                "\\nicefrac{1}{2}",
                "\\textsuperscript{2}",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "\\begin{cases} x & x > 0 \\\\ -x & x \\le 0 \\end{cases}",
                "\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}",
                "\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}",
                "\\begin{align} a &= b \\end{align}",
                "\\begin{vmatrix} a & b \\\\ c & d \\end{vmatrix}",
                "\\begin{matrix} a \\\\\\frac{1}{2} \\end{matrix}",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "5\\,\\text{m/s}",
                "10\\ \\text{kg}",
                "a\\quad b",
                "a \\\\ b",
                "\\\\",
                "\\!",
                "\\,",
                "\\;",
                "a\\:b",
            ],
        ),
        lambda: _pick(
            rng,
            [
                "%",
                "#",
                "&",
                "\\%",
                "\\#",
                "\\&",
                "~",
                "$",
                "\\$5",
                "$$",
                "{",
                "}",
                "{{",
                "}}",
                "\\{",
                "\\}",
            ],
        ),
        lambda: _pick(rng, MATH_UNICODE_SAMPLES),
        lambda: "".join(
            _pick(rng, UNICODE_MATH_CHARS) for _ in range(rng.randint(1, 4))
        ),
        lambda: "".join(_pick(rng, GREEK) for _ in range(rng.randint(1, 5))),
        lambda: _pick(
            rng,
            [
                "\\n",
                "\\t",
                "\\r\\n",
                "\\nu",
                "\\theta",
                "\\nStatement",
                "\\ne",
                "\\ni",
                "\\not",
                "\\neg",
                "\\newline",
                "\\top",
                "\\tt",
                "\\ref{eq1}",
            ],
        ),
        lambda: _pick(rng, CHEM),
        lambda: _pick(rng, SCI),
        lambda: _pick(
            rng,
            ["\\\\frac{1}{2}", "\\\\alpha", "\\\\\\\\pi", "\\\\cdots", "\\\\text{x}"],
        ),
        lambda: _pick(
            rng,
            [
                "\\mathbb{R}",
                "\\mathcal{L}",
                "\\overline{AB}",
                "\\underline{x}",
                "\\dot{x}",
                "\\ddot{x}",
                "\\tilde{y}",
                "\\int_0^1 f(x)\\,dx",
                "\\sum_{i=1}^{n} i",
                "\\lim_{x \\to 0}",
                "\\binom{n}{k}",
                "\\prod_{k}",
                "\\oint",
            ],
        ),
        lambda: _pick(rng, ["\n", "\n\n", " \n ", "x\ny"]),
        lambda: _pick(
            rng,
            [
                "\x0crac{1}{2}",
                "\theta",
                "\x08eta",
                "\x0bec{F}",
                "\rho",
                "\nabla",
                "\nu",
                "\x0c",
                "\x00",
                "\x7f",
                "\x1b[0m",
            ],
        ),
        lambda: "\\frac{" * 20 + "1" + "}{2}" * 20,
        lambda: "{" * rng.randint(1, 30) + "x" + "}" * rng.randint(0, 30),
    ]
    parts = [_pick(rng, choices)() for _ in range(rng.randint(1, 4))]
    return _pick(rng, [" ", "", " + ", " = ", ", "]).join(parts)


def gen_math(rng):
    body = gen_math_body(rng)
    style = rng.random()
    if style < 0.40:
        return "$" + body + "$", "inline"
    if style < 0.55:
        return "$$" + body + "$$", "display"
    if style < 0.70:
        if rng.random() < 0.3:
            body = body.replace(" ", "\n", 1) if " " in body else body + "\n"
        return "\\(" + body + "\\)", "paren"
    if style < 0.85:
        if rng.random() < 0.4:
            body = "\n" + body + "\n"
        return "\\[" + body + "\\]", "bracket"
    if style < 0.92:
        return "$$\n" + body + "\n$$", "display_ml"
    return body, "bare"


def gen_control_command(rng):
    letter = _pick(rng, "bfntrv")
    cmd = _pick(rng, CMD_BY_LETTER[letter])
    ctrl = CTRL_FOR_LETTER[letter]
    tail = _pick(rng, ["", "{x}", " x", "{1}{2}", "2"])
    return ctrl + cmd[1:] + tail


def gen_mojibake(rng):
    style = rng.random()
    if style < 0.4:
        return _pick(rng, MOJIBAKE_KEYS)
    if style < 0.7:
        src = "".join(
            _pick(rng, GREEK + "×÷±√∞→≤≥≠²³₂₄°–—’“”…") for _ in range(rng.randint(1, 4))
        )
        try:
            return src.encode("utf-8").decode(
                _pick(rng, ["latin-1", "cp1252"]), errors="replace"
            )
        except Exception:
            return src.encode("utf-8").decode("latin-1")
    if style < 0.85:
        return _pick(
            rng,
            [
                "Ï€",
                "Ã—",
                "âˆš2",
                "Î±",
                "Î ",
                "Ï",
                "Ï/Ï",
                "2Ï",
                "â€”¹",
                "Ã©",
                "ÃƒÂ©",
                "naÃ¯ve",
                "cafÃ©",
                "Â",
                "Ã",
                "�",
            ],
        )
    return _pick(rng, PROSE_WORDS).encode("utf-8").decode("latin-1")


def gen_atom(rng):
    r = rng.random()
    if r < 0.28:
        w = _pick(rng, PROSE_WORDS)
        return w, "prose", [w]
    if r < 0.33:
        return _pick(rng, SHORT_WORDS), "short", []
    if r < 0.45:
        m, k = gen_math(rng)
        return m, "math_" + k, []
    if r < 0.50:
        return _pick(rng, CURRENCY), "currency", []
    if r < 0.53:
        return _pick(rng, CHEM), "chem", []
    if r < 0.56:
        return _pick(rng, SCI), "sci", []
    if r < 0.59:
        return _pick(rng, MATH_UNICODE_SAMPLES), "unicode_math", []
    if r < 0.61:
        return (
            "".join(_pick(rng, UNICODE_MATH_CHARS) for _ in range(rng.randint(1, 3))),
            "unicode_math",
            [],
        )
    if r < 0.63:
        return "".join(_pick(rng, GREEK) for _ in range(rng.randint(1, 6))), "greek", []
    if r < 0.67:
        return gen_control_command(rng), "control_cmd", []
    if r < 0.69:
        return _pick(rng, CONTROL_CHARS), "control", []
    if r < 0.73:
        return gen_mojibake(rng), "mojibake", []
    if r < 0.75:
        i = _pick(rng, IMAGES)
        return i, "image", [i]
    if r < 0.77:
        u = _pick(rng, URLS)
        return u, "url", [u]
    if r < 0.80:
        i = _pick(rng, IDS)
        return i, "id", [i]
    if r < 0.82:
        return _pick(rng, JSONISH), "json", []
    if r < 0.85:
        return _pick(rng, MARKDOWN), "markdown", []
    if r < 0.88:
        return _pick(rng, ESCAPES_LITERAL), "escape", []
    if r < 0.90:
        return _pick(rng, DOUBLE_ESC), "double_esc", []
    if r < 0.92:
        return _pick(rng, LEFT_RIGHT), "leftright", []
    if r < 0.94:
        return _pick(rng, ORPHANS), "orphan", []
    if r < 0.965:
        return _pick(rng, MISC), "misc", []
    if r < 0.975:
        h = _pick(rng, HINDI)
        return h, "hindi", [h]
    if r < 0.98:
        return _pick(rng, RTL), "rtl", []
    if r < 0.99:
        return _pick(rng, EMOJI), "emoji", []
    return _pick(rng, SURROGATES), "surrogate", []


SEPARATORS = [" ", " ", " ", "", "\n", ", ", ". ", ": ", " - ", "\n\n", "\t"]


def gen_input(rng, idx):
    """Returns (atoms, seps, kinds, must_keep). text = join."""
    mode = rng.random()
    if idx % 500 == 0:
        return [_pick(rng, ["", " ", "\n", "  \n\t ", " "])], [], ["empty"], []
    if idx % 250 == 7:  # long input, ~10 kB
        n = 900
    elif mode < 0.15:
        n = 1
    elif mode < 0.6:
        n = rng.randint(2, 5)
    else:
        n = rng.randint(5, 14)
    atoms, kinds, keep = [], [], []
    for _ in range(n):
        a, k, mk = gen_atom(rng)
        atoms.append(a)
        kinds.append(k)
        keep.extend(mk)
    seps = [_pick(rng, SEPARATORS) for _ in range(max(0, n - 1))]
    return atoms, seps, kinds, keep


def join(atoms, seps):
    out = []
    for i, a in enumerate(atoms):
        out.append(a)
        if i < len(seps):
            out.append(seps[i])
    return "".join(out)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
AUDIT_FORBIDDEN = {
    "control_char",
    "legacy_delimiter",
    "mojibake",
    "bare_left_brace",
    "double_escaped_command",
}
RESIDUE_CMD_RE = re.compile(r"\\[A-Za-z]")


def check_fix_throws(text):
    try:
        fix(text)
        return None
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def check_idempotent(text):
    f1 = FIX(text)
    f2 = FIX(f1)
    return None if f1 == f2 else (f1, f2)


def check_keep(text, keep):
    out = FIX(text)
    lost = [k for k in keep if k in text and k not in out]
    return lost or None


def check_audit(text):
    out = FIX(text)
    kinds = set(audit_kinds(out))
    bad = sorted(kinds & AUDIT_FORBIDDEN)
    return bad or None


def math_segments(text):
    return [(s["value"], s["display"]) for s in segment(text) if s["kind"] == "math"]


@lru_cache(maxsize=300000)
def katex_failures(text):
    fails = []
    for value, display in math_segments(text):
        ok, err = KATEX.render(value, display)
        if not ok:
            fails.append((value, err))
    return fails


def check_katex(text):
    """Returns (fails_after, blamed) where blamed is True when the input's own
    math rendered (or it had none) and fix's output does not."""
    out = FIX(text)
    fails_after = katex_failures(out)
    if not fails_after:
        return None
    fails_before = katex_failures(text)
    blamed = not fails_before
    return fails_after, blamed


def check_to_plain(text):
    out = FIX(text)
    plain = to_plain(out)
    problems = []
    if RESIDUE_CMD_RE.search(plain):
        problems.append("cmd:" + RESIDUE_CMD_RE.search(plain).group(0))
    if (
        ("{" in plain or "}" in plain)
        and "\\{" not in out
        and "\\}" not in out
        and "{{IMAGE:" not in out
        and "{" not in text
    ):
        problems.append("brace")
    if "$" in plain and "\\$" not in out and out.count("$") % 2 == 0:
        problems.append("dollar")
    return problems or None


def check_json_roundtrip(text):
    if CTRL_RE.search(text):
        return None
    try:
        got = loads_latex_aware(json.dumps({"q": text}))["q"]
    except Exception as exc:  # noqa: BLE001
        return f"raises {type(exc).__name__}"
    return None if got == text else ("mismatch", got)


def check_json_raw(text):
    raw = text.replace('\\"', '\\\\"').replace('"', '\\"')
    doc = '{"q": "' + raw + '"}'
    try:
        got = loads_latex_aware(doc)
    except Exception as exc:  # noqa: BLE001
        return f"raises {type(exc).__name__}: {str(exc)[:60]}"
    q = got.get("q") if isinstance(got, dict) else None
    if not isinstance(q, str):
        return "no q"
    if CTRL_RE.search(q) and not CTRL_RE.search(
        text.replace("\n", "").replace("\t", "").replace("\r", "")
    ):
        # raw newlines / tabs in the input are content; anything else is damage
        new_ctrl = [c for c in CTRL_RE.findall(q) if c not in "\n\t\r"]
        if new_ctrl:
            return ("control", q)
        # a \n that was LaTeX (e.g. "\nabla") decoded to a newline?
        if (
            text.count("\n") < q.count("\n")
            or text.count("\t") < q.count("\t")
            or text.count("\r") < q.count("\r")
        ):
            return ("control_ws", q)
    return None


CHECKS = {
    "a_idempotent": lambda t, keep: check_idempotent(t),
    "b_throws": lambda t, keep: check_fix_throws(t),
    "d_keep": lambda t, keep: check_keep(t, keep),
    "e_audit": lambda t, keep: check_audit(t),
    "f_katex": lambda t, keep: check_katex(t),
    "g_to_plain": lambda t, keep: check_to_plain(t),
    "h_json_roundtrip": lambda t, keep: check_json_roundtrip(t),
    "h_json_raw": lambda t, keep: check_json_raw(t),
}


def safe(fn, text, keep):
    try:
        return fn(text, keep)
    except Exception as exc:  # noqa: BLE001
        return f"CHECK RAISED {type(exc).__name__}: {str(exc)[:100]}"


# ---------------------------------------------------------------------------
# Minimisation (ddmin) and classification
# ---------------------------------------------------------------------------


def ddmin(items, predicate, joiner, budget=1500):
    """Classic delta debugging over a list of items."""
    calls = 0

    def test(seq):
        nonlocal calls
        calls += 1
        try:
            return bool(predicate(joiner(seq)))
        except Exception:  # noqa: BLE001
            return False

    n = 2
    while len(items) >= 2 and calls < budget:
        chunk = max(1, len(items) // n)
        subsets = [items[i : i + chunk] for i in range(0, len(items), chunk)]
        reduced = False
        for i, sub in enumerate(subsets):
            comp = [x for j, s in enumerate(subsets) if j != i for x in s]
            if comp and test(comp):
                items = comp
                n = max(n - 1, 2)
                reduced = True
                break
        if not reduced:
            if n >= len(items):
                break
            n = min(len(items), n * 2)
    return items


def minimise(text, predicate, atoms=None):
    if atoms and len(atoms) > 1:
        atoms = ddmin(list(atoms), predicate, "".join)
        text = "".join(atoms)
    if len(text) > 4000:
        return text
    chars = ddmin(
        list(text), predicate, "".join, budget=3000 if len(text) < 300 else 800
    )
    return "".join(chars)


def classify(check, text, result):
    out = FIX(text) if check != "b_throws" else ""
    if check == "a_idempotent":
        f1, f2 = result
        if re.search(r"[\^_]\{", f2) and not re.search(r"[\^_]\{", f1):
            return "wrap_bare_scripts wraps x^10/a_12 AFTER _normalize_braces ran (braces added on 2nd pass)"
        if any(ch in f1 for ch in UNICODE_MATH) and not any(
            ch in f2 for ch in UNICODE_MATH
        ):
            return "wrapping ($…$ added by wrap_bare_latex_commands / wrap_bare_scripts / pure-math) happens AFTER unicode_math_to_latex (Unicode converted on 2nd pass)"
        if (
            "&" in text
            and ("&" in f1) != ("&" in f2)
            or "&amp;" in text
            or "&lt;" in text
        ):
            return "ftfy unescape_html applied once per pass (&amp;amp; -> &amp; -> &)"
        if f1.count("$") != f2.count("$"):
            return "second pass wraps/escapes $ differently (currency / span parity changes after first pass)"
        if "\\\\" in f1 and "\\\\" not in f2:
            return "collapse_double_backslashes acts on something created by the first pass"
        return "other"
    if check == "f_katex":
        fails, blamed = result
        seg, err = fails[0]
        m = re.search(r"Undefined control sequence: (\\\S+)", err)
        if "in text mode" in err or (
            "\\text{" in seg
            and (
                "got '_'" in err
                or "got '^'" in err
                or (
                    m
                    and m.group(1)
                    in {
                        "\\times",
                        "\\pi",
                        "\\cdot",
                        "\\rightarrow",
                        "\\alpha",
                        "\\theta",
                        "\\leq",
                        "\\infty",
                        "\\div",
                        "\\pm",
                        "\\ldots",
                        "\\sqrt",
                        "\\tfrac",
                        "\\circ",
                        "\\omega",
                        "\\mu",
                        "\\Delta",
                        "\\degree",
                    }
                )
            )
        ):
            return "unicode_math_to_latex converts inside \\text{...}: math commands / ^ _ in text mode"
        if "Expected group as argument" in err or ("Got function '$'" in err):
            return "wrap_bare_latex_commands wraps \\frac12 / \\sqrt2 / \\vec F without their argument -> $\\sqrt$2"
        if "Double superscript" in err or "Double subscript" in err:
            return "input already had x^10^2 (double script); _normalize_braces keeps it broken"
        if m:
            return f"undefined control sequence {m.group(1)} (not KaTeX; canonicalize wrapped or kept it)"
        if "got '&'" in err:
            return "& outside an environment (input error or \\text{a & b})"
        if "Expected '$'" in err or "Can't use function '$'" in err:
            return "$ inside \\text{} or unbalanced $ inside a span"
        if "only in display mode" in err:
            return "\\begin{align} in inline span"
        return "other: " + err[:80]
    if check == "e_audit":
        return "audit kinds after fix: " + ",".join(result)
    if check == "g_to_plain":
        return "to_plain residue: " + ",".join(result)
    if check == "h_json_raw":
        if isinstance(result, str) and result.startswith("raises"):
            if "\\ " in text or re.search(r"\\\d", text):
                return "escape_latex_for_json keeps backslash+space / backslash+digit, which is invalid JSON -> raises"
            return "raises: " + result
        return "control char produced: " + str(result[0])
    if check == "h_json_roundtrip":
        return str(result[0]) if isinstance(result, tuple) else result
    if check == "d_keep":
        return "lost tokens: " + ", ".join(result)
    if check == "b_throws":
        return result
    return "?"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


DEADLINE_S = 330


def main(n=20000, seed=2026):
    rng = random.Random(seed)
    fix("warm up π $x^2$ Ã©")  # ftfy / regex warm-up
    failures = defaultdict(list)  # check -> [(text, atoms, result)]
    slow = []
    kind_counter = Counter()
    t_start = time.time()
    for idx in range(n):
        atoms, seps, kinds, keep = gen_input(rng, idx)
        kind_counter.update(kinds)
        text = join(atoms, seps)
        # split atoms with separators for atom-level minimisation
        pieces = []
        for i, a in enumerate(atoms):
            pieces.append(a)
            if i < len(seps):
                pieces.append(seps[i])
        t0 = time.perf_counter()
        err = check_fix_throws(text)
        dt = time.perf_counter() - t0
        if err:
            failures["b_throws"].append((text, pieces, err))
            continue
        nbytes = len(text.encode("utf-8", "surrogatepass"))
        allowed = max(0.005, 0.050 * nbytes / 10000)
        if dt > allowed:
            slow.append((dt, nbytes, text[:120], kinds[:6]))
        for name, fn in CHECKS.items():
            if name == "b_throws":
                continue
            res = safe(fn, text, keep)
            if res:
                failures[name].append((text, pieces, res))
        if time.time() - t_start > DEADLINE_S / 2:
            print(f"  deadline: stopping generation at {idx}")
            n = idx
            break
        if idx and idx % 1000 == 0:
            print(
                f"  {idx}/{n} inputs, {time.time() - t_start:.0f}s, failures so far: "
                + ", ".join(f"{k}={len(v)}" for k, v in sorted(failures.items())),
                flush=True,
            )
    elapsed = time.time() - t_start
    print(f"Ran {n} inputs in {elapsed:.0f}s")

    # Minimise + classify a sample of each failure class.
    report = {
        "n": n,
        "seed": seed,
        "elapsed_s": elapsed,
        "atom_kinds": dict(kind_counter),
        "checks": {},
        "slow": [],
    }
    for name, items in sorted(failures.items()):
        print(f"\n== {name}: {len(items)} failing inputs ==", flush=True)
        fn = CHECKS[name]
        by_cause = defaultdict(list)
        sample = (
            items[:400]
            if name != "f_katex"
            else [it for it in items if it[2][1]][:300]
            + [it for it in items if not it[2][1]][:60]
        )
        rng2 = random.Random(1)
        rng2.shuffle(sample)
        seen_causes = Counter()
        for text, pieces, res in sample:
            # cheap pre-classification on the unminimised input to cap per-cause work
            try:
                pre = classify(name, text, res)
            except Exception:  # noqa: BLE001
                pre = "?"
            if seen_causes[pre] >= 3 or time.time() - t_start > DEADLINE_S:
                by_cause[pre].append({"input": text[:200], "minimised": False})
                continue
            seen_causes[pre] += 1

            def pred(t, _fn=fn, _name=name):
                r = safe(_fn, t, [])
                if not r or isinstance(r, str) and r.startswith("CHECK RAISED"):
                    return False
                if _name == "f_katex":
                    return r[1]  # only keep reductions that stay blamed on fix
                return True

            if name == "d_keep":
                # tokens must remain in the candidate for the predicate to make sense
                lost = res
                pred = lambda t, _lost=lost: bool(check_keep(t, _lost))  # noqa: E731
            try:
                mini = minimise(text, pred, pieces)
                mres = safe(fn, mini, res if name == "d_keep" else [])
                cause = classify(name, mini, mres)
            except Exception as exc:  # noqa: BLE001
                mini, mres, cause = text, res, f"minimise failed: {exc}"
            entry = {
                "input": mini,
                "fix": fix(mini) if name != "b_throws" else None,
                "result": _jsonable(mres),
                "minimised": True,
            }
            if name == "f_katex":
                entry["blamed_on_fix"] = (
                    bool(mres[1]) if isinstance(mres, tuple) else None
                )
            if name == "g_to_plain":
                entry["to_plain"] = to_plain(FIX(mini))
            by_cause[cause].append(entry)
        report["checks"][name] = {"count": len(items), "by_cause": {}}
        for cause, entries in sorted(by_cause.items(), key=lambda kv: -len(kv[1])):
            mins = [e for e in entries if e.get("minimised")]
            mins.sort(key=lambda e: len(e["input"]))
            report["checks"][name]["by_cause"][cause] = {
                "sampled": len(entries),
                "examples": mins[:4],
            }
            print(f"  [{len(entries):3d}] {cause}")
            for e in mins[:2]:
                print(f"        in : {e['input']!r}")
                if e.get("fix") is not None:
                    print(f"        fix: {e['fix']!r}")
    slow.sort(reverse=True)
    report["slow"] = [
        {"ms": round(dt * 1000, 1), "bytes": nb, "head": head, "kinds": kinds}
        for dt, nb, head, kinds in slow[:25]
    ]
    print(f"\n== slow inputs (> 50 ms per 10 kB, floor 5 ms): {len(slow)} ==")
    for dt, nb, head, kinds in slow[:10]:
        print(f"  {dt * 1000:7.1f} ms  {nb:6d} B  {kinds}  {head[:60]!r}")
    with open(os.path.join(HERE, "fuzz_results.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=_jsonable)
    print("\nwrote fuzz_results.json")


def _jsonable(x):
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, (list, tuple)):
        return [_jsonable(i) for i in x]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    return repr(x)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    main(n, seed)
