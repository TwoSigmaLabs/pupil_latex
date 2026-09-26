"""`audit`: detect raw or mangled LaTeX. Read-only, pure.

Backend `services/ai/helper/latex_audit.py` (the eight production
signatures found the week of 2026-09-07) plus the four log-only checks from
Backend `validate_latex_text`, expressed as finding kinds. Precision over
recall: a finding may page someone, so each detector prefers to miss an
ambiguous case rather than flag a legitimate one.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from .commands import (
    ARGUMENT_COMMANDS,
    AUDIT_EXTRA_ALLOWED_COMMANDS,
    JSON_WHITESPACE_COLLISION_COMMANDS,
    KATEX_COMMANDS,
    LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
    UNSUPPORTED_COMMANDS,
)
from .spans import math_mask, math_ranges
from .walk import is_non_content_key, is_not_rendered_key, is_url_or_path_string

KIND_CONTROL_CHAR = "control_char"
KIND_LEGACY_DELIMITER = "legacy_delimiter"
KIND_UNBALANCED_DOLLAR = "unbalanced_dollar"
KIND_COMMAND_MISSING_ARGUMENT = "command_missing_argument"
KIND_FRAC_MISSING_ARGS = "frac_missing_args"
KIND_SCRIPT_MISSING_BRACES = "script_missing_braces"
KIND_MOJIBAKE = "mojibake"
KIND_DOUBLE_ESCAPED_COMMAND = "double_escaped_command"
KIND_UNSUPPORTED_COMMAND = "unsupported_command"
KIND_BARE_UNICODE_MATH = "bare_unicode_math"
KIND_UNICODE_CHEMISTRY = "unicode_chemistry"
KIND_BARE_LEFT_BRACE = "bare_left_brace"

ALL_KINDS: tuple[str, ...] = (
    KIND_CONTROL_CHAR,
    KIND_LEGACY_DELIMITER,
    KIND_UNBALANCED_DOLLAR,
    KIND_COMMAND_MISSING_ARGUMENT,
    KIND_FRAC_MISSING_ARGS,
    KIND_SCRIPT_MISSING_BRACES,
    KIND_MOJIBAKE,
    KIND_DOUBLE_ESCAPED_COMMAND,
    KIND_UNSUPPORTED_COMMAND,
    KIND_BARE_UNICODE_MATH,
    KIND_UNICODE_CHEMISTRY,
    KIND_BARE_LEFT_BRACE,
)

# Control characters must be ZERO after the write-sink repair, so any hit is
# a regression of that fix (or a write path that bypasses it).
ERROR_KINDS: frozenset[str] = frozenset({KIND_CONTROL_CHAR})

SNIPPET_MAX_CHARS = 120
_SNIPPET_RADIUS = 45


@dataclass(frozen=True)
class Finding:
    """One defect at one position in one string."""

    kind: str
    position: int
    snippet: str


def _visible(ch: str) -> str:
    if ch == "\n":
        return "↵"
    if ord(ch) < 0x20 or ord(ch) == 0x7F:
        return f"<0x{ord(ch):02X}>"
    return ch


def make_snippet(text: str, position: int, radius: int = _SNIPPET_RADIUS) -> str:
    """A short window around ``position`` with every control char visible."""
    start = max(0, position - radius)
    end = min(len(text), position + radius)
    window = "".join(_visible(ch) for ch in text[start:end])
    if start > 0:
        window = "…" + window
    if end < len(text):
        window = window + "…"
    return window[:SNIPPET_MAX_CHARS]


# ---------------------------------------------------------------------------
# Math-span tokenizer shared by several detectors
# ---------------------------------------------------------------------------


def _unescaped_dollar_positions(text: str) -> list[int]:
    return [
        i for i, ch in enumerate(text) if ch == "$" and (i == 0 or text[i - 1] != "\\")
    ]


def _math_spans(text: str, *, closed_only: bool = False) -> list[tuple[int, int]]:
    """(inner_start, inner_end) of each ``$…$`` / ``$$…$$`` span."""
    spans: list[tuple[int, int]] = []
    positions = _unescaped_dollar_positions(text)
    i = 0
    open_kind: str | None = None
    open_inner_start = 0
    while i < len(positions):
        pos = positions[i]
        if i + 1 < len(positions) and positions[i + 1] == pos + 1:
            token, width, step = "$$", 2, 2
        else:
            token, width, step = "$", 1, 1
        if open_kind is None:
            open_kind = token
            open_inner_start = pos + width
        else:
            spans.append((open_inner_start, pos))
            open_kind = None
        i += step
    if open_kind is not None and not closed_only:
        spans.append((open_inner_start, len(text)))
    return spans


def _is_inside_math_span(text: str, pos: int) -> bool:
    n = 0
    for i in range(pos):
        if text[i] == "$" and (i == 0 or text[i - 1] != "\\"):
            n += 1
    return n % 2 == 1


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

_OTHER_C0_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ALPHA_RUN_RE = re.compile(r"[A-Za-z]+")
_WS_CTRL_LETTER = {"\t": "t", "\n": "n", "\r": "r"}
_MIN_RUN_AFTER_NEWLINE = 3


def _detect_control_chars(text: str) -> list[Finding]:
    findings = [
        Finding(KIND_CONTROL_CHAR, m.start(), make_snippet(text, m.start()))
        for m in _OTHER_C0_RE.finditer(text)
    ]
    if not any(ch in text for ch in _WS_CTRL_LETTER):
        return findings
    dollars: list[int] | None = None
    for i, ch in enumerate(text):
        letter = _WS_CTRL_LETTER.get(ch)
        if letter is None:
            continue
        m = _ALPHA_RUN_RE.match(text, i + 1)
        if not m:
            continue
        run = m.group(0)
        if ch == "\n" and len(run) < _MIN_RUN_AFTER_NEWLINE:
            continue
        if (letter + run) in LATEX_COMMANDS_BEHIND_JSON_ESCAPES:
            findings.append(Finding(KIND_CONTROL_CHAR, i, make_snippet(text, i)))
            continue
        # Inside a math span a raw newline/tab/CR is never content; when the
        # letters after it spell a command under ANY of the three escape
        # letters (`$<LF>ightarrow$`) the byte is a decoded backslash.
        if dollars is None:
            dollars = [
                k
                for k, c in enumerate(text)
                if c == "$" and (k == 0 or text[k - 1] != "\\")
            ]
        inside = sum(1 for k in dollars if k < i) % 2 == 1 and any(
            k > i for k in dollars
        )
        if inside and any(
            (c + run) in JSON_WHITESPACE_COLLISION_COMMANDS for c in "ntr"
        ):
            findings.append(Finding(KIND_CONTROL_CHAR, i, make_snippet(text, i)))
    return findings


_LEGACY_DELIM_RE = re.compile(r"(?<!\\)\\[()\[\]]")


def _detect_legacy_delimiters(text: str) -> list[Finding]:
    return [
        Finding(KIND_LEGACY_DELIMITER, m.start(), make_snippet(text, m.start()))
        for m in _LEGACY_DELIM_RE.finditer(text)
    ]


def _detect_unbalanced_dollars(text: str) -> list[Finding]:
    positions = _unescaped_dollar_positions(text)
    if len(positions) % 2 == 0:
        return []
    last = positions[-1]
    return [Finding(KIND_UNBALANCED_DOLLAR, last, make_snippet(text, last))]


_CMD_THEN_CLOSE_RE = re.compile(
    r"\\(?:" + "|".join(ARGUMENT_COMMANDS) + r")(?![A-Za-z])\s*(?=\$|\Z)"
)


def _detect_command_missing_argument(text: str) -> list[Finding]:
    return [
        Finding(KIND_COMMAND_MISSING_ARGUMENT, m.start(), make_snippet(text, m.start()))
        for m in _CMD_THEN_CLOSE_RE.finditer(text)
    ]


_FRAC_RE = re.compile(r"\\[dt]?frac(?![A-Za-z])")
_SIMPLE_ARG_RE = re.compile(r"[A-Za-z0-9]")


def _skip_brace_group(text: str, i: int) -> int | None:
    depth = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _consume_frac_argument(text: str, i: int) -> int | None:
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    if i >= n:
        return None
    ch = text[i]
    if ch == "{":
        return _skip_brace_group(text, i)
    if ch == "\\":
        m = _ALPHA_RUN_RE.match(text, i + 1)
        return m.end() if m else i + 2
    if _SIMPLE_ARG_RE.match(ch):
        return i + 1
    return None


def _detect_frac_missing_args(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for m in _FRAC_RE.finditer(text):
        after_cmd = m.end()
        first = _consume_frac_argument(text, after_cmd)
        if first is None:
            rest = text[after_cmd:].lstrip(" \t")
            if rest == "" or rest.startswith("$"):
                continue  # reported by command_missing_argument
            findings.append(
                Finding(
                    KIND_FRAC_MISSING_ARGS, m.start(), make_snippet(text, m.start())
                )
            )
            continue
        if _consume_frac_argument(text, first) is None:
            findings.append(
                Finding(
                    KIND_FRAC_MISSING_ARGS, m.start(), make_snippet(text, m.start())
                )
            )
    return findings


_SCRIPT_NO_BRACES_RE = re.compile(
    r"(?<!\\)[\^_](?:\d{2,}|[+\-][A-Za-z0-9]|[A-Za-z]{2,})"
)
_MAX_SCRIPT_SPAN_CHARS = 400


def _detect_script_missing_braces(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for start, end in _math_spans(text, closed_only=True):
        if end - start > _MAX_SCRIPT_SPAN_CHARS:
            continue
        for m in _SCRIPT_NO_BRACES_RE.finditer(text, start, end):
            findings.append(
                Finding(
                    KIND_SCRIPT_MISSING_BRACES, m.start(), make_snippet(text, m.start())
                )
            )
    return findings


_MOJIBAKE_RE = re.compile(r"�|â€|[ÎÏ]|[âÂÃ][\x80-\xff]")


def _detect_mojibake(text: str) -> list[Finding]:
    return [
        Finding(KIND_MOJIBAKE, m.start(), make_snippet(text, m.start()))
        for m in _MOJIBAKE_RE.finditer(text)
    ]


_DOUBLE_ESCAPED_RE = re.compile(r"(?<!\\)(?:\\\\)+[A-Za-z]{2,}")
_JSON_OBJECT_HINT_RE = re.compile(r'\{\s*"[^"\n]{1,80}"\s*:')


_ROW_ENVIRONMENT_RE = re.compile(r"\\begin\{|&")


def _detect_double_escaped_commands(text: str) -> list[Finding]:
    if _JSON_OBJECT_HINT_RE.search(text):
        return []
    # Inside a matrix / aligned block `\\` is a row separator, so `a&b\\cos x`
    # is a row that starts with `\cos`, not a double-escaped command.
    row_spans = [
        (s, e)
        for s, e, _d in math_ranges(text)
        if _ROW_ENVIRONMENT_RE.search(text[s:e])
    ]
    return [
        Finding(KIND_DOUBLE_ESCAPED_COMMAND, m.start(), make_snippet(text, m.start()))
        for m in _DOUBLE_ESCAPED_RE.finditer(text)
        if not any(s <= m.start() < e for s, e in row_spans)
    ]


_COMMAND_NAME_RE = re.compile(r"(?<!\\)\\([A-Za-z]+)")
_UNSUPPORTED_RE = re.compile(
    r"\\(?:" + "|".join(UNSUPPORTED_COMMANDS) + r")(?![A-Za-z])"
)


def _detect_unsupported_commands(text: str) -> list[Finding]:
    findings = [
        Finding(KIND_UNSUPPORTED_COMMAND, m.start(), make_snippet(text, m.start()))
        for m in _UNSUPPORTED_RE.finditer(text)
    ]
    reported = {f.position for f in findings}
    for start, end in _math_spans(text, closed_only=True):
        for m in _COMMAND_NAME_RE.finditer(text, start, end):
            name = m.group(1)
            if name in KATEX_COMMANDS or name in AUDIT_EXTRA_ALLOWED_COMMANDS:
                continue
            if m.start() in reported:
                continue
            findings.append(
                Finding(
                    KIND_UNSUPPORTED_COMMAND, m.start(), make_snippet(text, m.start())
                )
            )
    return findings


_BARE_UNICODE_MATH_RE = re.compile(
    r"[×÷±∓√∞∂∇≤≥≠≈≡∝→←↔⇌⇒⇐⇔∈∉⊂⊃⊆⊇∪∩∅∀∃∧∨αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]"
)


def _detect_bare_unicode_math(text: str) -> list[Finding]:
    if not _BARE_UNICODE_MATH_RE.search(text):
        return []
    mask = math_mask(text)
    return [
        Finding(KIND_BARE_UNICODE_MATH, m.start(), make_snippet(text, m.start()))
        for m in _BARE_UNICODE_MATH_RE.finditer(text)
        if not mask[m.start()]
    ]


_UNICODE_CHEM_RE = re.compile(r"[A-Z][a-z]?[₀-₉]+")


def _detect_unicode_chemistry(text: str) -> list[Finding]:
    return [
        Finding(KIND_UNICODE_CHEMISTRY, m.start(), make_snippet(text, m.start()))
        for m in _UNICODE_CHEM_RE.finditer(text)
    ]


_BARE_BRACE_CMD_RE = re.compile(r"\\left(?!\\)\{|\\right(?!\\)\}")


def _detect_bare_left_brace(text: str) -> list[Finding]:
    return [
        Finding(KIND_BARE_LEFT_BRACE, m.start(), make_snippet(text, m.start()))
        for m in _BARE_BRACE_CMD_RE.finditer(text)
    ]


DETECTORS = (
    _detect_control_chars,
    _detect_legacy_delimiters,
    _detect_unbalanced_dollars,
    _detect_command_missing_argument,
    _detect_frac_missing_args,
    _detect_script_missing_braces,
    _detect_mojibake,
    _detect_double_escaped_commands,
    _detect_unsupported_commands,
    _detect_bare_unicode_math,
    _detect_unicode_chemistry,
    _detect_bare_left_brace,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def audit(text: Any) -> list[Finding]:
    """Every defect in one string, ordered by position then kind."""
    if not isinstance(text, str) or not text:
        return []
    findings: list[Finding] = []
    for detector in DETECTORS:
        findings.extend(detector(text))
    findings.sort(key=lambda f: (f.position, f.kind))
    return findings


def audit_kinds(text: Any) -> list[str]:
    """The kinds only, in finding order (what the corpus compares)."""
    return [f.kind for f in audit(text)]


def _decode_json_leaf(text: str) -> Any:
    head = text.lstrip()[:1]
    if head not in "{[":
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _content_leaves(obj: Any, key_hint: str, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        if is_non_content_key(key_hint) or is_not_rendered_key(key_hint):
            return
        if is_url_or_path_string(obj):
            return
        decoded = _decode_json_leaf(obj)
        if decoded is not None:
            yield from _content_leaves(decoded, key_hint, f"{path}(json)")
            return
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            yield from _content_leaves(v, str(k), child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _content_leaves(v, key_hint, f"{path}[{i}]")


def audit_deep(obj: Any) -> list[tuple[str, Finding]]:
    """``(field_path, finding)`` for every content string leaf of a document."""
    out: list[tuple[str, Finding]] = []
    for path, text in _content_leaves(obj, "", ""):
        for finding in audit(text):
            out.append((path, finding))
    return out


def count_by_kind(findings: Iterable[Finding]) -> dict[str, int]:
    counter = Counter(f.kind for f in findings)
    return {k: counter[k] for k in ALL_KINDS if counter[k]}


def is_error(kinds: Iterable[str]) -> bool:
    """True when any kind is a regression class (log at ERROR)."""
    return bool(ERROR_KINDS.intersection(kinds))
