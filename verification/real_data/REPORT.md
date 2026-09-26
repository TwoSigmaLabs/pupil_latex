# Real-data verification of pupiltree-latex

Run on 2026-09-25 by an independent verification agent over locally available production exports. Scripts and result JSON files sit next to this report (`extract_strings.py`, `verify_python.py`, `render_katex.mjs`, `verify_js.mjs`, `compare_parity.py`, `analyze.py`, `strings.json`, `python_results.json`, `katex_results.json`, `js_results.json`, `dart_results.json`, `parity_results.json`, `summary.json`, `real_data_changes.json`, `overreach_identifiers_wrapped.json`, `snapshot_hashes.txt`). No database or network access was used; PII-shaped keys, URL and e-mail values were skipped.

The eleven defects listed in §10 were **fixed in the library after this run** (see the `real-data-D*` tags in the corpus); the numbers below describe the state before those fixes.

## 1. Sources

| Source                                                                         | Files | Leaves | Unique strings | Changed by `fix` | Math segments before → after |
| ------------------------------------------------------------------------------ | ----: | -----: | -------------: | ---------------: | ---------------------------: |
| `mongo-backups/*.json` (6 pre-image dumps)                                     |     6 | 12,997 |          4,543 |               45 |                    342 → 343 |
| `pupiltree-agents/scripts/latex_test_output/before_ahs.json`                   |     1 |    477 |            203 |                5 |                      24 → 24 |
| `Backend/tests/**` fixtures                                                    |    30 |  2,983 |            886 |               12 |                    224 → 232 |
| `pupiltree-agents/tests/**`                                                    |     7 |    695 |             30 |                0 |                            0 |
| `script_editor/test/**`                                                        |    12 |    510 |             42 |                3 |                      44 → 44 |
| `corpus/harvested/*.json` (inputs only; deliberately broken unit-test strings) |     8 |  3,955 |          2,998 |            1,074 |                2,408 → 2,785 |
| **Total**                                                                      |    65 | 22,049 |      **8,702** |            1,140 |                3,042 → 3,428 |

"Real data" below means the 5,704 non-corpus strings.

## 2. Audit findings before and after `fix` (strings with at least one finding)

