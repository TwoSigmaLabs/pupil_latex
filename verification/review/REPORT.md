# Adversarial review of the Python reference implementation

Run on 2026-09-25 by an independent reviewer agent against the Python package, with a KaTeX 0.16 + mhchem server for rendering checks. Scripts and logs sit next to this report: `fuzz.py` (property fuzzer, 3,000-input bounded run plus a 20,000-input generation phase), `attacks.py` (targeted attacks, `attacks_log.txt`), `consistency.py` (cross-function properties on 3,879 corpus strings + 1,200 random inputs, `consistency_log.txt`), `katex_triage.py`, `verify_final.py` (re-verification, `verify_final_log.txt`), `katex_server.js` / `katex_client.py`, `probe.py`.

**Every finding below was fixed in the library after this run** and is covered by corpus cases tagged `review-*`; the numbers describe the state before those fixes.

## 1. Spec / code disagreements (all resolved)

| #     | Finding                                                                                                             | Resolution                                                                                         |
| ----- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| S1    | Spec said a rejected inline closer is skipped; code lets the first candidate decide                                 | Spec corrected (code was right)                                                                    |
| S2    | Spec said the narrow set decides outside math in the JSON transport; code used the full vocabulary minus four names | Spec corrected; `PROSE_ESCAPE_COMMANDS` is now a shared constant used by transport and `normalize` |
| S3/S4 | Script-label and in-math repair rules undocumented; in-math rule fired on unterminated spans                        | Documented; rule now needs a closing `$` and ≥3 letters                                            |
| S5    | Only ~115 commands had doubled backslashes collapsed                                                                | Every KaTeX command plus `ce`, `pu`; odd runs (line breaks) never collapsed                        |
| S6    | `10⁻³` / `mc²` outside math never converted                                                                         | `fix` gained `wrap_unicode_scripts`                                                                |
| S7    | URL stash regex could be cut by the chemistry wrapper                                                               | URL regex excludes `$`; chemistry lookbehind excludes `_`                                          |
| S8    | `cbrt` treated as structural; `textmu` etc. accepted by audit                                                       | `cbrt` removed; those commands are reported as unsupported                                         |
| S9    | `\ ` and `\<digit>` kept in JSON → parser raised                                                                    | Doubled                                                                                            |
| S10   | `normalize` deleted NBSP and `—`+superscripts                                                                       | NBSP → space; dash rule removed                                                                    |
| S11   | `to_plain` split real commands at a shorter prefix (`\neg` → `≠g`)                                                  | Never peel a KaTeX command; ~45 map entries added                                                  |

## 2. Failures by root cause (A = unrenderable or text lost, B = wrong but readable, C = cosmetic)

