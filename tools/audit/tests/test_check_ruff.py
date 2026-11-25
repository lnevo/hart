"""tools/audit/check_ruff.py: the pinned ruff is found or refused with a reason, and ruff's answers map to exit codes.

Fake ruff binaries (bash scripts) stand in for the error paths; the real pinned ruff, where installed, checks that
ruff.toml's exclusions and Jython ignores hold on the real files.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import check_ruff as cr  # noqa: E402

FAKE = """#!/usr/bin/env bash
if [[ "$1" == --version ]]; then echo "${FAKE_VERSION:-ruff 9.9.9}"; exit "${FAKE_VERSION_RC:-0}"; fi
printf '%s' "${FAKE_OUT:-}"
exit "${FAKE_RC:-0}"
"""


class Scratch(unittest.TestCase):
    """A scratch checkout: requirements.txt pinning ruff 9.9.9, a ruff.toml, one .py file and a fake ruff."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        (self.root / "requirements.txt").write_text("numpy==2.5.4\nruff==9.9.9   # the pin\n", encoding="utf-8")
        (self.root / "ruff.toml").write_text('[lint]\nselect = ["F"]\n', encoding="utf-8")
        (self.root / "a.py").write_text("x = 1\n", encoding="utf-8")
        self.ruff = self.fake("ruff")
        patcher = mock.patch.object(cr, "candidates", lambda root: [self.ruff])
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake(self, name: str) -> Path:
        path = self.root / "bin" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(FAKE, encoding="utf-8")
        path.chmod(0o755)
        return path

    def env(self, **values: str):
        return mock.patch.dict(os.environ, {f"FAKE_{k.upper()}": v for k, v in values.items()})


class PinTests(Scratch):
    def test_the_one_pin_is_read_past_its_comment(self) -> None:
        self.assertEqual(cr.pinned_version(self.root), "9.9.9")

    def test_no_pin_or_two_pins_are_refused(self) -> None:
        for text in ("numpy==1\n", "ruff==1\nruff==2\n", "# ruff==1 in a comment only\n"):
            (self.root / "requirements.txt").write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaisesRegex(cr.RuffSetupError, "pins ruff [02] times"):
                cr.pinned_version(self.root)

    def test_a_missing_requirements_file_is_refused(self) -> None:
        (self.root / "requirements.txt").unlink()
        with self.assertRaisesRegex(cr.RuffSetupError, "cannot read .*requirements.txt"):
            cr.pinned_version(self.root)


class FindTests(Scratch):
    def test_the_first_place_with_the_pinned_version_wins(self) -> None:
        other = self.fake("ruff-other")
        other.write_text(FAKE.replace("${FAKE_VERSION:-ruff 9.9.9}", "ruff 1.0.0"), encoding="utf-8")
        self.assertEqual(cr.find_ruff("9.9.9", [self.root / "missing", other, self.ruff]), self.ruff)

    def test_another_version_is_refused_and_named(self) -> None:
        with self.env(version="ruff 1.0.0"), self.assertRaisesRegex(cr.RuffSetupError,
                                                                    r"ruff 9\.9\.9 .*not found: .*ruff is 1\.0\.0"):
            cr.find_ruff("9.9.9", [self.ruff])

    def test_no_ruff_anywhere_says_where_it_looked_and_how_to_install(self) -> None:
        places = [self.root / ".venv/bin/ruff"]
        with self.assertRaises(cr.RuffSetupError) as got:
            cr.find_ruff("9.9.9", places)
        self.assertIn("not installed at", str(got.exception))
        self.assertIn(f"{self.root / '.venv/bin/pip'} install ruff==9.9.9", str(got.exception))

    def test_a_ruff_that_cannot_say_its_version_is_refused(self) -> None:
        with self.env(version="garbage", version_rc="1"), self.assertRaisesRegex(cr.RuffSetupError, "answered 1"):
            cr.find_ruff("9.9.9", [self.ruff])

    def test_a_broken_first_ruff_does_not_hide_a_good_one_later(self) -> None:
        broken = self.root / "bin" / "broken"
        broken.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        broken.chmod(0o755)
        self.assertEqual(cr.find_ruff("9.9.9", [broken, self.ruff]), self.ruff)
        with self.assertRaisesRegex(cr.RuffSetupError, "broken --version answered 1"):
            cr.find_ruff("9.9.9", [broken])

    def test_pin_prints_the_requirement_for_ci_and_win_run(self) -> None:
        with mock.patch.object(cr, "ROOT", self.root), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cr.main(["--pin"]), 0)
        self.assertEqual(out.getvalue(), "ruff==9.9.9\n")
        (self.root / "requirements.txt").write_text("numpy==1\n", encoding="utf-8")
        with mock.patch.object(cr, "ROOT", self.root), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cr.main(["--pin"]), 2)
        self.assertIn("pins ruff 0 times", err.getvalue())


