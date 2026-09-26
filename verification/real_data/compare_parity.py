"""Cross-language parity: Python vs JS vs Dart on the same real strings.

Reads python_results.json, js_results.json, dart_results.json; writes
parity_results.json with every mismatch (up to 30 examples per language and
field) and prints the summary.
"""

from __future__ import annotations

import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return {r["id"]: r for r in json.load(fh)}


S = {
    s["id"]: s
    for s in json.load(open(os.path.join(HERE, "strings.json"), encoding="utf-8"))
}
PY = load("python_results.json")
OTHERS = {"js": load("js_results.json"), "dart": load("dart_results.json")}
FIELDS = [
    "fix",
    "audit_before",
    "audit_after",
    "segments",
    "to_plain_text",
    "to_plain_pdf",
]


def norm_segments(segs):
    return [
        {
            "kind": s["kind"],
            "display": bool(s["display"]),
            "value": s["value"],
            "raw": s["raw"],
        }
        for s in segs
    ]


def snippet(s, n=300):
    return s if len(s) <= n else s[:n] + "…"


out = {}
for lang, R in OTHERS.items():
    counts = Counter()
    examples = {f: [] for f in FIELDS}
    ids_mismatched = set()
    for sid, py in PY.items():
        other = R.get(sid)
        if other is None:
            counts["missing"] += 1
            continue
        for f in FIELDS:
            a, b = py[f], other[f]
            if f == "segments":
                a, b = norm_segments(a), norm_segments(b)
            if a != b:
                counts[f] += 1
                ids_mismatched.add(sid)
                if len(examples[f]) < 30:
                    examples[f].append(
                        {
                            "id": sid,
                            "source": S[sid]["source"],
                            "path": S[sid]["path"],
                            "input": snippet(S[sid]["text"]),
                            "python": a
                            if f != "segments"
                            else snippet(json.dumps(a, ensure_ascii=False)),
                            lang: b
                            if f != "segments"
                            else snippet(json.dumps(b, ensure_ascii=False)),
                        }
                    )
    non_idem = [sid for sid, r in R.items() if not r.get("idempotent", True)]
    out[lang] = {
        "strings_compared": len(PY),
        "mismatch_counts": dict(counts),
        "strings_with_any_mismatch": len(ids_mismatched),
        "non_idempotent_ids": non_idem,
        "examples": examples,
    }
    print(
        lang,
        "mismatches:",
        dict(counts),
        "strings:",
        len(ids_mismatched),
        "non-idempotent:",
        len(non_idem),
    )

with open(os.path.join(HERE, "parity_results.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
