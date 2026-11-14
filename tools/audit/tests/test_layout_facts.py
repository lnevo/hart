"""check_layout_facts.py passes on the repo and catches a flipped switch sense.

The Switch 9 rewiring (2026-11-12) took three commits to bring tables.xml, the
CATS desks and the generators back into agreement. Each test below flips one
side of Switch 9 in a temporary copy and expects the check to name Switch 9 and
the two sources that disagree.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))
import check_layout_facts as check  # noqa: E402

DATA_FILES = ("switches.csv", "switch_legs.csv", "public_name_map.csv", "control_points.csv", "mast_cells.csv")


class LayoutFactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def copy(self, src: Path, edit=None) -> Path:
        dst = self.tmp / src.name
        text = src.read_text(encoding="utf-8")
        if edit is not None:
            new = edit(text)
            self.assertTrue(new != text, f"edit did not change {src.name}")
            text = new
        dst.write_text(text, encoding="utf-8")
        return dst

    def failures(self, **kw) -> list[str]:
        return check.run(**kw).failures(check.KNOWN)

    def test_repo_passes(self) -> None:
        self.assertEqual(self.failures(), [])

    def test_flipped_continuing_sense(self) -> None:
        tables = self.copy(check.TABLES, lambda t: re.sub(
            r'(<layoutturnout ident="TO10"[^>]*?) continuing="4"', r'\1 continuing="2"', t))
        out = self.failures(tables=tables)
        self.assertTrue(any(m.startswith("Switch 9: Layout Editor TO10 (continuing=2) closes to Track EH-3")
                            and "switch_legs.csv says closed Track EH-2" in m for m in out), out)

    def test_flipped_block_path(self) -> None:
        def flip(text: str) -> str:
            os9 = re.search(r"<occupancysensor>BS Switch 9</occupancysensor>.*?</block>", text, re.S)
            body = os9.group(0).replace(
                '<beansetting setting="2">\n          <turnout systemName="Switch 9" />',
                '<beansetting setting="4">\n          <turnout systemName="Switch 9" />')
            return text[:os9.start()] + body + text[os9.end():]

        out = self.failures(tables=self.copy(check.TABLES, flip))
        self.assertTrue(any(m.startswith("Switch 9: OS Switch 9 block paths reach Track EH-2")
                            and "closed leg" in m for m in out), out)

    def test_flipped_cats_normal(self) -> None:
        def flip(text: str) -> str:
            cell = re.search(r'<SECTION X="24" Y="8">.*?</SECTION>', text, re.S)
            body = cell.group(0).replace('ROUTEID="BOTTOM" NORMAL="true"', 'ROUTEID="BOTTOM"').replace(
                'ROUTEID="LEFT"', 'ROUTEID="LEFT" NORMAL="true"')
            return text[:cell.start()] + body + text[cell.end():]

        desk = self.copy(check.DESKS[0], flip)
        out = self.failures(desks=(desk,))
        self.assertTrue(any(m.startswith("Switch 9: HART_CTC.xml OS Switch 9 NORMAL") for m in out), out)

    def test_flipped_fact_fails_on_every_side(self) -> None:
        data = self.tmp / "data"
        data.mkdir()
        for name in DATA_FILES:
            shutil.copy(check.facts.DATA / name, data / name)
        legs = data / "switch_legs.csv"
        legs.write_text(legs.read_text().replace(
            "9,OS Switch 9,Track EH-2,Track EH-3", "9,OS Switch 9,Track EH-3,Track EH-2"))
        out = [m for m in self.failures(data=data) if m.startswith("Switch 9:")]
        self.assertTrue(any("Layout Editor TO10" in m for m in out), out)
        self.assertTrue(any("block paths" in m for m in out), out)
        self.assertTrue(any("HART_CTC.xml" in m and "(close) leads to Track EH-2" in m for m in out), out)
        self.assertTrue(any("HART_ABS.xml" in m for m in out), out)

    def data_copy(self) -> Path:
        data = self.tmp / "data"
        data.mkdir(exist_ok=True)
        for name in DATA_FILES:
            shutil.copy(check.facts.DATA / name, data / name)
        return data

    def test_a_control_point_on_another_level_than_its_switches_fails(self) -> None:
        data = self.data_copy()
        cps = data / "control_points.csv"
        cps.write_text(cps.read_text().replace("plane,Plane,1,", "plane,Plane,2,"))
        out = self.failures(data=data)
        self.assertIn("Switch 5: switches.csv level 1, control_points.csv puts Plane on level 2", out)
        self.assertIn("OS Switch 5: is in Plane (level 2), its switches in switch_legs.csv say level 1", out)

    def test_a_throat_block_is_held_to_its_tracks_switch(self) -> None:
        # Track K-1 West shares Track K-1's occupancy sensor; Track K-1 is a leg of Switch 39.
        data = self.data_copy()
        names = data / "public_name_map.csv"
        names.write_text(names.read_text().replace("block,Track K-1 West,Track K-1 West,Princess,",
                                                   "block,Track K-1 West,Track K-1 West,Brick,"))
        switches = data / "switches.csv"
        switches.write_text(switches.read_text().replace("1,39,TOL29,", "2,39,TOL29,"))
        out = self.failures(data=data)
        self.assertIn("Track K-1 West: is in Brick (level 1), its switches in switch_legs.csv say level 2", out)

    def test_a_cp_with_no_control_point_row_fails(self) -> None:
        data = self.data_copy()
        cps = data / "control_points.csv"
        cps.write_text("".join(line for line in cps.read_text().splitlines(True)
                               if not line.startswith("engine_house,")))
        out = self.failures(data=data)
        self.assertIn("Engine House: a cp in public_name_map.csv with no row (and no level) in "
                      "control_points.csv", out)

    def test_a_main_takes_the_level_of_the_blocks_it_joins(self) -> None:
        data = self.data_copy()
        switches = data / "switches.csv"
        switches.write_text(switches.read_text().replace("1,1,TOL3,", "2,1,TOL3,"))
        out = self.failures(data=data)
        self.assertTrue(any(m.startswith("Track Main West: no control point") and "join levels ['1', '2']" in m
                            for m in out), out)

    def test_a_mast_moved_on_one_desk_fails(self) -> None:
        def move(text: str) -> str:
            cell = re.search(r'<SECTION X="45" Y="6">.*?</SECTION>', text, re.S)
            return text[:cell.start()] + cell.group(0).replace("Mast 24L", "Mast 24LX") + text[cell.end():]

        out = self.failures(desks=(self.copy(check.DESKS[0], move), check.DESKS[1]))
        self.assertIn("Mast 24L: HART_CTC.xml has Mast 24LX at (45, 6, 'RIGHT'), "
                      "mast_cells.csv has Mast 24L there", out)

    def test_a_mast_drawn_with_the_wrong_head_fails(self) -> None:
        data = self.data_copy()
        cells = data / "mast_cells.csv"
        cells.write_text(cells.read_text().replace("Mast 4RA,6,10,RIGHT,E,d1,IH436", "Mast 4RA,6,10,RIGHT,E,d1,IH437"))
        self.assertIn("Mast 4RA: mast_cells.csv draws it d1 IH437, tables.xml gives it heads ['IH436']",
                      self.failures(data=data))

    def test_stale_known_entry_fails(self) -> None:
        report = check.run()
        known = dict(check.KNOWN, **{"Switch 1: made up": "made up"})
        self.assertIn("KNOWN entry no longer happens; remove it from KNOWN: Switch 1: made up",
                      report.failures(known))

    def test_a_new_difference_on_a_known_track_still_fails(self) -> None:
        report = check.run()
        accepted = "EH-1: GUIObjects.xml labels (2,2) 'EH-1'; the CATS desk does not"
        report.add("uss-diagram:EH-1", accepted)
        report.add("uss-diagram:EH-1", "EH-1: GUIObjects.xml labels (1,1) 'EH-1'; the CATS desk does not")
        known = {accepted: "accepted for this test"}
        self.assertEqual(report.failures(known),
                         ["EH-1: GUIObjects.xml labels (1,1) 'EH-1'; the CATS desk does not"])

    def test_throat_blocks_count_as_their_track(self) -> None:
        t = check.Tables(check.TABLES)
        self.assertEqual(t.track_name("Track S-R West"), "Track S-R")
        self.assertEqual(t.track_name("Track Main West"), "Track Main West")


if __name__ == "__main__":
    unittest.main()
