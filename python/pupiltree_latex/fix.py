"""`fix`: the one call for people who do not want to learn the six.

    from pupiltree_latex import fix, fix_deep

    fix("Cost $5 and \\(\\theta\\) with \x0crac{1}{2} and π and H₂O")
    # -> 'Cost \\$5 and $\\theta$ with $\\frac{1}{2}$ and $\\pi$ and $\\text{H}_{2}\\text{O}$'

``fix`` = `normalize` (lossless repair, mojibake, delimiters, orphans,
currency, prose escapes) → `canonicalize` (Unicode math → LaTeX, bare
structural commands and scripts wrapped in ``$…$``, brace fixes) →
`wrap_bare_symbol_commands` (a bare ``\\times`` / ``\\pi`` / ``\\leq`` in
prose → ``$\\times$``) → `wrap_unicode_chemistry` (``H₂O`` →
``$\\text{H}_{2}\\text{O}$``) → `wrap_unicode_scripts` (``10⁻³`` →
``$10^{-3}$``, ``mc²`` → ``$mc^{2}$``) → `escape_text_specials` (``%`` and
a ``$`` inside ``\\text{}`` escaped inside math) → `merge_adjacent_math`
(``$\\times$ $10^8$`` → ``$\\times 10^8$``). Idempotent. Non-strings pass
through. ``fix_deep`` walks a JSON-like document and skips ids, URLs, paths,
timestamps and status enums (CONTRACT §5).

Where to call it:
  - **Backend, write path**: on fresh model output, once, then store.
  - **Frontend / renderer**: on whatever text is about to be displayed. The
    `MathText` widgets and components call it for you.
  - **Not** as a read-path rewrite of stored content that is served back
    to other apps (serve stored bytes plus `repair`; see CONTRACT §3).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from .canonicalize import canonicalize
from .normalize import normalize
from .repair import repair_deep
from .segment import Segment, segment
from .unicode_math import (
    UNICODE_MATH,
    cluster_left,
    cluster_right,
    convert_cluster,
    wrap_cluster,
)
from .walk import is_narrative_key, is_non_content_key, is_url_or_path_string

# ---------------------------------------------------------------------------
# Bare symbol commands
# ---------------------------------------------------------------------------

# Commands that take no argument and stand alone: every plain `\name` that a
# Unicode math character maps to, plus the common aliases. A bare one in
# prose (`3 \times 10^8`) renders as the literal backslash text; wrapping it
# is always right because these commands mean nothing outside math.
# `sqrt` (from `√`) is excluded: it needs an argument and `$\sqrt$` is a
# parse error.
SYMBOL_COMMANDS: frozenset[str] = frozenset(
    {v[1:] for v in UNICODE_MATH.values() if re.fullmatch(r"\\[A-Za-z]+", v)}
    | {
        "to",
        "le",
        "ge",
        "ne",
        "implies",
        "iff",
        "deg",
        "degree",
        "cdots",
        "dots",
        "ldots",
    }
) - {"sqrt"}
_BARE_SYMBOL_RE = re.compile(
    r"(?<!\\)\\("
    + "|".join(sorted(SYMBOL_COMMANDS, key=len, reverse=True))
    + r")(?![A-Za-z])"
)


def _apply_to_text_segments(text: str, transform: Callable[[str], str]) -> str:
    parts: list[str] = []
    for seg in segment(text):
        parts.append(transform(seg["raw"]) if seg["kind"] == "text" else seg["raw"])
    return "".join(parts)


def _apply_to_math_segments(text: str, transform: Callable[[str], str]) -> str:
    parts: list[str] = []
    for seg in segment(text):
        if seg["kind"] == "math":
            raw = seg["raw"]
            k = 2 if raw.startswith(("$$", "\\")) else 1
            parts.append(
                raw[:k] + transform(raw[k : len(raw) - k]) + raw[len(raw) - k :]
            )
        else:
            parts.append(seg["raw"])
    return "".join(parts)


# A symbol command that a broken earlier pass left between two dollars which
# the renderers do not read as a span (`x$\leq$5`: a closer followed by a
# digit is not a closer). In a text segment its dollars are dropped first and
# it is then wrapped like any bare command.
_DELIMITED_SYMBOL_RE = re.compile(
    r"(?<![\\$])\$(\\(?:"
    + "|".join(sorted(SYMBOL_COMMANDS, key=len, reverse=True))
    + r"))\$(?![$A-Za-z])"
)
# Inside a cluster: another bare symbol command (`3\times4\times5`).
_CLUSTER_COMMAND_RE = re.compile(
    r"\\(?:"
    + "|".join(sorted(SYMBOL_COMMANDS, key=len, reverse=True))
    + r")(?![A-Za-z])"
)


def _wrap_symbols_in_text(t: str) -> str:
    if "$" in t:
        t = _DELIMITED_SYMBOL_RE.sub(lambda m: m.group(1), t)
    out: list[str] = []
    last = 0
    for m in _BARE_SYMBOL_RE.finditer(t):
        if m.start() < last:
            continue  # already inside the previous cluster
        start = cluster_left(t, m.start(), last)
        end = cluster_right(t, m.start(), command_re=_CLUSTER_COMMAND_RE)
        out.append(t[last:start])
        out.append(wrap_cluster(t, start, end, convert_cluster(t[start:end])))
        last = end
    out.append(t[last:])
    return "".join(out)


def wrap_bare_symbol_commands(text: Any) -> Any:
    """``3 \\times 10`` → ``3 $\\times$ 10``; ``\\alpha`` → ``$\\alpha$`` — for
    argument-less symbol commands outside math spans only.

    The span takes the tight cluster around the command (``x\\leq5`` →
    ``$x\\leq5$``, ``\\alpha_1`` → ``$\\alpha_1$``, ``3\\times4\\times5`` →
    ``$3\\times4\\times5$``), so it never ends right before a digit; a
    command already between stray dollars (``x$\\leq$5``) is re-wrapped
    without them, never into ``$$``."""
    if not isinstance(text, str) or "\\" not in text:
        return text
    return _apply_to_text_segments(text, _wrap_symbols_in_text)


# ---------------------------------------------------------------------------
# Unicode chemistry and scripts
# ---------------------------------------------------------------------------

_SUB_DIGITS = "₀₁₂₃₄₅₆₇₈₉"
_SUP_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
_SUP_TO_ASCII = str.maketrans(_SUP_CHARS, "0123456789+-")
_SUB_TO_ASCII = str.maketrans(_SUB_DIGITS, "0123456789")

# A chemistry-shaped run: an optional coefficient, then a capital letter,
# then element letters, digits and parentheses, with at least one Unicode
# sub/superscript. The superscript characters are listed one by one: ¹²³
# are U+00B9/U+00B2/U+00B3 and sit outside the U+2070–U+2079 range.
_SCRIPT_CLASS = _SUB_DIGITS + _SUP_CHARS
_CHEM_RUN_RE = re.compile(
    r"(?<!\w)"  # not preceded by a letter, digit or `_` (`xH₂O`, `TRUE_FALSE⁻` stay)
    r"[0-9]*[a-z]?(?=[A-Z])[A-Za-z0-9()]*["
    + _SCRIPT_CLASS
    + r"][A-Za-z0-9()"
    + _SCRIPT_CLASS
    + r"]*"
)
_CHARGE_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]*[⁺⁻]")
# Any other base + Unicode scripts outside math (`10⁻³`, `mc²`, `x₁`, `s²`):
# a word of letters/digits followed by one run of scripts.
_SCRIPT_RUN_RE = re.compile(
    r"(?<!\w)([A-Za-z0-9]+(?:\.[0-9]+)?)(["
    + _SUP_CHARS
    + r"]+|["
    + _SUB_DIGITS
    + r"]+)(?!["
    + _SCRIPT_CLASS
    + r"])"
)


def _trim_unbalanced_parens(run: str) -> tuple[str, str]:
    """``H₂O)`` → (``H₂O``, ``)``): a closing parenthesis that has no opener
    inside the run belongs to the prose around it."""
    tail = ""
    while run.endswith(")") and run.count(")") > run.count("("):
        run = run[:-1]
        tail = ")" + tail
    return run, tail


def _convert_chem_run(run: str) -> str:
    out: list[str] = []
    i = 0
    n = len(run)
    while i < n:
        ch = run[i]
        if ch in _SUB_DIGITS:
            j = i
            while j < n and run[j] in _SUB_DIGITS:
                j += 1
            out.append("_{" + run[i:j].translate(_SUB_TO_ASCII) + "}")
            i = j
        elif ch in _SUP_CHARS:
            j = i
            while j < n and run[j] in _SUP_CHARS:
                j += 1
            out.append("^{" + run[i:j].translate(_SUP_TO_ASCII) + "}")
            i = j
        else:
            j = i
            while j < n and run[j] not in _SCRIPT_CLASS:
                j += 1
            out.append("\\text{" + run[i:j] + "}")
            i = j
    return "$" + "".join(out) + "$"


def _pad_span(text: str, start: int, end: int | None, span: str) -> str:
    """One space around a new span where a neighbour would break it: a
    literal ``$`` right before or after (``$$`` opens display math), or a
    digit right after (a closer followed by a digit is not a closer)."""
    if start > 0 and text[start - 1] == "$" and (start < 2 or text[start - 2] != "\\"):
        span = " " + span
    if (
        end is not None
        and end < len(text)
        and (text[end] == "$" or text[end].isdigit())
    ):
        span = span + " "
    return span


def _chem_in_text(text: str) -> str:
    def replace(m: re.Match[str]) -> str:
        run, tail = _trim_unbalanced_parens(m.group(0))
        start = m.start()
        if start > 0 and text[start - 1] in "\\{":
            return run + tail
        has_subscript = any(c in _SUB_DIGITS for c in run)
        if not has_subscript and not _CHARGE_RE.search(run):
            return run + tail
        span = _convert_chem_run(run)
        if tail:
            return _pad_span(text, start, None, span) + tail
        return _pad_span(text, start, m.end(), span)

    return _CHEM_RUN_RE.sub(replace, text)


def wrap_unicode_chemistry(text: Any) -> Any:
    """``H₂O`` → ``$\\text{H}_{2}\\text{O}$``, ``SO₄²⁻`` → ``$\\text{SO}_{4}^{2-}$``,
    ``Fe³⁺`` → ``$\\text{Fe}^{3+}$`` — outside existing math spans only.

    A run must start with a capital letter (after an optional coefficient)
    and carry a subscript digit or a superscript charge; ``10⁸``, ``mc²``
    and ``x₁`` are left to `wrap_unicode_scripts`.
    """
    if not isinstance(text, str) or not text:
        return text
    if not any(c in text for c in _SCRIPT_CLASS):
        return text
    return _apply_to_text_segments(text, _chem_in_text)


# Units set upright when they carry a Unicode power (`mol⁻¹`, `mm³`, `kPa²`).
# A multi-letter base must be in this list; a single letter (`m`, `s`, `g`)
# only counts as a unit right after a number or a `/` (`9.8 m/s²`), so the
# variables `x²` and `a²` stay italic.
UNIT_BASES: frozenset[str] = frozenset(
    (
        "mm cm dm km nm pm um mg kg ms ns ps us mol mmol kmol rad sr cd "
        "mL kJ kW kV kN kPa MPa Pa Hz kHz MHz GHz eV keV MeV mA mV"
    ).split()
)
SINGLE_LETTER_UNITS: frozenset[str] = frozenset("msgl")


def _number_or_slash_before(text: str, start: int) -> bool:
    """True when ``text[:start]`` ends with ``/`` or with a digit followed by
    spaces or tabs."""
    k = start - 1
    if k >= 0 and text[k] == "/":
        return True
    while k >= 0 and text[k] in " \t":
        k -= 1
    return k >= 0 and "0" <= text[k] <= "9"


def _scripts_in_text(text: str) -> str:
    def replace(m: re.Match[str]) -> str:
        start = m.start()
        if start > 0 and text[start - 1] in "\\{":
            return m.group(0)
        base, scripts = m.group(1), m.group(2)
        # A unit is set upright (`240 cm³`, `m/s²`, `mol⁻¹`, `per mm³`);
        # anything else (`mc²`, `x₁`, `10⁸`) is math.
        after_number = _number_or_slash_before(text, start)
        if base in UNIT_BASES or (
            base.isalpha()
            and base.islower()
            and after_number
            and (len(base) > 1 or base in SINGLE_LETTER_UNITS or text[start - 1] != "/")
        ):
            base = "\\text{" + base + "}"
        if scripts[0] in _SUP_CHARS:
            span = "$" + base + "^{" + scripts.translate(_SUP_TO_ASCII) + "}$"
        else:
            span = "$" + base + "_{" + scripts.translate(_SUB_TO_ASCII) + "}$"
        return _pad_span(text, start, m.end(), span)

    return _SCRIPT_RUN_RE.sub(replace, text)


def wrap_unicode_scripts(text: Any) -> Any:
    """``10⁻³`` → ``$10^{-3}$``, ``mc²`` → ``$mc^{2}$``, ``x₁`` → ``$x_{1}$``
    — a base of letters/digits followed by one run of Unicode scripts,
    outside math spans, after chemistry has taken its formulas."""
    if not isinstance(text, str) or not text:
        return text
    if not any(c in text for c in _SCRIPT_CLASS):
        return text
    return _apply_to_text_segments(text, _scripts_in_text)


# ---------------------------------------------------------------------------
# Specials inside math
# ---------------------------------------------------------------------------

_TEXT_GROUP_RE = re.compile(
    r"\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|mathrm|mbox)\s*\{"
)
_UNESCAPED_PERCENT_RE = re.compile(r"(?<!\\)%")
_UNESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)\$")


def _escape_specials_in_math(value: str) -> str:
    # `%` starts a TeX comment: `$50%$` renders nothing after it.
    value = _UNESCAPED_PERCENT_RE.sub(r"\\%", value)
    # A `$` inside a `\text{…}` group would end the span for the renderer.
    out: list[str] = []
    i = 0
    n = len(value)
    while i < n:
        m = _TEXT_GROUP_RE.match(value, i)
        if m:
            depth = 0
            j = m.end() - 1
            while j < n:
                if value[j] == "\\":
                    j += 2
                    continue
                if value[j] == "{":
                    depth += 1
                elif value[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            group = value[i:j]
            out.append(_UNESCAPED_DOLLAR_RE.sub(r"\\$", group))
            i = j
            continue
        out.append(value[i])
        i += 1
    return "".join(out)


def escape_text_specials(text: Any) -> Any:
    """Inside math spans: ``%`` → ``\\%``; a ``$`` inside ``\\text{…}`` →
    ``\\$``. Both would otherwise cut the formula short in every renderer."""
    if not isinstance(text, str) or ("%" not in text and "$" not in text):
        return text
    return _apply_to_math_segments(text, _escape_specials_in_math)


# ---------------------------------------------------------------------------
# Adjacent spans
# ---------------------------------------------------------------------------

_ONLY_BLANKS_RE = re.compile(r"[ \t]*")
_ENV_RE = re.compile(r"\\(begin|end)\{")
# Declaration-style switches: they change the scope of a merged span.
DECLARATION_COMMANDS = (
    "bf it rm sf tt cal sl em mit color displaystyle textstyle scriptstyle "
    "scriptscriptstyle tiny scriptsize footnotesize small normalsize large Large "
    "LARGE huge Huge"
).split()
_DECLARATION_RE = re.compile(
    r"\\(?:" + "|".join(DECLARATION_COMMANDS) + r")(?![A-Za-z])"
)


def _mergeable(value: str) -> bool:
    """A span is merged only when it is self-contained: balanced braces and
    matched `\\begin`/`\\end`. Merging a broken span would break its
    neighbours too."""
    depth = 0
    for ch in value:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    if depth != 0:
        return False
    # A declaration-style switch (`\bf`, `\color{red}`, `\Large`) acts on
    # everything after it in its span: merged, `$\flat$ $\bf x$` would set
    # the neighbours in bold too.
    if "\\" in value and _DECLARATION_RE.search(value):
        return False
    envs = _ENV_RE.findall(value)
    return envs.count("begin") == envs.count("end")


def merge_adjacent_math(text: Any) -> Any:
    """``$\\times$ $10^8$`` → ``$\\times 10^8$``: inline spans separated by
    nothing or by spaces/tabs become one span. Display spans, spans with
    prose between them and spans that are not self-contained are left alone.
    Linear: each span's mergeability is computed once."""
    if not isinstance(text, str) or text.count("$") < 4:
        return text
    segs = segment(text)
    out: list[str] = []
    run_values: list[str] = []  # values of the inline spans being merged
    run_ok = False

    def flush() -> None:
        if run_values:
            out.append("$" + " ".join(run_values) + "$")
            run_values.clear()

    i = 0
    n = len(segs)
    while i < n:
        seg = segs[i]
        is_inline = (
            seg["kind"] == "math" and not seg["display"] and seg["raw"].startswith("$")
        )
        if is_inline:
            ok = _mergeable(seg["value"])
            if run_values and run_ok and ok:
                run_values.append(seg["value"])
            else:
                flush()
                run_values.append(seg["value"])
                run_ok = ok
            i += 1
            continue
        if (
            seg["kind"] == "text"
            and _ONLY_BLANKS_RE.fullmatch(seg["raw"])
            and run_values
            and i + 1 < n
            and segs[i + 1]["kind"] == "math"
            and not segs[i + 1]["display"]
            and segs[i + 1]["raw"].startswith("$")
            and run_ok
            and _mergeable(segs[i + 1]["value"])
        ):
            i += 1  # the blank separator disappears into the merged span
            continue
        flush()
        out.append(seg["raw"])
        i += 1
    flush()
    return "".join(out)


