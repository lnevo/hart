from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "seed_default_thrown_turnouts.py"


class SeedDefaultThrownReadOnlyTest(unittest.TestCase):
    def test_write_mode_is_gone(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--write"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2)

    def test_never_publishes_mqtt(self) -> None:
        self.assertNotIn("mosquitto_pub", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
