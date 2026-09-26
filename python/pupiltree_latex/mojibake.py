"""Mojibake repair.

Two engines:

* `fix_mojibake_table` — deterministic table + context rules, identical in
  Python, Dart and JS. Used by `normalize` everywhere. Ported from the
  script_editor `MojibakeFixer` (kept there since 2026-04) and the
  worksheet.ai copy of it.
* `fix_mojibake_ftfy` — `ftfy.fix_text` with the Backend's configuration.
  Used by `canonicalize` in Python when ftfy is installed; it repairs
  patterns the table does not know. Corpus cases that need it are tagged
  ``"impl": ["python"]``.
"""

from __future__ import annotations

import re
from typing import Any

try:  # ftfy is an optional dependency (`pip install pupiltree-latex[ftfy]`)
    import ftfy
    from ftfy import TextFixerConfig

    _FTFY_CONFIG: Any = TextFixerConfig(
        unescape_html=True,
        fix_encoding=True,
        fix_latin_ligatures=True,
        fix_character_width=True,
        uncurl_quotes=False,
        fix_line_breaks=False,  # CR/CRLF are content; the ports do not touch them
        normalization="NFC",
    )
    HAS_FTFY = True
except ImportError:  # pragma: no cover - exercised on machines without ftfy
    ftfy = None
    _FTFY_CONFIG = None
    HAS_FTFY = False

_FTFY_PAD_HEAD = "abc xxx "
_FTFY_PAD_TAIL = " yyy def"

# UTF-8 bytes of a symbol read as Latin-1 / Windows-1252. Longest keys first
# so `Ï\u0088` is tried before `Ï`.
MOJIBAKE_TABLE: dict[str, str] = {
    # Greek lowercase
    "Ï€": "π",
    "Ï‰": "ω",
    "Î±": "α",
    "Î²": "β",
    "Î³": "γ",
    "Î´": "δ",
    "Îµ": "ε",
    "Î¶": "ζ",
    "Î·": "η",
    "Î¸": "θ",
    "Î¹": "ι",
    "Îº": "κ",
    "Î»": "λ",
    "Î¼": "μ",
    "Î½": "ν",
    "Î¾": "ξ",
    "Ïƒ": "σ",
    "Ï„": "τ",
    "Ï…": "υ",
    "Ï†": "φ",
    "Ï‡": "χ",
    "Ï\u0088": "ψ",
    "Ï\u0081": "ρ",
    # Greek uppercase
    'Î"': "Γ",
    "Î\u0094": "Δ",
    "Î˜": "Θ",
    "Î\u009b": "Λ",
    "Îž": "Ξ",
    "Î ": "Π",
    "Î£": "Σ",
    "Î¦": "Φ",
    "Î¨": "Ψ",
    "Î©": "Ω",
    # Math symbols
    "âˆš": "√",
    "âˆž": "∞",
    "âˆ«": "∫",
    "â‰¤": "≤",
    "â‰¥": "≥",
    "â‰ ": "≠",
    "â‰ˆ": "≈",
    "Ã—": "×",
    "Ã·": "÷",
    "Â±": "±",
    "Â²": "²",
    "Â³": "³",
    "Â¹": "¹",
    "Â°": "°",
    "Âµ": "µ",
    "Â·": "·",
    "Â½": "½",
    "Â¼": "¼",
    "Â¾": "¾",
    # Arrows and symbols written with their C1 bytes
    "â\u0086\u0092": "→",
    "â\u0086\u0090": "←",
    "â\u0086\u0094": "↔",
    "â\u0087\u008c": "⇌",
    "â\u0087\u0092": "⇒",
    "â\u0088«": "∫",
    "â\u0088\u0091": "∑",
    "â\u0088\u008f": "∏",
    "â\u0088\u009a": "√",
    "â\u0088\u0082": "∂",
    "â\u0088\u0087": "∇",
    "â\u0088\u0088": "∈",
    "â\u0088\u009e": "∞",
    "â\u0088«": "∫",
    "−«": "∫",
    # Subscript digits
    "â\u0082\u0080": "₀",
    "â\u0082\u0081": "₁",
    "â\u0082\u0082": "₂",
    "â\u0082\u0083": "₃",
    "â\u0082\u0084": "₄",
    "â\u0082\u0085": "₅",
    "â\u0082\u0086": "₆",
    "â\u0082\u0087": "₇",
    "â\u0082\u0088": "₈",
    "â\u0082\u0089": "₉",
    # Superscript signs
    "â\u0081º": "⁺",
    "â\u0081»": "⁻",
    # Punctuation
    "â€”": "—",
    "â€“": "–",
    'â€"': "—",
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€\u009d": "”",
    "â€¦": "…",
    # cp1252 renderings of Greek letters whose second byte is a C1 control
    # that Windows-1252 maps to a printable (0x88 → ˆ U+02C6)
    "Ïˆ": "ψ",
}

