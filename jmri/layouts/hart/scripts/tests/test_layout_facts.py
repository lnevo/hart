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
from hartlib import devices, hand_lists  # noqa: E402

FILES = ("switches.csv", devices.MASTER_FILE, "schematic/stations.csv", "schematic/interlockings.csv", "mast_cells.csv",
         f"schematic/{hand_lists.OVERRIDES_NAME}")

STATIONS = "schematic/stations.csv"


class LoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        for name in FILES:
            (self.data / name).parent.mkdir(exist_ok=True)
            if name == devices.MASTER_FILE:      # the master's two files, as the reader finds them in the folder
                devices.pair_copy(self.data)
            else:
                shutil.copy(facts.DATA / name, self.data / name)

    def append(self, name: str, line: str) -> None:
        with (self.data / name).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def test_repo_data_loads(self) -> None:
        switches = facts.load_switches()
        self.assertEqual(switches[9].legs[0].closed, "Track EH-2")
        self.assertEqual((switches[9].hardware, switches[9].dcc), ("M2T1310", "119"))

    def test_a_number_reused_on_another_level_names_both_rows(self) -> None:
        self.append("switches.csv", "2,9,9,,,,,,,,,,,")
        with self.assertRaisesRegex(ValueError, r"lines 7 \(level 1\) and \d+ \(level 2\) both use Switch 9"):
            facts.load_switches(self.data)

    def test_an_os_block_on_two_rows_names_both(self) -> None:
        path = self.data / "switches.csv"
        lines = path.read_text().splitlines(keepends=True)
        lines.insert(7, "1,9,,os:9,block:11B-end,block:9C-end,,,,,,,,\n")       # right after Switch 9's row
        path.write_text("".join(lines))
        with self.assertRaisesRegex(ValueError, r"lines 7 and 8: both are OS Switch 9"):
            facts.load_switches(self.data)

    def test_an_os_block_of_another_switch_is_refused(self) -> None:
        # a staging row's OS block is its os_id (os_block is the name store's name of it, naming-layers step 5)
        text = (self.data / "switches.csv").read_text().replace("1,11,,os:11,", "1,11,,os:9,")
        (self.data / "switches.csv").write_text(text)
        with self.assertRaisesRegex(ValueError, r"line 8 \(Switch 11\): a row keyed by its OS block gives the device IDs of it \(os_id os:11"):
            facts.load_switches(self.data)

    def test_a_shared_lever_names_both_rows(self) -> None:
        text = (self.data / "switches.csv").read_text().replace("TO10,no,31,no", "TO10,no,33,no")
        (self.data / "switches.csv").write_text(text)
        with self.assertRaisesRegex(ValueError, r"lines 7 \(Switch 9\) and 8 \(Switch 11\) both use USS lever IS33"):
            facts.load_switches(self.data)

    def test_levels_come_from_switches_and_control_points(self) -> None:
        levels = facts.staging_levels()
        self.assertEqual(levels[("turnout", "Switch 9")], "1")       # switches.csv
        self.assertEqual(levels[("fb", "FB Switch 9 N")], "1")       # its switch
        self.assertEqual(levels[("block", "Track Main East")], "1")  # a leg of Switch 7 and 33
        self.assertEqual(levels[("mast", "Mast 10LA")], "1")         # cp Engine House
        self.assertEqual(levels[("block", "Track Main West")], "1")  # its cp, Brick;East End, both level 1

    def test_a_line_block_takes_its_places_level_only_when_every_place_has_one(self) -> None:
        def row(cp):
            return dict(layer="block", user_name="Track X", role="track", cp=cp)
        self.assertEqual(facts.staging_levels(rows=[row("Brick;West Yard")]), {("block", "Track X"): "1"})
        self.assertEqual(facts.staging_levels(rows=[row("Brick;Nowhere")]), {})       # a place with no level
        self.assertEqual(facts.staging_levels(rows=[row("Princess;CP 127")]), {})     # places on two levels
        self.assertEqual(facts.staging_levels(rows=[row("")]), {})

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
        self.assertEqual([n for n, s in switches.items() if s.level == 1 and not s.hand], [])

    def test_a_hand_other_than_l_r_or_blank_is_refused(self) -> None:
        text = (self.data / "switches.csv").read_text().replace("block:9C-end,L,owner", "block:9C-end,left,owner")
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
