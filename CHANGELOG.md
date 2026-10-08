# Changelog

All three implementations (Python, Dart, JavaScript) share one version and one corpus. A version is releasable only when every harness is green.

## 1.3.0 (2026-10-08)

Bugs found while migrating Fillers, Backend, pupiltree-agents, script_editor and worksheet.ai to 1.2.0 (audit rounds 5 and 6). New corpus cases are tagged `audit5-<n>` and `audit6-<n>`; every fix is in Python, JavaScript and Dart.

**Versioning note.** These fixes were first prepared as 1.2.1 (a patch: new corpus cases only). The `normalize` padded-span trim below changes two existing `must_not_change` expectations, and CONTRACT §7 makes any change to a corpus expectation a minor bump, so everything ships together as 1.3.0. There is no 1.2.1 tag.

### Changed corpus expectations

- `must_not_change/audit4-6-space-before-closer` (`Compute $2x + 3 $.`, via `normalize`) and `must_not_change/audit4-6-space-before-closer-power` (`Find $3x^2 - 1 $ when x is 2`, via `normalize`) are removed. The same inputs are now `normalize` cases with the same ids, expecting `Compute $2x + 3$.` and `Find $3x^2 - 1$ when x is 2`.
- `normalize/audit5-8-padded-span-keeps-ne` (new in the untagged 1.2.1) now expects `$x \ne y$` instead of `$ x \ne y $`; the padded-span protection is still pinned by `normalize/audit5-8-untrimmed-padded-span-keeps-ne` (`$ x \ne y $5`, closer before a digit, unchanged).

Consumers that compare `normalize` output literally must re-check padded spans. `fix` and `canonicalize` output does not change: they already trimmed these spans.

### Fixed in every language

- **`normalize` trims a padded span (audit6-1).** Every frontend now displays stored content as `segment(normalize(text))`, and `segment` keeps pandoc's rule (no whitespace right inside the delimiters). A stored `Solve $ x + 1 = 0 $ for x.` or `Compute $2x + 3 $.` therefore showed as raw text in script_editor and was not drawn as maths in worksheet.ai's PDF, while the apps' old regexes rendered it. `normalize` now runs `canonicalize`'s padded-span trim (API §3 step 10a) right after `escapeCurrency` (new step 5a): `$ x + 1 = 0 $` → `$x + 1 = 0$`, `$2x + 3 $` → `$2x + 3$`, `$ x + 1$` → `$x + 1$`, `($ a^2 + b^2 $)` → `($a^2 + b^2$)`. Currency still wins: `Prices: $10, $20`, `$5 and $10`, `Rs $5 and $10`, `costs $5.`, `I paid $ 5 and got $ 3` and a closer followed by a digit (`pay $ x + 1 $5 now`) are unchanged. A single letter is not clearly math, so `where $ v $ is speed` stays padded, as it does in `fix`.
- **`to_plain` trims the same padding (audit6-2).** After `repair`, padded spans are trimmed with the amounts `escapeCurrency` reads as money masked first: `Compute $2x + 3 $.` → `Compute 2x + 3.` (was `Compute 2x + 3 .`), `($ a^2 + b^2 $)` → `(a² + b²)`, and `tts` now reads a padded span as maths (`Solve $ x^2 = 4 $.` → `Solve x squared = 4.`, was left with its dollars).
- **`to_plain` pairs math the way `segment` does (audit5-1).** `Rs $5 and $10` was `Rs 5 and 10`: the delimiter strip paired two amounts as a span. A dollar that `normalize`'s currency rule reads as money (the closer is followed by a digit, or there is no closer), outside every `segment` math span and followed by an amount, is now a literal dollar: `Rs $5 and $10`, `$5-$10`, `Rs $5 and $x^2$` → `Rs $5 and x²`.
- **Unpaired amounts keep their dollar (audit5-2).** `$5` and `costs $5.` were `5` / `costs 5.`; they stay `$5` / `costs $5.` in `text`, `pdf` and `compare` (`compare` already kept `\$5`, so a stored amount and a typed one still compare equal). A cut-off span keeps the old behaviour: `$45m` → `45m`, `$4\sqrt{3}s` → `4√3s`.
- **`to_plain` repairs first (audit5-3).** Every style runs `repair` with `guessWhitespace=true`, as `fix` does: `Area <FF>rac{1}{2}` → `Area 1/2`, `3 <TAB>imes 4` → `3 × 4`, `$x <LF>ightarrow y$` → `x → y`, `<BS>eta` → `β`, and ANSI colour codes are removed. A `\name:` whose name is in `SCRIPT_LABELS` is a label anywhere in a line, so a repaired `(<TAB>ool: timer)` reads `(\tool: timer)` (`text`) / `(tool: timer)` (`pdf`), not `(→ol: timer)`.
- **`fix` idempotency on `$ $` shapes (audit5-8).** `a $ $\nu$ b` became `a $ <LF>u$ b` in `normalize`, and `$\nu = $\frac{c}{\lambd$a^{{2}$}$}$` lost its `\nu` on a second `fix`: the prose-escape decoder paired `$ $` with a regex while `segment` renders `$\nu$`. A position is now protected when either `segment` or the regex calls it math (decoding is lossy, and a padded span that is not trimmed, such as `$ x \ne y $5`, must keep its `\ne`).

