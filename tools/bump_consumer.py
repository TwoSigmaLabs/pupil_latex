"""Rewrite a consumer repository's pupiltree-latex pin to a new version.

Used by `.github/workflows/propagate.yml`, once per consumer checkout:

    python tools/bump_consumer.py bump --repo-dir consumer --kinds python,js --version 1.2.0 \\
        [--iife path/to/pupiltree-latex.iife.js] [--github-output "$GITHUB_OUTPUT"]

Kinds and the files each one rewrites (directories such as .git, node_modules
and virtualenvs are skipped):

- python:  requirements*.txt, constraints*.txt, any .txt under a requirements/
           directory, pyproject.toml, setup.cfg, setup.py, Pipfile, Dockerfile*
- js:      package.json (the release tarball URL). The lock file is refreshed
           by the workflow with `npm install --package-lock-only`.
- flutter: pubspec.yaml, the `ref:` of a pupiltree_latex(_flutter) git
           dependency that points at pupil_latex. pubspec.lock is refreshed by
           the workflow with `flutter pub get`.
- fillers: the python files plus .html/.htm/.js/.jinja/.j2 pages (an IIFE
           `<script src>` on jsDelivr or a release URL), and every vendored
           `pupiltree-latex.iife.js`, replaced with `--iife` when given. A
           README* next to a vendored bundle (Fillers
           `frontend/static/vendor/pupiltree-latex/README.md`) gets its
           `Version: X.Y.Z` line and `releases/tag/vX.Y.Z` link rewritten.

Only references to the pupil_latex repository are touched: a git ref
(`pupil_latex@vX.Y.Z`, `pupil_latex.git@vX.Y.Z`, `pupil_latex#vX.Y.Z`) or a
release download URL (`pupil_latex/releases/download/vX.Y.Z/<asset>-X.Y.Z…`).
A repository with no reference is left alone and reported as unchanged.

Standard library only. Tests: tools/tests/test_bump_consumer.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = "TwoSigmaLabs/pupil_latex"
KINDS = ("python", "js", "flutter", "fillers")
IIFE_NAME = "pupiltree-latex.iife.js"

SEMVER = r"\d+\.\d+\.\d+"
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "__pycache__",
    ".dart_tool",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    ".next",
}

# `pupil_latex@v1.2.0`, `pupil_latex.git@v1.2.0`, `pupil_latex#v1.2.0`
# (pip/npm git refs and jsDelivr `gh/<owner>/pupil_latex@v1.2.0/`).
GIT_REF = re.compile(r"(pupil_latex(?:\.git)?[@#])v(" + SEMVER + r")(?![\w.])")
# `pupil_latex/releases/download/v1.2.0/pupiltree_latex-1.2.0-py3-none-any.whl`,
# `.../v1.2.0/pupiltree-latex-1.2.0.tgz`, `.../v1.2.0/pupiltree-latex.iife.js`.
RELEASE_URL = re.compile(
    r"(pupil_latex/releases/download/)v("
    + SEMVER
    + r")/(pupiltree[-_]latex)(-"
    + SEMVER
    + r")?(?=[-.])"
)
# `pupil_latex/releases/tag/v1.2.0` (a release page link).
RELEASE_TAG_URL = re.compile(r"(pupil_latex/releases/tag/)v(" + SEMVER + r")(?![\w.])")


def normalize_version(version: str) -> str:
    v = version.strip()
    if v.startswith("v"):
        v = v[1:]
    if not re.fullmatch(SEMVER, v):
        raise ValueError(
            f"not a release version: {version!r} (expected X.Y.Z or vX.Y.Z)"
        )
    return v


def rewrite_refs(text: str, version: str) -> tuple[str, set[str]]:
    """Rewrite git refs and release URLs to `version`; return text and old versions."""
    version = normalize_version(version)
    old: set[str] = set()

    def git_ref(m: re.Match[str]) -> str:
        old.add(m.group(2))
        return f"{m.group(1)}v{version}"

    def release(m: re.Match[str]) -> str:
        old.add(m.group(2))
        suffix = f"-{version}" if m.group(4) else ""
        return f"{m.group(1)}v{version}/{m.group(3)}{suffix}"

    text = GIT_REF.sub(git_ref, text)
    text = RELEASE_URL.sub(release, text)
    text = RELEASE_TAG_URL.sub(git_ref, text)
    return text, old


# `- Version: 1.2.0 (...)` in the README next to a vendored IIFE bundle
# (Fillers `frontend/static/vendor/pupiltree-latex/README.md`).
VENDORED_VERSION_LINE = re.compile(
    r"^([ \t]*(?:[-*+][ \t]+)?(?:\*\*)?Version(?:\*\*)?:(?:\*\*)?[ \t]*`?)(v?)("
    + SEMVER
    + r")(?![\w.])",
    re.IGNORECASE | re.MULTILINE,
)


def is_vendored_readme(path: Path) -> bool:
    """A README (any extension) in the directory of a vendored IIFE bundle."""
    return (
        path.name.lower().startswith("readme") and (path.parent / IIFE_NAME).is_file()
    )


def rewrite_vendored_readme(text: str, version: str) -> tuple[str, set[str]]:
    """Rewrite the `Version: X.Y.Z` line and the release links of the README
    that documents a vendored IIFE bundle."""
    version = normalize_version(version)
    old: set[str] = set()

    def line(m: re.Match[str]) -> str:
        old.add(m.group(3))
        return f"{m.group(1)}{m.group(2)}{version}"

    text = VENDORED_VERSION_LINE.sub(line, text)
    text, old2 = rewrite_refs(text, version)
    return text, old | old2


_DEP_KEY = re.compile(r"^(\s*)(pupiltree_latex(?:_flutter)?):\s*(#.*)?$")
_REF = re.compile(r"^(\s*ref:\s*)(['\"]?)v?(" + SEMVER + r")\2(\s*(?:#.*)?)$")


def rewrite_pubspec(text: str, version: str) -> tuple[str, set[str]]:
    """Rewrite `ref:` inside a pupiltree_latex(_flutter) git dependency on pupil_latex."""
    version = normalize_version(version)
    lines = text.splitlines(keepends=True)
    old: set[str] = set()
    i = 0
    while i < len(lines):
        m = _DEP_KEY.match(lines[i].rstrip("\r\n"))
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        j = i + 1
        block: list[int] = []
        while j < len(lines):
            body = lines[j].rstrip("\r\n")
            if body.strip() and len(body) - len(body.lstrip()) <= indent:
                break
            block.append(j)
            j += 1
        if any("pupil_latex" in lines[k] for k in block):
            for k in block:
                eol = lines[k][len(lines[k].rstrip("\r\n")) :]
                r = _REF.match(lines[k].rstrip("\r\n"))
                if r:
                    old.add(r.group(3))
                    lines[k] = (
                        f"{r.group(1)}{r.group(2)}v{version}{r.group(2)}{r.group(4)}{eol}"
                    )
        i = j
    return "".join(lines), old


def _python_file(path: Path) -> bool:
    name = path.name
    if re.fullmatch(r"(requirements|constraints)[\w.-]*\.(txt|in)", name):
        return True
    if path.suffix in {".txt", ".in"} and "requirements" in {
        p.lower() for p in path.parent.parts
    }:
        return True
    return name in {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "Pipfile",
    } or name.startswith("Dockerfile")


def _matches(kind: str, path: Path) -> bool:
    if kind == "python":
        return _python_file(path)
    if kind == "js":
        return path.name == "package.json"
    if kind == "flutter":
        return path.name == "pubspec.yaml"
    if kind == "fillers":
        if path.name == IIFE_NAME:
            return False
        return _python_file(path) or path.suffix in {
            ".html",
            ".htm",
            ".js",
            ".jinja",
            ".j2",
        }
    raise ValueError(kind)


def iter_files(root: Path):
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS and not p.is_symlink():
                    stack.append(p)
            elif p.is_file():
                yield p


@dataclass
class Result:
    changed: list[str] = field(default_factory=list)
    old_versions: set[str] = field(default_factory=set)
    references: int = 0
    pubspec_dirs: list[str] = field(default_factory=list)
    npm_dirs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "changed": self.changed,
            "old_versions": sorted(self.old_versions),
            "references": self.references,
            "pubspec_dirs": self.pubspec_dirs,
            "npm_dirs": self.npm_dirs,
        }


def bump(
    repo_dir: Path, kinds: list[str], version: str, iife: Path | None = None
) -> Result:
    version = normalize_version(version)
    for k in kinds:
        if k not in KINDS:
            raise ValueError(f"unknown kind {k!r}; expected one of {', '.join(KINDS)}")
    res = Result()
    new_iife = iife.read_bytes() if iife else None
    for path in iter_files(repo_dir):
        rel = path.relative_to(repo_dir).as_posix()
        if "fillers" in kinds and path.name == IIFE_NAME:
            res.references += 1
            if new_iife is not None and path.read_bytes() != new_iife:
                path.write_bytes(new_iife)
                res.changed.append(rel)
            continue
        readme = "fillers" in kinds and is_vendored_readme(path)
        if not readme and not any(_matches(k, path) for k in kinds):
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if readme:
            new, old = rewrite_vendored_readme(text, version)
        elif "pupil_latex" not in text:
            continue
        elif path.name == "pubspec.yaml":
            new, old = rewrite_pubspec(text, version)
            new, old2 = rewrite_refs(new, version)
            old |= old2
        else:
            new, old = rewrite_refs(text, version)
        if old:
            res.references += 1
            res.old_versions |= old
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            res.changed.append(rel)
            parent = path.parent.relative_to(repo_dir).as_posix() or "."
            if path.name == "pubspec.yaml":
                res.pubspec_dirs.append(parent)
            elif path.name == "package.json":
                res.npm_dirs.append(parent)
    res.changed.sort()
    return res


def changelog_anchor(changelog: str, version: str) -> str:
    """GitHub's anchor for the `## <version> …` heading, or '' if absent."""
    version = normalize_version(version)
    for line in changelog.splitlines():
        m = re.match(r"^##\s+(" + re.escape(version) + r"\b.*?)\s*$", line)
        if m:
            slug = m.group(1).strip().lower()
            slug = re.sub(r"[^\w\- ]", "", slug)
            return slug.replace(" ", "-")
    return ""


