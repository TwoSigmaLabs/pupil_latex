# Changelog

All three implementations (Python, Dart, JavaScript) share one version and one corpus. A version is releasable only when every harness is green.

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
