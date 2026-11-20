"""A deploy asks every host named on the command line for an ssh answer before it changes anything.

Windows is kept matching the Pi and the Pi step runs first, so an unreachable Windows must stop
`--pi --win` before the Pi step. ssh and scp are stand-ins that log each call: a host listed in
down.txt refuses, the no-op and the Pi's read-only checks answer, and anything else (the first
real host step) fails with 99. Nothing reaches a host. HOME and TMPDIR are temporary folders, the
gate that rewrites tables.xml runs as a dry run (keep_repo_tables), and every test checks that the
checkout is as it was.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_stage import git, keep_repo_tables, stage_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
REDEPLOY = ROOT / "tools/hosts/redeploy_commit.sh"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
PI = "pi.example.invalid"
WIN = "win.example.invalid"
PI_DOWN = f"STOP: cannot reach the Pi ({PI}) over ssh."
WIN_DOWN = f"STOP: cannot reach Windows (nobody@{WIN} port 1) over ssh."
ANY_DOWN = "STOP: cannot reach"
NO_FILE = "No file was sent to or installed on any host, and the Mac install did not run."
UNPULLED_HINT = "could not check the Pi for unpulled changes"
RESTARTING = "Starting PanelPro on the Pi again (it was quit for this deploy)"
FAKE_SSH = r"""#!/bin/bash
echo "ssh $*" >>"@TMP@/network.log"
while read -r host; do
  [[ -n "$host" && " $* " == *"$host "* ]] && { echo "ssh: connect to host $host: refused" >&2; exit 255; }
done <"@TMP@/down.txt"
cmd="${@: -1}"
case "$cmd" in
  true|"exit 0") exit 0 ;;                       # the preflight no-op
  "bash -s -- '"*) cat >/dev/null; exit 0 ;;     # unpulled_changes.sh: nothing unpulled
  "bash -s") cat >/dev/null; cat "@TMP@/restart.txt"; exit 0 ;;  # panelpro_restart_due.sh
