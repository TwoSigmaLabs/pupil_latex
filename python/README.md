# pupiltree_latex (Python)

The reference implementation of the Pupiltree math-text contract. See the repository `README.md` and `spec/API.md` for the full description.

```bash
pip install "pupiltree-latex[ftfy] @ git+https://github.com/TwoSigmaLabs/pupil_latex@v1.2.1#subdirectory=python"
```

```python
from pupiltree_latex import (
    repair, normalize, canonicalize, segment, to_plain, audit,
    repair_deep, canonicalize_deep, audit_deep,
    escape_latex_for_json, loads_latex_aware,
    inject_latex_rules, inject_narrative_prose_rules,
)
```

- `ftfy` is optional. With it, `canonicalize` repairs mojibake patterns the built-in table does not know; without it the table is used. `normalize` never needs it.
- Python 3.10 or newer, no other dependencies.
- Tests: `python -m pytest` (runs the shared corpus in `../corpus` plus behaviour tests). `python -m pupiltree_latex.corpus` runs the corpus alone.
- `python -m pupiltree_latex.export_tables` regenerates `../corpus/tables/*.json`, the source of the Dart and JS constant tables.
