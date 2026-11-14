"""check_hart_phase02.py takes a crossover's secondary OS blocks from switch_legs.csv."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_hart_phase02.py"
spec = importlib.util.spec_from_file_location("check_hart_phase02", SCRIPT)
phase02 = importlib.util.module_from_spec(spec)
sys.modules["check_hart_phase02"] = phase02
spec.loader.exec_module(phase02)


class SecondaryOsBlocksTest(unittest.TestCase):
    def test_rows_after_a_switchs_first_are_secondary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "legs.csv"
            p.write_text("switch,os_block,closed_leg,thrown_leg\n"
                         "1,OS Switch 1,Track A,Track B\n"
                         "7,OS Switch 7,Track A,OS Switch 7b\n"
                         "7,OS Switch 7b,Track B,OS Switch 7\n", encoding="utf-8")
            self.assertEqual({"OS Switch 7b"}, phase02.secondary_os_blocks(p))

    def test_repo_crossovers(self):
        self.assertEqual(3, len(phase02.secondary_os_blocks()))
        self.assertEqual(0, phase02.main())


if __name__ == "__main__":
    unittest.main()
