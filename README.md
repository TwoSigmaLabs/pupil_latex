# pupiltree-latex

One contract, one test corpus, one API for LaTeX math text across every Pupiltree app.

**New here? Start with [USAGE.md](USAGE.md)**: install, the one call for backends, the one component for React, plain JavaScript and Flutter, with examples.

LaTeX bugs at Pupiltree were the same eight bug classes re-fixed in seven repos, in three languages, by nine copies of the same logic that drifted apart. This project replaces those copies with:

1. **A written contract** (`spec/CONTRACT.md`) for what math text looks like on the wire and where each fix is allowed to run.
2. **A shared conformance corpus** (`corpus/*.json`, ~3,400 cases converted from the existing test suites plus curated incident cases). Every implementation must pass it in CI. A fix added once becomes a test every app must pass.
3. **Three implementations with the same six functions** (`spec/API.md`): Python `pupiltree_latex`, Dart `pupiltree_latex` (+ a Flutter `MathText` widget), JavaScript `@pupiltree/latex` (+ a React `<MathText>` and a vanilla `typesetMath` for KaTeX auto-render).

## The one call

```python
from pupiltree_latex import fix, fix_deep
fix("Cost $5 and \\(\\theta\\) with \x0crac{1}{2} and π and H₂O")
# 'Cost \\$5 and $\\theta$ with $\\frac{1}{2}$ and $\\pi$ and $\\text{H}_{2}\\text{O}$'
```

`fix` runs repair, normalisation, canonicalisation and chemistry wrapping in one idempotent call. Backends call it on fresh model output before storing; the `MathText` widget (Flutter), `<MathText>` (React) and `typesetMath` (vanilla JS) call it by default on whatever they render, so a frontend developer only imports the component. `fix_deep` does the same over a whole document while leaving ids, URLs, timestamps and status enums alone. The six functions below are what `fix` is made of, for callers that need one step on its own.

## The six functions

| Function                | What it does                                                                                                        | Lossless           | Where it runs                                        |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------ | ---------------------------------------------------- |
| `repair(text)`          | Undo JSON-escape damage (`<FF>rac` → `\frac`, `<TAB>imes` → `\times`), drop other control bytes                     | yes                | everywhere: DB write sinks, read paths, clients      |
| `normalize(text)`       | Display-safe prep: `\(…\)` → `$…$`, orphan delimiters, currency `$5` → `\$5`, padded `$ x + 1 $` → `$x + 1$`, literal `\n` in prose, mojibake table | content-preserving | clients before rendering                             |
| `canonicalize(text)`    | Full write-time sanitiser: everything above plus Unicode → LaTeX, bare `\frac`/`H_{2}O`/`π` wrapping, brace fixes   | no (heuristic)     | **only** at the generation chokepoint, never on read |
| `segment(text)`         | The one tokenizer: prose / inline math / display math, escape- and brace-aware, currency-safe                       | yes                | every renderer                                       |
| `to_plain(text, style)` | LaTeX → Unicode text for PDFs (`pdf`), canvases and reports (`text`), speech (`tts`), answer matching (`compare`)   | lossy by design    | PDF, canvas, TTS, answer matching                    |
| `audit(text)`           | Detect what is still broken (12 finding kinds), never mutates                                                       | read-only          | logs, CI, editor hints                               |

Plus `escape_latex_for_json` / `loads_latex_aware` (decode model JSON without turning `\frac` into a form feed), deep walkers that skip ids, URLs and enums, and the prompt rule text (`LATEX_SYSTEM_RULES`, `NARRATIVE_PROSE_RULES`, `PLAIN_NOTATION_RULES`).

## Install

Every consumer pins a release tag. There is no package registry: installs come from the public repository `github.com/TwoSigmaLabs/pupil_latex` and the files attached to each GitHub release (the Python wheel, the npm tarball and the IIFE bundle). No credentials are needed.

```bash
# Python (Backend, pupiltree-agents, Fillers, worksheet.ai backend), through git
pip install "pupiltree-latex[ftfy] @ git+https://github.com/TwoSigmaLabs/pupil_latex@v1.4.0#subdirectory=python"

# Python without git (recommended for Docker builds: slim images have no git)
pip install "pupiltree-latex[ftfy] @ https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.4.0/pupiltree_latex-1.4.0-py3-none-any.whl"
# requirements.txt:
# pupiltree-latex[ftfy] @ https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.4.0/pupiltree_latex-1.4.0-py3-none-any.whl
```

```bash
# JavaScript (worksheet.ai, pupil-assessment-ui): package.json keeps this URL
npm install https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.4.0/pupiltree-latex-1.4.0.tgz
```

```html
<!-- Plain <script> pages (Fillers), next to KaTeX; Safari/iOS 14+, Chrome/Edge 80+, Firefox 78+ -->
<script src="https://cdn.jsdelivr.net/gh/TwoSigmaLabs/pupil_latex@v1.4.0/js/dist/pupiltree-latex.iife.js"></script>
```

