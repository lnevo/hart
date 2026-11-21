"""layout_facts.py refuses switch facts that would be ambiguous."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import layout_facts as facts  # noqa: E402

FILES = ("switches.csv", "switch_legs.csv", "devices.csv", "schematic/stations.csv", "mast_cells.csv")

STATIONS = "schematic/stations.csv"


class LoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        for name in FILES:
            (self.data / name).parent.mkdir(exist_ok=True)
            shutil.copy(facts.DATA / name, self.data / name)

    def append(self, name: str, line: str) -> None:
        with (self.data / name).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def test_repo_data_loads(self) -> None:
        switches = facts.load_switches()
        self.assertEqual(switches[9].legs[0].closed, "Track EH-2")
        self.assertEqual((switches[9].hardware, switches[9].dcc), ("M2T1310", "119"))

    def test_a_number_reused_on_another_level_names_both_rows(self) -> None:
        self.append("switches.csv", "2,9,TO999,no,99,no")
        with self.assertRaisesRegex(ValueError, r"lines 6 \(level 1\) and 22 \(level 2\) both use Switch 9"):
            facts.load_switches(self.data)

    def test_an_os_block_on_two_rows_names_both(self) -> None:
        self.append("switch_legs.csv", "11,OS Switch 9,Track EH-1,Track EH-3")
        with self.assertRaisesRegex(ValueError, r"lines 7 and 25: both list OS Switch 9"):
            facts.load_switches(self.data)

    def test_a_shared_lever_names_both_rows(self) -> None:
        text = (self.data / "switches.csv").read_text().replace("1,9,TO10,no,31,no", "1,9,TO10,no,33,no")
        (self.data / "switches.csv").write_text(text)
        with self.assertRaisesRegex(ValueError, r"Switch 9\) and 7 \(Switch 11\) both use USS lever IS33"):
            facts.load_switches(self.data)

    def test_levels_come_from_switches_and_control_points(self) -> None:
        levels = facts.staging_levels()
        self.assertEqual(levels[("turnout", "Switch 9")], "1")       # switches.csv
        self.assertEqual(levels[("fb", "FB Switch 9 N")], "1")       # its switch
        self.assertEqual(levels[("block", "Track Main East")], "1")  # a leg of Switch 7 and 33
        self.assertEqual(levels[("mast", "Mast 10LA")], "1")         # cp Engine House
        self.assertNotIn(("block", "Track Main West"), levels)       # main between control points

    def test_a_control_point_without_a_level_is_refused(self) -> None:
        text = (self.data / STATIONS).read_text().replace("1,Plane,5,", ",Plane,5,")
        (self.data / STATIONS).write_text(text)
        with self.assertRaisesRegex(ValueError, r"stations.csv line 4 \(Plane\): level is a whole number, not ''"):
            facts.cp_levels(self.data)

    def test_a_mast_follows_its_control_point_to_a_new_level(self) -> None:
        text = (self.data / STATIONS).read_text().replace("1,Plane,5,", "2,Plane,5,")
        (self.data / STATIONS).write_text(text)
        levels = facts.staging_levels(self.data)
        self.assertEqual(levels[("mast", "Mast 6LA")], "2")
        self.assertEqual(levels[("turnout", "Switch 5")], "1")       # switches.csv still says 1

    def test_every_staging_switch_has_the_owners_hand(self) -> None:
        switches = facts.load_switches()
        self.assertEqual(switches[9].hand, "L")
        self.assertEqual(switches[13].hand, "L")
        self.assertEqual(switches[23].hand, "R")
        self.assertEqual([n for n, s in switches.items() if s.level == "1" and not s.hand], [])

    def test_a_hand_other_than_l_r_or_blank_is_refused(self) -> None:
        text = (self.data / "switches.csv").read_text().replace("1,9,TO10,no,31,no,L", "1,9,TO10,no,31,no,left")
        (self.data / "switches.csv").write_text(text)
        with self.assertRaisesRegex(ValueError, r"Switch 9\): hand is L, R or blank, got 'left'"):
            facts.load_switches(self.data)

    def test_a_mast_or_a_cell_listed_twice_names_both_rows(self) -> None:
        self.append("mast_cells.csv", "Mast 2L,1,1,LEFT,W,h2,,,,")
        with self.assertRaisesRegex(ValueError, r"lines 4 and 25: same mast Mast 2L"):
            facts.load_mast_cells(self.data)

    def test_a_d1_icon_needs_its_head(self) -> None:
        self.append("mast_cells.csv", "Mast 99L,1,1,LEFT,W,d1,,,,")
        with self.assertRaisesRegex(ValueError, r"line 25 \(Mast 99L\): uss_head is the head for d1"):
            facts.load_mast_cells(self.data)


if __name__ == "__main__":
    unittest.main()
