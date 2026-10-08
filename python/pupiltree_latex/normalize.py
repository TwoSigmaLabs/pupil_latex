"""`normalize`: display-safe, content-preserving preparation for a renderer.

Ported from script_editor `latex_preprocess.dart` (#420, #421). The order is
load-bearing: delimiters are normalised BEFORE prose escapes are decoded, so
a `\\theta` still sitting inside `\\(…\\)` is recognised as math and not
turned into a TAB plus "heta" (the B5 bug, script_editor #420 and tutor
#383). Nothing here wraps text in `$`, converts Unicode or touches URLs.
"""

from __future__ import annotations

import re
from typing import Any

from .audit import _detect_command_missing_argument, _detect_frac_missing_args
from .commands import PROSE_ESCAPE_COMMANDS
from .mojibake import fix_mojibake_table
from .repair import repair
from .segment import segment

# ---------------------------------------------------------------------------
# 3. delimiters
# ---------------------------------------------------------------------------

# `(?<!\\)` so a LaTeX line break `\\[2pt]` inside a display block is not
# mistaken for an opening `\[`, and `\\)` (an escaped backslash then a
# parenthesis) is not a closer.
_DISPLAY_BRACKET_RE = re.compile(r"(?<!\\)\\\[([\s\S]+?)(?<!\\)\\\]")
_INLINE_PAREN_RE = re.compile(r"(?<!\\)\\\(([\s\S]+?)(?<!\\)\\\)")
_INNER_NEWLINE_RE = re.compile(r"\s*\n\s*")


def normalize_delimiters(text: str) -> str:
    """``\\(…\\)`` → ``$…$`` and ``\\[…\\]`` → ``$$…$$``.

    Newlines inside an inline span collapse to one space: no inline matcher
    (gpt_markdown, remark-math, this package's `segment`) crosses lines.
    """
    if "\\(" not in text and "\\[" not in text:
        return text
    text = _DISPLAY_BRACKET_RE.sub(lambda m: "$$" + m.group(1) + "$$", text)
    text = _INLINE_PAREN_RE.sub(
        lambda m: "$" + _INNER_NEWLINE_RE.sub(" ", m.group(1)).strip() + "$", text
    )
    return text


# ---------------------------------------------------------------------------
# 4. orphan delimiters
# ---------------------------------------------------------------------------

_ORPHAN_DELIMITER_RE = re.compile(r"(?<!\\)\\[()\[\]]")


def strip_orphan_delimiters(text: str) -> str:
    """Remove any ``\\(`` ``\\)`` ``\\[`` ``\\]`` left after
    `normalize_delimiters`; by construction they have no partner. Leaving one
    would make gpt_markdown skip every ``$…$`` in the field."""
    if (
        "\\(" not in text
        and "\\)" not in text
        and "\\[" not in text
        and "\\]" not in text
    ):
        return text
    return _ORPHAN_DELIMITER_RE.sub("", text)


# ---------------------------------------------------------------------------
# 5. currency
# ---------------------------------------------------------------------------


def _is_digit(s: str, i: int) -> bool:
    return 0 <= i < len(s) and "0" <= s[i] <= "9"


def _is_space(s: str, i: int) -> bool:
    return 0 <= i < len(s) and s[i] in " \t"


def _is_escaped(s: str, i: int) -> bool:
    return i > 0 and s[i - 1] == "\\"


_FORMULA_CHARS_RE = re.compile(r"[0-9A-Za-z+\-*/=<>().,^_ \t]+")
_FORMULA_OPERATOR_RE = re.compile(r"[+\-*/=<>^_]")
_FORMULA_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_TWO_LETTERS_RE = re.compile(r"[A-Za-z]{2,}")


def is_formula(content: str) -> bool:
    """True when the content of `$<digit>… $` (space before the closer) is
    clearly a formula, not prose between two amounts: after removing command
    names it is only digits, letters, operators, brackets and spaces, has an
    operator and a letter or command, and no two letters in a row (no word).
    `2x + 3`, `3x^2 - 1`, `5\\times 2 = 10` are formulas; `5 and x`, `10, `
    are not."""
    core = content.rstrip(" \t")
    if not core:
        return False
    has_command = bool(_FORMULA_COMMAND_RE.search(core))
    bare = _FORMULA_COMMAND_RE.sub(" ", core)
    if not _FORMULA_CHARS_RE.fullmatch(bare) or _TWO_LETTERS_RE.search(bare):
        return False
    if not _FORMULA_OPERATOR_RE.search(bare) and not has_command:
        return False
    if not (has_command or any(c.isalpha() for c in bare)):
        return False
    # A command that needs an argument and has none (`$5 \text $`) cannot
    # render: as currency it at least stays readable.
    probe = "$" + core + "$"
    return not (
        _detect_command_missing_argument(probe) or _detect_frac_missing_args(probe)
    )