class RunTests(Scratch):
    def test_clean_findings_and_ruff_errors(self) -> None:
        with self.env(rc="0", out="All checks passed!\n"):
            self.assertEqual(cr.run(self.root), (0, "All checks passed!"))
        with self.env(rc="1", out="a.py:1:8: F401 [*] `os` imported but unused\nFound 1 error.\n"):
            self.assertEqual(cr.run(self.root, [str(self.root / "a.py")])[0], 1)
        with self.env(rc="2", out="error: bad config\n"), self.assertRaisesRegex(cr.RuffError, "exit 2"):
            cr.run(self.root)
        # exit 1 with nothing this check can count is not a pass
        with self.env(rc="1", out="something else\n"), self.assertRaisesRegex(cr.RuffError, "no finding"):
            cr.run(self.root)

    def test_inputs_are_checked_before_ruff_runs(self) -> None:
        with self.assertRaisesRegex(cr.RuffSetupError, "no such file: .*nope.py"):
            cr.run(self.root, [str(self.root / "nope.py")])
        with self.assertRaisesRegex(ValueError, "empty file list"):
            cr.run(self.root, [])
        (self.root / "ruff.toml").unlink()
        with self.assertRaisesRegex(cr.RuffSetupError, "no ruff.toml in"):
            cr.run(self.root)

    def test_relative_and_dotted_paths_are_made_absolute(self) -> None:
        log = self.root / "argv.log"
        self.ruff.write_text(FAKE.replace('printf', f'printf "%s\\n" "$@" > {log}; printf'), encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(self.root / "bin")
        try:
            cr.run(Path(".."), ["../bin/../a.py"])
        finally:
            os.chdir(cwd)
        argv = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(argv[argv.index("--config") + 1], str(self.root / "ruff.toml"))
        self.assertEqual(argv[-1], str(self.root / "a.py"))

    def test_a_symlinked_path_is_the_file_it_names(self) -> None:
        log = self.root / "argv.log"
        self.ruff.write_text(FAKE.replace('printf', f'printf "%s\\n" "$@" > {log}; printf'), encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "link"
            link.symlink_to(self.root)
            cr.run(link, [str(link / "a.py")])
        argv = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(argv[argv.index("--config") + 1], str(self.root / "ruff.toml"))
        self.assertEqual(argv[-1], str(self.root / "a.py"))

    def test_a_file_git_ignores_is_skipped_as_the_whole_repo_run_skips_it(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        (self.root / "scratch").mkdir()
        (self.root / "scratch/x.py").write_text("import os\n", encoding="utf-8")
        log = self.root / "argv.log"
        self.ruff.write_text(FAKE.replace('printf', f'printf "%s\\n" "$@" > {log}; printf'), encoding="utf-8")
        self.assertEqual(cr.run(self.root, [str(self.root / "scratch/x.py")]), (0, "every file named is ignored by git"))
        self.assertFalse(log.exists())          # ruff was not started
        cr.run(self.root, [str(self.root / "scratch/x.py"), str(self.root / "a.py")])
        self.assertEqual(log.read_text(encoding="utf-8").splitlines()[-1], str(self.root / "a.py"))

    def test_a_git_failure_is_reported_not_taken_as_not_ignored(self) -> None:
        (self.root / ".git").write_text("gitdir: /nonexistent\n", encoding="utf-8")     # a broken worktree link
        with self.assertRaisesRegex(cr.RuffSetupError, "git check-ignore in .* answered 128"):
            cr.run(self.root, [str(self.root / "a.py")])

    def test_main_exit_codes(self) -> None:
        with mock.patch.object(cr, "ROOT", self.root):
            for rc, out, want in (("0", "", 0), ("1", "a.py:1:1: F821 Undefined name `y`\n", 1), ("2", "boom", 2)):
                with self.subTest(rc=rc), self.env(rc=rc, out=out), contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(cr.main([]), want)
                    if want == 2:
                        self.assertIn("check_ruff: ruff stopped with exit 2", err.getvalue())


class RealRuffTests(unittest.TestCase):
    """The pinned ruff on the real ruff.toml, where it is installed."""

    def setUp(self) -> None:
        try:
            self.ruff = cr.find_ruff(cr.pinned_version(ROOT), cr.candidates(ROOT))
        except cr.RuffSetupError as err:
            self.skipTest(str(err))

    def test_a_finding_in_a_new_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.py"
            bad.write_text("import os\nprint(undefined_name)\n", encoding="utf-8")
            count, out = cr.run(ROOT, [str(bad)])
        self.assertEqual(count, 2, out)
        self.assertIn("F401", out)
        self.assertIn("F821", out)

    def test_excluded_and_jython_files_pass(self) -> None:
        # signal_coordinator.py does not parse as Python 3 (latch.await): excluded; panel_status.py uses JMRI's globals
        for rel in ("jmri/scripts/signal_coordinator.py", "jmri/layouts/hart/scripts/panel_status.py"):
            with self.subTest(rel=rel):
                self.assertEqual(cr.run(ROOT, [str(ROOT / rel)])[0], 0)

    def test_the_jython_ignore_is_f821_only(self) -> None:
        # a scratch copy at the same path in a scratch checkout: an unused import in a Jython file is still reported
        with tempfile.TemporaryDirectory() as d:
            root = Path(os.path.realpath(d))
            for rel in ("ruff.toml", "requirements.txt"):
                shutil.copy(ROOT / rel, root / rel)
            jy = root / "jmri/layouts/hart/scripts/panel_status.py"
            jy.parent.mkdir(parents=True)
            jy.write_text("import os\nsensors.getSensor('x')\n", encoding="utf-8")
            with mock.patch.object(cr, "candidates", lambda r: [self.ruff]):
                count, out = cr.run(root, [str(jy)])
        self.assertEqual(count, 1, out)
        self.assertIn("F401", out)


if __name__ == "__main__":
    unittest.main()
