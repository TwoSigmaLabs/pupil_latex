"""Fail when a shared table is not emitted by every port's generator.

`python -m pupiltree_latex.export_tables` writes corpus/tables/*.json. The JS
(`js/scripts/gen-tables.mjs`) and Dart (`dart/pupiltree_latex/tool/gen_tables.dart`)
generators each keep their own list of table names, so a new table can be
silently skipped by a port. This check makes that a CI failure.

    python tools/check_generated_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = {
    "js": ROOT / "js" / "scripts" / "gen-tables.mjs",
    "dart": ROOT / "dart" / "pupiltree_latex" / "tool" / "gen_tables.dart",
}


def main() -> int:
    tables = sorted(p.stem for p in (ROOT / "corpus" / "tables").glob("*.json"))
    missing = 0
    for port, gen in GENERATORS.items():
        source = gen.read_text(encoding="utf-8")
        for name in tables:
            forms = (f"'{name}'", f'"{name}"', f"{name}:")
            if not any(form in source for form in forms):
                missing += 1
                print(f"MISSING  {port}: {gen.relative_to(ROOT)} does not emit {name}.json")
    if not missing:
        print(f"OK       {len(tables)} tables emitted by js and dart generators")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
