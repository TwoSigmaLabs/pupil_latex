"""`to_plain`: LaTeX to plain Unicode text for PDFs, canvases, grading and TTS.

The `text` / `pdf` styles are Backend `services/baa_render_meta.latex_to_plain`
verbatim (2026-09-25, includes #1368, #1599, #1745). The `tts` style is the
agents' `_clean_script_for_tts` applied through `segment`.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from .commands import KATEX_COMMANDS, SCRIPT_LABELS
from .normalize import currency_positions
from .repair import repair
from .segment import segment
from .spans import math_mask

# Greek letters + common math operators that appear in physics/chem answers.
LATEX_CMD_MAP: Dict[str, str] = {
    # Greek (lowercase)
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "omicron": "ο",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "varepsilon": "ε",
    "vartheta": "ϑ",
    "varphi": "φ",
    "varpi": "ϖ",
    "varrho": "ϱ",
    "varsigma": "ς",
    # Greek (uppercase)
    "Alpha": "Α",
    "Beta": "Β",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Epsilon": "Ε",
    "Zeta": "Ζ",
    "Eta": "Η",
    "Theta": "Θ",
    "Iota": "Ι",
    "Kappa": "Κ",
    "Lambda": "Λ",
    "Mu": "Μ",
    "Nu": "Ν",
    "Xi": "Ξ",
    "Omicron": "Ο",
    "Pi": "Π",
    "Rho": "Ρ",
    "Sigma": "Σ",
    "Tau": "Τ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Chi": "Χ",
    "Psi": "Ψ",
    "Omega": "Ω",
    # Operators / symbols
    "times": "×",
    "div": "÷",
    "pm": "±",
    "mp": "∓",
    "cdot": "·",
    "cdots": "···",
    "ldots": "…",
    "dots": "…",
    "leq": "≤",
    "geq": "≥",
    "neq": "≠",
    "approx": "≈",
    "equiv": "≡",
    "sim": "~",
    "propto": "∝",
    "infty": "∞",
    "to": "→",
    "rightarrow": "→",
    "leftarrow": "←",
    "Rightarrow": "⇒",
    "Leftarrow": "⇐",
    "circ": "°",
    "degree": "°",
    "deg": "°",
    "angstrom": "Å",
    "sqrt": "√",
    "int": "∫",
    "iint": "∬",
    "oint": "∮",
    "sum": "Σ",
    "prod": "Π",
    "partial": "∂",
    "nabla": "∇",
    "emptyset": "∅",
    "varnothing": "∅",
    "in": "∈",
    "notin": "∉",
    "subset": "⊂",
    "subseteq": "⊆",
    "supset": "⊃",
    "supseteq": "⊇",
    "cup": "∪",
    "cap": "∩",
    "forall": "∀",
    "exists": "∃",
    "therefore": "∴",
    "because": "∵",
    "perp": "⊥",
    "parallel": "∥",
    "triangle": "△",
    "square": "□",
    "star": "★",
    "ast": "∗",
    "leftrightarrow": "↔",
    "Leftrightarrow": "⇔",
    "implies": "⇒",
    "iff": "⇔",
    "lim": "lim",
    "max": "max",
    "min": "min",
    # Seen in live in-class content (frequency-ordered from a scan of
    # student submissions); without these they rendered as the
    # bare command name, e.g. "\colon" → "colon".
    "angle": "∠",
    "colon": ":",
    "mid": "|",
    "le": "≤",
    "ge": "≥",
    "cong": "≅",
    "simeq": "≃",
    "arcsin": "arcsin",
    "arccos": "arccos",
    "arctan": "arctan",
    "sinh": "sinh",
    "cosh": "cosh",
    "tanh": "tanh",
    "quad": " ",
    "qquad": "  ",
    "ne": "≠",
    "lt": "<",
    "gt": ">",
    "prime": "′",
    # Accent/style wrappers: drop the command and keep the argument, which
    # the trailing brace-strip then unwraps (`\hat{n}` → `{n}` → `n`).
    "hat": "",
    "vec": "",
    # Sizing pairs. These MUST be present: without them the prefix-peeling
    # fallback below matches "le" inside "left" and renders `\left(` as
    # `≤ft(` — the single most visible corruption in physics content, which
    # uses sized bracket pairs constantly.
    "left": "",
    "right": "",
    # Arrows that START with "left"/"right" must be listed explicitly: the
    # prefix-peeling fallback would otherwise strip the sizing command out of
    # them and leave "leftharpoons" behind.
    "longrightarrow": "⟶",
    "longleftarrow": "⟵",
    "longleftrightarrow": "⟷",
    "Longrightarrow": "⟹",
    "Longleftarrow": "⟸",
    "rightleftharpoons": "⇌",
    "leftrightharpoons": "⇋",
    "rightharpoonup": "⇀",
    "rightharpoondown": "⇁",
    "leftharpoonup": "↼",
    "leftharpoondown": "↽",
    "rightarrowtail": "↣",
    "leftarrowtail": "↢",
    "big": "",
    "Big": "",
    "bigg": "",
    "Bigg": "",
    # Accents that carry no Unicode combining form worth the trouble; the
    # base symbol is what a plain-text reader needs.
    "dot": "",
    "ddot": "",
    "check": "",
    "breve": "",
    "acute": "",
    "grave": "",
    "widehat": "",
    "widetilde": "",
    "boldsymbol": "",
    "mathfrak": "",
    "mathsf": "",
    "limits": "",
    "nolimits": "",
    "bar": "",
    "lvert": "|",
    "rvert": "|",
    "vert": "|",
    "lVert": "‖",
    "rVert": "‖",
    "Vert": "‖",
    "lbrace": "{",
    "rbrace": "}",
    "langle": "⟨",
    "rangle": "⟩",
    "lfloor": "⌊",
    "rfloor": "⌋",
    "lceil": "⌈",
    "rceil": "⌉",
    "tilde": "",
    "overline": "",
    "underline": "",
    "mathbb": "",
    "mathcal": "",
    "displaystyle": "",
    # Trig / log — keep the name so the reader sees plain "sin", "cos", etc.
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "cot": "cot",
    "sec": "sec",
    "csc": "csc",
    "log": "log",
    "ln": "ln",
    "exp": "exp",
    # Added 2026-09-25 (review F15): real commands the map lacked were
    # being split at a shorter known prefix (neg became ne + g).
    "neg": "¬",
    "lnot": "¬",
    "top": "⊤",
    "bot": "⊥",
    "inf": "inf",
    "sup": "sup",
    "det": "det",
    "dim": "dim",
    "gcd": "gcd",
    "pmod": "mod",
    "bmod": "mod",
    "leqslant": "≤",
    "geqslant": "≥",
    "newline": " ",
    "intercal": "⊺",
    "land": "∧",
    "lor": "∨",
    "setminus": "∖",
    "oplus": "⊕",
    "otimes": "⊗",
    "ll": "≪",
    "gg": "≫",
    "uparrow": "↑",
    "downarrow": "↓",
    "mapsto": "↦",
    "hookrightarrow": "↪",
    "nearrow": "↗",
    "searrow": "↘",
    "Uparrow": "⇑",
    "Downarrow": "⇓",
    "aleph": "ℵ",
    "hbar": "ℏ",
    "ell": "ℓ",
    "Re": "Re",
    "Im": "Im",
    "vdots": "⋮",
    "ddots": "⋱",
    "bullet": "•",
    "dagger": "†",
    "checkmark": "✓",
    "textmu": "µ",
    "cbrt": "∛",
    # Unit-ish helpers that show up wrapped as commands
    "AA": "Å",
}


_SUPERSCRIPT_MAP = str.maketrans(
    "0123456789+-=()ni",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ",
)
_SUBSCRIPT_MAP = str.maketrans(
    "0123456789+-=()aeoxhklmnpst",
    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ",
)


# `\{`, `\}` and `\$` are literal characters, not grouping or maths
# delimiters. They are parked as sentinels for the duration of the transform
# so neither the delimiter passes nor the brace scanner can consume them, then
# restored. Single private-use characters (U+E010–U+E014): one code unit,
# so an argument reader can never take half of one (`$\binom$"}`).
_LBRACE_SENTINEL = "\ue010"
_RBRACE_SENTINEL = "\ue011"
_DOLLAR_SENTINEL = "\ue012"
_LABEL_SENTINEL_OPEN = "\ue013"
_LABEL_SENTINEL_CLOSE = "\ue014"

# A lesson-script label at the start of a line (`\instruction:`, `\heading:`,
# `\mindmap:`): a lowercase word right after a backslash and before `:`. It
# is parked before the command scanner, which read `\instruction` as `\in` +
# "struction" (∈struction). `text` keeps it verbatim (the canvas reads the
# labels); `pdf` and `compare` drop the backslash, as `tts` always did.
_SCRIPT_LABEL_LINE_RE = re.compile(r"(^|\n)([ \t]*)\\([a-z][a-z_]*):")
# Anywhere in a line, only a word in `SCRIPT_LABELS` is a label.
_SCRIPT_LABEL_ANY_RE = re.compile(r"\\([a-z][a-z_]*):")

# Math spans for the prose-brace pass, display first: the same shapes the
# delimiter strip below removes.
_PLAIN_SPAN_RE = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$]+\$")
_SIMPLE_FRACTION_PART_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?|[^\W\d_]")


def _matching_brace(s: str, k: int, skip: Optional[bytearray] = None) -> int:
    """Index of the `}` closing the `{` at ``k``, or -1. Positions marked in
    ``skip`` (math spans) are not counted."""
    depth = 0
    for j in range(k, len(s)):
        if skip is not None and skip[j]:
            continue
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _command_name_ending_at(s: str, end: int) -> Optional[str]:
    """The name of the `\\name` whose last letter is ``s[end - 1]``, or None."""
    j = end
    while j > 0 and ("a" <= s[j - 1] <= "z" or "A" <= s[j - 1] <= "Z"):
        j -= 1
    if j < end and j > 0 and s[j - 1] == "\\":
        return s[j:end]
    return None


def _attached_brace(s: str, k: int, closes: set) -> bool:
    """True when the `{` at ``k`` is a command or script argument: right
    after `^`/`_`, a `\\name`, the `]` of an optional argument that follows a
    `\\name`, or the `}` of another argument; or after spaces when the
    command takes arguments (`\\frac {a}{b}`)."""
    if k == 0:
        return False
    prev = s[k - 1]
    if prev in "^_" or (k - 1) in closes:
        return True
    if prev == "]":
        opener = s.rfind("[", 0, k - 1)
        return opener > 0 and _command_name_ending_at(s, opener) is not None
    if prev in " \t":
        j = k - 1
        while j > 0 and s[j - 1] in " \t":
            j -= 1
        return _command_name_ending_at(s, j) in _ARGUMENT_TAKING_CMDS
    return _command_name_ending_at(s, k) is not None


# A prose brace pair is a literal set / JSON object when its content holds
# one of these (a list or key separator).
_LITERAL_BRACE_HINTS = frozenset(",:;|")


def _protect_prose_braces(s: str) -> str:
    """Braces in prose (outside `$…$`/`$$…$$` and not a command or script
    argument) whose content is a list or object (`A = {1, 2, 3}`,
    `{x | x > 0}`, `{"central": …}`: a `,` `:` `;` or `|` inside, more than
    one character) are text. They are parked as the `\\{`/`\\}` sentinels.
    `1{,}000` and `{x}` are still LaTeX grouping, an unclosed `{` is kept,
    and a `}` with no opener is dropped as before."""
    if "{" not in s:
        return s
    n = len(s)
    in_math = bytearray(n)
    for m in _PLAIN_SPAN_RE.finditer(s):
        for j in range(m.start(), m.end()):
            in_math[j] = 1
    chars = list(s)
    closes: set = set()
    k = 0
    while k < n:
        if in_math[k] or s[k] != "{":
            k += 1
            continue
        close = _matching_brace(s, k, in_math)
        if _attached_brace(s, k, closes):
            if close == -1:
                break
            closes.add(close)
            k = close + 1
            continue
        if close == -1:
            chars[k] = _LBRACE_SENTINEL
            k += 1
            continue
        inner = s[k + 1 : close]
        if len(inner) <= 1 or not any(c in _LITERAL_BRACE_HINTS for c in inner):
            k = close + 1  # `{,}`, `{x}`: grouping
            continue
        chars[k] = _LBRACE_SENTINEL
        chars[close] = _RBRACE_SENTINEL
        k += 1
    return "".join(chars)


_IMAGE_MARKER_RE = re.compile(r"\{\{IMAGE:[^}]+\}\}")
# `$5`, `$1,200.50`: a dollar before an amount that is not followed by a
# letter, a command or a script (`$45m`, `$4\sqrt{3}` are cut-off spans).
_CURRENCY_AT_RE = re.compile(r"\$[0-9]+(?:[.,][0-9]+)*(?![0-9A-Za-z\\^_{])")


def _park_currency_dollars(s: str) -> str:
    """Park the amounts (tag `audit5-1`): a dollar outside every `segment`
    math span that `escape_currency` reads as money (`Rs $5 and $10`: the
    closer is followed by a digit; `costs $5.`: no closer) and that is
    followed by an amount, not by a letter or a command (`$45m`, `$4\\sqrt3`
    are cut-off spans). It becomes the literal-dollar sentinel, so the
    delimiter strip below can no longer pair it with another amount."""
    if "$" not in s:
        return s
    money = currency_positions(s)
    if not money:
        return s
    in_math = math_mask(s)
    chars = list(s)
    for k in money:
        if not in_math[k] and _CURRENCY_AT_RE.match(s, k):
            chars[k] = _DOLLAR_SENTINEL
    return "".join(chars)


_LATEX_DISPLAY_DOLLAR_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_LATEX_DELIM_RE = re.compile(r"\$([^$]+)\$")
# A literal ``\n`` escape that survived into the stored string, e.g.
# "...\nStatement II:". The command scanner is greedy and would eat it as a
# command named "nStatement", dropping the line break and leaving a stray "n"
# glued to the next word — ~2k occurrences in live in-class content. Only
# fires before an uppercase letter or whitespace, so the real commands that
# start with "n" (\nu, \neq, \nabla, \notin) are untouched.
_LATEX_NEWLINE_ESCAPE_RE = re.compile(r"\\n(?=[A-Z\s]|$)")

# A control word. A run of backslashes before the letters is one command: a
# double-escaped ``\\frac`` is the same fraction, not a line break + "frac".
_LATEX_CMD_RE = re.compile(r"\\+([A-Za-z]+)")
_LATEX_ENV_TOKEN_RE = re.compile(r"\\(begin|end)\s*\{([^{}]*)\}")

_FRAC_CMDS = frozenset({"frac", "dfrac", "tfrac", "cfrac"})
_BINOM_CMDS = frozenset({"binom", "dbinom", "tbinom"})
# Wrappers whose only job is styling or chemistry markup — the inner content
# is the answer. `\textit` and friends were once missing and reached the
# teacher as `textitSalmonella typhi`.
_WRAPPER_CMDS = frozenset(
    {
        "text",
        "textit",
        "textbf",
        "textrm",
        "textsf",
        "texttt",
        "textsc",
        "textup",
        "textnormal",
        "mathrm",
        "mathit",
        "mathbf",
        "mathsf",
        "mathtt",
        "mathbb",
        "mathcal",
        "mathfrak",
        "mathscr",
        "boldsymbol",
        "bm",
        "operatorname",
        "emph",
        "mbox",
        "hbox",
        "ce",
        # Boxes, strikes and braces around content: the content is the answer.
        "boxed",
        "fbox",
        "cancel",
        "bcancel",
        "xcancel",
        "sout",
        "underbrace",
        "overbrace",
        "pu",
    }
)
# `\color{red}{5}` / `	extcolor{red}{5}`: the colour name is styling and the
# second argument is the content. `\color{red} 5` (a switch) keeps what follows.
_COLOR_CMDS = frozenset({"color", "textcolor", "colorbox"})
# Layout with no reading value: the command AND its argument go. Left as
# unknown commands they reached the reader as "hspace1cm", "labeleq1".
_DROP_WITH_ARG_CMDS = frozenset(
    {
        "hspace",
        "vspace",
        "phantom",
        "hphantom",
        "vphantom",
        "label",
        "tag",
        "kern",
        "mkern",
        "mspace",
        "hskip",
    }
)
# Accents: (combining mark, name). By default the base symbol is kept and the
# accent dropped (what grading and the in-class report have always done); a
# report that must keep the meaning of `\vec{F}` asks for ``mark_accents``.
_ACCENT_CMDS = {
    "vec": ("\u20d7", "vec"),
    "overrightarrow": ("\u20d7", "vec"),
    "overleftarrow": ("\u20d6", "vec"),
    "hat": ("\u0302", "hat"),
    "widehat": ("\u0302", "hat"),
    "bar": ("\u0304", "bar"),
    "overline": ("\u0305", "bar"),
    "dot": ("\u0307", "dot"),
    "ddot": ("\u0308", "ddot"),
    "tilde": ("\u0303", "tilde"),
    "widetilde": ("\u0303", "tilde"),
}
_PLAIN_ACCENT_CMDS = frozenset(
    {"check", "breve", "acute", "grave", "underline", "mathring"}
)
# `\left.` / `\right.` are invisible delimiters; every sizing command is
# dropped and the delimiter it sizes kept.
_SIZING_CMDS = frozenset(
    {
        "left",
        "right",
        "big",
        "Big",
        "bigg",
        "Bigg",
        "bigl",
        "bigr",
        "Bigl",
        "Bigr",
        "biggl",
        "biggr",
        "Biggl",
        "Biggr",
        "middle",
    }
)
_DROP_CMDS = frozenset(
    {
        "hline",
        "nonumber",
        "notag",
        "textstyle",
        "scriptstyle",
        "displaystyle",
        "scriptscriptstyle",
    }
)
_MATRIX_ENVS = {
    "matrix": ("[", "]"),
    "pmatrix": ("[", "]"),
    "bmatrix": ("[", "]"),
    "Bmatrix": ("[", "]"),
    "smallmatrix": ("[", "]"),
    "array": ("[", "]"),
    "vmatrix": ("|", "|"),
    "Vmatrix": ("‖", "‖"),
}
# Commands whose `{…}` argument may follow after spaces (prose-brace pass).
_ARGUMENT_TAKING_CMDS = (
    _FRAC_CMDS
    | _BINOM_CMDS
    | _WRAPPER_CMDS
    | _COLOR_CMDS
    | _DROP_WITH_ARG_CMDS
    | frozenset(_ACCENT_CMDS)
    | _PLAIN_ACCENT_CMDS
    | frozenset({"sqrt", "begin", "end"})
)

# Characters that read correctly as a superscript without a Unicode script
# form: primes and the degree sign (`0^\circ` → `0°`).
_SCRIPT_PASSTHROUGH = frozenset("°′″‴")
_SUPERSCRIPT_CHARS = frozenset("0123456789+-=()ni")
_SUBSCRIPT_CHARS = frozenset("0123456789+-=()aeoxhklmnpst")
_SINGLE_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|.", re.DOTALL)
_SCRIPT_SPACE_RE = re.compile(r"\s*([^\w\s])\s*")

# NOT stripping the space after a command is deliberate. LaTeX itself eats it
# (``\Delta p`` is "Δp"), but by the time this runs the ``$...$`` delimiters are
# already gone, so a space that was OUTSIDE the maths cannot be told from one
# inside it — and "$\leq$ and $\geq$" collapsed to "≤and ≥and". Losing a word
# boundary is a real corruption; a cosmetic "Δ p" is not.


def _to_super(s: str) -> str:
    """Best-effort Unicode superscript. Untranslatable chars fall through."""
    return s.translate(_SUPERSCRIPT_MAP)


def _to_sub(s: str) -> str:
    return s.translate(_SUBSCRIPT_MAP)


def _read_group(s: str, i: int) -> Tuple[str, int]:
    """``s[i]`` is ``{``: return the balanced inner text (any depth) and the
    index after its closing brace. An unclosed group runs to the end."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
    return s[i + 1 :], len(s)


def _read_arg(s: str, i: int) -> Tuple[Optional[str], int]:
    """One macro argument at ``i`` (leading spaces skipped, as in LaTeX): a
    braced group, a control word, or a single character."""
    j = i
    while j < len(s) and s[j] in " \t":
        j += 1
    if j >= len(s) or s[j] == "}":
        return None, i
    if s[j] == "{":
        return _read_group(s, j)
    m = _LATEX_CMD_RE.match(s, j)
    if m:
        return m.group(0), m.end()
    return s[j], j + 1


def _is_wrapped(body: str) -> bool:
    """True when ``body`` is one parenthesised group: "(a+b)", not "(a)/(b)"."""
    if not (body.startswith("(") and body.endswith(")")):
        return False
    depth = 0
    for k, ch in enumerate(body):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and k < len(body) - 1:
            return False
    return depth == 0


def _script(body: str, marker: str) -> str:
    """Render a converted sub/superscript body. Unicode script characters only
    when EVERY character has one — a half-converted "vₐvg" reads as a
    different word — otherwise ``_x`` / ``_(avg)``."""
    body = _SCRIPT_SPACE_RE.sub(r"\1", body).strip()
    if not body:
        return ""
    if marker == "^":
        chars, table = _SUPERSCRIPT_CHARS, _SUPERSCRIPT_MAP
    else:
        chars, table = _SUBSCRIPT_CHARS, _SUBSCRIPT_MAP
    if marker == "^" and all(ch in _SCRIPT_PASSTHROUGH for ch in body):
        return body
    if all(ch in chars for ch in body):
        return body.translate(table)
    if len(body) == 1:
        return marker + body
    return f"{marker}({body})"


def _split_table(content: str) -> List[List[str]]:
    """Split an environment body into rows (``\\\\``) of cells (``&``) at the
    top level — separators inside braces or a nested environment belong to
    that inner construct."""
    rows: List[List[str]] = []
    cells: List[str] = []
    buf: List[str] = []
    depth = env_depth = 0
    i, n = 0, len(content)
    while i < n:
        c = content[i]
        if c == "\\":
            m = _LATEX_ENV_TOKEN_RE.match(content, i)
            if m:
                env_depth += 1 if m.group(1) == "begin" else -1
                buf.append(m.group(0))
                i = m.end()
                continue
            if content.startswith("\\\\", i) and depth == 0 and env_depth == 0:
                cells.append("".join(buf))
                rows.append(cells)
                cells, buf = [], []
                i += 2
                continue
            # Copy the escape whole so an escaped "\&" is never split on.
            buf.append(content[i : i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "&" and depth == 0 and env_depth == 0:
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append("".join(buf))
    rows.append(cells)
    return rows


def _environment(name: str, content: str, mark_accents: bool) -> str:
    """``pmatrix`` → ``[a b; c d]``, ``vmatrix`` → ``|a b; c d|``, ``cases`` →
    ``a, x>0; b, x≤0``; any other environment (aligned, …) → rows joined by
    "; " with the alignment points dropped."""
    base = name.rstrip("*")
    if base == "array":
        k = 0
        while k < len(content) and content[k] in " \t":
            k += 1
        if k < len(content) and content[k] == "{":
            content = content[_read_group(content, k)[1] :]
    rows = []
    for raw_cells in _split_table(content):
        cells = [_convert(cell, mark_accents).strip() for cell in raw_cells]
        if any(cells):
            rows.append(cells)
    if base in _MATRIX_ENVS:
        opener, closer = _MATRIX_ENVS[base]
        body = "; ".join(" ".join(c for c in row if c) for row in rows)
        return f"{opener}{body}{closer}"
    joiner = ", " if base == "cases" else ""
    return "; ".join(joiner.join(c for c in row if c) for row in rows)


def _fraction_part(part: str) -> str:
    """A numerator or denominator: a single token (a number or one letter,
    `22`, `3.5`, `x`, `π`) or one parenthesised group stays bare; anything
    compound gets parentheses (`(a+b)`)."""
    core = part.strip()
    if _SIMPLE_FRACTION_PART_RE.fullmatch(core) or _is_wrapped(core):
        return core
    return f"({part})"


def _fraction_needs_parens(out: List[str], s: str, i: int) -> bool:
    """`2\\frac{1}{2}` and `\\frac{1}{2}x` read `2(1/2)` and `(1/2)x`: a
    fraction touching a term (a letter or digit before it, a letter, digit,
    `(`, `\\`, `^`, `_` or `{` after it, or a `/` before it) is parenthesised
    so it is not read as `21/2` or `1/2x`."""
    prev = ""
    for piece in reversed(out):
        if piece:
            prev = piece[-1]
            break
    nxt = s[i] if i < len(s) else ""
    return (
        (prev.isalnum() or prev == "/")
        or nxt.isalnum()
        or (nxt != "" and nxt in "(\\^_{")
    )


def _command(name: str, s: str, j: int, mark_accents: bool) -> Tuple[str, int]:
    """Render control word ``\\name`` whose arguments start at ``j``. Returns
    the text and the index after everything consumed."""
    if name in _FRAC_CMDS or name in _BINOM_CMDS:
        num, j = _read_arg(s, j)
        den, j = _read_arg(s, j)
        a = _convert(num or "", mark_accents)
        b = _convert(den or "", mark_accents)
        if name in _FRAC_CMDS:
            return f"{_fraction_part(a)}/{_fraction_part(b)}", j
        return f"C({a}, {b})", j
    if name == "sqrt":
        k = j
        while k < len(s) and s[k] in " \t":
            k += 1
        root = "√"
        if k < len(s) and s[k] == "[":
            close = s.find("]", k)
            if close != -1:
                index = _convert(s[k + 1 : close], mark_accents).strip()
                j = close + 1
                if index and all(ch in _SUPERSCRIPT_CHARS for ch in index):
                    root = index.translate(_SUPERSCRIPT_MAP) + "√"
                elif index:
                    root = f"({index})√"
        arg, j = _read_arg(s, j)
        body = _convert(arg or "", mark_accents)
        if not body or _SINGLE_TOKEN_RE.fullmatch(body) or _is_wrapped(body):
            return root + body, j
        return f"{root}({body})", j
    if name in _WRAPPER_CMDS:
        arg, j = _read_arg(s, j)
        return _convert(arg or "", mark_accents), j
    if name in _COLOR_CMDS:
        _colour, j = _read_arg(s, j)
        k = j
        while k < len(s) and s[k] in " 	":
            k += 1
        if k < len(s) and s[k] == "{":
            arg, j = _read_arg(s, j)
            return _convert(arg or "", mark_accents), j
        return "", j
    if name in _DROP_WITH_ARG_CMDS:
        _arg, j = _read_arg(s, j)
        return "", j
    if name in _ACCENT_CMDS or name in _PLAIN_ACCENT_CMDS:
        arg, j = _read_arg(s, j)
        body = _convert(arg or "", mark_accents)
        if not mark_accents or name in _PLAIN_ACCENT_CMDS or not body:
            return body, j
        combining, label = _ACCENT_CMDS[name]
        if len(body) == 1:
            return body + combining, j
        return f"{label}({body})", j
    if name in _SIZING_CMDS:
        if j < len(s) and s[j] == ".":
            j += 1
        return "", j
    if name in _DROP_CMDS:
        return "", j
    if name == "begin":
        arg, k = _read_arg(s, j)
        if arg is None or not s[j:k].lstrip(" \t").startswith("{"):
            return "", j
        env = arg.strip()
        depth = 1
        for m in _LATEX_ENV_TOKEN_RE.finditer(s, k):
            if m.group(2).strip() != env:
                continue
            depth += 1 if m.group(1) == "begin" else -1
            if depth == 0:
                return _environment(env, s[k : m.start()], mark_accents), m.end()
        return _environment(env, s[k:], mark_accents), len(s)
    if name == "end":
        arg, k = _read_arg(s, j)
        return "", k if arg is not None else j
    if name in LATEX_CMD_MAP:
        return LATEX_CMD_MAP[name], j
    # A real KaTeX command that is not in the map keeps its name as text
    # (`\intercal` → "intercal"); it is never split (`\neg` is not `\ne` + g).
    if name in KATEX_COMMANDS:
        return name, j
    # `\cmd` written without a separator before the next word runs into it,
    # because the command scanner is greedy: `\colonN` matches as one command
    # named "colonN". Peel the longest known command off the front and keep
    # the remainder as text. Minimum length 2 so a stray `\cm` isn't split on
    # a one-letter name. Unknown commands lose the backslash (\foo → foo).
    for cut in range(len(name) - 1, 1, -1):
        head = name[:cut]
        if head in LATEX_CMD_MAP:
            return LATEX_CMD_MAP[head] + name[cut:], j
    return name, j


def _convert(s: str, mark_accents: bool) -> str:
    """Single left-to-right pass over maths text. Arguments are read with a
    balanced-brace scanner and converted recursively, so nesting depth is
    unbounded (a regex pass could only ever see a fixed number of levels)."""
    out: List[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = _LATEX_CMD_RE.match(s, i)
            if m:
                piece, i = _command(m.group(1), s, m.end(), mark_accents)
                if m.group(1) in _FRAC_CMDS and _fraction_needs_parens(out, s, i):
                    piece = f"({piece})"
                out.append(piece)
                continue
            nxt = s[i + 1] if i + 1 < n else ""
            if not nxt:
                i += 1
                continue
            if nxt in ",;:> " or nxt == "\\":
                # Spacing commands and a `\\` line break read as one space.
                # ``\!`` is a NEGATIVE space and collapses to nothing.
                out.append(" ")
            elif nxt in "%&#_":
                out.append(nxt)
            # `\(`, `\)`, `\[`, `\]` delimiters, `\!`, and an orphan backslash
            # ("\0.008Wb" residue) all render as nothing.
            i += 2 if nxt in ",;:> \\%&#_!()[]" else 1
            continue
        if c in "^_":
            j = i + 1
            if j < n and s[j] == "{":
                raw, j = _read_group(s, j)
            elif j < n and _LATEX_CMD_RE.match(s, j):
                m = _LATEX_CMD_RE.match(s, j)
                raw, j = m.group(0), m.end()
            elif j < n and (s[j].isalnum() or s[j] in "+-"):
                raw, j = s[j], j + 1
            else:
                out.append(c)
                i += 1
                continue
            out.append(_script(_convert(raw, mark_accents), c))
            i = j
            continue
        if c == "{":
            raw, i = _read_group(s, i)
            out.append(_convert(raw, mark_accents))
            continue
        if c == "}":
            # Unmatched closing brace: grouping residue, not content.
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def latex_to_plain(
    text: Any,
    *,
    mark_accents: bool = False,
    keep_label_backslash: bool = True,
    force: bool = False,
) -> Any:
    """Convert a LaTeX-math-laced string into plain text/Unicode.

    Targets the constructs question and BAA content actually carries:
      - `$...$`, `$$...$$`, `\\(...\\)`, `\\[...\\]` delimiters → stripped;
        an escaped `\\$` is a literal dollar
      - `\\lambda`, `\\pi`, `\\theta`, `\\circ` etc. → Unicode (λ, π, θ, °)
      - `^{...}` / `_{...}` → Unicode scripts when every character has one
        (10^{-15} → 10⁻¹⁵), else `^(...)` / `_(...)` (lim_(x→0))
      - `\\frac{a}{b}` → `(a)/(b)` at any nesting depth, `\\binom` → `C(n, k)`
      - `\\sqrt{x}` → `√x` / `√(2m)`, `\\sqrt[3]{8}` → `³√8`
      - `\\text{...}`, `\\mathrm{...}`, `\\ce{...}` wrappers → inner content
      - `\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}` → `[a b; c d]`
      - accents (`\\vec`, `\\hat`, `\\bar`, `\\dot`, …) keep their argument;
        with ``mark_accents`` a one-symbol argument gets the combining mark
        (F⃗) and a longer one is named (vec(AB)) so the meaning survives

    ``mark_accents`` defaults to False: grading (``services.answer_match``)
    and the in-class report compare/show the bare symbol, as they always have.

    Non-string inputs are returned unchanged so this is safe to apply to
    arbitrary BAA payload fields.
    """
    if not isinstance(text, str):
        return text
    if not force and "$" not in text and "\\" not in text and "{" not in text:
        return text

    out = text

    # `{{IMAGE:…}}` markers are not braces to strip: park them first.
    image_stash: List[str] = []

    def _stash_image(m: "re.Match[str]") -> str:
        image_stash.append(m.group(0))
        return f"\x00IMG{len(image_stash) - 1}\x00"

    if "{{IMAGE:" in out:
        out = _IMAGE_MARKER_RE.sub(_stash_image, out)

    # Amounts outside the `segment` math spans (`Rs $5 and $10`, `costs $5.`)
    # are literal dollars, never paired as a span (tag `audit5-1`).
    out = _park_currency_dollars(out)

    # Literal `\n` escapes first — before the greedy command scanner can claim
    # them as `\nStatement`-style pseudo-commands.
    out = _LATEX_NEWLINE_ESCAPE_RE.sub("\n", out)

    # Escaped braces and dollars are literal characters. Parked before the
    # delimiter passes (an escaped "\$5" is a price, not the start of a maths
    # span) and restored at the very end. Without this `$\{a, b\}$` rendered
    # as "\a, b\" and "costs \$5 and $x$" as "costs \5 and x".
    out = (
        out.replace(r"\$", _DOLLAR_SENTINEL)
        .replace(r"\{", _LBRACE_SENTINEL)
        .replace(r"\}", _RBRACE_SENTINEL)
    )

    # Lesson-script labels at a line start are not commands.
    labels: List[str] = []

    def _stash_label(m: "re.Match[str]") -> str:
        labels.append(m.group(3))
        return (
            m.group(1)
            + m.group(2)
            + f"{_LABEL_SENTINEL_OPEN}{len(labels) - 1}{_LABEL_SENTINEL_CLOSE}:"
        )

    def _stash_known_label(m: "re.Match[str]") -> str:
        if m.group(1) not in SCRIPT_LABELS:
            return m.group(0)
        labels.append(m.group(1))
        return f"{_LABEL_SENTINEL_OPEN}{len(labels) - 1}{_LABEL_SENTINEL_CLOSE}:"

    if "\\" in out and ":" in out:
        out = _SCRIPT_LABEL_LINE_RE.sub(_stash_label, out)
        # A known label (`SCRIPT_LABELS`, the words `repair` restores) is a
        # label anywhere: `(<TAB>ool: timer)` became `\tool:`, which the
        # scanner read as `\to` + "ol" (tag `audit5-3`).
        out = _SCRIPT_LABEL_ANY_RE.sub(_stash_known_label, out)

    # Braces in prose are text (`A = {1, 2, 3}`), not grouping.
    out = _protect_prose_braces(out)

    # Pull maths out of `$$...$$` / `$...$` so the scanner below operates on
    # the inner content too. `\(...\)` / `\[...\]` are dropped by the scanner.
    out = _LATEX_DISPLAY_DOLLAR_RE.sub(lambda m: m.group(1), out)
    out = _LATEX_DELIM_RE.sub(lambda m: m.group(1), out)

    try:
        out = _convert(out, mark_accents)
    except RecursionError:
        # Pathological nesting (hundreds of brace levels): fall back to a
        # flat strip so the caller still gets readable text.
        out = re.sub(r"\\[A-Za-z]+", "", out).replace("{", "").replace("}", "")

    # Collapse runs of spaces the substitutions introduced — a spacing command
    # next to an ordinary space ("a\quad b") would otherwise leave a visible
    # double gap. Horizontal space only: newlines carry meaning here.
    out = re.sub(r"[ \t]{2,}", " ", out)

    # An UNPAIRED delimiter at either end. Some stored answers carry only the
    # opening one — "$45m", "$4\sqrt{3}s" — so the paired-delimiter pass above
    # never matched and the dollar reached the teacher. Bounded to a leading or
    # trailing dollar on an odd count, so a mid-string amount ("costs $5") is
    # left alone: that is a currency figure, not a broken math span.
    if out.count("$") % 2 == 1:
        if out.startswith("$"):
            out = out[1:]
        elif out.endswith("$"):
            out = out[:-1]

    # Literal characters come back now that grouping and delimiters are done.
    out = (
        out.replace(_LBRACE_SENTINEL, "{")
        .replace(_RBRACE_SENTINEL, "}")
        .replace(_DOLLAR_SENTINEL, "$")
    )

    for idx, name in enumerate(labels):
        out = out.replace(
            f"{_LABEL_SENTINEL_OPEN}{idx}{_LABEL_SENTINEL_CLOSE}",
            ("\\" if keep_label_backslash else "") + name,
        )

    for idx, original in enumerate(image_stash):
        out = out.replace(f"\x00IMG{idx}\x00", original)

    # Compose accents where a precomposed character exists (`i` + U+0302 →
    # `î`) so PDF fonts draw one glyph; marks with no precomposed form (F⃗)
    # are left as they are.
    return unicodedata.normalize("NFC", out)


# ---------------------------------------------------------------------------
# tts style (agents podcast_node / story_node `_clean_script_for_tts`)
# ---------------------------------------------------------------------------

_SPOKEN_OPERATORS: Tuple[Tuple[str, str], ...] = (
    (r"\times", "times"),
    (r"\div", "divided by"),
    (r"\pm", "plus or minus"),
    (r"\leq", "less than or equal to"),
    (r"\geq", "greater than or equal to"),
    (r"\neq", "not equal to"),
    (r"\le", "less than or equal to"),
    (r"\ge", "greater than or equal to"),
    (r"\ne", "not equal to"),
    (r"\cdot", "times"),
    (r"\approx", "approximately"),
    (r"\infty", "infinity"),
    (r"\int", "integral of"),
    (r"\sum", "sum of"),
)


def _command_to_word(m: "re.Match[str]") -> str:
    """``\alpha`` → ``alpha``; any other command loses its backslash."""
    return m.group(1)


_SPOKEN_OPERATOR_RE = re.compile(
    r"\\(" + "|".join(re.escape(c[1:]) for c, _ in _SPOKEN_OPERATORS) + r")(?![A-Za-z])"
)
_SPOKEN_OPERATOR_WORDS = {c[1:]: w for c, w in _SPOKEN_OPERATORS}
_SPOKEN_CMD_RE = re.compile(r"\\([A-Za-z]+)")
# Font and text wrappers: spoken as their content (`\text{cm}` → cm).
_SPOKEN_WRAPPERS = frozenset(
    (
        "text textbf textit textrm textsf texttt textnormal textup textmd emph "
        "mathrm mathit mathbf mathsf mathtt mathbb mathcal mathfrak mathscr "
        "boldsymbol bm operatorname mbox hbox boxed fbox"
    ).split()
)
# mhchem: `\ce{H2O}` → "H 2 O".
_SPOKEN_CHEM_WRAPPERS = frozenset({"ce", "pu"})
# Sizing and style commands with nothing to say (`\left(` → "(").
_SPOKEN_DROPPED = frozenset(
    (
        "left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr "
        "Biggl Biggr displaystyle textstyle scriptstyle scriptscriptstyle "
        "limits nolimits nonumber notag hline"
    ).split()
)
_SPOKEN_SPACES = frozenset({"quad", "qquad", "enspace", "thinspace", "medspace"})
_SPOKEN_DROPPED_WITH_ARG = frozenset(
    {"hspace", "vspace", "phantom", "hphantom", "vphantom", "label", "tag", "color"}
)
_SPOKEN_MATRIX_ENVS = frozenset(
    {"matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "smallmatrix"}
)
_CHEM_TEXT_RE = re.compile(r"[A-Z][A-Za-z()]*")
_CHEM_CHARGE_RE = re.compile(r"([0-9]*)([+-])")


def _spoken_chem(content: str) -> str:
    """``H2O`` / ``H_2O`` / ``SO4^{2-}`` → ``H 2 O`` / ``SO 4 2 minus``."""
    content = content.replace("<=>", " is in equilibrium with ").replace(
        "<->", " is in equilibrium with "
    )
    content = content.replace("->", " gives ").replace("<-", " comes from ")
    content = re.sub(
        r"\^\{?([0-9]*)([+-])\}?",
        lambda m: (
            " "
            + (m.group(1) + " " if m.group(1) else "")
            + ("plus" if m.group(2) == "+" else "minus")
            + " "
        ),
        content,
    )
    content = re.sub(r"_\{?([0-9]+)\}?", r" \1 ", content)
    content = re.sub(r"(?<=[A-Za-z)\]])([0-9]+)", r" \1 ", content)
    return content.replace("{", "").replace("}", "")


def _needs_parens(spoken: str) -> bool:
    return bool(re.search(r"[\s+\-=]", spoken.strip()))


def _spoken_structures(s: str, prose: bool = False) -> str:
    """Spoken form of fractions, roots, wrappers, chemistry, environments and
    escapes, read with balanced braces at any depth. Operators, Greek and
    scripts are left for the word rules that run after."""
    out: List[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "&" and not prose:
            out.append(" ")
            i += 1
            continue
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if s.startswith("\\\\", i):
            out.append(" ")
            i += 2
            continue
        m = _SPOKEN_CMD_RE.match(s, i)
        if not m:
            nxt = s[i + 1 : i + 2]
            if nxt == "%":
                out.append(" percent ")
            elif nxt == "{":
                out.append("(")
            elif nxt == "}":
                out.append(")")
            elif nxt and nxt in "&#_$":
                out.append(nxt)
            else:
                out.append(" ")  # \, \; \: \! \  and a lone backslash
            i += 2
            continue
        name, j = m.group(1), m.end()
        if name in _FRAC_CMDS:
            num, j = _read_arg(s, j)
            den, k = _read_arg(s, j)
            if num is None or den is None:
                out.append(" ")
                i = j
                continue
            out.append(
                "("
                + _spoken_structures(num).strip()
                + " over "
                + _spoken_structures(den).strip()
                + ")"
            )
            i = k
            continue
        if name == "sqrt":
            index = ""
            k = j
            while k < n and s[k] in " \t":
                k += 1
            if k < n and s[k] == "[":
                close = s.find("]", k)
                if close != -1:
                    index, j = s[k + 1 : close].strip(), close + 1
            arg, j = _read_arg(s, j)
            if arg is None:
                out.append(" square root ")
                i = j
                continue
            inner = _spoken_structures(arg).strip()
            if _needs_parens(inner):
                inner = "(" + inner + ")"
            if not index or index == "2":
                phrase = "square root of"
            elif index == "3":
                phrase = "cube root of"
            else:
                phrase = index + "th root of"
            out.append(phrase + " " + inner)
            i = j
            continue
        if name in _SPOKEN_CHEM_WRAPPERS:
            arg, j = _read_arg(s, j)
            out.append(" " + _spoken_chem(arg or "") + " ")
            i = j
            continue
        if name in _SPOKEN_WRAPPERS:
            arg, j = _read_arg(s, j)
            arg = arg or ""
            if name in ("text", "mathrm") and ("_" in arg or "^" in arg):
                arg = _spoken_chem(arg)  # `\mathrm{H_2O}`
            inner = _spoken_structures(arg)
            # `\text{H}_{2}\text{O}`, `\text{Fe}^{3+}`: an element read
            # with its count or charge.
            if _CHEM_TEXT_RE.fullmatch(inner.strip()):
                spoken = [inner.strip()]
                while j < n and s[j] in "_^":
                    script, k = _read_arg(s, j + 1)
                    if script is None:
                        break
                    charge = _CHEM_CHARGE_RE.fullmatch(script)
                    if s[j] == "_" and script.isdigit():
                        spoken.append(script)
                    elif s[j] == "^" and charge:
                        if charge.group(1):
                            spoken.append(charge.group(1))
                        spoken.append("plus" if charge.group(2) == "+" else "minus")
                    else:
                        break
                    j = k
                if len(spoken) > 1:
                    out.append(" " + " ".join(spoken) + " ")
                    i = j
                    continue
            out.append(inner)
            i = j
            continue
        if name == "begin":
            env_arg, j = _read_arg(s, j)
            env = (env_arg or "").strip()
            end_m = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}").search(s, j)
            body_end = end_m.start() if end_m else n
            after = end_m.end() if end_m else n
            if env == "array":
                arg, j = _read_arg(s, j)  # column spec
            rows = [
                [_spoken_structures(cell).strip() for cell in row]
                for row in _split_table(s[j:body_end])
            ]
            rows = [[c for c in row if c] for row in rows]
            rows = [row for row in rows if row]
            if env.rstrip("*") in _SPOKEN_MATRIX_ENVS:
                out.append(
                    " matrix with rows " + "; ".join(", ".join(r) for r in rows) + " "
                )
            elif env.rstrip("*") == "cases":
                cases = "; ".join(", ".join(r) for r in rows)
                out.append(" " + re.sub(r",\s*,", ",", cases) + " ")
            else:
                out.append(" " + "; ".join(" ".join(r) for r in rows) + " ")
            i = after
            continue
        if name == "end":
            _, j = _read_arg(s, j)
            i = j
            continue
        if name in _SPOKEN_DROPPED:
            while j < n and s[j] in " \t":
                j += 1
            if j < n and s[j] == ".":
                j += 1  # `\left.`
            i = j
            continue
        if name in _SPOKEN_SPACES:
            out.append(" ")
            i = j
            continue
        if name in _SPOKEN_DROPPED_WITH_ARG:
            _, j = _read_arg(s, j)
            i = j
            continue
        if name in ("textcolor", "colorbox"):
            _, j = _read_arg(s, j)
            arg, j = _read_arg(s, j)
            out.append(_spoken_structures(arg or ""))
            i = j
            continue
        # Operators, Greek, functions: the word rules below read them. A
        # space keeps `\alpha\text{x}` from becoming `\alphax`.
        out.append(m.group(0) + (" " if j < n and s[j] == "\\" else ""))
        i = j
    return "".join(out)


def _strip_outer_parens(text: str) -> str:
    """``(a over b)`` → ``a over b`` when ONE pair wraps the whole text."""
    if not (text.startswith("(") and text.endswith(")")):
        return text
    depth = 0
    for k, ch in enumerate(text):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and k < len(text) - 1:
            return text
    return text[1:-1]


def _latex_to_spoken(latex: str) -> str:
    text = _spoken_structures(latex.strip())
    text = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", " degrees", text)
    base = r"([\w)\]|])"
    text = re.sub(base + r"\^(?:\{2\}|2)(?![0-9])", r"\1 squared", text)
    text = re.sub(base + r"\^(?:\{3\}|3)(?![0-9])", r"\1 cubed", text)
    text = re.sub(base + r"\^\{([^{}]+)\}", r"\1 to the power \2", text)
    text = re.sub(base + r"\^(\w)", r"\1 to the power \2", text)
    text = re.sub(base + r"_\{([^{}]+)\}", r"\1 sub \2", text)
    text = re.sub(base + r"_(\w)", r"\1 sub \2", text)
    # Every command becomes a word with room around it (`4\pi` → "4 pi").
    text = _SPOKEN_OPERATOR_RE.sub(
        lambda m: " " + _SPOKEN_OPERATOR_WORDS[m.group(1)] + " ", text
    )
    text = re.sub(r"\\([a-zA-Z]+)", lambda m: " " + m.group(1) + " ", text)
    text = text.replace("{", "").replace("}", "").replace("\\", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    return _strip_outer_parens(text.strip())


def _to_spoken(text: str) -> str:
    parts: List[str] = []
    for seg in segment(text):
        parts.append(
            _latex_to_spoken(seg["value"])
            if seg["kind"] == "math"
            # Bare LaTeX in prose (`rac{1}{2}` never wrapped): fractions,
            # roots, wrappers and environments are read the same way.
            else (
                _spoken_structures(seg["value"], prose=True)
                if "\\" in seg["value"]
                else seg["value"]
            )
        )
    cleaned = "".join(parts)
    cleaned = re.sub(
        r"\\(?:frac|sqrt|sum|int|prod|lim|log|ln|sin|cos|tan)\b", "", cleaned
    )
    cleaned = re.sub(r"\\([a-zA-Z]+)", _command_to_word, cleaned)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


STYLES = ("text", "pdf", "tts", "compare")

_SUPERSCRIPT_TO_ASCII = {v: k for k, v in zip("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")}
_SUBSCRIPT_TO_ASCII = {
    v: k for k, v in zip("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ")
}
_SUPERSCRIPT_RUN_RE = re.compile("[" + "".join(_SUPERSCRIPT_TO_ASCII) + "]+")
_SUBSCRIPT_RUN_RE = re.compile("[" + "".join(_SUBSCRIPT_TO_ASCII) + "]+")
# Characters `compare` folds to one ASCII form.
_COMPARE_FOLD = {
    "−": "-",  # minus sign
    "‐": "-",  # hyphen
    "‒": "-",  # figure dash
    "×": "*",
    "·": "*",
    "⋅": "*",
    "∗": "*",
    "÷": "/",
}
_COMPARE_SPACE_RE = re.compile(r"\s+")
_COMPARE_OPERATOR_SPACE_RE = re.compile(r" ?([+\-*/=<>^_(),{}\[\]]) ?")


def _fold_for_compare(text: str) -> str:
    """One ASCII-leaning form for answer comparison: scripts as `^…`/`_…`,
    minus signs and multiplication dots folded, whitespace collapsed and
    removed around operators and brackets."""
    text = "".join(_COMPARE_FOLD.get(ch, ch) for ch in text)
    text = _SUPERSCRIPT_RUN_RE.sub(
        lambda m: "^" + "".join(_SUPERSCRIPT_TO_ASCII[c] for c in m.group(0)), text
    )
    text = _SUBSCRIPT_RUN_RE.sub(
        lambda m: "_" + "".join(_SUBSCRIPT_TO_ASCII[c] for c in m.group(0)), text
    )
    text = _COMPARE_SPACE_RE.sub(" ", text).strip()
    return _COMPARE_OPERATOR_SPACE_RE.sub(r"\1", text)


def to_plain(text: Any, style: str = "text") -> Any:
    """LaTeX → plain text.

    ``style="text"``: accents dropped (grading, canvas, in-class report).
    ``style="pdf"``: accents marked (``\\vec{F}`` → ``F⃗``, ``\\vec{AB}`` → ``vec(AB)``).
    ``style="tts"``: spoken English for a text-to-speech voice.
    ``style="compare"``: one form for answer comparison, so a typed answer
    equals the same value in LaTeX (``1/3`` = ``$\\frac{1}{3}$``, ``x^2`` =
    ``$x^2$``, ``−3`` = ``-3``, ``90°`` = ``$90^\\circ$``).
    Non-strings are returned unchanged.
    """
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")
    if not isinstance(text, str):
        return text
    # A form feed / backspace / TAB that was a command (`<FF>rac`, `<TAB>imes`)
    # is restored first, with the same `guessWhitespace` as `fix` (`normalize`).
    text = repair(text)
    if style == "tts":
        return _to_spoken(text)
    if style == "compare":
        plain = latex_to_plain(text, keep_label_backslash=False, force=True)
        return _fold_for_compare(plain)
    return latex_to_plain(
        text, mark_accents=(style == "pdf"), keep_label_backslash=(style == "text")
    )
