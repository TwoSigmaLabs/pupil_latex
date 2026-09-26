"""Fail when a service carries a diverged copy of the prompt rules.

Every LLM service must inject `LATEX_SYSTEM_RULES` / `NARRATIVE_PROSE_RULES`
from `pupiltree_latex.prompt_rules`. Until each repo has migrated, this
check compares any local copy found in the repo (a Python string assigned
to a name ending in `LATEX_SYSTEM_RULES` or `NARRATIVE_PROSE_RULES`) with
the package text, ignoring whitespace differences.

    python tools/check_prompt_parity.py <repo-dir>
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from pupiltree_latex.prompt_rules import LATEX_SYSTEM_RULES, NARRATIVE_PROSE_RULES  # noqa: E402

CANONICAL = {
    "LATEX_SYSTEM_RULES": LATEX_SYSTEM_RULES,
    "NARRATIVE_PROSE_RULES": NARRATIVE_PROSE_RULES,
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


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def find_copies(root: Path) -> list[tuple[Path, str, str]]:
    copies: list[tuple[Path, str, str]] = []
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
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
    return copies


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
    if not copies:
        print("no local copies found (good: import from pupiltree_latex.prompt_rules)")
    return 1 if diverged else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
