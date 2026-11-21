"""check_hart_phase02.py takes a crossover's secondary OS blocks from the staging rows of switches.csv."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_hart_phase02.py"
spec = importlib.util.spec_from_file_location("check_hart_phase02", SCRIPT)
phase02 = importlib.util.module_from_spec(spec)
sys.modules["check_hart_phase02"] = phase02
spec.loader.exec_module(phase02)


class SecondaryOsBlocksTest(unittest.TestCase):
    def test_rows_after_a_switchs_first_are_secondary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "switches.csv"
            p.write_text("level,switch,half,os_block,le_ident\n"
                         "1,1,,OS Switch 1,TO1\n"
                         "1,7,,OS Switch 7,TO7\n"
                         "1,7,,OS Switch 7b,\n"
                         "2,101,101A,,\n"
                         "2,101,101B,,\n", encoding="utf-8")
            self.assertEqual({"OS Switch 7b"}, phase02.secondary_os_blocks(p))

    def test_repo_crossovers_are_exactly_these(self):
        # Pinned on purpose: a reordered or dropped staging row of switches.csv changes this set.
        self.assertEqual({"OS Switch 7b", "OS Switch 23b", "OS Switch 35a"}, phase02.secondary_os_blocks())
        self.assertEqual(0, phase02.main())

    def test_a_crossover_with_one_row_fails(self):
        root = ET.fromstring('<layout-config><layoutturnout ident="TO1" type="RH_XOVER"/>'
                             '<layoutturnout ident="TO2" type="RH_TURNOUT"/></layout-config>')
        with tempfile.TemporaryDirectory() as tmp:
            sw = Path(tmp) / "switches.csv"
            sw.write_text("level,switch,os_block,le_ident\n1,7,OS Switch 7,TO1\n1,9,OS Switch 9,TO2\n",
                          encoding="utf-8")
            self.assertEqual(["Switch 7 is a crossover (TO1) but switches.csv has 1 row(s) for it, not 2"],
                             phase02.crossover_row_errors(root, sw))
            sw.write_text(sw.read_text(encoding="utf-8").replace("TO1\n", "TO1\n1,7,OS Switch 7b,\n"),
                          encoding="utf-8")
            self.assertEqual([], phase02.crossover_row_errors(root, sw))

    def test_a_file_without_the_columns_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "switches.csv"
            p.write_text("switch,os_block\n7,OS Switch 7\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "no column level, le_ident"):
                phase02.secondary_os_blocks(p)

    def test_repo_crossovers_have_two_rows(self):
        self.assertEqual([], phase02.crossover_row_errors(ET.parse(phase02.PANEL).getroot()))


class HartTablesTest(unittest.TestCase):
    """HART_TABLES (tools/check.sh, hartlib.paths) names the tables file the checks read."""

    def run_with(self, value):
        import os
        import subprocess
        env = {k: v for k, v in os.environ.items() if k != "HART_TABLES"}
        if value is not None:
            env["HART_TABLES"] = value
        return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)

    def test_the_checkout_file_by_default_and_the_named_file_when_set(self):
        self.assertEqual(0, self.run_with(None).returncode)
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "tables.xml"
            broken.write_text("<layout-config/>", encoding="utf-8")
            done = self.run_with(str(broken))
        self.assertNotEqual(0, done.returncode)


if __name__ == "__main__":
    unittest.main()
