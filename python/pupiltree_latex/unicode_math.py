"""Unicode math character → LaTeX command mapping, aligned with flutter_math_fork.

Verbatim from Backend `services/ai/helper/unicode_to_latex.py` (2026-09-25);
only the public names were added at the bottom.

The mapping is a curated STEM subset of KaTeX's src/symbols.js (KaTeX is the
upstream project flutter_math_fork ports). Every entry here is a character
flutter_math_fork can render via its LaTeX form. Characters outside this
table are intentionally left alone so the caller's validator can flag them.

Conversion is span-aware by default: Unicode math chars are only replaced
inside `$...$` / `$$...$$` spans, so prose like "the frequency ν is 500 Hz"
retains its Unicode character for screen readers while `$ν = 500$` becomes
`$\\nu = 500$` for flutter_math_fork.

Run sanitize_latex_text -> unicode_math_to_latex as the last step of the
sanitizer pipeline, after ftfy has normalized mojibake to clean Unicode.
"""

from __future__ import annotations

import re

from .spans import math_mask, math_ranges


UNICODE_MATH: dict[str, str] = {
    # Greek lowercase
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ϵ": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ϑ": r"\vartheta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ϖ": r"\varpi",
    "ρ": r"\rho",
    "ϱ": r"\varrho",
    "σ": r"\sigma",
    "ς": r"\varsigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "ϕ": r"\varphi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    # Greek uppercase (those that differ visually from Latin letters)
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    # Binary operators
    "×": r"\times",
    "÷": r"\div",
    "±": r"\pm",
    "∓": r"\mp",
    "·": r"\cdot",
    "⋅": r"\cdot",
    "∗": r"\ast",
    "⊕": r"\oplus",
    "⊖": r"\ominus",
    "⊗": r"\otimes",
    "⊙": r"\odot",
    "∘": r"\circ",
    # Relational
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∼": r"\sim",
    "≃": r"\simeq",
    "≅": r"\cong",
    "∝": r"\propto",
    "≪": r"\ll",
    "≫": r"\gg",
    "⊥": r"\perp",
    "∥": r"\parallel",
    "∣": r"\mid",
    # Calculus & analysis
    "∂": r"\partial",
    "∇": r"\nabla",
    "∫": r"\int",
    "∬": r"\iint",
    "∭": r"\iiint",
    "∮": r"\oint",
    "∞": r"\infty",
    "∑": r"\sum",
    "∏": r"\prod",
    "√": r"\sqrt",
    "∛": r"\sqrt[3]",
    "∜": r"\sqrt[4]",
    "ℏ": r"\hbar",
    "ℓ": r"\ell",
    # Arrows
    "→": r"\rightarrow",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow",
    "↑": r"\uparrow",
    "↓": r"\downarrow",
    "⇌": r"\rightleftharpoons",
    "↦": r"\mapsto",
    # Set theory & logic
    "∈": r"\in",
    "∉": r"\notin",
    "∋": r"\ni",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "⊆": r"\subseteq",
    "⊇": r"\supseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "∅": r"\emptyset",
    "∀": r"\forall",
    "∃": r"\exists",
    "∄": r"\nexists",
    "¬": r"\neg",
    "∧": r"\land",
    "∨": r"\lor",
    "∴": r"\therefore",
    "∵": r"\because",
    "⊄": r"\not\subset",
    "⊅": r"\not\supset",
    "⊈": r"\nsubseteq",
    "⊉": r"\nsupseteq",
    # Blackboard bold
    "ℝ": r"\mathbb{R}",
    "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}",
    "ℂ": r"\mathbb{C}",
    "ℙ": r"\mathbb{P}",
    # Geometry
    "∠": r"\angle",
    "∡": r"\measuredangle",
    "△": r"\triangle",
    "□": r"\square",
    # Degree symbol (math context)
    "°": r"^{\circ}",
    # Fractions (rare, but render correctly as LaTeX fractions)
    "½": r"\tfrac{1}{2}",
    "⅓": r"\tfrac{1}{3}",
    "⅔": r"\tfrac{2}{3}",
    "¼": r"\tfrac{1}{4}",
    "¾": r"\tfrac{3}{4}",
    "⅕": r"\tfrac{1}{5}",
    "⅖": r"\tfrac{2}{5}",
    "⅗": r"\tfrac{3}{5}",
    "⅘": r"\tfrac{4}{5}",
    "⅙": r"\tfrac{1}{6}",
    "⅚": r"\tfrac{5}{6}",
    "⅛": r"\tfrac{1}{8}",
    "⅜": r"\tfrac{3}{8}",
    "⅝": r"\tfrac{5}{8}",
    "⅞": r"\tfrac{7}{8}",
    "⅐": r"\tfrac{1}{7}",
    "⅑": r"\tfrac{1}{9}",
    "⅒": r"\tfrac{1}{10}",
    # Unicode superscripts — digits
    "⁰": "^{0}",
    "¹": "^{1}",
    "²": "^{2}",
    "³": "^{3}",
    "⁴": "^{4}",
    "⁵": "^{5}",
    "⁶": "^{6}",
    "⁷": "^{7}",
    "⁸": "^{8}",
    "⁹": "^{9}",
    "⁺": "^{+}",
    "⁻": "^{-}",
    "⁼": "^{=}",
    "⁽": "^{(}",
    "⁾": "^{)}",
    # Unicode superscripts — letters (physics/math indices)
    "ⁿ": "^{n}",
    "ⁱ": "^{i}",
    "ᵃ": "^{a}",
    "ᵇ": "^{b}",
    "ᶜ": "^{c}",
    "ᵈ": "^{d}",
    "ᵉ": "^{e}",
    "ᶠ": "^{f}",
    "ᵍ": "^{g}",
    "ʰ": "^{h}",
    "ʲ": "^{j}",
    "ᵏ": "^{k}",
    "ˡ": "^{l}",
    "ᵐ": "^{m}",
    "ᵒ": "^{o}",
    "ᵖ": "^{p}",
    "ʳ": "^{r}",
    "ˢ": "^{s}",
    "ᵗ": "^{t}",
    "ᵘ": "^{u}",
    "ᵛ": "^{v}",
    "ʷ": "^{w}",
    "ˣ": "^{x}",
    "ʸ": "^{y}",
    "ᶻ": "^{z}",
    "ᵀ": "^{T}",
    "ᴬ": "^{A}",
    "ᴮ": "^{B}",
    "ᴰ": "^{D}",
    "ᴱ": "^{E}",
    "ᴳ": "^{G}",
    "ᴴ": "^{H}",
    "ᴵ": "^{I}",
    "ᴶ": "^{J}",
    "ᴷ": "^{K}",
    "ᴸ": "^{L}",
    "ᴹ": "^{M}",
    "ᴺ": "^{N}",
    "ᴼ": "^{O}",
    "ᴾ": "^{P}",
    "ᴿ": "^{R}",
    "ᵁ": "^{U}",
    "ⱽ": "^{V}",
    "ᵂ": "^{W}",
    # Unicode subscripts — digits
    "₀": "_{0}",
    "₁": "_{1}",
    "₂": "_{2}",
    "₃": "_{3}",
    "₄": "_{4}",
    "₅": "_{5}",
    "₆": "_{6}",
    "₇": "_{7}",
    "₈": "_{8}",
    "₉": "_{9}",
    "₊": "_{+}",
    "₋": "_{-}",
    "₌": "_{=}",
    "₍": "_{(}",
    "₎": "_{)}",
    # Unicode subscripts — letters (indices in physics/chem: Hₙ, Tₐ, μₛ, etc.)
    "ₐ": "_{a}",
    "ₑ": "_{e}",
    "ₕ": "_{h}",
    "ᵢ": "_{i}",
    "ⱼ": "_{j}",
    "ₖ": "_{k}",
    "ₗ": "_{l}",
    "ₘ": "_{m}",
    "ₙ": "_{n}",
    "ₒ": "_{o}",
    "ₚ": "_{p}",
    "ᵣ": "_{r}",
    "ₛ": "_{s}",
    "ₜ": "_{t}",
    "ᵤ": "_{u}",
    "ᵥ": "_{v}",
    "ₓ": "_{x}",
    # Unicode subscripts — Greek letters (rare but present: e.g. ᵧ for γ)
    "ᵦ": r"_{\beta}",
    "ᵧ": r"_{\gamma}",
    "ᵨ": r"_{\rho}",
    "ᵩ": r"_{\phi}",
    "ᵪ": r"_{\chi}",
    # Physics bra-ket
    "⟨": r"\langle",
    "⟩": r"\rangle",
    # Ellipses
    "…": r"\ldots",
    "⋯": r"\cdots",
    "⋮": r"\vdots",
    "⋱": r"\ddots",
}