| ID  | Sev | Root cause                                                      | Reproducer                             | Was                                                 | Now                                                 |
| --- | --- | --------------------------------------------------------------- | -------------------------------------- | --------------------------------------------------- | --------------------------------------------------- |
| F1  | A   | Unicode converted inside `\text{}`                              | `$\text{H₂O}$`                         | `$\text{H_{2}O}$` (parse error)                     | unchanged                                           |
| F2  | A   | each script char became its own `^{}`                           | `$10⁻³$`                               | `$10^{-}^{3}$`                                      | `$10^{-3}$`                                         |
| F3  | A   | `$` parity counted `$$` twice                                   | `$$x⃗$$`                               | `$$$\vec{x}$$$`                                     | `$$\vec{x}$$`                                       |
| F4  | A   | `\\{2,}cmd` ate a row break                                     | `$$a \\\frac{1}{2}$$`                  | `$$a \frac{1}{2}$$`                                 | unchanged                                           |
| F5  | A   | currency scanner vs `$1$$\gamma$`                               | `$1$γ`                                 | not idempotent                                      | `$1 \gamma$`                                        |
| F6  | A   | pure-math wrapper re-wrapped an unpaired `$`                    | `$ H₂`                                 | not idempotent                                      | left alone                                          |
| F7  | A   | `\ ` / `\1` kept in JSON                                        | `{"q": "5\ \text{m}"}`                 | `JSONDecodeError`                                   | parses                                              |
| F8  | A   | NBSP deleted                                                    | `5 km` (NBSP)                          | `5km`                                               | `5 km`                                              |
| F9  | B   | `—`+superscript deleted                                         | `10—¹ range`                           | `10 range`                                          | unchanged                                           |
| F10 | B   | C1 stripped after the table created a new key                   | `Î` + U+009E                           | `Π` on 2nd pass                                     | `Ξ` (generated table)                               |
| F11 | B   | in-math repair on an unterminated span                          | `$\no`                                 | `$\to` on 2nd pass                                  | unchanged                                           |
| F12 | B   | argument-less command wrapped whole                             | form feed + `rac`                      | `$\frac$`                                           | `\frac`                                             |
| F13 | B   | digit runs braced inside an identifier                          | `$q_001_easy_2026$`                    | double subscript                                    | unchanged                                           |
| F14 | B   | `\\cdots`, `\\ce{}` not collapsed                               | `\\cdots`                              | `$\\cdots$`                                         | `\cdots` → `$\cdots$` by `fix`                      |
| F15 | B   | prefix peeling in `to_plain`                                    | `$\neg p$`, `$a \leqslant b$`          | `≠g p`, `a ≤slant b`                                | `¬ p`, `a ≤ b`                                      |
| F16 | B   | tts regexes                                                     | `$x^{20}$`, nested `\frac`, `\pmatrix` | `x squared0`, `frac1 over 23`, `plus or minusatrix` | `x to the power 20`, `(1 over 2) over 3`, `pmatrix` |
| F17 | B   | recursion per brace level                                       | 1,000 nested braces                    | `RecursionError`                                    | falls back to a flat strip                          |
| F18 | B   | entity decoding once per pass                                   | `&amp;amp;`                            | not idempotent                                      | `&`                                                 |
| F19 | C   | lone surrogates                                                 | `\ud83d x`                             | `� x`, audit forever                                | dropped                                             |
| F20 | C   | TAB + English word                                              | `Draw<TAB>an angle`                    | `\tan`                                              | unchanged (Backend production rule; documented)     |
| F21 | C   | `\nu` vocabulary differed between `normalize` and the transport | `Given\nu = 5 cm`                      | two readings                                        | one vocabulary: a line break                        |
| F22 | C   | `$`, `%` inside math never escaped                              | `$\text{costs $5}$`, `$50%$`           | unrenderable                                        | `\$`, `\%` via `fix`                                |

Passed unchanged: all currency examples, nested `\frac` depth 20, `\left{`/`\right}` across spans, identifier tokens, Hindi/Hebrew prose with commands, emoji/ZWJ/BOM, multi-line `\(…\)`/`\[…\]`, matrices and cases, image markers (12 in one string, one inside math, one inside a URL), JSON round trip of 5,079 control-free strings, `repair` idempotent on 5,079 inputs, `segment` slices reassemble every input, `audit(fix(x))` never reports `control_char`, `legacy_delimiter` or `bare_left_brace`.

## 3. Performance (10 kB inputs)

| Shape                                      | Before   | After                              |
| ------------------------------------------ | -------- | ---------------------------------- |
| Greek prose `α β γ π ω …`                  | 3,217 ms | 224 ms                             |
| `a⃗ a⃗ …`                                  | 1,749 ms | 74 ms                              |
| `audit` on Greek prose                     | 747 ms   | 162 ms                             |
| 900 newlines                               | 101 ms   | 40 ms                              |
| `$a{$a{…` (unclosed brace after every `$`) | 919 ms   | ~2 s, pathological input, accepted |
| 1,000 nested braces in `to_plain`          | crash    | flat fallback                      |

Cause of the quadratic paths: every helper re-scanned `$` parity from the start of the string per match. All of them now share one math-span mask per call (`spans.py`), built from the same tokenizer the renderers use.

## 4. Cross-function consistency

`normalize(canonicalize(x)) == canonicalize(x)` has 291 exceptions by design: `canonicalize` neither escapes `$5x`-style currency with an even `$` count nor decodes literal `\n`; callers who need both use `fix`. `fix(x)` is a fixed point of `normalize`, `canonicalize` and `fix` on every input that had an exception before (F5, F6, F10, F18).
