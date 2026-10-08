# The Pupiltree math-text contract

Version 1.3.0 (2026-10-08). This file is the single description of what math text looks like on the wire between the LLM services, the database and every renderer. `pupiltree-latex` implements it; `python/pupiltree_latex/prompt_rules.py` carries the same rules as prompt text.

## If you read only one thing

- **Backend**: call `fix_deep(doc)` (Python) on fresh Class A model output (§2) at the write chokepoint, once, before storing. For model JSON, decode it with `loads_latex_aware(text)` first, so `\frac` does not become a form feed. `fix_deep` skips ids, URLs, timestamps, enums and taxonomy lists (§5).
- **Frontend**: render with `MathText` (Flutter), `<MathText>` (React) or `PupiltreeLatex.typesetMath(el)` (vanilla JS). They call `fix` by default on whatever they render.

Nothing else is needed. The six functions below (`repair`, `normalize`, `canonicalize`, `segment`, `to_plain`, `audit`) are what `fix` is made of, for callers that need one step on its own; `to_plain` is for PDF, canvas and TTS output.

```python
from pupiltree_latex import fix_deep, loads_latex_aware

doc = fix_deep(loads_latex_aware(model_response_text))  # then store doc
```

## 1. Canonical form

A **canonical** string is what every generator writes and every store holds.

| Rule                    | Canonical                                                                 | Not canonical                   |
| ----------------------- | ------------------------------------------------------------------------- | ------------------------------- |
| Inline math             | `$…$`                                                                     | `\(…\)`                         |
| Display math            | `$$…$$`                                                                   | `\[…\]`                         |
| Currency                | `\$5`                                                                     | `$5`                            |
| Commands                | one backslash: `\frac`                                                    | `\\frac`, `\\\\frac`            |
| Multi-character scripts | `x^{10}`, `a_{12}`                                                        | `x^10`                          |
| Literal braces in math  | `\left\{ … \right\}`                                                      | `\left{ … \right}`              |
| Encoding                | UTF-8, NFC                                                                | mojibake (`Ï€`, `Ã—`)           |
| Control characters      | none except TAB, LF, CR                                                   | form feed, backspace, other C0  |
| Math symbols            | LaTeX commands inside `$…$` (`$\pi$`, `$\times$`)                         | bare `π`, `×`, `H₂O`            |
| Chemistry               | `$\text{H}_{2}\text{O}$`                                                  | `H2O`, `H₂O`                    |
| Prose                   | plain text; no `\text{}` around ordinary words                            | `$\text{Coulomb}$`              |
| Command set             | the intersection of KaTeX and flutter_math_fork (see `katex_commands.py`) | `\mathscr`, `\mathfrak`, `\cal` |

Markdown emphasis (`**bold**`, `*italic*`) is allowed in prose and must not appear inside a math span.

## 2. Two content classes

- **Class A: renderable math text.** Questions, options, explanations, remedies, AHS content, lesson scripts, assessments. Canonical form applies. Generated through prompts that carry `LATEX_SYSTEM_RULES`.
- **Class B: plain narrative or plain Unicode.** Podcast and story scripts (narration read by TTS), and period plans / in-class questions produced by the master-plan generators, which use Unicode subscripts and arrows on purpose. Prompts carry `NARRATIVE_PROSE_RULES` or a "no LaTeX" notation rule. The library must never "upgrade" Class B text to LaTeX. `canonicalize` is only called at Class A write chokepoints.

## 3. Where each function may run

| Function       | Lossless           | Write path (fresh model output) | DB write sink (any content) | Read path | Client before render | PDF / canvas / TTS          |
| -------------- | ------------------ | ------------------------------- | --------------------------- | --------- | -------------------- | --------------------------- |
| `fix`          | no (heuristic)     | yes, Class A (`fix_deep`)       | no                          | no        | yes (the components) | before `to_plain` if needed |
| `repair`       | yes                | yes                             | yes                         | yes       | yes                  | yes                         |
| `normalize`    | content-preserving | yes                             | no                          | no        | yes                  | before `to_plain` if needed |
| `canonicalize` | no (heuristic)     | **only here**, Class A          | no                          | **never** | no                   | no                          |
| `segment`      | yes                | –                               | –                           | –         | yes                  | –                           |
| `to_plain`     | lossy by design    | –                               | –                           | –         | –                    | yes                         |
| `audit`        | read-only          | yes (log)                       | yes (log)                   | optional  | debug                | –                           |

