"""Derive every number the report needs from the result files.

Reads strings.json, python_results.json, python_findings.json,
katex_results.json, parity_results.json, raw_responses.json,
sources_summary.json; writes summary.json, real_data_changes.json and
overreach_identifiers_wrapped.json.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python"))
from pupiltree_latex import loads_latex_aware, segment  # noqa: E402


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


S = {s["id"]: s for s in load("strings.json")}
R = {r["id"]: r for r in load("python_results.json")}
F = load("python_findings.json")
K = load("katex_results.json")
P = load("parity_results.json")
RAWS = load("raw_responses.json")
SRC = load("sources_summary.json")


def is_real(sid):
    return not S[sid]["source"].startswith("corpus")


def snip(s, n=220):
    return s if len(s) <= n else s[:n] + "…"


# ---- per-source basics -------------------------------------------------
per_source = defaultdict(lambda: Counter())
for sid, r in R.items():
    src = S[sid]["source"]
    per_source[src]["strings"] += 1
    if r["fix"] != S[sid]["text"]:
        per_source[src]["changed_by_fix"] += 1
    per_source[src]["math_segments_before"] += sum(
        1 for s in segment(S[sid]["text"]) if s["kind"] == "math"
    )
    per_source[src]["math_segments_after"] += sum(
        1 for s in r["segments"] if s["kind"] == "math"
    )
    for k in set(r["audit_before"]):
        per_source[src]["before:" + k] += 1
    for k in set(r["audit_after"]):
        per_source[src]["after:" + k] += 1

# ---- real-data changes, classified ------------------------------------
CTRL = {"\t": "TAB", "\n": "LF", "\r": "CR"}
LABEL_RE = re.compile(r"^[a-z]+:")
changes = []
change_kinds = Counter()
label_corruptions = Counter()
for sid, r in R.items():
    if not is_real(sid):
        continue
    a, b = S[sid]["text"], r["fix"]
    if a == b:
        continue
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    kinds = Counter()
    ops = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old, new = a[i1:i2], b[j1:j2]
        after = a[i2 : i2 + 20]
        if (
            old in ("\\t", "\\n", "\\r", "\\r\\n", "\\n\\n")
            and new
            and all(c in CTRL for c in new)
        ):
            m = LABEL_RE.match(after)
            if m or re.match(r"^[a-z]{2,}", after):
                word = old[-1] + re.match(r"^[a-z]*", after).group(0)
                kind = "script_label_corrupted"
                label_corruptions["\\" + word] += 1
            else:
                kind = "json_escape_decoded"
        elif "\x1b" in old:
            kind = "ansi_escape_stripped"
        elif old and all(ord(c) < 0x20 or ord(c) == 0x7F for c in old) and not new:
            kind = "control_char_dropped"
        elif old == "\xa0":
            kind = "nbsp_removed"
        elif old in ("−", "‐", "‒", "µ", "∆"):
            kind = "homoglyph"
        elif old == "amp;":
            kind = "html_unescaped"
        elif old == "\t" and new == "\\t":
            kind = "tab_restored_to_text_command"
        elif "…" in old and "ldots" in new:
            kind = "ellipsis_wrapped_as_ldots"
        elif "\\text{" in new:
            kind = "unicode_chemistry_wrapped"
        elif "$" in new and not old:
            kind = "wrapped_in_math"
        elif "$" in new and old and old not in "$":
            kind = "unicode_math_to_latex"
        else:
            kind = "other"
        kinds[kind] += 1
        if len(ops) < 6:
            ops.append(
                {
                    "kind": kind,
                    "before": a[max(0, i1 - 30) : i1] + "<<" + old + ">>" + after,
                    "after": b[max(0, j1 - 30) : j1]
                    + "<<"
                    + new
                    + ">>"
                    + b[j2 : j2 + 20],
                }
            )
    change_kinds.update(kinds.keys())
    changes.append(
        {
            "id": sid,
            "source": S[sid]["source"],
            "path": S[sid]["path"],
            "kinds": dict(kinds),
            "ops": ops,
        }
    )
with open(os.path.join(HERE, "real_data_changes.json"), "w", encoding="utf-8") as fh:
    json.dump(changes, fh, ensure_ascii=False, indent=1)

# ---- identifiers moved from prose into math ----------------------------
SNAKE = re.compile(r"(?<![A-Za-z0-9_\\])[A-Za-z]+_[A-Za-z0-9_]+")
moved = []
for sid, r in R.items():
    prose_ids = set()
    for seg in segment(S[sid]["text"]):
        if seg["kind"] == "text":
            prose_ids.update(SNAKE.findall(seg["value"]))
    if not prose_ids:
        continue
    math_after = " ".join(s["value"] for s in r["segments"] if s["kind"] == "math")
    hit = [t for t in prose_ids if t in math_after]
    if hit:
        moved.append(
            {
                "id": sid,
                "real": is_real(sid),
                "source": S[sid]["source"],
                "path": S[sid]["path"],
                "tokens": hit,
                "input": snip(S[sid]["text"]),
                "output": snip(r["fix"]),
            }
        )
with open(
    os.path.join(HERE, "overreach_identifiers_wrapped.json"), "w", encoding="utf-8"
) as fh:
    json.dump(moved, fh, ensure_ascii=False, indent=1)

# ---- to_plain residue, classified --------------------------------------
UNESC_DOLLAR = re.compile(r"(?<!\\)\$")
residue = {"text": Counter(), "pdf": Counter()}
residue_other = {"text": [], "pdf": []}
for sid, r in R.items():
    src_text = r["fix"]
    for style in ("text", "pdf"):
        p = r["to_plain_" + style]
        if "$" in p:
            if "\\$" in src_text:
                cls = "dollar:currency_by_design"
            elif len(UNESC_DOLLAR.findall(src_text)) % 2 == 1:
                cls = "dollar:unbalanced_input"
            else:
                cls = "dollar:other"
            residue[style][cls] += 1
            if cls == "dollar:other" and len(residue_other[style]) < 20:
                residue_other[style].append(
                    {
                        "id": sid,
                        "path": S[sid]["path"],
                        "input": snip(src_text),
                        "plain": snip(p),
                    }
                )
        if "{" in p or "}" in p:
            if re.search(r"\\[lr]brace|\\left\\\{|\\right\\\}|\\\{|\\\}", src_text):
                cls = "brace:literal_brace_by_design"
            elif src_text.lstrip()[:1] in "{[" or '{"' in src_text:
                cls = "brace:json_or_code_text"
            else:
                cls = "brace:other"
            residue[style][cls] += 1
            if cls == "brace:other" and len(residue_other[style]) < 40:
                residue_other[style].append(
                    {
                        "id": sid,
                        "path": S[sid]["path"],
                        "input": snip(src_text),
                        "plain": snip(p),
                    }
                )
        if re.search(r"\\[A-Za-z]", p):
            residue[style]["backslash_letter"] += 1
            if len(residue_other[style]) < 60:
                residue_other[style].append(
                    {
                        "id": sid,
                        "path": S[sid]["path"],
                        "input": snip(src_text),
                        "plain": snip(p),
                        "cls": "backslash",
                    }
                )

# ---- KaTeX ---------------------------------------------------------------
kfail = K["failures"]
katex = {
    "katex_version": K["katex_version"],
    "unique_segments": K["unique_segments"],
    "segments_before": K["segments_before"],
    "segments_after": K["segments_after"],
    "failing_unique": K["failing_unique"],
    "failing_before": K["failing_before"],
    "failing_after": K["failing_after"],
    "real_data_failing_unique": sum(
        1 for f in kfail if any(is_real(i) for i in f["before_ids"] + f["after_ids"])
    ),
    "only_after": [
        {k: f[k] for k in ("tex", "display", "message", "after_ids")}
        | {"inputs": [snip(S[i]["text"], 120) for i in f["after_ids"]]}
        for f in kfail
        if not f["before_n"]
    ],
    "only_before": [
        {k: f[k] for k in ("tex", "display", "message", "before_ids")}
        for f in kfail
        if not f["after_n"]
    ],
    "message_histogram": Counter(
        f["message"].split(" at position")[0].split(": ", 1)[-1][:70] for f in kfail
    ).most_common(30),
    "real_segments_before": sum(
        c["math_segments_before"]
        for s, c in per_source.items()
        if not s.startswith("corpus")
    ),
    "real_segments_after": sum(
        c["math_segments_after"]
        for s, c in per_source.items()
        if not s.startswith("corpus")
    ),
}

# ---- raw model responses -------------------------------------------------
raw_summary = {
    "candidates": len(RAWS),
    "by_shape": Counter(),
    "parsed_ok": 0,
    "parse_failed": [],
    "control_chars_in_leaves": 0,
}
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def leaves(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)


for r in RAWS:
    body = r["raw"]
    m = FENCE.search(body)
    if m:
        body = m.group(1)
    shape = (
        "fenced_json"
        if m
        else ("json_shaped" if body.strip()[:1] in "{[" else "not_json_answer_string")
    )
    raw_summary["by_shape"][shape] += 1
    if shape == "not_json_answer_string":
        continue
    try:
        parsed = loads_latex_aware(body)
        raw_summary["parsed_ok"] += 1
        raw_summary["control_chars_in_leaves"] += sum(
            1 for leaf in leaves(parsed) if CTRL_RE.search(leaf)
        )
    except Exception as exc:  # noqa: BLE001
        raw_summary["parse_failed"].append({"path": r["path"], "error": str(exc)[:160]})

summary = {
    "sources": SRC,
    "per_source": {k: dict(v) for k, v in per_source.items()},
    "n_strings": F["n_strings"],
    "n_changed_by_fix": F["n_changed_by_fix"],
    "audit_before_strings": F["audit_before_strings"],
    "audit_after_strings": F["audit_after_strings"],
    "audit_before_findings": F["audit_before_findings"],
    "audit_after_findings": F["audit_after_findings"],
    "real_data_changes": {
        "strings": len(changes),
        "kinds": dict(change_kinds),
        "label_corruptions": dict(label_corruptions),
    },
    "overreach_regex_counts": F["overreach_counts"],
    "identifiers_moved_into_math": {
        "total": len(moved),
        "real": sum(1 for m in moved if m["real"]),
        "real_examples": [m for m in moved if m["real"]],
    },
    "idempotency_violations": F["idempotency_violations"],
    "to_plain_residue": {k: dict(v) for k, v in residue.items()},
    "to_plain_residue_other_examples": residue_other,
    "katex": katex,
    "raw": raw_summary | {"by_shape": dict(raw_summary["by_shape"])},
    "parity": {
        lang: {
            k: d[k]
            for k in (
                "strings_compared",
                "mismatch_counts",
                "strings_with_any_mismatch",
                "non_idempotent_ids",
            )
        }
        for lang, d in P.items()
    },
}
with open(os.path.join(HERE, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=1)
print(
    json.dumps(
        {
            k: summary[k]
            for k in (
                "real_data_changes",
                "identifiers_moved_into_math",
                "to_plain_residue",
                "raw",
                "parity",
            )
        },
        ensure_ascii=False,
        indent=1,
        default=str,
    )[:6000]
)
print(
    "katex:",
    {
        k: v
        for k, v in katex.items()
        if k not in ("only_after", "only_before", "message_histogram")
    },
)
print("only_after:", json.dumps(katex["only_after"], ensure_ascii=False)[:1500])
print("idempotency:", len(F["idempotency_violations"]))
