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
            ["bash", str(DUE), "TCS_MQTT.test", max_age],
            check=True, capture_output=True, text=True, env=env,
        )
        return out.stdout.strip()

    def test_no_marker_means_no_restart(self) -> None:
        self.assertEqual("no", self.due())

    def test_fresh_marker_restarts_and_is_kept_until_start_succeeds(self) -> None:
        self.log.write_text("old session")
        os.utime(self.log, (time.time() - 60, time.time() - 60))
        self.marker.write_text("quit")
        self.assertEqual("yes", self.due())
        self.assertTrue(self.marker.exists())

    def test_started_by_hand_since_the_quit_is_stale(self) -> None:
        self.marker.write_text("quit")
        os.utime(self.marker, (time.time() - 120, time.time() - 120))
        self.log.write_text("PanelPro started from the desktop")
        self.assertEqual("stale", self.due())
        self.assertFalse(self.marker.exists())

    def test_old_marker_is_stale(self) -> None:
        self.marker.write_text("quit for an ops-pull last week")
        old = time.time() - 3 * 3600
        os.utime(self.marker, (old, old))
        self.assertEqual("stale", self.due())
        self.assertFalse(self.marker.exists())

    def test_running_panelpro_clears_the_marker(self) -> None:
        self.marker.write_text("quit")
        self.running(True)
        self.assertEqual("running", self.due())
        self.assertFalse(self.marker.exists())


class ScriptsAgreeTest(unittest.TestCase):
    def test_deploy_quits_before_and_checks_after_the_pi_apply(self) -> None:
        src = (HOSTS / "sync_hart_package.sh").read_text(encoding="utf-8")
        quit_at = src.index('bash "$ROOT/tools/hosts/pi_quit_panelpro.sh"')
        apply_at = src.index("bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh")
        due_at = src.index("pi/panelpro_restart_due.sh")
        self.assertLess(quit_at, apply_at)
        self.assertLess(apply_at, due_at)

    def test_start_clears_the_marker_only_after_panelpro_is_up(self) -> None:
        src = (HOSTS / "pi_start_panelpro.sh").read_text(encoding="utf-8")
        started = src.index('echo "PanelPro started on the Pi')
        did_not_start = src.index("PanelPro did not start")
        clear = src.rindex('rm -f "$HOME/.hart_panelpro_quit_for_deploy"')
        self.assertLess(did_not_start, clear)
        self.assertLess(clear, started)


if __name__ == "__main__":
    unittest.main()
