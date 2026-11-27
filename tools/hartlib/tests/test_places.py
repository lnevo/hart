"""hartlib.places (ADR-039 lane L4c): place ids in the cp cells, each read back to the names the builders used
before. hartlib.occupancy_bindings has its own test (test_occupancy_bindings.py)."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import devices, level_masts, places  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

CP_FILES = (devices.FIELD, devices.MASTER, level_masts.PATH)


def cp_cells(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r["cp"] for r in csv.DictReader(fh)]


class PlacesTest(unittest.TestCase):
    def test_every_cp_item_of_the_repo_files_is_a_known_id(self):
        known = places.table().by_id
        for path in CP_FILES:
            items = {p for c in cp_cells(path) for p in c.split(places.LIST) if c}
            self.assertTrue(items, path.name)
            self.assertEqual(sorted(i for i in items if i not in known), [], path.name)

    def test_the_cells_read_back_as_they_are(self):
        # ids -> names -> ids is the identity on every cell, so a rebuild writes the same bytes (staging's names that
        # are also a staging interlocking's go to the station, as every cell has them)
        for path in CP_FILES:
            for cell in cp_cells(path):
                self.assertEqual(places.ids(places.names(cell)), cell, path.name)

    def test_names(self):
        self.assertEqual(places.names("st:barn;st:engine-house"), "Barn;Engine House")
        self.assertEqual(places.names("st:princess;cp:127"), "Princess;CP 127")
        self.assertEqual(places.names(""), "")
        self.assertEqual(places.ids("Brick;West Yard"), "st:brick;st:west-yard")
        self.assertEqual(places.ids("CP 225"), "cp:225")

    def test_a_staging_interlocking_keeps_its_id_and_name(self):
        t = places.table()
        self.assertEqual(t.by_id["cp:brick"], "Brick")
        self.assertEqual(t.by_name["Brick"], "st:brick")

    def test_an_unknown_id_stops_and_a_plain_name_is_kept(self):
        with self.assertRaises(FactsError):
            places.names("st:nowhere", "x line 2")
        self.assertEqual(places.names("CP 1"), "CP 1")        # a test's own place name
        self.assertEqual(places.ids("CP 1"), "CP 1")

    def test_readers_see_names(self):
        rows = devices.load()
        self.assertIn("Barn;Engine House", {r.cp for r in rows})
        self.assertFalse([r for r in rows if r.cp.startswith(("st:", "cp:"))])
        masts = level_masts.read()
        self.assertIn("CP 107", {r["cp"] for r in masts})
        self.assertFalse([r for r in masts if r["cp"].startswith(("st:", "cp:"))])

    def test_the_master_writes_ids(self):
        text = devices.master_text([dict(dict.fromkeys(devices.COLUMNS, ""), cp="Barn;CP 107")])
        self.assertIn("st:barn;cp:107", text)

    def test_a_bad_id_column_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "stations.csv"
            bad.write_text("station_id,level,station\nBarn,1,Barn\n", encoding="utf-8")
            with self.assertRaises(FactsError):
                places._table(bad.read_bytes(), places.INTERLOCKINGS.read_bytes())
            bad.write_text("station_id,level,station\nst:a,1,A\nst:a,1,B\n", encoding="utf-8")
            with self.assertRaises(FactsError):
                places._table(bad.read_bytes(), places.INTERLOCKINGS.read_bytes())

    def test_an_empty_name_or_a_missing_column_stops(self):
        with self.assertRaisesRegex(FactsError, r"stations.csv line 2 \(no name, level 1\): station is empty"):
            places._table(b"station_id,level,station\nst:a,1,\n", b"cp_id,level,interlocking\n")
        with self.assertRaisesRegex(FactsError, "stations.csv: no column level"):
            places._table(b"station_id,station\nst:a,A\n", b"cp_id,level,interlocking\n")
        with self.assertRaisesRegex(FactsError, "stations.csv: not UTF-8 text"):
            places._table(b"station_id,level,station\nst:a,1,\xff\n", b"cp_id,level,interlocking\n")


NO_CPS = b"cp_id,level,interlocking\n"


class NameOnceTest(unittest.TestCase):
    """A station or control point name is given once on the railroad (ids() has no level to choose by), and the error
    names both rows; a staging interlocking named as a station of its own level is the one exception."""

    def test_the_repo_lists_pass(self):
        t = places.table()                   # raises on a name given twice
        shared = sorted(n for n in t.by_name if sum(1 for v in t.by_id.values() if v == n) > 1)
        self.assertEqual(shared, ["Barn", "Brick", "East End", "Princess"])     # the four staging interlockings
        for name in shared:
            ids = sorted(i for i, v in t.by_id.items() if v == name)
            self.assertEqual([i.split(":")[0] for i in ids], ["cp", "st"], name)
            self.assertTrue(t.by_name[name].startswith("st:"), name)

    def test_two_stations_of_one_name_on_a_level_stop_naming_both(self):
        with self.assertRaisesRegex(FactsError, r"stations.csv line 3 \(A, level 1\): station 'A' is the name of "
                                                r"stations.csv line 2 \(A, level 1\) as well"):
            places._table(b"station_id,level,station\nst:a,1,A\nst:b,1,A\n", NO_CPS)

    def test_a_name_on_two_levels_stops(self):
        with self.assertRaisesRegex(FactsError, r"line 3 \(A, level 2\).* is the name of .*line 2 \(A, level 1\)"):
            places._table(b"station_id,level,station\nst:a,1,A\nst:b,2,A\n", NO_CPS)
        with self.assertRaisesRegex(FactsError, r"interlockings.csv line 3 \(CP 1, level 3\): interlocking 'CP 1' "
                                                r"is the name of interlockings.csv line 2 \(CP 1, level 2\)"):
            places._table(b"station_id,level,station\n", b"cp_id,level,interlocking\ncp:1,2,CP 1\ncp:2,3,CP 1\n")

    def test_an_interlocking_may_carry_its_stations_name_on_its_level_only(self):
        t = places._table(b"station_id,level,station\nst:a,1,A\n", b"cp_id,level,interlocking\ncp:a,1,A\n")
        self.assertEqual((t.by_name["A"], t.by_id["cp:a"]), ("st:a", "A"))
        with self.assertRaisesRegex(FactsError, r"interlockings.csv line 2 \(A, level 2\).*stations.csv line 2"):
            places._table(b"station_id,level,station\nst:a,1,A\n", b"cp_id,level,interlocking\ncp:a,2,A\n")
        with self.assertRaisesRegex(FactsError, r"interlockings.csv line 3 \(A, level 1\): interlocking 'A' is the "
                                                r"name of interlockings.csv line 2 \(A, level 1\) as well"):
            places._table(b"station_id,level,station\nst:a,1,A\n",
                          b"cp_id,level,interlocking\ncp:a,1,A\ncp:b,1,A\n")


def copy_with_lists(data: Path, renames: dict[str, str]) -> devices.Files:
    """The repo's device pair, dictionary, masts.csv and lists copied under `data`, each station renamed in the
    copy's stations.csv by `renames` ({old name: new name})."""
    files = devices.pair_copy(data)
    folder = data / places.SCHEMATIC.name
    folder.mkdir()
    for f in (places.STATIONS, places.INTERLOCKINGS, level_masts.PATH):
        (folder / f.name).write_bytes(f.read_bytes())
    with (folder / places.STATIONS.name).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    for r in rows[1:]:
        r[2] = renames.get(r[2], r[2])
    with (folder / places.STATIONS.name).open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    return files


