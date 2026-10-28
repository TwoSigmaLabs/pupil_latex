"""Fail when a service carries a diverged copy of the prompt rules.

Every LLM service must inject `LATEX_SYSTEM_RULES` / `NARRATIVE_PROSE_RULES`
/ `PLAIN_NOTATION_RULES` from `pupiltree_latex.prompt_rules`. Until each repo
has migrated, this check finds local copies in the repo's Python sources and
compares them with the package text, ignoring whitespace differences:

- a string assigned to a name ending in one of those three names;
- any string literal (f-string parts included) that carries a block's
  header line (its first line, such as the PLAIN NOTATION RULES title),
  compared from the header to the block's "=== END ... ===" line.

A diverged copy fails the check (exit 1). It also lists, as LOCAL lines that
do not fail, hand-written rules the library now covers: a string that forbids
LaTeX while showing Unicode sub/superscripts (a local plain-notation rule;
use `inject_plain_notation_rules`), and `TODO(pupiltree-latex): move to
LATEX_SYSTEM_RULES` comments (the rule is in `LATEX_SYSTEM_RULES` since
1.4.0; delete the local bullet).

    python tools/check_prompt_parity.py <repo-dir>
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from pupiltree_latex.prompt_rules import (  # noqa: E402
    LATEX_SYSTEM_RULES,
    NARRATIVE_PROSE_RULES,
    PLAIN_NOTATION_RULES,
)

CANONICAL = {
    "LATEX_SYSTEM_RULES": LATEX_SYSTEM_RULES,
    "NARRATIVE_PROSE_RULES": NARRATIVE_PROSE_RULES,
    "PLAIN_NOTATION_RULES": PLAIN_NOTATION_RULES,
}
SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "build",
    "dist",
    ".git",
    "__pycache__",
    "pupiltree_latex",
}

# A block runs from its first line (the header) to its last line (the END line).
_BOUNDS = {
    name: (text.strip().splitlines()[0].strip(), text.strip().splitlines()[-1].strip())
    for name, text in CANONICAL.items()
}
_SCRIPT_CHARS = re.compile(r"[₀-₉⁰-⁹⁺⁻]")
_NO_LATEX = re.compile(r"\bno\s+latex\b", re.IGNORECASE)
_TODO = re.compile(r"TODO\(pupiltree-latex\):\s*move to LATEX_SYSTEM_RULES")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _embedded_block(text: str, name: str) -> str | None:
    """The block `name` pasted inside `text` (header to END line), or None."""
    head, end = _BOUNDS[name]
    start = text.find(head)
    if start < 0:
        return None
    stop = text.find(end, start)
    return text[start:] if stop < 0 else text[start : stop + len(end)]


def find_copies(root: Path) -> list[tuple[Path, str, str]]:
    """Local copies of a rules block as (path, block name, copied text)."""
    copies: list[tuple[Path, str, str]] = []
    for path, tree in _sources(root):
        named: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(
                node.value, ast.Constant
            ):
                continue
            if not isinstance(node.value.value, str):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    for name in CANONICAL:
                        if target.id.endswith(name):
                            copies.append((path, name, node.value.value))
                            named.add(id(node.value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in named
            ):
                for name in CANONICAL:
                    block = _embedded_block(node.value, name)
                    if block is not None:
                        copies.append((path, name, block))
    return copies


def find_local_rules(root: Path) -> list[tuple[Path, int, str]]:
    """Hand-written rules the library now carries, as (path, line, what)."""
    found: list[tuple[Path, int, str]] = []
    for path, tree in _sources(root):
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _NO_LATEX.search(node.value)
                and _SCRIPT_CHARS.search(node.value)
                and _BOUNDS["PLAIN_NOTATION_RULES"][0] not in node.value
            ):
                found.append(
                    (
                        path,
                        node.lineno,
                        "plain-notation rule (use inject_plain_notation_rules)",
                    )
                )
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _TODO.search(line):
                found.append(
                    (
                        path,
                        lineno,
                        "rule now in LATEX_SYSTEM_RULES (delete the local copy)",
                    )
                )
    return found


def _sources(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        yield path, tree


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    if not root.is_dir():
        # A mistyped path used to report "no local copies found" and pass.
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    diverged = 0
    copies = find_copies(root)
    for path, name, text in copies:
        if _squash(text) == _squash(CANONICAL[name]):
            print(f"OK       {path} :: {name}")
        else:
            diverged += 1
            print(
                f"DIVERGED {path} :: {name} (import it from pupiltree_latex.prompt_rules instead)"
            )
    for path, lineno, what in find_local_rules(root):
        print(f"LOCAL    {path}:{lineno} :: {what}")
    if not copies:
        print("no local copies found (good: import from pupiltree_latex.prompt_rules)")
    return 1 if diverged else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
