"""build_image.sh takes no argument or one --stop, and refuses anything else before it reaches Lima.

A stub `limactl` on PATH logs its arguments and succeeds, and HART_PI_OS_* point into a temporary folder, so nothing
here starts, stops or builds a real VM."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hosts/pi-os/build_image.sh"
VM = "hart-pi-build-test"


class BuildImageArguments(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)
        stub = self.tmp / "bin"
        stub.mkdir()
        self.log = self.tmp / "limactl.log"
        (stub / "limactl").write_text(f'#!/bin/sh\necho "$*" >> "{self.log}"\nexit 0\n', encoding="utf-8")
        (stub / "limactl").chmod(0o755)
        self.env = {"PATH": f"{stub}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.tmp / "home"),
                    "HART_PI_OS_PRIVATE": str(self.tmp / "private"), "HART_PI_OS_WORK": str(self.tmp / "work"),
                    "HART_PI_OS_VM": VM}

    def run_it(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.env, cwd=self.tmp, capture_output=True,
                              text=True, timeout=60)

    def limactl_calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_stop_stops_the_named_vm(self) -> None:
        done = self.run_it("--stop")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([f"stop {VM}"], self.limactl_calls())

    def test_an_unknown_argument_is_refused_with_its_name(self) -> None:
        for args in (["--stp"], ["stop"], [""], ["--help"]):
            with self.subTest(args=args):
                done = self.run_it(*args)
                self.assertEqual(64, done.returncode, done.stderr)
                self.assertIn(f"build_image.sh: unknown argument: {args[0]}\n", done.stderr)
                self.assertIn("usage: build_image.sh [--stop]", done.stderr)
        self.assertEqual([], self.limactl_calls())

    def test_more_than_one_argument_is_refused(self) -> None:
        done = self.run_it("--stop", "now")
        self.assertEqual(64, done.returncode, done.stderr)
        self.assertIn("one argument at most, got 2: --stop now", done.stderr)
        self.assertEqual([], self.limactl_calls())

    def test_no_argument_builds_and_stops_at_the_first_missing_input(self) -> None:
        """No argument is a build: it reaches the input checks (here the missing secrets) and calls no Lima command
        that changes anything."""
        done = self.run_it()
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(f"missing {self.tmp / 'private'}/secrets.env: run pull_from_pi.sh first", done.stderr)
        self.assertEqual([], self.limactl_calls())


if __name__ == "__main__":
    unittest.main()
