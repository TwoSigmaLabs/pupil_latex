# Using pupiltree-latex

This guide shows how to add pupiltree-latex to a Pupiltree app and fix LaTeX in one line. It covers Python backends, React and plain JavaScript frontends, and Flutter apps.

You do not need to know LaTeX rules to use it. Import it, call one function (or render one component), and the maths, chemistry, currency and decimals in your content display correctly.

## What it fixes

| Problem in the content                            | Example input                             | After the library                                             |
| ------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------- |
| Unicode maths from the model                      | `Speed of light 3×10⁸ m/s`                | `Speed of light $3\times10^{8}$ m/s`                          |
| Chemistry and powers                              | `Water is H₂O and the area is πr²`        | `Water is $\text{H}_{2}\text{O}$ and the area is $\pi r^{2}$` |
| Dollar amounts mistaken for maths                 | `It costs $5 and $10`                     | `It costs \$5 and \$10`                                       |
| Old delimiters                                    | `Solve \(x^2 - 5x + 6 = 0\)`              | `Solve $x^2 - 5x + 6 = 0$`                                    |
| Bare commands in any language                     | `समीकरण \frac{3}{4} और π = 3.14 हल करें।` | `समीकरण $\frac{3}{4}$ और $\pi$ = 3.14 हल करें।`               |
| JSON damage (`\f` of `\frac` read as a form feed) | form feed + `rac{1}{2}`                   | `$\frac{1}{2}$`                                               |
| Garbled characters (mojibake)                     | `â‚¹500`                                  | `₹500`                                                        |
| A missing closing brace                           | `$\frac{1}{2$`                            | `$\frac{1}{2}$`                                               |

Things it leaves exactly as written: decimals (`2.5583`), Indian grouping (`₹2,50,000`), percentages, ratios (`9:3:3:1`), degrees, ids, URLs, timestamps, image markers, and prose in any script.

Things it never guesses: a formula with a missing piece, such as `$\frac{1}{$`. It is left as written and reported by `audit`, so you can regenerate it instead of showing a student a wrong fraction.

## Install

Pin a release tag. All three packages share one version number. The repository `TwoSigmaLabs/pupil_latex` is public, so no GitHub token is needed anywhere.

**Python** (Backend, pupiltree-agents, Fillers, worksheet.ai backend):

```bash
pip install "pupiltree-latex[ftfy] @ git+https://github.com/TwoSigmaLabs/pupil_latex@v1.3.0#subdirectory=python"
```

That line needs `git`. Slim Docker images do not have it, so for Docker builds install the wheel attached to the release instead (recommended). In `requirements.txt`:

```text
pupiltree-latex[ftfy] @ https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.3.0/pupiltree_latex-1.3.0-py3-none-any.whl
```

The `[ftfy]` extra gives the best repair of garbled characters. Without it the library uses its built-in table, which covers the common cases.

**JavaScript and React** (worksheet.ai, pupil-assessment-ui):

```bash
npm install https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.3.0/pupiltree-latex-1.3.0.tgz
npm install katex        # needed for rendering; react too if you use <MathText>
```

`package.json` then lists `"@pupiltree/latex": "https://github.com/.../pupiltree-latex-1.3.0.tgz"`. No `vendor/` folder is needed.

**Flutter** (script_editor, tutor frontend), in `pubspec.yaml`:

```yaml
dependencies:
  pupiltree_latex_flutter:
    git:
      url: https://github.com/TwoSigmaLabs/pupil_latex
      ref: v1.3.0
      path: dart/pupiltree_latex_flutter
```

Add only the Flutter package. It brings in the core `pupiltree_latex` package for you. Listing both with the same tag makes `flutter pub get` fail.

**Plain HTML pages with no bundler** (Fillers): load the bundle from jsDelivr, pinned to the tag, after KaTeX:

```html
<script src="https://cdn.jsdelivr.net/gh/TwoSigmaLabs/pupil_latex@v1.3.0/js/dist/pupiltree-latex.iife.js"></script>
```

To serve it yourself instead, download `pupiltree-latex.iife.js` from the v1.3.0 release and put it next to your KaTeX files.

