"""A Pi deploy brings back PanelPro it quit; one closed by hand stays closed."""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DUE = ROOT / "tools/hosts/pi/panelpro_restart_due.sh"
HOSTS = ROOT / "tools/hosts"


class RestartDueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.marker = self.home / ".hart_panelpro_quit_for_deploy"
        self.log = self.home / ".jmri/log/session.log"
        self.log.parent.mkdir(parents=True)
        self.running(False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def running(self, yes: bool) -> None:
        stub = self.bin / "pgrep"
        stub.write_text(f"#!/bin/sh\nexit {0 if yes else 1}\n")
        stub.chmod(0o755)

    def due(self, max_age: str = "7200") -> str:
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin"}
        out = subprocess.run(
            ["bash", str(DUE), max_age],
            check=True, capture_output=True, text=True, env=env,
        )
        return out.stdout.strip()

    def test_no_marker_means_no_restart(self) -> None:
        self.assertEqual("no", self.due())

    def test_fresh_marker_restarts_and_is_kept_until_start_succeeds(self) -> None:
        self.marker.write_text("quit")
        self.assertEqual("yes", self.due())
        self.assertTrue(self.marker.exists())

    def test_age_is_measured_in_seconds(self) -> None:
        self.marker.write_text("quit")
        os.utime(self.marker, (time.time() - 5, time.time() - 5))
        self.assertEqual("yes", self.due("30"))
        os.utime(self.marker, (time.time() - 45, time.time() - 45))
        self.assertEqual("stale", self.due("30"))

    def test_old_marker_is_stale(self) -> None:
        self.marker.write_text("quit for an ops-pull last week")
        old = time.time() - 3 * 3600
        os.utime(self.marker, (old, old))
        self.assertEqual("stale", self.due())
        self.assertFalse(self.marker.exists())

    def test_running_jmri_or_cats_clears_the_marker_and_starts_nothing(self) -> None:
        self.marker.write_text("quit")
        self.running(True)
        self.assertEqual("running", self.due())
        self.assertFalse(self.marker.exists())


class ScriptsAgreeTest(unittest.TestCase):
    def test_deploy_never_quits_panelpro_itself(self) -> None:
        src = (HOSTS / "sync_hart_package.sh").read_text(encoding="utf-8")
        self.assertNotIn('bash "$ROOT/tools/hosts/pi_quit_panelpro.sh"', src)

    def test_restart_check_runs_on_exit_through_the_pi_apply_and_after_it(self) -> None:
        src = (HOSTS / "sync_hart_package.sh").read_text(encoding="utf-8")
        trap_at = src.index("trap 'rm -rf \"$STAGE\"; pi_restart_if_due' EXIT")
        apply_at = src.index("bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh")
        done_at = src.index('echo "Pi deploy done."')
        self.assertLess(trap_at, apply_at)
        self.assertIn("pi_restart_if_due", src[done_at: done_at + 80])

    def test_only_a_for_deploy_quit_leaves_the_marker(self) -> None:
        src = (HOSTS / "pi_quit_panelpro.sh").read_text(encoding="utf-8")
        write = src.index('date -Is > "$HOME/.hart_panelpro_quit_for_deploy"')
        guard = src.rindex('if [[ "$for_deploy" == 1 ]]; then', 0, write)
        self.assertLess(write - guard, 80)

    def test_start_clears_the_marker_only_after_panelpro_is_up(self) -> None:
        src = (HOSTS / "pi_start_panelpro.sh").read_text(encoding="utf-8")
        started = src.index('echo "PanelPro started on the Pi')
        did_not_start = src.index("PanelPro did not start")
        clear = src.rindex('rm -f "$HOME/.hart_panelpro_quit_for_deploy"')
        self.assertLess(did_not_start, clear)
        self.assertLess(clear, started)

if __name__ == "__main__":
    unittest.main()
