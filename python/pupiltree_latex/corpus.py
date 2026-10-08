"""Run the shared conformance corpus against this implementation.

    python -m pupiltree_latex.corpus [corpus_dir]

Every implementation ships an equivalent harness. A case has one of these
assertion shapes (spec §9):

- ``expected``: exact output (string, segment list, kind list or JSON value)
- ``contains`` / ``not_contains``: substrings of a string output
- ``kinds_include`` / ``kinds_exclude``: audit kinds that must / must not occur
- ``json_contains``: ``{"key": "substring"}`` on a parsed JSON object
- ``must_render``: `segment` yields a math segment (JS also runs KaTeX)
- ``property: "idempotent"``: ``f(f(x)) == f(x)``
- ``expected_error``: the parser must raise
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import (
    audit_kinds,
    canonicalize,
    fix,
    loads_latex_aware,
    loads_model_json,
    normalize,
    repair,
    segment,
    to_plain,
)

FUNCTIONS = (
    "repair",
    "normalize",
    "canonicalize",
    "fix",
    "segment",
    "to_plain",
    "audit",
    "json_transport",
)
STRING_FUNCTIONS = ("repair", "normalize", "canonicalize", "fix", "to_plain")


class ParseError(Exception):
    pass


def run(function: str, case: dict) -> Any:
    """The implementation's output for ``case`` (``ParseError`` on failure)."""
    inp = case["input"]
    if function == "repair":
        return repair(inp, guess_whitespace=case.get("variant") != "hard")
    if function == "normalize":
        return normalize(inp)
    options = case.get("opts") or {}
    if function == "canonicalize":
        return canonicalize(inp, **options)
    if function == "fix":
        return fix(inp, **options)
    if function == "segment":
        return [dict(s) for s in segment(inp)]
    if function == "to_plain":
        return to_plain(inp, case.get("style", "text"))
    if function == "audit":
        return audit_kinds(inp)
    if function == "json_transport":
        try:
            if "loads_model_json" in str(case.get("via", "")):
                return loads_model_json(inp)
            return loads_latex_aware(inp)
        except ValueError as exc:
            raise ParseError(str(exc)) from exc
    raise KeyError(function)


def check(function: str, case: dict) -> tuple[bool, Any]:
    """``(passed, got)`` for one case."""
    if case.get("expected_error"):
        try:
            got = run(function, case)
        except ParseError:
            return True, "<error>"
        return False, got
    if case.get("must_render"):
        got = run("segment", case)
        return any(s["kind"] == "math" for s in got), got
    if case.get("property") == "idempotent":
        once = run(function, case)
        twice = run(function, {**case, "input": once})
        return once == twice, (once, twice)
    try:
        got = run(function, case)
    except ParseError as exc:
        return False, f"<error: {exc}>"
    if "expected" in case and case["expected"] is not None:
        if got != case["expected"]:
            return False, got
        if function in STRING_FUNCTIONS and isinstance(got, str):
            again = run(function, {**case, "input": got})
            if again != got:
                return False, ("not idempotent", got, again)
        return True, got
    ok = True
    if "contains" in case:
        ok = ok and all(s in got for s in case["contains"])
    if "not_contains" in case:
        ok = ok and not any(s in got for s in case["not_contains"])
    if "kinds_include" in case:
        ok = ok and all(k in got for k in case["kinds_include"])
    if "kinds_exclude" in case:
        ok = ok and not any(k in got for k in case["kinds_exclude"])
    if "json_contains" in case:
        for key, needle in case["json_contains"].items():
            value = got.get(key) if isinstance(got, dict) else None
            ok = ok and isinstance(value, str) and needle in value
    predicate_keys = {
        "contains",
        "not_contains",
        "kinds_include",
        "kinds_exclude",
        "json_contains",
    }
    if not predicate_keys.intersection(case):
        return False, "<no assertion in case>"
    return ok, got


def unchanged(function: str, inp: str) -> tuple[bool, Any]:
    """``must_not_change``: True when ``function`` leaves ``inp`` alone."""
    if function == "segment":
        segs = segment(inp)
        return (
            len(segs) == 1 and segs[0]["kind"] == "text" and segs[0]["value"] == inp
        ), segs
    if function == "audit":
        kinds = audit_kinds(inp)
        return kinds == [], kinds
    got = run(function, {"input": inp})
    return got == inp, got


def load(corpus_dir: Path, function: str, impl: str = "python") -> list[dict]:
    path = corpus_dir / f"{function}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c for c in data["cases"] if impl in c.get("impl", ["python", "dart", "js"])]


def main(argv: list[str]) -> int:
    corpus_dir = (
        Path(argv[1])
        if len(argv) > 1
        else Path(__file__).resolve().parents[2] / "corpus"
    )
    failed = 0
    total = 0
    for function in FUNCTIONS:
        for case in load(corpus_dir, function):
            total += 1
            ok, got = check(function, case)
            if not ok:
                failed += 1
                print(
                    f"FAIL {function}/{case['id']}\n  input: {case['input']!r}\n  got:   {got!r}"
                )
    for case in load(corpus_dir, "must_not_change"):
        for fn in case["functions"]:
            total += 1
            ok, got = unchanged(fn, case["input"])
            if not ok:
                failed += 1
                print(
                    f"FAIL must_not_change/{case['id']} via {fn}\n  input: {case['input']!r}\n  got:   {got!r}"
                )
    print(f"{total - failed}/{total} corpus checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