# HTML entities a model or an old export leaves in content (`a &amp; b`).
# ftfy unescapes these; the table path does the same with this small set
# plus numeric references so every language agrees.
HTML_ENTITIES: dict[str, str] = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&#39;": "'",
    "&nbsp;": " ",
    "&deg;": "°",
    "&times;": "×",
    "&divide;": "÷",
    "&plusmn;": "±",
    "&minus;": "−",
    "&middot;": "·",
    "&hellip;": "…",
    "&pi;": "π",
    "&alpha;": "α",
    "&beta;": "β",
    "&theta;": "θ",
    "&lambda;": "λ",
    "&mu;": "μ",
    "&omega;": "ω",
    "&Delta;": "Δ",
    "&rarr;": "→",
    "&larr;": "←",
    "&le;": "≤",
    "&ge;": "≥",
    "&ne;": "≠",
    "&radic;": "√",
    "&infin;": "∞",
    "&sup2;": "²",
    "&sup3;": "³",
}
_ENTITY_RE = re.compile(r"&(?:#(\d{1,7})|#[xX]([0-9A-Fa-f]{1,6})|([A-Za-z]{2,8}));")


def unescape_html_entities(text: str) -> str:
    """`&amp;` → `&`, `&#960;` → `π`, `&#x3c0;` → `π`; unknown names stay."""
    if "&" not in text:
        return text
    for _ in range(3):
        decoded = _ENTITY_RE.sub(_entity_replace, text)
        if decoded == text:
            return text
        text = decoded
    return text


def _entity_replace(m: "re.Match[str]") -> str:
    if m.group(1):
        code = int(m.group(1))
    elif m.group(2):
        code = int(m.group(2), 16)
    else:
        return HTML_ENTITIES.get(m.group(0), m.group(0))
    if 0 < code <= 0x10FFFF and not (0xD800 <= code <= 0xDFFF):
        return chr(code)
    return m.group(0)






def _readings(ch: str) -> list[str]:
    """How ``ch`` looks when its UTF-8 bytes are read as Latin-1 and as
    Windows-1252 (bytes cp1252 leaves undefined keep their Latin-1 char)."""
    raw = ch.encode("utf-8")
    latin1 = raw.decode("latin-1")
    cp1252 = "".join(
        b.to_bytes(1, "big").decode("cp1252", errors="strict")
        if b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D)
        else chr(b)
        for b in raw
    )
    return [latin1, cp1252] if cp1252 != latin1 else [latin1]


_GENERATED_MOJIBAKE_SOURCE = (
    "αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ"
    "×÷±∓·⋅√∛∞∂∇≤≥≠≈≡∼≅∝⊥∥∫∬∭∮∑∏"
    "→←↔⇒⇐⇔↑↓⇌↦∈∉⊂⊃⊆⊇∪∩∅∀∃∧∨¬∴∵ℝℕℤℚℂℏℓ∠△°"
    "₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼"
    "—–…‘’“”•"
    "€£¥₹¢"  # currency: `â‚¬5` must become `€5`, never `$â‚\neg5$`
)
for _ch in _GENERATED_MOJIBAKE_SOURCE:
    for _reading in _readings(_ch):
        if len(_reading) >= 2 and _reading != _ch:
            MOJIBAKE_TABLE.setdefault(_reading, _ch)

_TABLE_KEYS_LONGEST_FIRST = sorted(MOJIBAKE_TABLE, key=len, reverse=True)
_NON_ASCII_RE = re.compile(r"[^\x00-\x7f]")
_BAD_RE = re.compile("[�ÃÂ]")
_REPLACEMENT_RE = re.compile("�")
_C1_RE = re.compile("[\u0080-\u009f]")
_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")
_GARBAGE = r"[\u0080-\u009f -ÿ]"
_ROOT_DIGITS_RE = re.compile(r"â" + _GARBAGE + r"{0,3}(\d+)")
_ROOT_PAREN_RE = re.compile(r"â" + _GARBAGE + r"{0,3}\(")
_LETTER_ROOT_RE = re.compile(r"([A-Za-z])â" + _GARBAGE + r"{0,3}(\d)")
_SLASH_ROOT_RE = re.compile(r"/â" + _GARBAGE + r"{0,3}(\d)")
_DIGIT_PI_RE = re.compile(r"(\d)" + _GARBAGE + r"{0,2}Ï")
_LEAD_PI_SLASH_RE = re.compile(r"(^|[\s(,\[])Ï" + _GARBAGE + r"{0,2}/")
_SLASH_OMEGA_RE = re.compile(r"/Ï(?=[\s,.)\]}]|$)")
_OP_PI_RE = re.compile(r"([+\-*×÷=/(])Ï(?=[+\-*×÷=/)\s,]|$)")
_LEAD_PI_RE = re.compile(r"(^|[\s(,])Ï(?=[\s),.]|$)")