### Release tooling

- `propagate.yml`: worksheet.ai moved to `TwoSigmaLabs/worksheet.ai` (base `main`); every consumer now uses the one `PUPIL_LATEX_BUMP_TOKEN` secret (the `PUPIL_LATEX_BUMP_TOKEN_PUPILTREE` fallback is gone). A missing secret is a `::warning::` plus a run summary from a new `token` job and no bump job runs; on a tag run (called from `ci.yml`) the `resolve` and `bump` jobs are `continue-on-error`, so a consumer that cannot be bumped is an `::error::` on its own job and the release run stays green. Manual and `release`-event runs still fail.
- `tools/bump_consumer.py` (kind `fillers`): a `README*` next to a vendored `pupiltree-latex.iife.js` gets its `Version: X.Y.Z` line and `pupil_latex/releases/tag/vX.Y.Z` link rewritten (Fillers `frontend/static/vendor/pupiltree-latex/README.md`).

## 1.2.0 (2026-10-08)

Regressions found when the library was compared with the projects' own LaTeX code (audit round 4). New corpus cases are tagged `audit4-<n>`; every fix is in Python, JavaScript and Dart.

**Versioning note.** This release was prepared as 1.1.1, but two curated `to_plain` expectations change (below), and CONTRACT §7 makes any change to a corpus expectation a minor bump, so it ships as 1.2.0. There is no 1.1.1 tag. Consumers that compare `to_plain` output literally must re-check fractions.

### Fixed in every language

- **Identifiers stay prose (audit4-1).** `Gap: lo_0` no longer becomes `Gap: $lo_0$`: a two-letter lowercase base before `_` is an identifier. `x_0`, `v_1`, `a_n`, `H_2O`, `CO_2` still wrap.
- **Braces in prose are kept by `to_plain` (audit4-2).** `A = {1, 2, 3}`, `the set {a, b}` and the canvas `\mindmap: {"central": …}` JSON keep their braces; `1{,}000` and `{x}` are still grouping.
- **Simple fractions read `22/7` (audit4-3).** `to_plain` writes `a/b` when each part is a number or one letter, parenthesises compound parts (`(a+b)/(c+d)`), and wraps a fraction that touches a term (`2(1/2)`, `(1/2)mv²`).
- **Lesson-script labels survive `to_plain` (audit4-4).** `\instruction:` was `∈struction:` and `\heading:` lost its backslash; a label at a line start is kept verbatim in `text` and without the backslash in `pdf`/`tts`/`compare`.
  A consumer that shows `text` output to readers (worksheet.ai `cleanLatex`) and does not want `\heading:` should use `pdf`.
