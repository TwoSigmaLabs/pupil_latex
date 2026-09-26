"""Reproducers for the previous run's D0-D11 defects plus new candidates found in the re-run.

Run:  PYTHONIOENCODING=utf-8 python defects_check.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\Ankit\Desktop\pupiltree\pupiltree-latex\python")
from pupiltree_latex import audit_kinds, fix, to_plain  # noqa: E402

S = {
    s["id"]: s
    for s in json.load(open(os.path.join(HERE, "strings.json"), encoding="utf-8"))
}
BS = "\\"
LF = "\n"
cases = [
    (
        "D0 label lines",
        BS
        + "heading: Intro: [5 Minutes]"
        + LF
        + BS
        + "teacher: Good morning, class!"
        + LF
        + BS
        + "type: teacher"
        + LF
        + BS
        + "tool: board"
        + LF
        + BS
        + "read: Key Concepts:"
        + LF
        + BS
        + "thinkingroutine: See-Think-Wonder",
        "unchanged",
    ),
    (
        "D1 log_{10} in math",
        "Use $" + BS + "log_{10} x$ and $" + BS + "bigcup_{i} A_i$ here",
        "unchanged",
    ),
    ("D1 log_{10} bare", "compute " + BS + "log_{10} x now", None),
    ("D2 $sqrt$2", "Root: $" + BS + "sqrt$2", "unchanged"),
    ("D2 escaped-dollar x^2$", "  " + BS + "$x^2$ ", "unchanged"),
    ("D3 prose ellipsis", "prose … prose", "unchanged"),
    ("D3 thinking routine", "I Used to Think… Now I Think", "unchanged"),
    ("D4 no_capture", "no_capture", "unchanged"),
    ("D4 ai_recreate", "ai_recreate", "unchanged"),
    ("D4 lo_0", "lo_0", None),
    ("D5 grade_level value", "6_A", "unchanged"),
    (
        "D6 cp1252 psi",
        "wavefunction Ïˆ(x) collapses",
        "wavefunction $" + BS + "psi$(x) collapses",
    ),
    ("D6 cp1252 psi in math", "$|Ïˆ|^2$", "$|" + BS + "psi|^2$"),
    (
        "D7 broken span merge",
        "$" + BS + "frac{1}{2$ and $x$ and $" + BS + "left( y$",
        None,
    ),
    ("D8 &amp;", "Tom &amp; Jerry &lt; 5", "Tom & Jerry < 5"),
    ("D9 CRLF", "line one\r\nline two\rline three", "unchanged"),
    ("D10 1{,}000 to_plain", "$1{,}000$", "PLAIN:1,000"),
    ("D11 $<LF>ightarrow$", "2H₂ + O₂ $" + LF + "ightarrow$ 2H₂O", None),
    ("D11 audit sees it", "A $" + LF + "ightarrow$ B", "AUDIT"),
    # new candidates from this run
    (
        "R1 literal \\n before Word:",
        "Host: Priya" + BS + "nGuest: Vikram" + BS + "nHost: Hi",
        None,
    ),
    ("R1b literal \\n before lowercase", "Host: Priya" + BS + "nguest is here", None),
    ("R1c literal \\n in prose (no colon)", "line one" + BS + "nline two", None),
    ("R2 escaped $1.56 text{ meters}$", BS + "$1.56 " + BS + "text{ meters}$", None),
    ("R3 orphan $ldots", "$" + BS + "ldots", None),
    ("R4 Compute $2x + 3 $.", "Compute $2x + 3 $.", None),
    ("R5 unit superscript", "240 cm³ and (a³) and 6a²", None),
    ("R6 √x²", "√x²", None),
    (
        "R7 nested broken",
        "$" + BS + "text{VS} = $" + BS + "frac{" + BS + "text{CS}$}{R}$",
        None,
    ),
]
for name, inp, exp in cases:
    out = fix(inp)
    if exp == "PLAIN:1,000":
        p = to_plain(out, "text")
        ok = p == "1,000"
        print(f"{'PASS' if ok else 'FAIL'} {name}: to_plain={p!r}")
    elif exp == "AUDIT":
        k = audit_kinds(inp)
        ok = "control_char" in k
        print(f"{'PASS' if ok else 'FAIL'} {name}: audit={k} fix={out!r}")
    elif exp == "unchanged":
        ok = out == inp
        print(f"{'PASS' if ok else 'FAIL'} {name}: {inp!r} -> {out!r}")
    elif exp is None:
        idem = fix(out) == out
        print(
            f"INFO {name}: {inp!r} -> {out!r} idempotent={idem} audit_after={audit_kinds(out)}"
        )
    else:
        ok = out == exp
        print(f"{'PASS' if ok else 'FAIL'} {name}: {inp!r} -> {out!r}")

# Real mongo dumps: every `\label:` at a line start must survive verbatim.
LBL = re.compile(r"(?m)^\\[a-z_]+:")
bad = 0
total = 0
labels_seen = set()
for sid, s in S.items():
    if s["source"] != "mongo-backups":
        continue
    labels = LBL.findall(s["text"])
    if not labels:
        continue
    total += 1
    labels_seen.update(labels)
    if LBL.findall(fix(s["text"])) != labels:
        bad += 1
        print("LABEL DAMAGE", sid, s["path"][-60:])
print(
    f"mongo dump strings with label lines: {total}, damaged by fix: {bad}, labels: {sorted(labels_seen)}"
)
