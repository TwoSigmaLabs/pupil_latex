"""Extract every renderable string leaf from the LOCAL content sources.

Writes strings.json (unique content strings with provenance) and
raw_responses.json (raw model responses for loads_latex_aware).
Skips CONTRACT §5 non-content keys, URL/path strings and PII-shaped keys.
No network, no database.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter, OrderedDict

OUT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(OUT, "..", ".."))
# The workspace that holds the sibling app checkouts and the local exports
# (mongo-backups/, Backend/, pupiltree-agents/, ...): $PUPILTREE_WORKSPACE, or
# the directory this repository is checked out in.
ROOT = os.environ.get("PUPILTREE_WORKSPACE") or os.path.dirname(REPO)
sys.path.insert(0, os.path.join(REPO, "python"))
from pupiltree_latex.walk import is_non_content_key, is_url_or_path_string, is_not_rendered_key  # noqa: E402

PII_KEY_RE = re.compile(r"(name|email|phone|mobile|teacher|student|school|login|password)", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

SOURCES = OrderedDict()
SOURCES["mongo-backups"] = sorted(glob.glob(os.path.join(ROOT, "mongo-backups", "*.json")))
SOURCES["agents/before_ahs.json"] = [os.path.join(ROOT, "pupiltree-agents", "scripts", "latex_test_output", "before_ahs.json")]
SOURCES["Backend/tests"] = sorted(
    glob.glob(os.path.join(ROOT, "Backend", "tests", "fixtures", "**", "*.json"), recursive=True)
    + glob.glob(os.path.join(ROOT, "Backend", "tests", "pdf_v2_output", "*.json"))
    + glob.glob(os.path.join(ROOT, "Backend", "tests", "results", "*.json"))
)
SOURCES["pupiltree-agents/tests"] = sorted(glob.glob(os.path.join(ROOT, "pupiltree-agents", "tests", "**", "*.json"), recursive=True))
SOURCES["script_editor/test"] = sorted(glob.glob(os.path.join(ROOT, "script_editor", "test", "**", "*.json"), recursive=True))
SOURCES["tutor-frontend/test"] = sorted(glob.glob(os.path.join(ROOT, "pupiltree.ai_tutor-frontend", "test", "**", "*.json"), recursive=True))
SOURCES["corpus/harvested (inputs)"] = sorted(glob.glob(os.path.join(REPO, "corpus", "harvested", "*.json")))

strings: "OrderedDict[str, dict]" = OrderedDict()
raws: list[dict] = []
leaf_counts: Counter = Counter()
unique_counts: Counter = Counter()
skipped_counts: Counter = Counter()
file_counts: Counter = Counter()


def add(text: str, source: str, path: str) -> None:
    if not isinstance(text, str) or not text.strip():
        return
    if is_url_or_path_string(text):
        skipped_counts[source + ":url_or_path_value"] += 1
        return
    if EMAIL_RE.search(text) and len(text) < 80:
        skipped_counts[source + ":email_value"] += 1
        return
    leaf_counts[source] += 1
    if text in strings:
        strings[text]["dupes"] += 1
        return
    strings[text] = {"source": source, "path": path, "text": text, "dupes": 0}
    unique_counts[source] += 1


def walk(obj, source: str, path: str, key_hint: str = "") -> None:
    if isinstance(obj, str):
        add(obj, source, path)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k)
            if is_not_rendered_key(ks) or ks.lower() in {"raw_text", "raw_model_text", "model_raw"} or ks.lower().endswith("_raw_response"):
                if isinstance(v, str) and v.strip():
                    raws.append({"source": source, "path": f"{path}.{ks}", "raw": v})
                continue
            if is_non_content_key(ks):
                skipped_counts[source + ":non_content_key"] += 1
                continue
            if PII_KEY_RE.search(ks) and not ks.lower().endswith(("question", "questions", "content", "text", "answer", "explanation", "script", "plan", "title", "outcomes")):
                skipped_counts[source + ":pii_key"] += 1
                continue
            walk(v, source, f"{path}.{ks}", ks)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, source, f"{path}[{i}]", key_hint)


for source, files in SOURCES.items():
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            print("SKIP", f, exc)
            continue
        file_counts[source] += 1
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if source.startswith("corpus/harvested"):
            cases = data.get("cases", data) if isinstance(data, dict) else data
            for i, c in enumerate(cases):
                inp = c.get("input")
                if isinstance(inp, str):
                    add(inp, source, f"{rel}#{c.get('id', i)}")
                elif isinstance(inp, (dict, list)):
                    walk(inp, source, f"{rel}#{c.get('id', i)}")
            continue
        walk(data, source, rel)

# Fenced-JSON strings anywhere are raw model responses too.
FENCE_RE = re.compile(r"```(?:json)?\s*[\[{]", re.I)
for text, rec in strings.items():
    if FENCE_RE.search(text):
        raws.append({"source": rec["source"], "path": rec["path"], "raw": text, "via": "fenced"})

out = []
for i, (text, rec) in enumerate(strings.items()):
    out.append({"id": i, "source": rec["source"], "path": rec["path"], "dupes": rec["dupes"], "text": text})

with open(os.path.join(OUT, "strings.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=0)
with open(os.path.join(OUT, "raw_responses.json"), "w", encoding="utf-8") as fh:
    json.dump(raws, fh, ensure_ascii=False, indent=0)

summary = {
    "files_per_source": dict(file_counts),
    "string_leaves_per_source": dict(leaf_counts),
    "unique_strings_first_seen_per_source": dict(unique_counts),
    "unique_total": len(out),
    "raw_responses": len(raws),
    "skipped": dict(skipped_counts),
    "chars_total": sum(len(s["text"]) for s in out),
}
with open(os.path.join(OUT, "sources_summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)
print(json.dumps(summary, indent=2))