def pr_body(
    version: str, result: Result, changelog: str = "", notes: list[str] | None = None
) -> str:
    version = normalize_version(version)
    anchor = changelog_anchor(changelog, version)
    url = f"https://github.com/{REPO}/blob/v{version}/CHANGELOG.md" + (
        f"#{anchor}" if anchor else ""
    )
    old = ", ".join(f"v{v}" for v in sorted(result.old_versions)) or "an older version"
    lines = [
        f"Bumps pupiltree-latex from {old} to **v{version}**.",
        "",
        f"What changed: [CHANGELOG v{version}]({url}).",
        "",
        "Files:",
        *[f"- `{c}`" for c in result.changed],
    ]
    if notes:
        lines += ["", "Needs attention:", *[f"- {n}" for n in notes]]
    lines += ["", f"Opened automatically by `{REPO}/.github/workflows/propagate.yml`."]
    return "\n".join(lines) + "\n"


def _write_github_output(path: str, result: Result) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"changed={'true' if result.changed else 'false'}\n")
        fh.write(f"references={result.references}\n")
        fh.write(f"old_versions={' '.join(sorted(result.old_versions))}\n")
        fh.write(f"pubspec_dirs={json.dumps(result.pubspec_dirs)}\n")
        fh.write(f"npm_dirs={json.dumps(result.npm_dirs)}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bump", help="rewrite the pins in a consumer checkout")
    b.add_argument("--repo-dir", type=Path, required=True)
    b.add_argument("--kinds", required=True, help="comma-separated: " + ",".join(KINDS))
    b.add_argument("--version", required=True)
    b.add_argument(
        "--iife", type=Path, help="new pupiltree-latex.iife.js for vendored copies"
    )
    b.add_argument("--json-out", type=Path, help="write the result as JSON here")
    b.add_argument(
        "--github-output", help="append step outputs to this file ($GITHUB_OUTPUT)"
    )
    pb = sub.add_parser("pr-body", help="print the pull request body")
    pb.add_argument("--version", required=True)
    pb.add_argument(
        "--result", type=Path, required=True, help="JSON written by `bump --json-out`"
    )
    pb.add_argument("--changelog", type=Path)
    pb.add_argument("--note", action="append", default=[])
    args = ap.parse_args(argv)

    if args.cmd == "pr-body":
        data = json.loads(args.result.read_text(encoding="utf-8"))
        res = Result(changed=data["changed"], old_versions=set(data["old_versions"]))
        log = args.changelog.read_text(encoding="utf-8") if args.changelog else ""
        sys.stdout.write(pr_body(args.version, res, log, args.note))
        return 0

    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    try:
        res = bump(args.repo_dir, kinds, args.version, args.iife)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json_out:
        args.json_out.write_text(json.dumps(res.as_dict(), indent=1), encoding="utf-8")
    if args.github_output:
        _write_github_output(args.github_output, res)
    if not res.references:
        print(
            f"no pupiltree-latex reference found for kinds {','.join(kinds)}; nothing to bump"
        )
    elif not res.changed:
        print(f"already at v{normalize_version(args.version)}")
    else:
        print("\n".join(res.changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
