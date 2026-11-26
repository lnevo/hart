"""check_stamps: what a stamp's key holds (the environment tests skip on, the store, the skipped tests, the git
refs and the job's own manifest entry), so that a change to any of them reruns the job and nothing else does."""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402
from stamps_case import RepoCase  # noqa: E402


REPO = cs.ROOT


class SkipConditionTest(unittest.TestCase):
    def test_every_environment_variable_a_test_skips_on_is_in_the_key(self) -> None:
        """A job whose tests skipped is stamped with the skips in its key; what they skip on must be in the key too.
        An environment variable read in a skip decorator, or in the lines before a skipTest, is in KEY_ENV."""
        tracked = subprocess.run(["git", "ls-files", "*tests/test*.py"], cwd=REPO, capture_output=True, text=True,
                                 check=True).stdout.split()
        read = re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z_0-9]+)["']|os\.environ\[["']([A-Z_0-9]+)["']\]""")
        found = {}
        for rel in tracked:
            if rel.startswith(("jmri/layouts/hart/parked/", "archive/")):
                continue
            lines = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines):
                if "skipIf" in line or "skipUnless" in line or "skipTest" in line or "SkipTest" in line:
                    for near in lines[max(0, i - 3):i + 1]:
                        for m in read.finditer(near):
                            found.setdefault(m.group(1) or m.group(2), rel)
        # SCHEMATIC_PLUGIN is in the key through the plugin's state (panel_stamps.plugin_state)
        missing = {k: v for k, v in found.items() if k not in cs.KEY_ENV and k != "SCHEMATIC_PLUGIN"}
        self.assertEqual(missing, {})
        self.assertIn("CHECK_AUDIT", found, "the scan no longer sees test_check_stamps' own skip")

    def test_the_cache_folder_and_the_jmri_guard_are_in_the_key(self) -> None:
        """HART_CACHE_DIR picks the cache folders a job reads (the trace leaves .cache paths out), and
        HART_GUARD_JMRI_RUNNING forces the answer the table writers and their tests refuse or skip on: a job run with
        either changed must run again, whatever it read."""
        self.assertIn("HART_CACHE_DIR", cs.KEY_ENV)
        self.assertIn("HART_GUARD_JMRI_RUNNING", cs.KEY_ENV)
        ck = cs.Checker(Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()))
        for var, value in (("HART_CACHE_DIR", "/elsewhere/cache"), ("HART_GUARD_JMRI_RUNNING", "1"),
                           ("HART_GUARD_JMRI_RUNNING", "0")):
            with self.subTest(var=var, value=value):
                env = {k: v for k, v in os.environ.items() if k not in ("HART_CACHE_DIR", "HART_GUARD_JMRI_RUNNING")}
                with unittest.mock.patch.dict(os.environ, env, clear=True):
                    base = cs.outside_state("unit-mimic", ck)
                    with unittest.mock.patch.dict(os.environ, {var: value}):
                        self.assertNotEqual(cs.outside_state("unit-mimic", ck), base)
                        self.assertIn(f"{var}={value}", cs.outside_state("unit-mimic", ck))

    def test_the_environment_and_the_user_are_in_the_key(self) -> None:
        ck = cs.Checker(Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()))
        base = cs.outside_state("unit-mimic", ck)
        self.assertRegex(base, r"(?m)^euid=\d+$")
        with unittest.mock.patch.dict(os.environ, {"CHECK_AUDIT": "/x"}):
            self.assertNotEqual(cs.outside_state("unit-mimic", ck), base)


class StoreTest(unittest.TestCase):
    def test_default_store_is_in_the_main_checkout_and_git_ignored(self) -> None:
        main = cs.main_checkout()
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(main.resolve(), Path(common).parent.resolve())
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHECK_STAMPS_DIR", None)
            os.environ.pop("HART_CACHE_DIR", None)
            import importlib
            fresh = importlib.reload(cs)
            self.addCleanup(importlib.reload, cs)
            self.assertEqual(fresh.STORE, main / ".cache" / "hart" / "check-stamps")
        ignored = subprocess.run(["git", "check-ignore", "-q", ".cache/hart/check-stamps/x.sha256"], cwd=REPO)
        self.assertEqual(ignored.returncode, 0, "the stamp folder is not git-ignored")


class SkipStampTest(RepoCase):
    """A unit job whose tests skipped records its stamp with the skipped tests' ids and reasons in its key; what they
    skipped on (here a tool shutil.which does not find) is an input like any read file."""

    TESTS = ("import shutil, unittest\n"
             "TOOL = shutil.which('hart-no-such-tool')\n\n"
             "class S(unittest.TestCase):\n"
             "    @unittest.skipUnless(TOOL, 'no hart-no-such-tool')\n"
             "    def test_needs_the_tool(self):\n"
             "        pass\n\n"
             "    def test_plain(self):\n"
             "        open('tools/x/tests/test_a.py').read()\n")

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        patch = unittest.mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"})
        patch.start()
        self.addCleanup(patch.stop)
        (self.root / "tools/x/tests/test_s.py").write_text(self.TESTS)

    def run_tests(self) -> tuple[Path, str]:
        log = self.tmp / "trace.log"
        log.write_text("0\tb\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=cs.traced.HOOK_DIR)
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-b", "-q", "-s", "tools/x/tests",
                               "-p", "test_s.py"], cwd=self.root, env=env, capture_output=True, text=True, check=True)
        return log, done.stderr

    def test_a_job_with_a_skipped_test_records_and_reruns_when_the_tool_appears(self) -> None:
        log, out = self.run_tests()
        self.assertIn("OK (skipped=1)", out)
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        stamp = cs.traced.load(cs._file("unit-guards test_s", self.store))
        self.assertEqual(stamp["skips"], [["test_s.S.test_needs_the_tool", "no hart-no-such-tool"]])
        self.assertTrue(self.current("unit-guards test_s"))
        (self.bin / "hart-no-such-tool").write_text("#!/bin/sh\n")
        (self.bin / "hart-no-such-tool").chmod(0o755)
        self.assertIn("hart-no-such-tool", cs.why_not_current("unit-guards test_s", self.root, self.store))

    def test_an_edit_still_reruns_it(self) -> None:
        log, _ = self.run_tests()
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.assertFalse(self.current("unit-guards test_s"))

    def test_the_key_holds_which_tests_skipped_and_why(self) -> None:
        log, _ = self.run_tests()
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        path = cs._file("unit-guards test_s", self.store)
        good = cs.traced.load(path)
        for skips in ([["test_s.S.test_needs_the_tool", "another reason"]],
                      [["test_s.S.test_plain", "no hart-no-such-tool"]],
                      [*good["skips"], ["test_s.S.test_plain", "no hart-no-such-tool"]]):
            with self.subTest(skips=skips):
                cs.traced.save(path, {**good, "skips": skips})
                self.assertIn("the code, command", cs.why_not_current("unit-guards test_s", self.root, self.store))
        ck = cs.Checker(self.root, self.store)
        self.assertEqual(cs.key("unit-mimic", ck, [], []), cs.key("unit-mimic", ck, [], [], skips=[]),
                         "a job with no skips keeps the key it had")

    def test_fewer_skips_in_the_trace_than_the_output_shows_records_nothing(self) -> None:
        log, _ = self.run_tests()
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        reason = cs.record("unit-guards test_s", log, self.root, self.store, skipped=2)
        self.assertIn("the output shows 2 skipped tests and the trace holds 1", reason)
        self.assertFalse(self.current("unit-guards test_s"), "the old stamp is dropped")


class GitRefsTest(RepoCase):
    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=self.root,
                       check=True, capture_output=True)

    def test_the_redeploy_job_reruns_when_head_moves(self) -> None:
        """test_redeploy_commit's deploy script (bash) stages HEAD and checks origin/main, which no trace sees."""
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        name = "unit-hosts test_redeploy_commit"
        ck = cs.Checker(self.root, self.store)
        state = cs.outside_state(name, ck)
        for ref in ("head=", "base=", "origin="):
            self.assertRegex(state, f"(?m)^{ref}")
        self.assertNotRegex(cs.outside_state("a", ck), "(?m)^origin=")
        self.assertNotRegex(cs.outside_state("unit-mimic", ck), "(?m)^(head|base|origin)=")
        self.assertIsNone(self.record(name))
        self.assertTrue(self.current(name))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertFalse(self.current(name))

    def test_a_manifest_job_holds_the_refs_its_git_field_names(self) -> None:
        """A read-only check whose entry names head reruns after a commit that changes nothing it read; one whose entry
        says [] (its trace replays every git read it makes) stays current; a unit job's REFS_OF is not consulted."""
        unstamp = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        unstamp.start()
        self.addCleanup(unstamp.stop)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        ck = cs.Checker(self.root, self.store)
        self.assertRegex(cs.outside_state("a", ck), "(?m)^head=[0-9a-f]{40}\nbase=")
        self.assertNotRegex(cs.outside_state("b", ck), "(?m)^(head|base|origin)=")
        for name in ("a", "b"):
            self.assertIsNone(self.record(name))
            self.assertTrue(self.current(name))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertFalse(self.current("a"), "HEAD moved: a's key holds it")
        self.assertTrue(self.current("b"), "b names no ref and read nothing that changed")
        self.assertIn("the code, command", cs.why_not_current("a", self.root, self.store))

    def test_a_git_command_a_check_ran_is_replayed_without_head_in_its_key(self) -> None:
        """What lets a check drop HEAD: a read-only git command its trace holds is run again at compare time, so a
        commit that changes its answer reruns the check, and one that does not leaves it current."""
        unstamp = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        unstamp.start()
        self.addCleanup(unstamp.stop)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        code = "import subprocess\nsubprocess.run(['git', 'ls-files', 'tools'], check=True, capture_output=True)\n"
        self.assertIsNone(self.record("b", code=code))
        stamp = cs.traced.load(cs._file("b", self.store))
        self.assertEqual((stamp["programs"], [c[1:] for c in stamp["git"]]), ([], [["git", "ls-files", "tools"]]))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertTrue(self.current("b"), "the same answer: b reads nothing that changed")
        (self.root / "tools/new.txt").write_text("n\n")
        self.git("add", "tools/new.txt")
        self.assertFalse(self.current("b"), "git ls-files answers otherwise now")

    def test_the_deploy_stage_job_reruns_when_an_edit_in_the_tree_is_committed(self) -> None:
        """test_deploy_stage stages a git clone of HEAD (its setUpClass), not the working tree its read set hashes."""
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        name = "unit-hosts test_deploy_stage"
        ck = cs.Checker(self.root, self.store)
        self.assertRegex(cs.outside_state(name, ck), "(?m)^head=[0-9a-f]{40}$")
        self.assertNotRegex(cs.outside_state(name, ck), "(?m)^(base|origin)=")
        (self.root / "tools/edit.txt").write_text("in the tree, not yet committed\n")
        self.assertIsNone(self.record(name, code="open('tools/edit.txt').read()\n"))
        self.assertTrue(self.current(name))
        status = ["git", "status", "--porcelain", "tools/edit.txt"]
        self.assertEqual(subprocess.run(status, cwd=self.root, capture_output=True, text=True).stdout,
                         "?? tools/edit.txt\n", "the job read an edit that is in the tree, not in HEAD")
        self.git("add", "tools/edit.txt")
        self.git("commit", "-q", "-m", "two")
        self.assertEqual(subprocess.run(status, cwd=self.root, capture_output=True, text=True).stdout, "")
        self.assertFalse(self.current(name), "the commit changed nothing in the tree, but HEAD moved")


