"""Decode model JSON without turning its LaTeX into control characters.

``json.loads`` accepts a single-backslash ``\\frac`` as the JSON escape form
feed + ``rac`` and returns the corrupted string without raising (Backend
#1651, #1654; agents #516, #531). `escape_latex_for_json` doubles the
backslashes that are LaTeX before the parser sees them.

Where a string value is "in math" is decided with the same tokenizer every
renderer uses (`segment`), not by `$` parity, so an unpaired currency dollar
(``"$5000 gives $\\frac{1}{4}$ … $\\nu$"``) no longer flips the decision for
the rest of the value.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .commands import JSON_WHITESPACE_COLLISION_COMMANDS, PROSE_ESCAPE_COMMANDS
from .segment import segment

_ALPHA_RUN_RE = re.compile(r"[A-Za-z]+")


def _spells_latex_command(json_text: str, pos: int, in_math: bool) -> bool:
    """True if the letters starting at ``pos`` form a command.

    Inside math the whole KaTeX vocabulary decides (``\\nu`` is LaTeX, a run
    that is no command such as ``\\nnext`` is a newline). Outside math the
    same vocabulary decides except for the four names that production prose
    proved to be line breaks.
    """
    m = _ALPHA_RUN_RE.match(json_text, pos)
    if not m:
        return False
    # A lesson-script label (`\teacher:`, `\type:`, `\read:`) is never an escape.
    if m.end() < len(json_text) and json_text[m.end()] == ":" and m.group(0).islower():
        return True
    vocabulary = (
        JSON_WHITESPACE_COLLISION_COMMANDS if in_math else PROSE_ESCAPE_COMMANDS
    )
    return m.group(0) in vocabulary


def _is_escaped(s: str, pos: int) -> bool:
    count = 0
    p = pos - 1
    while p >= 0 and s[p] == "\\":
        count += 1
        p -= 1
    return count % 2 == 1


def _string_end(json_text: str, start: int) -> int:
    """Index of the closing quote of the JSON string opened at ``start``
    (or ``len(json_text)`` when unterminated)."""
    i = start + 1
    n = len(json_text)
    while i < n:
        c = json_text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i
        i += 1
    return n


def _math_mask(body: str) -> list[bool]:
    """``mask[i]`` is True when ``body[i]`` lies inside a math span, using
    `segment` on the raw (still JSON-escaped) body: `$` positions are the
    same in either form, and `segment` already handles ``\\$``."""
    mask = [False] * len(body)
    pos = 0
    for seg in segment(body):
        length = len(seg["raw"])
        if seg["kind"] == "math":
            for k in range(pos, pos + length):
                mask[k] = True
        pos += length
    return mask


def escape_latex_for_json(json_text: str) -> str:
    """Escape LaTeX backslash sequences inside JSON string values.

    Inside a string value:
      - ``\\"``, ``\\\\``, ``\\/``, ``\\uXXXX`` are kept;
      - ``\\n`` ``\\t`` ``\\r`` stay JSON escapes unless the letters after
        the backslash spell a command (see `_spells_latex_command`);
      - ``\\b`` and ``\\f`` are ALWAYS LaTeX (backspace and form feed never
        occur in lesson text);
      - any other backslash (letter, digit, space, brace, …) is doubled:
        none of those is a JSON escape, so keeping it would make the
        parser raise.
    """
    out: list[str] = []
    i = 0
    n = len(json_text)
    while i < n:
        c = json_text[i]
        if c != '"':
            out.append(c)
            i += 1
            continue
        # A string value: copy the opening quote, then walk the body with a
        # precomputed math mask.
        end = _string_end(json_text, i)
        body = json_text[i + 1 : end]
        mask = _math_mask(body)
        out.append('"')
        j = 0
        m = len(body)
        while j < m:
            b = body[j]
            if b != "\\":
                out.append(b)
                j += 1
                continue
            next_c = body[j + 1] if j + 1 < m else ""
            if next_c in ('"', "\\", "/"):
                out.append(b)
                out.append(next_c)
                j += 2
                continue
            if (
                next_c == "u"
                and j + 5 < m
                and all(ch in "0123456789abcdefABCDEF" for ch in body[j + 2 : j + 6])
            ):
                out.append(body[j : j + 6])
                j += 6
                continue
            in_math = mask[j] if j < m else False
            if next_c in ("n", "t", "r") and not _spells_latex_command(
                body, j + 1, in_math
            ):
                out.append(b)
                out.append(next_c)
                j += 2
                continue
            # Every other backslash is LaTeX (`\ ` is a spacing command, `\1`
            # a macro argument, `\{` a brace); neither is a JSON escape, so
            # leaving them would make the parser raise.
            out.append("\\\\")
            j += 1
        if end < n:
            out.append('"')
        i = end + 1
    return "".join(out)


def loads_latex_aware(json_text: str, *, strict: bool = False) -> Any:
    """``json.loads`` for model output that may carry single-backslash LaTeX.

    ``strict=False`` by default: models emit raw newlines and tabs inside
    string values, and those are content, not errors. Falls back to the plain
    decode and raises what that raises.
    """
    try:
        return json.loads(escape_latex_for_json(json_text), strict=strict)
    except json.JSONDecodeError:
        return json.loads(json_text, strict=strict)


def loads_model_json(json_text: str) -> Any:
    """Transport-only decode: escape, then ``json.loads(strict=False)``. No
    fallback, no sanitiser — invalid JSON raises."""
    return json.loads(escape_latex_for_json(json_text), strict=False)
