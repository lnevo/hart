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
        again = self.run_it("on", "other")                         # a second on keeps the first
        self.assertIn("already set", again.stdout)
        self.assertEqual(self.fields()["by"], "speedmatch")
        self.assertEqual(self.run_it("off").returncode, 0)
        self.assertFalse(self.flag.exists())

    def test_bad_arguments_stop(self) -> None:
        self.assertEqual(self.run_it("on", "--by", "someone").returncode, 2)
        self.assertFalse(self.flag.exists())
        self.assertEqual(self.run_it("sideways").returncode, 2)


if __name__ == "__main__":
    unittest.main()