# Homoglyph normalization — pairs of Unicode chars that RENDER IDENTICALLY
# but have different codepoints. Upstream AI models occasionally emit the
# "wrong" codepoint; without normalization UNICODE_MATH lookup silently
# misses them. Applied before the lookup so the canonical form flows through.
HOMOGLYPHS: dict[str, str] = {
    "µ": "μ",  # µ MICRO SIGN            → μ GREEK SMALL LETTER MU
    "∆": "Δ",  # ∆ INCREMENT             → Δ GREEK CAPITAL LETTER DELTA
    "ħ": "ℏ",  # ħ LATIN h WITH STROKE   → ℏ PLANCK CONSTANT OVER 2PI
    "−": "-",  # − MINUS SIGN            → ASCII hyphen-minus
    "‐": "-",  # ‐ HYPHEN                → ASCII hyphen-minus
    "‒": "-",  # ‒ FIGURE DASH           → ASCII hyphen-minus
    "Ω": "Ω",  # Ω OHM SIGN (deprecated) → Ω GREEK CAPITAL OMEGA
    "K": "K",  # K KELVIN SIGN           → ASCII K
    "Å": "Å",  # Å ANGSTROM SIGN         → Å Latin-1 A-ring (Å unit rendered identically; NFC usually collapses)
}
_HOMOGLYPH_RE = re.compile("[" + re.escape("".join(HOMOGLYPHS.keys())) + "]")