- **ANSI colour codes (audit4-5).** `repair` removes `ESC[1m … ESC[0m` whole, not just the ESC byte.
- **`$2x + 3 $` (audit4-6).** A formula with a space before its closing dollar is no longer escaped as currency by `normalize`; `canonicalize`/`fix` trim it to `$2x + 3$`. `Prices: $10, $20` and `$5 and $10` stay currency. `segment` keeps the pandoc closer rule.
- **Answer comparison (audit4-7, audit4-10).** New `to_plain(text, "compare")` style: `1/3` = `$\frac{1}{3}$`, `x^2` = `$x^2$`, `H_2O` = `$H_2O$`, `10^-3` = `$10^{-3}$`, `90°` = `$90^\circ$`, `−3` = `-3`. `text`/`pdf` keep U+2212 as written.
- **Chemistry without mhchem (audit4-8).** `fix(text, chemistry=False)` (JS `{chemistry: false}`, Dart `chemistry: false`; also `canonicalize`, `fix_deep`, `canonicalize_deep`) never wraps a bare `\ce{…}`/`\pu{…}`. `typesetMath` passes it automatically when KaTeX has no mhchem (`hasMhchem()`), so Fillers no longer shows a red `\ce` error.
- **Span merging keeps scope (audit4-9).** `$\forall$ $\flat$ $\bf x$` is no longer merged into one span (the `\bf` leaked); spans with a declaration switch (`DECLARATION_COMMANDS`) are never merged.
- **Flutter `*` between operands (audit4-11).** `MathText` escapes a spaced `*` in prose so gpt_markdown no longer reads `7/5 * (-3/12) + 7/5 * (5/12)` as emphasis.
- **Read path documented (audit4-12).** CONTRACT §3: the read path is `repair(guessWhitespace=False)`; `guessWhitespace=True` is the opt-in that restores TAB/LF/CR before unambiguous commands only. Corpus cases pin both.

### Changed corpus expectations

- `to_plain/curated-frac-and-script`: `(1)/(2)mv²` → `(1/2)mv²` (audit4-3).
- `to_plain/curated-nested-frac`: `((1)/(2))/(3)` → `(1/2)/3` (audit4-3).
- Nine harvested Backend `latex_to_plain` cases that expected `(1)/(2)`-style output moved to `corpus/review/to_plain_mismatches.json` (`backend-latex-to-plain-r2-0001/0006/0014/0021/0026/0027/0040`, `backend-latex-to-plain-no-residue-0003/0004`); their inputs are pinned again as curated `audit4-3-*` cases with the new output.

### API additions

- Python: `fix(text, *, chemistry=True)`, `fix_deep(obj, *, chemistry=True)`, `canonicalize(text, *, chemistry=True)`, `canonicalize_deep(obj, *, chemistry=True)`, `to_plain(text, "compare")`, `DECLARATION_COMMANDS`.
- JavaScript: `fix(text, {chemistry})`, `fixDeep(obj, {chemistry})`, `canonicalize(text, {chemistry})`, `canonicalizeDeep(obj, {chemistry})`, type `CanonicalizeOptions`, `toPlain(text, "compare")`, `DECLARATION_COMMANDS`; DOM: `hasMhchem(renderToString?)`, `TypesetOptions.chemistry`, `TypesetOptions.katex.renderToString`.
- Dart: `fix(text, {bool chemistry = true})`, `fixDeep(obj, {bool chemistry = true})`, `canonicalize(text, {bool chemistry = true})`, `canonicalizeDeep(obj, {bool chemistry = true})`, `toPlain(text, style: 'compare')`, `kDeclarationCommands`.
- Flutter adapter: `toMarkdownSource(text)` (what `MathText.processed` now uses), `operatorStar` (U+E02A stand-in) and `operatorStarPattern` (draws it as `*`). gpt_markdown 1.3.0 has no `\*` escape, so a spaced prose `*` is replaced by the stand-in instead of being backslash-escaped.
- Corpus: a case may carry `opts` (keyword options for `fix`/`canonicalize`); new table `corpus/tables/declaration_commands.json`.