# ---------------------------------------------------------------------------
# The one call
# ---------------------------------------------------------------------------


def fix(text: Any, *, chemistry: bool = True) -> Any:
    """Repair, normalise, canonicalise, wrap what is still bare, escape what
    would cut a formula short and merge adjacent spans, in one call.

    ``chemistry=False`` is for renderers without KaTeX's mhchem extension:
    a bare ``\\ce{…}`` / ``\\pu{…}`` is never put into a new math span."""
    if not isinstance(text, str) or not text:
        return text
    text = canonicalize(normalize(text), chemistry=chemistry)
    text = wrap_bare_symbol_commands(text)
    text = wrap_unicode_chemistry(text)
    text = wrap_unicode_scripts(text)
    text = escape_text_specials(text)
    return merge_adjacent_math(text)


def fix_deep(
    obj: Any,
    _key_hint: str = "",
    *,
    chemistry: bool = True,
    narrative_keys: Iterable[str] | None = None,
) -> Any:
    """`fix` over every content string of a JSON-like document, skipping
    non-content keys and URL-shaped values (CONTRACT §5).

    ``narrative_keys`` (tag ``v140-b5``): values under these keys are
    Class B narration (CONTRACT §2) and get the lossless `repair_deep` only,
    never `fix`. An entry ``name@sibling`` matches ``name`` only in an object
    that also has a ``sibling`` key (``script@transcript``)."""
    keys = tuple(narrative_keys) if narrative_keys else ()
    if isinstance(obj, str):
        if is_non_content_key(_key_hint) or is_url_or_path_string(obj):
            return obj
        return fix(obj, chemistry=chemistry)
    if isinstance(obj, dict):
        return {
            k: (
                repair_deep(v)
                if is_narrative_key(k, obj, keys)
                else fix_deep(v, _key_hint=k, chemistry=chemistry, narrative_keys=keys)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            fix_deep(v, _key_hint=_key_hint, chemistry=chemistry, narrative_keys=keys)
            for v in obj
        ]
    return obj


def needs_fix(text: Any, *, chemistry: bool = True) -> bool:
    """True when `fix` would change more than `normalize` does: it would add
    LaTeX for Unicode or bare maths (``H₂O``, ``√2``, ``π``, ``x × y``,
    ``\\frac{1}{2}`` in prose) or repair a formula (tag ``v140-b9``).
    ``False`` for non-strings and for text `fix` leaves as `normalize` does
    (plain prose, ``$x^2$``, ``costs $5``)."""
    if not isinstance(text, str) or not text:
        return False
    if text.isascii() and not any(c in text for c in "\\^_${}%`"):
        return False
    return fix(text, chemistry=chemistry) != normalize(text)


__all__ = [
    "SYMBOL_COMMANDS",
    "Segment",
    "escape_text_specials",
    "fix",
    "fix_deep",
    "needs_fix",
    "merge_adjacent_math",
    "wrap_bare_symbol_commands",
    "wrap_unicode_chemistry",
    "wrap_unicode_scripts",
]