class CopyListsTest(unittest.TestCase):
    """A copied master or masts.csv reads (and writes) its cp cells by the lists beside it, not the repo's."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        self.files = copy_with_lists(self.data, {"Engine House": "Roundhouse"})
        self.folder = self.data / places.SCHEMATIC.name

    def test_table_and_names_take_the_copys_lists(self):
        self.assertEqual(places.lists_beside(self.files), self.folder)
        self.assertEqual(places.names("st:barn;st:engine-house", schematic=self.folder), "Barn;Roundhouse")
        self.assertEqual(places.names("st:barn;st:engine-house"), "Barn;Engine House")      # the repo's
        self.assertEqual(places.ids("Roundhouse", schematic=self.folder), "st:engine-house")
        self.assertEqual(places.ids("Roundhouse"), "Roundhouse")             # the repo has no such place
        self.assertIs(places.table(self.folder), places.table(self.folder))  # one Table per content

    def test_the_copied_master_reads_and_writes_by_its_lists(self):
        rows = devices.load(self.files)
        self.assertIn("Barn;Roundhouse", {r.cp for r in rows})
        self.assertNotIn("Barn;Engine House", {r.cp for r in rows})
        self.assertIn("Barn;Engine House", {r.cp for r in devices.load()})
        text = devices.master_text([r.cells() for r in rows], self.files)
        self.assertIn("st:barn;st:engine-house", text)
        self.assertNotIn("Roundhouse", text)
        devices.write_generated(devices.generated_rows(self.files), self.files)
        self.assertEqual(self.files.master.read_bytes(), devices.MASTER.read_bytes())   # read back byte for byte

    def test_the_copied_masts_file_reads_by_its_lists(self):
        masts = level_masts.read(self.folder / level_masts.PATH.name)
        repo = level_masts.read()
        self.assertEqual(len(masts), len(repo))
        renamed = [(a["cp"], b["cp"]) for a, b in zip(masts, repo) if a["cp"] != b["cp"]]
        self.assertTrue(renamed)
        self.assertTrue(all(b.replace("Engine House", "Roundhouse") == a for a, b in renamed), renamed)

    def test_a_changed_list_is_read_again(self):
        self.assertIn("Barn;Roundhouse", {r.cp for r in devices.load(self.files)})
        stations = self.folder / places.STATIONS.name
        stations.write_text(stations.read_text(encoding="utf-8").replace("Roundhouse", "Engine Shed"),
                            encoding="utf-8")
        self.assertIn("Barn;Engine Shed", {r.cp for r in devices.load(self.files)})

    def test_a_copy_with_no_lists_reads_the_repos(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = devices.pair_copy(Path(tmp))
            self.assertIsNone(places.lists_beside(files))
            self.assertIn("Barn;Engine House", {r.cp for r in devices.load(files)})

    def test_an_id_the_copys_lists_lack_stops_the_load(self):
        stations = self.folder / places.STATIONS.name
        lines = stations.read_text(encoding="utf-8").splitlines(keepends=True)
        stations.write_text("".join(l for l in lines if not l.startswith("st:engine-house,")), encoding="utf-8")
        with self.assertRaisesRegex(devices.DevicesError, r"devices_generated.csv line \d+: st:engine-house is no "
                                                          "station_id"):
            devices.load(self.files)


class OneErrorTypeTest(unittest.TestCase):
    def test_devices_error_is_the_facts_error(self):
        self.assertIs(devices.DevicesError, FactsError)
        # a places fault reaches a caller that catches DevicesError
        with self.assertRaisesRegex(devices.DevicesError, "x line 2: st:nowhere"):
            places.names("st:nowhere", "x line 2")


# The cp each turnout row held before the owner dropped it (2026-11-25): staging's desk area, main and upper's
# interlocking. Every other turnout (a local switch of a yard or spur) had none.
BEFORE = {"1": {"st:brick": "1 3", "st:plane": "5", "st:barn": "7", "st:engine-house": "9 11 13",
                "st:south-yard": "15 17 19 21", "st:east-end": "23 25 27 29 31 33", "st:princess": "35 37 39"},
          "2": {"cp:107": "107 109 111 117 119", "cp:123": "123 125", "cp:127": "127 131"},
          "3": {"cp:201": "201 203 219 221", "cp:211": "211", "cp:217": "217", "cp:223": "223",
                "cp:225": "225 227 229"}}


class SwitchPlaceTest(unittest.TestCase):
    """A turnout row has no cp: places.switch_place gives its switch's place from the switch lists, the id its cp
    held, and hartlib.devices stops on a cp put back."""

    def test_every_switch_has_the_place_its_turnout_cp_held(self):
        want = {(lv, s): ident for lv, by in BEFORE.items() for ident, sw in by.items() for s in sw.split()}
        self.assertEqual(dict(places.switch_places()), want)
        turnouts = [r for r in devices.load() if r.layer == "turnout"]
        self.assertTrue(turnouts)
        for r in turnouts:
            number = r.id.split(":")[1]
            level = r.level_cell
            self.assertEqual(r.cp, "", r.user_name)
            self.assertEqual(places.switch_place(level, number), want.get((level, number), ""), r.id)
            self.assertEqual(devices.place(r), places.names(want.get((level, number), "")), r.id)

    def test_a_switch_in_two_stations_takes_its_desk_area(self):
        self.assertEqual(places.switch_place(1, 3), "st:brick")            # also in West Yard, of the Brick area
        self.assertEqual(places.switch_place("1", "9"), "st:engine-house")  # also in Barn; a desk area of its own
        self.assertEqual(places.switch_place("1", "5"), "st:plane")         # staging's interlocking Brick has it
        self.assertEqual(places.switch_place("2", "101"), "")               # a local switch

    def test_a_copy_of_the_lists_names_its_own_turnouts(self):
        """A device master read from a copy takes the copy's switch lists (places.lists_beside), not the repo's."""
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "schematic").mkdir()
            for f in (places.STATIONS, places.INTERLOCKINGS):
                (data / "schematic" / f.name).write_bytes(f.read_bytes())
            text = (data / "schematic" / places.INTERLOCKINGS.name).read_text(encoding="utf-8")
            row = next(line for line in text.splitlines() if line.startswith("cp:217,"))
            self.assertIn(",CP 217,217,", row)
            moved = text.replace(row, row.replace(",CP 217,217,", ',CP 217,"217,219",'))   # 219 is CP 201's too
            (data / "schematic" / places.INTERLOCKINGS.name).write_text(moved, encoding="utf-8")
            folder = places.lists_beside(data)
            self.assertEqual(folder, data / "schematic")
            self.assertEqual(places.lists_beside(None), None)
            with self.assertRaisesRegex(FactsError, "switch 219 .*is in"):     # the copy's lists are read
                places.switch_places(folder)
            (data / "schematic" / places.INTERLOCKINGS.name).write_text(text, encoding="utf-8")
            self.assertEqual(places.switch_place(3, 217, folder), "cp:217")

    def test_a_switch_in_no_list_place_and_a_bad_name_stop_cleanly(self):
        self.assertEqual(places.of({"layer": "turnout", "id": "switch:999", "level": "2", "cp": ""}), "")
        self.assertEqual(places.of({"layer": "turnout", "id": "switch:107", "level": "", "cp": ""}), "")

    def test_a_turnout_id_that_names_no_switch_stops(self):
        for ident in ("", "switch:", "switch:07", "switch:7a", "test:turnout:Switch 7", "os:7"):
            with self.subTest(ident), self.assertRaisesRegex(FactsError, rf"turnout 'Switch 7' \(level 2\): id "
                                                                         rf"'{ident}' is not switch:<n> or dcc:<n>"):
                places.of({"layer": "turnout", "id": ident, "level": "2", "cp": "", "user_name": "Switch 7"})

    def test_check_rows_holds_every_turnout_id_to_its_role(self):
        rows = [r.cells() for r in devices.load()]
        turnouts = [r for r in rows if r["layer"] == "turnout" and r["level"]]
        self.assertEqual({r["role"] for r in turnouts}, {"turnout", "lcc_alias"})      # every real row passes
        devices.check_rows(rows)
        switch = next(r for r in turnouts if r["role"] == "turnout")
        alias = next(r for r in turnouts if r["role"] == "lcc_alias")
        for row, ident, why in ((switch, "switch:07", "is not switch:<switch number>"),
                                (switch, "switch:1a", "is not switch:<switch number>"),
                                (switch, alias["id"], "is not switch:<switch number>"),
                                (alias, switch["id"], "is not dcc:<switch number>"),
                                (alias, "dcc:", "is not dcc:<switch number>")):
            with self.subTest(ident):
                changed = [dict(r, id=ident) if r is row else r for r in rows]
                with self.assertRaisesRegex(devices.DevicesError, rf"{row['user_name']} \(level {row['level']}, "
                                                                  rf"turnout\): id '{ident}' {why}"):
                    devices.check_rows(changed)
        changed = [dict(r, role="os") if r is switch else r for r in rows]
        with self.assertRaisesRegex(devices.DevicesError, rf"{switch['user_name']} .*a turnout row's role is turnout "
                                                          "or lcc_alias, not 'os'"):
            devices.check_rows(changed)

    def test_a_cp_put_back_on_a_turnout_row_stops(self):
        rows = [r.cells() for r in devices.load()]
        for ident, cp in (("switch:107", "CP 107"), ("dcc:1", "Brick")):
            with self.subTest(ident):
                changed = [dict(r, cp=cp) if r["id"] == ident else r for r in rows]
                with self.assertRaisesRegex(devices.DevicesError, "a turnout row has no cp"):
                    devices.check_rows(changed)
        devices.check_rows(rows)


if __name__ == "__main__":
    unittest.main()
