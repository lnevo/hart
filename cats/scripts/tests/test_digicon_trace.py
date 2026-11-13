"""digicon_trace follows a points leg along the drawn track to the next block."""
from __future__ import annotations

import copy
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import digicon_trace as trace  # noqa: E402

# A plant at (2,1): points LEFT, legs RIGHT (straight) and BOTTOM (slash down to row 2).
GRID = """<TRACKPLAN>
  <SECTION X="1" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track West"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"/></SECTION>
  <SECTION X="2" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK><TRACK>LOWERBACKSLASH</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><SWITCHPOINTS/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"/><SEC_EDGE EDGE="BOTTOM"/></SECTION>
  <SECTION X="3" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="OS Switch 1"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"><BLOCK NAME="OS Switch 1"/></SEC_EDGE></SECTION>
  <SECTION X="4" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track Main"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"><SHARED X="9" Y="9">LEFT</SHARED></SEC_EDGE></SECTION>
  <SECTION X="2" Y="2"><TRACKGROUP><TRACK>UPPERSLASH</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="TOP"/><SEC_EDGE EDGE="LEFT"/></SECTION>
  <SECTION X="1" Y="2"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="RIGHT"/><SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track Siding"/></SEC_EDGE></SECTION>
</TRACKPLAN>"""


def grid() -> dict:
    return trace.track_cells(ET.fromstring(GRID))


class TraceTest(unittest.TestCase):
    def test_plant_edges(self) -> None:
        self.assertEqual(trace.plant_edges(grid()[(2, 1)]), ("LEFT", ["RIGHT", "BOTTOM"]))
        self.assertEqual(trace.plant_edges(grid()[(1, 1)]), (None, []))

    def test_a_legs_neighbour_is_never_the_os(self) -> None:
        # Nothing on (2,1); past the points is Track West, which neither leg reaches
        # first (they reach OS Switch 1 and Track Siding), so there is no answer.
        with self.assertRaises(trace.PlantError):
            trace.plant_os(grid(), (2, 1))

    def test_os_spanning_the_frog_is_found(self) -> None:
        cells = grid()
        cells[(1, 1)].find("SEC_EDGE[@EDGE='LEFT']/BLOCK").set("NAME", "OS Switch 1")
        self.assertEqual(trace.plant_os(cells, (2, 1)), "OS Switch 1")

    def test_name_on_the_frog_cell_wins(self) -> None:
        cells = grid()
        ET.SubElement(cells[(2, 1)].find("SEC_EDGE[@EDGE='RIGHT']"), "BLOCK", {"NAME": "OS Switch 1"})
        self.assertEqual(trace.plant_os(cells, (2, 1)), "OS Switch 1")

    def test_two_names_on_the_frog_cell_fail(self) -> None:
        cells = grid()
        ET.SubElement(cells[(2, 1)].find("SEC_EDGE[@EDGE='RIGHT']"), "BLOCK", {"NAME": "OS Switch 1"})
        ET.SubElement(cells[(2, 1)].find("SEC_EDGE[@EDGE='BOTTOM']"), "BLOCK", {"NAME": "OS Switch 2"})
        with self.assertRaises(trace.PlantError):
            trace.plant_os(cells, (2, 1))

    def test_straight_leg_skips_its_own_os(self) -> None:
        self.assertEqual(trace.trace_leg(grid(), (2, 1), "RIGHT", own="OS Switch 1"), "Track Main")

    def test_diverging_leg_follows_the_slashes(self) -> None:
        self.assertEqual(trace.trace_leg(grid(), (2, 1), "BOTTOM", own="OS Switch 1"), "Track Siding")

    def test_shared_jump_to_a_missing_cell_ends_the_trace(self) -> None:
        cells = grid()
        cells[(4, 1)].find("SEC_EDGE[@EDGE='LEFT']").remove(cells[(4, 1)].find("SEC_EDGE[@EDGE='LEFT']/BLOCK"))
        self.assertIsNone(trace.trace_leg(cells, (2, 1), "RIGHT", own="OS Switch 1"))


class DeskPlantsTest(unittest.TestCase):
    def test_two_plants_in_one_os_fail(self) -> None:
        cells = trace.track_cells(ET.fromstring(GRID))
        other = copy.deepcopy(cells[(2, 1)])
        other.set("Y", "5")
        cells[(2, 5)] = other
        for xy in ((2, 1), (2, 5)):
            sp = cells[xy].find("SEC_EDGE[@EDGE='LEFT']/SWITCHPOINTS")
            ET.SubElement(sp, "ROUTEINFO", {"ROUTEID": "RIGHT"})
            ET.SubElement(cells[xy].find("SEC_EDGE[@EDGE='RIGHT']"), "BLOCK", {"NAME": "OS Switch 1"})
        with self.assertRaisesRegex(trace.PlantError, r"\(2, 1\) and \(2, 5\) are both in OS Switch 1"):
            trace.desk_plants(cells)


class DeskTest(unittest.TestCase):
    """Spot checks on the wired CTC desk, including a plant reached through another plant."""

    @classmethod
    def setUpClass(cls) -> None:
        root = ET.parse(SCRIPTS.parent / "panels/HART_CTC.xml").getroot()
        cls.cells = trace.track_cells(root.find("TRACKPLAN"))

    def test_switch_9(self) -> None:
        self.assertEqual(trace.plant_os(self.cells, (24, 8)), "OS Switch 9")
        self.assertEqual(trace.trace_leg(self.cells, (24, 8), "BOTTOM"), "Track EH-2")
        self.assertEqual(trace.trace_leg(self.cells, (24, 8), "LEFT"), "Track EH-3")

    def test_switch_11_thrown_reaches_switch_9(self) -> None:
        self.assertEqual(trace.trace_leg(self.cells, (26, 8), "LEFT"), "OS Switch 9")

    def test_every_wired_plant_has_its_own_os(self) -> None:
        self.assertEqual(len(trace.desk_plants(self.cells)), 23)

    def test_unnamed_frog_cell(self) -> None:
        # Switch 3's frog cell carries no BLOCK; its OS is found past the points.
        self.assertEqual(trace.plant_os(self.cells, (5, 9)), "OS Switch 3")
        self.assertEqual(trace.trace_leg(self.cells, (5, 9), "BOTTOM"), "Track W-1")


if __name__ == "__main__":
    unittest.main()
