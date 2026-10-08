"""pupiltree-latex: one contract, one corpus, one API for math text.

    from pupiltree_latex import fix            # the one call
    from pupiltree_latex import repair, normalize, canonicalize, segment, to_plain, audit

See ``spec/API.md`` for the semantics each function guarantees and
``spec/CONTRACT.md`` for where each one may run.
"""

from __future__ import annotations

from .audit import (
    ALL_KINDS,
    ERROR_KINDS,
    Finding,
    audit,
    audit_deep,
    audit_kinds,
    count_by_kind,
    is_error,
)
from .canonicalize import canonicalize, canonicalize_deep
from .fix import (
    DECLARATION_COMMANDS,
    SINGLE_LETTER_UNITS,
    UNIT_BASES,
    escape_text_specials,
    fix,
    fix_deep,
    merge_adjacent_math,
    wrap_bare_symbol_commands,
    wrap_unicode_chemistry,
    wrap_unicode_scripts,
)
from .commands import (
    COLLAPSE_COMMANDS,
    JSON_WHITESPACE_COLLISION_COMMANDS,
    KATEX_COMMANDS,
    LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
    STRUCTURAL_COMMANDS,
)
from .json_transport import escape_latex_for_json, loads_latex_aware, loads_model_json
from .mojibake import HTML_ENTITIES, MOJIBAKE_TABLE, fix_mojibake_ftfy, fix_mojibake_table, unescape_html_entities
from .normalize import (
    decode_escapes_outside_math,
    escape_currency,
    normalize,
    normalize_delimiters,
    strip_orphan_delimiters,
)
from .prompt_rules import (
    LATEX_SYSTEM_RULES,
    NARRATIVE_PROSE_RULES,
    has_formatting_contract,
    inject_latex_rules,
    inject_narrative_prose_rules,
    narrative_field_exemption,
)
from .repair import repair, repair_deep
from .segment import Segment, contains_math, is_plain_prose, segment
from .to_plain import LATEX_CMD_MAP, STYLES, to_plain
from .unicode_math import (
    GREEK_MATH_LETTERS,
    GREEK_UNIT_SYMBOLS,
    HOMOGLYPHS,
    JOINING_CHARS,
    JOINING_COMMANDS,
    UNICODE_MATH,
    WRAPPABLE_BARE_CHARS,
)
from .walk import NON_CONTENT_KEY_SUFFIXES, NON_CONTENT_KEYS

VERSION = "1.2.1"
__version__ = VERSION

__all__ = [
    "VERSION",
    "fix",
    "fix_deep",
    "wrap_unicode_chemistry",
    "wrap_bare_symbol_commands",
    "merge_adjacent_math",
    "wrap_unicode_scripts",
    "escape_text_specials",
    "repair",
    "repair_deep",
    "normalize",
    "normalize_delimiters",
    "strip_orphan_delimiters",
    "escape_currency",
    "decode_escapes_outside_math",
    "canonicalize",
    "canonicalize_deep",
    "segment",
    "Segment",
    "contains_math",
    "is_plain_prose",
    "to_plain",
    "STYLES",
    "audit",
    "audit_kinds",
    "audit_deep",
    "Finding",
    "ALL_KINDS",
    "ERROR_KINDS",
    "count_by_kind",
    "is_error",
    "escape_latex_for_json",
    "loads_latex_aware",
    "loads_model_json",
    "fix_mojibake_table",
    "fix_mojibake_ftfy",
    "unescape_html_entities",
    "HTML_ENTITIES",
    "LATEX_SYSTEM_RULES",
    "NARRATIVE_PROSE_RULES",
    "inject_latex_rules",
    "inject_narrative_prose_rules",
    "narrative_field_exemption",
    "has_formatting_contract",
    "LATEX_COMMANDS_BEHIND_JSON_ESCAPES",
    "JSON_WHITESPACE_COLLISION_COMMANDS",
    "KATEX_COMMANDS",
    "COLLAPSE_COMMANDS",
    "STRUCTURAL_COMMANDS",
    "UNICODE_MATH",
    "HOMOGLYPHS",
    "WRAPPABLE_BARE_CHARS",
    "LATEX_CMD_MAP",
    "MOJIBAKE_TABLE",
    "NON_CONTENT_KEYS",
    "NON_CONTENT_KEY_SUFFIXES",
    "JOINING_CHARS",
    "JOINING_COMMANDS",
    "UNIT_BASES",
    "SINGLE_LETTER_UNITS",
    "GREEK_MATH_LETTERS",
    "GREEK_UNIT_SYMBOLS",
    "DECLARATION_COMMANDS",
]
