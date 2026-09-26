"""Targeted attacks on pupiltree_latex (review deliverable, spec task 3).

    set PYTHONPATH=..\..\python
    python attacks.py

One function per attack. Each prints its inputs, the outputs of the relevant
functions and a verdict (PASS / FAIL / NOTE). A FAIL is a wrong output as
judged by the spec, by KaTeX (through katex_server.js) or by plain
content-preservation; a NOTE is a spec-conformant result that still breaks
the "every LaTeX issue is fixed" promise. The verdicts are collected into
attacks_results.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python")
)

from pupiltree_latex import (  # noqa: E402
    audit_kinds,
    canonicalize,
    escape_latex_for_json,
    fix,
    loads_latex_aware,
    normalize,
    repair,
    segment,
    to_plain,
)
from katex_client import KaTeX  # noqa: E402

KATEX = KaTeX()
RESULTS: list[dict] = []
CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def show(label, value):
    print(f"    {label:<14} {value!r}")


def renders(text):
    """(all_ok, [(segment, error)]) for every math segment of ``text``."""
    fails = []
    for s in segment(text):
        if s["kind"] == "math":
            ok, err = KATEX.render(s["value"], s["display"])
            if not ok:
                fails.append((s["value"], err[:90]))
    return not fails, fails


def verdict(name, status, why, **data):
    print(f"  => {status}: {why}")
    RESULTS.append({"attack": name, "status": status, "why": why, **data})


def attack(fn):
    def wrapper():
        print(f"\n### {fn.__name__}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            verdict(fn.__name__, "FAIL", f"attack raised {type(exc).__name__}: {exc}")

    wrapper.__name__ = fn.__name__
    ATTACKS.append(wrapper)
    return wrapper


ATTACKS: list = []


def check_one(name, text, expect=None, must_render=True, must_keep=(), extra=""):
    """Common body: fix, idempotency, KaTeX, kept tokens, optional expected."""
    out = fix(text)
    out2 = fix(out)
    show("input", text)
    show("fix", out)
    problems = []
    if out2 != out:
        show("fix(fix)", out2)
        problems.append("not idempotent")
    ok, fails = renders(out)
    if must_render and not ok:
        show("katex", fails[0])
        problems.append(f"KaTeX: {fails[0][1][:60]}")
    for tok in must_keep:
        if tok not in out:
            problems.append(f"lost {tok!r}")
    if expect is not None and out != expect:
        show("expected", expect)
        problems.append("differs from expected")
    if problems:
        verdict(
            name,
            "FAIL",
            "; ".join(problems) + (f" ({extra})" if extra else ""),
            input=text,
            output=out,
        )
    else:
        verdict(name, "PASS", extra or "ok", input=text, output=out)
    return out


# ---------------------------------------------------------------------------
# Currency and dollar handling
# ---------------------------------------------------------------------------


@attack
def currency_pandoc_rule():
    for text in [
        "$5$",
        "$5 $",
        "It costs $5$ per item",
        "$5 and $10",
        "$5-$10",
        "US$ 5",
        "$5,000.50 total",
        "\\$5 already",
        "Cost $5. Then $x^2$.",
    ]:
        out = fix(text)
        segs = [(s["kind"], s["value"]) for s in segment(out)]
        show("input", text)
        show("fix", out)
        show("segments", segs)
    # `$5$` is math by the pandoc rule; `$5 $` is currency. Both idempotent?
    ok = (
        fix("$5$") == "$5$"
        and fix("$5 $") == "\\$5 $"
        and fix(fix("$5 $")) == fix("$5 $")
    )
    verdict(
        "currency_pandoc_rule",
        "PASS" if ok else "FAIL",
        "pandoc closer rule as specified; note `$5$` stays math (a price written `$5$` renders as the number 5)",
    )


@attack
def display_dollars_inside_inline():
    check_one("display_dollars_inside_inline", "$a $$ b$", must_render=False)
    check_one("display_dollars_inside_inline_2", "$x$$y$", must_render=True)
    out = fix("$x$$y$")
    segs = segment(out)
    show("segments", [(s["kind"], s["value"]) for s in segs])


@attack
def escaped_dollar_inside_text():
    check_one("escaped_dollar_inside_text", r"$\text{cost \$5}$", must_keep=[r"\$5"])
    check_one(
        "dollar_inside_text",
        r"$\text{cost $5}$",
        must_render=True,
        extra="a bare $ inside \\text{} is a KaTeX error; fix should escape it",
    )


@attack
def double_backslash_before_dollar():
    for text in [r"a\\$x$", r"row \\ $x$", r"$a \\ b$ and \\$y$"]:
        out = fix(text)
        show("input", text)
        show("fix", out)
        show("segments", [(s["kind"], s["value"]) for s in segment(out)])
        show("audit", audit_kinds(out))
    ok, fails = renders(fix(r"a\\$x$"))
    verdict(
        "double_backslash_before_dollar",
        "PASS" if ok else "FAIL",
        "segment treats \\\\$ as a math opener; normalize/canonicalize treat it as escaped (parity mismatch between the tokenizer and the $-counters)"
        if ok
        else str(fails),
    )


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


@attack
def nested_frac_depth_20():
    body = "\\frac{" * 20 + "1" + "}{2}" * 20
    for text in ["$" + body + "$", body]:
        check_one("nested_frac_depth_20", text)
    plain = to_plain("$" + body + "$")
    show("to_plain", plain[:80] + "...")
    t0 = time.perf_counter()
    try:
        to_plain("{" * 1000 + "x" + "}" * 1000)
        deep = "ok"
    except RecursionError:
        deep = "RecursionError"
    dt = time.perf_counter() - t0
    verdict(
        "nested_braces_1000_to_plain",
        "FAIL" if deep != "ok" else "PASS",
        f"to_plain on 1000 nested braces: {deep} ({dt * 1000:.0f} ms)",
    )


@attack
def unbalanced_braces_inside_math():
    for text in ["$\\frac{1}{2$", "$x^{2$ and $y}$", "$a{b$ c", "${$", "$}$"]:
        out = fix(text)
        show("input", text)
        show("fix", out)
        show("segments", [(s["kind"], s["value"]) for s in segment(out)])
        show("audit", audit_kinds(out))
    verdict(
        "unbalanced_braces_inside_math",
        "NOTE",
        "unbalanced braces are left as they are (segment refuses the span, so it shows as text); audit has no kind for unbalanced braces",
    )


@attack
def left_brace_split_across_spans():
    text = r"$\left{ x$ and $y \right}$"
    out = check_one("left_brace_split_across_spans", text, must_render=False)
    show("audit", audit_kinds(out))
    if "bare_left_brace" in audit_kinds(out):
        verdict(
            "left_brace_split_across_spans",
            "FAIL",
            "\\left{ / \\right} survive fix (audit still flags bare_left_brace)",
        )


@attack
def scripts():
    check_one(
        "double_superscript",
        "$x^10^2$",
        must_render=False,
        extra="input was already invalid LaTeX (double superscript)",
    )
    check_one("chained_subscript_prose", "a_b_c", expect="a_b_c")
    check_one(
        "class_name_in_prose",
        "Students of 10_A scored well",
        must_keep=["10_A"],
        extra="class name in prose",
    )
    check_one("snake_case_short_head", "Set my_var to 3", must_keep=["my_var"])
    check_one("x_train", "Use x_train and y_pred", must_keep=["x_train", "y_pred"])
    check_one("x_0_wrap", "at x_0 the value", expect="at $x_0$ the value")
    check_one("mc2", "E = mc^2 is famous", expect="E = $mc^2$ is famous")


@attack
def hindi_prose_with_math():
    check_one("hindi_prose_with_math", "यह \\alpha कण है", must_keep=["यह", "कण", "है"])
    check_one("hindi_prose_with_frac", "गति \\frac{1}{2} है", must_keep=["गति", "है"])
    check_one("hindi_prose_with_unicode", "कोण θ = 30° है", must_keep=["कोण", "है"])
    out = fix("यह \\alpha कण है")
    if out.startswith("$") and out.endswith("$"):
        verdict(
            "hindi_prose_with_math",
            "FAIL",
            "whole Hindi sentence wrapped in $…$ (no 4-letter ASCII word found); KaTeX renders it as spaceless math text",
            output=out,
        )


@attack
def emoji_and_rtl():
    for text in [
        "Well done 👍🏽 $x^2$",
        "🧪 H₂O",
        "مرحبا $x$",
        "שלום \\alpha",
        "a\u200bb $x$",
        "\ufeff$x$",
        "\ud83d lone surrogate",
        "👨‍👩‍👧 family",
    ]:
        try:
            out = fix(text)
            show("input", text)
            show("fix", out)
        except Exception as exc:  # noqa: BLE001
            verdict(
                "emoji_and_rtl", "FAIL", f"{text!r} raised {type(exc).__name__}: {exc}"
            )
            return
    lone = fix("\ud83d lone surrogate")
    verdict(
        "emoji_and_rtl",
        "NOTE" if "\ufffd" in lone else "PASS",
        "lone surrogate becomes U+FFFD (ftfy fix_surrogates) which audit then reports as mojibake forever"
        if "\ufffd" in lone
        else "ok",
    )


@attack
def literal_newline_inside_display_math():
    text = "$$\\nx = 1 \\\\\\ny = 2$$"
    out = check_one("literal_newline_inside_display_math", text, must_render=False)
    show("segments", [(s["kind"], s["value"]) for s in segment(out)])
    check_one(
        "literal_newline_in_prose", "Line one\\nLine two", expect="Line one\nLine two"
    )
    check_one(
        "literal_newline_before_nu",
        "Given\\nu = 5 cm",
        extra="\\nu in prose is kept as the command (spec §2.6), so a real line break before 'u = 5 cm' is lost",
    )


@attack
def tab_before_heta():
    check_one("tab_before_heta_prose", "angle \theta", expect="angle $\\theta$")
    check_one("tab_before_heta_math", "$\theta$", expect="$\\theta$")
    got = loads_latex_aware('{"q": "$\\theta$"}')["q"]
    show("json \\theta", got)
    verdict(
        "tab_before_heta",
        "PASS" if got == "$\\theta$" else "FAIL",
        "JSON path" if got == "$\\theta$" else f"json gave {got!r}",
    )
    # A TSV-ish table: TAB followed by the word 'an' or 'to' is a real word
    for text in ["Draw\tan angle", "from\tto", "value\ttimes 2", "sum\ttotal"]:
        out = repair(text)
        show("repair", (text, out))
    r = repair("Draw\tan angle")
    if "\\tan" in r:
        verdict(
            "tab_before_word",
            "NOTE",
            "TAB + 'an angle' becomes \\tan angle: a tab before the English word 'an' is read as the command",
            output=r,
        )


@attack
def nu_ne_ni_not_in_every_context():
    rows = []
    for cmd in [
        "\\nu",
        "\\ne",
        "\\ni",
        "\\not",
        "\\neg",
        "\\newline",
        "\\nabla",
        "\\neq",
    ]:
        prose = f"Given {cmd} = 5"
        math = f"$a {cmd} b$"
        js = loads_latex_aware('{"q": "' + prose + '"}')["q"]
        jm = loads_latex_aware('{"q": "' + math + '"}')["q"]
        rows.append((cmd, normalize(prose), fix(prose), fix(math), js, jm))
        print(
            f"    {cmd:<9} normalize={normalize(prose)!r:<28} fix={fix(prose)!r:<30} math={fix(math)!r:<22} json_prose={js!r:<26} json_math={jm!r}"
        )
    bad = [r for r in rows if CTRL_RE.search(r[3]) or CTRL_RE.search(r[5])]
    verdict(
        "nu_ne_ni_not_in_every_context",
        "FAIL" if bad else "PASS",
        "control char inside math after fix / json"
        if bad
        else "prose keeps the ambiguous four as commands (normalize) but the JSON path decodes them as line breaks — the two paths disagree on the same bytes",
    )


@attack
def boxed_ce_pu_mathscr():
    check_one(
        "boxed", "Answer: \\boxed{42}", extra="not structural, so left bare in prose"
    )
    check_one("boxed_math", "$\\boxed{42}$")
    check_one("ce", "\\ce{H2O} is water", extra="bare \\ce in prose is not wrapped")
    check_one("ce_math", "$\\ce{2H2 + O2 -> 2H2O}$")
    check_one("pu", "$\\pu{5 m/s}$")
    out = check_one("mathscr", "$\\mathscr{L}$", must_render=True)
    show("audit", audit_kinds(out))
    check_one("cal", "$\\cal C$")


@attack
def environments():
    check_one("matrix", "$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$")
    check_one(
        "cases", "$f(x) = \\begin{cases} x & x > 0 \\\\ -x & x \\le 0 \\end{cases}$"
    )
    check_one(
        "align_inline",
        "$\\begin{align} a &= b \\end{align}$",
        must_render=False,
        extra="align only renders in display mode",
    )
    check_one(
        "matrix_prose",
        "\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}",
        extra="bare environment in prose is not wrapped",
    )
    check_one(
        "row_break_then_cmd",
        "$$a \\\\\\frac{1}{2}$$",
        must_keep=["\\\\\\frac"],
        extra="\\\\ row break directly followed by \\frac",
    )
    check_one(
        "row_break_then_end",
        "$\\begin{aligned} a &= b \\\\\\end{aligned}$",
        must_keep=["\\\\\\end"],
    )
    print(
        "    to_plain matrix:",
        repr(to_plain("$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$")),
    )
    print(
        "    to_plain cases :",
        repr(to_plain("$\\begin{cases} x & x > 0 \\\\ -x & x \\le 0 \\end{cases}$")),
    )


@attack
def text_with_nested_braces_and_units():
    check_one("text_nested", "$\\text{if } x \\in \\{1, 2\\}$")
    check_one("text_nested_2", "$\\text{a {b} c}$")
    check_one("units", "$5\\,\\text{m/s}$")
    check_one(
        "units_prose",
        "v = 5\\,\\text{m/s}",
        extra="prose with a spacing command and \\text",
    )
    check_one(
        "text_unicode_sub", "$\\text{H₂O}$", extra="Unicode subscript inside \\text{}"
    )
    check_one("text_unicode_times", "$\\text{5 × 3}$")
    check_one("text_unicode_degree", "$\\text{25°C}$")
    check_one("text_unicode_pi", "$\\text{π r}$")
    check_one("text_unicode_arrow", "$\\ce{A -> B} \\text{→}$")
    check_one("text_hindi", "$\\text{यह} = 5$")


@attack
def percent_hash_ampersand():
    check_one("percent_prose", "50% of students", expect="50% of students")
    check_one(
        "percent_math",
        "$50%$",
        must_render=False,
        extra="unescaped % inside math starts a comment: KaTeX renders '50' only; fix does not escape it",
    )
    check_one("hash_prose", "Question #3", expect="Question #3")
    check_one("hash_math", "$#3$", must_render=False)
    check_one("amp_prose", "AT&T and R&D", expect="AT&T and R&D")
    check_one(
        "amp_math", "$a & b$", must_render=False, extra="& outside an environment"
    )
    check_one("escaped_percent_math", "$50\\%$")
    print(
        "    to_plain:",
        [to_plain(x) for x in ["$50\\%$", "$a \\& b$", "$\\#1$", "50% of"]],
    )


@attack
def numbers_next_to_dollar():
    check_one("thousands", "Pay $1,000 now", expect="Pay \\$1,000 now")
    check_one("sci_currency", "$1.5e-3", expect="\\$1.5e-3")
    check_one(
        "thousands_math",
        "$1,000 \\times 2$",
        extra="a math span that starts with a digit and has a valid closer stays math",
    )
    check_one("sci_math", "$1.5 \\times 10^{-3}$")
    check_one(
        "range", "between $5 and $10 dollars", expect="between \\$5 and \\$10 dollars"
    )
    check_one(
        "price_then_math",
        "costs $5 and x = $\\frac{1}{2}$",
        expect="costs \\$5 and x = $\\frac{1}{2}$",
    )


@attack
def scientific_notation_and_chemistry_unicode():
    check_one(
        "sci_unicode", "c = 3 × 10⁸ m/s", extra="Unicode superscript after a number"
    )
    check_one("sci_ascii", "c = 3 x 10^8 m/s")
    check_one("sci_e", "c = 3e8 m/s", expect="c = 3e8 m/s")
    check_one("chem_water", "H₂O is water")
    check_one("chem_sulfate", "SO₄²⁻ ion")
    check_one("chem_iron", "Fe³⁺ and Fe²⁺")
    check_one("chem_paren", "Ca(OH)₂ is lime", must_keep=["lime"])
    check_one("chem_equation", "2H₂ + O₂ → 2H₂O")
    check_one("chem_glucose", "C₆H₁₂O₆")
    check_one("chem_in_word", "xH₂O", extra="preceded by a letter: not chemistry")
    check_one("chem_10_8", "10⁸ and mc² and x₁", extra="not chemistry-shaped")


@attack
def json_transport_edge_cases():
    cases = [
        ('{"q": "5\\\\ \\\\text{m}"}'.replace("\\\\", "\\"), "backslash-space"),
        ('{"q": "\\\\[2pt]"}'.replace("\\\\", "\\"), "backslash-bracket"),
        ('{"q": "a\\\\1"}'.replace("\\\\", "\\"), "backslash-digit"),
        (
            '{"q": "\\\\begin{pmatrix}1&2\\\\\\\\3&4\\\\end{pmatrix}"}'.replace(
                "\\\\", "\\"
            ),
            "row break \\\\ in raw LaTeX",
        ),
        (
            '{"q": "\\\\frac{1}{2} \\\\theta \\\\nu \\\\times"}'.replace("\\\\", "\\"),
            "single-backslash commands",
        ),
        ('{"q": "Step 1\\nnext step\\ttab"}', "JSON escapes that are prose"),
        (
            '{"q": "$\\\\nu$ and \\\\nu and\\nu"}'.replace("\\\\", "\\"),
            "nu in math and prose",
        ),
        ('{"q": "\\\\teacher: hello"}'.replace("\\\\", "\\"), "script label"),
        (
            '{"q": "\\\\u03b1 and \\\\underline{x} and \\\\udeaf"}'.replace(
                "\\\\", "\\"
            ),
            "\\u escapes vs \\underline",
        ),
        ('{"q": "a\\\\"}'.replace("\\\\", "\\"), "trailing backslash"),
        ('{"q": "\\\\\\"quoted\\\\\\""}'.replace("\\\\", "\\"), "escaped quotes"),
    ]
    failures = []
    for doc, label in cases:
        try:
            got = loads_latex_aware(doc)
            q = got["q"]
            ctrl = [c for c in CTRL_RE.findall(q) if c not in "\n\t"]
            print(
                f"    {label:<32} {doc!r:<52} -> {q!r}"
                + (f"   CONTROL {ctrl!r}" if ctrl else "")
            )
            if ctrl:
                failures.append((label, q))
        except Exception as exc:  # noqa: BLE001
            print(
                f"    {label:<32} {doc!r:<52} -> RAISES {type(exc).__name__}: {str(exc)[:50]}"
            )
            failures.append((label, f"raises {type(exc).__name__}"))
    verdict(
        "json_transport_edge_cases",
        "FAIL" if failures else "PASS",
        "; ".join(f"{l}: {r}" for l, r in failures) if failures else "ok",
    )


@attack
def json_roundtrip_of_fixed_output():
    """Everything fix produces must survive a JSON round trip."""
    bad = []
    for text in [
        "Cost \\$5 and $\\theta$",
        "$\\frac{1}{2}$",
        "line\nbreak",
        "$\\text{H}_{2}\\text{O}$",
        "a\\\\b",
        "$\\nu$",
        "\\nabla",
        "tab\there",
    ]:
        out = fix(text)
        back = loads_latex_aware(json.dumps({"q": out}))["q"]
        print(f"    {out!r:<36} -> {back!r}")
        if back != out:
            bad.append((out, back))
    verdict(
        "json_roundtrip_of_fixed_output",
        "FAIL" if bad else "PASS",
        str(bad) if bad else "ok",
    )


@attack
def markers_and_urls():
    check_one(
        "image_marker_prose", "See {{IMAGE:x_1}} below", must_keep=["{{IMAGE:x_1}}"]
    )
    check_one(
        "image_marker_with_cmd",
        "{{IMAGE:x_1}} \\alpha = 3",
        must_keep=["{{IMAGE:x_1}}"],
        extra="marker next to a bare command",
    )
    check_one(
        "url_prose",
        "see https://a.b/c_d^e/f_g.png?x=1 now",
        must_keep=["https://a.b/c_d^e/f_g.png?x=1"],
    )
    many = (
        " ".join(f"{{{{IMAGE:img_{i}}}}}" for i in range(12))
        + " $a_1 {{IMAGE:last_1}}$"
    )
    check_one(
        "twelve_markers_one_in_math",
        many,
        must_keep=[f"{{{{IMAGE:img_{i}}}}}" for i in range(12)] + ["{{IMAGE:last_1}}"],
        must_render=False,
    )
    check_one(
        "url_containing_marker",
        "http://host/{{IMAGE:x_1}}",
        must_keep=["{{IMAGE:x_1}}"],
    )
    print(
        "    to_plain marker:",
        repr(to_plain("{{IMAGE:169_optA}}")),
        "| to_plain url:",
        repr(to_plain("https://a.b/c_d.png")),
    )
    if to_plain("{{IMAGE:169_optA}}") != "{{IMAGE:169_optA}}":
        verdict(
            "to_plain_image_marker",
            "FAIL",
            "to_plain destroys an image marker (CONTRACT §5: markers survive every function)",
            output=to_plain("{{IMAGE:169_optA}}"),
        )


@attack
def mojibake_and_nbsp():
    check_one(
        "nbsp",
        "5\u00a0km and Chapter\u00a05",
        must_keep=["5 km", "Chapter 5"],
        extra="NBSP should become a space, not vanish",
    )
    check_one(
        "em_dash_superscript",
        "10—¹ range",
        must_keep=["—"],
        extra="_DASH_SUPER_GARBAGE_RE deletes an em dash followed by superscript digits",
    )
    check_one("html_entities_twice", "&amp;amp;", extra="entity unescape once per pass")
    check_one("mojibake_pi", "Ï€ r²", expect="$\\pi$ $r^{2}$", extra="")
    check_one("mojibake_double", "cafÃƒÂ©", must_keep=["caf"])
    check_one(
        "french_word",
        "naÏf Île",
        must_keep=["Île"],
        extra="real accented capitals vs mojibake rules",
    )
    check_one(
        "romanian_In",
        "În casă",
        must_keep=["În"],
        extra="`Î ` (Î + space) is a mojibake key for Π",
    )


@attack
def ref_cycle_control_char():
    text = "see \\ref{eq1} and \\rule{1pt}{1pt}"
    out = fix(text)
    show("input", text)
    show("fix", out)
    show("audit", audit_kinds(out))
    if CTRL_RE.search(out):
        verdict(
            "ref_cycle_control_char",
            "FAIL",
            "fix produced a control character (\\ref is in LATEX_COMMANDS_BEHIND_JSON_ESCAPES but not in KATEX_COMMANDS, so repair and decode_escapes fight)",
            output=out,
        )
    else:
        verdict("ref_cycle_control_char", "PASS", "ok")


@attack
def orphans_and_legacy_delims():
    check_one("orphan_paren", "value \\( x", expect="value  x")
    check_one("legacy_multiline", "\\(\n x^2 \n\\)", expect="$x^2$")
    check_one("display_multiline", "\\[\n x^2 \n\\]")
    check_one(
        "inline_containing_legacy",
        "$\\(x\\)$",
        must_render=False,
        extra="legacy delimiters nested in $…$ -> $$x$$",
    )
    check_one(
        "md_escaped_brackets",
        "Use \\[link\\] syntax",
        must_keep=["link"],
        extra="markdown-escaped brackets become display math",
    )


@attack
def performance_quadratic_scans():
    cases = {
        "greek_prose_10k": ("α β γ π ω " * 2000)[:10000],
        "newline_words_10k": ("hello\nworld " * 900)[:10000],
        "open_brace_dollars_10k": ("$a{" * 3400)[:10000],
        "vec_arrows_10k": ("a⃗ " * 3400)[:10000],
        "mixed_10k": ("velocity $v$ and π and $\\alpha$ costs $5 " * 300)[:10000],
    }
    slow = []
    for name, text in cases.items():
        for fname, f in [
            ("fix", fix),
            ("segment", segment),
            ("audit", audit_kinds),
            ("to_plain", to_plain),
            ("repair", repair),
        ]:
            t0 = time.perf_counter()
            f(text)
            ms = (time.perf_counter() - t0) * 1000
            flag = "  <-- SLOW" if ms > 50 else ""
            print(f"    {name:<24} {fname:<9} {ms:8.1f} ms{flag}")
            if ms > 50:
                slow.append(f"{fname}({name}) {ms:.0f} ms")
    verdict(
        "performance_quadratic_scans",
        "FAIL" if slow else "PASS",
        "; ".join(slow) if slow else "all under 50 ms per 10 kB",
    )


@attack
def to_plain_prefix_peeling():
    cases = {
        "\\neg p": "¬p / neg p",
        "\\top": "⊤ / top",
        "\\inf": "inf",
        "a \\pmod{n}": "a mod n",
        "a \\leqslant b": "a ≤ b",
        "\\newline": "",
        "\\intercal": "intercal",
        "\\middle|": "|",
        "\\bigcup": "∪",
    }
    bad = []
    for latex, want in cases.items():
        got = to_plain(f"${latex}$")
        print(f"    {latex:<16} -> {got!r:<14} (reasonable: {want})")
        if any(ch in got for ch in "≠→∈±≤∫") and latex not in ("a \\leqslant b",):
            bad.append((latex, got))
        if latex == "a \\leqslant b" and "slant" in got:
            bad.append((latex, got))
    verdict(
        "to_plain_prefix_peeling",
        "FAIL" if bad else "PASS",
        "prefix peeling in _command splits real commands: " + str(bad) if bad else "ok",
    )


@attack
def tts_style():
    cases = {
        "$x^{20}$": "x to the power 20",
        "$\\frac{\\frac{1}{2}}{3}$": "1 over 2 over 3",
        "$x^{30}$": "x to the power 30",
        "$\\pmatrix$": "pmatrix",
        "$x^2 + y^3$": "x squared + y cubed",
    }
    bad = []
    for latex, want in cases.items():
        got = to_plain(latex, "tts")
        print(f"    {latex:<28} -> {got!r:<22} (want ~ {want})")
        if (
            "squared0" in got
            or "cubed0" in got
            or "over 23" in got
            or "minusatrix" in got
        ):
            bad.append((latex, got))
    verdict("tts_style", "FAIL" if bad else "PASS", str(bad) if bad else "ok")


@attack
def prose_only_short_words():
    for text in [
        "Let x be \\alpha",
        "So a = \\pi r",
        "if x \\in A then",
        "x \\to 0 as n \\to \\infty",
        "\\alpha-decay",
        "a \\cdot b",
    ]:
        out = fix(text)
        ok, fails = renders(out)
        print(
            f"    {text!r:<32} -> {out!r}"
            + ("" if ok else f"   KATEX FAIL {fails[0][1][:40]}")
        )
    out = fix("Let x be \\alpha")
    verdict(
        "prose_only_short_words",
        "PASS" if not (out.startswith("$") and out.endswith("$")) else "FAIL",
        "short-word prose sentences are not wrapped whole"
        if not out.startswith("$")
        else f"whole sentence wrapped: {out!r}",
    )


@attack
def sqrt_without_argument_and_bare_root():
    check_one(
        "sqrt_bare", "use \\sqrt here", expect="use \\sqrt here", must_render=False
    )
    check_one("sqrt2", "\\sqrt2 is irrational", extra="\\sqrt2 without braces")
    check_one("frac12", "half is \\frac12")
    check_one("root_glyph_2", "√2 is irrational")
    check_one("root_glyph_expr", "√(x+1) and √2gh", extra="√2gh keeps the glyph")
    check_one(
        "sqrt_dollar", "$\\sqrt$2", must_render=False, extra="already broken input"
    )


@attack
def double_escaped_commands_not_in_collapse_list():
    bad = []
    for text in [
        "\\\\cdots",
        "\\\\ce{H2O}",
        "\\\\displaystyle x",
        "\\\\mathscr{L}",
        "\\\\ldots",
        "$\\\\cdots$",
        "\\\\Rightarrow",
        "\\\\frac{1}{2}",
    ]:
        out = fix(text)
        kinds = audit_kinds(out)
        print(f"    {text!r:<20} -> {out!r:<24} audit={kinds}")
        if "double_escaped_command" in kinds:
            bad.append(text)
    verdict(
        "double_escaped_commands_not_in_collapse_list",
        "FAIL" if bad else "PASS",
        f"still double-escaped after fix: {bad}" if bad else "ok",
    )


@attack
def normalize_vs_segment_currency_parity():
    """normalize's `_MATH_SPAN_RE` and canonicalize's `_INLINE_SPAN_RE` do not
    apply the pandoc closer rules that `segment` applies."""
    bad = []
    for text in [
        "$5 and $x \\nabla y$",
        "cost $5 then\\nnext $x^2$",
        "a $ b $ c \\nnext",
    ]:
        out = normalize(text)
        segs = [(s["kind"], s["value"]) for s in segment(out)]
        print(f"    {text!r:<34} -> {out!r:<40} segs={segs}")
        if "\\nnext" in out and any(k == "text" and "\\nnext" in v for k, v in segs):
            bad.append(text)
    verdict(
        "normalize_vs_segment_currency_parity",
        "FAIL" if bad else "PASS",
        "a literal \\n in prose was not decoded because a regex-level span swallowed it"
        if bad
        else "ok",
    )


@attack
def repair_newline_eq():
    for text in [
        "Values:\neq 5",
        "x\ntimes 2",
        "\rho is density",
        "a\tto b",
        "given\nabla",
    ]:
        out = repair(text)
        print(f"    {text!r:<24} -> {out!r}  audit={audit_kinds(text)}")
    r = repair("Values:\neq 5")
    verdict(
        "repair_newline_eq",
        "NOTE" if "\\neq" in r else "PASS",
        "LF + 'eq' is restored as \\neq although audit (3-letter minimum after LF) would not have flagged it"
        if "\\neq" in r
        else "ok",
    )


if __name__ == "__main__":
    for a in ATTACKS:
        a()
    with open(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "attacks_results.json"
        ),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    print("\n\nSUMMARY")
    for status in ("FAIL", "NOTE", "PASS"):
        names = [r["attack"] for r in RESULTS if r["status"] == status]
        print(f"  {status}: {len(names)}  {names}")