```yaml
# Flutter apps (script_editor, tutor frontend) — pubspec.yaml
# Depend on the widget package ONLY. pupiltree_latex comes in transitively.
# Listing both packages with the same git tag fails pub version solving.
dependencies:
  pupiltree_latex_flutter:
    git:
      url: https://github.com/TwoSigmaLabs/pupil_latex
      ref: v1.4.0
      path: dart/pupiltree_latex_flutter
```

```yaml
# Pure-Dart consumers (no Flutter) — pubspec.yaml
dependencies:
  pupiltree_latex:
    git:
      url: https://github.com/TwoSigmaLabs/pupil_latex
      ref: v1.4.0
      path: dart/pupiltree_latex
```

Releasing: push a `v*` tag. CI runs every suite, then attaches `pupiltree_latex-X.Y.Z-py3-none-any.whl`, `pupiltree-latex-X.Y.Z.tgz` and `pupiltree-latex.iife.js` to the GitHub release. Publishing the release runs `.github/workflows/propagate.yml`, which opens a `chore: bump pupiltree-latex to vX.Y.Z` pull request in every consumer that already pins the library (it needs the `PUPIL_LATEX_BUMP_TOKEN` secret with contents and pull-request write on every consumer, all under TwoSigmaLabs including `TwoSigmaLabs/worksheet.ai`; see the workflow header). Without the secret the release still goes green and the run carries a warning; re-run propagate by hand once the secret is set.

## Use

```python
from pupiltree_latex import fix_deep, loads_latex_aware, audit_deep, repair_deep

doc = loads_latex_aware(model_response_text)        # transport: no \frac → form feed
doc = fix_deep(doc)                                 # write chokepoint, fresh Class A output only: this is all a backend needs
for path, finding in audit_deep(doc): log(path, finding.kind, finding.snippet)   # optional
stored = repair_deep(mongo_doc)                     # optional, lossless: any write sink or read path
```

```dart
import 'package:pupiltree_latex_flutter/pupiltree_latex_flutter.dart';
MathText(question.text)                             // normalize → segment → gpt_markdown/flutter_math
```

```tsx
import { MathText } from "@pupiltree/latex/react";
<MathText text={option.text} />; // normalize → segment → KaTeX + mhchem
```

```js
// Fillers, vanilla
PupiltreeLatex.typesetMath(rootElement); // repair + mask currency + KaTeX auto-render + audit
```

## Run the tests

```bash
cd python && python -m pytest                       # ~3,400 corpus checks + behaviour tests
cd dart/pupiltree_latex && dart test
cd js && npm test
```

`python -m pupiltree_latex.corpus` (from `python/`) runs the corpus without pytest; the Dart and JS packages have the same harness.

## Add a fix

1. Reproduce the bug as a corpus case first: add it to the curated list in `tools/build_corpus.py` (or a harvested file), tag it with its bug class (B1–B8) and issue, and run `python tools/build_corpus.py`. The build fails until the Python implementation meets the expectation.
2. Fix Python, then Dart, then JS. A change is not mergeable until all three harnesses are green.
3. Tag a version (`v1.x.y`). Publishing its release opens the pin-bump pull requests in the consumers.

The eight bug classes: B1 JSON-escape corruption, B2 a surface that skips the renderer (caught by `tools/lint_plain_text_sites.py`, not by the library), B3 currency `$`, B4 delimiter variants and orphans, B5 pipeline step order, B6 mojibake and bare Unicode, B7 over-reach (rewriting ids, URLs, `√2`, `Q17`), B8 plain-text conversion residue.

## Layout

```
spec/CONTRACT.md            the rules; spec/API.md the function semantics
corpus/<function>.json      the executable spec; corpus/tables/ the shared constants (generated from Python)
corpus/harvested/           cases converted from the old test suites (input to the build)
corpus/review/              harvested cases the implementation rejects, with what it produced instead
python/                     reference implementation + tests
dart/pupiltree_latex        pure Dart port;  dart/pupiltree_latex_flutter  the MathText widget
js/                         TypeScript port, React and DOM adapters, IIFE bundle
tools/build_corpus.py       curated cases + harvested → corpus/*.json
tools/lint_plain_text_sites.py   CI check for math fields rendered as plain text (bug class B2)
tools/check_prompt_parity.py     CI check that a service's prompt rules match spec/CONTRACT.md
tools/bump_consumer.py           moves a consumer's pin to a new tag (used by .github/workflows/propagate.yml)
```

## Where this came from

Backend `services/ai/helper/latex_rules.py`, `unicode_to_latex.py`, `latex_audit.py`, `baa_render_meta.latex_to_plain`, `services/ai/utils._latex_aware_escape` (the reference sanitiser, ~700 tests); pupiltree-agents `katex_commands.py`, `escape_latex_for_json`, the TTS cleaner; script_editor `latex_preprocess.dart`, `mojibake_fixer.dart`, `ScriptEditorTex`; Fillers `period_content_renderer.js`; worksheet.ai `MathText.js`.
