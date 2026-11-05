"""`repair`: undo JSON-escape damage to LaTeX commands, drop other C0 bytes.

A parser that reads `\\frac` as the JSON escape `\\f` stores form feed +
"rac"; `\\times` becomes TAB + "imes". Production held thousands of these
(Backend #1564, #1651, #1654; agents #343, #516, #531; Fillers #274, #293;
script_editor #420). This is the one function that is safe on ANY content:
every DB write sink, every read path and every client runs it.
"""

from __future__ import annotations

import re
from typing import Any

from .commands import (
    JSON_WHITESPACE_COLLISION_COMMANDS,
    KATEX_COMMANDS,
    LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
    SCRIPT_LABELS,
)

_WHITESPACE_LETTER = {"\x09": "t", "\x0a": "n", "\x0d": "r"}
_WHITESPACE_AS_SPACE = {0x09: 0x20, 0x0A: 0x20, 0x0D: 0x20}


def _only_command_reading(run: str) -> str:
    """The one letter in n/t/r for which ``letter + run`` is a KaTeX command,
    or "" when none or more than one fits (`ightarrow` → "r")."""
    fits = [c for c in "ntr" if (c + run) in JSON_WHITESPACE_COLLISION_COMMANDS]
    return fits[0] if len(fits) == 1 else ""


_ALPHA_RUN_RE = re.compile(r"[A-Za-z]+")
# Every C0 control except TAB, LF, CR — plus DEL.
_OTHER_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ANY_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
# A whole ANSI CSI sequence (terminal colour/bold codes copied from a log):
# ESC `[`, parameter bytes, intermediate bytes, one final byte. Removing only
# the ESC left `[1mRecall Prompt 1:[0m` behind.
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def repair(text: Any, guess_whitespace: bool = True) -> Any:
    """Restore control characters that were LaTeX commands; drop the rest.

    - U+0008 → ``\\b`` and U+000C → ``\\f`` when a letter follows.
    - U+000B → ``\\v`` when ``v`` + the following letters is a KaTeX command.
    - TAB / LF / CR → ``\\t`` / ``\\n`` / ``\\r`` only when ``guess_whitespace``
      and the following letters spell a command in
      `LATEX_COMMANDS_BEHIND_JSON_ESCAPES`; otherwise they are kept.
    - An ANSI CSI sequence (``ESC [ … m``) is removed whole.
    - Any other C0 control and DEL is removed.

    ``guess_whitespace=False`` is the read-path form (Backend #1595): stored
    bytes are served with only the two unconditional repairs applied.
    Idempotent; non-strings are returned unchanged.
    """
    if not isinstance(text, str) or not text:
        return text
    if not _ANY_CONTROL_RE.search(text):
        return text
    if "\x1b[" in text:
        text = _ANSI_CSI_RE.sub("", text)
    out: list[str] = []
    n = len(text)
    dollars: list[int] | None = None  # positions of unescaped `$`, on demand

    def _in_closed_span(pos: int) -> bool:
        """An odd number of unescaped `$` before ``pos`` and one after it:
                the corrupted span `$x <LF>ightarrow y$` still counts (the newline
                is the very damage), an unterminated `$
        o` does not."""
        nonlocal dollars
        if dollars is None:
            # Currency-aware (tag `v140-b7`): a dollar that `normalize` reads
            # as money is no span delimiter, so `costs $5.<LF>angle … $10`
            # keeps its line break. The damaged whitespace is read as a
            # space for this, so a span cut by it still pairs.
            from .normalize import currency_positions  # normalize imports repair

            money = set(currency_positions(text.translate(_WHITESPACE_AS_SPACE)))
            dollars = [
                k
                for k, c in enumerate(text)
                if c == "$" and (k == 0 or text[k - 1] != "\\") and k not in money
            ]
        before = sum(1 for k in dollars if k < pos)
        return before % 2 == 1 and any(k > pos for k in dollars)

    i = 0
    while i < n:
        ch = text[i]
        if ch in ("\x08", "\x0c"):
            # Restored only when a letter follows: a bare form feed has no
            # command to go back to and is dropped with the other C0 bytes
            # (script_editor #420 rule; Backend restored unconditionally).
            if i + 1 < n and text[i + 1].isalpha():
                out.append("\\b" if ch == "\x08" else "\\f")
            else:
                out.append(ch)
        elif ch == "\x0b":
            m = _ALPHA_RUN_RE.match(text, i + 1)
            if m and ("v" + m.group(0)) in KATEX_COMMANDS:
                out.append("\\v")
            # else: dropped by the final strip
            else:
                out.append(ch)
        elif ch in _WHITESPACE_LETTER and guess_whitespace:
            letter = _WHITESPACE_LETTER[ch]
            m = _ALPHA_RUN_RE.match(text, i + 1)
            run = m.group(0) if m else ""
            if run and (letter + run) in LATEX_COMMANDS_BEHIND_JSON_ESCAPES:
                out.append("\\" + letter)
            elif (
                run
                and m.end() < n
                and text[m.end()] == ":"
                and (letter + run) in SCRIPT_LABELS
            ):
                # `<TAB>eacher:` / `<LF>ead:` — a decoded lesson-script label.
                out.append("\\" + letter)
            elif (
                run
                and len(run) >= 3
                and _in_closed_span(i)
                and _only_command_reading(run)
            ):
                # Inside a CLOSED `$…$` span a raw newline/tab is never
                # content: `$<LF>ightarrow$` can only have been `\rightarrow`.
                # Three letters minimum, as for the audit: `$<LF>o` is not `\to`.
                out.append("\\" + _only_command_reading(run))
            else:
                out.append(ch)
        else:
            out.append(ch)
        i += 1
    return _OTHER_CONTROL_RE.sub("", "".join(out))


def repair_deep(obj: Any, guess_whitespace: bool = True) -> Any:
    """`repair` over every string in a JSON-like document. No key skipping is
    needed: the repair cannot damage an id, a URL or a timestamp."""
    if isinstance(obj, str):
        return repair(obj, guess_whitespace)
    if isinstance(obj, dict):
        return {k: repair_deep(v, guess_whitespace) for k, v in obj.items()}
    if isinstance(obj, list):
        return [repair_deep(v, guess_whitespace) for v in obj]
    return obj
