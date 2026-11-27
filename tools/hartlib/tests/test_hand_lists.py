"""hartlib.hand_lists, the one reader of block_overrides.csv, main_lines.csv, mast_cells.csv and the USS board's grid
(naming-layers step 6): each reads the committed file as its old reader did, stops on a bad row naming the file and
line, and the old readers (block_override_rows, build_main_route, layout_facts) are its wrappers."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent / "src"), str(ROOT / "tools/schematic"), str(ROOT / "jmri/layouts/hart/scripts")]
from hartlib import hand_lists, paths, railroad  # noqa: E402

OVERRIDES = paths.LAYOUT_DATA / "schematic" / hand_lists.OVERRIDES_NAME


class Temp(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def copy(self, source: Path, edit=None) -> Path:
        out = self.tmp / source.name
        text = source.read_text(encoding="utf-8")
        out.write_text(edit(text) if edit else text, encoding="utf-8")
        return out


class BlockOverrides(Temp):
    def test_the_committed_file(self):
        rows = hand_lists.read_block_overrides(OVERRIDES)
        self.assertEqual({r["kind"] for r in rows}, set(hand_lists.OVERRIDE_KINDS))
        track = next(r for r in rows if r["kind"] == "track" and r["id"] == "os:15")
        self.assertEqual((track["block"], track["switch_a"], track["switch_b"]), ("OS Switch 15", "13", "15"))
        self.assertEqual(hand_lists.read_block_overrides(OVERRIDES, ("split",)),
                         [r for r in rows if r["kind"] == "split"])

    def test_a_bad_row_stops_naming_the_file_and_line(self):
        path = self.copy(OVERRIDES, lambda t: t + "1,track,13,15,,,OS Switch 15,,,\n")
        with self.assertRaisesRegex(hand_lists.HandListError, r"block_overrides.csv: line \d+ \(level 1, kind track\): "
                                    "block 'OS Switch 15' is no OS block ID"):
            hand_lists.read_block_overrides(path)
        with self.assertRaisesRegex(ValueError, "no kind nope"):
            hand_lists.read_block_overrides(OVERRIDES, ("nope",))

    def test_block_override_rows_wraps_it_with_its_own_error(self):
        import block_override_rows as bor
        self.assertEqual(bor.read_block_overrides(OVERRIDES), hand_lists.read_block_overrides(OVERRIDES))
        path = self.copy(OVERRIDES, lambda t: t.replace("level,kind", "lvl,kind", 1))
        with self.assertRaisesRegex(bor.MapError, "block_overrides.csv: columns"):
            bor.read_block_overrides(path)
        with self.assertRaisesRegex(bor.MapError, "no OS block ID"):
            bor.os_block_name("1", "OS Switch 7", {})


class MainLines(Temp):
    NAMES = {("1", "block:33A-35A"): "Track Princess Lead", ("1", "block:39B-helix"): "Track Helix Outer"}

    def lines(self, *rows: str) -> Path:
        path = self.tmp / hand_lists.MAIN_LINES_NAME
        path.write_text(",".join(hand_lists.MAIN_LINE_COLUMNS) + "\n" + "".join(r + "\n" for r in rows),
                        encoding="utf-8")
        return path

    def test_the_committed_file(self):
        for sheet in hand_lists.SHEETS:
            with self.subTest(sheet):
                rows = hand_lists.read_main_lines(sheet)
                self.assertTrue(rows)
                self.assertFalse([r for r in rows for c in hand_lists.STOP_CELLS if "block:" in r[c]])

    def test_stops_come_back_by_the_name_stores_names(self):
        path = self.lines("staging,A,1,35@block:33A-35A,block:39B-helix,,,yes,")
        row, = hand_lists.read_main_lines("staging", path, self.NAMES)
        self.assertEqual((row["via"], row["to"]), ("35@Princess Lead", "Helix Outer"))

    def test_a_track_by_name_or_an_unknown_id_stops(self):
        for stop, msg in (("35@East Lead", "names a track by its name"), ("block:9X-9Y", "no block of the device")):
            with self.subTest(stop), self.assertRaisesRegex(hand_lists.HandListError, msg):
                hand_lists.read_main_lines("staging", self.lines(f"staging,A,1,{stop},5,,,,"), self.NAMES)

    def test_build_main_route_wraps_it_with_its_own_error(self):
        import build_main_route
        self.assertEqual(build_main_route.read_lines("main_upper"), hand_lists.read_main_lines("main_upper"))
        with self.assertRaisesRegex(build_main_route.RouteError, "unknown sheet 'upper'"):
            build_main_route.read_lines("upper")


class UssBoard(Temp):
    def folder(self, edit_cells=None) -> Path:
        for name in (hand_lists.MAST_CELLS, hand_lists.USS_CELLS, hand_lists.USS_PLANTS):
            shutil.copyfile(paths.LAYOUT_DATA / name, self.tmp / name)
        if edit_cells:
            p = self.tmp / hand_lists.MAST_CELLS
            p.write_text(edit_cells(p.read_text(encoding="utf-8")), encoding="utf-8")
        return self.tmp

    def test_the_committed_files(self):
        cells = hand_lists.read_mast_cells()
        self.assertEqual(cells[0].mast, "Mast 4RA")
        self.assertEqual(len({c.mast for c in cells}), len(cells))
        plants = hand_lists.read_uss_plants()
        grid = hand_lists.read_uss_cells()
        self.assertTrue(all(grid[xy]["tracks"] for xy in plants))

    def test_a_bad_mast_cell_stops(self):
        data = self.folder(lambda t: t + "Mast 99L,1,1,LEFT,W,d1,,,,\n")
        with self.assertRaisesRegex(hand_lists.HandListError, r"mast_cells.csv line \d+ \(Mast 99L\): uss_head"):
            hand_lists.read_mast_cells(data)

    def test_a_bad_header_short_row_or_number_stops_naming_the_line(self):
        for edit, msg in ((lambda t: t.replace("mast,x,y", "mast,col,y", 1), r"mast_cells.csv: columns mast,x,y"),
                          (lambda t: t + "Mast 99L,1,1,LEFT,W,h2\n", r"mast_cells.csv line \d+: 10 fields, not 6"),
                          (lambda t: t + "Mast 99L,1,1,LEFT,W,h2,,,,,x\n", r"mast_cells.csv line \d+: 10 fields, not 11"),
                          (lambda t: t + "Mast 99L,one,1,LEFT,W,h2,,,,\n",
                           r"mast_cells.csv line \d+ \(Mast 99L\): x and y are whole numbers, not 'one'")):
            with self.subTest(msg), self.assertRaisesRegex(hand_lists.HandListError, msg):
                hand_lists.read_mast_cells(self.folder(edit))

    def test_layout_facts_reads_through_it(self):
        import layout_facts
        self.assertIs(layout_facts.MastCell, hand_lists.MastCell)
        self.assertEqual(layout_facts.load_mast_cells(), hand_lists.read_mast_cells())
        self.assertEqual(layout_facts.load_uss_plants(), hand_lists.read_uss_plants())


class RetiredMasts(Temp):
    """read_retired_masts (step 13): the committed file reads, a bad row stops, and mast_plan.read_retired wraps it."""

    def test_the_committed_file(self):
        retired = hand_lists.read_retired_masts()
        self.assertTrue(retired)
        self.assertTrue(all(m.startswith("Mast ") for m in retired))
        import mast_plan
        from map_error import MapError
        self.assertEqual(mast_plan.read_retired(), retired)
        self.assertEqual(mast_plan.RETIRED, hand_lists.RETIRED_MASTS)
        path = self.copy(hand_lists.RETIRED_MASTS, lambda t: t.replace("system_name", "sysname", 1))
        with self.assertRaisesRegex(hand_lists.HandListError, f"{hand_lists.RETIRED_MASTS.name}: columns"):
            hand_lists.read_retired_masts(path)
        with self.assertRaisesRegex(MapError, f"{hand_lists.RETIRED_MASTS.name}: columns"):
            mast_plan.read_retired(path)

    def test_an_ordinal_given_twice_stops_naming_the_line(self):
        first = next(iter(hand_lists.read_retired_masts().items()))
        path = self.copy(hand_lists.RETIRED_MASTS, lambda t: t + f"Mast 999X,{first[1]},,\n")
        with self.assertRaisesRegex(hand_lists.HandListError, r"line \d+: 'Mast 999X' .* reuses an ordinal"):
            hand_lists.read_retired_masts(path)


class SheetRows(Temp):
    def test_the_committed_file_and_build_staging_sets(self):
        rows = hand_lists.read_sheet_rows()
        self.assertTrue(rows)
        self.assertTrue(all(set(hand_lists.SHEET_COLUMNS) <= set(r) for _line, r in rows))
        import build_staging_sets
        _areas, stations = build_staging_sets.read_masters()
        self.assertEqual([s.name for s in build_staging_sets.read_sheets(stations)], [r["sheet"] for _l, r in rows])
        path = self.copy(hand_lists.SHEETS_FILE, lambda t: t.replace("stations", "stops", 1))
        with self.assertRaisesRegex(railroad.FactsError, "no column stations"):
            hand_lists.read_sheet_rows(path)
        with self.assertRaisesRegex(build_staging_sets.SetsError, "no column stations"):
            build_staging_sets.read_sheets(stations, path)


class PanelItems(Temp):
    def test_the_committed_file_and_panel_items_load(self):
        data = hand_lists.read_panel_items()
        self.assertTrue(data["items"])
        import panel_items
        self.assertEqual(panel_items.ITEMS, hand_lists.PANEL_ITEMS)
        self.assertEqual(panel_items.load(), panel_items.load(hand_lists.PANEL_ITEMS))
        self.assertEqual(panel_items.load()["items"], data["items"])

    def test_a_file_that_does_not_parse_stops(self):
        path = self.copy(hand_lists.PANEL_ITEMS, lambda t: t[:-10])
        with self.assertRaisesRegex(hand_lists.HandListError, f"cannot read {hand_lists.PANEL_ITEMS.name}"):
            hand_lists.read_panel_items(path)
        import panel_items
        with self.assertRaisesRegex(panel_items.ItemsError, f"cannot read {hand_lists.PANEL_ITEMS.name}"):
            panel_items.load(path)
        with self.assertRaisesRegex(panel_items.ItemsError, "cannot read"):
            panel_items.load(self.tmp / "none.json")


class PanelLamps(Temp):
    def test_the_committed_file(self):
        lamps = hand_lists.read_panel_lamps()
        self.assertEqual([lamp.system_name for lamp in lamps], ["M2S1567", "IS:SML_MODE", "IS:TRACK_POWER", "IH9990"])
        self.assertEqual({(lamp.layer, lamp.icon) for lamp in lamps}, {("sensor", "sensor"), ("head", "signalhead")})

    def stops(self, edit, pattern: str) -> None:
        path = self.copy(hand_lists.PANEL_LAMPS, edit)
        with self.assertRaisesRegex(hand_lists.HandListError, pattern):
            hand_lists.read_panel_lamps(path)

    def test_a_missing_file_stops(self):
        with self.assertRaisesRegex(hand_lists.HandListError, "cannot read none.csv"):
            hand_lists.read_panel_lamps(self.tmp / "none.csv")

    def test_a_missing_column_stops(self):
        self.stops(lambda t: t.replace(",jmri_comment", "", 1), r"columns \[.*\], not \[")

    def test_a_short_row_stops(self):
        self.stops(lambda t: t.rstrip("\n") + "\nIS:X,sensor\n", r"line 6: not 7 fields")

    def test_an_empty_cell_stops(self):
        self.stops(lambda t: t.replace(",Bridge HBLOOP,", ",,", 1), r"line 2: user_name empty")

    def test_a_system_name_listed_twice_stops(self):
        self.stops(lambda t: t.replace("IS:TRACK_POWER", "IS:SML_MODE", 1),
                   r"line 4: system_name 'IS:SML_MODE' is listed twice")

    def test_a_user_name_listed_twice_stops(self):
        self.stops(lambda t: t.replace(",Track Power,", ",SML Mode,", 1), r"line 4: user_name 'SML Mode' is listed twice")

    def test_an_unknown_layer_stops(self):
        self.stops(lambda t: t.replace("IH9990,head,", "IH9990,mast,", 1), r"line 5: layer 'mast' is not one of")

    def test_an_icon_not_its_layers_stops(self):
        self.stops(lambda t: t.replace(",field,signalhead,", ",field,sensor,", 1),
                   r"line 5: icon 'sensor'; a head lamp's is signalhead")

    def test_an_unknown_assignment_stops(self):
        self.stops(lambda t: t.replace(",virtual,", ",spare,", 1), r"line 3: assignment 'spare' is not one of")

    def test_a_file_with_no_lamps_stops(self):
        self.stops(lambda t: t.splitlines()[0] + "\n", "no lamps")


class SourcesStations(unittest.TestCase):
    def test_the_stations_file_is_a_source(self):
        self.assertEqual(railroad.Sources.under(Path("/x")).stations, Path("/x/schematic/stations.csv"))
        self.assertTrue(railroad.Sources.under().stations.is_file())


if __name__ == "__main__":
    unittest.main()
