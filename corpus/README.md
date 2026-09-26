# The conformance corpus

`<function>.json` files are the executable specification. Every implementation runs all of them in CI (`python -m pytest` in `python/`, `dart test` in `dart/pupiltree_latex`, `npm test` in `js/`).

Do not edit these files by hand. They are written by `python tools/build_corpus.py` from:

- the **curated** cases in that script (explicit expectations for every bug class and production incident), and
- the **harvested** cases in `harvested/` (assertions transcribed from the existing test suites of Backend, pupiltree-agents, script_editor, Fillers, worksheet.ai and the tutor frontend on 2026-09-25; see `harvested/README.md`).

A harvested case is admitted only when the Python implementation reproduces its assertion. The rest are written to `review/<function>_mismatches.json` together with what Python produced (`python_got`), for a human to decide whether the old test or the new implementation is right. Most of them are helper-level assertions (a single step called directly, which the full pipeline is expected to differ on) or renderer assertions the corpus cannot express.

## Case schema

```json
{
  "id": "curated-currency-range",
  "input": "$5-$10",
  "expected": "\\$5-\\$10",
  "tags": ["B3"],
  "impl": ["python", "dart", "js"],
  "source": "script_editor/test/.../latex_preprocess_test.dart::currency",
  "note": "optional"
}
```

Assertion shapes (exactly one per case):

| Field                             | Meaning                                                                                                                  |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `expected`                        | exact output. String functions are also checked to be idempotent on their own output                                     |
| `contains` / `not_contains`       | substrings that must / must not appear in a string output                                                                |
| `kinds_include` / `kinds_exclude` | audit kinds that must / must not occur                                                                                   |
| `json_contains`                   | `{"key": "substring"}` on a parsed JSON object                                                                           |
| `must_render`                     | `segment` yields a math segment; with `"engine": "katex"` the JS harness also renders it with KaTeX and expects no error |
| `property: "idempotent"`          | `f(f(x)) == f(x)`                                                                                                        |
| `expected_error: true`            | the JSON parser must raise                                                                                               |

Modifiers: `variant: "hard"` (repair with `guess_whitespace=false`), `style` (`to_plain`), `impl` (which implementations the case applies to; default all three), `via` (the source function the assertion was made through).

`must_not_change.json` lists inputs that every function in its `functions` list must return unchanged (for `segment`: one text segment; for `audit`: no findings).

`tables/*.json` are the shared constants, generated from the Python package by `python -m pupiltree_latex.export_tables`; the Dart and JS packages generate their table sources from them.
