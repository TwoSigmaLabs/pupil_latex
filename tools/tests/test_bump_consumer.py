"""Tests for tools/bump_consumer.py (stdlib unittest; pytest runs them too).

python -m unittest discover -s tools/tests
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bump_consumer as bc  # noqa: E402

GIT_PIN = "pupiltree-latex[ftfy] @ git+https://github.com/TwoSigmaLabs/pupil_latex@v1.1.0#subdirectory=python\n"
WHEEL_PIN = (
    "pupiltree-latex[ftfy] @ https://github.com/TwoSigmaLabs/pupil_latex/releases/download/"
    "v1.1.0/pupiltree_latex-1.1.0-py3-none-any.whl\n"
)
TGZ = "https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.1.0/pupiltree-latex-1.1.0.tgz"
CDN = "https://cdn.jsdelivr.net/gh/TwoSigmaLabs/pupil_latex@v1.1.0/js/dist/pupiltree-latex.iife.js"
PUBSPEC = """name: app
dependencies:
  flutter:
    sdk: flutter
  pupiltree_latex_flutter:
    git:
      url: https://github.com/TwoSigmaLabs/pupil_latex
      ref: v1.1.0   # pinned
      path: dart/pupiltree_latex_flutter
  other_pkg:
    git:
      url: https://github.com/someone/other
      ref: v1.1.0
