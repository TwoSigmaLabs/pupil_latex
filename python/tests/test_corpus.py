"""Run the shared conformance corpus (``corpus/*.json``) against the Python
implementation through `pupiltree_latex.corpus`. Every implementation
ships an equivalent harness; a case that fails here fails the library, not
the app that hit it."""

from __future__ import annotations

from pathlib import Path

import pytest

from pupiltree_latex import corpus

CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"


def _cases(name: str):
    return [pytest.param(c, id=c["id"]) for c in corpus.load(CORPUS_DIR, name)]


def _check(function: str, case: dict) -> None:
    ok, got = corpus.check(function, case)
    assert ok, (
        f"{case['id']} ({case.get('source', 'curated')}) tags={case.get('tags')}\n"
        f"  input:    {case['input']!r}\n"
        f"  expected: {case.get('expected')!r} "
        f"{ {k: v for k, v in case.items() if k in ('contains', 'not_contains', 'kinds_include', 'kinds_exclude', 'json_contains', 'must_render', 'property', 'expected_error')} }\n"
        f"  got:      {got!r}"
    )


@pytest.mark.parametrize("case", _cases("repair"))
def test_repair(case):
    _check("repair", case)


@pytest.mark.parametrize("case", _cases("normalize"))
def test_normalize(case):
    _check("normalize", case)


@pytest.mark.parametrize("case", _cases("canonicalize"))
def test_canonicalize(case):
    _check("canonicalize", case)


@pytest.mark.parametrize("case", _cases("fix"))
def test_fix(case):
    _check("fix", case)


@pytest.mark.parametrize("case", _cases("segment"))
def test_segment(case):
    _check("segment", case)


@pytest.mark.parametrize("case", _cases("to_plain"))
def test_to_plain(case):
    _check("to_plain", case)


@pytest.mark.parametrize("case", _cases("audit"))
def test_audit(case):
    _check("audit", case)


@pytest.mark.parametrize("case", _cases("json_transport"))
def test_json_transport(case):
    _check("json_transport", case)


@pytest.mark.parametrize("case", _cases("must_not_change"))
def test_must_not_change(case):
    for name in case["functions"]:
        ok, got = corpus.unchanged(name, case["input"])
        assert ok, (
            f"{case['id']}: {name} changed the input\n  input: {case['input']!r}\n  got:   {got!r}"
        )


def test_corpus_files_exist():
    missing = [
        f
        for f in (*corpus.FUNCTIONS, "must_not_change")
        if not (CORPUS_DIR / f"{f}.json").exists()
    ]
    assert not missing, f"corpus files missing: {missing} (run tools/build_corpus.py)"
