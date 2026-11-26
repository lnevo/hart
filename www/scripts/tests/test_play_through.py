"""Extra East: HART Railroad play-through: every run, island and road, is played to its end screen over many draws in a
fake DOM (play_through_test.js). Fails on an exception or a run that does not end. Skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "play_through_test.js"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlayThrough(unittest.TestCase):
    def test_every_run_plays_to_the_end(self):
        r = subprocess.run(["node", str(SCRIPT), "40"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("play-through OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
