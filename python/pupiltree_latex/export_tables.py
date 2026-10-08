"""Write the shared constant tables to ``corpus/tables/*.json``.

The Python package is the source of every table; the Dart and JS packages
load or embed these JSON files so the three implementations cannot drift.

    python -m pupiltree_latex.export_tables [out_dir]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import (
    COLLAPSE_COMMANDS,
    HOMOGLYPHS,
    JSON_WHITESPACE_COLLISION_COMMANDS,
    KATEX_COMMANDS,
    LATEX_CMD_MAP,
    LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
    MOJIBAKE_TABLE,
    NON_CONTENT_KEY_SUFFIXES,
    NON_CONTENT_KEYS,
    STRUCTURAL_COMMANDS,
    UNICODE_MATH,
    VERSION,
    WRAPPABLE_BARE_CHARS,
)
from .commands import (
    ARGUMENT_COMMANDS,
    AUDIT_EXTRA_ALLOWED_COMMANDS,
    NON_KATEX_MODEL_EMISSIONS,
    SCRIPT_LABELS,
    UNSUPPORTED_COMMANDS,
)
from .fix import DECLARATION_COMMANDS, SINGLE_LETTER_UNITS, SYMBOL_COMMANDS, UNIT_BASES
from .mojibake import HTML_ENTITIES
from .unicode_math import (
    GREEK_MATH_LETTERS,
    GREEK_UNIT_SYMBOLS,
    JOINING_CHARS,
    JOINING_COMMANDS,
)
from .walk import FILE_EXTENSIONS, NOT_RENDERED_KEYS, URL_PREFIXES

TABLES = {
    "katex_commands": sorted(KATEX_COMMANDS),
    "non_katex_model_emissions": sorted(NON_KATEX_MODEL_EMISSIONS),
    "json_whitespace_collision_commands": sorted(JSON_WHITESPACE_COLLISION_COMMANDS),
    "latex_commands_behind_json_escapes": sorted(LATEX_COMMANDS_BEHIND_JSON_ESCAPES),
    "collapse_commands": list(COLLAPSE_COMMANDS),
    "structural_commands": list(STRUCTURAL_COMMANDS),
    "argument_commands": list(ARGUMENT_COMMANDS),
    "unsupported_commands": list(UNSUPPORTED_COMMANDS),
    "audit_extra_allowed_commands": sorted(AUDIT_EXTRA_ALLOWED_COMMANDS),
    "unicode_math": UNICODE_MATH,
    "homoglyphs": HOMOGLYPHS,
    "wrappable_bare_chars": "".join(sorted(WRAPPABLE_BARE_CHARS)),
    "latex_cmd_map": LATEX_CMD_MAP,
    "mojibake_table": MOJIBAKE_TABLE,
    "non_content_keys": sorted(NON_CONTENT_KEYS),
    "non_content_key_suffixes": list(NON_CONTENT_KEY_SUFFIXES),
    "not_rendered_keys": sorted(NOT_RENDERED_KEYS),
    "script_labels": sorted(SCRIPT_LABELS),
    "symbol_commands": sorted(SYMBOL_COMMANDS),
    "html_entities": HTML_ENTITIES,
    "url_prefixes": list(URL_PREFIXES),
    "file_extensions": list(FILE_EXTENSIONS),
    "joining_chars": "".join(sorted(JOINING_CHARS)),
    "joining_commands": sorted(JOINING_COMMANDS),
    "unit_bases": sorted(UNIT_BASES),
    "single_letter_units": "".join(sorted(SINGLE_LETTER_UNITS)),
    "greek_math_letters": "".join(sorted(GREEK_MATH_LETTERS)),
    "greek_unit_symbols": list(GREEK_UNIT_SYMBOLS),
    "declaration_commands": list(DECLARATION_COMMANDS),
}


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, value in TABLES.items():
        path = out_dir / f"{name}.json"
        path.write_text(
            json.dumps(
                {"version": VERSION, "name": name, "value": value},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


if __name__ == "__main__":
    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[2] / "corpus" / "tables"
    )
    for p in export(target):
        print(p)
