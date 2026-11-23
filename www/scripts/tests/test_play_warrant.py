"""Extra East: HART Railroad track warrant form: the pure check of a copied warrant (warrant_compare_test.js).
Skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "warrant_compare_test.js"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlayWarrant(unittest.TestCase):
    def test_compare_finds_the_wrong_boxes(self):
        r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warrant compare OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