**Upgrading**: when a new version is released, every consumer that already pins the library gets a `chore: bump pupiltree-latex to vX.Y.Z` pull request. Read the CHANGELOG section it links, let CI run, and merge.

## Backend: one call before you save

Call `fix_deep` on fresh model output before it is stored. It walks the whole document, fixes every text field, and leaves ids, URLs, timestamps and status fields alone.

```python
from pupiltree_latex import loads_latex_aware, fix_deep

doc = loads_latex_aware(model_response_text)   # parse model JSON without turning \frac into a form feed
doc = fix_deep(doc)                            # fix every text field
collection.insert_one(doc)
```

Example:

```python
fix_deep({"_id": "q_1", "question": "Area = πr²", "options": [{"text": "2πr"}], "imageUrl": "https://x/a_b.png"})
# {'_id': 'q_1', 'question': 'Area = $\\pi r^{2}$', 'options': [{'text': '$2\\pi r$'}], 'imageUrl': 'https://x/a_b.png'}
```

Why `loads_latex_aware` matters: Python's `json.loads` reads `\f` in `\frac` as a form feed and `\t` in `\times` as a tab. `loads_latex_aware` keeps the commands intact.

For a single string, use `fix`:

```python
from pupiltree_latex import fix
fix("Speed of light 3×10⁸ m/s")   # 'Speed of light $3\\times10^{8}$ m/s'
```

Put the same LaTeX rules in your prompts so the model writes clean output in the first place:

```python
from pupiltree_latex import inject_latex_rules
system_prompt = inject_latex_rules(system_prompt)
```

## React frontend: one component

```tsx
import "katex/dist/katex.min.css";
import { MathText } from "@pupiltree/latex/react";

<MathText text={question.text} />
<MathText text={option.text} as="span" className="option" />
```

`MathText` runs `fix` on the text, then renders prose as text and maths with KaTeX. Chemistry in `\ce{…}` works because mhchem is loaded for you. A formula KaTeX cannot read shows as grey source text, never as a blank or a red error.

## Plain JavaScript page: one function

```html
<link rel="stylesheet" href="katex/katex.min.css" />
<script src="katex/katex.min.js"></script>
<script src="katex/contrib/mhchem.min.js"></script>
<script src="katex/contrib/auto-render.min.js"></script>
<script src="pupiltree-latex.iife.js"></script>
<script>
  if (window.PupiltreeLatex) {
    PupiltreeLatex.typesetMath(document.getElementById("lesson"));
  }
</script>
```

`typesetMath` fixes every text node under the element, keeps dollar amounts as text, and renders the maths. Running it twice on the same element is safe.

If the page does not load `mhchem.min.js`, `typesetMath` notices (`PupiltreeLatex.hasMhchem()`) and leaves a bare `\ce{…}` as text instead of turning it into a red error. Pass `{ chemistry: true }` or `{ chemistry: false }` to decide yourself; `fix(text, { chemistry: false })` does the same for one string.

Supported browsers: Safari and iOS 14 or newer, Chrome and Edge 80 or newer, Firefox 78 or newer. On anything older the script logs one console error and does nothing, so check `window.PupiltreeLatex` before calling it.

## Flutter app: one widget

```dart
import 'package:pupiltree_latex_flutter/pupiltree_latex_flutter.dart';

MathText(question.text)
MathText(option.text, style: Theme.of(context).textTheme.bodyLarge, maxLines: 2)
```

`MathText` runs `fix`, renders prose with markdown and maths with flutter_math. Chemistry in `\ce{…}` and units in `\pu{…}` are translated for you, because flutter_math has no chemistry support of its own. A formula that cannot be read shows as grey source text.

## Other outputs: PDF, plain text and speech

Use `to_plain` (Python), `toPlain` (JavaScript and Dart) when the target cannot render LaTeX.

