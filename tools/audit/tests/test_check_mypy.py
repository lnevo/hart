"""tools/audit/check_mypy.py: which files are checked, the baseline comparison and its refusals, and mypy's answers.

Fake pythons (bash scripts) stand in for mypy so the error paths run without it; one test runs the real pinned mypy
on a scratch checkout where it is installed.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import check_mypy as cm  # noqa: E402

FAKE = """#!/usr/bin/env bash
if [[ "$3" == --version ]]; then echo "${FAKE_VERSION:-mypy 9.9.9 (compiled: no)}"; exit "${FAKE_VERSION_RC:-0}"; fi
printf '%b' "${FAKE_OUT:-}"
exit "${FAKE_RC:-0}"
"""

MYPY_INI = """[mypy]
mypy_path = src
exclude = (?x)(^skip/ | ^jy/dual\\.py$)

[mypy-pkg.*]
disallow_untyped_defs = True

[mypy-pkg.tests.*]
disallow_untyped_defs = False

[mypy-tools.*]
disallow_untyped_defs = True
warn_return_any = True

[mypy-loose.*]
warn_return_any = True
"""

RUFF = """extend-exclude = ["vendor", "old/one.py"]
[lint.per-file-ignores]
"jy/inside.py" = ["F821"]
"tools/x.py" = ["F401"]
"""


class Scratch(unittest.TestCase):
    """A scratch git checkout with a pin, mypy.ini, ruff.toml and files of each kind."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.write("requirements.txt", "ruff==1\nmypy==9.9.9  # the pin\n")
        self.write("mypy.ini", MYPY_INI)
        self.write("ruff.toml", RUFF)
        for rel in ("a.py", "tools/x.py", "other/a.py", "vendor/v.py", "old/one.py", "old/two.py", "skip/s.py",
                    "jy/dual.py", "jy/inside.py", "src/pkg/m.py", "src/pkg/tests/t.py"):
            self.write(rel, "x = 1\n")
        self.write("jy/imports.py", "import os\nfrom java.lang import Thread\n")
        self.write("untracked.py", "x = 1\n")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "--", *[p for p in self.tracked()]], check=True)
        self.python = self.root / "fakepython"
        self.python.write_text(FAKE, encoding="utf-8")
        self.python.chmod(0o755)

    def tracked(self) -> list[str]:
        return [str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()
                and p.name != "untracked.py" and ".git" not in p.parts]

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def env(self, **kw: str) -> contextlib.AbstractContextManager[object]:
        return mock.patch.dict(os.environ, {f"FAKE_{k.upper()}": v for k, v in kw.items()})


class Files(Scratch):
    def test_excludes_ruff_lists_jython_and_mypy_exclude(self) -> None:
        self.assertEqual(sorted(cm.checked_files(self.root)),
                         ["a.py", "old/two.py", "other/a.py", "src/pkg/m.py", "src/pkg/tests/t.py", "tools/x.py"])

    def test_under_matches_whole_segments(self) -> None:
        self.assertTrue(cm.under("vendor/v.py", ["vendor"]))
        self.assertTrue(cm.under("old/one.py", ["old/one.py"]))
        self.assertFalse(cm.under("vendored/v.py", ["vendor"]))

    def test_is_jython(self) -> None:
        self.assertTrue(cm.is_jython("x = 1\n  import jmri\n"))
        self.assertTrue(cm.is_jython("from javax.swing import JFrame\n"))
        self.assertFalse(cm.is_jython("import javascript_tools\n# import jmri in a comment\n"))

    def test_bad_ruff_toml(self) -> None:
        self.write("ruff.toml", "extend-exclude = [\n")
        with self.assertRaisesRegex(cm.MypySetupError, "cannot read .*ruff.toml"):
            cm.checked_files(self.root)
        self.write("ruff.toml", 'extend-exclude = "vendor"\n')
        with self.assertRaisesRegex(cm.MypySetupError, "must be a list"):
            cm.checked_files(self.root)

    def test_bad_mypy_ini(self) -> None:
        self.write("mypy.ini", "[other]\n")
        with self.assertRaisesRegex(cm.MypySetupError, r"no \[mypy\] section"):
            cm.checked_files(self.root)
        self.write("mypy.ini", "[mypy]\nexclude = (\n")
        with self.assertRaisesRegex(cm.MypySetupError, "not a regular expression"):
            cm.checked_files(self.root)
        (self.root / "mypy.ini").unlink()
        with self.assertRaisesRegex(cm.MypySetupError, "cannot read"):
            cm.checked_files(self.root)

    def test_no_git(self) -> None:
        with tempfile.TemporaryDirectory() as bare:
            Path(bare, "mypy.ini").write_text(MYPY_INI, encoding="utf-8")
            Path(bare, "ruff.toml").write_text(RUFF, encoding="utf-8")
            with self.assertRaises(cm.files.GitError):
                cm.checked_files(Path(bare))

    def test_batches_never_share_a_name(self) -> None:
        got = cm.batches(["a/x.py", "b/x.py", "a/y.py", "c/x.py", "b/y.py"])
        self.assertEqual(got, [["a/x.py", "a/y.py"], ["b/x.py", "b/y.py"], ["c/x.py"]])
        self.assertEqual(cm.batches([]), [])