"""


class RewriteRefs(unittest.TestCase):
    def test_git_pin(self):
        out, old = bc.rewrite_refs(GIT_PIN, "1.2.0")
        self.assertIn("pupil_latex@v1.2.0#subdirectory=python", out)
        self.assertEqual(old, {"1.1.0"})

    def test_wheel_url_rewrites_tag_and_filename(self):
        out, old = bc.rewrite_refs(WHEEL_PIN, "1.2.0")
        self.assertIn("/download/v1.2.0/pupiltree_latex-1.2.0-py3-none-any.whl", out)
        self.assertNotIn("1.1.0", out)
        self.assertEqual(old, {"1.1.0"})

    def test_tgz_and_iife_urls(self):
        out, _ = bc.rewrite_refs(TGZ, "v1.2.0")
        self.assertTrue(out.endswith("/v1.2.0/pupiltree-latex-1.2.0.tgz"))
        url = "https://github.com/TwoSigmaLabs/pupil_latex/releases/download/v1.1.0/pupiltree-latex.iife.js"
        out, _ = bc.rewrite_refs(url, "1.2.0")
        self.assertTrue(out.endswith("/v1.2.0/pupiltree-latex.iife.js"))

    def test_jsdelivr_and_npm_git_refs(self):
        out, _ = bc.rewrite_refs(CDN, "1.2.0")
        self.assertIn("pupil_latex@v1.2.0/js/dist/", out)
        out, _ = bc.rewrite_refs(
            '"x": "github:TwoSigmaLabs/pupil_latex#v1.1.0"', "1.2.0"
        )
        self.assertIn("pupil_latex#v1.2.0", out)
        out, _ = bc.rewrite_refs(
            "git+https://github.com/TwoSigmaLabs/pupil_latex.git@v1.0.3", "1.2.0"
        )
        self.assertIn("pupil_latex.git@v1.2.0", out)

    def test_other_packages_untouched(self):
        text = "requests==1.1.0\nfoo @ git+https://github.com/x/other_latex@v1.1.0\n"
        out, old = bc.rewrite_refs(text, "1.2.0")
        self.assertEqual(out, text)
        self.assertEqual(old, set())

    def test_idempotent(self):
        once, _ = bc.rewrite_refs(WHEEL_PIN + GIT_PIN, "1.2.0")
        twice, old = bc.rewrite_refs(once, "1.2.0")
        self.assertEqual(once, twice)
        self.assertEqual(old, {"1.2.0"})


class RewritePubspec(unittest.TestCase):
    def test_only_pupil_latex_block(self):
        out, old = bc.rewrite_pubspec(PUBSPEC, "1.2.0")
        self.assertIn("      ref: v1.2.0   # pinned\n", out)
        self.assertIn("url: https://github.com/someone/other\n      ref: v1.1.0\n", out)
        self.assertEqual(old, {"1.1.0"})

    def test_quoted_ref_and_crlf(self):
        text = PUBSPEC.replace("ref: v1.1.0   # pinned", "ref: 'v1.1.0'").replace(
            "\n", "\r\n"
        )
        out, _ = bc.rewrite_pubspec(text, "1.2.0")
        self.assertIn("ref: 'v1.2.0'\r\n", out)
        self.assertEqual(out.count("\r\n"), text.count("\r\n"))

    def test_branch_ref_left_alone(self):
        text = PUBSPEC.replace("ref: v1.1.0   # pinned", "ref: main")
        out, old = bc.rewrite_pubspec(text, "1.2.0")
        self.assertEqual(out, text)
        self.assertEqual(old, set())


class Bump(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
        return p

    def test_python_repo(self):
        self.write("requirements.txt", "fastapi==0.1\n" + GIT_PIN)
        self.write("requirements/prod.txt", WHEEL_PIN)
        self.write("Dockerfile", "RUN pip install " + WHEEL_PIN)
        self.write("docs/notes.md", GIT_PIN)  # not a dependency file
        self.write(".venv/lib/requirements.txt", GIT_PIN)  # skipped dir
        res = bc.bump(self.root, ["python"], "1.2.0")
        self.assertEqual(
            res.changed, ["Dockerfile", "requirements.txt", "requirements/prod.txt"]
        )
        self.assertEqual(res.old_versions, {"1.1.0"})
        self.assertIn("1.1.0", (self.root / "docs/notes.md").read_text())

    def test_no_reference_is_a_clean_skip(self):
        self.write("requirements.txt", "fastapi==0.1\n")
        self.write("package.json", '{"dependencies": {"katex": "^0.16.0"}}')
        res = bc.bump(self.root, ["python", "js"], "1.2.0")
        self.assertEqual(res.changed, [])
        self.assertEqual(res.references, 0)

    def test_js_repo_reports_npm_dirs(self):
        pkg = {"dependencies": {"@pupiltree/latex": TGZ, "katex": "^0.16.11"}}
        self.write("frontend/package.json", json.dumps(pkg, indent=2) + "\n")
        res = bc.bump(self.root, ["js"], "1.2.0")
        self.assertEqual(res.changed, ["frontend/package.json"])
        self.assertEqual(res.npm_dirs, ["frontend"])
        data = json.loads((self.root / "frontend/package.json").read_text())
        self.assertTrue(
            data["dependencies"]["@pupiltree/latex"].endswith(
                "pupiltree-latex-1.2.0.tgz"
            )
        )

    def test_flutter_repo_reports_pubspec_dirs(self):
        self.write("pubspec.yaml", PUBSPEC)
        res = bc.bump(self.root, ["flutter"], "1.2.0")
        self.assertEqual(res.changed, ["pubspec.yaml"])
        self.assertEqual(res.pubspec_dirs, ["."])

    def test_fillers_script_src_and_vendored_iife(self):
        self.write("templates/board.html", f'<script src="{CDN}"></script>\n')
        self.write("static/vendor/pupiltree-latex.iife.js", "old bundle")
        new = self.write("new/pupiltree-latex.iife.js.download", "new bundle")
        res = bc.bump(self.root, ["fillers"], "1.2.0", iife=new)
        self.assertEqual(
            res.changed,
            ["static/vendor/pupiltree-latex.iife.js", "templates/board.html"],
        )
        self.assertEqual(
            (self.root / "static/vendor/pupiltree-latex.iife.js").read_text(),
            "new bundle",
        )

    def test_already_current(self):
        self.write("requirements.txt", GIT_PIN.replace("1.1.0", "1.2.0"))
        res = bc.bump(self.root, ["python"], "1.2.0")
        self.assertEqual(res.changed, [])
        self.assertEqual(res.references, 1)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            bc.bump(self.root, ["python"], "1.2")
        with self.assertRaises(ValueError):
            bc.bump(self.root, ["ruby"], "1.2.0")

    def test_cli_writes_github_output(self):
        self.write("requirements.txt", GIT_PIN)
        out = self.root / "gh_output"
        result = self.root / "result.json"
        with redirect_stdout(io.StringIO()):
            rc = bc.main(
                [
                    "bump",
                    "--repo-dir",
                    str(self.root),
                    "--kinds",
                    "python",
                    "--version",
                    "v1.2.0",
                    "--github-output",
                    str(out),
                    "--json-out",
                    str(result),
                ]
            )
        self.assertEqual(rc, 0)
        text = out.read_text()
        self.assertIn("changed=true\n", text)
        self.assertIn("old_versions=1.1.0\n", text)
        self.assertEqual(
            json.loads(result.read_text())["changed"], ["requirements.txt"]
        )


class PrBody(unittest.TestCase):
    def test_anchor_and_body(self):
        log = "# Changelog\n\n## 1.2.0 (2026-10-08)\n\nstuff\n\n## 1.1.0 (2026-09-26)\n"
        self.assertEqual(bc.changelog_anchor(log, "1.2.0"), "120-2026-10-08")
        self.assertEqual(bc.changelog_anchor(log, "9.9.9"), "")
        res = bc.Result(changed=["requirements.txt"], old_versions={"1.1.0"})
        body = bc.pr_body("1.2.0", res, log, ["run `flutter pub get`"])
        self.assertIn("from v1.1.0 to **v1.2.0**", body)
        self.assertIn("/blob/v1.2.0/CHANGELOG.md#120-2026-10-08", body)
        self.assertIn("- `requirements.txt`", body)
        self.assertIn("run `flutter pub get`", body)


if __name__ == "__main__":
    unittest.main()
