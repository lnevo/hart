"""Extra East signal tables: an unknown arm, lamp or plate key throws a named error (signals_keys_test.js).
Skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "signals_keys_test.js"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SignalKeys(unittest.TestCase):
    def test_unknown_keys_throw_named_errors(self):
        r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("signal keys OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
