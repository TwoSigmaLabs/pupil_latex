# pupiltree_latex_flutter

The `MathText` widget every Pupiltree Flutter app renders math text with:
`fix` → `segment`-based `\(…\)` / `\[…\]` delimiters → gpt_markdown (≥ 1.3.0,
plusparse) → flutter_math_fork. A formula that fails to parse shows its
source in grey italic.

## Depending on it

**Flutter apps: depend on `pupiltree_latex_flutter` ONLY.** It brings
`pupiltree_latex` with it (a path dependency inside the same git repo), and
`package:pupiltree_latex/pupiltree_latex.dart` is importable as usual.

```yaml
dependencies:
  pupiltree_latex_flutter:
    git:
      url: https://github.com/TwoSigmaLabs/pupil_latex
      ref: v1.2.0
      path: dart/pupiltree_latex_flutter
```

Do not list `pupiltree_latex` as well. Listing both with the same git tag
fails pub version solving: the app's git source and the widget's path
source are different sources for the same package.

Pure-Dart consumers (no Flutter) depend on `dart/pupiltree_latex` alone.

## Flutter-only behaviour

- `\ce{…}` and `\pu{…}` are translated to plain LaTeX before
  flutter_math_fork draws them (`ceToLatex`), because flutter_math_fork has
  no mhchem. Web clients load the real mhchem extension instead. Notation
  the translator does not know is left as written, and shows as source.
- Inline `\(…\)` is claimed through `inlinePatterns` before gpt_markdown
  parses emphasis, so `$a$ * $b*c$` draws both formulas.

## Tests

```
flutter analyze
flutter test
```