def normalize_homoglyphs(text: str) -> str:
    """Replace visually-identical Unicode codepoints with their canonical form.

    Example: µ (U+00B5 MICRO SIGN) → μ (U+03BC GREEK SMALL LETTER MU).
    Runs idempotently; no-op when no targets are present.

    This MUST run before unicode_math_to_latex so the canonical codepoint
    reaches the lookup table.
    """
    if not isinstance(text, str) or not text:
        return text
    if not _HOMOGLYPH_RE.search(text):
        return text
    out_parts: list[str] = []
    for ch in text:
        out_parts.append(HOMOGLYPHS.get(ch, ch))
    return "".join(out_parts)


# Combining vector arrow (U+20D7) is the Unicode way to write `a⃗` (a-vector).
# No precomposed form exists — this combiner survives NFC. Always convert to
# `\vec{X}` regardless of math-span context, because the combiner itself is
# unambiguous math notation (prose never uses it).
_COMBINING_VEC_RE = re.compile(r"([A-Za-z])⃗")


def convert_combining_vec(text: str, *, wrap_bare: bool = True) -> str:
    """Convert `X⃗` (letter + U+20D7) to LaTeX `\\vec{X}`.

    When wrap_bare=True (default), occurrences outside $...$ are wrapped in
    `$...$` so flutter_math_fork renders them. Inside existing math spans,
    the surrounding `$...$` is left intact.
    """
    if not isinstance(text, str) or not text:
        return text
    if "⃗" not in text:
        return text

    if not wrap_bare:
        return _COMBINING_VEC_RE.sub(r"\\vec{\1}", text)

    # Walk matches, wrap ones outside math spans (one mask for the call:
    # `$` parity was wrong inside `$$…$$` and O(n) per match).
    mask = math_mask(text)

    def _replace(m: re.Match[str]) -> str:
        if mask[m.start()]:
            return rf"\vec{{{m.group(1)}}}"
        return rf"$\vec{{{m.group(1)}}}$"

    return _COMBINING_VEC_RE.sub(_replace, text)


# Fast-path check: any character from UNICODE_MATH present? If not,
# _replace_in_span is a no-op.
_TRIGGER_RE = re.compile("[" + re.escape("".join(UNICODE_MATH.keys())) + "]")


def _needs_terminator(replacement: str, next_char: str | None) -> bool:
    """True when `\\cmd` would run into a following letter.

    Decided at replacement time (not post-hoc) to avoid the backtracking
    trap where greedy `\\[A-Za-z]+` cannot distinguish `\\times` followed
    by `x` from a hypothetical `\\timesx` command.
    """
    if not replacement.startswith("\\"):
        return False
    if not replacement[-1].isalpha():
        return False
    if next_char is None:
        return False
    return next_char.isalpha()


# The radical glyphs map to `\sqrt`, the one command here that REQUIRES an
# argument: `$\sqrt$` is a KaTeX parse error ("Expected group as argument to
# '\sqrt'"), drawn as red text on the classroom board (#1654). They are only
# converted together with their radicand; with none to take, the glyph stays,
# which both renderers display.
_ROOT_CHARS = frozenset("√∛∜")
_ROOT_NUMBER_RE = re.compile(r"[-−]?\d+(?:\.\d+)?")
_CLOSERS = {"(": ")", "{": "}"}
# What may not follow a captured number or letter: more of the same word, a
# call, or a script. `√2gh` lost its vinculum on the way here, so it could be
# `\sqrt{2}gh` or `\sqrt{2gh}` — not ours to decide.
_SCRIPT_CHARS = frozenset("^_⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ₀₁₂₃₄₅₆₇₈₉")


def _root_argument(text: str, pos: int) -> tuple[str, int] | None:
    """The radicand starting at `pos` as (inner text, end index), or None.

    Only shapes with a single reading are taken: a balanced `(…)` or `{…}`
    group that stays inside one line and one math span, a number, or a single
    letter.
    """
    if pos >= len(text):
        return None
    ch = text[pos]
    if ch in _CLOSERS:
        closer, depth = _CLOSERS[ch], 0
        for end in range(pos, len(text)):
            c = text[end]
            if c in "$\n":
                return None
            if c == ch:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    inner = text[pos + 1 : end]
                    return (inner, end + 1) if inner.strip() else None
        return None
    m = _ROOT_NUMBER_RE.match(text, pos)
    if m:
        end = m.end()
    elif ch.isalpha():
        end = pos + 1
    else:
        return None
    nxt = text[end] if end < len(text) else ""
    if nxt.isalnum() or nxt == "(" or nxt in _SCRIPT_CHARS:
        return None
    return text[pos:end], end


def _root_has_next_token(segment: str, pos: int) -> bool:
    """Inside math `\\sqrt` takes the next token; False when there is none."""
    rest = segment[pos:].lstrip()
    return bool(rest) and rest[0] not in "}&^_" and not rest.startswith("\\\\")


