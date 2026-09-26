"""Bounded KaTeX triage: 1500 fuzz inputs, group every failing math segment of
fix(x) by KaTeX error class, blame fix only when the input's own segments
rendered. No minimisation; prints the shortest reproducer per class."""

import os, random, re, sys, time
from collections import defaultdict

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python")
)
from pupiltree_latex import fix, segment, to_plain, loads_latex_aware  # noqa: E402
import fuzz  # noqa: E402

K = fuzz.KATEX
rng = random.Random(99)
groups = defaultdict(list)
plain = defaultdict(list)
jsonraw = defaultdict(list)
t0 = time.time()
for i in range(1500):
    atoms, seps, kinds, keep = fuzz.gen_input(rng, i + 1)
    text = fuzz.join(atoms[:8], seps[:7])
    out = fix(text)
    before_ok = all(
        K.render(s["value"], s["display"])[0]
        for s in segment(text)
        if s["kind"] == "math"
    )
    for s in segment(out):
        if s["kind"] != "math":
            continue
        ok, err = K.render(s["value"], s["display"])
        if ok:
            continue
        m = re.search(r"Undefined control sequence: (\\[A-Za-z]+)", err)
        if m:
            cls = "undefined " + m.group(1)
        else:
            cls = re.sub(
                r" at position.*| at end of input.*",
                "",
                err.replace("KaTeX parse error: ", ""),
            )[:60]
        groups[(cls, before_ok)].append((text, s["value"], err))
    r = fuzz.check_to_plain(text)
    if r:
        plain[tuple(r)].append((text, out, to_plain(out)))
    r = fuzz.check_json_raw(text)
    if r:
        jsonraw[str(r)[:40] if isinstance(r, str) else r[0]].append((text, r))
    if time.time() - t0 > 150:
        print("deadline at", i)
        break

print("\n== KaTeX failures of fix(x) segments (class, input-rendered-before) ==")
for (cls, before_ok), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    items.sort(key=lambda t: len(t[1]))
    text, seg, err = items[0]
    print(
        f"[{len(items):4d}] blamed_on_fix={before_ok}  {cls}\n        in={text!r}\n        seg={seg!r}"
    )
print("\n== to_plain residue ==")
for k, items in sorted(plain.items(), key=lambda kv: -len(kv[1])):
    items.sort(key=lambda t: len(t[0]))
    print(
        f"[{len(items):4d}] {k}  in={items[0][0]!r}  fix={items[0][1]!r}  plain={items[0][2]!r}"
    )
print("\n== json raw ==")
for k, items in sorted(jsonraw.items(), key=lambda kv: -len(kv[1])):
    items.sort(key=lambda t: len(t[0]))
    print(f"[{len(items):4d}] {k}  in={items[0][0]!r}  -> {items[0][1]!r}")
