"""`canonicalize`: the write-time sanitiser for fresh Class A model output.

Backend `services/ai/helper/latex_rules.sanitize_latex_text` (2026-09-25),
with two deliberate changes: `repair` is this package's superset, and the
``\\(…\\)`` / ``\\[…\\]`` rewrite refuses a backslash-escaped bracket
(``\\\\[2pt]`` is a line break, not a delimiter — the audit already treated
it that way).

Heuristic. Idempotent. Runs ONCE, at the generation chokepoint. Never on the
read path (Backend #1595, the 14 September 2026 incident).
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from .audit import _detect_command_missing_argument, _detect_frac_missing_args
from .commands import (
    ARGUMENT_COMMANDS,
    COLLAPSIBLE_COMMANDS,
    KATEX_COMMANDS,
    STRUCTURAL_COMMANDS,
)
from .mojibake import fix_mojibake_ftfy
from .repair import repair
from .segment import segment
from .unicode_math import (
    UNICODE_MATH,
    convert_combining_vec,
    normalize_homoglyphs,
    unicode_math_to_latex,
    wrap_bare_unicode_math,
)
from .spans import math_mask, math_ranges
from .walk import is_non_content_key, is_url_or_path_string

# ---------------------------------------------------------------------------
# Delimiter rewrites
# ---------------------------------------------------------------------------

_PAREN_INLINE_RE = re.compile(r"(?<!\\)\\\((.+?)(?<!\\)\\\)", re.DOTALL)
_BRACKET_DISPLAY_RE = re.compile(r"(?<!\\)\\\[(.+?)(?<!\\)\\\]", re.DOTALL)

# Inside a math segment, x^10 → x^{10}, a_12 → a_{12} (2+ digit runs only).
_MISSING_BRACE_RE = re.compile(r"([\^_])(-?\d{2,})")
_DISPLAY_SPAN_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_SPAN_RE = re.compile(r"(?<!\$)\$([^$]+?)\$(?!\$)")
# An identifier that ended up inside math (`$q_001_easy_2026$`): bracing its
# digit runs only produces a double-subscript error.
_IDENTIFIER_IN_MATH_RE = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+){2,}")


def _normalize_braces_in_math(segment: str) -> str:
    protected = [(m.start(), m.end()) for m in _IDENTIFIER_IN_MATH_RE.finditer(segment)]

    def replace(m: re.Match[str]) -> str:
        if any(a <= m.start() < b for a, b in protected):
            return m.group(0)
        return m.group(1) + "{" + m.group(2) + "}"

    return _MISSING_BRACE_RE.sub(replace, segment)


def _normalize_braces(text: str) -> str:
    text = _DISPLAY_SPAN_RE.sub(
        lambda m: "$$" + _normalize_braces_in_math(m.group(1)) + "$$", text
    )
    text = _INLINE_SPAN_RE.sub(
        lambda m: "$" + _normalize_braces_in_math(m.group(1)) + "$", text
    )
    return text


# ---------------------------------------------------------------------------
# Structural fixes
# ---------------------------------------------------------------------------

# An EVEN run of backslashes directly before a KaTeX command is JSON
# re-encoding damage (`\\frac`); an odd run (`\\\frac`) is a line break
# followed by a command and is left alone.
_COLLAPSE_RE = re.compile(
    r"(?<!\\)((?:\\\\)+)("
    + "|".join(
        re.escape(c) for c in sorted(COLLAPSIBLE_COMMANDS, key=len, reverse=True)
    )
    + r")(?![a-zA-Z])"
)


_ROW_ENVIRONMENT_RE = re.compile(r"\\begin\{|&")
_TWO_ARGUMENT_COMMANDS = frozenset(
    {"frac", "dfrac", "tfrac", "cfrac", "binom", "dbinom", "tbinom"}
)


def _collapse_double_backslashes(text: str) -> str:
    """`\\\\frac` → `\\frac` everywhere EXCEPT inside a math span that holds
    an environment or an alignment `&`: there `\\\\` is a row separator and
    `a&b\\\\cos x` really is a row starting with `\\cos`. Single-letter
    names (`\\c`, `\\b`) are never collapsed: `\\\\c` is a row + "c".
    """
    if "\\\\" not in text:
        return text

    def _collapse(chunk: str) -> str:
        return _COLLAPSE_RE.sub(
            lambda m: m.group(0) if len(m.group(2)) == 1 else "\\" + m.group(2), chunk
        )

    out: list[str] = []
    pos = 0
    for start, end, _display in math_ranges(text):
        out.append(_collapse(text[pos:start]))
        span = text[start:end]
        out.append(span if _ROW_ENVIRONMENT_RE.search(span) else _collapse(span))
        pos = end
    out.append(_collapse(text[pos:]))
    return "".join(out)


_LEFT_BRACE_RE = re.compile(r"\\left(?!\\)\{")
_RIGHT_BRACE_RE = re.compile(r"\\right(?!\\)\}")


def _fix_left_right_braces(text: str) -> str:
    text = _LEFT_BRACE_RE.sub(r"\\left\\{", text)
    text = _RIGHT_BRACE_RE.sub(r"\\right\\}", text)
    return text


# ---------------------------------------------------------------------------
# Currency (Backend rule: only when the unescaped `$` count is odd)
# ---------------------------------------------------------------------------

_CURRENCY_RE = re.compile(r"(?<!\\)\$(\d[\d,]*(?:\.\d+)?)(?=[\s.,;!?)\]\-–—]|$)")


def _dollar_escaped(text: str, i: int) -> bool:
    """True when an odd run of backslashes precedes ``text[i]`` (``\\$`` is
    an escaped dollar, ``\\\\$`` a line break followed by a real one)."""
    k = i - 1
    while k >= 0 and text[k] == "\\":
        k -= 1
    return (i - 1 - k) % 2 == 1


def _count_unescaped_dollars(text: str) -> int:
    n = 0
    for i, ch in enumerate(text):
        if ch == "$" and not _dollar_escaped(text, i):
            n += 1
    return n


# `\$` preceded by an even run of backslashes (none, or `\\` line breaks):
# only that dollar is escaped. `\\$\frac{1}{2}$` is a line break followed by
# a span, and stashing its `\$` once broke the span into `\\$$…$$`.
_ESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)((?:\\\\)*)\\\$")


def _stash_escaped_dollars(text: str) -> str:
    if "\\$" not in text:
        return text
    return _ESCAPED_DOLLAR_RE.sub(lambda m: m.group(1) + _ESCAPED_DOLLAR_SENTINEL, text)


def _escape_currency(text: str) -> str:
    if _count_unescaped_dollars(text) % 2 == 0:
        return text
    return _CURRENCY_RE.sub(r"\\$\1", text)


# ---------------------------------------------------------------------------
# Bare-command wrapping
# ---------------------------------------------------------------------------

_STRUCTURAL_CMD_RE = re.compile(
    r"\\(?:" + "|".join(STRUCTURAL_COMMANDS) + r")(?![A-Za-z])"
)


def _find_command_extent(text: str, start: int) -> int:
    """Index one past the command at ``start``, its ``[..]``/``{..}``
    arguments and adjacent ``_x`` / ``^x`` scripts (nested braces handled)."""
    n = len(text)
    i = start + 1
    while i < n and text[i].isalpha():
        i += 1
    while i < n:
        ch = text[i]
        if ch in "[{":
            opener = ch
            closer = "]" if opener == "[" else "}"
            depth = 1
            i += 1
            while i < n and depth > 0:
                if text[i] == opener:
                    depth += 1
                elif text[i] == closer:
                    depth -= 1
                i += 1
        elif ch in "_^":
            i += 1
            if i >= n:
                break
            if text[i] == "{":
                depth = 1
                i += 1
                while i < n and depth > 0:
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                    i += 1
            elif text[i] == "\\":
                i += 1
                while i < n and text[i].isalpha():
                    i += 1
            elif not text[i].isspace():
                i += 1
            else:
                break
        else:
            break
    return i


_ANY_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")
_SCRIPT_LABEL_RE = re.compile(r"\\[a-z][a-z_]*:")
_TEXT_BRACE_RE = re.compile(r"\\text\s*\{[^}]*\}")
# Short function words that make a string prose even though they are under
# four letters (Backend's prose test was "a 4+ letter word", which let
# `3 \times 10^8 and \frac{a}{b}` be wrapped whole, italicising "and").
_PROSE_STOPWORDS = frozenset(
    (
        "a an and are as at be but by for if in is it of on or so the then to was "
        "we he she you all any can did do does get got had has how its let may "
        "not now one our out per put see set two use via was who why yet"
    ).split()
)
_SHORT_WORD_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]{1,3}(?![A-Za-z])")
_NON_ASCII_WORD_RE = re.compile(r"[^\W\d_\x00-\x7f][^\W\d_]+")
# Every character UNICODE_MATH maps to `^{…}` or `_{…}` (²³, ⁻, ₀, ⁿ, ₐ, …).
_UNICODE_SCRIPT_RE = re.compile(
    "["
    + re.escape(
        "".join(k for k, v in UNICODE_MATH.items() if v.startswith(("^{", "_{")))
    )
    + "]"
)


def _has_dollar_inside_braces(text: str) -> bool:
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif ch == "}" and (i == 0 or text[i - 1] != "\\") and depth > 0:
            depth -= 1
        elif ch == "$" and (i == 0 or text[i - 1] != "\\") and depth > 0:
            return True
    return False


def _wrap_pure_math_short_strings(text: str) -> str:
    if len(text) > 200 or "$$" in text or not _ANY_LATEX_CMD_RE.search(text):
        return text
    if _has_dollar_inside_braces(text):
        return text
    # A lesson-script line (`\teacher: …`) is prose, however short.
    if _SCRIPT_LABEL_RE.search(text):
        return text
    # An unpaired `$` means the author's spans are broken; stripping and
    # re-wrapping would not converge (`$ H₂` → `$ $…$` → …).
    if _count_unescaped_dollars(text) % 2 == 1:
        return text
    # At least one REAL command must sit outside a span: `\\cs` (a line
    # break followed by "cs") is not math and must not be wrapped.
    mask = math_mask(text)
    has_bare_cmd = any(
        not mask[m.start()] and m.group(0)[1:] in KATEX_COMMANDS
        for m in _ANY_LATEX_CMD_RE.finditer(text)
    )
    if not has_bare_cmd:
        return text
    # A command that needs an argument and has none (`\frac` alone) cannot
    # render however it is wrapped.
    if _detect_command_missing_argument(text) or _detect_frac_missing_args(text):
        return text
    stripped = _TEXT_BRACE_RE.sub("", text)
    stripped = re.sub(r"\$[^$]*\$", "", stripped)
    stripped = _ANY_LATEX_CMD_RE.sub("", stripped)
    if re.findall(r"[A-Za-z]{4,}", stripped):
        return text
    # Prose in any other script (Devanagari, Tamil, …): a run of two or more
    # non-ASCII letters. Bare Greek was already wrapped by step 14, so what
    # is left is words.
    # Unicode super/subscripts (`10²³`) are \w to the regex engine but are
    # math, not letters of a word: they are blanked out first.
    if _NON_ASCII_WORD_RE.search(_UNICODE_SCRIPT_RE.sub(" ", stripped)):
        return text
    if any(w.lower() in _PROSE_STOPWORDS for w in _SHORT_WORD_RE.findall(stripped)):
        return text
    inner = text.strip()
    if not inner:
        return text
    inner = inner.replace("$", "")
    if not inner:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    return f"{lead}${inner}${trail}"


_BARE_SCRIPT_RE = re.compile(
    # Not right after the currency sentinel (its LAST char, U+E001), a
    # backslash (`\log_{10}` is a command, not a bare script) or a `$`.
    r"(?<![\ue001\\$])"
    r"\b[A-Za-z0-9]+"
    r"(?:[_^](?:\{[^{}]*\}|\\[a-zA-Z]+|[A-Za-z0-9]+))+"
    r"[A-Za-z0-9]*"
)


def _looks_like_identifier(s: str) -> bool:
    """snake_case / ALL_CAPS / slug tokens the script regex matches by
    accident: `MCQ_SINGLE`, `q_001_easy_2026`, `ahs_69e74f5e84fd`."""
    if any(c in s for c in r"\{}^"):
        return False
    if "_" not in s:
        return False
    if s.count("_") >= 2:
        return True
    base, rest = s.split("_", 1)
    if len(base) >= 3:
        return True
    # A class name: digits, underscore, 1–4 capital letters (`10_A`, `6_B`,
    # `12_PCM`). Math never writes a numeric base with a capital subscript.
    if base.isdigit() and rest.isalpha() and rest.isupper() and len(rest) <= 4:
        return True
    # `no_capture`, `ai_recreate`: a suffix that is a lowercase WORD (3+
    # letters, nothing else) is an enum, not a subscript (`v_avg` is the one
    # real-math casualty; `E_n`, `x_0`, `H_2O` keep their short suffixes).
    return len(rest) >= 3 and rest.isalpha() and rest.islower()


def _wrap_bare_scripts(text: str) -> str:
    if "^" not in text and "_" not in text:
        return text
    in_math_at = math_mask(text)

    def replace(m: re.Match[str]) -> str:
        if in_math_at[m.start()] or _looks_like_identifier(m.group(0)):
            return m.group(0)
        return f"${m.group(0)}$"

    return _BARE_SCRIPT_RE.sub(replace, text)


def _wrap_bare_latex_commands(text: str) -> str:
    if "\\" not in text or not _STRUCTURAL_CMD_RE.search(text):
        return text
    n = len(text)
    # What is math is what the renderers will typeset (`segment`), not `$`
    # parity: `$ $\text{H}_{2}$` has one literal dollar and one span, and
    # parity once wrapped the span a second time into `$$…$$`.
    mask = math_mask(text)
    out: list[str] = []
    i = 0
    while i < n:
        ch = text[i]
        if not mask[i] and ch == "\\":
            m = _STRUCTURAL_CMD_RE.match(text, i)
            if m:
                end = _find_command_extent(text, i)
                if "$" in text[i:end] or any(mask[i:end]):
                    out.append(ch)
                    i += 1
                    continue
                # A command that needs an argument but has none (`use \sqrt
                # here`) would become `$\sqrt$`, a parse error painted red;
                # left as prose it is at least readable and `audit` flags it.
                name = text[i + 1 : m.end()]
                if name in ARGUMENT_COMMANDS and end == m.end():
                    out.append(ch)
                    i += 1
                    continue
                # `\frac{x}` / `\tbinom{x}`: a two-argument command with one
                # argument fails in every renderer; leave it as prose.
                if (
                    name in _TWO_ARGUMENT_COMMANDS
                    and text[m.end() : end].count("{") < 2
                ):
                    out.append(ch)
                    i += 1
                    continue
                # A number right after (`\sqrt{2}3`) joins the span: a closing
                # `$` followed by a digit is not a closer.
                if end < n and "0" <= text[end] <= "9" and not mask[end]:
                    end = _NUMBER_AFTER_COMMAND_RE.match(text, end).end()  # type: ignore[union-attr]
                # A literal `$` right before or after (`$\frac{1}{2}` with no
                # closer): the author's delimiters are broken and a new span
                # would only make `$$`. Leave it as prose.
                if (i > 0 and text[i - 1] == "$" and not mask[i - 1]) or (
                    end < n and text[end] == "$" and not mask[end]
                ):
                    out.append(ch)
                    i += 1
                    continue
                out.append("$")
                out.append(text[i:end])
                out.append("$")
                if end < n and text[end].isdigit() and not mask[end]:
                    out.append(" ")
                i = end
                continue
        out.append(ch)
        i += 1
    return "".join(out)


_NUMBER_AFTER_COMMAND_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")


# ---------------------------------------------------------------------------
# `$ x^2 + 1 = 0 $`: a span whose content is padded with spaces
# ---------------------------------------------------------------------------

_PADDED_SPAN_HINT_RE = re.compile(r"\$[ \t]|[ \t]\$")
_STRONG_MATH_RE = re.compile(r"\\[A-Za-z]|[\^_]")
_WEAK_MATH_RE = re.compile(r"=")
_UNICODE_MATH_CHAR_RE = re.compile("[" + re.escape("".join(UNICODE_MATH)) + "]")


def _looks_like_padded_math(core: str) -> bool:
    """True when the content of a `$ … $` pair is a formula, not prose
    between two currency amounts (`$ 5 and got $`)."""
    strong = _STRONG_MATH_RE.search(core) or _UNICODE_MATH_CHAR_RE.search(core)
    if not strong:
        # `=` alone is enough unless the content starts like an amount.
        if not _WEAK_MATH_RE.search(core) or core[0].isdigit():
            return False
    # A command that needs an argument and has none (`$5 \text $`) cannot
    # render; as prose it at least stays readable.
    probe = "$" + core + "$"
    if _detect_command_missing_argument(probe) or _detect_frac_missing_args(probe):
        return False
    words = _TEXT_BRACE_RE.sub("", core)
    words = _ANY_LATEX_CMD_RE.sub("", words)
    if re.search(r"[A-Za-z]{4,}", words):
        return False
    return not any(w.lower() in _PROSE_STOPWORDS for w in _SHORT_WORD_RE.findall(words))


def _trim_padded_line(line: str) -> str:
    if "$$" in line:
        return line
    dollars = [
        k for k, c in enumerate(line) if c == "$" and not _dollar_escaped(line, k)
    ]
    if len(dollars) < 2 or len(dollars) % 2:
        return line  # unpaired: which dollar is currency is not ours to guess
    out: list[str] = []
    pos = 0
    for a, b in zip(dollars[0::2], dollars[1::2]):
        inner = line[a + 1 : b]
        core = inner.strip(" \t")
        if (
            not core
            or core == inner
            or not _looks_like_padded_math(core)
            # A dollar glued to a word or number outside the pair
            # (`$x = $y`, `wait$ … $now`) reads as currency or a typo.
            or (b + 1 < len(line) and line[b + 1].isalnum())
            or (a > 0 and line[a - 1].isalnum())
        ):
            continue
        out.append(line[pos:a])
        out.append("$" + core + "$")
        pos = b + 1
    out.append(line[pos:])
    return "".join(out)


def _trim_padded_spans(text: str) -> str:
    """``Solve $ x^2 + 1 = 0 $ now`` → ``Solve $x^2 + 1 = 0$ now``.

    The renderers do not open a span on ``$`` + space (pandoc rule), so a
    padded formula shows its dollars and the wrapping steps used to nest a
    second span inside it. In text segments only, dollars are paired in order
    on each line (a line with an odd count or a ``$$`` is left alone); a pair
    is trimmed when its padded content is math: a command, ``^``, ``_`` or a
    Unicode math character, or ``=`` when it does not start with a digit;
    neither dollar glued to a letter or digit outside the pair (``$x = $y``);
    no command missing its argument; and no prose (a 4+ letter word or a stop word outside ``\\text{}`` and command
    names). ``I paid $ 5 and got $ 3 back`` is currency and stays."""
    if "$" not in text or not _PADDED_SPAN_HINT_RE.search(text):
        return text
    out: list[str] = []
    for seg in segment(text):
        raw = seg["raw"]
        if seg["kind"] == "text" and raw.count("$") >= 2:
            raw = "\n".join(_trim_padded_line(line) for line in raw.split("\n"))
        out.append(raw)
    return "".join(out)


# ---------------------------------------------------------------------------
# `$\frac{1}{2$`: a closed span whose last group was never closed
# ---------------------------------------------------------------------------

_LEFT_CMD_RE = re.compile(r"\\left(?![A-Za-z])")
_RIGHT_CMD_RE = re.compile(r"\\right(?![A-Za-z])")
_TRAILING_CMD_RE = re.compile(r"\\([A-Za-z]+)\s*$")
# A group may not end right after these: the added `}` would leave them
# without their argument (`$\frac{1}{\sqrt$`, `$x^{2^$`).
_NEEDS_ARGUMENT = (
    frozenset(ARGUMENT_COMMANDS)
    | _TWO_ARGUMENT_COMMANDS
    | frozenset({"left", "right", "begin", "end", "sqrt", "cbrt"})
)


def _missing_closers(content: str) -> int:
    """How many ``}`` close ``content``, or 0 when it is balanced, has more
    ``}`` than ``{`` at any point, or when closing it would guess: the
    innermost open group is empty or ends in ``\\ ^ _ &`` or in a command
    that needs an argument. ``\\{`` / ``\\}`` do not count."""
    stack: list[int] = []
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            stack.append(i)
        elif ch == "}":
            if not stack:
                return 0
            stack.pop()
        i += 1
    if not stack:
        return 0
    inner = content[stack[-1] + 1 :].rstrip()
    if not inner or inner[-1] in "\\^_&{":
        return 0
    m = _TRAILING_CMD_RE.search(inner)
    if m and m.group(1) in _NEEDS_ARGUMENT:
        return 0
    return len(stack)


def _close_braces_in_line(line: str) -> str:
    dollars = [
        k
        for k, ch in enumerate(line)
        if ch == "$" and (len(line[:k]) - len(line[:k].rstrip("\\"))) % 2 == 0
    ]
    if len(dollars) < 2 or len(dollars) % 2:
        return line
    out: list[str] = []
    last = 0
    for a, b in zip(dollars[0::2], dollars[1::2]):
        content = line[a + 1 : b]
        if (
            not content
            or content[0].isspace()
            or content[-1].isspace()
            or (b + 1 < len(line) and line[b + 1].isdigit())
            or not _STRONG_MATH_RE.search(content)
        ):
            continue
        missing = _missing_closers(content)
        if not missing:
            continue
        if len(_LEFT_CMD_RE.findall(content)) != len(
            _RIGHT_CMD_RE.findall(content)
        ) or content.count("\\begin{") != content.count("\\end{"):
            continue
        fixed = content + "}" * missing
        probe = "$" + fixed + "$"
        if _detect_command_missing_argument(probe) or _detect_frac_missing_args(probe):
            continue
        segs = segment(probe)
        if len(segs) != 1 or segs[0]["kind"] != "math":
            continue
        out.append(line[last : a + 1])
        out.append(fixed)
        last = b
    if not out:
        return line
    out.append(line[last:])
    return "".join(out)


def _close_unbalanced_braces(text: str) -> str:
    """``$\\frac{1}{2$`` → ``$\\frac{1}{2}$``; ``$x^{2$`` → ``$x^{2}$``.

    A span whose last group was never closed is text to every renderer (the
    closer is found at brace depth 0 only), so the formula shows its source.
    In text segments only, line by line (a line with a ``$$`` or an odd
    count of unescaped ``$`` is left alone), dollars are paired in order. A
    pair gets the missing ``}`` appended to its content when all of: the
    content does not start or end with whitespace and the closer is not
    followed by a digit (the pandoc rules); it is math (a command, ``^`` or
    ``_``); it has more ``{`` than ``}`` and never more ``}`` than ``{``
    (``\\{`` / ``\\}`` do not count); the innermost open group is not empty
    and does not end in ``\\ ^ _ &`` or a command that needs an argument
    (``$\\frac{1}{$``, ``$x^{$`` stay: never guess an argument); ``\\left``
    and ``\\right``, ``\\begin{`` and ``\\end{`` are matched; and the result
    has no missing argument and is one span. Idempotent: a balanced span is
    never touched."""
    if "{" not in text or "$" not in text:
        return text
    out: list[str] = []
    for seg in segment(text):
        raw = seg["raw"]
        if seg["kind"] == "text" and "{" in raw and raw.count("$") >= 2:
            raw = "\n".join(
                line if "$$" in line else _close_braces_in_line(line)
                for line in raw.split("\n")
            )
        out.append(raw)
    return "".join(out)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

_ESCAPED_DOLLAR_SENTINEL = "\ue000DOLLAR_ESC\ue001"
_URL_RE = re.compile(r"^\s*(?:https?|gs|data|blob)://\S+\s*$", re.IGNORECASE)
_IMAGE_MARKER_RE = re.compile(r"\{\{IMAGE:[^}]+\}\}")
# `$` is excluded so a URL never swallows the math that follows it.
_EMBEDDED_URL_RE = re.compile(r"(?:https?|gs)://[^\s<>\"'$]+", re.IGNORECASE)
# Stash sentinels are made of private-use characters only: no letter, digit,
# `_` or brace, so no later step can read one as a script (`IMG_10` once
# became `IMG_{10}`). The index is encoded as characters U+E100 + n.
_STASH_OPEN = "\ue002"
_STASH_CLOSE = "\ue003"
_STASH_BASE = 0xE100


def _stash_token(idx: int) -> str:
    return _STASH_OPEN + chr(_STASH_BASE + idx) + _STASH_CLOSE


def canonicalize(text: Any) -> Any:
    """Normalize a fresh model string to the canonical form (spec §3)."""
    if not isinstance(text, str) or not text:
        return text
    if _URL_RE.match(text):
        return text

    image_stash: list[str] = []

    def _stash_image(m: re.Match[str]) -> str:
        image_stash.append(m.group(0))
        return _stash_token(len(image_stash) - 1)

    if "{{IMAGE:" in text:
        text = _IMAGE_MARKER_RE.sub(_stash_image, text)
    # A URL embedded in prose ("see https://…/a_b.png") is stashed the same
    # way: `_wrap_bare_scripts` would otherwise read `a_b` as a subscript.
    # (Backend only skipped whole-string URLs; this is the one widening.)
    if "://" in text:
        text = _EMBEDDED_URL_RE.sub(_stash_image, text)

    text = repair(text)
    text = _stash_escaped_dollars(text)
    text = _escape_currency(text)
    text = _stash_escaped_dollars(text)
    text = fix_mojibake_ftfy(text)
    text = normalize_homoglyphs(text)
    text = _collapse_double_backslashes(text)
    text = _fix_left_right_braces(text)
    text = _PAREN_INLINE_RE.sub(lambda m: f"${m.group(1)}$", text)
    text = _BRACKET_DISPLAY_RE.sub(lambda m: f"$${m.group(1)}$$", text)
    text = _trim_padded_spans(text)
    text = _close_unbalanced_braces(text)
    text = _normalize_braces(text)
    text = unicode_math_to_latex(text, inside_math_only=True)
    text = convert_combining_vec(text)
    text = wrap_bare_unicode_math(text)
    text = _wrap_bare_latex_commands(text)
    text = _wrap_bare_scripts(text)
    text = _wrap_pure_math_short_strings(text)
    # Step 14 left the symbols inside bare script / command argument groups
    # (`e^{iπ}`, `\frac{π}{2}`) to steps 15–17, which put the whole group in
    # one span. A group none of them took is prose; its symbols are wrapped
    # now, on their own, as step 14 would have.
    text = wrap_bare_unicode_math(text, skip_attached_groups=False)
    # The wrapping steps create new spans whose content the span-only steps
    # (brace normalisation, Unicode → LaTeX) have not seen: `\text{H₂O}`
    # became `$\text{H₂O}$` and only a second run produced
    # `$\text{H_{2}O}$`. Running those two steps once more makes one pass
    # equal to two.
    text = _normalize_braces(text)
    text = unicode_math_to_latex(text, inside_math_only=True)
    text = text.replace(_ESCAPED_DOLLAR_SENTINEL, r"\$")
    # Restore last-stashed first: a URL stashed after an image marker may
    # contain that marker's sentinel (`gs://{{IMAGE:x}}`).
    for idx in range(len(image_stash) - 1, -1, -1):
        text = text.replace(_stash_token(idx), image_stash[idx])
    return text


def canonicalize_deep(obj: Any, _key_hint: str = "") -> Any:
    """`canonicalize` over every content string in a JSON-like document.

    Skips non-content keys and URL-shaped values (CONTRACT §5); list items
    inherit the parent key. Coerces datetime/date to ISO-8601 and
    ``bson.ObjectId`` to str when bson is installed, so a Mongo document can
    be handed straight to a JSON response.
    """
    if isinstance(obj, str):
        if is_non_content_key(_key_hint) or is_url_or_path_string(obj):
            return obj
        return canonicalize(obj)
    if isinstance(obj, dict):
        return {k: canonicalize_deep(v, _key_hint=k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [canonicalize_deep(item, _key_hint=_key_hint) for item in obj]
    if isinstance(obj, datetime.datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=datetime.timezone.utc)
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    try:
        from bson import ObjectId  # type: ignore[import-untyped]

        if isinstance(obj, ObjectId):
            return str(obj)
    except ImportError:
        pass
    return obj