def _currency_positions_in_line(line: str) -> list[int]:
    """Indices of the currency dollars in one line (the `$` that
    `escape_currency` turns into `\\$`)."""
    found: list[int] = []
    if "$" not in line:
        return found
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch != "$" or _is_escaped(line, i):
            i += 1
            continue
        # `$$` display block: copy through to its closing `$$` (or end of line).
        if i + 1 < n and line[i + 1] == "$":
            close = line.find("$$", i + 2)
            i = n if close == -1 else close + 2
            continue
        if not _is_digit(line, i + 1):
            # A math opener: skip the whole span through to its first closer
            # (the tokenizer's rule) so the closer is never re-examined as a
            # currency opener (`$\\sqrt$2` must not become `$\\sqrt\\$2`).
            j = i + 1
            while j < n and not (line[j] == "$" and not _is_escaped(line, j)):
                j += 1
            i = j + 1 if j < n else i + 1
            continue
        # `$<digit>`: currency unless the next single `$` is a valid closer.
        j = i + 1
        closer_valid = False
        while j < n:
            if line[j] == "$" and not _is_escaped(line, j):
                # A `$` right after the closer is the NEXT span's opener
                # (`$1$$\\gamma$`), not a display delimiter: only whitespace
                # before and a digit after invalidate a closer.
                closer_valid = (
                    not _is_digit(line, j + 1)
                    and (
                        not _is_space(line, j - 1)
                        # `Compute $2x + 3 $.`: the renderers pair a closer after
                        # a space, so a formula keeps its dollars.
                        or is_formula(line[i + 1 : j])
                    )
                )
                break
            j += 1
        if closer_valid:
            i = j + 1
        else:
            found.append(i)
            i += 1
    return found


def currency_positions(text: str) -> list[int]:
    """Indices of the dollars `escape_currency` reads as money (pandoc's
    closer rule, per line). `to_plain` uses it to keep amounts."""
    found: list[int] = []
    if "$" not in text:
        return found
    base = 0
    for line in text.split("\n"):
        found.extend(base + k for k in _currency_positions_in_line(line))
        base += len(line) + 1
    return found


def _escape_currency_in_line(line: str) -> str:
    positions = _currency_positions_in_line(line)
    if not positions:
        return line
    out: list[str] = []
    pos = 0
    for k in positions:
        out.append(line[pos:k])
        out.append("\\$")
        pos = k + 1
    out.append(line[pos:])
    return "".join(out)


def escape_currency(text: str) -> str:
    """A ``$`` that is money becomes ``\\$`` (pandoc's closer rule, per line).

    ``$5000 and $\\frac14$`` → ``\\$5000 and $\\frac14$``; ``$5-$10`` →
    ``\\$5-\\$10``; ``costs $5.`` → ``costs \\$5.``; ``$2x + 3$`` unchanged.
    """
    if "$" not in text:
        return text
    return "\n".join(_escape_currency_in_line(line) for line in text.split("\n"))


# ---------------------------------------------------------------------------
# 5a. padded spans
# ---------------------------------------------------------------------------


def trim_padded_spans(text: str) -> str:
    """``Solve $ x + 1 = 0 $`` → ``Solve $x + 1 = 0$`` (tag ``audit6-1``).

    The same rule `canonicalize` applies (pairs per line; content clearly
    math; neither dollar glued to a letter or digit outside the pair, so a
    closer followed by a digit stays). Run after `escape_currency`: an
    escaped amount is never paired. `segment` keeps pandoc's rule (no
    whitespace inside the delimiters), so without this a stored padded
    formula displays as raw text."""
    # Imported here: `canonicalize` imports this module (`is_formula`).
    from .canonicalize import _trim_padded_spans

    return _trim_padded_spans(text)


