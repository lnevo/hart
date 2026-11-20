"""A deploy asks every host named on the command line for an ssh answer before it changes anything.

Windows is kept matching the Pi and the Pi step runs first, so an unreachable Windows must stop
`--pi --win` before the Pi step. ssh and scp are stand-ins that log each call: a host listed in
down.txt refuses, the no-op and the Pi's read-only checks answer, and anything else (the first
real host step) fails with 99. Nothing reaches a host, and HOME is a temporary folder.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_stage import stage_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
PI = "pi.example.invalid"
WIN = "win.example.invalid"
FAKE_SSH = r"""#!/bin/bash
echo "ssh $*" >>"@TMP@/network.log"
while read -r host; do
  [[ -n "$host" && " $* " == *"$host "* ]] && { echo "ssh: connect to host $host: refused" >&2; exit 255; }
done <"@TMP@/down.txt"
cmd="${@: -1}"
case "$cmd" in
  true|"exit 0") exit 0 ;;                       # the preflight no-op
  "bash -s -- '"*) cat >/dev/null; exit 0 ;;     # unpulled_changes.sh: nothing unpulled
  "bash -s") cat >/dev/null; echo no; exit 0 ;;  # panelpro_restart_due.sh: no restart due
esac
exit 99
"""


class PreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = stage_env(self.tmp)
        self.env.update(HOME=str(self.tmp / "home"))
        (self.tmp / "bin/ssh").write_text(FAKE_SSH.replace("@TMP@", str(self.tmp)), encoding="utf-8")
        self.down()

    def down(self, *hosts: str) -> None:
        (self.tmp / "down.txt").write_text("".join(f"{h}\n" for h in hosts), encoding="utf-8")

    def calls(self) -> list[str]:
        log = self.tmp / "network.log"
        return log.read_text().splitlines() if log.exists() else []

    def deploy(self, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SYNC), *flags], cwd=ROOT, env=self.env,
                              capture_output=True, text=True, timeout=600)

    def test_windows_down_stops_pi_and_win_before_any_pi_step(self) -> None:
        self.down(WIN)
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(f"STOP: cannot reach Windows (nobody@{WIN} port 1) over ssh.", done.stderr)
        self.assertIn("Nothing was sent to or installed on any host", done.stderr)
        self.assertNotIn("cannot reach the Pi", done.stderr)
        self.assertNotIn("Deploy → Pi", done.stdout)
        # The Pi saw only its read-only checks: unpulled changes, the no-op, the restart check.
        pi = [c.split(f"{PI} ", 1)[1] for c in self.calls() if f"{PI} " in c]
        self.assertEqual(3, len(pi), self.calls())
        self.assertTrue(pi[0].startswith("bash -s -- '"), pi)
        self.assertEqual(["true", "bash -s"], pi[1:])
        self.assertFalse((self.tmp / "home").exists(), "the Mac install ran")

    def test_both_down_names_both_and_skips_the_restart_check(self) -> None:
        self.down(PI, WIN)
        self.env["HART_DISCARD_PI_CHANGES"] = "1"  # else the unpulled check stops on the Pi first
        done = self.deploy("--all")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(f"STOP: cannot reach the Pi ({PI}) over ssh.", done.stderr)
        self.assertIn("STOP: cannot reach Windows", done.stderr)
        self.assertEqual(2, len(self.calls()), self.calls())

    def test_single_host_checks_only_that_host(self) -> None:
        self.down(PI, WIN)
        self.env["HART_DISCARD_PI_CHANGES"] = "1"
        pi = self.deploy("--pi")
        self.assertEqual(1, pi.returncode, pi.stderr)
        self.assertIn("cannot reach the Pi", pi.stderr)
        self.assertNotIn("Windows", pi.stderr)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertFalse(any(WIN in c for c in self.calls()), self.calls())
        (self.tmp / "network.log").unlink()
        win = self.deploy("--win")
        self.assertEqual(1, win.returncode, win.stderr)
        self.assertIn("cannot reach Windows", win.stderr)
        self.assertNotIn("the Pi", win.stderr)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())

    def test_both_reachable_goes_on_to_the_pi_step(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertNotIn("cannot reach", done.stderr)
        self.assertIn("Deploy → Pi", done.stdout)
        calls = self.calls()
        self.assertTrue(calls[1].endswith(f"{PI} true"), calls)
        self.assertTrue(calls[2].endswith(f"{WIN} exit 0"), calls)
        # The first real host step, which the stand-in fails.
        self.assertIn("mktemp -d /tmp/hart-deploy.XXXXXX", calls[3])
        self.assertEqual(99, done.returncode, done.stderr[-2000:])

    def test_one_host_goes_on_while_the_other_is_down(self) -> None:
        self.down(PI)
        done = self.deploy("--win")
        self.assertNotIn("cannot reach", done.stderr)
        self.assertIn("Deploy → Windows", done.stdout)
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())

    def test_dry_run_and_stage_only_skip_the_check(self) -> None:
        self.down(PI, WIN)
        done = self.deploy("--pi", "--win", "--stage-only", str(self.tmp / "stage"))
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual([], self.calls())
        done = self.deploy("--win", "--dry-run")
        self.assertNotIn("cannot reach", done.stderr)
        self.assertEqual([], self.calls())


if __name__ == "__main__":
    unittest.main()
