"""Python pass: fix / audit / over-reach / idempotency / to_plain / raw JSON.

Reads strings.json; writes python_results.json (per-string outputs used for
cross-language parity), math_segments.json (for KaTeX) and
python_findings.json (everything the report needs).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\Ankit\Desktop\pupiltree\pupiltree-latex\python")
from pupiltree_latex import audit_kinds, fix, loads_latex_aware, segment, to_plain  # noqa: E402

DEFECT_KINDS = [
    "control_char",
    "legacy_delimiter",
    "unbalanced_dollar",
    "mojibake",
    "bare_unicode_math",
    "bare_left_brace",
    "double_escaped_command",
    "unicode_chemistry",
]
URL_RE = re.compile(r"https?://\S+")
HEX24_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{24}(?![0-9a-fA-F])")
IMAGE_RE = re.compile(r"\{\{IMAGE:[^}]*\}\}")
SNAKE_RE = re.compile(r"[A-Za-z]+_[A-Za-z0-9_]+")
WORD_RE = re.compile(r"(?<![\\A-Za-z])[A-Za-z]{4,}(?![A-Za-z])")
RESIDUE = {
    "backslash_letter": re.compile(r"\\[A-Za-z]"),
    "dollar": re.compile(r"\$"),
    "brace": re.compile(r"[{}]"),
}
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

with open(os.path.join(HERE, "strings.json"), encoding="utf-8") as fh:
    STRINGS = json.load(fh)

results = []
before_kinds: Counter = Counter()
after_kinds: Counter = Counter()
strings_with_finding_before: Counter = Counter()
strings_with_finding_after: Counter = Counter()
after_examples: dict[str, list] = defaultdict(list)
overreach: dict[str, list] = defaultdict(list)
overreach_counts: Counter = Counter()
idem_violations: list = []
plain_residue: dict[str, list] = defaultdict(list)
plain_residue_counts: Counter = Counter()
math_segments: dict = {}
changed = 0


def math_spans_of(text: str) -> list:
    return [(s["value"], s["display"]) for s in segment(text) if s["kind"] == "math"]


def in_math_of(text: str, needle: str) -> bool:
    return any(needle in s["value"] for s in segment(text) if s["kind"] == "math")


def snippet(s: str, n: int = 240) -> str:
    return s if len(s) <= n else s[:n] + "…"


t0 = time.perf_counter()
for rec in STRINGS:
    sid, text = rec["id"], rec["text"]
    fixed = fix(text)
    if fixed != text:
        changed += 1
    kb = audit_kinds(text)
    ka = audit_kinds(fixed)
    before_kinds.update(kb)
    after_kinds.update(ka)
    for k in set(kb):
        strings_with_finding_before[k] += 1
    for k in set(ka):
        strings_with_finding_after[k] += 1
        if k in DEFECT_KINDS and len(after_examples[k]) < 20:
            after_examples[k].append(
                {
                    "id": sid,
                    "source": rec["source"],
                    "path": rec["path"],
                    "input": snippet(text, 400),
                    "output": snippet(fixed, 400),
                    "kinds_before": kb,
                    "kinds_after": ka,
                }
            )

    # Over-reach
    for name, rx in (("url", URL_RE), ("hex24", HEX24_RE), ("image_marker", IMAGE_RE)):
        for m in rx.findall(text):
            if m not in fixed:
                overreach_counts[name] += 1
                if len(overreach[name]) < 30:
                    overreach[name].append(
                        {
                            "id": sid,
                            "path": rec["path"],
                            "token": m,
                            "input": snippet(text),
                            "output": snippet(fixed),
                        }
                    )
    for m in set(SNAKE_RE.findall(text)):
        if m not in fixed:
            cat = "snake_in_math" if in_math_of(text, m) else "snake_in_prose"
            overreach_counts[cat] += 1
            if len(overreach[cat]) < 30:
                overreach[cat].append(
                    {
                        "id": sid,
                        "path": rec["path"],
                        "token": m,
                        "input": snippet(text),
                        "output": snippet(fixed),
                    }
                )
    wi = Counter(WORD_RE.findall(text))
    wo = Counter(WORD_RE.findall(fixed))
    lost = [w for w, c in wi.items() if wo[w] < c]
    if lost:
        overreach_counts["word"] += len(lost)
        if len(overreach["word"]) < 30:
            overreach["word"].append(
                {
                    "id": sid,
                    "path": rec["path"],
                    "lost": lost,
                    "input": snippet(text),
                    "output": snippet(fixed),
                }
            )

    # Idempotency
    fixed2 = fix(fixed)
    if fixed2 != fixed:
        idem_violations.append(
            {
                "id": sid,
                "path": rec["path"],
                "input": snippet(text, 400),
                "fix1": snippet(fixed, 400),
                "fix2": snippet(fixed2, 400),
            }
        )

    # Math segments (before and after) for KaTeX
    for which, src in (("before", text), ("after", fixed)):
        for tex, disp in math_spans_of(src):
            key = json.dumps([tex, disp], ensure_ascii=False)
            e = math_segments.setdefault(
                key,
                {
                    "tex": tex,
                    "display": disp,
                    "before": [],
                    "after": [],
                    "before_n": 0,
                    "after_n": 0,
                },
            )
            if len(e[which]) < 5:
                e[which].append(sid)
            e[which + "_n"] += 1

    # to_plain
    plains = {}
    for style in ("text", "pdf"):
        for which, src in (("orig", text), ("fixed", fixed)):
            p = to_plain(src, style)
            plains[f"{style}_{which}"] = p
            for rk, rx in RESIDUE.items():
                if rx.search(p):
                    plain_residue_counts[f"{style}/{which}/{rk}"] += 1
                    if which == "fixed" and len(plain_residue[f"{style}/{rk}"]) < 20:
                        plain_residue[f"{style}/{rk}"].append(
                            {
                                "id": sid,
                                "path": rec["path"],
                                "input": snippet(src, 300),
                                "plain": snippet(p, 300),
                            }
                        )

    results.append(
        {
            "id": sid,
            "fix": fixed,
            "audit_before": kb,
            "audit_after": ka,
            "segments": segment(fixed),
            "to_plain_text": plains["text_fixed"],
            "to_plain_pdf": plains["pdf_fixed"],
        }
    )
elapsed = time.perf_counter() - t0

# Raw model responses
with open(os.path.join(HERE, "raw_responses.json"), encoding="utf-8") as fh:
    RAWS = json.load(fh)
raw_ok, raw_fail, raw_ctrl = 0, [], []


def leaves(o, path=""):
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from leaves(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from leaves(v, f"{path}[{i}]")


FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
for r in RAWS:
    raw = r["raw"]
    body = raw
    m = FENCE_RE.search(raw)
    if m:
        body = m.group(1)
    try:
        parsed = loads_latex_aware(body)
        raw_ok += 1
        for p, leaf in leaves(parsed):
            if CTRL_RE.search(leaf):
                raw_ctrl.append(
                    {
                        "source": r["source"],
                        "path": r["path"] + p,
                        "leaf": snippet(leaf, 200).encode("unicode_escape").decode(),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        raw_fail.append(
            {
                "source": r["source"],
                "path": r["path"],
                "error": str(exc)[:200],
                "head": snippet(body, 200),
            }
        )

findings = {
    "n_strings": len(STRINGS),
    "n_changed_by_fix": changed,
    "elapsed_s": round(elapsed, 1),
    "audit_before_findings": dict(before_kinds),
    "audit_after_findings": dict(after_kinds),
    "audit_before_strings": dict(strings_with_finding_before),
    "audit_after_strings": dict(strings_with_finding_after),
    "after_examples": after_examples,
    "overreach_counts": dict(overreach_counts),
    "overreach": overreach,
    "idempotency_violations": idem_violations,
    "plain_residue_counts": dict(plain_residue_counts),
    "plain_residue": plain_residue,
    "raw": {
        "n": len(RAWS),
        "ok": raw_ok,
        "failures": raw_fail,
        "control_chars_in_leaves": raw_ctrl,
    },
    "math_segments_unique": len(math_segments),
}
with open(os.path.join(HERE, "python_findings.json"), "w", encoding="utf-8") as fh:
    json.dump(findings, fh, ensure_ascii=False, indent=1)
with open(os.path.join(HERE, "python_results.json"), "w", encoding="utf-8") as fh:
    json.dump(results, fh, ensure_ascii=False)
with open(os.path.join(HERE, "math_segments.json"), "w", encoding="utf-8") as fh:
    json.dump(list(math_segments.values()), fh, ensure_ascii=False)

brief = {
    k: v
    for k, v in findings.items()
    if k
    not in (
        "after_examples",
        "overreach",
        "plain_residue",
        "idempotency_violations",
        "raw",
    )
}
print(json.dumps(brief, indent=1, ensure_ascii=False))
print("idempotency violations:", len(idem_violations))
print(
    "raw:",
    findings["raw"]["n"],
    "ok",
    raw_ok,
    "fail",
    len(raw_fail),
    "ctrl leaves",
    len(raw_ctrl),
)
