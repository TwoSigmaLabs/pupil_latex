"""Timing: wall-clock for fix over all strings.json, plus the 10 slowest strings."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\Ankit\Desktop\pupiltree\pupiltree-latex\python")
from pupiltree_latex import fix
S = json.load(open(os.path.join(HERE, "strings.json"), encoding="utf-8"))
for r in S: fix(r["text"])  # warm-up (regex compilation, ftfy tables)
t0 = time.perf_counter(); per = []
for r in S:
    a = time.perf_counter(); fix(r["text"]); per.append((time.perf_counter() - a, r))
total = time.perf_counter() - t0
per.sort(key=lambda x: -x[0])
out = {"n": len(S), "total_s": round(total, 3), "mean_ms": round(1000 * total / len(S), 4),
       "total_chars": sum(len(r["text"]) for r in S),
       "slowest": [{"id": r["id"], "ms": round(1000 * t, 2), "len": len(r["text"]), "source": r["source"], "path": r["path"][-70:]} for t, r in per[:10]]}
json.dump(out, open(os.path.join(HERE, "timing_results.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps(out, indent=1))
