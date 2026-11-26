"""Extra East loads and plays to its end screens, with a 24-hour clock (exam_run_test.js). Skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "exam_run_test.js"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExamRun(unittest.TestCase):
    def test_plays_every_run(self) -> None:
        r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("exam run OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
