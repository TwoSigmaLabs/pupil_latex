"""Final re-verification of every reproducer cited in REPORT.md against the current code."""

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
    repair,
)
from katex_client import KaTeX

K = KaTeX()


def row(label, text, fn=fix):
    out = fn(text)
    again = fn(out)
    segs = (
        [s["value"] for s in segment(out) if s["kind"] == "math"]
        if isinstance(out, str)
        else []
    )
    bad = [(s, K.render(s)[1][:50]) for s in segs if not K.render(s)[0]]
    print(
        f"{label:<34} in={text!r}\n{'':34} out={out!r}{'' if again == out else '   NOT IDEMPOTENT -> ' + repr(again)}{'   KATEX FAIL ' + repr(bad) if bad else ''}{'   audit=' + str(audit_kinds(out)) if isinstance(out, str) and audit_kinds(out) else ''}"
    )


row("display vec parity", "$$x⃗$$")
row("display vec parity 2", "$$a⃗ + b⃗$$")
row("unicode super run in math", "$10⁻³$")
row("unicode sub run in math", "$C₆H₁₂O₆$")
row("unicode super run prose", "3 × 10⁻³")
row("text{} unicode sub", "$\\text{H₂O}$")
row("text{} unicode times", "$\\text{5 × 3}$")
row("text{} degree", "$\\text{25°C}$")
row("text{} pi", "$\\text{π r}$")
row("dollar in text", "$\\text{costs $5}$")
row("adjacent spans $1$γ", "$1$γ")
row("orphan then chem", "$ H₂")
row("Hindi prose", "यह \\alpha कण है")
row("Hebrew prose", "שלום \\alpha")
row("row break then frac", "$$a \\\\\\frac{1}{2}$$")
row("row break then end", "$\\begin{aligned} a &= b \\\\\\end{aligned}$")
row(
    "11 markers one in math",
    " ".join(f"{{{{IMAGE:i{i}}}}}" for i in range(10)) + " $a {{IMAGE:last}}$",
)
row("url swallows marker", "http://host/{{IMAGE:x_1}}\ta")
row("nbsp", "5 km")
row("em dash superscript", "10—¹ range")
row("entities twice", "&amp;amp;")
row("mojibake C1 space", "Î\x9e ", normalize)
row("$\\no normalize", "$\\no", normalize)
row("\\x0crac", "\x0crac")
row("double esc cdots", "\\\\cdots")
row("double esc ce", "\\\\ce{H2O}")
row("lone surrogate", "\ud83d x")
row("q id in math", "$q_001_easy_2026$")
row("literal \\n in math", "$a\\nb$")
row("tab an", "Draw\tan angle", repair)
row("newline eq", "Values:\neq 5", repair)
row("literal newline before nu", "Given\\nu = 5 cm")
row("sqrt no arg", "use \\sqrt here")
row("sqrt2", "\\sqrt2 is irrational")
row("frac12", "half is \\frac12")
row("percent in math", "$50%$")
row("mathscr", "$\\mathscr{L}$")
row("cbrt", "$\\cbrt{8}$")
print()
print(
    "to_plain:",
    {
        x: to_plain(x)
        for x in [
            "$\\neg p$",
            "$\\top$",
            "$\\inf$",
            "$a \\pmod{n}$",
            "$a \\leqslant b$",
            "$\\newline$",
            "$\\intercal$",
            "{{IMAGE:169_optA}}",
            "$1{,}000$",
        ]
    },
)
print(
    "tts     :",
    {
        x: to_plain(x, "tts")
        for x in ["$x^{20}$", "$\\frac{\\frac{1}{2}}{3}$", "$\\pmatrix$"]
    },
)
try:
    to_plain("{" * 1000 + "x" + "}" * 1000)
    print("to_plain 1000 nested braces: ok")
except RecursionError:
    print("to_plain 1000 nested braces: RecursionError")
for doc in [
    '{"q": "5\\\\ \\\\text{m}"}'.replace("\\\\", "\\"),
    '{"q": "a\\\\1"}'.replace("\\\\", "\\"),
    '{"q": "\\\\begin{pmatrix}1&2\\\\\\\\3&4\\\\end{pmatrix}"}'.replace("\\\\", "\\"),
    '{"q": "\\\\udeaf"}'.replace("\\\\", "\\"),
]:
    try:
        print("json", repr(doc), "->", repr(loads_latex_aware(doc)))
    except Exception as e:
        print("json", repr(doc), "-> RAISES", type(e).__name__, str(e)[:50])
import time

for name, s in {
    "greek 10k": ("α β γ π ω " * 2000)[:10000],
    "newline words 10k": ("hello\nworld " * 900)[:10000],
    "open-brace dollars 10k": ("$a{" * 3400)[:10000],
    "vec arrows 10k": ("a⃗ " * 3400)[:10000],
}.items():
    for fname, f in [
        ("fix", fix),
        ("audit", audit_kinds),
        ("segment", segment),
        ("repair", repair),
    ]:
        t0 = time.perf_counter()
        f(s)
        ms = (time.perf_counter() - t0) * 1000
        if ms > 50:
            print(f"SLOW {fname}({name}): {ms:.0f} ms")
