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

DATA_FILES = ("switches.csv", "switch_legs.csv", "public_name_map.csv", "control_points.csv", "mast_cells.csv",
              "uss_board_cells.csv", "uss_board_plants.csv")


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
            r'(<layoutturnout ident="TO10"[^>]*?) continuing="2"', r'\1 continuing="4"', t))
        out = self.failures(tables=tables)
        self.assertTrue(any(m.startswith("Switch 9: Layout Editor TO10 (continuing=4) closes to Track EH-3")
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
        # on the live (generated) desk: Switch 9's plant cell, found by its OS block, with NORMAL on the other leg
        import xml.etree.ElementTree as ET
        _cells, plants = check.desk_plants(check.DESKS[0], check.Report())
        x, y = plants["OS Switch 9"]
        tree = ET.parse(check.DESKS[0])
        sec = tree.getroot().find(f"TRACKPLAN/SECTION[@X='{x}'][@Y='{y}']")
        routes = sec.findall("SEC_EDGE/SWITCHPOINTS/ROUTEINFO")
        self.assertEqual(len(routes), 2)
        for ri in routes:
            if ri.get("NORMAL") == "true":
                del ri.attrib["NORMAL"]
            else:
                ri.set("NORMAL", "true")
        desk = self.tmp / check.DESKS[0].name
        tree.write(desk, encoding="UTF-8", xml_declaration=True)
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

    def test_a_mast_renamed_on_one_desk_fails(self) -> None:
        out = self.failures(desks=(self.copy(check.DESKS[0], lambda t: t.replace(">Mast 24L<", ">Mast 24LX<", 1)),
                                   check.DESKS[1]))
        self.assertIn("Mast 24L: HART_CTC.xml has 0 lamps for it, not one", out)
        self.assertIn("Mast 24LX: HART_CTC.xml has a lamp for it, staging_masts.csv has no such visible mast", out)

    def test_a_mast_on_the_wrong_block_edge_fails(self) -> None:
        # Mast 24L protects OS Switch 23a: its lamp on another block's edge is named
        def move(text: str) -> str:
            sig = text.index(">Mast 24L<")
            start = text.rindex("<SEC_EDGE", 0, sig)
            end = text.index("</SEC_EDGE>", sig)
            edge = text[start:end]
            name = re.search(r'<BLOCK[^>]* NAME="([^"]+)"', edge).group(1)
            return text[:start] + edge.replace(f'NAME="{name}"', 'NAME="Track West Ext"', 1) + text[end:]

        out = self.failures(desks=(self.copy(check.DESKS[0], move), check.DESKS[1]))
        self.assertIn("Mast 24L: HART_CTC.xml has its lamp on the edge of Track West Ext, but it protects "
                      "OS Switch 23a (staging_masts.csv)", out)

    def test_mast_cells_are_not_checked_while_the_uss_board_is_parked(self) -> None:
        # mast_cells.csv and the board's grid are the parked USS machine's (owner, 2026-11-19): a wrong head or a
        # missing grid cell is not reported until the board is back in the tables
        data = self.data_copy()
        cells = data / "mast_cells.csv"
        cells.write_text(cells.read_text().replace("Mast 4RA,6,10,RIGHT,E,d1,IH436", "Mast 4RA,6,10,RIGHT,E,d1,IH437"))
        grid = data / "uss_board_cells.csv"
        text = grid.read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("6,10,"))     # Mast 4RA's cell
        grid.write_text(text.replace(line + "\n", ""), encoding="utf-8")
        self.assertFalse([f for f in self.failures(data=data) if "mast_cells.csv" in f])

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

    # ---- main and upper: plants on internal turnouts, masts from main_upper_masts.csv

    def test_main_and_upper_pass_on_the_release_candidate_tables(self) -> None:
        candidate = check.HART / "output/trial/tables_cutover.xml"
        if not candidate.exists():
            self.skipTest("no release candidate tables (make panels writes them)")
        self.assertEqual(self.failures(tables=candidate), [])

    def level_plant(self, user: str):
        """(tree, the SECTION of the first plant commanding `user`) on a copy of the CTC desk."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(check.DESKS[0])
        for sec in tree.getroot().iter("SECTION"):
            if any(io.get("USER_NAME") == user for io in sec.findall("SEC_EDGE/SWITCHPOINTS/ROUTEINFO/*/IOSPEC")):
                return tree, sec
        self.fail(f"no plant commands {user}")

    def write(self, tree) -> Path:
        desk = self.tmp / check.DESKS[0].name
        tree.write(desk, encoding="UTF-8", xml_declaration=True)
        return desk

    def test_a_main_upper_plant_with_its_legs_swapped_fails(self) -> None:
        tree, sec = self.level_plant("Switch 111")
        routes = sec.findall("SEC_EDGE/SWITCHPOINTS/ROUTEINFO")
        self.assertEqual(len(routes), 2)
        for ri in routes:                       # close becomes throw and back, NORMAL kept on the close leg
            for io in ri.findall("*/IOSPEC"):
                io.text = {"close": "throw", "throw": "close"}[io.text.strip()]
            if ri.get("NORMAL") == "true":
                del ri.attrib["NORMAL"]
            else:
                ri.set("NORMAL", "true")
        out = self.failures(desks=(self.write(tree),))
        self.assertTrue(any(m.startswith("HART_CTC.xml: Switch 111 closes to ") and "the Layout Editor" in m
                            for m in out), out)

    def test_a_main_upper_plant_on_no_internal_turnout_fails(self) -> None:
        tree, sec = self.level_plant("Switch 111")
        for io in sec.findall("SEC_EDGE/SWITCHPOINTS/ROUTEINFO/*/IOSPEC"):
            io.set("DECADDR", ":HART:C3:999")
        out = self.failures(desks=(self.write(tree),))
        self.assertTrue(any("commands Switch 111 (IT:HART:C3:999); tables.xml has IT:HART:C3:111" in m
                            for m in out), out)
        self.assertNotIn("HART_CTC.xml: no plant commands internal turnout Switch 111", out)

    def test_a_staging_block_with_no_detector_is_still_held_to_the_tables(self) -> None:
        # only the device map's main and upper blocks may be missing from the Layout Editor (review, 2026-11-17)
        import xml.etree.ElementTree as ET
        tree = ET.parse(check.DESKS[0])
        name = next(b.get("NAME") for b in tree.getroot().iter("BLOCK")
                    if b.find("OCCUPIEDSPEC") is not None and b.get("NAME") not in check.device_map_blocks())
        for b in tree.getroot().iter("BLOCK"):          # its detector binding dropped and its name misspelt
            if b.get("NAME") == name:
                b.set("NAME", name + " Typo")
                for spec in b.findall("OCCUPIEDSPEC"):
                    b.remove(spec)
        out = self.failures(desks=(self.write(tree),))
        self.assertIn(f"HART_CTC.xml: block {name} Typo is not a Layout Editor block in tables.xml", out)

    def test_a_main_upper_desk_block_on_another_sensor_than_its_block_fails(self) -> None:
        """Each main and upper desk block reports the virtual sensor its Layout Editor block has in tables.xml."""
        tables = self.copy(check.TABLES, lambda t: t.replace("<systemName>IS:HART:C3:B:101-111</systemName>",
                                                             "<systemName>IS:HART:C3:B:X</systemName>"))
        out = self.failures(tables=tables)
        want = ("block Track 101-111 reports OCCUPIEDSPEC IS:HART:C3:B:101-111 close; UNOCCUPIEDSPEC "
                "IS:HART:C3:B:101-111 throw (user name BS 101-111); tables.xml binds it to BS 101-111 "
                "(IS:HART:C3:B:X)")
        self.assertEqual([m for m in out if "101-111" in m], [f"{d}: {want}" for d in ("HART_CTC.xml", "HART_ABS.xml")])

    def desk_block(self, name: str, change) -> list[str]:
        """The failures with every BLOCK named `name` on a copy of the CTC desk changed by `change(block)`."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(check.DESKS[0])
        hit = [b for b in tree.getroot().iter("BLOCK") if b.get("NAME") == name]
        self.assertTrue(hit, name)
        for b in hit:
            change(b)
        return [m for m in self.failures(desks=(self.write(tree),)) if name in m]

    def test_an_unbound_main_upper_desk_block_fails(self) -> None:
        """Only the desk-only middle of 225's X may be unbound; any other main or upper block must report its sensor."""
        def unbind(b):
            for tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC"):
                for spec in b.findall(tag):
                    b.remove(spec)
        self.assertEqual(self.desk_block("Track 101-111", unbind),
                         ["HART_CTC.xml: block Track 101-111 reports OCCUPIEDSPEC none; UNOCCUPIEDSPEC none (user name "
                          "None); tables.xml binds it to BS 101-111 (IS:HART:C3:B:101-111)"])
        self.assertEqual(self.desk_block("OS Switch 225", lambda b: None), [])        # desk-only, dark: fine

    def test_a_wrong_unoccupied_spec_fails(self) -> None:
        def wrong(b):
            for io in b.findall("UNOCCUPIEDSPEC/IOSPEC"):
                io.set("DECADDR", ":HART:C3:B:OS101")
        out = self.desk_block("Track 101-111", wrong)
        self.assertEqual(len(out), 1, out)
        self.assertIn("UNOCCUPIEDSPEC IS:HART:C3:B:OS101 throw", out[0])

        def wrong_command(b):
            for io in b.findall("UNOCCUPIEDSPEC/IOSPEC"):
                io.text = "close"
        self.assertIn("UNOCCUPIEDSPEC IS:HART:C3:B:101-111 close", self.desk_block("Track 101-111", wrong_command)[0])

    def test_a_bound_desk_only_block_fails(self) -> None:
        import xml.etree.ElementTree as ET

        def bind(b):
            spec = ET.SubElement(b, "OCCUPIEDSPEC")
            ET.SubElement(spec, "IOSPEC", {"DECADDR": ":HART:C3:B:OS225", "JMRIPREFIX": "IS"}).text = "close"
        self.assertEqual(self.desk_block("OS Switch 225", bind),
                         ["HART_CTC.xml: desk-only block OS Switch 225 reports a sensor; it has none"])

    def test_a_main_upper_block_missing_from_tables_that_hold_the_levels_fails(self) -> None:
        tables = self.copy(check.TABLES, lambda t: t.replace("<userName>Track 101-111</userName>",
                                                             "<userName>Track 101-111 Gone</userName>"))
        out = self.failures(tables=tables)
        self.assertIn("HART_CTC.xml: block Track 101-111 is not a Layout Editor block in tables.xml", out)

    def test_main_upper_tables_with_no_internal_turnouts_fail(self) -> None:
        tables = self.copy(check.TABLES, lambda t: t.replace("IT:HART:C3:", "IT:HART:CX:"))
        out = self.failures(tables=tables)
        self.assertTrue(any("holds main/upper blocks but no IT:HART:C3: turnout" in m for m in out), out)

    def test_a_main_upper_turnout_with_no_plant_fails(self) -> None:
        for user in ("Switch 117", "Switch 225"):           # 225: a double crossover, four points on one turnout
            with self.subTest(turnout=user):
                import xml.etree.ElementTree as ET
                tree = ET.parse(check.DESKS[0])
                for parent in tree.getroot().iter():
                    for io in [i for i in parent.findall("IOSPEC") if i.get("USER_NAME") == user]:
                        parent.remove(io)
                self.assertIn(f"HART_CTC.xml: no plant commands internal turnout {user}",
                              self.failures(desks=(self.write(tree),)))

    def test_the_double_crossover_commands_its_turnout_from_all_four_points(self) -> None:
        cells = check.trace.track_cells(check.parse(check.DESKS[0]).getroot().find("TRACKPLAN"))
        points = [(os_name, xy, edge) for os_name, xy, edge in check.trace.level_plants(cells)
                  if os_name.startswith("OS Switch 225")]
        self.assertEqual(sorted(p[0] for p in points), [f"OS Switch 225{c}" for c in "abcd"])   # a point per corner
        for _os, xy, edge in points:
            ios = cells[xy].findall(f"SEC_EDGE[@EDGE='{edge}']/SWITCHPOINTS/ROUTEINFO/ROUTECOMMAND/IOSPEC")
            self.assertEqual(sorted((i.get("USER_NAME"), i.text.strip()) for i in ios),
                             [("Switch 225", "close"), ("Switch 225", "throw")])

    def test_a_main_upper_mast_missing_or_off_its_block_fails(self) -> None:
        out = self.failures(desks=(self.copy(check.DESKS[0], lambda t: t.replace(">Mast 108LB<", ">Mast 108LX<", 1)),))
        self.assertIn("Mast 108LB: HART_CTC.xml has 0 lamps for it, not one", out)

        def move(text: str) -> str:
            sig = text.index(">Mast 226RA<")
            start = text.rindex("<SEC_EDGE", 0, sig)
            end = text.index("</SEC_EDGE>", sig)
            edge = text[start:end]
            name = re.search(r'<BLOCK[^>]* NAME="([^"]+)"', edge).group(1)
            self.assertEqual(name, "OS Switch 225a")    # the desk's corner block, as the Layout Editor's
            return text[:start] + edge.replace(f'NAME="{name}"', 'NAME="Track 225-229"', 1) + text[end:]

        out = self.failures(desks=(self.copy(check.DESKS[0], move),))
        self.assertIn("Mast 226RA: HART_CTC.xml has its lamp on the edge of Track 225-229, but it protects "
                      "OS Switch 225a (main_upper_masts.csv)", out)

    def test_desk_legs_name_the_layout_editor_tracks_inside_os_blocks(self) -> None:
        self.assertTrue(check.same_place("OS Switch 107", "Track 107-109"))
        self.assertTrue(check.same_place("OS Switch 213", "Track 213-217 1"))
        self.assertFalse(check.same_place("OS Switch 105", "Track 107-109"))
        self.assertFalse(check.same_place(None, "Track 107-109"))
        self.assertEqual(check.desk_block_of("OS Switch 225c", {"OS Switch 225"}), "OS Switch 225")
        self.assertEqual(check.desk_block_of("OS Switch 107", {"OS Switch 107"}), "OS Switch 107")


if __name__ == "__main__":
    unittest.main()
