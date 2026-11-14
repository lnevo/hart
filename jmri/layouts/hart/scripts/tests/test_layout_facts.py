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

FILES = ("switches.csv", "switch_legs.csv", "public_name_map.csv", "control_points.csv")


class LoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        for name in FILES:
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
        levels = facts.name_map_levels()
        self.assertEqual(levels[("turnout", "Switch 9")], "1")       # switches.csv
        self.assertEqual(levels[("fb", "FB Switch 9 N")], "1")       # its switch
        self.assertEqual(levels[("block", "Track Main East")], "1")  # a leg of Switch 7 and 33
        self.assertEqual(levels[("mast", "Mast 10LA")], "1")         # cp Engine House
        self.assertNotIn(("block", "Track Main West"), levels)       # main between control points

    def test_a_control_point_without_a_level_is_refused(self) -> None:
        text = (self.data / "control_points.csv").read_text().replace("plane,Plane,1,", "plane,Plane,,")
        (self.data / "control_points.csv").write_text(text)
        with self.assertRaisesRegex(ValueError, r"control_points.csv line 3 \(Plane\): no level"):
            facts.cp_levels(self.data)

    def test_a_mast_follows_its_control_point_to_a_new_level(self) -> None:
        text = (self.data / "control_points.csv").read_text().replace("plane,Plane,1,", "plane,Plane,2,")
        (self.data / "control_points.csv").write_text(text)
        levels = facts.name_map_levels(self.data)
        self.assertEqual(levels[("mast", "Mast 6LA")], "2")
        self.assertEqual(levels[("turnout", "Switch 5")], "1")       # switches.csv still says 1

    def test_switch_9_is_left_hand_and_unrecorded_hands_are_blank(self) -> None:
        switches = facts.load_switches()
        self.assertEqual(switches[9].hand, "L")
        self.assertEqual(switches[13].hand, "")

    def test_a_hand_other_than_l_r_or_blank_is_refused(self) -> None:
        text = (self.data / "switches.csv").read_text().replace("1,9,TO10,no,31,no,L", "1,9,TO10,no,31,no,left")
        (self.data / "switches.csv").write_text(text)
        with self.assertRaisesRegex(ValueError, r"Switch 9\): hand is L, R or blank, got 'left'"):
            facts.load_switches(self.data)

    def test_the_engine_terminal_draws_switch_9_from_its_hand(self) -> None:
        sys.path.insert(0, str(facts.paths.REPO_ROOT / "tools/anyrail"))
        import engine_terminal

        self.assertEqual(engine_terminal.SW9_HAND, "L")
        self.assertIn("Switch 9 is left hand: its normal route goes to EH-2", engine_terminal.svg()[0])


if __name__ == "__main__":
    unittest.main()
