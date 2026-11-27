"""G0c of the deploy gate (tools/hosts/deploy/gate.sh, ci_pass.py --main-red): a deploy or dry run to a host stops
before any ssh when main's push run of check.yml for the commit finished red; every other case does not block.

The harness is test_deploy_gates.GateHarness: sync_hart_package.sh runs on this checkout with ssh, scp, rsync to a host
and tar as recorders, and gh is a stand-in, so nothing reaches a host or GitHub and nothing publishes MQTT. The
ci_pass.py decision itself is tested in test_ci_pass.py (MainRedTest).
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_gates import GateHarness  # noqa: E402
from test_deploy_preflight import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "tools/hosts/deploy"))
from ci_pass import NOT_BLOCKING  # noqa: E402


class OffHostRunsDoNotAskForG4(GateHarness):
    """G4's CI pass (ci_pass.py --commit) is asked only on a real deploy to a host; the python3 stand-in logs it."""

    def test_dry_staging_and_mac_only_runs_do_not_ask_ci(self) -> None:
        """None of them asks for G4's CI pass. A dry run to a host asks only G0c's one question (is main red)."""
        for marker in ("ci_pass_skip", "tables_stale"):
            (self.tmp / marker).touch()
        for flags in (("--pi", "--win", "--dry-run"), ("--pi", "--win", "--stage-only", str(self.tmp / "stage")), ()):
            with self.subTest(flags=flags):
                (self.tmp / "gh.log").unlink(missing_ok=True)
                done = self.deploy(*flags)
                self.assertIn("ran G4: a dry run, a staging run or the Mac alone does not ask CI", done.stdout)
                self.assertIn("STOP: tables.xml is not what", done.stderr)
                self.assertFalse((self.tmp / "ci_pass.log").exists())
                asked = (self.tmp / "gh.log").read_text().splitlines() if (self.tmp / "gh.log").exists() else []
                if "--dry-run" in flags:
                    self.assertEqual(1, len(asked), asked)
                    self.assertIn("/actions/workflows/check.yml/runs", asked[0])
                else:
                    self.assertEqual([], asked)


