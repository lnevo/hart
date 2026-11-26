"""The shared game engine's pure helpers (game_engine_test.js). Skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "game_engine_test.js"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class GameEngine(unittest.TestCase):
    def test_pure_helpers(self) -> None:
        r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("game engine OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