The read path serves stored bytes plus `repair`. This is the lesson of Backend #1595 and the 14 September 2026 incident (a full sanitiser replay over stored content rewrote `√2` as `$\sqrt$2` in about 11k fields).

**The read path is exactly `repair(text, guessWhitespace=False)`** (`repair_deep(doc, False)`): it restores a form feed, backspace or vertical tab that was a command (`<FF>rac` → `\frac`), removes ANSI colour codes and other control bytes, and keeps every TAB, LF and CR as stored. A service that knows its stored text went through a JSON parser may opt in to `guessWhitespace=True`, which additionally restores TAB/LF/CR only before an unambiguous command (`<TAB>ext{` → `\text{`, `<TAB>imes`, `<TAB>heta`, `<TAB>an`, `<LF>ightarrow` inside a closed `$…$`); never `<LF>u` or `<LF>e`, which are line breaks as often as `\nu`/`\ne`. Corpus tag `audit4-12` pins both forms.

**Clients display stored content through `normalize` then `segment`.** `segment` keeps pandoc's rule (no whitespace right inside the delimiters), so `normalize` trims a padded span with the same rule `canonicalize` uses (`Solve $ x + 1 = 0 $` → `Solve $x + 1 = 0$`, `Compute $2x + 3 $.` → `Compute $2x + 3$.`; amounts such as `I paid $ 5 and got $ 3` stay). Content stored before `fix` existed therefore renders without a rewrite (tag `audit6-1`, since 1.3.0).

**Answer comparison** uses `to_plain(text, "compare")` on both sides (API §5), so a typed `1/3`, `x^2`, `H_2O`, `−3` or `90°` equals the stored `$\frac{1}{3}$`, `$x^2$`, `$H_2O$`, `-3` or `$90^\circ$`.

**`to_plain` repairs its input itself**: it runs `repair(text)` with `guessWhitespace=True`, the same as `fix`, so a PDF, canvas or TTS caller does not call `repair` first (`Area <FF>rac{1}{2}` → `Area 1/2`). It reads math spans as `segment` does and keeps an amount's dollar (`Rs $5 and $10`, `costs $5.`) in every style (tags `audit5-1`–`audit5-3`).

**Renderers without mhchem** (Fillers loads KaTeX core only) call `fix(text, chemistry=False)`; `typesetMath` does so automatically when `\ce` does not parse. Loading `katex/contrib/mhchem` is the alternative.

## 4. Rendering

Every app renders through one adapter built on `segment`:

- Flutter: `MathText` (gpt_markdown + flutter_math_fork, `Strict.ignore`, plain-prose fast path, error fallback shows the source in grey italic).
- Web (React): `<MathText>` (KaTeX + mhchem, `throwOnError: false`, `strict: "ignore"`, `trust: false`, source in `<code>` on error).
- Web (vanilla, Fillers): `typesetMath(root)` (KaTeX auto-render with masked currency and lossless repair).

A formula that fails to parse shows its source, never a red box, never nothing. `audit` reports it.

## 5. Field names that are never content

Values under these keys are passed through untouched by the deep walkers: ids (`_id`, `id`, `*Id`, `*_id`), URLs and paths (`url`, `*Url`, `*_url`, `path`, `filename`, …), tokens and secrets, e-mail and phone, names and usernames, timestamps (`createdAt`, `*_at`, `*_date`), status enums (`status`, `type`, `mode`, `role`, …), class metadata (`grade`, `section`, `board`, `subject`, `className`), versions and MIME types, taxonomy lists (`tags`, `labels`, `keywords`: `{"tags": ["x_1"]}` stays as it is). Any string that is wholly a URL or ends in a media/file extension is also skipped. `{{IMAGE:…}}` markers survive every function unchanged.

## 6. Prompt text

`LATEX_SYSTEM_RULES` (Class A) and `NARRATIVE_PROSE_RULES` (Class B) live in `python/pupiltree_latex/prompt_rules.py`. Services must inject them through `inject_latex_rules` / `inject_narrative_prose_rules`, which are idempotent, and may append `narrative_field_exemption(...)` when one JSON object mixes both classes. The consumer CI check `tools/check_prompt_parity.py` fails when a service carries a diverged copy of this text.

## 7. Versioning

Semantic versions as git tags (`v1.2.0`). A change that alters any corpus expectation is a minor bump; a change that only adds cases or fixes a case all implementations already agreed on is a patch. Consumers pin a tag.
