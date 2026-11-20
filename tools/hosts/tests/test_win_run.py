"""win_run.sh refuses before it reaches Windows: while the operating flag is set (CATS has the box), and with no
command. A stand-in ssh on PATH records any call, so a refusal that still connected would show."""
from __future__ import annotations

import os
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
