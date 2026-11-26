"""check_stamps: record and current on a fake repo: a job is current after a pass until a file it read, its
declaration (after an untraceable program) or the state outside the repo changes, and a run that cannot be
trusted records nothing."""
from __future__ import annotations

import os
import sys
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402
from stamps_case import RepoCase  # noqa: E402


class StampTest(RepoCase):
    def test_hit_after_record_and_miss_after_a_file_it_read_changes(self) -> None:
        self.assertFalse(self.current())
        self.assertIsNone(self.record())
        self.assertTrue(self.current())
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.assertFalse(self.current())

    def test_a_data_file_the_job_did_not_read_is_no_input(self) -> None:
        self.record()
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.assertTrue(self.current())

    def test_check_sh_is_an_input(self) -> None:
        self.record()
        (self.root / "tools/check.sh").write_text("v2\n")
        self.assertFalse(self.current())

    def test_an_untraceable_program_falls_back_to_the_declaration(self) -> None:
        code = self.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n"
        self.assertIsNone(self.record(code=code))
        self.assertTrue(self.current())
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.assertFalse(self.current(), "a declared file the shell may have read")
        self.record(code=code)
        (self.root / "www/index.html").write_text("v2\n")
        self.assertTrue(self.current(), "outside unit-hartlib's declaration")

    def test_another_worktree_inside_the_checkout_is_not_an_input(self) -> None:
        self.record("a", code=self.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n")
        (self.root / ".claude/worktrees/other/tools/y.py").write_text("v2\n")
        self.assertTrue(self.current("a"))

    def test_the_private_plan_and_the_interpreter_packages_are_inputs(self) -> None:
        plan = self.tmp / "plan.any"
        plan.write_text("p1\n")
        with unittest.mock.patch.dict(os.environ, {"ANYRAIL_PLAN": str(plan)}):
            self.record("a")
            self.assertTrue(self.current("a"))
            plan.write_text("p2\n")
            self.assertFalse(self.current("a"))
            self.record("a")
            with unittest.mock.patch.object(cs.stamps_cache, "venv_state", return_value="other interpreter"):
                self.assertFalse(self.current("a"))

    def test_a_stamp_helper_answer_other_than_0_or_1_is_not_a_skip(self) -> None:
        self.assertEqual(cs.main(["current", "no such job"]), 2)

    def test_the_hops_venv_is_an_input_of_its_jobs(self) -> None:
        hops = self.root / "ops/hart-ops/.venv/bin"
        hops.mkdir(parents=True)
        (hops / "python").write_text("")
        site = self.root / "ops/hart-ops/.venv/lib/python3.13/site-packages/numpy-1.0.dist-info"
        site.mkdir(parents=True)
        self.record("unit-hart-ops")
        self.assertTrue(self.current("unit-hart-ops"))
        site.rename(site.with_name("numpy-2.0.dist-info"))
        self.assertFalse(self.current("unit-hart-ops"))

    def test_the_job_name_is_in_the_stamp(self) -> None:
        self.record("unit-hartlib")
        stamp = cs.traced.load(cs._file("unit-hartlib", self.store))
        cs.traced.save(cs._file("unit-mimic", self.store), stamp)
        self.assertFalse(self.current("unit-mimic"))

    def test_the_file_hash_cache_follows_a_change_of_size(self) -> None:
        self.record()
        (self.root / "tools/x/tests/test_a.py").write_text("v1\nand more\n")
        self.assertFalse(self.current())

    def test_outside_state_that_changed_while_the_job_ran_records_nothing(self) -> None:
        plan = self.tmp / "plan.any"
        plan.write_text("p1\n")
        with unittest.mock.patch.dict(os.environ, {"ANYRAIL_PLAN": str(plan)}):
            before = cs.snapshot("a", self.root, self.store)
            log = self.run_job()
            plan.write_text("p2\n")             # the job saw p1; the key worked out now would hold p2
            self.assertIn("changed while the job ran", cs.record("a", log, self.root, self.store, before=before))
            self.assertFalse(self.current("a"))

    def test_a_job_that_is_one_bash_program_records_on_its_declaration(self) -> None:
        """check.sh's panels job: bash alone, with no Python process in its trace. It records, keyed on every file,
        so any edit reruns it (in the one static job, the other checks' processes carried such a trace)."""
        log = self.tmp / "bash.log"
        log.write_text(f"0\tt\t{time.time_ns()}\n0\tx\tcheck.sh-run\t{self.root}\tbash\ttools/b.sh\t--check\n")
        self.assertIsNone(cs.record("a", log, self.root, self.store))
        self.assertTrue(self.current("a"))
        (self.root / "docs/a.md").write_text("edited while it ran\n")
        self.assertIn("docs/a.md changed while the job ran", cs.record("a", log, self.root, self.store))
        log.write_text(f"0\tt\t{time.time_ns()}\n0\tx\tcheck.sh-run\t{self.root}\tbash\ttools/b.sh\t--check\n")
        self.assertIsNone(cs.record("a", log, self.root, self.store))
        self.assertTrue(self.current("a"))
        self.assertEqual(cs.traced.load(cs._file("a", self.store))["programs"], ["bash"])
        (self.root / "docs/a.md").write_text("v2\n")
        self.assertFalse(self.current("a"))

    def test_a_short_trace_records_nothing_and_drops_the_old_stamp(self) -> None:
        self.record()
        log = self.tmp / "short.log"
        log.write_text("0\tb\n")
        self.assertIn("did not load", cs.record("unit-hartlib", log, self.root, self.store))
        self.assertFalse(self.current())


class RootListingTest(RepoCase):
    def test_a_root_name_added_after_a_pass_reruns_a_job_that_listed_the_root(self) -> None:
        """What check.sh's .cache line prevents, and the stamps' answer without it: the job reruns, never skips."""
        self.assertIsNone(self.record(code="import os\nos.listdir('.')\n"))
        self.assertTrue(self.current())
        (self.root / ".cache").mkdir()
        self.assertFalse(self.current())


if __name__ == "__main__":
    unittest.main()