| Kind                     | Before | After | Real data before → after | Verdict on the remainder                                                       |
| ------------------------ | -----: | ----: | -----------------------: | ------------------------------------------------------------------------------ |
| control_char             |     38 |     0 |                    4 → 0 | fixed                                                                          |
| legacy_delimiter         |     33 |     0 |                    0 → 0 | fixed                                                                          |
| unbalanced_dollar        |     59 |    20 |                    0 → 0 | 17 orphan-`$` unit-test inputs unfixable; 3 library-made (D1, D2, fixed since) |
| mojibake                 |     29 |     2 |                    0 → 0 | `�` unfixable; cp1252 `Ïˆ` (D6, fixed since)                                   |
| bare_unicode_math        |    186 |    11 |                    2 → 0 | all radicand-less `√`, kept by design (#1654)                                  |
| bare_left_brace          |      2 |     0 |                    0 → 0 | fixed                                                                          |
| double_escaped_command   |      6 |     0 |                    0 → 0 | fixed                                                                          |
| unicode_chemistry        |      3 |     0 |                    2 → 0 | fixed                                                                          |
| command_missing_argument |     29 |    32 |                    0 → 0 | content (`\frac{x}`, `\sqrt` alone)                                            |
| frac_missing_args        |      9 |    10 |                    0 → 0 | content                                                                        |
| script_missing_braces    |      8 |     5 |                    0 → 1 | `$no_capture$` (D4, fixed since)                                               |
| unsupported_command      |      5 |     4 |                    0 → 0 | content (`\mathscr` …)                                                         |

On real data, `fix` left zero findings of any candidate-defect kind.

## 3. KaTeX rendering (throwOnError, strict "ignore", mhchem)

| Set                      | Segments | Failing |
| ------------------------ | -------: | ------: |
| All strings, original    |    3,042 |     496 |
| All strings, after `fix` |    3,428 |     496 |
| Real data, original      |      634 |       0 |
| Real data, after `fix`   |      643 |       0 |

All 434 unique failures come from harvested unit-test inputs that are broken by construction (argument-less `\frac`/`\sqrt`/`\text`, undefined `\textmu`, `\nicefrac`, `\root`, …). `fix` repaired six of them (`\left{ x \right}`, backspace-corrupted `\beta`/`\binom`, form-feed-corrupted `x^2` and `\frac`, a lone `pmatrix`) and worsened four (wrapping an argument-less structural command; merging a broken span into its neighbours, D7). Both classes are covered by rules added since.

## 4. Over-reach

URLs (56), 24-hex ids (340) and every 4+ letter word (88,696): zero violations apart from five correct control-character repairs (`\board`, `\times`, `\binom`, `\theta`, `\rightarrow`). Four real over-reaches were found and are fixed since: `lo_0` and `no_capture` wrapped as subscripts (D4), `grade_level: "6_A"` wrapped (D5), prose `…` turned into `$\ldots$` (D3).

## 5. Idempotency

Two violations, identical in all three languages, both caused by `\log_{10}` / `\bigcup_{i}` being read as a bare script right after a backslash (D1, fixed since).

## 6. Cross-language parity (8,702 strings × fix, segment, auditKinds, toPlain)

JavaScript and Dart agreed with each other on every string. Both differed from Python on six strings, all caused by Python's ftfy configuration: HTML entities (`&amp;`, D8) and CR/CRLF line breaks (D9). Both are aligned since (entity decoding in the table path; ftfy no longer rewrites line breaks).

## 7. `to_plain` residue

No backslash-command residue on any string. Remaining `$` are escaped currency (correct) or odd-`$` inputs; remaining braces are literal by design (`\left\{`) or JSON strings from the transport corpus, plus `1{,}000` (D10, fixed since).

## 8. Raw model responses

No genuine raw model responses exist in the local exports; the two JSON-shaped candidates parse with `loads_latex_aware` with no control characters in their leaves. This path is only weakly exercised by local data.

## 9. What `fix` changed on real data (65 strings)

- **35 lesson-script strings had their DSL labels corrupted** (`\teacher:` → TAB + `eacher:`, `\type:`, `\tool:`, `\read:`, `\thinkingroutine:`): defect D0, the one serious real-data finding, fixed since in `normalize`, `repair`, `escape_latex_for_json` and `canonicalize`.
- 10 literal `\n` sequences correctly turned into line breaks; 1 real TAB inside `$1\text{ cm}$` correctly restored to `\text`; 2 chemistry formulas wrapped; 5 answer-vector values wrapped (`√3` → `$\sqrt{3}$` …; the answer matcher compares through `to_plain`, so grading is unaffected); 3 ANSI colour codes (`ESC[1m`) dropped from a stored lesson plan (an upstream generator bug worth an issue); 4 homoglyph/NBSP/entity fixes; 5 over-reaches (§4, fixed since).
- Two stored documents carry `$<LF>ightarrow$` (a `\rightarrow` decoded through a `\n` escape). `audit` did not see it and `repair` could not restore it (D11): both now handle a control byte inside a math span whose letters spell exactly one command.

## 10. Defects found and their resolution

| #   | Finding                                                             | Resolution in the library                                                                                                          |
| --- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| D0  | `\teacher:` / `\type:` / `\tool:` / `\read:` decoded as escapes     | a `\word:` label is never an escape (normalize, transport, canonicalize); `repair` restores a decoded label; `SCRIPT_LABELS` table |
| D1  | `\log_{10}` wrapped as a bare script → unrenderable, non-idempotent | bare-script run may not follow `\`, `$` or the currency sentinel                                                                   |
| D2  | `$\sqrt$2` and `\$x^2$` made worse by currency/script rules         | currency scanner copies a math span through to its first closer; sentinel lookbehind fixed                                         |
| D3  | prose `…` → `$\ldots$`                                              | `…` removed from the wrappable set                                                                                                 |
| D4  | `no_capture`, `ai_recreate` wrapped as subscripts                   | a lowercase-word suffix (3+ letters) marks an identifier                                                                           |
| D5  | `grade_level: "6_A"` rewritten                                      | `grade_level`, `*_level` are non-content keys                                                                                      |
| D6  | cp1252 `Ïˆ` (ψ) not in the mojibake table                           | added                                                                                                                              |
| D7  | broken span merged into its neighbours                              | merge only self-contained spans (balanced braces, matched environments)                                                            |
| D8  | `&amp;` decoded by Python only                                      | table path decodes HTML entities too                                                                                               |
| D9  | CR/CRLF rewritten by Python only                                    | ftfy `fix_line_breaks=False`                                                                                                       |
| D10 | `1{,}000` keeps braces in `to_plain`                                | `{` triggers the conversion; image markers protected                                                                               |
| D11 | `$<LF>ightarrow$` invisible to `audit`, unrepairable                | flagged and repaired inside math spans                                                                                             |

Genuinely unfixable content (all from unit-test inputs, reported by `audit`): orphan `$`, `�`, argument-less `\frac`, `\textmu` / `\nicefrac` / `\root`, radicand-less `√`.

**Bottom line at the time of the run:** on 5,704 real production strings, `fix` produced zero candidate-defect audit findings, zero KaTeX failures (634 → 643 math segments, none failing), zero URL or id damage, and the three languages agreed on all but one string. The lesson-script label defect (D0) had to be fixed before `fix` could be applied to scripts; it is fixed and covered by corpus cases.