class Strict(Scratch):
    def test_scope_from_package_sections(self) -> None:
        scope = cm.strict_scope(self.root)
        self.assertEqual(scope, cm.StrictScope(("src/pkg", "tools"), ("src/pkg/tests",)))
        self.assertTrue(scope.holds("src/pkg/m.py"))
        self.assertTrue(scope.holds("tools/deep/y.py"))
        self.assertFalse(scope.holds("src/pkg/tests/t.py"))
        self.assertFalse(scope.holds("src/pkgx/m.py"))
        self.assertFalse(scope.holds("a.py"))

    def test_package_found_under_mypy_path_before_root(self) -> None:
        self.write("pkg/other.py", "x = 1\n")
        self.assertEqual(cm.package_folder(self.root, "pkg", ["src"]), "src/pkg")
        self.assertEqual(cm.package_folder(self.root, "pkg", []), "pkg")

    def test_section_with_no_folder(self) -> None:
        self.write("mypy.ini", "[mypy]\n[mypy-gone.*]\ndisallow_untyped_defs = True\n")
        with self.assertRaisesRegex(cm.MypySetupError, r"\[mypy-gone\.\*\] names no folder"):
            cm.strict_scope(self.root)

    def test_strict_option_on_one_module_or_not_a_boolean(self) -> None:
        self.write("mypy.ini", "[mypy]\n[mypy-tools.x]\ndisallow_untyped_defs = True\n")
        with self.assertRaisesRegex(cm.MypySetupError, "set it on a whole package"):
            cm.strict_scope(self.root)
        self.write("mypy.ini", "[mypy]\n[mypy-tools.*]\ndisallow_untyped_defs = maybe\n")
        with self.assertRaisesRegex(cm.MypySetupError, "disallow_untyped_defs"):
            cm.strict_scope(self.root)

    def test_repo_scope(self) -> None:
        scope = cm.strict_scope(ROOT)
        for path in ("tools/hartlib/src/hartlib/paths.py", "tools/audit/check_mypy.py"):
            self.assertTrue(scope.holds(path), path)
        for path in ("tools/hartlib/tests/test_paths.py", "tools/audit/tests/test_check_mypy.py",
                     "tools/schematic/build.py"):
            self.assertFalse(scope.holds(path), path)


class Pin(Scratch):
    def test_pin_found_once(self) -> None:
        self.assertEqual(cm.pinned_version(self.root), "9.9.9")

    def test_pin_missing_or_twice(self) -> None:
        self.write("requirements.txt", "ruff==1\n# mypy==1.0 in a comment\n")
        with self.assertRaisesRegex(cm.MypySetupError, "0 times"):
            cm.pinned_version(self.root)
        self.write("requirements.txt", "mypy==1\nmypy==2\n")
        with self.assertRaisesRegex(cm.MypySetupError, "2 times"):
            cm.pinned_version(self.root)
        (self.root / "requirements.txt").unlink()
        with self.assertRaisesRegex(cm.MypySetupError, "cannot read"):
            cm.pinned_version(self.root)

    def test_find_takes_the_pinned_one(self) -> None:
        with self.env(version="mypy 9.9.9 (compiled: yes)"):
            self.assertEqual(cm.find_mypy("9.9.9", [self.root / "nothing", self.python]), self.python)

    def test_find_refuses_other_version_or_none(self) -> None:
        with self.env(version="mypy 1.0.0"), self.assertRaisesRegex(cm.MypySetupError, "has mypy 1.0.0"):
            cm.find_mypy("9.9.9", [self.python])
        with self.env(version="No module named mypy", version_rc="1"), \
                self.assertRaisesRegex(cm.MypySetupError, "has no mypy"):
            cm.find_mypy("9.9.9", [self.python])
        with self.assertRaisesRegex(cm.MypySetupError, "no python at"):
            cm.find_mypy("9.9.9", [self.root / "nothing"])


