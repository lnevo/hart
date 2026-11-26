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
        self.assertIn("Barn;Engine House", {r["cp"] for r in rows})
        self.assertFalse([r for r in rows if r["cp"].startswith(("st:", "cp:"))])
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
        turnouts = [r for r in devices.load() if r["layer"] == "turnout"]
        self.assertEqual(len(turnouts), 118)
        for r in turnouts:
            number = r["id"].split(":")[1]
            self.assertEqual(r["cp"], "", r["user_name"])
            self.assertEqual(places.switch_place(r["level"], number), want.get((r["level"], number), ""), r["id"])
            self.assertEqual(devices.place(r), places.names(want.get((r["level"], number), "")), r["id"])

    def test_a_switch_in_two_stations_takes_its_desk_area(self):
        self.assertEqual(places.switch_place(1, 3), "st:brick")            # also in West Yard, of the Brick area
        self.assertEqual(places.switch_place("1", "9"), "st:engine-house")  # also in Barn; a desk area of its own
        self.assertEqual(places.switch_place("1", "5"), "st:plane")         # staging's interlocking Brick has it
        self.assertEqual(places.switch_place("2", "101"), "")               # a local switch

    def test_a_cp_put_back_on_a_turnout_row_stops(self):
        rows = [dict(r) for r in devices.load()]
        for ident, cp in (("switch:107", "CP 107"), ("dcc:1", "Brick")):
            with self.subTest(ident):
                changed = [dict(r, cp=cp) if r["id"] == ident else r for r in rows]
                with self.assertRaisesRegex(devices.DevicesError, "a turnout row has no cp"):
                    devices.check_rows(changed)
        devices.check_rows(rows)


if __name__ == "__main__":
    unittest.main()