## 1.1.0 (2026-09-26)

Corpus expectations changed, so consumers must bump their pin together (CONTRACT §7). New corpus cases are tagged `audit2-*` and `audit3-*`.

### Fixed in every language

- **Scientific notation and relations stay one formula.** `3×10⁸ m/s`, `6.022×10²³`, `x≤5`, `λ₁`, `ε₀`, `CuSO₄·5H₂O` used to produce `$$…$$` display blocks mid-sentence; they now become one inline span (`$3\times10^{8}$ m/s`). No closing `$` is ever emitted directly before a digit.
- **Greek words.** `2πr`, `fλ`, `hν`, `ωt`, `TΔS` become one span (`$2\pi r$`); units such as `5 µs`, `10 kΩ` are unchanged.
- **Script and argument groups.** `e^{iπ}`, `x_{α}`, `\frac{π}{2}`, `\sqrt{2π}` convert in one pass instead of nesting dollars.
- **Missing closing braces** are completed when the result is certain: `$\frac{1}{2$` → `$\frac{1}{2}$`. Empty arguments (`$\frac{1}{$`) are never guessed and stay as written.
- **Spaces inside dollars.** `Solve $ x^2 + 1 = 0 $` renders as one formula; `$ 5 and $ 3` stays currency.
- **Units upright.** `cm³`, `m/s²`, `mol⁻¹`, `mm³` use `\text{}`; variables like `x²` stay italic.
- **Mojibake currency.** `â‚¹`, `â‚¬`, `Â£`, `Â¥`, `Â¢` repair to `₹ € £ ¥ ¢` on the table path (no ftfy), instead of wrapping `¬` as math.
- **Repeated Greek letters.** `ππ`, `ωω`, `√√2` are no longer collapsed by the mojibake table.
- **Idempotency.** `\\\frac{1}{2}` and `$ H₂` now reach a fixed point in one call.
- **Text to speech.** `to_plain(…, "tts")` no longer leaves `\text`, `\ce`, `\left`, matrix or `\%` residue.
- **`fix_deep`** leaves `tags`, `labels` and `keywords` lists untouched.

### JavaScript and Dart catch-up

The ports now include the four 1.0.0 fixes that had only reached Python (matrix rows kept, one-argument `\frac` left alone, lowercase-only script labels, units after a number upright). Parity with Python on the table path (no ftfy) is exact.

### JavaScript

- No regex lookbehind anywhere. Minimum browsers are now Safari/iOS 14, Chrome/Edge 80, Firefox 78 (was Safari 16.4). The IIFE still fails soft (one `console.error`) on anything older.
- React `<MathText>`: a formula KaTeX cannot parse shows the grey source fallback instead of red error text; `fix`/`segment` are memoised.
- Astral-plane letters (`𝑥`) are handled by code point.

### Dart and Flutter

- No regex lookbehind, so Flutter web works on old Safari too.
- `MathText` renders `\ce{…}` and `\pu{…}` through a built-in translator (flutter_math_fork has no mhchem), finds math with the shared `segment()` so Flutter and web agree, and no longer lets `*` inside math turn into italics.
- Segment's closer rule uses the same digit class as Python and JavaScript.

### Tooling and docs

- `spec/CONTRACT.md` opens with the one call to make: `fix_deep` on the backend, `MathText` / `typesetMath` on the frontend.
- README install lines work: Flutter apps depend on `pupiltree_latex_flutter` only; JavaScript installs from the release tarball.
- CI checks that the JS and Dart generated tables are current and that every shared table is emitted (`tools/check_generated_tables.py`).
- `tools/check_prompt_parity.py` fails on a path that does not exist instead of passing.

## 1.0.0 (2026-09-25)

First version: `repair`, `normalize`, `canonicalize`, `segment`, `to_plain`, `audit`, `fix`, JSON transport and deep walkers in Python, Dart and JavaScript, with the shared corpus.