# Text-mode groups inside math: their content is prose, and KaTeX renders
# `\text{H₂O}` or `\text{→}` as written while `\text{H_{2}O}` is a parse
# error. The group is copied verbatim (balanced braces).
_TEXT_GROUP_RE = re.compile(
    r"\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|mathrm|mbox|hbox|ce|pu)\s*\{"
)
_SUPERSCRIPT_CHARS = frozenset(k for k, v in UNICODE_MATH.items() if v.startswith("^{"))
_SUBSCRIPT_CHARS = frozenset(k for k, v in UNICODE_MATH.items() if v.startswith("_{"))


def _skip_group(segment: str, i: int) -> int:
    """Index just past the `}` matching the `{` at ``i`` (or len on imbalance)."""
    depth = 0
    n = len(segment)
    while i < n:
        c = segment[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _replace_chars(segment: str) -> str:
    """Replace every Unicode math char in a segment with its LaTeX form.

    Skips `\\text{…}`-family groups (prose inside math), turns a RUN of
    Unicode super/subscripts into one `^{…}` / `_{…}` (`10⁻³` → `10^{-3}`,
    never `10^{-}^{3}`), and, when a replacement is a `\\cmd` command and
    the next character is a letter, appends a space so `a⋅b` → `a\\cdot b`.
    """
    if not _TRIGGER_RE.search(segment):
        return segment
    out_parts: list[str] = []
    n = len(segment)
    i = 0
    while i < n:
        ch = segment[i]
        if ch == "\\":
            m = _TEXT_GROUP_RE.match(segment, i)
            if m:
                end = _skip_group(segment, m.end() - 1)
                out_parts.append(segment[i:end])
                i = end
                continue
        if ch in _SUPERSCRIPT_CHARS or ch in _SUBSCRIPT_CHARS:
            table = _SUPERSCRIPT_CHARS if ch in _SUPERSCRIPT_CHARS else _SUBSCRIPT_CHARS
            j = i
            inner: list[str] = []
            while j < n and segment[j] in table:
                inner.append(UNICODE_MATH[segment[j]][2:-1])
                j += 1
            out_parts.append(
                ("^{" if table is _SUPERSCRIPT_CHARS else "_{") + "".join(inner) + "}"
            )
            i = j
            continue
        if ch in _ROOT_CHARS:
            arg = _root_argument(segment, i + 1)
            if arg is not None:
                inner, i = arg
                out_parts.append(UNICODE_MATH[ch] + "{" + _replace_chars(inner) + "}")
                continue
            if not _root_has_next_token(segment, i + 1):
                out_parts.append(ch)
                i += 1
                continue
        replacement = UNICODE_MATH.get(ch, ch)
        if replacement != ch:
            next_char = segment[i + 1] if i + 1 < n else None
            if _needs_terminator(replacement, next_char):
                replacement = replacement + " "
        out_parts.append(replacement)
        i += 1
    return "".join(out_parts)


# Math-span regexes (same semantics as latex_rules.py).
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$([^$]+?)\$(?!\$)")


def unicode_math_to_latex(text: str, *, inside_math_only: bool = True) -> str:
    """Convert Unicode math characters to their LaTeX command form inside
    existing math spans.

    Args:
        text: the string to transform.
        inside_math_only: when True (default), only replace inside $...$
            and $$...$$ spans. When False, replace everywhere (use only
            for pre-prompt normalization of free-form model output).

    Returns `text` unchanged when no target characters are present.
    """
    if not isinstance(text, str) or not text:
        return text
    if not _TRIGGER_RE.search(text):
        return text

    if not inside_math_only:
        return _replace_chars(text)

    # Spans come from the renderers' tokenizer, so display math, escaped
    # dollars and currency are read exactly as they will be typeset.
    out: list[str] = []
    pos = 0
    for start, end, _display in math_ranges(text):
        out.append(text[pos:start])
        raw = text[start:end]
        k = 2 if raw.startswith(("$$", "\\")) else 1
        out.append(
            raw[:k] + _replace_chars(raw[k : len(raw) - k]) + raw[len(raw) - k :]
        )
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _is_inside_math_span(text: str, pos: int) -> bool:
    """True if pos is inside an unescaped $...$ or $$...$$ span."""
    n = 0
    for i in range(pos):
        if text[i] == "$" and (i == 0 or text[i - 1] != "\\"):
            n += 1
    return n % 2 == 1


# Characters we auto-wrap with $...$ when they appear bare in prose. This
# is the set of Unicode math chars whose LaTeX form is self-contained (no
# argument needed) — so wrapping each in `$\command$` always renders.
# Excludes fractions (which expand to multi-part \tfrac{}{}) and degree
# symbol (which is typically attached to a preceding number).
WRAPPABLE_BARE_CHARS = frozenset(
    "αβγδεζηθικλμνξπρστυφχψω"  # Greek lowercase
    "ΓΔΘΛΞΠΣΥΦΨΩ"  # Greek uppercase
    "ϵϑϖϱςϕ"  # Greek variants
    "×÷±∓·⋅∗⊕⊖⊗⊙∘"  # Binary operators (adds ⋅ dot-operator)
    "≤≥≠≈≡∼≃≅∝≪≫⊥∥∣"  # Relational
    "∂∇∫∬∭∮∞∑∏√ℏℓ"  # Calculus
    "→←↔⇒⇐⇔↑↓⇌↦"  # Arrows
    "∈∉∋⊂⊃⊆⊇⊄⊅⊈⊉∪∩∅∀∃∄¬∧∨"  # Set theory / logic (adds ⊄⊅⊈⊉)
    "∴∵"  # Logical connectors (therefore, because)
    "ℝℕℤℚℂℙ"  # Blackboard bold
    "∠∡△□"  # Geometry
    "⟨⟩"  # Bra-ket
    "⋯⋮⋱"  # Ellipses — NOT `…` (U+2026): prose uses it ("I think… now")
)

_WRAPPABLE_RE = re.compile("[" + re.escape("".join(WRAPPABLE_BARE_CHARS)) + "]")


def _group_end(text: str, j: int, mask: list[bool]) -> int | None:
    """Index one past the ``}`` closing the ``{`` at ``j`` (a backslash skips
    the next character), or None when it does not close before a newline,
    a math span or the end of the text."""
    depth = 0
    n = len(text)
    k = j
    while k < n:
        if mask[k]:
            return None
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if c == "\n":
            return None
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k + 1
        k += 1
    return None


def _command_name_ends_at(text: str, k: int) -> bool:
    """True when ``text[:k]`` ends with an unescaped ``\\name``."""
    q = k
    while q > 0 and _is_ascii_letter(text[q - 1]):
        q -= 1
    if q == k or q == 0 or text[q - 1] != "\\":
        return False
    run = 0
    while q - 1 - run >= 0 and text[q - 1 - run] == "\\":
        run += 1
    return run % 2 == 1


def attached_group_mask(text: str, mask: list[bool] | None = None) -> list[bool]:
    """``out[i]`` is True when ``text[i]`` lies inside a closed brace group,
    outside math, that belongs to a bare script (``e^{iπ}``, ``x_{α}``) or to
    a bare command's arguments (``\\frac{π}{2}``, ``\\sqrt[3]{2π}``,
    ``\\text{π}``): the character right before the ``{`` is ``^`` or
    ``_``, the end of an unescaped ``\\name``, the ``]`` of an optional
    argument that directly follows a ``\\name``, or the ``}`` of another
    such group. The later wrapping steps put the whole group in one span,
    so the characters inside must not get a span of their own first
    (``$e^{i$\\pi$}$``)."""
    if mask is None:
        mask = math_mask(text)
    n = len(text)
    out = [False] * (n + 1)
    attached_close: set[int] = set()  # end index of each attached group
    i = 0
    while i < n:
        if text[i] == "{" and not mask[i]:
            run = 0
            while i - 1 - run >= 0 and text[i - 1 - run] == "\\":
                run += 1
            end = _group_end(text, i, mask) if run % 2 == 0 else None
            if end is not None:
                prev = text[i - 1] if i > 0 else ""
                attached = (
                    prev in ("^", "_")
                    or _command_name_ends_at(text, i)
                    or (prev == "}" and i in attached_close)
                )
                if not attached and prev == "]":
                    o = text.rfind("[", 0, i - 1)
                    attached = (
                        o > 0
                        and "]" not in text[o + 1 : i - 1]
                        and _command_name_ends_at(text, o)
                    )
                if attached:
                    for k in range(i, end):
                        out[k] = True
                    attached_close.add(end)
        i += 1
    return out


def wrap_bare_unicode_math(text: str, *, skip_attached_groups: bool = True) -> str:
    """Wrap any bare Unicode math char (outside $...$) with `$\\command$`.

    After ftfy normalizes mojibake to clean Unicode, characters like π, ν,
    ×, → may appear outside math spans. flutter_math_fork only renders
    content inside $...$, so bare Unicode renders as plain-font text — a
    typography inconsistency with properly-wrapped math elsewhere in the
    same screen.

    Consecutive wrappable chars are combined into a single span so `ħω`
    becomes `$\\hbar\\omega$` rather than the uglier `$\\hbar$$\\omega$`.
    Whitespace or prose breaks a run, so `α β` stays as two separate spans.

    Only operates on characters whose LaTeX form stands alone (no arguments
    needed). Does not touch chars already inside $...$ spans.
    """
    if not isinstance(text, str) or not text:
        return text
    if not _WRAPPABLE_RE.search(text):
        return text

    mask = math_mask(text)
    # A symbol inside a bare script or command argument group (`e^{iπ}`,
    # `\frac{π}{2}`) is left to the step that wraps the whole group;
    # canonicalize calls this again with the skip off for groups nothing
    # wrapped.
    in_group = attached_group_mask(text, mask) if skip_attached_groups else None
    out: list[str] = []
    last = 0  # text[:last] has been emitted
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if (
            ch in WRAPPABLE_BARE_CHARS
            and not mask[i]
            and (in_group is None or not in_group[i])
        ):
            if ch in _ROOT_CHARS and _root_argument(text, i + 1) is None:
                i += 1  # no radicand: the glyph stays as written (#1654)
                continue
            # The span takes the whole tight cluster around the symbol
            # (`3×4×5`, `x≤5`, `ε₀`, `10⁻³×10²`), so its closing `$` is never
            # followed by a digit (the renderers' closer rule would drop it).
            word = greek_word_at(text, i, mask) if ch in GREEK_MATH_LETTERS else None
            if word is not None and word[0] >= last:
                # `2πr`, `fλ`, `Δx`: the span takes the whole Greek word.
                start = word[0]
                end = cluster_right(text, start, mask)
            else:
                start = cluster_left(text, i, last, mask)
                end = cluster_right(text, i, mask)
            out.append(text[last:start])
            out.append(
                wrap_cluster(text, start, end, convert_cluster(text[start:end]), mask)
            )
            last = i = end
            continue
        i += 1
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Tight clusters: what a new `$…$` span around a bare symbol must take with it
# ---------------------------------------------------------------------------

_ALL_SCRIPT_CHARS = _SUPERSCRIPT_CHARS | _SUBSCRIPT_CHARS
_ASCII_SCRIPT_RE = re.compile(
    r"[_^](?:\{[^{}$\n]*\}|\\[A-Za-z]+|[A-Za-z0-9](?![A-Za-z]))"
)
_NUMBER_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
_NUMBER_CHARS = frozenset("0123456789.,")


def _is_ascii_letter(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z")


def _masked(mask: list[bool] | None, k: int) -> bool:
    return mask is not None and mask[k]


def _left_atom(
    text: str, end: int, floor: int, mask: list[bool] | None, before_subscript: bool
) -> int | None:
    """Start of the number or standalone single letter that ends at ``end``,
    or None when what ends there may not join a span."""
    if end <= floor or _masked(mask, end - 1):
        return None
    c = text[end - 1]
    if "0" <= c <= "9":
        q = end - 1
        while (
            q - 1 >= floor and text[q - 1] in _NUMBER_CHARS and not _masked(mask, q - 1)
        ):
            q -= 1
        while text[q] in ".,":
            q += 1
        prev = text[q - 1] if q >= 1 else ""
        # A script argument (`10^2`), an escaped or currency dollar (`\$5`,
        # the canonicalize sentinel ending in U+E001) or a word (`CO2`) owns
        # the number.
        if prev and (
            prev in "\\^_$\ue001"
            or (_is_ascii_letter(prev) and not _standalone_letter(text, q - 1))
        ):
            return None
        return q
    if _is_ascii_letter(c):
        p = end - 1
        prev = text[p - 1] if p >= 1 else ""
        if _is_ascii_letter(prev) or (prev and prev in "\\^_"):
            return None
        # An uppercase letter with a subscript digit is chemistry (`H₂`),
        # which `wrap_unicode_chemistry` sets upright later.
        if before_subscript and c.isupper():
            return None
        return p
    return None


def _standalone_letter(text: str, k: int) -> bool:
    return (
        _is_ascii_letter(text[k])
        and (k == 0 or not _is_ascii_letter(text[k - 1]))
        and (k + 1 >= len(text) or not _is_ascii_letter(text[k + 1]))
    )


# Operators and relations whose operands are pulled into the span: `3×4`,
# `x≤5`, `n→∞`, `a∈A`. Letters next to other symbols stay outside (`µs`,
# `kΩ` and `J·s` are units; `2√3` and `2π` keep their Backend #1654 shape).
JOINING_CHARS: frozenset[str] = frozenset("×÷±∓≤≥≠≈≡∼≃≅∝≪≫→←↔⇒⇐⇔⇌↦∈∉⊂⊃⊆⊇∪∩∧∨")
JOINING_COMMANDS: frozenset[str] = frozenset(
    {UNICODE_MATH[c][1:] for c in JOINING_CHARS}
    | {"le", "ge", "ne", "to", "implies", "iff"}
)
_JOINING_COMMAND_RE = re.compile(
    r"\\(?:"
    + "|".join(sorted(JOINING_COMMANDS, key=len, reverse=True))
    + r")(?![A-Za-z])"
)


def _joining_at(text: str, p: int) -> bool:
    """True when a joining operator (character or command) starts at ``p``."""
    if p >= len(text):
        return False
    return text[p] in JOINING_CHARS or (
        text[p] == "\\" and _JOINING_COMMAND_RE.match(text, p) is not None
    )


# ---------------------------------------------------------------------------
# Greek words: `2πr`, `fλ`, `hν`, `Δx`, `ωt` are one span (audit round 3)
# ---------------------------------------------------------------------------

# The Greek letters (and ℏ) that `UNICODE_MATH` maps to a command. A word
# made of these plus ASCII letters, digits and Unicode scripts is one math
# term. Accented Greek (`ό`, `ά`) and capitals that look Latin (`Ε`) are not
# in the set, so Greek-language prose never forms such a word.
GREEK_MATH_LETTERS: frozenset[str] = frozenset(
    "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΥΦΨΩϵϑϖϱςϕℏ"
)
# A Greek word that is a unit keeps today's shape (`$\mu$s`, `k$\Omega$`):
# an optional number, then μ + a unit symbol, or an SI prefix + Ω (+ m/cm
# for ohm-metre), then optional Unicode scripts (`μm²`).
GREEK_UNIT_SYMBOLS: tuple[str, ...] = (
    "s m g l L A V W F H J C K T N S M Pa Hz Wb eV mol"
).split()
_GREEK_UNIT_RE = re.compile(
    r"[0-9]*(?:[.,][0-9]+)*(?:[kMGTmμµnp]?Ω(?:c?m)?|[μµ](?:"
    + "|".join(sorted(GREEK_UNIT_SYMBOLS, key=len, reverse=True))
    + r"|Ω)?)["
    + re.escape("".join(sorted(_SUPERSCRIPT_CHARS | _SUBSCRIPT_CHARS)))
    + r"]*"
)
_THREE_ASCII_LETTERS_RE = re.compile(r"[A-Za-z]{3}")
_THREE_GREEK_RE = re.compile(
    "[" + re.escape("".join(sorted(GREEK_MATH_LETTERS))) + "]{3}"
)
_CHEM_IN_WORD_RE = re.compile(
    "[A-Z][" + re.escape("".join(sorted(_SUBSCRIPT_CHARS))) + "]"
)


def _greek_word_char(text: str, k: int, mask: list[bool] | None) -> bool:
    if k < 0 or k >= len(text) or _masked(mask, k):
        return False
    c = text[k]
    if c in GREEK_MATH_LETTERS or c in _SUPERSCRIPT_CHARS or c in _SUBSCRIPT_CHARS:
        return True
    if c.isascii() and c.isalnum():
        return True
    # `.` / `,` only inside a number (`2.5λ`)
    return (
        c in ".,"
        and 0 < k < len(text) - 1
        and "0" <= text[k - 1] <= "9"
        and "0" <= text[k + 1] <= "9"
        and not _masked(mask, k - 1)
        and not _masked(mask, k + 1)
    )


def greek_word_at(
    text: str, k: int, mask: list[bool] | None = None
) -> tuple[int, int] | None:
    """``(start, end)`` of the Greek word containing ``text[k]``, or None.

    A Greek word is a maximal run, with no whitespace, of Greek math letters
    (``GREEK_MATH_LETTERS``), ASCII letters, digits (``.``/``,`` between
    digits) and Unicode scripts that contains at least one Greek letter and
    one ASCII letter or digit: ``2πr``, ``fλ``, ``Δx``, ``ωt``, ``πr²``. It
    is refused when it has 3+ ASCII letters in a row (``αβγtest``,
    ``Thetaα``, ``sinθ``), 3+ Greek letters in a row, an uppercase letter
    with a subscript (chemistry, ``ΔH₂O``), when it is a unit
    (``_GREEK_UNIT_RE``: ``µs``, ``kΩ``, ``10Ω``, ``5μm²``), or when it
    touches another word or a script: the character before it is a letter
    or digit of any script, ``\\ ^ _ { $`` or the canonicalize dollar
    sentinel; the character after it is a letter or digit of any script."""
    if not _greek_word_char(text, k, mask):
        return None
    s = k
    while _greek_word_char(text, s - 1, mask):
        s -= 1
    e = k + 1
    while _greek_word_char(text, e, mask):
        e += 1
    word = text[s:e]
    if not any(c in GREEK_MATH_LETTERS for c in word):
        return None
    if not any(c.isascii() and c.isalnum() for c in word):
        return None
    if s > 0 and not _masked(mask, s - 1):
        b = text[s - 1]
        if b.isalnum() or b in "\\^_{$\ue001":
            return None
    if e < len(text) and not _masked(mask, e) and text[e].isalnum():
        return None
    if (
        _THREE_ASCII_LETTERS_RE.search(word)
        or _THREE_GREEK_RE.search(word)
        or _CHEM_IN_WORD_RE.search(word)
        or _GREEK_UNIT_RE.fullmatch(word)
    ):
        return None
    return s, e


def cluster_left(
    text: str, start: int, floor: int, mask: list[bool] | None = None
) -> int:
    """Move ``start`` left over the tight operands a new span must include,
    when the cluster starts with a joining operator (``JOINING_CHARS`` /
    ``JOINING_COMMANDS``): numbers (``3.14``, ``1,00,000``), standalone
    single letters (``x`` in ``x≤5``, not ``abc``) and Unicode scripts
    attached to one of those. Never below ``floor``, never into a math span,
    a word, a script argument (``10^2``) or a currency amount (``\\$5``)."""
    if not _joining_at(text, start):
        return start
    while start > floor and not _masked(mask, start - 1):
        c = text[start - 1]
        if c in _ALL_SCRIPT_CHARS:
            q = start - 1
            while (
                q - 1 >= floor
                and text[q - 1] in _ALL_SCRIPT_CHARS
                and not _masked(mask, q - 1)
            ):
                q -= 1
            b = _left_atom(text, q, floor, mask, text[q] in _SUBSCRIPT_CHARS)
        else:
            b = _left_atom(text, start, floor, mask, False)
        if b is None:
            break
        start = b
    return start


def cluster_right(
    text: str,
    pos: int,
    mask: list[bool] | None = None,
    command_re: "re.Pattern[str] | None" = None,
) -> int:
    """End of the tight cluster that starts at ``pos``: a run of wrappable
    symbols (a radical with its radicand), bare symbol commands matched by
    ``command_re``, numbers, ASCII scripts (``_1``, ``^{2}``), Unicode
    script runs, and a standalone single letter right after a joining
    operator (``x→y``), with nothing between them."""
    n = len(text)
    p = pos
    after_joining = False
    while p < n and not _masked(mask, p):
        c = text[p]
        joining = False
        word = (
            greek_word_at(text, p, mask)
            if c in GREEK_MATH_LETTERS or (c.isascii() and c.isalnum())
            else None
        )
        if word is not None and word[0] >= pos:
            p = word[1]  # `2πr`, `Δx`: the whole Greek word
        elif c in WRAPPABLE_BARE_CHARS:
            if c in _ROOT_CHARS:
                arg = _root_argument(text, p + 1)
                if arg is None:
                    break
                p = arg[1]
            else:
                joining = c in JOINING_CHARS
                p += 1
        elif c in _ALL_SCRIPT_CHARS:
            while p < n and text[p] in _ALL_SCRIPT_CHARS and not _masked(mask, p):
                p += 1
        elif c == "\\" and command_re is not None:
            m = command_re.match(text, p)
            if not m:
                break
            joining = _joining_at(text, p)
            p = m.end()
        elif c in "_^":
            if p == pos:
                break
            m = _ASCII_SCRIPT_RE.match(text, p)
            if not m or "$" in m.group(0):
                break
            p = m.end()
        elif "0" <= c <= "9":
            p = _NUMBER_RE.match(text, p).end()  # type: ignore[union-attr]
        elif _is_ascii_letter(c):
            nxt = text[p + 1] if p + 1 < n else ""
            if not after_joining or (p > 0 and _is_ascii_letter(text[p - 1])):
                break
            if _is_ascii_letter(nxt) or nxt == "(":
                break
            if c.isupper() and nxt and nxt in _SUBSCRIPT_CHARS:
                break  # chemistry (`5H₂O`): left to wrap_unicode_chemistry
            p += 1
        else:
            break
        after_joining = joining
    return p


def convert_cluster(cluster: str) -> str:
    """LaTeX for a cluster: symbols → commands (a radical takes its
    radicand), a run of Unicode scripts → one ``^{…}`` / ``_{…}``, anything
    else as written; a space only where a command would run into a letter."""
    parts: list[str] = []
    n = len(cluster)
    i = 0
    while i < n:
        c = cluster[i]
        step = 1
        if c in _ALL_SCRIPT_CHARS:
            table = _SUPERSCRIPT_CHARS if c in _SUPERSCRIPT_CHARS else _SUBSCRIPT_CHARS
            j = i
            inner: list[str] = []
            while j < n and cluster[j] in table:
                inner.append(UNICODE_MATH[cluster[j]][2:-1])
                j += 1
            rep = ("^{" if table is _SUPERSCRIPT_CHARS else "_{") + "".join(inner) + "}"
            step = j - i
        elif c in _ROOT_CHARS and _root_argument(cluster, i + 1) is not None:
            inner_text, end = _root_argument(cluster, i + 1)  # type: ignore[misc]
            rep = UNICODE_MATH[c] + "{" + _replace_chars(inner_text) + "}"
            step = end - i
        elif c in WRAPPABLE_BARE_CHARS:
            rep = UNICODE_MATH[c]
        else:
            rep = c
        if parts and _needs_terminator(parts[-1], rep[0]):
            parts.append(" ")
        parts.append(rep)
        i += step
    return "".join(parts)


def wrap_cluster(
    text: str, start: int, end: int, latex: str, mask: list[bool] | None = None
) -> str:
    """``$latex$`` for ``text[start:end]``, padded with one space where the
    neighbour would break the span: a literal ``$`` right before or after
    (``$$`` would open display math) or a digit right after (a closer
    followed by a digit is not a closer)."""
    head = ""
    tail = ""
    if start > 0 and text[start - 1] == "$" and not _masked(mask, start - 1):
        if start < 2 or text[start - 2] != "\\":
            head = " "
    if end < len(text) and not _masked(mask, end):
        nxt = text[end]
        if nxt == "$" or nxt.isdigit():
            tail = " "
    return head + "$" + latex + "$" + tail
