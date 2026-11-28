"""tools/check.sh's choice of path on a scratch repo (the docs-only path, the light path, the full path and why), and
tools/ci/light_checks.sh on stand-in scripts. The verdict itself (tools/ci/changed_kind.py) is tested in
test_check_docs_only.py, whose scratch repo these use."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_docs_only import Scratch, git  # noqa: E402


class CheckSh(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Scratch(Path(self.tmp.name), with_check_sh=True)

    def test_a_docs_only_branch_takes_the_quick_path_and_says_so_first(self) -> None:
        self.s.write("wiki/decisions/ADR-1.md", "# ADR\n")
        done = self.s.check_sh(STUB_PIN="")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertTrue(lines[0].startswith("Docs-only change (1 changed path, all Markdown docs)"), lines[0])
        self.assertIn("STUB DOCS CHECKS HOPS_PY=python3", lines)
        # not a pass of check.sh: no "ALL PASSED", and no stamp written
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertEqual("DOCS CHECKS PASSED (the docs-only path; FULL=1 runs check.sh in full)", lines[-1])

    def test_a_light_verdict_runs_the_light_checks_and_their_exit_is_the_run_s(self) -> None:
        self.s.write("tools/ci/changed_kind.py", 'print("light: 1 changed path, a stand-in verdict")\n')
        self.s.write("tools/ci/light_checks.sh", 'echo "STUB LIGHT $* HOPS_PY=$HOPS_PY"\necho "LIGHT CHECKS PASSED"\n'
                                                 'exit "${STUB_LIGHT_RC:-0}"\n')
        done = self.s.check_sh(STUB_PIN="")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertTrue(lines[0].startswith("Light change (1 changed path, a stand-in verdict)"), lines[0])
        self.assertIn("STUB LIGHT --git HOPS_PY=python3", lines)
        self.assertEqual("LIGHT CHECKS PASSED", lines[-1])
        self.assertNotIn("ALL PASSED", done.stdout.replace("LIGHT CHECKS PASSED", ""))
        self.assertNotIn("STUB DOCS CHECKS", done.stdout)
        self.assertEqual(3, self.s.check_sh(STUB_PIN="", STUB_LIGHT_RC="3").returncode)
        stopped = self.s.check_sh()     # the plugin pin guard still stops it before any check
        self.assertEqual(2, stopped.returncode)
        self.assertNotIn("STUB LIGHT", stopped.stdout)

    def test_a_failed_docs_check_fails_the_run(self) -> None:
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh(STUB_PIN="", STUB_DOCS_RC="1")
        self.assertEqual(1, done.returncode)
        self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_the_docs_path_still_stops_on_a_wrong_plugin_pin(self) -> None:
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh()
        self.assertEqual(2, done.returncode)
        self.assertIn("STOP: stub: stopped before any job", done.stderr)
        self.assertNotIn("STUB DOCS CHECKS", done.stdout)

    def test_a_code_change_or_an_explicit_request_takes_the_full_path(self) -> None:
        self.s.write("tools/x.py", "x = 2\n")
        done = self.s.check_sh()
        self.assertEqual(2, done.returncode, done.stdout)   # the stub pin guard stops the full path before any job
        # the first line names the path that made it full, so a run that goes full says why
        self.assertEqual("Full checks: tools/x.py is code or configuration (.py) (tools/ci/changed_kind.py; "
                         "make pr-kind)\n", done.stdout)
        self.s.write("tools/x.py", "x = 1\n")
        self.s.write("wiki/a.md", "# A, edited\n")
        for env in ({"FULL": "1"}, {"CI": "true"}, {"CHECK_ONLY": "phase02"}, {"PORTAL_CHECK": "1"},
                    {"CHECK_AUDIT_FAILS": "1"}):
            with self.subTest(env):
                done = self.s.check_sh(**env)
                self.assertNotIn("Docs-only", done.stdout)
                self.assertNotIn("STUB DOCS CHECKS", done.stdout)
                self.assertIn("STOP: stub", done.stderr)

    def test_no_merge_base_takes_the_full_path_with_the_reason(self) -> None:
        git(self.s.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh()
        first = done.stdout.splitlines()[0]
        self.assertTrue(first.startswith("Full checks: cannot tell what changed, no merge base with origin/main"),
                        first)
        self.assertNotIn("STUB DOCS CHECKS", done.stdout)
        self.assertIn("STOP: stub", done.stderr)

    def test_a_crash_of_the_verdict_takes_the_full_path_and_says_so(self) -> None:
        self.s.write("tools/ci/changed_kind.py", "raise SystemExit('boom')\n")
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh()
        self.assertTrue(done.stdout.startswith("Full checks: tools/ci/changed_kind.py --git failed: boom"), done.stdout)
        self.assertIn("STOP: stub", done.stderr)


STUB_KIND = 'import os, sys\nif os.environ.get("STUB_JOBS") is None: sys.exit("not light")\nprint(os.environ["STUB_JOBS"])\n'
STUB_CHECK = '#!/usr/bin/env bash\necho "STUB CHECK.SH CHECK_ONLY=$CHECK_ONLY"\necho "$CHECK_PASS_LINE"\nexit "${STUB_CHECK_RC:-0}"\n'
STUB_DOCS = '#!/usr/bin/env bash\necho "STUB DOCS"\nexit "${STUB_DOCS_RC:-0}"\n'


class LightChecks(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel, text in (("tools/ci/light_checks.sh", (ROOT / "tools/ci/light_checks.sh").read_text()),
                          ("tools/ci/changed_kind.py", STUB_KIND), ("tools/check.sh", STUB_CHECK),
                          ("tools/ci/docs_checks.sh", STUB_DOCS)):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        (self.root / "tools/check.sh").chmod(0o755)

    def run_light(self, **env: str) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if not k.startswith(("STUB_", "CHECK_"))}
        return subprocess.run(["bash", str(self.root / "tools/ci/light_checks.sh"), "--git"], env={**base, **env},
                              capture_output=True, text=True, timeout=60)

    def test_runs_the_jobs_then_the_docs_checks_and_ends_light(self) -> None:
        done = self.run_light(STUB_JOBS="lint\npipeline-map")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertIn("STUB CHECK.SH CHECK_ONLY=^(lint|pipeline-map)$", lines)
        self.assertIn("--- light: check.sh's jobs passed", lines)
        self.assertIn("STUB DOCS", lines)
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertTrue(lines[-1].startswith("LIGHT CHECKS PASSED"), lines[-1])

    def test_a_failure_in_either_fails_after_both_ran(self) -> None:
        for env, named in (({"STUB_CHECK_RC": "1"}, "check.sh jobs"), ({"STUB_DOCS_RC": "1"}, "quick docs checks")):
            with self.subTest(named):
                done = self.run_light(STUB_JOBS="lint", **env)
                self.assertEqual(1, done.returncode)
                self.assertIn("STUB DOCS", done.stdout)
                self.assertIn(f"light checks FAILED: {named}", done.stdout)
                self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_no_job_list_stops_before_any_check(self) -> None:
        for env in ({}, {"STUB_JOBS": ""}):
            with self.subTest(env):
                done = self.run_light(**env)
                self.assertEqual(2, done.returncode)
                self.assertIn("STOP:", done.stdout)
                self.assertNotIn("STUB", done.stdout)


if __name__ == "__main__":
    unittest.main()
