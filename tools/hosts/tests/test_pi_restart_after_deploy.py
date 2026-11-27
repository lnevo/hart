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

    def test_a_pgrep_that_cannot_tell_keeps_the_marker_and_starts_nothing(self) -> None:
        self.marker.write_text("quit")
        stub = self.bin / "pgrep"
        stub.write_text("#!/bin/sh\nexit 2\n")
        self.assertEqual("unknown", self.due())
        self.assertTrue(self.marker.exists())


class DeploySendsTheHelperTest(unittest.TestCase):
    """common.sh pi_restart_if_due sends jmri_profile_match.sh ahead of panelpro_restart_due.sh: a stand-in ssh runs
    what it is sent with bash on this machine (HOME a temporary folder, pgrep a stub), so nothing reaches a host."""

    def restart(self, pgrep_exit: int) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            stub = tmp / "bin"
            stub.mkdir()
            (stub / "ssh").write_text('#!/bin/bash\nexec bash -c "${@: -1}"\n', encoding="utf-8")
            (stub / "pgrep").write_text(f"#!/bin/sh\nexit {pgrep_exit}\n", encoding="utf-8")
            for tool in ("ssh", "pgrep"):
                (stub / tool).chmod(0o755)
            (tmp / ".hart_panelpro_quit_for_deploy").write_text("quit", encoding="utf-8")
            env = {"HOME": str(tmp), "PATH": f"{stub}:/usr/bin:/bin", "HART_ENV_FILE": str(tmp / "none"),
                   "HART_PI_SSH": "pi.example.invalid"}
            return subprocess.run(["bash", "-c", 'source "$1"; pi_restart_if_due', "x",
                                   str(HOSTS / "deploy/common.sh")],
                                  env=env, capture_output=True, text=True, timeout=60)

    def test_a_running_jmri_is_seen_through_the_helper(self) -> None:
        done = self.restart(0)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("JMRI was running on the Pi during the deploy", done.stderr)

    def test_a_pgrep_that_cannot_tell_starts_nothing(self) -> None:
        done = self.restart(2)
        self.assertIn("Could not check whether to start PanelPro on the Pi", done.stderr)
        self.assertNotIn("Starting PanelPro", done.stdout)


class ScriptsAgreeTest(unittest.TestCase):
    def test_deploy_quits_panelpro_only_to_pull(self) -> None:
        """The one quit is the gate's pull (autopull_pi_changes, in autopull.sh since 2026-11-26, which common.sh
        sources; with the --for-deploy marker that pi_restart_if_due reads); no step quits it to ship."""
        quit_call = 'pi_quit_panelpro.sh}" --for-deploy'
        for path in [HOSTS / "sync_hart_package.sh", *sorted((HOSTS / "deploy").glob("*.sh"))]:
            src = path.read_text(encoding="utf-8")
            if path.name != "autopull.sh":
                self.assertNotIn(quit_call, src, path.name)
                self.assertNotIn('bash "$ROOT/tools/hosts/pi_quit_panelpro.sh"', src, path.name)
                continue
            # inside autopull_pi_changes, the file's last function, and only once
            self.assertLess(src.index("autopull_pi_changes() {"), src.index(quit_call))
            self.assertEqual(1, src.count(quit_call))
        common = (HOSTS / "deploy/common.sh").read_text(encoding="utf-8")
        self.assertIn('source "$DEPLOY_STEPS_DIR/autopull.sh"', common)

    def test_restart_check_runs_on_exit_through_the_pi_apply_and_after_it(self) -> None:
        # the entry point restarts while PI_STEP is set, from the checks passing through the staging and the Mac
        # install; ship_pi.sh takes over (its own EXIT trap) for the rsync and the apply
        entry = (HOSTS / "sync_hart_package.sh").read_text(encoding="utf-8")
        entry_exit = entry[entry.index("on_exit() {"):entry.index("trap on_exit EXIT")]
        self.assertIn('if [[ "$PI_STEP" -eq 1 ]]; then', entry_exit)
        self.assertIn("pi_restart_if_due", entry_exit)
        armed = entry.index('PI_STEP="$DO_PI"')
        self.assertGreater(armed, entry.index('bash "$DEPLOY_STEPS/gate.sh"'))
        self.assertLess(armed, entry.index('stage.sh" "${stage_flags'))
        self.assertLess(entry.index('stage.sh" "${stage_flags'), entry.index('bash "$DEPLOY_STEPS/ship_mac.sh"'))
        self.assertLess(entry.index('bash "$DEPLOY_STEPS/ship_mac.sh"'), entry.index("PI_STEP=0   # ship_pi.sh"))
        self.assertLess(entry.index("PI_STEP=0   # ship_pi.sh"), entry.index('ship_pi.sh" ${ship_flags'))
        src = (HOSTS / "deploy/ship_pi.sh").read_text(encoding="utf-8")
        on_exit = src[src.index("on_exit() {"):src.index("trap on_exit EXIT")]
        self.assertIn('if [[ "$PI_STEP" -eq 1 ]]; then', on_exit)
        self.assertIn("pi_restart_if_due", on_exit)
        step_at = src.index("PI_STEP=1")
        apply_at = src.index("bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh")
        done_at = src.index('echo "Pi deploy done."')
        self.assertLess(step_at, apply_at)
        self.assertIn("PI_STEP=0\npi_restart_if_due", src[done_at: done_at + 80])

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
