"""The cleanup of the PanelPro wrappers' shared run lifecycle (tools/hosts/panelpro_session.sh): a JMRI that stays
or ignores TERM, signals to the wrapper, a dead launcher, SIGKILL and the restore after it, run against a fake
StartJMRI.

Split out of test_panelpro_wrappers.py on 2026-11-26 with no change in the tests, so each file stays under the size
limit (tools/audit/check_py_sizes.py). The sandbox (a temporary checkout, HOME and PATH with no MQTT client) and the
test base class come from that file, whose docstring says what the sandbox keeps away from the live profile.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest

# its folder is on sys.path under discover
from test_panelpro_wrappers import SCRIPTS, Sandbox, WrapperCase, _default_signals


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


def _wait_for(check, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.1)
    return check()


def _group_commands(pgid: int) -> str:
    """The command lines of the processes in process group PGID, one per line."""
    out = subprocess.run(["ps", "-A", "-o", "pgid=,command="], capture_output=True, text=True, check=True).stdout
    return "\n".join(line.split(None, 1)[1] for line in out.splitlines()
                     if len(line.split(None, 1)) == 2 and line.split(None, 1)[0] == str(pgid))


def _wrapper_shells(box: "Sandbox", wrapper: str, pgid: int) -> int:
    """How many processes in group PGID run WRAPPER's command line: its shell, and its wait helper (a fork)."""
    return _group_commands(pgid).splitlines().count(" ".join(box.cmd(wrapper)))


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class Cleanup(WrapperCase):
    def test_success_waits_for_jmri_to_quit_then_restores(self) -> None:
        env = self.box.env(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_PANELPRO_SMOKE_MARKER")
        done = self.box.run("run_panelpro_smoke_test.sh", env)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("PanelPro smoke: ok", done.stdout)
        self.assertNotIn("Stopping", done.stderr)
        self.assert_restored()

    def test_jmri_that_stays_after_the_marker_is_stopped(self) -> None:
        env = self.box.env(FAKE_MODE="hang", FAKE_MARKER_FROM="HART_CTC_LOGIC_SMOKE_MARKER",
                           HART_PANELPRO_EXIT_WAIT="1")
        done = self.box.run("run_ctc_logic_smoke.sh", env)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("PanelPro did not quit after the CTC Logic smoke; stopping it", done.stderr)
        self.assertFalse(_alive(self.box.java_pid()))
        self.assert_restored()

    def test_timeout_stops_java_even_when_it_ignores_term(self) -> None:
        env = self.box.env(FAKE_MODE="hang", FAKE_IGNORE_TERM="1", HART_PANELPRO_TIMEOUT="2",
                           HART_PANELPRO_KILL_WAIT="1")
        started = time.monotonic()
        done = self.box.run("run_panelpro_smoke_test.sh", env)
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("did not produce a marker", done.stderr)
        self.assertIn("PanelPro ignored TERM; killing", done.stderr)
        self.assertFalse(_alive(self.box.java_pid()))
        self.assertLess(time.monotonic() - started, 30)
        self.assert_restored()

    def signal_run(self, box: Sandbox, wrapper: str, sig: signal.Signals, ready=None,
                   **extra: str) -> tuple[int, str, bool]:
        """Start WRAPPER with a hanging java, send SIG to the wrapper's pid alone once java runs and READY(pgid)
        holds (by default: the wait helper runs beside the wrapper's shell, so the shell has only builtins left
        before its `wait`, no foreground step), and return (exit code, stderr, whether java still ran when the wrapper had exited).
        The run is its own process group, so nothing it started outlives the test; a run that does not exit is
        a failure that shows its output."""
        env = box.env(**{"FAKE_MODE": "hang", "HART_PANELPRO_TIMEOUT": "60", **extra})
        proc = subprocess.Popen(box.cmd(wrapper), env=env, cwd=box.tmp, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, preexec_fn=_default_signals,
                                start_new_session=True)
        try:
            java = box.java_pid()
            self.assertIn(b'enabled="no"', box.profile.read_bytes())   # patched while running
            ready = ready or (lambda pgid: _wrapper_shells(box, wrapper, pgid) >= 2)
            self.assertTrue(_wait_for(lambda: ready(proc.pid), 20), "the run never got ready for the signal")
            proc.send_signal(sig)
            try:
                _out, err = proc.communicate(timeout=30)
                java_left = _alive(java)          # before the group kill below can hide a java left running
            except subprocess.TimeoutExpired:
                _kill_group(proc.pid)
                _out, err = proc.communicate()
                self.fail(f"{wrapper} still ran 30 s after {sig.name}; its stderr:\n{err}")
        finally:
            _kill_group(proc.pid)          # also a java or helper a failed run left
            if proc.returncode is None:
                proc.communicate()
        return proc.returncode, err, java_left

    def test_sigterm_sigint_and_sighup_stop_java_and_restore(self) -> None:
        # Each signal on its own sandbox: a run that fails cannot leave a backup that fails the next.
        for sig, code in ((signal.SIGTERM, 143), (signal.SIGINT, 130), (signal.SIGHUP, 129)):
            with self.subTest(signal=sig.name):
                box = self.new_box()
                rc, err, java_left = self.signal_run(box, "run_sml_discover.sh", sig)
                self.assertEqual(code, rc, err)
                self.assertIn("Stopping the PanelPro this run started", err)
                self.assertFalse(java_left, err)
                self.assert_restored(box.profile, box.original)

    def test_a_signal_during_a_long_poll_acts_at_once(self) -> None:
        """The waits poll in a background helper and the shell waits in `wait`, so a signal sent to the
        wrapper's pid is acted on at once, not after the poll's sleep (bash can drop a signal that arrives
        while a foreground command runs). A 30 s poll would hold a foreground sleep for 30 s."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sig.name):
                box = self.new_box()
                err_path = box.tmp / "stderr"
                with open(err_path, "w", encoding="utf-8") as err_file:
                    proc = subprocess.Popen(box.cmd("run_panelpro_smoke_test.sh"),
                                            env=box.env(FAKE_MODE="hang", HART_PANELPRO_TIMEOUT="600",
                                                        HART_PANELPRO_POLL="30"),
                                            cwd=box.tmp, stdout=subprocess.DEVNULL, stderr=err_file,
                                            preexec_fn=_default_signals, start_new_session=True)
                try:
                    java = box.java_pid()
                    self.assertTrue(_wait_for(lambda: "sleep 30" in _group_commands(proc.pid), 20),
                                    "the wait never reached its 30 s sleep")
                    proc.send_signal(sig)
                    stopped = _wait_for(lambda: "Stopping the PanelPro this run started"
                                        in err_path.read_text(encoding="utf-8"), 10)
                    self.assertTrue(stopped, f"no stop within 10 s of {sig.name} during a 30 s poll; stderr:\n"
                                             + err_path.read_text(encoding="utf-8"))
                    self.assertTrue(_wait_for(lambda: not _alive(java), 10))
                finally:
                    _kill_group(proc.pid)   # the stop's own 30 s poll is not under test here
                    proc.wait()

    def test_java_left_by_a_dead_launcher_is_stopped_on_a_signal(self) -> None:
        # The launcher quits and leaves java: only the wait helper saw java as its child, and the stop
        # after the signal still finds it (PP_PIDS_FILE).
        box = self.new_box()
        rc, err, java_left = self.signal_run(box, "run_sml_discover.sh", signal.SIGTERM, FAKE_MODE="detach",
                                             ready=lambda pgid: "StartJMRI" not in _group_commands(pgid))
        java = int((box.state / "java.pid").read_text())
        self.assertEqual(143, rc, err)
        self.assertIn(f"Stopping the PanelPro this run started (pids {java})", err)   # java alone: launcher gone
        self.assertFalse(java_left, err)
        self.assert_restored(box.profile, box.original)

    def launch_slow_exec(self, exec_wait: str | None = None) -> subprocess.CompletedProcess[str]:
        """pp_launch on a launcher that shows another command line for 1.5 s before it becomes StartJMRI (as
        every launcher does for a moment after the fork), then a 3 s pp_wait_marker; prints rc=<its result>."""
        slow = self.box.tmp / "slow_start"
        slow.write_text("sleep 1.5\nexec -a StartJMRI sleep 30\n", encoding="utf-8")
        script = self.box.tmp / "slow_exec.sh"
        script.write_text(f"""set -euo pipefail
ROOT={self.box.root}
source "$ROOT/tools/hosts/panelpro_session.sh"
PROFILE_ID=x
STARTJMRI="{slow}"
pp_launch "$FAKE_STATE/launch.log"
rc=0
pp_wait_marker "$FAKE_STATE/never" 3 0.1 || rc=$?
kill "$PP_JPID"
rm -f ${{PP_TMP_FILES[@]+"${{PP_TMP_FILES[@]}}"}}
echo "rc=$rc"
""", encoding="utf-8")
        slow.chmod(0o755)
        env = self.box.env(**({"HART_PANELPRO_EXEC_WAIT": exec_wait} if exec_wait else {}))
        return subprocess.run(["/bin/bash", str(script)], env=env, capture_output=True, text=True,
                              preexec_fn=_default_signals, timeout=60)

    def test_the_first_poll_waits_for_the_launcher_to_exec(self) -> None:
        # The wait must see the launcher as running, so it times out (2), not "PanelPro quit first" (1),
        # which a poll right after the fork once reported (3 in about 1000 loaded runs).
        done = self.launch_slow_exec()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("rc=2", done.stdout.strip(), done.stderr)
        self.assertNotIn("still does not show", done.stderr)

    def test_a_launcher_that_never_shows_as_startjmri_is_named(self) -> None:
        # The exec wait is bounded: past it the run says so and the wait judges the launcher (here: not ours).
        done = self.launch_slow_exec(exec_wait="0")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("The PanelPro launcher (pid", done.stderr)
        self.assertIn("still does not show as StartJMRI", done.stderr)
        self.assertEqual("rc=1", done.stdout.strip(), done.stderr)

    def test_the_wait_helper_quits_when_the_wrapper_is_killed(self) -> None:
        # SIGKILL cannot be trapped: the helper (a fork of the wrapper's shell, same command line) must not
        # go on polling to the 60 s timeout. Java stays, as after any SIGKILL (the recovery note says so).
        box = self.new_box()
        proc = subprocess.Popen(box.cmd("run_sml_discover.sh"), env=box.env(FAKE_MODE="hang", HART_PANELPRO_TIMEOUT="60"),
                                cwd=box.tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                preexec_fn=_default_signals, start_new_session=True)
        try:
            box.java_pid()
            self.assertTrue(_wait_for(lambda: _wrapper_shells(box, "run_sml_discover.sh", proc.pid) >= 2, 20),
                            "no wait helper beside the wrapper's shell")
            proc.kill()
            proc.wait()
            self.assertTrue(_wait_for(lambda: _wrapper_shells(box, "run_sml_discover.sh", proc.pid) == 0, 10),
                            "the wait helper still runs 10 s after the wrapper was killed:\n"
                            + _group_commands(proc.pid))
        finally:
            _kill_group(proc.pid)

    def test_after_sigkill_the_next_run_refuses_and_restore_recovers(self) -> None:
        env = self.box.env(FAKE_MODE="hang", HART_PANELPRO_TIMEOUT="60")
        proc = subprocess.Popen(self.box.cmd("run_panelpro_stage1.sh"), env=env, cwd=self.box.tmp,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=_default_signals)
        java = self.box.java_pid()
        proc.kill()
        proc.wait(timeout=10)
        os.kill(java, signal.SIGKILL)   # the owner quits the PanelPro it left
        bak = self.box.profile.with_name("profile.xml.hart-run.bak")
        self.assertEqual(self.box.original, bak.read_bytes())
        self.assertNotEqual(self.box.original, self.box.profile.read_bytes())

        (self.box.state / "launch_arg").unlink()
        again = self.box.run("run_panelpro_smoke_test.sh", self.box.env())
        self.assertEqual(1, again.returncode)
        self.assertIn(f"restore --profile {self.box.profile}", again.stderr)
        self.assertFalse((self.box.state / "launch_arg").exists())

        restore = [sys.executable, str(self.box.root / "tools/hosts/panelpro_profile.py"), "restore",
                   "--profile", str(self.box.profile)]
        busy = subprocess.run(restore, capture_output=True, text=True, env={**env, "HART_GUARD_JMRI_RUNNING": "1"})
        self.assertNotEqual(0, busy.returncode)
        self.assertIn("running", busy.stderr)
        fixed = subprocess.run(restore, capture_output=True, text=True, env=env)
        self.assertEqual(0, fixed.returncode, fixed.stderr)
        self.assert_restored()
        self.assertFalse(self.box.profile.with_name("profile.xml.hart-run.sha256").exists())

    def test_cleanup_keeps_the_backup_when_the_started_jmri_cannot_be_stopped(self) -> None:
        script = self.box.tmp / "stuck.sh"
        script.write_text(f"""set -euo pipefail
ROOT={self.box.root}
source "$ROOT/tools/hosts/panelpro_session.sh"
pp_profile
pp_begin "$ROOT/{SCRIPTS}/panelpro_smoke_test.py"
pp_stop_jmri() {{ echo "Could not stop pids 99999" >&2; return 1; }}
exit 1
""", encoding="utf-8")
        done = subprocess.run(["/bin/bash", str(script)], env=self.box.env(), capture_output=True, text=True,
                              preexec_fn=_default_signals,
                              timeout=60)
        self.assertEqual(1, done.returncode)
        self.assertIn("PROFILE NOT RESTORED: quit that PanelPro, then run: python3", done.stderr)
        self.assertIn(f"restore --profile {self.box.profile}", done.stderr)
        self.assertTrue(self.box.profile.with_name("profile.xml.hart-run.bak").exists())
        self.assertNotEqual(self.box.original, self.box.profile.read_bytes())


if __name__ == "__main__":
    unittest.main()
