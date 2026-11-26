"""check_hart_phase02.py takes a crossover's secondary OS blocks from the staging rows of switches.csv, read through
hartlib.railroad (naming-layers step 6)."""
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


def switches_file(tmp: str, keep, edit=lambda line: line) -> Path:
    """A copy of the repo's switches.csv with the rows of the switches `keep` ((level, switch) pairs) only, each line
    passed through `edit`: the rows read through hartlib.railroad.read_switch_rows, which holds every column."""
    lines = phase02.SWITCHES.read_text(encoding="utf-8").splitlines()
    rows = [edit(line) for line in lines[1:] if tuple(line.split(",")[:2]) in keep]
    p = Path(tmp) / "switches.csv"
    p.write_text("\n".join([lines[0], *rows]) + "\n", encoding="utf-8")
    return p


class SecondaryOsBlocksTest(unittest.TestCase):
    def test_rows_after_a_switchs_first_are_secondary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = switches_file(tmp, {("1", "1"), ("1", "7"), ("2", "101")})
            self.assertEqual({"OS Switch 7b"}, phase02.secondary_os_blocks(p))
            self.assertEqual(["OS Switch 1", "OS Switch 7", "OS Switch 7b"],
                             [r.os_block for r in phase02.staging_rows(p)])

    def test_repo_crossovers_are_exactly_these(self):
        # Pinned on purpose: a reordered or dropped staging row of switches.csv changes this set.
        self.assertEqual({"OS Switch 7b", "OS Switch 23b", "OS Switch 35a"}, phase02.secondary_os_blocks())
        self.assertEqual(0, phase02.main())

    def test_a_crossover_with_one_row_fails(self):
        root = ET.fromstring('<layout-config><layoutturnout ident="TO1" type="RH_XOVER"/>'
                             '<layoutturnout ident="TO2" type="RH_TURNOUT"/></layout-config>')
        idents = {"TO117": "TO1", "TO10": "TO2"}           # Switch 7's and 9's Layout Editor turnouts, renamed
        renamed = lambda line: ",".join(idents.get(c, c) for c in line.split(","))  # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            one = switches_file(tmp, {("1", "7"), ("1", "9")},
                                lambda line: "" if line.startswith("1,7,,os:7:A-5B,") else renamed(line))
            one.write_text("\n".join(x for x in one.read_text(encoding="utf-8").splitlines() if x) + "\n",
                           encoding="utf-8")
            self.assertEqual(["Switch 7 is a crossover (TO1) but switches.csv has 1 row(s) for it, not 2"],
                             phase02.crossover_row_errors(root, one))
            both = switches_file(tmp, {("1", "7"), ("1", "9")}, renamed)
            self.assertEqual([], phase02.crossover_row_errors(root, both))

    def test_a_file_without_the_columns_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "switches.csv"
            p.write_text("switch,os_id\n7,os:7\n", encoding="utf-8")
            with self.assertRaisesRegex(phase02.railroad.FactsError, "switches.csv: no column level, half"):
                phase02.secondary_os_blocks(p)

    def test_a_row_hartlib_refuses_stops_with_its_line(self):
        """The rows are read by hartlib.railroad.read_switch_rows, so a staging row with no OS block ID stops."""
        with tempfile.TemporaryDirectory() as tmp:
            p = switches_file(tmp, {("1", "9")}, lambda line: line.replace(",os:9,", ",,"))
            with self.assertRaisesRegex(phase02.railroad.FactsError, r"switches.csv line 2 \(Switch 9\): a staging row is keyed by "
                                                    r"its OS block"):
                phase02.staging_rows(p)

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


class RefusedSwitchesTest(unittest.TestCase):
    def test_main_fails_with_the_message_when_switches_csv_is_refused(self):
        import contextlib
        import io
        from unittest import mock
        out = io.StringIO()
        refused = phase02.railroad.FactsError("switches.csv line 2: bad row")
        with mock.patch.object(phase02, "staging_rows", side_effect=refused), contextlib.redirect_stdout(out):
            self.assertEqual(phase02.main(), 1)
        self.assertEqual(out.getvalue(), "FAIL\n  - switches.csv line 2: bad row\n")


if __name__ == "__main__":
    unittest.main()
