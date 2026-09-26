"""Bug class B2: a screen renders a math field through plain text.

Eight of the historical LaTeX fixes were "this screen never called the
renderer". No library can fix that, so this lint flags the pattern in
source code: a known math field name rendered through `Text(...)` (Dart),
`{x.field}` / `innerHTML` (JS/TS/JSX/TSX), or `{{ field }}` (Jinja) instead of
the shared `MathText` / `typesetMath` adapters.

    python tools/lint_plain_text_sites.py <repo-dir> [--fields question,options,...] [--allow-comment latex-ok]

Exit status 1 when any site is found. A line containing the allow comment
(default ``latex-ok``) is skipped, so a deliberate plain-text site can be
documented in place.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_FIELDS = (
    "question", "questiontext", "question_text", "stem", "options", "option",
    "optiontext", "option_text", "answer", "correctanswer", "correct_answer",
    "explanation", "reason", "solution", "modelsolution", "model_solution",
    "hint", "content", "statement", "problem", "feedback", "remedy",
)  # fmt: skip

SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "build",
    "dist",
    ".dart_tool",
    ".git",
    "__pycache__",
    "vendor",
    "static",
}
EXTENSIONS = {".dart", ".js", ".jsx", ".ts", ".tsx", ".html", ".jinja", ".jinja2"}

# What a "plain text sink" looks like per language. `{field}` is replaced
# by an alternation of the configured field names (any case, any prefix
# object). The sink must NOT already be a math adapter.
# The field must be the LAST component of the expression (`q.question`,
# `_question!.question`, `q.question.text`), so `question.subjectCode` and
# `question.chapterId` are not flagged.
DART_SINK = r"\bText\(\s*(?:'[^']*\$\{)?[\w.!?]*\b(?:{field})(?:\.(?:text|value))?\b(?!\s*[.!?]\w)"
DART_SINK_INTERP = r"\bText\(\s*'[^']*\$\{[^}]*\.(?:{field})\b"
JSX_SINK = r"\{\s*[\w.?]*\.(?:{field})\s*\}"
JS_INNERHTML = r"innerHTML\s*=\s*[^;\n]*\b(?:{field})\b"
JINJA_SINK = r"\{\{\s*[\w.]*\.?(?:{field})\s*(?:\|\s*safe\s*)?\}\}"
MATH_ADAPTERS = (
    "MathText",
    "ScriptEditorTex",
    "LatexMarkdownText",
    "typesetMath",
    "renderMath",
    "katex",
    "Latex(",
    "renderRemedyContent",
    "renderQuestionContent",
    "renderOptionContent",
    "TextWithLinkPreviews",
)


def _compile(pattern: str, fields: tuple[str, ...]) -> re.Pattern[str]:
    alternation = "|".join(re.escape(f) for f in fields)
    return re.compile(pattern.replace("{field}", alternation), re.IGNORECASE)


def scan(
    root: Path, fields: tuple[str, ...], allow_comment: str
) -> list[tuple[Path, int, str]]:
    dart = [_compile(DART_SINK, fields), _compile(DART_SINK_INTERP, fields)]
    jsx = [_compile(JSX_SINK, fields), _compile(JS_INNERHTML, fields)]
    jinja = [_compile(JINJA_SINK, fields)]
    hits: list[tuple[Path, int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if (
            ".test." in path.name
            or path.name.endswith("_test.dart")
            or "/test/" in path.as_posix()
            or "/tests/" in path.as_posix()
        ):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        patterns = (
            dart
            if path.suffix == ".dart"
            else jinja
            if path.suffix in {".html", ".jinja", ".jinja2"}
            else jsx
        )
        for n, line in enumerate(lines, 1):
            if allow_comment in line:
                continue
            if any(adapter in line for adapter in MATH_ADAPTERS):
                continue
            if any(p.search(line) for p in patterns):
                hits.append((path, n, line.strip()))
    return hits


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("root", type=Path)
    ap.add_argument(
        "--fields", default=",".join(DEFAULT_FIELDS), help="comma-separated field names"
    )
    ap.add_argument("--allow-comment", default="latex-ok")
    args = ap.parse_args(argv[1:])
    fields = tuple(f.strip() for f in args.fields.split(",") if f.strip())
    hits = scan(args.root, fields, args.allow_comment)
    for path, n, line in hits:
        print(f"{path}:{n}: {line[:140]}")
    print(
        f"{len(hits)} plain-text site(s) render a math field (add `{args.allow_comment}` on the line if deliberate)"
    )
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
