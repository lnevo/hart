"""check_stamps: the local stamps that let tools/check.sh skip a job whose inputs are what its last pass saw, and the
audit that pins every job's declared inputs (the unit-test jobs, a quick sample of them here)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_stamps as cs  # noqa: E402

REPO = cs.ROOT
CHECK_SH = (REPO / "tools" / "check.sh").read_text(encoding="utf-8")
# Jobs the audit runs for real: quick ones, one of each kind of folder a job tests.
AUDITED = (r"^(unit-hartlib|unit-mimic|unit-anyrail|unit-cats|unit-jmri-scripts"
           r"|unit-guards test_turnout_startup|unit-hosts test_load_env|unit-jmri test_speedmatch_distance)$")


class DeclarationTest(unittest.TestCase):
    def test_every_job_kind_in_check_sh_is_declared(self) -> None:
        kinds = {m.group(1) for m in re.finditer(r"^\s*(?:unit|later)\s+\"?(unit-[a-z-]+|public-text|portal|static)\b",
                                                 CHECK_SH, re.M)}
        kinds |= {"unit-jmri", "unit-hosts", "unit-guards"}     # their names are built in a loop
        self.assertTrue(kinds)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):
                self.assertIsNotNone(cs.declared(kind), f"{kind} has no declaration in check_stamps.BY_KIND")

    def test_a_placeholder_job_is_not_stampable(self) -> None:
        self.assertIsNone(cs.declared("unit-hart-ops skipped (no ops/hart-ops/.venv)"))
        self.assertIsNone(cs.declared("portal skipped in CI"))

    def test_check_sh_is_an_input_of_every_job(self) -> None:
        for kind in cs.BY_KIND:
            self.assertIn("tools/check.sh", cs.declared(kind))


class StampTest(unittest.TestCase):
    """A fake repo with a store of its own."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.store = self.tmp / "repo", self.tmp / "store"
        for rel in ("tools/check.sh", "tools/x/tests/test_a.py", "jmri/layouts/hart/data/switches.csv",
                    "www/index.html", "docs/a.md", ".claude/worktrees/other/tools/y.py"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("v1\n")
        patch = unittest.mock.patch.object(cs.ps, "plugin_state", return_value="plugin")
        patch.start()
        self.addCleanup(patch.stop)

    def stamp(self, name: str) -> str:
        return cs.stamp(name, self.root, self.store)

    def test_hit_after_record_and_miss_after_an_input_changes(self) -> None:
        ok, s = cs.is_current("unit-hartlib", self.root, self.store)
        self.assertFalse(ok)
        cs.record("unit-hartlib", s, self.store)
        self.assertTrue(cs.is_current("unit-hartlib", self.root, self.store)[0])
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.assertFalse(cs.is_current("unit-hartlib", self.root, self.store)[0])

    def test_data_and_check_sh_are_inputs(self) -> None:
        before = self.stamp("unit-hartlib")
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.assertNotEqual(self.stamp("unit-hartlib"), before)
        before = self.stamp("unit-hartlib")
        (self.root / "tools/check.sh").write_text("v2\n")
        self.assertNotEqual(self.stamp("unit-hartlib"), before)

    def test_a_site_file_is_not_an_input_of_a_tools_job(self) -> None:
        tools, site = self.stamp("unit-hartlib"), self.stamp("unit-portal")
        (self.root / "www/index.html").write_text("v2\n")
        self.assertEqual(self.stamp("unit-hartlib"), tools)
        self.assertNotEqual(self.stamp("unit-portal"), site)

    def test_another_worktree_inside_the_checkout_is_not_an_input(self) -> None:
        before = self.stamp("static")
        (self.root / ".claude/worktrees/other/tools/y.py").write_text("v2\n")
        self.assertEqual(self.stamp("static"), before)

    def test_the_command_name_and_the_job_are_in_the_stamp(self) -> None:
        self.assertNotEqual(self.stamp("unit-hartlib"), self.stamp("unit-mimic"))

    def test_the_file_hash_cache_follows_a_change_of_size(self) -> None:
        self.stamp("unit-hartlib")
        (self.root / "tools/x/tests/test_a.py").write_text("v1\nand more\n")
        ok, _ = cs.is_current("unit-hartlib", self.root, self.store)
        self.assertFalse(ok)


class AuditTest(unittest.TestCase):
    """Runs check.sh for the quick jobs under CHECK_AUDIT and fails for any repo file or folder a job's Python
    processes touched that its declaration does not cover."""

    @unittest.skipIf(os.environ.get("CHECK_AUDIT"), "already inside an audit run")
    def test_the_declared_inputs_cover_what_the_jobs_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k not in ("HART_TABLES", "FULL")}
            env.update(CHECK_ONLY=AUDITED, CHECK_AUDIT=tmp)
            done = subprocess.run(["bash", str(REPO / "tools/check.sh")], cwd=REPO, env=env, capture_output=True,
                                  text=True, timeout=900)
            self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-2000:])
            jobs = cs.read_audit(Path(tmp))
            self.assertEqual(len(jobs), 8, sorted(jobs))
            for name, (files, dirs) in jobs.items():
                with self.subTest(job=name):
                    self.assertTrue(files, "the audit hook logged nothing")
                    self.assertEqual(cs.uncovered(name, files, dirs), [])


if __name__ == "__main__":
    unittest.main()
