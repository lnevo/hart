"""check.sh's job_status: a job passes on the exit code it wrote itself, not on `wait`'s status, because bash 3.2
(macOS) can drop a finished background job so that `wait PID` says "not a child of this shell" for a job that
passed (2026-11-25, seen under load as jobs marked FAILED whose output was OK). The function text is taken from
check.sh itself and run with /bin/bash."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECK_SH = ROOT / "tools/check.sh"


def job_status_function() -> str:
    text = CHECK_SH.read_text(encoding="utf-8")
    m = re.search(r"^job_status\(\) \{\n.*?^\}\n", text, re.M | re.S)
    if m is None:
        raise AssertionError("tools/check.sh has no job_status() function")
    return m.group(0)


def status(jobs: Path, pid: int) -> int:
    script = job_status_function() + f'JOBS="{jobs}"; pids[0]={pid}; job_status 0\n'
    return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30).returncode


class JobStatus(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.jobs = Path(tmp.name)
        self.not_a_child = os.getpid()  # the test process: never a child of the bash that runs job_status

    def test_a_passed_job_passes_even_when_wait_says_not_a_child(self) -> None:
        (self.jobs / "0.rc").write_text("0\n")
        self.assertEqual(status(self.jobs, self.not_a_child), 0)

    def test_a_failed_job_fails(self) -> None:
        (self.jobs / "0.rc").write_text("1\n")
        self.assertNotEqual(status(self.jobs, self.not_a_child), 0)

    def test_a_job_that_wrote_no_code_fails(self) -> None:
        self.assertNotEqual(status(self.jobs, self.not_a_child), 0)

    def test_a_garbled_code_fails(self) -> None:
        (self.jobs / "0.rc").write_text("ok\n")
        self.assertNotEqual(status(self.jobs, self.not_a_child), 0)

    def test_it_still_waits_for_a_running_child(self) -> None:
        """job_status blocks until its own child ends, then reads the code the child wrote."""
        script = (job_status_function()
                  + f'JOBS="{self.jobs}"; ( sleep 0.5; echo 0 >"$JOBS/0.rc" ) & pids[0]=$!; job_status 0\n')
        done = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_every_job_writes_its_code_before_it_exits(self) -> None:
        text = CHECK_SH.read_text(encoding="utf-8")
        self.assertIn('echo "$rc" >"$JOBS/$n.rc"', text)
        self.assertIn('elif job_status "$i"; then', text)
        self.assertNotIn('elif wait "${pids[$i]}"; then', text)


if __name__ == "__main__":
    unittest.main()