def _try_fix_double_encoding(text: str) -> str:
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        raw = text.encode("latin-1")
    except UnicodeEncodeError:
        return text
    decoded = raw.decode("utf-8", errors="replace")
    original_bad = len(_BAD_RE.findall(text))
    decoded_bad = len(_REPLACEMENT_RE.findall(decoded))
    return decoded if decoded_bad < original_bad else text


def _apply_table(text: str) -> str:
    for key in _TABLE_KEYS_LONGEST_FIRST:
        if key in text:
            text = text.replace(key, MOJIBAKE_TABLE[key])
    return text


# π, ω and √ present before the context rules run are hidden behind these
# private-use placeholders so the doubled-symbol cleanup never touches them.
_COLLAPSE_PLACEHOLDERS: dict[str, str] = {"π": "\ue020", "ω": "\ue021", "√": "\ue022"}


def _apply_context_rules(text: str) -> str:
    for ch, placeholder in _COLLAPSE_PLACEHOLDERS.items():
        text = text.replace(ch, placeholder)
    # NBSP is a space, not garbage; C1 controls that survived the table are
    # garbage; a lone surrogate can never be encoded.
    text = text.replace("\u00a0", " ")
    text = _C1_RE.sub("", text)
    text = _LONE_SURROGATE_RE.sub("", text)
    text = _ROOT_DIGITS_RE.sub(lambda m: "√" + m.group(1), text)
    text = _ROOT_PAREN_RE.sub("√(", text)
    text = _LETTER_ROOT_RE.sub(lambda m: m.group(1) + "√" + m.group(2), text)
    text = _SLASH_ROOT_RE.sub(lambda m: "/√" + m.group(1), text)
    text = _DIGIT_PI_RE.sub(lambda m: m.group(1) + "π", text)
    text = _LEAD_PI_SLASH_RE.sub(lambda m: m.group(1) + "π/", text)
    text = _SLASH_OMEGA_RE.sub("/ω", text)
    text = text.replace("Ï/Ï", "π/ω")
    text = _OP_PI_RE.sub(lambda m: m.group(1) + "π", text)
    text = _LEAD_PI_RE.sub(lambda m: m.group(1) + "π", text)
    # Collapse a doubled π / ω / √ only when a context rule above produced
    # one of the pair: `Ï€Ï` once became `ππ`. A genuine repeated letter
    # (`ππ`, `ωω`, `√√2`, or `Ï€Ï€` which the table maps to `ππ`) is kept:
    # the characters present before the rules are protected by placeholders.
    for ch, placeholder in _COLLAPSE_PLACEHOLDERS.items():
        text = text.replace(ch + ch, ch)
        text = text.replace(placeholder + ch, placeholder)
        text = text.replace(ch + placeholder, placeholder)
        text = text.replace(placeholder, ch)
    return text


def fix_mojibake_table(text: Any) -> Any:
    """Deterministic mojibake repair, identical in every language."""
    if not isinstance(text, str) or not text:
        return text
    text = unescape_html_entities(text)
    if not _NON_ASCII_RE.search(text):
        return text
    text = _try_fix_double_encoding(text)
    text = _apply_table(text)
    text = _apply_context_rules(text)
    return text


def fix_mojibake_ftfy(text: Any) -> Any:
    """ftfy-based repair (Backend `_fix_mojibake`). Falls back to the table
    when ftfy is not installed."""
    if not isinstance(text, str) or not text:
        return text
    if not HAS_FTFY:
        return fix_mojibake_table(text)
    if len(text) < 20:
        # ftfy's heuristics need context to call a short string mojibake.
        padded = _FTFY_PAD_HEAD + text + _FTFY_PAD_TAIL
        fixed = ftfy.fix_text(padded, config=_FTFY_CONFIG)
        return fixed.removeprefix(_FTFY_PAD_HEAD).removesuffix(_FTFY_PAD_TAIL)
    return ftfy.fix_text(text, config=_FTFY_CONFIG)
