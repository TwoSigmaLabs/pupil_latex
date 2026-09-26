"""Build ``corpus/<function>.json`` from the curated cases below plus the
harvested cases in ``corpus/harvested/``.

    python tools/build_corpus.py            # write corpus files
    python tools/build_corpus.py --check    # only report

Curated cases carry explicit expectations. Harvested cases (converted from
the existing test suites of Backend, agents, script_editor, Fillers and
worksheet.ai) are admitted only when the Python implementation reproduces
their assertion; the rest are written to ``corpus/review/`` for a human.
A curated case whose expectation the Python implementation does not meet
stops the build: the implementation or the case is wrong, never both right.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

import pupiltree_latex as L  # noqa: E402

CORPUS = ROOT / "corpus"
HARVESTED = CORPUS / "harvested"
REVIEW = CORPUS / "review"

ALL = ["python", "dart", "js"]
PY = ["python"]

# ---------------------------------------------------------------------------
# Curated cases. (id, input, expected, tags, extra)
# ---------------------------------------------------------------------------

REPAIR = [
    (
        "formfeed-frac",
        "Area is \x0crac{1}{2}bh",
        "Area is \\frac{1}{2}bh",
        ["B1", "backend#1564"],
        {},
    ),
    ("backspace-beta", "\x08eta decay", "\\beta decay", ["B1"], {}),
    (
        "backspace-board-tag",
        "\x08oard: draw it",
        "\\board: draw it",
        ["B1", "backend#1651"],
        {},
    ),
    ("vt-vec", "force \x0bec{F}", "force \\vec{F}", ["B1", "script_editor#420"], {}),
    ("vt-not-command-dropped", "a\x0bb", "ab", ["B1"], {}),
    ("tab-times", "3 \times 10^8", "3 \\times 10^8", ["B1", "backend#1567"], {}),
    ("tab-text", "\text{H}_2O", "\\text{H}_2O", ["B1"], {}),
    ("tab-theta", "angle \theta", "angle \\theta", ["B1"], {}),
    ("tab-real-tab-kept", "col1\tcol2", "col1\tcol2", ["B7"], {}),
    ("lf-nabla", "\nabla f", "\\nabla f", ["B1"], {}),
    ("lf-neq", "a \neq b", "a \\neq b", ["B1"], {}),
    (
        "lf-nu-is-a-line-break",
        "u = -25 cm\nu = 5",
        "u = -25 cm\nu = 5",
        ["B7", "backend#1585"],
        {},
    ),
    ("lf-list-item-ne", "\ne) No enzyme", "\ne) No enzyme", ["B7"], {}),
    ("lf-real-newline-kept", "line one\nline two", "line one\nline two", ["B7"], {}),
    ("cr-rho", "density \rho", "density \\rho", ["B1"], {}),
    ("cr-right", "\\left( x \right)", "\\left( x \\right)", ["B1"], {}),
    (
        "other-c0-and-del-dropped",
        "a\x00b\x01c\x1fd\x7fe",
        "abcde",
        ["B1", "fillers#274"],
        {},
    ),
    (
        "mixed-real-content",
        "$\\frac{1}{2}$ and \x0crac{3}{4} and \times",
        "$\\frac{1}{2}$ and \\frac{3}{4} and \\times",
        ["B1"],
        {},
    ),
    (
        "hard-variant-keeps-tab",
        "3 \times 10^8",
        "3 \times 10^8",
        ["B7", "backend#1595"],
        {"variant": "hard"},
    ),
    (
        "hard-variant-restores-ff",
        "\x0crac{1}{2}",
        "\\frac{1}{2}",
        ["B1", "backend#1595"],
        {"variant": "hard"},
    ),
    (
        "clean-text-untouched",
        "The quick brown fox.",
        "The quick brown fox.",
        ["B7"],
        {},
    ),
    (
        "script-label-tab-restored",
        "\teacher: Hello class",
        "\\teacher: Hello class",
        ["B1", "real-data-D0"],
        {},
    ),
    (
        "script-label-cr-restored",
        "\read: page 4",
        "\\read: page 4",
        ["B1", "real-data-D0"],
        {},
    ),
    (
        "script-label-only-with-colon",
        "\teacher said hi",
        "\teacher said hi",
        ["B7"],
        {},
    ),
    (
        "newline-inside-span-is-a-command",
        "$x \nightarrow y$",
        "$x \\rightarrow y$",
        ["B1", "real-data-D11"],
        {},
    ),
    (
        "newline-in-prose-kept-even-if-command-fits",
        "x \nightarrow y",
        "x \nightarrow y",
        ["B7"],
        {},
    ),
    ("in-math-repair-needs-closed-span", "$\no", "$\no", ["B7", "review-F11"], {}),
    (
        "in-math-repair-needs-three-letters",
        "$a \nu b$",
        "$a \nu b$",
        ["B7", "review-F11"],
        {},
    ),
]

NORMALIZE = [
    ("paren-inline", "\\(\\theta\\)", "$\\theta$", ["B4"], {}),
    ("bracket-display", "\\[x^2\\]", "$$x^2$$", ["B4"], {}),
    ("inline-newline-collapsed", "\\(a\n   b\\)", "$a b$", ["B4"], {}),
    ("line-break-not-delimiter", "x \\\\[2pt] y", "x \\\\[2pt] y", ["B4", "B7"], {}),
    (
        "orphan-open-stripped",
        "stray \\( here",
        "stray  here",
        ["B4", "script_editor#420"],
        {},
    ),
    ("orphan-close-stripped", "end \\] here", "end  here", ["B4"], {}),
    (
        "currency-before-math",
        "$5000 and $\\frac14$",
        "\\$5000 and $\\frac14$",
        ["B3"],
        {},
    ),
    ("currency-range", "$5-$10", "\\$5-\\$10", ["B3"], {}),
    ("currency-no-closer", "costs $5.", "costs \\$5.", ["B3"], {}),
    ("math-starting-with-digit", "$2x + 3$", "$2x + 3$", ["B3", "B7"], {}),
    (
        "currency-already-escaped",
        "Cost \\$60 and $x^2$",
        "Cost \\$60 and $x^2$",
        ["B3", "B7", "fillers#273"],
        {},
    ),
    (
        "prose-newline-decoded",
        "A is true.\\nB) The electric field",
        "A is true.\nB) The electric field",
        ["B1"],
        {},
    ),
    ("prose-crlf-decoded", "one\\r\\ntwo", "one\ntwo", ["B1"], {}),
    ("prose-tab-decoded", "a\\tTab", "a\tTab", ["B1"], {}),
    (
        "theta-in-prose-kept",
        "angle \\theta here",
        "angle \\theta here",
        ["B5", "B7"],
        {},
    ),
    ("neq-in-prose-kept", "a \\neq b", "a \\neq b", ["B5", "B7"], {}),
    (
        "nu-in-prose-is-a-line-break",
        "frequency \\nu",
        "frequency \nu",
        ["B7", "review-F21"],
        {
            "note": "Backend production evidence: a line break followed by 'u = 5 cm'; same vocabulary as the JSON transport"
        },
    ),
    ("text-in-prose-kept", "\\text{x}", "\\text{x}", ["B5", "B7"], {}),
    ("escape-inside-math-kept", "$a\\nb$", "$a\\nb$", ["B7"], {}),
    (
        "step-order-theta-in-parens",
        "\\(\\theta\\) and \\(\\times 2\\)",
        "$\\theta$ and $\\times 2$",
        ["B5", "script_editor#420", "tutor#383"],
        {},
    ),
    ("mojibake-pi", "Ï€ r^2", "π r^2", ["B6"], {}),
    ("mojibake-times", "3 Ã— 4", "3 × 4", ["B6"], {}),
    ("mojibake-root", "âˆš2", "√2", ["B6"], {}),
    ("control-char-repaired", "\x0crac{1}{2}", "\\frac{1}{2}", ["B1"], {}),
    (
        "no-wrapping-ever",
        "√2 and π and \\frac{1}{2} and H_{2}O",
        "√2 and π and \\frac{1}{2} and H_{2}O",
        ["B7"],
        {},
    ),
    (
        "url-and-marker-untouched",
        "https://a/b_c.png {{IMAGE:59_1}}",
        "https://a/b_c.png {{IMAGE:59_1}}",
        ["B7"],
        {},
    ),
    (
        "full-pipeline",
        "\\(\\theta\\) costs $5000 and $\\frac14$ then \\nNext",
        "$\\theta$ costs \\$5000 and $\\frac14$ then \nNext",
        ["B3", "B4", "B5"],
        {},
    ),
    (
        "script-labels-not-escapes",
        "\\teacher: Hello \\type: mcq \\read: page 4 \\tool: ruler",
        "\\teacher: Hello \\type: mcq \\read: page 4 \\tool: ruler",
        ["B1", "real-data-D0"],
        {},
    ),
    (
        "broken-sqrt-span-untouched",
        "Root: $\\sqrt$2",
        "Root: $\\sqrt$2",
        ["B3", "B7", "real-data-D2"],
        {},
    ),
    (
        "html-entities-decoded",
        "a &amp; b &lt; c &#960;",
        "a & b < c π",
        ["B6", "real-data-D8"],
        {},
    ),
    ("cp1252-psi", "The Ïˆ(x) wave", "The ψ(x) wave", ["B6", "real-data-D6"], {}),
    ("crlf-kept", "a\r\nb", "a\r\nb", ["B7", "real-data-D9"], {}),
    ("nbsp-becomes-space", "5\xa0km", "5 km", ["B7", "review-F8"], {}),
    ("dash-superscript-kept", "10—¹ range", "10—¹ range", ["B7", "review-F9"], {}),
    ("latin1-xi-fixed-once", "Î\x9e ", "Ξ ", ["B6", "review-F10"], {}),
    ("double-encoded-entity", "&amp;amp;", "&", ["B6", "review-F18"], {}),
    (
        "nu-in-prose-is-a-line-break",
        "Given\\nu = 5 cm",
        "Given\nu = 5 cm",
        ["B7", "review-F21"],
        {},
    ),
    (
        "closer-followed-by-opener",
        "$1$$\\gamma$",
        "$1$$\\gamma$",
        ["B3", "B7", "review-F5"],
        {},
    ),
    (
        "capitalised-name-after-newline-decoded",
        "Host: Priya\\nGuest: Vikram",
        "Host: Priya\nGuest: Vikram",
        ["B1", "final-R3"],
        {},
    ),
    (
        "lowercase-label-kept",
        "\\teacher: Hello\\nguest: hi",
        "\\teacher: Hello\\nguest: hi",
        ["B7", "final-R3"],
        {},
    ),
]

CANONICALIZE = [
    (
        "formfeed-frac-wrapped",
        "Area is \x0crac{1}{2}bh",
        "Area is $\\frac{1}{2}$bh",
        ["B1"],
        {},
    ),
    (
        "currency-odd-count",
        "Cost $60 and $x^2$",
        "Cost \\$60 and $x^2$",
        ["B3", "backend#1582"],
        {},
    ),
    (
        "currency-after-math",
        "$\\frac{1}{2}$ costs $5.",
        "$\\frac{1}{2}$ costs \\$5.",
        ["B3"],
        {},
    ),
    ("currency-balanced-untouched", "$10^{-34}$", "$10^{-34}$", ["B3", "B7"], {}),
    (
        "bare-sqrt-wrapped",
        "the ratio is 1/\\sqrt{2}",
        "the ratio is 1/$\\sqrt{2}$",
        ["B4"],
        {},
    ),
    (
        "bare-frac-and-currency",
        "The price is $50 and the ratio is 1/\\sqrt{2}",
        "The price is \\$50 and the ratio is 1/$\\sqrt{2}$",
        ["B3", "B4"],
        {},
    ),
    (
        "scripts-wrapped-identifiers-kept",
        "H_{2}O and MCQ_SINGLE and q_001_easy and 3^{\\circ}C",
        "$H_{2}O$ and MCQ_SINGLE and q_001_easy and $3^{\\circ}C$",
        ["B4", "B7", "backend#454"],
        {},
    ),
    ("root-takes-radicand", "√2", "$\\sqrt{2}$", ["B6", "backend#1654"], {}),
    ("root-without-radicand-stays", "√", "√", ["B6", "B7", "backend#1654"], {}),
    ("root-ambiguous-stays", "√2gh", "√2gh", ["B6", "B7", "backend#1654"], {}),
    ("unicode-times-and-script", "3 × 10^8", "3 $\\times$ $10^8$", ["B6"], {}),
    ("greek-run", "ħω", "$\\hbar\\omega$", ["B6"], {}),
    ("pi-alone", "π", "$\\pi$", ["B6"], {}),
    ("mojibake-table", "Ï€ is Ã— fun", "$\\pi$ is $\\times$ fun", ["B6"], {}),
    (
        "image-marker-kept",
        "{{IMAGE:59_1}} then \\frac{a}{b}",
        "{{IMAGE:59_1}} then $\\frac{a}{b}$",
        ["B7"],
        {},
    ),
    (
        "whole-url-kept",
        "https://s/x/uuid_page0.png",
        "https://s/x/uuid_page0.png",
        ["B7"],
        {},
    ),
    (
        "embedded-url-kept",
        "see https://a/b_c.png here",
        "see https://a/b_c.png here",
        ["B7"],
        {},
    ),
    (
        "broken-spans-merged",
        "\\left[ $\\frac12$ \\right] $\\frac{q^2}{a^2}$",
        "$\\left[ \\frac12 \\right] \\frac{q^2}{a^2}$",
        ["B4", "backend#afeac37e"],
        {},
    ),
    (
        "pure-math-short",
        "0.33 \\times 10^{11} \\text{ NC}^{-1}",
        "$0.33 \\times 10^{11} \\text{ NC}^{-1}$",
        ["B4"],
        {},
    ),
    ("multi-digit-script-braced", "$x^10$", "$x^{10}$", ["B4"], {}),
    (
        "double-backslash-collapsed",
        "\\\\frac{1}{2}",
        "$\\frac{1}{2}$",
        ["B1", "B4"],
        {},
    ),
    ("left-brace-fixed", "$\\left{a\\right}$", "$\\left\\{a\\right\\}$", ["B4"], {}),
    ("paren-delimiters", "\\(x\\) and \\[y\\]", "$x$ and $$y$$", ["B4"], {}),
    (
        "line-break-in-display-kept",
        "$$a \\\\[2pt] b$$",
        "$$a \\\\[2pt] b$$",
        ["B4", "B7"],
        {},
    ),
    (
        "plain-prose-untouched",
        "Coulomb's law describes the force.",
        "Coulomb's law describes the force.",
        ["B7"],
        {},
    ),
    ("e-n-mc2", "E_n = mc^2", "$E_n$ = $mc^2$", ["B4"], {}),
    ("chem-unicode-not-wrapped", "H₂O", "H₂O", ["B6", "B7"], {}),
    ("homoglyph-micro", "$5 µm$", "$5 \\mu m$", ["B6"], {}),
    (
        "wrapped-span-converted-in-one-pass",
        "\\text{H₂O} and x^10 in $x^10$",
        "$\\text{H₂O}$ and $x^{10}$ in $x^{10}$",
        ["B5", "B6"],
        {
            "note": "unicode inside \\text{} is kept; the wrapped span's script is braced in the same pass"
        },
    ),
    (
        "bare-sqrt-without-argument-left-alone",
        "use \\sqrt here",
        "use \\sqrt here",
        ["B7"],
        {},
    ),
    (
        "bare-frac-with-arguments-wrapped",
        "use \\frac{1}{2} here",
        "use $\\frac{1}{2}$ here",
        ["B4"],
        {},
    ),
    ("bare-sum-alone-wrapped", "the \\sum symbol", "the $\\sum$ symbol", ["B4"], {}),
    (
        "wrapped-script-braced-in-one-pass",
        "x^10 in $x^10$ and H₂O",
        "$x^{10}$ in $x^{10}$ and H₂O",
        ["B5"],
        {},
    ),
    (
        "log-subscript-not-bare-script",
        "\\log_{10} 100",
        "$\\log_{10}$ 100",
        ["B4", "real-data-D1"],
        {},
    ),
    (
        "escaped-dollar-then-script",
        "  \\$x^2$ ",
        "  \\$x^2$ ",
        ["B3", "B7", "real-data-D2"],
        {},
    ),
    (
        "enum-suffix-is-identifier",
        "no_capture and ai_recreate",
        "no_capture and ai_recreate",
        ["B7", "real-data-D4"],
        {},
    ),
    (
        "short-suffix-is-math",
        "E_n and x_0 and H_2O",
        "$E_n$ and $x_0$ and $H_2O$",
        ["B4"],
        {},
    ),
    ("prose-ellipsis-kept", "I think… now", "I think… now", ["B7", "real-data-D3"], {}),
    (
        "script-line-not-pure-math",
        "\\teacher: hi \\read: p4",
        "\\teacher: hi \\read: p4",
        ["B7", "real-data-D0"],
        {},
    ),
    (
        "image-marker-inside-url",
        "see gs://{{IMAGE:q2_fig}} -",
        "see gs://{{IMAGE:q2_fig}} -",
        ["B7", "fuzz"],
        {},
    ),
    (
        "image-marker-inside-math",
        "${{IMAGE:x_1}} and x^2$",
        "${{IMAGE:x_1}} and x^2$",
        ["B7", "fuzz"],
        {},
    ),
    (
        "many-image-markers",
        "{{IMAGE:a}}{{IMAGE:b}}{{IMAGE:c}}{{IMAGE:d}}{{IMAGE:e}}{{IMAGE:f}}{{IMAGE:g}}{{IMAGE:h}}{{IMAGE:i}}{{IMAGE:j}}{{IMAGE:k}} x_1",
        "{{IMAGE:a}}{{IMAGE:b}}{{IMAGE:c}}{{IMAGE:d}}{{IMAGE:e}}{{IMAGE:f}}{{IMAGE:g}}{{IMAGE:h}}{{IMAGE:i}}{{IMAGE:j}}{{IMAGE:k}} $x_1$",
        ["B7", "fuzz"],
        {},
    ),
    (
        "url-does-not-swallow-math",
        "see https://a.b/c $x^2$",
        "see https://a.b/c $x^2$",
        ["B7", "fuzz"],
        {},
    ),
    (
        "hindi-prose-with-command",
        "यह \\alpha कण है",
        "यह \\alpha कण है",
        ["B6", "fuzz"],
        {},
    ),
    (
        "hindi-prose-with-frac",
        "गति \\frac{1}{2} है",
        "गति $\\frac{1}{2}$ है",
        ["B4", "fuzz"],
        {},
    ),
    (
        "hindi-prose-with-unicode",
        "कोण θ = 30° है",
        "कोण $\\theta$ = 30° है",
        ["B6", "fuzz"],
        {},
    ),
    ("line-break-then-word-not-math", "\\\\cs", "\\\\cs", ["B7", "fuzz"], {}),
    (
        "class-name-in-prose",
        "Students of 10_A scored well",
        "Students of 10_A scored well",
        ["B7", "fuzz"],
        {},
    ),
    (
        "stream-class-name",
        "class 12_PCM section",
        "class 12_PCM section",
        ["B7", "fuzz"],
        {},
    ),
    (
        "unicode-inside-text-group-kept",
        "$\\text{H₂O} and \\text{5 × 3}$",
        "$\\text{H₂O} and \\text{5 × 3}$",
        ["B7", "review-F1"],
        {},
    ),
    (
        "script-run-merged-in-math",
        "$10⁻³$ and $C₆H₁₂O₆$",
        "$10^{-3}$ and $C_{6}H_{12}O_{6}$",
        ["B6", "review-F2"],
        {},
    ),
    ("display-vec", "$$x⃗$$", "$$\\vec{x}$$", ["B6", "review-F3"], {}),
    (
        "odd-run-of-backslashes-is-a-line-break",
        "$$a \\\\\\frac{1}{2}$$",
        "$$a \\\\\\frac{1}{2}$$",
        ["B7", "review-F4"],
        {},
    ),
    (
        "even-run-collapsed-any-command",
        "\\\\cdots and \\\\ce{H2O}",
        "\\cdots and \\ce{H2O}",
        ["B1", "review-F14"],
        {},
    ),
    ("unpaired-dollar-not-rewrapped", "$ H₂", "$ H₂", ["B7", "review-F6"], {}),
    ("frac-alone-not-wrapped", "\\frac", "\\frac", ["B7", "review-F12"], {}),
    (
        "identifier-inside-math-kept",
        "$q_001_easy_2026$",
        "$q_001_easy_2026$",
        ["B7", "review-F13"],
        {},
    ),
    (
        "log-with-subscript-wrapped",
        "see \\log_{10} x",
        "see $\\log_{10}$ x",
        ["B4"],
        {},
    ),
    ("cbrt-not-structural", "\\cbrt{8}", "\\cbrt{8}", ["B7", "review-S8"], {}),
    (
        "matrix-row-not-collapsed",
        "$\\begin{vmatrix}a&b\\\\c&d\\end{vmatrix}$",
        "$\\begin{vmatrix}a&b\\\\c&d\\end{vmatrix}$",
        ["B7", "final-R1"],
        {},
    ),
    (
        "aligned-row-starting-with-command",
        "$$\\begin{aligned}x&=1\\\\alpha&=2\\end{aligned}$$",
        "$$\\begin{aligned}x&=1\\\\alpha&=2\\end{aligned}$$",
        ["B7", "final-R1"],
        {},
    ),
    (
        "single-letter-command-not-collapsed",
        "a \\\\b c",
        "a \\\\b c",
        ["B7", "final-R1"],
        {},
    ),
    (
        "double-escaped-outside-environment-still-collapsed",
        "$\\\\frac{1}{2}$",
        "$\\frac{1}{2}$",
        ["B1"],
        {},
    ),
    (
        "frac-with-one-argument-left-alone",
        "see \\tbinom{x} here",
        "see \\tbinom{x} here",
        ["B7", "final-R6"],
        {},
    ),
]

SEGMENT = [
    (
        "mixed",
        "Cost \\$60 and $x^2$ then $5-$10 and $$a\nb$$ and \\(y\\) \\[z\\]",
        [
            {
                "kind": "text",
                "display": False,
                "value": "Cost $60 and ",
                "raw": "Cost \\$60 and ",
            },
            {"kind": "math", "display": False, "value": "x^2", "raw": "$x^2$"},
            {
                "kind": "text",
                "display": False,
                "value": " then $5-$10 and ",
                "raw": " then $5-$10 and ",
            },
            {"kind": "math", "display": True, "value": "a\nb", "raw": "$$a\nb$$"},
            {"kind": "text", "display": False, "value": " and ", "raw": " and "},
            {"kind": "math", "display": False, "value": "y", "raw": "\\(y\\)"},
            {"kind": "text", "display": False, "value": " ", "raw": " "},
            {"kind": "math", "display": True, "value": "z", "raw": "\\[z\\]"},
        ],
        ["B3", "B4"],
        {},
    ),
    (
        "currency-then-math",
        "$60 and $x^2$ end",
        [
            {"kind": "text", "display": False, "value": "$60 and ", "raw": "$60 and "},
            {"kind": "math", "display": False, "value": "x^2", "raw": "$x^2$"},
            {"kind": "text", "display": False, "value": " end", "raw": " end"},
        ],
        ["B3"],
        {},
    ),
    (
        "escaped-backslash-then-math",
        "\\\\$x$",
        [
            {"kind": "text", "display": False, "value": "\\\\", "raw": "\\\\"},
            {"kind": "math", "display": False, "value": "x", "raw": "$x$"},
        ],
        ["B3"],
        {},
    ),
    (
        "braces-protect-dollar",
        "$\\text{a$b}$",
        [
            {
                "kind": "math",
                "display": False,
                "value": "\\text{a$b}",
                "raw": "$\\text{a$b}$",
            },
        ],
        ["B4"],
        {},
    ),
    (
        "inline-does-not-cross-lines",
        "$a\nb$",
        [
            {"kind": "text", "display": False, "value": "$a\nb$", "raw": "$a\nb$"},
        ],
        ["B4"],
        {},
    ),
    (
        "unterminated-is-text",
        "open $x here",
        [
            {
                "kind": "text",
                "display": False,
                "value": "open $x here",
                "raw": "open $x here",
            },
        ],
        ["B4"],
        {},
    ),
    (
        "empty-display-is-text",
        "$$$$",
        [
            {"kind": "text", "display": False, "value": "$$$$", "raw": "$$$$"},
        ],
        ["B4"],
        {},
    ),
    (
        "escaped-dollar-inside-math",
        "$\\$5 + x$",
        [
            {
                "kind": "math",
                "display": False,
                "value": "\\$5 + x",
                "raw": "$\\$5 + x$",
            },
        ],
        ["B3"],
        {},
    ),
    (
        "paren-content-trimmed",
        "\\( x \\)",
        [
            {"kind": "math", "display": False, "value": "x", "raw": "\\( x \\)"},
        ],
        ["B4"],
        {},
    ),
    (
        "plain",
        "no math here",
        [
            {
                "kind": "text",
                "display": False,
                "value": "no math here",
                "raw": "no math here",
            },
        ],
        [],
        {},
    ),
]

TO_PLAIN = [
    ("frac-and-script", "$\\frac{1}{2}mv^{2}$", "(1)/(2)mv²", ["B8"], {}),
    ("vec-text-style", "$\\vec{F} = m\\vec{a}$", "F = ma", ["B8"], {}),
    (
        "vec-pdf-style",
        "$\\vec{F} = m\\vec{a}$",
        "F⃗ = ma⃗",
        ["B8", "backend#1745"],
        {"style": "pdf"},
    ),
    ("vec-multi-pdf", "$\\vec{AB}$", "vec(AB)", ["B8"], {"style": "pdf"}),
    ("sqrt-group", "$\\sqrt{2m}$", "√(2m)", ["B8", "backend#1599"], {}),
    ("sqrt-index", "$\\sqrt[3]{8}$", "³√8", ["B8"], {}),
    ("negative-exponent", "$10^{-15}$", "10⁻¹⁵", ["B8"], {}),
    ("chem-text", "$\\text{H}_2\\text{O}$", "H₂O", ["B8"], {}),
    ("left-right-dropped", "$\\left( x \\right)$", "( x )", ["B8", "backend#1368"], {}),
    ("boxed-kept", "$\\boxed{5}$", "5", ["B8", "backend#1745"], {}),
    ("matrix", "$\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}$", "[a b; c d]", ["B8"], {}),
    ("currency-literal", "costs \\$5 and $x$", "costs $5 and x", ["B3", "B8"], {}),
    (
        "nested-frac",
        "$\\frac{\\frac{1}{2}}{3}$",
        "((1)/(2))/(3)",
        ["B8", "backend#1599"],
        {},
    ),
    ("greek-and-ops", "$\\alpha \\times \\beta \\leq \\pi$", "α × β ≤ π", ["B8"], {}),
    ("no-math-untouched", "plain sentence", "plain sentence", ["B7"], {}),
    ("literal-newline-escape", "one\\nTwo", "one\nTwo", ["B8"], {}),
    (
        "tts-basic",
        "**Speed** is $\\frac{d}{t}$ and $x^2 + \\alpha$",
        "Speed is d over t and x squared + alpha",
        ["B8"],
        {"style": "tts"},
    ),
    (
        "tts-sqrt-and-ops",
        "$\\sqrt{x} \\times \\pi \\leq \\infty$",
        "square root of x times pi less than or equal to infinity",
        ["B8"],
        {"style": "tts"},
    ),
    ("thin-space-braces-dropped", "1{,}000", "1,000", ["B8", "real-data-D10"], {}),
    ("neg-not-peeled", "$\\neg p$", "¬ p", ["B8", "review-F15"], {}),
    ("leqslant", "$a \\leqslant b$", "a ≤ b", ["B8", "review-F15"], {}),
    ("unknown-katex-name-kept", "$\\intercal$", "⊺", ["B8", "review-F15"], {}),
    (
        "deep-nesting-no-crash",
        "{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{x}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}",
        "x",
        ["B8", "review-F17"],
        {},
    ),
    (
        "tts-power-twenty",
        "$x^{20}$",
        "x to the power 20",
        ["B8", "review-F16"],
        {"style": "tts"},
    ),
    (
        "tts-nested-frac",
        "$\\frac{\\frac{1}{2}}{3}$",
        "(1 over 2) over 3",
        ["B8", "review-F16"],
        {"style": "tts"},
    ),
    (
        "tts-pm-word-boundary",
        "$\\pmatrix$",
        "pmatrix",
        ["B8", "review-F16"],
        {"style": "tts"},
    ),
]

AUDIT = [
    ("control-char", "Area \x0crac{1}{2}", ["control_char"], ["B1"], {}),
    ("tab-times", "3 \times 10^8", ["control_char"], ["B1"], {}),
    ("legacy-delims", "\\(x\\) and \\[y\\]", ["legacy_delimiter"] * 4, ["B4"], {}),
    ("line-break-not-legacy", "$$a \\\\[2pt] b$$", [], ["B7"], {}),
    ("unbalanced", "costs $5", ["unbalanced_dollar"], ["B3"], {}),
    ("escaped-dollar-balanced", "costs \\$5", [], ["B3", "B7"], {}),
    (
        "sqrt-missing-arg",
        "$\\sqrt$2",
        ["command_missing_argument"],
        ["B7", "backend#1654"],
        {},
    ),
    ("frac-one-arg", "$\\frac{1}$", ["frac_missing_args"], ["B4"], {}),
    ("frac-ok", "$\\frac12$", [], ["B7"], {}),
    ("script-no-braces", "$x^10$", ["script_missing_braces"], ["B4"], {}),
    ("script-ok", "$x^2y$ and $x_1$", [], ["B7"], {}),
    ("mojibake", "Ï€ r", ["mojibake"], ["B6"], {}),
    ("double-escaped", "\\\\frac{1}{2}", ["double_escaped_command"], ["B1"], {}),
    ("json-embedded-not-double-escaped", '{"q": "\\\\frac{1}{2}"}', [], ["B7"], {}),
    ("unsupported-mathscr", "$\\mathscr{L}$", ["unsupported_command"], ["B4"], {}),
    (
        "unknown-command-in-math",
        "$\\notacommand{x}$",
        ["unsupported_command"],
        ["B4"],
        {},
    ),
    ("mhchem-allowed", "$\\ce{H2O}$", [], ["B7"], {}),
    (
        "bare-unicode",
        "3 × 10^8 and π",
        ["bare_unicode_math", "bare_unicode_math"],
        ["B6"],
        {},
    ),
    ("unicode-inside-math-ok", "$3 × 10^8$", [], ["B7"], {}),
    ("unicode-chemistry", "H₂O", ["unicode_chemistry"], ["B6"], {}),
    (
        "bare-left-brace",
        "$\\left{x\\right}$",
        ["bare_left_brace", "bare_left_brace"],
        ["B4"],
        {},
    ),
    ("clean", "The formula is $x^{2} + y^{2} = r^{2}$.", [], ["B7"], {}),
    (
        "newline-inside-span-flagged",
        "$x \nightarrow y$",
        ["control_char"],
        ["B1", "real-data-D11"],
        {},
    ),
    ("script-label-clean", "\\teacher: Hello class", [], ["B7"], {}),
    (
        "textmu-unsupported",
        "$\\textmu m$",
        ["unsupported_command"],
        ["B4", "review-S8"],
        {},
    ),
    ("display-unicode-not-bare", "$$α$$", [], ["B7", "review-F3"], {}),
    (
        "matrix-row-not-double-escaped",
        "$\\begin{bmatrix}x&y\\\\cos x&d\\end{bmatrix}$",
        [],
        ["B7", "final-R1"],
        {},
    ),
]

JSON_TRANSPORT = [
    (
        "frac-in-string",
        '{"q": "$\\frac{1}{2}$"}',
        {"q": "$\\frac{1}{2}$"},
        ["B1", "backend#1651"],
        {},
    ),
    ("newline-outside-math", '{"q": "A.\\nB."}', {"q": "A.\nB."}, ["B1", "B7"], {}),
    ("times-outside-math", '{"q": "3 \\times 10"}', {"q": "3 \\times 10"}, ["B1"], {}),
    ("theta-inside-math", '{"q": "$\\theta$"}', {"q": "$\\theta$"}, ["B1"], {}),
    ("beta-always-latex", '{"q": "\\beta decay"}', {"q": "\\beta decay"}, ["B1"], {}),
    (
        "nu-after-currency-is-a-line-break",
        '{"q": "$5 and \\nu = 2"}',
        {"q": "$5 and \nu = 2"},
        ["B1", "B3", "B7"],
        {
            "note": "no closing $, so the value is prose; a bare \\nu in prose breaks the "
            "contract while a line break before 'u = 2' is real content (Backend #1585)"
        },
    ),
    (
        "real-newline-after-currency",
        '{"q": "$5 and\\nnext"}',
        {"q": "$5 and\nnext"},
        ["B1", "B3"],
        {},
    ),
    ("unicode-escape-kept", '{"q": "\\u03c0"}', {"q": "π"}, ["B7"], {}),
    (
        "quote-and-slash-kept",
        '{"q": "say \\"hi\\" and a\\/b"}',
        {"q": 'say "hi" and a/b'},
        ["B7"],
        {},
    ),
    (
        "array-of-options",
        '["\\frac{1}{2}", "\\text{x}", "\\nabla"]',
        ["\\frac{1}{2}", "\\text{x}", "\\nabla"],
        ["B1"],
        {},
    ),
    ("invalid-json-errors", '{"q": ', None, ["B1"], {"expected_error": True}),
    (
        "script-labels-survive-transport",
        '{"s": "\\teacher: hi\\nnext \\type: mcq \\read: p4"}',
        {"s": "\\teacher: hi\nnext \\type: mcq \\read: p4"},
        ["B1", "real-data-D0"],
        {},
    ),
    (
        "backslash-space-and-digit",
        '{"q": "5\\ \\text{m} a\\1"}',
        {"q": "5\\ \\text{m} a\\1"},
        ["B1", "review-F7"],
        {},
    ),
    (
        "capitalised-name-after-newline",
        '{"s": "Host: Priya\\nGuest: Vikram"}',
        {"s": "Host: Priya\nGuest: Vikram"},
        ["B1", "final-R3"],
        {},
    ),
]

MUST_NOT_CHANGE = [
    (
        "identifier-caps",
        "MCQ_SINGLE",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "assessment-ui#b8834fb"],
    ),
    ("slug", "q_001_easy_2026", ["canonicalize", "fix", "normalize", "repair"], ["B7"]),
    (
        "hex-id",
        "ahs_69e74f5e84fd",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "backend#454"],
    ),
    (
        "audio-url",
        "https://storage.googleapis.com/x/ahs_69e74f5e84fd_vocab_20260425.wav",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7", "backend#454"],
    ),
    (
        "image-marker",
        "{{IMAGE:169_optA}}",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7"],
    ),
    (
        "question-number",
        "Q17 is next",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7", "tutor#982d982"],
    ),
    (
        "plain-prose",
        "The quick brown fox jumps over the lazy dog.",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7"],
    ),
    (
        "plain-chem-text",
        "H2O is water",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7"],
    ),
    (
        "balanced-math",
        "The formula is $x^{2} + y^{2} = r^{2}$.",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7"],
    ),
    (
        "escaped-currency",
        "Cost \\$60 and \\$15 then $x^2$ end",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B3", "B7", "script_editor#420"],
    ),
    (
        "real-whitespace",
        "col1\tcol2\nrow2",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7"],
    ),
    (
        "accented-name",
        "Ångström and café",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B6", "B7"],
    ),
    (
        "snake-case-field",
        "user_id and student_id",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7"],
    ),
    (
        "markdown-bold",
        "**Important:** read this",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7"],
    ),
    (
        "canonical-chemistry",
        "$\\text{H}_{2}\\text{SO}_{4}$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7"],
    ),
    (
        "script-lines",
        "\\teacher: Explain the water cycle.\n\\type: mcq\n\\read: page 4\n\\tool: ruler",
        ["repair", "normalize", "canonicalize", "fix"],
        ["B7", "real-data-D0"],
    ),
    (
        "prose-ellipsis",
        "I used to think… now I think",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "real-data-D3"],
    ),
    (
        "enum-values",
        "status no_capture then ai_recreate",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "real-data-D4"],
    ),
    (
        "crlf-text",
        "line one\r\nline two",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7", "real-data-D9"],
    ),
    (
        "image-marker-in-url",
        "gs://{{IMAGE:q2_fig}} -",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7", "fuzz"],
    ),
    (
        "class-names",
        "Students of 10_A and 12_PCM",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "fuzz"],
    ),
    (
        "hindi-prose",
        "यह एक वाक्य है",
        ["canonicalize", "fix", "normalize", "repair", "to_plain"],
        ["B7", "fuzz"],
    ),
    ("nbsp-prose", "Chapter\xa05 begins", ["repair"], ["B7", "review-F8"]),
    (
        "identifier-in-math",
        "$q_001_easy_2026$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "review-F13"],
    ),
    (
        "text-group-unicode",
        "$\\text{H₂O} and \\text{25°C}$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "review-F1"],
    ),
    (
        "line-break-before-command",
        "$$a \\\\\\frac{1}{2}$$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "review-F4"],
    ),
    (
        "matrix-rows",
        "$\\begin{bmatrix}x&y\\\\cos x&d\\end{bmatrix}$ and $$\\begin{aligned}x&=1\\\\alpha&=2\\end{aligned}$$",
        ["canonicalize", "fix", "normalize", "repair", "audit"],
        ["B7", "final-R1"],
    ),
]


# ---------------------------------------------------------------------------
# Audit round 2 (2026-09-26). Every case is tagged `audit2-…` so the Dart and
# JS ports can find what changed.
# ---------------------------------------------------------------------------

NORMALIZE += [
    # Currency mojibake (cp1252 readings of €, £, ₹, ¥): the table path must
    # restore them before anything can wrap the `¬` of `â‚¬` as `\neg`.
    ("audit2-mojibake-euro", "â‚¬5", "€5", ["B6", "audit2-currency-mojibake"], {}),
    (
        "audit2-mojibake-currencies",
        "Price Â£5, â‚¹500, Â¥3, 25Â°C",
        "Price £5, ₹500, ¥3, 25°C",
        ["B6", "audit2-currency-mojibake"],
        {},
    ),
    # A genuine repeated letter is never collapsed; only a pair produced by
    # the context rules is.
    ("audit2-double-pi-kept", "ππ", "ππ", ["B6", "B7", "audit2-double-greek"], {}),
    ("audit2-double-omega-kept", "ωω", "ωω", ["B6", "B7", "audit2-double-greek"], {}),
    ("audit2-double-root-kept", "√√2", "√√2", ["B6", "B7", "audit2-double-greek"], {}),
    (
        "audit2-mojibake-double-pi",
        "Ï€Ï€",
        "ππ",
        ["B6", "audit2-double-greek"],
        {
            "note": "UTF-8 ππ read as cp1252; the harvested script_editor case expecting one π is in review"
        },
    ),
]

CANONICALIZE += [
    (
        "audit2-times-chain",
        "The product 3×4×5=60 is easy.",
        "The product $3\\times4\\times5$=60 is easy.",
        ["B6", "audit2-cluster"],
        {},
    ),
    (
        "audit2-greek-subscript",
        "Given ε₀ and μ₀, find c.",
        "Given $\\epsilon_{0}$ and $\\mu_{0}$, find c.",
        ["B6", "audit2-cluster"],
        {},
    ),
    (
        "audit2-units-next-to-greek-stay-out",
        "µs and kΩ and J·s",
        "$\\mu$s and k$\\Omega$ and J$\\cdot$s",
        ["B6", "B7", "audit2-cluster"],
        {},
    ),
    (
        "audit2-devanagari-digit-after-span",
        "यदि x≤५ है",
        "यदि $x\\leq$ ५ है",
        ["B6", "audit2-cluster"],
        {"note": "a digit the cluster cannot take gets a space before it"},
    ),
    (
        "audit2-escaped-dollar-after-line-break",
        "\\\\$\\frac{1}{2}$",
        "\\\\$\\frac{1}{2}$",
        ["B3", "B5", "audit2-line-break-dollar"],
        {},
    ),
    (
        "audit2-line-break-then-frac",
        "\\\\\\frac{1}{2}",
        "\\\\$\\frac{1}{2}$",
        ["B4", "audit2-line-break-dollar"],
        {},
    ),
    (
        "audit2-lone-dollar-then-span",
        "$ $\\text{H}_{2}$",
        "$ $\\text{H}_{2}$",
        ["B4", "B5", "audit2-lone-dollar"],
        {},
    ),
    (
        "audit2-padded-span-trimmed",
        "Solve $ x^2 + 1 = 0 $ now",
        "Solve $x^2 + 1 = 0$ now",
        ["B4", "audit2-padded-span"],
        {},
    ),
    (
        "audit2-padded-span-with-command",
        "Let $ \\theta = 30° $ here",
        "Let $\\theta = 30^{\\circ}$ here",
        ["B4", "audit2-padded-span"],
        {},
    ),
    (
        "audit2-superscripts-are-not-a-word",
        "3 \\times 10²³",
        "$3 \\times 10^{23}$",
        ["B6", "audit2-script-not-word"],
        {},
    ),
    (
        "audit2-structural-command-before-digit",
        "\\sqrt{2}3",
        "$\\sqrt{2}3$",
        ["B4", "audit2-cluster"],
        {},
    ),
]

TO_PLAIN += [
    (
        "audit2-tts-chem-text",
        "$\\text{H}_{2}\\text{O}$",
        "H 2 O",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-unit-power",
        "$\\text{cm}^{3}$",
        "cm cubed",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-ion",
        "$\\text{Fe}^{3+}$",
        "Fe 3 plus",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-sulfate",
        "$\\text{SO}_{4}^{2-}$",
        "SO 4 2 minus",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-mathrm-chem",
        "$\\mathrm{H_2O}$",
        "H 2 O",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    ("audit2-tts-ce", "$\\ce{H2O}$", "H 2 O", ["B8", "audit2-tts"], {"style": "tts"}),
    (
        "audit2-tts-ce-reaction",
        "$\\ce{2H2 + O2 -> 2H2O}$",
        "2H 2 + O 2 gives 2H 2 O",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-nested-sqrt",
        "$\\sqrt{x^{2}+y^{2}}$",
        "square root of (x squared+y squared)",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-left-right",
        "$\\left( \\frac{a}{b} \\right)^{2}$",
        "((a over b)) squared",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-percent",
        "$5\\%$",
        "5 percent",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-matrix",
        "$$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$$",
        "matrix with rows 1, 2; 3, 4",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-left-brace",
        "$\\left\\{ x \\right\\}$",
        "x",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-cases",
        "$\\begin{cases} x, & x > 0 \\\\ -x, & x \\le 0 \\end{cases}$",
        "x, x > 0; -x, x less than or equal to 0",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-degrees",
        "$45^{\\circ}$",
        "45 degrees",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-cube-root",
        "$\\sqrt[3]{8}$",
        "cube root of 8",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-command-after-digit",
        "$\\mu_{0} = 4\\pi \\times 10^{-7}$",
        "mu sub 0 = 4 pi times 10 to the power -7",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
    (
        "audit2-tts-bare-frac-in-prose",
        "Kinetic energy is \\frac{1}{2}mv^2 here",
        "Kinetic energy is (1 over 2)mv^2 here",
        ["B8", "audit2-tts"],
        {"style": "tts"},
    ),
]

MUST_NOT_CHANGE += [
    (
        "audit2-currency-with-spaces",
        "I paid $ 5 and got $ 3 back",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B3", "B7", "audit2-padded-span"],
    ),
    (
        "audit2-padded-currency-equation",
        "Cost $ 5 = 5 $ only",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B3", "B7", "audit2-padded-span"],
    ),
    (
        "audit2-prose-digits",
        "2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "audit2-cluster"],
    ),
    (
        "audit2-line-break-then-span",
        "\\\\$\\frac{1}{2}$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B3", "B5", "audit2-line-break-dollar"],
    ),
    (
        "audit2-double-greek-normalize",
        "ππ and ωω",
        ["normalize", "repair"],
        ["B6", "B7", "audit2-double-greek"],
    ),
    (
        "audit2-radical-coefficient-kept",
        "2$\\sqrt{3}$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B7", "audit2-cluster"],
    ),
]


# ---------------------------------------------------------------------------
# Audit round 3 (2026-09-26). Tags `audit3-greek-word` (a word mixing Greek
# letters with Latin letters or digits is one span, spec §0.1) and
# `audit3-brace-close` (canonicalize step 10b closes the last group of a
# span that was never closed, spec §3).
# ---------------------------------------------------------------------------

CANONICALIZE += [
    (
        "audit3-greek-word-circle",
        "Area = 2πr and πr²",
        "Area = $2\\pi r$ and $\\pi r^{2}$",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-wave",
        "v = fλ and E = hν",
        "v = $f\\lambda$ and E = $h\\nu$",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-uncertainty",
        "Δx·Δp ≥ ħ/2",
        "$\\Delta x\\cdot\\Delta p$ $\\geq$ $\\hbar$/2",
        ["B6", "audit3-greek-word"],
        {"note": "fix merges the three spans; `/2` stays outside"},
    ),
    (
        "audit3-greek-word-phase",
        "y = A sin(ωt + φ)",
        "y = A sin($\\omega t$ + $\\phi$)",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-resistance",
        "R = ρL/A",
        "R = $\\rho L$/A",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-two-latin-letters",
        "Surface 2πrh",
        "Surface $2\\pi rh$",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-gibbs",
        "ΔG = ΔH − TΔS",
        "$\\Delta G$ = $\\Delta H$ - $T\\Delta S$",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-decimal-and-rupee",
        "2.5λ and ₹2π",
        "$2.5\\lambda$ and ₹$2\\pi$",
        ["B6", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-units-kept",
        "5 µs, 10 kΩ, 3 MΩ, 2 µm, 5 µg, 4 mΩ",
        "5 $\\mu$s, 10 k$\\Omega$, 3 M$\\Omega$, 2 $\\mu$m, 5 $\\mu$g, 4 m$\\Omega$",
        ["B6", "B7", "audit3-greek-word"],
        {"note": "a unit word keeps the audit2 shape"},
    ),
    (
        "audit3-greek-word-units-kept-glued",
        "Ω·m and J·s and 10Ω and 5μs and 10kΩ",
        "$\\Omega\\cdot$m and J$\\cdot$s and 10$\\Omega$ and 5$\\mu$s and 10k$\\Omega$",
        ["B6", "B7", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-mu-unit-wins",
        "F = μN and μ₀",
        "F = $\\mu$N and $\\mu_{0}$",
        ["B6", "B7", "audit3-greek-word"],
        {"note": "μN reads as micronewton: the unit rule wins over friction"},
    ),
    (
        "audit3-greek-word-long-latin-word",
        "αβγtest and Thetaα and λmax",
        "$\\alpha\\beta\\gamma$test and Theta$\\alpha$ and $\\lambda$max",
        ["B6", "B7", "audit3-greek-word"],
        {"note": "3+ Latin letters in a row: not one term"},
    ),
    (
        "audit3-greek-word-function-name",
        "sin θ and sinθ",
        "sin $\\theta$ and sin$\\theta$",
        ["B6", "B7", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-greek-word-greek-prose",
        "λόγος and Ελλάδα",
        "$\\lambda$ό$\\gamma$ο$\\varsigma$ and Ε$\\lambda\\lambda$ά$\\delta\\alpha$",
        ["B6", "B7", "audit3-greek-word"],
        {
            "note": "pins that the Greek-word rule does not apply to Greek-language prose (accented letters and Latin-looking capitals are not math letters); the per-letter wrapping itself predates audit3"
        },
    ),
    (
        "audit3-greek-word-touching-identifier-or-script",
        "q_π and २π",
        "q_$\\pi$ and २$\\pi$",
        ["B6", "B7", "audit3-greek-word"],
        {},
    ),
    (
        "audit3-brace-close-frac",
        "$\\frac{1}{2$",
        "$\\frac{1}{2}$",
        ["B4", "audit3-brace-close"],
        {},
    ),
    (
        "audit3-brace-close-power",
        "$x^{2$",
        "$x^{2}$",
        ["B4", "audit3-brace-close"],
        {},
    ),
    (
        "audit3-brace-close-sqrt",
        "$\\sqrt{x+1$",
        "$\\sqrt{x+1}$",
        ["B4", "audit3-brace-close"],
        {},
    ),
    (
        "audit3-brace-close-two-spans",
        "Take $\\frac{1}{2$ of $x^{2$ now",
        "Take $\\frac{1}{2}$ of $x^{2}$ now",
        ["B4", "audit3-brace-close"],
        {},
    ),
    (
        "audit3-brace-close-after-currency",
        "Price $5 and $\\frac{1}{2$",
        "Price \\$5 and $\\frac{1}{2}$",
        ["B3", "B4", "audit3-brace-close"],
        {},
    ),
    # `audit3-script-group`: a symbol inside the braces of a bare script or
    # command argument is converted with the whole group in one span, never
    # wrapped on its own inside it (`$e^{i$\pi$}$` was nested).
    (
        "audit3-script-group-euler",
        "Let e^{iπ} = -1 hold",
        "Let $e^{i\\pi}$ = -1 hold",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-letter-after-symbol",
        "e^{iπt}",
        "$e^{i\\pi t}$",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-subscripts",
        "x_{α} and y_{β}",
        "$x_{\\alpha}$ and $y_{\\beta}$",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-two-symbols",
        "a_{αβ} and e^{i×π}",
        "$a_{\\alpha \\beta}$ and $e^{i\\times \\pi}$",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-frac-argument",
        "\\frac{π}{2}",
        "$\\frac{\\pi}{2}$",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-sqrt-argument",
        "\\sqrt{2π} and \\sqrt[3]{2π}",
        "$\\sqrt{2\\pi}$ and $\\sqrt[3]{2\\pi}$",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-accent-argument",
        "\\vec{α}",
        "$\\vec{\\alpha}$",
        ["B5", "B6", "audit3-script-group"],
        {},
    ),
    (
        "audit3-script-group-text-verbatim",
        "\\text{π}",
        "$\\text{π}$",
        ["B5", "B6", "audit3-script-group"],
        {"note": "a \\text group is copied verbatim (step 12)"},
    ),
    (
        "audit3-script-group-prose-braces",
        "the set {α, β}",
        "the set {$\\alpha$, $\\beta$}",
        ["B6", "B7", "audit3-script-group"],
        {"note": "a brace group attached to nothing is prose"},
    ),
    (
        "audit3-script-group-not-wrapped-falls-back",
        "\\frac{π} and x^{π",
        "\\frac{$\\pi$} and x^{$\\pi$",
        ["B6", "B7", "audit3-script-group"],
        {
            "note": "a one-argument \\frac (R6) and an unclosed group stay prose; their symbols get spans of their own, as before"
        },
    ),
]

MUST_NOT_CHANGE += [
    (
        "audit3-brace-close-empty-second-argument",
        "$\\frac{1}{$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-empty-first-argument",
        "$\\frac{$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-empty-script",
        "$x^{$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-command-without-argument",
        "$\\frac{1}{\\sqrt$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-would-leave-frac-short",
        "$\\frac{\\frac{1}{2$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-left-without-right",
        "$\\left( x^{2$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-more-closers",
        "$a}{b$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-escaped-brace",
        "$\\{x$",
        ["canonicalize", "fix", "normalize", "repair"],
        ["B4", "B7", "audit3-brace-close"],
    ),
    (
        "audit3-brace-close-prose-and-currency",
        "cost $5 and {5 more $",
        ["canonicalize", "repair"],
        ["B3", "B7", "audit3-brace-close"],
    ),
]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


from pupiltree_latex import corpus as C  # noqa: E402
from curated_fix import FIX  # noqa: E402

_QUOTED_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")


def _unescape_literal(s: str) -> str:
    """A quoted fragment from a harvested property string is literal text
    (the harvester wrote real backslashes, not Python escapes)."""
    return s


def convert_property(function: str, case: dict) -> dict | None:
    """Turn a free-text harvested ``property`` into corpus predicate fields.

    Returns the converted case, or None when the property is about a
    renderer, a regex or anything the corpus cannot express."""
    prop = case.get("property") or ""
    if case.get("expected") is not None or prop == "idempotent":
        return case
    low = prop.lower()
    if any(
        w in low
        for w in (
            "regex",
            "widget",
            "rendered",
            "span",
            "class=",
            "element",
            "re-encode",
        )
    ):
        return None
    out = {k: v for k, v in case.items() if k != "property"}
    out["expected"] = None
    out["property_source"] = prop
    quoted = [_unescape_literal(q) for q in _QUOTED_RE.findall(prop)]
    if not quoted:
        return None
    if function == "audit":
        if low.startswith("kinds contain") or low.startswith(
            "exactly one finding of kind"
        ):
            out["kinds_include"] = quoted
        elif low.startswith("kinds do not contain"):
            out["kinds_exclude"] = quoted
        else:
            return None
        return out
    if function == "json_transport":
        m = re.match(r"parsed\['(\w+)'\] contains '", prop)
        if not m:
            return None
        out["json_contains"] = {m.group(1): quoted[-1]}
        return out
    # String functions: split the sentence at the first negation.
    contains, not_contains = [], []
    neg_at = min(
        [
            i
            for i in (
                low.find(" not "),
                low.find("none of"),
                low.find("does not"),
                low.find(" no "),
            )
            if i >= 0
        ]
        or [len(prop)]
    )
    for m in _QUOTED_RE.finditer(prop):
        literal = _unescape_literal(m.group(1))
        (not_contains if m.start() > neg_at else contains).append(literal)
    if not contains and not not_contains:
        return None
    if contains:
        out["contains"] = contains
    if not_contains:
        out["not_contains"] = not_contains
    return out


def run(function: str, case: dict):
    try:
        return C.run(function, case)
    except C.ParseError:
        return {"__error__": True}


def passes(function: str, case: dict) -> bool:
    ok, _ = C.check(function, case)
    return ok


def unchanged(fn: str, inp: str) -> bool:
    return C.unchanged(fn, inp)[0]


def curated(function: str, rows) -> list[dict]:
    out = []
    for row in rows:
        cid, inp, expected, tags, extra = row
        case = {
            "id": f"curated-{cid}",
            "input": inp,
            "expected": expected,
            "tags": tags,
            **extra,
        }
        out.append(case)
    return out


def harvested(function: str) -> list[dict]:
    path = HARVESTED / f"{function}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    for n, case in enumerate(cases):
        case.setdefault("id", f"harvested-{function}-{n:04d}")
    return cases


def build(check_only: bool) -> int:
    REVIEW.mkdir(exist_ok=True)
    failures = 0
    summary = []
    groups = {
        "repair": REPAIR,
        "normalize": NORMALIZE,
        "canonicalize": CANONICALIZE,
        "fix": FIX,
        "segment": SEGMENT,
        "to_plain": TO_PLAIN,
        "audit": AUDIT,
        "json_transport": JSON_TRANSPORT,
    }
    for function, rows in groups.items():
        cases = curated(function, rows)
        for case in cases:
            if not passes(function, case):
                failures += 1
                print(
                    f"CURATED FAIL {function}/{case['id']}: got {run(function, case)!r}"
                )
        admitted, rejected = [], []
        seen = {c["input"] for c in cases}
        for case in harvested(function):
            case = dict(case)
            if (
                function == "segment"
                and "renderMath" in str(case.get("via", ""))
                and "katex" in str(case.get("property", "")).lower()
            ):
                case.pop("property", None)
                case["must_render"] = True
                case["engine"] = "katex"
                if "$" not in case["input"] and "\(" not in case["input"]:
                    case["input"] = "$" + case["input"] + "$"
            elif case.get("property") is not None and case.get("expected") is None:
                converted = convert_property(function, case)
                if converted is None:
                    case["python_got"] = "<property not expressible>"
                    rejected.append(case)
                    continue
                case = converted
            if case.get("impl") and "python" not in case["impl"]:
                admitted.append(case)
                continue
            if passes(function, case):
                if (
                    case["input"] in seen
                    and not case.get("variant")
                    and not case.get("style")
                ):
                    continue
                seen.add(case["input"])
                admitted.append(case)
            else:
                case["python_got"] = run(function, case)
                rejected.append(case)
        all_cases = cases + admitted
        summary.append((function, len(cases), len(admitted), len(rejected)))
        if not check_only:
            (CORPUS / f"{function}.json").write_text(
                json.dumps(
                    {"function": function, "version": L.VERSION, "cases": all_cases},
                    ensure_ascii=False,
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
            (REVIEW / f"{function}_mismatches.json").write_text(
                json.dumps(
                    {"function": function, "cases": rejected},
                    ensure_ascii=False,
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
    # must_not_change
    mnc = []
    for cid, inp, functions, tags in MUST_NOT_CHANGE:
        case = {
            "id": f"curated-{cid}",
            "input": inp,
            "functions": functions,
            "tags": tags,
        }
        for fn in functions:
            if not unchanged(fn, inp):
                failures += 1
                print(f"CURATED FAIL must_not_change/{cid} via {fn}")
        mnc.append(case)
    admitted_mnc, rejected_mnc = [], []
    for case in harvested("must_not_change"):
        ok = all(unchanged(fn, case["input"]) for fn in case["functions"])
        (admitted_mnc if ok else rejected_mnc).append(case)
    summary.append(("must_not_change", len(mnc), len(admitted_mnc), len(rejected_mnc)))
    if not check_only:
        (CORPUS / "must_not_change.json").write_text(
            json.dumps(
                {
                    "function": "must_not_change",
                    "version": L.VERSION,
                    "cases": mnc + admitted_mnc,
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        (REVIEW / "must_not_change_mismatches.json").write_text(
            json.dumps(
                {"function": "must_not_change", "cases": rejected_mnc},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"{'function':16} {'curated':>8} {'harvested':>10} {'review':>7}")
    for name, c, a, r in summary:
        print(f"{name:16} {c:8d} {a:10d} {r:7d}")
    if failures:
        print(f"\n{failures} curated case(s) FAILED against the Python implementation.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(build(check_only="--check" in sys.argv))