class MainRedStopsTheDeploy(GateHarness):
    """G0c (gate.sh, ci_pass.py --main-red): a deploy or dry run to a host stops before any ssh when the commit's push
    run of check.yml on main finished failure, cancelled or timed_out. The real ci_pass.py runs against a gh stand-in
    that answers the runs list from runs.json and fails every other call, so G4 still runs (its CI pass is
    unreadable); a stale tables.xml (tables_stale) marks a run that got past G0c to G4."""

    URL = "https://github.com/lnevo/hart/actions/runs/999"

    def setUp(self) -> None:
        super().setUp()
        self.sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                                  check=True).stdout.strip()
        gh = self.tmp / "bin/gh"
        gh.write_text(f"""#!/bin/bash
echo "gh $*" >>"{self.tmp}/gh.log"
for a in "$@"; do
  if [[ "$a" == repos/*/actions/workflows/check.yml/runs && -f "{self.tmp}/runs.json" ]]; then
    cat "{self.tmp}/runs.json"; exit 0
  fi
done
echo "stand-in: no GitHub in the tests" >&2
exit 4
""", encoding="utf-8")
        gh.chmod(0o755)

    def main_run(self, status: str = "completed", conclusion: str | None = "success") -> None:
        run = {"id": 999, "run_number": 9, "head_sha": self.sha, "head_branch": "main", "event": "push",
               "path": ".github/workflows/check.yml", "status": status, "conclusion": conclusion,
               "html_url": self.URL}
        (self.tmp / "runs.json").write_text(json.dumps({"total_count": 1, "workflow_runs": [run]}), encoding="utf-8")

    def assert_red_stop(self, done: subprocess.CompletedProcess, conclusion: str) -> None:
        self.assertIn(f"STOP: main is red: the push run of .github/workflows/check.yml on main for {self.sha[:12]} "
                      f"ended {conclusion} ({self.URL}). Fix forward or revert first", done.stderr)
        self.assert_nothing_shipped(done)
        self.assertEqual([], self.calls(), "a host was asked after main was red")
        self.assertFalse((self.tmp / "tables_check.log").exists(), "the gate went on past a red main")

    def test_a_red_run_stops_a_deploy_before_any_ssh(self) -> None:
        self.hosts_ok()
        for conclusion in ("failure", "cancelled", "timed_out"):
            for flags in (("--pi", "--win"), ("--pi",), ("--win",)):
                with self.subTest(conclusion=conclusion, flags=flags):
                    self.main_run(conclusion=conclusion)
                    self.assert_red_stop(self.deploy(*flags), conclusion)

    def test_the_dry_run_refuses_a_red_main_and_passes_a_green_one(self) -> None:
        """The coordinator's proof: sync_hart_package.sh --pi --win --dry-run, with nothing sent anywhere."""
        self.main_run(conclusion="failure")
        self.assert_red_stop(self.deploy("--pi", "--win", "--dry-run"), "failure")
        self.main_run(conclusion="success")
        done = self.deploy("--pi", "--win", "--dry-run")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertIn(f"main red check: main's push run for {self.sha[:12]} passed ({self.URL})", done.stdout)
        self.assertNotIn("main is red", done.stderr)
        self.assertEqual([], [c for c in self.calls() if c.startswith(("ssh ", "scp "))], self.calls())
        self.assertFalse(self.mac_installed())

    def test_a_green_run_goes_on_to_the_other_gates(self) -> None:
        (self.tmp / "tables_stale").touch()
        self.main_run(conclusion="success")
        done = self.deploy("--pi", "--win")
        self.assertIn(f"passed ({self.URL})", done.stdout)
        self.assertIn("ran G4: ", done.stdout)
        self.assertIn("STOP: tables.xml is not what", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_run_still_going_is_not_waited_for(self) -> None:
        """Pending: the gate neither waits nor stops, as it treats a pending run today (G4 runs, no skip)."""
        (self.tmp / "tables_stale").touch()
        for status in ("in_progress", "queued"):
            with self.subTest(status=status):
                self.main_run(status=status, conclusion=None)
                done = self.deploy("--pi", "--win")
                self.assertIn(f"is {status} ({self.URL}); not waiting for it, {NOT_BLOCKING}", done.stdout)
                self.assertIn("ran G4: no CI pass", done.stdout)
                self.assertIn("STOP: tables.xml is not what", done.stderr)
                self.assertNotIn("main is red", done.stderr)

    def test_every_other_case_runs_g4_as_before(self) -> None:
        """No run yet and a gh error do not block; the line says which."""
        (self.tmp / "tables_stale").touch()
        cases = {
            "no run yet": ({"total_count": 0, "workflow_runs": []},
                           f"main red check: no push run of check.yml on main for {self.sha[:12]} yet; {NOT_BLOCKING}"),
            "another ending": (None, f"ended startup_failure ({self.URL}), not failure, cancelled, timed_out; "
                                     f"{NOT_BLOCKING}"),
            "gh fails": ("", "main red check: could not ask GitHub (gh api -X failed (exit 4): stand-in: no GitHub in "
                             f"the tests); {NOT_BLOCKING}"),
        }
        for name, (reply, text) in cases.items():
            with self.subTest(case=name):
                (self.tmp / "runs.json").unlink(missing_ok=True)
                if reply is None:
                    self.main_run(conclusion="startup_failure")
                elif reply:
                    (self.tmp / "runs.json").write_text(json.dumps(reply), encoding="utf-8")
                done = self.deploy("--pi", "--win")
                self.assertIn(text, done.stdout)
                self.assertIn("ran G4: ", done.stdout)
                self.assertIn("STOP: tables.xml is not what", done.stderr)
                self.assertNotIn("main is red", done.stderr)
                self.assertNotIn("Traceback", done.stdout + done.stderr)

    def test_a_crash_of_the_check_does_not_block(self) -> None:
        """ci_pass.py --main-red that dies (an import error, exit 1) leaves the deploy going on to G4."""
        (self.tmp / "tables_stale").touch()
        self.main_run(conclusion="failure")
        crash = self.tmp / "bin3/python3"
        crash.parent.mkdir()
        crash.write_text(f"""#!/bin/bash
for a in "$@"; do
  if [[ "$a" == --main-red ]]; then echo "Traceback (stand-in): ImportError" >&2; exit 1; fi
done
exec "{self.tmp / 'bin2/python3'}" "$@"
""", encoding="utf-8")
        crash.chmod(0o755)
        self.env["PATH"] = f"{crash.parent}:{self.env['PATH']}"
        done = self.deploy("--pi", "--win")
        self.assertIn("Traceback (stand-in): ImportError", done.stderr)
        self.assertNotIn("main is red", done.stderr)
        self.assertIn("ran G4: ", done.stdout)
        self.assertIn("STOP: tables.xml is not what", done.stderr)

    def test_check_only_staging_and_the_mac_alone_do_not_ask(self) -> None:
        self.main_run(conclusion="failure")
        self.hosts_ok()
        for flags in (("--pi", "--win", "--check-only"), ("--pi", "--win", "--stage-only", str(self.tmp / "stage")), ()):
            with self.subTest(flags=flags):
                done = self.deploy(*flags)
                self.assertEqual(0, done.returncode, done.stderr[-2000:])
                self.assertNotIn("main is red", done.stderr)
                self.assertFalse((self.tmp / "gh.log").exists())


if __name__ == "__main__":
    unittest.main()
