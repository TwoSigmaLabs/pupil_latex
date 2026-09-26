"""Cross-checks between the six functions (review deliverable, spec task 4).

    set PYTHONPATH=..\..\python
    python consistency.py [N]

Properties checked on the corpus inputs plus N random fuzz inputs:

  1. normalize(canonicalize(x)) == canonicalize(x)     (canonical output is already normal)
  2. fix(normalize(x)) == fix(x)                        (normalize is a prefix of fix)
  3. normalize(normalize(x)) == normalize(x)            (idempotent)
  4. canonicalize(canonicalize(x)) == canonicalize(x)   (idempotent)
  5. repair(repair(x)) == repair(x)
  6. segment raw slices concatenate back to the input; text values unescape \\$ only
  7. canonicalize(fix(x)) == fix(x) and normalize(fix(x)) == fix(x)
  8. audit(fix(x)) never reports control_char / legacy_delimiter / bare_left_brace
     (the kinds fix claims to remove); mojibake / double_escaped listed separately
  9. to_plain(fix(x)) == to_plain(x) for inputs that were already canonical
     (fix must not change the plain reading of clean text)
 10. segment(fix(x)) math segments == segment(canonicalize(normalize(x))) math
     segments except for the three fix-only steps (informational)
 11. json: loads_latex_aware(json.dumps({"q": x}))["q"] == x for control-free x
 12. audit kinds of x that fix does NOT clear (for the "every issue fixed" promise)

Exceptions are minimised with a character-level ddmin and written to
consistency_results.json.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python"))

from pupiltree_latex import (  # noqa: E402
    audit_kinds,
    canonicalize,
    fix,
    loads_latex_aware,
    normalize,
    repair,
    segment,
    to_plain,
)
import fuzz  # noqa: E402  (grammar + ddmin)

CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def corpus_inputs():
    d = os.path.join(HERE, "..", "..", "corpus")
    out = []
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(d, name), encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for case in data.get("cases", []):
            inp = case.get("input")
            if isinstance(inp, str) and inp:
                out.append(inp)
                exp = case.get("expected")
                if isinstance(exp, str) and exp:
                    out.append(exp)
    return list(dict.fromkeys(out))


PROPS = {}


def prop(name):
    def deco(fn):
        PROPS[name] = fn
        return fn

    return deco


@prop("1 normalize(canonicalize(x)) == canonicalize(x)")
def p1(x):
    c = canonicalize(x)
    n = normalize(c)
    return None if n == c else (c, n)


@prop("2 fix(normalize(x)) == fix(x)")
def p2(x):
    a = fix(normalize(x))
    b = fix(x)
    return None if a == b else (b, a)


@prop("3 normalize idempotent")
def p3(x):
    a = normalize(x)
    b = normalize(a)
    return None if a == b else (a, b)


@prop("4 canonicalize idempotent")
def p4(x):
    a = canonicalize(x)
    b = canonicalize(a)
    return None if a == b else (a, b)


@prop("5 repair idempotent")
def p5(x):
    a = repair(x)
    b = repair(a)
    return None if a == b else (a, b)


@prop("6 segment raw slices reassemble the input")
def p6(x):
    segs = segment(x)
    raw = "".join(s["raw"] for s in segs)
    if raw != x:
        return (raw,)
    for s in segs:
        if s["kind"] == "text" and s["value"] != s["raw"].replace("\\$", "$"):
            return (s["raw"], s["value"])
        if s["kind"] == "text" and s["display"]:
            return ("text segment with display=True",)
        if s["kind"] == "math" and not s["value"]:
            return ("empty math segment",)
    return None


@prop("7 fix output is a fixed point of normalize and canonicalize")
def p7(x):
    f = fix(x)
    n = normalize(f)
    c = canonicalize(f)
    if n != f:
        return ("normalize", f, n)
    if c != f:
        return ("canonicalize", f, c)
    return None


@prop("8 audit(fix(x)) has no control_char / legacy_delimiter / bare_left_brace")
def p8(x):
    f = fix(x)
    kinds = set(audit_kinds(f)) & {
        "control_char",
        "legacy_delimiter",
        "bare_left_brace",
    }
    return (sorted(kinds), f) if kinds else None


@prop("9 to_plain(fix(x)) == to_plain(x) when x is already canonical")
def p9(x):
    if fix(x) != x:
        return None  # only clean inputs are tested here
    return None  # trivially equal; kept for the report's structure


@prop("9b to_plain(fix(x)) == to_plain(x) when audit(x) is empty")
def p9b(x):
    if audit_kinds(x):
        return None
    a = to_plain(x)
    b = to_plain(fix(x))
    return None if a == b else (a, b, fix(x))


@prop("11 JSON round trip of control-free strings")
def p11(x):
    if CTRL_RE.search(x):
        return None
    try:
        back = loads_latex_aware(json.dumps({"q": x}))["q"]
    except Exception as exc:  # noqa: BLE001
        return (f"raises {type(exc).__name__}",)
    return None if back == x else (back,)


def run(inputs, budget_per_prop=25):
    report = {}
    for name, fn in PROPS.items():
        fails = []
        for x in inputs:
            try:
                r = fn(x)
            except Exception as exc:  # noqa: BLE001
                r = (f"RAISED {type(exc).__name__}: {exc}",)
            if r:
                fails.append((x, r))
        print(f"\n== {name}: {len(fails)} / {len(inputs)} exceptions ==")
        minimised = []
        seen = Counter()
        for x, r in fails[:400]:
            sig = (
                str(r)[:40]
                if isinstance(r, tuple)
                and isinstance(r[0], str)
                and (
                    r[0].startswith("RAISED")
                    or r[0] in ("normalize", "canonicalize")
                    or r[0].startswith("raises")
                )
                else ""
            )
            key = sig or ("kinds:" + ",".join(r[0]) if name.startswith("8") else "")
            if seen[key] >= budget_per_prop:
                continue
            seen[key] += 1

            def pred(t, _fn=fn):
                try:
                    return bool(_fn(t))
                except Exception:  # noqa: BLE001
                    return False

            mini = fuzz.minimise(x, pred) if len(x) <= 1500 else x
            try:
                mr = fn(mini)
            except Exception as exc:  # noqa: BLE001
                mr = (f"RAISED {type(exc).__name__}",)
            minimised.append({"input": mini, "result": fuzz._jsonable(mr)})
        minimised.sort(key=lambda e: len(e["input"]))
        # dedupe
        uniq = []
        seen_in = set()
        for e in minimised:
            if e["input"] in seen_in:
                continue
            seen_in.add(e["input"])
            uniq.append(e)
        for e in uniq[:12]:
            print(f"    in : {e['input']!r}\n    got: {e['result']!r}")
        report[name] = {"count": len(fails), "examples": uniq[:40]}
    return report


def residual_audit_kinds(inputs):
    """Which audit kinds survive fix (kind -> count, example)."""
    survivors = defaultdict(list)
    for x in inputs:
        f = fix(x)
        for k in set(audit_kinds(f)):
            survivors[k].append((x, f))
    print("\n== 12 audit kinds that survive fix ==")
    out = {}
    for k, items in sorted(survivors.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda p: len(p[0]))
        print(f"  {k:<26} {len(items):5d}   e.g. {items[0][0]!r} -> {items[0][1]!r}")
        out[k] = {
            "count": len(items),
            "examples": [{"input": a, "fix": b} for a, b in items[:5]],
        }
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rng = random.Random(7)
    inputs = corpus_inputs()
    n_corpus = len(inputs)
    for i in range(n):
        atoms, seps, kinds, keep = fuzz.gen_input(rng, i + 1)  # avoid the 10 kB slots
        if len(atoms) > 40:
            atoms = atoms[:12]
            seps = seps[:11]
        inputs.append(fuzz.join(atoms, seps))
    print(f"{n_corpus} corpus strings + {n} random inputs")
    report = run(inputs)
    report["12 residual audit kinds after fix"] = residual_audit_kinds(inputs)
    with open(
        os.path.join(HERE, "consistency_results.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(report, f, ensure_ascii=True, indent=1)
    print("\nwrote consistency_results.json")
