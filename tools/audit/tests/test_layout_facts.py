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
from hartlib import devices, hand_lists  # noqa: E402

DATA_FILES = ("switches.csv", devices.MASTER_FILE, "schematic/stations.csv", "schematic/interlockings.csv", "mast_cells.csv",
              "uss_board_cells.csv", "uss_board_plants.csv", f"schematic/{hand_lists.OVERRIDES_NAME}")


def with_os9_paths(text: str, closed: str = "2", thrown: str = "4") -> str:
    """The tables text with OS Switch 9's two block paths stored, as a PanelPro Store writes them (the generated
    tables.xml stores none, ADR-029): Track EH-2 (IB21) with Switch 9 at `closed`, Track EH-3 (IB22) at `thrown`."""
    paths = "".join(f'      <path todir="64" fromdir="128" block="{b}">\n        <beansetting setting="{st}">\n'
                    f'          <turnout systemName="Switch 9" />\n        </beansetting>\n      </path>\n'
                    for b, st in (("IB21", closed), ("IB22", thrown)))
    os9 = re.search(r"<occupancysensor>BS Switch 9</occupancysensor>\n", text)
    return text[:os9.end()] + paths + text[os9.end():]


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
                            and "switches.csv says closed Track EH-2" in m for m in out), out)

    def test_stored_block_paths_are_held_to_the_legs(self) -> None:
        """A tables file that stores block paths (a PanelPro Store) has them checked against switches.csv; the
        generated tables.xml stores none, so the check has nothing to hold there."""
        right = self.failures(tables=self.copy(check.TABLES, with_os9_paths))
        self.assertFalse([m for m in right if m.startswith("Switch 9:")], right)
        self.assertIn("Switch 7: OS Switch 7 has no block paths in tables.xml", right)   # the others store none
        out = self.failures(tables=self.copy(check.TABLES, lambda t: with_os9_paths(t, closed="4", thrown="2")))
        self.assertTrue(any(m.startswith("Switch 9: OS Switch 9 block paths reach Track EH-2")
                            and "closed leg" in m for m in out), out)
        self.assertFalse(check.Tables(check.TABLES).paths_stored)

    def test_a_wrong_crossover_leg_fails_against_the_panel(self) -> None:
        """The generated tables store no paths, so a crossover's legs are held to the panel's track."""
        data = self.data_copy()
        legs = data / "switches.csv"
        legs.write_text(legs.read_text().replace("1,7,,os:7:A-13C,block:5C-7B,os:7:A-5B,",
                                                 "1,7,,os:7:A-13C,block:7A-13C,os:7:A-5B,"))    # Track Barn
        out = [m for m in self.failures(data=data) if m.startswith("Switch 7:")]
        self.assertTrue(any("closes OS Switch 7 to Track Barn, the panel's track from that half's closed end reaches ['Track Scale']" in m
                            for m in out), out)
        legs.write_text(legs.read_text().replace("1,7,,os:7:A-5B,block:7B-33C,os:7:A-13C,",
                                                 "1,7,,os:7:A-5B,block:7B-33C,block:5C-7B,"))    # Track Scale
        out = [m for m in self.failures(data=data) if m.startswith("Switch 7:")]
        self.assertTrue(any("throws OS Switch 7b to Track Scale" in m for m in out), out)

    def test_a_crossover_whose_halves_share_a_block_is_named(self) -> None:
        tables = self.copy(check.TABLES, lambda t: t.replace('blockcname="OS Switch 7b" blockdname="OS Switch 7b"',
                                                             'blockcname="OS Switch 7" blockdname="OS Switch 7"', 1))
        out = [m for m in self.failures(tables=tables) if m.startswith("Switch 7:")]
        self.assertTrue(any("halves are blocks ['OS Switch 7', 'OS Switch 7']" in m for m in out), out)

    def test_a_slip_or_level_crossing_on_a_joined_block_is_named(self) -> None:
        tables = self.copy(check.TABLES, lambda t: re.sub(
            r'(<tracksegment ident="[^"]*" blockname="Track Main West"[^>]*?type1=")[A-Z_]+(")',
            r"\1LEVEL_XING_A\2", t, count=1))
        with self.assertRaisesRegex(ValueError, "LEVEL_XING_A.*slip or level crossing"):
            check.Tables(tables).joined_blocks("Track Main West")

    def test_a_part_is_read_as_the_block_it_is_inside(self) -> None:
        """A part is a JMRI block of its own inside an OS block; switches.csv names the OS
        blocks, so a leg is read past the parts of its own OS block and a part as the block it is part of."""
        t = check.Tables(check.TABLES, parts=check.part_map(check.DEVICE_MAP))
        self.assertEqual(t.os_of("Track 1-3 at 1"), "OS Switch 1")
        self.assertEqual(t.os_of("Track Barn"), "Track Barn")
        ident = next(i for i, lt in t.layout_turnouts.items() if lt.get("blockname") == "OS Switch 1")
        legs = {t.leg_block(ident, c, "OS Switch 1") for c in "BC"}
        self.assertIn("OS Switch 3", legs)
        cells, plants = check.desk_plants(check.DESKS[0], check.Report())
        xy = plants["OS Switch 35a"]
        right = check.trace.trace_leg(cells, xy, "RIGHT", own="OS Switch 35a")
        self.assertEqual(right, "Track 35-37")
        self.assertEqual(check.trace.trace_leg(cells, xy, "RIGHT", own="OS Switch 35a",
                                               inside=frozenset({"Track 35-37"})), "OS Switch 37")

    def test_the_parts_come_from_the_caller_not_the_repo(self) -> None:
        """Tables reads a part only from the part list its caller gives (run: the master that goes with the checked
        file), never the repo's devices.csv behind its back: with none, a part is its own name."""
        bare = check.Tables(check.TABLES)
        self.assertEqual(bare.part_of, {})
        self.assertEqual(bare.os_of("Track 1-3 at 1"), "Track 1-3 at 1")
        given = check.Tables(check.TABLES, parts={"Track X": "OS Switch 1"})
        self.assertEqual(given.os_of("Track X"), "OS Switch 1")
        # run() takes the parts from the master it is given: a master with no part rows leaves Switch 1's leg a part
        rows = [r for r in check.devices.load(check.DEVICE_MAP) if r["role"] != "part"]
        master = self.tmp / devices.ONE_FILE
        master.write_text(check.devices.master_text(rows), encoding="utf-8")
        self.assertEqual(check.part_map(master), {})
        self.assertEqual(len(check.part_map(check.DEVICE_MAP)), 39)          # 14 staging, 11 main, 14 upper

    def test_a_level_desk_leg_is_read_as_the_le_reads_it(self) -> None:
        """check_level_desk compares a main or upper plant's close and throw legs with the Layout Editor's, which
        reads a part as its OS block (leg_block): the desk leg is read the same way (desk_leg: past its own OS
        block's parts, a part as the block it is in), so a swapped plant is never hidden by a part's own name."""
        t = check.Tables(check.TABLES, parts=check.part_map(check.DEVICE_MAP))
        cells = check.trace.track_cells(check.parse(check.DESKS[0]).getroot().find("TRACKPLAN"))
        plants = {os_name: (xy, points) for os_name, xy, points in check.trace.level_plants(cells, check.level_turnouts())}

        def legs(os_name):
            xy, points = plants[os_name]
            out = {}
            for ri in cells[xy].findall(f"SEC_EDGE[@EDGE='{points}']/SWITCHPOINTS/ROUTEINFO"):
                out[ri.find("ROUTECOMMAND/IOSPEC").text.strip()] = check.desk_leg(t, cells, xy, ri.get("ROUTEID"),
                                                                                    os_name)
            return out
        self.assertEqual(legs("OS Switch 109")["throw"], "OS Switch 105")      # Track 105-109, part of OS 105
        self.assertEqual(legs("OS Switch 213")["close"], "OS Switch 215")      # past its own part Track 213-215
    def test_joined_blocks_come_from_the_panel_when_no_paths_are_stored(self) -> None:
        t = check.Tables(check.TABLES)
        self.assertIn("OS Switch 1", t.joined_blocks("Track Main West"))
        stored = check.Tables(self.copy(check.TABLES, with_os9_paths))
        self.assertEqual({"Track EH-2", "Track EH-3"}, stored.joined_blocks("OS Switch 9"))

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
            (data / name).parent.mkdir(exist_ok=True)
            if name == devices.MASTER_FILE:      # the master's two files, as the reader finds them in the folder
                devices.pair_copy(data)
            else:
                shutil.copy(check.facts.DATA / name, data / name)
        legs = data / "switches.csv"
        legs.write_text(legs.read_text().replace(
            "1,9,,os:9,block:9B-end,block:9C-end,", "1,9,,os:9,block:9C-end,block:9B-end,"))   # EH-2 and EH-3 swapped
        out = [m for m in self.failures(data=data) if m.startswith("Switch 9:")]
        self.assertTrue(any("Layout Editor TO10" in m for m in out), out)
        self.assertFalse(any("block paths" in m for m in out), out)      # the generated tables store none
        self.assertTrue(any("HART_CTC.xml" in m and "(close) leads to Track EH-2" in m for m in out), out)
        self.assertTrue(any("HART_ABS.xml" in m for m in out), out)

    def data_copy(self) -> Path:
        data = self.tmp / "data"
        data.mkdir(exist_ok=True)
        for name in DATA_FILES:
            (data / name).parent.mkdir(exist_ok=True)
            if name == devices.MASTER_FILE:      # the master's two files, as the reader finds them in the folder
                devices.pair_copy(data)
            else:
                shutil.copy(check.facts.DATA / name, data / name)
        return data

    def test_a_control_point_on_another_level_than_its_switches_fails(self) -> None:
        data = self.data_copy()
        stations = data / "schematic" / "stations.csv"
        stations.write_text(stations.read_text().replace("1,Plane,5,", "2,Plane,5,"))
        out = self.failures(data=data)
        self.assertIn("Switch 5: switches.csv level 1, stations.csv puts Plane on level 2", out)
        self.assertIn("OS Switch 5: is in Plane (level 2), its switches in switches.csv say level 1", out)

    def test_a_cp_with_no_control_point_row_fails(self) -> None:
        data = self.data_copy()
        stations = data / "schematic" / "stations.csv"
        stations.write_text("".join(line for line in stations.read_text().splitlines(True)
                                    if not line.startswith("st:engine-house,1,Engine House,")))
        # the copy's master reads its cp cells by the copy's lists (hartlib.places.lists_beside), so the load stops
        # on the id no row of them has, naming the file and line
        with self.assertRaisesRegex(devices.DevicesError, r"devices_generated.csv line \d+: st:engine-house is no "
                                                          "station_id of stations.csv"):
            self.failures(data=data)

    def test_a_block_in_no_place_takes_the_level_of_the_blocks_it_joins(self) -> None:
        # every staging line block lists the places it joins (cp, owner 2026-11-21), so Track Main West's is emptied
        # in a copy; switches.csv keeps staging switches (the ones with legs) on level 1, so the switch is moved in
        # memory
        import dataclasses
        from unittest import mock
        sys.path.insert(0, str(ROOT / "tools/hartlib/tests"))
        from master_edit import change
        data = self.data_copy()
        change(data / devices.MASTER_FILE, ("1", "block", "Track Main West"), cp="")
        import gen_ctc_track_plan  # noqa: F401  it reads switches.csv once at import: before the patch moves Switch 1
        real = check.facts.load_switches

        def moved(data=check.facts.DATA):
            out = real(data)
            out[1] = dataclasses.replace(out[1], level=2)
            return out
        with mock.patch.object(check.facts, "load_switches", moved):
            out = self.failures(data=data)
        self.assertTrue(any(m.startswith("Track Main West: no control point") and "are on levels ['1', '2']" in m
                            for m in out), out)

    def test_a_mast_renamed_on_one_desk_fails(self) -> None:
        out = self.failures(desks=(self.copy(check.DESKS[0], lambda t: t.replace(">Mast 24L<", ">Mast 24LX<", 1)),
                                   check.DESKS[1]))
        self.assertIn("Mast 24L: HART_CTC.xml has 0 lamps for it, not one", out)
        self.assertIn("Mast 24LX: HART_CTC.xml has a lamp for it, masts.csv has no such visible mast", out)

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
                      "OS Switch 23a (masts.csv)", out)

    def test_mast_cells_are_not_checked_while_the_uss_board_is_parked(self) -> None:
        # mast_cells.csv and the board's grid are the parked USS machine's: a wrong head or a
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

    # ---- main and upper: plants on internal turnouts, masts from masts.csv

    def test_main_and_upper_pass_on_the_live_tables(self) -> None:
        self.assertEqual(self.failures(tables=check.HART / "output/tables.xml"), [])

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
        self.assertNotIn("HART_CTC.xml: no plant commands main or upper turnout Switch 111", out)

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

    def test_a_detector_swapped_in_by_its_row_reports_its_field_sensor(self) -> None:
        """Naming-layers step 14: a main or upper block's sensor may be the field sensor of a detector the owner
        swapped in by its row (assignment field), by that column, not the level; any other must be virtual."""
        import unittest.mock
        import xml.etree.ElementTree as ET
        tables = self.copy(check.TABLES, lambda t: t.replace("<systemName>IS:HART:C3:B:101-111</systemName>",
                                                             "<systemName>M2S3399</systemName>"))
        tree = ET.parse(check.DESKS[0])
        for b in tree.getroot().iter("BLOCK"):
            if b.get("NAME") == "Track 101-111":
                for io in b.findall("OCCUPIEDSPEC/IOSPEC") + b.findall("UNOCCUPIEDSPEC/IOSPEC"):
                    io.set("JMRIPREFIX", "M2S")
                    io.set("DECADDR", "3399")
        desk = self.write(tree)
        self.assertTrue([m for m in self.failures(tables=tables, desks=(desk,)) if "101-111" in m])
        with unittest.mock.patch.object(check, "field_sensors", lambda: frozenset({"M2S3399"})):
            self.assertEqual([m for m in self.failures(tables=tables, desks=(desk,)) if "101-111" in m], [])

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

    def test_main_upper_tables_with_other_turnout_names_fail(self) -> None:
        """The main and upper turnouts are the device master's rows (not a name prefix): tables.xml giving them other
        system names than the desk commands fails."""
        tables = self.copy(check.TABLES, lambda t: t.replace("IT:HART:C3:", "IT:HART:CX:"))
        out = self.failures(tables=tables)
        self.assertTrue(any("commands Switch 111 (IT:HART:C3:111); tables.xml has IT:HART:CX:111" in m for m in out),
                        out)

    def test_main_upper_plants_are_picked_by_the_rows(self) -> None:
        """A main or upper turnout swapped to a physical name (ADR-028) is still a level plant's: the plants follow
        the rows' user names, not a prefix."""
        import copy
        cells = check.trace.track_cells(copy.deepcopy(check.parse(check.DESKS[0]).getroot()).find("TRACKPLAN"))
        level = check.level_turnouts()
        self.assertIn("Switch 111", level)
        for io in cells[next(xy for _os, xy, _e in check.trace.level_plants(cells, level))].iter("IOSPEC"):
            io.set("JMRIPREFIX", "M2T")
            io.set("DECADDR", "3308")
        self.assertEqual(len(check.trace.level_plants(cells, level)),
                         len(check.trace.level_plants(check.trace.track_cells(
                             check.parse(check.DESKS[0]).getroot().find("TRACKPLAN")), level)))
        self.assertNotIn("OS Switch 111", check.trace.desk_plants(cells, bound=True, level_turnouts=level))

    def test_a_main_upper_turnout_with_no_plant_fails(self) -> None:
        for user in ("Switch 117", "Switch 225"):           # 225: a double crossover, four points on one turnout
            with self.subTest(turnout=user):
                import xml.etree.ElementTree as ET
                tree = ET.parse(check.DESKS[0])
                for parent in tree.getroot().iter():
                    for io in [i for i in parent.findall("IOSPEC") if i.get("USER_NAME") == user]:
                        parent.remove(io)
                self.assertIn(f"HART_CTC.xml: no plant commands main or upper turnout {user}",
                              self.failures(desks=(self.write(tree),)))

    def test_the_double_crossover_commands_its_turnout_from_all_four_points(self) -> None:
        cells = check.trace.track_cells(check.parse(check.DESKS[0]).getroot().find("TRACKPLAN"))
        points = [(os_name, xy, edge) for os_name, xy, edge in check.trace.level_plants(cells, check.level_turnouts())
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
                      "OS Switch 225a (masts.csv)", out)

    def test_desk_legs_name_the_layout_editor_tracks_inside_os_blocks(self) -> None:
        self.assertTrue(check.same_place("OS Switch 107", "Track 107-109"))
        self.assertTrue(check.same_place("OS Switch 213", "Track 213-217 1"))
        self.assertFalse(check.same_place("OS Switch 105", "Track 107-109"))
        self.assertFalse(check.same_place(None, "Track 107-109"))
        self.assertEqual(check.desk_block_of("OS Switch 225c", {"OS Switch 225"}), "OS Switch 225")
        self.assertEqual(check.desk_block_of("OS Switch 107", {"OS Switch 107"}), "OS Switch 107")


if __name__ == "__main__":
    unittest.main()
