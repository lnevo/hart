"""tools/hosts/operating.sh: set, show and clear the operating flag the main guard reads."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "operating.sh"


class OperatingFlag(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.flag = Path(self.tmp.name) / "operating"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_it(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, HART_OPERATING_FLAG=str(self.flag))
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def fields(self) -> dict:
        return dict(line.split("=", 1) for line in self.flag.read_text().splitlines())

    def test_owner_flag_set_shown_and_cleared_only_with_owner(self) -> None:
        self.assertEqual(self.run_it("status").returncode, 1)
        self.assertEqual(self.run_it("on", "ops", "session").returncode, 0)
        got = self.fields()
        self.assertEqual((got["by"], got["reason"]), ("owner", "ops session"))
        self.assertTrue(got["since"])
        shown = self.run_it("status")
        self.assertEqual(shown.returncode, 0)
        self.assertIn("by=owner", shown.stdout)
        refused = self.run_it("off")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("--owner", refused.stderr)
        self.assertTrue(self.flag.exists())
        self.assertEqual(self.run_it("off", "--owner").returncode, 0)
        self.assertFalse(self.flag.exists())
        self.assertEqual(self.run_it("off").returncode, 0)          # already clear

    def test_speedmatch_flag_cleared_by_the_agent_and_never_overwritten(self) -> None:
        self.assertEqual(self.run_it("on", "--by", "speedmatch", "job x").returncode, 0)
        again = self.run_it("on", "--by", "speedmatch", "other")   # a second run's on keeps the first
        self.assertIn("already set", again.stdout)
        self.assertEqual(self.fields()["by"], "speedmatch")
        self.assertEqual(self.run_it("off").returncode, 0)
        self.assertFalse(self.flag.exists())

    def test_the_owner_takes_over_a_speedmatch_flag(self) -> None:
        self.run_it("on", "--by", "speedmatch", "job x")
        took = self.run_it("on", "ops session")
        self.assertEqual(took.returncode, 0)
        self.assertIn("taken over", took.stdout)
        self.assertEqual(self.fields()["by"], "owner")
        self.assertEqual(self.run_it("off").returncode, 1)          # the run's agent can no longer clear it
        self.assertTrue(self.flag.exists())
        self.assertEqual(list(self.flag.parent.glob("operating.*")), [])   # no temp file left behind

    def test_bad_arguments_stop(self) -> None:
        self.assertEqual(self.run_it("on", "--by", "someone").returncode, 2)
        self.assertFalse(self.flag.exists())
        self.assertEqual(self.run_it("sideways").returncode, 2)

    def test_guard_is_open_when_clear_and_refuses_when_set(self) -> None:
        self.assertEqual(self.run_it("guard", "a test deploy").returncode, 0)
        self.run_it("on", "ops", "session")
        done = self.run_it("guard", "a test deploy")
        self.assertEqual(done.returncode, 3)
        self.assertIn("the operating flag is set", done.stderr)
        self.assertIn("ops session", done.stderr)
        self.assertIn("a test deploy waits", done.stderr)

    def test_guard_override_goes_ahead_and_says_so(self) -> None:
        self.run_it("on", "ops")
        env = dict(os.environ, HART_OPERATING_FLAG=str(self.flag), HART_DEPLOY_WHILE_OPERATING="1")
        done = subprocess.run(["bash", str(SCRIPT), "guard"], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0)
        self.assertIn("HART_DEPLOY_WHILE_OPERATING=1", done.stderr)

    @unittest.skipIf(os.geteuid() == 0, "root reads any file")
    def test_guard_fails_closed_on_an_unreadable_flag(self) -> None:
        self.run_it("on", "ops")
        self.flag.chmod(0)
        try:
            done = self.run_it("guard")
        finally:
            self.flag.chmod(0o600)
        self.assertEqual(done.returncode, 3)
        self.assertIn("cannot be read", done.stderr)


if __name__ == "__main__":
    unittest.main()
