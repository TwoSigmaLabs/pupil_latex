# Final real-data re-verification

Re-run on 2026-09-25 over the same 8,702 strings as `REPORT.md` (5,704 real strings from the six mongo pre-image dumps, the AHS export and repo fixtures; 2,998 harvested unit-test inputs that are broken by construction), after the fixes from the first real-data run and the adversarial review. Scripts and results: `defects_check.py`, `timing.py`, `timing_results.json`, regenerated `python_results.json`, `katex_results.json`, `summary.json`, `real_data_changes.json`; the previous run's results are in `prev/`.

## Audit findings (strings with at least one finding, before → after `fix`)

| Kind                     | previous run | this run | real data, this run |
| ------------------------ | ------------ | -------- | ------------------- |
| control_char             | 38 → 0       | 40 → 0   | 6 → 0               |
| legacy_delimiter         | 33 → 0       | 33 → 0   | 0 → 0               |
| unbalanced_dollar        | 59 → 20      | 59 → 17  | 0 → 0               |
| mojibake                 | 29 → 2       | 29 → 2   | 0 → 0               |
| bare_unicode_math        | 186 → 11     | 123 → 11 | 2 → 0               |
| bare_left_brace          | 2 → 0        | 2 → 0    | 0 → 0               |
| double_escaped_command   | 6 → 0        | 6 → 0    | 0 → 0               |
| unicode_chemistry        | 3 → 0        | 3 → 0    | 2 → 0               |
| command_missing_argument | 29 → 31      | 29 → 32  | 0 → 0               |
| frac_missing_args        | 9 → 10       | 9 → 10   | 0 → 0               |
| script_missing_braces    | 8 → 5        | 8 → 3    | 0 → 0               |
| unsupported_command      | 5 → 4        | 13 → 12  | 0 → 0               |

The audit now sees the two real `$<LF>ightarrow$` strings (control_char 38 → 40 before) and reports `\textmu` and friends as unsupported. On real data `fix` leaves zero findings of any kind.

## Rendering, over-reach, idempotency, residue, timing

- **KaTeX** (throwOnError, strict "ignore", mhchem): real data 634 → 645 math segments, 0 failing before and after. All 434 unique failures are harvested unit-test inputs; `fix` repaired 6 and introduced 4, one of which was a real regression (matrix rows, fixed since; see below).
- **Over-reach**: 0 URLs, ids or image markers damaged; every lost 4+ letter word is a correct control-byte repair. Three gap titles `lo_0`, `lo_1`, `lo_2` are still wrapped as subscripts (indistinguishable from `x_0`; the generator should write a title).
- **Idempotency**: 0 violations on all 8,702 strings (previous run: 2).
- **`to_plain` residue** on real data: 0 (previous run had `1{,}000`).
- **Timing**: `fix` over all 8,702 strings (976 k chars) takes 1.40 s, 0.16 ms per string on average; the slowest string (40 kB lesson plan) 60 ms; linear at about 1.5 µs per character.
- **What `fix` changes on the 4,543 mongo-dump strings**: 17 strings, all correct repairs (two `\rightarrow` control bytes, a TAB-corrupted `\tool:` and `\text`, two chemistry formulas, three ANSI codes dropped) or harmless merges of adjacent spans, plus the three `lo_0` titles. All 37 lesson scripts keep every `\label:` line byte-for-byte.

## Defects D0–D11 from the first run

All confirmed fixed by `defects_check.py` (script labels, `\log_{10}`, `$\sqrt$2`, prose `…`, `no_capture`, `grade_level`, `Ïˆ`, broken-span merging, `&amp;`, CR/LF, `1{,}000`, `$<LF>ightarrow$`).

## New findings from this run and their resolution

| #            | Finding                                                                                         | Resolution                                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| R1 (serious) | `\\` row separator collapsed when the next letters spell a command (`a&b\\cos x` → `a&b\cos x`) | Collapse skips any math span holding `\begin{` or `&`; single-letter names never collapsed; audit ignores those spans |
| R2           | `Gap: lo_0` → `$lo_0$`                                                                          | Not changed: `lo_0` is indistinguishable from `x_0`; content issue for the generator                                  |
| R3           | `Host: Priya\nGuest: Vikram` no longer decoded (label rule too broad)                           | Labels are lowercase words only                                                                                       |
| R4/R5        | orphan-`$` inputs made differently broken (corpus only)                                         | Left: unbalanced input, reported by `audit`                                                                           |
| R6           | `\tbinom{x}` (one argument) wrapped, then fails                                                 | Two-argument commands need two `{` to be wrapped                                                                      |
| C1           | adjacent spans merged in already-correct content                                                | Accepted: renders identically                                                                                         |
| C2           | `240 cm³` → italic `$cm^{3}$`                                                                   | A lowercase base after a number becomes `\text{cm}^{3}`                                                               |
| C3           | ANSI codes leave `[1m`                                                                          | Upstream generator bug                                                                                                |

## Verdict

On the six mongo dumps the library changes 17 of 4,543 strings, each a correct repair or a harmless rewrite except the three `lo_0` titles; nothing is lost, every resulting formula renders, `fix` is idempotent and linear. With the matrix-row rule fixed, it is safe to apply to that content and to math-heavy collections. The JavaScript and Dart ports were mid-change during this run, so their parity was verified separately by the port harnesses on the shared corpus.
