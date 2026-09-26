# Harvested conformance corpus

Test vectors transcribed from the existing unit tests of Backend, pupiltree-agents,
script_editor, Fillers, worksheet.ai and the tutor frontend (`origin/develop`).
Harvested on 2026-09-25. Nothing here was computed by running a sanitiser: every
`input`/`expected` is a test literal, and table sweeps (`sweep` field) were expanded
from the module constants (`_UNICODE_MATH`, `_HOMOGLYPHS`, `_WRAPPABLE_BARE_CHARS`,
`JSON_WHITESPACE_COLLISION_COMMANDS`, `KATEX_COMMANDS`, `_TYPOGRAPHIC_LATEX`) exactly
as the parametrized tests expand them.

## Files

| File                   | Cases | Sources covered                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------- | ----: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `repair.json`          |    83 | Backend `test_read_path_byte_identical_a8.py` (30: `repair_hard_control_bytes`, `sanitize_db_response`, all `variant: "hard"`), Backend `test_llm_json_latex_contract_1651.py` (21: `repair_control_chars_deep`, incl. the mocked-Mongo writer sinks), agents `test_content_integrity_531.py` (25: `repair_control_char_corruption`, `repair_control_chars_deep`), script_editor `latex_preprocess_test.dart` control-char group (5: `restoreControlCharCommands`, asserted through `preprocessLatexText`), Fillers `stripControlChars` (2, tagged `legacy-lossy`)                                                                                                                 |
| `normalize.json`       |    55 | script_editor `latex_preprocess_test.dart` (33: `preprocessLatexText` with `via` = step name: `normalizeMathDelimiters`, `decodeEscapesOutsideMath`, `stripOrphanMathDelimiters`, `escapeCurrencyDollars`; ORDERING group pins step order), `mojibake_fixer_test.dart` (14: `via: "mojibake"`), `latex_pipeline_audit_test.dart` (1), `latex_e2e_reality_test.dart` (1), Fillers `normalizeMathDelimiters` (3), tutor `student_valid_math_test.dart` (3, from `origin/develop`)                                                                                                                                                                                                    |
| `canonicalize.json`    |  1289 | Backend `test_latex_rules.py` (134: `sanitize_latex_text`, `sanitize_json_strings`), `test_unicode_to_latex.py` (1042: full `_UNICODE_MATH` sweep in three contexts x2 functions, `_HOMOGLYPHS` sweep, root-glyph contract, edge cases; `via` = helper name), `test_sqrt_keeps_its_argument_1654.py` (52), `test_read_path_byte_identical_a8.py` write-path snapshot (19: `sanitize_json_strings`), `test_latex_escape_fix.py` (10: `fix_common_latex_errors`, `sanitize_latex_option`, unmapped helpers), agents `test_narrative_prose_latex.py` (32: `strip_typographic_latex`, unmapped helper)                                                                                 |
| `segment.json`         |    73 | worksheet.ai `MathText.test.js` (54: 47 CORPUS `must_render` entries, 3 `splitMath` exact splits, 4 DOM properties), Fillers `maskEscapedDollars` (6 exact, sentinel U+E000) + 3 jsdom KaTeX render properties, script_editor `latex_e2e_reality_test.dart` (10: math-span counts)                                                                                                                                                                                                                                                                                                                                                                                                 |
| `to_plain.json`        |   141 | Backend `test_latex_to_plain.py` (30), `test_latex_to_plain_r2.py` (60; `style: "pdf"` = `mark_accents=True`, `style: "text"` otherwise), `test_latex_to_plain_no_residue.py` (51: `via` = `plain_text`, 30 exact + 21 residue-only properties)                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `audit.json`           |    85 | Backend `test_latex_audit.py` (76: `audit_latex_text`; `expected` is the ordered kind list, or a `property` when the test only checks membership/count), `test_latex_rules.py` (9: `validate_latex_text`, warnings as substring properties or `[]`)                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `json_transport.json`  |  1763 | agents `test_latex_never_corrupts.py` (1469: `escape_latex_for_json`, incl. 370 collision-command cells and 1042 `KATEX_COMMANDS` cells; `safe_json_loads`; AHS `_parse_json_object`), agents `test_escape_latex_newlines.py` (56), agents `test_content_integrity_531.py` (6: unmapped parse paths), Backend `test_latex_parser_known_failures_10.py` (146: 140 cells, 8 `expected_failure: true` for the strict xfails), `test_llm_json_latex_contract_1651.py` (54: 8 parsers x 6 wires + `_validate_content_body`), `test_loads_model_json.py` (20, 5 `expected_error`), `test_latex_control_char_corruption.py` (8), `test_latex_rules.py` (4: `parse_json_with_latex[_any]`) |
| `must_not_change.json` |   499 | Index of every `output == input` assertion above, deduplicated on (input, via, function, source): canonicalize 440, repair 44, normalize 11, to_plain 2, segment 2. These inputs also remain in their function file.                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

Total: 3,988 cases (3,489 function cases + 499 index rows).

## Conventions

- `via`: the source function/step the assertion was made through. Helper-level cases
  (`_wrap_bare_scripts` etc. are exercised through `sanitize_latex_text`; `unicode_math_to_latex`,
  `wrap_bare_unicode_math`, `normalize_homoglyphs`, `convert_combining_vec` are direct) should be
  re-verified through the full pipeline.
