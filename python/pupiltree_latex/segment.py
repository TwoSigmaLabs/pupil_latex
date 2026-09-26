"""`segment`: the one tokenizer every renderer uses.

Splits a string into prose and math segments. Escape-aware (`\\$` is a
literal dollar, `\\\\$x$` opens math), brace-aware (the KaTeX auto-render
walk: a backslash skips the next character, `{`/`}` nest), and
currency-aware for inline `$…$` (pandoc's rule: content must not start with
whitespace or span a line, the closer must not be followed by a digit).
Unlike pandoc, an inline span never runs past a rejected closer — the first
candidate closer decides — so `$60 and $x^2$` keeps `$60` literal and
renders `$x^2$`.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


class Segment(TypedDict):
    kind: str  # "text" | "math"
    display: bool
    value: str
    raw: str


def _escaped(s: str, i: int) -> bool:
    """True when an odd number of backslashes immediately precedes ``i``."""
    count = 0
    p = i - 1
    while p >= 0 and s[p] == "\\":
        count += 1
        p -= 1
    return count % 2 == 1


def _find_end(delim: str, s: str, start: int) -> int:
    """KaTeX auto-render's findEndOfMath: index of the closing delimiter at
    brace depth ≤ 0, or -1."""
    idx = start
    depth = 0
    n = len(s)
    while idx < n:
        if depth <= 0 and s.startswith(delim, idx):
            return idx
        ch = s[idx]
        if ch == "\\":
            idx += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        idx += 1
    return -1


def segment(text: Any) -> list[Segment]:
    """Split ``text`` into ``{"kind", "display", "value", "raw"}`` segments.

    Delimiter priority at each position: ``$$``, ``\\[``, ``$``, ``\\(``.
    Text ``value`` has ``\\$`` unescaped to ``$``; ``raw`` is the exact source
    slice. Math ``value`` is the inner content (``\\(…\\)`` trimmed).
    Non-strings and the empty string yield ``[]``.
    """
    if not isinstance(text, str) or not text:
        return []
    s = text
    n = len(s)
    out: list[Segment] = []
    text_raw: list[str] = []
    text_val: list[str] = []

    def flush() -> None:
        if text_raw:
            out.append(
                Segment(
                    kind="text",
                    display=False,
                    value="".join(text_val),
                    raw="".join(text_raw),
                )
            )
            text_raw.clear()
            text_val.clear()

    def push_math(raw: str, value: str, display: bool) -> None:
        flush()
        out.append(Segment(kind="math", display=display, value=value, raw=raw))

    i = 0
    while i < n:
        ch = s[i]
        if ch == "\\":
            if _escaped(s, i):
                text_raw.append(ch)
                text_val.append(ch)
                i += 1
                continue
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt == "$":
                text_raw.append("\\$")
                text_val.append("$")
                i += 2
                continue
            if nxt == "[":
                end = _find_end("\\]", s, i + 2)
                if end != -1:
                    push_math(s[i : end + 2], s[i + 2 : end], True)
                    i = end + 2
                    continue
            if nxt == "(":
                end = _find_end("\\)", s, i + 2)
                if end != -1:
                    push_math(s[i : end + 2], s[i + 2 : end].strip(), False)
                    i = end + 2
                    continue
            text_raw.append(ch)
            text_val.append(ch)
            i += 1
            continue
        if ch == "$":
            if s.startswith("$$", i):
                end = _find_end("$$", s, i + 2)
                if end > i + 2:
                    push_math(s[i : end + 2], s[i + 2 : end], True)
                    i = end + 2
                    continue
            elif i + 1 < n and not s[i + 1].isspace():
                end = _find_end("$", s, i + 1)
                if end != -1:
                    content = s[i + 1 : end]
                    closer_ok = not s[end - 1].isspace() and (
                        end + 1 >= n or not s[end + 1].isdigit()
                    )
                    if content and "\n" not in content and closer_ok:
                        push_math(s[i : end + 1], content, False)
                        i = end + 1
                        continue
            text_raw.append("$")
            text_val.append("$")
            i += 1
            continue
        text_raw.append(ch)
        text_val.append(ch)
        i += 1
    flush()
    return out


_COMMAND_RE = re.compile(r"\\[A-Za-z]")


def contains_math(text: Any) -> bool:
    """True when the text has a math segment or a backslash command."""
    if not isinstance(text, str) or not text:
        return False
    if _COMMAND_RE.search(text):
        return True
    return any(seg["kind"] == "math" for seg in segment(text))


# Anything that markdown or LaTeX would interpret. Mirrors script_editor's
# `ScriptEditorTex._markdownSyntaxRx` (the plain-prose fast path added in
# #428 after a 7.58 s ANR on 30 cards × 7 fields).
_NOT_PLAIN_RE = re.compile(
    r"[\\$*~`|\[\]<>#\r⸻【]"  # markup characters, ⸻, 【
    r"|\n\n"  # blank line
    r"|--"  # rule / em-dash marker
    r"|(?:^|\n)[ \t]+\S"  # leading indentation
    r"|(?:^|\n)(?:[-*+] |\d+[.)] )"  # list marker
)


def is_plain_prose(text: Any) -> bool:
    """Renderer fast path: True when the text can be shown as plain text."""
    if not isinstance(text, str):
        return False
    return _NOT_PLAIN_RE.search(text) is None
