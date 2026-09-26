"""Command vocabularies shared by every function in the package.

`KATEX_COMMANDS` lives in `katex_commands.py` (a faithful extract of the
KaTeX support table). Everything here is a curated subset with a stated
purpose. Keep the JSON mirrors in `corpus/tables/` in sync by running
`python -m pupiltree_latex.export_tables`.
"""

from __future__ import annotations

from .katex_commands import (  # noqa: F401  (re-exported)
    JSON_WHITESPACE_COLLISION_COMMANDS,
    KATEX_COMMANDS,
    NON_KATEX_MODEL_EMISSIONS,
)

# (LATEX_COMMANDS_BEHIND_JSON_ESCAPES is defined below; PROSE_ESCAPE_COMMANDS
# at the end of this file depends on it.)

# Five LaTeX command families start with a letter that is also a JSON escape:
# \b, \f, \n, \t, \r. `\b` and `\f` are always LaTeX (backspace and form feed
# never occur in lesson text). `\n`, `\t`, `\r` are real whitespace in prose,
# so they are only repaired when the letters after them spell one of these
# unambiguous commands. Deliberately WITHOUT \nu, \ne, \ni, \not: a real line
# break followed by "u = -25 cm", "e) No enzyme" or "i) Presence of" was found
# in production for each of them.
LATEX_COMMANDS_BEHIND_JSON_ESCAPES: frozenset[str] = frozenset(
    {
        "nabla",
        "neq",
        "notin",
        "newline",
        "nolimits",
        "nonumber",
        "ngeq",
        "nleq",
        "nmid",
        "nparallel",
        "nsubseteq",
        "nsupseteq",
        "natural",
        "nrightarrow",
        "theta",
        "Theta",
        "times",
        "text",
        "textbf",
        "textit",
        "textrm",
        "textsf",
        "texttt",
        "textcolor",
        "textstyle",
        "tau",
        "to",
        "tan",
        "tanh",
        "tilde",
        "triangle",
        "triangleq",
        "triangleleft",
        "top",
        "therefore",
        "tfrac",
        "tbinom",
        "thinspace",
        "tag",
        "rho",
        "rightarrow",
        "Rightarrow",
        "right",
        "rm",
        "rangle",
        "rceil",
        "rfloor",
        "rbrace",
        "rvert",
        "rVert",
        "ref",
        "rule",
        "raisebox",
        "rightleftharpoons",
        "rightharpoonup",
        "rightleftarrows",
        "Re",
    }
)

# Lesson-script labels: the teaching-script DSL marks a line with a backslash
# word and a colon (`\teacher: …`, `\type: mcq`). Five of them start with a
# JSON-escape letter, so `\teacher:` used to be decoded into TAB + "eacher:"
# by every escape decoder (found on 446 sites in six production dumps). A
# backslash + letters immediately followed by `:` is a label, never an escape.
SCRIPT_LABELS: frozenset[str] = frozenset(
    {
        "heading", "teacher", "instruction", "activity", "write", "tool", "type",
        "content", "board", "read", "ppt", "flashcard", "thinkingroutine",
        "simulation", "video", "image", "question", "answer", "note", "timer",
        "recap", "example", "task", "discussion", "reflection", "summary",
    }
)  # fmt: skip

# Commands that stored content commonly carries with doubled backslashes
# (`\\frac`) after several JSON encode/decode cycles. `canonicalize` collapses
# a run of 2+ backslashes before exactly these names.
COLLAPSE_COMMANDS: tuple[str, ...] = (
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau",
    "upsilon", "phi", "chi", "psi", "omega", "Gamma", "Delta", "Theta",
    "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega",
    "frac", "dfrac", "tfrac", "sqrt", "binom", "sum", "int", "prod", "iint",
    "iiint", "oint", "times", "div", "pm", "mp", "cdot", "leq", "geq", "neq",
    "approx", "equiv", "sim", "cong", "propto", "infty", "partial", "nabla",
    "rightarrow", "leftarrow", "Rightarrow", "Leftarrow", "leftrightarrow",
    "Leftrightarrow", "mapsto", "to", "rightleftharpoons", "in", "notin",
    "subset", "supset", "subseteq", "supseteq", "cup", "cap", "emptyset",
    "forall", "exists", "sin", "cos", "tan", "cot", "sec", "csc", "log", "ln",
    "exp", "lim", "max", "min", "vec", "hat", "bar", "dot", "overline",
    "underline", "tilde", "text", "left", "right", "begin", "end", "hbar",
    "ell", "mathbb", "mathcal", "mathbf", "mathrm", "langle", "rangle",
    "angle", "triangle", "square", "quad", "qquad",
)  # fmt: skip

# Structural commands that only render inside a math span. `canonicalize`
# wraps a bare occurrence (plus its arguments and scripts) in `$…$`.
STRUCTURAL_COMMANDS: tuple[str, ...] = (
    "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "int", "iint",
    "iiint", "oint", "binom", "dbinom", "tbinom", "lim", "liminf", "limsup",
    "overline", "underline", "overbrace", "underbrace", "vec", "hat", "bar",
    "dot", "ddot", "mathbb", "mathcal", "mathbf", "mathfrak",
    # Function names take no braces but still only render inside math
    # (`\log_{10} x`, `\sin\theta`); they are wrapped with their scripts.
    "log", "ln", "lg", "exp", "sin", "cos", "tan", "cot", "sec", "csc",
    "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "max", "min",
    "det", "gcd",
    # Text-mode wrappers only mean something inside math; a bare
    # `\text{H₂O}` in prose is shown literally by every renderer.
    "text", "textbf", "textit", "mathrm",
)  # fmt: skip

# Commands that flutter_math_fork cannot render at all. `audit` flags them
# wherever they appear.
UNSUPPORTED_COMMANDS: tuple[str, ...] = ("mathscr", "mathfrak", "cal")

# Commands `audit` accepts inside math although KaTeX's support table does not
# list them: mhchem (`\ce`, `\pu`) is enabled on every web surface. The model
# emissions in NON_KATEX_MODEL_EMISSIONS (`\textmu`, `\nicefrac`, …) do NOT
# render and are reported as unsupported.
AUDIT_EXTRA_ALLOWED_COMMANDS: frozenset[str] = frozenset({"ce", "pu"})

# Commands `canonicalize` collapses a doubled backslash before (`\\frac` →
# `\frac`): every KaTeX command plus mhchem.
COLLAPSIBLE_COMMANDS: frozenset[str] = KATEX_COMMANDS | frozenset({"ce", "pu"})

# The escape decoders' vocabulary OUTSIDE math: the full KaTeX vocabulary
# minus the four names production prose proved to be line breaks
# ("\nu = -25 cm", "\ne) No enzyme", "\ni) Presence of", "\not").
PROSE_ESCAPE_COMMANDS: frozenset[str] = (
    JSON_WHITESPACE_COLLISION_COMMANDS | LATEX_COMMANDS_BEHIND_JSON_ESCAPES
) - frozenset({"nu", "ne", "ni", "not"})

# Commands that cannot render without an argument (`$\sqrt$2` is a KaTeX
# parse error painted red on the classroom board).
ARGUMENT_COMMANDS: tuple[str, ...] = (
    "frac", "dfrac", "tfrac", "sqrt", "text", "textbf", "textit", "mathrm",
    "mathbf", "vec", "hat", "bar", "overline", "underline", "dot", "tilde",
    "binom",
)  # fmt: skip