- `options`: keyword arguments the test passed (`inside_math_only`, `wrap_bare`).
- `property` with `expected: null`: the test asserts a predicate, not an exact string.
  `"idempotent"` is recorded once per input.
- `expected_error: true`: the parser must raise (`json_transport`). `expected_failure: true`:
  the source test is a strict `xfail` (frozen legacy parser); the property is what the
  test WANTS, and today's Backend parser does not satisfy it.
- `sweep`: the case is one row of a table expansion.
- `variant: "hard"`: Backend read-path repair (`repair_hard_control_bytes`), which only
  reverses BS/FF and drops other C0 bytes; TAB/LF/CR untouched, DEL kept.
- `style`: `to_plain` accent mode (`text` default, `pdf` = `mark_accents=True`).
- `must_render: true` (`segment`): the string must typeset without a KaTeX/flutter_math error;
  `math_spans` records the asserted span count where a test counted them.
- Tags: B1 control chars/JSON escapes, B3 currency, B4 delimiters/orphans, B5 step order or
  idempotency, B6 mojibake/unicode, B7 must-not-change/over-reach, B8 to-plain residue,
  plus `repo#issue` from the test name or docstring, `legacy-lossy` for Fillers.
- Notes flag pinned over-reaches that are NOT desired behaviour: A8 write-path snapshot wraps
  a YouTube id (`$l_CySKUI5W4$`) and an unlisted enum (`$ai_recreate$`), and rewrites
  TAB+`an` to `\tan`; the Backend#1598 parser cells decode `\nu` after an unpaired `$`
  as a newline; script_editor e2e documents a mojibake leak. Review before adopting.
- Control characters and backslashes are real characters JSON-escaped by `json.dump`
  (`ensure_ascii=False`). Python non-raw literals such as `"5\text{ N}"` were transcribed
  with the real TAB the test creates.

## Skipped (and why)

- Tests that need Mongo, HTTP, files or private fixtures: Backend `test_llm_json_latex_contract_1651.py`
  source-scan ratchets (`test_every_module_that_writes_*`, `test_class_practice_pass2_array_branch_*`,
  `test_the_session_and_master_plan_writers_call_the_sink_by_name`), `_extract_story_image_slugs`,
  `normalise_class_practice_segments` (its assertion is on `sanitize_question_text`, which strips `$`);
  agents `test_content_integrity_531.py` LLM-graph tests (`llm_writer_node` etc.), option-numbering
  and answer-key tests (not LaTeX); agents `test_latex_never_corrupts.py` prompt-contract half
  (`inject_latex_rules`, `ensure_formatting_contract`, adapters, v3.3 generators) and
  `_repair_json_syntax`. The mocked-Mongo writer tests WERE harvested at the string level because
  the assertion is on the `repair_control_chars_deep` sink.
- Logging tests: `test_log_latex_warnings_*`, `test_migration_log_*`, `test_no_diff_logging_by_default`.
- Non-string inputs (`None`, `42`, lists, datetime/ObjectId coercion, `sanitize_json_strings` dict
  walking as such): recorded only where a string leaf carries a LaTeX assertion.
- Backend `test_latex_rules.py::sanitize_option_text` tests (chemistry `\text{}` preservation) and
  `inject_latex_rules`/`LATEX_SYSTEM_RULES` tests: not in the function mapping.
- Backend `tests/test_fix_latex_currency_1582.py`: the only direct `sanitize_latex_text` call
  (`test_no_currency_means_no_placeholders_and_todays_pipeline`) uses it as an oracle
  (`_postprocess_field(...) == (sanitize_latex_text(model), None)`) and asserts nothing about its
  output, so nothing could be recorded; the `_freeze_currency`/`_postprocess_field` cases are
  route-level placeholder logic.
- Backend `test_latex_escape_fix.py` parity tests (`sanitize_choice_text`, `answers_match`,
  `sanitize_options`) and `test_latex_to_plain_r2.py::_safe` (fpdf Latin-1 transliteration):
  not to_plain/canonicalize contracts. `strip_math_markup`/`normalize_answer` were not wanted.
- Backend `test_latex_audit.py`: `audit_document` (dict paths, JSON-leaf decoding), `make_snippet`,
  `severity_for`, `Finding` immutability; snippet `<0x..>` requirement is kept as a note.
- script_editor `latex_pipeline_audit_test.dart` groups A-F and `latex_e2e_reality_test.dart`
  LEAK 1/3/4/5: the assertion is only "widget builds" or documents a leak as the current
  behaviour (B2 / not a string contract). `toBracketDelimiters` and `renderedHintsFor` are the
  renderer hand-off direction, not in the mapping.
- Fillers: everything except the three pure helpers (template/DOM/CI structure tests). `null -> ''`
  cases dropped (non-string).
- worksheet.ai: `**bold**` markdown test and the empty/undefined render test.
- agents `test_narrative_prose_latex.py`: mutant-function tests and `_TYPOGRAPHIC_SPAN_RE` regex
  tests (the table-reachability assertion is recorded as 5 cases).