class Runs(Scratch):
    def test_counts_errors_not_notes(self) -> None:
        out = ("a.py:3: error: bad  [x]\na.py:4:2: error: bad  [y]\na.py:4: note: see\n"
               "tools/x.py:1: error: bad  [z]\n")
        with self.env(out=out, rc="1"):
            self.assertEqual(cm.run_batch(self.python, self.root, ["a.py"]), {"a.py": 2, "tools/x.py": 1})

    def test_clean_run(self) -> None:
        with self.env(rc="0"):
            self.assertEqual(cm.run_batch(self.python, self.root, ["a.py"]), {})

    def test_crash_and_unreadable_output(self) -> None:
        with self.env(out="Traceback", rc="2"), self.assertRaisesRegex(cm.MypyError, "exit 2"):
            cm.run_batch(self.python, self.root, ["a.py"])
        with self.env(out="something odd", rc="1"), self.assertRaisesRegex(cm.MypyError, "no error this check"):
            cm.run_batch(self.python, self.root, ["a.py"])

    def test_cannot_start(self) -> None:
        with self.assertRaisesRegex(cm.MypyError, "could not run"):
            cm.run_batch(self.root / "nothing", self.root, ["a.py"])


class Baseline(Scratch):
    def test_absent_is_empty(self) -> None:
        self.assertEqual(cm.read_baseline(self.root / "none.json"), {})

    def test_bad_baseline(self) -> None:
        for text in ("{", "[]", '{"a.py": 0}', '{"a.py": "2"}', '{"a.py": true}'):
            path = self.write("b.json", text)
            with self.subTest(text=text), self.assertRaises(cm.BaselineError):
                cm.read_baseline(path)

    def test_compare(self) -> None:
        now = {"a.py": 3, "b.py": 1, "new.py": 2, "src/pkg/x.py": 1, "src/pkg/tests/t.py": 1}
        base = {"a.py": 2, "b.py": 4, "gone.py": 5, "src/pkg/tests/t.py": 1}
        v = cm.compare(now, base, cm.strict_scope(self.root))
        self.assertEqual(v.strict, {"src/pkg/x.py": 1})
        self.assertEqual(v.rose, {"a.py": (2, 3), "new.py": (0, 2)})
        self.assertEqual(v.fell, {"b.py": (4, 1), "gone.py": (5, 0)})
        self.assertFalse(v.ok)
        self.assertTrue(cm.compare({"b.py": 1}, base, cm.strict_scope(self.root)).ok)

    def test_write_leaves_strict_folders_out_and_sorts(self) -> None:
        path = self.root / "b.json"
        cm.write_baseline(path, {"z.py": 1, "a.py": 2, "src/pkg/x.py": 1, "src/pkg/tests/t.py": 1},
                          cm.strict_scope(self.root))
        self.assertEqual(list(json.loads(path.read_text(encoding="utf-8"))), ["a.py", "src/pkg/tests/t.py", "z.py"])
        self.assertEqual(cm.read_baseline(path), {"a.py": 2, "src/pkg/tests/t.py": 1, "z.py": 1})


