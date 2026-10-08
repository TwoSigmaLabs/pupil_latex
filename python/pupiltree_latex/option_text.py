"""`normalize_option_text`: one answer option, as the apps should show it.

Backend `services/ai/utils.sanitize_option_text` (#1662, #1920, #1934): a
model often wraps a plain word in ``$\\text{…}$`` or puts a script or a
maths special inside ``\\text{}``, which text mode cannot hold. `fix` keeps
those as written (they are valid in some renderers and it never guesses at
prose); an option field is short and self-contained, so this function goes
one step further. Tag ``v140-b4``.
"""

from __future__ import annotations

import re
from typing import Any

from .fix import fix
from .segment import segment

# A plain `\text{…}` body: no maths specials, no braces, no dollar.
_PLAIN_BODY = r"[^{}\\$^_%&#]*"
_WHOLE_TEXT_SPAN_RE = re.compile(r"\\text\s*\{\s*(" + _PLAIN_BODY + r"?)\s*\}")
# An element sequence (`H`, `Na`, `NaCl`, `H2O`) is chemistry: kept.
_CHEMISTRY_BODY_RE = re.compile(r"(?:[A-Z][a-z]?[0-9]*){1,4}")
# A whole span of plain words (`$Coulomb$`): letters, spaces and light
# punctuation, with at least one word of four letters or more.
_PLAIN_WORDS_RE = re.compile(r"[A-Za-z][A-Za-z .,'\-]*")
_LONG_WORD_RE = re.compile(r"[A-Za-z][a-z]{3,}")

_TEXT_CMD_RE = re.compile(r"\\text\s*\{\s*([^{}]*?)\s*\}")
_NEEDS_MATHS_RE = re.compile(r"[\\^_%&#]")
_TEXT_WITH_SCRIPT_RE = re.compile(
    r"\\text\s*\{((?:[^{}]|\{[^{}]*\})*?[\^_]\{[^{}]*\}(?:[^{}]|\{[^{}]*\})*)\}"
)
_SCRIPT_GROUP_RE = re.compile(r"([\^_]\{[^{}]*\})")
_DOUBLE_SUPERSCRIPT_RE = re.compile(r"\^\{([^{}]*)\}\^\{([^{}]*)\}")


def _escape_specials(body: str) -> str:
    """``%`` ``&`` ``#`` not already escaped get a backslash (maths mode)."""
    out: list[str] = []
    for i, ch in enumerate(body):
        if ch in "%&#" and (i == 0 or body[i - 1] != "\\"):
            out.append("\\")
        out.append(ch)
    return "".join(out)


def _lift_text_scripts(m: re.Match[str]) -> str:
    """``\\text{H_{2}O}`` → ``\\text{H}_{2}\\text{O}``; ``\\text{ m^{2}}`` →
    ``\\text{ m}^{2}``; ``^{-}^{1}`` merges into ``^{-1}``."""
    pieces: list[str] = []
    for run in _SCRIPT_GROUP_RE.split(m.group(1)):
        if _SCRIPT_GROUP_RE.fullmatch(run):
            pieces.append(run)
        elif run.strip():
            pieces.append("\\text{" + run + "}")
    lifted = "".join(pieces)
    while _DOUBLE_SUPERSCRIPT_RE.search(lifted):
        lifted = _DOUBLE_SUPERSCRIPT_RE.sub(r"^{\1\2}", lifted)
    return lifted


def _unwrap_maths_body(m: re.Match[str]) -> str:
    """``\\text{ %}`` → ``\\%``, ``\\text{ \\Omega}`` → ``\\Omega``: a text
    group whose body needs maths mode is unwrapped in place."""
    body = m.group(1)
    if not _NEEDS_MATHS_RE.search(body):
        return m.group(0)
    start = m.start()
    before = m.string[start - 1] if start else " "
    return ("" if before.isspace() else " ") + _escape_specials(body)


def _math_body(body: str) -> str:
    if "\\text" not in body:
        return body
    body = _TEXT_WITH_SCRIPT_RE.sub(_lift_text_scripts, body)
    return _TEXT_CMD_RE.sub(_unwrap_maths_body, body)


def _plain_text_group(m: re.Match[str]) -> str:
    end = m.end()
    nxt = m.string[end] if end < len(m.string) else ""
    if nxt in ("_", "^"):
        return m.group(0)
    return m.group(1)


def _text_body(raw: str) -> str:
    if "\\text" in raw:
        raw = _WHOLE_TEXT_SPAN_RE.sub(_plain_text_group, raw)
    return raw.replace("\\{", "{").replace("\\}", "}")


def _span_word(value: str) -> str | None:
    """The words of a span that is only ``\\text{plain words}``
    (``$\\text{rises}$``), or None. An element sequence (``\\text{NaCl}``)
    is chemistry and stays."""
    m = _WHOLE_TEXT_SPAN_RE.fullmatch(value.strip())
    if not m:
        return None
    word = m.group(1)
    if (
        word
        and any(c.isalpha() for c in word)
        and not _CHEMISTRY_BODY_RE.fullmatch(word)
    ):
        return word
    return None


def _whole_span_word(text: str) -> str | None:
    """The plain word(s) of an option that is one inline span and nothing
    else (``$\\text{Coulomb}$``, ``$Coulomb$``), or None."""
    core = text.strip()
    segs = segment(core)
    if len(segs) != 1 or segs[0]["kind"] != "math" or segs[0]["display"]:
        return None
    if not segs[0]["raw"].startswith("$"):
        return None
    body = segs[0]["value"].strip()
    if _WHOLE_TEXT_SPAN_RE.fullmatch(body):
        return _span_word(body)
    if _PLAIN_WORDS_RE.fullmatch(body) and _LONG_WORD_RE.search(body):
        return body.strip()
    return None


def normalize_option_text(text: Any, *, chemistry: bool = True) -> Any:
    """`fix`, then the option-field clean-ups (tag ``v140-b4``):

    - an option that is one span of plain words loses the span:
      ``$\\text{Coulomb}$`` → ``Coulomb``, ``$Coulomb$`` → ``Coulomb``
      (an element sequence such as ``$\\text{NaCl}$`` and a single letter
      ``$x$`` stay);
    - outside maths, ``\\text{word}`` → ``word`` (not before ``_``/``^``)
      and ``\\{`` / ``\\}`` → ``{`` / ``}``;
    - inside maths, scripts move out of ``\\text{}`` (``$\\text{H_{2}O}$`` →
      ``$\\text{H}_{2}\\text{O}$``, ``$5 \\text{ m^{2}}$`` →
      ``$5 \\text{ m}^{2}$``) and a ``\\text{}`` whose body needs maths mode
      is unwrapped (``$50 \\text{ %}$`` → ``$50 \\%$``,
      ``$5 \\text{ \\Omega}$`` → ``$5 \\Omega$``).

    Idempotent; non-strings pass through."""
    if not isinstance(text, str) or not text:
        return text
    text = fix(text, chemistry=chemistry)
    word = _whole_span_word(text)
    if word is not None:
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        return lead + word + trail
    out: list[str] = []
    for seg in segment(text):
        raw = seg["raw"]
        if seg["kind"] == "math" and raw.startswith("$"):
            k = 2 if raw.startswith("$$") else 1
            word = _span_word(seg["value"]) if k == 1 else None
            if word is not None:
                raw = word
            else:
                body = raw[k : len(raw) - k]
                raw = raw[:k] + _math_body(body) + raw[len(raw) - k :]
        elif seg["kind"] == "text":
            raw = _text_body(raw)
        out.append(raw)
    return "".join(out)


__all__ = ["normalize_option_text"]