esac
exit 99
"""


class PreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = stage_env(self.tmp)
        keep_repo_tables(self.tmp)
        self.scratch = self.tmp / "scratch"
        self.scratch.mkdir()
        self.env.update(HOME=str(self.tmp / "home"), TMPDIR=str(self.scratch))
        (self.tmp / "bin/ssh").write_text(FAKE_SSH.replace("@TMP@", str(self.tmp)), encoding="utf-8")
        (self.tmp / "restart.txt").write_text("no\n", encoding="utf-8")
        self.down()
        # No test may change the checkout: the tables bytes and git's view of it stay as they were.
        before = (TABLES.read_bytes(), git("status", "--porcelain"))
        self.addCleanup(lambda: self.assertEqual(
            before, (TABLES.read_bytes(), git("status", "--porcelain")), "the deploy changed the checkout"))

    def down(self, *hosts: str) -> None:
        (self.tmp / "down.txt").write_text("".join(f"{h}\n" for h in hosts), encoding="utf-8")

    def calls(self) -> list[str]:
        log = self.tmp / "network.log"
        return log.read_text().splitlines() if log.exists() else []

    def pi_calls(self) -> list[str]:
        return [c.split(f"{PI} ", 1)[1] for c in self.calls() if f"{PI} " in c]

    def deploy(self, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SYNC), *flags], cwd=ROOT, env=self.env,
                              capture_output=True, text=True, timeout=600)

    def test_windows_down_stops_pi_and_win_before_any_pi_step(self) -> None:
        self.down(WIN)
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(WIN_DOWN, done.stderr)
        self.assertIn(NO_FILE, done.stderr)
        self.assertNotIn(PI_DOWN, done.stderr)
        self.assertNotIn("Deploy → Pi", done.stdout)
        # The Pi saw only the no-op and the restart check: no unpulled check, no file step.
        self.assertEqual(["true", "bash -s"], self.pi_calls(), self.calls())
        self.assertNotIn(RESTARTING, done.stdout)
        self.assertFalse((self.tmp / "home").exists(), "the Mac install ran")
        self.assertFalse((self.tmp / "gates.log").exists(), "the tables.xml gate ran")

    def test_stop_says_that_panelpro_quit_for_the_deploy_is_started_again(self) -> None:
        self.down(WIN)
        (self.tmp / "restart.txt").write_text("yes\n", encoding="utf-8")
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(NO_FILE, done.stderr)
        self.assertIn("The Pi answered: PanelPro there is started again if it was quit for this deploy",
                      done.stderr)
        self.assertIn(RESTARTING, done.stdout)
        # The no-op, the restart check, then pi_start_panelpro.sh's own ssh (which the stand-in fails).
        self.assertEqual(3, len(self.pi_calls()), self.calls())
        self.assertIn("PanelPro did not start on the Pi; run tools/hosts/pi_start_panelpro.sh", done.stderr)

    def test_pi_down_names_the_pi_not_the_unpulled_check(self) -> None:
        self.down(PI)
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(PI_DOWN, done.stderr)
        self.assertNotIn(WIN_DOWN, done.stderr)
        self.assertNotIn(UNPULLED_HINT, done.stderr)
        self.assertNotIn("HART_DISCARD_PI_CHANGES", done.stderr)
        self.assertNotIn("The Pi answered", done.stderr)
        # One no-op each, and no restart check on a Pi that does not answer.
        self.assertEqual(2, len(self.calls()), self.calls())

    def test_both_down_names_both_and_skips_the_restart_check(self) -> None:
        self.down(PI, WIN)
        done = self.deploy("--all")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(PI_DOWN, done.stderr)
        self.assertIn(WIN_DOWN, done.stderr)
        self.assertEqual(2, len(self.calls()), self.calls())

    def test_single_host_checks_only_that_host(self) -> None:
        self.down(PI, WIN)
        pi = self.deploy("--pi")
        self.assertEqual(1, pi.returncode, pi.stderr)
        self.assertIn(PI_DOWN, pi.stderr)
        self.assertNotIn(WIN_DOWN, pi.stderr)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertFalse(any(WIN in c for c in self.calls()), self.calls())
        (self.tmp / "network.log").unlink()
        win = self.deploy("--win")
        self.assertEqual(1, win.returncode, win.stderr)
        self.assertIn(WIN_DOWN, win.stderr)
        self.assertNotIn(PI_DOWN, win.stderr)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())

    def test_both_reachable_goes_on_to_the_pi_step(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertNotIn(ANY_DOWN, done.stderr)
        self.assertIn("Deploy → Pi", done.stdout)
        calls = self.calls()
        self.assertTrue(calls[0].endswith(f"{PI} true"), calls)
        self.assertTrue(calls[1].endswith(f"{WIN} exit 0"), calls)
        self.assertTrue(calls[2].endswith(f"{PI} bash -s -- '/srv/fake-pi/JMRI_UserFiles'"), calls)
        # The first real host step, which the stand-in fails.
        self.assertIn("mktemp -d /tmp/hart-deploy.XXXXXX", calls[3])
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        # The gate that rewrites tables.xml was reached, and ran as a dry run.
        self.assertEqual(1, len((self.tmp / "gates.log").read_text().splitlines()))

    def test_one_host_goes_on_while_the_other_is_down(self) -> None:
        self.down(PI)
        done = self.deploy("--win")
        self.assertNotIn(ANY_DOWN, done.stderr)
        self.assertIn("Deploy → Windows", done.stdout)
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())

    def test_windows_tarball_is_removed_on_every_way_out(self) -> None:
        # A real run that fails at the first Windows step, twice, then a dry run: the old template
        # (hart-pkg.XXXXXX.tgz) left its literal name behind and the second run failed at mktemp.
        for flags in (("--win",), ("--win",), ("--win", "--dry-run")):
            done = self.deploy(*flags)
            self.assertIn("Deploy → Windows", done.stdout)
            self.assertNotIn("mktemp:", done.stderr)
            self.assertEqual([], sorted(p.name for p in self.scratch.iterdir()), flags)
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertIn("dry-run: would scp", done.stdout)
        # The real runs got as far as asking Windows for a drop folder, after the tarball was made.
        self.assertEqual(2, sum("hart-deploy-" in c for c in self.calls()), self.calls())
        src = SYNC.read_text(encoding="utf-8")
        self.assertIn('mktemp "${TMPDIR:-/tmp}/hart-pkg.XXXXXX")', src)

    def test_dry_run_and_stage_only_skip_the_check(self) -> None:
        self.down(PI, WIN)
        done = self.deploy("--pi", "--win", "--stage-only", str(self.tmp / "stage"))
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual([], self.calls())
        done = self.deploy("--win", "--dry-run")
        self.assertNotIn(ANY_DOWN, done.stderr)
        self.assertEqual([], self.calls())

    def test_check_only_asks_the_hosts_named_and_stops_there(self) -> None:
        done = self.deploy("--check-only", "--win")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Host check: every host named answered over ssh.", done.stdout)
        self.assertNotIn("Pi check", done.stdout)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertTrue(self.calls()[0].endswith(f"{WIN} exit 0"), self.calls())
        self.down(WIN)
        done = self.deploy("--check-only", "--all")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(WIN_DOWN, done.stderr)

    def test_redeploy_checks_the_hosts_before_the_older_commits_deploy(self) -> None:
        self.down(WIN)
        for hosts in (("--pi", "--win"), ("--win",)):
            done = subprocess.run(["bash", str(REDEPLOY), "HEAD", "--allow-unmerged", *hosts], cwd=ROOT,
                                  env=self.env, capture_output=True, text=True, timeout=600)
            self.assertEqual(1, done.returncode, done.stderr)
            self.assertIn(WIN_DOWN, done.stderr)
            self.assertNotIn("temporary worktree", done.stdout)
        self.assertFalse(any("mktemp" in c or "powershell" in c for c in self.calls()), self.calls())


if __name__ == "__main__":
    unittest.main()
