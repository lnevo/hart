"""win_run.sh refuses before it reaches Windows: while the operating flag is set (CATS has the box), and with no
command. A stand-in ssh on PATH records any call, so a refusal that still connected would show."""
from __future__ import annotations

import os
import shutil
import time
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WIN_RUN = ROOT / "tools/hosts/win_run.sh"


class WinRunRefuses(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.called = self.tmp / "ssh-called"
        ssh = self.bin / "ssh"
        ssh.write_text(f"#!/bin/sh\ntouch '{self.called}'\nexit 0\n")
        ssh.chmod(0o755)
        self.flag = self.tmp / "operating"

    def run_it(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", HART_OPERATING_FLAG=str(self.flag),
                   HART_WIN_SSH="nobody@example.invalid", HART_WIN_SSH_PORT="2222")
        return subprocess.run(["bash", str(WIN_RUN), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=60)

    def test_operating_flag_set_exits_3_without_ssh(self) -> None:
        self.flag.write_text("by=owner\nsince=2026-11-20T00:00:00\nreason=test\n")
        r = self.run_it("--", "true")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("operating flag", r.stderr)
        self.assertFalse(self.called.exists())

    def test_no_command_is_a_usage_error(self) -> None:
        r = self.run_it()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(self.called.exists())

    def test_make_remote_without_cmd_is_a_usage_error(self) -> None:
        r = subprocess.run(["make", "-s", "remote"], cwd=ROOT, capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("set CMD", r.stderr)
        self.assertFalse(self.called.exists())


if __name__ == "__main__":
    unittest.main()


FLOCK = shutil.which("flock")


@unittest.skipUnless(FLOCK, "flock is a Linux tool (CI and the Windows box have it)")
class WinRunSlots(unittest.TestCase):
    """The block that runs on Windows before the command: at most WIN_RUN_SLOTS runs at once, each with
    nproc/slots check.sh jobs. Rendered with --print-script and run alone against a fake main clone."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "main/.git").mkdir(parents=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "nproc").write_text("#!/bin/sh\necho 8\n")
        (self.bin / "nproc").chmod(0o755)
        env = dict(os.environ, WIN_RUN_SLOTS="2", HART_WIN_SSH="nobody@example.invalid")
        script = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--", "true"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60, check=True).stdout
        block = script.split("# --- slots", 1)[1].split("# --- end slots", 1)[0]
        self.block = self.tmp / "slots.sh"
        self.block.write_text(f'set -euo pipefail\nmain="{self.tmp}/main"\n#{block}\necho "jobs=$CHECK_MAX_JOBS slot=$got"\n')

    def run_block(self, timeout: float) -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        try:
            return subprocess.run(["bash", str(self.block)], env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(exc.cmd, -1, exc.stdout or "", (exc.stderr or b"").decode()
                                               if isinstance(exc.stderr, bytes) else (exc.stderr or ""))

    def hold(self, slot: int) -> subprocess.Popen:
        p = subprocess.Popen([FLOCK, str(self.tmp / f"main/.git/win_run.slot{slot}"), "sleep", "30"])
        self.addCleanup(p.kill)
        return p

    def test_a_free_slot_gives_half_the_cpus(self) -> None:
        done = self.run_block(10)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("jobs=4 slot=0", done.stdout)

    def test_the_second_slot_is_used_when_the_first_is_held(self) -> None:
        self.hold(0)
        time.sleep(0.5)
        done = self.run_block(10)
        self.assertIn("slot=1", done.stdout)

    def test_a_third_run_waits(self) -> None:
        self.hold(0), self.hold(1)
        time.sleep(0.5)
        done = self.run_block(3)
        self.assertEqual(-1, done.returncode)
        self.assertIn("waiting for a free slot", done.stderr)