class ManifestKeyTest(RepoCase):
    """A manifest job's key holds its own entries (tools/pipeline/checks.toml): an edit to one entry reruns that job
    and no other, and a manifest that cannot be read leaves the job to run and record nothing."""
    JOBS = ("a", "b", "public-text", "ruff", "portal", "unit-hartlib", "unit-guards test_x")

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def keys(self) -> dict[str, str]:
        ck = cs.Checker(self.root, self.store)
        return {name: cs.key(name, ck, [], []) for name in self.JOBS}

    def edit(self, old: str, new: str) -> None:
        path = self.root / cs.MANIFEST
        text = path.read_text()
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new))

    def rerun_after(self, old: str, new: str) -> list[str]:
        before = self.keys()
        self.edit(old, new)
        after = self.keys()
        return [name for name in self.JOBS if before[name] != after[name]]

    def test_an_edited_cmd_reruns_its_own_job_only(self) -> None:
        self.assertEqual(self.rerun_after('"tools/ruff.py"]', '"tools/ruff.py", "--fix"]'), ["ruff"])
        self.assertEqual(self.rerun_after('"tools/b.py"]', '"tools/b.py", "--check"]'), ["b"])
        self.assertEqual(self.rerun_after('"tools/portal.py"]', '"tools/portal2.py"]'), ["portal"])

    def test_a_step_added_to_the_static_group_reruns_no_other_job(self) -> None:
        self.assertEqual(self.rerun_after('[[step]]\nname = "public-text"',
                                          '[[step]]\nname = "c"\nrunner = "check"\ngroup = "static"\n'
                                          'cmd = ["python3", "tools/c.py"]\ngit = []\n[[step]]\nname = "public-text"'),
                         [])

    def test_an_edited_git_field_reruns_its_own_job_only(self) -> None:
        self.assertEqual(self.rerun_after('cmd = ["python3", "tools/b.py"]\ngit = []',
                                          'cmd = ["python3", "tools/b.py"]\ngit = ["origin"]'), ["b"])

    def test_a_git_field_the_key_cannot_use_is_an_error_not_a_skip(self) -> None:
        self.edit('cmd = ["python3", "tools/b.py"]\ngit = []', 'cmd = ["python3", "tools/b.py"]\ngit = ["tip"]')
        with self.assertRaisesRegex(cs.pm.ManifestError, "step 'b': git: 'tip': not a ref name"):
            cs.outside_state("a", cs.Checker(self.root, self.store))

    def test_a_comment_reruns_nothing(self) -> None:
        self.assertEqual(self.rerun_after('[[step]]\nname = "a"', '# why a\n[[step]]\nname = "a"'), [])

    def test_check_sh_and_the_loader_rerun_every_job(self) -> None:
        before = self.keys()
        for rel in ("tools/check.sh", *cs.pm.FILES):     # FILES: manifest.py and its parts (test_stamp_gate counts them)
            (self.root / rel).write_text("edited\n")
            after = self.keys()
            self.assertEqual([n for n in self.JOBS if before[n] == after[n]], [], rel)
            before = after

    def test_the_stamp_follows_the_entry(self) -> None:
        self.assertIsNone(self.record("ruff"))
        self.assertIsNone(self.record("public-text"))
        self.assertTrue(self.current("ruff"))
        self.edit('"tools/ruff.py"]', '"tools/ruff.py", "--fix"]')
        self.assertFalse(self.current("ruff"))
        self.assertTrue(self.current("public-text"))
        self.assertIn("the code, command", cs.why_not_current("ruff", self.root, self.store))

    def test_an_entry_edited_while_the_job_ran_records_nothing(self) -> None:
        before = cs.snapshot("ruff", self.root, self.store)
        log = self.run_job()
        self.edit('"tools/ruff.py"]', '"tools/ruff.py", "--fix"]')
        self.assertIn("tools/pipeline/checks.toml changed while the job ran",
                      cs.record("ruff", log, self.root, self.store, before=before))

    def test_a_manifest_that_cannot_be_read_or_lacks_the_job_is_an_error_not_a_skip(self) -> None:
        ck = cs.Checker(self.root, self.store)
        self.assertNotIn("manifest=", cs.outside_state("unit-hartlib", ck))
        self.edit('name = "ruff"', 'name = "ruff2"')
        with self.assertRaisesRegex(cs.pm.ManifestError, "has no job 'ruff'"):
            cs.outside_state("ruff", cs.Checker(self.root, self.store))
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        with self.assertRaisesRegex(cs.pm.ManifestError, "not valid TOML"):
            cs.outside_state("a", cs.Checker(self.root, self.store))
        # a unit job does not read the manifest
        self.assertNotIn("manifest=", cs.outside_state("unit-hartlib", cs.Checker(self.root, self.store)))

    def test_the_batch_runs_a_job_whose_key_cannot_be_made_and_records_nothing(self) -> None:
        out = self.tmp / "batch"
        out.mkdir()
        (self.root / cs.MANIFEST).unlink()
        self.assertEqual(cs.current_batch(["ruff", "unit-hartlib"], out, why=False, root=self.root, store=self.store),
                         [2, 1])
        self.assertIn("checks.toml: cannot read it", (out / "0.stamplog").read_text())

    def test_the_command_line_says_so_without_a_traceback(self) -> None:
        self.assertIsNone(self.record("a"))                # a stamp, so `why` works out the key
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        err = io.StringIO()
        real = cs.Checker
        with unittest.mock.patch.object(cs, "Checker", lambda *a, **k: real(self.root, self.store)), \
                contextlib.redirect_stderr(err):
            rc = cs.main(["why", "a"])
        self.assertEqual(rc, 2)
        self.assertIn("check_stamps.py: not stamped:", err.getvalue())
        self.assertIn("not valid TOML", err.getvalue())


if __name__ == "__main__":
    unittest.main()