_CURRENCY_MASK = "\ue000"  # U+E000 (private use): never in content


def trim_padded_spans_keep_currency(text: str) -> str:
    """`trim_padded_spans` on text whose amounts are not escaped (`to_plain`
    input): the dollars `currency_positions` reads as money are masked first,
    so they are never paired (``Rs $5 and $10 for $ x^2 $`` → only the last
    pair is trimmed)."""
    if "$" not in text or _CURRENCY_MASK in text:
        return text
    money = currency_positions(text)
    if money:
        chars = list(text)
        for k in money:
            chars[k] = _CURRENCY_MASK
        text = "".join(chars)
    return trim_padded_spans(text).replace(_CURRENCY_MASK, "$")


# ---------------------------------------------------------------------------
# 6. prose escapes
# ---------------------------------------------------------------------------

# A whole math span. Inline content may contain `\$` but no bare `$` and no
# newline — the shape every inline matcher accepts.
_MATH_SPAN_RE = re.compile(r"\$\$[\s\S]*?\$\$|(?<!\\)\$(?:\\.|[^$\n\\])+\$")
_PROSE_ESCAPE_RE = re.compile(r"\\r\\n|\\[nrt]")
_COMMAND_NAME_RE = re.compile(r"\\([A-Za-z]+)")


# A lesson-script label is a lowercase word: `\teacher:`, `\type:`. A
# capitalised word after `\n` (`Host: Priya\nGuest: Vikram`) is a line break
# followed by a name.
_SCRIPT_LABEL_RE = re.compile(r"\\[a-z][a-z_]*:")


def _decode_prose_escapes(prose: str) -> str:
    def replace(m: re.Match[str]) -> str:
        name = _COMMAND_NAME_RE.match(prose, m.start())
        # Same vocabulary as the JSON transport: outside math `\nu`, `\ne`,
        # `\ni`, `\not` are line breaks (production prose proved it).
        if name and name.group(1) in PROSE_ESCAPE_COMMANDS:
            return m.group(0)
        # A lesson-script label (`\teacher:`, `\type:`, `\read:`) is never an
        # escape, whatever the word.
        if _SCRIPT_LABEL_RE.match(prose, m.start()):
            return m.group(0)
        return "\t" if m.group(0) == "\\t" else "\n"

    return _PROSE_ESCAPE_RE.sub(replace, prose)


def decode_escapes_outside_math(text: str) -> str:
    """Literal two-character ``\\n`` / ``\\r\\n`` / ``\\r`` / ``\\t`` in prose
    become real whitespace. Math spans are left intact, and a known command
    (``\\theta``, ``\\neq``, ``\\text{…}``, ``\\right``) is never touched."""
    if "\\" not in text:
        return text
    # Protected: every `segment` math span (what the renderers typeset; tag
    # `audit5-8`: in `a $ $\\nu$ b` the regex pairs `$ $` and used to decode
    # the `\\nu` that `segment` renders) and every regex span (a padded
    # `$ x \\ne y $5` that `trim_padded_spans` left). Decoding is lossy, so
    # a position either reader calls math is kept.
    n = len(text)
    protected = bytearray(n)
    for m in _MATH_SPAN_RE.finditer(text):
        protected[m.start() : m.end()] = b"\x01" * (m.end() - m.start())
    pos = 0
    for seg in segment(text):
        end = pos + len(seg["raw"])
        if seg["kind"] == "math":
            protected[pos:end] = b"\x01" * (end - pos)
        pos = end
    out: list[str] = []
    k = 0
    while k < n:
        j = k
        flag = protected[k]
        while j < n and protected[j] == flag:
            j += 1
        out.append(text[k:j] if flag else _decode_prose_escapes(text[k:j]))
        k = j
    return "".join(out)


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


def normalize(text: Any) -> Any:
    """repair → mojibake table → delimiters → orphans → currency → padded
    spans → escapes.

    Idempotent, content-preserving. Non-strings are returned unchanged.
    """
    if not isinstance(text, str) or not text:
        return text
    text = repair(text)
    text = fix_mojibake_table(text)
    text = normalize_delimiters(text)
    text = strip_orphan_delimiters(text)
    text = escape_currency(text)
    text = trim_padded_spans(text)
    text = decode_escapes_outside_math(text)
    return text