class Main(Scratch):
    def main(self, now: dict[str, int] | Exception, *argv: str, base: dict[str, int] | None = None) -> tuple[int, str]:
        baseline = self.root / "base.json"
        if base is not None:
            baseline.write_text(json.dumps(base), encoding="utf-8")
        out = io.StringIO()
        with mock.patch.object(cm, "ROOT", self.root), mock.patch.object(cm, "BASELINE", "base.json"), \
                mock.patch.object(cm, "run", side_effect=[now]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = cm.main(list(argv))
        return rc, out.getvalue()

    def test_pass_at_the_baseline(self) -> None:
        rc, out = self.main({"a.py": 2}, base={"a.py": 2})
        self.assertEqual(rc, 0)
        self.assertIn("no file above its baseline count", out)
        self.assertNotIn("below the baseline", out)

    def test_a_fall_passes_with_a_note_and_update_locks_it_in(self) -> None:
        rc, out = self.main({"a.py": 1}, base={"a.py": 2, "gone.py": 1})
        self.assertEqual(rc, 0)
        self.assertIn("2 file(s) below the baseline; `--update` locks them in", out)
        self.assertEqual(json.loads((self.root / "base.json").read_text(encoding="utf-8")), {"a.py": 2, "gone.py": 1})
        rc, _ = self.main({"a.py": 1}, "--update")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((self.root / "base.json").read_text(encoding="utf-8")), {"a.py": 1})
        rc, out = self.main({"a.py": 1})
        self.assertEqual(rc, 0)
        self.assertNotIn("below the baseline", out)

    def test_a_fall_beside_a_rise_still_fails(self) -> None:
        rc, out = self.main({"a.py": 1, "b.py": 2}, base={"a.py": 2, "b.py": 1})
        self.assertEqual(rc, 1)
        self.assertIn("rose: b.py: 1 -> 2", out)

    def test_a_new_file_with_errors_fails(self) -> None:
        rc, out = self.main({"new.py": 1}, base={"a.py": 1})
        self.assertEqual(rc, 1)
        self.assertIn("rose: new.py: 0 -> 1", out)

    def test_rise_fails(self) -> None:
        rc, out = self.main({"a.py": 3}, base={"a.py": 2})
        self.assertEqual(rc, 1)
        self.assertIn("rose: a.py: 2 -> 3", out)

    def test_strict_folder_error_fails(self) -> None:
        rc, out = self.main({"src/pkg/x.py": 1}, base={})
        self.assertEqual(rc, 1)
        self.assertIn("strict: src/pkg/x.py: 1 error(s)", out)
        rc, out = self.main({"src/pkg/x.py": 1}, base={"src/pkg/x.py": 1})
        self.assertEqual(rc, 1, "a baseline row does not excuse a strict file")

    def test_bad_strict_section_is_exit_2(self) -> None:
        self.write("mypy.ini", "[mypy]\n[mypy-gone.*]\ndisallow_untyped_defs = True\n")
        rc, out = self.main({})
        self.assertEqual(rc, 2)
        self.assertIn("names no folder", out)

    def test_update_writes_and_refuses_a_rise(self) -> None:
        rc, _ = self.main({"a.py": 1}, "--update", base={"a.py": 2})
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((self.root / "base.json").read_text(encoding="utf-8")), {"a.py": 1})
        rc, out = self.main({"a.py": 1, "n.py": 1}, "--update")
        self.assertEqual(rc, 1)
        self.assertIn("--update refused", out)
        self.assertEqual(json.loads((self.root / "base.json").read_text(encoding="utf-8")), {"a.py": 1})

    def test_setup_error_is_exit_2(self) -> None:
        rc, out = self.main(cm.MypySetupError("mypy 9.9.9 (requirements.txt) not found"), base=None)
        self.assertEqual(rc, 2)
        self.assertIn("check_mypy:", out)

    def test_bad_baseline_is_exit_2(self) -> None:
        (self.root / "base.json").write_text("{", encoding="utf-8")
        rc, out = self.main({})
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", out)

    def test_list(self) -> None:
        rc, out = self.main({}, "--list")
        self.assertEqual(rc, 0)
        self.assertIn("other/a.py", out.splitlines())


class RealMypy(Scratch):
    def test_real_mypy_counts_a_type_error(self) -> None:
        try:
            python = cm.find_mypy(cm.pinned_version(ROOT), cm.interpreters(ROOT))
        except cm.MypySetupError as err:
            self.skipTest(str(err))
        self.write("mypy.ini", "[mypy]\n")
        self.write("bad.py", "x: int = 'one'\n")
        with mock.patch.dict(os.environ, {"HART_CACHE_DIR": str(self.root / ".cache")}):
            self.assertEqual(cm.run_batch(python, self.root, ["bad.py", "a.py"]), {"bad.py": 1})


if __name__ == "__main__":
    unittest.main()