```python
from pupiltree_latex import to_plain

to_plain(r"$\frac{1}{2}$ of $\text{H}_{2}\text{O}$", "text")   # '1/2 of H₂O'   canvases, reports
to_plain(r"$\frac{1}{2}$ of $\text{H}_{2}\text{O}$", "pdf")    # '1/2 of H₂O'   PDF export
to_plain(r"$x^{2} + \frac{1}{2}$", "tts")                      # 'x squared + (1 over 2)'   text to speech
to_plain(r"$\frac{1}{3}$", "compare") == to_plain("1/3", "compare")   # True   answer matching
```

`compare` gives one form for comparing a typed answer with a stored one: `x^2` and `$x^2$` both become `x^2`, `H_2O`, `H₂O` and `$\text{H}_{2}\text{O}$` become `H_2O`, `−3` becomes `-3`, `$90^\circ$` becomes `90°`, and spaces around operators go. Since 1.4.0 `compare` also folds compatibility characters (full-width `ｘ＝５` → `x=5`, `½` → `1/2`, `㎝` → `cm`, `℃` → `°C`, thin and no-break spaces, `–` → `-`), decodes HTML entities like Python's `html.unescape` (`5&thinsp;m` → `5 m`), drops a leading option label (`B) 8-celled`, `(A) 2/4`, `C. x^2`, `D: 5` → the answer alone) and drops unpaired `$` / `\)` halves (`3.2$ m` → `3.2 m`), so a consumer needs no NFKC, entity or label code of its own. Every style repairs mojibake (`Ï€` → `π`); `text`/`pdf` write bare chemistry in prose as Unicode (`H_2SO_4` → `H₂SO₄`, identifiers such as `lo_0` stay). `text` and `pdf` keep braces in prose (`A = {1, 2, 3}`), keep lesson-script labels at a line start (`\instruction:`; `pdf` drops the backslash) and keep the minus sign `−` as written.

## Checking content: audit

`audit` finds what is still broken without changing anything. Use it in logs, CI, or to decide when to regenerate a question.

```python
from pupiltree_latex import audit, audit_deep

[(f.kind, f.snippet) for f in audit(r"Broken $\frac{1}{$ here")]
# [('frac_missing_args', 'Broken $\\frac{1}{$ here')]

for path, finding in audit_deep(doc):
    logger.warning("latex %s at %s: %s", finding.kind, path, finding.snippet)
```

A good backend pattern: `fix_deep` the model output, `audit_deep` the result, and ask the model again if any finding is an error.

## Same names in every language

| Task                    | Python                  | JavaScript                  | Dart                      |
| ----------------------- | ----------------------- | --------------------------- | ------------------------- |
| Fix one string          | `fix(text)`             | `fix(text)`                 | `fix(text)`               |
| Fix a whole document    | `fix_deep(doc)`         | `fixDeep(doc)`              | `fixDeep(doc)`            |
| Parse model JSON safely | `loads_latex_aware(s)`  | `loadsLatexAware(s)`        | `loadsLatexAware(s)`      |
| LaTeX to plain text     | `to_plain(text, style)` | `toPlain(text, style)`      | `toPlain(text, style: …)` |
| Find what is broken     | `audit(text)`           | `audit(text)`               | `audit(text)`             |
| Render                  | none                    | `<MathText>`, `typesetMath` | `MathText` widget         |

Every function gives the same output in all three languages for the same input. A shared set of about 3,900 test cases checks this in CI.

## Rules of thumb

- **Call `fix` or `fix_deep` on fresh model output, not only at display time.** The frontend components fix again anyway, and `fix` is safe to run many times.
- **Store the fixed text.** Every app then reads clean content.
- **Do not write your own LaTeX clean-up.** If something still renders wrong, report it with the exact input text. The fix goes into this library once, with a test, and every app gets it.
- **Write `\$` for a literal dollar sign inside maths,** and leave plain amounts like `$5` as they are; the library escapes them.

## Reporting a problem

Open an issue on `TwoSigmaLabs/pupil_latex` with:

1. The exact input text, copied from the database or API response.
2. What you saw and where (which app and screen).
3. What you expected.

Maintainers: see "Add a fix" in `README.md`. Each fix starts as a test case in the shared set and then lands in Python, Dart and JavaScript together.
