"""tools/check.sh running what tools/pipeline/manifest.py lists, in a scratch repo with a stand-in manifest.py: a
manifest that fails or lists nothing stops it, each step is a job of its own, and check.sh's own conditions (the
panels jobs first, when the portal job runs) still apply.

Split out of test_pipeline_manifest.py on 2026-11-26 with no change in the tests, so each file stays under the size
limit (tools/audit/check_py_sizes.py). The scratch repo and the stand-in lines come from that file, which other tests
import them from too; docs_checks.sh and the guard on check.sh's own lines stay there, as they read the map.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

# its folder is on sys.path under discover
from test_pipeline_manifest import OWN, STATIC, STATIC_ONLY, scratch_check_sh


class CheckShTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = scratch_check_sh(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_check(self, **env: str) -> subprocess.CompletedProcess:
        base = {"STUB_PIN": "", "STUB_STATIC": STATIC, "STUB_OWN": OWN, "FULL": "1", "CHECK_ONLY": STATIC_ONLY}
        return self.s.check_sh(**{**base, **env})

    def assertStopped(self, done: subprocess.CompletedProcess, *said: str) -> None:
        self.assertEqual(2, done.returncode, done.stdout + done.stderr)
        for text in said:
            self.assertIn(text, done.stderr)
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertNotIn("ran ", done.stdout)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_manifest_that_fails_stops_the_run_before_any_job(self) -> None:
        self.assertStopped(self.run_check(STUB_MANIFEST_FAIL="1"), "manifest.py: stub manifest error",
                           "STOP: tools/pipeline/manifest.py jobs check --group static failed")

    def test_an_empty_list_stops_the_run(self) -> None:
        self.assertStopped(self.run_check(STUB_STATIC=""), "jobs check --group static listed no check")
        self.assertStopped(self.run_check(STUB_OWN="\n"), "jobs check --ungrouped listed no check")

    def test_a_line_that_is_not_a_step_stops_the_run(self) -> None:
        self.assertStopped(self.run_check(STUB_STATIC="Not a line\n"),
                           'printed "Not a line"')

    def test_the_steps_check_sh_adds_to_must_be_listed(self) -> None:
        self.assertStopped(self.run_check(STUB_STATIC=STATIC.replace("panels-tables python3", "pan python3")),
                           "no panels-tables job")
        self.assertStopped(self.run_check(STUB_OWN="solo python3 tools/a.py\n"), "no portal step")

    def test_each_static_line_is_a_job_of_its_own_panels_first_with_the_callers_pythonpath(self) -> None:
        done = self.run_check(PYTHONPATH="/caller")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        jobs = [line for line in done.stdout.splitlines() if line.startswith("--- ")]
        self.assertEqual([j.split(" (")[0] for j in jobs], ["--- panels-tables", "--- one", "--- two", "--- shell"])
        ran = [line for line in done.stdout.splitlines() if line.startswith("ran ")]
        self.assertEqual(ran, ["ran panels-tables PYTHONPATH=/caller", "ran --check PYTHONPATH=/caller",
                               "ran mod PYTHONPATH=lib/src:/caller", "ran shell --check"])
        self.assertEqual("ALL PASSED", done.stdout.splitlines()[-1])
        done = self.run_check(PYTHONPATH="")
        self.assertIn("ran mod PYTHONPATH=lib/src\n", done.stdout)

    def test_a_panels_job_runs_its_line_as_it_is_in_every_run(self) -> None:
        """Stage 6: no --full (that was build_panels.sh's); each panels job is a Python check like any other."""
        for env in ({"FULL": ""}, {"FULL": "1"}, {"CI": "true", "FULL": ""}):
            with self.subTest(env=env):
                done = self.run_check(**env)
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)
                self.assertRegex(done.stdout, r"(?m)^ran panels-tables PYTHONPATH=")
                self.assertNotIn("--full", done.stdout)

    def test_a_line_the_shell_cannot_parse_stops_the_run(self) -> None:
        for env in ({"STUB_STATIC": STATIC + "bad python3 'unclosed\n"}, {"STUB_OWN": "bad python3 'unclosed\n" + OWN}):
            with self.subTest(env=env):
                self.assertStopped(self.run_check(**env), "printed a line the shell cannot parse: bad python3 'unclosed")

    def test_a_failing_check_fails_its_own_job_and_the_run(self) -> None:
        done = self.run_check(STUB_STATIC=STATIC + "gone python3 tools/none.py\n")
        self.assertEqual(1, done.returncode)
        self.assertIn("--- gone FAILED", done.stdout)
        self.assertIn("--- one (", done.stdout)
        self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_a_check_of_another_program_is_refused_not_run(self) -> None:
        done = self.run_check(STUB_STATIC=STATIC + "odd node tools/a.py\n")
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- odd FAILED", done.stdout)
        self.assertIn("odd: check.sh's run_check takes python3, env VAR=... python3 or bash, not node; not run",
                      done.stdout)

    def test_the_results_file_names_each_job_and_its_result(self) -> None:
        """CHECK_RESULTS_TO: what tools/ci/stamp_gate.py's skip record and weekly guard read."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "results.tsv"
            done = self.run_check(STUB_STATIC=STATIC + "gone python3 tools/none.py\n", CHECK_RESULTS_TO=str(out))
            self.assertEqual(1, done.returncode)
            self.assertEqual(out.read_text(), "panels-tables\tpassed\none\tpassed\ntwo\tpassed\nshell\tpassed\ngone\tfailed\n")
            done = self.run_check(CHECK_ONLY="^nothing-by-this-name$", CHECK_RESULTS_TO=str(out))
            self.assertEqual(1, done.returncode)
            self.assertEqual(out.read_text(), "", "no job: an empty file, which the gate refuses, not a blank line")
            done = self.run_check(CHECK_RESULTS_TO=str(Path(d) / "no-such-folder" / "r.tsv"))
            self.assertEqual(2, done.returncode)
            self.assertIn("no-such-folder/r.tsv: cannot write it", done.stderr)
            self.assertNotIn("ran ", done.stdout)

    def test_no_job_to_run_is_no_pass(self) -> None:
        done = self.run_check(CHECK_ONLY="^nothing-by-this-name$")
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- no job to run: CHECK_ONLY=^nothing-by-this-name$ matches none", done.stdout)
        self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_steps_in_no_group_are_jobs_of_their_own_and_portal_keeps_its_conditions(self) -> None:
        done = self.run_check(CHECK_ONLY="^(solo|portal.*)$", PORTAL_CHECK="1")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- solo (", done.stdout)
        self.assertIn("ran solo PYTHONPATH=", done.stdout)
        self.assertIn("ran portal PYTHONPATH=", done.stdout)
        done = self.run_check(CHECK_ONLY="^portal", CI="true")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- portal skipped in CI (", done.stdout)
        self.assertNotIn("ran portal", done.stdout)


if __name__ == "__main__":
    unittest.main()
